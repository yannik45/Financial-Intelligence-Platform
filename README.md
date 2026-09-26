# Financial Intelligence Platform

A portfolio management platform that brings simulated trading, account cash
flows, risk analytics, market data, and explainable ML suggestions into one
workspace. The backend owns financial calculations and ledger state; the
browser presents results and collects review decisions.

![Portfolio dashboard with valuation, risk metrics, and allocation charts](docs/assets/portfolio-overview.png)

## What you can explore

| Area | Implemented behavior |
|---|---|
| Portfolio workspace | Create or import a portfolio, inspect holdings, allocation, valuation history, and separate market-risk, diversification, and liquidity indicators |
| Simulated trading | Search instruments, place buy/sell orders using backend prices, and see cash, holdings, and P&L update from one signed ledger |
| Transaction intelligence | Explore checking, savings, and linked brokerage activity; generate a reproducible synthetic bank feed; edit classification suggestions |
| Market data and forecasts | Use credential-free demo prices or optional Alpaca daily data; inspect source and freshness; view a clearly labeled volatility estimate |

![Instrument discovery and simulated order workflow](docs/assets/trading-and-forecast.png)

Orders are simulated and never reach a broker. The included sample data makes
the application usable without market-data credentials or customer data.

## Run the application

With Docker and Compose installed, from the repository root:

```powershell
docker compose up --build --wait
```

Open the dashboard at **http://localhost:5173**. The API health endpoint is at
**http://localhost:8000/health**, and its OpenAPI page is at
**http://localhost:8000/docs**. Select a demo portfolio, open the trading panel,
and inspect activity or a forecast. `docker compose down` stops the stack while
retaining its SQLite database and generated model artifacts in a named volume.

The included synthetic price series supports a labeled EWMA volatility
estimate. The XGBoost model from the historical study can be installed
separately for external instruments. The fixed sample prices end on
2026-06-30; later estimates are marked stale.

Optional external daily bars require backend-only Alpaca credentials in a local
`.env` (see [.env.example](.env.example)). External orders are still simulated.

## How it is built

```text
React / Vite -> Nginx /api proxy -> FastAPI -> SQLite ledger and cached prices
                                           |-> deterministic analytics
                                           |-> classification and forecast services

Offline commands -> versioned data -> evaluation -> verified model artifacts
```

The frontend uses React, TypeScript, TanStack Query, and Recharts. The backend
uses Python 3.12, FastAPI, SQLAlchemy, Alembic, pandas, scikit-learn, and
XGBoost. `uv.lock` and `package-lock.json` pin the environments. Docker Compose
runs unprivileged API and web containers with persistent runtime storage.

Every portfolio links to one brokerage account. A simulated order writes a
regular signed security transaction; holdings, cash, and analytics are derived
from that shared record. Market observations carry source and freshness metadata.
The UI does not calculate financial metrics or supply execution prices.

## ML evidence

The transaction classifier combines direction-aware rules, character TF-IDF,
and a multilingual semantic model. A frozen 252-case synthetic product challenge
for the earlier rules-plus-lexical policy reached **69.8% overall accuracy**;
it auto-accepted **60.7%** of cases at **96.1% accuracy among accepted cases**.
The semantic model reached **95.5% accuracy** on a separate set of **44
curated in-scope descriptions**. These evaluations use synthetic or curated
data; they do not measure accuracy on real bank transactions.

The volatility study compared EWMA, Ridge, and XGBoost on a historical US-equity
sample using chronological splits and a 20-trading-day purge. Its committed
final-test record reports XGBoost mean absolute error of **0.0690**, versus
**0.0699** for Ridge. The licensed SIP snapshot needed to calculate those
figures is not included. The included price series uses
the separate EWMA estimate.

Start with the [ML overview](docs/ml/README.md) for serving behavior,
evaluation results, and data sources.

## Develop and verify

Requires Python 3.12, [uv](https://docs.astral.sh/uv/), Node.js 22+, and npm:

```powershell
uv sync --locked --all-groups --extra semantic
uv run --extra semantic alembic upgrade head
uv run --extra semantic financial-ai-bootstrap-category-model
uv run --extra semantic financial-ai-api
```

In another terminal:

```powershell
cd apps/web
npm.cmd ci
npm.cmd run dev
```

Run backend tests with `uv run pytest` and frontend checks with `npm.cmd test`
and `npm.cmd run build` from `apps/web`. CI also builds the containers and
smoke-tests a demo forecast through the browser-facing proxy.

The current deployment uses SQLite and has no authentication, so it is intended
for a single instance with sample data. Handling real customer data or live
trading would require access control, licensed data, security and privacy
controls, and independent model validation. Forecasts are informational and do
not place orders.

For more detail, see the [system overview](docs/architecture/system-overview.md),
[container setup](docs/architecture/containerization.md),
[risk-indicator method](docs/architecture/portfolio-risk-score.md), and
[data provenance notes](data/README.md).
