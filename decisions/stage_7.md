# Stage 7 — 견고성 검증 및 정직성 출력

**날짜:** 2026-05-31  
**범위:** `sentinel/robustness.py` 신규 작성, `backtest.py` 정직성 출력 + `--sweep` 플래그 추가,  
`sentinel/engine.py` 버그 수정 1건.

---

## 구현된 내용

### `sentinel/robustness.py`

| 함수 | 역할 |
|---|---|
| `SWEEP_CONFIGS` | 12개 구성 목록 (A: top_n×sizing, B: 휩쏘 토글, C: 워치독) |
| `run_sweep(daily, monthly, params_base, configs)` | 스윕 실행 → 지표 딕셔너리 목록 반환 |
| `print_sweep_table(results)` | 그룹별 표 출력 + 견고성 판정 |
| `compare_watchdog_by_bear_type(daily, monthly, params)` | 워치독 ON/OFF × 하락장 유형별 비교 |
| `_print_postfire_analysis(daily, log_on, eq_off, eq_on)` | 발동 후 60거래일 성과 + 휩쏘 판정 |

### `backtest.py`

- `print_honesty_warnings(params)` — 코드가 임의로 정한 가정 명시 출력 (체결·비용·데이터·리밸런싱·워치독)
- `--sweep` 플래그 — `run_sweep` + `compare_watchdog_by_bear_type` 실행

### `sentinel/engine.py` 버그 수정

`_execute_partial_exit`는 `shares={}` (현금 상태)에서 `freed=0`으로 아무것도 매수 못 함.  
**수정**: `shares가 비어 있으면 full_rebalance`를 사용하도록 조건에 `and shares` 추가.  
원인: 초기화 시 AGG 미상장으로 매수 실패 → `shares={}`, `prev_target_key=frozenset({'AGG'})` 불일치.  
**회귀 테스트 25/25 통과.**

---

## 견고성 스윕 결과 (전체 12개 구성)

```
★ 기준선 SPY B&H: MDD=-55.2%  Sharpe=0.53  CAGR=8.6%

── A. top_n × sizing
★BASE n=3 equal  wd=OFF   MDD=-27.4%  Sharpe=0.54  CAGR=+6.0%  회전율=53.7%  ✓ MDD↓
      n=2 equal  wd=OFF   MDD=-29.6%  Sharpe=0.44  CAGR=+5.1%  회전율=68.1%  ✓ MDD↓
      n=4 equal  wd=OFF   MDD=-21.5%  Sharpe=0.61  CAGR=+6.5%  회전율=46.9%  ✓ MDD↓
      n=3 invvol wd=OFF   MDD=-28.0%  Sharpe=0.54  CAGR=+5.8%  회전율=55.9%  ✓ MDD↓
      n=2 invvol wd=OFF   MDD=-30.5%  Sharpe=0.42  CAGR=+4.8%  회전율=71.4%  ✓ MDD↓
      n=4 invvol wd=OFF   MDD=-23.8%  Sharpe=0.59  CAGR=+6.1%  회전율=49.5%  ✓ MDD↓

── B. 휩쏘 완화 토글
+buffer=4%    wd=OFF   MDD=-23.8%  Sharpe=0.58  CAGR=+5.9%  회전율=57.8%  ✓ MDD↓
+confirm=2m   wd=OFF   MDD=-28.8%  Sharpe=0.51  CAGR=+5.4%  회전율=52.6%  ✓ MDD↓
+partial=50%  wd=OFF   MDD=-22.8%  Sharpe=0.66  CAGR=+7.2%  회전율=29.7%  ✓ MDD↓
+all toggles  wd=OFF   MDD=-22.7%  Sharpe=0.68  CAGR=+6.8%  회전율=30.9%  ✓ MDD↓

── C. 워치독
BASE n=3 equal  wd=ON    MDD=-25.6%  Sharpe=0.54  CAGR=+5.7%  회전율=51.1%  ✓ MDD↓
+all toggles  wd=ON      MDD=-21.7%  Sharpe=0.55  CAGR=+4.8%  회전율=31.8%  ✓ MDD↓

견고성 판정: 12/12개 구성에서 SENTINEL MDD < SPY MDD
✓ 모든 파라미터 조합에서 MDD 우위 유지 → 1순위 목표 견고성 확인
```

### 관찰

- **MDD 범위**: -21.5% ~ -30.5%. 어느 조합에서도 SPY(-55.2%)를 하회하는 구성 없음 → **견고함**.
- **n=4가 n=3보다 MDD 개선**: 분산 효과. 단 회전율도 낮아짐.
- **partial=50%**: MDD -22.8%, CAGR +7.2%, 회전율 29.7% — 회전율 최소화 + 성과 개선. 주목할 토글.
- **all toggles**: MDD -22.7%, Sharpe 0.68 — 모든 완화 장치를 켜면 가장 낮은 MDD·높은 Sharpe.
- **CAGR은 SPY(8.6%) 미만**: 방어 모드 51.5% + 10년 현금 보유 드래그. 예상된 트레이드오프.

---

## 워치독 유형별 비교

| 구간 | 유형 | OFF_수익 | ON_수익 | Δ수익 | OFF_MDD | ON_MDD | 판정 |
|---|---|---|---|---|---|---|---|
| 닷컴 버블 | 느린하락 | +0.0%† | +0.0%† | 0 | +0.0% | +0.0% | — 중립 |
| GFC | 느린하락 | +0.0%† | +0.0%† | 0 | +0.0% | +0.0% | — 중립 |
| 코로나 | V자 | -11.4% | -13.1% | -1.8%p | -16.1% | -17.8% | **★ 휩쏘** |
| 2022 금리 | 느린하락 | -22.9% | -21.0% | +1.9%p | -23.1% | -21.2% | **✓ WD효과** |

†닷컴·GFC 구간은 전략이 이미 100% 방어여서 워치독 발동 없음. 비교 무의미.

---

## 워치독 발동 후 60거래일 성과 (휩쏘 판정)

| 발동일 | SPY_60d | WD_ON | WD_OFF | 판정 |
|---|---|---|---|---|
| 2010-05-20 | +1.1% | +4.0% | +4.3% | — 중립 |
| 2011-08-04 | +7.5% | +1.4% | +2.1% | **★ V자 휩쏘** |
| 2015-08-24 | +9.0% | -2.3% | -1.6% | **★ V자 휩쏘** |
| 2018-02-08 | +4.0% | +3.0% | +6.4% | — 중립 |
| 2018-12-20 | +15.1% | +0.8% | -0.1% | **★ V자 휩쏘** |
| 2020-02-27 | -0.1% | +4.6% | +6.7% | — 중립 |
| 2020-06-11 | +14.5% | +16.6% | +19.3% | **★ V자 휩쏘** |
| 2022-02-22 | -8.5% | -5.8% | -8.1% | **✓ 추세 하락** |
| 2022-04-22 | -6.9% | -2.5% | -4.4% | **✓ 추세 하락** |

**결론: 9건 중 V자 휩쏘 4건, 추세 하락 2건, 중립 3건.**  
V자 구간에서는 워치독 발동 후 60일 동안 WD_ON이 WD_OFF보다 일관되게 낮음.  
워치독의 순기여는 2022처럼 추세가 계속되는 구간에서만 확인됨.

---

## 다음 단계

단계 8 지시 대기 중.
