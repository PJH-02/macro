# Code Context: Macro Screener Implementation Map

This document explains the **code itself** rather than only the runtime behavior summary.
It is meant for:
- repository users trying to understand where logic lives,
- AI agents that need a code-oriented context file,
- maintainers who want a fast map of module boundaries and responsibilities.

Use this file together with:
- `doc/program-context.md` for end-to-end runtime behavior,
- `doc/repository-orientation.md` for repository navigation.

---

## 1. Codebase shape

Top-level important areas:
- `src/macro_screener/` — main application package
- `macro_screener/` — top-level wrapper package so repo-root execution works
- `config/` — default config + Stage 1 artifact
- `doc/` — human-readable context docs
- `tests/` — regression and runtime validation
- `src/data/` — default runtime outputs and runtime state artifacts

---

## 2. Entry points

### 2.1 CLI
File:
- `src/macro_screener/cli.py`

Responsibilities:
- parse CLI arguments
- choose subcommand
- call the corresponding runtime function
- print machine-readable JSON

Current commands:
- `show-config`
- `manual-run`
- `demo-run`
- `scheduled-run`
- `backtest-run`
- `backtest-stub`

### 2.2 Top-level module execution
Files:
- `macro_screener/__init__.py`
- `macro_screener/__main__.py`

Purpose:
- make `python -m macro_screener ...` work from repo root
- forward the top-level package to `src/macro_screener`

This wrapper exists because the repository uses a `src/` layout but expects operator commands from the repository root.

---

## 3. Runtime orchestration

### 3.1 Main orchestrator
File:
- `src/macro_screener/pipeline/runner.py`

This is the central runtime file.
It is where the application:
- builds run context,
- resolves macro state,
- loads Stage 1/reference inputs,
- loads stock universe,
- loads disclosures,
- computes Stage 1,
- computes Stage 2,
- publishes outputs.

Core functions to know:
- `build_manual_context(...)`
- `run_manual(...)`
- `run_scheduled(...)`
- `run_demo(...)`
- `run_pipeline_context(...)`

Meaning in practice:
- `build_manual_context(...)` creates timestamps and IDs for manual-style runs
- `run_manual(...)` is a thin wrapper that feeds manual context into the main pipeline
- `run_scheduled(...)` does the same for scheduled windows
- `run_pipeline_context(...)` is the real batch pipeline

### 3.2 Runtime bootstrap
File:
- `src/macro_screener/pipeline/runtime.py`

Responsibilities:
- create runtime directories
- initialize SQLite registry
- establish the output-root contract

### 3.3 Publication
File:
- `src/macro_screener/pipeline/publisher.py`

Responsibilities:
- create per-run snapshot directory
- write parquet / CSV / JSON artifacts
- write `snapshot.json`
- update SQLite snapshot records
- update `latest.json`

Important implementation detail:
- nested values are normalized before parquet write
- this prevents parquet failures from empty nested fields such as `block_scores={}`

---

## 4. Data adapters

### 4.1 Macro adapter
File:
- `src/macro_screener/data/macro_client.py`

Responsibilities:
- define fixed series roster by channel
- classify per-series signals
- combine Korea/US signals into channel states
- carry fallback/confidence/warning metadata

Important constructs:
- `FIXED_CHANNEL_SERIES_ROSTER`
- `FIXED_SERIES_CLASSIFIER_SPECS`
- `LiveMacroDataSource`
- `MacroLoadResult`

Why these matter:
- `FIXED_CHANNEL_SERIES_ROSTER` answers “which series feed each channel?”
- `FIXED_SERIES_CLASSIFIER_SPECS` answers “how does a raw series become -1 / 0 / +1?”
- `MacroLoadResult` is the runtime container for channel states plus metadata

### 4.2 DART adapter
File:
- `src/macro_screener/data/dart_client.py`

Responsibilities:
- fetch live disclosures from DART
- paginate through API results
- normalize each item
- filter by cutoff visibility
- maintain structured cursor/watermark state
- write/read the DART cache

Important implementation points:
- same-day disclosures are normalized to the current cutoff
- cursor is structured, not just a plain timestamp
- legacy cutoff-only cursor states are specially handled to avoid replay drift

DART behavior is shaped by three layers:
1. fetch window,
2. cutoff visibility filtering,
3. cursor advancement / watermark persistence.

### 4.3 KRX adapter
File:
- `src/macro_screener/data/krx_client.py`

Responsibilities:
- load stock universe
- support live/common-stock universe construction
- map stocks into the local classification authority

Operationally, this is one of the heavier runtime stages in a full manual run.

### 4.4 Reference-data builder
File:
- `src/macro_screener/data/reference.py`

Responsibilities:
- derive `industry_master.csv`
- own taxonomy helper logic
- support Stage 1 reference/artifact lookup

