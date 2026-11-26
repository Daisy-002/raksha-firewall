import re


def generalize_age(value, band_width=5):
    if isinstance(value, bool):
        return value

    try:
        age = int(value)
    except (ValueError, TypeError):
        return value

    if age < 0 or age > 120:
        return value

    lower = (age // band_width) * band_width
    return f"{lower}-{lower + band_width - 1}"


def generalize_value(field, value):
    key = re.sub(r"[^a-z]", "", str(field).casefold())

    if key in {"age", "patientage", "ageyears"}:
        return generalize_age(value)

    return value