# Plan: Replace Stage 1 with Signed Macro Channel Scoring + Short-Term Overlay, Then Refactor Stage 2 Stock Ranking Around Sector Context

## 1. Objective

Refactor the current `macro-screener` repository from the existing **discrete channel state + rank-table-backed Stage 1** into a new architecture with the following properties:

1. **Stage 1** computes **signed macro channel scores** for `G`, `IC`, `FC`, `ED`, and `FX`.
2. Stage 1 uses a **fixed signed sector exposure matrix** instead of the current positive/negative rank-table artifact.
3. Some indicators are **long-term core indicators**; some indicators are **short-term overlay indicators**.
4. **Crude oil, USD/KRW, DXY, and JPY/KRW are short-term overlay indicators only.**
5. **All indicators that are explicitly modeled as YoY series must use YoY Up/Down signed logic.**
6. **All remaining long-term indicators must use signed MA-cross logic.**
7. **Stage 2** must screen stocks across the full stock universe, using **Stage 2 individual-stock scoring + Stage 1 sector context**.
8. Preserve the current repository’s **batch flow**, **snapshot publishing**, **DART cursor/cutoff behavior**, and **operator-facing artifact contract** as much as possible.

---

## 2. Current Repository Baseline (What Exists Today)

The current repository is a **batch Korean equity screener** with:

- a batch pipeline orchestrated from `src/macro_screener/pipeline/runner.py`
- Stage 1 sector scoring from macro inputs
- Stage 2 stock scoring from DART disclosures plus Stage 1 sector context
- snapshot publication under `src/data/...`
- a current Stage 1 that is **rank-table-backed**, not simple exposure multiplication
- a current Stage 2 that uses:

```text
final_stock_score = normalized_dart_score + 0.35 * normalized_sector_score
```

The current active runtime macro scope is Korea + US only; **OECD is not an active runtime provider today** and must be added explicitly if OECD CLI remains a required production input.

---

## 3. Target Architecture Summary

### 3.1 System Identity

- **Market**: Korea equities only (`KOSPI + KOSDAQ` common stocks)
- **Execution mode**: batch
- **MVP cadence**: 2 runs per day (`pre_open`, `post_close`)
- **Consumer**: downstream trading strategy
- **Not in scope**:
  - portfolio optimization
  - execution / order routing
  - always-on intraday service
  - public API service

### 3.2 New Stage 1 Intent

Stage 1 must no longer:
- resolve each channel to a single `-1/0/+1` state and then choose a regime rank table.

Stage 1 must instead:
1. compute **signed long-term channel score components** from indicator-specific rules,
2. compute **signed short-term overlay channel score components** from designated overlay indicators,
3. combine those into an **effective signed channel score**,
4. multiply that score by a **fixed signed sector exposure matrix**,
5. sum contributions across channels to obtain final sector scores.

### 3.3 New Stage 2 Intent

Stage 2 must:
1. accept Stage 1 sector scores,
2. score stocks across the full stock universe using **Stage 2 individual-stock signals + Stage 1 sector context**,
3. compute `final_stock_score = stage2_individual_stock_score + stage1_sector_score`,
4. publish ranked stock outputs.

---

## 4. Authoritative Stage 1 Math

## 4.1 Long-Term Core Indicator Score

Each long-term core indicator `i` produces a **signed** score:

\[
LT_i \in \{-1, 0, +1\}
\]

Long-term channel score:

\[
LT_c = \sum_{i \in Core(c)} LT_i
\]

## 4.2 Short-Term Overlay Indicator Score

Each short-term overlay indicator `j` produces a **signed** overlay score:

\[
OV_j \in \{-1, 0, +1\}
\]

Overlay channel score:

\[
OV_c = \sum_{j \in Overlay(c)} OV_j
\]

## 4.3 Effective Channel Score

The effective signed channel score is:

\[
ChannelScore_c = LT_c + 0.5 \cdot OV_c
\]

This preserves the original user requirement that short-term effects are scaled down relative to the long-term core, while implementing the explicit rule that crude oil and the listed FX indicators are **overlay-only**.

## 4.4 Sector Score

For sector `s`:

\[
SectorScore_s = \sum_{c \in \{G, IC, FC, ED, FX\}} ChannelScore_c \cdot Exposure_{c,s}
\]

Per-channel sector contribution:

\[
Contribution_{c,s} = ChannelScore_c \cdot Exposure_{c,s}
\]

---

## 5. Authoritative Rule Families

## 5.1 Long-Term Rule Family: `YOY_DIRECTION_SIGN`

Use this only for indicators that are explicitly represented as YoY series.

Definition:

\[
LT_i =
\begin{cases}
+1 & \text{if YoY}(t) > \text{YoY}(t-1) + \epsilon \\
-1 & \text{if YoY}(t) < \text{YoY}(t-1) - \epsilon \\
0 & \text{otherwise}
\end{cases}
\]

Interpretation:
- accelerating YoY -> `+1`
- decelerating YoY -> `-1`
- effectively flat within deadband -> `0`

This is the required interpretation of **“YoY Up/Down”**.

## 5.2 Long-Term Rule Family: `MA_CROSS_SIGN`

Use this for all non-YoY long-term core indicators.

Definition:

\[
LT_i =
\begin{cases}
+1 & \text{if MA}_{short}(x_i) > \text{MA}_{long}(x_i) + \epsilon \\
-1 & \text{if MA}_{short}(x_i) < \text{MA}_{long}(x_i) - \epsilon \\
0 & \text{otherwise}
\end{cases}
\]

Interpretation:
- short MA above long MA -> `+1`
- short MA below long MA -> `-1`
- effectively tied within deadband -> `0`

