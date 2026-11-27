import base64
import re
from collections import Counter
from .normalization import normalize_key

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
    "HOSPITAL_ID": re.compile(
        r"\b(?:JJH|SNJ|HOSP|UHID|IPD|ADM|OPD)[-/]"
        r"[A-Z0-9][A-Z0-9/-]{2,}\b",
        re.I,
    ),
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
        "nextofkinname", "contactpersonname",
        "नाम", "मरीज का नाम", "रोगी का नाम",
        "पिता का नाम", "माता का नाम", "पिता/पति का नाम",
    },
    "mrn": {
        "mrn", "uhid", "patientid", "patient_id",
        "patientmrn", "patientnumber", "patientno",
        "medicalrecordnumber", "medicalrecordno",
        "medicalrecordid", "mrnumber", "mrno", "mrid",
        "chartnumber", "chartno", "hospitalid",
        "hospitalrecordnumber", "uhidnumber",
        "registrationid", "registrationnumber",
        "registrationno", "healthid", "abhaid",
        "hospitalnumber", "hospnumber", "opnumber",
        "ipnumber", "visitid", "patientref", "patientreference",
        "claimid", "claimnumber", "आधार संख्या", "आभा आईडी",
        "रोगी आईडी", "पंजीकरण संख्या",
    },
    "address": {
        "address", "fulladdress", "residentialaddress",
        "permanentaddress", "currentaddress", "addressline1",
        "addressline2", "addressline3", "streetaddress",
        "house", "building", "buildingname", "flat", "flatno",
        "flatnumber", "area", "neighborhood", "neighbourhood",
        "postoffice", "postofficename", "panchayat", "block",
        "subdistrict",
        "houseno", "house_number", "street", "streetname",
        "landmark", "locality", "mohalla", "colony",
        "village", "villagename", "gram", "town",
        "pincode", "pin", "postalcode", "zipcode",
        "district", "ward", "tehsil",
        "पता", "गांव", "गाँव", "ग्राम", "मोहल्ला",
        "जिला", "ज़िला", "तहसील", "पिन कोड", "मकान",
        "घर", "इलाका", "क्षेत्र", "डाकघर", "वार्ड",
    },
    "insurance": {
        "insuranceid", "insurance_id", "policyid",
        "policynumber", "insurancenumber",
        "insurance_no", "insuranceno", "membernumber",
        "memberid", "claimnumber", "claimid",
        "बीमा संख्या", "पॉलिसी नंबर", "दावा संख्या", "सदस्य संख्या",
    },
    "dob": {
        "dob", "dateofbirth", "birthdate",
        "patientdob", "date_of_birth", "janmtithi",
        "जन्म तिथि", "जन्मतिथि", "जन्म तारीख", "जन्मतारीख",
    },
    "phone": {
        "phone", "phone_no", "phone_number", "mobile",
        "mobileno", "mobilenumber", "contactnumber",
        "contactno", "telephone", "mobile no", "mobile number",
        "फोन", "फोन नंबर", "मोबाइल", "मोबाइल नंबर",
        "संपर्क नंबर",
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
    r"date\s*of\s*birth|dob|"
    r"patient|name|patient\s*name|"
    r"name\s*of\s*patient|"
    r"patient\s*naam|pita(?:\s*/\s*pati)?\s*ka\s*naam|"
    r"naam|pata|gaon|gram|mohalla|tehsil|jila|zila|"
    r"mobile(?:\s*(?:no|number))?|phone(?:\s*(?:no|number))?|"
    r"father(?:'s)?\s*name|mother(?:'s)?\s*name|"
    r"husband(?:'s)?\s*name|wife(?:'s)?\s*name|"
    r"guardian(?:'s)?\s*name|relative\s*name|"
    r"house(?:\s*(?:no\.?|number))?|flat(?:\s*(?:no\.?|number))?|"
    r"building(?:\s*name)?|street(?:\s*address)?|"
    r"address(?:\s*(?:line\s*\d|details?))?|"
    r"locality|landmark|area|neighbou?rhood|colony|"
    r"village|town|city|district|ward|tehsil|block|"
    r"post\s*office|postal\s*code|zip(?:\s*code)?|"
    r"pin(?:\s*code)?|"
    r"s/o|d/o|w/o|c/o|"
    r"नाम|मरीज\s*का\s*नाम|रोगी\s*का\s*नाम|"
    r"पिता\s*का\s*नाम|माता\s*का\s*नाम|"
    r"पता|गांव|ग्राम|मोहल्ला|मकान(?:\s*संख्या)?|"
    r"घर(?:\s*संख्या)?|इलाका|क्षेत्र|डाकघर|वार्ड|"
    r"मोबाइल|फोन|आधार|पिन\s*कोड|"
    r"जिला|तहसील|"
    r"जन्म\s*तिथि|जन्मतिथि"
    r")\s*[:：=\-]\s*(?P<value>[^\n,;|]{2,80})",
    re.I
)

