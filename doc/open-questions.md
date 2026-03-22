# Open Questions for Final MVP Implementation Kickoff

> Purpose: preserve only the real remaining implementation questions after the final documentation consolidation.

## 1. Questions already resolved in the final doc set

The following are **no longer open** and should not be re-opened unless a later explicit product decision changes them:
- MVP external macro scope = **Korea + US-only external macro**
- KRX security-type ambiguity is operationally resolved by the authoritative local classification CSV
- the MVP provider roster no longer includes mandatory BIS/OECD/IMF runtime adapters
- Stage 1 uses **full ordered sector-rank tables**, not coarse favored/disfavored lists
- channel combination inside each channel uses the **simple arithmetic mean** plus a channel-specific neutral band
- KRX official endpoints remain the primary market/universe source
- DART API keys come from environment/secret sources
- Korea holiday handling stays hardcoded for MVP
- normalization uses cross-sectional z-scores with lambda applied after normalization
- DART half-life defaults and the fast-overlay `5%` baseline are already fixed for the final-stage baseline
- backtest may process independent dates in parallel

## 2. Remaining open questions only

### Q1. What is the exact raw transform for each fixed series?
Examples:
- YoY
- QoQ annualized
- moving-average slope
- spread change
- level relative to threshold

This must be frozen per series for the final implementation config.

### Q2. What is the neutral band `tau_c` for each channel?
Need exact values for mapping the combined simple-average signal back into `{-1, 0, +1}`.

### Q3. Which US `ED` proxy is final?
Choose one:
- US real imports of goods YoY
- US real goods consumption YoY

### Q4. Is ALFRED required for historical backfill before live collection starts?
If yes, document vintage handling explicitly.
If no, document the historical limitation and rely on persisted release snapshots from go-live onward.

### Q5. What is the final industry taxonomy file name, schema, refresh process, and ownership?
The final docs must freeze:
- file path
- required columns
- refresh process
- ownership

## 3. Production-readiness blocker assessment (2026-03-22)

**Decision:** the docs are **not** production-ready for end-to-end implementation. Stop full production execution after Phase 1 grounding and resolve Q1-Q5, plus the remaining executable Stage 1 freeze gaps, first.

| Blocker | Why it blocks entire production | Grounding |
|---|---|---|
| Q1. Per-series raw transforms are still undefined. | Stage 1 cannot classify real Korea/US provider data deterministically, and replay cannot prove the same transform was applied historically. Any implementation would have to invent product logic inside config/runtime. | `doc/prd.md` requires persisted `transformation_method` metadata for Korea, KOSIS, and US series; `doc/plan.md` Phases 2b-4 require config defaults plus release-aware persistence. |
| Q2. `tau_c` is still undefined for every channel. | The final simple-average combination rule cannot map provider inputs back into `{-1, 0, +1}` without exact thresholds, so `ChannelState.state` cannot be derived from live macro data. | `doc/prd.md` defines the `tau_c`-based mapping; `src/macro_screener/data/macro_client.py` currently only returns pre-baked/manual states, which shows the runtime has no final classifier yet. |
| Q3. The final US `ED` proxy is still unresolved. | Phase 3 cannot sign off the fixed US series roster or final validation baseline while the product still permits two different canonical primary-series choices for the external-demand channel. | `doc/prd.md` lists a preferred US real imports choice plus a fallback US real goods consumption choice; `doc/open-questions.md` still asks for one final frozen primary series. |
| Q4. The ALFRED/vintage decision is still unresolved. | Historical replay cannot be signed off as point-in-time safe until the project decides whether pre-go-live backfill depends on ALFRED vintages or only on persisted release snapshots from go-live onward. | `doc/prd.md` and `doc/plan.md` both require vintage-aware or release-aware metadata; the provider fixtures include US `vintage_mode`, but the current runtime has no finalized vintage/backfill path. |
| Q5. The derived industry taxonomy artifact is still unresolved. | Stage 1 rank tables, KRX joins, and operator ownership cannot be productionized without one frozen file path/schema/refresh owner for the authoritative derived taxonomy. | `doc/prd.md` makes `stock_classification.csv` authoritative and allows a derived `industry_master.csv`; `doc/plan.md` depends on that artifact for Stage 1 rank tables and Phase 3 KRX joins. |

### Additional gating gap beyond Q1-Q5

- **Stage 1 rank-table / weight freeze is still incomplete.** The direction is settled — full ordered sector-rank tables plus versioned channel weights — but the concrete executable artifact is still not frozen. `doc/prd.md` requires versioned rank tables and weights (`F1.5`, `F1.12`) yet the config example still contains placeholder ellipses, and `doc/plan.md` still treats default tables/weights as future Phase 2b work.

### Additional grounding from the current implementation

- `src/macro_screener/models/contracts.py` still defines `ChannelState` with only `effective_at`, `source`, and optional `confidence`, which is short of the PRD-required metadata contract.
- `src/macro_screener/stage1/base_score.py` and `src/macro_screener/stage1/ranking.py` still implement symmetric exposure × state scoring instead of the PRD's rank-derived sector-prior model.
- `src/macro_screener/data/macro_client.py` still centers on manual or last-known channel states rather than provider-specific Korea/US series ingestion with release metadata.
- `src/macro_screener/data/dart_client.py` still persists simple cutoff/page-style watermarks instead of the monotone disclosure cursoring and amendment-safe metadata required by the plan.
- `tests/fixtures/provider_contracts/` is useful Phase 1 grounding, but it only proves example provider contracts exist; it does not freeze the unresolved scoring, vintage, taxonomy, or concrete rank-table/weight decisions above.

## 4. Exit condition for this file

This file should shrink to zero open questions, and the Stage 1 rank-table / weight artifact should be frozen, before full production implementation begins.