## 5.3 Short-Term Overlay Rule Family: `ZSCORE_SIGN`

Use this only for designated overlay indicators.

Definition:

\[
OV_j =
\begin{cases}
+1 & z_j > +z_{thr} \\
-1 & z_j < -z_{thr} \\
0 & \text{otherwise}
\end{cases}
\]

Default semantic threshold:

\[
z_{thr} = 1.0
\]

Exact window length and input transform must be configurable and **must not be hardcoded implicitly**.

---

## 6. Indicator-to-Rule Assignment (Authoritative)

This section is authoritative for the current target design.

| Channel | Indicator | Role | Rule Family | Signed Score Source | Orientation / Semantics |
|---|---|---:|---|---|---|
| `G` | OECD CLI | LT core | `MA_CROSS_SIGN` | level / configured transform | rising growth activity = positive |
| `G` | Manufacturing PMI | LT core | `MA_CROSS_SIGN` | level / configured transform | improving activity = positive |
| `G` | Services PMI | LT core | `MA_CROSS_SIGN` | level / configured transform | improving activity = positive |
| `IC` | PPI | LT core | `MA_CROSS_SIGN` unless explicitly replaced with a YoY input series | level / configured transform | stronger inflation/cost pressure = positive |
| `IC` | Industrial metals (e.g. copper) | LT core | `MA_CROSS_SIGN` | price level / configured transform | stronger industrial cost pressure = positive |
| `IC` | Crude oil | ST overlay only | `ZSCORE_SIGN` | configured short-term transform | stronger short-term cost shock = positive |
| `FC` | KR corporate bond spread | LT core | `MA_CROSS_SIGN` on orientation-normalized input | level / configured transform | easier financial conditions = positive |
| `FC` | KR base rate | LT core | `MA_CROSS_SIGN` on orientation-normalized input | level / configured transform | easier financial conditions = positive |
| `FC` | KR yield-curve slope | LT core | `MA_CROSS_SIGN` on orientation-normalized input | level / configured transform | easier financial conditions = positive |
| `ED` | KR total exports YoY | LT core | `YOY_DIRECTION_SIGN` | YoY series | improving external demand = positive |
| `FX` | USD/KRW | ST overlay only | `ZSCORE_SIGN` | configured short-term transform | KRW weakness = positive |
| `FX` | DXY | ST overlay only | `ZSCORE_SIGN` | configured short-term transform | stronger USD / KRW weakness context = positive |
| `FX` | JPY/KRW | ST overlay only | `ZSCORE_SIGN` | configured short-term transform | user-defined FX semantics; must be quote-normalized |

### Important consequences of this assignment

1. `FX` has **overlay indicators only** under the current target design.
2. `ED` currently has **one LT core indicator** (`KR total exports YoY`).
3. `IC` mixes LT core indicators with one ST overlay indicator.
4. `FC` requires **direction normalization** because not every raw indicator is positive when it rises.
5. Any future indicator added to Stage 1 must explicitly declare:
   - channel
   - role (`LT core` or `ST overlay`)
   - rule family
   - input transform
   - orientation semantics
   - release lag
   - carry-forward policy

---

## 7. Orientation Rules (Do Not Leave Implicit)

Each indicator must have an explicit `orientation` field so that signed scoring is computed on a normalized directional meaning.

### 7.1 Positive-when-rising indicators
Examples:
- OECD CLI
- PMI series
- PPI (if the channel semantics are “higher cost pressure = stronger IC”)
- industrial metals
- crude oil overlay
- USD/KRW (if `FX` high score = KRW weakness)
- DXY (if used as KRW-weak / USD-strong context)

### 7.2 Positive-when-falling indicators
Examples:
- KR corporate bond spread, if wider spread = tighter conditions and `FC` positive means easier conditions
- KR base rate, if higher policy rate = tighter conditions and `FC` positive means easier conditions

### 7.3 Indicator needing explicit user confirmation / config
- KR yield-curve slope: define whether steepening is scored as easier / supportive, or whether a different normalization is intended
- JPY/KRW: quote convention must be explicit (`KRW per JPY`, `KRW per 100 JPY`, etc.)

Implementation rule:
- the scoring engine must not assume that “higher raw value always means +1”.
- the engine must first normalize by `orientation`, then apply the rule family.

---

## 8. Sector Exposure Matrix (Authoritative Constant)

The following table is a **rank-table-like signed sector exposure coefficient matrix per channel**. It is **not** the final total sector rank table, because final sector ranking is produced only after per-channel contributions are summed.

