# Product Requirements Document (PRD): Macro Regime-Based Two-Stage Screening System (MVP)

> Purpose: define the final production-ready MVP requirements, data contracts, scoring semantics, degraded-mode behavior, and success criteria for the batch macro/DART screener.

## 1. Product overview

### 1.1 Product summary
Build a batch-driven Korean-equity screening system that publishes:
- a full **industry ranking** from macro-regime inputs,
- a full **stock ranking** from DART disclosure state plus Stage 1 industry context,
- immutable snapshots for downstream strategy consumption,
- and point-in-time-safe replay outputs for historical research.

### 1.2 Target users
- **Primary:** quantitative analysts and portfolio managers
- **Secondary:** system operators and researchers

### 1.3 Product boundary
This system is a **screener**, not a portfolio optimizer, execution engine, or public API platform.

Downstream systems decide:
- number of names to trade,
- portfolio construction,
- sizing,
- execution,
- downstream serving beyond the file contract.

### 1.4 Document authority
- `doc/strategy.md` defines the product boundary and strategic posture.
- `doc/prd.md` defines the authoritative final product and data-contract requirements.
- `doc/plan.md` defines the authoritative implementation path.
- `doc/open-questions.md` contains only the remaining unresolved kickoff questions.

## 2. Scope and scenarios

### 2.1 In scope
- KOSPI + KOSDAQ **common stocks only**
- pre-open and post-close scheduled runs
- manual runs
- historical replay / backtest
- immutable snapshot publishing
- full-universe industry and stock rankings
- explicit data contracts for market, disclosure, Korea macro, and US external macro providers
- degraded-mode visibility and persisted fallback metadata

### 2.2 Out of scope
- portfolio construction or execution
- public API/service freeze beyond immutable parquet + latest pointer files
- real-time intraday production updates
- production news overlay
- full-text semantic interpretation of DART disclosures
- broad multi-country “global macro” monitoring as an MVP goal
- aggressively optimized macro weights or formulas without PIT-safe validation

### 2.3 Core user outcomes
1. identify favored/disfavored industries under the current macro regime
2. identify disclosure-driven stock opportunities and risks
3. compare immutable snapshots over time
4. reproduce the same screening logic historically without look-ahead leakage
5. detect when a run used degraded inputs or fallbacks

### 2.4 Key scenarios

#### Morning pre-open briefing
1. the system triggers the pre-open run at `08:30 KST`
2. the pipeline ingests eligible overnight DART disclosures, the latest visible Korea/US macro releases, and prior-close market overlays
3. Stage 1 classifies macro channel states and ranks industries
4. Stage 2 scores stocks using DART state plus the Stage 1 industry context
5. analysts review top industries, top stocks, and degraded-mode warnings before market open

#### Post-close review
1. the system triggers the post-close run at `15:45 KST`
2. the pipeline ingests same-day close overlays plus disclosures visible by cutoff
3. updated rankings are published as immutable artifacts
4. analysts compare the post-close output against the pre-open run

#### Historical replay
1. a researcher supplies a date range
2. the engine replays the same pipeline using only data visible by each historical cutoff
3. the researcher reviews ranking stability, summary metrics, and degraded/fallback annotations

## 3. Final external-macro scope and source-priority rules

### 3.1 MVP external-macro scope
For MVP, the external macro block is **United States only**.

The product goal is to rank Korean industries and Korean stocks using the external macro signals that materially affect Korean equities. MVP is therefore:
- **Korea macro block**, and
- **US external macro block**,
- not broad multi-country OECD / IMF / BIS runtime coverage,
- not a world-aggregate macro monitor.

### 3.2 Provider roster for MVP

#### Korea-side providers
- **KRX** — live universe / market overlays / OHLCV context
- **DART** — disclosure ingestion for Stage 2
- **ECOS** — Korea macro/statistical series
- **KOSIS** — Korea macro/statistical series
- **Local classification CSV** — authoritative common-stock and industry taxonomy mapping

