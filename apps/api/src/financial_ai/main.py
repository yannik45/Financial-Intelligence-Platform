import json
import logging
import time
from contextlib import asynccontextmanager
from datetime import date
from secrets import randbelow
from typing import Annotated, Literal
from uuid import UUID, uuid4, uuid5

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from financial_ai.analytics import AnalyticsError, calculate_analytics
from financial_ai.clock import business_today
from financial_ai.config import get_settings
from financial_ai.database import SessionLocal, get_session
from financial_ai.demo_bank_feed import generate_demo_bank_feed
from financial_ai.importer import PortfolioImportError, parse_portfolio_csv
from financial_ai.market_data import market_data_provider
from financial_ai.market_data_service import (
    InstrumentNotFoundError,
    MarketDataProviderError,
    MarketDataService,
    build_market_data_service,
)
from financial_ai.market_forecast_service import (
    MarketForecastService,
    get_loaded_market_forecast_model,
)
from financial_ai.ml.market_forecast.data.daily_bars import DailyBarValidationError
from financial_ai.ml.market_forecast.modeling.inference import InsufficientForecastHistoryError
from financial_ai.ml.market_forecast.modeling.model_artifact import MarketForecastArtifactError
from financial_ai.ml.transaction_classification.core.category_service import (
    TransactionClassification,
    TransactionClassifier,
    get_transaction_classifier,
)
from financial_ai.ml.transaction_classification.core.contracts import (
    TAXONOMY_VERSION,
    ClassificationInputSource,
    ClassificationMethod,
    determine_feedback_status,
    route_transaction_text,
)
from financial_ai.ml.transaction_classification.modeling.category_artifact import ModelArtifactError
from financial_ai.models import (
    Account,
    MarketInstrument,
    Portfolio,
    Transaction,
    TransactionClassificationRecord,
)
from financial_ai.portfolio_trading import (
    CurrencyMismatchError,
    IdempotencyConflictError,
    InsufficientCashError,
    InsufficientHoldingsError,
    PortfolioNotFoundError,
    PortfolioTradingError,
    PortfolioTradingService,
)
from financial_ai.risk_score import calculate_risk_score
from financial_ai.schemas import (
    AccountRead,
    AnalyticsResponse,
    CatalogAsset,
    DemoBankFeedCreate,
    DemoBankFeedResult,
    MarketDataStatus,
    MarketHistoryRead,
    MarketInstrumentRead,
    MarketQuoteRead,
    MarketVolatilityForecastRead,
    PortfolioCreate,
    PortfolioOrderCreate,
    PortfolioRead,
    PortfolioSummary,
    PortfolioTradeRead,
    TradingPortfolioRead,
    TransactionCategoryReview,
    TransactionClassificationRequest,
    TransactionClassificationResponse,
    TransactionClassificationStatusRead,
    TransactionCreate,
    TransactionPage,
    TransactionRead,
    TransactionType,
)
from financial_ai.seed import seed_demo_accounts, seed_demo_portfolios

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("financial_ai")
SessionDependency = Annotated[Session, Depends(get_session)]
ClassifierDependency = Annotated[TransactionClassifier, Depends(get_transaction_classifier)]


def get_portfolio_trading_service(
    session: SessionDependency,
) -> PortfolioTradingService:
    return PortfolioTradingService(session)


PortfolioTradingDependency = Annotated[
    PortfolioTradingService, Depends(get_portfolio_trading_service)
]


@asynccontextmanager
async def lifespan(_: FastAPI):
    with SessionLocal() as session:
        seed_demo_portfolios(session)
        seed_demo_accounts(session)
    yield


app = FastAPI(title="Financial Intelligence Platform API", version="0.1.0", lifespan=lifespan)
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    correlation_id = request.headers.get("X-Correlation-ID", str(uuid4()))
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception(json.dumps({"event": "request_failed", "correlation_id": correlation_id}))
        raise
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    response.headers["X-Correlation-ID"] = correlation_id
    logger.info(
        json.dumps(
            {
                "event": "request_completed",
                "correlation_id": correlation_id,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": elapsed_ms,
            }
        )
    )
    return response


@app.exception_handler(PortfolioImportError)
async def import_error_handler(_: Request, exc: PortfolioImportError):
    return JSONResponse(
        status_code=422,
        content={"code": "invalid_portfolio_csv", "message": str(exc), "details": exc.details},
    )


@app.get("/health")
def health(session: SessionDependency) -> dict[str, str]:
    session.execute(text("SELECT 1"))
    return {"status": "ok", "database": "ok"}


