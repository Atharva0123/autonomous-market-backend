"""Concurrent, best-effort data loader for the dashboard's global market pulse."""
from __future__ import annotations

import asyncio

import httpx

from config import Settings, get_settings
from schemas.api_models import ToolRequest, ToolResult
from tools.registry import build_tool_registry


async def load_global_pulse(settings: Settings | None = None) -> list[ToolResult]:
    """Fetch public global events, risk/regime context and retail sentiment.

    Each provider reports its own failure as a typed result so one unavailable feed
    cannot prevent the rest of the dashboard from rendering.
    """
    current = settings or get_settings()
    registry = build_tool_registry(current)
    jobs = [
        ("NORTH7", "Global market context and regime overview"),
        ("NORTH7", "Latest global events and trends"),
        ("NORTH7", "Current global risk outlook"),
        ("WallstreetBets", "Latest Reddit retail sentiment and ticker mentions"),
    ]
    if current.fxnewsbias_api_key:
        jobs.append(("FXNewsBias", "Latest forex sentiment"))
    if current.sugra_api_key:
        jobs.append(("Sugra", "Latest news headlines and sentiment"))

    async with httpx.AsyncClient(timeout=current.request_timeout_seconds) as client:
        for tool in registry.values():
            tool.client = client

        async def invoke(name: str, query: str) -> ToolResult:
            try:
                result = await registry[name].run(ToolRequest(query=query))
                # Repeated NORTH7 calls have distinct intent/routes; preserve each
                # response in UI state even though the provider name is shared.
                result.provider = f"{name} · {query.split()[1].lower()}" if name == "NORTH7" else name
                return result
            except Exception as exc:  # defensive UI boundary
                return ToolResult(provider=name, ok=False, error=f"Dashboard feed failed: {exc}")

        results = await asyncio.gather(*(invoke(name, query) for name, query in jobs))
        for tool in registry.values():
            tool.client = None
    return results
