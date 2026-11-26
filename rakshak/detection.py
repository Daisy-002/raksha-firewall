import re
import unicodedata
from collections import Counter

# Deterministic, offline, CPU-only PII detection.
# Field-aware rules are deliberately stronger than free-text rules.

PATTERNS = {
    "PHONE": re.compile(
        r"(?<![0-9०-९])(?:\+?(?:91|९१)[\s.-]?)?0?[6-9६-९][0-9०-९]{4}[\s.-]?[0-9०-९]{5}(?![0-9०-९])"
    ),
    "EMAIL": re.compile(
        r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I
    ),
    "AADHAAR": re.compile(
        r"(?<!\d)(?:\d{4}[\s-]?){2}\d{4}(?!\d)"
    ),
    "AADHAAR_MASKED": re.compile(
        r"(?<![A-Z0-9])(?:X{4}|[*]{4}|[X*]{4})[\s-]?\d{4}[\s-]?\d{4}(?!\d)",
        re.I
    ),
    "PAN": re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b", re.I),
    "ABHA": re.compile(r"\b\d{2}-\d{4}-\d{4}-\d{4}\b"),
    "PIN": re.compile(r"(?<!\d)[1-9]\d{5}(?!\d)"),
}

# Field names are normalized before matching. Do not match generic
# "patient" alone: FHIR Patient references must remain intact.
FIELD_GROUPS = {
    "name": {
        "name", "patientname", "patientfullname", "fullname",
        "firstname", "middlename", "lastname", "surname",
        "beneficiaryname", "membername", "applicantname",
        "insuredname", "attendername", "guardianname",
        "fathername", "mothername", "spousename",
        "husbandname", "wifeName".lower(), "relative",
        "relative_name", "relativefullname", "nextofkin",
        "nextofkinname", "contactpersonname"
    },
    "mrn": {
        "mrn", "uhid", "patientid", "patient_id",
        "medicalrecordnumber", "medicalrecordno",
        "registrationid", "registrationnumber",
        "registrationno", "healthid", "abhaid",
        "hospitalnumber", "hospnumber", "opnumber",
        "ipnumber", "visitid", "insuranceid",
        "policyid", "memberid", "claimid"
    },
    "address": {
        "address", "fulladdress", "residentialaddress",
        "permanentaddress", "currentaddress", "house",
        "houseno", "house_number", "street", "streetname",
        "landmark", "locality", "mohalla", "colony",
        "village", "villagename", "gram", "town",
        "pincode", "pin", "postalcode", "zipcode",
        "district", "ward", "tehsil"
    },
    "insurance": {
        "insuranceid", "insurance_id", "policyid",
        "policynumber", "insurancenumber",
        "insurance_no", "membernumber", "claimnumber"
    },
    "dob": {
        "dob", "dateofbirth", "birthdate",
        "patientdob", "date_of_birth"
    },
}

SENSITIVE_HINTS = {
    "patientname", "fullname", "firstname", "lastname",
    "fathername", "mothername", "spousename", "guardianname",
    "relative_name", "relativefullname", "nextofkin",
    "address", "fulladdress", "residentialaddress",
    "permanentaddress", "currentaddress", "phone", "mobile",
    "mobileno", "phonenumber", "email", "emailid",
    "aadhaar", "aadhar", "pan", "abha", "passport",
    "village", "villagename", "mohalla", "locality",
    "landmark", "houseno", "house", "pincode", "postalcode",
    "insuranceid", "policynumber", "claimnumber",
}

# Labels in English, Hindi and common Hinglish.
LABELLED_VALUE = re.compile(
    r"(?P<label>"
    r"patient\s*name|name\s*of\s*patient|"
    r"patient\s*naam|pita(?:\s*/\s*pati)?\s*ka\s*naam|"
    r"naam|pata|gaon|gram|mohalla|tehsil|jila|zila|"
    r"mobile(?:\s*(?:no|number))?|phone(?:\s*(?:no|number))?|"
    r"father(?:'s)?\s*name|mother(?:'s)?\s*name|"
    r"husband(?:'s)?\s*name|wife(?:'s)?\s*name|"
    r"guardian(?:'s)?\s*name|relative\s*name|"
    r"s/o|d/o|w/o|c/o|"
    r"नाम|मरीज\s*का\s*नाम|रोगी\s*का\s*नाम|"
    r"पिता\s*का\s*नाम|माता\s*का\s*नाम|"
    r"पता|गांव|ग्राम|मोहल्ला|"
    r"मोबाइल|फोन|आधार|पिन\s*कोड"
    r")\s*[:：=\-]\s*(?P<value>[^\n,;|]{2,80})",
    re.I
)

RELATIVE_LABEL = re.compile(
    r"\b(?:s\s*/\s*o|d\s*/\s*o|w\s*/\s*o|c\s*/\s*o)\s*"
    r"[\w\u0900-\u097f][A-Za-z\u0900-\u097f.'-]+"
    r"(?:\s+[\w\u0900-\u097f][A-Za-z\u0900-\u097f.'-]+){0,3}",
    re.I
)

