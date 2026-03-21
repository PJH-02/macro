# Implementation Plan: Macro Regime-Based Two-Stage Screening System (MVP)

> Purpose: define the implementation order, delivery milestones, stack choices, testing expectations, and operational rules for the MVP.

## 1. Inputs to this plan

This implementation plan assumes:
- `doc/strategy.md` is the source of high-level architecture and final MVP operating decisions
- `doc/prd.md` is the source of product requirements

## 2. Technology and delivery baseline

### 2.1 Core stack

| Area | MVP choice |
|---|---|
| Language | Python 3.11+ |
| Package management | `uv` or `pip + venv` |
| Data processing | `pandas`, `numpy` |
| HTTP/API clients | synchronous `httpx` |
| Scheduler | `APScheduler` |
| Trading calendar | XKRX-aware calendar helper + hardcoded MVP holiday list |
| Persistence | SQLite + parquet |
| Config | typed settings + YAML |
| CLI | simple command entrypoints |
| Logging | structured JSON logging |
| Testing | unit + integration + backtest suites |

### 2.2 Delivery principles
1. deliver the MVP in thin vertical slices
2. keep Stage 1 and Stage 2 contract boundaries explicit
3. make point-in-time correctness and immutability first-class from the start
4. prefer externalized configuration over hardcoded behavior
5. treat degraded-mode behavior as explicit policy, not ad-hoc fallback

## 3. Target repo layout

```text
src/macro_screener/
  config/
  models/
  data/
  stage1/
  stage2/
  pipeline/
  backtest/
  db/

tests/
  unit/
  integration/
  backtest/
  fixtures/
```

### Module expectations
- `config/` — settings, exposure matrix, runtime overrides
- `models/` — contract-level models (`ChannelState`, `IndustryScore`, `DARTEvent`, `StockScore`, `Snapshot`)
- `data/` — KRX, DART, macro-source boundaries
- `stage1/` — channel-state, scoring, overlays, ranking
- `stage2/` — classification, decay, normalization, merge, ranking
- `pipeline/` — runner, scheduler, publisher
- `backtest/` — replay, calendar, snapshot store
- `db/` — database setup, tables, repositories, immutability enforcement

## 4. Delivery phases

## Phase 1 — foundation

### Goal
Create the runnable project skeleton and shared contracts.

### Deliverables
- project package structure
- config loading and validation
- core models/contracts
- SQLite setup and repository layer
- CLI entry points
- logging/test scaffolding

### Acceptance criteria
- project boots locally
- config loads cleanly
- core models serialize/deserialize cleanly
- snapshot immutability checks exist in the persistence layer

## Phase 2 — Stage 1

### Goal
Implement macro-to-industry scoring.

### Deliverables
- manual/stub channel-state provider
- exposure-matrix loading
- base-score logic
- overlay logic
- industry ranking/tie-breaks
- `Stage1Result` handoff contract

### Acceptance criteria
- channel states are produced for all 5 channels
- industry ranking is produced for the full universe
- close-based next-day timing rules are enforced
- Stage 1 outputs contain the required audit fields

## Phase 3 — Stage 2

### Goal
Implement disclosure-to-stock scoring.

### Deliverables
- DART classifier
- DART event persistence shape
- decay logic
- normalization logic
- stock ranking/tie-breaks
- `ScoringContext` consumption path

### Acceptance criteria
- Stage 2 accepts `Stage1Result`
- full stock ranking is produced
- neutral/unknown classification ratio is logged
- raw and normalized score components are stored together

## Phase 4 — orchestration and publication

### Goal
Turn Stage 1 + Stage 2 into reliable scheduled snapshots.

### Deliverables
- scheduler
- runner
- snapshot persistence
- parquet publisher
- latest snapshot pointer at `data/snapshots/latest.json`
- missed-run recovery flow

### Acceptance criteria
- pre-open and post-close runs work
- manual runs work
- scheduled window dedupe uses `(trading_date, run_type)`
- published snapshots are immutable and never overwritten
- duplicate recovery attempts are skipped rather than overwriting publication

## Phase 5 — backtest and hardening

### Goal
Make the same logic replayable historically and operationally safe.

### Deliverables
- replay engine
- PIT-safe historical materialization
- backtest metrics/export
- alerting metrics
- degraded-mode handling
- operational smoke checks

### Acceptance criteria
- backtest honors PIT rules
- recovery/idempotency behavior is deterministic
- degraded-mode policy is testable
- replay output is isolated from live output namespaces

