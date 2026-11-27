"""Two-pass pipeline: learn who is in the data, then rewrite every file."""
import csv
import hashlib
import io
import json
import re
import time
from pathlib import Path, PurePosixPath

from . import dates
from .config import load_policy
from .detection import Lexicon, detect
from .fields import classify
from .ingestion import Quarantine, discover_files, load
from .linkage import Linker, cluster_key
from .pseudonymization import deterministic_offset, digest, get_secret, pseudonym
from .records import list_parents, split, walk
from .redaction import Harvester, Redactor
from .reporting import write_report
from .validation import has_residual_identifier


class Context:
    def __init__(self, policy):
        self.policy = policy
        self.lexicon = Lexicon()
        self.entities = {}
        self.owners = {}


class Record:
    def __init__(self, document, locator, body):
        self.document, self.locator, self.body = document, locator, body
        self.clues = None
        self.pid = None
        self.rare = False


def _flatten(document):
    if document.kind == "text":
        return [document.data]
    if document.kind == "table":
        return [cell for row in document.data for cell in row]
    found, stack = [], [document.data]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
        elif isinstance(node, str):
            found.append(node)
    return found


def _harvest(record, lexicon):
    document = record.document
    harvester = Harvester(lexicon, document.order)
    if document.kind == "text":
        harvester.text(record.body)
    elif document.kind == "table":
        header = document.data[0]
        for i, cell in enumerate(record.body):
            harvester.value(cell, header[i] if i < len(header) else "", (),
                            document.roles[i] if i < len(document.roles) else "text", None)
    else:
        walk(record.body, harvester, parents=list_parents(record.locator))
    # File names often carry the admission or patient number of a note.
    if record.locator == "doc":
        stem = re.sub(r"_+", " ", PurePosixPath(document.relative).stem)
        for start, end, kind in detect(stem):
            if kind in {"MRN", "PHONE"}:
                harvester.clues.add_id(kind, stem[start:end])
    record.clues = harvester.finish()


def _date_orders(documents):
    """Infer day/month order per file, then borrow it from files in the same folder family."""
    families = {}
    for document in documents:
        document.order = dates.infer_order(_flatten(document))
        family = re.split(r"[_\-. ]", PurePosixPath(document.relative).name)[0]
        if document.order:
            families.setdefault(family, []).append(document.order)
    for document in documents:
        if not document.order:
            votes = families.get(re.split(r"[_\-. ]", PurePosixPath(document.relative).name)[0], [])
            document.order = "mdy" if votes.count("mdy") > votes.count("dmy") else "dmy"


def _link(records, context):
    clusters = Linker([r.clues for r in records]).run()
    keyed = {}
    for index in sorted(clusters):
        key = cluster_key(clusters[index])
        if key:
            keyed[index] = key
    codes = {i: set().union(*(records[m].clues.codes for m in clusters[i].members)) for i in keyed}
    frequency = {}
    for found in codes.values():
        for code in found:
            frequency[code] = frequency.get(code, 0) + 1
    limit = context.policy["rare_diagnosis_max_patients"]
    # Rarity is only meaningful when there is a population to compare against.
    comparable = len(keyed) > limit * 5
    used = set()
    for index, key in keyed.items():
        pid = pseudonym(key)
        while pid in used:
            key += "+"
            pid = pseudonym(key)
        used.add(pid)
        rare = comparable and any(frequency[c] <= limit for c in codes[index])
        for member in clusters[index].members:
            records[member].pid, records[member].rare = pid, rare
        for item in sorted(clusters[index].ids):
            context.owners.setdefault(item, pid)


def _safe_path(relative, redactor):
    parts = []
    for position, part in enumerate(PurePosixPath(relative).parts):
        suffix = PurePosixPath(part).suffix
        stem = part[: len(part) - len(suffix)] if suffix else part
        readable = re.sub(r"[_+]+", " ", stem)
        found = detect(readable, redactor.lexicon) or re.search(r"\d{6,}", readable)
        if found:
            part = "file_" + digest("filename", f"{relative}|{position}").hex()[:12] + suffix.lower()
        parts.append(part)
    return PurePosixPath(*parts)


def _rebuild(document, outputs, header_redactor):
    if document.kind == "text":
        return outputs[0][1].replace("\n", document.newline)
    if document.kind == "table":
        stream = io.StringIO(newline="")
        writer = csv.writer(stream, delimiter=document.delimiter, lineterminator=document.newline)
        header = []
        for cell in document.data[0]:
            new = header_redactor.text(cell)
            base, number = new, 2
            while new != cell and new in header:
                new = f"{base} {number}"
                number += 1
            header.append(new)
        writer.writerow(header)
        writer.writerows(row for _, row in outputs)
        return stream.getvalue()
    data = document.data
    if not outputs:
        data = walk(data, header_redactor)
    elif outputs[0][0] == "doc":
        data = outputs[0][1]
    else:
        replaced = {locator: body for locator, body in outputs}
        if isinstance(data, list):
            data = [replaced[f"/{i}"] for i in range(len(data))]
        else:
            rebuilt = {}
            for key, value in data.items():
                escaped = str(key).replace("~", "~0").replace("/", "~1")
                if f"/{escaped}/0" in replaced:
                    rebuilt[key] = [replaced[f"/{escaped}/{i}"] for i in range(len(value))]
                else:
                    # Export metadata and other values outside the records.
                    rebuilt.update(walk({key: value}, header_redactor))
            data = rebuilt
    separators = None if document.indent else (",", ":")
    return json.dumps(data, ensure_ascii=False, indent=document.indent, separators=separators) + "\n"


