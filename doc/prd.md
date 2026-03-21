# Product Requirements Document (PRD): Macro Regime-Based Two-Stage Screening System (MVP)

> Purpose: define the product-level requirements, boundaries, outputs, and success criteria for the MVP.

## 1. Product overview

### 1.1 Product summary

Build a batch-driven Korean-equity screening system that publishes:
- a full **industry ranking** from macro regime inputs,
- a full **stock ranking** from DART disclosure state plus Stage 1 industry context,
- immutable snapshots twice daily for downstream strategy consumption.

### 1.2 Target users
- **Primary:** quantitative analysts and portfolio managers
- **Secondary:** system operators and researchers

### 1.3 Product boundary
This system is a **screener**, not a portfolio optimizer or execution engine.

Downstream systems decide:
- number of names to trade,
- portfolio construction,
- sizing,
- entry/exit execution.

## 2. User outcomes and scenarios

### 2.1 Core user outcomes
1. identify favored/disfavored industries under the current macro regime,
2. identify disclosure-driven stock opportunities and risks,
3. compare snapshots over time,
4. backtest the same screening logic historically.

### 2.2 Key scenarios

#### Morning pre-open briefing
1. system triggers pre-open run at `08:30 KST`
2. pipeline ingests eligible overnight DART disclosures, latest macro inputs, and prior-close market data
3. Stage 1 produces industry rankings
4. Stage 2 produces stock rankings
5. analyst reviews top industries, top stocks, and flagged names before market open

#### Post-close review
1. system triggers post-close run at `15:45 KST`
2. pipeline ingests same-day close data and intraday disclosures visible by cutoff
3. updated rankings are published
4. analyst compares pre-open vs post-close changes

#### Historical replay
1. researcher supplies a date range
2. engine replays the same pipeline with point-in-time inputs
3. researcher reviews ranking stability and summary metrics

## 3. Scope

### 3.1 In scope
- KOSPI + KOSDAQ **common stocks only**
- pre-open and post-close scheduled runs
- manual runs
- historical replay / backtest
- immutable snapshot publishing
- full-universe industry and stock rankings

### 3.2 Out of scope
- real-time production news overlay
- portfolio construction or execution
- full-text semantic interpretation of DART disclosures
- liquidity / market-cap / special-status filters in MVP
- fully specified production macro-channel formulas

## 4. Functional requirements

## 4.1 Stage 1 — macro-based industry scoring

| ID | Requirement | Priority |
|---|---|---|
| F1.1 | Maintain 5 macro channels: `G`, `IC`, `FC`, `ED`, `FX`. | MUST |
| F1.2 | Channel states are in `{-1, 0, +1}`. | MUST |
| F1.3 | Support manual/stub channel-state override for MVP and testing. | MUST |
| F1.4 | Load an external industry exposure matrix. | MUST |
| F1.5 | Compute base industry score from exposure × state. | MUST |
| F1.6 | Compute fast-overlay adjustments without modifying the underlying channel states. | MUST |
| F1.7 | Rank all industries with no cutoff. | MUST |
| F1.8 | Preserve deterministic tiebreaks for equal scores. | MUST |
| F1.9 | Preserve next-trading-day timing rules for close-based inputs. | MUST |
| F1.10 | Record internal confidence values where available. | SHOULD |

### 4.1a Stage 1 output requirements
Each published Stage 1 result must include at minimum:
- `industry_code`
- `industry_name`
- `base_score`
- `overlay_adjustment`
- `final_score`
- `rank`
- sufficient metadata to trace the run cutoff and config basis

## 4.2 Stage 2 — DART-based stock scoring

| ID | Requirement | Priority |
|---|---|---|
| F2.1 | Classify DART disclosures into the MVP block model: positive blocks = supply contracts / treasury stock / facility investment; negative blocks = dilutive financing / corrections-cancellations / governance risk. | MUST |
| F2.2 | Use disclosure-type codes and title-based pattern matching only. | MUST |
| F2.3 | Extract structured fields and risk flags from disclosures. | MUST |
| F2.4 | Treat DART events as decaying state, not one-off points. | MUST |
| F2.5 | Combine normalized DART score and normalized industry score. | MUST |
| F2.6 | Keep `FinancialScore = 0` in MVP while preserving the slot in the formula. | MUST |
| F2.7 | Store both raw and normalized values. | MUST |
| F2.8 | Rank all stocks with no cutoff. | MUST |
| F2.9 | Log unknown disclosure types as neutral. | MUST |
| F2.10 | Require Stage 2 to consume a defined `Stage1Result` contract. | MUST |
| F2.11 | Track neutral/unknown classification ratio. | SHOULD |

