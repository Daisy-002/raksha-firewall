"""Script-aware text helpers: tokens, transliteration and name matching."""
import re
import unicodedata
from difflib import SequenceMatcher
from functools import lru_cache

# Length-preserving digit folding, so match offsets stay valid on the original text.
_DIGITS = {}
for _zero in (0x0966, 0x09E6, 0x0A66, 0x0AE6, 0xFF10, 0x0660, 0x06F0):
    for _i in range(10):
        _DIGITS[_zero + _i] = str(_i)

TOKEN = re.compile(
    r"[\u0900-\u0963\u0971-\u097F\u200c\u200d]+|"
    r"[A-Za-z\u00C0-\u024F]+(?:['\u2019](?![sS](?![A-Za-z]))[A-Za-z]+)*")
DEVANAGARI = re.compile(r"[ऀ-ॿ]")


def fold_digits(text):
    return text.translate(_DIGITS)


def clean(value):
    value = unicodedata.normalize("NFKC", str(value))
    value = fold_digits(value).replace("‌", "").replace("‍", "")
    return " ".join(value.split())


def words(text):
    return TOKEN.findall(text)


_CONSONANTS = dict(zip(
    "कखगघङचछजझञटठडढणतथदधनपफबभमयरलळवशषसह",
    ["k", "kh", "g", "gh", "n", "ch", "chh", "j", "jh", "n", "t", "th", "d", "dh", "n",
     "t", "th", "d", "dh", "n", "p", "ph", "b", "bh", "m", "y", "r", "l", "l", "v",
     "sh", "sh", "s", "h"],
))
_VOWELS = dict(zip("अआइईउऊऋएऐओऔऑऍ",
                   ["a", "a", "i", "i", "u", "u", "ri", "e", "ai", "o", "au", "o", "e"]))
_SIGNS = dict(zip("ािीुूृेैोौॉॅ",
                  ["a", "i", "i", "u", "u", "ri", "e", "ai", "o", "au", "o", "e"]))
_NUKTA = {"j": "z", "ph": "f", "d": "r", "dh": "rh", "k": "q"}


def romanize(word):
    """Small Devanagari to Latin transliteration, good enough for name matching."""
    word = unicodedata.normalize("NFD", word)
    out, pending = [], False
    for char in word:
        if char in _CONSONANTS:
            if pending:
                out.append("a")
            out.append(_CONSONANTS[char])
            pending = True
        elif char == "़":
            if out:
                out[-1] = _NUKTA.get(out[-1], out[-1])
        elif char in _SIGNS:
            out.append(_SIGNS[char])
            pending = False
        elif char == "्":
            pending = False
        elif char in "ंँ":
            if pending:
                out.append("a")
            out.append("n")
            pending = False
        elif char in _VOWELS:
            if pending:
                out.append("a")
            out.append(_VOWELS[char])
            pending = False
    # A final inherent vowel is silent in Hindi names (schwa deletion).
    return "".join(out)


# Common written abbreviations of names.
ABBREVIATIONS = {"md": "mohammad", "mohd": "mohammad", "mohmd": "mohammad", "muhd": "mohammad", "kr": "kumar"}


@lru_cache(maxsize=200000)
def phonetic(word):
    """Spelling-tolerant key that works across Latin variants and Devanagari."""
    if DEVANAGARI.search(word):
        word = romanize(word)
    word = unicodedata.normalize("NFKD", word.casefold())
    word = re.sub(r"[^a-z]", "", word)
    word = ABBREVIATIONS.get(word, word)
    for old, new in (("chh", "c"), ("ch", "c"), ("ph", "f"), ("ee", "i"), ("oo", "u"),
                     ("ou", "au"), ("w", "v"), ("q", "k"), ("z", "j"), ("ck", "k"),
                     ("sh", "s"), ("th", "t"), ("dh", "d"), ("bh", "b"), ("kh", "k"),
                     ("gh", "g"), ("jh", "j"), ("y", "i")):
        word = word.replace(old, new)
    word = re.sub(r"(.)\1+", r"\1", word)
    if len(word) > 3:
        word = re.sub(r"(?<=[^aeiou])[ah]$|h$", "", word)
    return word


@lru_cache(maxsize=200000)
def skeleton(word):
    key = phonetic(word)
    return key[:1] + re.sub(r"[aeiouh]", "", key[1:])


@lru_cache(maxsize=200000)
def similar_word(left, right):
    a, b = phonetic(left), phonetic(right)
    if not a or not b:
        return False
    if a == b:
        return True
    if min(len(a), len(b)) < 3:
        return False
    ratio = SequenceMatcher(None, a, b).ratio()
    if skeleton(left) == skeleton(right):
        return ratio >= 0.7
    # One vowel or ending differs in a long name (for example Parvati / Parvathi).
    return min(len(a), len(b)) >= 6 and ratio >= 0.87
