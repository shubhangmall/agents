"""Live research progress timeline for the Deep Research Gradio UI (ux-01).

ResearchManager.run() yields TimelineUpdate events in place of the old coarse
progress strings ("Searches planned...", "Searches complete..."). The Gradio
wrapper in deep_research.py routes chunks to the progress component by *type*
(isinstance check), never by inspecting text content — producing a
TimelineUpdate requires application code, so model-generated report text can
never be misrouted into the raw-HTML progress component.

Design notes (from the verified 2026 patterns):
- ChatGPT: a live activity surface during the run that collapses to a compact
  summary when done -> the "done" state renders only a collapsed summary bar.
- Gemini: a named staged pipeline (Planning -> Searching -> Reasoning ->
  Reporting) -> the stepper + per-stage boxes below.
- Only the standard library is used so this module stays importable anywhere.

All planner/search text is HTML-escaped before rendering.
"""

import html as _html
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class TimelineUpdate:
    """A progress event for the research timeline.

    Yielded by ResearchManager.run(); the UI routes these to the gr.HTML
    progress component by type. Report text is plain str and can never
    produce one of these, which keeps the untrusted-content boundary intact.
    """

    html: str


@dataclass(frozen=True)
class SearchProgress:
    """Per-search completion event for the native progress bar (ux-08).

    Yielded by ResearchManager.run() once per planned search as it finishes
    (failed searches count too). The Gradio wrapper routes these by type to
    gr.Progress — rendering "Searching 2/5…" — and never to an HTML
    component, so this carries no untrusted content.
    """

    completed: int
    total: int

_ACTIVE = "active"
_DONE = "done"
_FAILED = "failed"

_SPIN_CSS = (
    "<style>"
    ".drt-spin{display:inline-block;width:12px;height:12px;border:2px solid #35507e;"
    "border-top-color:#6ea8fe;border-radius:50%;animation:drt-rot .8s linear infinite;vertical-align:-1px}"
    "@keyframes drt-rot{to{transform:rotate(360deg)}}"
    ".drt-pulse{animation:drt-pul 1.6s ease-in-out infinite}"
    "@keyframes drt-pul{0%,100%{opacity:1}50%{opacity:.45}}"
    "</style>"
)

_CARD = (
    "background:#131b2c;border:1px solid #232f4b;border-radius:12px;"
    "padding:14px 16px;margin:0 0 10px;font-size:14px;line-height:1.5"
)
_MUTED = "color:#8b98b8"
_ACCENT = "color:#6ea8fe"
_GREEN = "color:#4ade80"
_RED = "color:#f87171"


def _esc(text):
    return _html.escape("" if text is None else str(text), quote=True)


class TimelineState:
    """Mutable progress state for a single research run."""

    def __init__(self, query=""):
        self.query = query
        self.items = []  # {"query","reason","state","meta"}; state in active/done/failed
        self.phase = "plan"  # plan|search|write|done|failed|stopped
        self.started_at = time.monotonic()
        self.summary = None
        self.failure_message = ""
        self.stopped_message = ""

    def begin_planning(self):
        """Mark the planning stage active (the initial state)."""
        self.phase = "plan"

    def set_plan(self, items):
        """Record the planner output; searches become the active stage."""
        self.items = [
            {"query": q, "reason": r, "state": _ACTIVE, "meta": ""} for q, r in items
        ]
        self.phase = "search"

    def mark_search_done(self, query, ok=True, meta=""):
        """Flip the first still-active item matching query to done/failed."""
        for item in self.items:
            if item["query"] == query and item["state"] == _ACTIVE:
                item["state"] = _DONE if ok else _FAILED
                item["meta"] = meta
                return
        for item in self.items:
            if item["state"] == _ACTIVE:
                item["state"] = _DONE if ok else _FAILED
                item["meta"] = meta
                return

    def begin_writing(self):
        self.phase = "write"

    def mark_done(self, summary):
        self.phase = "done"
        self.summary = summary

    def mark_failed(self, message=""):
        """Terminal failure state (e.g. planning raised): no stuck spinner."""
        self.phase = "failed"
        self.failure_message = message

    def mark_stopped(self, message="Stopped by user"):
        """Terminal user-cancelled state (ux-08 Stop button): no stuck spinner."""
        self.phase = "stopped"
        self.stopped_message = message

    def elapsed(self):
        return time.monotonic() - self.started_at

    def counts(self):
        done = sum(1 for i in self.items if i["state"] == _DONE)
        failed = sum(1 for i in self.items if i["state"] == _FAILED)
        return done, failed, len(self.items)


