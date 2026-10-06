import gradio as gr
import html as _html
import logging
import time

import history as history_store
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

    The completed run is persisted to the session-history store (ux-10) so it
    appears in the "Past research" dropdown.
    """
    timeline_html = ""
    report_md = ""
    try:
        async for chunk in ResearchManager(
            history_path=history_store.default_history_path()
        ).run(query):  # Stream status updates and final report
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


def _history_choices(runs):
    """Dropdown (label, value) pairs for stored runs, newest first."""
    return [(history_store.entry_label(entry), entry["id"]) for entry in runs]


def refresh_history():
    """Reload the history store; returns (dropdown update, state)."""
    runs = history_store.load_history()
    return gr.Dropdown(choices=_history_choices(runs), value=None), runs


def load_history_run(entry_id, runs):
    """Reload a past run into the main view: query, timeline banner, report.

    History content is plain text (query/report from a previous run), never
    routed into a raw-HTML component — the timeline gets a static banner only.
    """
    entry = next((e for e in (runs or []) if e["id"] == entry_id), None)
    if entry is None:
        return gr.skip(), gr.skip(), gr.skip()
    when = time.strftime(
        "%b %d, %Y · %H:%M", time.localtime(entry.get("timestamp", 0))
    )
    n_sources = len(entry.get("sources", []))
    banner = (
        '<div style="background:#131b2c;border:1px solid #232f4b;border-radius:12px;'
        'padding:12px 16px;display:flex;align-items:center;gap:12px;font-size:14px">'
        '<span style="font-size:20px">📚</span>'
        f"<span><b>Viewing saved run</b>"
        f'<span style="color:#8b98b8"> · {_html.escape(when)}'
        f" · {n_sources} source{'s' if n_sources != 1 else ''}</span>"
        "</span></div>"
    )
    return entry.get("query", ""), banner, entry.get("report", "")


def remove_history_run(entry_id):
    """Delete the selected run from the store, then refresh the dropdown."""
    if entry_id:
        history_store.delete_run(entry_id)
    return refresh_history()


def _start_research():
    """Button/status updates shared by click and Enter-key submit."""
    return (
        gr.Button("Processing...", variant="primary", interactive=False),
        gr.Markdown("🔄 **Researching...**", visible=True),
    )


def _finish_research():
    return (
        gr.Button("Run", variant="primary", interactive=True),
        gr.Markdown("", visible=False),
    )


# Build Gradio UI
with gr.Blocks(theme=gr.themes.Default(primary_hue="sky")) as ui:
    with gr.Row():
        with gr.Column(scale=1, min_width=280):
            gr.Markdown("## 🕘 Past research")
            gr.Markdown(
                "Select a previous run to reload its report. "
                "History is stored locally as JSON in your home directory."
            )
            history_runs = history_store.load_history()
            history_dropdown = gr.Dropdown(
                label="Past runs",
                choices=_history_choices(history_runs),
                interactive=True,
            )
            delete_button = gr.Button("Delete selected run", size="sm")
            history_state = gr.State(history_runs)
        with gr.Column(scale=3):
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

    # Reload a past run when picked from the history dropdown
    history_dropdown.change(
        fn=load_history_run,
        inputs=[history_dropdown, history_state],
        outputs=[query_textbox, timeline, report],
    )
    delete_button.click(
        fn=remove_history_run,
        inputs=[history_dropdown],
        outputs=[history_dropdown, history_state],
    )

    # Trigger research when button is clicked with button state management
    run_event = (
        run_button.click(
            fn=_start_research,
            outputs=[run_button, status_text],
            queue=False,
        )
        .then(fn=run, inputs=query_textbox, outputs=[timeline, report], show_progress="hidden")
        .then(fn=_finish_research, outputs=[run_button, status_text])
        .then(fn=refresh_history, outputs=[history_dropdown, history_state])
    )

    # Also allow submitting with Enter key with button state management
    submit_event = (
        query_textbox.submit(
            fn=_start_research,
            outputs=[run_button, status_text],
            queue=False,
        )
        .then(fn=run, inputs=query_textbox, outputs=[timeline, report], show_progress="hidden")
        .then(fn=_finish_research, outputs=[run_button, status_text])
        .then(fn=refresh_history, outputs=[history_dropdown, history_state])
    )

ui.queue()  # Enable queuing for proper event handling
ui.launch(inbrowser=True)  # Launch UI and open it in the browser
