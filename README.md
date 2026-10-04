---
title: Autonomous Market Backend
emoji: 📈
colorFrom: blue
colorTo: green
sdk: gradio
sdk_version: 6.29.1
app_file: app.py
pinned: false
---
# Global Market Intelligence Desk

A local, single-user financial research application. A Next.js dashboard sits in front of a FastAPI service that reuses the Python provider registry. The application does not connect to a broker or place trades.

## Start the application

Requirements: Python 3.11+, Node.js 20+, npm.

In PowerShell, from the repository root:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Start the API in one terminal:

```powershell
python -m uvicorn api.main:app --reload --host 127.0.0.1 --port 8000
```

Start the web app in a second terminal:

```powershell
cd frontend
npm ci
Copy-Item .env.example .env.local
npm run dev
```

Open `http://localhost:3000`. Only the fixed username `AtharvaKh` is accepted. For a local first run, set a private `AUTH_SETUP_TOKEN` in root `.env`; the setup screen requires it before creating the single account. Account state and provider preferences are stored under ignored `.state/`. Passwords are salted PBKDF2 hashes, not encrypted passwords. For hosted deployment, pre-provision the password hash and session secret in the API host's private environment and use PostgreSQL for durable provider settings. See [`docs/deployment-security.md`](docs/deployment-security.md). The prior Streamlit app is retained during migration and remains available with `streamlit run app.py`.

The dashboard uses the public World Bank Indicators API and GDELT news index without keys. The 3D globe uses Natural Earth country boundaries joined to ISO metadata, so clicking a country polygon updates the country dashboard. Country macro and news requests load independently: a GDELT timeout or rate limit no longer prevents the macro charts from rendering. Selecting a sector filters the macro chart to relevant *national* World Bank indicators; these are sector context, not sector returns or causal estimates. English headline sentiment is shown only when indexed English headlines are available.

Asset history tries Marketstack and then an optional Alpha Vantage daily-data fallback. API settings are loaded from the root `.env` file beside `config.py`; `.env.example` is a safe template and is not loaded by the application. Set `MARKETSTACK_API_KEY` or `ALPHAVANTAGE_API_KEY` in root `.env` and restart the API; the Data Sources page lists readiness without exposing credentials. Marketstack free is EOD, up to 12 months and 100 monthly requests; Alpha Vantage free daily data is compact to the latest 100 observations. Neither is an unrestricted live/intraday feed. Unsupported symbols, exchange suffixes, date ranges or quotas may still yield no history. Optional LLM synthesis can be enabled with `LLM_PROVIDER` and matching provider settings. Missing sources are shown as unavailable.

The authenticated app and administrator API are restricted to `AtharvaKh`. The Data Sources page has administrator-only provider enablement and Marketstack/Alpha Vantage routing controls. Credentials are never editable or returned by these routes; configure each credential in the private environment of the FastAPI host. For HTTPS, set `AUTH_COOKIE_SECURE=true`. See the hosting guidance before publishing.

Optional Google sign-in requires a Google OAuth web client. In Google Cloud Console, add `http://localhost:3000` as an authorized JavaScript origin and `http://localhost:3000/api/v1/auth/google/callback` as the exact redirect URI. Set `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and `GOOGLE_ALLOWED_EMAIL` in the root `.env`, then restart the API. The allowed email restricts this local single-user login to your account. Keep the client secret private.

## Features and scope

- Interactive 3D globe, keyboard-accessible country picker, and hybrid country/asset/sector/prompt search.
- `Ctrl/Cmd+K` command palette, debounced autocomplete, local recent searches, trending prompts, and 7-day / 1-month / YTD / 1-year date presets.
- Obsidian/slate/cobalt/red interface with simple and Pro research views, source freshness, a five-minute indexed-news ticker, and a live API request-budget counter.
- One-minute bounded browser cache for repeat country, source, and catalog lookups; authentication logout clears its research cache and local recent searches.
- Country macro history for GDP level and growth, CPI inflation, unemployment, trade, reserves, tax revenue, and public debt, where reported by the World Bank.
- GDELT-indexed country or sector headlines. English headlines receive a VADER polarity score from -1 to +1; unsupported languages are marked unavailable. This is not a trade signal.
- Headline scores are summarized separately over 7-day and 30-day windows. On news API errors or HTTP 429, the backend honors bounded retries, uses stale cached results where available, then falls back to public RSS.
- Admin-only API and public RSS scraper tester. Outputs are truncated and secret-redacted; live Marketstack checks can consume quota.
- Mobile workspace drawer, compact SVG country map below 640px, stacked panels, and sticky prediction action. The desktop view retains the interactive 3D globe.
- Pairwise correlations on aligned annual country macro series, including observation count and source links. Correlation is descriptive, not evidence of causation.
- Asset history and 7/30/90-calendar-day forecast scenarios, when a configured provider returns dated prices. Walk-forward model selection is evaluated against a random-walk baseline; an unvalidated edge is explicitly reported. Empirical 95% ranges require at least 20 calibration residuals.
- Official country fiscal context. India?Ts FY2025-26 estimate is narrowly scoped to eligible listed equity/equity-oriented fund sales, under the assumptions and rule citations shown in the UI; surcharge, cess, loss set-off, treaty, and filing effects are excluded.
- Simple and Pro views, source/contract catalog, five-minute provider refresh, explicit freshness/cadence, and date-range controls.

The dashboard is not an institutional terminal data license. World Bank releases are not live market quotes, GDELT is a news index, and source contracts, exchange entitlements, geographic coverage, and redistribution rights vary by provider. The implementation catalog and limitations are documented in [`docs/feature-source-coverage.md`](docs/feature-source-coverage.md).

The active UI is Next.js (`frontend/src/app/globals.css` and `frontend/src/components/`); `app.py` remains a legacy Streamlit entrypoint. Backend diagnostics are in `components/api_tester.py`, sentiment utilities in `components/sentiment_gauge.py`, and public RSS parsing/fetching in `scrapers/news_scraper.py`.

See [`docs/website-product-review.md`](docs/website-product-review.md) for a detailed component review and feature priorities for normal users, research analysts, and traders.

## Validate

Run Python tests from the repository root:

```powershell
python -m pytest -q
```

Run frontend checks from `frontend`:

```powershell
npx tsc --noEmit
npm run lint
npm run build
```

Backend tests mock provider HTTP responses and do not consume live API quotas. No model claims predictive skill without beating the naA_ve baseline on later chronological test origins.

## Configuration

See `.env.example` for API credentials, timeout/retry and concurrency bounds, source URLs, caching, and CORS. `frontend/.env.example` contains only the server-side FastAPI origin used by the same-origin proxy. Never commit real credentials.
