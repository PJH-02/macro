# Program Context: macro-screener

This file is the runtime-oriented overview for the current codebase.
Use it when you need the shortest accurate explanation of what the program does today.

Pair it with:
- `doc/repository-orientation.md` for file-navigation guidance
- `doc/code-context.md` for module/code ownership guidance

## 1. What the repository does

`macro-screener` is a batch Korean equity screener.
A normal run:
1. resolves a run context,
2. resolves macro channel states,
3. computes Stage 1 grouped-sector scores,
4. loads the stock universe,
5. loads visible DART disclosures,
6. computes Stage 2 stock scores,
7. publishes an immutable snapshot.

This repository is **not** a portfolio construction engine, trade execution system, or intraday service.
It publishes ranked snapshots for downstream consumption.

## 2. Runtime shape

The main orchestration lives in `src/macro_screener/pipeline/runner.py`.
The effective pipeline is:

```text
config + run context
  -> macro-state resolution
  -> Stage 1 grouped-sector scoring
  -> stock-universe loading
  -> DART disclosure loading
  -> Stage 2 stock scoring
  -> snapshot publication
```

Main execution modes exposed by the CLI:
- `demo-run`
- `manual-run`
- `scheduled-run`
- `backtest-run`
- `backtest-stub`

## 3. Stage 1 today

Stage 1 uses five channels:
- `G` — Growth / Activity
- `IC` — Inflation / Cost
- `FC` — Financial Conditions
- `ED` — External Demand
- `FX` — Foreign Exchange

Important current behavior:
- channel states are still discrete `-1 / 0 / +1`
- grouped-sector exposures come from `config/macro_sector_exposure.v2.json`
- the runtime path in `src/macro_screener/stage1/ranking.py` computes sector scores by **direct channel-state × exposure multiplication**
- overlay adjustments are then applied before ranking
- output objects still use `industry_*` field names for compatibility

The taxonomy and exposure matrix live in `src/macro_screener/data/reference.py`.
That module defines the grouped sector roster, the grouped-sector exposure matrix, and the stock-classification mapping helpers.

## 4. Stage 2 today

Stage 2 lives in `src/macro_screener/stage2/`.
The runtime behavior in `src/macro_screener/stage2/ranking.py` is:
- classify DART events into block types,
- decay each event by trading days elapsed,
- aggregate raw DART score by stock,
- z-score the raw DART scores across the stock universe,
- add the matched Stage 1 sector score.

Current final score formula:

```text
final_score = normalized_dart_score + stage1_sector_score
```

Notes:
- Stage 2 runs on the full stock universe; Stage 1 does not act as a hard gate
- `normalized_financial_score` remains in the model contract but is currently `0.0`
- unknown DART classifications are treated as neutral and can emit a warning if their ratio is too high

## 5. Providers and inputs

### Active runtime providers
- `ECOS` / `FRED` / optional `KOSIS` via `src/macro_screener/data/macro_client.py`
- `DART` via `src/macro_screener/data/dart_client.py`
- `KRX` via `src/macro_screener/data/krx_client.py`

### Important local inputs
- `config/default.yaml`
- `config/macro_sector_exposure.v2.json`
- `stock_classification.csv`
- `data/reference/industry_master.csv`

### Not active as main runtime providers
- `BIS`
- `OECD`
- `IMF`

## 6. Output and state contract

Publication lives in `src/macro_screener/pipeline/publisher.py`.
Important output artifacts include:
- `industry_scores.csv`
- `industry_scores.parquet`
- `screened_stock_list.csv`
- `screened_stocks_by_score.json`
- `screened_stocks_by_industry.json`
- `snapshot.json`
- `stock_scores.parquet`

Important runtime details:
- config paths are relative to the chosen output root
- the CLI default output root is `repo_root/src`
- so default CLI runs publish under `src/data/...`
- `latest.json` is updated only for `published` or `incomplete` snapshots
- SQLite snapshot state is updated through the snapshot registry in `src/macro_screener/db/store.py`

## 7. Practical debugging guidance

If a run looks wrong, start here:
- overall control flow: `src/macro_screener/pipeline/runner.py`
- publication/output issues: `src/macro_screener/pipeline/publisher.py`
- macro-state issues: `src/macro_screener/data/macro_client.py`
- taxonomy/exposure issues: `src/macro_screener/data/reference.py`
- stock universe issues: `src/macro_screener/data/krx_client.py`
- disclosure/cursor issues: `src/macro_screener/data/dart_client.py`
- Stage 1 scoring issues: `src/macro_screener/stage1/ranking.py`
- Stage 2 scoring issues: `src/macro_screener/stage2/ranking.py`

## 8. Common pitfalls

- `industry_*` names in models/files do **not** mean the old rank-table industry model is still the business concept; the active concept is grouped sector.
- `config/default.yaml` points to `data/...`, but the CLI default output root is `src`, so actual default outputs land under `src/data/...`.
- A process exiting cleanly is not enough; a meaningful successful run should also create the snapshot directory, write `snapshot.json`, and update the registry/latest pointer when allowed.
