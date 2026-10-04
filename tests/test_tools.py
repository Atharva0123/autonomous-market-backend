"""Registry, schema and deterministic mock response tests."""
import httpx
import pytest
import respx
from schemas.api_models import ToolRequest, ToolResult
from tools.market_equity import OpenFIGITool
from tools.local_regional import MFAPITool
from config import Settings


def test_registry_contains_all_twenty_tools(registry):
    assert len(registry) == 20
    assert len(set(registry)) == 20
    assert "Bank Data" in registry
    assert "Aletheia" in registry


@pytest.mark.asyncio
async def test_mfapi_response_validates(settings):
    tool = MFAPITool(settings=settings)
    with respx.mock(base_url="https://api.mfapi.in") as router:
        router.get("/mf/123").mock(return_value=httpx.Response(200, json={"meta":{"scheme_code":123},"data":[]}))
        tool.endpoint = "https://api.mfapi.in/mf"
        result = await tool.run(ToolRequest(query="NAV", params={"scheme_code":123}))
    assert ToolResult.model_validate(result.model_dump())
    assert result.ok and result.data["meta"]["scheme_code"] == 123


@pytest.mark.asyncio
async def test_mfapi_search_resolves_scheme_then_fetches_nav(settings):
    tool = MFAPITool(settings=settings)
    with respx.mock(base_url="https://api.mfapi.in") as router:
        router.get("/mf/search").mock(
            return_value=httpx.Response(200, json=[{"schemeCode":321,"schemeName":"HDFC Flexicap Fund"}]))
        router.get("/mf/321").mock(return_value=httpx.Response(200, json={"meta":{"scheme_code":321},"data":[{"date":"01-01-2025","nav":"12.0"}]}))
        result = await tool.run(ToolRequest(query="HDFC flexicap mutual fund"))
    assert result.ok
    assert result.data["scheme"]["schemeCode"] == 321
    assert result.data["nav_history"]["meta"]["scheme_code"] == 321


@pytest.mark.asyncio
async def test_openfigi_payload(settings):
    tool = OpenFIGITool(settings=settings)
    with respx.mock(base_url="https://api.openfigi.com") as router:
        route = router.post("/v3/mapping").mock(return_value=httpx.Response(200, json=[{"data":[{"ticker":"NVDA"}]}]))
        result = await tool.run(ToolRequest(query="NVDA", symbol="NVDA"))
    assert result.ok
    assert route.calls[0].request.read()


@pytest.mark.asyncio
async def test_each_configured_registry_adapter_returns_typed_result(settings):
    from tools.registry import build_tool_registry

    registry = build_tool_registry(settings)
    for credential in ("marketstack_api_key", "aletheia_api_key", "drillr_api_key", "econpulse_api_key",
                       "fxnewsbias_api_key", "sugra_api_key"):
        setattr(settings, credential, "test-key")
    settings.bank_data_api_key = settings.tax_data_api_key = "test-key"
    # Each provider URL is set to the same deterministic local response server.
    for tool in registry.values():
        if tool.name == "Marketstack":
            tool.endpoint = "https://mock.test/marketstack"
        elif tool.name == "OpenFIGI":
            tool.endpoint = "https://mock.test/openfigi"
        elif tool.name == "MFAPI":
            tool.endpoint = "https://mock.test/mfapi"
        else:
            tool.endpoint = "https://mock.test/provider"
    with respx.mock(base_url="https://mock.test") as router:
        router.get(re.compile(r"/.*")).mock(return_value=httpx.Response(200, json={"data": []}))
        router.post(re.compile(r"/.*")).mock(return_value=httpx.Response(200, json=[{"data": []}]))
        for tool in registry.values():
            result = await tool.run(ToolRequest(query="test HDFC0CAGSBK", symbol="TEST",
                                                params={"scheme_code": "123", "ifsc": "HDFC0CAGSBK"}))
            assert ToolResult.model_validate(result.model_dump())
            assert result.ok, f"{tool.name} failed: {result.error}"


import re


@pytest.mark.asyncio
async def test_successful_result_is_cached(settings):
    from tools.base import GenericJSONTool
    tool = GenericJSONTool("cache-test", "test", "https://mock.test/cached", settings=settings)
    with respx.mock(base_url="https://mock.test") as router:
        route = router.get("/cached").mock(return_value=httpx.Response(200, json={"value": 4}))
        first = await tool.run(ToolRequest(query="same"))
        second = await tool.run(ToolRequest(query="same"))
    assert first.ok and second.ok
    assert second.from_cache
    assert route.call_count == 1


def test_marketstack_supports_multi_symbol_params(settings):
    from tools.market_equity import MarketstackTool
    tool = MarketstackTool(settings=settings)
    tool.endpoint = "https://example.test/eod"
    _, params, _, _ = tool.request_spec(ToolRequest(query="compare", symbol="NVDA", params={"symbols": "NVDA,AMD"}))
    assert params["symbols"] == "NVDA,AMD"


def test_marketstack_history_uses_range_endpoint(settings):
    from tools.market_equity import MarketstackTool
    tool = MarketstackTool(settings=settings)
    endpoint, params, _, _ = tool.request_spec(ToolRequest(query="NVDA historical price history", symbol="NVDA"))
    assert endpoint.endswith("/eod")
    assert params["date_from"] and params["date_to"]
