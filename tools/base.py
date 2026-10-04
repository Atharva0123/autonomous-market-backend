"""Async HTTP tool base with bounded concurrency, retries and telemetry."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import time
from collections import OrderedDict
from abc import ABC, abstractmethod
from typing import Any

import httpx

from config import Settings, get_settings
from schemas.api_models import ToolRequest, ToolResult
from tools.usage import reserve_request

logger = logging.getLogger(__name__)
_CACHE: OrderedDict[str, tuple[float, Any, int | None, dict[str, str]]] = OrderedDict()
_CACHE_LIMIT = 512


def _safe_error(error: Exception, settings: Settings) -> str:
    """Remove credentials from HTTP exception messages before logging or displaying."""
    message = str(error)
    for secret in (settings.marketstack_api_key, settings.alphavantage_api_key,
                   settings.openfigi_api_key, settings.tradestie_api_key,
                   settings.bank_data_api_key, settings.tax_data_api_key,
                   settings.aletheia_api_key, settings.drillr_api_key,
                   settings.econpulse_api_key, settings.fxnewsbias_api_key,
                   settings.north7_api_key, settings.sugra_api_key,
                   settings.openai_api_key, settings.anthropic_api_key,
                   settings.fred_api_key, settings.google_client_secret):
        if secret:
            message = message.replace(secret, "[REDACTED]")
    return re.sub(r"(?i)(access_key|api[_-]?key|token)=([^&\s]+)", r"\1=[REDACTED]", message)


def _retry_delay(response: httpx.Response | None, attempt: int, base: float) -> float:
    """Honor Retry-After when available, otherwise use capped exponential backoff."""
    if response is not None:
        raw = response.headers.get("Retry-After")
        if raw:
            try:
                return min(max(float(raw), 0.0), 30.0)
            except ValueError:
                pass
    return min(base * (2 ** attempt), 8.0)


class ProviderTool(ABC):
    """Base adapter. Subclasses define the provider's documented request shape."""
    name: str
    description: str
    endpoint: str | None = None
    method: str = "GET"
    credential_setting: str | None = None

    def __init__(self, settings: Settings | None = None, client: httpx.AsyncClient | None = None,
                 semaphore: asyncio.Semaphore | None = None) -> None:
        self.settings = settings or get_settings()
        self.client = client
        self.semaphore = semaphore or asyncio.Semaphore(self.settings.max_concurrent_requests)

    @abstractmethod
    def request_spec(self, request: ToolRequest) -> tuple[str, dict[str, Any], dict[str, str], Any]:
        """Return URL, query parameters, headers, and optional JSON body."""

    async def run(self, request: ToolRequest) -> ToolResult:
        """Execute the provider request and return errors as data, never uncaught HTTP errors."""
        started = time.perf_counter()
        if self.endpoint is None:
            return ToolResult(provider=self.name, ok=False,
                              error=f"{self.name} endpoint is not configured. Set its *_BASE_URL environment variable.")
        if self.credential_setting and not getattr(self.settings, self.credential_setting, None):
            return ToolResult(provider=self.name, ok=False,
                              error=f"{self.name} requires {self.credential_setting.upper()} to be configured.")
        url, params, headers, body = self.request_spec(request)
        cache_key = hashlib.sha256(json.dumps([self.name, self.method, url, params, body, headers], sort_keys=True, default=str).encode()).hexdigest()
        cached = _CACHE.get(cache_key)
        now = time.monotonic()
        if cached and cached[0] > now:
            _CACHE.move_to_end(cache_key)
            return ToolResult(provider=self.name, ok=True, data=cached[1], status_code=cached[2],
                              elapsed_ms=(time.perf_counter()-started)*1000, from_cache=True)
        if cached:
            _CACHE.pop(cache_key, None)
        own_client = self.client is None
        client = self.client or httpx.AsyncClient(timeout=self.settings.request_timeout_seconds)
        try:
            async with self.semaphore:
                response: httpx.Response | None = None
                for attempt in range(self.settings.request_retries + 1):
                    try:
                        budget_remaining = None
                        if self.name == "Marketstack":
                            allowed, budget_remaining = await asyncio.to_thread(
                                reserve_request, self.settings.usage_db_path,
                                "Marketstack", self.settings.marketstack_monthly_budget,
                                self.settings.provider_preferences_database_url)
                            if not allowed:
                                return ToolResult(provider=self.name, ok=False,
                                    error=f"Configured Marketstack monthly request budget ({self.settings.marketstack_monthly_budget}) is exhausted.",
                                    elapsed_ms=(time.perf_counter()-started)*1000, attempts=attempt,
                                    budget_remaining=budget_remaining)
                        async with client.stream(self.method, url, params=params, headers=headers, json=body) as streamed:
                            chunks: list[bytes] = []
                            total_bytes = 0
                            async for chunk in streamed.aiter_bytes():
                                total_bytes += len(chunk)
                                if total_bytes > self.settings.response_max_bytes:
                                    raise ValueError(f"{self.name} response exceeded {self.settings.response_max_bytes} bytes")
                                chunks.append(chunk)
                            response = httpx.Response(status_code=streamed.status_code, headers=streamed.headers,
                                                      content=b"".join(chunks), request=streamed.request)
                        if response.status_code == 429 or response.status_code >= 500:
                            if attempt < self.settings.request_retries:
                                await asyncio.sleep(_retry_delay(response, attempt, self.settings.retry_backoff_seconds))
                                continue
                        response.raise_for_status()
                        try:
                            payload: Any = response.json()
                        except ValueError:
                            payload = {"text": response.text[:10000]}
                        remaining = _int_header(response, "ratelimit-remaining", "x-ratelimit-remaining")
                        reset = _float_header(response, "ratelimit-reset", "x-ratelimit-reset")
                        if self.settings.result_cache_ttl_seconds:
                            _CACHE[cache_key] = (time.monotonic() + self.settings.result_cache_ttl_seconds,
                                                 payload, response.status_code, dict(response.headers))
                            _CACHE.move_to_end(cache_key)
                            while len(_CACHE) > _CACHE_LIMIT:
                                _CACHE.popitem(last=False)
                        return ToolResult(provider=self.name, ok=True, data=payload,
                                          status_code=response.status_code,
                                          elapsed_ms=(time.perf_counter()-started)*1000, attempts=attempt + 1,
                                          rate_limit_remaining=remaining, rate_limit_reset_seconds=reset,
                                          budget_remaining=budget_remaining)
                    except (httpx.TransportError, httpx.HTTPStatusError, ValueError) as exc:
                        status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
                        retryable = status == 429 or (status is not None and status >= 500) or isinstance(exc, httpx.TransportError)
                        if retryable and attempt < self.settings.request_retries:
                            await asyncio.sleep(_retry_delay(response, attempt, self.settings.retry_backoff_seconds))
                            continue
                        safe_error = _safe_error(exc, self.settings)
                        logger.warning("Provider %s failed: %s", self.name, safe_error)
                        return ToolResult(provider=self.name, ok=False, error=safe_error, status_code=status,
                                          elapsed_ms=(time.perf_counter()-started)*1000, attempts=attempt + 1,
                                          rate_limit_remaining=_int_header(response, "ratelimit-remaining", "x-ratelimit-remaining") if response else None,
                                          rate_limit_reset_seconds=_float_header(response, "ratelimit-reset", "x-ratelimit-reset") if response else None,
                                          budget_remaining=budget_remaining)
                return ToolResult(provider=self.name, ok=False, error="Request exhausted retries.",
                                  status_code=response.status_code if response else None,
                                  elapsed_ms=(time.perf_counter()-started)*1000)
        finally:
            if own_client:
                await client.aclose()


