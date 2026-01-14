import gradio as gr
from dotenv import load_dotenv
from research_manager import ResearchManager

load_dotenv(override=True)

# Create a shared instance to persist the report
research_manager = ResearchManager()


async def run(query: str):
    async for chunk in research_manager.run(query):
        yield chunk, research_manager.get_cost_summary()


async def chat(message: str, history: list[tuple[str, str]]):
    async for chunk in research_manager.chat(message, history):
        yield chunk


def refresh_cost() -> str:
    return research_manager.get_cost_summary()


with gr.Blocks(theme=gr.themes.Default(primary_hue="sky")) as ui:
    gr.Markdown("# Deep Research")
    query_textbox = gr.Textbox(label="What topic would you like to research?")
    run_button = gr.Button("Run", variant="primary")
    report = gr.Markdown(label="Report")
    cost_summary = gr.Markdown(label="Session Cost Summary")
    refresh_cost_button = gr.Button("Refresh Cost")

    run_button.click(fn=run, inputs=query_textbox, outputs=[report, cost_summary])
    query_textbox.submit(fn=run, inputs=query_textbox, outputs=[report, cost_summary])
    refresh_cost_button.click(fn=refresh_cost, inputs=None, outputs=cost_summary)

    # Add Q&A Chat section
    gr.Markdown("## Q&A")
    chatbot = gr.ChatInterface(fn=chat)

ui.launch(inbrowser=True)