def _stepper(state):
    """Four-stage stepper; hidden once the run is done (collapsed view)."""
    order = ["plan", "search", "write", "done"]
    labels = {"plan": "Plan", "search": "Searching", "write": "Writing", "done": "Report"}
    try:
        idx = order.index(state.phase)
    except ValueError:
        idx = 0
    steps = []
    for i, key in enumerate(order):
        if i < idx or state.phase == "done":
            mark, color = "✓", _GREEN
        elif i == idx:
            mark, color = '<span class="drt-spin"></span>', _ACCENT
        else:
            mark, color = str(i + 1), "color:#5b6a89"
        steps.append(
            f'<div style="flex:1;text-align:center;font-size:12px;font-weight:600;{color}">'
            f'<div style="margin-bottom:4px">{mark}</div>{labels[key]}</div>'
        )
    return (
        '<div style="display:flex;align-items:flex-start;margin:2px 0 12px">'
        + "".join(steps)
        + "</div>"
    )


def _plan_box(state):
    rows = []
    for item in state.items:
        rows.append(
            '<div style="display:flex;gap:10px;align-items:flex-start;padding:8px 10px;'
            "border:1px solid #232f4b;border-radius:8px;margin-bottom:6px;background:#0e1626\">"
            f'<span style="{_GREEN};font-weight:700">✓</span>'
            "<span style=\"flex:1\">"
            f"{_esc(item['query'])}"
            f"<span style=\"display:block;font-size:12px;{_MUTED}\">{_esc(item['reason'])}</span>"
            "</span></div>"
        )
    return (
        f'<div style="{_CARD}"><div style="font-weight:700;margin-bottom:10px">'
        f'<span style="font-size:11px;{_MUTED};text-transform:uppercase;letter-spacing:.6px">Stage 1 · </span>'
        "Research plan</div>" + "".join(rows) + "</div>"
    )


def _search_box(state):
    done, failed, total = state.counts()
    finished = (done + failed) == total and total > 0
    pct = int(100 * (done + failed) / total) if total else 100
    # ux-08: "Searching 2/5" plus a live elapsed timer while the run is alive.
    status = (
        f"{done + failed}/{total} searches complete"
        if finished
        else f"Searching {done + failed}/{total}"
    )
    status_line = f"{status} · {state.elapsed():.0f}s elapsed"
    rows = []
    for item in state.items:
        st = item["state"]
        if st == _DONE:
            icon = f'<span style="{_GREEN};font-weight:700">✓</span>'
            meta = f'<span style="font-size:12px;{_MUTED}">{_esc(item["meta"])}</span>' if item["meta"] else ""
        elif st == _FAILED:
            icon = f'<span style="{_RED};font-weight:700">✕</span>'
            meta = f'<span style="font-size:12px;{_MUTED}">failed</span>'
        else:
            icon = '<span class="drt-spin"></span>'
            meta = f'<span style="font-size:12px;{_MUTED}">searching…</span>'
        rows.append(
            '<div style="display:flex;gap:10px;align-items:center;padding:8px 10px;'
            "border:1px solid #232f4b;border-radius:8px;margin-bottom:6px;background:#0e1626\">"
            f"{icon}<span style=\"flex:1\">{_esc(item['query'])}</span>{meta}</div>"
        )
    return (
        f'<div style="{_CARD}"><div style="font-weight:700;margin-bottom:10px">'
        f'<span style="font-size:11px;{_MUTED};text-transform:uppercase;letter-spacing:.6px">Stage 2 · </span>'
        "Searching the web</div>"
        f'<div style="display:flex;justify-content:space-between;font-size:12px;{_MUTED};margin-bottom:6px">'
        f"<span>{status_line}</span></div>"
        '<div style="height:6px;background:#0c1322;border-radius:4px;overflow:hidden;margin-bottom:12px">'
        f'<div style="height:100%;width:{pct}%;background:linear-gradient(90deg,#6ea8fe,#9d7bff);'
        'border-radius:4px;transition:width .4s"></div></div>'
        + "".join(rows)
        + "</div>"
    )


