# Macro Screener MVP

[한국어 버전](README.ko.md)

A minimal, runnable MVP for a **macro regime-based two-stage Korean equity screener**.

The final human-facing doc set is:
- `doc/strategy.md`
- `doc/prd.md`
- `doc/plan.md`
- `doc/open-questions.md`

## What the program does

This repository implements a **batch screener** for Korean equities.
It is designed to help a new user understand:
- what data the program collects,
- how macro state becomes an industry ranking,
- how disclosures become a stock ranking,
- what is already implemented in code,
- and what is still intentionally provisional.

At a high level, the runtime works like this:

```mermaid
flowchart LR
    A[Config + Calendar + Run Context] --> B[Pipeline Runner]
    B --> C[Macro Sources\nECOS / KOSIS / FRED / ALFRED]
    B --> D[Market / Universe Sources\nKRX + stock_classification.csv]
    B --> E[Disclosure Source\nDART]
    C --> F[Stage 1\nMacro channel states]
    D --> F
    F --> G[Industry ranking]
    G --> H[Stage 2\nStock scoring]
    E --> H
    H --> I[Snapshot Publisher\nParquet + SQLite + latest.json]
```

This is a **full-universe ranking system**, not a portfolio engine:
- it ranks industries,
- then ranks stocks,
- and publishes immutable snapshots,
- without deciding how many names to buy or how to size them.

### Stage 1 — Industry ranking

Stage 1 converts macro inputs into five channel states, then converts those channel states into a ranked industry table.

#### 1) Macro channels

The program uses five macro channels:
- `G` — Growth / Activity
- `IC` — Inflation / Cost
- `FC` — Financial Conditions
- `ED` — External Demand
- `FX` — Foreign Exchange

The sign semantics are **state-language semantics**, not acceleration-language semantics:

| Channel | `+1` | `0` | `-1` |
|---|---|---|---|
| `G` | above-trend activity | neutral | below-trend activity |
| `IC` | elevated cost pressure | neutral | subdued cost pressure |
| `FC` | easy financial conditions | neutral | tight financial conditions |
| `ED` | supportive external demand | neutral | weak external demand |
| `FX` | KRW-weak / exporter-favorable currency state | neutral | KRW-strong / importer-favorable currency state |

`0` means **neutral only**. Missing or stale inputs are tracked through metadata and fallback flags, not silently encoded as neutral.

#### 2) Which data each macro channel uses

The current ratified data design is **Korea + US external macro only**.

| Channel | Korea-side series | US-side series | Main providers | Current transform idea |
|---|---|---|---|---|
| `G` | Korea Industrial Production YoY | US Industrial Production YoY | ECOS / FRED | 3-month moving average YoY |
| `IC` | Korea CPI YoY | US CPI YoY | ECOS / FRED | 3-month moving average vs target band |
| `FC` | Korea corporate credit spread | US corporate credit spread | ECOS / FRED | z-score vs history |
| `ED` | Korea exports to US YoY | US real imports of goods YoY | ECOS / FRED | 3-month moving average YoY |
| `FX` | USD/KRW | Broad trade-weighted US dollar index | ECOS / FRED | 3-month log return |

Important `ED` rule:
- primary US `ED` series = **US real imports of goods YoY**
- fallback = **US real personal consumption expenditures on goods YoY**
- fallback is allowed only in **live degraded mode** with lower confidence and explicit fallback metadata
- fallback is **not** the canonical series for official historical validation/backtest

#### 3) How a macro channel is built

Each channel is built in four conceptual steps:

```mermaid
flowchart TD
    A[Raw Korea series] --> C[Per-series transform]
    B[Raw US series] --> C
    C --> D[Per-series classifier to -1 / 0 / +1]
    D --> E[Simple arithmetic mean within channel]
    E --> F[Apply channel-specific tau_c]
    F --> G[Final channel state]
```

The neutral-band thresholds currently used are:

| Channel | `tau_c` |
|---|---:|
| `G` | `0.25` |
| `IC` | `0.25` |
| `FC` | `0.25` |
| `ED` | `0.25` |
| `FX` | `0.50` |

