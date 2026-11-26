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

GENERIC_FILENAME_WORDS = {
    "admission", "ambulance", "arogya", "billing", "blood", "census",
    "claim", "clean", "consent", "discharge", "dengue", "dhhardoi",
    "doctor", "drug", "export", "fhir", "formulary", "hardoi",
    "hospital", "jeevanjyoti", "lab", "management", "misc", "note",
    "opd", "pathkind", "prescription", "protocol", "range", "registration",
    "report", "result", "sanjeevani", "summary", "ward",
}


def filename_contains_pii(name: str) -> bool:
    normalized = unicodedata.normalize("NFKC", str(name))

    if any(pattern.search(normalized) for pattern in PII_FILENAME_PATTERNS):
        return True

    if BASE64_CANDIDATE.search(normalized):
        return True

    stem = normalized.rsplit(".", 1)[0]
    parts = re.split(r"[_\s-]+", stem)
    for size in range(2, min(4, len(parts)) + 1):
        for start in range(len(parts) - size + 1):
            candidate = parts[start:start + size]
            if not all(re.fullmatch(r"[A-Z][a-z]{2,}", part) for part in candidate):
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
