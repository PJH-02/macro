# Software Design Document (SDD): Macro Regime-Based Two-Stage Screening System (MVP)

> **Document type:** Software Design Document (SDD)
> **Version:** 0.2-draft
> **Date:** 2026-03-21
> **Status:** Refinement draft
> **Companion documents:**
> - `doc/macro_regime_screening_project_claude.md` — source specification and final design intent
> - `doc/prd.md` — product requirements
> - `doc/plan.md` — implementation plan and module map
> - `.omc/plans/open-questions.md` — resolved planning inputs and remaining gaps
> - `.omx/plans/sdd-refinement-plan.md` — refinement rationale and decision record
>
> **Sufficiency note:** The current SDD together with the source spec, PRD, implementation plan, open questions, and refinement plan are enough to refine this document into a stronger v0.2 handoff. They are not enough to finalize every low-level decision such as persistence indexes, exact recovery-keying, or final downstream consumer contracts.

---

## 1. Purpose and Scope

This SDD is the design-contract layer between the product documents and implementation. It defines runtime boundaries, ownership, timing rules, canonical contracts, persistence behavior, and verification traceability.

### 1.1 In Scope

This document defines:
- component boundaries and ownership
- scheduled, manual, and backtest runtime sequences
- point-in-time and publication invariants
- canonical data and config contracts
- persistence, immutability, retry, idempotency, and recovery behavior
- requirement → design → module → verification traceability

### 1.2 Out of Scope

This document does **not**:
- rewrite the PRD or implementation plan
- finalize every low-level schema, index, or versioning choice
- finalize the downstream consumer protocol beyond immutable snapshot export
- invent new channel-threshold logic beyond what the source spec still marks as deferred

---

## 2. Design Goals, Constraints, and Resolved Inputs

### 2.1 Design Goals

1. Preserve point-in-time correctness in live and backtest modes.
2. Produce full-universe rankings with no hard cutoff at industry or stock level.
3. Keep scheduled execution deterministic at pre-open and post-close.
4. Preserve immutable published snapshots for auditability and replay.
5. Keep data ingestion, scoring, orchestration, and persistence decoupled.
6. Make the document executable as an implementation handoff without guesswork.

### 2.2 Hard Constraints from the Source Spec and PRD

- Market scope is KOSPI + KOSDAQ common stocks only.
- MVP is batch-first, not real-time.
- Stage 2 consumes `Stage1Result`, not raw Stage 1 internals.
- Stage 1 and Stage 2 do not call external APIs directly.
- `FinancialScore` exists in the data model and formula, but remains `0` in MVP.
- Backtest must prevent look-ahead bias.
- API keys must stay out of committed code and config files.
- Published snapshots are immutable.

### 2.3 Resolved Planning Inputs Folded into This Draft

| Area | Resolved input | Design effect |
|---|---|---|
| KRX source | Use official KRX market-data endpoints as the primary MVP source | `data.krx_client` owns listings, OHLCV, and industry mapping; universe filtering is based on the listing security type |
| Industry taxonomy | Use the committed KOSPI+KOSDAQ industry mapping CSV that backs the exposure matrix | `config.exposure_matrix` validates complete industry coverage before Stage 1 runs |
| DART key handling | DART API key is available in `.env` | Secrets remain environment-only; the SDD does not place the key in committed config |
| Holiday calendar | Use a hardcoded Korean holiday list for MVP | Scheduler uses XKRX-aware trading-day logic plus the resolved holiday list |
| Score normalization | Use cross-sectional z-score normalization per snapshot for both `DARTScore` and `IndustryScore`; zero standard deviation maps to `0`; `lambda` is applied after normalization | Stage 2 stores both raw and normalized values for auditability and tiebreaks |
| DART decay | Use exponential decay in trading-day units with half-life grid `{5, 10, 20, 60, 120, 252}` | `decay.py` stays configurable while remaining interpretable |
| DART defaults | `supply_contract=20`, `treasury_stock=10`, `facility_investment=60`, `dilutive_financing=60`, `correction_cancellation_withdrawal=10`, `governance_risk=120` | These are the MVP defaults for block-level persistence strength |
| Fast overlay threshold | Price-type overlays trigger at a 5% move versus the latest workday close | Overlay logic remains rule-based and threshold-driven |
| Backtest concurrency | Support parallel processing of independent replay days | Backtest may parallelize after PIT inputs are materialized, but day-level boundaries remain strict |

---

## 3. System Context and Ownership

### 3.1 External Systems

