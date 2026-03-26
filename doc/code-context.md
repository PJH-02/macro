# Code Context

This file is the code-oriented map of the current implementation.
Use it when you already understand the runtime at a high level and need to know where logic lives.

## 1. Codebase shape

Important top-level areas:
- `src/macro_screener/` — main application package
- `config/` — runtime defaults and Stage 1 grouped-sector artifact
- `doc/` — human-oriented context docs
- `tests/` — regression coverage
- `data/` — reference/generated assets

The codebase uses a `src/` layout, but the CLI default output root is `repo_root/src`, so default runtime outputs land under `src/data/...`.

## 2. Entry points

### CLI
File:
- `src/macro_screener/cli.py`

Responsibilities:
- parse CLI arguments
- expose `show-config`, `demo-run`, `manual-run`, `scheduled-run`, `backtest-run`, `backtest-stub`
- print machine-readable JSON with concise summaries

### Runtime orchestration
File:
- `src/macro_screener/pipeline/runner.py`

Responsibilities:
- build run context
- load config
- resolve macro states
- load grouped-sector exposures
- load stock universe
- load DART disclosures
- compute Stage 1 and Stage 2
- publish snapshots

Important functions to know:
- `build_manual_context(...)`
- `build_demo_snapshot(...)`
- `run_manual(...)`
- `run_scheduled(...)`
- `run_demo(...)`
- `run_pipeline_context(...)`

### Publication
File:
- `src/macro_screener/pipeline/publisher.py`

Responsibilities:
- create the per-run snapshot directory
- write CSV / parquet / JSON artifacts
- write `snapshot.json`
- update the SQLite registry
- update `latest.json` for publishable statuses

## 3. Data adapters

### Macro adapter
File:
- `src/macro_screener/data/macro_client.py`

Responsibilities:
- define the channel-series roster
- classify raw series into `-1 / 0 / +1`
- combine provider data into channel-state results with metadata
- carry confidence, warning, and fallback information

### DART adapter
File:
- `src/macro_screener/data/dart_client.py`

Responsibilities:
- fetch disclosures from DART
- paginate and normalize events
- enforce cutoff visibility
- maintain cache/cursor state
- fall back to stale cache only when policy allows it

### KRX adapter
File:
- `src/macro_screener/data/krx_client.py`

Responsibilities:
- load the stock universe
- join live/taxonomy data
- load grouped-sector exposure rows from `config/macro_sector_exposure.v2.json`
- apply a small set of stock-code sector overrides when taxonomy rows are missing

### Reference-data helpers
File:
- `src/macro_screener/data/reference.py`

Responsibilities:
- define the grouped sector roster
- define `GROUPED_SECTOR_EXPOSURE_MATRIX`
- map stock-classification labels into grouped sectors
- build/load `industry_master.csv`
- build/write the Stage 1 artifact JSON

## 4. Stage 1 implementation

### Main scoring logic
File:
- `src/macro_screener/stage1/ranking.py`

Current behavior:
- validates that all five channel states are present
- converts each channel state into a simple channel score map
- multiplies channel scores by grouped-sector exposures
- adds overlay adjustments
- ranks sectors by final score, then tie-breakers

Important reality:
- the active path is **direct exposure multiplication**, not the older rank-table scoring contract
- call signatures still keep some compatibility parameters (`sector_rank_tables`, `channel_weights`) even though the current implementation ignores them
- output objects still use `IndustryScore` / `industry_scores`

### Supporting Stage 1 modules
- `src/macro_screener/stage1/channel_state.py` — builds `ChannelState` records
- `src/macro_screener/stage1/overlay.py` — resolves overlay adjustments
- `src/macro_screener/stage1/base_score.py` — supporting score helpers

## 5. Stage 2 implementation

### Main scoring logic
File:
- `src/macro_screener/stage2/ranking.py`

Current behavior:
- groups disclosures by stock
- classifies disclosure block type
- decays contributions by trading days elapsed
- computes raw DART scores
- z-scores raw DART scores across the universe
- adds the matched Stage 1 sector score to produce the final stock score

Current final score contract:

```text
final_score = normalized_dart_score + stage1_sector_score
```

### Supporting Stage 2 modules
- `src/macro_screener/stage2/classifier.py`
- `src/macro_screener/stage2/decay.py`
- `src/macro_screener/stage2/normalize.py`

## 6. Models and persistence

### Model contracts
File:
- `src/macro_screener/models/contracts.py`

Important contracts:
- `ChannelState`
- `IndustryScore`
- `Stage1Result`
- `StockScore`
- `Snapshot`
- `SnapshotStatus`
- `RunType` / `RunMode`

Compatibility detail:
- `IndustryScore` / `industry_scores` naming remains in the model layer even though the active taxonomy is grouped sector
- `StockScore` still carries `normalized_financial_score`, but the current Stage 2 pipeline sets it to `0.0`

### Persistence
File:
- `src/macro_screener/db/store.py`

Responsibilities:
- snapshot registry updates
- publication deduplication for scheduled windows
- cursor / watermark support used by runtime adapters

## 7. Tests to inspect first

When checking current behavior, start with:
- `tests/test_manual_run_ids.py`
- Stage 1 / Stage 2 / pipeline regressions near the feature you are changing

`tests/test_manual_run_ids.py` is especially relevant for the current codebase because manual run IDs are now timestamped and suffixed to avoid collisions.
