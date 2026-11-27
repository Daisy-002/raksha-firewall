"""Context-aware detection of personal data as non-overlapping spans.

The same detector is used twice: once to harvest linking clues and the global
name lexicon, and again to redact. Spans are (start, end, type) tuples.
"""
import re

from .textutil import ABBREVIATIONS, DEVANAGARI, TOKEN, fold_digits, phonetic, similar_word, skeleton
from .vocab import DOCTOR_TITLES, GENERIC_NAME_PARTS, HONORIFICS, PREFIXES, STOPWORDS

_SEP = r"[ \t._-]{0,2}"
# Order matters: longer and more specific identifiers are claimed first.
ID_PATTERNS = [
    ("EMAIL", re.compile(r"(?<![\w.+-])[\w.+-]+@[A-Za-z][\w-]*(?:\.[\w-]+)*")),
    ("INSURANCE", re.compile(r"(?<![A-Z0-9])(?:PMJAY|POL|TPA|CGHS|ESIC?)(?:[-/][A-Z]{2})?(?:[-/]\d{2,}){1,3}(?![\d])", re.I)),
    ("ABHA", re.compile(r"(?<!\d)\d{2}[ -]?\d{4}[ -]\d{4}[ -]\d{4}(?!\d)|(?<![\d.])\d{14}(?![\d.])")),
    ("AADHAAR_MASKED", re.compile(r"(?<![A-Za-z0-9])(?:[Xx*•#]{4}[ -]?){1,2}\d{4}(?!\d)")),
    ("PHONE", re.compile(rf"(?<![\w.])(?:\+{_SEP}91{_SEP}|\(\+?91\){_SEP}|0091{_SEP}|91[ -]|0{_SEP})?[6-9](?:{_SEP}\d){{9}}(?![\d]|\.\d)")),
    ("AADHAAR", re.compile(r"(?<![\d.])\d{4}[ -]?\d{4}[ -]?\d{4}(?![\d]|\.\d)")),
    ("PHONE", re.compile(r"(?<![\w.])(?:[6-9]\d{1,3}[Xx*]{4,6}\d{2,4})(?!\w)|(?<![\d])\+91[ -]?\d{5}[ -]?\d{5}(?!\d)|(?<![\d.])0\d{2,4}-\d{6,8}(?!\d)")),
    ("PAN", re.compile(r"(?<![A-Za-z0-9])[A-Za-z]{5}\d{4}[A-Za-z](?![A-Za-z0-9])")),
    ("MRN", re.compile(
        r"(?<![A-Za-z0-9])(?:"
        # Known hospital-number prefixes in any case, then any upper-case prefix with digit groups.
        r"(?i:UHID|MRN|IPD|IP|OPD|ADM|CR|HOSP|REG)(?:[-/_]?\d{2,4}){0,2}[-/_]?\d{4,}"
        r"|[A-Z]{2,6}\d{0,4}(?:[-/_][A-Z]{1,4})?(?:[-/_]\d{2,4}){0,2}[-/_]\d{4,}"
        r")(?![A-Za-z0-9])")),
]
_ID_LABEL = re.compile(
    r"(?i)(?<![A-Za-z])(?:UHID|MRN|MR[ .]?No|Reg(?:istration|n)?[ .]*(?:No|Number|ID)|IPD?[ .]*(?:No|Number)|"
    r"Patient[ .]*(?:ID|No)|CR[ .]*No|Hosp(?:ital)?[ .]*(?:ID|No)|Admission[ .]*No|Policy[ .]*(?:No|Number)|"
    r"Member[ .]*ID|पंजीकरण[ ]*(?:सं\.?|संख्या)|आईपीडी[ ]*(?:सं\.?|संख्या))\.?[ \t]*[:#=\-]?[ \t]*"
    r"(?P<v>(?=[A-Za-z0-9/_-]*\d{3})[A-Za-z0-9][A-Za-z0-9/_-]{3,})")

# Other government and personal documents, recognised by their label.
_DOCUMENT_ID = re.compile(
    r"(?i)(?<![A-Za-z])(?:passport|voter[ ]?id|epic|driving[ ]licen[cs]e|DL|ration[ ]card|esic?|bank[ ]a/?c|account|"
    r"vehicle|ABHA|aadh?aar|adhaa?r|आधार)(?:[ ]*(?:no\.?|number|id|card|संख्या))?[ \t]*[:#=\-]?[ \t]*"
    r"(?P<v>(?=[A-Z0-9/ -]*\d{4})[A-Z]{0,4}[ -]?\d[A-Z0-9/-]*(?:[ ]\d{4,})*)")