`FX` is intentionally more conservative because currency moves are noisier and often need broader confirmation.

#### 4) How Stage 1 calculates industry rank and score

The current implementation uses a **provisional Stage 1 artifact**:
- `config/stage1_sector_rank_tables.v1.json`
- plus the derived taxonomy file `data/reference/industry_master.csv`

That artifact defines:
- ordered industry rank tables for each channel and regime,
- channel weights,
- neutral-band defaults,
- and a provisional bootstrap scoring configuration.

The score flow is:

```mermaid
flowchart LR
    A[Channel states] --> B[Select regime-specific rank table]
    B --> C[Convert industry rank to score]
    C --> D[Multiply by channel weight]
    D --> E[Sum across channels]
    E --> F[Add overlay adjustment]
    F --> G[Final industry score]
```

In plain words:
1. for each channel, choose the positive or negative rank table depending on the channel state,
2. convert each industry's rank into a normalized score,
3. multiply by the configured channel weight,
4. sum the weighted channel contributions,
5. then add any overlay adjustment.

Today the implementation supports both:
- the new **rank-table-backed path** used by the runner when the artifact exists,
- and some older/manual fallback paths that still remain in the codebase for safety and compatibility.

### Stage 2 — Stock ranking

Stage 2 converts DART-style disclosure events into stock scores and combines them with Stage 1 industry context.

#### 1) Inputs to Stage 2

Stage 2 uses:
- stock universe and industry mapping from KRX + `stock_classification.csv`
- disclosure events from DART
- industry scores from Stage 1

#### 2) How disclosure scoring works

Each disclosure is classified into a block type, then decayed over trading days.
Examples of block types include:
- supply contract
- treasury stock
- facility investment
- dilutive financing
- correction / cancellation / withdrawal
- governance risk
- neutral / unknown

Unknown disclosure types are not fatal; they become neutral and are counted so operators can monitor the unknown ratio.

#### 3) How Stage 2 calculates stock score

```mermaid
flowchart TD
    A[DART disclosures] --> B[Disclosure classification]
    B --> C[Trading-day decay]
    C --> D[Raw DART score by stock]
    E[Stage 1 industry score] --> F[Normalize by snapshot]
    D --> F
    F --> G[Final stock score = normalized_dart + lambda * normalized_industry]
    G --> H[Rank stocks with tie-breakers]
```

Current scoring logic:
1. gather all visible disclosures for each stock,
2. classify them into block types,
3. apply the configured half-life decay,
4. sum to a raw DART score,
5. normalize raw DART scores cross-sectionally,
6. normalize Stage 1 industry scores cross-sectionally,
7. combine them using the current `lambda` weight.

Current baseline:
- industry contribution weight (`lambda`) = `0.35`
- `FinancialScore = 0` in the MVP formula, but the slot is kept in the model

Stock ranking tie-breakers are still explicit and deterministic.

#### 4) Which providers are used, and for what

| Provider | Current role in the program | Data used today | Runtime status |
|---|---|---|---|
| `KRX` | market/universe source | common-stock universe via sanctioned master download, then local taxonomy join | active runtime provider |
| `DART` | disclosure source | filings / disclosure events for Stage 2 | active runtime provider |
| `ECOS` | Korea macro/statistical source | Korea activity / CPI / credit spread / FX / country-export series | active runtime provider path |
| `KOSIS` | Korea macro/statistical source | optional Korea external-demand live path when a KOSIS series identifier is configured | conditional runtime provider |
| `FRED` | US macro source | current US activity / CPI / credit spread / goods-demand / broad USD series | active runtime provider path |
| `ALFRED` | US historical macro source | intended vintage-aware historical validation path | planned / partial runtime path |
| `BIS` | reference / future source | not used in the current runtime path | not an MVP runtime provider |
| `OECD` | reference / future source | not used in the current runtime path | not an MVP runtime provider |
| `IMF` | reference / backfill source | not used in the current MVP runtime path; only allowed as secondary/reference/backfill under doc rules | not an MVP runtime provider |

