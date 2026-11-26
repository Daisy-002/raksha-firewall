import unicodedata
import re


DEVANAGARI_DIGITS = str.maketrans(
    "०१२३४५६७८९",
    "0123456789"
)


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", str(value))
    value = value.translate(DEVANAGARI_DIGITS)
    value = value.replace("\u200c", "").replace("\u200d", "")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def normalize_key(value: str) -> str:
    value = normalize_text(value).casefold()
    return "".join(
        char
        for char in value
        if unicodedata.category(char)[0] in {"L", "M", "N"}
    )