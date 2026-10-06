"""Tests for suggested follow-up questions (ux-06)."""
import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import followup
from followup import (
    FollowupQuestions,
    build_followup_prompt,
    chip_values,
    clean_questions,
    followup_questions_for,
    report_failed,
    suggest_followups,
    template_fallback,
)


def _run(coro):
    return asyncio.run(coro)


def _fake_client(*, parsed=None, text="", error=None):
    async def generate_structured(prompt, schema=None, **kwargs):
        if error is not None:
            raise error
        return SimpleNamespace(parsed=parsed, text=text)

    return SimpleNamespace(generate_structured=generate_structured)


class CleanQuestionsTests(unittest.TestCase):
    def test_strips_and_drops_empties(self):
        self.assertEqual(clean_questions(["  Go deeper? ", "", "   ", None]), ["Go deeper?"])

    def test_dedupes_case_insensitively(self):
        self.assertEqual(
            clean_questions(["Compare X with Y", "compare x with y", "Compare X with Y"]),
            ["Compare X with Y"],
        )

    def test_caps_at_max_suggestions(self):
        self.assertEqual(
            len(clean_questions([f"q{i}" for i in range(10)])),
            followup.MAX_SUGGESTIONS,
        )

    def test_strips_html_metachars(self):
        questions = clean_questions(
            ["What about <script>alert(1)</script>?", "R&D budgets & <b>growth</b>"]
        )
        self.assertEqual(len(questions), 2)
        for q in questions:
            self.assertNotIn("<", q)
            self.assertNotIn(">", q)
            self.assertNotIn("&", q)
        self.assertIn("script", questions[0])  # text kept, markup gone

    def test_caps_length(self):
        long_q = "x" * 500
        result = clean_questions([long_q])
        self.assertEqual(len(result), 1)
        self.assertLessEqual(len(result[0]), followup.MAX_QUESTION_CHARS)
        self.assertTrue(result[0].endswith("…"))

    def test_handles_none(self):
        self.assertEqual(clean_questions(None), [])

    def test_coerces_non_strings(self):
        self.assertEqual(clean_questions([123, "ok"]), ["123", "ok"])


class TemplateFallbackTests(unittest.TestCase):
    def test_four_templates_mention_topic(self):
        questions = template_fallback("solid-state batteries")
        self.assertEqual(len(questions), 4)
        self.assertTrue(all("solid-state batteries" in q for q in questions))

    def test_empty_query_uses_generic_topic(self):
        questions = template_fallback("   ")
        self.assertEqual(len(questions), 4)
        self.assertTrue(all("this topic" in q for q in questions))

    def test_hostile_query_templates_have_no_raw_markup(self):
        questions = template_fallback("<img src=x onerror=alert(1)>")
        self.assertEqual(len(questions), 4)
        for q in questions:
            self.assertNotIn("<", q)
            self.assertNotIn(">", q)
            self.assertNotIn("&", q)


class ChipValuesTests(unittest.TestCase):
    def test_always_returns_max_suggestions_values(self):
        for n in range(0, 8):
            with self.subTest(n=n):
                values = chip_values([f"q{i}" for i in range(n)])
                self.assertEqual(len(values), followup.MAX_SUGGESTIONS)

    def test_pads_short_lists_with_none(self):
        values = chip_values(["a", "b"])
        self.assertEqual(
            values,
            ["a", "b"] + [None] * (followup.MAX_SUGGESTIONS - 2),
        )

    def test_truncates_long_lists(self):
        values = chip_values([f"q{i}" for i in range(10)])
        self.assertEqual(values, [f"q{i}" for i in range(followup.MAX_SUGGESTIONS)])


class BuildPromptTests(unittest.TestCase):
    def test_includes_query_and_report(self):
        prompt = build_followup_prompt("batteries", "A short report.")
        self.assertIn("batteries", prompt)
        self.assertIn("A short report.", prompt)

    def test_truncates_long_report(self):
        prompt = build_followup_prompt("q", "x" * 10000)
        self.assertLess(len(prompt), 10000)
        self.assertIn("…", prompt)


