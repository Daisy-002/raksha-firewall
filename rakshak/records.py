"""Split documents into patient records and visit every value inside them."""
import base64
import binascii
import re

from .fields import NON_PERSON, classify, tokens

_IDENTITY_ROLES = {"name", "relative", "mrn", "phone", "aadhaar", "abha", "dob"}
_BASE64 = re.compile(r"[A-Za-z0-9+/]{24,}={0,2}")
# FHIR resources that describe staff, places or products, not patients.
NON_PATIENT_RESOURCES = {"Practitioner", "PractitionerRole", "Organization", "Location", "Medication", "HealthcareService"}


def decode_base64(value):
    """Return the text hidden in a base64 value, or None."""
    compact = "".join(value.split())
    if len(compact) < 16 or len(compact) % 4 or not re.fullmatch(r"[A-Za-z0-9+/]+={0,2}", compact):
        return None
    try:
        text = base64.b64decode(compact, validate=True).decode("utf-8")
    except (binascii.Error, ValueError):
        return None
    if not text or any(not c.isprintable() and c not in "\r\n\t" for c in text):
        return None
    return text


def _has_identity(item, depth=0):
    if not isinstance(item, dict) or depth > 3:
        return False
    for key, value in item.items():
        role = classify(key)
        # A bare "name" is not enough: tests, drugs and wards have names too.
        if role in _IDENTITY_ROLES and (role != "name" or set(tokens(key)) - {"name"}):
            return True
        if _has_identity(value, depth + 1):
            return True
    return False


def split(document):
    """Return a list of (locator, record_object)."""
    data = document.data
    if document.kind == "table":
        return [(f"row:{i}", row) for i, row in enumerate(data[1:])]
    if document.kind == "text":
        return [("doc", data)]
    if isinstance(data, list):
        return [(f"/{i}", item) for i, item in enumerate(data)]
    if data.get("resourceType"):
        return [("doc", data)]
    found = []
    for key, value in data.items():
        if (isinstance(value, list) and value and not set(tokens(key)) & NON_PERSON
                and any(_has_identity(item) for item in value)):
            escaped = str(key).replace("~", "~0").replace("/", "~1")
            found.extend((f"/{escaped}/{i}", item) for i, item in enumerate(value))
    return found or [("doc", data)]


def role_of(key, parents, container, resource):
    """Role of a JSON value, using its key, its ancestors and its siblings."""
    role = classify(key, parents)
    lowered = str(key)
    above = [str(p) for p in parents]
    if isinstance(container, dict) and lowered == "value" and "system" in container:
        system = str(container["system"])
        if system == "phone":
            return "phone"
        if system == "email":
            return "email"
        parts = tokens(system)
        if "healthid" in parts or "abha" in parts:
            return "abha"
        if parts and parts[-1] in {"uhid", "mrn", "ipd", "opd", "patient"}:
            return "mrn"
    if isinstance(container, dict) and lowered.startswith("value") and "url" in container:
        extension = classify(str(container["url"]).rstrip("/").split("/")[-1])
        if extension != "text":
            return extension
    if "relationship" in above:
        return "text"
    if resource:
        if resource in NON_PATIENT_RESOURCES:
            return "text" if role in {"name", "relative", "address", "village", "pin"} else role
        if lowered in {"text", "family", "given", "prefix", "suffix"} and "name" in above:
            return "relative" if "contact" in above or resource == "RelatedPerson" else "name"
        if lowered == "name" and resource not in {"Patient", "RelatedPerson"}:
            return "text"
        if lowered == "display":
            if above and above[-1] in {"subject", "patient"}:
                return "name"
            return "text"
        if "address" in above:
            return {"line": "address", "text": "address", "city": "village",
                    "postalCode": "pin", "district": "district"}.get(lowered, "text")
    return role


def list_parents(locator):
    """Ancestor keys of a record taken from a list, e.g. "/visits/3" -> ("visits",)."""
    return tuple(p.replace("~1", "/").replace("~0", "~") for p in locator.split("/")[1:-1])


def walk(node, visit, key="", parents=(), container=None, resource=None, role=None):
    """Rebuild `node`, passing every scalar to visit(value, key, parents, role)."""
    if isinstance(node, dict):
        resource = node.get("resourceType", resource)
        inner = parents + ((key,) if key != "" else ())
        result = {}
        for child_key, child in node.items():
            child_role = role_of(child_key, inner, node, resource)
            # A name object passes its meaning to the parts inside it.
            if role in {"name", "relative"} and child_role == "text":
                if str(child_key) in {"first", "last", "middle", "local", "full", "text", "given", "family"}:
                    child_role = role
            result_key, result_value = visit.entry(
                child_key,
                walk(child, visit, child_key, inner, node, resource, child_role),
                child_role, resource, inner)
            if result_key is None:
                continue
            base, number = result_key, 2
            while result_key in result:
                result_key = f"{base}_{number}"
                number += 1
            result[result_key] = result_value
        return result
    if isinstance(node, list):
        return [walk(item, visit, key, parents, container, resource, role) for item in node]
    if role is None:
        role = "text"
    return visit.value(node, key, parents, role, resource)
