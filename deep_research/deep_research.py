import gradio as gr
import html
import logging
from clarify import MAX_QUESTIONS, format_clarifications, generate_questions
from research_manager import ResearchManager
from provider_errors import ProviderError, public_error_message
from timeline import route_chunk


async def run(query: str, clarifications: str | None = None):
    """Run the research process and stream progress/results back to the UI.

    Yields (timeline_html, report_md) tuples. Progress is routed to the
    timeline component by *type*: only TimelineUpdate events — which only
    application code can produce — ever reach the raw-HTML component.
    Report text is plain str and always lands in the report Markdown, even
    if it happens to contain marker-like text.

    clarifications is the optional ux-09 block of answered clarifying
    questions; ResearchManager feeds it into the planner prompt.
    """
    timeline_html = ""
    report_md = ""
    try:
        async for chunk in ResearchManager().run(query, clarifications=clarifications):  # Stream status updates and final report
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


async def run_with_answers(query: str, questions, *answers):
    """Collect quick-reply / free-text answers, then run with clarifications.

    inputs are (query, clarify_state, radio0, free0, radio1, free1, ...).
    Free text wins over a quick reply; unanswered questions are dropped.
    """
    pairs = []
    for index, item in enumerate(questions or []):
        radio = answers[2 * index] if 2 * index < len(answers) else None
        free = answers[2 * index + 1] if 2 * index + 1 < len(answers) else None
        answer = (free or "").strip() or str(radio or "").strip()
        if answer:
            pairs.append((item.get("question", ""), answer))
    clarifications = format_clarifications(pairs)
    async for timeline_html, report_md in run(query, clarifications=clarifications):
        yield timeline_html, report_md


_CLARIFY_NOTE = (
    "### A couple of quick questions *(optional)*\n"
    "Answer any of them — or skip — to help the research team focus. "
    "Your answers are fed to the planner."
)


def _hidden_question_rows():
    """gr.update tuples that hide and reset every clarifying-question row."""
    rows = []
    for _ in range(MAX_QUESTIONS):
        rows.append(gr.update(visible=False, value=""))
        rows.append(gr.update(visible=False, value=None, choices=[]))
        rows.append(gr.update(visible=False, value=""))
    return rows


async def clarify(query: str):
    """Pre-run screen (ux-09): generate optional clarifying questions.

    Returns one gr.update per entry in clarify_outputs. Never blocks the
    run: a blank query restores the idle button, and any LLM failure still
    opens the panel with working Skip / Continue buttons.
    """
    if not (query or "").strip():
        return (
            gr.Button("Run", variant="primary", interactive=True),
            gr.Markdown("⚠️ **Please enter a topic first.**", visible=True),
            [],
            gr.update(visible=False),
            gr.update(value=_CLARIFY_NOTE),
            *_hidden_question_rows(),
        )
    try:
        questions = await generate_questions(query)
    except Exception:
        # Skippable by design: a provider hiccup must never block research.
        logging.error("Clarifying questions failed; offering skip instead")
        questions = None

    if questions is None:
        note = (
            "⚠️ **Couldn't load clarifying questions** — you can start "
            "research right away."
        )
        state, rows = [], _hidden_question_rows()
    elif not questions:
        note = (
            "Your request looks specific already — press **Continue with "
            "answers** to start, or **Skip**."
        )
        state, rows = [], _hidden_question_rows()
    else:
        note = _CLARIFY_NOTE
        state = [
            {"question": item.question, "options": list(item.options)}
            for item in questions
        ]
        rows = []
        for index, item in enumerate(questions):
            # Question text comes from the LLM: escape it before it reaches
            # the Markdown component (same untrusted-content boundary as the
            # timeline). Radio choices are rendered as plain text by Gradio.
            rows.append(
                gr.update(
                    visible=True,
                    value=f"**{index + 1}.** {html.escape(item.question)}",
                )
            )
            rows.append(
                gr.update(visible=True, choices=list(item.options), value=None)
            )
            rows.append(gr.update(visible=True, value=""))
        rows.extend(_hidden_question_rows()[len(rows):])

    return (
        gr.update(),  # run_button stays disabled while the panel is open
        gr.Markdown(
            "👇 **Answer any questions below — or skip — then continue.**",
            visible=True,
        ),
        state,
        gr.update(visible=True),
        gr.update(value=note),
        *rows,
    )


def _set_preparing():
    return (
        gr.Button("Preparing questions...", variant="primary", interactive=False),
        gr.Markdown("✨ **Preparing a couple of quick questions…**", visible=True),
    )


def _set_running():
    return (
        gr.Button("Processing...", variant="primary", interactive=False),
        gr.Markdown("🔄 **Researching...**", visible=True),
        gr.update(visible=False),  # hide the clarify panel once research starts
    )


def _restore_idle():
    return (
        gr.Button("Run", variant="primary", interactive=True),
        gr.Markdown("", visible=False),
    )


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

    # ux-09: optional clarifying questions before the run (skippable screen)
    clarify_state = gr.State([])  # [{"question": str, "options": [str]}]
    clarify_panel = gr.Column(visible=False)
    with clarify_panel:
        clarify_note = gr.Markdown(_CLARIFY_NOTE)
        clarify_rows = []
        for _ in range(MAX_QUESTIONS):
            q_label = gr.Markdown(visible=False)
            with gr.Row():
                q_radio = gr.Radio(label="Quick replies", choices=[], visible=False)
                q_free = gr.Textbox(
                    label="Or type your own answer", visible=False, lines=1
                )
            clarify_rows.append((q_label, q_radio, q_free))
        with gr.Row():
            clarify_skip = gr.Button("Skip — start research")
            clarify_go = gr.Button("Continue with answers", variant="primary")

    timeline = gr.HTML(value="", label="Research progress")  # Live timeline (ux-01)
    report = gr.Markdown(label="Report")  # Output area for the final report

    clarify_outputs = [run_button, status_text, clarify_state, clarify_panel, clarify_note]
    for _label, _radio, _free in clarify_rows:
        clarify_outputs += [_label, _radio, _free]

    # Run/Skip/Continue share button state management
    run_event = (
        run_button.click(fn=_set_preparing, outputs=[run_button, status_text], queue=False)
        .then(fn=clarify, inputs=query_textbox, outputs=clarify_outputs)
    )

    # Also allow submitting with Enter key
    submit_event = (
        query_textbox.submit(fn=_set_preparing, outputs=[run_button, status_text], queue=False)
        .then(fn=clarify, inputs=query_textbox, outputs=clarify_outputs)
    )

    # Skip: run immediately with no clarifications
    skip_event = (
        clarify_skip.click(
            fn=_set_running,
            outputs=[run_button, status_text, clarify_panel],
            queue=False,
        )
        .then(fn=run, inputs=query_textbox, outputs=[timeline, report], show_progress="hidden")
        .then(fn=_restore_idle, outputs=[run_button, status_text])
    )

    # Continue: collect answers into clarifications, then run
    go_inputs = [query_textbox, clarify_state]
    for _label, _radio, _free in clarify_rows:
        go_inputs += [_radio, _free]
    go_event = (
        clarify_go.click(
            fn=_set_running,
            outputs=[run_button, status_text, clarify_panel],
            queue=False,
        )
        .then(
            fn=run_with_answers,
            inputs=go_inputs,
            outputs=[timeline, report],
            show_progress="hidden",
        )
        .then(fn=_restore_idle, outputs=[run_button, status_text])
    )

ui.queue()  # Enable queuing for proper event handling
ui.launch(inbrowser=True)  # Launch UI and open it in the browser
