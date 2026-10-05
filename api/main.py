"""Async HTTP API used by the Next.js dashboard."""
from __future__ import annotations

import asyncio
import json
import secrets
import hmac
import logging
import os
import re
import time
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from fastapi.responses import RedirectResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from agent.forecasting import forecast_series
from agent.orchestrator import ResearchAgent
from api.catalog import SECTORS, source_catalog, suggestions
from api.auth import LocalAuthStore, validate_credentials
from api.provider_settings import ProviderSettingsUpdate, load_preferences, save_preferences
from api.data_sources import (INDIA_TAX_URL, MACRO_INDICATORS, PublicDataService,
                              WORLD_BANK_CITATION, all_countries, describe_http_error, get_country)
from api.models import (CountryOverview, IndiaTaxEstimateRequest, ResearchRequest,
                        SourceCitation)
from api.tax import estimate_india_gain
from config import get_settings
from components.api_tester import run_provider_check, run_scraper_check
from schemas.api_models import ToolRequest
from schemas.report_model import ResearchReport
from tools.market_equity import MarketstackTool
from tools.usage import request_budget

logger = logging.getLogger(__name__)
settings = get_settings()
if os.getenv("VERCEL") and not (settings.auth_password_hash and settings.auth_password_salt and settings.auth_session_secret):
    raise RuntimeError("Serverless deployment requires AUTH_PASSWORD_HASH, AUTH_PASSWORD_SALT, and AUTH_SESSION_SECRET private environment values.")
if os.getenv("VERCEL") and not settings.auth_cookie_secure:
    raise RuntimeError("AUTH_COOKIE_SECURE=true is required on Vercel so authentication cookies are sent over HTTPS only.")
if os.getenv("VERCEL") and not settings.provider_preferences_database_url:
    raise RuntimeError("Set PROVIDER_PREFERENCES_DATABASE_URL (or DATABASE_URL from the Neon integration) to private PostgreSQL on Vercel so provider settings and monthly API quotas persist across function instances.")
