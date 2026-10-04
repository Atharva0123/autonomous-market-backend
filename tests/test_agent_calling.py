"""Intent routing and agent fallback tests."""
import pytest
import httpx
import respx
import asyncio
from agent.orchestrator import ResearchAgent
from config import Settings
from agent.synthesizer import Synthesizer
from tools.macro_geopolitics import North7Tool
from schemas.api_models import ToolRequest


def test_reddit_intent_routes_to_wsb():
    agent = ResearchAgent(Settings(_env_file=None, llm_provider="disabled"))
    assert "WallstreetBets" in agent.select_tools("Check Reddit WSB retail sentiment on NVDA")


@pytest.mark.asyncio
async def test_report_is_returned_even_without_configured_providers():
    agent = ResearchAgent(Settings(_env_file=None, llm_provider="disabled"))
    report = await agent.run("What is the outlook for NVDA?")
    assert report.query.startswith("What is")
    assert report.bias == "neutral"
    assert agent.last_memory is not None


def test_macro_and_forex_intents_select_macro_sources():
    agent = ResearchAgent(Settings(_env_file=None, llm_provider="disabled"))
    selected = agent.select_tools("Forex bias and energy CPI outlook")
    assert "EconPulse" in selected
    assert "NORTH7" in selected


def test_growth_and_global_trend_intents_include_event_sources():
    agent = ResearchAgent(Settings(_env_file=None, llm_provider="disabled"))
    selected = agent.select_tools("Global trends and NVDA growth outlook")
    assert "NORTH7" in selected
    assert "Sugra" in selected


def test_north7_selects_risk_and_event_routes():
    tool = North7Tool(settings=Settings(_env_file=None, llm_provider="disabled"))
    risk_url, *_ = tool.request_spec(ToolRequest(query="Current global risk outlook"))
    events_url, *_ = tool.request_spec(ToolRequest(query="Latest global events and trends"))
    assert risk_url.endswith("/risk")
    assert events_url.endswith("/events")


@pytest.mark.asyncio
async def test_empty_query_is_rejected():
    agent = ResearchAgent(Settings(_env_file=None, llm_provider="disabled"))
    with pytest.raises(ValueError, match="cannot be empty"):
        await agent.run("  ")


def test_fxnewsbias_score_uses_documented_0_to_100_scale():
    from agent.synthesizer import _sentiment_values
    assert _sentiment_values({"data": [{"currency": "USD", "score": 75}]}, "FXNewsBias") == [0.5]


@pytest.mark.asyncio
async def test_llm_planner_filters_unknown_tools_and_falls_back(settings):
    settings.llm_provider = "openai"
    settings.openai_api_key = "test-key"
    settings.llm_base_url = "https://planner.test/v1"
    planner = Synthesizer(settings)
    with respx.mock(base_url="https://planner.test") as router:
        router.post("/v1/chat/completions").mock(return_value=httpx.Response(200, json={
            "choices":[{"message":{"content":"{\"tools\":[\"unknown\"],\"reason\":\"bad name\"}"}}]}))
        names, reason = await planner.plan_tools("NVDA", {"OpenFIGI":"mapping"}, ["OpenFIGI"])
    assert names == ["OpenFIGI"]
    assert "deterministic" in reason


@pytest.mark.asyncio
async def test_tool_events_are_emitted_as_each_call_finishes():
    class FakeTool:
        description = "mock"
        client = None
        def __init__(self, name: str, delay: float):
            self.name, self.delay = name, delay
        async def run(self, request):
            await asyncio.sleep(self.delay)
            from schemas.api_models import ToolResult
            return ToolResult(provider=self.name, ok=True, data={})

    agent = ResearchAgent(Settings(_env_file=None, llm_provider="disabled"))
    agent.select_tools = lambda query: ["slow", "fast"]
    agent.tools = {"slow": FakeTool("slow", .04), "fast": FakeTool("fast", .001)}
    events: list[str] = []
    await agent.run("mock query", on_event=events.append)
    assert events.index("fast: success") < events.index("slow: success")
