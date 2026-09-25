"""Application service for current market volatility forecasts."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo

from financial_ai.config import get_settings
from financial_ai.market_data_service import (
    InstrumentNotFoundError,
    MarketDataProviderError,
    MarketDataService,
)
from financial_ai.ml.market_forecast.modeling.inference import (
    MarketVolatilityForecast,
    forecast_ewma_volatility,
    forecast_volatility,
)
from financial_ai.ml.market_forecast.modeling.model_artifact import (
    LoadedMarketForecastModel,
    load_market_forecast_model_artifact,
)

FORECAST_HISTORY_CALENDAR_DAYS = 600
US_MARKET_TIMEZONE = ZoneInfo("America/New_York")
DAILY_BAR_FINALIZATION_TIME = time(16, 15)


@dataclass(frozen=True)
class CurrentMarketVolatilityForecast:
    """Forecast result with provider freshness and retrieval provenance."""

    forecast: MarketVolatilityForecast
    source: str
    retrieved_at: datetime
    data_status: str
    training_source_feed: str | None
    feed_match: bool | None


def last_completed_us_market_date(now: datetime) -> date:
    """Return the latest weekday whose US regular session is safely complete."""
    if now.tzinfo is None:
        raise ValueError("Current time must include timezone information")
    local_now = now.astimezone(US_MARKET_TIMEZONE)
    if local_now.weekday() < 5 and local_now.time() >= DAILY_BAR_FINALIZATION_TIME:
        candidate = local_now.date()
    else:
        candidate = local_now.date() - timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate -= timedelta(days=1)
    return candidate


class MarketForecastService:
    """Refresh cached daily bars and produce a versioned volatility forecast."""

    def __init__(
        self,
        market_data: MarketDataService,
        loaded_model: LoadedMarketForecastModel | None,
        clock: Callable[[], datetime] | None = None,
        demo_mode: bool = False,
    ) -> None:
        self._market_data = market_data
        self._loaded_model = loaded_model
        self._clock = clock or (lambda: datetime.now(UTC))
        self._demo_mode = demo_mode

    def forecast(self, instrument_id: str) -> CurrentMarketVolatilityForecast:
        now = self._clock()
        completed_through = last_completed_us_market_date(now)
        date_from = completed_through - timedelta(days=FORECAST_HISTORY_CALENDAR_DAYS)
        if self._demo_mode:
            date_from = None
        history = self._market_data.history(
            instrument_id,
            date_from=date_from,
            date_to=completed_through,
        )
        latest_observation = history.points[-1].observed_on
        needs_refresh = self._market_data.is_stale(history.retrieved_at) or (
            latest_observation < completed_through and not self._demo_mode
        )
        data_status = "current"
        if needs_refresh:
            try:
                history = self._market_data.history(
                    instrument_id,
                    date_from=date_from,
                    date_to=completed_through,
                    refresh=True,
                )
            except (InstrumentNotFoundError, MarketDataProviderError):
                data_status = "stale"

        if history.points[-1].observed_on < completed_through:
            data_status = "stale"
        if self._loaded_model is None:
            result = forecast_ewma_volatility(history)
            training_feed = None
        else:
            result = forecast_volatility(history, self._loaded_model)
            training_feed = self._loaded_model.metadata.training_source_feed
        source_parts = history.source.split(":", maxsplit=1)
        inference_feed = source_parts[1] if len(source_parts) == 2 else None
        return CurrentMarketVolatilityForecast(
            forecast=result,
            source=history.source,
            retrieved_at=history.retrieved_at,
            data_status=data_status,
            training_source_feed=training_feed,
            feed_match=(
                inference_feed == training_feed if inference_feed and training_feed else None
            ),
        )


@lru_cache
def get_loaded_market_forecast_model() -> LoadedMarketForecastModel:
    """Load and cache the checksum-verified forecast artifact."""
    settings = get_settings()
    return load_market_forecast_model_artifact(
        settings.market_forecast_model_artifact_path,
        settings.market_forecast_model_metadata_path,
    )