#### US-side providers
- **FRED / ALFRED or direct official US sources routed through one adapter layer**

Recommended practical rule:
- use **FRED** for latest/current series retrieval
- use **ALFRED** or persisted release snapshots when vintage-aware PIT behavior is required
- keep source attribution to the underlying official source (BEA, BLS, Federal Reserve, Treasury, Census, etc.) in metadata

#### Non-MVP / future-extension providers
- BIS
- OECD
- IMF

These may remain as:
- future expansion providers,
- secondary validation sources,
- or emergency backfill/reference sources,

but they are **not** mandatory MVP runtime providers.

### 3.3 Source-priority rule
For runtime Stage 1 channel classification:
1. prefer **actual realized official data**
2. prefer series without forecast/projection content
3. if two sources are materially equivalent, choose the source with:
   - no projections,
   - clearer release timing,
   - easier PIT handling,
   - fewer provider dependencies
4. if IMF is used, prefer **IMF topic datasets** with actual observations
5. use **IMF WEO only as reference/backfill**, not as the primary runtime classifier input
6. do **not** allow projected WEO periods to enter Stage 1 channel-state classification

## 4. Frozen domain semantics

### 4.1 Channel set
The system maintains exactly five macro channels:
- `G` — Growth / Activity
- `IC` — Inflation / Cost
- `FC` — Financial Conditions
- `ED` — External Demand
- `FX` — Foreign Exchange

### 4.2 Channel sign convention
The channel-state sign convention is frozen as follows.

| Channel | `+1` | `0` | `-1` |
|---|---|---|---|
| `G` | growth / activity accelerating | neutral | growth / activity decelerating |
| `IC` | inflation / cost pressure rising | neutral | disinflation / cost pressure easing |
| `FC` | financial conditions easing | neutral | financial conditions tightening |
| `ED` | external demand strengthening | neutral | external demand weakening |
| `FX` | KRW weakness / exporter-favorable | neutral | KRW strength / importer-favorable |

### 4.3 Neutral vs missing
- `0` means **neutral only**.
- Missing, stale, failed, or unavailable inputs must **not** be encoded as `0`.
- Missing/stale conditions must be represented through source status, fallback mode, warning flags, and reduced confidence.

### 4.4 Channel-state record requirements
Each channel-state record must include at minimum:
- `channel`
- `state`
- `as_of_timestamp`
- `input_cutoff`
- `source_name`
- `source_version` or source identifier
- `confidence`
- `fallback_mode`
- `warning_flags`

### 4.5 Channel combination rule
The channel combination rule is frozen as **simple combination**.

Implementation contract:
1. each raw series is transformed into a per-series classifier input
2. each per-series input is classified into `{-1, 0, +1}`
3. Korea-side and US-side signals inside the same channel are combined by **simple arithmetic mean**
4. the combined channel score is mapped back to the final channel state using a documented neutral band

For channel `c`:

```text
S_c = (1 / n_c) * Σ s_{c,k}, where each s_{c,k} ∈ {-1, 0, +1}
```

Then:

```text
z_c = +1 if S_c > tau_c
z_c =  0 if -tau_c <= S_c <= tau_c
z_c = -1 if S_c < -tau_c
```

Where:
- `tau_c` is the channel-specific neutral-band threshold
- PIT handling still requires explicit release timestamp, observation period, effective timestamp, next-trading-day application rule when required, and revision handling

## 5. Industry taxonomy and local reference-file rules

### 5.1 `stock_classification.csv`
`stock_classification.csv` is authoritative for:
- `stock_code`
- common-stock inclusion / exclusion
- stock-to-industry assignment
- market / local classification metadata if maintained there

If live KRX data lacks stable production-grade security-type metadata, the runtime must:
1. ingest the live KRX universe
2. join it to the maintained local classification CSV by `stock_code`
3. use the CSV to filter to the common-stock MVP universe and attach industry classification

