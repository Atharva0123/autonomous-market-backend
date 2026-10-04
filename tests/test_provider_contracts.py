"""Contract-level tests for verified provider request encodings."""
from schemas.api_models import ToolRequest
from tools.local_regional import RazorpayIFSCTool
from tools.macro_geopolitics import DrillrTool, EconPulseTool, North7Tool
from tools.market_equity import AletheiaTool
from tools.sentiment_news import FXNewsBiasTool, SugraTool, WallstreetBetsTool


def test_aletheia_v2_header_and_symbol(settings):
    settings.aletheia_api_key = "secret"
    url, params, headers, body = AletheiaTool(settings=settings).request_spec(ToolRequest(query="NVDA", symbol="NVDA"))
    assert url.endswith("/StockData") and params["symbol"] == "NVDA"
    assert headers["Accept-Version"] == "2" and headers["key"] == "secret" and body is None


def test_drillr_routes_insider_query(settings):
    settings.drillr_api_key = "secret"
    url, params, headers, _ = DrillrTool(settings=settings).request_spec(
        ToolRequest(query="Show insider trades for NVDA", symbol="NVDA"))
    assert url.endswith("/insider-trades") and params["ticker"] == "NVDA"
    assert headers["X-API-KEY"] == "secret"


def test_econpulse_maps_inflation_and_auth(settings):
    settings.econpulse_api_key = "secret"
    url, _, headers, _ = EconPulseTool(settings=settings).request_spec(ToolRequest(query="CPI inflation"))
    assert url.endswith("/cpi") and headers["Authorization"] == "Bearer secret"


def test_fxnewsbias_auth_and_sugra_documented_routes(settings):
    settings.fxnewsbias_api_key = "fx-secret"
    fx = FXNewsBiasTool(settings=settings).request_spec(ToolRequest(query="FX sentiment"))
    assert fx[0].endswith("/sentiment") and fx[2]["Authorization"] == "Bearer fx-secret"
    settings.sugra_api_key = "sugra-secret"
    sugra = SugraTool(settings=settings).request_spec(ToolRequest(query="US CPI trend"))
    assert sugra[0].endswith("/fred/us/cpi") and sugra[1]["n"] == 6
    assert sugra[2]["x-api-key"] == "sugra-secret"


def test_north7_defaults_to_free_context_and_tradestie_is_public(settings):
    url, _, headers, _ = North7Tool(settings=settings).request_spec(ToolRequest(query="Market outlook"))
    assert url.endswith("/agent-context") and not headers
    url, _, headers, _ = WallstreetBetsTool(settings=settings).request_spec(ToolRequest(query="WSB sentiment"))
    assert url == "https://tradestie.com/api/v1/apps/reddit" and not headers


def test_razorpay_ifsc_path(settings):
    url, _, _, _ = RazorpayIFSCTool(settings=settings).request_spec(ToolRequest(query="Validate HDFC0CAGSBK"))
    assert url.endswith("/HDFC0CAGSBK")
