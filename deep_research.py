import gradio as gr
from dotenv import load_dotenv
from research_manager import ResearchManager

load_dotenv(override=True)

# Create a shared instance to persist the report
research_manager = ResearchManager()


async def run(query: str):
    async for chunk in research_manager.run(query):
        yield chunk, research_manager.get_cost_summary(), []


async def chat(message: str, history: list[tuple[str, str]]):
    if not message:
        yield history, ""
        return
    prior_history = history or []
    updated_history = list(prior_history)
    updated_history.append((message, ""))
    yield updated_history, ""
    async for chunk in research_manager.chat(message, prior_history):
        last_user, last_assistant = updated_history[-1]
        if last_assistant:
            updated_history[-1] = (last_user, f"{last_assistant}\n{chunk}")
        else:
            updated_history[-1] = (last_user, chunk)
        yield updated_history, ""


def refresh_cost() -> str:
    return research_manager.get_cost_summary()


async def refresh_sessions():
    choices = await research_manager.list_sessions()
    return gr.update(choices=choices)


async def load_session(session_id: str):
    if not session_id:
        return "", "", [], "", None
    (
        report_markdown,
        cost_text,
        history,
        initial_prompt,
    ) = await research_manager.load_session(session_id)
    return report_markdown, cost_text, history, initial_prompt, session_id


def new_session():
    research_manager.reset_session_state()
    return "", "", [], "", None, gr.update(value=None)


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
            run_button = gr.Button("Run", variant="primary")
            report = gr.Markdown(label="Report")
            cost_summary = gr.Markdown(label="Session Cost Summary")
            refresh_cost_button = gr.Button("Refresh Cost")

            gr.Markdown("## Q&A")
            chatbot = gr.Chatbot(label="Q&A")
            chat_input = gr.Textbox(label="Ask a question")
            chat_button = gr.Button("Send")

    run_button.click(
        fn=run, inputs=query_textbox, outputs=[report, cost_summary, chatbot]
    )
    query_textbox.submit(
        fn=run, inputs=query_textbox, outputs=[report, cost_summary, chatbot]
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
        outputs=[report, cost_summary, chatbot, query_textbox, session_state],
    )
    new_session_button.click(
        fn=new_session,
        inputs=None,
        outputs=[
            report,
            cost_summary,
            chatbot,
            query_textbox,
            session_state,
            session_radio,
        ],
    )

ui.launch(inbrowser=True)
