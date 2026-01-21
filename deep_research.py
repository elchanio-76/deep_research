import gradio as gr
from dotenv import load_dotenv
from config import SEARCH_MODE_DEFAULT
from research_manager import ResearchManager

load_dotenv(override=True)

# Create a shared instance to persist the report
research_manager = ResearchManager()


async def run(query: str, search_mode: str):
    async for chunk in research_manager.run(query, search_mode):
        yield chunk, research_manager.get_cost_summary(), []


def _messages_to_pairs(messages: list[dict[str, str]]) -> list[tuple[str, str]]:
    history: list[tuple[str, str]] = []
    pending_user: str | None = None
    for message in messages:
        role = message.get("role")
        content = message.get("content", "")
        if role == "user":
            if pending_user is not None:
                history.append((pending_user, ""))
            pending_user = content
        else:
            if pending_user is None:
                history.append(("", content))
            else:
                history.append((pending_user, content))
                pending_user = None
    if pending_user is not None:
        history.append((pending_user, ""))
    return history


async def chat(message: str, history: list[dict[str, str]]):
    if not message:
        yield history, ""
        return
    prior_messages = history or []
    updated_messages = list(prior_messages)
    updated_messages.append({"role": "user", "content": message})
    yield updated_messages, ""
    prior_history = _messages_to_pairs(prior_messages)
    async for chunk in research_manager.chat(message, prior_history):
        if updated_messages and updated_messages[-1].get("role") == "assistant":
            last_content = updated_messages[-1].get("content", "")
            updated_messages[-1] = {
                "role": "assistant",
                "content": f"{last_content}\n{chunk}" if last_content else chunk,
            }
        else:
            updated_messages.append({"role": "assistant", "content": chunk})
        yield updated_messages, ""


def refresh_cost() -> str:
    return research_manager.get_cost_summary()


async def refresh_sessions():
    choices = await research_manager.list_sessions()
    return gr.update(choices=choices)


async def load_session(session_id: str):
    if not session_id:
        return "", "", [], "", SEARCH_MODE_DEFAULT, None
    (
        report_markdown,
        cost_text,
        history,
        initial_prompt,
        search_mode,
    ) = await research_manager.load_session(session_id)
    return report_markdown, cost_text, history, initial_prompt, search_mode, session_id


def new_session():
    research_manager.reset_session_state()
    return "", "", [], "", SEARCH_MODE_DEFAULT, None, gr.update(value=None)


with gr.Blocks(theme=gr.themes.Default(primary_hue="sky")) as ui:
    gr.Markdown("# Deep Research")
    session_state = gr.State(None)
    search_mode_choices = {
        "No Adaptive Search": "no_adaptive",
        "Deep Dive (+3 searches)": "deep_dive",
        "Deep Dive + Gap-Filling (2x budget)": "deep_dive_gap_fill",
    }

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
                    (label, value) for label, value in search_mode_choices.items()
                ],
                value=SEARCH_MODE_DEFAULT,
            )
            run_button = gr.Button("Run", variant="primary")
            report = gr.Markdown(label="Report")
            cost_summary = gr.Markdown(label="Session Cost Summary")
            refresh_cost_button = gr.Button("Refresh Cost")

            gr.Markdown("## Q&A")
            chatbot = gr.Chatbot(label="Q&A", type="messages")
            chat_input = gr.Textbox(label="Ask a question")
            chat_button = gr.Button("Send")

    run_button.click(
        fn=run,
        inputs=[query_textbox, search_mode],
        outputs=[report, cost_summary, chatbot],
    )
    query_textbox.submit(
        fn=run,
        inputs=[query_textbox, search_mode],
        outputs=[report, cost_summary, chatbot],
    )
    refresh_cost_button.click(fn=refresh_cost, inputs=None, outputs=cost_summary)

    chat_button.click(
        fn=chat, inputs=[chat_input, chatbot], outputs=[chatbot, chat_input]
    )
    chat_input.submit(
        fn=chat, inputs=[chat_input, chatbot], outputs=[chatbot, chat_input]
    )

    refresh_sessions_button.click(
        fn=refresh_sessions, inputs=None, outputs=session_radio
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
            session_state,
            session_radio,
        ],
    )

if __name__ == "__main__":
    ui.launch(inbrowser=True)
