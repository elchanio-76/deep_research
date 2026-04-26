"""Export error types for the export pipeline."""


class ExportError(Exception):
    """Base class for all export-related errors."""


class SessionNotFoundError(ExportError):
    """Raised when the requested session does not exist in the database."""


class ReportNotReadyError(ExportError):
    """Raised when the session exists but report_markdown is NULL."""


class RenderError(ExportError):
    """Raised when a renderer (e.g. weasyprint) fails to produce output."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason
