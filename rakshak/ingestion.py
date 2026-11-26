import json
from pathlib import Path


def decode_bytes(raw: bytes):
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw[3:].decode("utf-8", errors="strict")

    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16", errors="strict")

    for encoding in ("utf-8", "cp1252"):
        try:
            return raw.decode(encoding, errors="strict")
        except UnicodeDecodeError:
            pass

    raise ValueError("undecodable_text")


def load_json(text: str):
    return json.loads(text)


def read_file(path: Path):
    return decode_bytes(path.read_bytes())