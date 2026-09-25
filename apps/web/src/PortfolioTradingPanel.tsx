import { useEffect, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, api } from "./api";
import InstrumentForecast from "./InstrumentForecast";
import type { MarketInstrument, PortfolioHolding, PortfolioOrderCreate } from "./types";

const formatMoney = (value: string, currency: string) =>
  new Intl.NumberFormat("en-IE", { style: "currency", currency }).format(Number(value));

function clientOrderId() {
  return globalThis.crypto?.randomUUID?.() ?? `order-${Date.now()}-${Math.random()}`;
}

export default function PortfolioTradingPanel({ portfolioId }: { portfolioId: string }) {
  const queryClient = useQueryClient();
  const [searchText, setSearchText] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [instrument, setInstrument] = useState<MarketInstrument | null>(null);
  const [forecastInstrument, setForecastInstrument] = useState<MarketInstrument | null>(null);
  const [side, setSide] = useState<"buy" | "sell">("buy");
  const [quantity, setQuantity] = useState("1");
  const [showTrade, setShowTrade] = useState(false);

  useEffect(() => {
    const timeout = window.setTimeout(() => setDebouncedSearch(searchText.trim()), 400);
    return () => window.clearTimeout(timeout);
  }, [searchText]);

  const overview = useQuery({
    queryKey: ["portfolio-overview", portfolioId],
    queryFn: () => api.portfolioOverview(portfolioId),
  });
  const instruments = useQuery({
    queryKey: ["market-instruments", overview.data?.market_data_mode, debouncedSearch],
    queryFn: () => api.marketInstruments(debouncedSearch, overview.data!.market_data_mode),
    enabled:
      overview.data?.market_data_mode === "external" && debouncedSearch.length >= 2,
    retry: false,
    staleTime: 60_000,
  });
  const demoCatalog = useQuery({
    queryKey: ["market-instruments", "demo", "catalog"],
    queryFn: () => api.marketInstruments("*", "demo"),
    enabled: overview.data?.market_data_mode === "demo",
    retry: false,
    staleTime: Number.POSITIVE_INFINITY,
  });
  const selectedQuote = useQuery({
    queryKey: ["market-quote", instrument?.id],
    queryFn: () => api.marketQuote(instrument!.id),
    enabled: Boolean(instrument),
    retry: (failureCount, error) =>
      failureCount < 1 &&
      (!(error instanceof ApiError) || error.status >= 500),
  });
  const executeOrder = useMutation({
    mutationFn: (payload: PortfolioOrderCreate) =>
      api.executePortfolioOrder(portfolioId, payload),
    onSuccess: () => {
      setInstrument(null);
      setForecastInstrument(null);
      setQuantity("1");
      setSearchText("");
      setShowTrade(false);
      void Promise.all([
        queryClient.invalidateQueries({ queryKey: ["portfolios"] }),
        queryClient.invalidateQueries({ queryKey: ["portfolio-overview", portfolioId] }),
        queryClient.invalidateQueries({ queryKey: ["analytics", portfolioId] }),
        queryClient.invalidateQueries({ queryKey: ["transactions"] }),
        queryClient.invalidateQueries({ queryKey: ["accounts"] }),
      ]);
    },
  });

  const submitOrder = (event: FormEvent) => {
    event.preventDefault();
    if (!instrument) return;
    executeOrder.mutate({
      client_order_id: clientOrderId(),
      instrument_id: instrument.id,
      side,
      quantity,
    });
  };
  const prepareHoldingOrder = (holding: PortfolioHolding, orderSide: "buy" | "sell") => {
    setShowTrade(true);
    setInstrument(holding.instrument);
    setForecastInstrument(holding.instrument);
    setSide(orderSide);
    setQuantity(orderSide === "buy" ? "1" : holding.quantity);
    setSearchText(holding.instrument.symbol);
  };
  const openForecast = (selected: MarketInstrument) => {
    setForecastInstrument(selected);
    setShowTrade(true);
  };
  const selectInstrument = (selected: MarketInstrument | null) => {
    setInstrument(selected);
    setForecastInstrument(selected);
    if (
      selected &&
      !overview.data?.holdings.some((holding) => holding.instrument.id === selected.id)
    ) {
      setSide("buy");
    }
  };

  if (overview.isLoading) return <div className="loading">Loading portfolio ledger…</div>;
  if (overview.isError) return <div className="error">{overview.error.message}</div>;
  if (!overview.data) return null;
  const portfolio = overview.data;
  const selectedHolding = instrument
    ? portfolio.holdings.find((holding) => holding.instrument.id === instrument.id)
    : undefined;

  return (
    <>
      <section className="metrics-grid paper-metrics">
        <Metric label="Total equity" value={portfolio.total_equity} currency={portfolio.base_currency} note="Cash plus holdings" />
        <Metric label="Available cash" value={portfolio.cash_balance} currency={portfolio.base_currency} note="Opening cash plus ledger cash flows" />
        <Metric label="Holdings" value={portfolio.holdings_value} currency={portfolio.base_currency} note={`${portfolio.holdings.length} open positions`} />
        <Metric label="Realized P&L" value={portfolio.realized_pnl} currency={portfolio.base_currency} note="Average-cost method" />
      </section>

      <button className="floating-trade-button" type="button" onClick={() => setShowTrade(true)}>
        <span aria-hidden="true">⌕</span> Trade
      </button>
      {showTrade ? (
        <div className="trade-sheet-backdrop" onMouseDown={() => setShowTrade(false)}>
          <section className="trade-sheet" onMouseDown={(event) => event.stopPropagation()}>
        <div className="panel-title"><div><span className="eyebrow">TRADE</span><h2>Buy or sell</h2></div><button className="secondary compact" type="button" onClick={() => setShowTrade(false)}>Close</button></div>
        <span className="page-meta">Available cash: {formatMoney(portfolio.cash_balance, portfolio.base_currency)}</span>
        <div className="instrument-search">
          {portfolio.market_data_mode === "demo" ? (
            <label>
              Demo instrument
              <select
                value={instrument?.id ?? ""}
                disabled={demoCatalog.isLoading || demoCatalog.isError}
                onChange={(event) => {
                  selectInstrument(
                    demoCatalog.data?.find((item) => item.id === event.target.value) ?? null,
                  );
                }}
              >
                <option value="">
                  {demoCatalog.isLoading
                    ? "Loading demo catalog…"
                    : demoCatalog.isError
                      ? "Demo catalog unavailable"
                      : "Select a synthetic instrument"}
                </option>
                {demoCatalog.data?.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.symbol} · {item.name} · {item.currency}
                  </option>
                ))}
              </select>
            </label>
          ) : (
            <label>
              Search by symbol or name
              <input
                value={searchText}
                onChange={(event) => {
                  setSearchText(event.target.value);
                  selectInstrument(null);
                }}
                placeholder="Example: Apple or AAPL"
              />
            </label>
          )}
          <small className="order-note">
            {portfolio.market_data_mode === "external"
              ? "Searches the Alpaca US instrument catalog."
              : "All selectable instruments use deterministic synthetic prices."}
          </small>
          {portfolio.market_data_mode === "external" && !instrument ? (
            <div className="instrument-results">
              {instruments.isFetching ? <span>Searching…</span> : null}
              {instruments.isError ? <span className="negative">Search unavailable</span> : null}
              {!instruments.isFetching &&
              !instruments.isError &&
              debouncedSearch.length >= 2 &&
              instruments.data?.length === 0 ? (
                <span>No matching US instrument found.</span>
              ) : null}
              {instruments.data?.map((item) => (
              <button type="button" className="instrument" key={item.id} onClick={() => selectInstrument(item)}>
                <b>{item.symbol}</b><span>{item.name}</span><small>{item.exchange || item.provider} · {item.currency}</small>
              </button>
              ))}
            </div>
          ) : null}
        </div>
        {instrument ? (
          <form className="paper-order-form" noValidate onSubmit={submitOrder}>
            <div className="order-instrument-summary">
              <div>
                <b>{instrument.symbol}</b>
                <span>{instrument.name}</span>
                <small>{selectedHolding ? `${Number(selectedHolding.quantity).toLocaleString()} units held` : "Not currently held"}</small>
              </div>
              <div className="selected-quote">
                <b aria-label="Selected instrument price">
                  {selectedQuote.isLoading
                    ? "Loading latest close…"
                    : selectedQuote.data
                      ? formatMoney(selectedQuote.data.close, instrument.currency)
                      : "Price unavailable"}
                </b>
                {selectedQuote.data ? (
                  <span>
                    Latest close · {selectedQuote.data.observed_on}
                    {selectedQuote.data.is_stale ? " · stale" : ""}
                  </span>
                ) : null}
                {selectedQuote.isError ? (
                  <span className="negative">{selectedQuote.error.message}</span>
                ) : null}
              </div>
            </div>
            <div className="order-controls">
              <fieldset className="side-field">
                <legend>Order side</legend>
                <div className="side-toggle">
                  <button className={side === "buy" ? "active" : ""} type="button" aria-pressed={side === "buy"} onClick={() => setSide("buy")}>Buy</button>
                  <button className={side === "sell" ? "active" : ""} type="button" aria-pressed={side === "sell"} disabled={!selectedHolding} onClick={() => {
                    setSide("sell");
                    if (selectedHolding && Number(quantity) > Number(selectedHolding.quantity)) {
                      setQuantity(selectedHolding.quantity);
                    }
                  }}>Sell</button>
                </div>
              </fieldset>
              <fieldset className="quantity-field">
                <legend>Quantity</legend>
                <div className="quantity-presets">
                  {[1, 3, 5, 10].map((value) => (
                    <button
                      className={quantity === String(value) ? "active" : ""}
                      type="button"
                      key={value}
                      aria-label={`Set quantity to ${value}`}
                      disabled={side === "sell" && Boolean(selectedHolding) && value > Number(selectedHolding?.quantity)}
                      onClick={() => setQuantity(String(value))}
                    >
                      {value}
                    </button>
                  ))}
                </div>
                <input aria-label="Custom quantity" required min="1" max={side === "sell" ? selectedHolding?.quantity : undefined} step="1" type="number" value={quantity} onChange={(event) => setQuantity(event.target.value)} />
              </fieldset>
            </div>
            <div className="order-total">
              <span>Estimated order value</span>
              <strong aria-label="Estimated order value">
                {selectedQuote.data && Number(quantity) > 0
                  ? formatMoney(
                      String(Number(selectedQuote.data.close) * Number(quantity)),
                      instrument.currency,
                    )
                  : "—"}
              </strong>
            </div>
            <button className="submit-order" disabled={executeOrder.isPending || selectedQuote.isLoading || selectedQuote.isError || Number(quantity) < 1 || (side === "sell" && Boolean(selectedHolding) && Number(quantity) > Number(selectedHolding?.quantity))}>{executeOrder.isPending ? "Executing…" : side === "buy" ? "Buy position" : "Sell position"}</button>
            {instrument.currency !== portfolio.base_currency ? <span className="order-note">The backend converts {instrument.currency} settlement into {portfolio.base_currency} using the stored FX reference rate.</span> : null}
          </form>
        ) : null}
        {executeOrder.isError ? <div className="error">{executeOrder.error.message}</div> : null}
        {forecastInstrument ? (
        <InstrumentForecast
          instrumentId={forecastInstrument.id}
          symbol={forecastInstrument.symbol}
          onClose={() => setForecastInstrument(null)}
        />
      ) : null}
          </section>
        </div>
      ) : null}

      <HoldingsTable
        holdings={portfolio.holdings}
        currency={portfolio.base_currency}
        canForecast
        onForecast={openForecast}
        onOrder={prepareHoldingOrder}
      />
      <ul className="warnings">{portfolio.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>
    </>
  );
}

