# 제품 요구사항 문서(PRD): 매크로 국면 기반 2단계 스크리닝 시스템 (MVP)

[English version](prd.md)

> 목적: MVP의 제품 수준 요구사항, 범위, 출력물, 성공 기준을 정의합니다.

## 1. 제품 개요

### 1.1 제품 요약

다음을 발행하는 배치 기반 한국 주식 스크리닝 시스템을 구축합니다:
- 매크로 국면 입력으로부터 계산한 전체 **업종 랭킹**
- DART 공시 상태 + Stage 1 업종 맥락으로부터 계산한 전체 **종목 랭킹**
- downstream 전략 소비를 위한 하루 2회 불변 스냅샷

### 1.2 대상 사용자
- **Primary:** 퀀트 애널리스트, 포트폴리오 매니저
- **Secondary:** 시스템 운영자, 리서처

### 1.3 제품 경계
이 시스템은 **스크리너**이며, 포트폴리오 최적화기나 실행 엔진이 아닙니다.

downstream 시스템이 결정하는 것:
- 실제 매매할 종목 수
- 포트폴리오 구성
- 포지션 크기(sizing)
- 진입/청산 실행

## 2. 사용자 결과와 시나리오

### 2.1 핵심 사용자 결과
1. 현재 매크로 국면에서 우호적/비우호적인 업종을 식별한다.
2. 공시 기반 종목 기회와 위험을 식별한다.
3. 시점별 스냅샷을 비교한다.
4. 동일한 스크리닝 로직을 과거에 백테스트한다.

### 2.2 핵심 시나리오

#### 아침 장전 브리핑
1. 시스템이 `08:30 KST` 에 pre-open run을 실행한다.
2. 파이프라인이 유효한 전일 야간 DART 공시, 최신 매크로 입력, 전일 종가 시장 데이터를 수집한다.
3. Stage 1이 업종 랭킹을 생성한다.
4. Stage 2가 종목 랭킹을 생성한다.
5. 애널리스트가 장 시작 전 상위 업종, 상위 종목, flagged 종목을 검토한다.

#### 장 마감 후 리뷰
1. 시스템이 `15:45 KST` 에 post-close run을 실행한다.
2. 파이프라인이 당일 종가 데이터와 cutoff 시점까지 보이는 장중 공시를 수집한다.
3. 업데이트된 랭킹이 발행된다.
4. 애널리스트가 pre-open 대비 post-close 변화를 비교한다.

#### 과거 리플레이
1. 리서처가 날짜 범위를 입력한다.
2. 엔진이 point-in-time 입력으로 동일 파이프라인을 재생한다.
3. 리서처가 랭킹 안정성과 요약 지표를 검토한다.

## 3. 범위

### 3.1 포함 범위
- KOSPI + KOSDAQ **보통주만**
- pre-open 및 post-close scheduled run
- manual run
- historical replay / backtest
- immutable snapshot publishing
- 전체 유니버스 업종 및 종목 랭킹

### 3.2 제외 범위
- 실시간 운영 뉴스 오버레이
- 포트폴리오 구성 또는 주문 실행
- DART 공시 전문 의미 해석
- MVP에서의 유동성 / 시가총액 / 특수상태 필터
- 완전히 구체화된 프로덕션 매크로 채널 공식

## 4. 기능 요구사항

## 4.1 Stage 1 — 매크로 기반 업종 점수 계산

| ID | Requirement | Priority |
|---|---|---|
| F1.1 | 5개 매크로 채널 `G`, `IC`, `FC`, `ED`, `FX` 를 유지한다. | MUST |
| F1.2 | 채널 상태는 `{-1, 0, +1}` 이다. | MUST |
| F1.3 | MVP와 테스트를 위해 manual/stub channel-state override를 지원한다. | MUST |
| F1.4 | 외부 업종 노출도 행렬을 로드한다. | MUST |
| F1.5 | exposure × state 로 기본 업종 점수를 계산한다. | MUST |
| F1.6 | 원래 채널 상태를 수정하지 않고 fast-overlay adjustment를 계산한다. | MUST |
| F1.7 | 컷오프 없이 모든 업종을 랭킹한다. | MUST |
| F1.8 | 동점 시 deterministic tie-break를 보존한다. | MUST |
| F1.9 | 종가 기반 입력에 대한 다음 거래일 적용 규칙을 보존한다. | MUST |
| F1.10 | 가능하면 내부 confidence 값을 기록한다. | SHOULD |

