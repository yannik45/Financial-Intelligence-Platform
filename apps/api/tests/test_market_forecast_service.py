from datetime import UTC, date, datetime
from decimal import Decimal

import pandas as pd
import pytest
from financial_ai.main import app, get_market_forecast_service
from financial_ai.market_data_service import MarketDataProviderError
from financial_ai.market_forecast_service import (
    CurrentMarketVolatilityForecast,
    MarketForecastService,
    last_completed_us_market_date,
)
from financial_ai.ml.market_forecast.modeling.inference import MarketVolatilityForecast
from financial_ai.ml.market_forecast.modeling.model_artifact import MarketForecastArtifactError
from financial_ai.schemas import MarketHistoryRead, MarketInstrumentRead, MarketPriceRead


def forecast_history() -> MarketHistoryRead:
    dates = pd.bdate_range("2026-05-01", periods=65)
    return MarketHistoryRead(
        instrument=MarketInstrumentRead(
            id="instrument-1",
            provider="alpaca",
            symbol="AAPL",
            name="Apple Inc.",
            exchange="NASDAQ",
            currency="USD",
            asset_class="US Equity",
            region="United States",
            is_active=True,
            updated_at=datetime(2026, 8, 10, tzinfo=UTC),
        ),
        source="alpaca:iex",
        retrieved_at=datetime(2026, 8, 7, 20, 30, tzinfo=UTC),
        points=[
            MarketPriceRead(
                observed_on=observed_on.date(),
                open=Decimal(str(100 + index)),
                high=Decimal(str(102 + index)),
                low=Decimal(str(99 + index)),
                close=Decimal(str(101 + index)),
                adjusted_close=Decimal(str(101 + index)),
                volume=Decimal(str(1_000_000 + index * 1_000)),
            )
            for index, observed_on in enumerate(dates)
        ],
    )


class RecordingMarketData:
    def __init__(self, *, stale: bool, fail_refresh: bool = False) -> None:
        self.stale = stale
        self.fail_refresh = fail_refresh
        self.calls: list[dict[str, object]] = []
        self.result = forecast_history()

    def history(self, instrument_id, date_from=None, date_to=None, refresh=False):
        self.calls.append(
            {
                "instrument_id": instrument_id,
                "date_from": date_from,
                "date_to": date_to,
                "refresh": refresh,
            }
        )
        if refresh and self.fail_refresh:
            raise MarketDataProviderError("upstream unavailable")
        return self.result

    def is_stale(self, retrieved_at):
        return self.stale


def forecast_result(history: MarketHistoryRead) -> MarketVolatilityForecast:
    return MarketVolatilityForecast(
        symbol=history.instrument.symbol,
        observed_on=history.points[-1].observed_on,
        horizon_trading_days=20,
        predicted_annualized_volatility=0.237,
        model_version="model-v1",
    )


def loaded_model_stub():
    return type(
        "LoadedModelStub",
        (),
        {"metadata": type("MetadataStub", (), {"training_source_feed": "sip"})()},
    )()


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (datetime(2026, 8, 10, 19, 0, tzinfo=UTC), date(2026, 8, 7)),
        (datetime(2026, 8, 10, 21, 0, tzinfo=UTC), date(2026, 8, 10)),
        (datetime(2026, 8, 8, 18, 0, tzinfo=UTC), date(2026, 8, 7)),
    ],
)
def test_last_completed_market_date_excludes_open_sessions_and_weekends(now, expected):
    assert last_completed_us_market_date(now) == expected


def test_last_completed_market_date_requires_timezone_information():
    with pytest.raises(ValueError, match="timezone"):
        last_completed_us_market_date(datetime(2026, 8, 10, 12, 0))


def test_forecast_service_refreshes_full_window_when_cache_is_stale(monkeypatch):
    market_data = RecordingMarketData(stale=True)
    monkeypatch.setattr(
        "financial_ai.market_forecast_service.forecast_volatility",
        lambda history, model: forecast_result(history),
    )
    service = MarketForecastService(
        market_data,
        loaded_model=loaded_model_stub(),
        clock=lambda: datetime(2026, 8, 10, 19, 0, tzinfo=UTC),
    )

    result = service.forecast("instrument-1")

    assert result.data_status == "stale"
    assert result.training_source_feed == "sip"
    assert result.feed_match is False
    assert [call["refresh"] for call in market_data.calls] == [False, True]
    assert market_data.calls[-1]["date_to"] == date(2026, 8, 7)


