# Program Context: Macro Screener MVP

This document is the **main runtime/context brief** for repository users and AI agents.
It is written to be self-contained: a reader should be able to understand how the program works today without relying on deleted historical design docs.

This file explains:
- what the program is for,
- what is in scope and out of scope,
- what data it gathers and consumes,
- how Stage 1 and Stage 2 are calculated,
- what gets published,
- and what practical caveats matter during use and debugging.

---

## 1. What this repository is

`macro-screener` is a **batch Korean equity screener** built around a two-stage ranking model.

The high-level idea is:
1. collect macro state,
2. convert macro state into an industry ranking (**Stage 1**),
3. combine DART disclosure state with that industry context to rank stocks (**Stage 2**),
4. publish the result as an immutable snapshot.

The program is **not**:
- a portfolio construction engine,
- a trade execution engine,
- a real-time intraday monitoring service,
- a public API platform.

It is a **snapshot-publishing screener**.
Its job is to rank the full universe and publish the result for downstream use.

---

## 2. What is in scope right now

### In scope
- Korean equities only
- KOSPI + KOSDAQ common-stock screening
- batch/scheduled execution
- manual execution
- historical replay / backtest paths
- immutable published snapshots
- Stage 1 macro-based industry scoring
- Stage 2 DART-based stock scoring conditioned on Stage 1
- degraded-mode fallback with explicit warnings/metadata

### Out of scope
- portfolio sizing or execution
- intraday live trading decisions
- news-overlay production rules
- full-text semantic interpretation of disclosures
- broad global macro monitoring beyond Korea + US

### Current macro scope
The active runtime macro scope is:
- **Korea macro/statistical inputs**, and
- **US external macro inputs**

This means the MVP runtime is **Korea + US only**.
`BIS`, `OECD`, and `IMF` are not active runtime providers.

---

## 3. How to use the 3-document context set

The intended self-contained context set is:

1. `doc/program-context.md` — what the system does and how the runtime behaves
2. `doc/repository-orientation.md` — where to look in the repository and in what order
3. `doc/code-context.md` — code/module structure and ownership

These three documents are meant to be enough for another user to give an AI the repository’s practical working context.

Recommended order:
1. read this file first,
2. then `doc/repository-orientation.md`,
3. then `doc/code-context.md`.

---

## 4. High-level runtime model

The runtime is a single batch flow:

```text
run context + config
  -> macro-state resolution
  -> Stage 1 industry scoring
  -> stock-universe loading
  -> DART disclosure loading
  -> Stage 2 stock scoring
  -> snapshot publishing
```

Main execution modes:
- `manual-run`
- `scheduled-run`
- `demo-run`
- `backtest-run`
- `backtest-stub`

The system is **batch-oriented**:
- each run has an explicit cutoff,
- each run produces a full snapshot,
- downstream users consume files/SQLite,
- the runtime is not an always-on API service.

---

## 5. End-to-end runtime flow

The main orchestration function is `run_pipeline_context(...)` in `src/macro_screener/pipeline/runner.py`.

At a practical level, a normal run does the following.

### 5.1 Bootstrap
- load config (`config/default.yaml` + optional override)
- initialize runtime directories
- initialize SQLite store
- reconstruct scheduled-window context when needed

Important runtime locations:
- `config/stage1_sector_rank_tables.v1.json` — provisional Stage 1 rank-table artifact
- `data/reference/industry_master.csv` — derived industry taxonomy authority
- `src/data/snapshots/` — default snapshot output root
- `src/data/snapshots/latest.json` — latest pointer file
- `src/data/macro_screener.sqlite3` — operational / audit store

Important practical detail:
- the CLI defaults the output root to `src`
- so default runtime output is written under `src/data/...`, not repository-root `data/...`

### 5.2 Resolve macro state
The runtime resolves macro state before Stage 1.
It can use:
- explicit CLI channel overrides,
- configured manual channel states,
- persisted last-known channel states,
- live macro provider data.

Current intended behavior:
- `manual-run` defaults to the **live-provider path** unless `--macro-source manual` is passed
- `scheduled-run` uses the same live-provider path
- degraded/fallback state is represented through metadata/warnings, not silently mapped to neutral

### 5.3 Load stock universe and taxonomy
The runtime loads:
- a live/common-stock universe from the sanctioned KIS/KRX master-download workflow,
- then joins it with the authoritative local classification mapping.

Current classification authorities:
- `stock_classification.csv` — authoritative local stock classification input
- `data/reference/industry_master.csv` — derived industry taxonomy authority

### 5.4 Load DART disclosures
The runtime loads DART disclosures after macro resolution and before Stage 2 scoring.

