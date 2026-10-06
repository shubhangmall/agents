"""One-click export helpers for completed reports (ux-05).

Provides the backend half of the "Download .md" button: writes the final
report markdown to a temp file and returns its path, which Gradio's
DownloadButton serves under the file's basename. The "Copy report" button is
a pure client-side clipboard write wired up in deep_research.py, so no
backend code is needed for it.
"""
import os
import tempfile
import time

# Fixed filename prefix: no user input ever reaches the filesystem name.
EXPORT_FILENAME_PREFIX = "deep-research-report"
EXPORT_DIR_NAME = "deep_research_exports"
# Stale export files are pruned opportunistically to keep the temp dir tidy.
EXPORT_MAX_AGE_SECONDS = 24 * 60 * 60


def _export_dir() -> str:
    path = os.path.join(tempfile.gettempdir(), EXPORT_DIR_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def _prune_stale_exports(export_dir: str) -> None:
    now = time.time()
    try:
        entries = os.listdir(export_dir)
    except OSError:
        return
    for entry in entries:
        if not entry.startswith(EXPORT_FILENAME_PREFIX) or not entry.endswith(".md"):
            continue
        full = os.path.join(export_dir, entry)
        try:
            if now - os.path.getmtime(full) > EXPORT_MAX_AGE_SECONDS:
                os.remove(full)
        except OSError:
            pass


def export_report_file(report_md: str | None) -> str:
    """Write report markdown to a temp .md file; return the file path.

    Never raises on empty/bad input: an empty report produces a placeholder
    document instead. The returned path is safe to hand to Gradio as a
    DownloadButton value.
    """
    text = (report_md or "").strip()
    if not text:
        text = "# Deep Research report\n\n_No report content was generated._\n"
    elif not text.endswith("\n"):
        text += "\n"
    export_dir = _export_dir()
    _prune_stale_exports(export_dir)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    path = os.path.join(export_dir, f"{EXPORT_FILENAME_PREFIX}-{stamp}.md")
    if os.path.exists(path):
        # Same-second rerun: keep the name unique without ever colliding.
        path = os.path.join(
            export_dir, f"{EXPORT_FILENAME_PREFIX}-{stamp}-{os.getpid()}.md"
        )
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path
