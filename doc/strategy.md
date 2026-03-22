# Strategy: Macro Regime-Based Two-Stage Screening System (MVP)

> Purpose: provide the concise strategic source of truth for product scope, architecture direction, and the final MVP operating posture.

## 1. Why this exists

The project exists to produce a repeatable Korean-equity screening system that:
- ranks **industries** by macro favorability,
- ranks **stocks** by disclosure-driven catalysts,
- publishes full-universe immutable snapshots for downstream research and strategy consumption,
- and supports point-in-time-safe historical replay.

It is a **screener**, not a portfolio optimizer, execution engine, or public API platform.

## 2. Final human-facing doc set

The final human-facing documentation set is:
1. `doc/strategy.md` — boundary and architecture anchor
2. `doc/prd.md` — authoritative product and data-contract requirements
3. `doc/plan.md` — authoritative implementation plan
4. `doc/open-questions.md` — only the true remaining kickoff questions

Historical corrective inputs and draft planning notes are not part of the final authoritative doc set once their content is merged here and into `prd.md` / `plan.md`.

## 3. MVP boundaries

### In scope
- market: **KOSPI + KOSDAQ common stocks only**
- cadence: **twice-daily batch runs**
  - pre-open
  - post-close
- outputs:
  - full industry ranking
  - full stock ranking
  - immutable published snapshots
  - point-in-time-safe replay outputs
- Stage 1: macro-based industry scoring
- Stage 2: DART-based stock scoring conditioned on Stage 1
- manual and backtest execution paths
- degraded-mode fallback with explicit warnings and confidence impact

### Out of scope
- real-time intraday production updates
- news-overlay production rules
- portfolio construction / execution
- full-text semantic interpretation of DART disclosures
- public API/service freeze beyond file outputs
- aggressive macro-formula or weight optimization without PIT-safe validation

## 4. Core strategic principles

1. **Two-stage design**
   - Stage 1 ranks industries.
   - Stage 2 ranks stocks using Stage 1 as an input feature.
2. **Full-universe outputs**
   - no hard cutoff at industry or stock level.
3. **Point-in-time correctness**
   - live and backtest runs must only use data visible by the relevant cutoff.
4. **Batch-first architecture**
   - MVP is optimized for reliable scheduled snapshots, not continuous updates.
5. **Immutable publication**
   - published snapshots are audit artifacts and must not be overwritten.
6. **Explicit contracts over implicit behavior**
   - provider contracts, channel semantics, scoring assumptions, and snapshot semantics must stay explicit.
7. **Narrow external-macro scope**
   - MVP external macro is **Korea + US-only external macro**, not a broad global macro monitor.

## 5. Strategic architecture

## 5.1 Stage 1: macro-based industry scoring

Stage 1 converts Korea-side and US-side macro inputs into channel states, then converts those channel states into ranked industries using full ordered sector-rank tables.

### Channel set
- `G` — Growth / Activity
- `IC` — Inflation / Cost
- `FC` — Financial Conditions
- `ED` — External Demand
- `FX` — Foreign Exchange

### Fixed MVP rules
- each channel state is in `{-1, 0, +1}`
- channel interpretation and sign semantics are fixed
- `0` means **neutral only**
- missing, stale, failed, or fallback inputs are represented separately through metadata and confidence, not by coercing to `0`
- Korea-side and US-side signals inside a channel combine by a documented **simple arithmetic mean**, then map back to the final channel state through a channel-specific neutral band
- Stage 1 industry scoring uses **weighted rank-derived sector priors + overlay**, not symmetric exposure multiplication
- full ordered sector-rank tables are authoritative for each channel / regime
- `+1` and `-1` are **not** assumed to be mirror-image reverse tables
- fast overlays do **not** replace the slower structural Stage 1 ranking basis
- industry tie-breakers remain, in order:
  1. lower absolute negative penalty
  2. higher positive contribution
  3. industry code ascending

### Stage 1 data authority
For production MVP planning, Stage 1 relies on:
- Korea macro/statistical sources: `ECOS`, `KOSIS`
- US external macro sources: **FRED / ALFRED or an equivalent official-source adapter layer**
- local taxonomy authority: `stock_classification.csv`
- derived taxonomy authority when needed: `industry_master.csv` or equivalent, generated from the local classification CSV
- KRX as market / universe / overlay infrastructure, **not** as the sole macro provider for any channel
- manual override / stub mode only for local verification and controlled degraded fallback

### What is frozen now
- the 5 channels and their economic meaning
- the sign semantics for `+1 / 0 / -1`
- Korea + US-only external macro framing
- simple channel-combination rule
- local CSV authority for common-stock filtering and industry taxonomy
- full sector-rank-table Stage 1 scoring shape
- equal default channel weights unless explicitly changed later

### What remains intentionally open
- exact raw-series transform for each fixed series
- exact neutral-band threshold `tau_c` for each channel
- final choice of the US `ED` proxy when more than one acceptable realized series exists
- whether ALFRED vintages are required before live collection starts
- final filename/schema/ownership for the derived industry taxonomy master

## 5.2 Stage 2: DART-based stock scoring

Stage 2 converts disclosure state into ranked stocks.

