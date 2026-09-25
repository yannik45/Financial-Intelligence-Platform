import { useQuery } from "@tanstack/react-query";
import { ApiError, api } from "./api";

type InstrumentForecastProps = {
  instrumentId: string;
  symbol: string;
  onClose: () => void;
};

const formatPercent = (value: number) => `${(value * 100).toFixed(1)}%`;

const periodVolatility = (annualizedVolatility: number, tradingDays: number) =>
  annualizedVolatility * Math.sqrt(tradingDays / 252);

function errorContent(error: Error) {
  if (!(error instanceof ApiError)) {
    return { title: "Forecast unavailable", message: "The request could not reach the API.", retryable: true };
  }
  if (error.code === "market_forecast_model_unavailable") {
    return { title: "Forecast model is not initialized", message: error.message, retryable: false };
  }
  if (error.code === "market_forecast_history_insufficient") {
    return { title: "Insufficient market history", message: error.message, retryable: false };
  }
  return { title: "Current market data is unavailable", message: error.message, retryable: true };
}

export default function InstrumentForecast({ instrumentId, symbol, onClose }: InstrumentForecastProps) {
  const forecast = useQuery({
    queryKey: ["market-volatility-forecast", instrumentId],
    queryFn: () => api.marketVolatilityForecast(instrumentId),
    retry: (failureCount, error) => {
      if (error instanceof ApiError) {
        return error.code === "market_forecast_data_unavailable" && failureCount < 2;
      }
      return failureCount < 2;
    },
    staleTime: 15 * 60_000,
  });
  const failure = forecast.isError ? errorContent(forecast.error) : null;

  return (
    <section className="panel instrument-forecast" aria-label={`${symbol} volatility forecast`}>
      <div className="panel-title">
        <div><span className="eyebrow">MARKET VOLATILITY FORECAST</span><h3>{symbol} risk outlook</h3></div>
        <button className="secondary compact" type="button" onClick={onClose}>Close</button>
      </div>
      {forecast.isLoading ? <div className="forecast-loading">Loading forecast…</div> : null}
      {failure ? (
        <div className="forecast-error">
          <b>{failure.title}</b><span>{failure.message}</span>
          {failure.retryable ? <button className="secondary compact" type="button" onClick={() => forecast.refetch()}>Retry</button> : null}
        </div>
      ) : null}
      {forecast.data ? (
        <>
          <div className="forecast-summary">
            <div>
              <strong>
                {formatPercent(
                  periodVolatility(
                    forecast.data.predicted_annualized_volatility,
                    forecast.data.horizon_trading_days,
                  ),
                )}
              </strong>
              <span>{forecast.data.data_status === "stale" ? `Historical ${forecast.data.horizon_trading_days}-day volatility estimate as of ${forecast.data.observed_on}` : `Expected volatility over the next ${forecast.data.horizon_trading_days} trading days`}</span>
            </div>
            <div>
              <b>{formatPercent(forecast.data.predicted_annualized_volatility)} annualized</b>
              <span>Data through {forecast.data.observed_on}</span>
            </div>
            <span className={`forecast-status ${forecast.data.data_status === "stale" ? "stale" : ""}`}>
              {forecast.data.data_status === "stale" ? "Stale market data" : "Current market data"}
            </span>
          </div>
          <p className="forecast-interpretation">Method: {forecast.data.model_version.startsWith("ewma-") ? "EWMA reference" : "XGBoost model"}.</p>
          <p className="forecast-interpretation">This estimates future variation, not direction, return, or probability of loss.</p>
          <details className="forecast-methodology">
            <summary>Methodology and limitations</summary>
            <p>The horizon value converts annualized volatility using the square-root-of-time convention and is not a guaranteed price range.</p>
            <p>Method {forecast.data.model_version} · Source {forecast.data.source} · Retrieved {new Date(forecast.data.retrieved_at).toLocaleString("en-IE")}</p>
            {forecast.data.model_version.startsWith("ewma-") ? <p>This EWMA reference uses past daily closing prices. Demo prices are synthetic. The XGBoost evaluation results do not apply to this estimate.</p> : null}
            {forecast.data.feed_match === false && forecast.data.training_source_feed ? <p>The model was trained on {forecast.data.training_source_feed.toUpperCase()} data, while this forecast uses a different provider feed. Coverage and volume may differ.</p> : null}
          </details>
        </>
      ) : null}
    </section>
  );
}
