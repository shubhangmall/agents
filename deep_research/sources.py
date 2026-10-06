"""Sources panel for the Deep Research UI (ux-02).

Renders the deduped research sources as a panel of clickable cards
(title, domain, link) above the report. Follows the same security pattern
as timeline.py: this module only ever produces SourcesUpdate events, which
the UI routes by *type* to the dedicated raw-HTML sources component.
Report/model text is plain str and can never produce one of these, which
keeps the untrusted-content boundary intact.
"""

import html as _html
from dataclasses import dataclass
from hashlib import sha256
from urllib.parse import urlparse

__all__ = ["SourcesUpdate", "dedupe_sources", "render_sources"]


@dataclass(frozen=True)
class SourcesUpdate:
    """Typed event carrying rendered sources HTML to the UI.

    Only application code can produce one of these (see render_sources),
    so the UI wrapper can route it to the raw-HTML sources component by
    type. Never constructed from model output.
    """

    html: str


def dedupe_sources(search_results) -> tuple:
    """Dedupe sources across search results by URL, preserving first-seen order."""
    seen: set[str] = set()
    unique: list = []
    for result in search_results:
        for source in getattr(result, "sources", None) or ():
            url = getattr(source, "url", "")
            if not url or url in seen:
                continue
            seen.add(url)
            unique.append(source)
    return tuple(unique)


def _is_safe_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


_AVATAR_COLORS = (
    "#4f6df5",
    "#7c5cf0",
    "#0ea5a5",
    "#4d9f6b",
    "#c07a2a",
    "#c0526b",
    "#5b8def",
    "#8a6ff0",
)


def _avatar_color(domain: str) -> str:
    digest = sha256(domain.encode("utf-8")).digest()
    return _AVATAR_COLORS[digest[0] % len(_AVATAR_COLORS)]


_CSS = (
    "<style>"
    ".drs-panel{margin:0 0 12px}"
    ".drs-head{font-size:13px;font-weight:600;color:#8b98b8;margin:0 0 8px;"
    "text-transform:uppercase;letter-spacing:.06em}"
    ".drs-count{display:inline-block;min-width:20px;text-align:center;"
    "background:#232f4b;color:#c7d2e8;border-radius:10px;padding:1px 7px;"
    "font-size:12px;margin-left:6px}"
    ".drs-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));"
    "gap:8px}"
    ".drs-card{display:flex;gap:10px;align-items:flex-start;text-decoration:none;"
    "background:#131b2c;border:1px solid #232f4b;border-radius:10px;"
    "padding:10px 12px;transition:border-color .15s}"
    ".drs-card:hover{border-color:#6ea8fe}"
    ".drs-avatar{flex:0 0 auto;width:30px;height:30px;border-radius:8px;color:#fff;"
    "font-weight:700;font-size:15px;display:flex;align-items:center;"
    "justify-content:center}"
    ".drs-meta{display:flex;flex-direction:column;min-width:0;gap:2px}"
    ".drs-title{color:#dbe4f5;font-size:13.5px;line-height:1.35;font-weight:600;"
    "display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;"
    "overflow:hidden}"
    ".drs-domain{color:#8b98b8;font-size:12px;white-space:nowrap;overflow:hidden;"
    "text-overflow:ellipsis}"
    "</style>"
)


def render_sources(sources) -> SourcesUpdate:
    """Render deduped sources as a 'Sources (n)' card panel event.

    Every text value is HTML-escaped and only http(s) URLs are linked, so
    source metadata can never break out of the card markup. Returns a
    SourcesUpdate (never a bare string) for type-based UI routing.
    """
    cards = []
    for source in sources:
        url = getattr(source, "url", "") or ""
        if not _is_safe_url(url):
            continue
        domain = getattr(source, "domain", "") or ""
        title = getattr(source, "title", "") or domain or url
        cards.append(
            '<a class="drs-card" href="'
            + _html.escape(url, quote=True)
            + '" target="_blank" rel="noopener noreferrer">'
            '<span class="drs-avatar" style="background:'
            + _avatar_color(domain)
            + '">'
            + _html.escape((domain[:1] or "?").upper())
            + "</span>"
            '<span class="drs-meta"><span class="drs-title">'
            + _html.escape(title)
            + '</span><span class="drs-domain">'
            + _html.escape(domain)
            + "</span></span></a>"
        )
    if not cards:
        return SourcesUpdate("")
    return SourcesUpdate(
        _CSS
        + '<div class="drs-panel"><div class="drs-head">Sources'
        + f'<span class="drs-count">{len(cards)}</span></div>'
        + '<div class="drs-grid">'
        + "".join(cards)
        + "</div></div>"
    )
