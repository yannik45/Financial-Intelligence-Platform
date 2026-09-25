# System overview

The project is a local-first, single-instance portfolio demo. Financial state
and calculations belong to FastAPI services; React displays their results and
submits user choices. No broker orders are placed.

```text
Browser -> React / Nginx -> FastAPI -> SQLite ledger + cached market data
                              |-> portfolio analytics and risk indicators
                              |-> simulated trading
                              |-> transaction classification
                              `-> volatility estimates

Offline ML commands -> versioned data, reports, and optional model artifacts
```

| Area | Code | Responsibility |
|---|---|---|
| UI | `apps/web/src` | Portfolio, trading, activity, and review views |
| API and domain services | `apps/api/src/financial_ai` | Validation, ledger writes, market data, analytics, and HTTP contracts |
| Database schema | `apps/api/alembic` | Versioned SQLite migrations |
| ML workflows | `apps/api/src/financial_ai/ml` | Data preparation, evaluation, artifacts, and feedback |
| Committed evidence | `data/market`, `data/evaluation` | ECB reference data, taxonomy benchmarks, and aggregate market-study records |
| Local runtime | `data/runtime` | SQLite, generated datasets, models, and reports; ignored by Git |

## Ledger and portfolio calculations

Each portfolio links to one brokerage account. Opening positions plus signed
security transactions determine holdings; opening cash plus all signed ledger
cash flows determines the account balance. A simulated buy or sale therefore
updates activity, cash, holdings, P&L, and risk analytics together. The backend
obtains the latest daily close and stored FX rate, rejects insufficient cash or
holdings, and makes identical client-order retries idempotent. The browser
cannot provide an execution price. Fees, taxes, spreads, and slippage are zero
in this simulation.

`booked_at` is the order date in the configured app timezone; `created_at` is
the UTC event time; `price_observed_on` is the source market date. A cached
price does not backdate a ledger entry. The UI stores only the selected
portfolio ID locally and validates it against the API on startup.

Analytics replay current holdings, then calculate valuation, allocation,
cost basis, return, volatility, drawdown, and concentration from backend price
and FX data. Historical charts reconstruct today's quantities backwards: they
are **not** the portfolio's actual historical account performance. The
[risk-indicator method](portfolio-risk-score.md) separates measured market
risk, diversification quality, and liquidity resilience.

## Market data and ML

A portfolio chooses either deterministic synthetic `demo` prices or optional
Alpaca `external` daily observations. Instruments and observations are cached
with source, observation date, and retrieval time; the UI exposes freshness.
Stored ECB reference rates support EUR conversions. The demo price snapshot
ends on 2026-06-30 and is labeled stale afterward.

The classifier runs bilingual rules before its lexical and semantic models.
Bank-feed suggestions need model agreement for automatic acceptance; manual
suggestions remain editable. The backend repeats classification when saving
and stores prediction and review provenance. Feedback enters an offline export,
review, candidate, and explicit-promotion process, never online retraining.

The forecast endpoint uses a close-price EWMA reference in a fresh checkout.
External instruments use the checksum-verified XGBoost artifact when it is
installed. The raw historical SIP training data and artifact are not bundled;
the [ML overview](../ml/README.md) explains what was evaluated and what the
demo serves. Quote and forecast queries are independent, so a forecast error
does not disable an otherwise valid simulated order.

## Delivery boundary

Docker Compose runs an unprivileged FastAPI container and an unprivileged
Nginx container. Nginx serves the React build and proxies `/api`; a named
volume preserves SQLite and generated artifacts. CI tests both applications,
builds the images, and probes health and a demo forecast through the proxy.
See the [container setup](containerization.md) for operational details.

There is no authentication or real customer-data workflow. SQLite and the
shared volume target one instance. Production use would need access control,
licensed data, privacy and security controls, durable external storage,
monitoring, and independent model validation.
