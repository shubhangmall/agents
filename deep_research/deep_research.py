import gradio as gr
import logging
from plan_preview import PlanReady, plan_to_rows, rows_to_plan
from research_manager import ResearchManager
from provider_errors import ProviderError, public_error_message
from timeline import route_chunk

PLAN_ROWS = 5  # planner cap (planner_agent.HOW_MANY_SEARCHES); one editable row each


def _plan_updates(timeline_html, report_md, show, rows, planned):
    """Build one plan() yield tuple: (timeline, report, accordion, *rows, planned_query).

    The trailing planned_query snapshots the query the plan was built for, so
    editing the query box after planning cannot skew a later approved run.
    """
    return (
        timeline_html,
        report_md,
        gr.update(visible=show),
        *(
            gr.update(value=query, info=reason or None, visible=show and bool(query))
            for query, reason in rows
        ),
        planned,
    )


def _blank_rows():
    return [("", "")] * PLAN_ROWS


async def plan(query: str):
    """Phase 1: run the planner and present the plan for approval.

    Yields (timeline_html, report_md, plan_accordion, *plan_rows) tuples.
    PlanReady events are routed by type (like TimelineUpdate): only
    application code can produce one. No searching starts in this phase.
    """
    timeline_html = ""
    report_md = ""
    rows = _blank_rows()
    try:
        async for chunk in ResearchManager().plan_phase(query):
            if isinstance(chunk, PlanReady):
                rows = (plan_to_rows(chunk.plan) + _blank_rows())[:PLAN_ROWS]
                if any(query for query, _ in rows):
                    yield _plan_updates(timeline_html, report_md, True, rows, query)
                else:
                    yield _plan_updates(
                        timeline_html,
                        "⚠️ **The planner returned an empty plan.** "
                        "Try regenerating the plan or rephrasing your topic.",
                        False,
                        rows,
                        query,
                    )
                continue
            timeline_html, report_md, emit = route_chunk(chunk, timeline_html, report_md)
            if not emit:
                logging.error(
                    "Deep Research yielded unexpected chunk type: %s",
                    type(chunk).__name__,
                )
                continue
            yield _plan_updates(timeline_html, report_md, False, rows, query)
    except ProviderError as error:
        logging.error("Deep Research planning failed: %s", error.category)
        yield _plan_updates(timeline_html, public_error_message(error), False, rows, query)
    except Exception:
        logging.error("Deep Research planning failed: unexpected internal error")
        yield _plan_updates(
            timeline_html,
            "⚠️ **Deep Research could not plan this request. Please try again later.**",
            False,
            rows,
            query,
        )