| System | Role | Interface | Notes |
|---|---|---|---|
| KRX market data source | Listings, OHLCV, industry mapping | HTTP/API | Primary official source for MVP |
| DART OpenAPI | Disclosure ingestion | HTTP/API | Incremental disclosure retrieval |
| Macro source | Channel inputs | Pluggable API or stub | MVP may use stub/manual override |
| SQLite | Operational persistence | Local DB | Snapshots, events, job state, audit records |
| Parquet files | Immutable snapshot export | Filesystem | Backtest and archival output |
| Scheduler runtime | Timed orchestration | In-process | Pre-open and post-close triggers |

### 3.2 Component Ownership

| Component | Owns | Produces | Consumes | Notes |
|---|---|---|---|---|
| `config` | Settings, exposure matrix loading, validation | Validated runtime config | Env, YAML, defaults | Fails fast on invalid exposure coverage |
| `data.krx_client` | KRX listings, OHLCV, industry mapping, universe filtering | Eligible universe rows, market data | External KRX source | Excludes ETFs, ETNs, REITs, infrastructure funds, and non-equities |
| `data.dart_client` | Disclosure list/detail retrieval and watermarking | Structured disclosure rows | DART API | Tracks incremental ingestion state |
| `data.macro_client` | Macro adapter boundary | Channel input payloads | Stub or future provider | Manual override path enters here |
| `stage1` | Macro-to-industry scoring | `Stage1Result`, ranked industries | Macro inputs, exposure matrix, OHLCV overlays | Does not call external APIs |
| `stage2` | DART-to-stock scoring | Ranked stock results | `Stage1Result`, disclosures, config | Does not call external APIs |
| `pipeline.runner` | Run lifecycle orchestration | Completed run, persisted snapshot request | Clients, stages, db, publisher | Owns run boundaries and failure propagation |
| `pipeline.scheduler` | Scheduled trigger management | Run invocations | Calendar, runner, job store | Uses APScheduler with persistent job state |
| `backtest.engine` | Historical replay orchestration | Replay outputs, metrics | Snapshot store, PIT data | May parallelize independent replay days |
| `db` | Persistence and retrieval | Stored snapshots, events, state | Runner, scheduler, backtest | Owns CRUD and immutability checks |
| `publisher` | Output shaping and export | Published snapshot artifact | Stage outputs, db records | Must not mutate persisted results |

### 3.3 Boundary Rules

- `stage1` and `stage2` must not call external APIs directly.
- `stage2` must consume `Stage1Result`, not raw Stage 1 internals.
- `backtest.engine` must construct the same `ScoringContext` interface used in live mode.
- `publisher` must not mutate persisted results.
- Raw SQL stays inside the DB layer.
- Published snapshots are controlled by the repository/orchestration boundary, not by stage code.

---

## 4. Runtime Sequences

### 4.1 Common Run Lifecycle

Every run follows the same high-level lifecycle:
1. Resolve the run type and `as_of_timestamp`.
2. Load effective config, calendar context, and manual overrides if present.
3. Ingest eligible KRX, DART, and macro inputs.
4. Build `ScoringContext`.
5. Execute Stage 1.
6. Execute Stage 2 only if Stage 1 succeeds.
7. Persist the snapshot and supporting audit records.
8. Publish the snapshot after persistence succeeds.
9. Record timing, counts, warnings, and error metadata.

### 4.2 Scheduled Pre-Open Run

**Trigger:** Trading day, default 08:30 KST.

**Sequence:**
1. Scheduler checks the trading calendar and skips non-trading days.
2. Runner creates `run_id`, `run_type=pre_open`, and the pre-open `as_of_timestamp`.
3. Runner loads effective config, exposure matrix, and any manual macro overrides.
4. KRX client loads the eligible universe and prior-close market data.
5. DART client loads disclosures that are visible before the pre-open cutoff.
6. Macro client resolves channel inputs.
7. Stage 1 computes channel states, base score, overlay adjustment, and industry ranking.
8. Stage 2 consumes `Stage1Result` plus disclosure state and computes stock scores.
9. Runner persists the snapshot and audit records.
10. Publisher marks the snapshot published and exposes the latest output.
11. Metrics and logs capture duration, counts, neutral/unknown ratio, and warnings.

**Invariants:**
- Stage 2 never runs if Stage 1 fails.
- Only data available by the pre-open cutoff may be used.
- Published snapshots are immutable.

### 4.3 Scheduled Post-Close Run

**Trigger:** Trading day, default 15:45 KST.

