"""Typed HTTP request/response schemas for the web dashboard."""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class SourceCitation(BaseModel):
    """Provenance and freshness for an observed fact or source record."""

    source_id: str
    name: str
    url: HttpUrl
    dataset: str
    record_id: str | None = None
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    observed_at: str | None = None
    cadence: str = "unknown"
    status: Literal["available", "delayed", "stale", "unavailable", "unverified"] = "available"
    usage_note: str | None = None


class Observation(BaseModel):
    """One normalized dated observation with direct source attribution."""

    period: str
    value: float


class MacroSeries(BaseModel):
    """Country indicator and its historical observations."""

    indicator: str
    label: str
    unit: str
    observations: list[Observation] = Field(default_factory=list)
    source: SourceCitation
    status: Literal["available", "unavailable"] = "available"


class CountryInfo(BaseModel):
    """ISO-coded country catalog row used by search and the globe."""

    iso2: str
    iso3: str
    name: str
    flag: str | None = None


class CountryOverview(BaseModel):
    """Normalized data assembled for a country page; missing series are explicit."""

    country: CountryInfo
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    range_start: int
    range_end: int
    macro: list[MacroSeries] = Field(default_factory=list)
    market_coverage: Literal["partial", "unavailable", "available"] = "partial"
    limitations: list[str] = Field(default_factory=list)


class NewsStory(BaseModel):
    """Headline enriched with sentiment and record-level provenance."""

    title: str
    url: HttpUrl
    publisher: str
    published_at: datetime | None = None
    language: str | None = None
    country_iso3: str
    topic: str
    sentiment_score: float | None = Field(default=None, ge=-1, le=1)
    sentiment_label: Literal["positive", "negative", "neutral", "unavailable"] = "unavailable"
    sentiment_evidence_count: int = 0
    sentiment_model: str | None = None
    source: SourceCitation


class Suggestion(BaseModel):
    """One grouped hybrid search suggestion."""

    kind: Literal["country", "asset", "sector", "commodity", "index", "prompt", "macro"]
    label: str
    value: str
    description: str = ""
    query_template: str | None = None


class ResearchRequest(BaseModel):
    """Validated natural-language research submission."""

    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=2, max_length=2000)
    date_from: date | None = None
    date_to: date | None = None
    make_prediction: bool = False


class TaxPolicy(BaseModel):
    """Public fiscal/tax facts; statutory rules are not inferred from revenue data."""

    country: CountryInfo
    tax_revenue_series: MacroSeries
    statutory_rates_status: Literal["not_catalogued", "partially_catalogued"] = "not_catalogued"
    official_policy_url: HttpUrl | None = None
    limitations: list[str] = Field(default_factory=list)


class IndiaTaxEstimateRequest(BaseModel):
    """Supported India resident individual's listed-equity disposal estimate."""

    asset_type: Literal["listed_equity", "equity_oriented_fund"]
    acquisition_date: date
    transfer_date: date
    purchase_value_inr: float = Field(gt=0)
    sale_value_inr: float = Field(gt=0)
    eligible_costs_inr: float = Field(default=0, ge=0)
    stt_eligible: bool
    prior_112a_gains_inr: float = Field(default=0, ge=0)
    tax_year: Literal["FY2025-26"] = "FY2025-26"


class IndiaTaxEstimate(BaseModel):
    """Tax component before surcharge/cess and other household income effects."""

    jurisdiction: str = "India"
    tax_year: str
    gain_type: Literal["short_term", "long_term"]
    gross_gain_inr: float
    taxable_gain_inr: float
    applicable_rate_pct: float
    estimated_tax_before_surcharge_cess_inr: float
    assumptions: list[str]
    citations: list[SourceCitation]
    validated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