def _write_box():
    return (
        f'<div style="{_CARD}"><div style="font-weight:700;margin-bottom:6px">'
        f'<span style="font-size:11px;{_MUTED};text-transform:uppercase;letter-spacing:.6px">Stage 3 · </span>'
        'Writing report <span class="drt-spin"></span></div>'
        f'<div class="drt-pulse" style="font-size:13px;{_MUTED}">'
        "Synthesizing evidence into a grounded report…</div></div>"
    )


def _done_bar(state):
    summary = _esc(state.summary or "")
    return (
        '<div style="background:linear-gradient(135deg,#12271d,#14293a);'
        "border:1px solid #1f5138;border-radius:12px;padding:12px 16px;"
        'display:flex;align-items:center;gap:12px;font-size:14px">'
        f'<span style="{_GREEN};font-size:20px;font-weight:700">✓</span>'
        "<span><b>Research complete</b>"
        + (f'<span style="{_MUTED}"> · {summary}</span>' if summary else "")
        + "</span></div>"
    )


def _failed_bar(state):
    detail = _esc(state.failure_message or "")
    return (
        '<div style="background:linear-gradient(135deg,#2a1414,#2a1a2e);'
        "border:1px solid #7f2d2d;border-radius:12px;padding:12px 16px;"
        'display:flex;align-items:center;gap:12px;font-size:14px">'
        f'<span style="{_RED};font-size:20px;font-weight:700">✕</span>'
        "<span><b>Research failed</b>"
        + (f'<span style="{_MUTED}"> · {detail}</span>' if detail else "")
        + "</span></div>"
    )


def _stopped_bar(state):
    """Neutral (non-error) banner for a user-cancelled run (ux-08)."""
    detail = _esc(state.stopped_message or "")
    return (
        '<div style="background:linear-gradient(135deg,#2a2114,#1c2333);'
        "border:1px solid #8a6d2f;border-radius:12px;padding:12px 16px;"
        'display:flex;align-items:center;gap:12px;font-size:14px">'
        '<span style="color:#fbbf24;font-size:20px;font-weight:700">⏹</span>'
        "<span><b>Research stopped</b>"
        + (f'<span style="{_MUTED}"> · {detail}</span>' if detail else "")
        + "</span></div>"
    )


def render_stopped(message=""):
    """Standalone stopped banner HTML for the Stop-button handler (ux-08).

    Appended to the last timeline HTML when the user cancels a run.
    """
    state = TimelineState()
    state.mark_stopped(message)
    return _SPIN_CSS + _stopped_bar(state)


def apply_stop_banner(timeline_html, running):
    """Append the 'Research stopped' banner iff research is still running.

    Pure helper for the Stop button (ux-08): when Stop is clicked after the
    run already finished (or twice), the timeline must be returned unchanged
    so a completed report is never stamped as stopped.
    """
    if not running:
        return timeline_html
    return timeline_html + render_stopped()


def render_timeline(state) -> TimelineUpdate:
    """Render the current TimelineState as a progress event for Gradio.

    Returns a TimelineUpdate (never a bare string) so the UI wrapper can
    route progress to the raw-HTML component by type.
    """
    if state.phase == "done":
        return TimelineUpdate(_SPIN_CSS + _done_bar(state))
    if state.phase == "failed":
        return TimelineUpdate(_SPIN_CSS + _failed_bar(state))
    if state.phase == "stopped":
        return TimelineUpdate(_SPIN_CSS + _stopped_bar(state))
    parts = [_SPIN_CSS, _stepper(state)]
    if state.items:
        parts.append(_plan_box(state))
        parts.append(_search_box(state))
    else:
        parts.append(
            f'<div style="{_CARD}"><span class="drt-spin"></span> '
            f'<span style="{_MUTED}">Planning searches…</span></div>'
        )
    if state.phase == "write":
        parts.append(_write_box())
    return TimelineUpdate("".join(parts))


def route_chunk(chunk, timeline_html="", report_md=""):
    """Route one ResearchManager.run() chunk to the UI components.

    Returns (timeline_html, report_md, emit). Only TimelineUpdate events —
    which only application code can produce — reach the raw-HTML timeline;
    plain str report text always lands in report_md, even if it contains
    marker-like text. Unknown chunk types are dropped (emit=False) rather
    than routed to either component.
    """
    if isinstance(chunk, TimelineUpdate):
        return chunk.html, report_md, True
    if isinstance(chunk, str):
        return timeline_html, chunk, True
    return timeline_html, report_md, False
