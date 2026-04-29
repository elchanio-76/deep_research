"""Internal DTOs and API response models for the export pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel


class ExportFormat(str, Enum):
    markdown = "markdown"
    pdf = "pdf"
    docx = "docx"


class DeliveryMode(str, Enum):
    download = "download"
    url = "url"


@dataclass
class QAPair:
    question: str  # content of a user-role message
    answer: str  # content of the following assistant-role message


@dataclass
class MetadataHeader:
    title: str  # session.header or initial_prompt[:120] + "…"
    session_id: str  # UUID as string
    exported_at: str  # UTC ISO-8601 timestamp
    format: str  # "markdown" or "pdf"

    @staticmethod
    def derive_title(header: str | None, initial_prompt: str) -> str:
        """Return the document title per Requirement 3.2/3.3."""
        if header:
            return header
        if len(initial_prompt) > 120:
            return initial_prompt[:120] + "\u2026"
        return initial_prompt

    @staticmethod
    def now_utc() -> str:
        """Return the current UTC time as an ISO-8601 string."""
        return datetime.now(timezone.utc).isoformat()


@dataclass
class DocumentParts:
    metadata: MetadataHeader
    report_body: str  # verbatim report_markdown
    qa_pairs: list[QAPair] = field(default_factory=list)


@dataclass
class ExportResult:
    content: bytes  # UTF-8 bytes for MD, binary for PDF
    filename: str  # "report-{session_id}.md" or ".pdf"
    media_type: str  # "application/octet-stream" or "application/pdf"
    fmt: ExportFormat

    @staticmethod
    def filename_for(session_id: str, fmt: ExportFormat) -> str:
        """Derive the output filename per Requirement 4.4."""
        ext_map = {
            ExportFormat.markdown: "md",
            ExportFormat.pdf: "pdf",
            ExportFormat.docx: "docx",
        }
        return f"report-{session_id}.{ext_map[fmt]}"


class ExportUrlResponse(BaseModel):
    """JSON response body returned when delivery_mode=url."""

    file_path: str  # absolute path on the server
    url: str  # relative URL, e.g. "/exports/report-<id>.pdf"
