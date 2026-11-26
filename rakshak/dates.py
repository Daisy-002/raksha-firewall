import datetime as dt
import re
import unicodedata

from .pseudonymization import deterministic_offset


_TIME_SUFFIX = (
    r"(?P<suffix>(?:[ T]\d{1,2}:\d{2}"
    r"(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?)"
)
YEAR_FIRST_DATE = re.compile(
    r"(?P<year>(?:19|20)\d{2})(?P<separator>[-/.])"
    r"(?P<month>\d{1,2})(?P=separator)(?P<day>\d{1,2})"
    + _TIME_SUFFIX
)
DAY_FIRST_DATE = re.compile(
    r"(?P<day>\d{1,2})(?P<separator>[-/.])"
    r"(?P<month>\d{1,2})(?P=separator)(?P<year>(?:19|20)\d{2})"
    + _TIME_SUFFIX
)
DATE_PATTERNS = [YEAR_FIRST_DATE, DAY_FIRST_DATE]


def _ascii_digits(value):
    return "".join(
        str(unicodedata.digit(char)) if char.isdecimal() else char
        for char in value
    )


def shift_date_string(value: str, patient_key: str, maximum: int = 180):
    offset = deterministic_offset(patient_key, maximum)
    stripped = value.strip()
    normalized = _ascii_digits(stripped)
    match = YEAR_FIRST_DATE.fullmatch(normalized)
    year_first = match is not None
    if match is None:
        match = DAY_FIRST_DATE.fullmatch(normalized)
    if match is None:
        return value

    try:
        date = dt.date(
            int(match.group("year")),
            int(match.group("month")),
            int(match.group("day")),
        )
    except ValueError:
        return value

    shifted = date + dt.timedelta(days=offset)
    separator = match.group("separator")
    if year_first:
        result = (
            f"{shifted.year:04d}{separator}{shifted.month:02d}"
            f"{separator}{shifted.day:02d}"
        )
    else:
        result = (
            f"{shifted.day:02d}{separator}{shifted.month:02d}"
            f"{separator}{shifted.year:04d}"
        )

    result += match.group("suffix") or ""
    if any("०" <= char <= "९" for char in stripped):
        result = result.translate(str.maketrans("0123456789", "०१२३४५६७८९"))

    leading = value[:len(value) - len(value.lstrip())]
    trailing = value[len(value.rstrip()):]
    return leading + result + trailing
