# Repository Orientation for Users and AI Agents

This document is a **navigation and ingestion map**.
It exists so that a new user or AI agent can figure out, quickly and correctly:
- what to read first,
- where the real entrypoints are,
- where inputs/outputs/state live,
- and how to avoid common wrong assumptions.

This file is intentionally practical.
For full runtime behavior, use `doc/program-context.md`.
For code/module structure, use `doc/code-context.md`.

---

## 1. Recommended reading order

If you need the shortest correct ingestion path, read in this order:

1. `doc/program-context.md` — system behavior and runtime semantics
2. `doc/repository-orientation.md` — this file, for repository navigation and file-purpose guidance
3. `doc/code-context.md` — module/code ownership map
4. code entrypoints:
   - `src/macro_screener/cli.py`
   - `src/macro_screener/pipeline/runner.py`
   - `src/macro_screener/pipeline/publisher.py`

If you only have time to load three documents into an AI context window, the preferred trio is:
- `doc/program-context.md`
- `doc/repository-orientation.md`
- `doc/code-context.md`

---

## 2. Source-of-truth hierarchy for the 3-doc context set

Use this hierarchy when different files answer different kinds of questions:

| Question | Best file to start with | Why |
| --- | --- | --- |
| What does the program do end-to-end? | `doc/program-context.md` | Most complete runtime/behavior summary |
| Where should I look in the repo? | `doc/repository-orientation.md` | Fast navigation and file-role map |
| How is the code structured? | `doc/code-context.md` | Module/ownership boundary map |
| What does the runtime actually execute? | `src/macro_screener/pipeline/runner.py` | Executable behavior |
| What gets published? | `src/macro_screener/pipeline/publisher.py` | Real publication contract |

---

## 3. Top-level directories and what they mean

### `src/macro_screener/`
Main application package.
Contains runtime orchestration, adapters, Stage 1/Stage 2 scoring, models, config loader helpers, and persistence logic.

### `macro_screener/`
Top-level wrapper package.
Exists so `python -m macro_screener ...` works from repository root without entering `src/`.

### `config/`
Default runtime config and Stage 1 artifact.
Important files:
- `config/default.yaml`
- `config/stage1_sector_rank_tables.v1.json`

### `doc/`
Human-readable documentation.
The intended self-contained context set is:
- `doc/program-context.md`
- `doc/repository-orientation.md`
- `doc/code-context.md`

### `tests/`
Regression and runtime validation.
Use tests when you want expected behavior, not just implementation behavior.

### `src/data/`
Default runtime output/state location.
Many users expect output under repository-root `data/`, but the default CLI output root is `src`, so runtime output lands under `src/data/...`.

---

## 4. Current runnable entrypoints

### CLI entrypoint
- `src/macro_screener/cli.py`

Commands exposed there:
- `show-config`
- `manual-run`
- `demo-run`
- `scheduled-run`
- `backtest-run`
- `backtest-stub`

### Runtime entrypoint
- `src/macro_screener/pipeline/runner.py`

This is the real orchestration file for `manual-run` and `scheduled-run`.

### Publication entrypoint
- `src/macro_screener/pipeline/publisher.py`

This is the right place to inspect when a run seems to “finish” but outputs are missing, partial, or malformed.

---

## 5. Input map

### Config and reference inputs
- `config/default.yaml` — runtime defaults, paths, thresholds, weights, decay settings
- `config/stage1_sector_rank_tables.v1.json` — Stage 1 artifact
- `stock_classification.csv` — local stock classification authority
- `data/reference/industry_master.csv` — derived taxonomy authority

Important distinction:
- `config/default.yaml` defines runtime defaults
- `config/stage1_sector_rank_tables.v1.json` defines the current structural Stage 1 artifact
- `stock_classification.csv` and `industry_master.csv` define the taxonomy universe that scoring is applied to

### Provider adapters
- `src/macro_screener/data/macro_client.py` — macro loading/classification
- `src/macro_screener/data/krx_client.py` — stock-universe loading
- `src/macro_screener/data/dart_client.py` — disclosure ingestion / cache / cursor

### Stage logic
- `src/macro_screener/stage1/` — industry-scoring path
- `src/macro_screener/stage2/` — stock-scoring path

### Persistence
- `src/macro_screener/db/store.py` — SQLite persistence and watermarks

---

## 6. Output and state map

With the default config, CLI runs publish under `src/data/`.

Important default locations:
- snapshot root: `src/data/snapshots/<run_id>/`
- latest pointer: `src/data/snapshots/latest.json`
- SQLite registry: `src/data/macro_screener.sqlite3`
- DART cache: `src/data/cache/dart/latest.json`

Published snapshot artifacts currently include:
- `industry_scores.csv`
- `industry_scores.parquet`
- `screened_stock_list.csv`
- `screened_stocks_by_score.json`
- `screened_stocks_by_industry.json`
- `snapshot.json`
- `stock_scores.parquet`

---

## 7. Fast debugging routes

### “Why did a run fail?”
Start with:
1. `src/macro_screener/pipeline/runner.py`
2. `src/macro_screener/pipeline/publisher.py`
3. the relevant adapter in `src/macro_screener/data/`
4. `src/macro_screener/db/store.py`

### “Why are Stage 1 results strange?”
Start with:
1. `src/macro_screener/stage1/ranking.py`
2. `config/stage1_sector_rank_tables.v1.json`
3. `src/macro_screener/data/macro_client.py`
4. `src/macro_screener/data/reference.py`

Typical Stage 1 confusion sources:
- neutral-band interpretation
- channel-state construction
- rank-table artifact contents
- taxonomy mapping drift

### “Why are Stage 2 results strange?”
Start with:
1. `src/macro_screener/stage2/ranking.py`
2. `src/macro_screener/stage2/classifier.py`
3. `src/macro_screener/data/dart_client.py`

Typical Stage 2 confusion sources:
- disclosure visibility by cutoff
- DART cursor/cache behavior
- normalized ranking vs absolute value interpretation
- the `0.35` industry contribution weight

### “Why is output missing or partial?”
Start with:
1. `src/macro_screener/pipeline/publisher.py`
2. `src/macro_screener/db/store.py`
3. the specific run directory under `src/data/snapshots/<run_id>/`
4. `src/data/snapshots/latest.json`

---

## 8. Common wrong assumptions

### Wrong assumption 1
“Output should be under repository-root `data/`.”

Reality:
- default CLI output root is `src`
- so default runtime outputs land under `src/data/...`

### Wrong assumption 2
“`manual-run` is fundamentally different from `scheduled-run`.”

Reality:
- both are triggers of the same main live-provider pipeline
- differences are mainly run context and schedule semantics

### Wrong assumption 3
“DART cache = all filings for the day.”

Reality:
- DART cache is cutoff-aware and cursor-aware
- it is not just a naive dump of every filing seen today

### Wrong assumption 4
“Process exit 0 means snapshot success.”

Reality:
A meaningful success shape includes:
- run dir exists,
- `snapshot.json` exists,
- `latest.json` updated,
- SQLite snapshot row written.

---

## 9. Minimal context package for another AI

If another user wants to give an AI enough context to work effectively on this codebase, the recommended package is:
- `doc/program-context.md`
- `doc/repository-orientation.md`
- `doc/code-context.md`

These three are intended to be enough for most practical coding and debugging tasks without sending older deleted authority docs.
