"""Local API contract checks that never call live public data providers."""
import pytest
from urllib.parse import parse_qs, urlparse
import httpx
import respx

def test_catalog_and_health_contracts(authenticated_client):
    client = authenticated_client
    assert client.get("/api/v1/health").json()["status"] == "ok"
    countries = client.get("/api/v1/countries").json()
    assert any(item["iso3"] == "IND" for item in countries)
    assert any(item["iso3"] == "WLD" for item in countries) is False
    search = client.get("/api/v1/catalog/search", params={"q": "NVIDIA"}).json()
    assert any(item["kind"] == "asset" and item["value"] == "NVDA" for item in search)
    source_rows = client.get("/api/v1/sources").json()
    assert len(source_rows) >= 25
    assert any(item["id"] == "gdelt" for item in source_rows)


def test_supported_india_tax_api_returns_rule_sources(authenticated_client):
    client = authenticated_client
    response = client.post("/api/v1/tax/estimate-india", json={
        "asset_type": "listed_equity", "acquisition_date": "2025-01-01",
        "transfer_date": "2025-08-01", "purchase_value_inr": 100000,
        "sale_value_inr": 200000, "stt_eligible": True,
        "tax_year": "FY2025-26",
    })
    assert response.status_code == 200
    payload = response.json()
    assert payload["estimated_tax_before_surcharge_cess_inr"] == 20000
    assert payload["citations"]
    assert all(source["url"].startswith("https://") for source in payload["citations"])


def test_local_auth_bootstrap_and_route_guard(authenticated_client):
    client = authenticated_client
    assert client.get("/api/v1/auth/status").json()["authenticated"] is True
    assert client.get("/api/v1/auth/status").json()["google_enabled"] is False
    assert client.get("/api/v1/auth/google/start").status_code == 503
    assert client.post("/api/v1/auth/setup", json={"username": "other", "password": "another valid password", "setup_token": "test-only-administrator-setup-token"}).status_code == 409
    assert client.get("/api/v1/countries").status_code == 200
    assert client.post("/api/v1/auth/logout").status_code == 200
    assert client.get("/api/v1/countries").status_code == 401
    assert client.post("/api/v1/auth/login", json={"username": "researcher", "password": "correct horse battery"}).status_code == 401
    assert client.post("/api/v1/auth/login", json={"username": "AtharvaKh", "password": "correct horse battery"}).status_code == 200
    assert client.get("/api/v1/countries").status_code == 200


def test_provider_readiness_is_explicit_and_does_not_expose_secrets(authenticated_client):
    payload = authenticated_client.get("/api/v1/data-status").json()
    assert "Marketstack" in payload["providers"]
    assert "World Bank Indicators" in payload["providers"]
    assert "Alpha Vantage" in payload["providers"]
    assert payload["providers"]["Marketstack"]["ready"] is False
    assert payload["alphavantage_key_configured"] is False
    assert "MARKETSTACK_API_KEY" in " ".join(payload["forecast_requirements"])
    assert all("api_key" not in str(row).lower() for row in payload["providers"].values())
    usage = authenticated_client.get("/api/v1/usage").json()
    assert usage["provider"] == "Marketstack"
    assert 0 <= usage["remaining"] <= usage["limit"]


def test_google_oauth_redirect_verifies_state_and_allowlisted_email(authenticated_client, monkeypatch):
    import api.main as api_main
    monkeypatch.setattr(api_main.settings, "google_client_id", "test-client.apps.googleusercontent.com")
    monkeypatch.setattr(api_main.settings, "google_client_secret", "test-secret")
    monkeypatch.setattr(api_main.settings, "google_redirect_uri", "http://localhost:3000/api/v1/auth/google/callback")
    monkeypatch.setattr(api_main.settings, "google_login_success_url", "http://localhost:3000/")
    monkeypatch.setattr(api_main.settings, "google_allowed_email", "owner@example.com")
    with respx.mock(assert_all_called=True) as router:
        router.post("https://oauth2.googleapis.com/token").mock(return_value=httpx.Response(200, json={"access_token": "fake-token"}))
        router.get("https://openidconnect.googleapis.com/v1/userinfo").mock(return_value=httpx.Response(200, json={
            "sub": "google-user-id", "email": "owner@example.com", "email_verified": True,
        }))
        start = authenticated_client.get("/api/v1/auth/google/start", follow_redirects=False)
        assert start.status_code == 302
        oauth = urlparse(start.headers["location"])
        state = parse_qs(oauth.query)["state"][0]
        callback = authenticated_client.get("/api/v1/auth/google/callback", params={"code": "auth-code", "state": state}, follow_redirects=False)
    assert callback.status_code == 303
    assert callback.headers["location"] == "http://localhost:3000/"
    assert authenticated_client.get("/api/v1/auth/status").json()["authenticated"] is True


@pytest.mark.asyncio
async def test_alpha_vantage_free_daily_fallback_normalizes_and_filters(monkeypatch):
    from datetime import date
    import api.main as api_main

    monkeypatch.setattr(api_main.settings, "alphavantage_api_key", "test-key")
    async def fake_json(_url, _params, _cache):
        return ({"Time Series (Daily)": {
            "2026-10-02": {"4. close": "101.25"},
            "2026-09-30": {"4. close": "99.00"},
            "2026-09-01": {"4. close": "80.00"},
        }}, "miss")
    monkeypatch.setattr(api_main.data_service, "_get_json", fake_json)
    rows, error = await api_main._fetch_alphavantage_history("NVDA_TEST", date(2026, 9, 15), date(2026, 10, 4))
    assert error is None
    assert rows == [("2026-09-30", 99.0), ("2026-10-02", 101.25)]
