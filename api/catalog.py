"""User-facing source and suggestion catalogs."""
from __future__ import annotations

from api.data_sources import all_countries
from api.models import Suggestion

SECTORS: tuple[tuple[str, str], ...] = (
    ("Technology", "Information technology, semiconductors, software, hardware"),
    ("Financials", "Banks, insurance, capital markets, payments"),
    ("Health Care", "Pharmaceuticals, biotechnology, medical devices"),
    ("Energy", "Oil, gas, utilities, renewables"),
    ("Industrials", "Capital goods, transport, aerospace, manufacturing"),
    ("Consumer Discretionary", "Retail, automotive, travel, durable goods"),
    ("Consumer Staples", "Food, household goods, personal products"),
    ("Materials", "Metals, mining, chemicals, forestry"),
    ("Communication Services", "Telecom, media, entertainment"),
    ("Real Estate", "Property, REITs, construction"),
    ("Utilities", "Electricity, water, gas utilities"),
)
ASSETS: tuple[tuple[str, str, str], ...] = (
    ("NVDA", "NVIDIA", "asset"), ("AAPL", "Apple", "asset"),
    ("MSFT", "Microsoft", "asset"), ("GOOGL", "Alphabet", "asset"),
    ("AMZN", "Amazon", "asset"), ("SPY", "SPDR S&P 500 ETF", "asset"),
    ("BTC-USD", "Bitcoin", "asset"), ("ETH-USD", "Ethereum", "asset"),
    ("GC=F", "Gold futures reference", "commodity"),
    ("CL=F", "Crude oil futures reference", "commodity"),
    ("SI=F", "Silver futures reference", "commodity"),
    ("^GSPC", "S&P 500", "index"), ("^IXIC", "Nasdaq Composite", "index"),
    ("^NSEI", "NIFTY 50", "index"), ("^BSESN", "BSE Sensex", "index"),
)
PROMPTS: tuple[tuple[str, str, str], ...] = (
    ("US Inflation CPI", "Research United States CPI inflation releases, trend and source dates", "macro"),
    ("Oil chokepoints", "Review sourced geopolitical events affecting oil supply chokepoints and energy markets", "macro"),
    ("Federal Reserve rate cut", "Review Federal Reserve rate expectations, official policy sources and market context", "macro"),
    ("India IT mutual funds", "Compare Indian information technology mutual funds and latest available NAV history", "asset"),
    ("Global macro pulse", "Review recent global GDP, inflation, rates, trade and market headlines", "global"),
    ("Country outlook", "Summarize macro releases, market context and sourced risks for {country}", "country"),
    ("Sector news and sentiment", "Find recent {sector} headlines and score English-language sentiment", "sector"),
    ("Asset trend and forecast", "Analyze {asset} price history, sentiment, risk and 7/30/90-day scenarios", "asset"),
    ("Make prediction", "Forecast {asset} from {date_from} to {date_to} using walk-forward validated models", "asset"),
    ("Tax policy update", "Summarize official tax policy and tax news for {country} as of {date_to}", "country"),
)


def suggestions(query: str, limit: int = 15) -> list[Suggestion]:
    """Return ranked, local-first suggestions; free-form research remains supported."""
    needle = query.strip().casefold()
    if not needle:
        return [Suggestion(kind="prompt", label=label, value=template, description="Research prompt", query_template=template)
                for label, template, _ in PROMPTS[:4]]
    matches: list[tuple[int, Suggestion]] = []
    for country in all_countries():
        if needle in country.name.casefold() or needle == country.iso2.casefold() or needle == country.iso3.casefold():
            matches.append((0, Suggestion(kind="country", label=f"{country.flag or ''} {country.name}",
                                         value=country.iso3, description=f"Country · {country.iso2}/{country.iso3}")))
    for value, label, kind in ASSETS:
        if needle in value.casefold() or needle in label.casefold():
            matches.append((1, Suggestion(kind=kind, label=f"{label} ({value})", value=value,
                                         description="Market asset; live/history availability depends on configured sources")))
    for name, description in SECTORS:
        if needle in name.casefold() or needle in description.casefold():
            matches.append((2, Suggestion(kind="sector", label=name, value=name, description=description)))
    for label, template, _ in PROMPTS:
        if needle in label.casefold() or needle in template.casefold():
            matches.append((3, Suggestion(kind="prompt", label=label, value=template,
                                         description="Use as a research prompt", query_template=template)))
    return [item for _, item in sorted(matches, key=lambda row: row[0])[:limit]]


