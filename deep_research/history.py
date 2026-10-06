"""Session history for the Deep Research Gradio UI (ux-10).

Past runs (query, timestamp, report, sources) are persisted to a small JSON
file so the UI can list them in a dropdown: selecting a past run reloads its
report. The file store is fine for a local demo; a real deployment would swap
these functions for per-user server-side storage.

Entries are plain dicts:
    {"id": str, "query": str, "timestamp": float,
     "report": str, "sources": [{"title", "url", "domain"}, ...]}

The store file holds {"runs": [...]} in chronological (oldest-first) order;
load_history() returns entries newest-first for the dropdown.

Only the standard library is used so this module stays importable anywhere.
"""

import json
import os
import time
import uuid
from pathlib import Path

ENV_PATH = "DEEP_RESEARCH_HISTORY_PATH"
DEFAULT_FILENAME = ".deep_research_history.json"
MAX_ENTRIES = 50


def default_history_path():
    """Filesystem path of the history store.

    Honors DEEP_RESEARCH_HISTORY_PATH for overrides (and tests); otherwise
    lives in the user's home directory so it survives repo checkouts.
    """
    override = os.getenv(ENV_PATH, "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / DEFAULT_FILENAME


def _valid_entry(entry):
    return (
        isinstance(entry, dict)
        and isinstance(entry.get("id"), str)
        and isinstance(entry.get("query"), str)
        and isinstance(entry.get("timestamp"), (int, float))
        and isinstance(entry.get("report"), str)
        and isinstance(entry.get("sources"), list)
    )


def _read_store(store):
    try:
        with open(store, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        # Missing, unreadable, or corrupt file: history is empty, never an error.
        return []
    runs = data.get("runs") if isinstance(data, dict) else None
    if not isinstance(runs, list):
        return []
    return [entry for entry in runs if _valid_entry(entry)]


def _write_store(store, runs):
    store.parent.mkdir(parents=True, exist_ok=True)
    tmp = store.with_name(store.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump({"runs": runs}, handle, ensure_ascii=False)
    os.replace(tmp, store)


def load_history(path=None):
    """Return stored runs newest-first; never raises."""
    store = Path(path) if path else default_history_path()
    return list(reversed(_read_store(store)))


def entry_sources(search_results):
    """Flatten SearchResult.sources into JSON-able dicts, deduped by URL."""
    sources = []
    seen = set()
    for result in search_results or []:
        for source in getattr(result, "sources", None) or []:
            url = str(getattr(source, "url", "") or "").strip()
            if not url or url in seen:
                continue
            seen.add(url)
            sources.append(
                {
                    "title": str(getattr(source, "title", "") or ""),
                    "url": url,
                    "domain": str(getattr(source, "domain", "") or ""),
                }
            )
    return sources


def append_run(query, report, sources, *, path=None, timestamp=None,
               max_entries=MAX_ENTRIES):
    """Persist one completed run; returns the stored entry.

    sources is a list of {"title", "url", "domain"} dicts (see entry_sources).
    Keeps at most max_entries runs, dropping the oldest.
    """
    store = Path(path) if path else default_history_path()
    runs = _read_store(store)
    entry = {
        "id": uuid.uuid4().hex,
        "query": str(query or ""),
        "timestamp": float(timestamp) if timestamp is not None else time.time(),
        "report": str(report or ""),
        "sources": [
            {
                "title": str(item.get("title", "")),
                "url": str(item.get("url", "")),
                "domain": str(item.get("domain", "")),
            }
            for item in (sources or [])
            if isinstance(item, dict)
        ],
    }
    runs.append(entry)
    if max_entries is not None:
        runs = runs[-max_entries:]
    _write_store(store, runs)
    return entry


def delete_run(entry_id, *, path=None):
    """Remove one run by id; returns True if a run was removed."""
    store = Path(path) if path else default_history_path()
    runs = _read_store(store)
    kept = [entry for entry in runs if entry.get("id") != entry_id]
    if len(kept) == len(runs):
        return False
    _write_store(store, kept)
    return True


def entry_label(entry, max_query_len=60):
    """Dropdown label like 'Oct 06, 2026 · 01:20 · quantum batteries'."""
    when = time.strftime(
        "%b %d, %Y · %H:%M", time.localtime(entry.get("timestamp", 0))
    )
    query = " ".join(str(entry.get("query", "")).split())
    if len(query) > max_query_len:
        query = query[: max_query_len - 1] + "…"
    return f"{when} · {query}" if query else when