So if a new user asks “which data is currently gathered via BIS, OECD, IMF?”, the answer is:
- **none in the active MVP runtime path**
- they remain reference / future-extension / secondary-validation sources only.

## Current implementation status

The codebase is no longer just a skeleton. The current repository state now includes:
- ratified strategy / PRD / implementation-plan docs
- a materialized provisional Stage 1 artifact and derived taxonomy file
- Stage 1 artifact-backed runner integration
- ChannelState metadata expansion
- persisted fallback metadata round-trip
- DART cursor/store hardening
- pipeline and regression coverage for the updated runtime path

What is production-like today:
- batch execution paths exist for `manual`, `scheduled`, `demo`, and `backtest`
- immutable snapshots are published
- SQLite acts as an operational / audit store
- the runtime now uses the provisional Stage 1 artifact in both `manual-run` and `scheduled-run`
- `manual-run` and `scheduled-run` now share the same live-provider pipeline for macro, disclosure, and stock-universe loading
- the live macro path now uses ECOS/FRED directly and can optionally prefer KOSIS for Korea external-demand data when configured
- the live Korean stock universe still uses the sanctioned KIS/KRX master-download workflow joined to the local taxonomy authority
- DART live mode stays explicit, with stale-cache degradation kept visible in warnings/metadata

What is still intentionally provisional:
- the Stage 1 artifact is **provisional**, not a final reviewed research artifact
- KOSIS runtime participation for Korea external-demand data depends on a configured KOSIS series identifier and falls back explicitly when unavailable
- ALFRED/vintage retrieval is not yet the primary implemented historical path
- an explicit manual/fallback macro path still exists for diagnostics or degraded execution, but it is no longer the default behavior of ordinary `manual-run`
- live provider credentials / connectivity are not proven by this README alone

## Data boundaries in the code today

If you want to read the repository from the code downward, the most important modules are:

| Module | Responsibility |
|---|---|
| `src/macro_screener/pipeline/runner.py` | main runtime orchestration: macro states, Stage 1, Stage 2, publishing |
| `src/macro_screener/data/macro_client.py` | live macro source abstraction, optional KOSIS participation, explicit fallback reload |
| `src/macro_screener/data/reference.py` | derived industry master and provisional Stage 1 artifact generation |
| `src/macro_screener/data/krx_client.py` | stock universe loading, KRX market context, stock-to-industry mapping |
| `src/macro_screener/data/dart_client.py` | disclosure ingestion, cursor / watermark logic |
| `src/macro_screener/stage1/ranking.py` | Stage 1 score construction and industry ranking |
| `src/macro_screener/stage1/channel_state.py` | conversion of runtime channel metadata into `ChannelState` records |
| `src/macro_screener/stage2/ranking.py` | Stage 2 stock scoring and ranking |
| `src/macro_screener/db/store.py` | snapshot store, watermarks, channel-state persistence |
| `src/macro_screener/backtest/engine.py` | replay/backtest orchestration |

A more code-oriented function/module flow is:

```mermaid
flowchart TD
    A[CLI / Scheduler] --> B[run_pipeline_context]
    B --> C[_resolve_macro_states]
    B --> D[_load_stage1_rows_and_rank_tables]
    C --> E[_compute_stage1_result_compat]
    D --> E
    E --> F[compute_stage1_result]
    F --> G[Stage 1 industry scores]
    B --> H[_load_disclosures]
    G --> I[compute_stock_scores]
    H --> I
    I --> J[publish_snapshot]
    J --> K[Parquet + CSV + JSON + SQLite + latest.json]
```

## How to run

For real production-style runs, put your provider keys in the repository root `.env`.
The current runtime reads `.env` automatically.

Currently relevant keys are:
- `DART_API_KEY`
- `ECOS_API_KEY`
- `FRED_API_KEY`
- `KOSIS_API_KEY`
- `KRX_API_KEY` if/when you enable the later API-keyed KRX fetch path

Typical commands:

### 1) Manual run

```bash
python3 -m macro_screener.cli manual-run \
  --output-dir ./out \
  --run-id manual-prod-run
```