```python
SECTOR_EXPOSURE = {
    "G": {
        "반도체": 12,
        "반도체장비": 11,
        "기계": 10,
        "자동차/부품": 9,
        "조선": 8,
        "철강": 7,
        "화학": 6,
        "IT하드웨어/디스플레이/전자부품": 5,
        "건설/건자재": 4,
        "해운/물류": 3,
        "증권": 2,
        "은행": 1,
        "비철/산업금속": 0,
        "항공": 0,
        "내구소비재/의류/화장품": -1,
        "여행/레저": -2,
        "에너지(정유/가스)": -3,
        "방산": -4,
        "소프트웨어/인터넷/게임": -5,
        "보험": -6,
        "유통/소매": -7,
        "헬스케어/바이오": -8,
        "리츠/부동산": -9,
        "필수소비재(음식료)": -10,
        "통신": -11,
        "유틸리티": -12
    },
    "IC": {
        "에너지(정유/가스)": 12,
        "비철/산업금속": 11,
        "철강": 10,
        "조선": 9,
        "방산": 8,
        "해운/물류": 7,
        "은행": 6,
        "건설/건자재": 5,
        "자동차/부품": 4,
        "기계": 3,
        "반도체": 2,
        "IT하드웨어/디스플레이/전자부품": 1,
        "증권": 0,
        "리츠/부동산": 0,
        "헬스케어/바이오": -1,
        "소프트웨어/인터넷/게임": -2,
        "통신": -3,
        "보험": -4,
        "반도체장비": -5,
        "화학": -6,
        "내구소비재/의류/화장품": -7,
        "유통/소매": -8,
        "필수소비재(음식료)": -9,
        "유틸리티": -10,
        "여행/레저": -11,
        "항공": -12
    },
    "FC": {
        "소프트웨어/인터넷/게임": 12,
        "헬스케어/바이오": 11,
        "반도체장비": 10,
        "리츠/부동산": 9,
        "건설/건자재": 8,
        "증권": 7,
        "반도체": 6,
        "IT하드웨어/디스플레이/전자부품": 5,
        "내구소비재/의류/화장품": 4,
        "유통/소매": 3,
        "여행/레저": 2,
        "항공": 1,
        "통신": 0,
        "유틸리티": 0,
        "조선": -1,
        "기계": -2,
        "자동차/부품": -3,
        "방산": -4,
        "해운/물류": -5,
        "화학": -6,
        "필수소비재(음식료)": -7,
        "비철/산업금속": -8,
        "철강": -9,
        "에너지(정유/가스)": -10,
        "보험": -11,
        "은행": -12
    },
    "ED": {
        "반도체": 12,
        "반도체장비": 11,
        "IT하드웨어/디스플레이/전자부품": 10,
        "기계": 9,
        "자동차/부품": 8,
        "조선": 7,
        "방산": 6,
        "화학": 5,
        "철강": 4,
        "해운/물류": 3,
        "비철/산업금속": 2,
        "에너지(정유/가스)": 1,
        "건설/건자재": 0,
        "은행": 0,
        "증권": -1,
        "소프트웨어/인터넷/게임": -2,
        "헬스케어/바이오": -3,
        "항공": -4,
        "보험": -5,
        "내구소비재/의류/화장품": -6,
        "여행/레저": -7,
        "유통/소매": -8,
        "필수소비재(음식료)": -9,
        "통신": -10,
        "유틸리티": -11,
        "리츠/부동산": -12
    },
    "FX": {
        "__meta__": {"high_score_semantics": "KRW_weak"},
        "반도체": 12,
        "조선": 11,
        "자동차/부품": 10,
        "기계": 9,
        "방산": 8,
        "반도체장비": 7,
        "철강": 6,
        "비철/산업금속": 5,
        "해운/물류": 4,
        "IT하드웨어/디스플레이/전자부품": 3,
        "에너지(정유/가스)": 2,
        "은행": 1,
        "헬스케어/바이오": 0,
        "건설/건자재": 0,
        "소프트웨어/인터넷/게임": -1,
        "보험": -2,
        "통신": -3,
        "증권": -4,
        "필수소비재(음식료)": -5,
        "화학": -6,
        "리츠/부동산": -7,
        "내구소비재/의류/화장품": -8,
        "유틸리티": -9,
        "유통/소매": -10,
        "여행/레저": -11,
        "항공": -12
    }
}
```

Implementation rule:
- replace current `config/stage1_sector_rank_tables.v1.json` logic with a new exposure-matrix artifact, for example:
  - `config/macro_sector_exposure.v2.json`

---

## 9. Stage 1 Output Contract (New)

Stage 1 must output the following structured data:

```yaml
stage1_result:
  run_metadata: ...
  channel_scores:
    G:
      lt_score: ...
      overlay_score: ...
      total_score: ...
      indicator_details: ...
      warnings: ...
    IC: ...
    FC: ...
    ED: ...
    FX: ...
  sector_contributions:
    sector_name:
      G: ...
      IC: ...
      FC: ...
      ED: ...
      FX: ...
      total: ...
  sector_ranks: ...
  warnings: [...]
  config_version: ...
```

Required characteristics:
- keep **per-indicator diagnostics**
- keep **warnings / confidence / degraded metadata**
- do **not** silently encode missing data as neutral
- preserve enough detail for downstream debugging and audit

---

## 10. Stage 2 Requirements (Updated)

## 10.1 Full-Universe Stage 2 Scoring

Stage 2 must no longer score the entire stock universe in the same way regardless of Stage 1.

Instead:
1. obtain Stage 1 sector scores,
2. score stocks across the full stock universe,
3. compute a Stage 2 individual-stock score,
4. add Stage 1 sector context to obtain the final stock score.

## 10.2 Stage 2 Inputs

- Stage 1 sector scores
- stock universe joined to authoritative sector mapping
- DART disclosures visible at the run cutoff

## 10.3 Stage 2 Outputs

- stock-level ranked scores
- component-level score breakdowns
- explanation / audit fields
- sector provenance (which sector context contributed to the name)

## 10.4 Important Note

The current repository’s Stage 2 formula:

```text
normalized_dart_score + 0.35 * normalized_sector_score
```

must **not** be treated as the final target architecture. The new design requires:
- a Stage 2 individual-stock score
- a Stage 1 sector score
- `final_stock_score = stage2_individual_stock_score + stage1_sector_score`

---

## 11. Required Repository Changes by Module

## 11.1 `src/macro_screener/data/macro_client.py`

Replace the current fixed `-1/0/+1` channel-state classifier posture with an **indicator-spec-driven scoring engine**.

Required changes:
- remove dependence on a single fixed per-series classifier interpretation
- support per-indicator fields:
  - `channel`
  - `role` (`lt_core` / `st_overlay`)
  - `rule_family`
  - `input_transform`
  - `orientation`
  - `short_window`
  - `long_window`
  - `deadband_epsilon`
  - `z_window`
  - `z_threshold`
  - `release_lag`
  - `carry_forward_limit`
