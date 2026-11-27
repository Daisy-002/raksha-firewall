"""Read input files safely. Anything doubtful is quarantined, never copied."""
import csv
import io
import json
import os
import re
from pathlib import Path

SUPPORTED = {".csv", ".tsv", ".json", ".txt"}


class Quarantine(Exception):
    """Carries a safe reason code only, never file content."""


class Document:
    def __init__(self, relative, kind, data, newline="\n", delimiter=",", indent=2):
        self.relative = relative
        self.kind = kind
        self.data = data
        self.newline = newline
        self.delimiter = delimiter
        self.indent = indent


def discover_files(root: Path):
    found = []
    for folder, directories, files in os.walk(root):
        directories.sort()
        found.extend(Path(folder) / name for name in files)
    return sorted(found, key=lambda p: p.relative_to(root).as_posix())


def decode_bytes(raw: bytes) -> str:
    try:
        if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
            text = raw.decode("utf-16")
        else:
            try:
                text = raw.decode("utf-8-sig")
            except UnicodeDecodeError:
                # Legacy Windows export. Runs of high bytes mean damaged data.
                if re.search(rb"[\x80-\xff]{3,}", raw):
                    raise Quarantine("undecodable_text") from None
                text = raw.decode("cp1252")
    except UnicodeError:
        raise Quarantine("undecodable_text") from None
    if re.search(r"[\x00-\x08\x0b\x0e-\x1f�]", text):
        raise Quarantine("binary_or_corrupt")
    return text


def _depth_ok(data, limit):
    stack = [(data, 1)]
    while stack:
        node, depth = stack.pop()
        if depth > limit:
            return False
        if isinstance(node, dict):
            stack.extend((child, depth + 1) for child in node.values())
        elif isinstance(node, list):
            stack.extend((child, depth + 1) for child in node)
    return True


def load(path: Path, relative: str, raw: bytes, policy) -> Document:
    extension = path.suffix.lower()
    if extension not in SUPPORTED:
        raise Quarantine("unsupported_format")
    text = decode_bytes(raw)
    if not text.strip():
        raise Quarantine("empty_file")
    newline = "\r\n" if "\r\n" in text else "\n"

    if extension == ".json":
        try:
            data = json.loads(text)
        except RecursionError:
            raise Quarantine("excessive_nesting") from None
        except ValueError:
            raise Quarantine("malformed_json") from None
        if not isinstance(data, (dict, list)):
            raise Quarantine("unsupported_json_shape")
        if not _depth_ok(data, policy["max_json_depth"]):
            raise Quarantine("excessive_nesting")
        indent = 2 if "\n" in text.strip() else None
        return Document(relative, "json", data, newline, indent=indent)

    if extension in {".csv", ".tsv"}:
        if text.lstrip()[0] in "{[<":
            raise Quarantine("format_mismatch")
        delimiter = "\t" if extension == ".tsv" else ","
        csv.field_size_limit(10_000_000)
        try:
            rows = list(csv.reader(io.StringIO(text, newline=""), delimiter=delimiter, strict=True))
        except csv.Error:
            raise Quarantine("malformed_table") from None
        if not rows or not rows[0]:
            raise Quarantine("empty_file")
        return Document(relative, "table", rows, newline, delimiter=delimiter)

    return Document(relative, "text", text.replace("\r\n", "\n"), newline)
