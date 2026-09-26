import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import PortfolioTradingPanel from "./PortfolioTradingPanel";

afterEach(() => {
  vi.unstubAllGlobals();
});

const instrument = {
  id: "instrument-1",
  provider: "alpaca",
  symbol: "AAPL",
  name: "Apple Inc.",
  exchange: "NASDAQ",
  currency: "USD",
  asset_class: "US Equity",
  region: "United States",
  is_active: true,
  updated_at: "2026-08-14T08:00:00Z",
};

test.each(["external", "demo"] as const)(
  "opens the same instrument forecast from holdings and order preparation in %s mode",
  async (mode) => {
    const selectedInstrument = { ...instrument, provider: mode === "demo" ? "demo" : "alpaca" };
    vi.stubGlobal(
      "fetch",
      vi.fn((input: string | URL | Request) => {
        const url = String(input);
        if (url.endsWith("/v1/portfolios/portfolio-1/overview")) {
          return Promise.resolve({
            ok: true,
            json: () =>
              Promise.resolve({
                id: "portfolio-1",
                name: `${mode} Portfolio`,
                base_currency: "USD",
                market_data_mode: mode,
                opening_cash: "10000.00",
                created_at: "2026-08-14T08:00:00Z",
                trade_count: 0,
                cash_balance: "8000.00",
                holdings_value: "2000.00",
                total_equity: "10000.00",
                total_pnl: "100.00",
                realized_pnl: "0.00",
                holdings: [
                  {
                    instrument: selectedInstrument,
                    quantity: "10",
                    average_cost: "190.00",
                    latest_price: "200.00",
                    market_value: "2000.00",
                    unrealized_pnl: "100.00",
                    weight: 0.2,
                    price_observed_on: "2026-08-13",
                    price_source: "alpaca:iex",
                    quote_is_stale: false,
                  },
                ],
                trades: [],
                warnings: [],
              }),
          });
        }
        if (url.endsWith("/v1/market/instruments/instrument-1/volatility-forecast")) {
          return Promise.resolve({
            ok: true,
            json: () =>
              Promise.resolve({
                symbol: "AAPL",
                observed_on: "2026-08-13",
                horizon_trading_days: 20,
                predicted_annualized_volatility: 0.237,
                annualized: true,
                model_version: mode === "demo" ? "ewma-close-0.94-v1" : "market-volatility-xgboost-v1",
                source: "alpaca:iex",
                retrieved_at: "2026-08-14T08:00:00Z",
                data_status: "current",
                training_source_feed: mode === "demo" ? null : "sip",
                feed_match: mode === "demo" ? null : false,
              }),
          });
        }
        if (url.endsWith("/v1/market/instruments/instrument-1/quote")) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ instrument: selectedInstrument, observed_on: "2026-08-13", close: "200.00", source: "alpaca:iex", retrieved_at: "2026-08-14T08:00:00Z", is_stale: false }),
          });
        }
        return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
      }),
    );

    render(
      <QueryClientProvider client={new QueryClient()}>
        <PortfolioTradingPanel portfolioId="portfolio-1" />
      </QueryClientProvider>,
    );

    fireEvent.click(await screen.findByRole("button", { name: "Forecast" }));
    expect(await screen.findByText("6.7%")).toBeInTheDocument();
    expect(screen.getByText("23.7% annualized")).toBeInTheDocument();
    expect(screen.getByText(mode === "demo" ? "Method: EWMA reference." : "Method: XGBoost model.")).toBeInTheDocument();
    fireEvent.click(within(screen.getByLabelText("AAPL volatility forecast")).getByRole("button", { name: "Close" }));
    expect(screen.queryByLabelText("AAPL volatility forecast")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Buy more" }));
    expect(await screen.findByLabelText("AAPL volatility forecast")).toBeInTheDocument();
  },
);