- support orientation normalization before scoring
- keep fallback / confidence / warning metadata

## 11.2 `src/macro_screener/stage1/ranking.py`

Replace rank-table-backed Stage 1 logic with direct exposure multiplication.

Required behavior:
- compute `lt_score` per channel
- compute `overlay_score` per channel
- compute `total_channel_score = lt_score + 0.5 * overlay_score`
- multiply by exposure matrix
- sum per-sector contributions
- output ranked sectors

## 11.3 `src/macro_screener/stage1/overlay.py`

Repurpose or rewrite this module so that it becomes the canonical implementation of the new **short-term overlay engine**.

Required behavior:
- score crude oil and the FX overlay indicators using `ZSCORE_SIGN`
- aggregate overlay by channel
- expose overlay diagnostics separately from LT core

## 11.4 `src/macro_screener/stage1/channel_state.py`

The current `ChannelState` concept is no longer sufficient.

Replace or extend with a richer record, e.g.:

```python
MacroChannelScore(
    channel: str,
    lt_score: float,
    overlay_score: float,
    total_score: float,
    indicator_details: list,
    warnings: list,
    confidence: float | None,
)
```

## 11.5 `src/macro_screener/data/reference.py`

Required changes:
- validate that current repo taxonomy maps into the plan's grouped sector universe exactly
- define / enforce authoritative sector labels
- provide mapping utilities if current taxonomy labels do not match the new sector names one-for-one


### 11.5.1 Authoritative target grouped sector taxonomy

The following grouped sector labels are the authoritative target taxonomy for both Stage 1 sector scoring and Stage 2 per-stock sector matching:

- `반도체`
- `반도체장비`
- `기계`
- `자동차/부품`
- `조선`
- `철강`
- `화학`
- `IT하드웨어/디스플레이/전자부품`
- `건설/건자재`
- `해운/물류`
- `증권`
- `은행`
- `비철/산업금속`
- `항공`
- `내구소비재/의류/화장품`
- `여행/레저`
- `에너지(정유/가스)`
- `방산`
- `소프트웨어/인터넷/게임`
- `보험`
- `유통/소매`
- `헬스케어/바이오`
- `리츠/부동산`
- `필수소비재(음식료)`
- `통신`
- `유틸리티`

Implementation rule:
- every stock must resolve to exactly one target grouped sector before Stage 2 stock scoring is finalized
- Stage 1 and Stage 2 must use the same grouped sector vocabulary
- if the current repo taxonomy is more granular, that granularity must be collapsed into this grouped taxonomy rather than expanding the exposure matrix

### 11.5.2 Mapping source and stock-level assignment rule

Use the current local classification authority as the source of truth for per-stock classification input:
- `stock_classification.csv`
- derived `data/reference/industry_master.csv`

Per-stock assignment rule:
1. read each stock's current classification row
2. derive a grouped target sector from the current taxonomy using the mapping table below plus explicit override rules
3. persist that grouped sector on the stock-level reference dataset
4. require Stage 2 stock scoring to read the persisted grouped sector rather than recomputing it ad hoc inside ranking code

Required output shape for the stock-level mapping layer:
- `stock_code`
- `stock_name`
- current classification fields
- `grouped_sector`
- `mapping_rule_id`
- `mapping_confidence`
- `mapping_review_required` (boolean)

Implementation rule:
- sector assignment must be deterministic and reproducible
- if a stock's grouped sector cannot be resolved deterministically, it must be flagged for review instead of silently defaulting

### 11.5.3 Explicit mapping table from current repo labels to grouped sectors

The plan's grouped sector labels are the answer. The following table makes the mapping explicit using labels that exist in `stock_classification.csv` / `data/reference/industry_master.csv`. This table is normative for the current plan and should be materialized into reference mapping artifacts.

