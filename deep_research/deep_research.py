import gradio as gr
import logging
from research_manager import ResearchManager
from provider_errors import ProviderError



async def run(query: str):
    """Run the research process and stream progress/results back to the UI"""
    try:
        async for chunk in ResearchManager().run(query):  # Stream status updates and final report
            yield chunk
    except ProviderError as error:
        logging.exception("Deep Research request failed")
        yield f"⚠️ **Deep Research could not complete this request ({error.category}).**"
    except Exception:
        logging.exception("Deep Research request failed")
        yield "⚠️ **Deep Research could not complete this request. Please try again later.**"


# Build Gradio UI
with gr.Blocks(theme=gr.themes.Default(primary_hue="sky")) as ui:
    gr.Markdown("# Deep Research")  # App title
    gr.Markdown(
        "🔎 A team of **agents** will scour the web together for information and print your report below."
    )  # Informational line for user
    query_textbox = gr.Textbox(
        label="Please enter a topic for the agent team to research."
    )  # Input field for query
    gr.Markdown("This search may take up to a minute to complete. Thank you for your patience.")
    run_button = gr.Button("Run", variant="primary")  # Button to start research
    status_text = gr.Markdown("", visible=False)  # Status indicator with spinner
    report = gr.Markdown(label="Report")  # Output area for progress and final report

    # Trigger research when button is clicked with button state management
    run_event = (
        run_button.click(
            fn=lambda: (
                gr.Button("Processing...", variant="primary", interactive=False),
                gr.Markdown("🔄 **Researching...**", visible=True),
            ),
            outputs=[run_button, status_text],
            queue=False,
        )
        .then(fn=run, inputs=query_textbox, outputs=report, show_progress="full")
        .then(
            fn=lambda: (
                gr.Button("Run", variant="primary", interactive=True),
                gr.Markdown("", visible=False),
            ),
            outputs=[run_button, status_text],
        )
    )

    # Also allow submitting with Enter key with button state management
    submit_event = (
        query_textbox.submit(
            fn=lambda: (
                gr.Button("Processing...", variant="primary", interactive=False),
                gr.Markdown("🔄 **Researching...**", visible=True),
            ),
            outputs=[run_button, status_text],
            queue=False,
        )
        .then(fn=run, inputs=query_textbox, outputs=report, show_progress="full")
        .then(
            fn=lambda: (
                gr.Button("Run", variant="primary", interactive=True),
                gr.Markdown("", visible=False),
            ),
            outputs=[run_button, status_text],
        )
    )

ui.queue()  # Enable queuing for proper event handling
ui.launch(inbrowser=True)  # Launch UI and open it in the browser
