"""Tests for the clickable inline citation chips (ux-03)."""

import unittest

from citations import (
    CITATION_CSS,
    CITATION_RE,
    build_citation_map,
    linkify_citations,
    render_report_html,
)
from search_agent import ResearchSource, SearchResult


def _source(sid, title, url, domain=None):
    domain = domain if domain is not None else url.split("//", 1)[-1].split("/", 1)[0]
    return ResearchSource(id=sid, title=title, url=url, domain=domain)


def _results():
    return [
        SearchResult(
            query="q1",
            summary="s1",
            sources=(
                _source("source-aaaaaaaaaa", "First Article", "https://a.example/one"),
                _source("source-bbbbbbbbbb", "Second Article", "https://b.example/two"),
            ),
        ),
        SearchResult(
            query="q2",
            summary="s2",
            sources=(
                # Duplicate URL of the first source: deduped, keeps number 1.
                _source("source-aaaaaaaaaa", "First Article (dup)", "https://a.example/one"),
                _source("source-cccccccccc", "Third Article", "https://c.example/three"),
            ),
        ),
    ]


class BuildCitationMapTests(unittest.TestCase):
    def test_numbers_follow_first_seen_order(self):
        cmap = build_citation_map(_results())
        self.assertEqual(cmap["source-aaaaaaaaaa"]["number"], 1)
        self.assertEqual(cmap["source-bbbbbbbbbb"]["number"], 2)
        self.assertEqual(cmap["source-cccccccccc"]["number"], 3)

    def test_dedupes_by_url(self):
        cmap = build_citation_map(_results())
        self.assertEqual(len(cmap), 3)
        self.assertEqual(cmap["source-aaaaaaaaaa"]["title"], "First Article")

    def test_skips_unsafe_urls(self):
        results = [
            SearchResult(
                query="q",
                summary="s",
                sources=(
                    _source("source-dddddddddd", "Evil", "javascript:alert(1)"),
                    _source("source-eeeeeeeeee", "Fine", "https://e.example/"),
                ),
            )
        ]
        cmap = build_citation_map(results)
        self.assertNotIn("source-dddddddddd", cmap)
        self.assertEqual(cmap["source-eeeeeeeeee"]["number"], 1)

    def test_empty_results(self):
        self.assertEqual(build_citation_map([]), {})
        self.assertEqual(build_citation_map(None), {})


