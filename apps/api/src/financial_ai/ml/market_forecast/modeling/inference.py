"""Inference input preparation for market volatility forecasts."""

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from financial_ai.ml.market_forecast.data.daily_bars import validate_daily_bars
from financial_ai.ml.market_forecast.data.features import (
    FEATURE_COLUMNS,
    build_market_features,
)
from financial_ai.ml.market_forecast.modeling.ewma import (
    DEFAULT_EWMA_DECAY,
    DEFAULT_EWMA_MIN_OBSERVATIONS,
)
from financial_ai.ml.market_forecast.modeling.model_artifact import (
    LoadedMarketForecastModel,
    predict_volatility,
)
from financial_ai.schemas import MarketHistoryRead

FORECAST_HORIZON_TRADING_DAYS = 20
EWMA_MODEL_VERSION = "ewma-close-0.94-v1"


class InsufficientForecastHistoryError(ValueError):
    """Raised when cached history cannot produce a complete forecast input."""


@dataclass(frozen=True)
class MarketForecastInput:
    """Latest observation date and ordered model features for one instrument."""

    observed_on: date
    features: pd.DataFrame


@dataclass(frozen=True)
class MarketVolatilityForecast:
    """Original-scale volatility forecast with model and observation context."""

    symbol: str
    observed_on: date
    horizon_trading_days: int
    predicted_annualized_volatility: float
    model_version: str


def history_to_daily_bars(history: MarketHistoryRead) -> pd.DataFrame:
    """Convert cached market history into the validated daily-bar contract."""
    rows = [
        {
            "symbol": history.instrument.symbol,
            "observed_on": point.observed_on,
            "open": point.open,
            "high": point.high,
            "low": point.low,
            "close": point.close,
            "adjusted_close": point.adjusted_close,
            "volume": point.volume,
        }
        for point in history.points
    ]
    frame = pd.DataFrame(rows)
    return validate_daily_bars(frame)


def build_latest_forecast_input(history: MarketHistoryRead) -> MarketForecastInput:
    """Build the latest complete model input from cached daily history."""
    daily_bars = history_to_daily_bars(history)
    features = build_market_features(daily_bars)
    if features.empty:
        raise InsufficientForecastHistoryError("Market history has no complete feature row")
    latest_row = features.iloc[-1]
    latest_features = features.tail(1).loc[:, FEATURE_COLUMNS].reset_index(drop=True)

    return MarketForecastInput(
        observed_on=latest_row["observed_on"].date(),
        features=latest_features,
    )


def forecast_volatility(
    history: MarketHistoryRead,
    loaded_model: LoadedMarketForecastModel,
) -> MarketVolatilityForecast:
    """Forecast volatility from validated cached history and a verified model."""
    forecast_input = build_latest_forecast_input(history)
    predicted_volatility = predict_volatility(loaded_model, forecast_input.features)
    return MarketVolatilityForecast(
        symbol=history.instrument.symbol.upper(),
        observed_on=forecast_input.observed_on,
        horizon_trading_days=FORECAST_HORIZON_TRADING_DAYS,
        predicted_annualized_volatility=predicted_volatility,
        model_version=loaded_model.metadata.model_version,
    )


def forecast_ewma_volatility(history: MarketHistoryRead) -> MarketVolatilityForecast:
    """Forecast from observed closes when a trained OHLCV model is unavailable.

    This is the same 0.94 decay reference used in offline evaluation. Demo
    instruments have close-only synthetic data, so they cannot use XGBoost.
    """
    points = history.points
    if len(points) <= DEFAULT_EWMA_MIN_OBSERVATIONS:
        raise InsufficientForecastHistoryError("EWMA requires at least 21 daily closes")
    closes = np.asarray(
        [
            float(point.adjusted_close if point.adjusted_close is not None else point.close)
            for point in points
        ],
        dtype=float,
    )
    if not np.isfinite(closes).all() or (closes <= 0).any():
        raise InsufficientForecastHistoryError("EWMA requires positive finite daily closes")
    log_returns = np.diff(np.log(closes))
    variance = (
        pd.Series(log_returns)
        .pow(2)
        .ewm(
            alpha=1 - DEFAULT_EWMA_DECAY,
            adjust=False,
            min_periods=DEFAULT_EWMA_MIN_OBSERVATIONS,
        )
        .mean()
        .iloc[-1]
    )
    volatility = float(np.sqrt(variance * 252))
    if not np.isfinite(volatility) or volatility <= 0:
        raise InsufficientForecastHistoryError("EWMA could not estimate positive volatility")
    return MarketVolatilityForecast(
        symbol=history.instrument.symbol.upper(),
        observed_on=points[-1].observed_on,
        horizon_trading_days=FORECAST_HORIZON_TRADING_DAYS,
        predicted_annualized_volatility=volatility,
        model_version=EWMA_MODEL_VERSION,
    )
