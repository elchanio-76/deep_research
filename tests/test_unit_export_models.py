"""Unit tests for src/export/models.py pure helper methods.

Covers:
  - MetadataHeader.derive_title  (Requirements 17.1–17.5, Properties 11–12)
  - ExportResult.filename_for    (Requirements 17.6–17.9, Property 13)
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from src.export.models import ExportFormat, ExportResult, MetadataHeader

# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# Non-empty strings for derive_title header property (Property 11)
non_empty_str = st.text(min_size=1, max_size=300)

# Short strings (≤120 chars) for derive_title prompt property (Property 12)
short_str = st.text(min_size=0, max_size=120)

# UUID strings for filename_for property (Property 13)
uuid_str = st.uuids().map(str)

# All ExportFormat values
export_fmt = st.sampled_from(list(ExportFormat))


# ---------------------------------------------------------------------------
# 13.1  Example tests for MetadataHeader.derive_title
# ---------------------------------------------------------------------------


def test_derive_title_non_empty_header_returned_unchanged():
    # Requirement 17.1 — non-empty header is returned as-is
    assert MetadataHeader.derive_title("My Report", "some prompt") == "My Report"


def test_derive_title_non_empty_header_ignores_prompt():
    # Requirement 17.1 — header takes precedence regardless of prompt content
    long_prompt = "x" * 200
    assert MetadataHeader.derive_title("Title", long_prompt) == "Title"


def test_derive_title_none_header_short_prompt_returned_unchanged():
    # Requirement 17.2 — None header + prompt ≤ 120 chars → prompt unchanged
    prompt = "A short research question"
    assert MetadataHeader.derive_title(None, prompt) == prompt


def test_derive_title_none_header_exactly_120_chars_returned_unchanged():
    # Requirement 17.2 — boundary: exactly 120 chars is NOT truncated
    prompt = "a" * 120
    assert MetadataHeader.derive_title(None, prompt) == prompt


def test_derive_title_none_header_long_prompt_truncated_with_ellipsis():
    # Requirement 17.3 — None header + prompt > 120 chars → first 120 + "…"
    prompt = "b" * 200
    result = MetadataHeader.derive_title(None, prompt)
    assert result == "b" * 120 + "\u2026"


def test_derive_title_none_header_121_chars_truncated():
    # Requirement 17.3 — boundary: 121 chars triggers truncation
    prompt = "c" * 121
    result = MetadataHeader.derive_title(None, prompt)
    assert result == "c" * 120 + "\u2026"
    assert (
        len(result) == 121
    )  # 120 chars + 1 ellipsis character (U+2026 is a single code point)


# ---------------------------------------------------------------------------
# 13.2  Property 11: derive_title returns header unchanged for any non-empty header
# ---------------------------------------------------------------------------


@given(h=non_empty_str, initial_prompt=st.text())
@settings(max_examples=100)
def test_property_derive_title_non_empty_header_unchanged(h: str, initial_prompt: str):
    # Feature: unit-test-strategy, Property 11: derive_title returns header unchanged
    # for any non-empty header
    assert MetadataHeader.derive_title(h, initial_prompt) == h


# ---------------------------------------------------------------------------
# 13.3  Property 12: derive_title returns prompt unchanged for short prompts
# ---------------------------------------------------------------------------


@given(s=short_str)
@settings(max_examples=100)
def test_property_derive_title_short_prompt_unchanged(s: str):
    # Feature: unit-test-strategy, Property 12: derive_title returns prompt unchanged
    # for short prompts (length ≤ 120)
    assert MetadataHeader.derive_title(None, s) == s


# ---------------------------------------------------------------------------
# 13.4  Example tests for ExportResult.filename_for
# ---------------------------------------------------------------------------


def test_filename_for_markdown_ends_with_md():
    # Requirement 17.6
    session_id = "abc123"
    result = ExportResult.filename_for(session_id, ExportFormat.markdown)
    assert result.endswith(".md")


def test_filename_for_pdf_ends_with_pdf():
    # Requirement 17.7
    session_id = "abc123"
    result = ExportResult.filename_for(session_id, ExportFormat.pdf)
    assert result.endswith(".pdf")


def test_filename_for_docx_ends_with_docx():
    # Requirement 17.8
    session_id = "abc123"
    result = ExportResult.filename_for(session_id, ExportFormat.docx)
    assert result.endswith(".docx")


# ---------------------------------------------------------------------------
# 13.5  Property 13: filename_for always contains the session_id
# ---------------------------------------------------------------------------


@given(session_id=uuid_str, fmt=export_fmt)
@settings(max_examples=100)
def test_property_filename_for_contains_session_id(session_id: str, fmt: ExportFormat):
    # Feature: unit-test-strategy, Property 13: filename_for always contains
    # the session_id
    result = ExportResult.filename_for(session_id, fmt)
    assert session_id in result
