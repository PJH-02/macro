# Open Questions for Final MVP Implementation Kickoff

> Purpose: preserve the ratification history for recently resolved decisions and track the single remaining implementation prerequisite after document ratification.

## 1. Current status

There are currently **no remaining unresolved product-policy questions** blocking document ratification.

Authority for resolved policy now lives in:
1. `doc/strategy.md`
2. `doc/prd.md`
3. `doc/plan.md`

This file is now a **historical ledger / residual tracker only**. It is not the authority surface for already-ratified policy.

## 2. Ratified decision ledger (historical only)

The following are ratified and should not be re-opened unless a later explicit product decision changes them:
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
- channel semantics are frozen in **state-language**, not change-language
- the primary US `ED` series is **US real imports of goods YoY**
- fallback from the primary US `ED` series to US real personal consumption expenditures on goods YoY is allowed **only for live degraded mode**, with explicit fallback metadata and lower confidence; official historical validation/backtest must not substitute the fallback as the canonical primary series
- MVP execution may proceed with one **provisional versioned Stage 1 sector-rank-table / channel-weight artifact**, explicitly marked as temporary and replaceable after later team ratification

### R1. Frozen per-series transform table with state-language semantics

Interpretation rule for final channel states:
- `G`: above-trend / neutral / below-trend activity state
- `IC`: elevated / neutral / subdued cost-pressure state
- `FC`: easy / neutral / tight financial-conditions state
- `ED`: supportive / neutral / weak external-demand state
- `FX`: KRW-weak / neutral / KRW-strong currency state

These transforms classify the **current macro state**, not acceleration/deceleration semantics.

| series_id | transform | parameters | state-classifier threshold basis | notes |
|---|---|---|---|---|
| `kr_ipi_yoy_3mma` | 3-month moving average of industrial production YoY | `ma_window=3m` | `+1` if `> +1.0%p`, `0` if `[-1.0,+1.0]`, `-1` if `< -1.0%p` | classifies Korea activity as above-trend / neutral / below-trend while smoothing monthly production noise |
| `us_ipi_yoy_3mma` | 3-month moving average of industrial production YoY | `ma_window=3m` | `+1` if `> +1.0%p`, `0` if `[-1.0,+1.0]`, `-1` if `< -1.0%p` | captures realized US activity state spillover to Korean cyclicals/exporters |
| `kr_cpi_yoy_3mma` | 3-month moving average of CPI YoY | `inflation_target=2.0%` | `+1` if `> 2.75%`, `0` if `[1.25%,2.75%]`, `-1` if `< 1.25%` | uses level-vs-target because elevated vs subdued cost pressure matters more than month-to-month noise |
| `us_cpi_yoy_3mma` | 3-month moving average of CPI YoY | `inflation_target=2.0%` | `+1` if `> 2.75%`, `0` if `[1.25%,2.75%]`, `-1` if `< 1.25%` | reflects imported inflation / Fed-sensitive cost-pressure state |
| `kr_credit_spread_z36` | Korea IG corporate spread z-score vs 36-month history | `lookback=36m`, `smooth=3m` | `+1` if `< -0.5σ`, `0` if `[-0.5σ,+0.5σ]`, `-1` if `> +0.5σ` | narrower spread = easier financial-conditions state |
| `us_credit_spread_z36` | US IG corporate spread z-score vs 36-month history | `lookback=36m`, `smooth=3m` | `+1` if `< -0.5σ`, `0` if `[-0.5σ,+0.5σ]`, `-1` if `> +0.5σ` | captures global risk-appetite / funding-condition state spillover |
| `kr_exports_us_yoy_3mma` | 3-month moving average of Korea exports to US YoY | `ma_window=3m` | `+1` if `> +2.0%p`, `0` if `[-2.0,+2.0]`, `-1` if `< -2.0%p` | dampens shipping volatility while classifying Korea-to-US demand as supportive / neutral / weak |
| `us_real_imports_goods_yoy_3mma` | 3-month moving average of US real imports of goods YoY | `ma_window=3m` | `+1` if `> +1.5%p`, `0` if `[-1.5,+1.5]`, `-1` if `< -1.5%p` | primary realized US goods-demand state proxy for Korea export sensitivity |
| `usdkrw_3m_log_return` | 3-month log return of USD/KRW monthly average | `lookback=3m` | `+1` if `> +2.5%`, `0` if `[-2.5%,+2.5%]`, `-1` if `< -2.5%` | positive = KRW-weak state / exporter-favorable |
| `broad_usd_3m_log_return` | 3-month log return of broad trade-weighted USD index | `lookback=3m` | `+1` if `> +2.0%`, `0` if `[-2.0%,+2.0%]`, `-1` if `< -2.0%` | confirms whether the KRW move sits inside a broader dollar-state regime |