### 5.2 Derived `industry_master.csv` (or equivalent)
A derived taxonomy file may be generated from `stock_classification.csv` and becomes authoritative for:
- unique `industry_code`
- `industry_name`
- the industry universe used in Stage 1 ranking
- optional sector-ordering metadata

If an industry master file does not yet exist, the implementation plan must include a preprocessing step that:
1. reads `stock_classification.csv`
2. filters to the common-stock MVP universe
3. extracts the unique industry taxonomy
4. writes a maintained derived master file

## 6. External data contracts and fixed series roster

## 6.1 KRX Open API contract

### Authentication / transport
- authentication is request-header based
- the authentication header key is `AUTH_KEY`
- response formats may be JSON or XML

### Minimum required KRX services
- `유가증권 종목기본정보` — KOSPI stock master
- `코스닥 종목기본정보` — KOSDAQ stock master
- `유가증권 일별매매정보` — KOSPI daily trading data
- `코스닥 일별매매정보` — KOSDAQ daily trading data
- `KRX 시리즈 일별시세정보` — broad KRX series index data
- `KOSPI 시리즈 일별시세정보` — KOSPI series index data
- `KOSDAQ 시리즈 일별시세정보` — KOSDAQ series index data

### Required KRX use cases
- common-stock universe master
- daily OHLCV / turnover / liquidity-style overlays
- sector/index relative-strength overlays
- exporter/importer market overlay features
- stock-code keyed joins to the authoritative local classification CSV

### Required normalization rules
KRX records must map into at least:
- `stock_code`
- `market`
- `security_type`
- `listing_status`
- live market overlay fields used by Stage 1 / downstream ranking context

### Required exclusions
The MVP common-stock universe must exclude at minimum:
- ETF
- ETN
- ELW
- REIT / infrastructure-like fund structures
- preferred shares and other non-target share classes

**Authority rule:** the authoritative common-stock filter is the maintained local classification CSV, not dynamic inference from unstable KRX response fields.

## 6.2 DART OpenAPI contract

### Minimum required endpoints
- `corpCode.xml` — corporate-code master sync (`corp_code` ↔ `stock_code`)
- `list.json` — incremental disclosure list retrieval
- `company.json` — issuer/company normalization
- `document.xml` — original filing retrieval for detail parsing
- `majorstock.json` — large-shareholding / ownership-change signal
- `fnlttSinglAcnt.json` — key financial-account extraction when issuer-health enrichment is required
- `fnlttXbrl.xml` — raw XBRL retrieval when structured financial parsing must be reproduced exactly

### Durable cursor and watermark rules
The product must **not** use page number as the durable incremental cursor.
Use a monotone disclosure cursor such as:
- `(rcept_dt, rcept_no)`, or
- an equivalent strictly ordered disclosure cursor.

The stored watermark must include at least:
- last successful cursor
- fetch timestamp
- cutoff timestamp used by the run
- source status / retry metadata

### Detail-resolution and amendment rules
- `list.json` is necessary but not sufficient
- the system must define when `document.xml` or structured detail endpoints are pulled after list ingestion
- corrections, cancellations, withdrawals, and amended filings must be handled without introducing look-ahead leakage

## 6.3 Korea macro source contracts

### ECOS minimum service set
- `StatisticTableList`
- `StatisticItemList`
- `StatisticSearch`
- `KeyStatisticList`
- `StatisticMeta` when metadata lookup is required

For every ECOS series used, persist:
- table code
- item code(s)
- frequency
- unit
- source observation date
- release date if available
- retrieval timestamp
- transformation method

### KOSIS minimum service set
- statistical list lookup
- statistical data retrieval
- table-description lookup
- indicator-list / category-based indicator discovery

For every KOSIS series used, persist:
- table identifier
- item identifier
- frequency
- unit
- source observation date
- release date if available
- retrieval timestamp
- transformation method

