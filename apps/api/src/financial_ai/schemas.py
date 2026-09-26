from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from financial_ai.ml.transaction_classification.core.contracts import (
    ClassificationInputSource,
    ClassificationMethod,
    ClassificationRoute,
    FeedbackStatus,
    parse_product_category,
)


class PositionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    symbol: str
    quantity: Decimal
    purchase_price: Decimal
    purchase_date: date
    asset_class: str
    sector: str
    region: str
    currency: str


class PortfolioSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    base_currency: str
    kind: str
    market_data_mode: str
    created_at: datetime
    position_count: int
    account_id: str | None


class PortfolioRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    base_currency: str
    kind: str
    market_data_mode: str
    created_at: datetime
    account_id: str | None
    positions: list[PositionRead]


class CatalogAsset(BaseModel):
    symbol: str
    name: str
    currency: str
    asset_class: str
    sector: str
    region: str


class MarketInstrumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    provider: str
    symbol: str
    name: str
    exchange: str
    currency: str
    asset_class: str
    region: str | None
    is_active: bool
    updated_at: datetime


class MarketPriceRead(BaseModel):
    observed_on: date
    close: Decimal
    open: Decimal | None
    high: Decimal | None
    low: Decimal | None
    adjusted_close: Decimal | None
    volume: Decimal | None


class MarketQuoteRead(MarketPriceRead):
    instrument: MarketInstrumentRead
    source: str
    retrieved_at: datetime
    is_stale: bool


class MarketHistoryRead(BaseModel):
    instrument: MarketInstrumentRead
    source: str
    retrieved_at: datetime
    points: list[MarketPriceRead]


class MarketVolatilityForecastRead(BaseModel):
    symbol: str
    observed_on: date
    horizon_trading_days: int = Field(gt=0)
    predicted_annualized_volatility: float = Field(gt=0)
    annualized: bool = True
    model_version: str
    source: str
    retrieved_at: datetime
    data_status: str = Field(pattern="^(current|stale)$")
    training_source_feed: str | None
    feed_match: bool | None


class TradeSide(StrEnum):
    BUY = "buy"
    SELL = "sell"


class PortfolioCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    base_currency: str = Field(default="EUR", min_length=3, max_length=3)
    starting_cash: Decimal = Field(gt=0, max_digits=20, decimal_places=2)
    market_data_mode: str = Field(default="demo", pattern="^(demo|external)$")

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Portfolio name must not be empty")
        return normalized

    @field_validator("base_currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.upper()


class PortfolioOrderCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_order_id: str = Field(min_length=1, max_length=64)
    instrument_id: str = Field(min_length=1, max_length=36)
    side: TradeSide
    quantity: Decimal = Field(ge=1, multiple_of=1, max_digits=20, decimal_places=0)


class PortfolioTradeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    client_order_id: str
    side: TradeSide
    quantity: Decimal
    unit_price: Decimal
    instrument_currency: str
    settlement_amount: Decimal
    fees: Decimal
    currency: str
    booked_at: date
    price_observed_on: date
    price_source: str
    executed_at: datetime
    instrument: MarketInstrumentRead


class PortfolioHoldingRead(BaseModel):
    instrument: MarketInstrumentRead
    quantity: Decimal
    average_cost: Decimal
    latest_price: Decimal
    market_value: Decimal
    unrealized_pnl: Decimal
    weight: float
    price_observed_on: date
    price_source: str
    quote_is_stale: bool


class TradingPortfolioSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    base_currency: str
    market_data_mode: str
    opening_cash: Decimal
    created_at: datetime
    trade_count: int


class MarketDataStatus(BaseModel):
    demo_available: bool = True
    external_available: bool
    external_provider: str = "alpaca"


class TradingPortfolioRead(TradingPortfolioSummary):
    cash_balance: Decimal
    holdings_value: Decimal
    total_equity: Decimal
    total_pnl: Decimal
    realized_pnl: Decimal
    holdings: list[PortfolioHoldingRead]
    trades: list[PortfolioTradeRead]
    warnings: list[str]


class AllocationItem(BaseModel):
    label: str
    value_eur: Decimal
    weight: float


class PositionAnalytics(BaseModel):
    symbol: str
    market_value_eur: Decimal
    cost_basis_eur: Decimal
    pnl_eur: Decimal
    weight: float


class SeriesPoint(BaseModel):
    date: date
    value_eur: Decimal


class RiskComponent(BaseModel):
    key: str
    label: str
    score: float = Field(ge=0, le=100)
    weight: float = Field(gt=0, le=1)
    contribution: float = Field(ge=0, le=100)
    raw_value: float
    raw_unit: str
    summary: str
    details: dict[str, float] = Field(default_factory=dict)


class RiskDriver(BaseModel):
    component: str
    contribution: float
    explanation: str


class RiskDimension(BaseModel):
    key: str
    label: str
    score: float = Field(ge=0, le=100)
    level: str
    summary: str
    details: dict[str, float] = Field(default_factory=dict)


class PortfolioRiskScore(BaseModel):
    score: float = Field(ge=0, le=100)
    level: str
    methodology_version: str
    as_of: date
    components: list[RiskComponent]
    main_drivers: list[RiskDriver]
    diversification: RiskDimension
    liquidity_resilience: RiskDimension
    interpretation: str
    disclaimer: str
    limitations: list[str]


class AnalyticsResponse(BaseModel):
    portfolio_id: str
    as_of: date
    data_version: str
    market_value_eur: Decimal
    cost_basis_eur: Decimal
    unrealized_pnl_eur: Decimal
    unrealized_pnl_percent: float
    trailing_return_percent: float
    annualized_volatility_percent: float
    max_drawdown_percent: float
    concentration_hhi: float
    largest_position_symbol: str
    largest_position_weight: float
    positions: list[PositionAnalytics]
    allocations: dict[str, list[AllocationItem]]
    value_series: list[SeriesPoint]
    risk_score: PortfolioRiskScore | None = None
    warnings: list[str] = Field(default_factory=list)


class ApiError(BaseModel):
    code: str
    message: str
    details: list[dict[str, object]] = Field(default_factory=list)


class AccountType(StrEnum):
    CHECKING = "checking"
    SAVINGS = "savings"
    BROKERAGE = "brokerage"


class TransactionType(StrEnum):
    UNSPECIFIED = "unspecified"
    CARD_PAYMENT = "card_payment"
    TRANSFER = "transfer"
    DIRECT_DEBIT = "direct_debit"
    CASH_WITHDRAWAL = "cash_withdrawal"
    SALARY = "salary"
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    SECURITY_BUY = "security_buy"
    SECURITY_SELL = "security_sell"
    DIVIDEND = "dividend"
    INTEREST = "interest"
    FEE = "fee"
    TAX = "tax"


class AccountRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    account_type: AccountType
    currency: str
    kind: str
    opening_balance: Decimal
    current_balance: Decimal
    portfolio_id: str | None
    portfolio_name: str | None
    created_at: datetime
    transaction_count: int | None = None


class TransactionClassificationRecordRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    predicted_category: str | None
    final_category: str | None
    route: ClassificationRoute
    classification_method: ClassificationMethod
    confidence: float | None
    needs_review: bool
    feedback_status: FeedbackStatus
    reason: str
    taxonomy_version: str
    model_version: str | None
    input_source: ClassificationInputSource
    alternative_predicted_category: str | None
    alternative_model_version: str | None
    model_agreement: bool | None
    created_at: datetime


class TransactionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    account_id: str
    booked_at: date
    name: str
    amount: Decimal
    currency: str
    transaction_type: TransactionType
    counterparty: str | None
    category: str | None
    notes: str | None
    source: str
    market_instrument_id: str | None
    client_order_id: str | None
    security_symbol: str | None
    quantity: Decimal | None
    unit_price: Decimal | None
    fees: Decimal
    taxes: Decimal
    price_observed_on: date | None
    price_source: str | None
    created_at: datetime
    classifications: list[TransactionClassificationRecordRead] = Field(default_factory=list)


class TransactionCreate(BaseModel):
    account_id: str
    booked_at: date
    name: str = Field(min_length=1, max_length=160)
    amount: Decimal = Field(max_digits=20, decimal_places=2)
    currency: str = Field(default="EUR", min_length=3, max_length=3)
    transaction_type: TransactionType = TransactionType.UNSPECIFIED
    counterparty: str | None = Field(default=None, max_length=160)
    category: str | None = Field(default=None, max_length=60)
    category_confirmed: bool = False
    notes: str | None = Field(default=None, max_length=500)
    security_symbol: str | None = Field(default=None, max_length=24)
    quantity: Decimal | None = Field(default=None, gt=0, max_digits=20, decimal_places=8)
    unit_price: Decimal | None = Field(default=None, gt=0, max_digits=20, decimal_places=6)
    fees: Decimal = Field(default=Decimal("0.00"), ge=0, max_digits=20, decimal_places=2)
    taxes: Decimal = Field(default=Decimal("0.00"), ge=0, max_digits=20, decimal_places=2)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Transaction name must not be empty")
        return normalized

    @field_validator("category")
    @classmethod
    def validate_category(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        return parse_product_category(value)

    @model_validator(mode="after")
    def validate_security_fields(self) -> "TransactionCreate":
        if self.amount == 0:
            raise ValueError("Transaction amount must not be zero")
        security_types = {TransactionType.SECURITY_BUY, TransactionType.SECURITY_SELL}
        if self.transaction_type in security_types:
            missing = [
                field
                for field in ("security_symbol", "quantity", "unit_price")
                if getattr(self, field) is None
            ]
            if missing:
                raise ValueError(
                    "Security transactions require security_symbol, quantity, and unit_price"
                )
        elif any(
            value is not None for value in (self.security_symbol, self.quantity, self.unit_price)
        ):
            raise ValueError(
                "Security fields are only allowed for security buy or sell transactions"
            )
        return self


class TransactionPage(BaseModel):
    items: list[TransactionRead]
    total: int
    limit: int
    offset: int


class DemoBankFeedCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: str
    seed: int | None = Field(default=None, ge=0, le=2_147_483_647)
    year: int | None = Field(default=None, ge=2000, le=2100)
    month: int | None = Field(default=None, ge=1, le=12)
    variable_count: int = Field(default=12, ge=1, le=40)

    @model_validator(mode="after")
    def validate_period(self) -> "DemoBankFeedCreate":
        if (self.year is None) != (self.month is None):
            raise ValueError("year and month must be provided together")
        return self


class TransactionCategoryReview(BaseModel):
    category: str = Field(min_length=1, max_length=60)

    @field_validator("category")
    @classmethod
    def validate_category(cls, value: str) -> str:
        return parse_product_category(value)


class DemoBankFeedResult(BaseModel):
    seed: int
    year: int
    month: int
    generated_count: int
    created_count: int
    automatically_categorized_count: int
    review_count: int
    correct_prediction_count: int
    evaluated_count: int


class TransactionClassificationRequest(BaseModel):
    description: str = Field(min_length=1, max_length=320)
    amount: Decimal = Field(max_digits=20, decimal_places=2)
    counterparty: str | None = Field(default=None, max_length=160)


class TransactionClassificationResponse(BaseModel):
    category: str | None
    route: ClassificationRoute
    classification_method: ClassificationMethod
    confidence: float | None = Field(default=None, ge=0, le=1)
    needs_review: bool
    reason: str
    taxonomy_version: str
    model_version: str | None
    input_source: ClassificationInputSource
    alternative_category: str | None
    alternative_model_version: str | None
    model_agreement: bool | None


class TransactionClassificationStatusRead(BaseModel):
    status: Literal["ready", "degraded", "unavailable"]
    mode: str
    tfidf_model_version: str | None
    semantic_model_version: str | None
    reason: str | None
