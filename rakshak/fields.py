"""Decide what a column or JSON key means from the words in its label."""
import re

from .textutil import clean

_SPLIT = re.compile(r"[^0-9a-z\u0900-\u097F]+")

# Ancestors under which "name"/"id"/"text" does not describe a patient.
NON_PERSON = frozenset("""facility hospital organization organisation lab laboratory panel panels
test tests drug drugs medication medications rx diagnosis diagnoses coding code ward wards
department system doctor practitioner author performer consultant package procedure form
product schema class category profile""".split())


def tokens(label):
    label = re.sub(r"([a-z])([A-Z])", r"\1 \2", str(label))
    return [t for t in _SPLIT.split(clean(label).casefold()) if t]


def classify(label, path=()):
    """Return a role for a structured field. `path` holds the ancestor keys."""
    t = tokens(label)
    if not t:
        return "text"
    s, joined = set(t), "".join(t)
    s |= {w[:-1] for w in s if w in {"mothers", "fathers", "husbands", "guardians", "patients"}}
    parents = [w for key in path for w in tokens(key)]
    relative_parent = bool(set(parents) & {"guardian", "contact", "relative", "attendant", "kin", "nominee"})

    if re.search(r"(?i)(?<![a-z])[swdc]\s*/\s*o(?![a-z])", str(label)):
        return "relative"

    if re.search(r"(?i)contact\s*(?:#|no\b|num)", str(label)):
        return "phone"

    def has(*items):
        return bool(s & set(items))

    def sub(*items):
        return any(i in joined for i in items)

    if has("doctor", "dr", "consultant", "physician", "surgeon") or sub("refdoctor", "डॉक्टर"):
        return "doctor"
    # "created_by", "raised_by" and similar hold staff or visitor names.
    if len(t) > 1 and t[-1] == "by" and t[0] not in {"referred", "ref"}:
        return "name"
    if sub("sourcepath", "filepath", "originalpath", "exportpath", "filename", "sourcefile"):
        return "path"
    if sub("email", "ईमेल") or (has("abha") and has("address")):
        return "email"
    if sub("aadhaar", "aadhar", "adhaar", "adhar", "uidai", "आधार"):
        return "aadhaar"
    if sub("abha", "healthid", "आभा"):
        return "abha"
    if has("pan") or sub("panno", "pannumber", "payerpan"):
        return "pan"
    if sub("policy", "insurance", "pmjay", "ayushman", "beneficiaryid", "memberid", "tpaid", "बीमा", "पॉलिसी"):
        return "insurance"
    if has("phone", "mobile", "mob", "callback", "telephone", "tel", "whatsapp", "फोन", "मोबाइल", "दूरभाष") or sub(
            "phone", "mobile", "contactno", "contactnumber", "contactnum", "cellno"):
        return "phone"
    if has("dob") or sub("dateofbirth", "birthdate", "birthdt", "janmtithi", "janamtithi", "जन्म"):
        return "dob"
    if sub("uhid", "mrn", "patientid", "patientref", "patientno", "regno", "registrationno",
           "registrationnumber", "registrationid", "medicalrecord", "crno", "crnumber", "hospitalid",
           "patientreference", "ipdno", "ipno", "admissionno", "admissionnumber", "पंजीकरणसं", "रोगीआईडी",
           "पंजीकरणसंख्या"):
        return "mrn"
    if has("reg", "ipd", "uh") and has("no", "id", "number", "सं", "संख्या"):
        return "mrn"
    if sub("date", "तारीख", "तिथि", "datetime", "timestamp") or (s & {"dt", "on", "doa", "dod", "collected", "reported", "registered", "admitted", "discharged"}):
        return "date"
    if has("age", "umar", "umr", "आयु", "उम्र") or sub("agesex", "ageyears", "patientage"):
        return "age"
    if sub("pincode", "postalcode", "zipcode", "पिनकोड") or has("pin", "zip", "postal"):
        return "pin"
    if has("village", "gram", "gaon", "vill", "city", "ग्राम", "गांव", "गाँव") or sub("village"):
        return "village"
    if has("tehsil", "taluk", "taluka", "block", "तहसील"):
        return "tehsil"
    if has("district", "distt", "dist", "jila", "zila", "जिला", "ज़िला"):
        return "district"
    if has("state", "country", "राज्य"):
        return "text"
    if set(parents) & NON_PERSON and not relative_parent:
        return "text"
    if has("guardian", "relative", "father", "mother", "husband", "wife", "spouse", "attendant", "kin",
           "nominee", "pita", "pati", "पिता", "पति", "माता", "अभिभावक", "caregiver", "giver", "carer", "escort") or sub("relativename", "careof", "nextofkin"):
        if has("relation", "relationship", "type") and not has("name", "naam", "नाम"):
            return "text"
        return "relative"
    if has("address", "addr", "street", "locality", "landmark", "mohalla", "house", "colony", "line",
           "residence", "pata", "पता", "मोहल्ला", "मकान") or sub("address", "houseno"):
        return "address"
    namey = has("name", "naam", "नाम", "patient", "mareez", "beneficiary", "applicant", "insured", "claimant") or sub(
        "patientname", "fullname", "firstname", "lastname", "surname", "middlename", "membername")
    if namey or s & {"given", "family", "surname"} or (joined in {"first", "last", "local"} and "name" in parents):
        if has("history", "status", "type", "count", "id", "ref", "index"):
            return "text"
        if relative_parent:
            return "relative"
        return "name"
    if relative_parent and joined in {"text", "display"}:
        return "relative"
    return "text"
