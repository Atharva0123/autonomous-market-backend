"""Deterministic checks for the dashboard's transparent historical estimates."""
import math

from agent.dashboard_analytics import historical_scenario


def test_scenario_detects_positive_log_linear_trend():
    values = [100 * (1.01 ** index) for index in range(30)]
    result = historical_scenario(values, 20)
    assert result is not None
    assert result.observations == 30
    assert result.trend_growth_pct > 0
    assert result.lower_scenario_pct <= result.trend_growth_pct <= result.upper_scenario_pct
    assert result.risk_label in {"Low", "Moderate", "High"}


def test_scenario_needs_ten_positive_prices():
    assert historical_scenario([1, 2, 3, 4]) is None
    assert historical_scenario([1] * 9) is None


def test_scenario_handles_flat_history_and_validates_horizon():
    result = historical_scenario([42.0] * 12)
    assert result is not None
    assert math.isclose(result.trend_growth_pct, 0, abs_tol=1e-8)
    assert result.max_drawdown_pct == 0
    assert historical_scenario([42.0] * 12, 0) is None
