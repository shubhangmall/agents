"""Tests for the report document view with table of contents (ux-11)."""
import unittest

import document_view
from document_view import (
    build_document_view,
    extract_citations,
    extract_headings,
    inject_heading_anchors,
    render_citations_html,
    render_toc_html,
    slugify,
)

SAMPLE = """# Quantum Batteries

Intro paragraph.

## How they work

Some text with a citation [source-abcdef1234].

### Electrode design

```python
# not a heading
x = 1
```

## How they work

Duplicate heading, another citation [source-abcdef1234] and [source-0011223344].

~~~
## also not a heading
~~~

## Conclusion & next steps!
"""


class SlugifyTests(unittest.TestCase):
    def test_basic_slug(self):
        self.assertEqual(slugify("How They Work"), "how-they-work")

    def test_strips_punctuation(self):
        self.assertEqual(slugify("Conclusion & next steps!"), "conclusion-next-steps")

    def test_empty_falls_back(self):
        self.assertEqual(slugify("!!!"), "section")

    def test_slug_is_id_safe(self):
        self.assertNotRegex(slugify('<script>alert("x")</script>'), r"[<>&\"']")


class ExtractHeadingsTests(unittest.TestCase):
    def test_levels_and_order(self):
        headings = extract_headings(SAMPLE)
        self.assertEqual(
            [(h.level, h.text) for h in headings],
            [
                (1, "Quantum Batteries"),
                (2, "How they work"),
                (3, "Electrode design"),
                (2, "How they work"),
                (2, "Conclusion & next steps!"),
            ],
        )

    def test_skips_fenced_code_blocks(self):
        headings = extract_headings(SAMPLE)
        texts = [h.text for h in headings]
        self.assertNotIn("not a heading", texts)
        self.assertNotIn("also not a heading", texts)

    def test_duplicate_headings_get_unique_anchors(self):
        headings = extract_headings(SAMPLE)
        anchors = [h.anchor for h in headings]
        self.assertEqual(len(anchors), len(set(anchors)))
        dups = [h for h in headings if h.text == "How they work"]
        self.assertEqual([h.anchor for h in dups], ["how-they-work", "how-they-work-2"])

    def test_empty_markdown(self):
        self.assertEqual(extract_headings(""), [])
        self.assertEqual(extract_headings(None), [])

    def test_heading_without_space_is_not_a_heading(self):
        self.assertEqual(extract_headings("#nospace"), [])


class InjectAnchorsTests(unittest.TestCase):
    def test_anchors_match_toc_links(self):
        body, headings = inject_heading_anchors(SAMPLE)
        toc = render_toc_html(headings)
        for h in headings:
            self.assertIn(f'href="#{h.anchor}"', toc)
            self.assertIn(f'<a id="{h.anchor}"></a>', body)

    def test_anchor_count_matches_heading_count(self):
        body, headings = inject_heading_anchors(SAMPLE)
        self.assertEqual(body.count("<a id="), len(headings))

    def test_non_heading_lines_untouched(self):
        body, _ = inject_heading_anchors("plain text\n\n- list item")
        self.assertEqual(body, "plain text\n\n- list item")

    def test_anchor_ids_are_markup_free(self):
        body, headings = inject_heading_anchors("# <script>alert(1)</script>\n")
        self.assertEqual(len(headings), 1)
        anchor_line = body.splitlines()[0]
        self.assertNotIn("<script>", anchor_line)
        self.assertRegex(anchor_line, r'^<a id="[a-z0-9-]+"></a>$')

    def test_empty_heading_does_not_shift_later_anchors(self):
        # Regression: an empty-text heading line ("# ") used to consume a
        # heading slot in the injection pass while extract_headings skipped
        # it, shifting every later anchor onto the wrong line.
        body, headings = inject_heading_anchors("# Real\n\n# \n\n## Second\n")
        self.assertEqual([h.anchor for h in headings], ["real", "second"])
        lines = body.splitlines()
        real_idx = lines.index("# Real")
        second_idx = lines.index("## Second")
        empty_idx = lines.index("# ")
        self.assertEqual(lines[real_idx - 1], '<a id="real"></a>')
        self.assertEqual(lines[second_idx - 1], '<a id="second"></a>')
        # no anchor was injected before the empty heading line
        self.assertNotEqual(lines[empty_idx - 1], '<a id="real"></a>')
        self.assertNotEqual(lines[empty_idx - 1], '<a id="second"></a>')
        self.assertEqual(body.count("<a id="), 2)

    def test_duplicate_titles_never_collide_with_suffixed_anchors(self):
        # Regression: dedupe only tracked base slugs, so ['A', 'A-2', 'A']
        # produced ['a', 'a-2', 'a-2'] — a duplicate id on the page.
        headings = extract_headings("# A\n\n# A-2\n\n# A\n")
        anchors = [h.anchor for h in headings]
        self.assertEqual(anchors, ["a", "a-2", "a-3"])
        self.assertEqual(len(set(anchors)), len(anchors))

    def test_anchor_uniqueness_holds_for_adversarial_title_mixes(self):
        headings = extract_headings("# B\n\n# B\n\n# B-2\n\n# B\n\n# B-2\n")
        anchors = [h.anchor for h in headings]
        self.assertEqual(len(set(anchors)), len(anchors))
        body, _ = inject_heading_anchors("# B\n\n# B\n\n# B-2\n\n# B\n\n# B-2\n")
        for a in anchors:
            self.assertEqual(body.count(f'<a id="{a}"></a>'), 1)


