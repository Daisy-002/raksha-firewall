from .detection import sanitize_value
from .linkage import canonical_patient_key
from .generalization import generalize_value


def sanitize_structured_value(value, field, stats):
    if isinstance(value, dict):
        return {
            key: sanitize_structured_value(item, key, stats)
            for key, item in value.items()
        }

    if isinstance(value, list):
        return [
            sanitize_structured_value(item, field, stats)
            for item in value
        ]

    if isinstance(value, str):
        value = sanitize_value(field, value, stats)

    return generalize_value(field, value)


def inspect_record_identity(record):
    return canonical_patient_key(record)