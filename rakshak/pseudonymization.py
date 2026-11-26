import hashlib
import hmac
import os


def get_secret() -> bytes:
    secret = os.environ.get("RAKSHA_SECRET", "")
    if len(secret) < 8:
        raise RuntimeError("missing_or_weak_secret")
    return secret.encode("utf-8")


def _digest(domain: bytes, value: str) -> bytes:
    return hmac.new(
        get_secret(),
        domain + value.encode("utf-8"),
        hashlib.sha256
    ).digest()


def pseudonym(patient_key: str) -> str:
    alphabet = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
    digest = _digest(b"patient|", patient_key)
    number = int.from_bytes(digest[:5], "big")

    code = ""
    for _ in range(8):
        code += alphabet[number & 31]
        number >>= 5

    return "PSN-" + code


def deterministic_offset(patient_key: str, maximum: int = 180) -> int:
    if maximum < 1:
        return 1

    digest = _digest(b"date-shift|", patient_key)
    number = int.from_bytes(digest[:4], "big")
    offset = number % (2 * maximum + 1) - maximum

    return offset if offset != 0 else 1