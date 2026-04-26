"""PDF renderer for the export pipeline.

Pipeline: MarkdownRenderer.render(parts) → HTML (via ``markdown`` library)
          → inject CSS → weasyprint.HTML(string=html).write_pdf()

Any exception raised by weasyprint is wrapped in RenderError so callers
never need to import weasyprint directly.
"""

import re
import markdown as _md

import weasyprint

from src.export.errors import RenderError
from src.export.models import DocumentParts
from src.export.renderers import markdown as markdown_renderer

# ---------------------------------------------------------------------------
# CSS applied to every exported PDF (Requirements 2.4)
# ---------------------------------------------------------------------------

_CSS = """
body {
    font-family: Georgia, "Times New Roman", serif;
    font-size: 11pt;
    line-height: 1.6;
    margin: 1.5cm;
    color: #1a1a1a;
}

h1 { font-size: 2em;   margin-top: 1.2em; margin-bottom: 0.4em; }
h2 { font-size: 1.5em; margin-top: 1em;   margin-bottom: 0.3em; }
h3 { font-size: 1.2em; margin-top: 0.8em; margin-bottom: 0.2em; }

code, pre, tt {
    font-family: "Courier New", Courier, monospace;
    font-size: 0.9em;
    background: #f5f5f5;
    padding: 0.1em 0.3em;
    border-radius: 3px;
}

pre {
    padding: 0.8em 1em;
    overflow-x: auto;
    white-space: pre-wrap;
    word-wrap: break-word;
}

@page {
    margin: 1.5cm;
}
"""


_SUPPLEMENTARY_RE = re.compile(r"[\U00010000-\U0010FFFF]")


def _sanitize_for_weasyprint(text: str) -> str:
    """Replace supplementary-plane characters (U+10000–U+10FFFF) with the
    Unicode replacement character (U+FFFD).

    fontTools' OS/2 table subsetter only handles Unicode range bits 0–122,
    but supplementary characters trigger bit 123, causing a ValueError deep
    inside weasyprint's font-subsetting pipeline.  Replacing them with U+FFFD
    (which is in the BMP) keeps the document renderable while preserving a
    visible placeholder for any non-BMP content.
    """
    return _SUPPLEMENTARY_RE.sub("\ufffd", text)


def _to_html(md_text: str) -> str:
    """Convert a Markdown string to a full HTML document with injected CSS."""
    body_html = _md.markdown(
        _sanitize_for_weasyprint(md_text),
        extensions=["fenced_code", "tables", "nl2br"],
    )
    return (
        "<!DOCTYPE html>\n"
        "<html>\n"
        "<head>\n"
        '<meta charset="utf-8">\n'
        f"<style>{_CSS}</style>\n"
        "</head>\n"
        "<body>\n"
        f"{body_html}\n"
        "</body>\n"
        "</html>"
    )


def render(parts: DocumentParts) -> bytes:
    """Render *parts* to PDF bytes.

    Pipeline (Requirements 2.3, 2.4, 2.9):
    1. Produce Markdown via MarkdownRenderer.
    2. Convert Markdown → HTML.
    3. Render HTML → PDF bytes via weasyprint.

    Raises:
        RenderError: if weasyprint raises any exception during rendering.
    """
    md_text = markdown_renderer.render(parts)
    html = _to_html(md_text)

    try:
        pdf_bytes: bytes = weasyprint.HTML(string=html).write_pdf()
    except Exception as exc:
        raise RenderError(str(exc)) from exc

    return pdf_bytes
