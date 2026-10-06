"""Tests for optional clarifying questions before a research run (ux-09)."""
import asyncio
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

# Gradio's import chain chokes on bracketed IPv6 entries in this sandbox's
# no_proxy; narrow it before anything imports gradio (see the deep_research
# UI smoke test below). Analytics are disabled so no telemetry thread can
# block interpreter shutdown behind the egress proxy.
os.environ["no_proxy"] = "localhost,127.0.0.1"
os.environ["NO_PROXY"] = "localhost,127.0.0.1"
os.environ["GRADIO_ANALYTICS_ENABLED"] = "False"

import clarify
import llm_client
import planner_agent
import research_manager
from clarify import (
    MAX_OPTIONS,
    MAX_QUESTIONS,
    ClarifyStructuredOutputError,
    ClarifyingQuestion,
    ClarifyingQuestions,
    format_clarifications,
    generate_questions,
    sanitize_questions,
)


def _questions_json(items):
    import json

    return json.dumps({"questions": items})


class ClarifyParseTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.valid = _questions_json(
            [
                {"question": "Who is this for?", "options": ["Beginners", "Experts"]},
                {"question": "How deep?", "options": ["Overview", "Deep dive"]},
            ]
        )

    async def _generate(self, response):
        class FakeClient:
            async def generate_structured(self, *args, **kwargs):
                return response

        with patch.object(clarify, "get_llm_client", return_value=FakeClient()):
            return await generate_questions("some query")

    async def test_parsed_plain_and_fenced_output_accepted(self):
        parsed = ClarifyingQuestions.model_validate_json(self.valid)
        questions = await self._generate(llm_client.StructuredResponse("unused", parsed))
        self.assertEqual(questions[0].question, "Who is this for?")
        self.assertEqual(questions[1].options, ["Overview", "Deep dive"])
        questions = await self._generate(llm_client.StructuredResponse(self.valid))
        self.assertEqual(len(questions), 2)
        fenced = f"```json\n{self.valid}\n```"
        questions = await self._generate(llm_client.StructuredResponse(fenced))
        self.assertEqual(len(questions), 2)

    async def test_invalid_or_empty_output_raises(self):
        with self.assertRaisesRegex(
            ClarifyStructuredOutputError, "invalid structured output"
        ):
            await self._generate(llm_client.StructuredResponse("not json"))
        with self.assertRaisesRegex(
            ClarifyStructuredOutputError, "no structured output"
        ):
            await self._generate(llm_client.StructuredResponse("   "))

    async def test_empty_questions_list_means_query_is_specific(self):
        questions = await self._generate(
            llm_client.StructuredResponse('{"questions": []}')
        )
        self.assertEqual(questions, [])

    async def test_provider_failure_propagates_to_caller(self):
        class FailingClient:
            async def generate_structured(self, *args, **kwargs):
                raise llm_client.ProviderUnavailableError("down")

        with patch.object(clarify, "get_llm_client", return_value=FailingClient()):
            with self.assertRaises(llm_client.ProviderUnavailableError):
                await generate_questions("query")

    async def test_prompt_asks_for_disambiguation_not_facts(self):
        captured = {}

        class FakeClient:
            async def generate_structured(self, prompt, **kwargs):
                captured["prompt"] = prompt
                return llm_client.StructuredResponse('{"questions": []}')

        with patch.object(clarify, "get_llm_client", return_value=FakeClient()):
            await generate_questions("quantum batteries")
        self.assertIn("quantum batteries", captured["prompt"])
        self.assertIn("quick-reply", captured["prompt"])


class ClarifySanitizeTests(unittest.TestCase):
    def _item(self, question="Q?", options=("a", "b")):
        return SimpleNamespace(question=question, options=list(options))

    def test_questions_capped_at_max(self):
        items = [self._item(question=f"Q{i}") for i in range(9)]
        self.assertEqual(len(sanitize_questions(items)), MAX_QUESTIONS)

    def test_options_capped_at_max(self):
        items = [self._item(options=[f"o{i}" for i in range(9)])]
        self.assertEqual(len(sanitize_questions(items)[0].options), MAX_OPTIONS)

    def test_empty_question_or_fewer_than_two_options_dropped(self):
        items = [
            self._item(question="   "),
            self._item(question="Q1", options=["only-one"]),
            self._item(question="Q2", options=["a", "b"]),
        ]
        cleaned = sanitize_questions(items)
        self.assertEqual([q.question for q in cleaned], ["Q2"])

    def test_blank_options_stripped(self):
        items = [self._item(options=[" a ", "  ", "b"])]
        self.assertEqual(sanitize_questions(items)[0].options, ["a", "b"])

    def test_none_input_returns_empty(self):
        self.assertEqual(sanitize_questions(None), [])