## 6.4 US macro adapter contract

The MVP US external macro adapter must support:
- latest/current retrieval through FRED or equivalent official-source routing
- vintage-aware retrieval through ALFRED or persisted release snapshots when required
- source attribution to underlying official publishers in metadata
- exclusion of projected series periods from runtime classification

For every US series used, persist:
- dataset / series identifier
- underlying official source identifier when available
- frequency
- unit
- source observation date
- release date if available
- retrieval timestamp
- transformation method

## 6.5 Fixed Korea / US core series roster by channel

### `G` — Growth / Activity

#### Korea core series
- **Industrial Production Index YoY**
  - purpose: timely realized domestic activity signal
  - preferred source: ECOS or KOSIS

#### US core series
- **US Industrial Production Index YoY**
  - purpose: realized US activity proxy relevant to Korean cyclicals/exporters
  - preferred source: Federal Reserve data via FRED/ALFRED

#### Monitoring-only secondary series
- Korea real GDP growth
- US real GDP growth

### `IC` — Inflation / Cost

#### Korea core series
- **Korea CPI YoY**
  - preferred source: ECOS or KOSIS

#### US core series
- **US CPI YoY**
  - preferred source: BLS data via FRED/ALFRED

#### Optional monitoring-only secondary series
- Korea PPI YoY
- US Core CPI YoY

### `FC` — Financial Conditions

#### Korea core series
- **Korea corporate credit spread**
  - example definition: high-grade corporate bond yield minus Korea government bond yield of matched tenor
  - preferred source: ECOS

#### US core series
- **US corporate credit spread**
  - example definition: BAA corporate yield minus 10Y Treasury yield, or equivalent investment-grade spread series
  - preferred source: Federal Reserve / FRED/ALFRED

#### Sign handling
- narrower spread = easier financial conditions = `FC +`
- wider spread = tighter financial conditions = `FC -`

#### Optional monitoring-only secondary series
- Korea base rate
- effective federal funds rate

### `ED` — External Demand

#### Korea core series
- **Korea exports to the United States YoY**
  - preferred source: KOSIS or an official Korean trade-statistics source integrated through the KOSIS/data pipeline

#### US core series
- **US real goods demand proxy**
  - preferred choice: **US real imports of goods YoY**
  - acceptable fallback: **US real personal consumption expenditures on goods YoY**
  - preferred source: FRED/ALFRED with official-source attribution

### `FX` — Foreign Exchange

#### Korea core series
- **USD/KRW**
  - preferred transformation: level change or moving-average regime rule defined in config
  - preferred source: ECOS or an approved Korea FX source already routed through the macro layer

#### US core series
- **Broad trade-weighted US dollar index**
  - preferred source: Federal Reserve data via FRED/ALFRED

#### Sign handling
- USD/KRW up → KRW weaker → `FX +`
- broad USD strength usually aligns with exporter-favorable KRW-weakness pressure, but every raw FX series must declare its sign transform explicitly in config

#### Optional monitoring-only secondary series
- KRW REER / NEER

## 7. Stage 1 — macro-based industry scoring requirements

| ID | Requirement | Priority |
|---|---|---|
| F1.1 | Maintain 5 macro channels: `G`, `IC`, `FC`, `ED`, `FX`. | MUST |
| F1.2 | Classify each channel into `{-1, 0, +1}` using release-aware, PIT-safe Korea/US data. | MUST |
| F1.3 | Keep manual/stub channel-state override support for local verification and controlled fallback. | MUST |
| F1.4 | Separate neutral from missing/stale/failed source conditions. | MUST |
| F1.5 | Use full ordered sector-rank tables by channel/regime rather than a coarse favored/disfavored list. | MUST |
| F1.6 | Combine Korea-side and US-side signals within a channel using the simple channel-combination rule. | MUST |
| F1.7 | Compute the Stage 1 score as a weighted rank-derived prior score plus a separate overlay term. | MUST |
| F1.8 | Keep overlay adjustments separate from the rank-derived base score. | MUST |
| F1.9 | Rank all industries with deterministic tie-breaks and no cutoff. | MUST |
| F1.10 | Preserve next-trading-day timing rules for close-based inputs. | MUST |
| F1.11 | Persist confidence, fallback usage, and per-channel warning metadata. | MUST |
| F1.12 | Version all rank tables and channel weights in explicit config. | MUST |

