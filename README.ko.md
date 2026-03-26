# macro-screener

한국 주식 배치 스크리너입니다.

- **Stage 1**: 매크로 채널 -> 그룹 섹터 점수 계산
- **Stage 2**: 전체 종목 유니버스에 대해 DART 기반 개별 종목 점수 계산 후 Stage 1 섹터 문맥을 더함
- **출력**: 기본적으로 `src/data/` 아래에 스냅샷 산출물 생성

## 현재 모델

### Stage 1
- 채널: `G`, `IC`, `FC`, `ED`, `FX`
- 런타임은 매크로 신호를 signed channel state/score로 해석
- 섹터 점수는 **채널 점수 × 섹터 노출계수** 직접 곱셈으로 계산
- 분류 체계는 `doc/plan.md`의 grouped sector 기준을 따름

### Stage 2
- Stage 1 섹터 gating 없이 전체 종목 유니버스를 점수화
- 현재 최종 점수식:

```text
final_stock_score = stage2_individual_stock_score + stage1_sector_score
```

- 현재 `stage2_individual_stock_score`는 DART 기반
- 현재 `stage1_sector_score`는 해당 종목이 매핑된 grouped sector 점수

## 분류 체계

현재 종목 분류는 grouped sector로 접습니다. 예:
- `반도체`
- `자동차/부품`
- `조선`
- `소프트웨어/인터넷/게임`
- `헬스케어/바이오`
- `유통/소매`
- `필수소비재(음식료)`

정확한 매핑 규칙과 전체 appendix는 `doc/plan.md`를 참고하세요.

## 주요 경로

- CLI: `src/macro_screener/cli.py`
- 파이프라인: `src/macro_screener/pipeline/runner.py`
- 발행: `src/macro_screener/pipeline/publisher.py`
- taxonomy/exposure: `src/macro_screener/data/reference.py`
- 종목/노출 로드: `src/macro_screener/data/krx_client.py`
- Stage 1: `src/macro_screener/stage1/ranking.py`
- Stage 2: `src/macro_screener/stage2/ranking.py`

## 기본 산출물

CLI 기본 output root는 `src`이므로 산출물은 `src/data/...` 아래에 생성됩니다.

파일명 호환성은 유지합니다:
- `industry_scores.csv`
- `industry_scores.parquet`
- `screened_stock_list.csv`
- `screened_stocks_by_score.json`
- `screened_stocks_by_industry.json`
- `snapshot.json`
- `stock_scores.parquet`

비즈니스 개념은 grouped sector이지만, 호환성을 위해 `industry_*` 파일명은 유지됩니다.

## 실행

```bash
python -m macro_screener show-config
python -m macro_screener demo-run
python -m macro_screener manual-run
python -m macro_screener scheduled-run
```

## 검증

```bash
PYTHONPATH=src:. pytest -q
PYTHONPATH=src:. python3 -m macro_screener demo-run --output-dir /tmp/macro-demo
```

## 문서

- `doc/program-context.md`
- `doc/repository-orientation.md`
- `doc/code-context.md`
- `doc/plan.md`
