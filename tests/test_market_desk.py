"""Deterministic coverage for normalized data, forecast guardrails, and tax scope."""
from __future__ import annotations

import asyncio
from datetime import date

import httpx
import pytest
import respx

from agent.forecasting import _fit_predict, forecast_series
from api.catalog import suggestions
from api.data_sources import MACRO_INDICATORS, PublicDataService, describe_http_error, rolling_correlations
from api.models import IndiaTaxEstimateRequest
from api.tax import estimate_india_gain


@pytest.mark.asyncio
async def test_world_bank_rows_keep_direct_provenance_and_cache(settings):
    client = httpx.AsyncClient()
    service = PublicDataService(settings, client=client)
    try:
        with respx.mock(assert_all_called=True) as router:
            routes = []
            for index, (indicator, _, _) in enumerate(MACRO_INDICATORS):
                url = f"https://api.worldbank.org/v2/country/IND/indicator/{indicator}"
                value = 6.5 if indicator == "NY.GDP.MKTP.KD.ZG" else 6.5 + index
                rows = [{"indicator": {"id": indicator}, "date": "2024", "value": value}]
                routes.append(router.get(url).mock(return_value=httpx.Response(200, json=[{"page": 1, "pages": 1}, rows])))
            overview = await service.country_overview("IND", 2020, 2025)
            cached = await service.country_overview("IND", 2020, 2025)
            relationships = await service.country_relationships("IND", 2020, 2025)
            assert all(route.call_count == 1 for route in routes)
            growth = next(item for item in overview.macro if item.indicator == "NY.GDP.MKTP.KD.ZG")
            assert growth.observations[0].value == 6.5
            assert str(growth.source.url).startswith("https://api.worldbank.org/")
            assert growth.source.observed_at == "2024"
            assert any("8 of 8" in item for item in cached.limitations)
            assert all(row["status"] == "insufficient_aligned_history" for row in relationships["correlations"])
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_public_macro_retries_rate_limit_then_succeeds(settings):
    retry_settings = settings.model_copy(update={"request_retries": 1, "retry_backoff_seconds": 0.001})
    client = httpx.AsyncClient()
    service = PublicDataService(retry_settings, client=client)
    url = "https://api.worldbank.org/v2/country/USA/indicator/NY.GDP.MKTP.CD"
    try:
        with respx.mock(assert_all_called=True) as router:
            route = router.get(url).mock(side_effect=[
                httpx.Response(429, headers={"Retry-After": "0"}),
                httpx.Response(200, json=[{"page": 1}, []]),
            ])
            for indicator, _, _ in MACRO_INDICATORS:
                if indicator != "NY.GDP.MKTP.CD":
                    router.get(f"https://api.worldbank.org/v2/country/USA/indicator/{indicator}").mock(
                        return_value=httpx.Response(200, json=[{"page": 1}, []]))
            result = await service.country_overview("USA", 2020, 2025)
            assert route.call_count == 2
            assert result.country.iso3 == "USA"
            assert all(series.status == "unavailable" for series in result.macro)
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_public_macro_uses_stale_cache_with_explicit_status(settings):
    client = httpx.AsyncClient()
    service = PublicDataService(settings, client=client)
    params = {"format": "json", "per_page": 1000, "date": "2020:2025"}
    routes = []
    try:
        with respx.mock(assert_all_called=True) as router:
            for indicator, _, _ in MACRO_INDICATORS:
                url = f"https://api.worldbank.org/v2/country/CAN/indicator/{indicator}"
                row = {"indicator": {"id": indicator}, "date": "2024", "value": 1.0}
                routes.append(router.get(url).mock(side_effect=[
                    httpx.Response(200, json=[{"page": 1}, [row]]),
                    httpx.Response(503, text="temporary outage"),
                ]))
            fresh = await service.country_overview("CAN", 2020, 2025)
            assert all(series.source.status == "available" for series in fresh.macro)
            for indicator, _, _ in MACRO_INDICATORS:
                key = f"https://api.worldbank.org/v2/country/CAN/indicator/{indicator}?{httpx.QueryParams(params)}"
                service._cache[key] = (0.0, service._cache[key][1])
            stale = await service.country_overview("CAN", 2020, 2025)
            assert all(series.source.status == "stale" for series in stale.macro)
            assert all(series.observations for series in stale.macro)
            assert any("stale" in item for item in stale.limitations)
            assert routes[0].call_count == 2
            assert all(route.call_count == 1 for route in routes[1:])
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_news_marks_unsupported_language_sentiment_unavailable(settings):
    client = httpx.AsyncClient()
    service = PublicDataService(settings, client=client)
    try:
        with respx.mock(assert_all_called=True) as router:
            router.get(settings.gdelt_base_url).mock(return_value=httpx.Response(200, json={"articles": [
                {"title": "Markets rally on strong earnings", "url": "https://news.example/en", "language": "English", "domain": "news.example", "seendate": "20261003T120000Z"},
                {"title": "Mercados caen", "url": "https://news.example/es", "language": "Spanish", "domain": "news.example", "seendate": "20261003T120000Z"},
            ]}))
            stories = await service.news("IND", "India", limit=5)
            assert stories[0].sentiment_score is not None
            assert stories[0].sentiment_evidence_count == 1
            assert stories[0].source.url == stories[0].url
            assert stories[1].sentiment_score is None
            assert stories[1].sentiment_label == "unavailable"
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_news_rate_limit_uses_rss_fallback_without_repeating_primary(settings):
    limited_settings = settings.model_copy(update={"request_retries": 0})
    client = httpx.AsyncClient()
    service = PublicDataService(limited_settings, client=client)
    try:
        with respx.mock(assert_all_called=True) as router:
            route = router.get(settings.gdelt_base_url).mock(return_value=httpx.Response(429, text="slow down"))
            rss = router.get("https://news.google.com/rss/search").mock(return_value=httpx.Response(200, headers={"content-type": "application/rss+xml"}, text=(
                "<rss><channel><item><title>India markets recover as earnings rise</title>"
                "<link>https://publisher.example/story</link><source>Example Publisher</source>"
                "<pubDate>Sat, 03 Oct 2026 12:00:00 GMT</pubDate></item></channel></rss>")))
            results = await asyncio.gather(service.news("IND", "India", limit=3),
                                           service.news("IND", "India", limit=3), return_exceptions=True)
            assert all(isinstance(result, list) for result in results), [repr(result) for result in results]
            assert all(result and result[0].source.source_id == "google-news-rss" for result in results)
            cached_fallback = await service.news("IND", "India", limit=3)
            assert str(cached_fallback[0].url) == "https://publisher.example/story"
            assert route.call_count == 1
            assert rss.call_count >= 1
    finally:
        await client.aclose()


