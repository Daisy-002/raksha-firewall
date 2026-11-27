"""Harvest linking clues (pass 1) and write sanitised values (pass 2)."""
import base64
import re

from . import dates
from .detection import ID_PATTERNS, detect
from .fields import tokens
from .records import NON_PATIENT_RESOURCES, decode_base64, list_parents, walk
from .textutil import DEVANAGARI, TOKEN, clean, fold_digits, phonetic, similar_word, skeleton, words
from .vocab import GENERIC_NAME_PARTS, HONORIFICS, PREFIXES, STOPWORDS

ID_TYPES = {"mrn": "MRN", "phone": "PHONE", "aadhaar": "AADHAAR", "abha": "ABHA", "pan": "PAN",
            "insurance": "INSURANCE", "email": "EMAIL"}
NAME_SPANS = {"PATIENT_NAME", "RELATIVE_NAME", "PERSON_NAME"}
_EMPTY = {"", "na", "n/a", "nil", "none", "null", "unknown", "-", "--"}
_RELATION = re.compile(r"(?i)^\s*(?:(?:[SDWCH]\s*/\s*[Oo])|son of|daughter of|wife of|husband of|पुत्र|पुत्री|पत्नी|पति|पिता)[\s:.-]*")
_AGE = [re.compile(p) for p in (
    r"(?i)(?:\bage(?:\s*/\s*(?:sex|gender))?|\bumar|आयु|उम्र)\s*[:\-=]?\s*(?P<a>\d{1,3})(?![\d/.-])",
    r"(?i)(?:\bage(?:\s*/\s*(?:sex|gender))?|\bumar|आयु|उम्र)\s*[:\-=]?\s*(?P<a>\d{1,3})(?=\s*/\s*[MF])",
    r"(?<![\d./-])(?P<a>\d{1,3})(?=\s*(?i:yrs?|years?|y|वर्ष|साल)\.?\s*(?:/|,)\s*(?i:m\b|f\b|male|female|महिला|पुरुष))",
    r"(?<![\d./-])(?P<a>\d{1,3})(?=\s*/\s*[MF]\b)",
    r"(?<![\d./-])(?P<a>\d{1,3})(?=[ -](?i:years?|yrs?)[ -]old\b)",
    r"(?<![\d./-])(?P<a>\d{1,3})(?=\s*(?:वर्षीय|saal\s+(?:ka|ki|ke)\b))",
)]
_DOB_LABEL = re.compile(r"(?i)(?:\bd\.?o\.?b\.?|date\s+of\s+birth|birth\s*date|janm\s*tithi|जन्म\s*(?:तिथि|तारीख|दिनांक))\s*[:\-=]?\s*$")
ICD = re.compile(r"(?<![A-Za-z0-9/-])[A-TV-Z]\d{2}(?:\.\d{1,2})?(?![A-Za-z0-9/-])")


def identifier(kind, text):
    value = fold_digits(clean(text))
    if kind in {"PHONE", "AADHAAR", "ABHA"}:
        value = re.sub(r"\D", "", value)
        if kind == "PHONE":
            return value[-10:] if len(value) >= 10 else None
        return value if len(value) == (12 if kind == "AADHAAR" else 14) else None
    if kind == "EMAIL":
        return value.casefold()
    value = re.sub(r"[^A-Z0-9]", "", value.upper())
    return value if len(value) >= 5 and any(c.isdigit() for c in value) else None


def name_tokens(name):
    return tuple(w for w in words(clean(name) if not DEVANAGARI.search(name) else name)
                 if w.casefold() not in HONORIFICS and w.casefold() not in PREFIXES and phonetic(w))


def same_name(left, right):
    """True when every part of the shorter name matches a part of the longer one."""
    short, long_ = sorted((left, right), key=len)
    if not short:
        return False
    remaining = list(long_)
    identifying = False
    for word in short:
        match = next((w for w in remaining if similar_word(word, w)), None)
        if match is None:
            return False
        remaining.remove(match)
        identifying = identifying or phonetic(word) not in GENERIC_NAME_PARTS
    return identifying


def band(age, width, top):
    if age >= top:
        return f"{top}+"
    low = age // width * width
    return f"{low}-{low + width - 1}"


