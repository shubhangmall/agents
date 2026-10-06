"""Plan preview / approval flow for the Deep Research Gradio UI (ux-04).

ResearchManager.run() is split into two stages: plan_phase() yields a single
PlanReady event carrying the planner's WebSearchPlan, and run_from_plan()
executes an approved plan. The Gradio UI shows the plan as editable textbox
rows inside an accordion with Approve / Regenerate buttons; no searching
starts until the user approves.

Design notes:
- PlanReady is a typed event like TimelineUpdate: only application code can
  produce one, so the UI routes it by type (isinstance check). It is never
  passed through timeline.route_chunk — route_chunk drops unknown chunk types
  instead of sending them to the raw-HTML timeline component, which keeps the
  untrusted-content boundary intact.
- Delete is "clear the box": rows_to_plan drops blank rows. Reasons are
  planner metadata shown as row info text; edited rows rebuild with an empty
  reason rather than a stale one.
- Only the standard library is used so this module stays importable anywhere.
"""

from dataclasses import dataclass

from planner_agent import HOW_MANY_SEARCHES, WebSearchItem, WebSearchPlan


@dataclass(frozen=True)
class PlanReady:
    """The planner finished; the plan awaits user approval before searching.

    Yielded exactly once by ResearchManager.plan_phase(). The UI populates
    its editable rows from plan.searches and must not start run_from_plan()
    until the user approves (possibly after edits).
    """

    plan: WebSearchPlan


def plan_to_rows(plan: WebSearchPlan) -> list[tuple[str, str]]:
    """Flatten a plan into editable (query, reason) row pairs, capped at the
    planner's search limit."""
    return [
        (item.query, item.reason) for item in plan.searches[:HOW_MANY_SEARCHES]
    ]


def rows_to_plan(rows) -> WebSearchPlan:
    """Rebuild a WebSearchPlan from edited UI rows.

    Blank rows are dropped (delete = clear the box); surviving rows keep
    their order and are capped at the planner's search limit. Reasons are
    reset because the planner's original reasons may no longer describe an
    edited query.
    """
    items = []
    for row in rows or []:
        query = (row or "").strip()
        if query:
            items.append(WebSearchItem(reason="", query=query))
    return WebSearchPlan(searches=items[:HOW_MANY_SEARCHES])
