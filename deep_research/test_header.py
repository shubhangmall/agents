"""Tests for the ux-07 hero header and example topic chips.

header.py is pure data (no Gradio import) so its contract is tested directly.
The wiring in deep_research.py cannot be imported here (module-level
ui.launch), so it is verified structurally via AST instead.
"""
import ast
import os
import unittest

import header

_UI_PATH = os.path.join(os.path.dirname(__file__), "deep_research.py")


class HeaderCopyTests(unittest.TestCase):
    def test_header_is_a_hero_block_not_a_bare_title(self):
        self.assertIsInstance(header.HEADER_MARKDOWN, str)
        self.assertTrue(header.HEADER_MARKDOWN.startswith("#"))
        self.assertIn("Deep Research", header.HEADER_MARKDOWN.splitlines()[0])
        # more than a title line: describes what the product does
        self.assertGreaterEqual(len(header.HEADER_MARKDOWN.splitlines()), 3)

    def test_header_describes_the_agent_pipeline(self):
        text = header.HEADER_MARKDOWN.lower()
        self.assertIn("agents", text)
        for word in ("plan", "search", "report"):
            self.assertIn(word, text)

    def test_examples_label_is_plain_text(self):
        self.assertIsInstance(header.EXAMPLES_LABEL, str)
        self.assertTrue(header.EXAMPLES_LABEL.strip())


class ExampleTopicsTests(unittest.TestCase):
    def test_three_to_four_examples(self):
        self.assertGreaterEqual(len(header.EXAMPLE_TOPICS), 3)
        self.assertLessEqual(len(header.EXAMPLE_TOPICS), 4)

    def test_topics_are_unique_nonempty_strings(self):
        topics = header.EXAMPLE_TOPICS
        self.assertTrue(all(isinstance(t, str) and t.strip() for t in topics))
        self.assertEqual(len(set(topics)), len(topics))

    def test_topics_are_plain_text_safe_for_buttons(self):
        # Button values are rendered as text, never HTML; still, keep them
        # markup-free so nothing surprising can leak into the UI.
        for topic in header.EXAMPLE_TOPICS:
            self.assertNotIn("<", topic)
            self.assertNotIn(">", topic)

    def test_spec_example_is_covered(self):
        self.assertIn("EV adoption in Japan vs South Korea", header.EXAMPLE_TOPICS)


class UIWiringTests(unittest.TestCase):
    """Structural checks on deep_research.py (AST, no Gradio import needed)."""

    @classmethod
    def setUpClass(cls):
        with open(_UI_PATH, encoding="utf-8") as fh:
            cls.source = fh.read()
        cls.tree = ast.parse(cls.source)

    def test_ui_uses_header_module_copy(self):
        names = set()
        for node in ast.walk(self.tree):
            if isinstance(node, ast.ImportFrom) and node.module == "header":
                names.update(a.asname or a.name for a in node.names)
        self.assertIn("HEADER_MARKDOWN", names)
        self.assertIn("EXAMPLE_TOPICS", names)
        self.assertIn("HEADER_MARKDOWN", self.source)  # actually rendered
        self.assertNotIn('gr.Markdown("# Deep Research")', self.source)

    def test_bare_title_and_info_line_are_gone(self):
        self.assertNotIn("A team of **agents** will scour the web together", self.source)

    def test_one_button_per_example_topic(self):
        # finds `gr.Button(topic, ...) for topic in EXAMPLE_TOPICS`-style loops
        found = False
        for node in ast.walk(self.tree):
            if isinstance(node, ast.ListComp):
                for gen in node.generators:
                    if (
                        isinstance(gen.iter, ast.Name)
                        and gen.iter.id == "EXAMPLE_TOPICS"
                        and isinstance(node.elt, ast.Call)
                        and isinstance(node.elt.func, ast.Attribute)
                        and node.elt.func.attr == "Button"
                    ):
                        found = True
        self.assertTrue(found, "expected a gr.Button built per EXAMPLE_TOPICS entry")

    def test_chip_click_fills_query_textbox(self):
        # finds `chip.click(..., outputs=query_textbox)`
        found = False
        for node in ast.walk(self.tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "click"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "chip"
            ):
                outputs = [
                    kw for kw in node.keywords if kw.arg == "outputs"
                ]
                if outputs and isinstance(outputs[0].value, ast.Name):
                    self.assertEqual(outputs[0].value.id, "query_textbox")
                    found = True
        self.assertTrue(found, "expected chip.click wired to outputs=query_textbox")


if __name__ == "__main__":
    unittest.main()