class GenericJSONTool(ProviderTool):
    """Configurable JSON endpoint adapter for providers without a published contract."""
    def __init__(self, name: str, description: str, endpoint: str | None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.name, self.description, self.endpoint = name, description, endpoint
        self.method = "GET"
        if name == "Bank Data":
            self.credential_setting = "bank_data_api_key"
        elif name == "Tax Data":
            self.credential_setting = "tax_data_api_key"

    def request_spec(self, request: ToolRequest) -> tuple[str, dict[str, Any], dict[str, str], Any]:
        params = {"q": request.query, **request.params}
        headers: dict[str, str] = {}
        if self.name == "Bank Data" and self.settings.bank_data_api_key:
            headers["apikey"] = self.settings.bank_data_api_key
        if self.name == "Tax Data" and self.settings.tax_data_api_key:
            headers["apikey"] = self.settings.tax_data_api_key
        return self.endpoint or "", params, headers, None


def _int_header(response: httpx.Response, *names: str) -> int | None:
    for name in names:
        try:
            if name in response.headers:
                return int(response.headers[name])
        except ValueError:
            return None
    return None


def _float_header(response: httpx.Response, *names: str) -> float | None:
    for name in names:
        try:
            if name in response.headers:
                return float(response.headers[name])
        except ValueError:
            return None
    return None
