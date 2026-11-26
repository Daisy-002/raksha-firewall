def quarantine_reason(exception):
    """
    Return a safe reason code.
    Never include exception messages because they may contain source data.
    """
    if isinstance(exception, UnicodeError):
        return "undecodable_text"

    if isinstance(exception, RecursionError):
        return "excessive_nesting"

    if isinstance(exception, ValueError):
        message = str(exception)
        if message.isidentifier():
            return message

    return "processing_error"