# Macro Screener MVP

[English version](README.md)

**매크로 국면 기반 2단계 한국 주식 스크리너**를 위한 최소 실행 가능 MVP입니다.

최종 사용자용 문서 세트는 다음과 같습니다.
- `doc/strategy.md`
- `doc/prd.md`
- `doc/plan.md`
- `doc/open-questions.md`

## 프로그램이 하는 일

이 스크리너는 두 단계로 동작합니다.

### Stage 1 — 업종 랭킹
Stage 1은 다섯 개의 매크로 채널을 분류한 뒤 전체 업종 순위를 계산합니다.

채널:
- `G` — 성장 / 경기활동
- `IC` — 인플레이션 / 비용
- `FC` — 금융여건
- `ED` — 외부수요
- `FX` — 외환

최종 MVP 목표는 **한국 + 미국 외부 매크로** 구조입니다.
- 한국 매크로/통계 입력: `ECOS`, `KOSIS`
- 미국 외부 매크로 입력: `FRED` / `ALFRED` 또는 동등한 공식소스 어댑터 계층
- 종목/업종 필터링 권한: `stock_classification.csv`

### Stage 2 — 종목 랭킹
Stage 2는 DART 스타일 공시 이벤트를 종목 점수로 변환하고 Stage 1 업종 맥락과 결합합니다.

결과물:
- 전체 업종 랭킹
- 전체 종목 랭킹
- 변경 불가능한 스냅샷 산출물

MVP에는 **하드 컷오프가 없습니다.** 결과는 최종 매수 리스트가 아니라 전체 순위표입니다.

## 현재 구현 상태

현재 코드베이스는 이미 다음을 제공합니다.
- `src/macro_screener/` 아래의 실제 패키지 경계
- Stage 1 / Stage 2 실제 랭킹 로직
- **parquet + SQLite** 스냅샷 발행
- `manual`, `demo`, `scheduled`, `backtest` 실행 경로

중요한 현재 상태 메모:
- 코드에는 여전히 수동 / 파일 / 데모 폴백 경로가 남아 있습니다.
- 최종 프로덕션 목표는 현재 폴백 위주의 런타임이 아니라 위 문서 세트에 정의된 형태입니다.

## 현재 코드의 데이터 경계

현재 어댑터 경계:
- `src/macro_screener/data/macro_client.py`
- `src/macro_screener/data/krx_client.py`
- `src/macro_screener/data/dart_client.py`

현재 런타임 경계:
- `src/macro_screener/pipeline/runner.py`
- `src/macro_screener/pipeline/scheduler.py`
- `src/macro_screener/backtest/engine.py`

## 발행 계약

정식 downstream MVP 계약은 다음과 같습니다.
- 변경 불가능한 parquet 산출물
- 최신 포인터 파일 `data/snapshots/latest.json`
- 운영/감사용 SQLite 저장소 (주요 외부 소비 인터페이스는 아님)

## 참고

- 이 프로젝트는 아직 MVP 단계입니다.
- 최종 제품 범위는 **배치형 스크리너**이며 포트폴리오/집행 시스템이 아닙니다.
- BIS, OECD, IMF 는 MVP 필수 런타임 어댑터가 아니라 향후/참고용 제공자입니다.
- 영어 문서 세트에 대응하는 한국어 상세 문서는 현재 유지하지 않습니다.
