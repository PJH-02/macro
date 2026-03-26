# Repository Orientation

This file is the practical map for finding the right files quickly.
Use it after `doc/program-context.md` when you need to navigate the repository rather than reason about the runtime at a high level.

## 1. Recommended reading order

Shortest reliable onboarding path:
1. `README.md`
2. `doc/program-context.md`
3. `doc/repository-orientation.md`
4. `doc/code-context.md`
5. code entrypoints:
   - `src/macro_screener/cli.py`
   - `src/macro_screener/pipeline/runner.py`
   - `src/macro_screener/pipeline/publisher.py`

## 2. Top-level directories

### `src/macro_screener/`
Main application package.
Contains the CLI, pipeline orchestration, providers, Stage 1/Stage 2 logic, models, and persistence.

### `config/`
Runtime defaults and the current Stage 1 grouped-sector exposure artifact.
Key files:
- `config/default.yaml`
- `config/macro_sector_exposure.v2.json`

### `doc/`
Current human-oriented context docs.
The preferred compact context set is:
- `doc/program-context.md`
- `doc/repository-orientation.md`
- `doc/code-context.md`

### `tests/`
Regression coverage and behavior checks.
Use this when you need expected behavior rather than just reading implementation code.

### `data/`
Repository-level reference and generated data assets.
Important: config paths resolve relative to the output root, so default CLI runs still write to `src/data/...` because the CLI default output root is `src`.

## 3. Current runnable entrypoints

### CLI entrypoint
- `src/macro_screener/cli.py`

Commands exposed there:
- `show-config`
- `demo-run`
- `manual-run`
- `scheduled-run`
- `backtest-run`
- `backtest-stub`

### Runtime entrypoint
- `src/macro_screener/pipeline/runner.py`

This is the real orchestration path for manual, scheduled, and demo execution. Backtest commands are exposed through the CLI via `src/macro_screener/mvp.py` and the `src/macro_screener/backtest/` package.

### Publication entrypoint
- `src/macro_screener/pipeline/publisher.py`

This is the first place to inspect when a run appears to succeed but snapshot artifacts or pointers are missing.

## 4. Input map

### Configuration and reference inputs
- `config/default.yaml` — runtime defaults, policy flags, paths, decay settings
- `config/macro_sector_exposure.v2.json` — current grouped-sector exposure artifact for Stage 1
- `stock_classification.csv` — local stock classification authority
- `data/reference/industry_master.csv` — derived grouped-sector master file

### Provider adapters
- `src/macro_screener/data/macro_client.py` — macro loading and channel-state classification
- `src/macro_screener/data/krx_client.py` — stock-universe loading plus grouped-sector mapping joins
- `src/macro_screener/data/dart_client.py` — disclosure ingestion, cursor handling, and cache management
- `src/macro_screener/data/reference.py` — grouped-sector taxonomy/exposure helpers and artifact builders

### Stage logic
- `src/macro_screener/stage1/` — grouped-sector scoring
- `src/macro_screener/stage2/` — stock scoring

### Persistence
- `src/macro_screener/db/store.py` — SQLite snapshot registry and watermark state

## 5. Output and state map

With the default CLI output root, runtime outputs are written under `src/data/`.

Important default locations in practice:
- snapshot root: `src/data/snapshots/<run_id>/`
- latest pointer: `src/data/snapshots/latest.json`
- SQLite registry: `src/data/macro_screener.sqlite3`
- DART cache: `src/data/cache/dart/latest.json`

Published artifact filenames currently include:
- `industry_scores.csv`
- `industry_scores.parquet`
- `screened_stock_list.csv`
- `screened_stocks_by_score.json`
- `screened_stocks_by_industry.json`
- `snapshot.json`
- `stock_scores.parquet`

## 6. Fast debugging routes

### “Why did the run fail?”
Start with:
1. `src/macro_screener/pipeline/runner.py`
2. `src/macro_screener/pipeline/publisher.py`
3. the relevant provider under `src/macro_screener/data/`
4. `src/macro_screener/db/store.py`

### “Why are Stage 1 results strange?”
Start with:
1. `src/macro_screener/stage1/ranking.py`
2. `src/macro_screener/data/reference.py`
3. `config/macro_sector_exposure.v2.json`
4. `src/macro_screener/data/macro_client.py`

### “Why are Stage 2 results strange?”
Start with:
1. `src/macro_screener/stage2/ranking.py`
2. `src/macro_screener/stage2/classifier.py`
3. `src/macro_screener/stage2/decay.py`
4. `src/macro_screener/data/dart_client.py`

### “Why are outputs missing or partial?”
Start with:
1. `src/macro_screener/pipeline/publisher.py`
2. `src/macro_screener/db/store.py`
3. the run directory under `src/data/snapshots/<run_id>/`
4. `src/data/snapshots/latest.json`

## 7. Common wrong assumptions

- The old Stage 1 rank-table artifact is no longer the active scoring contract; the code now reads grouped-sector exposures from `config/macro_sector_exposure.v2.json`.
- `industry_*` field names and filenames remain for compatibility, even though the active business concept is grouped sector.
- Config paths saying `data/...` do not mean outputs land in repository-root `data/`; they are resolved against the chosen output root.
