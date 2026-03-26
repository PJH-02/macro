# macro-screener

A batch Korean equity screener with:
- **Stage 1**: macro channel -> grouped-sector scoring
- **Stage 2**: DART disclosure scoring for the full stock universe, then sector-context adjustment
- **Output**: immutable snapshot artifacts under `src/data/` by default

## Current model

### Stage 1
- Channels: `G`, `IC`, `FC`, `ED`, `FX`
- Runtime currently resolves macro signals into signed channel states/scores
- Sector scores are computed by **direct channel-score × sector-exposure multiplication**
- Taxonomy is the grouped sector model defined in `doc/plan.md`

### Stage 2
- Full-universe stock scoring; no Stage 1 sector gating
- Current stock-score composition:

```text
final_stock_score = stage2_individual_stock_score + stage1_sector_score
```

- Current `stage2_individual_stock_score` is DART-driven
- Current `stage1_sector_score` is the matched grouped-sector score from Stage 1

## Taxonomy

The program collapses current stock-classification labels into grouped sectors such as:
- `반도체`
- `자동차/부품`
- `조선`
- `소프트웨어/인터넷/게임`
- `헬스케어/바이오`
- `유통/소매`
- `필수소비재(음식료)`

See `doc/plan.md` for the authoritative mapping and exhaustive appendix.

## Main paths

- CLI: `src/macro_screener/cli.py`
- Pipeline: `src/macro_screener/pipeline/runner.py`
- Publication: `src/macro_screener/pipeline/publisher.py`
- Taxonomy/exposure: `src/macro_screener/data/reference.py`
- Stock universe/exposure loading: `src/macro_screener/data/krx_client.py`
- Stage 1: `src/macro_screener/stage1/ranking.py`
- Stage 2: `src/macro_screener/stage2/ranking.py`

## Default outputs

Default CLI output root is `src`, so snapshots land under `src/data/...`.

Important artifact names are intentionally kept stable:
- `industry_scores.csv`
- `industry_scores.parquet`
- `screened_stock_list.csv`
- `screened_stocks_by_score.json`
- `screened_stocks_by_industry.json`
- `snapshot.json`
- `stock_scores.parquet`

`industry_*` filenames are retained for compatibility even though the active business concept is now **grouped sector**.

## Run

```bash
python -m macro_screener show-config
python -m macro_screener demo-run
python -m macro_screener manual-run
python -m macro_screener scheduled-run
```

## Verify

```bash
PYTHONPATH=src:. pytest -q
PYTHONPATH=src:. python3 -m macro_screener demo-run --output-dir /tmp/macro-demo
```

## Docs

- `doc/program-context.md`
- `doc/repository-orientation.md`
- `doc/code-context.md`
- `doc/plan.md`
