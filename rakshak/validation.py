import re


RESIDUAL_PATTERNS = [
    re.compile(r"(?<!\d)[6-9]\d{9}(?!\d)"),
    re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b", re.I),
    re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b"),
    re.compile(r"(?<!\d)\d{4}[\s-]?\d{4}[\s-]?\d{4}(?!\d)"),
]


def find_residual_identifiers(text: str):
    found = []

    for pattern in RESIDUAL_PATTERNS:
        if pattern.search(text):
            found.append("possible_identifier")

    return found