data_service = PublicDataService(settings)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Own one bounded shared HTTP connection pool for the API process."""
    await data_service.start()
    yield
    await data_service.close()


app = FastAPI(title="Market Intelligence Desk API", version="1.0.0", lifespan=lifespan)
auth_store = LocalAuthStore(settings.auth_state_path, settings.auth_session_secret_path,
                            username=settings.admin_username, password_hash=settings.auth_password_hash,
                            password_salt=settings.auth_password_salt,
                            password_iterations=settings.auth_password_iterations)
origins = [origin.strip() for origin in settings.api_cors_origins.split(",") if origin.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST", "PUT"],
                   allow_headers=["Content-Type"], allow_credentials=True)

_login_attempts: dict[str, list[float]] = {}
_setup_attempts: dict[str, list[float]] = {}
_provider_test_attempts: dict[str, list[float]] = {}
_alphavantage_cache: dict[tuple[str, str, str], tuple[float, list[tuple[str, float]]]] = {}
_INDEX_LABELS = {
    "NSEI": "NIFTY 50", "^NSEI": "NIFTY 50", "NIFTY": "NIFTY 50",
    "BSESN": "BSE Sensex", "^BSESN": "BSE Sensex", "SENSEX": "BSE Sensex",
    "GSPC": "S&P 500", "^GSPC": "S&P 500", "IXIC": "Nasdaq Composite", "^IXIC": "Nasdaq Composite",
}


@app.middleware("http")
async def require_local_session(request: Request, call_next):
    """Protect all application data endpoints; health and account bootstrap stay public."""
    public_paths = {"/api/v1/health", "/api/v1/auth/status", "/api/v1/auth/setup", "/api/v1/auth/login",
                    "/api/v1/auth/google/start", "/api/v1/auth/google/callback"}
    if request.url.path.startswith("/api/v1/") and request.url.path not in public_paths:
        if request.session.get("username") != settings.admin_username:
            request.session.clear()
            from starlette.responses import JSONResponse
            return JSONResponse({"detail": "Authentication required. Sign in to continue."}, status_code=401)
        origin = request.headers.get("origin")
        if request.method in {"POST", "PUT", "PATCH", "DELETE"} and origin:
            if origin.rstrip("/") not in origins:
                from starlette.responses import JSONResponse
                return JSONResponse({"detail": "Cross-site state changes are not allowed."}, status_code=403)
    return await call_next(request)


# Session middleware must wrap the authentication guard so request.session is available.
app.add_middleware(SessionMiddleware, secret_key=auth_store.session_secret(settings.auth_session_secret), session_cookie="marketdesk_session",
                   max_age=settings.auth_session_max_age_seconds, same_site="lax", https_only=settings.auth_cookie_secure)


class LoginRequest(BaseModel):
    """Bound unauthenticated login fields before expensive password hashing."""
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=256)


class SetupRequest(LoginRequest):
    """One-time bootstrap request with a bounded high-entropy setup token."""
    setup_token: str = Field(min_length=16, max_length=512)


@app.get("/api/v1/auth/status")
async def auth_status(request: Request) -> dict[str, Any]:
    """Expose only bootstrap state and the current session identity."""
    username = request.session.get("username")
    return {"setup_required": auth_store.account() is None,
            "authenticated": username == settings.admin_username,
            "username": username if username == settings.admin_username else None,
            "is_admin": username == settings.admin_username,
            "google_enabled": bool(settings.google_client_id and settings.google_client_secret and settings.google_allowed_email)}


@app.get("/api/v1/auth/google/start")
async def google_auth_start(request: Request) -> RedirectResponse:
    """Start a restricted Google OpenID Connect login using server-side OAuth."""
    if not (settings.google_client_id and settings.google_client_secret and settings.google_allowed_email):
        raise HTTPException(status_code=503, detail="Google sign-in is not configured. Set the Google OAuth environment values first.")
    state = secrets.token_urlsafe(32)
    request.session["google_oauth_state"] = state
    params = httpx.QueryParams({
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "prompt": "select_account",
    })
    return RedirectResponse(f"https://accounts.google.com/o/oauth2/v2/auth?{params}", status_code=302)


@app.get("/api/v1/auth/google/callback")
async def google_auth_callback(request: Request, code: str = "", state: str = "", error: str = "") -> RedirectResponse:
    """Exchange the code, verify the allow-listed Google email, and set a local session."""
    success_url = settings.google_login_success_url
    if error or not code:
        return RedirectResponse(f"{success_url}?auth_error=google_cancelled", status_code=303)
    expected_state = request.session.pop("google_oauth_state", "")
    if not expected_state or not hmac.compare_digest(str(expected_state), state):
        return RedirectResponse(f"{success_url}?auth_error=google_state", status_code=303)
    if not (settings.google_client_id and settings.google_client_secret and settings.google_allowed_email):
        return RedirectResponse(f"{success_url}?auth_error=google_not_configured", status_code=303)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            token_response = await client.post("https://oauth2.googleapis.com/token", data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": settings.google_redirect_uri,
                "grant_type": "authorization_code",
            })
            token_response.raise_for_status()
            access_token = token_response.json().get("access_token")
            if not access_token:
                raise ValueError("Google did not return an access token")
            profile_response = await client.get("https://openidconnect.googleapis.com/v1/userinfo",
                                                headers={"Authorization": f"Bearer {access_token}"})
            profile_response.raise_for_status()
            profile = profile_response.json()
        email = str(profile.get("email", "")).strip().casefold()
        allowed = settings.google_allowed_email.strip().casefold()
        if email != allowed or profile.get("email_verified") is not True:
            return RedirectResponse(f"{success_url}?auth_error=google_email_not_allowed", status_code=303)
        account = auth_store.account()
        if account is None or account.get("username") != settings.admin_username:
            return RedirectResponse(f"{success_url}?auth_error=google_account_setup", status_code=303)
        request.session.clear()
        request.session["username"] = str(account.get("username", email))
        request.session["google_sub"] = str(profile.get("sub", ""))
        return RedirectResponse(success_url, status_code=303)
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        logger.exception("Google authentication failed during code exchange or profile verification")
        return RedirectResponse(f"{success_url}?auth_error=google_exchange", status_code=303)


@app.post("/api/v1/auth/setup")
async def auth_setup(payload: SetupRequest, request: Request) -> dict[str, str]:
    """Create the one allowed local account, on first run only."""
    if auth_store.account() is not None:
        raise HTTPException(status_code=409, detail="Local account setup has already been completed.")
    now, client = time.monotonic(), request.client.host if request.client else "unknown"
    recent = [when for when in _setup_attempts.get(client, []) if now - when < 900]
    if len(recent) >= 5:
        raise HTTPException(status_code=429, detail="Too many account setup attempts. Wait 15 minutes and retry.")
    supplied_setup_token = payload.setup_token
    if not settings.auth_setup_token or not hmac.compare_digest(supplied_setup_token, settings.auth_setup_token):
        _setup_attempts[client] = [*recent, now]
        raise HTTPException(status_code=403, detail="First-account setup is locked. Configure AUTH_SETUP_TOKEN on the API host.")
    _setup_attempts.pop(client, None)
    username, password = payload.username.strip(), payload.password
    problem = validate_credentials(username, password, settings.admin_username)
    if problem:
        raise HTTPException(status_code=422, detail=problem)
    if not auth_store.create_account(username, password):
        raise HTTPException(status_code=409, detail="Local account setup has already been completed.")
    request.session["username"] = username
    return {"status": "authenticated", "username": username}


@app.post("/api/v1/auth/login")
async def auth_login(payload: LoginRequest, request: Request) -> dict[str, str]:
    """Authenticate the local account and apply a small per-IP failure throttle."""
    now, client = time.monotonic(), request.client.host if request.client else "unknown"
    recent = [when for when in _login_attempts.get(client, []) if now - when < 900]
    if len(recent) >= 8:
        raise HTTPException(status_code=429, detail="Too many sign-in attempts. Wait 15 minutes and retry.")
    username, password = payload.username.strip(), payload.password
    if username != settings.admin_username or not auth_store.verify(username, password):
        _login_attempts[client] = [*recent, now]
        raise HTTPException(status_code=401, detail="Username or password is incorrect.")
    _login_attempts.pop(client, None)
    request.session.clear()
    request.session["username"] = username
    return {"status": "authenticated", "username": username}


@app.post("/api/v1/auth/logout")
async def auth_logout(request: Request) -> dict[str, str]:
    request.session.clear()
    return {"status": "signed_out"}


@app.get("/api/v1/health")
async def health() -> dict[str, str]:
    """Readiness endpoint with no upstream dependency."""
    return {"status": "ok", "service": "market-intelligence-api"}


@app.get("/api/v1/usage")
async def usage() -> dict[str, Any]:
    """Return this instance's locally tracked Marketstack request allowance."""
    budget = await asyncio.to_thread(request_budget, settings.usage_db_path, "Marketstack",
                                     settings.marketstack_monthly_budget,
                                     settings.provider_preferences_database_url)
    return {"provider": "Marketstack", **budget, "key_configured": bool(settings.marketstack_api_key),
            "period": datetime.now(timezone.utc).strftime("%Y-%m"), "entitlement": "end-of-day; plan-specific history"}