def _norm(value):
    value = unicodedata.normalize("NFKC", str(value or ""))
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def _field_role(field):
    key = _norm(field)

    # Date fields: let the existing date-shift engine transform them.
    if key.startswith(("dob", "dateofbirth", "birthdate", "janmtithi")):
        return "dob"

    if any(x in key for x in (
        "sourcepath", "originalpath", "filepath", "exportpath",
        "sourcefile", "originalfilename", "exportfilename"
    )):
        return "metadata"

    if any(x in key for x in (
        "phone", "mobile", "contactnumber", "contactno", "telephone"
    )):
        return "phone"

    if any(x in key for x in (
        "aadhaar", "aadhar", "pannumber", "passport", "nationalid"
    )):
        return "mrn"

    # Strong patient identifiers and insurance identifiers.
    if any(x in key for x in (
        "uhid", "mrn", "patientid", "medicalrecord",
        "patientref", "patientreference", "registrationid",
        "registrationnumber", "registrationno", "regno",
        "hospitalnumber", "opnumber", "ipnumber",
        "pmjayid", "insuranceid", "policyno",
        "policynumber", "claimnumber", "payerpan",
        "abhaid", "healthid", "visitid"
    )):
        return "mrn"

    # Person names, including relatives and guardians.
    if any(x in key for x in (
        "patientname", "firstname", "middlename", "lastname",
        "surname", "fullname", "beneficiaryname", "membername",
        "guardian", "father", "mother", "spouse", "husband",
        "wife", "relative", "nextofkin", "contactperson",
        "attendername", "refdoctor", "givenname", "familyname",
        "given", "family", "prefix", "suffix", "naam", "pita",
        "patika"
    )):
        return "name"

    # Addresses and geographic quasi-identifiers.
    if any(x in key for x in (
        "address", "street", "houseno", "house",
        "village", "mohalla", "locality", "landmark",
        "tehsil", "district", "town", "city", "colony",
        "ward", "postalcode", "pincode", "pin", "zipcode", "zip",
        "pata", "gaon", "gram", "jila", "zila"
    )):
        return "address"

    # Exact generic fields only when their context is unambiguous.
    if key in {"name", "patientfullname", "relative"}:
        return "name"

    return None

def _replace_patterns(value):
    value = PATTERNS["EMAIL"].sub("[REDACTED_EMAIL]", value)
    value = PATTERNS["PHONE"].sub("[REDACTED_PHONE]", value)
    value = PATTERNS["AADHAAR_MASKED"].sub("[REDACTED_AADHAAR]", value)
    value = PATTERNS["AADHAAR"].sub("[REDACTED_AADHAAR]", value)
    value = PATTERNS["PAN"].sub("[REDACTED_PAN]", value)
    value = PATTERNS["ABHA"].sub("[REDACTED_ABHA]", value)
    return value


def sanitize_value(field, value=None, stats=None):
    """
    Backwards-compatible project interface:
        sanitize_value(field, value, stats)

    Also accepts the newer two-argument form:
        sanitize_value(value, field)
    """
    if value is None:
        value = field
        field = None

    role = _field_role(field)

    # Preserve DOB for the engine's patient-specific date shifter.
    if role == "dob":
        return value

    if value is None:
        return value

    if isinstance(value, (int, float)):
        if role == "phone":
            return "[REDACTED_PHONE]"
        if role == "metadata":
            return "[REDACTED_METADATA]"
        if role in {"name", "mrn", "insurance", "address"}:
            return "[REDACTED]"
        return value

    if not isinstance(value, str):
        return value

    if not value.strip():
        return value

    # Preserve the existing statistics interface used by the pipeline/tests.
    if stats is not None:
        detected = sum(
            len(pattern.findall(value))
            for pattern in PATTERNS.values()
        )
        detected += len(LABELLED_VALUE.findall(value))
        detected += len(RELATIVE_LABEL.findall(value))
        if detected:
            stats.identifiers += detected

    if role == "name":
        return "[REDACTED_NAME]"
    if role == "mrn":
        return "[REDACTED_ID]"
    if role == "insurance":
        return "[REDACTED_INSURANCE_ID]"
    if role == "address":
        return "[GENERALIZED_LOCATION]"
    if role == "phone":
        return "[REDACTED_PHONE]"
    if role == "metadata":
        return "[REDACTED_METADATA]"

    value = _replace_patterns(value)

    def replace_label(match):
        label = match.group("label")
        label_norm = _norm(label)
        if any(x in label_norm for x in (
            "नाम", "name", "father", "mother", "husband",
            "wife", "guardian", "relative", "naam", "pita",
            "pati", "s/o", "d/o",
            "w/o", "c/o"
        )):
            return label + ": [REDACTED_NAME]"
        return label + ": [GENERALIZED_LOCATION]"

    value = LABELLED_VALUE.sub(replace_label, value)
    value = RELATIVE_LABEL.sub("[REDACTED_RELATIVE_NAME]", value)

    return value

def sanitize_field_name(field):
    # Preserve schema keys. Do not rename FHIR fields or CSV headers.
    return str(field)

def detect_identifiers(value):
    if not isinstance(value, str):
        value = str(value or "")

    found = Counter()
    for kind, pattern in PATTERNS.items():
        found[kind] += len(pattern.findall(value))

    for match in LABELLED_VALUE.finditer(value):
        label = _norm(match.group("label"))
        if any(x in label for x in ("नाम", "name", "father", "mother",
                                    "husband", "wife", "guardian",
                                    "relative", "s/o", "d/o", "w/o", "c/o")):
            found["NAME"] += 1
        else:
            found["ADDRESS"] += 1

    if RELATIVE_LABEL.search(value):
        found["RELATIVE_NAME"] += 1

    return dict(found)
