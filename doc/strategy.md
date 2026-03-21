# Strategy: Macro Regime-Based Two-Stage Screening System (MVP)

[한국어 버전](strategy.ko.md)


> Purpose: one concise source-of-truth for product intent, architecture strategy, and final MVP operating decisions.

## 1. Why this exists

The project exists to produce a repeatable Korean-equity screening system that:
- ranks **industries** by macro favorability,
- ranks **stocks** by disclosure-driven catalysts,
- and publishes full-universe snapshots that downstream strategies can consume.

It is a **screener**, not a portfolio optimizer or execution engine.

## 2. MVP boundaries

### In scope
- market: **KOSPI + KOSDAQ common stocks only**
- cadence: **twice daily batch runs**
  - pre-open
  - post-close
- outputs:
  - full industry ranking
  - full stock ranking
  - immutable published snapshots
- Stage 1: macro-based industry scoring
- Stage 2: DART-based stock scoring conditioned on Stage 1
- manual and backtest execution paths

### Out of scope
- real-time intraday production updates
- news overlay production rules
- portfolio optimization / execution
- full-text semantic interpretation of DART disclosures
- liquidity / market-cap / special-status filters in MVP
- fully specified production macro-channel formulas

## 3. Core strategic principles

1. **Two-stage design**
   - Stage 1 ranks industries.
   - Stage 2 ranks stocks using Stage 1 as an input feature.
2. **Full-universe outputs**
   - no hard cutoff at industry or stock level.
3. **Point-in-time correctness**
   - live and backtest runs must only use data available by the relevant cutoff.
4. **Batch-first architecture**
   - MVP is optimized for reliable scheduled snapshots, not continuous updates.
5. **Immutable publication**
   - published snapshots are audit artifacts and must not be overwritten.
6. **Explicit contracts over implicit DataFrame behavior**
   - core handoff objects and snapshot semantics must stay stable.

## 4. Strategic architecture

## 4.1 Stage 1: macro-based industry scoring

Stage 1 converts channel states plus exposure mappings into ranked industries.

### Channel set
- `G` — Growth / Activity
- `IC` — Inflation / Cost
- `FC` — Financial Conditions
- `ED` — External Demand
- `FX` — Foreign Exchange

### Fixed MVP rules
- each channel state is in `{-1, 0, +1}`
- channel interpretation is fixed
- exposure matrix values are in `{-1, 0, +1}`
- industry score = base score + overlay adjustment
- fast overlay does **not** replace slow-base labels
- industry tie-breakers are, in order:
  1. lower absolute negative penalty
  2. higher positive contribution
  3. industry code ascending

### MVP channel-state methodology
For MVP, **manual override / stub mode is the only documented channel-state method**.

Fixed now:
- the 5 channels and their economic meaning
- the discrete state space
- timing semantics for state effectiveness
- Stage 1 consumes states and produces a full industry ranking

Deferred beyond MVP baseline:
- exact per-channel variables
- exact numerical thresholds
- production channel-state formulas

## 4.2 Stage 2: DART-based stock scoring

Stage 2 converts disclosure state into ranked stocks.

### Fixed MVP rules
- classification uses disclosure codes + title-based pattern matching
- full-text semantic interpretation is out of scope
- DART events are persistent state variables with time decay
- stock score combines normalized DART score and normalized industry score
- `FinancialScore = 0` in MVP, but the slot remains in the formula

### Resolved defaults
- cross-sectional z-score normalization per snapshot
- if standard deviation is zero, normalized component = `0`
- `lambda` is applied **after** normalization
- decay uses trading-day exponential decay with interpretable half-life defaults
- MVP DART half-life defaults:
  - `supply_contract = 20`
  - `treasury_stock = 10`
  - `facility_investment = 60`
  - `dilutive_financing = 60`
  - `correction_cancellation_withdrawal = 10`
  - `governance_risk = 120`
- stock tie-breakers are, in order:
  1. higher raw DART score
  2. higher raw industry-score contribution
  3. stock code ascending

### 4.3 Minimum contract fields

The reader-facing doc set keeps the minimum contract shape explicit so implementers do not need hidden artifacts for handoff.

#### `Stage1Result`
- `run_id`
- `run_type`
- `as_of_timestamp`
- `channel_states`
- `industry_scores`
- `config_version`
- `warnings`

#### `ScoringContext`
- `run_metadata`
- `stage1_result`
- `config`
- `calendar_context`
- `mode`
- `input_cutoff`

#### `Snapshot`
- `run_id`
- `run_type`
- `as_of_timestamp`
- `input_cutoff`
- `published_at`
- `status`
- `industry_scores`
- `stock_scores`
- `warnings`

## 5. Runtime strategy

## 5.1 Scheduled runs
- pre-open run: default `08:30 KST`
- post-close run: default `15:45 KST`
- both publish immutable snapshots

## 5.2 Manual runs
- allowed through CLI
- must still obey point-in-time, persistence, and immutability rules

## 5.3 Backtest runs
- replay the same logical pipeline
- preserve point-in-time correctness
- may process independent days in parallel
- close-based next-day rules must be preserved

## 6. Final MVP operating decisions

### Data sources
- KRX market data: official KRX endpoints
- DART: OpenAPI with environment-provided API key
- Korean holiday handling: hardcoded MVP list behind the project calendar helper
- preferred future Korea-related macro sources: `ECOS`, `KOSIS`, `DART`
- preferred future global macro source: `BIS`

### Downstream consumption contract
- canonical external output is **immutable parquet snapshots**
- canonical latest pointer is `data/snapshots/latest.json`
- SQLite is the operational/audit store, not the primary external consumer contract
- CLI export/read helpers may exist for convenience
- no API/service contract is frozen in MVP

### Scheduled-window identity
- `scheduled_window_key = (trading_date, run_type)`
- `run_id` identifies an execution attempt, not the business window
- a business window may have multiple draft attempts but at most one published snapshot

## 7. MVP degraded-mode commitments

These are **final MVP commitments**, not provisional examples:

- if DART remains unavailable after configured retries, run with **stale DART data** and flag output
- if Korea/global macro sources are unavailable for a scheduled run, use **last known channel states** and log a warning
- if Stage 2 fails after Stage 1 succeeds, publish **Stage 1-only** output and flag the run incomplete
- if Stage 1 fails, Stage 2 does not run
- unknown DART disclosure types become neutral and are logged/count-tracked

## 8. Minimal MVP alert matrix

- neutral/unknown DART classification ratio `> 20%` → warning
- missed scheduled run detected during recovery → error
- snapshot publication failure → critical
- repeated external API failure after configured retries → error

Operator response is defined in the implementation plan.

## 9. What is intentionally deferred

These are not blockers for MVP implementation handoff, but they are not fully frozen yet:
- exact SQLite physical DDL and non-essential indexes
- migration tool vs manual versioned SQL
- non-file-based downstream service/API contract
- exact production channel variables/thresholds
- fine-grained alert/SLO tuning beyond the MVP alert matrix

## 10. Reading order

If you only read three project docs, read them in this order:
1. `doc/strategy.md`
2. `doc/prd.md`
3. `doc/plan.md`
