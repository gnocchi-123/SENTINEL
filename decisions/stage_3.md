# Stage 3 — 신호 산출 모듈 구현

**날짜:** 2026-05-30  
**범위:** `sentinel/signals.py` 전면 재작성, `tests/test_signals_lookahead.py` 신규 작성.  
백테스트 루프·거래비용·워치독 미구현.

---

## 구현된 함수 목록

| 함수 | 역할 |
|---|---|
| `compute_target_weights(data, as_of_month_end, params)` | 공개 API. 모듈 1→2→3 순차 실행. 비중 합계=1.0 보장. |
| `_raw_phase_signal(daily_slice, params)` | 단일 월말 기준 원시 국면 신호(조건 A AND B). |
| `_compute_phase_filter(daily_as_of, monthly_as_of, params)` | confirmation_months 반영 국면 필터. |
| `_compute_momentum_scores(monthly_as_of, universe, params)` | 유니버스 티커별 가중평균 모멘텀 점수. |
| `_weights_equal(selected)` | 균등 배분. |
| `_weights_inverse_vol(selected, monthly_as_of, params)` | 변동성 역가중 배분. |

---

## API 설계 결정

### 단일 진입점 — `compute_target_weights(data, as_of_month_end, params)`
- Stage 1 stub의 분산된 다중 함수 시그니처(`compute_market_filter`, `compute_sector_momentum` 등)를 폐기하고, 단일 진입점으로 통합.
- `data`는 전체 일봉 DataFrame을 받되, 함수 첫 줄에서 `data.loc[:as_of_month_end]`로 슬라이싱 → 이후 모든 연산은 슬라이싱된 객체만 사용.
- `as_of_month_end`는 실제 거래일이 아닌 캘린더 월말 날짜를 받아도 동작 (`.loc[:date]`가 비거래일을 자연스럽게 처리).

### 룩어헤드 방지 — assert + 테스트 이중 보장
- `assert daily_as_of.index.max() <= as_of_month_end` : 슬라이싱 직후 경계 검증.
- 테스트에서 as_of 이후 데이터를 NaN·랜덤 노이즈로 오염 후 결과 불변성 확인.

---

## 모듈별 설계 결정

### 모듈 1 — 국면 필터

**조건 A (200일 SMA):**
- `spy_daily.rolling(200).mean().iloc[-1]` : 일봉 전체 사용.
- `buffer_pct > 0`이면 임계값 = `SMA × (1 + buffer_pct)`. 중립 구간(SMA ± buffer 사이)은 **방어 처리** (방어 우선).
- 데이터 200행 미만이면 False (보수).

**조건 B (SPY vs BIL 12개월 수익률):**
- 월말 리샘플 가격으로 `(p_now / p_12m_ago) - 1` 계산.
- BIL 미상장 또는 NaN이면 False (보수).

**confirmation_months:**
- 최근 N개 월말 모두 원시 신호 True여야 ON. 하나라도 False → 즉시 OFF.
- 비대칭 설계(ON 유지는 엄격, OFF 전환은 즉각) → 방어 우선 원칙에 부합.

### 모듈 2 — 섹터 모멘텀

- `build_universe(params)` = 섹터 11개 + SOXX. BIL·defense는 제외.
- 각 룩백(3·6·12개월): `iloc[-(lb+1)]` 기준 총수익률. 해당 시점 NaN → 티커 제외.
- 가중평균 = `Σ(weight × return) / Σ(weight)`.
- `price_ago == 0` 방어 처리 추가 (ZeroDivisionError 예방).

### 모듈 3 — 포지션 크기

- `equal`: `1/N` 균등.
- `inverse_vol`: 최근 `inverse_vol_lookback_months`개월 월별 수익률 σ의 역수로 가중, 합=1 정규화. 변동성이 모두 0인 퇴화 케이스는 균등 배분으로 폴백.

---

## 테스트 결과

```
18 passed in 1.32s
```

| 테스트 | 검증 내용 |
|---|---|
| `test_no_lookahead_nan` × 8 | as_of 이후 전체 NaN 오염 후 결과 불변 |
| `test_no_lookahead_random_noise` × 8 | as_of 이후 0.05~20× 랜덤 노이즈 오염 후 결과 불변 |
| `test_weights_sum_to_one` | 8개 시점 비중 합계 = 1.0 (오차 < 1e-9) |
| `test_defense_on_crisis_month` | 2008-11 → AGG 100% 확인 |

---

## 샘플 출력 — 2007-01 ~ 2009-12

```
날짜          국면   포트폴리오
2007-01-31    OFF   AGG(100.0%)   ← BIL 미상장, 조건 B 계산 불가
...
2009-09-30    OFF   AGG(100.0%)   ← 금융위기 / 200SMA 하회
2009-10-31    ON    XLK(33.3%)  XLY(33.3%)  XLE(33.3%)
2009-11-30    ON    SOXX(33.3%) XLK(33.3%)  XLY(33.3%)
2009-12-31    ON    SOXX(33.3%) XLK(33.3%)  XLB(33.3%)
```

---

## 확인된 가정 및 주요 관찰

### BIL 미상장 기간 처리 (중요)
- BIL 상장일: 2007-05-30. 12개월 수익률 계산 가능 시점: 2008-06 이후.
- 그 이전 기간은 조건 B 계산 불가 → **보수적으로 방어 처리**.
- 결과: 2007년 전체가 OFF — SPY가 200SMA 위(조건 A=True)였음에도 방어 모드 유지.
- 이는 버그가 아닌 스펙 준수(`index_splicing: false`) 결과이며, 실전에서는 BIL 대신 T-bill 지수나 스플라이싱으로 해결 가능. **향후 과제로 유보.**

### 2022년 휩쏘 관찰
- 2022-01: ON → 2022-02: OFF → 2022-03: ON → 2022-04~12: OFF.
- 2~3월에 ON↔OFF가 한 달 간격으로 발생하는 전형적 휩쏘.
- `confirmation_months=2` 또는 `buffer_pct=0.03~0.05` 토글로 완화 가능 — 백테스트 비교 필요.

### 방어 우선 일관성
- 조건 A·B 중 하나라도 미충족, 데이터 부족, 유효 섹터 없음 → 모두 방어자산 100%.
- NaN 전파를 의도적으로 차단하지 않음 (채우지 않음). 늦은 상장 ETF는 순위 풀에서 자동 제외.

---

## 다음 단계

단계 4 지시 대기 중.
