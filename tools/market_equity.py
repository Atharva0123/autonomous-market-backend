"""Equity and instrument lookup tool adapters."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
import re
from typing import Any
from tools.base import ProviderTool, GenericJSONTool
from schemas.api_models import ToolRequest


class MarketstackTool(ProviderTool):
    name, description = "Marketstack", "Historical and end-of-day equity prices."
    credential_setting = "marketstack_api_key"
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs); self.endpoint = self.settings.marketstack_base_url or "https://api.marketstack.com/v2/eod"
    def request_spec(self, request: ToolRequest) -> tuple[str, dict[str, Any], dict[str, str], Any]:
        endpoint = self.endpoint or ""
        params: dict[str, Any] = {"access_key": self.settings.marketstack_api_key,
                                  "symbols": request.params.get("symbols") or request.symbol}
        if re.search(r"\b(history|historical|past|trend)\b", request.query, re.IGNORECASE):
            if endpoint.endswith("/eod/latest"):
                endpoint = endpoint[:-len("/latest")]
            dates = re.findall(r"\b\d{4}-\d{2}-\d{2}\b", request.query)
            today = datetime.now(timezone.utc).date()
            params["date_from"] = request.params.get("date_from") or (dates[0] if dates else (today-timedelta(days=90)).isoformat())
            params["date_to"] = request.params.get("date_to") or (dates[1] if len(dates) > 1 else today.isoformat())
        return endpoint, params, {}, None


class OpenFIGITool(ProviderTool):
    name, description, method = "OpenFIGI", "Map a ticker or identifier to FIGI metadata.", "POST"
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs); self.endpoint = f"{self.settings.openfigi_base_url.rstrip('/')}/mapping"
    def request_spec(self, request: ToolRequest) -> tuple[str, dict[str, Any], dict[str, str], Any]:
        headers = {"Content-Type": "application/json"}
        if self.settings.openfigi_api_key: headers["X-OPENFIGI-APIKEY"] = self.settings.openfigi_api_key
        job = {"idType": request.params.get("idType", "TICKER"), "idValue": request.symbol or request.query}
        return self.endpoint or "", {}, headers, [job]


class AletheiaTool(ProviderTool):
    """Aletheia StockData v2 endpoint for quotes and company statistics."""
    name, description = "Aletheia", "Equity quote, company statistics and ownership metrics."
    credential_setting = "aletheia_api_key"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.endpoint = f"{self.settings.aletheia_base_url.rstrip('/')}/StockData"

    def request_spec(self, request: ToolRequest) -> tuple[str, dict[str, Any], dict[str, str], Any]:
        return self.endpoint or "", {"symbol": request.symbol or request.query}, \
               {"key": self.settings.aletheia_api_key or "", "Accept-Version": "2"}, None


def generic_equity_tools(settings: Any) -> list[ProviderTool]:
    """Build configurable adapters for provider endpoints without verified contracts."""
    items = [("StockData", "Market news and sentiment.", settings.stockdata_base_url),
             ("Segmara", "IPO calendars and filing stages.", settings.segmara_base_url),
             ("Intrinio", "Fundamental metrics and equity prices.", settings.intrinio_base_url)]
    return [GenericJSONTool(n,d,e,settings=settings) for n,d,e in items]