class FormatClarificationsTests(unittest.TestCase):
    def test_answers_render_as_planner_block(self):
        block = format_clarifications(
            [("Who is this for?", "Beginners"), ("How deep?", "Overview")]
        )
        self.assertIn("Who is this for?", block)
        self.assertIn("Beginners", block)
        self.assertIn("How deep?", block)

    def test_blank_answers_are_dropped(self):
        self.assertIsNone(format_clarifications([]))
        self.assertIsNone(format_clarifications([("Q?", ""), ("", "A")]))
        self.assertIsNone(format_clarifications([("  ", "  ")]))
        block = format_clarifications([("Q?", "A"), ("Q2", " ")])
        self.assertIn("Q?", block)
        self.assertNotIn("Q2", block)


class PlannerClarificationsTests(unittest.IsolatedAsyncioTestCase):
    async def _plan(self, clarifications):
        captured = {}

        class FakeClient:
            async def generate_structured(self, prompt, **kwargs):
                captured["prompt"] = prompt
                return llm_client.StructuredResponse(
                    '{"searches": []}', planner_agent.WebSearchPlan(searches=[])
                )

        with patch.object(planner_agent, "get_llm_client", return_value=FakeClient()):
            plan = await planner_agent.plan_searches("query", clarifications=clarifications)
        return plan, captured["prompt"]

    async def test_clarifications_are_fed_into_planner_prompt(self):
        plan, prompt = await self._plan("The user answered:\n- Who? → Beginners")
        self.assertEqual(plan.searches, [])
        self.assertIn("The user answered:", prompt)
        self.assertIn("Beginners", prompt)

    async def test_no_clarifications_leaves_prompt_unchanged(self):
        _, prompt = await self._plan(None)
        self.assertIn("Research query: query", prompt)
        self.assertNotIn("answered", prompt)
        _, prompt = await self._plan("   ")
        self.assertNotIn("answered", prompt)


class ManagerClarificationsTests(unittest.IsolatedAsyncioTestCase):
    async def _run(self, clarifications):
        manager = research_manager.ResearchManager()
        captured = {}

        async def fake_plan(query, clarifications=None):
            captured["clarifications"] = clarifications
            return SimpleNamespace(searches=[])

        async def fake_writer(query, results):
            yield "report"

        with (
            patch.object(manager, "plan_searches", fake_plan),
            patch.object(manager, "write_report", fake_writer),
            patch.dict(os.environ, {"SEND_RESEARCH_EMAIL": ""}),
        ):
            chunks = [chunk async for chunk in manager.run("query", clarifications=clarifications)]
        return captured, chunks

    async def test_run_threads_clarifications_to_planner(self):
        captured, chunks = await self._run("block")
        self.assertEqual(captured["clarifications"], "block")
        self.assertTrue(chunks[-1].endswith("report"))

    async def test_run_without_clarifications_passes_none(self):
        captured, _ = await self._run(None)
        self.assertIsNone(captured["clarifications"])


def _load_ui_module():
    """Exec deep_research.py without starting the Gradio server (ux-04 pattern)."""
    import sys

    repo = os.path.dirname(os.path.abspath(__file__))
    if repo not in sys.path:
        sys.path.insert(0, repo)
    src = open(os.path.join(repo, "deep_research.py")).read()
    src = src.replace("ui.queue()  # Enable queuing for proper event handling\n", "")
    src = src.replace("ui.launch(inbrowser=True)  # Launch UI and open it in the browser\n", "")
    namespace = {"__name__": "deep_research_clarify_test"}
    exec(compile(src, "deep_research.py", "exec"), namespace)
    return namespace


def _update_value(update):
    """gr.update() returns a dict; raw components expose .value."""
    if isinstance(update, dict):
        return update.get("value")
    return getattr(update, "value", None)


def _update_flag(update, flag):
    if isinstance(update, dict):
        return update.get(flag)
    return getattr(update, flag, None)


class ClarifyUISmokeTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.ns = _load_ui_module()
        cls.outputs = cls.ns["clarify_outputs"]
        cls.rows = cls.ns["clarify_rows"]

    def _question_payload(self):
        return [
            ClarifyingQuestion(question='Who is this for? <script>alert("x")</script>', options=["Beginners", "Experts"]),
            ClarifyingQuestion(question="How deep?", options=["Overview", "Deep dive"]),
        ]

    async def _clarify(self, query, fake):
        with patch.dict(self.ns, {"generate_questions": fake}):
            return await self.ns["clarify"](query)

    async def test_success_renders_questions_with_escaping(self):
        async def fake(query):
            self.assertEqual(query, "batteries")
            return self._question_payload()

        updates = await self._clarify("batteries", fake)
        self.assertEqual(len(updates), len(self.outputs))
        state = updates[2]
        self.assertEqual(len(state), 2)
        self.assertEqual(state[0]["options"], ["Beginners", "Experts"])
        # panel opens
        self.assertTrue(_update_flag(updates[3], "visible"))
        # first question label is HTML-escaped (untrusted LLM content)
        label_value = _update_value(updates[5])
        self.assertIn("&lt;script&gt;", label_value)
        self.assertNotIn("<script>", label_value)
        # quick replies carry the options, nothing preselected
        radio_update = updates[6]
        self.assertTrue(_update_flag(radio_update, "visible"))
        self.assertIsNone(_update_value(radio_update))
        self.assertEqual(radio_update.get("choices"), ["Beginners", "Experts"])
        # free-text box is empty and visible
        self.assertTrue(_update_flag(updates[7], "visible"))
        self.assertEqual(_update_value(updates[7]), "")
        # unused third row (indices 11-13) stays hidden
        self.assertFalse(_update_flag(updates[11], "visible"))
        self.assertFalse(_update_flag(updates[12], "visible"))
        self.assertFalse(_update_flag(updates[13], "visible"))

    async def test_llm_failure_still_opens_skippable_panel(self):
        async def fake(query):
            raise RuntimeError("provider down")

        updates = await self._clarify("batteries", fake)
        self.assertEqual(updates[2], [])
        self.assertTrue(_update_flag(updates[3], "visible"))
        self.assertIn("start research right away", _update_value(updates[4]))
        self.assertFalse(_update_flag(updates[5], "visible"))

    async def test_already_specific_query_shows_panel_without_questions(self):
        async def fake(query):
            return []

        updates = await self._clarify("batteries", fake)
        self.assertEqual(updates[2], [])
        self.assertTrue(_update_flag(updates[3], "visible"))
        self.assertIn("specific already", _update_value(updates[4]))

    async def test_blank_query_restores_idle_button(self):
        async def fake(query):
            raise AssertionError("LLM must not be called for a blank query")

        updates = await self._clarify("   ", fake)
        button = updates[0]
        self.assertEqual(_update_value(button), "Run")
        self.assertTrue(_update_flag(button, "interactive"))
        self.assertFalse(_update_flag(updates[3], "visible"))
        self.assertIn("enter a topic", _update_value(updates[1]).lower())

    async def test_run_with_answers_collects_replies_and_free_text(self):
        captured = {}

        async def fake_run(query, clarifications=None):
            captured["query"] = query
            captured["clarifications"] = clarifications
            yield ("<timeline>", "md")

        questions = [
            {"question": "Who is this for?", "options": ["Beginners", "Experts"]},
            {"question": "How deep?", "options": ["Overview", "Deep dive"]},
        ]
        with patch.dict(self.ns, {"run": fake_run}):
            # quick reply for Q1, free text for Q2 (free text wins)
            chunks = [
                chunk
                async for chunk in self.ns["run_with_answers"](
                    "batteries", questions, "Beginners", "", None, "very deep please"
                )
            ]
        self.assertEqual(chunks, [("<timeline>", "md")])
        self.assertEqual(captured["query"], "batteries")
        clarifications = captured["clarifications"]
        self.assertIn("Who is this for?", clarifications)
        self.assertIn("Beginners", clarifications)
        self.assertIn("very deep please", clarifications)

    async def test_run_with_no_answers_behaves_like_skip(self):
        captured = {}

        async def fake_run(query, clarifications=None):
            captured["clarifications"] = clarifications
            yield ("<timeline>", "md")

        questions = [{"question": "Who?", "options": ["a", "b"]}]
        with patch.dict(self.ns, {"run": fake_run}):
            awaitable = self.ns["run_with_answers"]("q", questions, None, "")
            chunks = [chunk async for chunk in awaitable]
        self.assertEqual(chunks, [("<timeline>", "md")])
        self.assertIsNone(captured["clarifications"])


if __name__ == "__main__":
    unittest.main()
