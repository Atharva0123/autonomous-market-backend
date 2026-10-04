"""Free public macro/news data adapters with normalized provenance and cache."""
from __future__ import annotations

import asyncio
import logging
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit

import httpx
import pycountry
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from api.models import (CountryInfo, CountryOverview, MacroSeries, NewsStory,
                        Observation, SourceCitation)
from config import Settings, get_settings
from scrapers.news_scraper import parse_public_news_rss

MACRO_INDICATORS: tuple[tuple[str, str, str], ...] = (
    ("NY.GDP.MKTP.CD", "GDP", "current US dollars"),
    ("NY.GDP.MKTP.KD.ZG", "GDP growth", "% annual"),
    ("FP.CPI.TOTL.ZG", "Consumer inflation", "% annual"),
    ("SL.UEM.TOTL.ZS", "Unemployment", "% of labor force"),
    ("NE.TRD.GNFS.ZS", "Trade", "% of GDP"),
    ("FI.RES.TOTL.CD", "Foreign reserves", "current US dollars"),
    ("GC.TAX.TOTL.GD.ZS", "Tax revenue", "% of GDP"),
    ("GC.DOD.TOTL.GD.ZS", "Government debt", "% of GDP"),
)
WORLD_BANK_CITATION = "https://datahelpdesk.worldbank.org/knowledgebase/articles/889392"
INDIA_TAX_URL = "https://www.incometaxindia.gov.in/en/sale-of-shares"
_SENTIMENT = SentimentIntensityAnalyzer()
logger = logging.getLogger(__name__)


def describe_http_error(error: httpx.HTTPError) -> str:
    """Format upstream failures consistently, including HTTP status-only exceptions."""
    if isinstance(error, httpx.HTTPStatusError):
        return f"HTTP {error.response.status_code} {error.response.reason_phrase}."
    if isinstance(error, httpx.TimeoutException):
        return "Upstream request timed out."
    return str(error).strip() or f"Upstream transport error ({type(error).__name__})."


def all_countries() -> list[CountryInfo]:
    """Return the locally bundled ISO country catalog without network traffic."""
    rows: list[CountryInfo] = []
    for country in pycountry.countries:
        iso2 = getattr(country, "alpha_2", None)
        iso3 = getattr(country, "alpha_3", None)
        if not iso2 or not iso3:
            continue
        flag = "".join(chr(127397 + ord(char)) for char in iso2)
        rows.append(CountryInfo(iso2=iso2, iso3=iso3, name=country.name, flag=flag))
    return sorted(rows, key=lambda country: country.name)


def get_country(code: str) -> CountryInfo | None:
    """Resolve a two- or three-letter ISO code to a country record."""
    normalized = code.strip().upper()
    if normalized in {"WLD", "001"}:
        return CountryInfo(iso2="001", iso3="WLD", name="World", flag="🌐")
    country = (pycountry.countries.get(alpha_3=normalized) if len(normalized) == 3
               else pycountry.countries.get(alpha_2=normalized))
    if country is None or not hasattr(country, "alpha_3"):
        return None
    return CountryInfo(iso2=country.alpha_2, iso3=country.alpha_3,
                       name=country.name,
                       flag="".join(chr(127397 + ord(char)) for char in country.alpha_2))


def rolling_correlations(periods: list[str], left: list[float], right: list[float],
                         window: int = 5) -> list[dict[str, Any]]:
    """Return fixed-width trailing Pearson correlations over aligned observations."""
    import numpy as np

    if window < 2 or len(periods) != len(left) or len(periods) != len(right):
        return []
    output: list[dict[str, Any]] = []
    for end in range(window - 1, len(periods)):
        start = end - window + 1
        x = np.asarray(left[start:end + 1], dtype=float)
        y = np.asarray(right[start:end + 1], dtype=float)
        coefficient = None
        if float(np.std(x)) > 0 and float(np.std(y)) > 0:
            coefficient = round(float(np.corrcoef(x, y)[0, 1]), 4)
        output.append({"period_start": periods[start], "period_end": periods[end],
                       "coefficient": coefficient})
    return output