| Current repo label(s) | Target grouped sector |
|---|---|
| `반도체` | `반도체` |
| `반도체장비` *(when introduced as a direct label)* | `반도체장비` |
| `기계·장비`, `일반 목적용 기계`, `특수 목적용 기계`, `산용 기계 및 장비 임대`, `기계장비 및 관련 물품 도매` | `기계` |
| `자동차`, `자동차부품`, `자동차 재제조 부품`, `자동차 차체나 트레일러`, `자동차 부품 및 내장품 판매`, `자동차 판매` | `자동차/부품` |
| `조선` | `조선` |
| `철강`, `철강·소재` | `철강` |
| `비철금속`, `금속`, `금속가공`, `금속 주조`, `구조용 금속제품, 탱크 및 증기발생기` | `비철/산업금속` |
| `화학`, `기타 화학제품`, `비료, 농약 및 살균, 살충제`, `고무제품`, `플라스틱제품`, `화학섬유` | `화학` |
| `정유`, `에너지/화학`, `연료 소매` | `에너지(정유/가스)` |
| `소프트웨어`, `인터넷서비스`, `기타 정보 서비스`, `미디어/콘텐츠` *(software/platform primary)*, `게임` *(when introduced as a direct label)* | `소프트웨어/인터넷/게임` |
| `디스플레이`, `전자부품`, `컴퓨터 및 주변장치`, `통신장비`, `가전/전자제품`, `전기·전자`, `기타 전기장비`, `전구 및 조명장치`, `절연선 및 케이블`, `전동기, 발전기 및 전기 변환 · 공급 · 제어 장치`, `이차전지` | `IT하드웨어/디스플레이/전자부품` |
| `건설`, `건물설비 설치 공사`, `건축기술, 엔지니어링 및 관련 기술 서비스`, `기반조성 및 시설물 축조관련 전문공사`, `실내건축 및 건축마무리 공사`, `전기 및 통신 공사`, `건축자재, 철물 및 난방장치 도매`, `기타 비금속 광물제품`, `시멘트, 석회, 플라스터 및 그 제품`, `유리 및 유리제품` | `건설/건자재` |
| `해운`, `운송`, `운송·창고`, `도로 화물 운송`, `기타 운송관련 서비스`, `운송장비 임대`, `육상 여객 운송` *(non-airline)* | `해운/물류` |
| `항공 여객 운송`, `항공기,우주선 및 부품`, `그외 기타 운송장비` *(air/aerospace primary)* | `항공` |
| `증권`, `신탁 및 집합투자` *(securities/investment-product primary)* | `증권` |
| `은행` | `은행` |
| `보험` | `보험` |
| `전기 통신`, `통신`, `미디어/통신` *(communications-service primary)* | `통신` |
| `전력`, `가스`, `증기, 냉·온수 및 공기조절 공급`, `전기·가스` | `유틸리티` |
| `바이오`, `제약`, `의료기기`, `의료용품 및 기타 의약 관련제품`, `기초 의약물질`, `건강관리`, `의료·정밀기기`, `측정, 시험, 항해, 제어 및 기타 정밀기기; 광학기기 제외` *(healthcare/medical-device primary)* | `헬스케어/바이오` |
| `부동산`, `부동산 임대 및 공급` | `리츠/부동산` |
| `유통`, `무점포 소매`, `기타 상품 전문 소매`, `기타 생활용품 소매`, `기타 전문 도매`, `산용 농·축산물 및 동·식물 도매`, `상품 종합 도매`, `상품 중개`, `생활용품 도매`, `금융 지원 서비스` *(commerce-channel primary only if explicitly kept in retail/distribution universe)* | `유통/소매` |
| `음식료`, `음식료·담배`, `기타 식품`, `곡물가공품, 전분 및 전분제품`, `과실, 채소 가공 및 저장 처리`, `도시락 및 식사용 조리식품`, `도축, 육류 가공 및 저장 처리`, `동·식물성 유지 및 낙농제품`, `동물용 사료 및 조제식품`, `떡, 빵 및 과자류`, `수산물 가공 및 저장 처리`, `음식점` *(if kept in consumer staples bucket)* | `필수소비재(음식료)` |
| `섬유·의류`, `섬유/의류`, `화장품`, `가구`, `가정용 기기`, `가죽, 가방 및 유사제품`, `귀금속 및 장신용품`, `신발 및 신발 부분품`, `운동 및 경기용구`, `악기`, `직물직조 및 직물제품`, `방적 및 가공사`, `편조원단` | `내구소비재/의류/화장품` |
| `여행`, `레저`, `호텔/레저`, `스포츠 서비스`, `오락·문화`, `오디오물 출판 및 원판 녹음`, `창작 및 예술관련 서비스` | `여행/레저` |
| `무기 및 총포탄` | `방산` |
| `금융` *(issuer/business meaning must be reviewed and explicitly reassigned; do not leave as a final grouped label)* | manual review required |
| `기타`, `제조`, `서비스`, `일반서비스`, `기타제조` *(too broad as final grouped labels)* | manual review required |

Interpretation rule:
- mapping is based on effective business meaning, not only string equality
- the table above is the first-pass authoritative mapping set for labels that currently exist in the repo
- when a current label can plausibly map to more than one grouped sector, use the precedence rules below

### 11.5.4 Precedence rules for ambiguous matches

Apply precedence in this order when multiple grouped sectors match:

1. exact explicit override by `stock_code`
2. exact match on current fine-grained label
3. exact match on current middle-grained label
4. exact match on current coarse-grained label
5. keyword/semantic fallback rule
6. manual review queue

Mandatory ambiguity resolutions:
- `정유` / refinery-first names map to `에너지(정유/가스)`, not generic `화학`
- `가스` names map to `유틸리티` only when the business is utility supply/distribution; otherwise they map to `에너지(정유/가스)`
- `항공기, 우주선 및 부품`-type manufacturers map to `항공`
- logistics labels involving shipping/freight/warehouse map to `해운/물류`
- `인터넷서비스` and `게임` map to `소프트웨어/인터넷/게임`
- `전자부품` and `디스플레이` map to `IT하드웨어/디스플레이/전자부품` unless explicitly classified as semiconductor equipment
- `바이오` / `제약` / `의료기기` map to `헬스케어/바이오`
- `음식료` maps to `필수소비재(음식료)`, not generic `유통/소매`

### 11.5.5 Required reference artifacts

Add or derive artifacts such as:
- grouped sector mapping table from current taxonomy label -> target grouped sector
- stock-level grouped sector assignment table
- override table for exceptional names/codes
- unresolved mapping report

Suggested persisted fields for the grouped taxonomy artifact:
- `current_large_label`
- `current_middle_label`
- `current_small_label`
- `target_grouped_sector`
- `rule_id`
- `notes`

### 11.5.6 Failure policy

Do not silently coerce unresolved names.

Required behavior:
- if a current taxonomy label has no grouped-sector mapping, fail the taxonomy validation step
- if a stock maps to multiple grouped sectors after precedence rules, mark it `mapping_review_required=true` and exclude it from published final stock ranking until resolved, or fail the run depending on config
- publish mapping warnings in snapshot metadata
- add regression tests covering all explicit overrides and every grouped sector bucket

### 11.5.7 Exhaustive appendix: every current small taxonomy label

The following appendix covers every unique current `소분류` label found in `stock_classification.csv` at planning time. If the live taxonomy changes, this appendix and the derived mapping artifacts must be updated together.

