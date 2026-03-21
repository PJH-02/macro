# 전략 문서: 매크로 국면 기반 2단계 스크리닝 시스템 (MVP)

[English version](strategy.md)

> 목적: 제품 의도, 아키텍처 전략, 그리고 최종 MVP 운영 결정을 한 문서에서 간결하게 정리한 기준 문서.

## 1. 왜 이 프로젝트가 존재하는가

이 프로젝트의 목적은 반복 가능하고 일관된 한국 주식 스크리닝 시스템을 만드는 것입니다. 이 시스템은:
- 매크로 우호도를 기준으로 **업종**을 랭킹하고,
- 공시 기반 촉매를 기준으로 **종목**을 랭킹하며,
- downstream 전략이 소비할 수 있는 전체 유니버스 스냅샷을 발행합니다.

이 시스템은 **스크리너**이지, 포트폴리오 최적화기나 실행 엔진이 아닙니다.

## 2. MVP 범위

### 포함 범위
- 시장: **KOSPI + KOSDAQ 보통주만**
- 실행 주기: **하루 2회 배치 실행**
  - 장 시작 전(pre-open)
  - 장 종료 후(post-close)
- 출력물:
  - 전체 업종 랭킹
  - 전체 종목 랭킹
  - 변경 불가능한 발행 스냅샷
- Stage 1: 매크로 기반 업종 점수 계산
- Stage 2: Stage 1 결과를 조건으로 사용하는 DART 기반 종목 점수 계산
- 수동 실행 경로 및 백테스트 실행 경로

### 제외 범위
- 실시간 장중 운영 업데이트
- 뉴스 오버레이의 운영 규칙
- 포트폴리오 최적화 / 주문 실행
- DART 공시의 전문(full-text) 의미 해석
- MVP에서의 유동성 / 시가총액 / 특수상태 필터
- 완전히 구체화된 프로덕션용 매크로 채널 공식

## 3. 핵심 전략 원칙

1. **2단계 설계**
   - Stage 1은 업종을 랭킹합니다.
   - Stage 2는 Stage 1 결과를 입력 특징으로 사용해 종목을 랭킹합니다.
2. **전체 유니버스 출력**
   - 업종이나 종목 수준에서 하드 컷오프를 두지 않습니다.
3. **시점 적합성(Point-in-time correctness)**
   - 실거래 실행과 백테스트 실행은 해당 cutoff 시점에 실제로 이용 가능했던 데이터만 사용해야 합니다.
4. **배치 우선 아키텍처**
   - MVP는 연속 업데이트가 아니라 신뢰할 수 있는 정기 스냅샷 발행에 최적화됩니다.
5. **불변 발행(Immutable publication)**
   - 발행된 스냅샷은 감사 가능한 산출물이며 절대 덮어써서는 안 됩니다.
6. **암묵적 DataFrame 동작보다 명시적 계약 우선**
   - 핵심 handoff 객체와 스냅샷 의미론은 안정적으로 유지되어야 합니다.

## 4. 전략 아키텍처

## 4.1 Stage 1: 매크로 기반 업종 점수 계산

Stage 1은 채널 상태와 노출도 매핑을 이용해 업종 랭킹을 생성합니다.

### 채널 집합
- `G` — 성장 / 경기활동
- `IC` — 인플레이션 / 비용
- `FC` — 금융여건
- `ED` — 외부수요
- `FX` — 외환

### MVP에서 고정된 규칙
- 각 채널 상태는 `{-1, 0, +1}` 중 하나입니다.
- 채널의 경제적 의미는 고정입니다.
- 노출도 행렬 값은 `{-1, 0, +1}` 입니다.
- 업종 점수 = 기본 점수 + 오버레이 조정값
- 빠른 오버레이는 느린 베이스 라벨을 **대체하지 않습니다.**
- 업종 동점 처리 순서는 다음과 같습니다:
  1. 절대 음수 패널티가 더 작은 업종
  2. 양의 기여도가 더 큰 업종
  3. 업종 코드 오름차순

### MVP 채널 상태 방법론
MVP에서는 **manual override / stub mode만이 문서상 허용된 채널 상태 방법**입니다.

현재 확정된 내용:
- 5개 채널과 각 경제적 의미
- 이산 상태 공간
- 상태의 효력 발생 시점에 대한 의미론
- Stage 1이 상태를 받아 전체 업종 랭킹을 생성한다는 점

MVP 이후로 보류된 내용:
- 채널별 정확한 변수 정의
- 정확한 수치 임계값
- 프로덕션용 채널 상태 공식

## 4.2 Stage 2: DART 기반 종목 점수 계산

Stage 2는 공시 상태를 종목 랭킹으로 변환합니다.

### MVP에서 고정된 규칙
- 분류는 공시 코드 + 제목 기반 패턴 매칭을 사용합니다.
- 전문(full-text) 의미 해석은 범위 밖입니다.
- DART 이벤트는 일회성 점이 아니라 시간 감쇠를 갖는 상태 변수입니다.
- 종목 점수는 정규화된 DART 점수와 정규화된 업종 점수를 결합합니다.
- `FinancialScore = 0` 이지만, 수식 내 슬롯은 유지합니다.

