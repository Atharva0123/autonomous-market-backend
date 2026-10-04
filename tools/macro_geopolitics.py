"""Macro, geopolitical and alternative data tools."""
from __future__ import annotations
from tools.base import ProviderTool, GenericJSONTool
from schemas.api_models import ToolRequest
from typing import Any
from typing import Any


class DrillrTool(ProviderTool):
    """Drillr REST adapter for snapshot, history, insider and fundamentals queries."""
    name, description, credential_setting = "Drillr", "Equity fundamentals, insider filings, prices and ownership data.", "drillr_api_key"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.endpoint = self.settings.drillr_base_url.rstrip("/")

    def request_spec(self, request: ToolRequest) -> tuple[str, dict[str, Any], dict[str, str], Any]:
        query = request.query.lower()
        if any(term in query for term in ("insider", "form 4", "form 3")):
            route = "insider-trades"
        elif any(term in query for term in ("historical price", "price history", "chart", "ohlc")):
            route = "prices-historical"
        elif "price" in query or "quote" in query:
            route = "prices-snapshot"
        elif any(term in query for term in ("earnings", "revenue", "financial statement")):
            route = "income-statement"
        else:
            route = "financial-metrics-snapshot"
        params: dict[str, Any] = {"ticker": request.params.get("tickers") or request.symbol or ""}
        for key in ("from", "to", "interval", "limit", "page", "transaction_type"):
            if key in request.params:
                params[key] = request.params[key]
        headers = {"X-API-KEY": self.settings.drillr_api_key or ""}
        return f"{self.endpoint}/{route}", params, headers, None


class EconPulseTool(ProviderTool):
    """EconPulse macro endpoint selector using its documented API routes."""
    name, description, credential_setting = "EconPulse", "Inflation, treasury, energy, Bitcoin premium and calendar data.", "econpulse_api_key"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.endpoint = self.settings.econpulse_base_url.rstrip("/")

    def request_spec(self, request: ToolRequest) -> tuple[str, dict[str, Any], dict[str, str], Any]:
        query = request.query.lower()
        route = "energy" if any(x in query for x in ("energy", "oil", "wti", "gas")) else \
                "treasury" if any(x in query for x in ("yield", "treasury", "rates")) else \
                "ppi" if "ppi" in query else "cpi" if any(x in query for x in ("cpi", "inflation")) else \
                "btc-premium" if "bitcoin premium" in query else "calendar"
        return f"{self.endpoint}/{route}", {}, {"Authorization": f"Bearer {self.settings.econpulse_api_key or ''}"}, None


class North7Tool(ProviderTool):
    """NORTH7 public agent context; paid signal endpoint is opt-in when keyed."""
    name, description = "NORTH7", "Global market regime, risk, events, intelligence and trading signals."

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.endpoint = self.settings.north7_base_url.rstrip("/")

    def request_spec(self, request: ToolRequest) -> tuple[str, dict[str, Any], dict[str, str], Any]:
        query = request.query.lower()
        if self.settings.north7_api_key and any(x in query for x in ("trading signal", "signals", "alpha")):
            route = "signals/latest"
        elif request.symbol and self.settings.north7_api_key and any(x in query for x in ("analyze", "analysis", "deep dive")):
            route = f"analysis/{request.symbol}"
        elif any(x in query for x in ("event", "trend", "catalyst", "headline")):
            route = "events"
        elif "risk" in query:
            route = "risk"
        elif "regime" in query or "market context" in query:
            route = "regime" if "regime" in query else "agent-context"
        else:
            route = "agent-context"
        headers = {"X-API-Key": self.settings.north7_api_key} if self.settings.north7_api_key else {}
        return f"{self.endpoint}/{route}", {}, headers, None


def macro_tools(settings: Any) -> list[ProviderTool]:
    return [EconPulseTool(settings=settings), North7Tool(settings=settings),
            GenericJSONTool("XFINLAB", "Technical indicators, unusual volume and event detection.", settings.xfinlab_base_url, settings=settings)]
