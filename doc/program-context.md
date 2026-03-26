# Program Context: macro-screener

## What the program does now

`macro-screener` is a batch Korean equity screener.

Pipeline shape:

```text
run context/config
-> macro resolution
-> Stage 1 grouped-sector scoring
-> stock-universe loading + grouped-sector mapping
-> DART disclosure loading
-> Stage 2 full-universe stock scoring
-> snapshot publication
```

## Stage 1

- Inputs: signed macro channel states/scores for `G`, `IC`, `FC`, `ED`, `FX`
- Taxonomy: grouped sectors from `doc/plan.md`
- Method: direct channel-score × sector-exposure multiplication
- Output: ranked grouped-sector table with per-channel contributions

## Stage 2

- Universe: full stock universe
- Inputs:
  - DART disclosures
  - stock -> grouped-sector mapping
  - Stage 1 grouped-sector scores
- Current formula:

```text
final_stock_score = stage2_individual_stock_score + stage1_sector_score
```

- Current `stage2_individual_stock_score` is DART-based
- Current `stage1_sector_score` is the matched grouped-sector score

## Data/taxonomy notes

- `stock_classification.csv` is the local stock classification authority
- grouped-sector collapse rules live in `src/macro_screener/data/reference.py`
- `doc/plan.md` remains the authoritative design target and taxonomy appendix

## Outputs

Default CLI output root is `src`, so runtime outputs are written under `src/data/...`.

Important filenames are intentionally stable:
- `industry_scores.csv`
- `industry_scores.parquet`
- `screened_stock_list.csv`
- `screened_stocks_by_score.json`
- `screened_stocks_by_industry.json`
- `snapshot.json`
- `stock_scores.parquet`

`industry_*` naming is compatibility legacy; the active business concept is grouped sector.

## Current practical caveats

- OECD is still not an active runtime provider
- Some stock-classification labels remain manual-review cases in the grouped-sector mapping table
- FX/ED scale imbalance remains an explicit open model risk from `doc/plan.md`