MRN_LABELLED_VALUE = re.compile(
    r"(?<![A-Z0-9])"
    r"(?P<label>"
    r"mrn|mr\s*(?:no\.?|number)?|"
    r"medical[\s_-]*record(?:[\s_-]*(?:id|number|no\.?))?|"
    r"patient[\s_-]*(?:id|number|no\.?)|"
    r"hospital[\s_-]*(?:id|number|no\.?)|"
    r"uhid(?:[\s_-]*(?:id|number|no\.?))?|"
    r"chart[\s_-]*(?:id|number|no\.?)|"
    r"registration[\s_-]*(?:id|number|no\.?)|"
    r"reg[\s_-]*no\.?"
    r")"
    r"(?P<separator>\s*(?:[#:=\-]\s*|\s+))"
    r"(?P<value>(?=[A-Z0-9./_-]*\d)"
    r"[A-Z0-9](?:[A-Z0-9./_-]{1,}[A-Z0-9]))"
    r"(?![A-Z0-9])",
    re.I,
)

RELATIVE_LABEL = re.compile(
    r"\b(?:s\s*/\s*o|d\s*/\s*o|w\s*/\s*o|c\s*/\s*o)\s*"
    r"[\w\u0900-\u097f][A-Za-z\u0900-\u097f.'-]+"
    r"(?:\s+[\w\u0900-\u097f][A-Za-z\u0900-\u097f.'-]+){0,3}",
    re.I
)

FHIR_NARRATIVE_NAME = re.compile(
    r"(?is)(<div\b[^>]*>\s*)"
    r"(?P<name>(?:[A-Z][A-Za-z.'-]*|[\u0900-\u097f]+)"
    r"(?:\s+(?:[A-Z][A-Za-z.'-]*|[\u0900-\u097f]+)){1,3})"
    r"(?=,\s*\d{1,3}\s*(?:yrs?|years?|y/o)\b)"
)

TIMESTAMP_RELATIVE_NAME = re.compile(
    r"(?im)(\b\d{1,2}:\d{2}\s*[-–—]\s*)"
    r"(?:[A-Z][A-Za-z.'-]*|[\u0900-\u097f]+)"
    r"(?:\s+(?:[A-Z][A-Za-z.'-]*|[\u0900-\u097f]+)){0,3}"
    r"(?=\s*[-–—]\s*[KSDWC]\s*/(?:\s*O\b)?)"
)

