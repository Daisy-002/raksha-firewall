import re
import unicodedata


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
]


def filename_contains_pii(name: str) -> bool:
    normalized = unicodedata.normalize("NFKC", str(name))

    if any(pattern.search(normalized) for pattern in PII_FILENAME_PATTERNS):
        return True

    # Names embedded in filenames commonly use underscore-separated words.
    # This is deliberately conservative: only flag multi-part title-case
    # components when accompanied by a patient-like numeric identifier.
    stem = normalized.rsplit(".", 1)[0]
    has_name_like_parts = re.search(
        r"(?:^|[_-])[A-Z][a-z]{2,}(?:[_-])[A-Z][a-z]{2,}(?:[_-]|$)",
        stem,
    )
    has_numeric_identifier = re.search(r"\d{4,}", stem)

    return bool(has_name_like_parts and has_numeric_identifier)


def safe_filename(name: str, digest: str) -> str:
    if not filename_contains_pii(name):
        return name

    suffix = ""
    if "." in name:
        suffix = "." + name.rsplit(".", 1)[1]

    return f"file_{digest[:12]}{suffix}"