| Current `소분류` label | Target grouped sector |
|---|---|
| `가구` | `내구소비재/의류/화장품` |
| `가스` | `유틸리티` |
| `가전/전자제품` | `IT하드웨어/디스플레이/전자부품` |
| `가정용 기기` | `내구소비재/의류/화장품` |
| `가죽, 가방 및 유사제품` | `내구소비재/의류/화장품` |
| `개인 및 가정용품 수리` | `manual review required` |
| `개인 및 가정용품 임대` | `manual review required` |
| `건물설비 설치 공사` | `건설/건자재` |
| `건설` | `건설/건자재` |
| `건축기술, 엔지니어링 및 관련 기술 서비스` | `건설/건자재` |
| `건축자재, 철물 및 난방장치 도매` | `건설/건자재` |
| `고무제품` | `화학` |
| `곡물가공품, 전분 및 전분제품` | `필수소비재(음식료)` |
| `골판지, 종이 상자 및 종이용기` | `manual review required` |
| `과실, 채소 가공 및 저장 처리` | `필수소비재(음식료)` |
| `광고/마케팅` | `manual review required` |
| `교육지원 서비스` | `manual review required` |
| `구조용 금속제품, 탱크 및 증기발생기` | `비철/산업금속` |
| `귀금속 및 장신용품` | `내구소비재/의류/화장품` |
| `그외 기타 개인 서비스` | `manual review required` |
| `그외 기타 운송장비` | `항공` |
| `그외 기타 전문, 과학 및 기술 서비스` | `manual review required` |
| `그외 기타 제품` | `manual review required` |
| `금속` | `비철/산업금속` |
| `금속 주조` | `비철/산업금속` |
| `금속가공` | `비철/산업금속` |
| `금융` | `manual review required` |
| `금융 지원 서비스` | `유통/소매` |
| `기계장비 및 관련 물품 도매` | `기계` |
| `기록매체 복제` | `manual review required` |
| `기반조성 및 시설물 축조관련 전문공사` | `건설/건자재` |
| `기초 의약물질` | `헬스케어/바이오` |
| `기타 과학기술 서비스` | `manual review required` |
| `기타 교육기관` | `manual review required` |
| `기타 금융` | `manual review required` |
| `기타 비금속 광물제품` | `건설/건자재` |
| `기타 사지원 서비스` | `manual review required` |
| `기타 상품 전문 소매` | `유통/소매` |
| `기타 생활용품 소매` | `유통/소매` |
| `기타 식품` | `필수소비재(음식료)` |
| `기타 운송관련 서비스` | `해운/물류` |
| `기타 전기장비` | `IT하드웨어/디스플레이/전자부품` |
| `기타 전문 도매` | `유통/소매` |
| `기타 전문 서비스` | `manual review required` |
| `기타 정보 서비스` | `소프트웨어/인터넷/게임` |
| `기타 화학제품` | `화학` |
| `나무제품` | `manual review required` |
| `내화, 비내화 요제품` | `건설/건자재` |
| `도로 화물 운송` | `해운/물류` |
| `도시락 및 식사용 조리식품` | `필수소비재(음식료)` |
| `도축, 육류 가공 및 저장 처리` | `필수소비재(음식료)` |
| `동·식물성 유지 및 낙농제품` | `필수소비재(음식료)` |
| `동물용 사료 및 조제식품` | `필수소비재(음식료)` |
| `디스플레이` | `IT하드웨어/디스플레이/전자부품` |
| `떡, 빵 및 과자류` | `필수소비재(음식료)` |
| `레저` | `여행/레저` |
| `마그네틱 및 광학 매체` | `IT하드웨어/디스플레이/전자부품` |
| `무기 및 총포탄` | `방산` |
| `무점포 소매` | `유통/소매` |
| `미디어/콘텐츠` | `소프트웨어/인터넷/게임` |
| `미디어/통신` | `통신` |
| `바이오` | `헬스케어/바이오` |
| `반도체` | `반도체` |
| `방적 및 가공사` | `내구소비재/의류/화장품` |
| `보험` | `보험` |
| `부동산 임대 및 공급` | `리츠/부동산` |
| `비료, 농약 및 살균, 살충제` | `화학` |
| `비철금속` | `비철/산업금속` |
| `사시설 유지·관리 서비스` | `manual review required` |
| `사진장비 및 광학기기` | `IT하드웨어/디스플레이/전자부품` |
| `산용 기계 및 장비 임대` | `기계` |
| `산용 농·축산물 및 동·식물 도매` | `유통/소매` |
| `상품 종합 도매` | `유통/소매` |
| `상품 중개` | `유통/소매` |
| `생활용품 도매` | `유통/소매` |
| `서적, 잡지 및 기타 인쇄물 출판` | `manual review required` |
| `섬유/의류` | `내구소비재/의류/화장품` |
| `소프트웨어` | `소프트웨어/인터넷/게임` |
| `수산물 가공 및 저장 처리` | `필수소비재(음식료)` |
| `스포츠 서비스` | `여행/레저` |
| `시멘트, 석회, 플라스터 및 그 제품` | `건설/건자재` |
| `시장조사 및 여론조사` | `manual review required` |
| `신발 및 신발 부분품` | `내구소비재/의류/화장품` |
| `신탁 및 집합투자` | `증권` |
| `실내건축 및 건축마무리 공사` | `건설/건자재` |
| `악기` | `내구소비재/의류/화장품` |
| `어로 어` | `manual review required` |
| `에너지/화학` | `에너지(정유/가스)` |
| `여행` | `여행/레저` |
| `연료 소매` | `에너지(정유/가스)` |
| `오디오물 출판 및 원판 녹음` | `여행/레저` |
| `오락·문화` | `여행/레저` |
| `운동 및 경기용구` | `내구소비재/의류/화장품` |
| `운송` | `해운/물류` |
| `운송장비 임대` | `해운/물류` |
| `유리 및 유리제품` | `건설/건자재` |
| `유통` | `유통/소매` |
| `육상 여객 운송` | `해운/물류` |
| `은행` | `은행` |
| `음식료` | `필수소비재(음식료)` |
| `음식점` | `필수소비재(음식료)` |
| `의료기기` | `헬스케어/바이오` |
| `의료용품 및 기타 의약 관련제품` | `헬스케어/바이오` |
| `이차전지` | `IT하드웨어/디스플레이/전자부품` |
| `인쇄 및 인쇄관련 산` | `manual review required` |
| `인터넷서비스` | `소프트웨어/인터넷/게임` |
| `일반 교습 학원` | `manual review required` |
| `일반 목적용 기계` | `기계` |
| `자동차` | `자동차/부품` |
| `자동차 부품 및 내장품 판매` | `자동차/부품` |
| `자동차 재제조 부품` | `자동차/부품` |
| `자동차 차체나 트레일러` | `자동차/부품` |
| `자동차 판매` | `자동차/부품` |
| `자동차부품` | `자동차/부품` |
| `작물 재배` | `manual review required` |
| `전구 및 조명장치` | `IT하드웨어/디스플레이/전자부품` |
| `전기 및 통신 공사` | `건설/건자재` |
| `전기 통신` | `통신` |
| `전기·전자` | `IT하드웨어/디스플레이/전자부품` |
| `전동기, 발전기 및 전기 변환 · 공급 · 제어 장치` | `IT하드웨어/디스플레이/전자부품` |
| `전력` | `유틸리티` |
| `전문디자인` | `manual review required` |
| `전자부품` | `IT하드웨어/디스플레이/전자부품` |
| `절연선 및 케이블` | `IT하드웨어/디스플레이/전자부품` |
| `정유` | `에너지(정유/가스)` |
| `제약` | `헬스케어/바이오` |
| `제재 및 목재 가공` | `manual review required` |
| `조선` | `조선` |
| `종이/포장` | `manual review required` |
| `증권` | `증권` |
| `증기, 냉·온수 및 공기조절 공급` | `유틸리티` |
| `직물직조 및 직물제품` | `내구소비재/의류/화장품` |
| `창작 및 예술관련 서비스` | `여행/레저` |
| `철강` | `철강` |
| `초등 교육기관` | `manual review required` |
| `측정, 시험, 항해, 제어 및 기타 정밀기기; 광학기기 제외` | `헬스케어/바이오` |
| `컴퓨터 및 주변장치` | `IT하드웨어/디스플레이/전자부품` |
| `통신장비` | `IT하드웨어/디스플레이/전자부품` |
| `특수 목적용 기계` | `기계` |
| `편조원단` | `내구소비재/의류/화장품` |
| `폐기물 처리` | `manual review required` |
| `플라스틱제품` | `화학` |
| `항공 여객 운송` | `항공` |
| `항공기,우주선 및 부품` | `항공` |
| `해운` | `해운/물류` |
| `호텔/레저` | `여행/레저` |
| `화장품` | `내구소비재/의류/화장품` |
| `화학` | `화학` |
| `화학섬유` | `화학` |
| `회사 본부 및 경영 컨설팅 서비스` | `manual review required` |