def source_catalog() -> list[dict[str, str]]:
    """Describe integrations and mark contract maturity honestly."""
    sources = [
        {"id": "world-bank", "name": "World Bank Indicators", "domain": "Macro", "status": "implemented",
         "url": "https://datahelpdesk.worldbank.org/knowledgebase/articles/889392", "cadence": "varies by indicator", "key": "No"},
        {"id": "gdelt", "name": "GDELT DOC", "domain": "News", "status": "implemented",
         "url": "https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/amp/", "cadence": "news-index dependent", "key": "No"},
        {"id": "fred", "name": "FRED", "domain": "US macro", "status": "optional-key-not-yet-adapted",
         "url": "https://fred.stlouisfed.org/docs/api/fred/", "cadence": "series-specific", "key": "Free registration key"},
        {"id": "imf", "name": "IMF SDMX", "domain": "Macro", "status": "catalogued-next-adapter",
         "url": "https://data.imf.org/en/Resource-Pages/IMF-API", "cadence": "dataset-specific", "key": "Check dataset"},
        {"id": "ecb", "name": "ECB Data Portal", "domain": "Euro-area / EU macro", "status": "catalogued-next-adapter",
         "url": "https://data.ecb.europa.eu/help/api/overview", "cadence": "dataset-specific", "key": "No"},
        {"id": "un-comtrade", "name": "UN Comtrade", "domain": "Trade", "status": "catalogued-next-adapter",
         "url": "https://uncomtrade.org/docs/subscriptions/", "cadence": "release-specific", "key": "Optional free key with limits"},
        {"id": "marketstack", "name": "Marketstack", "domain": "Equities", "status": "configured-adapter",
         "url": "https://marketstack.com/documentation", "cadence": "plan-specific; EOD default", "key": "Free-tier key"},
        {"id": "alpha-vantage", "name": "Alpha Vantage", "domain": "Equities", "status": "fallback-adapter",
         "url": "https://www.alphavantage.co/documentation/", "cadence": "Daily; free compact response has 100 observations", "key": "Free API key"},
    ]
    providers = [
        ("Aletheia", "Company data", "documented-adapter-limited", "https://aletheiaapi.com/docs/", "Provider-specific", "API key"),
        ("Bank Data", "Banking reference", "configurable-unverified", "https://apilayer.com/marketplace/bank_data-api", "Provider-specific", "API key"),
        ("Drillr", "Equities / fundamentals", "documented-adapter", "https://drillr.ai/docs/api", "Provider-specific", "API key"),
        ("EconPulse", "Macro", "documented-adapter", "https://econpulse.io/docs", "Provider-specific", "API key"),
        ("FXNewsBias", "FX sentiment", "documented-adapter", "https://fxnewsbias.com/developers", "Provider-specific; may be delayed", "API key"),
        ("Helium", "News / options", "configurable-unverified", "https://heliumtrades.com", "Provider-specific", "Provider access"),
        ("MFAPI", "India mutual funds", "documented-adapter", "https://www.mfapi.in/docs/", "NAV release cadence", "No"),
        ("Intrinio", "Equities / fundamentals", "configurable-unverified", "https://intrinio.com/documentation", "Plan-specific", "Account / plan"),
        ("NORTH7", "Signals / geopolitical", "documented-adapter", "https://north7.ai", "Provider-specific", "Optional API key"),
        ("Segmara", "IPO / corporate events", "configurable-unverified", "https://segmara.com", "Provider-specific", "Provider access"),
        ("OpenFIGI", "Security identifiers", "documented-adapter", "https://www.openfigi.com/api/documentation", "Reference data", "Optional API key"),
        ("Portfolio Optimizer", "Portfolio analytics", "configurable-unverified", "https://portfoliooptimizer.io", "Provider-specific", "Provider access"),
        ("Razorpay IFSC", "India banking reference", "documented-adapter", "https://ifsc.razorpay.com", "Reference data", "No"),
        ("StockData", "Equities / news", "configurable-unverified", "https://stockdata.org", "Plan-specific", "Provider access"),
        ("Sugra", "Macro / news", "documented-adapter-limited", "https://sugra.systems", "Provider-specific", "Optional API key"),
        ("Tax Data", "Tax reference", "configurable-unverified", "https://apilayer.com/marketplace/tax_data-api", "Provider-specific", "API key"),
        ("Top5Stocks", "Daily watchlists", "configurable-unverified", "https://top5stocks.netlify.app", "Provider-specific", "Provider access"),
        ("WallstreetBets", "Retail mentions", "documented-adapter", "https://tradestie.com/apps/reddit/api/", "Feed-dependent", "No"),
        ("XFINLAB", "Technical / events", "configurable-unverified", "https://xfinlab.com", "Provider-specific", "Provider access"),
    ]
    sources.extend({"id": name.lower().replace(" ", "-"), "name": name, "domain": domain,
                    "status": status, "url": url, "cadence": cadence, "key": key}
                   for name, domain, status, url, cadence, key in providers)
    return sources