**Sequence:**
1. Scheduler confirms the day is a trading day.
2. Runner creates `run_id`, `run_type=post_close`, and the post-close `as_of_timestamp`.
3. Runner loads same-day close OHLCV where that data is allowed.
4. DART and macro inputs are resolved against the post-close cutoff.
5. Stage 1 computes channel states and industry ranking.
6. Stage 2 computes stock scores from `Stage1Result` and disclosures.
7. Snapshot persistence and publication follow the same path as pre-open.

**Post-close rule:**
- Market-close relative strength and internal breadth are computed from day T close data and first affect day T+1 snapshots.

### 4.4 Manual Ad-Hoc Run

**Trigger:** CLI invocation.

**Rules:**
- Uses the same runner contract as scheduled runs.
- Must explicitly declare run mode and timestamp basis.
- Must be tagged as manual in metadata.
- Must not bypass persistence or immutability rules.

### 4.5 Backtest Replay

**Trigger:** CLI date-range invocation.

**Sequence:**
1. Backtest engine enumerates trading days in the requested range.
2. For each replay day, it materializes point-in-time inputs available as of the replay timestamp.
3. It builds the same `ScoringContext` contract used in live mode.
4. It applies next-trading-day timing rules for slow-base and applicable overlay signals.
5. It runs Stage 1, then Stage 2.
6. It persists replay snapshots and metrics separately from live outputs.
7. It exports ranking time series and summary metrics.
8. It may process independent replay days in parallel, but no worker may see future data from another day.

**Backtest invariants:**
- No forward visibility into future disclosures or close-based metrics.
- Corrections filed on day T cannot change outputs before day T.
- Live-mode contracts and backtest-mode contracts must remain structurally compatible.

### 4.6 Failure Boundaries

- Stage 1 failure stops Stage 2.
- Persistence failure stops publication.
- Publisher failure after persistence leaves the snapshot unpublished; it does not mutate the stored snapshot in place.

---

## 5. Timing and Point-in-Time Invariants

This section is mandatory because correctness depends on when each input becomes eligible for use.

| Timestamp / boundary | Meaning | Enforcement |
|---|---|---|
| `as_of_timestamp` | Point-in-time boundary for the run | Runner and backtest engine must set it explicitly |
| `data_timestamp` | Newest eligible source data included in the run | Clients and repositories must honor the boundary |
| `run_timestamp` | Actual wall-clock execution time | Runner/backtest records it for audit |
| `publication_timestamp` | Time the snapshot became visible | Publisher sets it only after persistence succeeds |

### 5.1 Invariants

- Pre-open and post-close are the only scheduled publication points.
- Macro state may change internally between runs, but published output changes only at the next scheduled run.
- DART filings and corrections become visible only after the filing is available to the run.
- Day T close data affects day T+1 snapshots, not day T snapshots, when the source spec marks the signal as slow/base or next-day overlay.
- The price-type fast-overlay threshold is 5% versus the latest workday close.
- Every client or repository method used in replay must accept a timestamp or date boundary.
- `Stage1Result` records the PIT basis used for Stage 1.
- Snapshot metadata must distinguish data, run, and publication timestamps.

---

## 6. Canonical Contracts and Config Artifacts

### 6.1 Config Artifact: `ExposureMatrix`

The exposure matrix is a validated YAML config artifact, not a runtime-scored output.

| Field | Type | Notes |
|---|---|---|
| `industry_code` | string | Must cover every industry in the MVP universe |
| `channel_key` | enum(`G`, `IC`, `FC`, `ED`, `FX`) | One coefficient per channel |
| `exposure` | int in `{-1, 0, +1}` | Manual interpretability is the MVP rule |

**Ownership:**
- Produced by config loading.
- Consumed by Stage 1 base-score computation.
- Validated for complete industry coverage before scoring starts.

### 6.2 Runtime Contract Table

