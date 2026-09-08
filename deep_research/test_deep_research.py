import asyncio
import os
from pathlib import Path
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import config
import llm_client
import planner_agent
import research_manager
import search_agent
import search_client
import writer_agent
from provider_errors import (
    ProviderConfigurationError,
    ProviderUnavailableError,
    UnsupportedProviderCapabilityError,
    WriterStreamError,
    public_error_message,
)
from search_client import SearchHit


class PlannerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.valid = '{"searches":[{"reason":"scope","query":"agent patterns"}]}'

    async def _plan(self, response):
        class FakeClient:
            async def generate_structured(self, *args, **kwargs):
                return response

        with patch.object(planner_agent, "get_llm_client", return_value=FakeClient()):
            return await planner_agent.plan_searches("query")

    async def test_planner_accepts_parsed_plain_and_fenced_output(self):
        parsed = planner_agent.WebSearchPlan.model_validate_json(self.valid)
        self.assertEqual((await self._plan(llm_client.StructuredResponse("unused", parsed))).searches[0].query, "agent patterns")
        self.assertEqual((await self._plan(llm_client.StructuredResponse(self.valid))).searches[0].query, "agent patterns")
        fenced = f"```json\n{self.valid}\n```"
        self.assertEqual((await self._plan(llm_client.StructuredResponse(fenced))).searches[0].query, "agent patterns")

    async def test_planner_caps_and_sanitizes_invalid_output(self):
        searches = [{"reason": "r", "query": str(index)} for index in range(8)]
        response = llm_client.StructuredResponse(f'{{"searches":{searches!r}}}'.replace("'", '"'))
        plan = await self._plan(response)
        self.assertEqual(len(plan.searches), planner_agent.HOW_MANY_SEARCHES)
        with self.assertRaisesRegex(planner_agent.PlannerStructuredOutputError, "invalid structured output"):
            await self._plan(llm_client.StructuredResponse("not json"))


class SearchTests(unittest.IsolatedAsyncioTestCase):
    def test_tavily_hits_normalize_and_tag_evidence(self):
        hits = [
            SearchHit("Example", "https://example.com/a", "Relevant evidence"),
            SearchHit("Duplicate", "https://example.com/a", "ignored duplicate"),
            SearchHit("Bad", "javascript:bad", "rejected"),
        ]
        sources = search_agent._normalize_hits(hits)
        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0].domain, "example.com")
        summary = search_agent._evidence_summary(hits, sources)
        self.assertIn(f"[{sources[0].id}] Example", summary)
        self.assertIn("Relevant evidence", summary)
        self.assertNotIn("javascript:bad", summary)

    def test_evidence_budget_bounds_each_summary(self):
        hits = [SearchHit("Example", f"https://example.com/{i}", "x" * 100) for i in range(5)]
        sources = search_agent._normalize_hits(hits)
        summary = search_agent._evidence_summary(hits, sources, 120)
        self.assertLessEqual(len(summary), 120)

    def test_missing_provider_credentials_are_sanitized(self):
        settings = config.Settings.from_env()
        missing = config.Settings(**{**settings.__dict__, "llm_provider": "openrouter", "openrouter_api_key": None})
        with self.assertRaises(ProviderConfigurationError) as raised:
            config.require_llm_settings(missing)
        self.assertNotIn("Authorization", str(raised.exception))

    def test_environment_values_override_defaults_without_exposing_secrets(self):
        with patch.dict(
            os.environ,
            {
                "LLM_PROVIDER": "ollama",
                "LLM_MODEL": "deployment-model",
                "SEARCH_MAX_RESULTS": "3",
                "SEARCH_EVIDENCE_MAX_CHARS": "321",
            },
        ):
            settings = config.Settings.from_env()
        self.assertEqual(settings.llm_model, "deployment-model")
        self.assertEqual(settings.search_max_results, 3)
        self.assertEqual(settings.search_evidence_max_chars, 321)

    def test_invalid_evidence_budget_fails_cleanly(self):
        with patch.dict(os.environ, {"SEARCH_EVIDENCE_MAX_CHARS": "0"}):
            with self.assertRaises(config.ConfigurationError):
                config.Settings.from_env()

    def test_dotenv_never_overrides_deployment_environment(self):
        source = Path(config.__file__).read_text()
        self.assertIn("override=False", source)
        self.assertNotIn("override=True", source)

    def test_google_genai_runtime_reference_is_absent(self):
        root = Path(__file__).parent
        google_genai = ".".join(("google", "genai"))
        requirements = (root / "requirements.txt").read_text()
        self.assertNotIn("google-genai", requirements)
        for path in root.glob("*.py"):
            self.assertNotIn(google_genai, path.read_text())

    def test_user_facing_provider_error_is_sanitized(self):
        message = public_error_message(
            ProviderUnavailableError("raw body secret https://user:password@example.com")
        )
        self.assertIn("provider unavailable", message)
        self.assertNotIn("raw body", message)
        self.assertNotIn("password", message)

    async def test_tavily_request_is_basic_and_normalizes_mocked_response(self):
        class FakeResponse:
            status_code = 200

            def json(self):
                return {"results": [{"title": "Example", "url": "https://example.com", "content": "Evidence"}]}

        class FakeClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return None

            async def post(self, url, **kwargs):
                self.url = url
                self.kwargs = kwargs
                return FakeResponse()

        settings = config.Settings.from_env()
        settings = config.Settings(**{**settings.__dict__, "tavily_api_key": "test-key", "search_max_results": 5})
        with patch.object(search_client.httpx, "AsyncClient", return_value=FakeClient()) as client_factory:
            hits = await search_client.TavilySearchClient(settings).search("query")
        request = client_factory.return_value
        self.assertEqual(len(hits), 1)
        self.assertEqual(request.kwargs["json"]["search_depth"], "basic")
        self.assertEqual(request.kwargs["json"]["max_results"], 5)
        self.assertFalse(request.kwargs["json"]["include_answer"])
        self.assertFalse(request.kwargs["json"]["include_raw_content"])


class OrchestrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_searches_are_concurrent_and_failures_are_isolated(self):
        active = 0
        maximum = 0

        async def fake_search(item):
            nonlocal active, maximum
            active += 1
            maximum = max(maximum, active)
            await asyncio.sleep(0)
            active -= 1
            if item.query == "bad":
                raise RuntimeError("mock failure")
            return item.query

        plan = SimpleNamespace(searches=[SimpleNamespace(query=value) for value in ("one", "bad", "two")])
        with patch.object(research_manager, "search_web", fake_search):
            results = await research_manager.ResearchManager().perform_searches(plan)
        self.assertEqual(sorted(results), ["one", "two"])
        self.assertEqual(maximum, 3)

    async def test_email_failure_does_not_discard_report(self):
        manager = research_manager.ResearchManager()
        plan = SimpleNamespace(searches=[])

        async def fake_plan(query):
            return plan

        async def fake_writer(query, results):
            yield "complete report"

        with patch.object(manager, "plan_searches", fake_plan), patch.object(manager, "write_report", fake_writer), patch.object(research_manager, "send_email", side_effect=RuntimeError("mock")), patch.dict(os.environ, {"SEND_RESEARCH_EMAIL": "true"}):
            output = [chunk async for chunk in manager.run("query")]
        self.assertTrue(output[-1].endswith("complete report"))

    async def test_search_failure_logging_is_sanitized(self):
        async def fake_search(item):
            raise ProviderUnavailableError("secret body https://user:password@example.com")

        plan = SimpleNamespace(searches=[SimpleNamespace(query="query")])
        with patch.object(research_manager, "search_web", fake_search), patch.object(
            research_manager, "print"
        ) as printed:
            await research_manager.ResearchManager().perform_searches(plan)
        logged = " ".join(str(call) for call in printed.call_args_list)
        self.assertIn("provider unavailable", logged)
        self.assertNotIn("password", logged)
        self.assertNotIn("secret body", logged)

    async def test_provider_failure_is_not_retried(self):
        attempts = 0

        class FailingClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return None

            async def post(self, *args, **kwargs):
                nonlocal attempts
                attempts += 1
                raise llm_client.httpx.ConnectError("secret body")

        settings = config.Settings.from_env()
        settings = config.Settings(
            **{**settings.__dict__, "llm_provider": "ollama", "ollama_model": "local-test"}
        )
        with patch.object(llm_client.httpx, "AsyncClient", return_value=FailingClient()):
            with self.assertRaises(ProviderUnavailableError):
                await llm_client.LLMClient(settings).generate_text("query")
        self.assertEqual(attempts, 1)


