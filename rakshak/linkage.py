from .normalization import normalize_key, normalize_text


STRONG_ID_FIELDS = {
    "patientid",
    "patientref",
    "patientreference",
    "uhid",
    "mrn",
    "medicalrecordnumber",
    "medicalrecordno",
    "hospitalnumber",
    "abhaid",
    "healthid",
    "registrationid",
    "registrationnumber",
    "registrationno",
    "regno",
    "रोगीआईडी",
    "आधारसंख्या",
    "आभाआईडी",
    "पंजीकरणसंख्या",
}


def canonical_patient_key(record: dict):
    """
    Link only when a strong patient identifier is explicitly present.
    Never link on name, address, age, diagnosis, or phone alone.
    """
    candidates = []

    for key, value in record.items():
        normalized_key = normalize_key(str(key))

        if normalized_key in STRONG_ID_FIELDS:
            if value is None:
                continue

            value = normalize_text(str(value))
            if len(value) >= 3:
                candidates.append((normalized_key, value.casefold()))

    # Conflicting strong IDs mean abstain rather than risk a false merge.
    unique = set(candidates)

    if len(unique) == 1:
        namespace, identifier = next(iter(unique))
        return f"{namespace}:{identifier}"

    return None