HINGLISH_NAME_WORD = (
    r"(?!"
    r"and|are|aaj|admit(?:ted)?|blood|bp|bukhar|case|complaint|"
    r"complaints|cold|cough|dard|days?|doctor|fever|for|from|hai|"
    r"had|has|have|headache|high|history|hospital|ji|ka|kal|ke|khansi|"
    r"ki|ko|low|medicine|ne|pain|patient|pulse|sahab|sahib|sugar|"
    r"the|tha|thee|thi|today|treatment|with|yesterday"
    r")\b[A-Za-z][A-Za-z.'-]{1,}"
)
HINGLISH_NAME = rf"{HINGLISH_NAME_WORD}(?:\s+{HINGLISH_NAME_WORD}){{0,2}}"
HINGLISH_CLINICAL_TERM = (
    r"(?:bukhar|fever|khansi|cough|jukam|cold|dard|pain|headache|"
    r"sir\s*dard|pet\s*dard|chest\s*pain|saans|breathing|sugar|"
    r"diabetes|bp|blood\s+pressure|pulse|vomit(?:ing)?|ulti|"
    r"dizziness|chakkar|weakness|kamzori|infection|rash|swelling|"
    r"sujan|admit(?:ted)?|checkup|treatment|medicine|dawa|doctor|"
    r"hospital|clinic|opd|consult(?:ed|ation)?|complain(?:ed|ing)?|"
    r"report(?:ed)?|bataya|bola|kaha|dikhaya|aaya|aayi|laaya|laayi)"
)
HINGLISH_PERSON_CONTEXT = re.compile(
    rf"(?<![\w])(?P<name>{HINGLISH_NAME})"
    r"(?:\s+(?:sahab|sahib|ji))?"
    rf"(?=\s+(?:"
    rf"ko\s+(?:(?:\d{{1,2}}\s*(?:din|days?|haft(?:e|a)|weeks?|"
    rf"mahine?|months?)\s*(?:se)?|aaj|kal)\s*)?"
    rf"(?:{HINGLISH_CLINICAL_TERM})\b|"
    rf"(?:ka|ki|ke)\s+(?:bp|blood\s+pressure|pulse|sugar|"
    rf"fever|bukhar|dard|pain)\b|"
    rf"ne\s+(?:complain(?:ed|ing)?|report(?:ed)?|bataya|bola|kaha|"
    rf"dikhaya|(?:{HINGLISH_CLINICAL_TERM}))\b|"
    rf"(?:is\s+)?(?:admit(?:ted)?|referred|under\s+treatment)\b"
    rf"))",
    re.I,
)
HINGLISH_REVERSED_PERSON_CONTEXT = re.compile(
    rf"(?i)(?P<context>\b(?:{HINGLISH_CLINICAL_TERM})\b)"
    rf"(?P<gap>[^\n.!?;]{{0,48}}?)"
    rf"(?P<name>{HINGLISH_NAME})"
    rf"(?P<particle>\s+(?:ko|ka|ki|ke)\b)"
)

HINDI_PERSON_DURATION_CONTEXT = re.compile(
    r"[\u0900-\u097f]+(?:\s+(?!को\b)[\u0900-\u097f]+){1,3}"
    r"(?=\s+को\s+\d+\s*(?:दिन|दिनों|दिवस)\s+से(?:\s|$))"
)
BASE64_CANDIDATE = re.compile(
    r"(?<![A-Za-z0-9+/])"
    r"(?:[A-Za-z0-9+/]{4}){8,}"
    r"(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?"
    r"(?![A-Za-z0-9+/=])"
)

def _norm(value):
    return normalize_key(str(value or ""))


NORMALIZED_FIELD_GROUPS = {
    role: {_norm(alias) for alias in aliases}
    for role, aliases in FIELD_GROUPS.items()
}

DATE_FIELD_NAMES = {
    _norm(name)
    for name in {
        "date", "admissiondate", "dischargedate", "visitdate",
        "appointmentdate", "registrationdate", "servicedate",
        "dateofservice", "collectiondate", "specimendate", "testdate",
        "issuedate", "createddate", "updateddate",
        "प्रवेश तिथि", "छुट्टी तिथि", "भेंट तिथि",
        "पंजीकरण तिथि", "तारीख",
    }
}


