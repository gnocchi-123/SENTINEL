# SENTINEL

**S**ector-rotating **T**rend system with **E**xecution **N**ot **I**nfluenced by **E**motion **L**ogic

규칙 기반 추세추종 자산배분 백테스트 엔진. 하락장 방어(자본 보존)를 최우선으로,
섹터 상대모멘텀으로 상승장 수익을 추구한다.

> **경고:** 이 도구는 방법론 검증 목적의 시뮬레이터입니다.
> 과거 성과는 미래 수익을 보장하지 않으며, 투자 자문이 아닙니다.

---

## 설치

```bash
pip install -r requirements.txt
```

## 실행

```bash
# 기본 실행 (params.yaml 로드 및 적용 가정 출력)
python backtest.py

# 파라미터 파일 지정
python backtest.py --params params.yaml
```

## 프로젝트 구조

```
sentinel/
├── data.py       # 데이터 수집·캐싱 (yfinance → price_data.csv)
├── signals.py    # 신호 산출 (국면 필터·섹터 모멘텀·포지션 크기)
├── engine.py     # 백테스트 실행 루프
├── watchdog.py   # 워치독 오버레이 (기본 OFF)
├── metrics.py    # 성과 지표 (MDD·CAGR·Sharpe·Sortino)
└── report.py     # 시각화·보고
backtest.py       # 메인 엔트리포인트
params.yaml       # 전체 파라미터 (매직넘버 여기서만 관리)
requirements.txt
decisions/        # 단계별 주요 결정 기록
```

## 파라미터 조정

모든 파라미터는 `params.yaml`에서 관리한다. 코드 내 매직넘버 하드코딩 금지.

주요 토글:
- `tickers.semiconductor`: `SOXX` ↔ `SMH`
- `tickers.defense`: `AGG` ↔ `IEF` ↔ `BIL`
- `sizing`: `equal` ↔ `inverse_vol`
- `top_n_sectors`: 2 / 3 / 4 (견고성 스윕)
- `watchdog_enabled`: `false` ↔ `true`
- `transaction_cost_bps`: `5` ↔ `0` (비용 영향 확인)

## 모델 구조 (4개 모듈 + 워치독 오버레이)

매월 첫 거래일에 직전 월말 데이터로 신호를 산출하고, 당월 첫 거래일 종가로 체결.

```
1. 국면 필터  → SPY > 200일 MA AND SPY 12M 수익률 > BIL
               실패 시 → 방어자산(AGG) 100%

2. 섹터 모멘텀 → 3·6·12개월 혼합 순위 → 상위 N개 보유
               (SOXX 포함, 동일 순위 풀, 특별 로직 없음)

3. 포지션 크기 → 균등배분(기본) 또는 변동성 역가중(토글)

4. 청산        → 순위 탈락 또는 국면 필터 OFF 시에만
               무신호 = 무행동 (비중 드리프트 재조정도 없음)

[워치독 오버레이 — 기본 OFF]
   매 거래일 점검: SPY 252일 고점 대비 -10% AND VIX > 28
   발동 시: 주식분 50% 부분 청산 → 방어자산
   재진입: 다음 월초 국면 필터 재충족 시에만 (자동 복귀 없음)
```

## 알려진 약점

- 200일선 필터는 V자 급락(2020-03)에서 휩쏘 손실에 취약함.
- 이 모델은 느린 하락장(2008·2022)에 강하고, 빠른 V자 반등장에 약함. 구조적 대가.
- 워치독도 V자 급락에서는 오히려 독이 될 수 있어 기본 OFF.
