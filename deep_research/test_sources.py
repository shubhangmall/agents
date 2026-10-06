"""Tests for the sources panel (ux-02)."""
import asyncio
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import research_manager
import timeline
from sources import SourcesUpdate, dedupe_sources, render_sources
from search_agent import ResearchSource


def _src(url, title=None, domain=None):
    from urllib.parse import urlparse

    parsed = urlparse(url)
    return ResearchSource(
        id="source-test",
        title=title if title is not None else "t",
        url=url,
        domain=domain if domain is not None else parsed.netloc,
    )


class DedupeSourcesTests(unittest.TestCase):
    def test_dedupes_by_url_across_results(self):
        a = _src("https://a.example/x", "A")
        b = _src("https://b.example/y", "B")
        dup = _src("https://a.example/x", "A duplicate title")
        r1 = SimpleNamespace(sources=(a, b))
        r2 = SimpleNamespace(sources=(dup,))
        self.assertEqual(dedupe_sources([r1, r2]), (a, b))

    def test_preserves_first_seen_order(self):
        a = _src("https://a.example/1")
        b = _src("https://b.example/2")
        r = SimpleNamespace(sources=(b, a))
        self.assertEqual([s.url for s in dedupe_sources([r])],
                         ["https://b.example/2", "https://a.example/1"])

    def test_tolerates_missing_or_empty_sources(self):
        self.assertEqual(dedupe_sources([SimpleNamespace()]), ())
        self.assertEqual(dedupe_sources([SimpleNamespace(sources=None)]), ())
        self.assertEqual(dedupe_sources([]), ())


class RenderSourcesTests(unittest.TestCase):
    def test_renders_panel_with_count_and_cards(self):
        upd = render_sources((
            _src("https://a.example/x", "Alpha article", "a.example"),
            _src("https://b.example/y", "Beta post", "b.example"),
        ))
        self.assertIsInstance(upd, SourcesUpdate)
        self.assertIn("Sources", upd.html)
        self.assertIn('<span class="drs-count">2</span>', upd.html)
        self.assertEqual(upd.html.count('class="drs-card"'), 2)
        self.assertIn("Alpha article", upd.html)
        self.assertIn("a.example", upd.html)

    def test_cards_are_safe_external_links(self):
        upd = render_sources((_src("https://a.example/x", "T", "a.example"),))
        self.assertIn('href="https://a.example/x"', upd.html)
        self.assertIn('target="_blank"', upd.html)
        self.assertIn('rel="noopener noreferrer"', upd.html)

    def test_html_in_titles_and_domains_is_escaped(self):
        upd = render_sources((
            _src("https://a.example/x", '<script>alert(1)</script>', 'a.example"><b>'),
        ))
        self.assertNotIn("<script>", upd.html)
        self.assertIn("&lt;script&gt;", upd.html)
        self.assertIn("a.example&quot;&gt;&lt;b&gt;", upd.html)

    def test_non_http_urls_are_dropped(self):
        upd = render_sources((
            _src("https://a.example/ok", "OK"),
            _src("javascript:alert(1)", "Evil"),
            _src("ftp://f.example/file", "FTP"),
        ))
        self.assertEqual(upd.html.count('class="drs-card"'), 1)
        self.assertNotIn("javascript:", upd.html)
        self.assertNotIn("ftp://", upd.html)

    def test_empty_sources_render_empty_panel(self):
        upd = render_sources(())
        self.assertIsInstance(upd, SourcesUpdate)
        self.assertEqual(upd.html, "")

    def test_sources_update_is_frozen(self):
        upd = SourcesUpdate("<b>x</b>")
        with self.assertRaises(Exception):
            upd.html = "changed"


class SourcesRoutingTests(unittest.TestCase):
    """ux-01 boundary, extended: SourcesUpdate reaches only the sources component."""

    def test_sources_update_routes_to_sources_html(self):
        t, s, r, emit = timeline.route_chunk(
            SourcesUpdate("<b>src</b>"), "<b>t</b>", "", "md"
        )
        self.assertEqual((t, s, r, emit), ("<b>t</b>", "<b>src</b>", "md", True))

    def test_report_text_never_reaches_sources_html(self):
        payload = '<img src=x onerror=alert(1)>"><b>breakout'
        t, s, r, emit = timeline.route_chunk(payload, "<b>t</b>", "<i>old</i>", "")
        self.assertTrue(emit)
        self.assertEqual(s, "<i>old</i>")  # sources component untouched
        self.assertIn(payload, r)

    def test_timeline_update_does_not_touch_sources_html(self):
        from timeline import TimelineUpdate

        t, s, r, emit = timeline.route_chunk(
            TimelineUpdate("<b>t</b>"), "", "<i>keep</i>", ""
        )
        self.assertEqual((t, s, r, emit), ("<b>t</b>", "<i>keep</i>", "", True))


class SourcesIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_yields_sources_update_with_deduped_sources(self):
        manager = research_manager.ResearchManager()
        plan = SimpleNamespace(
            searches=[SimpleNamespace(query="q1", reason="r"),
                      SimpleNamespace(query="q2", reason="r")]
        )

        async def fake_plan(query):
            return plan

        async def fake_search(item):
            await asyncio.sleep(0)
            return SimpleNamespace(
                query=item.query,
                sources=(
                    _src("https://shared.example/doc", "Shared doc", "shared.example"),
                    _src(f"https://{item.query}.example/only", "Only here",
                         f"{item.query}.example"),
                ),
            )

        async def fake_writer(query, results):
            yield "report text"

        with (
            patch.object(manager, "plan_searches", fake_plan),
            patch.object(research_manager, "search_web", fake_search),
            patch.object(manager, "write_report", fake_writer),
            patch.dict(os.environ, {"SEND_RESEARCH_EMAIL": ""}),
        ):
            chunks = [c async for c in manager.run("query")]

        updates = [c for c in chunks if isinstance(c, SourcesUpdate)]
        self.assertEqual(len(updates), 1)
        html = updates[0].html
        # 2 searches x 2 sources, one shared -> 3 unique cards
        self.assertEqual(html.count('class="drs-card"'), 3)
        self.assertIn('<span class="drs-count">3</span>', html)
        self.assertIn("Shared doc", html)
        # The shared source appears only once despite being in both results
        self.assertEqual(html.count("https://shared.example/doc"), 1)
        # Sources panel is yielded before any report text
        first_str = next(i for i, c in enumerate(chunks) if isinstance(c, str))
        first_src = next(
            i for i, c in enumerate(chunks) if isinstance(c, SourcesUpdate)
        )
        self.assertLess(first_src, first_str)

    async def test_run_yields_empty_sources_panel_when_searches_fail(self):
        manager = research_manager.ResearchManager()
        plan = SimpleNamespace(searches=[SimpleNamespace(query="q1", reason="r")])

        async def fake_plan(query):
            return plan

        async def fake_search(item):
            raise RuntimeError("mock failure")

        async def fake_writer(query, results):
            yield "report text"

        with (
            patch.object(manager, "plan_searches", fake_plan),
            patch.object(research_manager, "search_web", fake_search),
            patch.object(manager, "write_report", fake_writer),
            patch.dict(os.environ, {"SEND_RESEARCH_EMAIL": ""}),
        ):
            chunks = [c async for c in manager.run("query")]

        updates = [c for c in chunks if isinstance(c, SourcesUpdate)]
        self.assertEqual(len(updates), 1)
        self.assertEqual(updates[0].html, "")


if __name__ == "__main__":
    unittest.main()
