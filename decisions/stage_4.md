# Stage 4 — 백테스트 엔진 구현 (모듈 4: 체결·비용·자산곡선)

**날짜:** 2026-05-31  
**범위:** `sentinel/engine.py` 전면 재작성, `backtest.py` 엔진 호출 추가. 워치독·성과지표 미구현.

---

## 구현된 함수 목록

| 함수 | 역할 |
|---|---|
| `run_backtest(daily, monthly, params)` | 월별 백테스트 루프. 반환: `(equity_curve, trade_log)` |
| `compute_turnover(prev_w, new_w)` | 편도 회전율 = 0.5 × Σ\|Δw\| |
| `apply_transaction_cost(pv, turnover, cost_bps)` | 거래비용 차감 후 포트폴리오 가치 |
| `assert_no_lookahead(signal_date, exec_date, data_up_to)` | 룩어헤드 조건 검증 (AssertionError) |
| `print_backtest_summary(equity, log_df, params)` | 요약 + 샘플 거래 로그 출력 |
| `_target_key(weights)` | (내부) 목표 티커 집합 → frozenset (무신호 비교 키) |
| `_portfolio_value(shares, prices_row)` | (내부) 일별 포트폴리오 가치 계산 |
| `_weight_vector(shares, prices_row, pv)` | (내부) 현재 보유 비중 딕셔너리 |
| `_execute_partial_exit(shares, new_target, prices, partial_exit)` | (내부) 탈락분 부분 청산 |
| `_full_rebalance(new_target, prices, pv)` | (내부) 목표 비중 완전 리밸런싱 |

---

## 주요 설계 결정

### 무신호=무행동 구현

`_target_key(weights) → frozenset[str]` 로 비교.

- 비교 기준 = **국면 상태 + 보유 섹터 집합** (티커 집합 동일 여부).
- `rebalance_on_weight_drift=false` 기본값: 비중 drift만으로는 거래하지 않음.
- 두 달 연속 `{XLK, XLY, XLE}` → NO TRADE, `{XLK, XLY, XLF}` → TRADE.

### partial_exit_fraction 로직

탈락 티커(prev에 있고 new_target에 없는 것)만 `partial_exit` 비율 청산:

```
freed = Σ(탈락 포지션 가치 × partial_exit) + Σ(유지·신규 포지션 가치)
retained = 탈락 포지션 가치 × (1 - partial_exit)  ← 잔류 포지션
new_target 비중으로 freed 자본 배분 + retained 포지션 합산
```

포트폴리오 가치 보존: freed + retained = pv_before. 거래비용은 실제 비중 변화(turnover)에만 적용.

### 가격 누락 안전장치

`_full_rebalance` / `_execute_partial_exit`에서 가격 NaN 티커를 건너뛰고 유효 비중 합계로 재정규화.  
`pv_after_raw == 0`(모든 가격 NaN)이면 `pv_before`로 폴백 후 경고.

### 일별 자산곡선 구성

- 점검 구간 이전 일자는 `_portfolio_value(shares, daily_prices.loc[d])`로 매일 계산.
- 보유 포지션 없는 날은 0으로 계산되므로 equity_curve에서 제외 (gap 발생, 아래 알려진 제약 참조).

---

## 전 구간 백테스트 결과 (2026-05-31 기준 캐시 데이터)

```
======================================================================
  SENTINEL 백테스트 — 전 구간 요약
======================================================================
  백테스트 기간   : 1999-02-01 ~ 2026-05-29
  시작 자산       : 1.0000
  종료 자산       : 4.8833  (+388.3%)
  점검 월 합계    : 328
  매매 발생 달    : 125
  무신호 건너뜀   : 203달  (61.9%)
======================================================================
```

---

## 샘플 거래 로그 (실행 결과)

```
날짜           신호기준일    국면  보유                            회전율      비용
1999-02-01   1999-01-29  OFF   AGG(100%)                     0.0%    0.00bp  ← 초기화 (AGG 미상장, 실제 미체결)
2009-11-02   2009-10-30  ON    XLE(33%) XLK(33%) XLY(33%)   50.0%    2.50bp
2009-12-01   2009-11-30  ON    SOXX(33%) XLK(33%) XLY(33%)  33.3%    1.67bp
2010-01-04   2009-12-31  ON    SOXX(33%) XLB(33%) XLK(33%)  33.8%    1.69bp
2010-06-01   2010-05-28  OFF   AGG(100%)                    100.0%   5.00bp
2010-10-01   2010-09-30  ON    XLI(33%) XLU(33%) XLY(33%)  100.0%   5.00bp
```

---

## 알려진 제약 및 관찰

### AGG / BIL 미상장 기간 — 방어 자산 미체결

- **AGG** 상장일: 2003-09-29. **BIL** 12개월 수익률 계산 가능 시점: 2008-06 이후.
- 1999-02 초기화 시 OFF(AGG) 신호였으나 AGG 가격 NaN → 실제 매수 미체결.
- **결정**: 이후 월에도 동일 OFF/AGG 신호 → "무신호=무행동"으로 건너뜀. 포트폴리오는 현금(pv=1.0) 유지.
- 결과: 1999-02 ~ 2009-10 (~10년) = 현금 보유, 0% 수익. `index_splicing: false` 사양 준수로 인한 의도된 동작.
- **실 운용에서는 이 기간 미발생 (실제 투자 시 BIL 대체재 또는 FRED T-bill 사용).**
- 향후 v1에서 BIL 스플라이싱 시 해소 예정.

### equity_curve gap

현금 보유 구간(shares={}) 중 점검일 사이 일봉은 daily_pv에 미기록 → equity_curve에 gap 발생.  
성과 지표 계산 시 `equity_curve.dropna()` 또는 `ffill` 사용 권장 (단계 5에서 처리).

### 2022년 휩쏘 흔적

2022-02: ON→OFF, 2022-03: OFF→ON, 2022-04~12: ON→OFF. 월 단위 전환 2회 발생.  
`confirmation_months=2` 또는 `buffer_pct=0.03~0.05` 적용 시 완화 가능 — 백테스트 비교 필요.

### OFF→ON / ON→OFF 전환 비용

- 전환 시 turnover ≈ 1.0 → 비용 5bp. 연간 2회 전환 기준 약 10bp.
- 섹터 교체만 발생 시 turnover ≈ 0.33~0.67 → 비용 1.67~3.33bp.

---

## 다음 단계

단계 5 지시 대기 중.
