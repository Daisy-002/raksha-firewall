import re


RESIDUAL_PATTERNS = [
    # Indian phone numbers with optional country code, trunk zero, and separators
    re.compile(
        r"(?<![0-9०-९])(?:\+?(?:91|९१)[\s.-]?)?0?[6-9६-९]"
        r"[0-9०-९]{4}[\s.-]?[0-9०-९]{5}(?![0-9०-९])"
    ),

    # Email addresses
    re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b", re.I),

    # PAN
    re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b", re.I),

    # Aadhaar-like 12-digit numbers
    re.compile(r"(?<!\d)\d{4}[\s-]?\d{4}[\s-]?\d{4}(?!\d)"),
]


def find_residual_identifiers(text: str):
    found = []

    for pattern in RESIDUAL_PATTERNS:
        if pattern.search(text):
            found.append("possible_identifier")

    return found