def test_forecast_service_marks_cached_data_stale_when_refresh_fails(monkeypatch):
    market_data = RecordingMarketData(stale=True, fail_refresh=True)
    monkeypatch.setattr(
        "financial_ai.market_forecast_service.forecast_volatility",
        lambda history, model: forecast_result(history),
    )
    service = MarketForecastService(
        market_data,
        loaded_model=loaded_model_stub(),
        clock=lambda: datetime(2026, 8, 10, 19, 0, tzinfo=UTC),
    )

    result = service.forecast("instrument-1")

    assert result.data_status == "stale"
    assert result.forecast.predicted_annualized_volatility == pytest.approx(0.237)


def test_forecast_service_uses_ewma_without_deployment_artifact():
    market_data = RecordingMarketData(stale=False)
    service = MarketForecastService(
        market_data,
        loaded_model=None,
        clock=lambda: datetime(2026, 8, 10, 19, 0, tzinfo=UTC),
    )

    result = service.forecast("instrument-1")

    assert result.forecast.model_version == "ewma-close-0.94-v1"
    assert result.forecast.predicted_annualized_volatility > 0
    assert result.training_source_feed is None
    assert result.feed_match is None


def test_forecast_service_does_not_hide_provider_failure_without_cache():
    class UnavailableMarketData:
        def history(self, *args, **kwargs):
            raise MarketDataProviderError("Alpaca credentials are required")

    service = MarketForecastService(
        UnavailableMarketData(),
        loaded_model=loaded_model_stub(),
        clock=lambda: datetime(2026, 8, 10, 19, 0, tzinfo=UTC),
    )

    with pytest.raises(MarketDataProviderError, match="credentials"):
        service.forecast("instrument-1")


def test_volatility_forecast_endpoint_exposes_provenance(client):
    history = forecast_history()
    response_value = CurrentMarketVolatilityForecast(
        forecast=forecast_result(history),
        source=history.source,
        retrieved_at=history.retrieved_at,
        data_status="current",
        training_source_feed="sip",
        feed_match=False,
    )

    class ForecastServiceStub:
        def forecast(self, instrument_id):
            assert instrument_id == "instrument-1"
            return response_value

    app.dependency_overrides[get_market_forecast_service] = lambda: ForecastServiceStub()
    try:
        response = client.get("/v1/market/instruments/instrument-1/volatility-forecast")
    finally:
        app.dependency_overrides.pop(get_market_forecast_service, None)

    assert response.status_code == 200
    assert response.json() == {
        "symbol": "AAPL",
        "observed_on": history.points[-1].observed_on.isoformat(),
        "horizon_trading_days": 20,
        "predicted_annualized_volatility": 0.237,
        "annualized": True,
        "model_version": "model-v1",
        "source": "alpaca:iex",
        "retrieved_at": history.retrieved_at.isoformat().replace("+00:00", "Z"),
        "data_status": "current",
        "training_source_feed": "sip",
        "feed_match": False,
    }


def test_volatility_forecast_endpoint_reports_provider_failure(client):
    class ForecastServiceStub:
        def forecast(self, instrument_id):
            raise MarketDataProviderError("Alpaca credentials are required")

    app.dependency_overrides[get_market_forecast_service] = lambda: ForecastServiceStub()
    try:
        response = client.get("/v1/market/instruments/instrument-1/volatility-forecast")
    finally:
        app.dependency_overrides.pop(get_market_forecast_service, None)

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "market_forecast_data_unavailable"


def test_fresh_demo_forecast_works_without_trained_model(client, monkeypatch):
    def unavailable_model():
        raise MarketForecastArtifactError("Run the model build command first")

    monkeypatch.setattr(
        "financial_ai.main.get_loaded_market_forecast_model",
        unavailable_model,
    )
    instrument_id = client.get(
        "/v1/market/instruments",
        params={"query": "world"},
    ).json()[0]["id"]

    response = client.get(f"/v1/market/instruments/{instrument_id}/volatility-forecast")

    assert response.status_code == 200
    payload = response.json()
    assert payload["model_version"] == "ewma-close-0.94-v1"
    assert payload["predicted_annualized_volatility"] > 0
    assert payload["training_source_feed"] is None
    assert payload["feed_match"] is None
    assert payload["source"] == "demo"


def test_volatility_forecast_endpoint_reports_unknown_instrument(client):
    response = client.get("/v1/market/instruments/unknown/volatility-forecast")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "instrument_not_found"
