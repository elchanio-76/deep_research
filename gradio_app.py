"""Gradio thin client for the Deep Research FastAPI backend.

Consumes the FastAPI REST endpoints and SSE streams via httpx.
No imports from src/core/ or src/agents/ — all communication is over HTTP.
"""

import json
import os
import tempfile

import gradio as gr
import httpx
from dotenv import load_dotenv

load_dotenv(override=True)

API_BASE = os.getenv("API_BASE_URL", "http://localhost:8000/api")

SEARCH_MODE_CHOICES = {
    "No Adaptive Search": "no_adaptive",
    "Deep Dive (+3 searches)": "deep_dive",
    "Deep Dive + Gap-Filling (2x budget)": "deep_dive_gap_fill",
}
SEARCH_MODE_DEFAULT = "no_adaptive"

# ---------------------------------------------------------------------------
# State helpers
# ---------------------------------------------------------------------------

# Track the current session_id across interactions
_current_session_id: str | None = None


def _set_session(session_id: str | None) -> None:
    global _current_session_id
    _current_session_id = session_id


def _get_session() -> str | None:
    return _current_session_id


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------


def _cost_text(cost: dict) -> str:
    """Format a cost summary dict into a markdown string."""
    if not cost:
        return ""
    return (
        f"**Tokens:** {cost.get('total_input_tokens', 0):,} in / "
        f"{cost.get('total_output_tokens', 0):,} out | "
        f"**Tool calls:** {cost.get('total_tool_calls', 0)} | "
        f"**Cost:** ${cost.get('total_cost', 0.0):.4f}"
    )


async def _list_sessions_api() -> list[tuple[str, str]]:
    """Fetch session list from API. Returns list of (label, session_id) tuples."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{API_BASE}/sessions")
            resp.raise_for_status()
            sessions = resp.json()
            choices = []
            for s in sessions:
                label = s.get("header") or s.get("initial_prompt", "")[:60]
                choices.append((label, s["id"]))
            return choices
    except Exception as e:
        print(f"[gradio_app] list_sessions error: {e}")
        return []


async def _load_session_api(session_id: str) -> dict:
    """Load full session detail from API."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(f"{API_BASE}/sessions/{session_id}")
        resp.raise_for_status()
        return resp.json()