## 5. Data-source and integration expectations

### 5.1 KRX client
Must support:
- common-stock universe ingestion
- OHLCV ingestion for overlay calculations
- industry mapping ingestion
- security-type filtering that excludes ETFs, ETNs, REITs, infrastructure funds, and other non-equities

### 5.2 DART client
Must support:
- disclosure list retrieval by date/cutoff
- detail retrieval for classified disclosures
- incremental watermarking
- unknown-type neutral fallback behavior

### 5.3 Macro data source
MVP uses **manual/stub mode**.

When real ingestion later replaces stub/manual mode, preferred sources are:
- `ECOS`
- `KOSIS`
- `DART`-derived Korea-related inputs where applicable
- `BIS` for global macro inputs

## 6. Testing strategy

### Unit tests
- channel-state and scoring rules
- overlay rules
- DART classification and decay
- normalization and ranking
- persistence immutability rules

### Integration tests
- Stage 1 pipeline
- Stage 2 pipeline
- full scheduled-run flow
- latest snapshot publishing behavior
- duplicate-window recovery behavior

### Backtest tests
- no look-ahead leakage
- next-day application rules
- replay reproducibility

### Documentation/contract checks
- `Stage1Result`, `ScoringContext`, and snapshot contracts remain consistent with strategy + PRD
- visible 3-doc set remains internally consistent after updates

## 7. Operational rules for MVP

## 7.1 Canonical output contract
- published runs write immutable parquet artifacts
- `data/snapshots/latest.json` points to the canonical latest published snapshot
- SQLite is the operational/audit store, not the primary consumer interface

## 7.2 Scheduled-window identity
- `scheduled_window_key = (trading_date, run_type)`
- `run_id` identifies an execution attempt
- multiple draft attempts are allowed
- at most one published snapshot is allowed per scheduled window
- later duplicate recovery attempts must be marked duplicate/skipped, not overwrite publication

## 7.3 Error handling and degraded mode

| Failure point | MVP behavior |
|---|---|
| KRX API down | retry 3x with backoff; if still failing, abort run and alert |
| DART API down | retry 3x; if still failing, run with stale DART data and flag output |
| Macro source unavailable (`ECOS`/`KOSIS`/`DART`/`BIS`) | use last known channel states and log warning |
| Stage 1 error | abort entire run |
| Stage 2 error | publish Stage 1 results only and flag incomplete run |
| Snapshot write failure | retry once; if still failing, log critical alert and keep unpublished |

## 7.4 Minimal alert matrix

| Condition | Severity | Operator action |
|---|---|---|
| neutral/unknown DART ratio `> 20%` | warning | inspect sample filings and classifier/title-pattern mappings |
| missed scheduled run during recovery | error | inspect scheduler/job-store state and rerun missing window manually |
| snapshot publication failure | critical | inspect DB/parquet write path and rerun same scheduled window |
| repeated API failure after retries | error | inspect source availability and decide whether downstream use should pause |

## 8. Requirement-to-implementation traceability

| Requirement group | Primary implementation surface | Primary verification lane |
|---|---|---|
| Stage 1 scoring (`F1.*`) | `stage1/*`, `models/channel.py`, `models/industry.py` | unit + integration |
| Stage 2 scoring (`F2.*`) | `stage2/*`, `models/dart_event.py`, `models/stock.py` | unit + integration + backtest |
| Pipeline/publishing (`F3.*`) | `pipeline/runner.py`, `pipeline/scheduler.py`, `publisher`, `db/*` | integration + smoke |
| Backtest (`F4.*`) | `backtest/*`, replay/materialization helpers | backtest tests |
| Ingestion (`F5.*`) | `data/krx_client.py`, `data/dart_client.py`, `data/macro_client.py` | unit + integration |
| Reliability / maintainability / security (`NF*`) | cross-cutting across config, db, pipeline, logging, tests | smoke + targeted unit/integration |

## 9. Remaining deferred items

Still intentionally deferred beyond MVP baseline:
- exact SQLite physical DDL, secondary indexes, and migration-tool choice
- non-file-based downstream service/API contract
- exact production channel variables/thresholds beyond manual/stub MVP mode
- finer-grained SLO/alert tuning

## 10. Completion criteria

The MVP documentation/implementation plan is complete enough when:
- strategy, PRD, and plan are mutually consistent
- implementation can proceed without reopening high-level architecture questions
- only low-level physical or post-MVP decisions remain deferred
