"""Small transparent scenario calculations for historical market series."""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass


@dataclass(frozen=True)
class HistoricalScenario:
    """Descriptive trend and realized-risk estimates, not a promised forecast."""

    observations: int
    horizon_sessions: int
    trend_growth_pct: float
    lower_scenario_pct: float
    upper_scenario_pct: float
    annualized_volatility_pct: float
    max_drawdown_pct: float
    risk_score: float
    risk_label: str


def historical_scenario(prices: list[float], horizon_sessions: int = 20) -> HistoricalScenario | None:
    """Fit a log-price linear trend and a realized-volatility scenario band.

    Requires at least 10 positive observations. The band uses historical daily
    log-return volatility and is not statistically calibrated to future outcomes.
    """
    clean = [float(value) for value in prices if math.isfinite(float(value)) and float(value) > 0]
    if len(clean) < 10 or horizon_sessions < 1:
        return None
    logs = [math.log(value) for value in clean]
    n = len(logs)
    xbar = (n - 1) / 2
    ybar = statistics.fmean(logs)
    denominator = sum((index - xbar) ** 2 for index in range(n))
    slope = sum((index - xbar) * (value - ybar) for index, value in enumerate(logs)) / denominator
    trend_growth = math.exp(slope * horizon_sessions) - 1
    returns = [logs[i] - logs[i - 1] for i in range(1, n)]
    daily_vol = statistics.stdev(returns) if len(returns) > 1 else 0.0
    annual_vol = daily_vol * math.sqrt(252)
    uncertainty = 1.96 * daily_vol * math.sqrt(horizon_sessions)
    lower = math.exp(math.log1p(max(trend_growth, -0.999999)) - uncertainty) - 1
    upper = math.exp(math.log1p(max(trend_growth, -0.999999)) + uncertainty) - 1
    peak = clean[0]
    drawdown = 0.0
    for price in clean:
        peak = max(peak, price)
        drawdown = min(drawdown, price / peak - 1)
    risk_score = min(100.0, max(0.0, 65 * min(annual_vol / 0.8, 1) + 35 * min(abs(drawdown) / 0.5, 1)))
    label = "Low" if risk_score < 33 else "Moderate" if risk_score < 66 else "High"
    return HistoricalScenario(n, horizon_sessions, trend_growth * 100, lower * 100, upper * 100,
                              annual_vol * 100, drawdown * 100, risk_score, label)
