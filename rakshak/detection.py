import re
from .normalization import normalize_text


PATTERNS = [
    (
        "PHONE",
        re.compile(
            r"(?<!\d)(?:\+?91[\s.-]?)?[6-9]\d{4}[\s.-]?\d{5}(?!\d)"
        ),
    ),
    (
        "AADHAAR",
        re.compile(r"(?<!\d)\d{4}[\s-]?\d{4}[\s-]?\d{4}(?!\d)"),
    ),
    (
        "EMAIL",
        re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b", re.I),
    ),
    (
        "PAN",
        re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b", re.I),
    ),
    (
        "ABHA",
        re.compile(r"\b\d{2}-\d{4}-\d{4}-\d{4}\b"),
    ),
]

SENSITIVE_FIELD_HINTS = {
    "patientname": "PATIENT_NAME",
    "name": "PERSON_NAME",
    "fullname": "PERSON_NAME",
    "firstname": "PERSON_NAME",
    "lastname": "PERSON_NAME",
    "fathername": "RELATIVE_NAME",
    "mothername": "RELATIVE_NAME",
    "spousename": "RELATIVE_NAME",
    "address": "ADDRESS",
    "residentialaddress": "ADDRESS",
    "homeaddress": "ADDRESS",
    "streetaddress": "ADDRESS",
    "email": "EMAIL",
    "emailaddress": "EMAIL",
    "mobilenumber": "PHONE",
    "phonenumber": "PHONE",
    "contactnumber": "PHONE",
    "aadharnumber": "AADHAAR",
    "aadhaar": "AADHAAR",
    "pan": "PAN",
    "pannumber": "PAN",
    "abhanumber": "ABHA",
}

# Avoid treating common clinical phrases as personal names.
CLINICAL_ALLOWLIST = {
    "parkinsons disease",
    "alzheimers disease",
    "blood pressure",
    "heart rate",
    "oxygen saturation",
    "respiratory rate",
    "temperature",
    "dolo 650",
    "crocin",
    "metformin",
    "insulin",
}


def _field_key(field):
    return re.sub(r"[^a-z]", "", str(field).casefold())


def _count(stats, kind, count=1):
    stats.identifiers += count
    stats.entities[kind] = stats.entities.get(kind, 0) + count


def _replace_patterns(text, stats):
    result = text

    for kind, pattern in PATTERNS:
        result, count = pattern.subn(f"[{kind}]", result)
        if count:
            _count(stats, kind, count)

    return result


def _replace_labelled_names(text, stats):
    """
    Detect names only in explicit identity contexts.
    Do not classify every capitalized word as a person.
    """
    patterns = [
        re.compile(
            r"(?i)\b(patient\s*name|name\s*of\s*patient|"
            r"नाम|मरीज\s*का\s*नाम|रोगी\s*का\s*नाम)\s*[:=-]\s*"
            r"([^\n,;|]{2,80})"
        ),
        re.compile(
            r"(?i)\b(father'?s?\s*name|mother'?s?\s*name|"
            r"spouse'?s?\s*name|guardian'?s?\s*name)\s*[:=-]\s*"
            r"([^\n,;|]{2,80})"
        ),
    ]

    result = text

    for pattern in patterns:
        def replacement(match):
            _count(stats, "PERSON_NAME")
            return match.group(1) + ": [PERSON_NAME]"

        result = pattern.sub(replacement, result)

    # Explicit relative-name forms.
    relative = re.compile(
        r"(?i)\b(?:S/O|D/O|W/O|C/O)\s*[:.-]?\s*"
        r"[A-Z][A-Za-z.' -]{2,50}"
    )

    def relative_replacement(match):
        _count(stats, "RELATIVE_NAME")
        return "[RELATIVE_NAME]"

    result = relative.sub(relative_replacement, result)

    return result


def sanitize_value(field, value, stats):
    if not isinstance(value, str):
        return value

    original = value
    normalized_field = _field_key(field)

    # Clinical text is not blindly redacted by column name.
    # Explicit identifiers are still detected below.
    if normalized_field in SENSITIVE_FIELD_HINTS and normalized_field not in {
        "clinicalnote",
        "notes",
        "diagnosis",
    }:
        kind = SENSITIVE_FIELD_HINTS[normalized_field]
        if value.strip():
            _count(stats, kind)
            return f"[{kind}]"

    result = _replace_patterns(original, stats)
    result = _replace_labelled_names(result, stats)

    # Remove obvious labelled addresses without destroying all prose.
    address_pattern = re.compile(
        r"(?i)\b(address|पता|residing\s+at|resident\s+of)\s*[:=-]\s*"
        r"([^\n;|]{5,150})"
    )

    def address_replacement(match):
        _count(stats, "ADDRESS")
        return match.group(1) + ": [ADDRESS]"

    result = address_pattern.sub(address_replacement, result)

    return result


def detect_identifiers(text):
    found = []

    for kind, pattern in PATTERNS:
        if pattern.search(text):
            found.append(kind)

    return found