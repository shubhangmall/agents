import asyncio
import gradio as gr
import logging
from research_manager import ResearchManager
from provider_errors import ProviderError, public_error_message
from timeline import SearchProgress, apply_stop_banner, route_chunk



async def run(query: str, progress=gr.Progress()):
    """Run the research process and stream progress/results back to the UI.

    Yields (timeline_html, report_md) tuples. Progress is routed to the
    timeline component by *type*: only TimelineUpdate events — which only
    application code can produce — ever reach the raw-HTML component.
    SearchProgress events drive the native gr.Progress bar ("Searching 2/5…")
    and are never yielded to a component. Report text is plain str and always
    lands in the report Markdown, even if it happens to contain marker-like
    text.
    """
    timeline_html = ""
    report_md = ""
    agen = ResearchManager().run(query)
    try:
        async for chunk in agen:  # Stream status updates and final report
            if isinstance(chunk, SearchProgress):
                # ux-08: native progress bar with per-search counts.
                total = chunk.total if chunk.total else 1
                progress(
                    chunk.completed / total,
                    desc=f"Searching {chunk.completed}/{chunk.total}…",
                )
                continue
            timeline_html, report_md, emit = route_chunk(chunk, timeline_html, report_md)
            if not emit:
                logging.error(
                    "Deep Research yielded unexpected chunk type: %s",
                    type(chunk).__name__,
                )
                continue
            yield timeline_html, report_md
    except asyncio.CancelledError:
        # ux-08 Stop button: Gradio cancelled this event. Close the pipeline
        # generator so in-flight searches don't keep running orphaned, then
        # re-raise so the event stays cancelled.
        await agen.aclose()
        raise
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
    stop_button = gr.Button("⏹ Stop", variant="stop", visible=False)  # ux-08: cancel a running research
    research_running = gr.State(False)  # ux-08: True while a pipeline is in flight
    status_text = gr.Markdown("", visible=False)  # Status indicator with spinner
    timeline = gr.HTML(value="", label="Research progress")  # Live timeline (ux-01)
    report = gr.Markdown(label="Report")  # Output area for the final report

    def _research_started():
        return (
            gr.Button("Processing...", variant="primary", interactive=False),
            gr.Markdown("🔄 **Researching...**", visible=True),
            gr.update(visible=True),  # reveal the Stop button
            True,
        )

    def _research_ended():
        return (
            gr.Button("Run", variant="primary", interactive=True),
            gr.Markdown("", visible=False),
            gr.update(visible=False),  # hide the Stop button
            False,
        )

    # Trigger research when button is clicked with button state management
    start_run = run_button.click(
        fn=_research_started,
        outputs=[run_button, status_text, stop_button, research_running],
        queue=False,
    )
    run_event = start_run.then(fn=run, inputs=query_textbox, outputs=[timeline, report])
    run_event.then(
        fn=_research_ended,
        outputs=[run_button, status_text, stop_button, research_running],
    )

    # Also allow submitting with Enter key with button state management
    start_submit = query_textbox.submit(
        fn=_research_started,
        outputs=[run_button, status_text, stop_button, research_running],
        queue=False,
    )
    submit_event = start_submit.then(fn=run, inputs=query_textbox, outputs=[timeline, report])
    submit_event.then(
        fn=_research_ended,
        outputs=[run_button, status_text, stop_button, research_running],
    )

    def _research_stopped(timeline_html, running):
        if not running:
            # Stop clicked after the run already finished (or twice): the
            # trailing _research_ended already reset the controls — leave
            # everything untouched so a completed report is never stamped
            # as stopped.
            return gr.update(), gr.update(), gr.update(), timeline_html, running
        # The run event is cancelled below, so its trailing state-reset never
        # fires — restore the controls here and mark the timeline stopped.
        run_btn, status, _, _ = _research_ended()
        return (
            run_btn,
            status,
            gr.update(visible=False),
            apply_stop_banner(timeline_html, running),
            False,
        )

    # ux-08: Stop cancels the in-flight research event; the generator's
    # CancelledError handler closes the pipeline so no searches are orphaned.
    stop_button.click(
        fn=_research_stopped,
        inputs=[timeline, research_running],
        outputs=[run_button, status_text, stop_button, timeline, research_running],
        queue=False,
        cancels=[run_event, submit_event],
    )

ui.queue()  # Enable queuing for proper event handling
ui.launch(inbrowser=True)  # Launch UI and open it in the browser