@app.get("/api/v1/countries")
async def countries() -> list[dict[str, str | None]]:
    """Return the ISO country catalog used to join globe polygons and search."""
    return [item.model_dump() for item in all_countries()]


@app.get("/api/v1/catalog/search")
async def search_catalog(q: str = Query(default="", max_length=120),
                         limit: int = Query(default=15, ge=1, le=30)) -> list[dict[str, Any]]:
    """Search countries, indexed assets, sectors, commodities and prompts."""
    return [item.model_dump() for item in suggestions(q, limit)]


@app.get("/api/v1/catalog/sectors")
async def sectors() -> list[dict[str, str]]:
    """Return the application's broad non-proprietary sector categories."""
    return [{"name": name, "description": description} for name, description in SECTORS]


@app.get("/api/v1/sources")
async def sources() -> list[dict[str, str]]:
    """Return source coverage and contract status for the UI's provenance drawer."""
    return source_catalog()


def _require_admin(request: Request) -> None:
    """Reject provider-management access unless the allow-listed user is signed in."""
    if request.session.get("username") != settings.admin_username:
        raise HTTPException(status_code=403, detail="Administrator access required.")


@app.get("/api/v1/admin/providers")
async def get_provider_management(request: Request) -> dict[str, Any]:
    """Return secret-free provider status and admin routing controls."""
    _require_admin(request)
    preferences = load_preferences(settings.provider_preferences_path, settings.provider_preferences_database_url)
    status = await data_status()
    serverless = bool(os.getenv("VERCEL"))
    return {**preferences, "admin_username": settings.admin_username,
            "persistence_mode": "postgresql" if settings.provider_preferences_database_url else
                               "ephemeral local file on this serverless host" if serverless else "local file",
            "providers": [{"name": name,
                           "ready": details["ready"],
                           "enabled": preferences["enabled_providers"].get(name, True),
                           "note": details["note"]}
                          for name, details in status["providers"].items()
                          if name in preferences["enabled_providers"]]}


@app.put("/api/v1/admin/providers")
async def update_provider_management(payload: ProviderSettingsUpdate,
                                    request: Request) -> dict[str, Any]:
    """Save provider toggles and failover preference; secret fields are forbidden."""
    _require_admin(request)
    try:
        save_preferences(settings.provider_preferences_path, payload, settings.provider_preferences_database_url)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return await get_provider_management(request)


class ProviderTestRequest(BaseModel):
    """Narrow, administrator-triggered provider connectivity check."""
    model_config = ConfigDict(extra="forbid")
    provider: str = Field(min_length=1, max_length=64)
    query: str = Field(default="Market data connectivity check", min_length=1, max_length=300)
    symbol: str | None = Field(default="NVDA", max_length=32)


