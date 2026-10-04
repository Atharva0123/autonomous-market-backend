"""Private provider toggles and price-source routing preferences.

This file stores non-secret preferences only. API credentials remain in server
environment variables and are never read into a browser response.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

PROVIDER_NAMES: tuple[str, ...] = (
    "Marketstack", "OpenFIGI", "Aletheia", "Drillr", "MFAPI", "StockData",
    "Segmara", "Intrinio", "WallstreetBets", "FXNewsBias", "Helium", "Sugra",
    "Top5Stocks", "EconPulse", "NORTH7", "XFINLAB", "Bank Data",
    "Razorpay IFSC", "Tax Data", "Portfolio Optimizer",
)


class ProviderSettingsUpdate(BaseModel):
    """Validated admin updates for routing preferences; never accepts API keys."""

    model_config = ConfigDict(extra="forbid")
    price_provider: Literal["auto", "Marketstack", "Alpha Vantage"] = "auto"
    automatic_failover: bool = True
    enabled_providers: dict[str, bool] = Field(default_factory=dict)


def defaults() -> dict[str, Any]:
    """Return safe defaults with all tools opted in and automatic price fallback."""
    return {"price_provider": "auto", "automatic_failover": True,
            "enabled_providers": {name: True for name in PROVIDER_NAMES}}


def load_preferences(path: str, database_url: str | None = None) -> dict[str, Any]:
    """Load preferences, ignoring unknown providers and malformed persisted data."""
    value = defaults()
    try:
        if database_url:
            import psycopg
            with psycopg.connect(database_url, connect_timeout=5) as connection:
                with connection.cursor() as cursor:
                    cursor.execute("CREATE TABLE IF NOT EXISTS marketdesk_settings (setting_key TEXT PRIMARY KEY, setting_value JSONB NOT NULL)")
                    cursor.execute("SELECT setting_value FROM marketdesk_settings WHERE setting_key = 'provider_preferences'")
                    row = cursor.fetchone()
                    raw = row[0] if row else None
        else:
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return value
        if raw.get("price_provider") in {"auto", "Marketstack", "Alpha Vantage"}:
            value["price_provider"] = raw["price_provider"]
        if isinstance(raw.get("automatic_failover"), bool):
            value["automatic_failover"] = raw["automatic_failover"]
        enabled = raw.get("enabled_providers")
        if isinstance(enabled, dict):
            value["enabled_providers"].update({
                name: state for name, state in enabled.items()
                if name in PROVIDER_NAMES and isinstance(state, bool)
            })
    except (OSError, json.JSONDecodeError):
        pass
    return value


def save_preferences(path: str, update: ProviderSettingsUpdate,
                     database_url: str | None = None) -> dict[str, Any]:
    """Atomically persist preferences after validating tool names."""
    unknown = set(update.enabled_providers) - set(PROVIDER_NAMES)
    if unknown:
        raise ValueError(f"Unknown providers: {', '.join(sorted(unknown))}")
    value = load_preferences(path, database_url)
    value["price_provider"] = update.price_provider
    value["automatic_failover"] = update.automatic_failover
    value["enabled_providers"].update(update.enabled_providers)
    if database_url:
        import psycopg
        with psycopg.connect(database_url, connect_timeout=5) as connection:
            with connection.cursor() as cursor:
                cursor.execute("CREATE TABLE IF NOT EXISTS marketdesk_settings (setting_key TEXT PRIMARY KEY, setting_value JSONB NOT NULL)")
                cursor.execute("INSERT INTO marketdesk_settings(setting_key, setting_value) VALUES ('provider_preferences', %s::jsonb) ON CONFLICT (setting_key) DO UPDATE SET setting_value = EXCLUDED.setting_value",
                               (json.dumps(value),))
    else:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(target.suffix + ".tmp")
        temporary.write_text(json.dumps(value, indent=2), encoding="utf-8")
        os.replace(temporary, target)
    return value
