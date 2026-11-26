import datetime as dt
import re
from .pseudonymization import deterministic_offset


DATE_PATTERNS = [
    re.compile(r"\b(19\d{2}|20\d{2})-(\d{2})-(\d{2})\b"),
    re.compile(r"\b(\d{1,2})/(\d{1,2})/(19\d{2}|20\d{2})\b"),
]


def shift_date_string(value: str, patient_key: str, maximum: int = 180):
    offset = deterministic_offset(patient_key, maximum)

    match = DATE_PATTERNS[0].fullmatch(value.strip())
    if match:
        try:
            date = dt.date(
                int(match.group(1)),
                int(match.group(2)),
                int(match.group(3))
            )
            shifted = date + dt.timedelta(days=offset)
            return shifted.isoformat()
        except ValueError:
            return value

    match = DATE_PATTERNS[1].fullmatch(value.strip())
    if match:
        try:
            date = dt.date(
                int(match.group(3)),
                int(match.group(2)),
                int(match.group(1))
            )
            shifted = date + dt.timedelta(days=offset)
            return shifted.strftime("%d/%m/%Y")
        except ValueError:
            return value

    return value