function Metric({ label, value, currency, note }: { label: string; value: string; currency: string; note: string }) {
  return <div className="metric"><p>{label}</p><strong>{formatMoney(value, currency)}</strong><span>{note}</span></div>;
}

function HoldingsTable({ holdings, currency, canForecast, onForecast, onOrder }: { holdings: PortfolioHolding[]; currency: string; canForecast: boolean; onForecast: (instrument: MarketInstrument) => void; onOrder: (holding: PortfolioHolding, side: "buy" | "sell") => void }) {
  return <section className="panel"><div className="panel-title"><div><span className="eyebrow">HOLDINGS</span><h3>Current positions</h3></div></div><div className="table-wrap"><table><thead><tr><th>Instrument</th><th>Quantity</th><th>Average cost</th><th>Latest close</th><th>Value</th><th>Unrealized P&amp;L</th><th></th></tr></thead><tbody>
    {holdings.map((holding) => <tr key={holding.instrument.id}><td><b>{holding.instrument.symbol}</b><small>{holding.instrument.name}</small></td><td>{Number(holding.quantity).toLocaleString()}</td><td>{formatMoney(holding.average_cost, currency)}</td><td>{formatMoney(holding.latest_price, currency)}<small>{holding.price_observed_on} · {holding.price_source}</small></td><td>{formatMoney(holding.market_value, currency)}</td><td className={Number(holding.unrealized_pnl) >= 0 ? "positive" : "negative"}>{formatMoney(holding.unrealized_pnl, currency)}</td><td><div className="position-actions">{canForecast ? <button className="secondary compact" type="button" onClick={() => onForecast(holding.instrument)}>Forecast</button> : null}<button className="secondary compact" type="button" onClick={() => onOrder(holding, "buy")}>Buy more</button><button className="secondary compact" type="button" onClick={() => onOrder(holding, "sell")}>Sell</button></div></td></tr>)}
    {!holdings.length ? <tr><td colSpan={7} className="empty-state">No open positions yet.</td></tr> : null}
  </tbody></table></div></section>;
}