class LinkifyCitationsTests(unittest.TestCase):
    def setUp(self):
        self.cmap = build_citation_map(_results())

    def test_known_token_becomes_chip(self):
        out = linkify_citations("Claim. [source-aaaaaaaaaa]", self.cmap)
        self.assertIn('class="drc-chip"', out)
        self.assertIn('href="#drc-source-1"', out)
        self.assertIn("[1]", out)
        self.assertNotIn("[source-aaaaaaaaaa]", out)

    def test_chip_tooltip_has_title_and_url(self):
        out = linkify_citations("[source-bbbbbbbbbb]", self.cmap)
        self.assertIn('href="#drc-source-2"', out)
        self.assertIn("Second Article", out)
        self.assertIn("https://b.example/two", out)

    def test_repeated_token_reuses_same_number(self):
        out = linkify_citations(
            "[source-aaaaaaaaaa] and again [source-aaaaaaaaaa]", self.cmap
        )
        self.assertEqual(out.count('href="#drc-source-1"'), 2)
        self.assertEqual(out.count("[1]"), 2)

    def test_unknown_source_id_left_untouched(self):
        out = linkify_citations("Invented. [source-ffffffff99]", self.cmap)
        self.assertIn("[source-ffffffff99]", out)
        self.assertNotIn("drc-chip", out)

    def test_malformed_tokens_untouched(self):
        for token in ("[source-abc]", "[source-AAAAAAAAAA]", "[source-aaaaaaaaaaa]",
                      "source-aaaaaaaaaa", "[source-aaaaaaaaa ]"):
            out = linkify_citations(f"x {token} y", self.cmap)
            self.assertIn(token, out, token)
            self.assertNotIn("drc-chip", out)

    def test_partial_stream_token_untouched(self):
        # A chunk boundary cutting a token in half must not produce a chip.
        out = linkify_citations("Claim. [source-aaaaa", self.cmap)
        self.assertNotIn("drc-chip", out)

    def test_token_inside_markdown_link_left_untouched(self):
        # The writer's own link wins: linkifying here used to destroy the
        # link and leave a dangling "(url)" literal.
        md = "see [source-aaaaaaaaaa](https://y.example) for details"
        out = linkify_citations(md, self.cmap)
        self.assertEqual(out, md)
        self.assertNotIn("drc-chip", out)

    def test_token_inside_link_url_left_untouched(self):
        md = "[read more](https://y.example/?ref=[source-aaaaaaaaaa])"
        out = linkify_citations(md, self.cmap)
        self.assertEqual(out, md)
        self.assertNotIn("drc-chip", out)

    def test_token_inside_image_syntax_left_untouched(self):
        md = "![source-aaaaaaaaaa](https://y.example/img.png)"
        out = linkify_citations(md, self.cmap)
        self.assertEqual(out, md)
        self.assertNotIn("drc-chip", out)

    def test_token_inside_inline_code_span_left_untouched(self):
        md = "use `[source-aaaaaaaaaa]` literally"
        out = linkify_citations(md, self.cmap)
        self.assertEqual(out, md)
        self.assertNotIn("drc-chip", out)

    def test_token_inside_fenced_code_block_left_untouched(self):
        md = "```\ncode [source-aaaaaaaaaa] here\n```\n\nReal claim [source-bbbbbbbbbb]."
        out = linkify_citations(md, self.cmap)
        self.assertIn("[source-aaaaaaaaaa]", out)  # protected
        self.assertNotIn("[source-bbbbbbbbbb]", out)  # linkified
        self.assertIn('href="#drc-source-2"', out)
        self.assertEqual(out.count("drc-chip"), 1)

    def test_token_before_parens_without_link_syntax_still_linkified(self):
        # "[token] (url)" is not a Markdown link (space before paren),
        # so the token still becomes a chip.
        md = "see [source-aaaaaaaaaa] (https://y.example)"
        out = linkify_citations(md, self.cmap)
        self.assertIn('href="#drc-source-1"', out)
        self.assertNotIn("[source-aaaaaaaaaa]", out)

    def test_empty_map_returns_markdown_unchanged(self):
        md = "No chips. [source-aaaaaaaaaa]"
        self.assertEqual(linkify_citations(md, {}), md)

    def test_surrounding_markdown_preserved(self):
        md = "# Title\n\n**Bold** claim [source-cccccccccc] done."
        out = linkify_citations(md, self.cmap)
        self.assertTrue(out.startswith("# Title\n\n**Bold** claim "))
        self.assertTrue(out.endswith(" done."))
        self.assertIn('href="#drc-source-3"', out)

    def test_xss_in_source_fields_is_escaped(self):
        results = [
            SearchResult(
                query="q",
                summary="s",
                sources=(
                    _source(
                        "source-eeeeeeeeee",
                        '"><img src=x onerror=alert(1)>',
                        "https://e.example/x?a=1&b=2",
                    ),
                ),
            )
        ]
        cmap = build_citation_map(results)
        out = linkify_citations("[source-eeeeeeeeee]", cmap)
        self.assertNotIn("<img", out)
        # The attribute-breakout attempt never survives: quotes and angle
        # brackets are escaped, so the payload is inert tooltip text.
        self.assertNotIn('"><img src=x onerror=alert(1)>', out)
        self.assertIn("&lt;img", out)
        self.assertIn("&quot;&gt;", out)
        self.assertIn("https://e.example/x?a=1&amp;b=2", out)


class RenderReportHtmlTests(unittest.TestCase):
    def test_css_prepended_and_tokens_linkified(self):
        cmap = build_citation_map(_results())
        out = render_report_html("Claim [source-aaaaaaaaaa].", cmap)
        self.assertTrue(out.startswith(CITATION_CSS))
        self.assertIn('class="drc-chip"', out)

    def test_css_present_without_tokens(self):
        out = render_report_html("Plain report, no citations.", build_citation_map(_results()))
        self.assertIn(".drc-chip", out)
        self.assertNotIn("[source-", out)

    def test_css_is_a_style_block(self):
        self.assertTrue(CITATION_CSS.startswith("<style>"))
        self.assertTrue(CITATION_CSS.endswith("</style>"))


class CitationRegexTests(unittest.TestCase):
    def test_matches_ten_hex_chars(self):
        m = CITATION_RE.search("[source-abcdef0123]")
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "abcdef0123")

    def test_rejects_wrong_length(self):
        self.assertIsNone(CITATION_RE.search("[source-abc]"))
        self.assertIsNone(CITATION_RE.search("[source-abcdef012345]"))


if __name__ == "__main__":
    unittest.main()