## 11.6 `src/macro_screener/models/contracts.py`

Extend contracts to carry the new Stage 1 and Stage 2 outputs.

Required additions:
- Stage 1 per-indicator and per-channel score detail
- sector contribution map
- Stage 2 component scores:
  - `stage2_individual_stock_score`
  - `stage1_sector_score`
  - `final_stock_score`

## 11.7 `src/macro_screener/stage2/ranking.py`

Required changes:
- do not gate the universe by Stage 1 sector ranking or selection logic
- keep current DART event scoring infrastructure where still valid
- define a Stage 2 individual-stock score path
- replace legacy hardwired Stage 2 combination logic with `final_stock_score = stage2_individual_stock_score + stage1_sector_score`

## 11.8 `src/macro_screener/data/dart_client.py`

Keep existing behavior:
- cutoff-aware visibility
- multi-page pagination
- structured cursor persistence
- stale-cache degraded mode where policy allows

No major redesign is needed here under the current target design.

## 11.9 `src/macro_screener/pipeline/runner.py`

Update orchestration order to:

```text
load config
-> load macro series
-> compute LT core scores
-> compute ST overlay scores
-> compute Stage 1 sector scores
-> load stock universe + taxonomy
-> load DART disclosures
-> compute Stage 2 individual-stock scores
-> compute final stock scores using sector context
-> publish snapshot
```

## 11.10 `src/macro_screener/pipeline/publisher.py`

Preserve current publication contract as much as possible, while expanding schema.

Required additions:
- Stage 1 channel detail in `snapshot.json`
- Stage 1 sector contribution columns in `industry_scores.csv` / parquet
- Stage 2 component score columns in `screened_stock_list.csv` / `stock_scores.parquet`
- sector-context metadata in snapshot outputs

Do not change operator-facing filenames unless versioning makes it unavoidable.

## 11.11 Config Surface

Update:
- `config/default.yaml`
- `src/macro_screener/config/defaults.py`
- `src/macro_screener/config/types.py`
- `src/macro_screener/config/loader.py`

Add new config surfaces for:
- indicator specs
- overlay specs
- exposure matrix path
- sector taxonomy mapping settings
- Stage 2 score composition settings (if a named component split is preserved in config)

---

## 12. New Config Schema (Recommended)

