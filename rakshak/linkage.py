"""Cluster records that belong to the same patient, preferring no link to a wrong one."""
from collections import defaultdict

from .redaction import same_name
from .textutil import phonetic
from .vocab import GENERIC_NAME_PARTS

STRONG = ("AADHAAR", "ABHA", "MRN", "PAN", "INSURANCE", "EMAIL")


class Cluster:
    def __init__(self, index, clues):
        self.members = [index]
        self.ids = set(clues.ids)
        names = clues.names or (clues.others if len(clues.others) == 1 else [])
        self.names = list(names)
        self.relatives = list(clues.relatives)
        self.dobs = set(clues.dobs)
        self.villages = set(clues.villages)
        self.ages = list(clues.ages)
        year = max(clues.years, default=None)
        if year and not self.ages:
            self.ages = [year - d.year for d in sorted(clues.dobs)]

    def absorb(self, other):
        self.members += other.members
        self.ids |= other.ids
        self.names += [n for n in other.names if n not in self.names]
        self.relatives += [n for n in other.relatives if n not in self.relatives]
        self.dobs |= other.dobs
        self.villages |= other.villages
        self.ages += other.ages


def _any_name(left, right):
    return any(same_name(a, b) for a in left for b in right)


def _compatible(a, b):
    if a.names and b.names and not _any_name(a.names, b.names):
        return False
    if a.dobs and b.dobs and not a.dobs & b.dobs:
        return False
    first = {v for k, v in a.ids if k == "AADHAAR"}
    second = {v for k, v in b.ids if k == "AADHAAR"}
    return not (first and second and not first & second)


def _single_patient(clues):
    """A record naming several people (a log or index) must not link them."""
    groups = []
    for name in clues.names:
        if not any(same_name(name, seen) for seen in groups):
            groups.append(name)
    if groups:
        # A bundle may carry several identity numbers for its one named patient.
        return len(groups) == 1
    for kind in ("AADHAAR", "ABHA", "PAN"):
        if sum(k == kind for k, _ in clues.ids) > 1:
            return False
    if sum(k == "MRN" for k, _ in clues.ids) > 2 or sum(k == "PHONE" for k, _ in clues.ids) > 3:
        return False
    return True


class Linker:
    def __init__(self, clue_list):
        self.parent = list(range(len(clue_list)))
        self.clusters = {i: Cluster(i, c) for i, c in enumerate(clue_list) if _single_patient(c)}

    def root(self, index):
        while self.parent[index] != index:
            self.parent[index] = self.parent[self.parent[index]]
            index = self.parent[index]
        return index

    def union(self, i, j):
        a, b = self.root(i), self.root(j)
        if a == b:
            return True
        if not _compatible(self.clusters[a], self.clusters[b]):
            return False
        a, b = min(a, b), max(a, b)
        self.clusters[a].absorb(self.clusters.pop(b))
        self.parent[b] = a
        return True

    def _shared(self, kinds):
        index = defaultdict(list)
        for i in sorted(self.clusters):
            for item in sorted(self.clusters[i].ids):
                if item[0] in kinds:
                    index[item].append(i)
        return [index[key] for key in sorted(index)]

    def _by_identifier(self, kinds):
        for members in self._shared(kinds):
            # Named records first, so unnamed ones cannot bridge two people.
            named = [i for i in members if self.clusters[self.root(i)].names]
            anchors = []
            for i in named:
                if not any(self.union(anchor, i) for anchor in anchors):
                    anchors.append(i)
            distinct = {self.root(a) for a in anchors}
            if len(distinct) <= 1:
                for i in members:
                    self.union(anchors[0] if anchors else members[0], i)

    def _by_attributes(self):
        blocks = defaultdict(list)
        for i in sorted(self.clusters):
            for name in self.clusters[i].names:
                for word in name:
                    if phonetic(word) not in GENERIC_NAME_PARTS:
                        blocks[phonetic(word)[:3]].append(i)
        for key in sorted(blocks):
            # Compare clusters, not records, so large exports stay fast.
            members = list(dict.fromkeys(self.root(i) for i in blocks[key]))
            for position, i in enumerate(members):
                for j in members[position + 1:]:
                    a, b = self.root(i), self.root(j)
                    if a != b and self._evidence(self.clusters[a], self.clusters[b]):
                        self.union(a, b)

    @staticmethod
    def _evidence(a, b):
        if not _any_name(a.names, b.names):
            return False
        full = any(same_name(x, y) and min(len(x), len(y)) >= 2 for x in a.names for y in b.names)
        relative = _any_name(a.relatives, b.relatives)
        if a.relatives and b.relatives and not relative:
            return False
        village = bool(a.villages & b.villages)
        close = any(abs(x - y) <= 2 for x in a.ages for y in b.ages)
        if relative:
            return True
        return full and (bool(a.dobs & b.dobs) or (village and close))

    def _attach_fragments(self):
        """'Meera, W/o Rajan' joins a patient only if exactly one candidate fits."""
        for i in sorted(self.clusters):
            if i not in self.clusters:
                continue
            fragment = self.clusters[i]
            if fragment.ids or not fragment.names or not fragment.relatives:
                continue
            fits = [j for j in sorted(self.clusters) if j != i
                    and _any_name(fragment.names, self.clusters[j].names)
                    and _any_name(fragment.relatives, self.clusters[j].relatives)]
            if len(fits) == 1:
                self.union(i, fits[0])

    def run(self):
        self._by_identifier(set(STRONG))
        self._by_identifier({"PHONE"})
        self._by_attributes()
        self._attach_fragments()
        return self.clusters


def cluster_key(cluster):
    """Stable text from which the keyed pseudonym is derived; None means unlinked."""
    for kind in STRONG + ("PHONE",):
        values = sorted(v for k, v in cluster.ids if k == kind)
        if values:
            return f"{kind}:{values[0]}"
    if cluster.names and cluster.relatives and (len(cluster.members) > 1 or cluster.villages or cluster.dobs):
        name = min(" ".join(phonetic(w) for w in n) for n in cluster.names)
        relative = min(" ".join(phonetic(w) for w in n) for n in cluster.relatives)
        extra = min([str(d) for d in cluster.dobs] or sorted(cluster.villages) or [""])
        return f"PERSON:{name}|{relative}|{extra}"
    return None
