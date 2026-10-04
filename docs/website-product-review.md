# Market Intelligence Desk — Product Review

Review basis: the current local repository and its data-source catalog. “Working” means an implemented path exists; it does not mean every upstream source is available at every moment or licensed for redistribution. This is a research workspace, not an execution terminal.

## Role-based jobs and expectations

### Normal user

**Primary job:** understand what is happening in a country or with a familiar asset without decoding specialist data tools.

**Must have:** a plain-language global/country summary; a selectable map plus keyboard/search alternative; clear definitions and units; simple date controls; recent headlines with source links and visible publication time; a clear “not available” state; source freshness; an explanation of why a metric matters; saved watchlists and alerts only after notification/data rights are designed.

**Current fit:** Simple/Pro mode, country picker and 3D globe, World Bank macro charts, news sentiment, asset research, source list, and a narrow India estimate. The app explicitly separates historical observations from estimates.

**Gaps / cautions:** it does not yet have a guided onboarding tour, per-country explainers, cross-device saved preferences, personalized alerting, consistent market-price coverage, or verified localized news/sentiment. The global view is an aggregate and should not be interpreted as the “average country.”

### Research analyst

**Primary job:** assemble a reproducible evidence pack and compare the data with known revisions, definitions, and coverage.

**Must have:** source and series identifiers, retrieval timestamp, observation period, revisions and units, exportable tables/reports, configurable date ranges, country/sector comparisons, API telemetry, and transparent methodology. Analyst-grade forecasts need walk-forward backtests against a naïve baseline and reproducible model settings.

**Current fit:** source citations, historical macro observations, date ranges, raw agent telemetry in Pro mode, cross-series correlations, and forecast evaluation fields are present. There is an API source catalog and deterministic provider tests.

**Gaps / cautions:** no report export workflow, no vintage/revision database, no bulk country/sector compare page, no analyst notes or saved research runs, and only a subset of the advertised providers have a concrete adapter. Current annual World Bank indicators are not sufficient for many short-horizon price or event studies. Correlation panels are descriptive and do not prove causality.

### Trader

**Primary job:** rapidly see market conditions, catalysts, liquidity, volatility, event risk, and scenarios with timestamps that match the trading session.

**Must have:** exchange-aware quotes and sessions, delayed/live entitlement labels, corporate-action-adjusted history, volume and liquidity, instrument mapping, economic calendar, rates/FX/commodity cross-asset panels, event alerts, scenario ranges, slippage/liquidity caveats, and auditable source timestamps. A live execution product additionally requires broker controls and extensive risk authorization; this product intentionally has no order path.

**Current fit:** historical price forecast screen, observed volatility/drawdown, basic news, selected macro context, and a strict no-orders boundary.

**Gaps / cautions:** no streaming quote or order book, no verified intraday feed, no corporate-action/total-return normalization, no exchange session calendar, no broker, no portfolio positions, no alert delivery, and no comprehensive event calendar. Free Marketstack access is EOD and its plan limits apply. The predictions are statistical scenarios, not reliably profitable signals; do not use this app as an execution decision system.

## Component-by-component review