@app.post("/api/v1/admin/test-provider")
async def test_provider(payload: ProviderTestRequest, request: Request) -> dict[str, Any]:
    """Run one selected enabled adapter and return only redacted bounded telemetry."""
    _require_admin(request)
    client = request.client.host if request.client else "unknown"
    now = time.monotonic()
    recent = [stamp for stamp in _provider_test_attempts.get(client, []) if now - stamp < 60]
    if len(recent) >= 10:
        raise HTTPException(status_code=429, detail="API tester limit reached: at most 10 provider checks per minute.")
    _provider_test_attempts[client] = [*recent, now]
    if payload.provider == "Public News RSS scraper":
        return await run_scraper_check(settings, payload.query)
    preferences = load_preferences(settings.provider_preferences_path, settings.provider_preferences_database_url)
    if not preferences["enabled_providers"].get(payload.provider, False):
        raise HTTPException(status_code=409, detail="Enable this registered provider in API Management before testing it.")
    try:
        result = await run_provider_check(settings, payload.provider, payload.query, payload.symbol)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return result


@app.get("/api/v1/data-status")
async def data_status() -> dict[str, Any]:
    """Report configured feeds and concrete setup requirements without exposing secrets."""
    configured = {
        "World Bank Indicators": (True, "Public macro history; annual/release cadence varies."),
        "GDELT DOC": (True, "Public news index; can throttle or be temporarily unavailable."),
        "Marketstack": (bool(settings.marketstack_api_key), "Historical equity EOD; requires API key and plan coverage."),
        "Alpha Vantage": (bool(settings.alphavantage_api_key), "Optional daily-price fallback; set free API key. Free response is compact (latest 100 sessions)."),
        "Aletheia": (bool(settings.aletheia_api_key), "Company data; account key required."),
        "Bank Data": (bool(settings.bank_data_base_url and settings.bank_data_api_key), "IBAN/SWIFT adapter requires endpoint and key."),
        "Drillr": (bool(settings.drillr_api_key), "Equity fundamentals and history; account key required."),
        "EconPulse": (bool(settings.econpulse_api_key), "Macro endpoints require account key."),
        "FXNewsBias": (bool(settings.fxnewsbias_api_key), "Forex sentiment endpoint requires account key."),
        "Helium": (bool(settings.helium_base_url), "Custom endpoint required; request contract must be verified."),
        "MFAPI": (True, "Public Indian mutual-fund NAV; scheme coverage varies."),
        "Intrinio": (bool(settings.intrinio_base_url), "Custom endpoint/account plan required."),
        "NORTH7": (True, "Public context endpoint; paid signals need optional key."),
        "Segmara": (bool(settings.segmara_base_url), "Custom provider endpoint required."),
        "OpenFIGI": (True, "Identifier lookup; public quota applies; optional key improves limits."),
        "Portfolio Optimizer": (bool(settings.portfolio_optimizer_base_url), "Custom provider endpoint required."),
        "Razorpay IFSC": (True, "Public India branch reference; IFSC input required."),
        "StockData": (bool(settings.stockdata_base_url), "Custom endpoint and data entitlement required."),
        "Sugra": (bool(settings.sugra_api_key), "Structured feed adapter requires account key."),
        "Tax Data": (bool(settings.tax_data_base_url and settings.tax_data_api_key), "VAT/tax adapter requires endpoint and key."),
        "Top5Stocks": (bool(settings.top5stocks_base_url), "Custom provider endpoint required."),
        "WallstreetBets": (True, "Public ticker-mention snapshot; not a complete Reddit feed."),
        "XFINLAB": (bool(settings.xfinlab_base_url), "Custom endpoint required; contract and entitlement must be verified."),
        "Marketstack request budget": (bool(settings.marketstack_api_key), f"Configured local monthly cap: {settings.marketstack_monthly_budget}."),
    }
    provider_status = {name: {"ready": ready, "note": note} for name, (ready, note) in configured.items()}
    return {"providers": provider_status, "forecast_requirements": [
        "At least one price-history adapter with dated close/NAV observations must be configured.",
        "Marketstack: set MARKETSTACK_API_KEY in the root .env. Alternative daily fallback: set ALPHAVANTAGE_API_KEY. Restart the API after changing credentials.",
        "The symbol must use the provider's exact exchange suffix and instrument identifier.",
        "Free Marketstack access is end-of-day, limited to 100 requests/month and 12 months of history.",
    ], "marketstack_key_configured": bool(settings.marketstack_api_key),
        "alphavantage_key_configured": bool(settings.alphavantage_api_key)}