### 7.1 Canonical Stage 1 config shape
Minimum config shape:

```yaml
stage1:
  channel_weights:
    G: 1.0
    IC: 1.0
    FC: 1.0
    ED: 1.0
    FX: 1.0

  sector_rank_tables:
    G:
      pos: [SEMI, AUTO, MACH, SHIP, CHEM, ...]
      neg: [UTIL, TELECOM, STAPLES, DEF_HEALTH, ...]
    IC:
      pos: [ENERGY, METALS, ...]
      neg: [AIR, RETAIL, UTIL, ...]
```

`neutral` does not need its own ranking table if its contribution is defined as zero.

### 7.2 Rank-to-score transform
Let:
- `N` = number of sectors
- `r` = 1-based rank
- `lower_mid = floor((N + 1)/2)`
- `upper_mid = ceil((N + 1)/2)`

Then define:

```text
score(r, N) =
  (lower_mid - r) / (lower_mid - 1)           if r < lower_mid
  0                                           if lower_mid <= r <= upper_mid
  -(r - upper_mid) / (N - upper_mid)          if r > upper_mid
```

Interpretation:
- top-ranked sector → near `+1`
- middle sector(s) → `0`
- bottom-ranked sector → near `-1`

If `N` is very small, guard the denominator and fall back to an equivalent clipped mapping.

### 7.3 Final Stage 1 score
For industry `i`:

```text
Score_i = Σ w_c * score(r_{i,c,z_c}, N_c) + O_i
```

Where:
- `w_c` = channel weight
- `z_c` = channel state in `{-1, 0, +1}`
- `r_{i,c,z_c}` = the sector rank for industry `i` in channel `c` under regime `z_c`
- `N_c` = total number of industries ranked under channel `c`
- `O_i` = overlay term

Hard rules:
- `z_c = 0` contributes zero
- `z_c = +1` and `z_c = -1` are **not** assumed to be mirror-image reverse tables
- channel weights default to equal weights unless explicitly changed

### 7.4 Stage 1 output requirements
Each published Stage 1 result must include at minimum:
- `industry_code`
- `industry_name`
- `base_score`
- `overlay_adjustment`
- `final_score`
- `rank`
- per-channel contribution breakdown
- run cutoff and config-version metadata
- confidence / fallback / warning metadata sufficient for audit

### 7.5 Stage 1 ranking detail requirements
- ranking must remain deterministic
- Stage 1 tie-breakers remain, in order:
  1. lower absolute negative penalty
  2. higher positive contribution
  3. industry code ascending

### 7.6 Overlay baseline carried forward
- fast overlay triggers use a **5% baseline threshold** versus the latest workday close price unless an explicitly validated replacement rule is adopted later

## 8. Stage 2 — DART-based stock scoring requirements

| ID | Requirement | Priority |
|---|---|---|
| F2.1 | Classify DART disclosures into the MVP block model: positive blocks = supply contracts / treasury stock / facility investment; negative blocks = dilutive financing / corrections-cancellations / governance risk. | MUST |
| F2.2 | Use disclosure-type codes and title-based pattern matching only. | MUST |
| F2.3 | Extract structured fields and risk flags from disclosures. | MUST |
| F2.4 | Treat DART events as decaying state, not one-off points. | MUST |
| F2.5 | Combine normalized DART score and normalized industry score. | MUST |
| F2.6 | Keep `FinancialScore = 0` in MVP while preserving the slot in the formula. | MUST |
| F2.7 | Store both raw and normalized values. | MUST |
| F2.8 | Rank all stocks with no cutoff. | MUST |
| F2.9 | Log unknown disclosure types as neutral. | MUST |
| F2.10 | Require Stage 2 to consume a defined `Stage1Result` contract. | MUST |
| F2.11 | Track neutral/unknown classification ratio. | SHOULD |

