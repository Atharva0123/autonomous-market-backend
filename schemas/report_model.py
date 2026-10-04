"""Final research report schema."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


class ResearchReport(BaseModel):
    """Structured, source-attributed market research output."""
    query: str
    executive_summary: str
    bias: Literal["bullish", "bearish", "neutral"] = "neutral"
    confidence: float = Field(default=0.0, ge=0, le=1)
    sentiment_index: float = Field(default=0.0, ge=-1, le=1)
    key_findings: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    tool_results: list[dict] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    data_freshness: dict[str, str] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