```yaml
macro_indicators:
  - id: OECD_CLI
    channel: G
    role: lt_core
    rule_family: MA_CROSS_SIGN
    input_transform: level
    orientation: positive_when_rising
    short_window: TBD
    long_window: TBD
    deadband_epsilon: TBD
    release_lag: TBD
    carry_forward_limit: TBD

  - id: KR_total_exports_yoy
    channel: ED
    role: lt_core
    rule_family: YOY_DIRECTION_SIGN
    input_transform: yoy
    orientation: positive_when_yoy_accelerates
    deadband_epsilon: TBD
    release_lag: TBD
    carry_forward_limit: TBD

  - id: USDKRW
    channel: FX
    role: st_overlay
    rule_family: ZSCORE_SIGN
    input_transform: TBD
    orientation: positive_when_krw_weakens
    z_window: TBD
    z_threshold: 1.0
    release_lag: 0
    carry_forward_limit: TBD
```

Implementation rule:
- **do not hardcode these inside the scoring logic** if they can live in config.

---

## 13. Tests Required Before Merge

Minimum test set:

1. `YOY_DIRECTION_SIGN` unit tests
   - accelerating YoY -> `+1`
   - decelerating YoY -> `-1`
   - flat within deadband -> `0`

2. `MA_CROSS_SIGN` unit tests
   - short MA above long MA -> `+1`
   - short MA below long MA -> `-1`
   - tied within deadband -> `0`

3. `ZSCORE_SIGN` unit tests
   - z > +1 -> `+1`
   - z < -1 -> `-1`
   - inside band -> `0`

4. orientation-normalization tests
   - positive-when-falling indicators correctly invert sign semantics

5. channel aggregation tests
   - `total = LT + 0.5 * overlay`

6. exposure multiplication tests
   - per-channel sector contributions are correct
   - final sector totals are correct

7. Stage 2 score composition tests
   - final stock score equals `stage2_individual_stock_score + stage1_sector_score`
   - full-universe scoring remains intact across all sectors

8. taxonomy mapping tests
   - current repo labels resolve into the plan's grouped sector taxonomy without drift

9. publisher regression tests
   - current artifact filenames remain valid
   - expanded schema serializes correctly
   - `snapshot.json` contains new channel detail

10. DART regression tests
    - cutoff-aware visibility and cursor semantics remain unchanged

---

## 14. Open Issues / Risks That Must Be Explicit in the Plan

These are not optional. Codex must not invent answers silently.

### 14.1 OECD CLI Provider Gap

Current runtime does **not** have OECD as an active provider.

If OECD CLI is mandatory, one of the following must be planned:
- add an OECD adapter,
- pre-ingest OECD CLI into local files,
- map CLI to an alternative provider/series.

### 14.2 FX Channel Scale Imbalance

Under the current user rule assignment:
- `FX` has **overlay-only** indicators
- therefore `FX` score is scaled only through `0.5 * overlay`
- this makes `FX` structurally lower-scale than channels with several LT core indicators

This may be intentional, but it must be acknowledged.

### 14.3 ED Channel Scale Imbalance

`ED` currently has one LT core indicator (`KR total exports YoY`).
This makes `ED` lower-scale than `G` or `FC` unless later normalized or weighted.

### 14.4 Financial Conditions Direction Ambiguity

`KR yield-curve slope` still needs an explicit sign convention in config.
`KR corporate bond spread` and `KR base rate` need explicit inverse-orientation handling.

### 14.5 FX Quote Convention Risk

`JPY/KRW` must be defined precisely. Quote inversion here will flip the sign of the entire signal.

### 14.6 Overlay Transform Is Not Yet Fully Specified

For overlay indicators, the exact transform used before z-scoring is not yet fixed:
- raw level
- first difference
- percent change
- log return
- short-horizon return

This must remain configurable until explicitly fixed.

### 14.7 Stage 2 Individual-Score Definition Scope

Under the current clarified design, Stage 2 should produce an individual-stock score and then add Stage 1 sector context:

- `final_stock_score = stage2_individual_stock_score + stage1_sector_score`

The immediate intended Stage 2 input path is DART-driven. If additional stock-specific inputs are added later, they must be introduced explicitly rather than inferred silently.

### 14.8 Taxonomy Mapping Risk

The grouped sector names used in `SECTOR_EXPOSURE` are the authoritative target taxonomy for this plan, even if they do not match current stock classification labels exactly.
This must be resolved in `reference.py` and validated in tests before Stage 1 sector scoring and Stage 2 sector-context scoring are trusted.

---

## 15. Implementation Guidance for Codex

When creating the actual code-edit plan:

1. Treat this file as the **authoritative behavioral target**.
2. Do **not** preserve the old Stage 1 rank-table scoring except as deprecated compatibility code if necessary.
3. Reuse the current pipeline, publication, and DART cursor infrastructure where possible.
4. Keep the artifact contract stable unless a schema version bump is required.
5. Do not invent additional Stage 2 feature inputs beyond the clarified design unless they are explicitly specified elsewhere.
6. Keep all scoring assumptions externally configurable whenever they are not explicitly fixed by this plan.

---

## 16. Minimal One-Paragraph Summary

Replace the current Stage 1 discrete-state rank-table model with a signed score model where long-term indicators contribute `-1/0/+1` via either `YOY_DIRECTION_SIGN` or `MA_CROSS_SIGN`, short-term overlay indicators contribute `-1/0/+1` via `ZSCORE_SIGN`, and each channel’s effective score is `LT + 0.5 * Overlay`. Use the provided signed sector exposure matrix instead of the current rank-table artifact. Then refactor Stage 2 so it scores the full stock universe, computes a Stage 2 individual-stock score, and combines it with Stage 1 sector context via `final_stock_score = stage2_individual_stock_score + stage1_sector_score`, while preserving the current batch pipeline, DART cursor logic, and snapshot publication contract.
