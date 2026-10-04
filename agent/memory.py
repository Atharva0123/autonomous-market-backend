"""Per-run execution trace and tool result memory."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from schemas.api_models import ToolResult


@dataclass
class AgentMemory:
    """Keep tool calls, errors, and decisions for display and report attribution."""
    query: str
    results: list[ToolResult] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def record(self, result: ToolResult) -> None:
        self.results.append(result)
        self.decisions.append(f"{result.provider}: {'success' if result.ok else result.error}")
