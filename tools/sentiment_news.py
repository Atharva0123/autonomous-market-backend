"""News and sentiment tools."""
from __future__ import annotations
from tools.base import ProviderTool, GenericJSONTool
from schemas.api_models import ToolRequest
from typing import Any


class FXNewsBiasTool(ProviderTool):
    """Documented FXNewsBias sentiment feed; free-tier delay is preserved in payload."""
    name, description, credential_setting = "FXNewsBias", "News sentiment scores for eight major currencies.", "fxnewsbias_api_key"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.endpoint = f"{self.settings.fxnewsbias_base_url.rstrip('/')}/sentiment"

    def request_spec(self, request: ToolRequest):
        return self.endpoint or "", {}, {"Authorization": f"Bearer {self.settings.fxnewsbias_api_key or ''}"}, None


class SugraTool(ProviderTool):
    """Sugra data adapter for documented CPI and news endpoints."""
    name, description, credential_setting = "Sugra", "Structured sourced macro, commodities and news feeds.", "sugra_api_key"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.endpoint = self.settings.sugra_base_url.rstrip("/")

    def request_spec(self, request: ToolRequest):
        query = request.query.lower()
        if "cpi" in query or "inflation" in query:
            route = "fred/us/cpi"
            params = {"mode": "last_n", "n": 6}
        elif any(token in query for token in ("news", "headline", "sentiment")):
            route = "api/v1/news/latest"
            params = {}
        else:
            # Unsupported paths are not guessed: callers can set a more specific query.
            route = "api/v1/news/latest"
            params = {}
        return f"{self.endpoint}/{route}", params, {"x-api-key": self.settings.sugra_api_key or ""}, None


class WallstreetBetsTool(ProviderTool):
    """Tradestie public WSB ticker mentions and sentiment feed."""
    name, description = "WallstreetBets", "Top WSB tickers, comment counts and sentiment scores."

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.endpoint = self.settings.tradestie_base_url

    def request_spec(self, request: ToolRequest):
        headers = {"X-Api-Key": self.settings.tradestie_api_key} if self.settings.tradestie_api_key else {}
        return self.endpoint or "", {}, headers, None


def sentiment_tools(settings: Any) -> list[ProviderTool]:
    return [WallstreetBetsTool(settings=settings),
            FXNewsBiasTool(settings=settings),
            GenericJSONTool("Helium", "Media bias and options research.", settings.helium_base_url, settings=settings),
            SugraTool(settings=settings),
            GenericJSONTool("Top5Stocks", "Daily stock and crypto watchlists.", settings.top5stocks_base_url, settings=settings)]
