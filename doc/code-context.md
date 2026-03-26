# Code Context

## Compact mental model

The current codebase can be read as five layers:

1. **config**
   - `src/macro_screener/config/*`
2. **data loading / taxonomy**
   - `src/macro_screener/data/reference.py`
   - `src/macro_screener/data/krx_client.py`
   - `src/macro_screener/data/macro_client.py`
   - `src/macro_screener/data/dart_client.py`
3. **scoring**
   - `src/macro_screener/stage1/ranking.py`
   - `src/macro_screener/stage2/ranking.py`
4. **pipeline orchestration**
   - `src/macro_screener/pipeline/runner.py`
   - `src/macro_screener/pipeline/publisher.py`
5. **contracts / serialization**
   - `src/macro_screener/models/contracts.py`
   - `src/macro_screener/serialization.py`

## Most important files

### `src/macro_screener/data/reference.py`
Owns:
- grouped-sector taxonomy
- current-label -> grouped-sector mapping
- exhaustive appendix-equivalent mapping data
- default grouped-sector exposure matrix

### `src/macro_screener/data/krx_client.py`
Owns:
- stock-universe loading
- stock-level grouped-sector assignment
- grouped-sector exposure-row loading

### `src/macro_screener/stage1/ranking.py`
Owns:
- direct grouped-sector scoring from macro channel scores
- per-channel contribution breakdown

### `src/macro_screener/stage2/ranking.py`
Owns:
- DART-driven individual-stock scoring
- final stock-score composition with sector context

### `src/macro_screener/pipeline/runner.py`
Owns:
- execution order
- data-source policy wiring
- snapshot assembly

### `src/macro_screener/pipeline/publisher.py`
Owns:
- writing CSV/parquet/JSON outputs
- latest pointer update
- snapshot persistence

## Naming caveat

Several compatibility names remain:
- `industry_code` *(legacy compatibility field)*
- `industry_name` *(legacy compatibility field)*
- `industry_scores.csv` *(legacy compatibility filename)*

These should be read as **grouped-sector-compatible legacy names** unless a file explicitly says otherwise.
