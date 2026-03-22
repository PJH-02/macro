# Macro Screener MVP

[한국어 버전](README.ko.md)

A minimal, runnable MVP for a **macro regime-based two-stage Korean equity screener**.

The final human-facing doc set is:
- `doc/strategy.md`
- `doc/prd.md`
- `doc/plan.md`
- `doc/open-questions.md`

## What the program does

This screener works in two stages.

### Stage 1 — Industry ranking
Stage 1 classifies five macro channels and converts them into a full industry ranking.

Channels:
- `G` — Growth / Activity
- `IC` — Inflation / Cost
- `FC` — Financial Conditions
- `ED` — External Demand
- `FX` — Foreign Exchange

The final MVP target is a **Korea + US external macro** design with:
- Korea macro/statistical inputs from `ECOS` / `KOSIS`
- US external-macro inputs via `FRED` / `ALFRED` or an equivalent official-source adapter layer
- authoritative stock and industry filtering from `stock_classification.csv`

### Stage 2 — Stock ranking
Stage 2 converts DART-style disclosure events into stock scores and combines them with the Stage 1 industry context.

Outputs:
- full industry ranking
- full stock ranking
- immutable snapshot artifacts

There is **no hard cutoff** in the MVP. The result is a full ranking, not a final trading list.

## Current implementation status

The current codebase already provides:
- real package boundaries under `src/macro_screener/`
- real ranking logic for Stage 1 and Stage 2
- snapshot publication to **parquet + SQLite**
- `manual`, `demo`, `scheduled`, and `backtest` execution paths

Important current-state note:
- the code still contains manual/file/demo fallback behavior in several data paths
- the final production target is defined by the doc set above, not by the current fallback-heavy runtime shape

## Data boundaries in the code today

Current adapter seams live in:
- `src/macro_screener/data/macro_client.py`
- `src/macro_screener/data/krx_client.py`
- `src/macro_screener/data/dart_client.py`

Current runtime seams live in:
- `src/macro_screener/pipeline/runner.py`
- `src/macro_screener/pipeline/scheduler.py`
- `src/macro_screener/backtest/engine.py`

## Publication contract

The canonical downstream MVP contract is:
- immutable parquet artifacts
- latest pointer file at `data/snapshots/latest.json`
- SQLite as operational/audit storage, not the primary external consumer contract

## Notes

- This project is still an MVP.
- The final product scope is a **batch screener**, not a portfolio/execution system.
- Future/reference providers such as BIS, OECD, and IMF are not required MVP runtime adapters.
- Korean document translations for the doc set are currently not maintained alongside the English docs.
