"""Tests for ux-13: dark mode theme support + responsive/mobile layout."""
import re
import unittest
from unittest.mock import patch

import gradio as gr

import deep_research
import timeline
from timeline import TimelineState, render_timeline


# Hexes from the old hardcoded dark palette; they may only survive as var()
# fallbacks, never as literal declarations. (The progress-bar fill keeps an
# intentional #6ea8fe/#9d7bff accent gradient, which reads on both themes.)
_DARK_HEXES = (
    "#131b2c", "#0e1626", "#0c1322", "#232f4b",
    "#35507e", "#8b98b8", "#5b6a89",
    "#12271d", "#14293a", "#2a1414", "#2a1a2e",
)

_THEME_VARS = (
    "--block-background-fill",
    "--border-color-primary",
    "--block-border-color",
    "--background-fill-secondary",
    "--body-text-color",
    "--body-text-color-subdued",
    "--color-accent",
)


def _all_phase_html():
    """Timeline HTML across every render path (planning/active/writing/done/failed)."""
    planning = render_timeline(TimelineState()).html
    active_state = TimelineState(query="q")
    active_state.set_plan([("q1", "reason one"), ("q2", "reason two")])
    active = render_timeline(active_state).html
    active_state.begin_writing()
    writing = render_timeline(active_state).html
    active_state.mark_done("2 searches · 4 sources · 12s")
    done = render_timeline(active_state).html
    failed_state = TimelineState()
    failed_state.mark_failed("Planning failed")
    failed = render_timeline(failed_state).html
    return planning + active + writing + done + failed


class ThemeSupportTests(unittest.TestCase):
    def test_theme_is_a_gradio_theme(self):
        self.assertIsInstance(deep_research.THEME, gr.themes.Base)

    def test_theme_ships_dark_mode_styles(self):
        # The app header's built-in light/dark toggle needs .dark styles.
        css = deep_research.THEME._get_theme_css()
        self.assertIn(".dark", css)

    def test_main_launches_with_the_theme(self):
        # Gradio 6 moved `theme` from the Blocks constructor to launch().
        with patch.object(gr.Blocks, "launch") as mock_launch:
            deep_research.main()
        _, kwargs = mock_launch.call_args
        self.assertIs(kwargs.get("theme"), deep_research.THEME)

    def test_main_applies_responsive_css_at_launch(self):
        # Gradio 6 moved `css` from the Blocks constructor to launch().
        with patch.object(gr.Blocks, "launch") as mock_launch:
            deep_research.main()
        _, kwargs = mock_launch.call_args
        css = kwargs.get("css") or ""
        self.assertIn("@media", css)
        self.assertRegex(css, r"max-width\s*:\s*\d+px")
        self.assertIn("dr-run-btn", css)


class TimelineThemeAwareTests(unittest.TestCase):
    def test_no_hardcoded_dark_surfaces_outside_var_fallbacks(self):
        html = _all_phase_html()
        without_fallbacks = re.sub(r"var\([^)]*\)", "", html)
        for color in _DARK_HEXES:
            self.assertNotIn(
                color, without_fallbacks,
                f"{color} used as a literal instead of a theme variable",
            )

    def test_surfaces_borders_and_text_use_theme_variables(self):
        html = _all_phase_html()
        for var in _THEME_VARS:
            self.assertIn(f"var({var}", html, f"theme variable {var} missing")

    def test_spinner_uses_theme_variables(self):
        self.assertIn("var(--color-accent", timeline._SPIN_CSS)
        self.assertIn("var(--border-color-primary", timeline._SPIN_CSS)

    def test_cards_carry_responsive_class_with_mobile_rules(self):
        html = _all_phase_html()
        self.assertIn("drt-card", html)
        self.assertIn("@media", timeline._SPIN_CSS)
        self.assertIn("max-width", timeline._SPIN_CSS)


class ResponsiveLayoutTests(unittest.TestCase):
    def test_build_ui_returns_blocks_without_launching(self):
        with patch.object(gr.Blocks, "launch") as mock_launch:
            ui = deep_research.build_ui()
        mock_launch.assert_not_called()
        self.assertIsInstance(ui, gr.Blocks)

    def test_query_row_holds_input_and_button(self):
        ui = deep_research.build_ui()

        def walk(block):
            yield block
            for child in getattr(block, "children", None) or []:
                yield from walk(child)

        rows = [b for b in walk(ui) if isinstance(b, gr.Row)]
        self.assertTrue(rows, "expected a gr.Row for the query input + button")
        kinds = {type(b) for row in rows for b in walk(row)}
        self.assertIn(gr.Textbox, kinds)
        self.assertIn(gr.Button, kinds)

    def test_responsive_css_constant_targets_small_screens(self):
        css = deep_research._RESPONSIVE_CSS
        self.assertIn("@media", css)
        self.assertRegex(css, r"max-width\s*:\s*\d+px")
        self.assertIn("dr-query-row", css)


if __name__ == "__main__":
    unittest.main()
