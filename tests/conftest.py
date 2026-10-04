"""Deterministic test fixtures; no live provider calls are made."""
import pytest
from config import Settings
from tools.registry import build_tool_registry


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None, llm_provider="disabled", request_retries=0, usage_db_path=":memory:")


@pytest.fixture
def registry(settings):
    return build_tool_registry(settings)


@pytest.fixture
def authenticated_client(tmp_path, monkeypatch):
    """Use isolated account files so API contracts never touch developer auth state."""
    from fastapi.testclient import TestClient
    import api.main as api_main
    from api.auth import LocalAuthStore

    monkeypatch.setattr(api_main, "auth_store", LocalAuthStore(str(tmp_path / "auth.json"), str(tmp_path / "secret"), username="AtharvaKh"))
    # The API module loads the developer's ignored .env at import time. Make
    # contract tests independent of local credentials and quota entitlements.
    for name in (
        "openai_api_key", "anthropic_api_key", "aletheia_api_key", "drillr_api_key",
        "econpulse_api_key", "fxnewsbias_api_key", "north7_api_key", "sugra_api_key",
        "tradestie_api_key", "marketstack_api_key", "alphavantage_api_key", "openfigi_api_key",
        "tax_data_api_key", "bank_data_api_key", "fred_api_key", "google_client_secret",
    ):
        monkeypatch.setattr(api_main.settings, name, None)
    monkeypatch.setattr(api_main.settings, "auth_setup_token", "test-only-administrator-setup-token")
    with TestClient(api_main.app) as client:
        response = client.post("/api/v1/auth/setup", json={"username": "AtharvaKh", "password": "correct horse battery", "setup_token": "test-only-administrator-setup-token"})
        assert response.status_code == 200
        yield client