### Fixed MVP rules
- classification uses disclosure codes + title-based pattern matching
- full-text semantic interpretation is out of scope
- DART events are persistent state variables with time decay
- stock score combines normalized DART score and normalized industry score
- `FinancialScore = 0` in MVP, but the slot remains in the formula
- unknown disclosure types become neutral and are counted / logged
- stock tie-breakers remain, in order:
  1. higher raw DART score
  2. higher raw industry-score contribution
  3. stock code ascending

### Resolved defaults carried forward
- cross-sectional z-score normalization per snapshot
- if standard deviation is zero, normalized component = `0`
- `lambda` is applied **after** normalization
- current runtime baseline keeps the Stage 2 industry contribution weight configurable, with the present code default at `0.35`
- decay uses trading-day exponential decay with interpretable half-life defaults:
  - `supply_contract = 20`
  - `treasury_stock = 10`
  - `facility_investment = 60`
  - `dilutive_financing = 60`
  - `correction_cancellation_withdrawal = 10`
  - `governance_risk = 120`

## 5.3 Minimum contract expectations

The reader-facing doc set keeps the minimum contract shape explicit so implementers do not need hidden artifacts for handoff.

### `Stage1Result`
- `run_id`
- `run_type`
- `as_of_timestamp`
- `channel_states`
- `industry_scores`
- `config_version`
- `warnings`

Channel states and industry outputs must retain enough metadata for:
- source identification
- input cutoff / timing audit
- confidence and fallback visibility
- per-channel contribution explanation

### `ScoringContext`
- `run_metadata`
- `stage1_result`
- `config`
- `calendar_context`
- `mode`
- `input_cutoff`

### `Snapshot`
- `run_id`
- `run_type`
- `as_of_timestamp`
- `input_cutoff`
- `published_at`
- `status`
- `industry_scores`
- `stock_scores`
- `warnings`

## 6. Runtime strategy

### Scheduled runs
- pre-open run: default `08:30 KST`
- post-close run: default `15:45 KST`
- both publish immutable snapshots

### Manual runs
- allowed through CLI
- must still obey point-in-time, persistence, and immutability rules

### Backtest runs
- replay the same logical pipeline
- preserve point-in-time correctness
- may process independent days in parallel
- close-based next-day rules must be preserved

## 7. Final MVP operating decisions

### Data-source posture
- KRX: official market/universe/overlay source
- DART: official disclosure source with PIT-safe cursoring
- ECOS + KOSIS: Korea macro/statistical sources
- US external macro: FRED / ALFRED or equivalent official-source adapter with official-source attribution retained in metadata
- local classification CSV: authoritative common-stock filter and industry taxonomy mapping
- BIS / OECD / IMF: not required MVP runtime providers; future-expansion, secondary-validation, or backfill/reference sources only
- Korean holiday handling: hardcoded MVP list behind the project calendar helper

### Source-priority rule
For runtime channel classification:
1. use Korea official series or US official realized series first
2. prefer actual observed data over projections
3. if IMF is ever used, prefer topic datasets with actual observations
4. use IMF WEO only as reference/backfill when no better actual series exists
5. never let projected WEO periods enter runtime Stage 1 classification

### Downstream consumption contract
- canonical external output is **immutable parquet snapshots**
- canonical latest pointer is `data/snapshots/latest.json`
- SQLite is the operational/audit store, not the primary external consumer contract
- CLI export/read helpers may exist for convenience
- no public API/service contract is frozen in MVP

### Scheduled-window identity
- `scheduled_window_key = (trading_date, run_type)`
- `run_id` identifies an execution attempt, not the business window
- a business window may have multiple draft attempts but at most one published snapshot

## 8. MVP degraded-mode commitments

These are final MVP commitments, not provisional examples:
- if DART remains unavailable after configured retries, run with **stale DART data** only when a prior successful state exists and flag the output
- if Korea or US macro sources are unavailable for a scheduled run, use **last known channel states** only under explicit fallback policy, log a warning, and reduce confidence rather than silently mapping to neutral
- if Stage 2 fails after Stage 1 succeeds, publish **Stage 1-only** output and flag the run incomplete
- if Stage 1 fails, Stage 2 does not run
- unknown DART disclosure types become neutral and are logged/count-tracked

## 9. Minimal MVP alert matrix

- neutral/unknown DART classification ratio `> 20%` → warning
- missed scheduled run detected during recovery → error
- snapshot publication failure → critical
- repeated external API failure after configured retries → error

Operator response and verification specifics live in `doc/plan.md`.

## 10. What is intentionally deferred

These are not blockers for MVP implementation handoff, but they are not fully frozen yet:
- exact raw transform for each fixed Korea/US series
- exact neutral-band `tau_c` values by channel
- final US `ED` proxy choice when multiple acceptable realized series remain
- whether ALFRED vintages are required before live collection starts
- final filename/schema/ownership for the derived industry taxonomy file
- exact SQLite physical DDL and non-essential indexes
- migration tool vs manual versioned SQL
- non-file-based downstream service/API contract
- fine-grained alert/SLO tuning beyond the MVP alert matrix

## 11. Reading order

If you only read the final project docs, read them in this order:
1. `doc/strategy.md`
2. `doc/prd.md`
3. `doc/plan.md`
4. `doc/open-questions.md`
