import re
import unicodedata

from .detection import BASE64_CANDIDATE


PII_FILENAME_PATTERNS = [
    # Indian mobile numbers, including common separators
    re.compile(r"(?<!\d)(?:\+?91[\s._-]?)?0?[6-9]\d{4}[\s._-]?\d{5}(?!\d)"),

    # Email addresses
    re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", re.I),

    # Aadhaar, including separated digits
    re.compile(r"(?<!\d)\d{4}[\s_-]?\d{4}[\s_-]?\d{4}(?!\d)"),

    # PAN
    re.compile(r"(?i)\b[A-Z]{5}\d{4}[A-Z]\b"),

    # ABHA number
    re.compile(r"(?<!\d)\d{2}[-_]\d{4}[-_]\d{4}[-_]\d{4}(?!\d)"),

    # Hospital and encounter identifiers
    re.compile(
        r"\b(?:JJH|SNJ|HOSP|UHID|IPD|ADM|OPD)[-/]"
        r"[A-Z0-9][A-Z0-9/-]{2,}\b",
        re.I,
    ),
]

FILENAME_NAME_CONTEXT = re.compile(
    r"(?<![A-Z0-9])"
    r"(?:patient(?:[\s._-]*name)?|name|relative|guardian|father|"
    r"mother|spouse|attender|naam|नाम|रोगी|मरीज)"
    r"[\s._-]+"
    r"(?P<name>(?:[A-Z][A-Z.'-]{1,}|[\u0900-\u097f]{2,})"
    r"(?:[\s_-]+(?:[A-Z][A-Z.'-]{1,}|[\u0900-\u097f]{2,})){1,2})"
    r"(?![A-Z0-9])",
    re.I,
)

FILENAME_MRN_CONTEXT = re.compile(
    r"(?i)(?<![A-Z0-9])"
    r"(?:mrn|mr[\s._-]*(?:no|number)?|"
    r"medical[\s._-]*record(?:[\s._-]*(?:id|number|no))?|"
    r"patient[\s._-]*(?:id|number|no)|"
    r"hospital[\s._-]*(?:id|number|no)|uhid|"
    r"chart[\s._-]*(?:id|number|no)|"
    r"registration[\s._-]*(?:id|number|no)|reg[\s._-]*no)"
    r"[\s._#:-]+(?=[A-Z0-9./_-]*\d)"
    r"[A-Z0-9](?:[A-Z0-9./_-]{1,}[A-Z0-9])(?![A-Z0-9])"
)

FILENAME_ADDRESS_CONTEXT = re.compile(
    r"(?i)(?<![A-Z0-9])"
    r"(?P<label>address|addr|house(?:[\s._-]*(?:no|number))?|"
    r"flat(?:[\s._-]*(?:no|number))?|building|street|locality|"
    r"landmark|area|neighbou?rhood|colony|village|gaon|gram|"
    r"mohalla|district|tehsil|block|ward|post[\s._-]*office|"
    r"postal[\s._-]*code|pin(?:[\s._-]*code)?|"
    r"पता|गांव|गाँव|ग्राम|मोहल्ला|मकान|घर|इलाका|क्षेत्र|"
    r"जिला|तहसील|डाकघर|वार्ड)"
    r"[\s._#:-]+"
    r"(?P<value>[A-Z0-9\u0900-\u097f][A-Z0-9\u0900-\u097f.'-]*"
    r"(?:[\s_-]+[A-Z0-9\u0900-\u097f][A-Z0-9\u0900-\u097f.'-]*){0,3})"
    r"(?![A-Z0-9])",
)

GENERIC_FILENAME_WORDS = {
    "admission", "ambulance", "arogya", "billing", "blood", "census",
    "claim", "clean", "consent", "discharge", "dengue", "dhhardoi",
    "doctor", "drug", "export", "fhir", "formulary", "hardoi",
    "hospital", "jeevanjyoti", "lab", "management", "misc", "note",
    "opd", "pathkind", "prescription", "protocol", "range", "registration",
    "report", "result", "sanjeevani", "summary", "ward",
    "patient", "name", "record", "records", "document", "data", "file",
    "template", "example", "input", "output", "test", "tests", "sample",
    "clinical", "note", "notes", "form", "screening", "case",
    "txt", "json", "csv", "tsv", "pdf", "xml", "html", "md",
}

FILENAME_EXTENSIONS = {"txt", "json", "csv", "tsv", "pdf", "xml", "html", "md"}


def filename_contains_pii(name: str) -> bool:
    normalized = unicodedata.normalize("NFKC", str(name))

    if any(pattern.search(normalized) for pattern in PII_FILENAME_PATTERNS):
        return True

    if BASE64_CANDIDATE.search(normalized):
        return True

    for match in FILENAME_NAME_CONTEXT.finditer(normalized):
        words = re.split(r"[\s._-]+", match.group("name"))
        if words and words[-1].casefold() in FILENAME_EXTENSIONS:
            words.pop()
        if len(words) >= 2 and not any(
            word.casefold() in GENERIC_FILENAME_WORDS
            for word in words
        ):
            return True

    if FILENAME_MRN_CONTEXT.search(normalized):
        return True

    for match in FILENAME_ADDRESS_CONTEXT.finditer(normalized):
        words = re.split(r"[\s._-]+", match.group("value"))
        if words and words[-1].casefold() in FILENAME_EXTENSIONS:
            words.pop()
        if match.group("label").casefold().startswith("house") and not any(
            any(character.isdigit() for character in word)
            for word in words
        ):
            continue
        if any(any(character.isdigit() for character in word) for word in words):
            return True
        if words and not any(
            word.casefold() in GENERIC_FILENAME_WORDS
            for word in words
        ):
            return True

    stem = normalized.rsplit(".", 1)[0]
    parts = re.split(r"[_\s-]+", stem)
    for size in range(2, min(4, len(parts)) + 1):
        for start in range(len(parts) - size + 1):
            candidate = parts[start:start + size]
            if not all(
                re.fullmatch(r"[A-Za-z][A-Za-z.'-]{1,}", part)
                for part in candidate
            ):
                continue
            if not any(
                character.isupper()
                for part in candidate
                for character in part
            ):
                continue
            if not any(
                part.casefold() in GENERIC_FILENAME_WORDS
                for part in candidate
            ):
                return True

    return False


def safe_filename(name: str, digest: str) -> str:
    if not filename_contains_pii(name):
        return name

    suffix = ""
    if "." in name:
        suffix = "." + name.rsplit(".", 1)[1]

    return f"file_{digest[:12]}{suffix}"
