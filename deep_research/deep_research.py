import gradio as gr
import logging
from research_manager import ResearchManager
from provider_errors import ProviderError, public_error_message
from timeline import route_chunk
from document_view import build_document_view


def _document_parts(report_md):
    """Build the document-view outputs from the current report text."""
    body_md, toc_html, cites_html = build_document_view(report_md)
    return body_md, toc_html, cites_html


async def run(query: str):
    """Run the research process and stream progress/results back to the UI.

    Yields (timeline_html, report_md, doc_body_md, toc_html, cites_html)
    tuples. Progress is routed to the timeline component by *type*: only
    TimelineUpdate events — which only application code can produce — ever
    reach the raw-HTML component. Report text is plain str and always lands
    in the report Markdown, even if it happens to contain marker-like text.
    The document-view panels are derived from the report text on every
    yield so the TOC/citations stay live while the report streams.
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
            doc_body_md, toc_html, cites_html = _document_parts(report_md)
            yield timeline_html, report_md, doc_body_md, toc_html, cites_html
    except ProviderError as error:
        logging.error("Deep Research request failed: %s", error.category)
        report_md = public_error_message(error)
        doc_body_md, toc_html, cites_html = _document_parts(report_md)
        yield timeline_html, report_md, doc_body_md, toc_html, cites_html
    except Exception:
        logging.error("Deep Research request failed: unexpected internal error")
        report_md = "⚠️ **Deep Research could not complete this request. Please try again later.**"
        doc_body_md, toc_html, cites_html = _document_parts(report_md)
        yield timeline_html, report_md, doc_body_md, toc_html, cites_html


def _toggle_view(choice):
    """Show the chat blob or the structured document view."""
    document = choice == "📄 Document view"
    return gr.update(visible=document), gr.update(visible=not document)


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
    view_radio = gr.Radio(
        ["💬 Chat view", "📄 Document view"],
        value="💬 Chat view",
        label="Report view",
    )  # Toggle between chat blob and structured document (ux-11)
    report = gr.Markdown(label="Report")  # Output area for the final report (chat view)
    doc_row = gr.Row(visible=False)  # Structured document view (ux-11)
    with doc_row:
        with gr.Column(scale=1, min_width=180):
            toc = gr.HTML(value="", label="Contents")  # Headings-derived TOC
        with gr.Column(scale=3, min_width=320):
            doc_body = gr.Markdown(label="Report")  # Report body with section anchors
        with gr.Column(scale=1, min_width=180):
            cites = gr.HTML(value="", label="Citations")  # Citation list

    view_radio.change(fn=_toggle_view, inputs=view_radio, outputs=[doc_row, report])

    _run_outputs = [timeline, report, doc_body, toc, cites]

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
        .then(fn=run, inputs=query_textbox, outputs=_run_outputs, show_progress="hidden")
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
        .then(fn=run, inputs=query_textbox, outputs=_run_outputs, show_progress="hidden")
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