| Contract | Key fields | Produced by | Consumed by | Persistence note |
|---|---|---|---|---|
| `ChannelState` | `channel_key`, `state`, `confidence`, `observed_at`, `effective_at`, `source` | Stage 1 channel-state logic | Stage 1 base score, overlay, logs | Stored in DB and snapshot metadata as needed |
| `IndustryScore` | `industry_code`, `industry_name`, `base_score`, `overlay_adjustment`, `final_score`, `rank`, `positive_contribution`, `negative_penalty_abs` | Stage 1 ranking | Stage 2, publisher, backtest | Immutable after publish |
| `Stage1Result` | `run_id`, `run_type`, `as_of_timestamp`, `channel_states`, `industry_scores`, `config_version`, `warnings` | Stage 1 pipeline | Stage 2, runner, backtest, persistence | Primary handoff contract between stages |
| `DARTEvent` | `stock_code`, `disclosure_id`, `received_at`, `disclosure_type`, `block`, `impact_base`, `flags`, `structured_fields`, `classification_confidence` | DART client / classifier | Stage 2 scoring, DB, analytics | Incremental watermarking required |
| `StockScore` | `stock_code`, `industry_code`, `raw_dart_score`, `raw_industry_score`, `z_dart`, `z_industry`, `financial_score`, `final_score`, `rank`, `flags`, `block_breakdown` | Stage 2 ranking | Publisher, backtest, downstream consumers | Store raw and normalized values together |
| `ScoringContext` | `run_metadata`, `stage1_result`, `config`, `calendar_context`, `mode` | Runner or backtest engine | Stage 2 scoring | No raw API clients in this boundary |
| `Snapshot` | `run_id`, `run_type`, `as_of_timestamp`, `data_timestamp`, `run_timestamp`, `publication_timestamp`, `industry_scores`, `stock_scores`, `status`, `warnings` | Runner / publisher / backtest | Downstream consumers | Immutable after publish |

### 6.3 Contract Rules

- Stage 2 must validate that all industry codes in the stock universe have matching Stage 1 scores.
- `StockScore` uses cross-sectional z-scores per snapshot.
- If the standard deviation for a component is zero, that normalized value is `0`.
- `lambda` is applied after normalization.
- `FinancialScore` remains `0` in MVP, but the field must exist in the model and formula.
- `ChannelState` exposes an internal confidence value, but the discrete state label remains the public runtime contract.
- `Snapshot` becomes immutable once published.

### 6.4 DART Decay Defaults

The decay function uses exponential decay in trading-day units.

| Disclosure block | Default half-life (trading days) |
|---|---:|
| `supply_contract` | 20 |
| `treasury_stock` | 10 |
| `facility_investment` | 60 |
| `dilutive_financing` | 60 |
| `correction_cancellation_withdrawal` | 10 |
| `governance_risk` | 120 |

The half-life grid is restricted to `{5, 10, 20, 60, 120, 252}` for MVP interpretability.

---

## 7. Persistence, Publication, and Immutability

### 7.1 Logical Storage Targets

| Logical table / artifact | Owner | Notes |
|---|---|---|
| `channel_states` | DB layer | Stores Stage 1 channel outputs |
| `industry_scores` | DB layer | Stores Stage 1 rankings |
| `dart_events` | DB layer | Stores incremental disclosures and classification metadata |
| `stock_scores` | DB layer | Stores Stage 2 output |
| `snapshots` | DB layer | Stores draft and published snapshots |
| `snapshot_publications` | Publisher / DB layer | Stores publication audit trail |
| `scheduler_jobs` | Scheduler / DB layer | APScheduler job store in the same SQLite DB |

### 7.2 Ownership Rules

- Repositories own CRUD semantics.
- Stage 1 and Stage 2 do not perform raw SQL or DB-engine manipulation.
- Snapshot publication state is controlled by orchestration and repository code only.
- Published snapshots cannot be updated in place.
- Parquet exports are append-only immutable artifacts.

### 7.3 Immutability Contract

- Snapshots may exist in draft state during processing.
- Once marked `published`, further mutation attempts must raise `ImmutableSnapshotError`.
- Re-running a day must create a new run record instead of mutating a published snapshot.

### 7.4 Parquet Export Contract

Each published snapshot must be exportable to parquet with:
- run metadata
- industry ranking table
- stock ranking table
- optional audit metadata block
- publication timestamp and cutoff basis

---

## 8. Error Handling, Retries, Idempotency, and Recovery

### 8.1 Error Categories

| Category | Example | Default behavior |
|---|---|---|
| external transient | timeout, 5xx, rate-limit | Retry with bounded exponential backoff |
| external permanent | invalid auth, schema rejection | Fail the stage and log/alert |
| integrity | missing industry code mapping | Fail the stage or run |
| neutralizable classification | unknown DART type | Log and assign neutral impact |
| persistence | DB write failure | Fail the run before publish |
| recovery | missed-run replay conflict | Halt recovery and alert |

### 8.2 Retry Policy

- External API reads use exponential backoff with bounded retries.
- Retry attempt count and cause must be logged.
- Retry policy values belong in config, not hardcoded business logic.
- Retry does not excuse violated integrity or publication rules.

### 8.3 Idempotency Rules

- Each run has a unique `run_id`.
- Reruns must not mutate a previously published snapshot.
- Incremental DART ingestion must track the last successful watermark.
- Scheduler recovery must detect missed runs before normal scheduling resumes.
- Backtest output must be reproducible from stored data and explicit cutoff boundaries.

