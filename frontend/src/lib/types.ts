export type Country = { iso2: string; iso3: string; name: string; flag?: string | null };
export type Source = {
  source_id: string; name: string; url: string; dataset: string; record_id?: string | null;
  retrieved_at: string; observed_at?: string | null; cadence: string;
  status: "available" | "delayed" | "stale" | "unavailable" | "unverified"; usage_note?: string | null;
};
export type Observation = { period: string; value: number };
export type MacroSeries = {
  indicator: string; label: string; unit: string; observations: Observation[];
  source: Source; status: "available" | "unavailable";
};
export type CountryOverview = {
  country: Country; generated_at: string; range_start: number; range_end: number;
  macro: MacroSeries[]; market_coverage: "partial" | "unavailable" | "available";
  limitations: string[];
};
export type Relationship = {
  label: string; coefficient?: number | null; evidence_count: number; period_start?: string | null;
  period_end?: string | null; rolling_window_years?: number; rolling_points?: { period_start: string; period_end: string; coefficient?: number | null }[];
  status: string; source_left: Source; source_right: Source;
};
export type CountryRelationships = { correlations: Relationship[]; interpretation: string; limitations: string[] };
export type Suggestion = {
  kind: "country" | "asset" | "sector" | "commodity" | "index" | "prompt" | "macro";
  label: string; value: string; description: string; query_template?: string | null;
};
export type NewsStory = {
  title: string; url: string; publisher: string; published_at?: string | null;
  language?: string | null; country_iso3: string; topic: string;
  sentiment_score?: number | null; sentiment_label: "positive" | "negative" | "neutral" | "unavailable";
  sentiment_evidence_count: number; sentiment_model?: string | null; source: Source;
};
export type ForecastHorizon = {
  horizon_days: number; horizon_sessions: number; last_observed_price: number; base_price: number;
  lower_95?: number | null; upper_95?: number | null; selected_model: string; model_adds_signal: boolean;
  evaluation_origins: number; test_origins: number; baseline_mae_pct?: number | null; model_mae_pct?: number | null;
  directional_accuracy_pct?: number | null; interval_coverage_pct?: number | null; status: string;
};
export type ForecastResponse = {
  status: string; prices?: { date: string; close: number }[]; price_source?: string; price_source_url?: string | null;
  forecasts?: { symbol: string; observations: number; generated_at: string; horizons: ForecastHorizon[];
    observed_annualized_volatility_pct?: number | null; observed_max_drawdown_pct?: number | null;
    risk_lookback_observations?: number; method: string; limitations: string[] };
  error?: string;
};
export type TaxEstimate = {
  jurisdiction: string; tax_year: string; gain_type: "short_term" | "long_term"; gross_gain_inr: number;
  taxable_gain_inr: number; applicable_rate_pct: number; estimated_tax_before_surcharge_cess_inr: number;
  assumptions: string[]; citations: Source[]; validated_at: string;
};
export type SourceInfo = { id: string; name: string; domain: string; status: string; url: string; cadence: string; key: string };
export type UsageStatus = { provider: string; used: number; limit: number; remaining: number; key_configured: boolean; period: string; entitlement: string };
