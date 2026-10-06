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


# ux-13: the Gradio theme ships both light and dark stylesheets, and the app
# header renders a built-in light/dark toggle that follows the OS setting by
# default. The timeline's custom HTML uses the theme's CSS variables
# (see timeline.py) so it stays readable in either mode.
THEME = gr.themes.Default(primary_hue="sky")

# ux-13: small-screen tweaks. Gradio Rows wrap their columns to full width on
# narrow viewports automatically; these rules just polish the result.
_RESPONSIVE_CSS = """
/* Align the Run button with the bottom of the labeled input on desktop. */
#dr-run-col { justify-content: flex-end; }
@media (max-width: 640px) {
  /* Stack the query row: button goes full-width under the input. */
  #dr-query-row { flex-wrap: wrap; }
  #dr-query-col, #dr-run-col { min-width: 100% !important; }
  #dr-run-btn { width: 100%; min-height: 44px; }
  .gradio-container { padding-left: 8px !important; padding-right: 8px !important; }
}
"""


def build_ui():
    """Build the Gradio Blocks UI without launching it.

    Import-safe (no server started) so tests can inspect the layout.
    Theme and page CSS are applied in main() via launch() — Gradio 6 moved
    both from the Blocks constructor to launch().
    """
    with gr.Blocks() as ui:
        gr.Markdown("# Deep Research")  # App title
        gr.Markdown(
            "🔎 A team of **agents** will scour the web together for information and print your report below."
        )  # Informational line for user
        # ux-13: input + button sit side-by-side on desktop and stack on
        # mobile (Gradio wraps Row columns at narrow widths).
        with gr.Row(elem_id="dr-query-row"):
            with gr.Column(scale=4, min_width=200, elem_id="dr-query-col"):
                query_textbox = gr.Textbox(
                    label="Please enter a topic for the agent team to research."
                )  # Input field for query
            with gr.Column(scale=1, min_width=140, elem_id="dr-run-col"):
                run_button = gr.Button(
                    "Run", variant="primary", elem_id="dr-run-btn"
                )  # Button to start research
        gr.Markdown("This search may take up to a minute to complete. Thank you for your patience.")
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
    return ui


def main():
    ui = build_ui()
    # Gradio 6 moved `theme` and `css` from the Blocks constructor to launch().
    ui.launch(theme=THEME, css=_RESPONSIVE_CSS, inbrowser=True)  # Launch UI and open it in the browser


if __name__ == "__main__":
    main()