@app.get("/api/v1/countries/{code}/overview", response_model=CountryOverview)
async def country_overview(code: str,
    start_year: int = Query(default=date.today().year - 10, ge=1960, le=2100),
    end_year: int = Query(default=date.today().year, ge=1960, le=2100),
) -> CountryOverview:
    """Return observed World Bank macro series, with explicit gaps and cadence."""
    if start_year > end_year:
        raise HTTPException(status_code=422, detail="start_year must be less than or equal to end_year")
    if get_country(code) is None:
        raise HTTPException(status_code=404, detail=f"Unknown ISO country code: {code}")
    try:
        return await data_service.country_overview(code, start_year, end_year)
    except (httpx.HTTPError, ValueError) as exc:
        message = describe_http_error(exc)
        logger.warning("Country macro request failed for %s: %s", code, message)
        # Degrade to a typed country page so UI content and search remain usable.
        country = get_country(code)
        assert country is not None
        from api.models import MacroSeries
        return CountryOverview(country=country, range_start=start_year, range_end=end_year,
            macro=[MacroSeries(indicator=indicator, label=label, unit=unit, status="unavailable",
                source=SourceCitation(source_id="world-bank-indicators", name="World Bank Indicators API",
                    url=WORLD_BANK_CITATION, dataset="World Development Indicators", record_id=indicator,
                    cadence="indicator-specific", status="unavailable", usage_note=message[:300]))
            for indicator, label, unit in MACRO_INDICATORS],
            market_coverage="unavailable", limitations=[f"World Bank source unavailable: {message[:300]}"])


@app.get("/api/v1/countries/{code}/tax-policy")
async def country_tax_policy(code: str,
    start_year: int = Query(default=date.today().year - 10, ge=1960, le=2100),
    end_year: int = Query(default=date.today().year, ge=1960, le=2100),
) -> dict[str, Any]:
    """Show observed tax-revenue macro data separately from statutory tax rules."""
    if get_country(code) is None:
        raise HTTPException(status_code=404, detail=f"Unknown ISO country code: {code}")
    try:
        return await data_service.tax_policy(code, start_year, end_year)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Public fiscal source unavailable: {describe_http_error(exc)}") from exc


@app.get("/api/v1/countries/{code}/relationships")
async def country_relationships(code: str,
    start_year: int = Query(default=date.today().year - 10, ge=1960, le=2100),
    end_year: int = Query(default=date.today().year, ge=1960, le=2100),
) -> dict[str, Any]:
    """Return sourced correlations from aligned macro observations, never causality claims."""
    if start_year > end_year:
        raise HTTPException(status_code=422, detail="start_year must be less than or equal to end_year")
    if get_country(code) is None:
        raise HTTPException(status_code=404, detail=f"Unknown ISO country code: {code}")
    try:
        return await data_service.country_relationships(code, start_year, end_year)
    except httpx.HTTPError as exc:
        logger.warning("Country relationship request failed for %s: %s", code, exc)
        raise HTTPException(status_code=502, detail=f"Macro relationship source unavailable: {exc}") from exc


@app.post("/api/v1/tax/estimate-india")
async def india_tax_estimate(request: IndiaTaxEstimateRequest) -> dict[str, Any]:
    """Estimate a narrow India listed-security capital-gains tax component."""
    return estimate_india_gain(request).model_dump(mode="json")


@app.get("/api/v1/countries/{code}/news")
async def country_news(code: str, topic: str | None = Query(default=None, max_length=100),
                       days: int = Query(default=7, ge=1, le=30),
                       limit: int = Query(default=30, ge=1, le=100)) -> dict[str, Any]:
    """Fetch country and sector news with headline sentiment and direct links."""
    country = get_country(code)
    if country is None:
        raise HTTPException(status_code=404, detail=f"Unknown ISO country code: {code}")
    try:
        stories = await data_service.news(country.iso3, country.name, topic, days, limit)
        return {"status": "available", "stories": [story.model_dump(mode="json") for story in stories],
                "source": stories[0].source.dataset if stories else "GDELT DOC 2.0 / Google News RSS",
                "limitations": ["News indexes can differ from publisher release times; English headline sentiment is not an investment signal."]}
    except Exception as exc:
        message = describe_http_error(exc) if isinstance(exc, httpx.HTTPError) else str(exc)
        logger.exception("Country news request failed for %s: %s", code, message)
        return {"status": "unavailable", "stories": [], "source": "GDELT DOC 2.0 / Google News RSS",
                "error": message[:300], "limitations": ["News source unavailable; no headlines have been inferred."]}


@app.post("/api/v1/research")
async def research(request: ResearchRequest) -> dict[str, Any]:
    """Run bounded existing agent research and attach provider source references."""
    _validate_date_range(request)
    query = _dated_query(request)
    agent = ResearchAgent(settings)
    report = await agent.run(query)
    await _attach_public_headline_evidence(report, request.query)
    return {"report": report.model_dump(mode="json"), "citations": _report_citations(report.tool_results)}


