"""Failure handling and configured fallback behavior."""
import httpx
import pytest
import respx
from concurrent.futures import ThreadPoolExecutor
from agent.orchestrator import ResearchAgent
from config import Settings
from tools.usage import reserve_request
from schemas.api_models import ToolRequest


@pytest.mark.asyncio
async def test_marketstack_429_falls_back_to_stockdata():
    settings = Settings(_env_file=None, llm_provider="disabled", marketstack_base_url="https://mock.test/price",
                        stockdata_base_url="https://mock.test/news", marketstack_api_key="test-key", request_retries=0,
                        usage_db_path=":memory:")
    agent = ResearchAgent(settings)
    with respx.mock(base_url="https://mock.test") as router:
        router.get("/price").mock(return_value=httpx.Response(429, json={"message":"limited"}))
        router.get("/news").mock(return_value=httpx.Response(200, json={"headline":"sample"}))
        report = await agent.run("NVDA market price outlook")
    assert report.query
    assert any(r.fallback_from == "Marketstack" and r.ok for r in agent.last_memory.results)


@pytest.mark.asyncio
async def test_marketstack_retries_and_redacts_key_from_errors(tmp_path):
    settings = Settings(_env_file=None, llm_provider="disabled", marketstack_base_url="https://mock.test/once",
                        marketstack_api_key="private-key-value", request_retries=1,
                        retry_backoff_seconds=0.01, result_cache_ttl_seconds=0,
                        usage_db_path=str(tmp_path / "budget.sqlite3"))
    from tools.market_equity import MarketstackTool
    from schemas.api_models import ToolRequest
    tool = MarketstackTool(settings=settings)
    with respx.mock(base_url="https://mock.test") as router:
        route = router.get("/once").mock(side_effect=[httpx.Response(429, headers={"Retry-After":"0"}),
                                                        httpx.Response(200, json={"data": []})])
        result = await tool.run(ToolRequest(query="NVDA", symbol="NVDA"))
    assert result.ok and result.attempts == 2 and route.call_count == 2

    with respx.mock(base_url="https://mock.test") as router:
        router.get("/once").mock(return_value=httpx.Response(401, json={"error":"unauthorized"}))
        failed = await tool.run(ToolRequest(query="different query", symbol="NVDA"))
    assert not failed.ok
    assert "private-key-value" not in (failed.error or "")


@pytest.mark.asyncio
async def test_oversized_provider_body_is_rejected_while_streaming(settings):
    from tools.base import GenericJSONTool
    settings.response_max_bytes = 1024
    tool = GenericJSONTool("large", "size-test", "https://large.test/payload", settings=settings)
    with respx.mock(base_url="https://large.test") as router:
        router.get("/payload").mock(return_value=httpx.Response(200, content=b"x" * 2048))
        result = await tool.run(ToolRequest(query="large"))
    assert not result.ok
    assert "exceeded 1024 bytes" in (result.error or "")


def test_persistent_budget_is_atomic_and_enforces_limit(tmp_path):
    database = str(tmp_path / "usage.sqlite3")
    with ThreadPoolExecutor(max_workers=8) as pool:
        reservations = list(pool.map(lambda _: reserve_request(database, "Marketstack", 5), range(12)))
    assert sum(1 for allowed, _ in reservations if allowed) == 5
    assert all(remaining >= 0 for _, remaining in reservations)