async def _delete_session_api(session_id: str) -> bool:
    """Delete a session via API. Returns True on success."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.delete(f"{API_BASE}/sessions/{session_id}")
            return resp.status_code == 204
    except Exception as e:
        print(f"[gradio_app] delete_session error: {e}")
        return False


# ---------------------------------------------------------------------------
# Gradio event handlers
# ---------------------------------------------------------------------------


async def run(query: str, search_mode: str, cost_effective: bool):
    """Stream research results from the API via SSE."""
    if not query.strip():
        yield "", "", []
        return

    report_acc = ""
    cost_md = ""
    progress_lines: list[str] = []

    payload = {
        "query": query,
        "search_mode": search_mode,
        "cost_effective": cost_effective,
    }

    try:
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "POST",
                f"{API_BASE}/research/start",
                json=payload,
                headers={"Accept": "text/event-stream"},
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    raw = line[len("data:") :].strip()
                    if not raw:
                        continue
                    try:
                        event = json.loads(raw)
                    except json.JSONDecodeError:
                        continue

                    etype = event.get("type")

                    if etype == "progress":
                        msg = event.get("message", "")
                        progress_lines.append(msg)
                        # Show progress in the report area while running
                        yield "\n".join(progress_lines), cost_md, []

                    elif etype == "report":
                        report_acc = event.get("content", "")
                        yield report_acc, cost_md, []

                    elif etype == "cost":
                        cost_md = _cost_text(event.get("summary", {}))
                        yield report_acc, cost_md, []

                    elif etype == "complete":
                        # Refresh session list after completion
                        yield report_acc, cost_md, []
                        break

                    elif etype == "error":
                        err = event.get("message", "Unknown error")
                        yield f"**Error:** {err}", cost_md, []
                        break

    except httpx.HTTPStatusError as e:
        yield f"**API error {e.response.status_code}:** {e.response.text}", "", []
    except Exception as e:
        yield f"**Connection error:** {e}", "", []


async def chat(message: str, history: list[dict], session_id: str | None):
    """Stream a chat response from the API via SSE."""
    if not message or not session_id:
        if not session_id:
            history = list(history or [])
            history.append(
                {
                    "role": "assistant",
                    "content": "No active session. Please run a research query first.",
                }
            )
        yield history, ""
        return

    history = list(history or [])
    history.append({"role": "user", "content": message})
    yield history, ""

    # Build history payload (exclude the message we just appended)
    api_history = [{"role": m["role"], "content": m["content"]} for m in history[:-1]]

    payload = {
        "session_id": session_id,
        "message": message,
        "history": api_history,
    }

    assistant_content = ""

    try:
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "POST",
                f"{API_BASE}/chat",
                json=payload,
                headers={"Accept": "text/event-stream"},
            ) as response:
                if response.status_code == 404:
                    history.append(
                        {
                            "role": "assistant",
                            "content": "Session not found or no report available.",
                        }
                    )
                    yield history, ""
                    return
                response.raise_for_status()

                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    raw = line[len("data:") :].strip()
                    if not raw:
                        continue
                    try:
                        event = json.loads(raw)
                    except json.JSONDecodeError:
                        continue

                    etype = event.get("type")

                    if etype == "chunk":
                        chunk = event.get("content", "")
                        if history and history[-1].get("role") == "assistant":
                            assistant_content += (
                                f"\n{chunk}" if assistant_content else chunk
                            )
                            history[-1] = {
                                "role": "assistant",
                                "content": assistant_content,
                            }
                        else:
                            assistant_content = chunk
                            history.append(
                                {"role": "assistant", "content": assistant_content}
                            )
                        yield history, ""

                    elif etype == "complete":
                        break

                    elif etype == "error":
                        err = event.get("message", "Unknown error")
                        history.append(
                            {"role": "assistant", "content": f"**Error:** {err}"}
                        )
                        yield history, ""
                        break

    except Exception as e:
        history.append({"role": "assistant", "content": f"**Connection error:** {e}"})
        yield history, ""


async def export_report(session_id: str | None, fmt: str):
    """Export the current session report as Markdown or PDF."""
    if not session_id:
        return gr.update(value=None, visible=False)

    ext = "pdf" if fmt == "pdf" else "md"
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.get(
                f"{API_BASE}/export/{session_id}/{fmt}",
                params={"delivery_mode": "download"},
            )
            if resp.status_code in (404, 422):
                gr.Warning(
                    f"Export unavailable: {resp.json().get('detail', resp.text)}"
                )
                return gr.update(value=None, visible=False)
            resp.raise_for_status()

        # Write bytes to a named temp file so Gradio can serve it
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=f".{ext}", prefix=f"report-{session_id}-"
        ) as tmp:
            tmp.write(resp.content)
            tmp_path = tmp.name
        return gr.update(value=tmp_path, visible=True)

    except Exception as e:
        print(f"[gradio_app] export_report error: {e}")
        return gr.update(value=None, visible=False)


async def refresh_sessions():
    choices = await _list_sessions_api()
    return gr.update(choices=choices)


async def load_session(session_id: str):
    """Load a session and populate all UI components."""
    if not session_id:
        return "", "", [], "", SEARCH_MODE_DEFAULT, False, None

    try:
        data = await _load_session_api(session_id)
    except Exception as e:
        return (
            f"**Error loading session:** {e}",
            "",
            [],
            "",
            SEARCH_MODE_DEFAULT,
            False,
            None,
        )

    report_md = data.get("report_markdown") or ""
    cost_md = _cost_text(data.get("cost_summary", {}))
    chat_history = [
        {"role": m["role"], "content": m["content"]}
        for m in data.get("chat_history", [])
    ]
    initial_prompt = data.get("initial_prompt", "")
    session_search_mode = data.get("search_mode", SEARCH_MODE_DEFAULT)
    cost_effective = data.get("cost_effective", False)

    return (
        report_md,
        cost_md,
        chat_history,
        initial_prompt,
        session_search_mode,
        cost_effective,
        session_id,
    )


def new_session():
    """Reset all UI state for a new research session."""
    return (
        "",
        "",
        [],
        "",
        SEARCH_MODE_DEFAULT,
        False,
        None,
        gr.update(value=None),
        gr.update(value=None, visible=False),
    )


# ---------------------------------------------------------------------------
# Gradio UI
# ---------------------------------------------------------------------------

with gr.Blocks(theme=gr.themes.Default(primary_hue="sky")) as ui:
    gr.Markdown("# Deep Research")
    session_state = gr.State(None)

    with gr.Row():
        with gr.Column(scale=1):
            with gr.Accordion("Sessions", open=True):
                session_radio = gr.Radio(label="Previous Sessions", choices=[])
                refresh_sessions_button = gr.Button("Refresh Sessions")
                new_session_button = gr.Button("New Session")

        with gr.Column(scale=3):
            query_textbox = gr.Textbox(label="What topic would you like to research?")
            search_mode = gr.Dropdown(
                label="Search Mode",
                choices=[
                    (label, value) for label, value in SEARCH_MODE_CHOICES.items()
                ],
                value=SEARCH_MODE_DEFAULT,
            )
            cost_effective_toggle = gr.Checkbox(
                label="Cost-Effective Search (uses Brave)",
                value=False,
            )
            run_button = gr.Button("Run", variant="primary")
            report = gr.Markdown(label="Report")
            cost_summary = gr.Markdown(label="Session Cost Summary")

            with gr.Row():
                export_format_dropdown = gr.Dropdown(
                    label="Export Format",
                    choices=[("Markdown", "markdown"), ("PDF", "pdf")],
                    value="markdown",
                    scale=1,
                )
                export_button = gr.Button("Export Report", variant="secondary", scale=1)
                export_file_output = gr.File(label="Download", visible=False, scale=2)

            gr.Markdown("## Q&A")
            chatbot = gr.Chatbot(label="Q&A", type="messages")
            chat_input = gr.Textbox(label="Ask a question")
            chat_button = gr.Button("Send")

    # --- Wire up events ---

    run_button.click(
        fn=run,
        inputs=[query_textbox, search_mode, cost_effective_toggle],
        outputs=[report, cost_summary, chatbot],
    )
    query_textbox.submit(
        fn=run,
        inputs=[query_textbox, search_mode, cost_effective_toggle],
        outputs=[report, cost_summary, chatbot],
    )

    chat_button.click(
        fn=chat,
        inputs=[chat_input, chatbot, session_state],
        outputs=[chatbot, chat_input],
    )
    chat_input.submit(
        fn=chat,
        inputs=[chat_input, chatbot, session_state],
        outputs=[chatbot, chat_input],
    )

    refresh_sessions_button.click(
        fn=refresh_sessions,
        inputs=None,
        outputs=session_radio,
    )
    ui.load(fn=refresh_sessions, inputs=None, outputs=session_radio)

    session_radio.change(
        fn=load_session,
        inputs=session_radio,
        outputs=[
            report,
            cost_summary,
            chatbot,
            query_textbox,
            search_mode,
            cost_effective_toggle,
            session_state,
        ],
    )
    new_session_button.click(
        fn=new_session,
        inputs=None,
        outputs=[
            report,
            cost_summary,
            chatbot,
            query_textbox,
            search_mode,
            cost_effective_toggle,
            session_state,
            session_radio,
            export_file_output,
        ],
    )

    export_button.click(
        fn=export_report,
        inputs=[session_state, export_format_dropdown],
        outputs=[export_file_output],
    )


if __name__ == "__main__":
    ui.launch(inbrowser=True)