Current DART live behavior:
- multi-page pagination
- structured cursor persistence with `accepted_at`, `input_cutoff`, `rcept_dt`, `rcept_no`
- same-day disclosure visibility at the current run cutoff
- stale-cache degradation when live fetch fails and policy allows it
- cache written to `src/data/cache/dart/latest.json`

### 5.5 Score Stage 1 and Stage 2
- Stage 1 ranks industries
- Stage 2 ranks stocks using DART + Stage 1 context

### 5.6 Publish results
The publisher writes:
- parquet / CSV / JSON artifacts,
- `snapshot.json`,
- latest pointer file,
- SQLite snapshot/watermark state.

A run is not meaningfully successful unless publication also succeeds.

---

## 6. Data sources and what each one is for

### 6.1 Macro/statistical providers
- **ECOS** — Korea macro/statistical series
- **KOSIS** — optional Korea external-demand path when configured
- **FRED** — US macro series in the active runtime path
- **ALFRED** — intended historical/vintage-aware support path; not the main active runtime path yet

### 6.2 Disclosure provider
- **DART** — Korean disclosure source for Stage 2

### 6.3 Market/universe provider
- **KRX** — market/universe source for stock coverage and overlays

### 6.4 Local classification authorities
- `stock_classification.csv` — authoritative local stock classification input
- `data/reference/industry_master.csv` — derived taxonomy authority used by runtime/doc expectations

### 6.5 Non-runtime providers
Not active in the current MVP runtime:
- BIS
- OECD
- IMF

---

## 7. Stage 1: industry scoring

Stage 1 converts macro state into a ranked industry table.

### 7.1 Channel set
The five channels are:
- `G` — Growth / Activity
- `IC` — Inflation / Cost
- `FC` — Financial Conditions
- `ED` — External Demand
- `FX` — Foreign Exchange

### 7.2 Channel-state semantics
Each channel ends in `-1 / 0 / +1`.

These are **state-language semantics**, not simple momentum labels:
- `G`: above-trend / neutral / below-trend activity
- `IC`: elevated / neutral / subdued cost pressure
- `FC`: easy / neutral / tight financial conditions
- `ED`: supportive / neutral / weak external demand
- `FX`: KRW-weak / neutral / KRW-strong currency state

Important rule:
- `0` means **neutral only**
- missing/stale/fallback input must not be silently encoded as neutral

### 7.3 How the neutral band actually works
Inside each channel, the runtime first computes **per-series states**.
Each per-series state is one of:
- `+1`
- `0`
- `-1`

Then the Korea-side and US-side values within the same channel are combined by **simple arithmetic mean**.

Conceptually:

```text
S_c = average(per-series states in channel c)
```

Where `S_c` is the combined score for channel `c`.

The final channel state is determined by comparing `S_c` with the channel’s neutral band `tau_c`.

Conceptually:

```text
state_c = +1  if S_c > tau_c
state_c =  0  if -tau_c <= S_c <= tau_c
state_c = -1  if S_c < -tau_c
```

Current neutral bands:
- `G = 0.25`
- `IC = 0.25`
- `FC = 0.25`
- `ED = 0.25`
- `FX = 0.50`

Meaning in practice:
- if one source is clearly positive and the other is neutral, many channels will still flip positive
- if one source is positive and the other negative, the mean is usually near zero and stays neutral
- `FX` uses a larger band because the runtime intentionally wants stronger confirmation before flipping FX away from neutral

Examples:
- with `tau = 0.25`, Korea `+1`, US `0` -> average `0.5` -> positive
- with `tau = 0.25`, Korea `+1`, US `-1` -> average `0.0` -> neutral
- with `tau = 0.50`, Korea `+1`, US `0` -> average `0.5` -> still neutral for FX

### 7.4 Current Stage 1 scoring posture
The active Stage 1 path is:
- **rank-table-backed scoring**
- using `config/stage1_sector_rank_tables.v1.json`
- plus channel contributions,
- plus overlay adjustment,
- followed by deterministic ranking.

Important practical point:
- the current runtime is not simple exposure × state multiplication
- the rank-table artifact is the main structural prior

### 7.5 What “rank-table-backed” means
The Stage 1 artifact contains, for each channel:
- a positive-regime ordered industry table,
- a negative-regime ordered industry table,
- channel weights,
- neutral-band information.

The runtime then:
1. chooses the positive or negative table based on the channel state,
2. finds the industry’s rank in that table,
3. converts rank into a numeric contribution,
4. multiplies by channel weight,
5. sums across channels,
6. adds overlay adjustment.