### 8.4 Recovery Behavior

- Scheduler startup checks for missed runs since the last successful execution.
- Missed runs are replayed before the scheduler resumes normal operation.
- APScheduler job state lives in the same SQLite DB via `SQLAlchemyJobStore`.
- The exact internal reconciliation key and conflict policy remain open; this draft only commits to the observable behavior above.

### 8.5 Degraded-Mode Rules

- Stage 2 does not run if Stage 1 fails.
- Unknown DART disclosure types are neutral and counted/logged.
- Manual macro override remains allowed for development and testing.
- If historical data audit proves incomplete, backtest scope must be constrained or converted to a forward-collection replay flow rather than silently fabricating coverage.
- Parallel replay is allowed, but it must never leak future data across replay days.

---

## 9. Traceability and Verification Matrix

This matrix links PRD requirement groups to SDD sections, planned modules, and primary verification modes.

| Requirement group | SDD sections | Planned modules | Primary verification |
|---|---|---|---|
| F1 Stage 1 macro, overlay, and ranking | 2, 3, 4, 5, 6, 7, 8 | `config/exposure_matrix.py`, `stage1/channel_state.py`, `stage1/base_score.py`, `stage1/overlay.py`, `stage1/ranking.py` | Unit, integration, backtest |
| F2 Stage 2 DART scoring and normalization | 2, 4, 5, 6, 8, 9 | `stage2/classifier.py`, `stage2/decay.py`, `stage2/dart_score.py`, `stage2/context.py`, `stage2/normalize.py`, `stage2/merge.py`, `stage2/ranking.py` | Unit, integration, backtest |
| F3 Scheduler, pipeline, and publication | 3, 4, 5, 7, 8, 9 | `pipeline/scheduler.py`, `pipeline/runner.py`, `pipeline/publisher.py`, `db/database.py`, `db/tables.py` | Integration, smoke, recovery tests |
| F4 Backtest engine and PIT correctness | 4, 5, 7, 8, 9 | `backtest/engine.py`, `backtest/calendar.py`, `backtest/snapshot_store.py` | Backtest, regression |
| F5 Data ingestion and external clients | 3, 4, 7, 8, 9 | `data/krx_client.py`, `data/dart_client.py`, `data/macro_client.py` | Unit, integration, API-contract |
| NF1-NF4 performance, reliability, extensibility, maintainability | 7, 8, 10 | `pipeline/*`, `db/*`, logging/metrics, tests | Performance smoke, failure-path, lint, typecheck |

### 9.1 Traceability Notes

- `F2.13` and `F2.14` are anchored by `Stage1Result` and `ScoringContext`.
- `F3.4` through `F3.8` are anchored by the runner, repository layer, and `Snapshot` immutability.
- `F4.2` through `F4.10` are anchored by `as_of_timestamp`, `data_timestamp`, and backtest replay boundaries.
- `NF2.4` maps to scheduler recovery behavior and persistent job state.

---

## 10. Open Design Decisions / Pending Finalization

The following items remain intentionally open because the current document set is not enough to close them without a new decision:

1. Final low-level persistence schema details, including indexes, unique constraints, and versioning / migration strategy.
2. Final downstream publisher / consumer contract beyond immutable snapshot export.
3. Final scheduler reconciliation key and conflict policy for missed-run replay.
4. Exact channel-threshold methodology for the items still marked `[DEFERRED]` in the source spec.
5. Final alerting and SLO boundaries for operational recovery behavior.
6. Final historical-data completeness outcome for backtest source coverage.

### 10.1 Already Resolved and Folded In

These are not open questions in this draft and should not be reopened unless the source docs change:
- official KRX endpoints as the primary source
- the exposure-matrix CSV-backed taxonomy
- DART key handling through environment-only secret injection
- hardcoded MVP holiday list
- cross-sectional z-score normalization with post-normalization `lambda`
- the DART half-life grid and default block values
- the 5% price-type overlay trigger threshold
- parallel replay support for backtest days

---

## 11. Immediate Follow-Up Tasks

1. Fill in final low-level schema and index details when implementation modules exist.
2. Add sequence diagrams only if a later implementation review needs them; the stepwise runtime sequences here are sufficient for v0.2.
3. Bind requirement IDs into implementation tests as modules are created.
4. Revisit scheduler reconciliation keying and publisher contracts only when code forces a concrete choice.
5. Link this file from `doc/plan.md` and future implementation PRs.
