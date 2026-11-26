import re


def filename_contains_pii(name: str) -> bool:
    patterns = [
        r"(?<!\d)[6-9]\d{9}(?!\d)",
        r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b",
        r"\b\d{4}[\s_-]?\d{4}[\s_-]?\d{4}\b",
    ]

    return any(re.search(pattern, name, re.I) for pattern in patterns)


def safe_filename(name: str, digest: str) -> str:
    if not filename_contains_pii(name):
        return name

    suffix = ""
    if "." in name:
        suffix = "." + name.rsplit(".", 1)[1]

    return f"file_{digest[:12]}{suffix}"