@app.get("/v1/market/catalog", response_model=list[CatalogAsset])
def market_catalog() -> list[CatalogAsset]:
    return [CatalogAsset(**asset.__dict__) for asset in market_data_provider.catalog()]


def market_error(exc: Exception) -> HTTPException:
    if isinstance(exc, InstrumentNotFoundError):
        return HTTPException(
            status_code=404,
            detail={"code": "instrument_not_found", "message": str(exc)},
        )
    if isinstance(exc, ValueError):
        return HTTPException(
            status_code=422,
            detail={"code": "invalid_market_data_request", "message": str(exc)},
        )
    return HTTPException(
        status_code=502,
        detail={"code": "market_data_unavailable", "message": str(exc)},
    )


@app.get("/v1/market/instruments", response_model=list[MarketInstrumentRead])
def search_market_instruments(
    session: SessionDependency,
    query: Annotated[str, Query(min_length=1, max_length=80)],
    limit: Annotated[int, Query(ge=1, le=25)] = 10,
    mode: Literal["demo", "external"] = "demo",
) -> list[MarketInstrumentRead]:
    try:
        service = build_market_data_service(session, mode)
        return [MarketInstrumentRead.model_validate(item) for item in service.search(query, limit)]
    except (MarketDataProviderError, RuntimeError) as exc:
        raise market_error(exc) from exc


@app.get("/v1/market/status", response_model=MarketDataStatus)
def market_data_status() -> MarketDataStatus:
    settings = get_settings()
    return MarketDataStatus(
        external_available=bool(settings.alpaca_api_key and settings.alpaca_secret_key)
    )


def market_service_for_instrument(session: Session, instrument_id: str) -> MarketDataService:
    instrument = session.get(MarketInstrument, instrument_id)
    if instrument is None:
        raise InstrumentNotFoundError(f"Unknown instrument: {instrument_id}")
    mode = "demo" if instrument.provider == "demo" else "external"
    return build_market_data_service(session, mode)


def get_market_forecast_service(
    instrument_id: str,
    session: SessionDependency,
) -> MarketForecastService:
    try:
        market_data = market_service_for_instrument(session, instrument_id)
    except InstrumentNotFoundError as exc:
        raise market_error(exc) from exc
    instrument = session.get(MarketInstrument, instrument_id)
    assert instrument is not None
    loaded_model = None
    if instrument.provider != "demo":
        settings = get_settings()
        artifact = settings.market_forecast_model_artifact_path
        metadata = settings.market_forecast_model_metadata_path
        if artifact.exists() or metadata.exists():
            try:
                loaded_model = get_loaded_market_forecast_model()
            except MarketForecastArtifactError as exc:
                raise HTTPException(
                    status_code=503,
                    detail={
                        "code": "market_forecast_model_unavailable",
                        "message": str(exc),
                    },
                ) from exc
    return MarketForecastService(
        market_data,
        loaded_model,
        demo_mode=instrument.provider == "demo",
    )


MarketForecastDependency = Annotated[
    MarketForecastService,
    Depends(get_market_forecast_service),
]


@app.get("/v1/market/instruments/{instrument_id}/quote", response_model=MarketQuoteRead)
def get_market_quote(
    instrument_id: str,
    session: SessionDependency,
    refresh: bool = False,
) -> MarketQuoteRead:
    try:
        service = market_service_for_instrument(session, instrument_id)
        return service.quote(instrument_id, refresh=refresh)
    except (InstrumentNotFoundError, MarketDataProviderError) as exc:
        raise market_error(exc) from exc


@app.get("/v1/market/instruments/{instrument_id}/history", response_model=MarketHistoryRead)
def get_market_history(
    instrument_id: str,
    session: SessionDependency,
    date_from: date | None = None,
    date_to: date | None = None,
    refresh: bool = False,
) -> MarketHistoryRead:
    try:
        service = market_service_for_instrument(session, instrument_id)
        return service.history(instrument_id, date_from, date_to, refresh)
    except (InstrumentNotFoundError, MarketDataProviderError, ValueError) as exc:
        raise market_error(exc) from exc


