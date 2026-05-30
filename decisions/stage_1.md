# Stage 1 — 프로젝트 골격 생성

**날짜:** 2026-05-30  
**범위:** 디렉터리 구조, params.yaml, 모듈 stub, backtest.py 엔트리포인트, README, requirements.txt. 데이터 다운로드·백테스트 로직 미구현.

---

## 생성된 파일 목록

| 파일 | 역할 |
|---|---|
| `params.yaml` | 전체 파라미터 단일 관리 파일. 매직넘버 여기서만. |
| `backtest.py` | 메인 엔트리. 현재: params 로드 + 가정 출력 + 면책 문구. |
| `sentinel/__init__.py` | 패키지 메타데이터. |
| `sentinel/data.py` | 데이터 수집·캐싱 stub. |
| `sentinel/signals.py` | 신호 산출 stub (모듈 1·2·3). |
| `sentinel/engine.py` | 백테스트 루프 stub (모듈 4 포함). |
| `sentinel/watchdog.py` | 워치독 오버레이 stub. |
| `sentinel/metrics.py` | 성과 지표 stub. |
| `sentinel/report.py` | 시각화·보고 stub. |
| `README.md` | 실행법·구조·토글 파라미터 설명. |
| `requirements.txt` | yfinance, pandas, numpy, pyyaml, matplotlib. |

---

## 주요 설계 결정

### 함수 시그니처 설계 원칙
- 모든 함수에 `params: dict` 인자 전달 → 파라미터 분산 방지.
- `signal_date: pd.Timestamp`를 명시적 인자로 분리 → 룩어헤드 금지 조건을 함수 경계에서 강제.
- `assert_no_lookahead()`를 `engine.py`에 독립 함수로 분리 → 테스트 가능한 형태로 룩어헤드 방지 보장.

### 면책 문구 위치
- `backtest.py` 실행 시 가장 먼저 출력 (파라미터 출력보다 앞).
- `report.py`에도 `DISCLAIMER` 상수 정의 → 차후 보고서 출력 시 재사용.

### params.yaml 구조 결정
- 섹터 리스트를 `tickers.sectors` 하위로 중첩 → 티커 관련 설정을 한 곳에 집중.
- 워치독 파라미터는 모두 `watchdog_` 접두사로 네임스페이스 통일.
- 휩쏘 완화 파라미터(`buffer_pct`, `confirmation_months`, `partial_exit_fraction`)도 명시적으로 포함 → 기본값은 OFF(0/1/1.0).

### stub 구조 원칙
- 본문은 `raise NotImplementedError`만.
- 각 함수 docstring에 룩어헤드 금지 여부, 반환값 형식, 예외 조건 명시.
- `sentinel/report.py`에 `DISCLAIMER` 상수를 모듈 수준으로 정의 → 다음 단계에서 import 가능.

---

## 확인된 가정 (이 단계에서 코드로 명시)

| 가정 | 코드 위치 |
|---|---|
| 체결 = 당월 첫 거래일 (룩어헤드 금지) | `engine.assert_no_lookahead()` 시그니처 |
| 무신호 = 무행동 | `engine.run_backtest()` docstring |
| SOXX 특별 로직 없음 | `signals.compute_sector_momentum()` docstring |
| 늦은 상장 ETF NaN 처리 | `signals.compute_sector_momentum()` docstring |
| 워치독 기본 OFF | `params.yaml`, `watchdog.apply_watchdog()` docstring |
| 면책 문구 항상 출력 | `backtest.py` DISCLAIMER, `report.py` DISCLAIMER |

---

## 검증 방법 (직접 확인 가능)

```bash
python backtest.py
```

출력 확인 항목:
1. 면책 문구(경고 박스)가 맨 위에 표시되는가
2. 모든 파라미터 섹션(데이터/국면필터/섹터모멘텀/포지션/비용/워치독/확정가정)이 출력되는가
3. 워치독이 OFF로 표시되는가
4. "단계 1 완료" 메시지가 마지막에 출력되는가

---

## 다음 단계

단계 2 지시 대기 중.