def _contains(body, pid):
    return pid in (body if isinstance(body, str) else json.dumps(body, ensure_ascii=False))


def run_pipeline(input_dir: Path, output_dir: Path):
    start = time.monotonic()
    get_secret()
    input_dir, output_dir = Path(input_dir).resolve(), Path(output_dir).resolve()
    if not input_dir.is_dir():
        raise ValueError("invalid_input_directory")
    if output_dir == input_dir or input_dir in output_dir.parents:
        raise ValueError("output_inside_input")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("output_directory_not_empty")
    sanitized_dir = output_dir / "sanitized"
    sanitized_dir.mkdir(parents=True, exist_ok=True)

    policy = load_policy()
    context = Context(policy)
    entries, documents = [], []
    for path in discover_files(input_dir):
        entry = {"input_sha256": None, "output": None, "status": "quarantined"}
        entries.append(entry)
        try:
            if path.is_symlink():
                raise Quarantine("symbolic_link")
            if path.stat().st_size > policy["max_file_mb"] * 1024 * 1024:
                hasher = hashlib.sha256()
                with path.open("rb") as handle:
                    for chunk in iter(lambda: handle.read(1 << 20), b""):
                        hasher.update(chunk)
                entry["input_sha256"] = hasher.hexdigest()
                raise Quarantine("file_too_large")
            raw = path.read_bytes()
            entry["input_sha256"] = hashlib.sha256(raw).hexdigest()
            document = load(path, path.relative_to(input_dir).as_posix(), raw, policy)
            document.entry = entry
            documents.append(document)
        except Quarantine as exc:
            entry["reason"] = str(exc)
        except Exception:
            entry["reason"] = "processing_error"

    _date_orders(documents)
    records, usable = [], []
    for document in documents:
        try:
            if document.kind == "table":
                document.roles = [classify(h) for h in document.data[0]]
            own = [Record(document, locator, body) for locator, body in split(document)]
            for record in own:
                _harvest(record, context.lexicon)
            records.extend(own)
            document.records = own
            usable.append(document)
        except Exception:
            document.entry["reason"] = "processing_error"

    context.lexicon.compile_places()
    _link(records, context)

    exported, used_paths, generalized = [], set(), 0
    for document in usable:
        try:
            outputs, claims, count = [], [], 0
            for record in document.records:
                key = record.pid or f"{document.relative}#{record.locator}"
                offset = deterministic_offset(key, policy["date_shift_max_days"], policy["date_shift_min_days"])
                redactor = Redactor(context, record.clues, record.pid, offset, document.order, record.rare)
                redactor.locator = record.locator
                body = redactor.record(record.body, document)
                pid = record.pid
                if pid and not _contains(body, pid):
                    if document.kind == "text":
                        body = f"Patient: {pid}\n{body}"
                    else:
                        pid = None
                count += redactor.generalized
                outputs.append((record.locator, body))
                has_identity = record.clues.ids or record.clues.names or record.clues.others or record.pid
                if has_identity:
                    claims.append((record.locator, pid))

            file_key = f"file#{document.relative}"
            offset = deterministic_offset(file_key, policy["date_shift_max_days"], policy["date_shift_min_days"])
            blank = Harvester(context.lexicon, document.order).clues
            outside = Redactor(context, blank, None, offset, document.order, False)
            result = _rebuild(document, outputs, outside)
            if has_residual_identifier(result):
                raise Quarantine("residual_identifier_detected")

            safe = _safe_path(document.relative, outside)
            number = 2
            while safe.as_posix().casefold() in used_paths:
                safe = safe.with_name(f"{safe.stem}_{number}{safe.suffix}")
                number += 1
            used_paths.add(safe.as_posix().casefold())
            destination = sanitized_dir.joinpath(*safe.parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(result.encode("utf-8"))
            name = "sanitized/" + safe.as_posix()
            document.entry.update(output=name, status="sanitized")
            document.entry.pop("reason", None)
            generalized += count
            exported.extend({"file": name, "loc": loc, "patient": pid} for loc, pid in claims)
        except Quarantine as exc:
            document.entry["reason"] = str(exc)
        except Exception:
            document.entry["reason"] = "processing_error"

    write_report(output_dir, entries, exported, context.entities, generalized, time.monotonic() - start)
    sanitized = sum(e["status"] == "sanitized" for e in entries)
    print(f"Raksha completed: {len(entries)} files; {sanitized} sanitized; "
          f"{len(entries) - sanitized} quarantined; {len(exported)} records")
