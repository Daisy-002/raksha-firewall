import re


RESIDUAL_PATTERNS = [
    # Indian phone numbers: ASCII digits
    re.compile(r"(?<!\d)[6-9][0-9]{9}(?!\d)"),

    # Indian phone numbers: Devanagari digits, including mixed scripts
    re.compile(r"(?<![0-9०-९])[6-9६-९][0-9०-९]{9}(?![0-9०-९])"),

    # Email addresses
    re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b", re.I),

    # PAN
    re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b"),

    # Aadhaar-like 12-digit numbers
    re.compile(r"(?<!\d)\d{4}[\s-]?\d{4}[\s-]?\d{4}(?!\d)"),
]


def find_residual_identifiers(text: str):
    found = []

    for pattern in RESIDUAL_PATTERNS:
        if pattern.search(text):
            found.append("possible_identifier")

    return found
