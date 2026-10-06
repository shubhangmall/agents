"""Hero header copy and example topic chips for the Deep Research UI (ux-07).

This module is intentionally free of Gradio imports so it stays unit-testable:
it holds only the copy and data that deep_research.py wires into components.
"""

# Hero header shown at the top of the app. Replaces the bare "# Deep Research"
# title plus one-line info text with a proper first-impression header.
HEADER_MARKDOWN = """# 🔎 Deep Research

**A team of AI agents that plans, searches the web, and writes your research report.**

Enter a topic below — or tap one of the example chips to get started. Research streams live, from plan to final report."""

# Label shown directly above the example chips.
EXAMPLES_LABEL = "💡 Try an example:"

# Clickable example topics. Each becomes a small button that fills the query
# textbox (it does not auto-run). Kept as plain text: button values are never
# interpreted as HTML, so no escaping is needed here.
EXAMPLE_TOPICS = (
    "EV adoption in Japan vs South Korea",
    "Future of AI coding assistants",
    "CRISPR gene therapy breakthroughs",
    "Progress on the SpaceX Starship program",
)