class WriterTests(unittest.IsolatedAsyncioTestCase):
    async def test_writer_streams_chunks_and_preserves_citation_contract(self):
        captured = {}

        class FakeLLM:
            async def stream_text(self, prompt, **kwargs):
                captured["prompt"] = prompt
                yield "first"
                yield "second"

        source = search_agent.ResearchSource("source-1234567890", "Example", "https://example.com", "example.com")
        result = search_agent.SearchResult("query", "[source-1234567890] Example\nEvidence", (source,))
        with patch.object(writer_agent, "get_llm_client", return_value=FakeLLM()):
            chunks = [chunk async for chunk in writer_agent.stream_report("query", [result])]
        self.assertEqual(chunks, ["first", "second"])
        self.assertIn("[source-XXXXXXXXXX]", captured["prompt"])
        self.assertIn("source-1234567890", captured["prompt"])

    async def test_partial_writer_failure_is_not_restarted(self):
        class FailingLLM:
            async def stream_text(self, prompt, **kwargs):
                yield "partial"
                raise WriterStreamError("Writer stream was interrupted")

        with patch.object(writer_agent, "get_llm_client", return_value=FailingLLM()):
            stream = writer_agent.stream_report("query", [])
            self.assertEqual(await anext(stream), "partial")
            with self.assertRaises(WriterStreamError):
                await anext(stream)


class StructuredOutputTests(unittest.IsolatedAsyncioTestCase):
    async def test_openrouter_default_uses_json_object_and_locally_validates(self):
        class FakeResponse:
            status_code = 200

            def json(self):
                return {
                    "choices": [
                        {
                            "message": {
                                "content": '{"searches":[{"reason":"scope","query":"query"}]}'
                            }
                        }
                    ]
                }

        class FakeClient:
            def __init__(self):
                self.kwargs = None

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return None

            async def post(self, url, **kwargs):
                self.kwargs = kwargs
                return FakeResponse()

        settings = config.Settings(
            llm_provider="openrouter",
            llm_model="openrouter/free",
            openrouter_api_key="test-key",
            groq_api_key=None,
            ollama_base_url="http://127.0.0.1:11434",
            ollama_model="llama3.2",
            search_provider="tavily",
            tavily_api_key="test-key",
            search_max_results=5,
        )
        fake_client = FakeClient()
        with patch.object(llm_client.httpx, "AsyncClient", return_value=fake_client):
            response = await llm_client.LLMClient(settings).generate_structured(
                "query", schema=planner_agent.WebSearchPlan
            )
        response_format = fake_client.kwargs["json"]["response_format"]
        self.assertEqual(response_format, {"type": "json_object"})
        self.assertIsInstance(response.parsed, planner_agent.WebSearchPlan)

    async def test_unknown_model_is_rejected_before_http(self):
        class FakeResponse:
            status_code = 200

            def json(self):
                return {"choices": [{"message": {"content": '{"searches": []}'}}]}

        class FakeClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return None

            async def post(self, url, **kwargs):
                self.kwargs = kwargs
                return FakeResponse()

        settings = config.Settings(
            llm_provider="ollama",
            llm_model="local-test",
            openrouter_api_key=None,
            groq_api_key=None,
            ollama_base_url="http://127.0.0.1:11434",
            ollama_model="local-test",
            search_provider="tavily",
            tavily_api_key="test-key",
            search_max_results=5,
        )
        fake_client = FakeClient()
        settings = config.Settings(**{**settings.__dict__, "ollama_model": "unknown"})
        with patch.object(llm_client.httpx, "AsyncClient", return_value=fake_client):
            with self.assertRaises(UnsupportedProviderCapabilityError):
                await llm_client.LLMClient(settings).generate_structured("query", schema=planner_agent.WebSearchPlan)
        self.assertFalse(hasattr(fake_client, "kwargs"))

    async def test_openrouter_default_has_planner_safe_capability(self):
        with patch.dict(os.environ, {}, clear=True):
            settings = config.Settings.from_env()
        self.assertEqual(settings.llm_provider, "openrouter")
        self.assertEqual(settings.llm_model, "openrouter/free")
        client = llm_client.LLMClient.__new__(llm_client.LLMClient)
        client.settings = settings
        self.assertEqual(client._capabilities()["structured"], "json_object")
        self.assertTrue(client._capabilities()["streaming"])


if __name__ == "__main__":
    unittest.main()