async def approve_and_run(planned_query: str, *rows):
    """Phase 2: run the approved (possibly edited) plan.

    planned_query is the query the plan was built for, snapshotted at plan
    time via gr.State — not the live query box — so editing the query after
    planning cannot skew the run. Blank rows are dropped (clear a box to
    delete that search). Yields (timeline_html, report_md, plan_accordion,
    *plan_rows) tuples; the plan editor hides once the pipeline starts.
    """
    search_plan = rows_to_plan(rows)
    hidden_rows = [gr.update(value="", visible=False)] * PLAN_ROWS
    if not search_plan.searches:
        yield (
            gr.update(),
            "⚠️ **No searches left in the plan.** Restore a search or regenerate "
            "the plan, then approve again.",
            gr.update(visible=True),
            # Keep the rows visible (empty) so the user can actually type a
            # search back in; hiding them left a dead accordion.
            *[gr.update(value="", visible=True) for _ in range(PLAN_ROWS)],
        )
        return
    timeline_html = ""
    report_md = ""
    try:
        async for chunk in ResearchManager().run_from_plan(planned_query, search_plan):
            timeline_html, report_md, emit = route_chunk(chunk, timeline_html, report_md)
            if not emit:
                logging.error(
                    "Deep Research yielded unexpected chunk type: %s",
                    type(chunk).__name__,
                )
                continue
            yield timeline_html, report_md, gr.update(visible=False), *hidden_rows
    except ProviderError as error:
        logging.error("Deep Research request failed: %s", error.category)
        yield timeline_html, public_error_message(error), gr.update(visible=False), *hidden_rows
    except Exception:
        logging.error("Deep Research request failed: unexpected internal error")
        yield (
            timeline_html,
            "⚠️ **Deep Research could not complete this request. Please try again later.**",
            gr.update(visible=False),
            *hidden_rows,
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
    plan_button = gr.Button("1. Plan searches", variant="primary")  # Phase 1: plan only
    status_text = gr.Markdown("", visible=False)  # Status indicator with spinner
    # Phase 1 result: editable plan checklist (ux-04). Hidden until the
    # planner returns; no searching starts until the user approves.
    plan_accordion = gr.Accordion("📋 Review the research plan", visible=False, open=True)
    with plan_accordion:
        gr.Markdown(
            "Edit any search below, **clear a box to remove that search**, then approve — "
            "or regenerate a fresh plan."
        )
        plan_boxes = [
            gr.Textbox(label=f"Search {i + 1}", visible=False, lines=1)
            for i in range(PLAN_ROWS)
        ]
        with gr.Row():
            approve_button = gr.Button("2. Approve & research", variant="primary")
            regen_button = gr.Button("🔄 Regenerate plan", variant="secondary")
    # Snapshot of the query the shown plan was built for (ux-04 fix: prevents
    # query skew when the query box is edited after planning).
    planned_query = gr.State(value="")
    timeline = gr.HTML(value="", label="Research progress")  # Live timeline (ux-01)
    report = gr.Markdown(label="Report")  # Output area for the final report

    plan_outputs = [timeline, report, plan_accordion, *plan_boxes]
    # Phase 1 also snapshots the planned query as a trailing output.
    plan_event_outputs = [*plan_outputs, planned_query]

    # Phase 1: plan the searches, then show the editable plan for approval
    plan_event = (
        plan_button.click(
            fn=lambda: (
                gr.Button("Planning...", variant="primary", interactive=False),
                gr.Markdown("🔄 **Planning searches...**", visible=True),
            ),
            outputs=[plan_button, status_text],
            queue=False,
        )
        .then(
            fn=plan,
            inputs=query_textbox,
            outputs=plan_event_outputs,
            show_progress="hidden",
        )
        .then(
            fn=lambda: (
                gr.Button("1. Plan searches", variant="primary", interactive=True),
                gr.Markdown("", visible=False),
            ),
            outputs=[plan_button, status_text],
        )
    )

    # Also allow submitting with Enter key with button state management
    submit_event = (
        query_textbox.submit(
            fn=lambda: (
                gr.Button("Planning...", variant="primary", interactive=False),
                gr.Markdown("🔄 **Planning searches...**", visible=True),
            ),
            outputs=[plan_button, status_text],
            queue=False,
        )
        .then(
            fn=plan,
            inputs=query_textbox,
            outputs=plan_event_outputs,
            show_progress="hidden",
        )
        .then(
            fn=lambda: (
                gr.Button("1. Plan searches", variant="primary", interactive=True),
                gr.Markdown("", visible=False),
            ),
            outputs=[plan_button, status_text],
        )
    )

    # Phase 2: approve the (possibly edited) plan and run the pipeline.
    # plan_button, regen_button and query_textbox are disabled while the
    # pipeline runs so a second concurrent pipeline cannot start (via the
    # Plan button, Regenerate, or Enter); all are restored afterwards.
    # The query comes from the planned_query snapshot, not the live box.
    approve_event = (
        approve_button.click(
            fn=lambda: (
                gr.Button("Researching...", variant="primary", interactive=False),
                gr.Button("1. Plan searches", variant="primary", interactive=False),
                gr.Button("🔄 Regenerate plan", variant="secondary", interactive=False),
                gr.update(interactive=False),
                gr.Markdown("🔄 **Researching...**", visible=True),
            ),
            outputs=[approve_button, plan_button, regen_button, query_textbox, status_text],
            queue=False,
        )
        .then(
            fn=approve_and_run,
            inputs=[planned_query, *plan_boxes],
            outputs=plan_outputs,
            show_progress="hidden",
        )
        .then(
            fn=lambda: (
                gr.Button("2. Approve & research", variant="primary", interactive=True),
                gr.Button("1. Plan searches", variant="primary", interactive=True),
                gr.Button("🔄 Regenerate plan", variant="secondary", interactive=True),
                gr.update(interactive=True),
                gr.Markdown("", visible=False),
            ),
            outputs=[approve_button, plan_button, regen_button, query_textbox, status_text],
        )
    )

    # Regenerate: re-run the planner and present a fresh editable plan
    regen_event = (
        regen_button.click(
            fn=lambda: (
                gr.Button("Regenerating...", variant="secondary", interactive=False),
                gr.Markdown("🔄 **Planning searches...**", visible=True),
            ),
            outputs=[regen_button, status_text],
            queue=False,
        )
        .then(fn=plan, inputs=query_textbox, outputs=plan_event_outputs, show_progress="hidden")
        .then(
            fn=lambda: (
                gr.Button("🔄 Regenerate plan", variant="secondary", interactive=True),
                gr.Markdown("", visible=False),
            ),
            outputs=[regen_button, status_text],
        )
    )

ui.queue()  # Enable queuing for proper event handling
ui.launch(inbrowser=True)  # Launch UI and open it in the browser
