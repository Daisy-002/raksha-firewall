from .detection import sanitize_value


def sanitize_clinical_note(text, stats):
    """
    Clean explicit personal identifiers while retaining clinical language,
    diagnoses, medication names, dosages, and treatment instructions.
    """
    return sanitize_value("clinical_note", text, stats)