# Address parts. District and state stay; everything finer is removed.
_PLACE = r"(?:[A-Z][A-Za-z'.-]*|[\u0900-\u097F]+)(?:[ ](?:[A-Z][A-Za-z'-]*|[\u0900-\u097F]+)){0,3}"
ADDRESS_PATTERNS = [
    ("HOUSE", re.compile(r"(?i)(?<![A-Za-z])(?:H\.?[ ]?No\.?|House(?:[ ]No\.?)?|Makan(?:[ ]No\.?)?|Flat(?:[ ]No\.?)?|Plot(?:[ ]No\.?)?|Qtr\.?(?:[ ]No\.?)?|मकान(?:[ ]*(?:नं\.?|संख्या))?)[ \t]*[:#-]?[ \t]*(?P<v>\d+[A-Za-z]?(?:[/-]\d+)*)")),
    ("LOCALITY", re.compile(r"(?<![A-Za-z])(?i:Mohalla|Moh\.|Colony of|Gali(?: No\.?)?|मोहल्ला|मुहल्ला)[ \t]*[:-]?[ \t]*(?P<v>" + _PLACE + r"|\d+)")),
    ("LOCALITY", re.compile(r"(?i)(?<![A-Za-z])(?P<v>Ward(?:[ ]No\.?)?[ ]?\d+)(?=[ ]*,[ ]*(?:Mohalla|near|Tehsil|Vill|Gram))")),
    ("LANDMARK", re.compile(r"(?<![A-Za-z])(?i:near|opp\.?|opposite|behind|beside|next to)[ \t]+(?P<v>[A-Z][A-Za-z'.-]*(?:[ ][A-Z][A-Za-z'-]*){0,3})")),
    ("LANDMARK", re.compile(r"(?:(?<=,)|^)[ ]*(?P<v>[\u0900-\u097F]+(?:[ ][\u0900-\u097F]+){0,3}[ ]के[ ](?:पास|पीछे|सामने|निकट))")),
    ("VILLAGE", re.compile(r"(?<![A-Za-z])(?i:Village|Vill\.?|Gram(?: Panchayat)?|Gaon|ग्राम|गांव|गाँव)(?![A-Za-z])[ \t]*[:\-–]?[ \t]*(?P<v>" + _PLACE + r")")),
    ("TEHSIL", re.compile(r"(?<![A-Za-z])(?i:Tehsil|Teh\.|Block|तहसील)[ \t]*[:-]?[ \t]*(?P<v>" + _PLACE + r")")),
]
# A number written after a phone label, in any grouping.
_PHONE_LABEL = re.compile(
    r"(?i)(?<![A-Za-z])(?:ph(?:one)?|mob(?:ile)?|contact(?:[ ]no\.?)?|tel|cell|whatsapp|call(?:[ ]me)?(?:[ ]on)?|संपर्क|मोबाइल|फोन)"
    r"\.?[ \t]*(?:no\.?|number)?[ \t]*[:#=\-]?[ \t]*(?P<v>\+?[(]?\d(?:[ ().-]{0,2}\d){9,13})(?!\d)")
_PIN = re.compile(r"(?:(?<=[A-Za-z\u097F])[ ]|(?i:\bPIN(?:[ ]?code)?[ \t]*[:=-]?[ \t]*)|[-–][ \t]*|(?<=,)[ \t]*|पिन[ ]*(?:कोड)?[ \t]*[:-]?[ \t]*)(?P<v>[1-9]\d{2}[ ]?\d{3})(?![\d.,]\d|\d)")
_ADDRESS_LINE = re.compile(r"(?im)^[ \t]*(?:Address|Residence|R/o|पता)[ \t]*[:\-]")

_NAME_LABEL = re.compile(
    r"(?i)(?<![A-Za-z])(?:patient(?:'s)?[ ]*(?:name)?|pt\.?(?:[ ]name)?|name(?:[ ]of(?:[ ]the)?[ ]patient)?|"
    r"mareez(?:[ ]ka[ ]naam)?|naam|beneficiary|मरीज़?[ ]*का[ ]*नाम|रोगी[ ]*का[ ]*नाम|नाम|report[ ]of|reg(?:arding)?\.?[ ]patient)"
    r"[ \t]*[:\-–=]?[ \t]+|(?<![A-Za-z])(?:patient(?:'s)?[ ]*(?:name)?|name|नाम)[ \t]*[:=\-–][ \t]*")