def _field_role(field):
    key = _norm(field)

    # Date fields: let the existing date-shift engine transform them.
    if key in NORMALIZED_FIELD_GROUPS["dob"] or key.startswith(
        ("dob", "dateofbirth", "birthdate", "janmtithi")
    ):
        return "dob"

    for role in ("phone", "insurance", "mrn", "name", "address"):
        if key in NORMALIZED_FIELD_GROUPS[role]:
            return role

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

    if any(x in key for x in (
        "insurance", "policyno", "policynumber",
        "membernumber", "memberid", "claimnumber", "claimid",
        "payerpan", "insuranceno"
    )):
        return "insurance"

    if any(x in key for x in (
        "uhid", "mrn", "patientid", "medicalrecord",
        "patientref", "patientreference", "registrationid",
        "registrationnumber", "registrationno", "regno",
        "hospitalnumber", "opnumber", "ipnumber",
        "pmjayid", "abhaid", "healthid", "visitid"
    )):
        return "mrn"

    # Person names, including relatives and guardians.
    if any(x in key for x in (
        "patientname", "firstname", "middlename", "lastname",
        "surname", "fullname", "beneficiaryname", "membername",
        "guardian", "father", "mother", "spouse", "husband",
        "wife", "relative", "nextofkin", "contactperson",
        "attendername", "refdoctor", "givenname", "familyname",
        "naam", "pita", "patika"
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


def is_date_field(field):
    key = _norm(field)
    return key in DATE_FIELD_NAMES or key in NORMALIZED_FIELD_GROUPS["dob"]


def _replace_patterns(value):
    value = PATTERNS["EMAIL"].sub("[REDACTED_EMAIL]", value)
    value = PATTERNS["PHONE"].sub("[REDACTED_PHONE]", value)
    value = PATTERNS["AADHAAR_MASKED"].sub("[REDACTED_AADHAAR]", value)
    value = PATTERNS["AADHAAR"].sub("[REDACTED_AADHAAR]", value)
    value = PATTERNS["PAN"].sub("[REDACTED_PAN]", value)
    value = PATTERNS["ABHA"].sub("[REDACTED_ABHA]", value)
    value = PATTERNS["HOSPITAL_ID"].sub("[REDACTED_ID]", value)
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
        detected += len(MRN_LABELLED_VALUE.findall(value))
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
    value = MRN_LABELLED_VALUE.sub(
        lambda match: (
            match.group("label")
            + match.group("separator")
            + "[REDACTED_ID]"
        ),
        value,
    )

    def replace_label(match):
        label = match.group("label")
        label_norm = _norm(label)
        if any(x in label_norm for x in (
            "नाम", "name", "patient", "father", "mother", "husband",
            "wife", "guardian", "relative", "naam", "pita",
            "pati", "s/o", "d/o",
            "w/o", "c/o"
        )):
            return label + ": [REDACTED_NAME]"
        if any(x in label_norm for x in (
            "dob", "dateofbirth", "जन्मतिथि"
        )):
            return label + ": [REDACTED_DATE]"
        return label + ": [GENERALIZED_LOCATION]"

    value = LABELLED_VALUE.sub(replace_label, value)
    value = RELATIVE_LABEL.sub("[REDACTED_RELATIVE_NAME]", value)

    if _norm(field) == "fhirnarrative":
        value = FHIR_NARRATIVE_NAME.sub(
            r"\1[REDACTED_NAME]", value
        )

    value = TIMESTAMP_RELATIVE_NAME.sub(
        r"\1[REDACTED_NAME]", value
    )
    value = HINGLISH_PERSON_CONTEXT.sub("[REDACTED_NAME]", value)
    value = HINGLISH_REVERSED_PERSON_CONTEXT.sub(
        lambda match: (
            match.group("context")
            + match.group("gap")
            + "[REDACTED_NAME]"
            + match.group("particle")
        ),
        value,
    )
    value = HINDI_PERSON_DURATION_CONTEXT.sub(
        "[REDACTED_NAME]", value
    )

    def sanitize_base64(match):
        encoded = match.group(0)
        try:
            decoded = base64.b64decode(encoded, validate=True).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            return encoded

        if not decoded or any(
            not character.isprintable() and character not in "\r\n\t"
            for character in decoded
        ):
            return encoded

        cleaned = sanitize_value("clinical_note", decoded, stats)
        if cleaned == decoded:
            return encoded
        return base64.b64encode(cleaned.encode("utf-8")).decode("ascii")

    value = BASE64_CANDIDATE.sub(sanitize_base64, value)

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

    if MRN_LABELLED_VALUE.search(value):
        found["MRN"] += len(MRN_LABELLED_VALUE.findall(value))

    if RELATIVE_LABEL.search(value):
        found["RELATIVE_NAME"] += 1

    return dict(found)
