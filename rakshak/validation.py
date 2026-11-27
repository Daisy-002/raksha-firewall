"""Independent last check: fail closed if a direct identifier survives."""
import re

from .textutil import fold_digits

RESIDUAL = [re.compile(p) for p in (
    r"(?<![\w.])(?:\+?91[ -]?|0)?[6-9]\d{4}[ -]?\d{5}(?![\w]|\.\d)",
    r"(?<![\w.-])\d{4}[ -]?\d{4}[ -]?\d{4}(?![\w-]|\.\d)",
    r"[\w.+-]+@[A-Za-z][\w-]+\.[A-Za-z]{2,}",
    r"(?<![A-Za-z0-9])[A-Z]{5}\d{4}[A-Z](?![A-Za-z0-9])",
)]
# Random UUIDs in FHIR references contain long digit groups and are not personal data.
_UUID = re.compile(r"[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}")


def has_residual_identifier(text):
    folded = _UUID.sub(" ", fold_digits(text))
    return any(pattern.search(folded) for pattern in RESIDUAL)