class PublicDataService:
    """HTTP data service with bounded concurrency and cadence-aware TTL cache."""

    def __init__(self, settings: Settings | None = None,
                 client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings or get_settings()
        self.client = client
        self._owns_client = client is None
        self._cache: dict[str, tuple[float, Any]] = {}
        self._cache_lock = asyncio.Lock()
        self._request_locks: dict[str, asyncio.Lock] = {}
        self._provider_cooldowns: dict[str, tuple[float, str]] = {}
        self._semaphore = asyncio.Semaphore(self.settings.max_concurrent_requests)

    async def start(self) -> None:
        """Create the shared async connection pool."""
        if self.client is None:
            self.client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.settings.request_timeout_seconds),
                follow_redirects=True,
                headers={"User-Agent": "MarketIntelligenceDesk/1.0 (local research application)"},
            )

    async def close(self) -> None:
        """Close the shared HTTP pool when the FastAPI app shuts down."""
        if self.client is not None and self._owns_client:
            await self.client.aclose()
            self.client = None

    async def _get_json(self, url: str, params: dict[str, Any], cache_seconds: int) -> tuple[Any, str]:
        if self.client is None:
            await self.start()
        assert self.client is not None
        key = f"{url}?{httpx.QueryParams(params)}"
        host = urlsplit(url).netloc
        now = time.monotonic()
        cooldown = self._provider_cooldowns.get(host)
        if cooldown and cooldown[0] > now:
            stale = self._cache.get(key)
            if stale:
                return stale[1], "stale"
            remaining = int(cooldown[0] - now)
            raise httpx.HTTPError(f"{host} upstream cooldown active; retry in about {remaining} seconds. {cooldown[1]}")
        async with self._cache_lock:
            cached = self._cache.get(key)
            if cached and cached[0] > now:
                return cached[1], "fresh"
            request_lock = self._request_locks.setdefault(key, asyncio.Lock())
        # Coalesce concurrent page/API requests that ask for the same source key.
        async with request_lock:
            cooldown = self._provider_cooldowns.get(host)
            if cooldown and cooldown[0] > time.monotonic():
                async with self._cache_lock:
                    stale = self._cache.get(key)
                if stale:
                    return stale[1], "stale"
                remaining = int(cooldown[0] - time.monotonic())
                raise httpx.HTTPError(f"{host} upstream cooldown active; retry in about {remaining} seconds. {cooldown[1]}")
            async with self._cache_lock:
                cached = self._cache.get(key)
                if cached and cached[0] > time.monotonic():
                    return cached[1], "fresh"
            async with self._semaphore:
                try:
                    payload = await self._request_json(url, params)
                except httpx.HTTPError as exc:
                    response = getattr(exc, "response", None)
                    if response is not None and response.status_code == 429:
                        retry_after = response.headers.get("Retry-After")
                        try:
                            cooldown_seconds = min(300.0, max(30.0, float(retry_after))) if retry_after else 60.0
                        except ValueError:
                            cooldown_seconds = 60.0
                        self._provider_cooldowns[host] = (time.monotonic() + cooldown_seconds, describe_http_error(exc))
                    elif isinstance(exc, httpx.TimeoutException):
                        self._provider_cooldowns[host] = (time.monotonic() + 30.0, describe_http_error(exc))
                    elif response is not None and response.status_code >= 500:
                        self._provider_cooldowns[host] = (time.monotonic() + 15.0, describe_http_error(exc))
                    async with self._cache_lock:
                        stale = self._cache.get(key)
                    if stale:
                        logger.warning("Serving stale cached public source data after upstream failure: %s", url)
                        return stale[1], "stale"
                    raise
            if cache_seconds:
                async with self._cache_lock:
                    self._cache[key] = (time.monotonic() + cache_seconds, payload)
            return payload, "miss"

    async def _request_json(self, url: str, params: dict[str, Any]) -> Any:
        """Retry transient public-source failures with bounded exponential backoff."""
        assert self.client is not None
        last_error: Exception | None = None
        for attempt in range(self.settings.request_retries + 1):
            try:
                if urlsplit(url).hostname == "api.gdeltproject.org":
                    # GDELT searches can take longer than the short timeout used
                    # for compact indicator requests; give only this feed more
                    # read time while keeping connection establishment bounded.
                    timeout = httpx.Timeout(
                        self.settings.gdelt_read_timeout_seconds,
                        connect=self.settings.request_timeout_seconds,
                    )
                    response = await self.client.get(url, params=params, timeout=timeout)
                else:
                    response = await self.client.get(url, params=params)
                if (response.status_code == 429 or response.status_code >= 500) and attempt < self.settings.request_retries:
                    retry_after = response.headers.get("Retry-After")
                    try:
                        delay = min(10.0, max(0.0, float(retry_after))) if retry_after else self.settings.retry_backoff_seconds * (2 ** attempt)
                    except ValueError:
                        delay = self.settings.retry_backoff_seconds * (2 ** attempt)
                    logger.info("Transient public source status %s; retry %s/%s after %.2fs",
                                response.status_code, attempt + 1, self.settings.request_retries, delay)
                    await asyncio.sleep(delay)
                    continue
                response.raise_for_status()
                if "xml" in response.headers.get("content-type", "").lower():
                    return response.text
                return response.json()
            except httpx.TransportError as exc:
                last_error = exc
                if attempt >= self.settings.request_retries:
                    raise
                delay = self.settings.retry_backoff_seconds * (2 ** attempt)
                logger.info("Transient public source transport failure; retry %s/%s after %.2fs",
                            attempt + 1, self.settings.request_retries, delay)
                await asyncio.sleep(delay)
        if last_error:
            raise last_error
        raise httpx.HTTPError("Public source request exhausted its retry budget.")

    async def country_overview(self, code: str, start_year: int, end_year: int) -> CountryOverview:
        """Fetch supported World Bank country series concurrently with partial failures."""
        country = get_country(code)
        if country is None:
            raise ValueError(f"Unknown ISO country code: {code}")
        params = {"format": "json", "per_page": 1000,
                  "date": f"{start_year}:{end_year}"}

        async def fetch_indicator(indicator: str) -> tuple[str, list[Observation], str, str | None]:
            url = (f"{self.settings.world_bank_base_url.rstrip('/')}/country/"
                   f"{country.iso3}/indicator/{indicator}")
            try:
                payload, cache_state = await self._get_json(url, params, self.settings.dashboard_cache_ttl_seconds)
            except httpx.HTTPError as exc:
                logger.warning("World Bank indicator %s unavailable for %s: %s", indicator, country.iso3, exc)
                return indicator, [], "miss", describe_http_error(exc)[:240]
            rows = payload[1] if isinstance(payload, list) and len(payload) > 1 and isinstance(payload[1], list) else []
            if isinstance(payload, list) and payload and isinstance(payload[0], dict) and payload[0].get("message"):
                return indicator, [], cache_state, str(payload[0]["message"])[:240]
            observations: list[Observation] = []
            for row in rows:
                if not isinstance(row, dict) or row.get("value") is None:
                    continue
                try:
                    value = float(row["value"])
                except (TypeError, ValueError):
                    continue
                observations.append(Observation(period=str(row.get("date", "")), value=value))
            return indicator, sorted(observations, key=lambda item: item.period), cache_state, None

        fetched = await asyncio.gather(*(fetch_indicator(indicator) for indicator, _, _ in MACRO_INDICATORS))
        by_indicator = {indicator: (observations, cached, error)
                        for indicator, observations, cached, error in fetched}
        retrieved = datetime.now(timezone.utc)
        series = []
        cached_count = 0
        stale_count = 0
        for indicator, label, unit in MACRO_INDICATORS:
            observations, cache_state, error = by_indicator[indicator]
            cached_count += int(cache_state == "fresh")
            stale_count += int(cache_state == "stale")
            source_status = "stale" if cache_state == "stale" else "available" if observations else "unavailable"
            observation_url = (f"{self.settings.world_bank_base_url.rstrip('/')}/country/{country.iso3}/"
                               f"indicator/{indicator}?format=json&date={start_year}%3A{end_year}")
            series.append(MacroSeries(
                indicator=indicator, label=label, unit=unit, observations=observations,
                status="available" if observations else "unavailable",
                source=SourceCitation(source_id="world-bank-indicators", name="World Bank Indicators API",
                    url=observation_url, dataset="World Development Indicators", record_id=indicator,
                    retrieved_at=retrieved,
                    observed_at=observations[-1].period if observations else None,
                    cadence="indicator-specific (annual/quarterly/monthly)",
                    status=source_status,
                    usage_note=error or "Observation availability and revision dates vary by indicator and country."),
            ))
        available_count = sum(item.status == "available" for item in series)
        return CountryOverview(country=country, range_start=start_year, range_end=end_year,
            macro=series, market_coverage="available" if available_count == len(series) else
                "partial" if available_count else "unavailable",
            limitations=[
                "World Bank observations are not live market quotes; indicator release cadence varies.",
                "Country exchange indices, sector returns, policy rates, and statutory tax rates are not inferred when no verified free source is configured.",
                f"{cached_count} of {len(series)} indicator responses served from fresh cache." if cached_count else
                "Fetched from the public World Bank Indicators API.",
                *([f"{stale_count} cached indicator responses are stale because the upstream source failed."] if stale_count else []),
            ])

    async def tax_policy(self, code: str, start_year: int, end_year: int):
        """Return observed tax revenue plus official policy links where catalogued."""
        overview = await self.country_overview(code, start_year, end_year)
        revenue = next(series for series in overview.macro if series.indicator == "GC.TAX.TOTL.GD.ZS")
        official_url = INDIA_TAX_URL if overview.country.iso3 == "IND" else None
        return {
            "country": overview.country,
            "tax_revenue_series": revenue,
            "statutory_rates_status": "partially_catalogued" if official_url else "not_catalogued",
            "official_policy_url": official_url,
            "limitations": [
                "Tax revenue as a share of GDP is an economic indicator, not a tax rate or personal liability estimate.",
                "Country statutory tax tables and tax news are being populated from verified official sources; missing rules are deliberately not estimated.",
            ],
        }

    async def country_relationships(self, code: str, start_year: int, end_year: int) -> dict[str, Any]:
        """Calculate pairwise annual macro correlations using aligned observations."""
        overview = await self.country_overview(code, start_year, end_year)
        by_id = {series.indicator: series for series in overview.macro}
        pairs = (
            ("NY.GDP.MKTP.KD.ZG", "FP.CPI.TOTL.ZG", "GDP growth ↔ inflation"),
            ("NY.GDP.MKTP.KD.ZG", "SL.UEM.TOTL.ZS", "GDP growth ↔ unemployment"),
            ("FP.CPI.TOTL.ZG", "NE.TRD.GNFS.ZS", "Inflation ↔ trade share"),
        )
        correlations = []
        for left_id, right_id, label in pairs:
            left = by_id[left_id]
            right = by_id[right_id]
            left_values = {item.period: item.value for item in left.observations}
            right_values = {item.period: item.value for item in right.observations}
            periods = sorted(left_values.keys() & right_values.keys())
            rolling_points = rolling_correlations(
                periods, [left_values[period] for period in periods],
                [right_values[period] for period in periods], window=5)
            latest = rolling_points[-1] if rolling_points else None
            correlations.append({
                "label": label, "left_indicator": left_id, "right_indicator": right_id,
                "coefficient": latest["coefficient"] if latest else None,
                "evidence_count": len(periods), "rolling_window_years": 5,
                "rolling_points": rolling_points,
                "period_start": latest["period_start"] if latest else None,
                "period_end": latest["period_end"] if latest else None,
                "source_left": left.source.model_dump(mode="json"),
                "source_right": right.source.model_dump(mode="json"),
                "status": "available" if latest and latest["coefficient"] is not None else "insufficient_aligned_history",
            })
        return {
            "country": overview.country.model_dump(mode="json"),
            "correlations": correlations,
            "interpretation": "Five-observation rolling Pearson correlation on aligned annual World Bank series; correlation does not establish causality.",
            "limitations": ["Annual macro values can be revised and may have different release dates.",
                            "At least five aligned annual observations and non-constant series are required for a rolling value."],
        }

    async def news(self, code: str, country_name: str, topic: str | None = None,
                   days: int = 7, limit: int = 30) -> list[NewsStory]:
        """Fetch country/topic stories, falling back to Google News RSS if GDELT fails."""
        query_parts = [country_name]
        if topic:
            query_parts.append(topic)
        else:
            query_parts.append("(economy OR markets OR inflation OR industry OR tax)")
        url = self.settings.gdelt_base_url
        params: dict[str, Any] = {
            "query": " ".join(query_parts), "mode": "artlist", "format": "json",
            "maxrecords": min(max(limit, 1), 100), "sort": "datedesc",
            "timespan": f"{min(max(days, 1), 30)}d",
        }
        try:
            payload, cache_state = await self._get_json(url, params, self.settings.dashboard_cache_ttl_seconds)
        except httpx.HTTPError as exc:
            logger.warning("GDELT news unavailable for %s; trying RSS fallback: %s", code, describe_http_error(exc))
            return await self._news_rss_fallback(code, country_name, topic, days, limit)
        articles = payload.get("articles", []) if isinstance(payload, dict) else []
        if not articles:
            logger.info("GDELT returned no headlines for %s; trying RSS fallback", code)
            return await self._news_rss_fallback(code, country_name, topic, days, limit)
        fetched = datetime.now(timezone.utc)
        stories: list[NewsStory] = []
        for article in articles:
            if not isinstance(article, dict) or not article.get("title") or not article.get("url"):
                continue
            language = str(article.get("language") or "unknown")
            is_english = language.lower() in {"english", "en", "eng"}
            score = float(_SENTIMENT.polarity_scores(str(article["title"]))["compound"]) if is_english else None
            sentiment_label = ("positive" if score is not None and score >= 0.15 else
                               "negative" if score is not None and score <= -0.15 else
                               "neutral" if score is not None else "unavailable")
            published = _parse_gdelt_date(article.get("seendate"))
            story_url = str(article["url"])
            stories.append(NewsStory(
                title=str(article["title"])[:400], url=story_url,
                publisher=str(article.get("domain") or "GDELT-indexed publisher"),
                published_at=published, language=language, country_iso3=code.upper(),
                topic=topic or "country markets and economy", sentiment_score=score,
                sentiment_label=sentiment_label, sentiment_evidence_count=1 if score is not None else 0,
                sentiment_model="VADER compound · English headline only" if score is not None else None,
                source=SourceCitation(source_id="gdelt-doc", name=str(article.get("domain") or "GDELT news index"),
                    url=story_url, dataset="GDELT DOC 2.0", record_id=str(article.get("url")),
                    retrieved_at=fetched, observed_at=published.isoformat() if published else None,
                    cadence="news-index dependent", status="stale" if cache_state == "stale" else "available",
                    usage_note="Headline-level English sentiment only; score is not an investment signal."),
            ))
        return stories

    async def _news_rss_fallback(self, code: str, country_name: str, topic: str | None,
                                 days: int, limit: int) -> list[NewsStory]:
        """Fetch attributed headline records from Google News RSS when GDELT is down."""
        query = f'"{country_name}" {topic or "markets economy business"}'
        iso_country = pycountry.countries.get(alpha_3=code.upper())
        region = getattr(iso_country, "alpha_2", "US")
        params = {"q": query, "hl": f"en-{region}", "gl": region, "ceid": f"{region}:en"}
        payload, cache_state = await self._get_json(
            "https://news.google.com/rss/search", params,
            min(self.settings.dashboard_cache_ttl_seconds, 180),
        )
        stories = parse_public_news_rss(payload, code, topic or "country markets and economy",
                                        limit=limit)
        if cache_state == "stale":
            for story in stories:
                story.source.status = "stale"
        return stories


def _parse_gdelt_date(value: Any) -> datetime | None:
    """Parse GDELT's YYYYMMDDTHHMMSS timestamp without assuming local time."""
    if not isinstance(value, str):
        return None
    normalized = value.strip().rstrip("Z")
    for pattern in ("%Y%m%dT%H%M%S", "%Y%m%d%H%M%S"):
        try:
            return datetime.strptime(normalized, pattern).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _parse_rss_date(value: Any) -> datetime | None:
    """Parse standard RSS publication dates into UTC-aware timestamps."""
    if not isinstance(value, str) or not value.strip():
        return None
    from email.utils import parsedate_to_datetime
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