@app.get(
    "/v1/market/instruments/{instrument_id}/volatility-forecast",
    response_model=MarketVolatilityForecastRead,
)
def get_market_volatility_forecast(
    instrument_id: str,
    service: MarketForecastDependency,
) -> MarketVolatilityForecastRead:
    try:
        result = service.forecast(instrument_id)
    except InstrumentNotFoundError as exc:
        raise market_error(exc) from exc
    except MarketDataProviderError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "market_forecast_data_unavailable",
                "message": str(exc),
            },
        ) from exc
    except (DailyBarValidationError, InsufficientForecastHistoryError) as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "market_forecast_history_insufficient",
                "message": str(exc),
            },
        ) from exc
    except MarketForecastArtifactError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "market_forecast_model_unavailable",
                "message": str(exc),
            },
        ) from exc
    forecast = result.forecast
    return MarketVolatilityForecastRead(
        symbol=forecast.symbol,
        observed_on=forecast.observed_on,
        horizon_trading_days=forecast.horizon_trading_days,
        predicted_annualized_volatility=forecast.predicted_annualized_volatility,
        model_version=forecast.model_version,
        source=result.source,
        retrieved_at=result.retrieved_at,
        data_status=result.data_status,
        training_source_feed=result.training_source_feed,
        feed_match=result.feed_match,
    )


def portfolio_trading_error(exc: PortfolioTradingError) -> HTTPException:
    if isinstance(exc, PortfolioNotFoundError):
        status_code = 404
    elif isinstance(
        exc,
        (
            InsufficientCashError,
            InsufficientHoldingsError,
            CurrencyMismatchError,
            IdempotencyConflictError,
        ),
    ):
        status_code = 409
    else:
        status_code = 422
    return HTTPException(
        status_code=status_code,
        detail={"code": exc.code, "message": str(exc)},
    )


@app.post("/v1/portfolios", response_model=TradingPortfolioRead, status_code=201)
def create_portfolio(
    payload: PortfolioCreate, service: PortfolioTradingDependency
) -> TradingPortfolioRead:
    try:
        return service.create_portfolio(payload)
    except PortfolioTradingError as exc:
        raise portfolio_trading_error(exc) from exc
    except (MarketDataProviderError, RuntimeError) as exc:
        raise market_error(exc) from exc


@app.get("/v1/portfolios/{portfolio_id}/overview", response_model=TradingPortfolioRead)
def get_portfolio_overview(
    portfolio_id: str, service: PortfolioTradingDependency
) -> TradingPortfolioRead:
    try:
        return service.detail(portfolio_id)
    except PortfolioTradingError as exc:
        raise portfolio_trading_error(exc) from exc
    except (InstrumentNotFoundError, MarketDataProviderError) as exc:
        raise market_error(exc) from exc


@app.post(
    "/v1/portfolios/{portfolio_id}/orders",
    response_model=PortfolioTradeRead,
    status_code=201,
)
def execute_portfolio_order(
    portfolio_id: str,
    payload: PortfolioOrderCreate,
    service: PortfolioTradingDependency,
) -> PortfolioTradeRead:
    try:
        return service.execute_order(portfolio_id, payload)
    except PortfolioTradingError as exc:
        raise portfolio_trading_error(exc) from exc
    except (InstrumentNotFoundError, MarketDataProviderError) as exc:
        raise market_error(exc) from exc


@app.get("/v1/portfolios", response_model=list[PortfolioSummary])
def list_portfolios(session: SessionDependency) -> list[PortfolioSummary]:
    portfolios = session.scalars(select(Portfolio).order_by(Portfolio.kind, Portfolio.name)).all()
    return [
        PortfolioSummary(
            id=portfolio.id,
            name=portfolio.name,
            base_currency=portfolio.base_currency,
            kind=portfolio.kind,
            market_data_mode=portfolio.market_data_mode,
            created_at=portfolio.created_at,
            position_count=len(portfolio.positions),
            account_id=portfolio.account_id,
        )
        for portfolio in portfolios
    ]


def get_portfolio_or_404(portfolio_id: str, session: Session) -> Portfolio:
    portfolio = session.get(Portfolio, portfolio_id)
    if portfolio is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "portfolio_not_found", "message": "Portfolio not found"},
        )
    return portfolio


@app.get("/v1/portfolios/{portfolio_id}", response_model=PortfolioRead)
def get_portfolio(portfolio_id: str, session: SessionDependency) -> Portfolio:
    return get_portfolio_or_404(portfolio_id, session)