### 8.1 Stage 2 defaults carried forward
- normalization uses cross-sectional z-scores per snapshot
- if standard deviation is zero, normalized component = `0`
- `lambda` is applied after normalization
- the present runtime baseline keeps the industry contribution weight configurable and currently defaults to `0.35`
- DART half-life defaults are:
  - `supply_contract = 20`
  - `treasury_stock = 10`
  - `facility_investment = 60`
  - `dilutive_financing = 60`
  - `correction_cancellation_withdrawal = 10`
  - `governance_risk = 120`

### 8.2 Stage 2 output requirements
Each published Stage 2 result must include at minimum:
- `stock_code`
- `industry_code`
- `final_score`
- `rank`
- `raw_dart_score`
- `raw_industry_score`
- normalized components used in the score
- risk/correction flags
- block-level breakdown sufficient for audit and explanation

### 8.3 Stage 2 ranking detail requirements
- ranking must remain deterministic
- Stage 2 tie-breakers remain, in order:
  1. higher raw DART score
  2. higher raw industry-score contribution
  3. stock code ascending

## 9. Pipeline, publishing, and replay requirements

| ID | Requirement | Priority |
|---|---|---|
| F3.1 | Run automatically at pre-open and post-close on trading days. | MUST |
| F3.2 | Support manual trigger via CLI. | MUST |
| F3.3 | Execute ingestion → Stage 1 → Stage 2 → snapshot → publish in order. | MUST |
| F3.4 | Prevent Stage 2 from running if Stage 1 fails. | MUST |
| F3.5 | Allow Stage 1-only incomplete publication if Stage 2 fails after Stage 1 succeeds. | MUST |
| F3.6 | Publish immutable snapshots with unique `run_id`. | MUST |
| F3.7 | Persist snapshots to SQLite and parquet. | MUST |
| F3.8 | Make the latest snapshot retrievable through the file contract. | MUST |
| F3.9 | Log starts, stage transitions, counts, timing, warnings, failures, and fallback use. | MUST |
| F3.10 | Use `scheduled_window_key = (trading_date, run_type)` for scheduled-window dedupe. | MUST |
| F3.11 | Persist warnings/flags that explain degraded-mode runs. | MUST |
| F4.1 | Replay the pipeline by trading day across a date range. | MUST |
| F4.2 | Enforce point-in-time correctness. | MUST |
| F4.3 | Preserve next-day application rules to avoid look-ahead bias. | MUST |
| F4.4 | Keep DART corrections from leaking backward in time. | MUST |
| F4.5 | Capture release-aware macro metadata so replay uses only historically visible data. | MUST |
| F4.6 | Export daily outputs and summary metrics. | MUST |
| F4.7 | Keep results reproducible from stored inputs and watermarks. | MUST |
| F4.8 | Support configurable holding-period analysis. | SHOULD |
| F4.9 | Support parallel processing of independent replay days. | SHOULD |

### 9.1 Canonical output contract
The canonical downstream MVP contract is:
- immutable parquet artifacts
- latest pointer file at `data/snapshots/latest.json`
- SQLite as operational/audit storage, not the primary external consumption contract

### 9.2 Minimum handoff objects
#### `Stage1Result`
- `run_id`
- `run_type`
- `as_of_timestamp`
- `channel_states`
- `industry_scores`
- `config_version`
- `warnings`

#### `ScoringContext`
- `run_metadata`
- `stage1_result`
- `config`
- `calendar_context`
- `mode`
- `input_cutoff`