### 확정된 기본값
- 스냅샷 단위 횡단면 z-score 정규화
- 표준편차가 0이면 정규화된 성분 = `0`
- `lambda` 는 정규화 **이후** 적용
- 감쇠는 해석 가능한 half-life 기본값을 사용하는 trading-day 지수 감쇠
- MVP DART half-life 기본값:
  - `supply_contract = 20`
  - `treasury_stock = 10`
  - `facility_investment = 60`
  - `dilutive_financing = 60`
  - `correction_cancellation_withdrawal = 10`
  - `governance_risk = 120`
- 종목 동점 처리 순서는 다음과 같습니다:
  1. raw DART score가 더 높은 종목
  2. raw industry-score contribution이 더 큰 종목
  3. 종목 코드 오름차순

### 4.3 최소 계약 필드

reader-facing 문서 집합에는 최소 계약 형태를 명시적으로 유지하여, 구현자가 숨겨진 산출물 없이도 handoff를 받을 수 있게 합니다.

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

## 5. 런타임 전략

## 5.1 정기 실행(Scheduled runs)
- pre-open 실행: 기본 `08:30 KST`
- post-close 실행: 기본 `15:45 KST`
- 두 실행 모두 변경 불가능한 스냅샷을 발행합니다.

## 5.2 수동 실행(Manual runs)
- CLI를 통해 허용됩니다.
- 여전히 point-in-time, 영속성, 불변성 규칙을 따라야 합니다.

## 5.3 백테스트 실행(Backtest runs)
- 동일한 논리 파이프라인을 재생합니다.
- point-in-time correctness를 유지합니다.
- 독립적인 날짜는 병렬 처리할 수 있습니다.
- 종가 기반 다음 거래일 적용 규칙을 보존해야 합니다.

## 6. 최종 MVP 운영 결정

### 데이터 소스
- KRX 시장 데이터: KRX 공식 엔드포인트
- DART: 환경변수 기반 API 키를 사용하는 OpenAPI
- 한국 휴일 처리: 프로젝트 캘린더 helper 뒤에 있는 하드코딩 MVP 리스트
- 향후 선호되는 한국 관련 매크로 소스: `ECOS`, `KOSIS`, `DART`
- 향후 선호되는 글로벌 매크로 소스: `BIS`

### downstream 소비 계약
- 정식 외부 출력은 **변경 불가능한 parquet 스냅샷** 입니다.
- 정식 최신 포인터는 `data/snapshots/latest.json` 입니다.
- SQLite는 운영/감사용 저장소이며, 주된 외부 소비 계약은 아닙니다.
- CLI export/read helper는 편의용으로 존재할 수 있습니다.
- MVP에서는 API/service 계약을 고정하지 않습니다.

### scheduled-window 식별
- `scheduled_window_key = (trading_date, run_type)`
- `run_id` 는 비즈니스 윈도우가 아니라 개별 실행 시도를 식별합니다.
- 하나의 비즈니스 윈도우에는 여러 draft 시도가 있을 수 있지만, 발행 스냅샷은 최대 하나입니다.

## 7. MVP degraded-mode 확정 정책

이 항목들은 예시가 아니라 **최종 MVP 확정 정책**입니다.

- DART가 설정된 재시도 이후에도 복구되지 않으면 **stale DART data** 로 실행하고 결과에 플래그를 남깁니다.
- 한국/글로벌 매크로 소스를 사용할 수 없으면 **last known channel states** 를 사용하고 warning을 남깁니다.
- Stage 1 성공 후 Stage 2가 실패하면 **Stage 1-only** 결과를 발행하고 run incomplete 상태를 기록합니다.
- Stage 1이 실패하면 Stage 2는 실행하지 않습니다.
- 알 수 없는 DART 공시 유형은 neutral로 처리하고 로그/카운트 추적합니다.

## 8. 최소 MVP alert 매트릭스

- neutral/unknown DART classification ratio `> 20%` → warning
- recovery 중 missed scheduled run 감지 → error
- snapshot publication failure → critical
- 설정된 재시도 이후에도 외부 API 실패 반복 → error

운영자 대응은 implementation plan에 정의합니다.

## 9. 의도적으로 보류된 항목

이 항목들은 MVP 구현 handoff의 blocker는 아니지만, 아직 완전히 확정된 것은 아닙니다.
- 정확한 SQLite physical DDL 및 비핵심 인덱스
- migration tool 사용 여부 vs 수동 버전 SQL
- 비파일 기반 downstream service/API 계약
- 정확한 프로덕션용 채널 변수/임계값
- MVP alert matrix를 넘어서는 세밀한 alert/SLO 튜닝

## 10. 읽기 순서

세 개의 프로젝트 문서만 읽는다면, 다음 순서를 권장합니다.
1. `doc/strategy.ko.md`
2. `doc/prd.ko.md`
3. `doc/plan.ko.md`