### 4.1a Stage 1 출력 요구사항
발행되는 각 Stage 1 결과는 최소한 다음을 포함해야 합니다:
- `industry_code`
- `industry_name`
- `base_score`
- `overlay_adjustment`
- `final_score`
- `rank`
- run cutoff 및 config 기준을 추적할 수 있는 충분한 메타데이터

## 4.2 Stage 2 — DART 기반 종목 점수 계산

| ID | Requirement | Priority |
|---|---|---|
| F2.1 | DART 공시를 MVP block model로 분류한다: positive block = supply contracts / treasury stock / facility investment, negative block = dilutive financing / corrections-cancellations / governance risk. | MUST |
| F2.2 | 공시 코드와 제목 기반 패턴 매칭만 사용한다. | MUST |
| F2.3 | 공시에서 구조화 필드와 risk flag를 추출한다. | MUST |
| F2.4 | DART 이벤트를 one-off point가 아니라 decay를 갖는 state로 취급한다. | MUST |
| F2.5 | 정규화된 DART 점수와 정규화된 업종 점수를 결합한다. | MUST |
| F2.6 | MVP에서 `FinancialScore = 0` 을 유지하되, 수식 슬롯은 보존한다. | MUST |
| F2.7 | raw 값과 normalized 값을 모두 저장한다. | MUST |
| F2.8 | 컷오프 없이 모든 종목을 랭킹한다. | MUST |
| F2.9 | 알 수 없는 공시 유형은 neutral로 기록한다. | MUST |
| F2.10 | Stage 2는 정의된 `Stage1Result` 계약을 입력으로 받아야 한다. | MUST |
| F2.11 | neutral/unknown classification ratio를 추적한다. | SHOULD |

### 4.2a Stage 2 출력 요구사항
발행되는 각 Stage 2 결과는 최소한 다음을 포함해야 합니다:
- `stock_code`
- `industry_code`
- `final_score`
- `rank`
- `raw_dart_score`
- `raw_industry_score`
- 점수 계산에 사용된 normalized component
- risk/correction flag
- 감사와 설명에 충분한 block-level breakdown

### 4.2b 랭킹 세부 요구사항
- 랭킹은 deterministic 해야 한다.
- 문서화된 tie-break 동작을 보존해야 한다.
- 필요한 입력이 있는 모든 종목은 발행되는 전체 결과에 포함되어야 한다.

## 4.3 파이프라인과 발행

| ID | Requirement | Priority |
|---|---|---|
| F3.1 | 거래일의 pre-open 및 post-close 에 자동 실행한다. | MUST |
| F3.2 | CLI를 통한 manual trigger를 지원한다. | MUST |
| F3.3 | ingestion → Stage 1 → Stage 2 → snapshot → publish 순서로 실행한다. | MUST |
| F3.4 | Stage 1 실패 시 Stage 2 실행을 막는다. | MUST |
| F3.5 | Stage 1 성공 후 Stage 2 실패 시 Stage 1-only incomplete publication을 허용한다. | MUST |
| F3.6 | 고유한 `run_id` 를 갖는 immutable snapshot을 발행한다. | MUST |
| F3.7 | snapshot을 SQLite와 parquet에 영속화한다. | MUST |
| F3.8 | 최신 snapshot을 downstream consumer가 조회할 수 있어야 한다. | MUST |
| F3.9 | 시작, 단계 전환, 건수, 시간, warning, failure를 로그로 남긴다. | MUST |
| F3.10 | scheduled-window dedupe를 위해 `scheduled_window_key = (trading_date, run_type)` 를 사용한다. | MUST |

