"""Clickable inline citation chips for the Deep Research report (ux-03).

Converts [source-XXXXXXXXXX] tokens in the streamed report Markdown into
small numbered clickable chips (Perplexity-style). Hovering a chip shows a
tooltip with the source title, domain, and URL; clicking it jumps to the
fragment ``#drc-source-N`` so the sources panel (ux-02) can give its Nth
card ``id="drc-source-N"`` and receive the jump once it is merged.

Keeps a numbered <-> source-ID map (built from the search results by
first-seen order, deduped by URL) and post-processes the streamed Markdown
with a regex -> HTML replacement.

Anchor contract (cross-PR dependency on the ux-02 sources panel):
    Chips link to ``#drc-source-N`` where N is the 1-based number assigned
    by ``build_citation_map`` (first-seen URL order, unsafe URLs excluded).
    The sources panel MUST emit ``id="drc-source-N"`` on its Nth card,
    using the same numbering, for chip clicks to jump to the card. Until
    the panel emits those ids, chip clicks are no-ops -- but the hover
    tooltip (title, domain, URL) keeps working regardless.

Only the standard library is used so this module stays importable anywhere.
All source text is HTML-escaped before rendering; tokens for unknown
source IDs are left untouched so the report never gains links to sources
that do not exist.
"""

import html as _html
import re
from urllib.parse import urlparse

__all__ = [
    "CITATION_CSS",
    "CITATION_RE",
    "build_citation_map",
    "linkify_citations",
    "render_report_html",
]

# The writer is instructed to cite claims as [source-XXXXXXXXXX]; real IDs
# are "source-" + 10 hex chars (see search_agent._source_id).
CITATION_RE = re.compile(r"\[source-([0-9a-f]{10})\]")

# Segments of the report Markdown where citation tokens must NOT become
# chips: fenced code blocks, inline code spans, and inline link/image
# syntax. A token inside a writer-authored link (e.g. the link text of
# `[source-...](url)`) is left to that link -- linkifying it would corrupt
# the Markdown. A token inside a code span would render chip HTML as
# literal tag text. An unclosed fence running to the end of the text is
# also protected so a mid-stream chunk does not flicker chips inside a
# code block (the next chunk re-renders from the accumulated Markdown).
_PROTECTED_RE = re.compile(
    r"```[\s\S]*?(?:```|$)"         # fenced code block (or unclosed fence to EOF)
    r"|`[^`\n]+`"                    # inline code span
    r"|!?\[[^\]\n]*\]\([^()\n]*\)",  # inline link or image
)

_CITATION_CSS = (
    "<style>"
    ".drc-chip{display:inline-block;min-width:18px;text-align:center;font-size:11px;"
    "font-weight:600;background:#1e2a44;border:1px solid #35507e;color:#9fc0ff;"
    "border-radius:9px;padding:0 5px;margin:0 1px;text-decoration:none;"
    "vertical-align:2px;line-height:16px;white-space:nowrap}"
    ".drc-chip:hover{background:#2b3d63;color:#cfe1ff;border-color:#6ea8fe}"
    "</style>"
)
CITATION_CSS = _CITATION_CSS


def _esc(text):
    return _html.escape("" if text is None else str(text), quote=True)


def _is_safe_url(url):
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def build_citation_map(search_results):
    """Build a source-ID -> numbered citation entry map.

    Dedupes by URL, preserving first-seen order across search results, so
    chip numbers match the order the sources panel shows them. Each entry
    is {"number", "title", "url", "domain"}.
    """
    entries = {}
    seen_urls = set()
    for result in search_results or ():
        for source in getattr(result, "sources", None) or ():
            url = getattr(source, "url", "") or ""
            sid = getattr(source, "id", "") or ""
            if not url or not sid or url in seen_urls or sid in entries:
                continue
            if not _is_safe_url(url):
                continue
            seen_urls.add(url)
            entries[sid] = {
                "number": len(entries) + 1,
                "title": getattr(source, "title", "") or "",
                "url": url,
                "domain": getattr(source, "domain", "") or "",
            }
    return entries


def _chip_html(entry):
    number = entry["number"]
    label = entry["title"] or entry["domain"] or "Source"
    tooltip = _esc(f"{label}\n{entry['url']}")
    return (
        f'<a href="#drc-source-{number}" class="drc-chip" '
        f'title="{tooltip}">[{number}]</a>'
    )


def linkify_citations(markdown, citation_map):
    """Replace known [source-XXXXXXXXXX] tokens with clickable chips.

    Tokens inside fenced code blocks, inline code spans, or Markdown
    link/image syntax are left untouched: linkifying them would corrupt
    the writer's own links or render chip HTML as literal tag text.
    Unknown or malformed tokens are left untouched. A mid-stream partial
    token never matches, so applying this to accumulated stream chunks is
    safe.
    """
    if not markdown or not citation_map:
        return markdown

    def _replace(match):
        entry = citation_map.get("source-" + match.group(1))
        if entry is None:
            return match.group(0)
        return _chip_html(entry)

    parts = []
    pos = 0
    for protected in _PROTECTED_RE.finditer(markdown):
        parts.append(CITATION_RE.sub(_replace, markdown[pos:protected.start()]))
        parts.append(protected.group(0))
        pos = protected.end()
    parts.append(CITATION_RE.sub(_replace, markdown[pos:]))
    return "".join(parts)


def render_report_html(report_markdown, citation_map):
    """Post-process streamed report Markdown: prepend chip CSS, linkify citations."""
    return CITATION_CSS + linkify_citations(report_markdown, citation_map)
