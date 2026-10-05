import gradio as gr
import logging
from research_manager import ResearchManager
from provider_errors import ProviderError, public_error_message
from timeline import route_chunk



async def run(query: str):
    """Run the research process and stream progress/results back to the UI.

    Yields (timeline_html, report_md) tuples. Progress is routed to the
    timeline component by *type*: only TimelineUpdate events — which only
    application code can produce — ever reach the raw-HTML component.
    Report text is plain str and always lands in the report Markdown, even
    if it happens to contain marker-like text.
    """
    timeline_html = ""
    report_md = ""
    try:
        async for chunk in ResearchManager().run(query):  # Stream status updates and final report
            timeline_html, report_md, emit = route_chunk(chunk, timeline_html, report_md)
            if not emit:
                logging.error(
                    "Deep Research yielded unexpected chunk type: %s",
                    type(chunk).__name__,
                )
                continue
            yield timeline_html, report_md
    except ProviderError as error:
        logging.error("Deep Research request failed: %s", error.category)
        yield timeline_html, public_error_message(error)
    except Exception:
        logging.error("Deep Research request failed: unexpected internal error")
        yield timeline_html, "⚠️ **Deep Research could not complete this request. Please try again later.**"


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
    timeline = gr.HTML(value="", label="Research progress")  # Live timeline (ux-01)
    report = gr.Markdown(label="Report")  # Output area for the final report

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
        .then(fn=run, inputs=query_textbox, outputs=[timeline, report], show_progress="hidden")
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
        .then(fn=run, inputs=query_textbox, outputs=[timeline, report], show_progress="hidden")
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
