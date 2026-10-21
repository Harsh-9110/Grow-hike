export interface User { id: string; email: string }
export interface Config { demo_mode: boolean; google_enabled: boolean; broker_enabled: boolean; demo_email: string | null; demo_password: string | null }
export interface Portfolio { id: string; name: string; kind: 'paper' | 'import' }
export interface Stock { symbol: string; name: string; sector: string; market: string; currency: string }
export interface Quote { symbol: string; price: string; previous_close: string; currency: string; as_of: string; provider: string; stale: boolean; demo: boolean }
export interface History { points: {date: string; close: string}[]; demo: boolean; stale: boolean; provider: string }
export interface Position extends Stock { quantity: string; average_cost: string; cost: string; cost_inr: string; value: string; value_inr: string; unrealized: string; unrealized_inr: string; return_pct: string; price: string; day_change_inr: string; demo: boolean; stale: boolean; provider: string; as_of: string }
export interface Allocation { name: string; value: string; weight_pct: string }
export interface Summary extends Portfolio { cash: string; total_value: string; holdings_value: string; cost_basis: string; day_change: string; day_change_note: string; realized_pnl: string; unrealized_pnl: string; total_pnl: string; xirr_pct: string | null; positions: Position[]; allocation: Record<string, Allocation[]>; stale: boolean; demo: boolean; import_note: string | null }
export interface Performance { points: {date: string; value: string; portfolio_index: string | null; nifty_index: string; sp500_inr_index: string; demo: boolean; stale: boolean}[]; volatility_pct: number | null; max_drawdown_pct: string | null; note: string; demo?: boolean }
export interface Entry { id: string; sequence: number; kind: string; symbol: string | null; quantity: string; price: string; fx_rate: string; cash_delta_inr: string; created_at: string }
export interface Watch { id: string; symbol: string }
export interface Alert { id: string; symbol: string; direction: string; target: string; triggered_at: string | null }
export interface Preview { valid: boolean; preview_id: string | null; rows: {symbol: string; quantity: string; average_price: string; currency: string}[]; errors: {row: number; message: string}[]; note?: string }
export interface Insight { summary: string; sources: {id: number; headline: string; url: string; published_at: string}[]; mode: string; note: string; stale: boolean }
export interface Forecast { status: string; demo: boolean; forecasts: {horizon_sessions: number; lstm: string | null; naive: string}[]; evaluation: {horizon_sessions: number; lstm_mae: string; naive_mae: string; lstm_directional_accuracy: number; naive_directional_accuracy: number; n_origins: number}[]; note: string; trained_at?: string; last_observation?: string }
export interface Metrics { counters: Record<string, number>; cache_hit_rate_pct: number; api_calls_saved: number; p50_ms: number; p95_ms: number; sample_size: number; jobs: Record<string, string | null>; note: string }