def test_hybrid_catalog_routes_country_sector_asset_and_prompt():
    assert any(item.kind == "country" and item.value == "IND" for item in suggestions("India"))
    assert any(item.kind == "sector" and item.value == "Technology" for item in suggestions("technology"))
    assert any(item.kind == "asset" and item.value == "NVDA" for item in suggestions("NVIDIA"))
    assert any(item.kind == "prompt" for item in suggestions("Make prediction"))


def test_upstream_http_errors_keep_status_details():
    request = httpx.Request("GET", "https://news.example/api")
    response = httpx.Response(429, request=request)
    error = httpx.HTTPStatusError("", request=request, response=response)
    assert describe_http_error(error) == "HTTP 429 Too Many Requests."


def test_rolling_macro_correlations_use_fixed_aligned_windows():
    periods = [str(year) for year in range(2018, 2024)]
    values = [float(year) for year in range(1, 7)]
    points = rolling_correlations(periods, values, [value * 2 for value in values], window=5)
    assert len(points) == 2
    assert points[0] == {"period_start": "2018", "period_end": "2022", "coefficient": 1.0}
    assert points[1]["period_start"] == "2019"
    assert rolling_correlations(periods[:4], values[:4], values[:4], window=5) == []


def test_india_tax_estimate_applies_supported_ltcg_threshold_and_cites_rules():
    request = IndiaTaxEstimateRequest(
        asset_type="listed_equity", acquisition_date=date(2024, 1, 1),
        transfer_date=date(2025, 8, 1), purchase_value_inr=100_000,
        sale_value_inr=400_000, stt_eligible=True, prior_112a_gains_inr=25_000,
    )
    result = estimate_india_gain(request)
    assert result.gain_type == "long_term"
    assert result.taxable_gain_inr == 200_000
    assert result.estimated_tax_before_surcharge_cess_inr == 25_000
    assert result.citations and all(str(item.url).startswith("https://") for item in result.citations)


@pytest.mark.parametrize("overrides", [
    {"stt_eligible": False},
    {"transfer_date": date(2026, 4, 1)},
    {"transfer_date": date(2024, 7, 22)},
])
def test_india_tax_estimator_rejects_out_of_scope_cases(overrides):
    values = dict(asset_type="listed_equity", acquisition_date=date(2024, 1, 1),
                  transfer_date=date(2025, 8, 1), purchase_value_inr=100_000,
                  sale_value_inr=120_000, stt_eligible=True)
    values.update(overrides)
    with pytest.raises(Exception):
        estimate_india_gain(IndiaTaxEstimateRequest(**values))


def test_forecast_requires_enough_history_and_discloses_no_edge():
    short = forecast_series("TEST", [100.0 + index for index in range(60)])
    assert not short.horizons
    assert "100" in short.limitations[0]

    # Deterministic, choppy series: model claims must be compared with naive baseline.
    prices = [100.0]
    for index in range(150):
        prices.append(prices[-1] * (1.002 if index % 2 == 0 else 0.998))
    result = forecast_series("TEST", prices)
    assert result.horizons
    assert all(item.lower_95 is None and item.upper_95 is None for item in result.horizons)
    assert all(item.model_adds_signal == (item.model_mae_pct is not None and item.baseline_mae_pct is not None and item.model_mae_pct < item.baseline_mae_pct and item.selected_model != "random_walk") for item in result.horizons)
    assert all(item.test_origins >= 0 for item in result.horizons)


def test_drift_forecast_does_not_read_observations_after_its_origin():
    import numpy as np

    logs = np.log(np.linspace(80.0, 125.0, 240))
    changed_future = logs.copy()
    changed_future[121:] = np.log(np.linspace(500.0, 900.0, len(changed_future) - 121))
    original = _fit_predict("drift", logs, origin=120, horizon=15)
    changed = _fit_predict("drift", changed_future, origin=120, horizon=15)
    assert original == changed
