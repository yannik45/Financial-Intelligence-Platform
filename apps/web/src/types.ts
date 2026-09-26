export type Portfolio = {
  id: string;
  name: string;
  kind: "demo" | "imported" | "manual";
  market_data_mode: "demo" | "external";
  base_currency: string;
  created_at: string;
  position_count: number;
  account_id: string | null;
};

export type Allocation = { label: string; value_eur: string; weight: number };
export type RiskComponent = {
  key: string;
  label: string;
  score: number;
  weight: number;
  contribution: number;
  raw_value: number;
  raw_unit: string;
  summary: string;
  details: Record<string, number>;
};
export type RiskDimension = {
  key: string;
  label: string;
  score: number;
  level: "strong" | "adequate" | "weak";
  summary: string;
  details: Record<string, number>;
};
export type PortfolioRiskScore = {
  score: number;
  level: "low" | "moderate" | "elevated" | "high";
  methodology_version: string;
  as_of: string;
  components: RiskComponent[];
  main_drivers: Array<{ component: string; contribution: number; explanation: string }>;
  diversification: RiskDimension;
  liquidity_resilience: RiskDimension;
  interpretation: string;
  disclaimer: string;
  limitations: string[];
};
export type Analytics = {
  portfolio_id: string;
  as_of: string;
  data_version: string;
  market_value_eur: string;
  cost_basis_eur: string;
  unrealized_pnl_eur: string;
  unrealized_pnl_percent: number;
  trailing_return_percent: number;
  annualized_volatility_percent: number;
  max_drawdown_percent: number;
  concentration_hhi: number;
  largest_position_symbol: string;
  largest_position_weight: number;
  positions: Array<{ symbol: string; market_value_eur: string; cost_basis_eur: string; pnl_eur: string; weight: number }>;
  allocations: Record<"asset_class" | "sector" | "region" | "currency", Allocation[]>;
  value_series: Array<{ date: string; value_eur: string }>;
  risk_score: PortfolioRiskScore | null;
  warnings: string[];
};

export type AccountType = "checking" | "savings" | "brokerage";
export type Account = {
  id: string;
  name: string;
  account_type: AccountType;
  currency: string;
  kind: "demo" | "manual" | "imported";
  opening_balance: string;
  current_balance: string;
  portfolio_id: string | null;
  portfolio_name: string | null;
  created_at: string;
  transaction_count: number;
};

export type TransactionType =
  | "unspecified"
  | "card_payment"
  | "transfer"
  | "direct_debit"
  | "cash_withdrawal"
  | "salary"
  | "deposit"
  | "withdrawal"
  | "security_buy"
  | "security_sell"
  | "dividend"
  | "interest"
  | "fee"
  | "tax";

export type Transaction = {
  id: string;
  account_id: string;
  booked_at: string;
  name: string;
  amount: string;
  currency: string;
  transaction_type: TransactionType;
  counterparty: string | null;
  category: string | null;
  notes: string | null;
  source: "demo" | "demo_bank_feed" | "manual" | "imported" | "market_order";
  market_instrument_id: string | null;
  client_order_id: string | null;
  security_symbol: string | null;
  quantity: string | null;
  unit_price: string | null;
  fees: string;
  taxes: string;
  price_observed_on: string | null;
  price_source: string | null;
  created_at: string;
  classifications: TransactionClassificationRecord[];
};

export type ClassificationRoute =
  | "deterministic"
  | "text_rule"
  | "expense_model"
  | "needs_review";
export type ClassificationMethod = "deterministic" | "keyword_rule" | "ml" | "none";
export type FeedbackStatus =
  | "accepted"
  | "accepted_implicit"
  | "accepted_explicit"
  | "corrected"
  | "manual"
  | "unreviewed";

export type TransactionClassification = {
  category: string | null;
  route: ClassificationRoute;
  classification_method: ClassificationMethod;
  confidence: number | null;
  needs_review: boolean;
  reason: string;
  taxonomy_version: string;
  model_version: string | null;
  input_source: "manual_entry" | "bank_feed";
  alternative_category: string | null;
  alternative_model_version: string | null;
  model_agreement: boolean | null;
};

