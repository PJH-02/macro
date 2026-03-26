# macro-screener

[English version](README.md)

`macro-screener`는 2단계 모델을 사용하는 한국 주식 배치 스크리너입니다.

1. **Stage 1**: 5개 매크로 채널 상태(`G`, `IC`, `FC`, `ED`, `FX`)를 grouped sector 점수로 변환합니다.
2. **Stage 2**: 전체 종목 유니버스에 대해 DART 공시 기반 점수를 계산한 뒤, 매칭되는 Stage 1 섹터 점수를 더합니다.
3. 최종적으로 immutable snapshot, `latest.json` 포인터, SQLite 레지스트리 상태를 발행합니다.

다른 엔지니어/에이전트에게 전달할 최소 문서 세트는 다음 3개입니다.
- `doc/program-context.md`
- `doc/repository-orientation.md`
- `doc/code-context.md`

## 현재 모델

### Stage 1
- 설정 버전: `sector-v2`
- Stage 1 입력 artifact: `config/macro_sector_exposure.v2.json`
- taxonomy/exposure helper: `src/macro_screener/data/reference.py`
- 현재 런타임 점수 방식: **채널 상태 × grouped-sector exposure 직접 곱셈**
- 출력 필드명은 호환성 때문에 계속 `industry_scores`를 사용하지만, 실제 비즈니스 개념은 grouped sector입니다.

현재 grouped sector 예시는 다음과 같습니다.
- `반도체`
- `자동차/부품`
- `조선`
- `소프트웨어/인터넷/게임`
- `헬스케어/바이오`
- `유통/소매`
- `필수소비재(음식료)`

### Stage 2
- Stage 1이 종목 진입 자체를 제한하지 않으며, 전체 유니버스를 점수화합니다.
- DART 이벤트를 분류하고 decay를 적용해 raw DART score를 만듭니다.
- raw DART score는 유니버스 전체에서 z-score 정규화됩니다.
- 최종 종목 점수는 다음과 같습니다.

```text
final_score = normalized_dart_score + stage1_sector_score
```

- `normalized_financial_score` 필드는 모델 계약에 남아 있지만 현재는 항상 `0.0`입니다.

## 주요 진입점

핵심 코드 경로:
- CLI: `src/macro_screener/cli.py`
- 파이프라인 오케스트레이션: `src/macro_screener/pipeline/runner.py`
- 산출물 발행: `src/macro_screener/pipeline/publisher.py`
- 매크로 로딩/분류: `src/macro_screener/data/macro_client.py`
- KRX 종목 유니버스 + exposure 로딩: `src/macro_screener/data/krx_client.py`
- DART 수집/커서/캐시: `src/macro_screener/data/dart_client.py`
- Stage 1 점수 계산: `src/macro_screener/stage1/ranking.py`
- Stage 2 점수 계산: `src/macro_screener/stage2/ranking.py`

지원 CLI 명령:
- `show-config`
- `demo-run`
- `manual-run`
- `scheduled-run`
- `backtest-run`
- `backtest-stub`

## 기본 입력과 출력

기본 설정 파일은 `config/default.yaml`입니다.

주요 기본 경로:
- `stock_classification.csv`
- `data/reference/industry_master.csv`
- `config/macro_sector_exposure.v2.json`
- `data/snapshots/latest.json`
- `data/macro_screener.sqlite3`

실무상 중요한 점:
- config 안의 경로는 선택한 output root를 기준으로 해석됩니다.
- CLI의 기본 output root는 `repo_root/src` 입니다.
- 따라서 기본 CLI 실행 결과는 `src/data/...` 아래에 생성됩니다.

현재 발행 파일 이름은 다음을 포함합니다.
- `industry_scores.csv`
- `industry_scores.parquet`
- `screened_stock_list.csv`
- `screened_stocks_by_score.json`
- `screened_stocks_by_industry.json`
- `snapshot.json`
- `stock_scores.parquet`

taxonomy가 grouped sector로 바뀌었어도 호환성 때문에 `industry_*` 파일명은 유지합니다.

## 실행

```bash
PYTHONPATH=src:. python -m macro_screener show-config
PYTHONPATH=src:. python -m macro_screener demo-run
PYTHONPATH=src:. python -m macro_screener manual-run
PYTHONPATH=src:. python -m macro_screener scheduled-run
```

## 검증

```bash
PYTHONPATH=src:. pytest -q
PYTHONPATH=src:. python -m macro_screener demo-run --output-dir /tmp/macro-demo
```
