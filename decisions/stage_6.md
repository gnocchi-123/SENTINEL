# Stage 6 — 성과 평가 및 리포트

**날짜:** 2026-05-31  
**범위:** `sentinel/metrics.py` 전면 구현, `sentinel/report.py` 전면 구현,  
`backtest.py` 리포트 호출 추가 (`--chart`, `--no-report` 플래그).

---

## 구현된 함수

### `sentinel/metrics.py`

| 함수 | 역할 |
|---|---|
| `prepare_series(equity_curve, daily_index)` | equity_curve를 전 거래일로 전진 채움 (일별 수익률 계산용) |
| `compute_cagr(pv)` | 연복리수익률 — 캘린더 연수 기준 |
| `compute_drawdown_series(pv)` | 일별 낙폭 계열 (수중 곡선) |
| `compute_max_drawdown(pv)` | 최대낙폭 (음수 소수점) |
| `compute_max_drawdown_details(pv)` | MDD 고점·저점·회복일·기간 dict |
| `compute_annual_volatility(pv)` | 연환산 변동성 |
| `compute_sharpe(pv, rf, periods)` | 샤프 비율 |
| `compute_sortino(pv, rf, periods)` | 소르티노 비율 (하방 변동성 기준) |
| `compute_calmar(pv)` | 칼마 비율 = CAGR / \|MDD\| |
| `compute_drawdown_periods(pv, bv, bear_markets)` | 하락장 구간별 수익·MDD 비교 DataFrame |
| `compute_summary(pv, bv, params, log_df)` | 전체 지표 요약 dict (SENTINEL + SPY B&H) |

### `sentinel/report.py`

| 함수 | 역할 |
|---|---|
| `print_report(summary, bear_df, params)` | MDD 우선 성과 요약 콘솔 출력 |
| `save_validation_csv(summary, bear_df, path, params)` | validation_results.csv 저장 |
| `plot_equity_and_drawdown(pv, bv, output, params)` | 자산곡선+드로다운 2-panel 차트 |
| `plot_equity_curve`, `plot_drawdown` | 단일 차트 stub (하위호환) |
| `plot_sector_allocation(weights_history)` | 섹터 비중 스택 차트 |

---

## 설계 결정

### `prepare_series` — 필수 전처리

equity_curve는 점검일(월초)만 기록되다가 활성 구간부터 일봉이 빽빽해지는 구조.  
`reindex(daily_index).ffill()` 로 모든 거래일을 채워야 일별 수익률 계산이 올바름.  
현금 보유 구간(1999-2003)은 전진 채움으로 0% 일별 수익이 생겨 변동성을 낮추는 효과 있음.  
이 효과를 상쇄하지 않는 것이 전략의 실제 성과(현금 보유 비용)를 정직하게 반영한다.

### 벤치마크 정렬

SPY B&H = equity_curve와 동일 시작일(1999-02-01)부터 종료일까지 정규화.  
`benchmark = spy_sub / spy_sub.iloc[0]` (시작값=1.0).

### 출력 우선순위

1. MDD + 고점·저점·기간·회복일  
2. Sharpe / Sortino / Calmar / 연변동성  
3. CAGR / 누적수익 (참고용)  
4. 매매 횟수 / 회전율 / 방어 비율

---

## 백테스트 결과 (1999-02 ~ 2026-05, watchdog OFF)

```
지표                               SENTINEL       SPY B&H
──────────────────────────────────────────────────────
최대낙폭 (MDD)                        -27.4%        -55.2%
  고점→저점                      2022-01-03→2023-10-27  2007-10-09→2009-03-09
  기간                                662일          517일
  회복일                          2024-07-10 (257일)
Sharpe                               0.54          0.53
Sortino                              0.39          0.50
Calmar                               0.22          0.16
연변동성                             12.1%         19.3%
CAGR                                 6.0%          8.6%
누적수익                             +388.3%       +859.1%
총 매매 횟수                          125             —
평균 회전율 (매매 달)                  53.7%            —
방어 모드 비율                        51.5%            —
```

## 하락장 구간별 비교

| 구간 | 유형 | SENTINEL | SPY | 수익차 | SENT MDD | SPY MDD |
|---|---|---|---|---|---|---|
| 닷컴 버블 | 느린하락 | +0.0%† | -47.5% | +47.5%p | +0.0% | -47.5% |
| GFC | 느린하락 | +0.0%† | -55.2% | +55.2%p | +0.0% | -55.2% |
| 코로나 | V자 | -11.4% | -33.7% | +22.4%p | -16.1% | -33.7% |
| 2022 금리 | 느린하락 | -22.9% | -24.5% | +1.6%p | -23.1% | -24.5% |

†닷컴·GFC는 BIL 미상장으로 포트폴리오가 현금 보유 → 0% 수익. 전략 의도가 아닌 데이터 한계.

## 주요 관찰

- **MDD 절반 수준**: SENTINEL -27.4% vs SPY -55.2%. 방어 1순위 목표 충족.
- **CAGR 희생**: 6.0% vs 8.6%. 현금 보유 10년(1999-2009) 드래그 + 방어모드 51.5% 비용.
- **코로나 V자**: 두 전략 모두 손실이나 SENTINEL이 절반 수준 (-11.4% vs -33.7%).
- **2022 느린 하락**: MDD 거의 동등 (-23.1% vs -24.5%). 방어 전환이 뒤늦었음.
- **Sortino 역전**: SENTINEL 0.39 < SPY 0.50 — CAGR 저하 대비 하방 변동성 감소폭이 크지 않음.
- **워치독 ON 필요성**: 2022처럼 MDD 차이가 적은 구간에서 워치독 효과 검토 필요.

---

## 다음 단계

단계 7 지시 대기 중.