| Component | Current state | Main limitation | Recommended next step |
| --- | --- | --- | --- |
| Account and access | First-run local account, PBKDF2 password hash, signed HttpOnly session, API route guard, sign-out | One local account; no recovery, MFA, audit trail, or external identity provider | Keep private/local; use an established OIDC provider before multi-user or public deployment; use HTTPS and secure cookies |
| Global 3D map | Country polygons are clickable and selection updates the country dashboard; search/select is the accessible fallback | Map coloring does not represent a comparable financial value; keyboard polygon navigation is limited | Keep map as country navigation, add explicit selected-country label and table/list navigation; add choropleth only with a defined sourced metric and legend |
| Country selector/search | Local catalog suggestions for countries, sectors, familiar assets, and prompts; date range and prediction intent | Asset/symbol catalog is small and not an instrument master; generic free-text research is provider-limited | Add provider-backed instrument search and result disambiguation by exchange, currency, and asset class |
| Macro panel | World Bank GDP growth, CPI, unemployment, trade, and tax revenue series | Indicator release lags, gaps, revisions and coverage vary; output is not a current nowcast | Add IMF/ECB/FRED/official national statistics with series-level metadata, revision dates, and configurable units |
| Latest news and sentiment | GDELT news lookup, source links, English VADER headline score | News index can throttle; sentiment is lexical and headline-only; language/source selection and syndication affect counts | Add transparent deduplication, article-level source/time, multilingual evaluation, provider-health fallback, and count/confidence calibration |
| Sector context | Sector headline filters and explanatory cross-market chain | No true sector price breadth or constituent universe is currently joined | Add a licensed market/constituent dataset and label index coverage, weighting, and observation time |
| Cross-market relationships | Rolling correlation from aligned historical macro series with evidence count and source links | Small annual samples; correlation is unstable and not evidence of a causal channel | Display sample size and confidence; add higher-frequency official series where possible; keep causal language out |
| Forecast chart | Dated close/NAV observations, naïve/model comparison, walk-forward metrics, empirical range when calibrated | Requires a configured price data API; plan coverage, symbol suffix and history length constrain output | Add provider diagnostics and source setup guidance; cache normalized prices; add adjustment semantics and freshness badges before adding more models |
| Risk summary | Historical annualized volatility and peak-to-trough drawdown | Lookback and data granularity may not match the user's holding period; no liquidity, gap, or portfolio exposure risk | Add scenario/stress panels only when the underlying series and assumptions are disclosed |
| Tax and policy | Tax revenue macro series plus one scoped India listed investment estimator | Tax revenue is not statutory rate; estimate is narrow, one tax year, and excludes multiple personal circumstances | Version the statutory rules, display tax-year validation and official citations; do not broaden scope without jurisdiction-specific validation |
| Data-source inventory | Catalog distinguishes implemented, documented, and unverified adapters | Catalog presence does not imply an active provider contract/key or working live entitlement | Show environment readiness, last successful retrieval, last error, and terms/cadence for each configured feed |
| Pro telemetry | Provider results and selected raw payloads in research mode | Raw payloads can be large/noisy and provider credentials must never be echoed | Add redaction checks, pagination, download controls, and correlation/request IDs |
| Theme and responsive layout | Dark slate/teal dashboard, improved mobile layout, first-run login | Small type and density still favor desktop; map takes considerable first-screen space | Conduct desktop/tablet/mobile user review, increase accessibility contrast, and support reduced motion |

## Data coverage and forecast error

The forecast error “No configured provider returned a dated price history” is expected when no price source key is installed. The Marketstack adapter now uses the historical EOD endpoint and the UI reports the missing key, provider diagnostics, and account setup path. The documented free plan offers EOD, up to 12 months of history, and 100 requests/month; it is not an intraday/live feed. A one-year default forecast window keeps the default request inside that history range, but users can still request an unsupported symbol or date range.

World Bank macro and GDELT headlines are public integrations; they can return partial coverage or be rate-limited. The MFAPI and Razorpay endpoints cover narrow India-specific functions. Several of the other catalog entries are adapters requiring keys, custom endpoints, or provider-contract verification. Do not interpret “20 providers registered” as 20 validated, entitled, functioning data feeds. Before claiming complete country coverage, build provider contract tests and a status matrix per dataset and market.

Forecasts are conditional statistical scenarios based on historical data. Backtest metrics may be weak or unavailable; no model should be described as predictive edge unless it beats a baseline out of sample across enough observations. Intervals are empirical, not guarantees. Macro/news narratives can explain possible channels but must remain distinct from observed values and model outputs.

## Security and deployment boundary

This release implements a **private, local, single-user** account. Passwords are salted and derived using PBKDF2-HMAC-SHA256, the browser receives an HttpOnly signed session cookie, and the API checks the session before serving data endpoints. State and signing key are written under `.state/`, which is ignored by Git. Use HTTPS and set `AUTH_COOKIE_SECURE=true` for an HTTPS deployment. Do not expose this local-account design directly to the public internet or treat it as multi-user access control; use a maintained identity provider, CSRF defenses, secret management, backups, and operational monitoring for that deployment class.

## Suggested delivery order

1. Configure keys for feeds actually needed and test each source against its provider contract, terms, cadence and symbol coverage.
2. Add last-success/last-error freshness and partial-coverage markers to all data panels.
3. Add quote/price provider alternatives with documented entitlement and normalized instrument identifiers.
4. Add analyst exports and country/sector comparisons, then event calendar and opt-in alerts.
5. Reassess identity/security before any multi-user or remote deployment.