_RELATIVE_LABEL = re.compile(
    r"(?i)(?<![A-Za-z])(?:(?:[SDW][ ]?/[ ]?[Oo])|[Cc][ ]?/[ ]?[Oo]|"
    r"(?:son|daughter|wife|husband|care)[ ]of|(?:father|mother|husband|wife|guardian|attendant|relative|informant)"
    r"(?:'s)?(?:[ ]*name)?(?=[ \t]*[:\-–])|(?:पिता|पति|माता|पत्नी|अभिभावक)(?:/पति)?[ ]*का[ ]*नाम|पुत्री|पुत्र|पत्नी|आत्मज)"
    r"[ \t]*[:\-–]?[ \t]*")
_ACTION_LABEL = re.compile(
    r"(?i)(?<![A-Za-z])(?:called[ ]by|witnessed[ ]by|informed[ ]by|received[ ]by|signed[ ]by|raised[ ]by|"
    r"accompanied[ ]by|brought[ ]by|sample[ ]from|created[ ]by|prepared[ ]by|contact(?:[ ]person)?[ \t]*:|"
    r"(?:staff[ ]nurse|nurse|attender|caregiver)(?=[ \t:]+[A-Z\u0900-\u097F]))[ \t:]*")
_KIN_WORD = re.compile(
    r"(?<![A-Za-z])(?i:husband|wife|father|mother|son|daughter|brother|sister|uncle|aunt|neighbou?r|guardian|"
    r"relative|attendant|pati|patni|beta|beti|bhai)[ \t]+(?=[A-Z])")
_DOCTOR = re.compile(DOCTOR_TITLES + r"(?:\.[ \t]*|[ \t]+)(?:(?:[A-Z]\.[ ]?)*(?:[A-Z][A-Za-z'-]+|[\u0900-\u097F]+)(?:[ ](?:[A-Z][a-z'-]+)){0,2})")
_PROTECT = re.compile(r"(?i)\bASHA(?=[ -](?:worker|karyakarta|sahyogi|didi))|[A-Z][a-z]+(?:'s|’s)[ ](?:disease|syndrome|sign|palsy|lymphoma)")

_HINGLISH_AFTER = re.compile(
    r"(?i)^[ \t]+(?:(?:ka|ki|ke)[ ](?:bp|sugar|pulse|temp|fever|bukhar|dard|report|ilaj|condition|attendant|"
    r"blood)|ko[ ](?:\d+[ ](?:din|day|hafte|mahine)|bukhar|fever|khansi|dard|ulti|chakkar|admit|aaj|kal|"
    r"discharge|lekar|dikhaya|dawai)|ne[ ](?:bataya|kaha|bola|complain))")
_HINDI_AFTER = re.compile(r"^(?=[ \t]+साथ[ ](?:आ|थ))|^[ \t]+(?:को|का|की|के|ने)[ \t]+(?:\d+|बुखार|खांसी|दर्द|बीपी|शुगर|भर्ती|रिपोर्ट|छुट्टी)")


class Lexicon:
    """Names and places learned from the input itself (never from a built-in list)."""

    def __init__(self):
        self.names = {}
        self.skeletons = {}
        self.places = set()

    def add_name(self, name):
        for word in TOKEN.findall(name):
            key = phonetic(word)
            if len(key) < 3 or key in GENERIC_NAME_PARTS or word.casefold() in STOPWORDS:
                continue
            self.names.setdefault(key, word)
            self.skeletons.setdefault(skeleton(word), set()).add(word)

    def add_place(self, place):
        place = " ".join(place.split())
        if len(place) >= 4 and place.casefold() not in STOPWORDS:
            self.places.add(place)

    def knows(self, word):
        # "MD" is a medical degree; abbreviations count only next to a known name.
        if word.casefold() in STOPWORDS or word.casefold() in ABBREVIATIONS:
            return False
        key = phonetic(word)
        if len(key) < 3:
            return False
        if key in self.names:
            return True
        return any(similar_word(word, other) for other in sorted(self.skeletons.get(skeleton(word), ())))

    def compile_places(self):
        ordered = sorted(self.places, key=lambda p: (-len(p), p))
        self.place_pattern = re.compile(
            r"(?i)(?<![\w\u0900-\u097F])(?:" + "|".join(map(re.escape, ordered)) + r")(?![\w\u0900-\u097F])"
        ) if ordered else None


class Spans:
    def __init__(self):
        self.items = []

    def add(self, start, end, kind):
        if end > start and not any(start < e and s < end for s, e, _ in self.items):
            self.items.append((start, end, kind))


