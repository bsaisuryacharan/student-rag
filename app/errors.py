# app/errors.py
class IngestionError(Exception):
    """Base for ingestion problems."""


class UnsupportedFileTypeError(IngestionError):
    pass


class FileTooLargeError(IngestionError):
    pass


class OcrNotAvailableError(IngestionError):
    pass