"""Application configuration loaded from environment variables."""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings. Provider endpoints may be overridden without code changes."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore", env_ignore_empty=True)
    app_name: str = "Autonomous Market Research Agent"
    log_level: str = "INFO"
    request_timeout_seconds: float = Field(default=3.0, gt=0, le=60)
    request_retries: int = Field(default=2, ge=0, le=5)
    retry_backoff_seconds: float = Field(default=0.35, gt=0, le=10)
    max_concurrent_requests: int = Field(default=5, ge=1, le=100)
    response_max_bytes: int = Field(default=2_000_000, ge=1024, le=20_000_000)
    result_cache_ttl_seconds: int = Field(default=90, ge=0, le=86400)
    llm_timeout_seconds: float = Field(default=30, gt=0, le=120)
    llm_max_input_chars: int = Field(default=60_000, ge=1000, le=500_000)
    max_tools_per_query: int = Field(default=12, ge=1, le=12)
    llm_provider: Literal["openai", "anthropic", "ollama", "disabled"] = "disabled"
    llm_model: str = "gpt-4o-mini"
    llm_base_url: str | None = None
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    aletheia_api_key: str | None = None
    drillr_api_key: str | None = None
    econpulse_api_key: str | None = None
    fxnewsbias_api_key: str | None = None
    north7_api_key: str | None = None
    sugra_api_key: str | None = None
    tradestie_api_key: str | None = None
    ollama_base_url: str = "http://localhost:11434"
    marketstack_api_key: str | None = None
    alphavantage_api_key: str | None = None
    openfigi_api_key: str | None = None
    tax_data_api_key: str | None = None
    bank_data_api_key: str | None = None
    marketstack_monthly_budget: int = Field(default=100, ge=0, le=100_000)
    usage_db_path: str = ".state/usage.sqlite3"
    marketstack_base_url: str = "https://api.marketstack.com/v2/eod"
    auth_state_path: str = ".state/auth.json"
    auth_session_secret_path: str = ".state/session_secret"
    admin_username: str = "AtharvaKh"
    auth_setup_token: str | None = None
    auth_password_hash: str | None = None
    auth_password_salt: str | None = None
    auth_password_iterations: int = Field(default=600_000, ge=600_000, le=2_000_000)
    auth_session_secret: str | None = Field(default=None, min_length=32)
    auth_session_max_age_seconds: int = Field(default=28800, ge=300, le=604800)
    auth_cookie_secure: bool = False
    provider_preferences_path: str = ".state/provider_preferences.json"
    provider_preferences_database_url: str | None = None
    google_client_id: str | None = None
    google_client_secret: str | None = None
    google_redirect_uri: str = "http://localhost:3000/api/v1/auth/google/callback"
    google_login_success_url: str = "http://localhost:3000/"
    google_allowed_email: str | None = None
    aletheia_base_url: str = "https://api.aletheiaapi.com"
    bank_data_base_url: str | None = None
    drillr_base_url: str = "https://gateway.drillr.ai/api/v2"
    econpulse_base_url: str = "https://api.econpulse.io/v1"
    fxnewsbias_base_url: str = "https://fxnewsbias.com/api/v1"
    helium_base_url: str | None = None
    intrinio_base_url: str | None = None
    north7_base_url: str = "https://north7.ai/v1"
    segmara_base_url: str | None = None
    portfolio_optimizer_base_url: str | None = None
    razorpay_ifsc_base_url: str = "https://ifsc.razorpay.com"
    stockdata_base_url: str | None = None
    sugra_base_url: str = "https://sugra.ai/api"
    tax_data_base_url: str | None = None
    top5stocks_base_url: str | None = None
    tradestie_base_url: str = "https://tradestie.com/api/v1/apps/reddit"
    xfinlab_base_url: str | None = None
    mfapi_base_url: str = "https://api.mfapi.in/mf"
    openfigi_base_url: str = "https://api.openfigi.com/v3"
    fred_api_key: str | None = None
    api_cors_origins: str = "http://localhost:3000"
    dashboard_cache_ttl_seconds: int = Field(default=300, ge=0, le=86400)
    gdelt_read_timeout_seconds: float = Field(default=12.0, gt=3, le=60)
    gdelt_base_url: str = "https://api.gdeltproject.org/api/v2/doc/doc"
    world_bank_base_url: str = "https://api.worldbank.org/v2"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings instance."""
    return Settings()
