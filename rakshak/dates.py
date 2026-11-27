"""Find, parse and shift dates in any of the supported spellings."""
import datetime as dt
import re

from .textutil import fold_digits
from .vocab import MONTHS

_MONTH = "|".join(sorted(MONTHS, key=len, reverse=True))
_YEAR = r"(?:19|20)\d{2}"
PATTERNS = [
    ("ymd", re.compile(rf"(?<![\d/.-])(?P<y>{_YEAR})(?P<s>[-/.])(?P<m>\d{{1,2}})(?P=s)(?P<d>\d{{1,2}})(?![\d/])")),
    ("num", re.compile(rf"(?<![\d/.-])(?P<a>\d{{1,2}})(?P<s>[-/.])(?P<b>\d{{1,2}})(?P=s)(?P<y>{_YEAR}|\d{{2}})(?![\d/]|[.-]\d)")),
    ("dMy", re.compile(rf"(?<![\w/-])(?P<d>\d{{1,2}})(?:st|nd|rd|th)?(?P<s1>[ -])(?P<M>{_MONTH})(?![A-Za-z])\.?(?:(?P<s2>,? |-)(?P<y>{_YEAR}|\d{{2}}(?!\d)))?", re.I)),
    ("Mdy", re.compile(rf"(?<![A-Za-z])(?P<M>{_MONTH})(?![A-Za-z])\.?(?P<s1> )(?P<d>\d{{1,2}})(?:st|nd|rd|th)?(?![\d:])(?:(?P<s2>,? )(?P<y>{_YEAR}))?", re.I)),
]
_DEVA = str.maketrans("0123456789", "०१२३४५६७८९")


def order_of(a, b):
    if a > 12 and b <= 12:
        return "dmy"
    if b > 12 and a <= 12:
        return "mdy"
    return None


def infer_order(texts):
    """Vote on day-first or month-first using only unambiguous numeric dates."""
    votes = {"dmy": 0, "mdy": 0}
    for text in texts:
        for match in PATTERNS[1][1].finditer(fold_digits(text)):
            found = order_of(int(match["a"]), int(match["b"]))
            if found:
                votes[found] += 1
    if votes["dmy"] == votes["mdy"]:
        return None
    return max(votes, key=votes.get)


def find(text, order="dmy", default_year=2026):
    """Yield (start, end, date, kind, match) for every valid date."""
    folded = fold_digits(text)
    taken = []
    for kind, pattern in PATTERNS:
        for m in pattern.finditer(folded):
            if any(m.start() < e and s < m.end() for s, e in taken):
                continue
            try:
                if kind == "ymd":
                    date = dt.date(int(m["y"]), int(m["m"]), int(m["d"]))
                elif kind == "num":
                    a, b, year = int(m["a"]), int(m["b"]), int(m["y"])
                    if len(m["y"]) == 2:
                        year += 2000
                    local = order_of(a, b) or order
                    day, month = (a, b) if local == "dmy" else (b, a)
                    date = dt.date(year, month, day)
                else:
                    year = int(m["y"]) if m["y"] else default_year
                    if year < 100:
                        year += 2000
                    date = dt.date(year, MONTHS[m["M"].casefold()], int(m["d"]))
            except (ValueError, KeyError):
                continue
            taken.append((m.start(), m.end()))
            yield m.start(), m.end(), date, kind, m


def render(original, date, offset, kind, match, order):
    """Write the shifted date in the same style as the original."""
    new = date + dt.timedelta(days=offset)
    if kind == "ymd":
        s = match["s"]
        out = f"{new.year:04d}{s}{new.month:02d}{s}{new.day:02d}"
    elif kind == "num":
        local = order_of(int(match["a"]), int(match["b"])) or order
        first, second = (new.day, new.month) if local == "dmy" else (new.month, new.day)
        year = f"{new.year % 100:02d}" if len(match["y"]) == 2 else f"{new.year:04d}"
        s = match["s"]
        out = f"{first:02d}{s}{second:02d}{s}{year}"
    else:
        word = match["M"]
        names = [n for n, v in MONTHS.items() if v == new.month and n.isascii() == word.isascii()]
        full = max(names, key=len)
        name = full if len(word) > 3 else min((n for n in names if len(n) >= 3), key=len, default=full)
        if word[:1].isupper():
            name = name.upper() if word.isupper() else name.capitalize()
        year = ""
        if match["y"]:
            year = match["s2"] + (f"{new.year % 100:02d}" if len(match["y"]) == 2 else str(new.year))
        if kind == "dMy":
            out = f"{new.day}{match['s1']}{name}{year}"
        else:
            out = f"{name}{match['s1']}{new.day}{year}"
    if any("\u0966" <= c <= "\u096f" for c in original):
        out = out.translate(_DEVA)
    return out
