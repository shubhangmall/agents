import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import config
import research_manager
import search_agent
import search_client


async def _chunks(*texts):
    for text in texts:
        yield text


class DepthPresetTests(unittest.TestCase):
    def test_presets_map_to_documented_result_counts(self):
        self.assertEqual(config.search_depth_preset("Quick"), 3)
        self.assertEqual(config.search_depth_preset("Standard"), 5)
        self.assertEqual(config.search_depth_preset("Deep"), 10)

    def test_unknown_preset_is_rejected(self):
        with self.assertRaises(ValueError):
            config.search_depth_preset("Ultra")

    def test_env_default_search_max_results_is_standard(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SEARCH_MAX_RESULTS", None)
            settings = config.Settings.from_env()
        self.assertEqual(settings.search_max_results, 5)

    def test_settings_for_depth_applies_preset_over_env(self):
        with patch.dict(os.environ, {"SEARCH_MAX_RESULTS": "5", "LLM_PROVIDER": "ollama", "LLM_MODEL": "m"}):
            deep = config.settings_for_depth("Deep")
            quick = config.settings_for_depth("Quick")
            standard = config.settings_for_depth("Standard")
        self.assertEqual(deep.search_max_results, 10)
        self.assertEqual(quick.search_max_results, 3)
        self.assertEqual(standard.search_max_results, 5)
        # Everything else still comes from the environment.
        self.assertEqual(deep.llm_provider, "ollama")
        self.assertEqual(deep.llm_model, "m")

    def test_settings_for_depth_does_not_mutate_base_settings(self):
        with patch.dict(os.environ, {"SEARCH_MAX_RESULTS": "5"}):
            base = config.Settings.from_env()
            derived = config.settings_for_depth("Deep")
        self.assertEqual(base.search_max_results, 5)
        self.assertEqual(derived.search_max_results, 10)

    def test_relaxed_range_accepts_deep_value_from_env(self):
        with patch.dict(os.environ, {"SEARCH_MAX_RESULTS": "10"}):
            self.assertEqual(config.Settings.from_env().search_max_results, 10)
        with patch.dict(os.environ, {"SEARCH_MAX_RESULTS": "11"}):
            with self.assertRaises(config.ConfigurationError):
                config.Settings.from_env()


class DepthPlumbingTests(unittest.IsolatedAsyncioTestCase):
    async def test_depth_reaches_tavily_max_results(self):
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
                self.kwargs = kwargs
                return FakeResponse()

        with patch.dict(os.environ, {"SEARCH_MAX_RESULTS": "5"}):
            for depth, expected in (("Quick", 3), ("Standard", 5), ("Deep", 10)):
                settings = config.settings_for_depth(depth)
                settings = config.Settings(**{**settings.__dict__, "tavily_api_key": "test-key"})
                with patch.object(search_client.httpx, "AsyncClient", return_value=FakeClient()) as client_factory:
                    await search_client.TavilySearchClient(settings).search("query")
                self.assertEqual(client_factory.return_value.kwargs["json"]["max_results"], expected)

    async def test_search_web_honors_passed_settings(self):
        with patch.dict(os.environ, {"SEARCH_MAX_RESULTS": "5"}):
            settings = config.settings_for_depth("Deep")
            settings = config.Settings(**{**settings.__dict__, "tavily_api_key": "test-key"})

            async def fake_search(query):
                return []

            with patch.object(search_agent, "get_search_client") as factory:
                factory.return_value.search = fake_search
                await search_agent.search_web(SimpleNamespace(query="q"), settings)
        factory.assert_called_once_with(settings)
        self.assertEqual(factory.call_args[0][0].search_max_results, 10)

    async def _run_manager(self, manager_settings):
        captured = {}

        async def fake_search(item, settings=None):
            captured["settings"] = settings
            return SimpleNamespace(query=item.query, sources=())

        manager = research_manager.ResearchManager()
        plan = SimpleNamespace(searches=[SimpleNamespace(query="q", reason="r")])
        with (
            patch.object(manager, "plan_searches", return_value=plan),
            patch.object(manager, "write_report", return_value=_chunks("report")),
            patch.object(research_manager, "search_web", fake_search),
        ):
            chunks = [chunk async for chunk in manager.run("query", settings=manager_settings)]
        self.assertTrue(chunks[-1].startswith("Research complete!"))
        return captured["settings"]

    async def test_manager_run_defaults_to_env_settings(self):
        with patch.dict(os.environ, {"SEARCH_MAX_RESULTS": "5"}):
            settings = await self._run_manager(None)
        self.assertEqual(settings.search_max_results, 5)

    async def test_manager_run_honors_explicit_settings(self):
        with patch.dict(os.environ, {"SEARCH_MAX_RESULTS": "5"}):
            settings = await self._run_manager(config.settings_for_depth("Quick"))
        self.assertEqual(settings.search_max_results, 3)


if __name__ == "__main__":
    unittest.main()
