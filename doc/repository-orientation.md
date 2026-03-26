# Repository Orientation

## Read in this order

1. `doc/program-context.md`
2. `doc/repository-orientation.md`
3. `doc/code-context.md`
4. `doc/plan.md`

## Main directories

- `src/macro_screener/` — application package
- `config/` — runtime config and sector exposure artifact
- `doc/` — human-readable docs
- `tests/` — regression tests
- `src/data/` — default runtime output/state

## Main entrypoints

- CLI: `src/macro_screener/cli.py`
- Runtime: `src/macro_screener/pipeline/runner.py`
- Publisher: `src/macro_screener/pipeline/publisher.py`

## Important files for the current refactor

- `src/macro_screener/data/reference.py`
  - grouped-sector taxonomy
  - exhaustive label mapping
  - default sector exposure matrix
- `src/macro_screener/data/krx_client.py`
  - stock-universe load
  - grouped-sector assignment at stock level
  - sector exposure row load
- `src/macro_screener/stage1/ranking.py`
  - Stage 1 grouped-sector scoring
- `src/macro_screener/stage2/ranking.py`
  - Stage 2 full-universe stock scoring
- `src/macro_screener/models/contracts.py`
  - result contracts / serialization shape

## Output map

With the default config, snapshots are published under `src/data/snapshots/<run_id>/`.

Important filenames:
- `industry_scores.csv`
- `industry_scores.parquet`
- `screened_stock_list.csv`
- `screened_stocks_by_score.json`
- `screened_stocks_by_industry.json`
- `snapshot.json`
- `stock_scores.parquet`

## Avoid these wrong assumptions

- “industry” in a filename always means the active taxonomy is fine-grained industry.
  - Not true anymore; current scoring is grouped-sector based.
- Stage 2 is sector-gated.
  - Not true; current Stage 2 scores the full universe.
- The old rank-table artifact still defines Stage 1 behavior.
  - Not true; the active target is the sector exposure matrix path.
