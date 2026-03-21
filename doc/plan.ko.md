# 구현 계획: 매크로 국면 기반 2단계 스크리닝 시스템 (MVP)

[English version](plan.md)

> 목적: MVP를 위한 구현 순서, 전달 마일스톤, 기술 스택 선택, 테스트 기대사항, 운영 규칙을 정의합니다.

## 1. 이 계획의 입력 문서

이 구현 계획은 다음을 전제로 합니다:
- `doc/strategy.md` 는 상위 아키텍처와 최종 MVP 운영 결정을 정의합니다.
- `doc/prd.md` 는 제품 요구사항을 정의합니다.

## 2. 기술 및 전달 기준선

### 2.1 핵심 스택

| 영역 | MVP 선택 |
|---|---|
| Language | Python 3.11+ |
| Package management | `uv` 또는 `pip + venv` |
| Data processing | `pandas`, `numpy` |
| HTTP/API clients | 동기식 `httpx` |
| Scheduler | `APScheduler` |
| Trading calendar | XKRX-aware calendar helper + 하드코딩 MVP 휴일 리스트 |
| Persistence | SQLite + parquet |
| Config | typed settings + YAML |
| CLI | 단순 command entrypoint |
| Logging | structured JSON logging |
| Testing | unit + integration + backtest suite |

### 2.2 전달 원칙
1. MVP를 얇은 vertical slice 단위로 전달한다.
2. Stage 1과 Stage 2의 계약 경계를 명확히 유지한다.
3. point-in-time correctness와 immutability를 처음부터 1급 요소로 취급한다.
4. 하드코딩보다 외부화된 설정을 우선한다.
5. degraded-mode 동작은 임시 fallback이 아니라 명시적 정책으로 취급한다.

## 3. 목표 저장소 구조

```text
src/macro_screener/
  config/
  models/
  data/
  stage1/
  stage2/
  pipeline/
  backtest/
  db/

tests/
  unit/
  integration/
  backtest/
  fixtures/
```

### 모듈 기대사항
- `config/` — settings, exposure matrix, runtime override
- `models/` — 계약 수준 모델 (`ChannelState`, `IndustryScore`, `DARTEvent`, `StockScore`, `Snapshot`)
- `data/` — KRX, DART, macro-source 경계
- `stage1/` — channel-state, scoring, overlay, ranking
- `stage2/` — classification, decay, normalization, merge, ranking
- `pipeline/` — runner, scheduler, publisher
- `backtest/` — replay, calendar, snapshot store
- `db/` — database setup, table, repository, immutability enforcement

## 4. 전달 단계

## Phase 1 — foundation

### 목표
실행 가능한 프로젝트 골격과 공통 계약을 만듭니다.

### Deliverables
- 프로젝트 패키지 구조
- config 로딩 및 검증
- 핵심 모델/계약
- SQLite setup 및 repository layer
- CLI entrypoint
- logging/test scaffolding

### Acceptance criteria
- 프로젝트가 로컬에서 부팅된다.
- config가 정상적으로 로드된다.
- 핵심 모델이 serialize/deserialize 된다.
- persistence layer에 snapshot immutability 검사가 존재한다.

## Phase 2 — Stage 1

### 목표
매크로 → 업종 점수 계산을 구현합니다.

### Deliverables
- manual/stub channel-state provider
- exposure-matrix loading
- base-score logic
- overlay logic
- industry ranking/tie-break
- `Stage1Result` handoff contract

### Acceptance criteria
- 5개 채널 모두에 대해 channel state가 생성된다.
- 전체 유니버스 업종 랭킹이 생성된다.
- 종가 기반 다음 거래일 적용 규칙이 유지된다.
- Stage 1 출력에 필요한 audit field가 포함된다.

## Phase 3 — Stage 2

### 목표
공시 → 종목 점수 계산을 구현합니다.

### Deliverables
- DART classifier
- DART event persistence shape
- decay logic
- normalization logic
- stock ranking/tie-break
- `ScoringContext` consumption path

### Acceptance criteria
- Stage 2가 `Stage1Result` 를 입력으로 받는다.
- 전체 종목 랭킹이 생성된다.
- neutral/unknown classification ratio가 로그에 기록된다.
- raw 점수와 normalized 점수가 함께 저장된다.

## Phase 4 — orchestration and publication

### 목표
Stage 1 + Stage 2를 신뢰 가능한 scheduled snapshot으로 전환합니다.

### Deliverables
- scheduler
- runner
- snapshot persistence
- parquet publisher
- `data/snapshots/latest.json` latest snapshot pointer
- missed-run recovery flow

### Acceptance criteria
- pre-open 및 post-close run이 동작한다.
- manual run이 동작한다.
- scheduled window dedupe가 `(trading_date, run_type)` 를 사용한다.
- 발행된 snapshot은 immutable 하며 덮어쓰지 않는다.
- duplicate recovery attempt는 publication을 덮어쓰지 않고 skip 처리된다.

## Phase 5 — backtest and hardening

### 목표
동일 로직을 과거에도 재생 가능하게 만들고 운영 안정성을 높입니다.

### Deliverables
- replay engine
- PIT-safe historical materialization
- backtest metrics/export
- alerting metrics
- degraded-mode handling
- operational smoke check

### Acceptance criteria
- backtest가 PIT 규칙을 준수한다.
- recovery/idempotency 동작이 deterministic 하다.
- degraded-mode 정책이 테스트 가능하다.
- replay 출력은 live 출력 namespace와 분리된다.