@app.post("/v1/portfolios/import", response_model=PortfolioRead, status_code=201)
async def import_portfolio(
    name: Annotated[str, Form(min_length=1, max_length=120)],
    file: Annotated[UploadFile, File()],
    session: SessionDependency,
) -> Portfolio:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise PortfolioImportError([{"field": "file", "message": "A .csv file is required"}])
    content = await file.read()
    if len(content) > 1_000_000:
        raise PortfolioImportError([{"field": "file", "message": "CSV must not exceed 1 MB"}])
    portfolio = parse_portfolio_csv(content, name)
    portfolio.account = Account(
        name=f"{name.strip()} Brokerage",
        account_type="brokerage",
        currency=portfolio.base_currency,
        kind="imported",
        opening_balance=0,
    )
    session.add(portfolio)
    session.commit()
    session.refresh(portfolio)
    return portfolio


@app.get("/v1/portfolios/{portfolio_id}/analytics", response_model=AnalyticsResponse)
def portfolio_analytics(
    portfolio_id: str,
    session: SessionDependency,
) -> AnalyticsResponse:
    portfolio = get_portfolio_or_404(portfolio_id, session)
    try:
        analytics = calculate_analytics(
            portfolio,
            market_service=build_market_data_service(session, portfolio.market_data_mode),
        )
        cash_balance = 0
        if portfolio.account:
            cash_balance = portfolio.account.opening_balance + sum(
                (item.amount for item in portfolio.account.transactions), start=0
            )
        cash_value_eur = float(cash_balance) * market_data_provider.fx_on_or_before(
            portfolio.base_currency, analytics.as_of
        )
        analytics.risk_score = calculate_risk_score(
            analytics,
            base_currency=portfolio.base_currency,
            cash_value_eur=cash_value_eur,
        )
        return analytics
    except AnalyticsError as exc:
        raise HTTPException(
            status_code=422, detail={"code": "analytics_unavailable", "message": str(exc)}
        ) from exc
    except (InstrumentNotFoundError, MarketDataProviderError) as exc:
        raise market_error(exc) from exc


def get_account_or_404(account_id: str, session: Session) -> Account:
    account = session.get(Account, account_id)
    if account is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "account_not_found", "message": "Account not found"},
        )
    return account


@app.get("/v1/accounts", response_model=list[AccountRead])
def list_accounts(session: SessionDependency) -> list[AccountRead]:
    accounts = session.scalars(select(Account).order_by(Account.account_type, Account.name)).all()
    return [
        AccountRead(
            id=account.id,
            name=account.name,
            account_type=account.account_type,
            currency=account.currency,
            kind=account.kind,
            opening_balance=account.opening_balance,
            current_balance=account.opening_balance
            + sum((item.amount for item in account.transactions), start=0),
            portfolio_id=account.portfolio.id if account.portfolio else None,
            portfolio_name=account.portfolio.name if account.portfolio else None,
            created_at=account.created_at,
            transaction_count=len(account.transactions),
        )
        for account in accounts
    ]


@app.get("/v1/accounts/{account_id}", response_model=AccountRead)
def get_account(account_id: str, session: SessionDependency) -> AccountRead:
    account = get_account_or_404(account_id, session)
    return AccountRead(
        id=account.id,
        name=account.name,
        account_type=account.account_type,
        currency=account.currency,
        kind=account.kind,
        opening_balance=account.opening_balance,
        current_balance=account.opening_balance
        + sum((item.amount for item in account.transactions), start=0),
        portfolio_id=account.portfolio.id if account.portfolio else None,
        portfolio_name=account.portfolio.name if account.portfolio else None,
        created_at=account.created_at,
        transaction_count=len(account.transactions),
    )


