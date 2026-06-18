# app/errors.py
class IngestionError(Exception):
    """Base for ingestion problems."""


class UnsupportedFileTypeError(IngestionError):
    pass


class FileTooLargeError(IngestionError):
    pass


class OcrNotAvailableError(IngestionError):
    pass


class DuplicateDocumentError(IngestionError):
    def __init__(self, message: str, existing_document_id: str) -> None:
        super().__init__(message)
        self.existing_document_id = existing_document_id