---

## 5. Stage 1 implementation

### 5.1 Main ranking logic
File:
- `src/macro_screener/stage1/ranking.py`

Responsibilities:
- convert channel state into industry contributions
- load and use the Stage 1 rank-table artifact
- produce `Stage1Result`

Current reality:
- active path is rank-table-backed
- contributions are deterministic
- output includes per-channel contribution detail

The runtime does not just “multiply exposure by signal”.
Instead it:
- selects a regime-specific rank table,
- maps rank to a score,
- applies channel weight,
- sums contributions,
- then adds overlay.

### 5.2 Channel-state record building
File:
- `src/macro_screener/stage1/channel_state.py`

Responsibilities:
- convert raw channel values into `ChannelState` records with metadata

### 5.3 Supporting score helpers
Files:
- `src/macro_screener/stage1/base_score.py`
- `src/macro_screener/stage1/overlay.py`

Responsibilities:
- contribution maps / score summarization
- overlay adjustment resolution

---

## 6. Stage 2 implementation

### 6.1 Main stock scoring
File:
- `src/macro_screener/stage2/ranking.py`

Responsibilities:
- group disclosures by stock
- classify and decay events
- compute raw DART scores
- normalize DART and industry scores
- create ranked `StockScore` rows

### 6.2 Supporting modules
Files:
- `src/macro_screener/stage2/classifier.py`
- `src/macro_screener/stage2/decay.py`
- `src/macro_screener/stage2/normalize.py`

Responsibilities:
- map disclosure text/code to block names
- compute decayed contribution by trading days
- normalize cross-sectional scores

---

## 7. Models and persistence

### 7.1 Contracts
File:
- `src/macro_screener/models/contracts.py`

Defines:
- `Stage1Result`
- `Snapshot`
- `StockScore`
- `IndustryScore`
- `ChannelState`
- scheduling/run metadata types

### 7.2 SQLite persistence
File:
- `src/macro_screener/db/store.py`

Responsibilities:
- initialize schema
- persist snapshots
- persist scheduled-window publication markers
- persist ingestion watermarks
- persist channel-state snapshots

Operationally important tables:
- `snapshots`
- `published_snapshots`
- `ingestion_watermarks`
- `channel_state_snapshots`

---

## 8. Configuration surfaces

Files:
- `config/default.yaml`
- `src/macro_screener/config/defaults.py`
- `src/macro_screener/config/types.py`
- `src/macro_screener/config/loader.py`

Responsibilities:
- define default runtime policy
- resolve paths relative to output root
- carry default thresholds, weights, and decay settings
- load `.env` + YAML config

Important operational detail:
- config paths are relative to the chosen output root
- CLI defaults the output root to `src`
- therefore default runtime outputs land under `src/data/...`

---

## 9. Output and artifact contract in code

Current default output tree:
- `src/data/cache/dart/latest.json`
- `src/data/snapshots/<run_id>/...`
- `src/data/snapshots/latest.json`
- `src/data/macro_screener.sqlite3`

Published artifact filenames currently include:
- `industry_scores.csv`
- `industry_scores.parquet`
- `screened_stock_list.csv`
- `screened_stocks_by_score.json`
- `screened_stocks_by_industry.json`
- `snapshot.json`
- `stock_scores.parquet`

These filenames are not just convenience outputs.
They are the practical publication contract consumed by downstream users and debugging workflows.

---

## 10. Where to start for common tasks

### “Why did a run fail?”
Read in this order:
1. `src/macro_screener/pipeline/runner.py`
2. `src/macro_screener/pipeline/publisher.py`
3. the relevant adapter under `src/macro_screener/data/`
4. `src/macro_screener/db/store.py`

### “Why is Stage 1 score behaving this way?”
Read:
1. `src/macro_screener/stage1/ranking.py`
2. `config/stage1_sector_rank_tables.v1.json`
3. `src/macro_screener/data/macro_client.py`
4. `src/macro_screener/data/reference.py`

### “Why is Stage 2 score behaving this way?”
Read:
1. `src/macro_screener/stage2/ranking.py`
2. `src/macro_screener/stage2/classifier.py`
3. `src/macro_screener/data/dart_client.py`

### “What exactly gets published?”
Read:
1. `src/macro_screener/pipeline/publisher.py`
2. `src/macro_screener/models/contracts.py`
3. `src/macro_screener/db/store.py`

---

## 11. AI-agent usage note

If another user wants to give an AI full repository context, the minimum useful set is:
- `doc/program-context.md`
- `doc/repository-orientation.md`
- `doc/code-context.md`

That set gives:
- product/runtime scope
- runtime flow
- repository navigation
- code ownership boundaries
- output contract
- current implementation posture