#### `Snapshot`
- `run_id`
- `run_type`
- `as_of_timestamp`
- `input_cutoff`
- `published_at`
- `status`
- `industry_scores`
- `stock_scores`
- `warnings`

### 9.3 Calendar baseline
- Korean holiday handling uses the hardcoded MVP holiday list behind the project calendar helper unless a later explicit doc revision changes that source

## 10. Degraded mode and operator visibility

| Condition | Required MVP behavior |
|---|---|
| DART unavailable after retries | run with stale DART data if available; otherwise fail fast; persist warnings and retry metadata |
| Korea or US macro provider unavailable | use last-known channel-state fallback only with reduced confidence and explicit fallback flags |
| Missing macro series with no last-known fallback | fail Stage 1 rather than silently mapping to neutral |
| Stage 2 failure after Stage 1 succeeds | publish Stage 1-only incomplete output with explicit warnings |
| Snapshot publication failure | retry, persist failure details, and avoid partial/corrupt published outputs |

Persisted operator visibility must include:
- source/provider name and version or identifier
- last successful cursor or watermark
- cutoff timestamp used by the run
- fallback mode used, if any
- warning flags for stale data, last-known reuse, retries, incomplete publication, or classification uncertainty
- confidence values for channel states where applicable

### 10.1 Minimal alert matrix
- neutral/unknown DART classification ratio `> 20%` -> warning
- missed scheduled run detected during recovery -> error
- snapshot publication failure -> critical
- repeated external API failure after configured retries -> error

## 11. Non-functional requirements

### 11.1 Performance
| ID | Requirement |
|---|---|
| NF1.1 | Full scheduled run target: `< 5 minutes` |
| NF1.2 | Single backtest day target: `< 30 seconds` |
| NF1.3 | Annual backtest target: `< 2 hours` |

### 11.2 Reliability
| ID | Requirement |
|---|---|
| NF2.1 | No partial/corrupt published snapshots. |
| NF2.2 | Graceful handling of API failures via retry/fallback rules. |
| NF2.3 | Scheduler recovery on missed runs. |
| NF2.4 | Graceful shutdown without data corruption. |
| NF2.5 | Published snapshots remain immutable. |
| NF2.6 | Watermarks and fallback metadata remain durable across reruns. |

### 11.3 Maintainability
| ID | Requirement |
|---|---|
| NF3.1 | Type hints and standard Python conventions. |
| NF3.2 | Configuration externalized, not hardcoded. |
| NF3.3 | Strong unit/integration/backtest coverage on scoring logic. |
| NF3.4 | Structured logging throughout. |
| NF3.5 | DB layer remains abstractable for future PostgreSQL migration. |
| NF3.6 | Rank tables, source mappings, and transform rules are versioned and auditable. |

### 11.4 Security
| ID | Requirement |
|---|---|
| NF4.1 | API keys only from environment/secret sources. |
| NF4.2 | No secrets in committed config or logs. |
| NF4.3 | Provider auth material must not be written to snapshot or warning payloads. |

## 12. MVP acceptance criteria

The final MVP documentation set is acceptable when:
- the product remains a batch-first screener rather than a service platform
- the final external-macro scope is explicitly **Korea + US-only external macro**
- the provider/runtime roster is explicit for KRX, DART, ECOS, KOSIS, local classification CSV, and the US macro adapter layer
- BIS / OECD / IMF are not treated as mandatory MVP runtime adapters
- channel semantics and neutral-vs-missing behavior are frozen
- the simple channel-combination rule and `tau_c`-based state mapping are documented
- Stage 1 uses full ordered sector-rank tables plus the deterministic rank-to-score transform
- local CSV authority and derived industry-master generation rules are explicit
- DART and macro ingestion are PIT-safe and watermark-safe
- degraded-mode behavior and operator visibility are explicit
- immutable parquet + `data/snapshots/latest.json` remain the only frozen downstream contract
- no portfolio optimizer, execution engine, or public service API is introduced