### R2. Frozen primary US `ED` series

- `primary_series: US real imports of goods YoY`
- `fallback_allowed: yes`
- `fallback_scope: live degraded mode only`
- `fallback_rule: use US real personal consumption expenditures on goods YoY only when the primary imports series is unavailable or stale for the classification window; set explicit fallback metadata and lower confidence for that run`
- `official_history_rule: official historical validation/backtest must not substitute the fallback as the canonical primary series`
- **Economic rationale:** imports of goods is the cleaner realized-demand bridge to Korea’s export cycle than domestic US goods consumption.

### R3. Provisional Stage 1 sector-rank-table / channel-weight artifact policy

- `policy: allow one provisional versioned Stage 1 artifact for MVP bootstrap`
- `scope: per-channel industry rank tables plus channel weights`
- `bootstrap_rule: the initial artifact may be heuristic/manual rather than economically optimized`
- `default_weight_rule: equal channel weights remain acceptable unless a later explicit version changes them`
- `labeling_rule: mark the artifact as provisional / non-authoritative in config-version notes`
- `revision_rule: later team-reviewed changes must be version-bumped and documented, not silently overwritten`

### R4. Final `tau_c` table

| channel | tau_c | rationale | validation note |
|---|---:|---|---|
| `G` | `0.25` | one-sided Korea or US activity already being clearly above-trend / below-trend is economically meaningful for Korean sector rotation | `(+1,0)` should classify as an above-trend growth state; `(+1,-1)` remains neutral |
| `IC` | `0.25` | one-sided elevated or subdued inflation pressure can still move rates / margin expectations quickly | allows a single clear cost-pressure state to register without requiring both geographies |
| `FC` | `0.25` | either Korea or US spread easy/tight state spills into Korean risk appetite | preserves sensitivity to US-led credit-condition shocks |
| `ED` | `0.25` | either export realization or US goods demand can establish the external-demand state | keeps the channel responsive to partial but still meaningful confirmation |
| `FX` | `0.50` | FX is noisier; require stronger joint confirmation before assigning a KRW-weak / KRW-strong final state | `(+1,0)` stays neutral; only broad confirmation should flip the final FX state |

### R5. Pre-go-live historical backfill policy

- `alfred_required_pre_go_live: yes`
- `policy_scope: all revisable US macro release series used for official historical validation`
- `exception_rule: non-revisable market-price-like series may use as-of historical market data without ALFRED`
- `if_vintage_unavailable: the series is not PIT-valid for official pre-go-live backtests and must be excluded or explicitly flagged as non-authoritative`
- **Economic rationale:** this keeps the historical macro regime record aligned with information that would actually have been visible at the time.

### R6. Derived industry taxonomy artifact contract

- `file_path: data/reference/industry_master.csv`
- `required_columns: industry_code, industry_name, sector_l1, sector_l2, sector_l3, stock_count, representative_stock_code, source_classification_version, generated_at`
- `refresh_process: regenerate whenever stock_classification.csv changes; commit the regenerated file together with the classification change; also run a monthly consistency refresh before any Stage 1 rank-table revision`
- `owner: stock_classification.csv maintainer (research/data owner)`
- `industry_code_rule: stable slug derived from sector_l1 > sector_l2 > sector_l3, never row-order-based`

## 3. Remaining implementation prerequisite

The only remaining narrow implementation prerequisite is:
- one **provisional versioned Stage 1 sector-rank-table / channel-weight artifact** must be checked into executable config before full production implementation begins

This is an implementation prerequisite, not a remaining product-policy question.

## 4. Exit condition for this file

Keep this file as a historical ledger / residual tracker after ratification. It may shrink further once the provisional Stage 1 artifact is explicitly identified in executable config and referenced from the authoritative docs.
