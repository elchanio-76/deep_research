"""Pure Markdown renderer for the export pipeline.

Produces a deterministic Markdown string from a DocumentParts instance.
No LLM is involved — this is a pure document assembly function.
"""

from src.export.models import DocumentParts


def render(parts: DocumentParts) -> str:
    """Render *parts* into a Markdown string.

    Output order (Requirements 1.3, 1.4, 3.1):
    1. Fenced YAML-style metadata block
    2. Report body (verbatim, no escaping — Requirements 7.2, 7.4)
    3. ``## Q&A History`` section (omitted when qa_pairs is empty — Req 1.6)

    The function is pure: identical inputs always produce identical output
    (Requirement 7.1).
    """
    sections: list[str] = []

    # --- 1. Metadata block (Requirements 1.4, 3.1, 3.2) ---
    meta = parts.metadata
    metadata_block = (
        "---\n"
        f"title: {meta.title}\n"
        f"session_id: {meta.session_id}\n"
        f"exported_at: {meta.exported_at}\n"
        f"format: {meta.format}\n"
        "---"
    )
    sections.append(metadata_block)

    # --- 2. Report body — verbatim (Requirements 7.2, 7.4) ---
    sections.append(parts.report_body)

    # --- 3. Q&A appendix (Requirements 1.5, 1.6) ---
    if parts.qa_pairs:
        qa_lines: list[str] = ["## Q&A History"]
        for pair in parts.qa_pairs:
            qa_lines.append(f"**Q:** {pair.question}\n\n**A:** {pair.answer}")
        sections.append("\n\n".join(qa_lines))

    return "\n\n".join(sections)
