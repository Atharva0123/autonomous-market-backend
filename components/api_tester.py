"""Admin-only API tester service with key-redacted, bounded output."""
from __future__ import annotations

import json
import re
import time
from typing import Any

import httpx

from config import Settings
from schemas.api_models import ToolRequest
from tools.registry import build_tool_registry
from scrapers.news_scraper import fetch_public_news_rss

_SENSITIVE_KEYS = re.compile(r"(^key$|api.?key|access.?key|token|secret|password|authorization|credential)", re.I)


def _redact(value: Any, secrets_to_hide: tuple[str, ...], depth: int = 0) -> Any:
    """Recursively redact common secret fields and configured secret values."""
    if depth > 8:
        return "[maximum nesting omitted]"
    if isinstance(value, dict):
        return {str(key): "[REDACTED]" if _SENSITIVE_KEYS.search(str(key)) else
                _redact(item, secrets_to_hide, depth + 1) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact(item, secrets_to_hide, depth + 1) for item in value[:100]]
    if isinstance(value, str):
        safe = value
        for secret in secrets_to_hide:
            if secret:
                safe = safe.replace(secret, "[REDACTED]")
        return safe[:4000]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)[:500]


async def run_provider_check(settings: Settings, provider: str, query: str,
                             symbol: str | None = None) -> dict[str, Any]:
    """Call exactly one registered provider and return bounded sanitized telemetry."""
    registry = build_tool_registry(settings)
    if provider not in registry:
        raise ValueError("Choose a provider from the registered API list.")
    tool = registry[provider]
    result = await tool.run(ToolRequest(query=query, symbol=symbol))
    protected_values = tuple(str(value) for value in settings.model_dump().values()
                             if isinstance(value, str) and len(value) >= 12)
    clean_data = _redact(result.data, protected_values)
    response = {"provider": result.provider, "ok": result.ok, "status_code": result.status_code,
                "elapsed_ms": result.elapsed_ms, "attempts": result.attempts,
                "from_cache": result.from_cache, "rate_limit_remaining": result.rate_limit_remaining,
                "rate_limit_reset_seconds": result.rate_limit_reset_seconds,
                "budget_remaining": result.budget_remaining,
                "error": _redact(result.error, protected_values), "data": clean_data}
    encoded = json.dumps(response, default=str)
    if len(encoded) > 16_000:
        response["data"] = encoded[:15_000] + "… [payload truncated]"
    return response


async def run_scraper_check(settings: Settings, query: str) -> dict[str, Any]:
    """Exercise the bounded public RSS scraper and return source-attributed rows."""
    started = time.perf_counter()
    try:
        stories = await fetch_public_news_rss(query, limit=8)
        return {"provider": "Public News RSS scraper", "ok": True, "status_code": 200,
                "elapsed_ms": (time.perf_counter() - started) * 1000, "attempts": 1,
                "from_cache": False, "rate_limit_remaining": None,
                "data": [story.model_dump(mode="json") for story in stories],
                "count": len(stories), "source": "Google News public RSS"}
    except (httpx.HTTPError, ValueError) as exc:
        message = str(exc)
        protected = tuple(str(value) for value in settings.model_dump().values()
                          if isinstance(value, str) and len(value) >= 12)
        return {"provider": "Public News RSS scraper", "ok": False,
                "status_code": getattr(getattr(exc, "response", None), "status_code", None),
                "elapsed_ms": (time.perf_counter() - started) * 1000, "attempts": 1,
                "from_cache": False, "error": _redact(message, protected), "data": None}
