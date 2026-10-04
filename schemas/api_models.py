"""Normalized Pydantic models shared by provider adapters."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ToolRequest(BaseModel):
    """A provider request with a small, validated parameter bag."""
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=2000)
    symbol: str | None = Field(default=None, max_length=32)
    params: dict[str, Any] = Field(default_factory=dict)


class ToolResult(BaseModel):
    """Provider response normalized for the agent and dashboard."""
    model_config = ConfigDict(extra="allow")
    provider: str
    ok: bool
    data: Any = None
    error: str | None = None
    status_code: int | None = None
    elapsed_ms: float = 0
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    fallback_from: str | None = None
    from_cache: bool = False
    attempts: int = 0
    rate_limit_remaining: int | None = None
    rate_limit_reset_seconds: float | None = None
    budget_remaining: int | None = None


class TelemetryEvent(BaseModel):
    """One observable tool execution event."""
    provider: str
    ok: bool
    duration_ms: float
    status_code: int | None = None
    message: str | None = None


class ToolPlan(BaseModel):
    """Validated tool selection proposed for one bounded research pass."""
    tools: list[str] = Field(default_factory=list, max_length=12)
    reason: str = Field(default="", max_length=1000)
