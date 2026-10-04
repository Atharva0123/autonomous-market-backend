"""Walk-forward statistical and ML forecasts with baseline selection and calibration."""
from __future__ import annotations

import math
import statistics
import warnings
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor
from statsmodels.tsa.arima.model import ARIMA


@dataclass(frozen=True)
class HorizonForecast:
    """Forecast and out-of-sample evaluation for one calendar horizon."""

    horizon_days: int
    horizon_sessions: int
    last_observed_price: float
    base_price: float
    lower_95: float | None
    upper_95: float | None
    selected_model: str
    model_adds_signal: bool
    evaluation_origins: int
    test_origins: int
    baseline_mae_pct: float | None
    model_mae_pct: float | None
    directional_accuracy_pct: float | None
    interval_coverage_pct: float | None
    status: str


@dataclass(frozen=True)
class ForecastBundle:
    """All requested forecast horizons and the limitations of the run."""

    symbol: str
    observations: int
    generated_at: str
    horizons: list[HorizonForecast]
    observed_annualized_volatility_pct: float | None
    observed_max_drawdown_pct: float | None
    risk_lookback_observations: int
    method: str
    limitations: list[str]


def _features(log_prices: np.ndarray, end: int) -> np.ndarray:
    """Create causal return/momentum/volatility inputs from data through end."""
    log_returns = np.diff(log_prices[:end + 1])
    output: list[float] = []
    for window in (1, 5, 21, 63):
        output.append(float(np.sum(log_returns[-window:])) if len(log_returns) >= window else 0.0)
    for window in (21, 63):
        output.append(float(np.std(log_returns[-window:], ddof=1)) if len(log_returns) >= window + 1 else 0.0)
    output.extend([float(log_returns[-1]) if len(log_returns) else 0.0,
                   float(np.mean(log_returns[-63:])) if len(log_returns) else 0.0])
    return np.asarray(output, dtype=float)


def _fit_predict(model_name: str, logs: np.ndarray, origin: int, horizon: int) -> float | None:
    """Estimate a cumulative log return using observations strictly before origin."""
    if model_name == "random_walk":
        return 0.0
    returns = np.diff(logs[:origin + 1])
    if model_name == "drift":
        return float(np.mean(returns[-min(63, len(returns)):]) * horizon) if len(returns) else 0.0
    if model_name == "arima":
        if len(returns) < 80:
            return None
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                fitted = ARIMA(returns[-252:], order=(1, 0, 1), enforce_stationarity=False,
                               enforce_invertibility=False).fit()
                projected = fitted.forecast(steps=horizon)
            return float(np.sum(projected))
        except (ValueError, np.linalg.LinAlgError, ZeroDivisionError):
            return None
    if model_name == "hist_gradient_boosting":
        features: list[np.ndarray] = []
        targets: list[float] = []
        first = 64
        final_known_origin = origin - horizon
        for end in range(first, final_known_origin + 1):
            features.append(_features(logs, end))
            targets.append(float(logs[end + horizon] - logs[end]))
        if len(targets) < 160:
            return None
        estimator = HistGradientBoostingRegressor(
            max_iter=70, max_leaf_nodes=10, min_samples_leaf=18,
            l2_regularization=1.0, learning_rate=0.06, random_state=17,
        )
        try:
            estimator.fit(np.vstack(features), np.asarray(targets))
            return float(estimator.predict(_features(logs, origin).reshape(1, -1))[0])
        except (ValueError, FloatingPointError):
            return None
    return None


def _metrics(actual: list[float], predicted: list[float]) -> float | None:
    if not actual:
        return None
    return float(np.mean(np.abs(np.asarray(actual) - np.asarray(predicted))) * 100)