class RenderTocTests(unittest.TestCase):
    def test_links_are_html_escaped(self):
        headings = extract_headings("# <script>alert(1)</script>\n")
        toc = render_toc_html(headings)
        self.assertNotIn("<script>", toc)
        self.assertIn("&lt;script&gt;", toc)

    def test_empty_headings_placeholder(self):
        toc = render_toc_html([])
        self.assertIn("No sections yet", toc)

    def test_indents_by_relative_level(self):
        headings = extract_headings("# A\n### B\n")
        toc = render_toc_html(headings)
        self.assertIn("padding-left:0px", toc)
        self.assertIn("padding-left:28px", toc)


class ExtractCitationsTests(unittest.TestCase):
    def test_order_and_dedupe(self):
        self.assertEqual(
            extract_citations(SAMPLE), ["abcdef1234", "0011223344"]
        )

    def test_ignores_malformed_markers(self):
        md = "[source-xyz] [source-ABCDEF123456] [source-abcdef12345] [source-abcdef12347]"
        self.assertEqual(extract_citations(md), [])

    def test_empty(self):
        self.assertEqual(extract_citations(""), [])
        self.assertEqual(extract_citations(None), [])


class RenderCitationsTests(unittest.TestCase):
    def test_numbered_and_escaped(self):
        html = render_citations_html(["abcdef1234", "0011223344"])
        self.assertIn("[source-abcdef1234]", html)
        self.assertIn("[source-0011223344]", html)
        self.assertIn(">1<", html)
        self.assertIn(">2<", html)

    def test_malicious_id_cannot_inject_markup(self):
        html = render_citations_html(['"><img src=x onerror=alert(1)>'])
        self.assertNotIn("<img", html)
        self.assertIn("&quot;&gt;", html)

    def test_empty_placeholder(self):
        self.assertIn("No citations", render_citations_html([]))


class BuildDocumentViewTests(unittest.TestCase):
    def test_returns_consistent_triple(self):
        body, toc, cites = build_document_view(SAMPLE)
        headings = extract_headings(SAMPLE)
        for h in headings:
            self.assertIn(f'<a id="{h.anchor}"></a>', body)
            self.assertIn(f'href="#{h.anchor}"', toc)
        for source_id in extract_citations(SAMPLE):
            self.assertIn(f"[source-{source_id}]", cites)

    def test_empty_report(self):
        body, toc, cites = build_document_view("")
        self.assertEqual(body, "")
        self.assertIn("No sections yet", toc)
        self.assertIn("No citations", cites)


if __name__ == "__main__":
    unittest.main()