`manual-run` is now the **manual trigger** of the standard live-provider pipeline. Unless you explicitly switch the macro source to the manual baseline path, it uses the same live data path as `scheduled-run`.

### 2) Scheduled-style run

```bash
python3 -m macro_screener.cli scheduled-run \
  --output-dir ./out \
  --trading-date 2026-03-23 \
  --run-type pre_open
```

`scheduled-run` is the **scheduled trigger** of that same live-provider pipeline. For the same effective input window, `manual-run` and `scheduled-run` are intended to consume the same provider data and publish the same result structure.

### 3) Backtest / replay

```bash
python3 -m macro_screener.cli backtest-run \
  --output-dir ./out \
  --start-date 2026-03-20 \
  --end-date 2026-03-23
```

If you need the explicit zero-baseline/fallback path instead of the ordinary live-provider path, use:

```bash
python3 -m macro_screener.cli manual-run \
  --output-dir ./out \
  --macro-source manual
```

If you want strict live-provider behavior, use a config that sets:

```yaml
environment: "production"
runtime:
  normal_mode: "live"
```

In that mode:
- `manual-run` and `scheduled-run` both stay on the live-provider path by default,
- manual macro defaults are not allowed as the normal source of truth,
- non-live KRX sources are rejected,
- and fake DART success via demo/file fallback is rejected.

## How the program generates its final result

The final operator-facing goal of the program is **the screened stock list**.

The runtime generates results in this order:
1. fetch or resolve macro inputs,
2. classify the 5 macro channels,
3. rank all industries in Stage 1,
4. score all visible stocks in Stage 2 using DART + Stage 1 context,
5. publish a snapshot with both machine-friendly and operator-friendly files.

Conceptually:

```mermaid
flowchart LR
    A[Live macro inputs] --> B[Stage 1 channel states]
    B --> C[Final industry rank]
    C --> D[Industry context for each stock]
    E[DART disclosures] --> F[Stage 2 stock score]
    D --> F
    F --> G[Final screened stock list]
    G --> H[CSV / JSON / Parquet snapshot outputs]
```

### The two most important result views

#### 1) Final industry rank
This is the ranked industry table from Stage 1.

Use:
- `industry_scores.csv`
- `industry_scores.parquet`

#### 2) Final screened stock list
This is the most important end result.
It is the final ranked stock table from Stage 2.

Use:
- `screened_stock_list.csv` ← easiest operator-facing file
- `screened_stocks_by_score.json` ← flat stock-score-sorted view
- `stock_scores.parquet`

If you want to see the stock list grouped by industry, use:
- `screened_stocks_by_industry.json`

That JSON groups stocks under each final industry rank, so you can answer:
- which industries ranked highest,
- which stocks were selected inside each industry,
- and how the final stock list was distributed across industries.

## Publication contract

The canonical downstream MVP publication contract is:
- immutable parquet artifacts
- latest pointer file at `data/snapshots/latest.json`
- SQLite as operational / audit storage, not the primary external consumer contract

A published run writes:
- industry parquet
- stock parquet
- industry CSV
- final screened stock CSV
- screened-stocks-by-score JSON
- screened-stocks-by-industry JSON
- snapshot JSON
- latest pointer JSON
- SQLite records for snapshots / published windows / watermarks / channel-state snapshots

Important status semantics:
- `published` = normal successful snapshot
- `incomplete` = Stage 1 succeeded but Stage 2 failed or had to fall back to Stage-1-only publication conditions
- `duplicate` = scheduled window already published, so the new run is skipped instead of overwriting history

## Notes

- This repository is a **batch screener**, not a portfolio construction or execution system.
- The current runtime path is **Korea + US external macro only**.
- `BIS`, `OECD`, and `IMF` should currently be described as **reference/future/non-MVP runtime providers**.
- The Stage 1 artifact is deliberately provisional and should eventually be replaced by a reviewed versioned artifact.
- New users should treat `doc/strategy.md`, `doc/prd.md`, and `doc/plan.md` as the final authority when README wording and code comments ever appear to diverge.