### 4.2a Stage 2 output requirements
Each published Stage 2 result must include at minimum:
- `stock_code`
- `industry_code`
- `final_score`
- `rank`
- `raw_dart_score`
- `raw_industry_score`
- normalized components used in the score
- risk/correction flags
- block-level breakdown sufficient for audit and explanation

### 4.2b Ranking detail requirements
- ranking must be deterministic
- ranking must preserve documented tie-break behavior
- all stocks with required inputs must be included in the published universe result

## 4.3 Pipeline and publishing

| ID | Requirement | Priority |
|---|---|---|
| F3.1 | Run automatically at pre-open and post-close on trading days. | MUST |
| F3.2 | Support manual trigger via CLI. | MUST |
| F3.3 | Execute ingestion → Stage 1 → Stage 2 → snapshot → publish in order. | MUST |
| F3.4 | Prevent Stage 2 from running if Stage 1 fails. | MUST |
| F3.5 | Allow Stage 1-only incomplete publication if Stage 2 fails after Stage 1 succeeds. | MUST |
| F3.6 | Publish immutable snapshots with unique `run_id`. | MUST |
| F3.7 | Persist snapshots to SQLite and parquet. | MUST |
| F3.8 | Make the latest snapshot retrievable to downstream consumers. | MUST |
| F3.9 | Log starts, stage transitions, counts, timing, warnings, and failures. | MUST |
| F3.10 | Use `scheduled_window_key = (trading_date, run_type)` for scheduled-window dedupe. | MUST |

### 4.3a Canonical output contract
The canonical downstream MVP contract is:
- immutable parquet artifacts
- latest pointer file at `data/snapshots/latest.json`
- SQLite as operational/audit storage, not the primary external consumption contract

## 4.4 Backtest

| ID | Requirement | Priority |
|---|---|---|
| F4.1 | Replay the pipeline by trading day across a date range. | MUST |
| F4.2 | Enforce point-in-time correctness. | MUST |
| F4.3 | Preserve next-day application rules to avoid look-ahead bias. | MUST |
| F4.4 | Keep DART corrections from leaking backward in time. | MUST |
| F4.5 | Support configurable holding-period analysis. | SHOULD |
| F4.6 | Export daily outputs and summary metrics. | MUST |
| F4.7 | Keep results reproducible from stored inputs. | MUST |
| F4.8 | Support parallel processing of independent replay days. | SHOULD |

## 4.5 Ingestion

| ID | Requirement | Priority |
|---|---|---|
| F5.1 | Fetch KOSPI/KOSDAQ stock listings with industry classification. | MUST |
| F5.2 | Fetch OHLCV for overlay calculations. | MUST |
| F5.3 | Fetch DART disclosures incrementally. | MUST |
| F5.4 | Support pluggable macro data source interfaces. | MUST |
| F5.5 | Use a stub/manual macro source in MVP. | MUST |
| F5.6 | Respect retry and rate-limit behavior for external APIs. | MUST |
| F5.7 | Exclude ETFs, ETNs, REITs, and non-equity instruments from the universe. | MUST |
| F5.8 | Preserve ingestion watermarks for incremental processing. | MUST |

## 5. Non-functional requirements

### 5.1 Performance
| ID | Requirement |
|---|---|
| NF1.1 | Full scheduled run target: `< 5 minutes` |
| NF1.2 | Single backtest day target: `< 30 seconds` |
| NF1.3 | Annual backtest target: `< 2 hours` |

### 5.2 Reliability
| ID | Requirement |
|---|---|
| NF2.1 | No partial/corrupt published snapshots. |
| NF2.2 | Graceful handling of API failures via retry/fallback rules. |
| NF2.3 | Scheduler recovery on missed runs. |
| NF2.4 | Graceful shutdown without data corruption. |
| NF2.5 | Published snapshots remain immutable. |

### 5.3 Maintainability
| ID | Requirement |
|---|---|
| NF3.1 | Type hints and standard Python conventions. |
| NF3.2 | Configuration externalized, not hardcoded. |
| NF3.3 | Strong unit/integration/backtest coverage on scoring logic. |
| NF3.4 | Structured logging throughout. |
| NF3.5 | DB layer remains abstractable for future PostgreSQL migration. |

### 5.4 Security
| ID | Requirement |
|---|---|
| NF4.1 | API keys only from environment/secret sources. |
| NF4.2 | No secrets in committed config or logs. |

## 6. MVP acceptance criteria

The MVP documentation set is acceptable when:
- the 3 reader-facing docs alone are enough to understand the product, strategy, and implementation plan,
- the system design supports scheduled industry + stock snapshots,
- degraded-mode and publication rules are explicit,
- the backtest path preserves point-in-time correctness,
- the remaining deferred items are truly non-blocking for MVP.