export type TransactionClassificationRecord = Omit<
  TransactionClassification,
  "category" | "alternative_category"
> & {
  id: string;
  predicted_category: string | null;
  alternative_predicted_category: string | null;
  final_category: string | null;
  feedback_status: FeedbackStatus;
  created_at: string;
};

export type TransactionClassificationRequest = {
  description: string;
  amount: string;
  counterparty?: string;
};

export type TransactionPage = {
  items: Transaction[];
  total: number;
  limit: number;
  offset: number;
};

export type TransactionFilters = {
  account_id?: string;
  transaction_type?: TransactionType;
  cash_flow?: "inflow" | "outflow";
  category?: string;
  date_from?: string;
  date_to?: string;
  limit: number;
  offset: number;
};

export type TransactionCreate = {
  account_id: string;
  booked_at: string;
  name: string;
  amount: string;
  currency: string;
  transaction_type?: TransactionType;
  counterparty?: string;
  category?: string;
  category_confirmed?: boolean;
  notes?: string;
  security_symbol?: string;
  quantity?: string;
  unit_price?: string;
  fees?: string;
  taxes?: string;
};

export type TransactionClassificationStatus = {
  status: "ready" | "degraded" | "unavailable";
  mode: string;
  tfidf_model_version: string | null;
  semantic_model_version: string | null;
  reason: string | null;
};

export type DemoBankFeedCreate = {
  account_id: string;
  seed?: number;
  year?: number;
  month?: number;
  variable_count?: number;
};

export type DemoBankFeedResult = {
  seed: number;
  year: number;
  month: number;
  generated_count: number;
  created_count: number;
  automatically_categorized_count: number;
  review_count: number;
  correct_prediction_count: number;
  evaluated_count: number;
};

export type MarketInstrument = {
  id: string;
  provider: string;
  symbol: string;
  name: string;
  exchange: string;
  currency: string;
  asset_class: string;
  region: string | null;
  is_active: boolean;
  updated_at: string;
};

export type TradingPortfolioSummary = {
  id: string;
  name: string;
  base_currency: string;
  market_data_mode: "demo" | "external";
  opening_cash: string;
  created_at: string;
  trade_count: number;
};

export type PortfolioTrade = {
  id: string;
  client_order_id: string;
  side: "buy" | "sell";
  quantity: string;
  unit_price: string;
  instrument_currency: string;
  settlement_amount: string;
  fees: string;
  currency: string;
  booked_at: string;
  price_observed_on: string;
  price_source: string;
  executed_at: string;
  instrument: MarketInstrument;
};

export type PortfolioHolding = {
  instrument: MarketInstrument;
  quantity: string;
  average_cost: string;
  latest_price: string;
  market_value: string;
  unrealized_pnl: string;
  weight: number;
  price_observed_on: string;
  price_source: string;
  quote_is_stale: boolean;
};

export type TradingPortfolio = TradingPortfolioSummary & {
  cash_balance: string;
  holdings_value: string;
  total_equity: string;
  total_pnl: string;
  realized_pnl: string;
  holdings: PortfolioHolding[];
  trades: PortfolioTrade[];
  warnings: string[];
};

export type PortfolioCreate = {
  name: string;
  base_currency: string;
  starting_cash: string;
  market_data_mode: "demo" | "external";
};

export type MarketDataStatus = {
  demo_available: boolean;
  external_available: boolean;
  external_provider: string;
};

export type MarketQuote = {
  instrument: MarketInstrument;
  observed_on: string;
  close: string;
  adjusted_close: string | null;
  volume: string | null;
  source: string;
  retrieved_at: string;
  is_stale: boolean;
};

export type MarketVolatilityForecast = {
  symbol: string;
  observed_on: string;
  horizon_trading_days: number;
  predicted_annualized_volatility: number;
  annualized: boolean;
  model_version: string;
  source: string;
  retrieved_at: string;
  data_status: "current" | "stale";
  training_source_feed: string | null;
  feed_match: boolean | null;
};

export type PortfolioOrderCreate = {
  client_order_id: string;
  instrument_id: string;
  side: "buy" | "sell";
  quantity: string;
};