@app.get("/v1/transactions", response_model=TransactionPage)
def list_transactions(
    session: SessionDependency,
    account_id: str | None = None,
    transaction_type: TransactionType | None = None,
    cash_flow: Literal["inflow", "outflow"] | None = None,
    category: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> TransactionPage:
    filters = []
    if account_id:
        get_account_or_404(account_id, session)
        filters.append(Transaction.account_id == account_id)
    if transaction_type:
        filters.append(Transaction.transaction_type == transaction_type.value)
    if cash_flow == "inflow":
        filters.append(Transaction.amount > 0)
    elif cash_flow == "outflow":
        filters.append(Transaction.amount < 0)
    if category:
        filters.append(func.lower(Transaction.category) == category.lower())
    if date_from:
        filters.append(Transaction.booked_at >= date_from)
    if date_to:
        filters.append(Transaction.booked_at <= date_to)
    if date_from and date_to and date_from > date_to:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_date_range", "message": "date_from must not exceed date_to"},
        )

    total = session.scalar(select(func.count()).select_from(Transaction).where(*filters)) or 0
    statement = (
        select(Transaction)
        .where(*filters)
        .order_by(Transaction.booked_at.desc(), Transaction.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    items = list(session.scalars(statement).all())
    return TransactionPage(items=items, total=total, limit=limit, offset=offset)


@app.post("/v1/transactions/demo-bank-feed", response_model=DemoBankFeedResult)
def create_demo_bank_feed(
    payload: DemoBankFeedCreate,
    session: SessionDependency,
    classifier: ClassifierDependency,
) -> DemoBankFeedResult:
    account = get_account_or_404(payload.account_id, session)
    if account.account_type == "brokerage":
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_account_type",
                "message": "Demo bank activity requires a checking or savings account",
            },
        )

    today = business_today()
    year = payload.year or today.year
    month = payload.month or today.month
    seed = payload.seed if payload.seed is not None else randbelow(2_147_483_648)
    generated = generate_demo_bank_feed(
        seed=seed,
        year=year,
        month=month,
        variable_count=payload.variable_count,
    )
    batch_key = f"{account.id}:{year:04d}-{month:02d}:{seed}"
    batch_namespace = UUID("40b090f5-0fd3-431b-a356-a9ea61fb3a7e")
    transaction_ids = [
        str(uuid5(batch_namespace, f"{batch_key}:{index}")) for index in range(len(generated))
    ]
    existing_ids = set(
        session.scalars(select(Transaction.id).where(Transaction.id.in_(transaction_ids))).all()
    )
    pending = [
        (index, item)
        for index, item in enumerate(generated)
        if transaction_ids[index] not in existing_ids
    ]
    try:
        classifications = classifier.classify_many(
            [(item.description, item.amount, item.counterparty) for _, item in pending],
            input_source=ClassificationInputSource.BANK_FEED,
        )
    except ModelArtifactError:
        classifications = []
        for _, item in pending:
            route = route_transaction_text(item.description, item.amount, item.counterparty)
            classifications.append(
                TransactionClassification(
                    category=route.category.value if route.category else None,
                    route=route.route,
                    method=route.method,
                    confidence=None,
                    needs_review=True,
                    reason="Category model artifact was unavailable during demo feed import.",
                    taxonomy_version=TAXONOMY_VERSION,
                    model_version=None,
                    input_source=ClassificationInputSource.BANK_FEED,
                )
            )

    created_count = 0
    auto_count = 0
    review_count = 0
    correct_count = 0

    for (index, item), classification in zip(pending, classifications, strict=True):
        transaction_id = transaction_ids[index]
        accepted_category = classification.category if not classification.needs_review else None
        transaction = Transaction(
            id=transaction_id,
            account_id=account.id,
            booked_at=item.booked_at,
            name=item.description,
            amount=item.amount,
            currency=account.currency,
            transaction_type=item.transaction_type,
            counterparty=item.counterparty,
            category=accepted_category,
            source="demo_bank_feed",
        )
        transaction.classifications.append(
            TransactionClassificationRecord(
                transaction_id=transaction.id,
                predicted_category=classification.category,
                final_category=None,
                route=classification.route.value,
                classification_method=classification.method.value,
                confidence=classification.confidence,
                needs_review=classification.needs_review,
                feedback_status="unreviewed",
                reason=classification.reason,
                taxonomy_version=classification.taxonomy_version,
                model_version=classification.model_version,
                input_source=classification.input_source.value,
                alternative_predicted_category=classification.alternative_category,
                alternative_model_version=classification.alternative_model_version,
                model_agreement=classification.model_agreement,
            )
        )
        session.add(transaction)
        created_count += 1
        auto_count += int(accepted_category is not None)
        review_count += int(classification.needs_review)
        correct_count += int(classification.category == item.expected_category)

    session.commit()
    return DemoBankFeedResult(
        seed=seed,
        year=year,
        month=month,
        generated_count=len(generated),
        created_count=created_count,
        automatically_categorized_count=auto_count,
        review_count=review_count,
        correct_prediction_count=correct_count,
        evaluated_count=created_count,
    )


@app.get(
    "/v1/transactions/classification/status",
    response_model=TransactionClassificationStatusRead,
)
def get_transaction_classification_status(
    classifier: ClassifierDependency,
) -> TransactionClassificationStatusRead:
    return TransactionClassificationStatusRead.model_validate(
        classifier.status(), from_attributes=True
    )