def _is_name_word(word):
    if word.casefold() in STOPWORDS or word.casefold() in HONORIFICS:
        return False
    return bool(DEVANAGARI.search(word)) or word[0].isupper()


def take_name(text, position, limit=4, allow_lower=False):
    """Read a person name starting at `position`; return (start, end) or None."""
    start = end = None
    count = 0
    while count < limit:
        match = TOKEN.search(text, position)
        if not match:
            break
        gap = text[position:match.start()]
        word = match.group()
        if count == 0:
            if gap.strip(" \t.:-–,\"'("):
                break
        elif gap not in (" ", ". ", ".", "  ", "-", "'"):
            break
        if word.casefold() in PREFIXES and count == 0:
            position = match.end()
            continue
        ok = _is_name_word(word) or (allow_lower and word.casefold() not in STOPWORDS
                                     and word.casefold() not in HONORIFICS)
        # Initials such as "R." are part of a name.
        if not ok and not (len(word) == 1 and word.isupper() and text[match.end():match.end() + 1] == "."):
            break
        start = match.start() if start is None else start
        end = position = match.end()
        count += 1
    return (start, end) if start is not None else None


def _name_before(text, position, limit=3):
    """Walk backwards from `position` over name words on the same line."""
    line_start = text.rfind("\n", 0, position) + 1
    found = [m for m in TOKEN.finditer(text, line_start, position)]
    start = end = None
    edge = position
    for match in reversed(found[-limit:]):
        gap = text[match.end():edge]
        if gap not in ("", " ", ". ", ".", "  ") or not _is_name_word(match.group()) and match.group().casefold() not in ("md", "mohd"):
            break
        start = edge = match.start()
        end = end or match.end()
    return (start, end) if start is not None else None