class ParseQuestionsTextTests(unittest.TestCase):
    def test_valid_json(self):
        text = '{"questions": ["One?", "Two?"]}'
        self.assertEqual(followup._parse_questions_text(text), ["One?", "Two?"])

    def test_fenced_json(self):
        text = '```json\n{"questions": ["One?"]}\n```'
        self.assertEqual(followup._parse_questions_text(text), ["One?"])

    def test_invalid_json_returns_empty(self):
        self.assertEqual(followup._parse_questions_text("not json at all"), [])

    def test_none_returns_empty(self):
        self.assertEqual(followup._parse_questions_text(None), [])


class SuggestFollowupsTests(unittest.TestCase):
    def test_uses_parsed_structured_output(self):
        client = _fake_client(parsed=FollowupQuestions(questions=["A?", "B?", "C?"]))
        with patch.object(followup, "get_llm_client", return_value=client):
            self.assertEqual(_run(suggest_followups("q", "report")), ["A?", "B?", "C?"])

    def test_falls_back_to_text_parse_when_unparsed(self):
        client = _fake_client(text='{"questions": ["Parsed?"]}')
        with patch.object(followup, "get_llm_client", return_value=client):
            self.assertEqual(_run(suggest_followups("q", "report")), ["Parsed?"])

    def test_llm_error_falls_back_to_templates(self):
        client = _fake_client(error=RuntimeError("provider down"))
        with patch.object(followup, "get_llm_client", return_value=client):
            questions = _run(suggest_followups("batteries", "report"))
        self.assertEqual(len(questions), 4)
        self.assertTrue(all("batteries" in q for q in questions))

    def test_unusable_output_falls_back_to_templates(self):
        client = _fake_client(parsed=FollowupQuestions(questions=[]), text="")
        with patch.object(followup, "get_llm_client", return_value=client):
            questions = _run(suggest_followups("batteries", "report"))
        self.assertEqual(len(questions), 4)

    def test_cleans_llm_questions(self):
        client = _fake_client(
            parsed=FollowupQuestions(questions=["A?", "a?", "", "B?", "C?", "D?", "E?"])
        )
        with patch.object(followup, "get_llm_client", return_value=client):
            self.assertEqual(
                _run(suggest_followups("q", "report")), ["A?", "B?", "C?", "D?"]
            )


class ReportFailedTests(unittest.TestCase):
    def test_provider_error_message_is_failure(self):
        self.assertTrue(report_failed("⚠️ **Deep Research could not complete this request.**"))

    def test_internal_error_message_is_failure(self):
        self.assertTrue(
            report_failed("⚠️ **Deep Research could not complete this request. Please try again later.**")
        )

    def test_completed_report_is_not_failure(self):
        self.assertFalse(report_failed("Research complete!\n\n# Report\n\nSome findings."))

    def test_none_is_failure(self):
        self.assertTrue(report_failed(None))


class FollowupQuestionsForTests(unittest.TestCase):
    def test_empty_query_skips_llm(self):
        client = _fake_client(parsed=FollowupQuestions(questions=["A?"]))
        with patch.object(followup, "get_llm_client", return_value=client) as get_client:
            self.assertEqual(_run(followup_questions_for("", "report")), [])
            get_client.assert_not_called()

    def test_empty_report_skips_llm(self):
        client = _fake_client(parsed=FollowupQuestions(questions=["A?"]))
        with patch.object(followup, "get_llm_client", return_value=client) as get_client:
            self.assertEqual(_run(followup_questions_for("q", "   ")), [])
            get_client.assert_not_called()

    def test_failed_report_skips_llm(self):
        client = _fake_client(parsed=FollowupQuestions(questions=["A?"]))
        with patch.object(followup, "get_llm_client", return_value=client) as get_client:
            self.assertEqual(
                _run(followup_questions_for("q", "⚠️ **Deep Research could not complete**")), []
            )
            get_client.assert_not_called()

    def test_successful_run_returns_llm_questions(self):
        client = _fake_client(parsed=FollowupQuestions(questions=["Go deeper?"]))
        with patch.object(followup, "get_llm_client", return_value=client):
            self.assertEqual(
                _run(followup_questions_for("q", "Research complete!\n\nreport")),
                ["Go deeper?"],
            )


if __name__ == "__main__":
    unittest.main()