@app.post("/api/v1/research/stream")
async def research_stream(request: ResearchRequest) -> StreamingResponse:
    """Stream agent plan/tool progress as server-sent JSON events, then final report."""
    _validate_date_range(request)
    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
    agent = ResearchAgent(settings)

    async def execute() -> None:
        try:
            report = await agent.run(_dated_query(request), on_event=lambda value: queue.put_nowait({"type": "trace", "message": value}))
            await _attach_public_headline_evidence(report, request.query)
            queue.put_nowait({"type": "trace", "message": "GDELT / indexed news: attached dated, source-linked topic headlines when available."})
            queue.put_nowait({"type": "complete", "payload": {"report": report.model_dump(mode="json"),
                                                                   "citations": _report_citations(report.tool_results)}})
        except Exception as exc:
            logger.exception("Streaming research failed")
            queue.put_nowait({"type": "error", "message": str(exc)[:300]})
        finally:
            queue.put_nowait(None)

    async def events():
        task = asyncio.create_task(execute())
        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield f"data: {json.dumps(event, default=str)}\n\n"
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    return StreamingResponse(events(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/v1/forecasts/{symbol}")
async def asset_forecast(symbol: str, date_from: date | None = None,
                         date_to: date | None = None) -> dict[str, Any]:
    """Fetch dated prices in admin-selected provider order, then run backtested scenarios."""
    normalized = symbol.strip().upper()
    if not re.fullmatch(r"[A-Z0-9.^=_-]{1,20}", normalized):
        raise HTTPException(status_code=422, detail="Symbol contains unsupported characters")
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from must be on or before date_to")
    start = date_from or date.today().replace(year=date.today().year - 5)
    end = date_to or date.today()
    preferences = load_preferences(settings.provider_preferences_path, settings.provider_preferences_database_url)
    enabled = preferences["enabled_providers"]
    primary = preferences["price_provider"]
    provider_order = (["Marketstack", "Alpha Vantage"] if primary == "auto"
                      else [primary, "Alpha Vantage" if primary == "Marketstack" else "Marketstack"])
    if not preferences["automatic_failover"]:
        provider_order = provider_order[:1]
    price_rows: list[tuple[str, float]] = []
    price_source: str | None = None
    provider_results: list[dict[str, Any]] = []
    for provider in provider_order:
        if provider == "Marketstack":
            if not enabled.get("Marketstack", True):
                provider_results.append({"provider": provider, "ok": False, "error": "Disabled in API Management."})
                continue
            if not settings.marketstack_api_key:
                provider_results.append({"provider": provider, "ok": False, "error": "API key is not configured in the server environment."})
                continue
            query = f"Get historical price history for {normalized} from {start.isoformat()} to {end.isoformat()}"
            event = await MarketstackTool(settings=settings).run(ToolRequest(query=query, symbol=normalized))
            provider_results.append(event.model_dump(mode="json"))
            price_rows = _extract_price_rows(event.data) if event.ok else []
            if event.ok and not price_rows:
                provider_results[-1]["error"] = "Provider returned no dated close values for this symbol and range."
            if price_rows:
                price_source = provider
                break
        else:
            if not enabled.get("Alpha Vantage", True):
                provider_results.append({"provider": provider, "ok": False, "error": "Disabled in API Management."})
                continue
            if not settings.alphavantage_api_key:
                provider_results.append({"provider": provider, "ok": False, "error": "API key is not configured in the server environment."})
                continue
            index_name = _INDEX_LABELS.get(normalized)
            if index_name:
                alpha_error = (f"Skipped {normalized}: this fallback uses Alpha Vantage TIME_SERIES_DAILY, "
                               "an equity-series endpoint, and did not return index history. The separate "
                               "INDEX_DATA endpoint is not enabled by this adapter.")
            else:
                price_rows, alpha_error = await _fetch_alphavantage_history(normalized, start, end)
            if price_rows:
                price_source = provider
                provider_results.append({"provider": provider, "ok": True, "data_points": len(price_rows)})
                break
            provider_results.append({"provider": provider, "ok": False,
                                     "error": alpha_error or "Provider returned no dated daily observations."})
    if not price_rows:
        provider_rows = [{"provider": item.get("provider"), "error": item.get("error"),
                          "status_code": item.get("status_code")} for item in provider_results if not item.get("ok")]
        index_name = _INDEX_LABELS.get(normalized)
        if not settings.marketstack_api_key and not settings.alphavantage_api_key:
            message = ("Price history is not configured. Add MARKETSTACK_API_KEY to the project .env file, "
                       "or ALPHAVANTAGE_API_KEY as the free daily-price fallback, then restart the API. "
                       "Marketstack free access is end-of-day with 12 months history and 100 monthly requests; "
                       "Alpha Vantage free access returns the latest 100 daily observations. No price provider succeeded.")
        elif index_name:
            marketstack_error = next((str(row["error"]) for row in provider_rows
                                      if row["provider"] == "Marketstack"), None)
            marketstack_status = next((row["status_code"] for row in provider_rows
                                       if row["provider"] == "Marketstack"), None)
            status_note = (f" Marketstack returned HTTP {marketstack_status}; check that the ticker and your plan "
                           "cover index history." if marketstack_status else "")
            message = (f"No dated price history is available for {index_name} ({normalized})."
                       f"{status_note} Alpha Vantage's configured fallback is the daily equity endpoint and "
                       "did not return index observations. StockData and XFINLAB have no endpoint configured, "
                       "so they were unavailable as fallbacks. Use an index-data provider that covers this index "
                       "and plan, or choose a listed security with a supported ticker.")
            if marketstack_error:
                message += f" Provider detail: {marketstack_error[:220]}"
        elif provider_rows:
            detail = "; ".join(f"{row['provider']}: {row['error'] or 'no data'}" for row in provider_rows[:4])
            message = f"Configured price providers returned no dated history. {detail}"
        else:
            message = ("No selected provider returned dated closes. Check the symbol format and provider coverage, "
                       "then retry with a date range inside the provider's history entitlement.")
        return {"symbol": normalized, "status": "unavailable", "observations": 0,
                "error": message, "source_results": provider_results,
                "provider_diagnostics": provider_rows,
                "setup": {"marketstack_key_required": not bool(settings.marketstack_api_key),
                          "env_variable": "MARKETSTACK_API_KEY", "restart_api_after_change": True}}
    price_rows.sort(key=lambda row: row[0])
    bundle = forecast_series(normalized, [price for _, price in price_rows])
    source_urls = {"Marketstack": "https://marketstack.com/documentation",
                   "Alpha Vantage": "https://www.alphavantage.co/documentation/",
                   "StockData": "https://stockdata.org", "MFAPI": "https://www.mfapi.in/docs/"}
    return {"status": "available" if bundle.horizons else "insufficient_history",
            "prices": [{"date": period, "close": price} for period, price in price_rows],
            "price_source": price_source, "price_source_url": source_urls.get(price_source or ""),
            "forecasts": bundle, "source_results": provider_results}


async def _fetch_alphavantage_history(symbol: str, start: date, end: date) -> tuple[list[tuple[str, float]], str | None]:
    """Fetch the free compact daily series as a fallback and cache by symbol/date."""
    if not settings.alphavantage_api_key:
        return [], None
    key = (symbol, start.isoformat(), end.isoformat())
    cached = _alphavantage_cache.get(key)
    if cached and cached[0] > time.monotonic():
        return cached[1], None
    try:
        payload, _ = await data_service._get_json("https://www.alphavantage.co/query", {
            "function": "TIME_SERIES_DAILY", "symbol": symbol, "outputsize": "compact",
            "apikey": settings.alphavantage_api_key,
        }, max(300, settings.dashboard_cache_ttl_seconds))
        if not isinstance(payload, dict):
            return [], "Alpha Vantage returned an unexpected response shape."
        series = payload.get("Time Series (Daily)")
        if not isinstance(series, dict):
            message = payload.get("Note") or payload.get("Information") or payload.get("Error Message")
            return [], f"Alpha Vantage did not return daily observations: {str(message or 'check symbol and API quota')[:180]}"
        rows: list[tuple[str, float]] = []
        for period, values in series.items():
            if not start.isoformat() <= str(period) <= end.isoformat() or not isinstance(values, dict):
                continue
            try:
                close = float(values.get("4. close"))
                if close > 0:
                    rows.append((str(period), close))
            except (TypeError, ValueError):
                continue
        rows.sort(key=lambda row: row[0])
        if rows:
            _alphavantage_cache[key] = (time.monotonic() + 300, rows)
        return rows, None
    except httpx.HTTPError as exc:
        logger.warning("Alpha Vantage historical fallback failed for %s: %s", symbol, describe_http_error(exc))
        return [], f"Alpha Vantage request failed: {describe_http_error(exc)}"


def _validate_date_range(request: ResearchRequest) -> None:
    if request.date_from and request.date_to and request.date_from > request.date_to:
        raise HTTPException(status_code=422, detail="date_from must be on or before date_to")


def _dated_query(request: ResearchRequest) -> str:
    query = request.query.strip()
    if request.date_from or request.date_to:
        query += f" Data date range: {request.date_from or 'earliest available'} to {request.date_to or 'latest available'}."
    if request.make_prediction:
        query += " Include evidence for a prediction and keep it separate from factual observations."
    return query


def _report_citations(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    urls = {
        "Marketstack": "https://marketstack.com/documentation",
        "Aletheia": "https://aletheiaapi.com/docs/",
        "Drillr": "https://drillr.ai/docs/api",
        "EconPulse": "https://econpulse.io/docs",
        "FXNewsBias": "https://fxnewsbias.com/developers",
        "MFAPI": "https://www.mfapi.in/docs/",
        "NORTH7": "https://north7.ai/developers",
        "OpenFIGI": "https://www.openfigi.com/api/documentation",
        "Sugra": "https://sugra.systems/api/build",
        "WallstreetBets": "https://tradestie.com/apps/reddit/api/",
    }
    citations = [{"provider": item.get("provider"), "url": urls.get(item.get("provider"), ""),
             "retrieved_at": item.get("timestamp"), "status": "available" if item.get("ok") else "unavailable",
             "record_id": item.get("provider")}
            for item in results]
    for item in results:
        if item.get("provider") != "GDELT News":
            continue
        for story in item.get("data", []):
            if not isinstance(story, dict) or not story.get("url"):
                continue
            citations.append({"provider": story.get("publisher", "GDELT-indexed publisher"),
                              "url": story["url"], "retrieved_at": story.get("source", {}).get("retrieved_at"),
                              "status": "available", "record_id": story.get("url")})
    return citations


async def _attach_public_headline_evidence(report: ResearchReport, query: str) -> None:
    """Attach public, dated news evidence to topical research without inventing facts."""
    normalized = query.casefold()
    oil_route_terms = ("oil chokepoint", "oil route", "strait", "shipping lane", "shipping route",
                       "hormuz", "suez", "bab el-mandeb", "malacca")
    if any(term in normalized for term in oil_route_terms):
        topic = "(oil OR petroleum OR crude) (chokepoint OR strait OR canal OR shipping OR supply)"
    elif any(term in normalized for term in ("oil", "energy", "commodity", "geopolit", "shipping", "supply chain")):
        topic = query[:180]
    else:
        return
    try:
        stories = await data_service.news("WLD", "World", topic=topic, days=30, limit=12)
    except Exception as exc:
        logger.warning("Public headline enrichment failed for research query: %s", str(exc)[:240])
        report.limitations.append("Topic-specific public headlines could not be fetched for this research run.")
        report.tool_results.append({"provider": "GDELT News", "ok": False, "error": str(exc)[:240]})
        return
    indexed = [story for story in stories if story.url]
    if not indexed:
        report.limitations.append("No matching indexed headlines were returned; no event or impact was inferred.")
        report.tool_results.append({"provider": "GDELT News", "ok": True, "data": [], "count": 0})
        return
    report.key_findings.extend(
        f"Indexed headline ({story.published_at.isoformat() if story.published_at else 'publication time unavailable'}; {story.publisher}): {story.title}"
        for story in indexed[:8]
    )
    report.sources.extend(story.url for story in indexed)
    sentiment_values = [story.sentiment_score for story in indexed if story.sentiment_score is not None]
    if sentiment_values:
        report.sentiment_index = max(-1.0, min(1.0, sum(sentiment_values) / len(sentiment_values)))
    report.data_freshness["GDELT indexed headlines"] = (
        max((story.published_at.isoformat() for story in indexed if story.published_at), default="publication time unavailable")
    )
    report.tool_results.append({
        "provider": "GDELT News", "ok": True,
        "data": [story.model_dump(mode="json") for story in indexed[:12]],
        "count": len(indexed), "topic_query": topic,
    })
    report.limitations.append(
        "Indexed headlines are evidence of reported coverage, not independently verified incidents, causal market effects, or forecasts."
    )


def _extract_price_rows(payload: Any) -> list[tuple[str, float]]:
    """Extract dated close/NAV values from common documented adapter shapes."""
    found: list[tuple[str, float]] = []
    if isinstance(payload, dict):
        rows = payload.get("data")
        if isinstance(rows, list):
            for item in rows:
                if not isinstance(item, dict):
                    continue
                period = item.get("date") or item.get("datetime") or item.get("timestamp")
                raw = item.get("close") or item.get("adj_close") or item.get("price") or item.get("nav")
                try:
                    if period is not None and raw is not None and float(raw) > 0:
                        found.append((str(period)[:10], float(raw)))
                except (TypeError, ValueError):
                    continue
        if not found:
            for value in payload.values():
                found.extend(_extract_price_rows(value))
    elif isinstance(payload, list):
        for item in payload:
            found.extend(_extract_price_rows(item))
    return found