Conceptually:

```text
industry_final_score
  = sum(weighted rank-derived channel contributions)
  + overlay_adjustment
```

### 7.6 Stage 1 output contract
The Stage 1 result includes:
- run metadata
- channel-state records with metadata
- ranked industry scores
- config version
- warnings

This Stage 1 result is consumed directly by Stage 2.

---

## 8. Stage 2: stock scoring

Stage 2 converts disclosures plus industry context into ranked stock rows.

Inputs:
- Stage 1 industry result
- loaded stock universe
- DART disclosures visible by cutoff

Core flow:
1. classify disclosure events into block types
2. apply block-specific decay in trading-day space
3. aggregate raw DART score per stock
4. normalize DART score cross-sectionally
5. normalize industry score cross-sectionally
6. combine them into final stock score
7. rank deterministically

Current default scoring combination:

```text
final_stock_score = normalized_dart_score + 0.35 * normalized_industry_score
```

### 8.1 What `0.35` means
`0.35` is the current default **industry contribution weight** in Stage 2.

It means:
- DART-driven stock information is the primary signal,
- Stage 1 industry context still matters,
- but Stage 1 industry context is scaled down relative to DART.

Interpretation:

```text
final_stock_score
  = 1.00 * normalized_dart_score
  + 0.35 * normalized_industry_score
```

So `0.35` is:
- **not** a threshold,
- **not** a neutral band,
- **not** a probability,
- **not** a percentage of selected names.

It is simply the coefficient that controls how strongly Stage 1 industry strength influences final Stage 2 stock ranking.

Practical effect:
- if two stocks have similar DART scores, the stock in the stronger Stage 1 industry gets a boost
- but DART remains dominant because its coefficient is effectively `1.0`

### 8.2 What “normalized” means here
Both DART and industry scores are normalized cross-sectionally before being combined.

That means:
- the runtime compares each stock or industry against the rest of the same snapshot,
- not against a fixed absolute threshold.

So final stock score is a **relative score inside one run**, not a universal absolute score that can be compared directly across snapshots without context.

The financial-score slot exists in the model, but is currently fixed to zero.

---

## 9. Runtime output contract

### 9.1 Default output root
The CLI defaults the output root to `src`.
So the default runtime writes to:
- `src/data/cache/...`
- `src/data/snapshots/...`
- `src/data/macro_screener.sqlite3`

### 9.2 Snapshot output tree
Default locations:
- `src/data/cache/dart/latest.json`
- `src/data/snapshots/<run_id>/...`
- `src/data/snapshots/latest.json`
- `src/data/macro_screener.sqlite3`

### 9.3 Main published artifacts
Operator-facing files:
- `industry_scores.csv`
- `screened_stock_list.csv`
- `screened_stocks_by_score.json`
- `screened_stocks_by_industry.json`
- `snapshot.json`
- `src/data/snapshots/latest.json`

Machine-friendly files:
- `industry_scores.parquet`
- `stock_scores.parquet`

SQLite stores:
- snapshots
- published scheduled windows
- ingestion watermarks
- channel-state snapshots

SQLite is an operational/audit store, not the primary downstream API.

### 9.4 What counts as a successful publication
A run should be treated as successfully published only if all of these are true:
- the run directory exists,
- `snapshot.json` exists,
- expected CSV / JSON / parquet artifacts exist,
- `src/data/snapshots/latest.json` points at the new run,
- SQLite has a snapshot record for the run.

This matters more than process exit code alone.

---

## 10. Operational caveats and pitfalls

Important caveats:
- `manual-run` and `scheduled-run` are two triggers of the same main live-provider pipeline
- default output is under `src/data/...`, not repository-root `data/...`
- DART visibility depends on cutoff-aware cursoring, not simply “today’s filings”
- Stage 2 may publish `incomplete` output if Stage 1 succeeded but Stage 2 degraded/fell back
- docs describe intended behavior, but runtime code defines executable behavior

Two common pitfalls:

1. Deleting repository-root `data/` does **not** clean the default snapshot path if the CLI still publishes under `src/data/`.
2. A run is only meaningfully successful if all of these are true:
   - run directory created,
   - `snapshot.json` exists,
   - `latest.json` updated,
   - SQLite snapshot row written.

---

## 11. What an AI should know before editing this repo

If another user wants to give an AI enough context to work productively, this file should be read together with:
- `doc/repository-orientation.md`
- `doc/code-context.md`

That 3-document set is meant to answer:
- what the program does,
- how the repository is organized,
- where the code lives,
- what the runtime publishes,
- and how to start debugging or extending it.