### 4.3a 정식 출력 계약
정식 downstream MVP 계약은 다음과 같습니다:
- immutable parquet artifact
- `data/snapshots/latest.json` 의 latest pointer 파일
- SQLite는 운영/감사 저장소이며, 주된 외부 소비 계약은 아님

## 4.4 백테스트

| ID | Requirement | Priority |
|---|---|---|
| F4.1 | 날짜 범위에 걸쳐 거래일 단위로 파이프라인을 replay 한다. | MUST |
| F4.2 | point-in-time correctness를 강제한다. | MUST |
| F4.3 | look-ahead bias를 피하기 위해 다음 거래일 적용 규칙을 보존한다. | MUST |
| F4.4 | DART correction이 과거 시점으로 역누수되지 않게 유지한다. | MUST |
| F4.5 | configurable holding-period analysis를 지원한다. | SHOULD |
| F4.6 | 일별 출력과 요약 지표를 export 한다. | MUST |
| F4.7 | 저장된 입력으로부터 결과 재현성을 유지한다. | MUST |
| F4.8 | 독립적인 replay day의 병렬 처리를 지원한다. | SHOULD |

## 4.5 수집(Ingestion)

| ID | Requirement | Priority |
|---|---|---|
| F5.1 | 업종 분류와 함께 KOSPI/KOSDAQ 종목 목록을 가져온다. | MUST |
| F5.2 | overlay 계산을 위한 OHLCV를 가져온다. | MUST |
| F5.3 | DART 공시를 incremental 하게 가져온다. | MUST |
| F5.4 | pluggable macro data source interface를 지원한다. | MUST |
| F5.5 | MVP에서는 stub/manual macro source를 사용한다. | MUST |
| F5.6 | 외부 API의 retry 및 rate-limit 동작을 준수한다. | MUST |
| F5.7 | ETF, ETN, REIT 및 비주식 상품을 유니버스에서 제외한다. | MUST |
| F5.8 | incremental processing을 위한 ingestion watermark를 보존한다. | MUST |

## 5. 비기능 요구사항

### 5.1 성능
| ID | Requirement |
|---|---|
| NF1.1 | 전체 scheduled run 목표: `< 5 minutes` |
| NF1.2 | 단일 backtest day 목표: `< 30 seconds` |
| NF1.3 | 연간 backtest 목표: `< 2 hours` |

### 5.2 신뢰성
| ID | Requirement |
|---|---|
| NF2.1 | 부분적이거나 손상된 snapshot이 발행되면 안 된다. |
| NF2.2 | API 실패는 retry/fallback 규칙으로 우아하게 처리한다. |
| NF2.3 | missed run에 대한 scheduler recovery를 지원한다. |
| NF2.4 | 데이터 손상 없이 graceful shutdown 해야 한다. |
| NF2.5 | 발행된 snapshot은 immutable 해야 한다. |

### 5.3 유지보수성
| ID | Requirement |
|---|---|
| NF3.1 | Type hint와 표준 Python 관례를 따른다. |
| NF3.2 | 설정은 하드코딩이 아니라 외부화한다. |
| NF3.3 | 점수 계산 로직에 대해 강한 unit/integration/backtest 테스트 커버리지를 가진다. |
| NF3.4 | 전 구간에 structured logging을 사용한다. |
| NF3.5 | DB 계층은 향후 PostgreSQL 마이그레이션 가능성을 유지해야 한다. |

### 5.4 보안
| ID | Requirement |
|---|---|
| NF4.1 | API key는 환경변수/secret source에서만 읽는다. |
| NF4.2 | config나 로그에 secret이 커밋되면 안 된다. |

## 6. MVP 수용 기준

다음 조건을 만족하면 MVP 문서 집합은 수용 가능합니다:
- 3개의 reader-facing 문서만으로도 제품, 전략, 구현 계획을 이해할 수 있다.
- 시스템 설계가 scheduled 업종 + 종목 snapshot을 지원한다.
- degraded-mode 및 publication 규칙이 명확하다.
- backtest 경로가 point-in-time correctness를 보존한다.
- 남아 있는 deferred item이 MVP에 대해 진짜 non-blocking 임이 명확하다.
