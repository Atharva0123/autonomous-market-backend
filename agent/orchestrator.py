"""Small async ReAct-style planner with tool routing and price fallback."""
from __future__ import annotations
import asyncio
import re
from collections.abc import Callable
import httpx
from config import Settings, get_settings
from schemas.api_models import ToolRequest, ToolResult
from schemas.report_model import ResearchReport
from api.provider_settings import load_preferences
from tools.registry import build_tool_registry
from agent.memory import AgentMemory
from agent.synthesizer import Synthesizer


class ResearchAgent:
    """Route user questions to focused provider tools and synthesize results."""
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.tools = build_tool_registry(self.settings)
        enabled = load_preferences(self.settings.provider_preferences_path,
                                   self.settings.provider_preferences_database_url)["enabled_providers"]
        self.tools = {name: tool for name, tool in self.tools.items() if enabled.get(name, True)}
        self.synthesizer = Synthesizer(self.settings)
        self.last_memory: AgentMemory | None = None

    def select_tools(self, query: str) -> list[str]:
        """Choose providers by intent keywords, falling back to broad market research."""
        q = query.lower(); selected: list[str] = []
        if any(k in q for k in ("reddit", "wsb", "wallstreetbets", "retail sentiment")): selected.append("WallstreetBets")
        if any(k in q for k in ("sentiment", "news", "media", "reddit", "social")): selected += ["FXNewsBias", "StockData", "Helium"]
        if any(k in q for k in ("macro", "cpi", "inflation", "yield", "economy", "geopolit", "forex", "fx ", "commodit", "energy")): selected += ["EconPulse", "NORTH7", "Sugra"]
        if any(k in q for k in ("mutual fund", "nav", "india", "mfapi")): selected.append("MFAPI")
        if any(k in q for k in ("insider", "ownership", "filing", "earnings")): selected += ["Aletheia", "Drillr", "Intrinio"]
        if any(k in q for k in ("ipo", "lockup")): selected.append("Segmara")
        if any(k in q for k in ("portfolio", "sharpe", "allocation", "risk")): selected.append("Portfolio Optimizer")
        if any(k in q for k in ("figi", "isin", "cusip", "identifier")): selected.append("OpenFIGI")
        symbols = re.findall(r"\b[A-Z]{1,5}\b", query)
        if symbols: selected += ["Marketstack", "XFINLAB", "StockData"]
        if any(k in q for k in ("growth outlook", "growth prediction", "risk outlook", "catalyst", "global trend")):
            selected += ["NORTH7", "Sugra", "StockData"]
        selected = list(dict.fromkeys(n for n in selected if n in self.tools))
        if not selected: selected = ["Marketstack", "StockData", "EconPulse"]
        return list(dict.fromkeys(n for n in selected if n in self.tools))[:self.settings.max_tools_per_query]

    async def run(self, query: str, on_event: Callable[[str], None] | None = None) -> ResearchReport:
        """Run selected tools, apply Marketstack->StockData fallback, and return a report."""
        if not query.strip():
            raise ValueError("Research query cannot be empty.")
        if len(query) > 2000:
            raise ValueError("Research query is too long (maximum 2,000 characters).")
        memory = AgentMemory(query=query); self.last_memory = memory
        fallback_plan = self.select_tools(query)
        names, plan_reason = await self.synthesizer.plan_tools(
            query, {name: tool.description for name, tool in self.tools.items()}, fallback_plan)
        memory.decisions.append(f"Plan: {plan_reason} Tools: {', '.join(names)}")
        if on_event:
            on_event(memory.decisions[-1])
        ignored = {"I", "A", "US", "USD", "CPI", "PPI", "ETF", "IPO", "NAV", "IT", "AI", "GDP", "WSB"}
        symbols = [token for token in re.findall(r"\$?\b[A-Z][A-Z0-9.]{0,5}\b", query)
                   if token not in ignored]
        symbol = symbols[0] if symbols else None
        async def invoke(name: str) -> ToolResult:
            params = {}
            if name == "Marketstack" and len(symbols) > 1:
                params["symbols"] = ",".join(symbols[:10])
            if name == "MFAPI":
                code = re.search(r"\b\d{5,7}\b", query)
                if code:
                    params["scheme_code"] = code.group(0)
            if name == "OpenFIGI":
                params["idType"] = "ID_ISIN" if re.search(r"\b[A-Z]{2}[A-Z0-9]{9}\d\b", query) else "TICKER"
            try:
                event = await self.tools[name].run(ToolRequest(query=query, symbol=symbol, params=params))
            except Exception as exc:
                event = ToolResult(provider=name, ok=False, error=str(exc))
            memory.record(event)
            if on_event:
                on_event(f"{event.provider}: {'success' if event.ok else event.error}")
            return event
        client = httpx.AsyncClient(timeout=self.settings.request_timeout_seconds)
        for tool in self.tools.values():
            tool.client = client
        try:
            await asyncio.gather(*(invoke(name) for name in names))
            market = next((r for r in memory.results if r.provider == "Marketstack"), None)
            if market is not None and not market.ok and "StockData" in self.tools:
                # Reuse a StockData result already collected for sentiment/news intent.
                fallback = next((r for r in memory.results if r.provider == "StockData"), None)
                if fallback is None:
                    fallback = await invoke("StockData")
                fallback.fallback_from = "Marketstack"
                if on_event:
                    on_event(f"StockData fallback for Marketstack: {'success' if fallback.ok else fallback.error}")
            return await self.synthesizer.synthesize(query, memory.results)
        finally:
            await client.aclose()
            for tool in self.tools.values():
                tool.client = None