## 5. 데이터 소스 및 연동 기대사항

### 5.1 KRX client
지원해야 하는 것:
- 보통주 유니버스 수집
- overlay 계산용 OHLCV 수집
- 업종 매핑 수집
- ETF, ETN, REIT, 인프라 펀드 및 기타 비주식 상품을 제외하는 security-type filtering

### 5.2 DART client
지원해야 하는 것:
- 날짜/cutoff 기준 공시 목록 조회
- 분류된 공시에 대한 상세 조회
- incremental watermarking
- unknown type에 대한 neutral fallback 동작

### 5.3 Macro data source
MVP는 **manual/stub mode** 를 사용합니다.

추후 실제 ingestion이 stub/manual mode를 대체할 때 선호되는 소스는 다음과 같습니다.
- `ECOS`
- `KOSIS`
- 필요 시 `DART` 기반 한국 관련 입력
- 글로벌 매크로 입력용 `BIS`

## 6. 테스트 전략

### Unit tests
- channel-state 및 scoring 규칙
- overlay 규칙
- DART classification 및 decay
- normalization 및 ranking
- persistence immutability 규칙

### Integration tests
- Stage 1 pipeline
- Stage 2 pipeline
- 전체 scheduled-run flow
- latest snapshot publishing behavior
- duplicate-window recovery behavior

### Backtest tests
- look-ahead leakage 없음
- 다음 거래일 적용 규칙 보존
- replay reproducibility

### Documentation/contract checks
- `Stage1Result`, `ScoringContext`, snapshot 계약이 strategy + PRD와 일관됨
- 보이는 3개 문서 집합이 업데이트 후에도 내부적으로 일관됨

## 7. MVP 운영 규칙

## 7.1 정식 출력 계약
- 발행된 run은 immutable parquet artifact를 기록한다.
- `data/snapshots/latest.json` 이 정식 latest published snapshot을 가리킨다.
- SQLite는 운영/감사 저장소이며, 주된 consumer interface는 아니다.

## 7.2 Scheduled-window identity
- `scheduled_window_key = (trading_date, run_type)`
- `run_id` 는 개별 실행 시도를 식별한다.
- 여러 draft attempt는 허용된다.
- 하나의 scheduled window에는 최대 하나의 published snapshot만 허용된다.
- 이후 duplicate recovery attempt는 publication을 덮어쓰지 않고 duplicate/skipped로 표시되어야 한다.

## 7.3 Error handling and degraded mode

| Failure point | MVP behavior |
|---|---|
| KRX API down | 3회 backoff retry 후 실패 시 run 중단 및 alert |
| DART API down | 3회 retry 후 실패 시 stale DART data로 실행하고 결과에 flag |
| Macro source unavailable (`ECOS`/`KOSIS`/`DART`/`BIS`) | last known channel states를 사용하고 warning 기록 |
| Stage 1 error | 전체 run 중단 |
| Stage 2 error | Stage 1-only 결과를 발행하고 incomplete run으로 표시 |
| Snapshot write failure | 1회 retry 후 실패 시 critical alert를 기록하고 unpublished 상태 유지 |

## 7.4 최소 alert 매트릭스

| Condition | Severity | Operator action |
|---|---|---|
| neutral/unknown DART ratio `> 20%` | warning | 샘플 공시와 classifier/title-pattern 매핑 점검 |
| recovery 중 missed scheduled run | error | scheduler/job-store 상태 확인 후 누락 윈도우 수동 재실행 |
| snapshot publication failure | critical | DB/parquet write path 확인 후 같은 scheduled window 재실행 |
| repeated API failure after retries | error | 소스 가용성을 확인하고 downstream 사용 지속 여부 판단 |

## 8. 요구사항-구현 추적성

| Requirement group | Primary implementation surface | Primary verification lane |
|---|---|---|
| Stage 1 scoring (`F1.*`) | `stage1/*`, `models/channel.py`, `models/industry.py` | unit + integration |
| Stage 2 scoring (`F2.*`) | `stage2/*`, `models/dart_event.py`, `models/stock.py` | unit + integration + backtest |
| Pipeline/publishing (`F3.*`) | `pipeline/runner.py`, `pipeline/scheduler.py`, `publisher`, `db/*` | integration + smoke |
| Backtest (`F4.*`) | `backtest/*`, replay/materialization helper | backtest tests |
| Ingestion (`F5.*`) | `data/krx_client.py`, `data/dart_client.py`, `data/macro_client.py` | unit + integration |
| Reliability / maintainability / security (`NF*`) | config, db, pipeline, logging, tests 전반 | smoke + targeted unit/integration |

## 9. 남아 있는 deferred item

MVP 기준선 이후에도 의도적으로 보류된 항목:
- 정확한 SQLite physical DDL, secondary index, migration-tool 선택
- 비파일 기반 downstream service/API 계약
- manual/stub MVP mode를 넘어서는 정확한 프로덕션 채널 변수/임계값
- 더 세밀한 SLO/alert tuning

## 10. 완료 기준

다음 조건을 만족하면 MVP 문서/구현 계획은 충분히 완료된 것입니다:
- strategy, PRD, plan이 서로 일관된다.
- 고수준 아키텍처 질문을 다시 열지 않고도 구현을 진행할 수 있다.
- low-level physical decision 또는 post-MVP decision만 남아 있다.
