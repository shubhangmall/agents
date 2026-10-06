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

import html
import json
import os
import time
import uuid
from pathlib import Path

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows has no fcntl
    fcntl = None

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


def _modify_store(store, mutate):
    """Read-modify-write the store under an exclusive file lock.

    `mutate(runs)` receives the current entry list and returns
    `(new_runs, result)`; the store is rewritten with `new_runs` (still via
    the atomic tmp+replace in _write_store) and `result` is returned.

    The lock serializes concurrent appends/deletes from threads or
    processes so no entry is silently lost. On platforms without fcntl
    (Windows) the mutation runs unlocked.
    """
    store.parent.mkdir(parents=True, exist_ok=True)
    if fcntl is None:
        runs = _read_store(store)
        new_runs, result = mutate(runs)
        _write_store(store, new_runs)
        return result
    lock_path = store.with_name(store.name + ".lock")
    with open(lock_path, "w", encoding="utf-8") as lock_handle:
        fcntl.flock(lock_handle, fcntl.LOCK_EX)
        try:
            runs = _read_store(store)
            new_runs, result = mutate(runs)
            _write_store(store, new_runs)
        finally:
            fcntl.flock(lock_handle, fcntl.LOCK_UN)
    return result


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
    Keeps at most max_entries runs, dropping the oldest. The read-modify-write
    is serialized with an exclusive file lock so concurrent appends cannot
    lose entries.
    """
    store = Path(path) if path else default_history_path()

    def mutate(runs):
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
        return runs, entry

    return _modify_store(store, mutate)


def delete_run(entry_id, *, path=None):
    """Remove one run by id; returns True if a run was removed."""
    store = Path(path) if path else default_history_path()

    def mutate(runs):
        kept = [entry for entry in runs if entry.get("id") != entry_id]
        return kept, len(kept) != len(runs)

    return _modify_store(store, mutate)


def entry_label(entry, max_query_len=60):
    """Dropdown label like 'Oct 06, 2026 · 01:20 · quantum batteries'.

    The query is HTML-escaped (defense in depth): Gradio renders dropdown
    labels as text today, but the label stays inert if it is ever rendered
    as HTML.
    """
    when = time.strftime(
        "%b %d, %Y · %H:%M", time.localtime(entry.get("timestamp", 0))
    )
    query = " ".join(str(entry.get("query", "")).split())
    if len(query) > max_query_len:
        query = query[: max_query_len - 1] + "…"
    query = html.escape(query)
    return f"{when} · {query}" if query else when
