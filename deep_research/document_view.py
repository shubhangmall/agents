"""Report document view with table of contents (ux-11).

Long research reports render as a structured document instead of a single
scrolling markdown blob:

- left column: a headings-derived table of contents (anchor links),
- center column: the report body (Markdown with injected ``<a id>`` anchors
  so TOC links jump to the section),
- right column: the ``[source-XXXXXXXXXX]`` citations found in the report.

Only the standard library is used so this module stays importable anywhere.
All heading/citation text is HTML-escaped before rendering; anchors are
slugified to ``[a-z0-9-]`` so they can never carry markup.

Design notes (in-page structured view; the true fullscreen overlay from the
spec is the follow-up L-effort step):
- Headings are ATX only (``#`` .. ``######``); fenced code blocks are skipped
  so ``#`` inside code never becomes a TOC entry.
- Citations are the grounded ``[source-XXXXXXXXXX]`` markers the writer
  emits (10 lowercase hex chars, see search_agent.source_id); no invented
  sources.
"""

import html as _html
import re
from dataclasses import dataclass

_HEADING_RE = re.compile(r"^ {0,3}(#{1,6})[ \t]+(.*?)[ \t]*#*[ \t]*$")
_FENCE_RE = re.compile(r"^\s*(```|~~~)")
_CITATION_RE = re.compile(r"\[source-([0-9a-f]{10})\]")
_SLUG_BAD_RE = re.compile(r"[^a-z0-9]+")

_CARD = (
    "background:#131b2c;border:1px solid #232f4b;border-radius:12px;"
    "padding:14px 16px;margin:0 0 10px;font-size:14px;line-height:1.5"
)
_MUTED = "color:#8b98b8"
_ACCENT = "color:#6ea8fe"
_HEADER = (
    "font-weight:700;margin-bottom:10px;font-size:12px;"
    "text-transform:uppercase;letter-spacing:.6px;" + _MUTED
)


def _esc(text):
    return _html.escape("" if text is None else str(text), quote=True)


@dataclass(frozen=True)
class Heading:
    """One ATX heading parsed out of the report Markdown."""

    level: int  # 1..6
    text: str  # raw heading text (may contain inline markdown)
    anchor: str  # unique slug, safe for use as an HTML id


def slugify(text):
    """Turn heading text into a URL/HTML-id-safe slug (GitHub-style)."""
    slug = _SLUG_BAD_RE.sub("-", str(text).lower()).strip("-")
    return slug or "section"


def _iter_heading_lines(markdown):
    """Yield (lineno, level, text) for non-empty ATX headings outside fences.

    Single source of truth for "which lines are real headings": both
    extract_headings() and inject_heading_anchors() iterate via this helper,
    so the Nth heading line always pairs with the Nth parsed heading.
    """
    in_fence = False
    for lineno, line in enumerate((markdown or "").splitlines()):
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = _HEADING_RE.match(line)
        if not match:
            continue
        text = match.group(2).strip()
        if text:
            yield lineno, len(match.group(1)), text


def _iter_headings(markdown):
    """Yield (level, text) for ATX headings outside fenced code blocks."""
    for _lineno, level, text in _iter_heading_lines(markdown):
        yield level, text


def extract_headings(markdown):
    """Parse report Markdown into a list of Heading with unique anchors.

    Duplicate heading texts get ``-2``, ``-3`` ... suffixes so every anchor
    is unique on the page.
    """
    headings = []
    seen = set()  # every anchor generated so far (base and suffixed alike)
    counts = {}
    for level, text in _iter_headings(markdown):
        base = slugify(text)
        n = counts.get(base, 0) + 1
        anchor = base if n == 1 else f"{base}-{n}"
        while anchor in seen:
            n += 1
            anchor = f"{base}-{n}"
        counts[base] = n
        seen.add(anchor)
        headings.append(Heading(level=level, text=text, anchor=anchor))
    return headings


def inject_heading_anchors(markdown):
    """Return (markdown, headings) with ``<a id="anchor"></a>`` jump targets.

    The anchor before each heading line matches the anchor that
    render_toc_html() links to, so TOC entries scroll to their section.
    Non-heading lines pass through untouched.
    """
    headings = extract_headings(markdown)
    by_line = {}  # line index -> anchor, in document order
    # Consume heading slots positionally via the same helper extract_headings
    # uses, so empty-text lines (which extract_headings skips) can never
    # shift the anchors of the real headings that follow them.
    for idx, (lineno, _level, _text) in enumerate(_iter_heading_lines(markdown)):
        if idx >= len(headings):
            break
        by_line[lineno] = headings[idx].anchor
    out = []
    for lineno, line in enumerate((markdown or "").splitlines()):
        if lineno in by_line:
            out.append(f'<a id="{by_line[lineno]}"></a>')
        out.append(line)
    return "\n".join(out), headings


def render_toc_html(headings):
    """Render the headings as a left-column table of contents (raw HTML)."""
    if not headings:
        body = f'<div style="font-size:13px;{_MUTED}">No sections yet.</div>'
    else:
        base_level = min(h.level for h in headings)
        links = []
        for h in headings:
            indent = (h.level - base_level) * 14
            links.append(
                f'<a href="#{h.anchor}" style="display:block;{_ACCENT};'
                f"text-decoration:none;padding:3px 0;padding-left:{indent}px;"
                'font-size:13px">'
                f"{_esc(h.text)}</a>"
            )
        body = "<nav>" + "".join(links) + "</nav>"
    return (
        f'<div style="{_CARD}"><div style="{_HEADER}">Contents</div>'
        + body
        + "</div>"
    )


def extract_citations(markdown):
    """Return the ``[source-XXXXXXXXXX]`` ids in first-seen order, deduped."""
    seen = []
    for match in _CITATION_RE.finditer(markdown or ""):
        source_id = match.group(1)
        if source_id not in seen:
            seen.append(source_id)
    return seen


def render_citations_html(citations):
    """Render the right-column citations card (raw HTML)."""
    if not citations:
        body = (
            f'<div style="font-size:13px;{_MUTED}">'
            "No citations in this report.</div>"
        )
    else:
        rows = []
        for i, source_id in enumerate(citations, start=1):
            rows.append(
                '<div style="display:flex;gap:8px;align-items:baseline;'
                "padding:6px 0;border-bottom:1px solid #1c2740;font-size:13px\">"
                f'<span style="flex:none;min-width:26px;text-align:center;'
                f"background:#1c2b4d;border-radius:6px;padding:1px 6px;{_ACCENT};"
                'font-weight:700;font-size:12px">'
                f"{i}</span>"
                f"<code style=\"color:#c8d3ea\">[{_esc('source-' + source_id)}]</code>"
                "</div>"
            )
        body = "".join(rows)
    return (
        f'<div style="{_CARD}"><div style="{_HEADER}">Citations</div>'
        + body
        + "</div>"
    )


def build_document_view(report_md):
    """Build the three document-view parts from a finished report.

    Returns (body_md, toc_html, citations_html): the report Markdown with
    heading anchors injected, the TOC panel HTML, and the citations panel
    HTML. The caller renders body_md in a Markdown component and the two
    panels in raw-HTML components.
    """
    body_md, headings = inject_heading_anchors(report_md or "")
    return body_md, render_toc_html(headings), render_citations_html(
        extract_citations(report_md)
    )