def forecast_series(symbol: str, prices: list[float], horizons_days: tuple[int, ...] = (7, 30, 90)) -> ForecastBundle:
    """Run expanding-window validation and calibrated scenario forecasting.

    Each calendar horizon maps to an approximate number of trading sessions. Model
    choice uses only an early validation slice and is retained only when its MAE
    beats a zero-return random-walk benchmark. A separate later calibration
    slice and final test slice prevent model selection from reusing interval/test data.
    A 95% band is withheld unless 20 calibration residuals are available.
    """
    clean = [float(price) for price in prices if math.isfinite(float(price)) and float(price) > 0]
    logs = np.log(np.asarray(clean, dtype=float))
    n = len(logs)
    from datetime import datetime, timezone
    generated_at = datetime.now(timezone.utc).isoformat()
    if n < 100:
        return ForecastBundle(symbol=symbol, observations=n, generated_at=generated_at, horizons=[],
            observed_annualized_volatility_pct=None, observed_max_drawdown_pct=None,
            risk_lookback_observations=0,
            method="walk-forward random-walk / drift / ARIMA(1,0,1) / gradient-boosting comparison",
            limitations=["At least 100 positive historical observations are required for walk-forward evaluation."])

    risk_start = max(0, n - 252)
    risk_prices = np.exp(logs[risk_start:])
    risk_returns = np.diff(np.log(risk_prices))
    realized_volatility = float(np.std(risk_returns, ddof=1) * math.sqrt(252) * 100) if len(risk_returns) > 1 else None
    peaks = np.maximum.accumulate(risk_prices)
    drawdowns = (risk_prices / peaks - 1.0) * 100
    max_drawdown = float(np.min(drawdowns)) if len(drawdowns) else None

    forecasts: list[HorizonForecast] = []
    model_names = ("drift", "arima", "hist_gradient_boosting")
    for calendar_days in horizons_days:
        sessions = max(1, round(calendar_days * 252 / 365))
        start = max(126, n // 2)
        step = max(1, sessions // 4)
        origins = list(range(start, n - sessions, step))
        predictions: dict[str, list[float]] = {"random_walk": [], **{name: [] for name in model_names}}
        actuals: list[float] = []
        for origin in origins:
            actual = float(logs[origin + sessions] - logs[origin])
            actuals.append(actual)
            for model in predictions:
                estimate = _fit_predict(model, logs, origin, sessions)
                predictions[model].append(float("nan") if estimate is None else estimate)
        # Discard a candidate only for origins where that model was not eligible.
        selection_end = max(1, int(len(origins) * 0.3))
        calibration_end = max(selection_end + 1, int(len(origins) * 0.6))
        baseline_validation = [p for p in predictions["random_walk"][:selection_end] if math.isfinite(p)]
        validation_actual = actuals[:selection_end]
        baseline_validation_mae = _metrics(validation_actual, baseline_validation)
        chosen = "random_walk"
        chosen_validation = baseline_validation_mae
        for model in model_names:
            pairs = [(actuals[i], value) for i, value in enumerate(predictions[model][:selection_end]) if math.isfinite(value)]
            if len(pairs) < 3:
                continue
            score = _metrics([p[0] for p in pairs], [p[1] for p in pairs])
            if score is not None and chosen_validation is not None and score < chosen_validation:
                chosen, chosen_validation = model, score

        test_indices = range(calibration_end, len(origins))
        base_test = [predictions["random_walk"][i] for i in test_indices]
        selected_test = [predictions[chosen][i] for i in test_indices]
        test_actual = [actuals[i] for i in test_indices]
        valid_test = [(actual, pred, base) for actual, pred, base in zip(test_actual, selected_test, base_test)
                      if math.isfinite(pred) and math.isfinite(base)]
        test_errors = [actual - pred for actual, pred, _ in valid_test]
        baseline_mae = _metrics([p[0] for p in valid_test], [p[2] for p in valid_test])
        model_mae = _metrics([p[0] for p in valid_test], [p[1] for p in valid_test])
        directional = (100 * sum((actual >= 0) == (pred >= 0) for actual, pred, _ in valid_test) / len(valid_test)
                       if valid_test else None)
        model_adds = chosen != "random_walk" and model_mae is not None and baseline_mae is not None and model_mae < baseline_mae

        selected_full = chosen if model_adds else "random_walk"
        point_return = _fit_predict(selected_full, logs, n - 1, sessions) or 0.0
        calibration_indices = range(selection_end, min(calibration_end, len(actuals)))
        validation_errors = [actuals[i] - predictions[selected_full][i]
                             for i in calibration_indices
                             if math.isfinite(predictions[selected_full][i])]
        if len(validation_errors) >= 20:
            lower_error, upper_error = np.quantile(validation_errors, [0.025, 0.975]).tolist()
            low = float(clean[-1] * math.exp(point_return + lower_error))
            high = float(clean[-1] * math.exp(point_return + upper_error))
            coverage = 100 * sum(lower_error <= error <= upper_error for error in test_errors) / len(test_errors) if test_errors else None
        else:
            low, high, coverage = None, None, None
        forecasts.append(HorizonForecast(
            horizon_days=calendar_days, horizon_sessions=sessions, last_observed_price=clean[-1],
            base_price=float(clean[-1] * math.exp(point_return)), lower_95=low, upper_95=high,
            selected_model=selected_full, model_adds_signal=model_adds,
            evaluation_origins=len(origins), test_origins=len(valid_test),
            baseline_mae_pct=baseline_mae, model_mae_pct=model_mae,
            directional_accuracy_pct=directional, interval_coverage_pct=coverage,
            status="model beat naïve baseline out of sample" if model_adds else "no validated edge over random-walk baseline",
        ))
    return ForecastBundle(
        symbol=symbol, observations=n, generated_at=generated_at, horizons=forecasts,
        observed_annualized_volatility_pct=realized_volatility,
        observed_max_drawdown_pct=max_drawdown,
        risk_lookback_observations=len(risk_prices),
        method="Expanding-window walk-forward with chronological model-selection, interval-calibration and final-test slices; random-walk benchmark; drift and ARIMA(1,0,1) statistical candidates; HistGradientBoosting ML candidate; 95% empirical interval only with >=20 separate calibration residuals.",
        limitations=[
            "Daily observations are mapped from calendar days to approximate trading sessions; source market calendars may differ.",
            "Historical backtest performance does not guarantee future performance; data gaps and provider revisions can change results.",
            "LLM qualitative scenarios are displayed separately from these quantitative forecasts.",
        ],
    )
