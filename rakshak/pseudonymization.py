"""Keyed, non-reversible pseudonyms and date offsets (HMAC-SHA256)."""
import hashlib
import hmac
import os

_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def get_secret() -> bytes:
    secret = os.environ.get("RAKSHA_SECRET", "")
    if not secret:
        raise RuntimeError("missing_secret")
    return secret.encode("utf-8", errors="surrogateescape")


def digest(domain: str, value: str) -> bytes:
    return hmac.new(get_secret(), f"{domain}|{value}".encode("utf-8"), hashlib.sha256).digest()


def pseudonym(patient_key: str) -> str:
    number = int.from_bytes(digest("patient", patient_key)[:7], "big")
    code = "".join(_ALPHABET[(number >> (5 * i)) & 31] for i in range(8))
    # Grouped in fours so a pseudonym can never look like a PAN or other identifier.
    return f"PSN-{code[:4]}-{code[4:]}"


def deterministic_offset(key: str, maximum: int = 180, minimum: int = 15) -> int:
    """A non-zero offset in [-maximum, -minimum] or [minimum, maximum]."""
    maximum = max(1, maximum)
    minimum = max(1, min(minimum, maximum))
    span = maximum - minimum + 1
    number = int.from_bytes(digest("date-shift", key)[:6], "big") % (2 * span)
    return number - span - minimum + 1 if number < span else number - span + minimum