def detect(text, lexicon=None, address_hint=False):
    """Return sorted spans of personal data found in free text."""
    folded = fold_digits(text)
    protected = [(m.start(), m.end()) for m in _DOCTOR.finditer(text)]
    protected += [(m.start(), m.end()) for m in _PROTECT.finditer(text)]
    protected += [(m.start(), m.end()) for m in re.finditer(r"PSN-[0-9A-Z]{4}-[0-9A-Z]{4}", text)]
    spans = Spans()

    for kind, pattern in ID_PATTERNS:
        for m in pattern.finditer(folded):
            spans.add(m.start(), m.end(), kind)
    for m in _PHONE_LABEL.finditer(folded):
        spans.add(m.start("v"), m.end("v"), "PHONE")
    for m in _DOCUMENT_ID.finditer(folded):
        spans.add(m.start("v"), m.end("v"), "OTHER_ID")
    for m in _ID_LABEL.finditer(folded):
        spans.add(m.start("v"), m.end("v"), "MRN")

    addressed = address_hint or bool(_ADDRESS_LINE.search(text))
    for kind, pattern in ADDRESS_PATTERNS:
        for m in pattern.finditer(folded):
            value = m.group("v")
            if value.split()[0].casefold() in {"worker", "no", "the"}:
                continue
            spans.add(m.start("v"), m.end("v"), kind)
    for m in _PIN.finditer(folded):
        line = folded[folded.rfind("\n", 0, m.start()) + 1:m.start()]
        if addressed or re.search(r"(?i)distt?\b|district|tehsil|pin|address|जिला|पता|पिन", line):
            spans.add(m.start("v"), m.end("v"), "PIN")

    def person(span, kind):
        if not span:
            return
        s, e = span
        if any(s < pe and ps < e for ps, pe in protected):
            return
        spans.add(s, e, kind)

    # Chat exports: "[date, time] Sender Name: message".
    for m in re.finditer(r"(?m)^\[[^\]\n]{6,40}\][ \t]*", text):
        found = take_name(text, m.end(), 3)
        if found and text[found[1]:found[1] + 1] == ":":
            person(found, "PERSON_NAME")
    for m in _RELATIVE_LABEL.finditer(text):
        marker = m.group().strip().casefold()
        found = take_name(text, m.end(), allow_lower=marker.startswith(("s/", "d/", "w/", "h/")))
        # "C/O fever" is a complaint; "C/O Ramesh" is a relative.
        if marker.startswith("c") and "/" in marker:
            if not found or not text[found[0]].isupper() and not DEVANAGARI.search(text[found[0]]):
                continue
            if text[max(0, m.start() - 4):m.start()].rstrip().endswith(("K/", "k/")):
                continue
        person(found, "RELATIVE_NAME")
    for m in _KIN_WORD.finditer(text):
        person(take_name(text, m.end(), 3), "RELATIVE_NAME")
    for m in _NAME_LABEL.finditer(text):
        person(take_name(text, m.end()), "PATIENT_NAME")
    for m in _ACTION_LABEL.finditer(text):
        person(take_name(text, m.end()), "PERSON_NAME")

    for m in TOKEN.finditer(text):
        word = m.group()
        if word.casefold() in HONORIFICS:
            if text[m.start() - 1:m.start()] == " ":
                person(_name_before(text, m.start() - 1), "PATIENT_NAME")
        elif word.casefold() in PREFIXES and len(word) > 1:
            person(take_name(text, m.end()), "PERSON_NAME")
        elif word[0].isupper() or DEVANAGARI.search(word):
            after = text[m.end():m.end() + 40]
            if _is_name_word(word) and (_HINGLISH_AFTER.match(after) or _HINDI_AFTER.match(after)):
                person(_name_before(text, m.end()), "PATIENT_NAME")

    # "Name, W/o Husband" or "Name, 45 yrs" at the start of a line.
    for m in re.finditer(r"(?m)^(?:[ \t]*)(?=[A-Z\u0900-\u097F])", text):
        found = take_name(text, m.end(), 3)
        if found and re.match(r"[ \t]*(?:,[ \t]*(?:[SDWC]/[Oo]\b|\d{1,3}[ \t]*(?i:yrs?|years|y/o|/[ ]?[MF]\b))|\((?i:attendant|patient|relative)|[ \t]*[-–][ \t]*(?:K/C/O|H/O|C/O))", text[found[1]:]):
            person(found, "PATIENT_NAME")
    # After a time stamp: "14:00 - Name - K/C/O ...", "18:40 - Name (attendant)".
    for m in re.finditer(r"(?m)\d{1,2}:\d{2}(?:[ ]?[ap]\.?m\.?)?\]?[ \t]*[-–:][ \t]*", text):
        found = take_name(text, m.end(), 3)
        if found and re.match(r"[ \t]*(?:[-–(,:]|(?i:ji|sahab|bhai|bhaiya|didi|chachu|chacha|amma)\b)", text[found[1]:]):
            person(found, "PERSON_NAME")
    for m in re.finditer(r"\([ ]?(?i:attendant|relative|husband|wife|father|mother)\b", text):
        person(_name_before(text, m.start() - 1), "RELATIVE_NAME")
    # Capitalised pair beside a phone number is very likely a contact person.
    for s, e, kind in list(spans.items):
        if kind != "PHONE":
            continue
        line_start = text.rfind("\n", 0, s) + 1
        for m in re.finditer(r"(?<![\w])[A-Z][a-z]+(?:[ ][A-Z][a-z]+){1,2}", text[line_start:s]):
            words = m.group().split()
            if all(w.casefold() not in STOPWORDS for w in words):
                person((line_start + m.start(), line_start + m.end()), "PERSON_NAME")

    if lexicon is not None:
        if lexicon.place_pattern:
            for m in lexicon.place_pattern.finditer(text):
                spans.add(m.start(), m.end(), "VILLAGE")
        run = []
        for m in TOKEN.finditer(text):
            s, e = m.span()
            word = m.group()
            hit = (word[0].isupper() or DEVANAGARI.search(word)) and lexicon.knows(word)
            if hit and not any(s < pe and ps < e for ps, pe in protected):
                if run and text[run[-1][1]:s] in (" ", ". ", "_", "-"):
                    run[-1][1] = e
                else:
                    run.append([s, e])
        for s, e in run:
            # Pull in a leading Md./Mohd and trailing generic surname parts.
            before = re.search(r"(?:\b(?:Md|Mohd|Mohammad|Mohammed)\.?[ ])$", text[:s])
            if before:
                s = before.start()
            while True:
                nxt = re.match(r"[ ]([A-Za-z\u0900-\u097F]+)", text[e:])
                if nxt and phonetic(nxt.group(1)) in GENERIC_NAME_PARTS and nxt.group(1).casefold() not in HONORIFICS:
                    e += nxt.end()
                else:
                    break
            person((s, e), "PERSON_NAME")
        # Lower-case mentions of a known name next to Hinglish clinical cues.
        for m in TOKEN.finditer(text):
            if m.group().islower() and _HINGLISH_AFTER.match(text[m.end():m.end() + 30]) and lexicon.knows(m.group()):
                person(m.span(), "PERSON_NAME")

    return sorted(spans.items)