@app.get("/v1/transactions/{transaction_id}", response_model=TransactionRead)
def get_transaction(transaction_id: str, session: SessionDependency) -> Transaction:
    transaction = session.get(Transaction, transaction_id)
    if transaction is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "transaction_not_found", "message": "Transaction not found"},
        )
    return transaction


@app.patch("/v1/transactions/{transaction_id}/category", response_model=TransactionRead)
def review_transaction_category(
    transaction_id: str,
    payload: TransactionCategoryReview,
    session: SessionDependency,
) -> Transaction:
    transaction = session.get(Transaction, transaction_id)
    if transaction is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "transaction_not_found", "message": "Transaction not found"},
        )
    latest = transaction.classifications[-1] if transaction.classifications else None
    transaction.category = payload.category
    if latest is not None:
        latest.final_category = payload.category
        latest.feedback_status = (
            "accepted_explicit" if latest.predicted_category == payload.category else "corrected"
        )
        latest.needs_review = False
    session.commit()
    session.refresh(transaction)
    return transaction


@app.post(
    "/v1/transactions/classify",
    response_model=TransactionClassificationResponse,
)
def classify_transaction(
    payload: TransactionClassificationRequest,
    classifier: ClassifierDependency,
) -> TransactionClassificationResponse:
    try:
        result = classifier.classify(
            description=payload.description,
            amount=payload.amount,
            counterparty=payload.counterparty,
            input_source=ClassificationInputSource.MANUAL_ENTRY,
        )
    except ModelArtifactError as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "category_model_unavailable", "message": str(exc)},
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "classification_input_invalid", "message": str(exc)},
        ) from exc
    return TransactionClassificationResponse(
        category=result.category,
        route=result.route,
        classification_method=result.method,
        confidence=result.confidence,
        needs_review=result.needs_review,
        reason=result.reason,
        taxonomy_version=result.taxonomy_version,
        model_version=result.model_version,
        input_source=result.input_source,
        alternative_category=result.alternative_category,
        alternative_model_version=result.alternative_model_version,
        model_agreement=result.model_agreement,
    )


@app.post("/v1/transactions", response_model=TransactionRead, status_code=201)
def create_transaction(
    payload: TransactionCreate,
    session: SessionDependency,
    classifier: ClassifierDependency,
) -> Transaction:
    account = get_account_or_404(payload.account_id, session)
    security_types = {TransactionType.SECURITY_BUY, TransactionType.SECURITY_SELL}
    if payload.transaction_type in security_types and account.account_type != "brokerage":
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_account_type",
                "message": "Security transactions require a brokerage account",
            },
        )

    try:
        classification = classifier.classify(
            description=payload.name,
            amount=payload.amount,
            counterparty=payload.counterparty,
            input_source=ClassificationInputSource.MANUAL_ENTRY,
        )
    except ModelArtifactError:
        route = route_transaction_text(payload.name, payload.amount, payload.counterparty)
        classification = TransactionClassification(
            category=None,
            route=route.route,
            method=ClassificationMethod.NONE,
            confidence=None,
            needs_review=True,
            reason="Category model artifact was unavailable when the transaction was saved.",
            taxonomy_version=TAXONOMY_VERSION,
            model_version=None,
        )

    transaction = Transaction(
        **payload.model_dump(
            mode="python",
            exclude={
                "currency",
                "transaction_type",
                "security_symbol",
                "category_confirmed",
            },
        ),
        currency=payload.currency.upper(),
        transaction_type=payload.transaction_type.value,
        security_symbol=payload.security_symbol.upper() if payload.security_symbol else None,
        source="manual",
    )
    session.add(transaction)
    session.flush()
    transaction.classifications.append(
        TransactionClassificationRecord(
            transaction_id=transaction.id,
            predicted_category=classification.category,
            final_category=payload.category,
            route=classification.route.value,
            classification_method=classification.method.value,
            confidence=classification.confidence,
            needs_review=classification.needs_review,
            feedback_status=determine_feedback_status(
                classification.category,
                payload.category,
                payload.category_confirmed,
            ).value,
            reason=classification.reason,
            taxonomy_version=classification.taxonomy_version,
            model_version=classification.model_version,
            input_source=classification.input_source.value,
            alternative_predicted_category=classification.alternative_category,
            alternative_model_version=classification.alternative_model_version,
            model_agreement=classification.model_agreement,
        )
    )
    session.commit()
    session.refresh(transaction)
    return transaction


def run() -> None:
    import uvicorn

    uvicorn.run("financial_ai.main:app", host="127.0.0.1", port=8000, reload=True)