class Clues:
    def __init__(self):
        self.ids = set()
        self.names = []
        self.others = []
        self.relatives = []
        self.dobs = set()
        self.villages = set()
        self.ages = []
        self.codes = set()
        self.years = []

    def add_id(self, kind, text):
        value = identifier(kind, text)
        if value:
            self.ids.add((kind, value))

    def add_name(self, bucket, text):
        parts = name_tokens(_RELATION.sub("", text))
        if parts and parts not in bucket:
            bucket.append(parts)


class Harvester:
    """Pass 1: collect identity clues from one record and grow the lexicon."""

    def __init__(self, lexicon, order):
        self.lexicon, self.order, self.clues = lexicon, order, Clues()
        self.parts = []

    def finish(self):
        """Join first and last name columns into one patient name."""
        if self.parts:
            ordered = list(dict.fromkeys(text for _, text in sorted(self.parts, key=lambda p: p[0])))
            full = " ".join(ordered)
            self.clues.add_name(self.clues.names, full)
            self.lexicon.add_name(full)
        return self.clues

    def entry(self, key, value, role, resource, parents):
        self.text(str(key))
        return key, value

    def value(self, value, key, parents, role, resource):
        if value is None or isinstance(value, bool):
            return value
        text = str(value).strip()
        if text.casefold() in _EMPTY:
            return value
        clues = self.clues
        if str(key) == "code" and ICD.fullmatch(text):
            clues.codes.add(text)
        part = set(tokens(str(key))) | {"".join(tokens(str(key)))}
        if role == "name" and part & {"first", "last", "firstname", "lastname", "surname", "middlename", "given", "family"}:
            if "[" not in text:
                order = 2 if part & {"last", "lastname", "surname", "family"} else 0
                self.parts.append((order, text))
            return value
        if role in ID_TYPES:
            clues.add_id(ID_TYPES[role], text)
        elif role in {"name", "relative"} and str(key).casefold().endswith("by"):
            if re.match(r"[A-Z][a-z]+(?:\s+[A-Z][A-Za-z'.-]+)+$", text) and not text.startswith("Dr"):
                self.lexicon.add_name(text)
        elif role in {"name", "relative"}:
            bare = _RELATION.sub("", text)
            if not re.match(r"(?:Dr\.?|डॉ)", bare) and re.search(r"[^\W\d_]", bare) and len(bare) <= 80 and "[" not in bare:
                found = detect(bare)
                if not any(kind not in NAME_SPANS for _, _, kind in found):
                    clues.add_name(clues.names if role == "name" else clues.relatives, bare)
                    self.lexicon.add_name(bare)
        elif role == "dob":
            clues.dobs.update(d for _, _, d, _, _ in dates.find(text, self.order))
        elif role == "age":
            match = re.search(r"\d{1,3}", fold_digits(text))
            if match and int(match.group()) <= 120:
                clues.ages.append(int(match.group()))
        elif role == "village":
            clues.villages.add(skeleton("".join(words(text))))
            self.lexicon.add_place(text)
        if role in {"text", "address", "date", "path"} or role == "doctor":
            self.text(text, role)
        return value

    def text(self, text, role="text"):
        decoded = decode_base64(text)
        if decoded is not None:
            text = decoded
        clues = self.clues
        spans = detect(text, address_hint=role == "address")
        for start, end, kind in spans:
            found = text[start:end]
            if kind in {"MRN", "PHONE", "AADHAAR", "ABHA", "PAN", "INSURANCE", "EMAIL"}:
                clues.add_id(kind, found)
            elif kind == "PATIENT_NAME":
                clues.add_name(clues.names, found)
                self.lexicon.add_name(found)
            elif kind == "RELATIVE_NAME":
                clues.add_name(clues.relatives, found)
                self.lexicon.add_name(found)
            elif kind == "PERSON_NAME":
                clues.add_name(clues.others, found)
                self.lexicon.add_name(found)
            elif kind == "VILLAGE":
                clues.villages.add(skeleton("".join(words(found))))
                self.lexicon.add_place(found)
        for pattern in _AGE:
            for match in pattern.finditer(fold_digits(text)):
                if int(match["a"]) <= 120:
                    clues.ages.append(int(match["a"]))
        for start, _, date, _, match in dates.find(text, self.order):
            if _DOB_LABEL.search(text[max(0, start - 40):start]):
                clues.dobs.add(date)
            else:
                clues.years.append(date.year)
        clues.codes.update(ICD.findall(text))


