# macro-screener

[한국어 버전](README.ko.md)

`macro-screener` is a batch Korean equity screener with a two-stage model:

1. **Stage 1** converts five macro channel states (`G`, `IC`, `FC`, `ED`, `FX`) into grouped-sector scores.
2. **Stage 2** scores the full stock universe from DART disclosures, then adds the matched Stage 1 sector score.
3. The pipeline publishes an immutable snapshot plus a `latest.json` pointer and SQLite registry updates.

If you only want the compact context set for another engineer or agent, start with:
- `doc/program-context.md`
- `doc/repository-orientation.md`
- `doc/code-context.md`

## Current model

### Stage 1
- Config version: `sector-v2`
- Stage 1 input artifact: `config/macro_sector_exposure.v2.json`
- Taxonomy/exposure helpers: `src/macro_screener/data/reference.py`
- Runtime scoring path: **direct channel-state × grouped-sector exposure multiplication**
- Output type: ranked `industry_scores` rows (the field name stays `industry_*` for compatibility, but the business concept is a grouped sector)

The grouped sector universe currently includes sectors such as:
- `반도체`
- `자동차/부품`
- `조선`
- `소프트웨어/인터넷/게임`
- `헬스케어/바이오`
- `유통/소매`
- `필수소비재(음식료)`

### Stage 2
- Full-universe stock scoring; Stage 1 does **not** gate which stocks enter Stage 2
- DART events are classified, decayed, and aggregated into a raw DART score
- Raw DART scores are z-scored across the universe
- The final stock score is:

```text
final_score = normalized_dart_score + stage1_sector_score
```

- `normalized_financial_score` remains present in the model contract, but is currently fixed at `0.0`

## Runtime entrypoints

Main code paths:
- CLI: `src/macro_screener/cli.py`
- Pipeline orchestration: `src/macro_screener/pipeline/runner.py`
- Publication: `src/macro_screener/pipeline/publisher.py`
- Macro loading/classification: `src/macro_screener/data/macro_client.py`
- KRX stock universe + exposure loading: `src/macro_screener/data/krx_client.py`
- DART ingestion/cursor/cache: `src/macro_screener/data/dart_client.py`
- Stage 1 scoring: `src/macro_screener/stage1/ranking.py`
- Stage 2 scoring: `src/macro_screener/stage2/ranking.py`

Supported CLI commands:
- `show-config`
- `demo-run`
- `manual-run`
- `scheduled-run`
- `backtest-run`
- `backtest-stub`

## Default inputs and outputs

Default config lives at `config/default.yaml`.

Important default paths from that config:
- `stock_classification.csv`
- `data/reference/industry_master.csv`
- `config/macro_sector_exposure.v2.json`
- `data/snapshots/latest.json`
- `data/macro_screener.sqlite3`

Important practical detail:
- config paths are relative to the chosen output root
- the CLI default output root is `repo_root/src`
- so a default CLI run writes to `src/data/...`

Published artifact filenames currently include:
- `industry_scores.csv`
- `industry_scores.parquet`
- `screened_stock_list.csv`
- `screened_stocks_by_score.json`
- `screened_stocks_by_industry.json`
- `snapshot.json`
- `stock_scores.parquet`

The `industry_*` filenames are intentionally kept for compatibility even though the active taxonomy is grouped-sector based.

## Run

```bash
PYTHONPATH=src:. python -m macro_screener show-config
PYTHONPATH=src:. python -m macro_screener demo-run
PYTHONPATH=src:. python -m macro_screener manual-run
PYTHONPATH=src:. python -m macro_screener scheduled-run
```

## Verify

```bash
PYTHONPATH=src:. pytest -q
PYTHONPATH=src:. python -m macro_screener demo-run --output-dir /tmp/macro-demo
```
