# Stage 5 — 워치독 오버레이 구현

**날짜:** 2026-05-31  
**범위:** `sentinel/watchdog.py` 전면 구현, `sentinel/engine.py` 워치독 연결,  
`tests/test_watchdog_regression.py` 신규 작성. 정규 리밸런싱 로직 변경 없음.

---

## 구현된 함수

### `sentinel/watchdog.py`

| 함수 | 역할 |
|---|---|
| `check_watchdog_trigger(daily_prices, check_date, params)` | AND 조건 판단 (SPY 낙폭 + VIX). 룩어헤드 금지 assert 포함. |
| `apply_watchdog(cur_weights, daily_prices, check_date, fired_flag, params)` | enabled/refire 플래그 체크 후 `check_watchdog_trigger` 호출. |
| `derisk_weights(cur_weights, defense_ticker, derisk_fraction)` | 주식분 × (1-fraction) 유지 + fraction → 방어자산. 합계=1.0 보장. |

### `sentinel/engine.py` 추가 사항

| 추가 | 내용 |
|---|---|
| `_run_watchdog_step(...)` | 워치독 1회 체크 + 디리스크 실행 헬퍼. shares/pv/log_entry 반환. |
| `run_backtest` — 워치독 연결 | 매 fill_range 일봉 + exec_date에서 `_run_watchdog_step` 호출 (wd_enabled=True 시에만). |
| `wd_fired_this_month` 플래그 | exec_date마다 리셋. "다음 월초 점검 전까지 추가 발동 없음" 구현. |
| `prev_target_key = None` | 워치독 발동 시 리셋 → 다음 정규 월초에서 강제 재평가 (재진입 구현). |
| `source` 컬럼 | log_df의 모든 행에 추가: "monthly" | "watchdog". |
| `print_backtest_summary` | 워치독 발동 로그 별도 출력 추가. |

---

## 설계 결정

### 정규 리밸런싱과의 분리

워치독은 `_run_watchdog_step` 헬퍼를 통해 완전히 분리된 코드 경로를 사용.  
`if wd_enabled:` 가드로 감싸므로 비활성화 시 연산 자체 미실행 → 비트 동일 보장.

### `wd_fired_this_month` 리셋 타이밍

각 period `i` 진입 직후(fill loop 이전)에 `False`로 리셋.  
커버 범위: fill_range(exec_date[i-1]+1 ~ exec_date[i]-1) + exec_date[i].  
= "전 정규 점검일 이후 ~ 현 정규 점검일까지" ≡ 스펙의 "다음 정규 월초 점검 전까지".

### 재진입 구현 (`prev_target_key = None`)

워치독 발동 시 `prev_target_key = None`으로 초기화.  
다음 exec_date에서 `signal_same = (None is not None and ...)` = False → 무조건 재평가.  
국면 필터 ON → 목표 섹터로 리밸런싱(재진입).  
국면 필터 OFF → 방어자산으로 리밸런싱.  
두 경우 모두 자동 복귀 없이 정규 월초 점검을 거쳐야 복귀.

### 2008 미발동 이유

2008년은 BIL 12개월 데이터 미확보로 국면 필터 OFF → 포트폴리오 100% AGG.  
워치독은 주식 보유분을 디리스크하는 장치 — 주식이 없으면 발동 대상 없음.  
`_run_watchdog_step` 첫 줄에서 `any(t != defense for t in shares)`로 guard.

---

## 회귀 테스트 결과 (7 / 7 통과)

| 테스트 | 내용 | 결과 |
|---|---|---|
| `test_watchdog_disabled_extreme_params_no_effect` | 극단 파라미터(임계값 거의 0)도 OFF이면 equity_curve·log 수치 비트 동일 | ✅ |
| `test_watchdog_explicit_false_identical_to_default` | explicit False vs default False 동일 | ✅ |
| `test_watchdog_enabled_fires_in_equity_periods` | ON 시 2020·2022에서 발동, 2009-11 이전 미��동 | ✅ |
| `test_derisk_weights_basic` | 50% 디리스크 → AGG 50%, 주식 각 25% | ✅ |
| `test_derisk_weights_100pct_derisk` | 100% 디리스크 → AGG 100% | ✅ |
| `test_derisk_weights_already_in_defense` | 방어자산 100%에서 디리스크 → 변화 없음 | ✅ |
| `test_derisk_weights_mixed_portfolio` | 주식+AGG 혼합에서 비중 합계=1 유지 | �� |

---

## 워치독 발동 로그 (전 구간, watchdog_enabled=True)

총 **9회** 발동. 모두 turnover=50%, 비용=2.50bp.

| 발동일 | 발동 전 | 발동 후 |
|---|---|---|
| 2010-05-20 | SOXX/XLI/XLY 각 33% | AGG 50% + 각 17% |
| 2011-08-04 | XLE/XLV/XLY 각 33% | AGG 50% + 각 16~17% |
| 2015-08-24 | XLP/XLV/XLY 각 33% | AGG 50% + 각 17% |
| 2018-02-08 | SOXX/XLK/XLY 각 33% | AGG 50% + 각 16~17% |
| 2018-12-20 | XLP/XLU/XLV 각 33% | AGG 50% + 각 16~18% |
| 2020-02-27 | SOXX/XLK/XLU 각 33% | AGG 50% + 각 16~17% |
| 2020-06-11 | SOXX/XLK/XLV 각 33% | AGG 50% + 각 16~17% |
| 2022-02-22 | XLE/XLF/XLP 각 33% | AGG 50% + 각 17% |
| 2022-04-22 | XLE/XLRE/XLU 각 33% | AGG 50% + 각 17% |

### 구간별 해석

**2008 (금융위기): 워치독 미발동**  
- 포트폴리오가 이미 100% AGG(방어). 디리스크 대상 없음.  
- 국면 필터가 BIL 데이터 부족으로 2008 내내 OFF 유지 → 정규 리밸런싱 자체가 방어 역할.

**2020-03 (COVID V자): 2회 발동**  
- 2020-02-27: SPY 급락 첫 번째 물결(−10.7% from 252일 고점 + VIX>28) → 50% 디리스크.  
- 2020-03-02: 정규 점검에서 국면 필터 OFF → 100% AGG로 완전 철수.  
- 2020-06-11: 반등 후 ON 복귀했으나 2차 조정에서 재발동. V자 장세에서 워치독의 양날 특성 확인.

**2022 (금리 인상): 2회 발동**  
- 2022-02-22: 인플레이션·우크라이나 충격(−10.5% + VIX>28) → 50% 디리스크.  
- 2022-04-22: 연준 긴축 가속(−12.4% + VIX>28) → 재발동 (새 월 진입 후 첫 발동).

### 최종 성과 비교

| | 종료 자산 | 총 수익률 |
|---|---|---|
| 워치독 OFF | 4.8833 | +388.3% |
| 워치독 ON | 4.5894 | +358.9% |

2020 V자 반등에서 워치독이 오히려 역효과(바닥 부근 매도→천장 부근 재매수) → 스펙의 "양날의 검" 확인.  
2022 같은 추세 하락에서는 효과 기대. 하락 유형별 분리 비교 필요 (단계 6 이후).

---

## 다음 단계

단계 6 지시 대기 중.