class Redactor:
    """Pass 2: produce the sanitised form of one record."""

    def __init__(self, context, clues, pid, offset, order, rare):
        self.context, self.clues, self.pid, self.offset = context, clues, pid, offset
        self.order, self.rare = order, rare
        self.locator = "doc"
        self.policy, self.lexicon = context.policy, context.lexicon
        self.year = max(set(clues.years), key=lambda y: (clues.years.count(y), y)) if clues.years else 2026
        self.generalized = False

    def count(self, kind):
        self.context.entities[kind] = self.context.entities.get(kind, 0) + 1

    def age(self, number):
        self.generalized = True
        width = self.policy["wide_age_band_years" if self.rare else "age_band_years"]
        return band(number, width, self.policy["top_age"])

    def pin(self, text):
        self.generalized = True
        digits = re.sub(r"\D", "", fold_digits(text))
        keep = 0 if self.rare else self.policy["pin_digits_kept"]
        return digits[:keep] + "X" * (6 - keep)

    def id_token(self, kind, text):
        self.count(kind)
        owner = self.context.owners.get((kind, identifier(kind, text)))
        if kind == "MRN" and owner:
            return owner
        return f"[{kind}]"

    def name_token(self, text, kind):
        self.count(kind)
        if kind == "RELATIVE_NAME":
            return "[RELATIVE]"
        parts = name_tokens(text)
        if self.pid and any(same_name(parts, own) for own in self.clues.names or self.clues.others):
            if not any(same_name(parts, relative) for relative in self.clues.relatives):
                return self.pid
        return "[NAME]"

    def address(self, text):
        """Keep only district and a PIN prefix."""
        self.count("ADDRESS")
        self.generalized = True
        kept = ["[ADDRESS]"]
        district = re.search(r"(?i)(?:distt?\.?|district|जिला|ज़िला)\s*[:-]?\s*([A-Za-zऀ-ॿ][A-Za-zऀ-ॿ ]*)", text)
        if district and not self.rare:
            kept.append("Distt. " + district.group(1).strip())
        pin = re.search(r"(?<!\d)[1-9]\d{2}\s?\d{3}(?!\d)", fold_digits(text))
        suffix = f" - {self.pin(pin.group())}" if pin else ""
        return ", ".join(kept) + suffix

    def text(self, text, role="text"):
        if not text:
            return text
        replacements = []
        for start, end, kind in detect(text, self.lexicon, address_hint=role == "address"):
            found = text[start:end]
            if kind in NAME_SPANS:
                new = self.name_token(found, kind)
            elif kind == "PIN":
                self.count(kind)
                new = self.pin(found)
            elif kind in {"VILLAGE", "TEHSIL", "HOUSE", "LOCALITY", "LANDMARK"}:
                self.count(kind)
                self.generalized = True
                new = f"[{kind}]"
            else:
                new = self.id_token(kind.replace("_MASKED", ""), found)
            replacements.append((start, end, new))

        def free(start, end):
            return not any(start < e and s < end for s, e, _ in replacements)

        # Short forms of this patient's own name, such as a first part used as a nickname.
        own = [w.casefold() for name in self.clues.names for w in name]
        for match in TOKEN.finditer(text):
            word = match.group()
            if (len(word) >= 4 and word[0].isupper() and word.casefold() not in STOPWORDS
                    and free(*match.span()) and any(k.startswith(word.casefold()) for k in own)):
                self.count("PATIENT_NAME")
                replacements.append((*match.span(), self.pid or "[NAME]"))

        for start, end, date, kind, match in dates.find(text, self.order, self.year):
            if not free(start, end):
                continue
            if _DOB_LABEL.search(text[max(0, start - 40):start]) or date in self.clues.dobs:
                self.count("DOB")
                new = "[DOB]"
            else:
                new = dates.render(text[start:end], date, self.offset, kind, match, self.order)
            self.generalized = True
            replacements.append((start, end, new))
        folded = fold_digits(text)
        for pattern in _AGE:
            for match in pattern.finditer(folded):
                start, end = match.span("a")
                if int(match["a"]) <= 120 and free(start, end):
                    replacements.append((start, end, self.age(int(match["a"]))))
        if self.rare:
            for match in re.finditer(r"(?i)(?:distt?\.?|district|जिला)\s*[:-]?\s*(?P<v>[A-Zऀ-ॿ][A-Za-zऀ-ॿ]+(?: [A-Z][a-z]+)?)", text):
                if free(*match.span("v")):
                    replacements.append((*match.span("v"), "[DISTRICT]"))
        for start, end, new in sorted(replacements, reverse=True):
            text = text[:start] + new + text[end:]

        def hidden(match):
            decoded = decode_base64(match.group())
            if decoded is None:
                return match.group()
            return base64.b64encode(self.text(decoded).encode("utf-8")).decode("ascii")

        return re.sub(r"(?<![A-Za-z0-9+/])[A-Za-z0-9+/]{24,}={0,2}(?![A-Za-z0-9+/=])", hidden, text)

    def value(self, value, key, parents, role, resource):
        if value is None or isinstance(value, bool):
            return value
        text = str(value)
        if text.strip().casefold() in _EMPTY:
            return value
        if str(key) == "data" and "contentType" not in text and any("attach" in str(p).lower() or str(p) in {"content", "presentedForm"} for p in parents):
            decoded = decode_base64(text)
            payload = self.text(decoded) if decoded is not None else "[REMOVED]"
            return base64.b64encode(payload.encode("utf-8")).decode("ascii")
        if role in ID_TYPES:
            known = identifier(ID_TYPES[role], text)
            if known is None and role == "mrn":
                return self.text(text)
            if role == "mrn" and self.pid:
                self.count("MRN")
                return self.pid
            return self.id_token(ID_TYPES[role], text)
        if role in {"name", "relative"}:
            if re.match(r"\s*(?:Dr\.?\s|डॉ)", text) or not re.search(r"[^\W\d_]", text):
                return self.text(text)
            if str(key).casefold().endswith("by") and not re.match(r"[A-Z][a-z]+(?:\s+[A-Z][A-Za-z'.-]+)+$", text):
                return self.text(text)
            if str(key).casefold().endswith("by"):
                self.count("PERSON_NAME")
                return "[NAME]"
            prefix = _RELATION.match(text)
            kept = prefix.group() if prefix else ""
            if role == "relative":
                self.count("RELATIVE_NAME")
                return kept + "[RELATIVE]"
            self.count("PATIENT_NAME")
            return self.pid or "[NAME]"
        if role == "dob":
            self.count("DOB")
            self.generalized = True
            return ""
        if role == "age":
            if isinstance(value, (int, float)):
                return self.age(int(value)) if 0 <= value <= 120 else value
            match = re.search(r"\d{1,3}", fold_digits(text))
            if match and int(match.group()) <= 120:
                return text[:match.start()] + self.age(int(match.group())) + text[match.end():]
            return self.text(text)
        if role == "pin":
            self.count("PIN")
            return self.pin(text)
        if role in {"village", "tehsil"}:
            self.count(role.upper())
            self.generalized = True
            return f"[{role.upper()}]"
        if role == "district" and self.rare:
            self.generalized = True
            return "[DISTRICT]"
        if role == "address":
            return self.address(text)
        if role == "path":
            self.count("PATH")
            return "[PATH]"
        if role == "doctor":
            return value
        if isinstance(value, (int, float)):
            digits = str(value)
            for kind, pattern in ID_PATTERNS:
                if kind in {"PHONE", "AADHAAR", "ABHA"} and pattern.fullmatch(digits):
                    return self.id_token(kind, digits)
            return value
        return self.text(text, role)

    def entry(self, key, value, role, resource, parents):
        # FHIR dates must stay valid, so a birth date is dropped instead of blanked.
        if resource and str(key) == "birthDate":
            self.count("DOB")
            self.generalized = True
            return None, None
        if resource and resource not in NON_PATIENT_RESOURCES and str(key) in {"id", "fullUrl", "reference"}:
            if str(value).startswith(("urn:uuid:", "#urn:")) or re.fullmatch(r"[0-9a-f-]{36}", str(value)):
                return key, value
        return self.text(str(key)), value

    def record(self, record, document):
        if document.kind == "text":
            return self.text(record)
        if document.kind == "table":
            header = document.data[0]
            roles = document.roles
            return [self.value(cell, header[i] if i < len(header) else "", (),
                               roles[i] if i < len(roles) else "text", None)
                    for i, cell in enumerate(record)]
        return walk(record, self, parents=list_parents(self.locator))
