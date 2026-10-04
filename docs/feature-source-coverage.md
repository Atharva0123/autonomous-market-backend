# Market Intelligence Feature and Source Coverage

This inventory is the product contract for the local, research-only Market Intelligence Desk. A field is shown only when a provider returns it with provenance; unsupported coverage is rendered as unavailable rather than inferred.

## Information an autonomous research agent needs

| Domain | Inputs and outputs | Initial free-source strategy | Cadence / limitation |
|---|---|---|---|
| Country macro | GDP level/growth, inflation, labor, trade, reserves, debt, tax revenue, population | World Bank Indicators API; IMF and ECB SDMX for supplemental series; FRED optional key for US | Mostly monthly, quarterly, or annual; never label macro series as live |
| Government and tax | Tax revenue, current policy/rate references, effective dates, tax news, official release links | World Bank tax-revenue series; official authority links curated per country; GDELT is discovery only | Country tax rules require jurisdiction and tax-year verification; no global tax liability calculation |
| Markets | Country index and sector/index constituents, equity/fund prices, FX, yields, commodities, crypto reference series | Existing free-tier tools where verified; country exchanges/official sources where redisplay terms permit | Record actual provider cadence (real-time, delayed, EOD, or unknown) and terms |
| Company and sector | Sector mapping, earnings, fundamentals, IPO/corporate events, insider/ownership | Existing provider-specific documented adapters; unsupported generic adapters remain marked unverified | Coverage depends on provider and market; preserve source per record |
| News and events | Country/sector headlines, publication time, source link, English sentiment, event tags | GDELT and configured no-cost feeds, filtered by country/topic | Preserve original URL/language; sentiment unavailable for unsupported language |
| Cross-market links | Rolling correlations and cross-asset co-moves; sourced explanatory context | Calculate only from aligned historical observations; cite each explanation | Correlation is descriptive and is not labeled causal |
| Risk and forecasts | Price history, returns, volatility, drawdown, horizons, model and backtest metrics | Historical provider observations; statistical baseline, ARIMA, then ML when eligible | Walk-forward evaluation only; show 95% intervals only when calibrated on held-out residuals |
| Retail / positioning | WSB mentions and provider sentiment, when available | Existing Tradestie/FXNewsBias adapters if configured | Social sentiment is not investor positioning; show sample size and source cadence |

## Product behavior

- Landing page: interactive 3D country globe, searchable/keyboard-accessible country picker, global macro tape, latest sourced trends, and last-updated statuses.
- Country workspace: overview, macro, markets/sectors, news, tax policy, cross-market context, and forecasts; selected-country scope is visible in every panel.
- Universal autocomplete: grouped country, asset, fund, index, sector, commodity, series, and prompt suggestions. Prompt actions include date range, research, and “Make prediction.”
- Simple mode: plain-language summary, traffic-light research bias, risk meter, forecast ranges, and source links. Pro mode: telemetry, raw payloads, model/backtest metrics, and detailed tables.
- Every observation and headline carries source name, URL, observation/publication date, retrieval timestamp, and freshness/entitlement caveat. LLM-authored narrative claims cite one or more returned source records.
- Refresh policy is provider-aware: country macro/news panels refresh every five minutes; identical concurrent requests are coalesced and cached to avoid duplicate provider calls. Last-known public data can be served with a visible stale status if an upstream request fails. Actual provider cadence may be slower and is displayed per source.
- Tax: global policy/news catalog first. India listed-equity and equity-fund estimator is limited to supported tax years and resident individual assumptions; every computed rule links to current official Income Tax Department materials. Unsupported circumstances return “not supported,” not a guessed estimate.
- The app is research-only and has no broker order interface.

## Source readiness notes

The existing twenty-provider registry remains available, but its nine configurable generic JSON entries are not treated as production-ready until endpoint, authentication, schema, freshness, and use terms are verified. New public data sources are added as dedicated adapters with deterministic fixtures. Raw provider text is always treated as untrusted data.
