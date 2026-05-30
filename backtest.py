"""SENTINEL 백테스트 메인 엔트리포인트.

사용법:
    python backtest.py [--params params.yaml]

현재 단계: params.yaml 로드 및 적용된 가정 출력.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

# ──────────────────────────────────────────────
# 면책 문구 및 경고 (항상 출력)
# ──────────────────────────────────────────────
DISCLAIMER = """
╔══════════════════════════════════════════════════════════════════════╗
║                          ⚠  경고 및 면책 고지  ⚠                    ║
╠══════════════════════════════════════════════════════════════════════╣
║  이 프로그램은 규칙 기반 전략의 역사적 시뮬레이션(백테스트) 도구입니다. ║
║                                                                      ║
║  1. 과최적화(curve fitting) 위험                                      ║
║     파라미터를 과거 데이터에 맞게 조정할수록 실전 성과는 악화될 수 있습니다.║
║     파라미터 견고성(robustness) 스윕으로 반드시 검증하십시오.           ║
║                                                                      ║
║  2. 과거 성과는 미래 수익을 보장하지 않습니다                           ║
║     백테스트 결과는 가상의 과거 성과이며, 실제 투자 수익과 다를 수 있습니다.║
║                                                                      ║
║  3. 투자 자문 아님                                                     ║
║     이 결과는 방법론 검증 목적이며, 특정 투자를 권유하지 않습니다.       ║
╚══════════════════════════════════════════════════════════════════════╝
"""


def load_params(path: str | Path) -> dict:
    """params.yaml을 로드하고 딕셔너리로 반환한다.

    Args:
        path: params.yaml 파일 경로.

    Returns:
        파라미터 딕셔너리.

    Raises:
        FileNotFoundError: 파일이 없을 경우.
        yaml.YAMLError: YAML 파싱 오류.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"params 파일을 찾을 수 없습니다: {path}")
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def print_assumptions(params: dict) -> None:
    """적용된 파라미터와 주요 가정을 화면에 출력한다."""

    tickers = params.get("tickers", {})
    sectors = tickers.get("sectors", [])

    print("=" * 70)
    print("  SENTINEL — 적용된 파라미터 및 확정 가정")
    print("=" * 70)

    print("\n[데이터]")
    print(f"  백테스트 시작일   : {params.get('start_date')}")
    print(f"  시장 기준         : {tickers.get('market')}")
    print(f"  섹터 유니버스     : {', '.join(sectors)}")
    print(f"  반도체 후보       : {tickers.get('semiconductor')}  (SMH 토글 가능)")
    print(f"  무위험 기준       : {tickers.get('risk_free')}")
    print(f"  방어 자산         : {tickers.get('defense')}  (IEF / BIL 토글 가능)")
    print(f"  VIX               : {tickers.get('vix')}")
    print(f"  가격 캐시         : {params.get('price_cache')}")
    print(f"  지수 스플라이싱   : {'적용' if params.get('index_splicing') else '미적용 (향후 과제)'}")

    print("\n[국면 필터 — 모듈 1]")
    print(f"  SPY 이동평균 기간 : {params.get('ma_period_days')}일")
    print(f"  MA 버퍼           : ±{params.get('buffer_pct', 0.0) * 100:.1f}%")
    print(f"  절대모멘텀 기간   : {params.get('absolute_momentum_lookback_months')}개월 (SPY vs BIL)")
    print(f"  신호 확인 기간    : {params.get('confirmation_months')}개월 연속")

    print("\n[섹터 모멘텀 — 모듈 2]")
    lookbacks = params.get("momentum_lookbacks_months", [])
    weights = params.get("momentum_weights", [])
    print(f"  모멘텀 기간       : {lookbacks}개월")
    print(f"  가중치            : {weights}  (단순평균)")
    print(f"  보유 섹터 수 (N)  : {params.get('top_n_sectors')}  (2/3/4 스윕 대상)")

    print("\n[포지션 크기 — 모듈 3]")
    sizing = params.get("sizing", "equal")
    print(f"  배분 방식         : {sizing}  (equal=균등배분, inverse_vol=변동성 역가중)")
    if sizing == "inverse_vol":
        print(f"  역가중 기간       : {params.get('inverse_vol_lookback_months')}개월")

    print("\n[체결·비용 — 모듈 4]")
    print(f"  체결 방식         : 직전 월말 신호 → 당월 첫 거래일 종가 체결 (룩어헤드 금지)")
    print(f"  거래비용          : 편도 {params.get('transaction_cost_bps')}bp")
    print(f"  비중 드리프트 리밸 : {'ON' if params.get('rebalance_on_weight_drift') else 'OFF'}")
    print(f"  부분 청산 비율    : {params.get('partial_exit_fraction', 1.0) * 100:.0f}%")

    print("\n[워치독 — 월중 방어 오버레이]")
    wd_on = params.get("watchdog_enabled", False)
    print(f"  활성화            : {'ON' if wd_on else 'OFF (기본 OFF, 백테스트 검증 후 채택 결정)'}")
    print(f"  낙폭 트리거       : {params.get('watchdog_drawdown_threshold') * 100:.0f}% from {params.get('watchdog_high_lookback_days')}일 고점")
    print(f"  VIX 트리거        : > {params.get('watchdog_vix_threshold')}")
    print(f"  디리스크 비율     : {params.get('watchdog_derisk_fraction') * 100:.0f}%")
    print(f"  재발동            : {'허용' if params.get('watchdog_refire') else '미허용'}")
    print(f"  재진입            : {params.get('watchdog_reentry')} (다음 정규 월초 점검 시)")

    print("\n[확정 가정 — 변경 시 명시적 합의 필요]")
    print("  - 무신호 = 무행동: 목표 비중이 전월과 동일하면 거래 없음")
    print("  - 개별 종목 고정 손절 없음: 섹터 순위 탈락·국면 필터 OFF 시에만 청산")
    print("  - SOXX는 11개 섹터와 동일 순위 풀에서 경쟁 (특별 로직 없음)")
    print("  - 늦은 상장 ETF(XLRE 2015, XLC 2018): 상장 전 NaN → 순위 풀 자동 제외")
    print("  - 워치독 재진입: 자동 복귀 없음, 다음 월초 국면 필터 재충족 시에만")

    print("\n" + "=" * 70)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="SENTINEL 백테스트 엔진",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--params",
        default="params.yaml",
        help="파라미터 파일 경로 (기본: params.yaml)",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="가격 캐시를 무시하고 yfinance에서 재다운로드",
    )
    args = parser.parse_args()

    print(DISCLAIMER)

    try:
        params = load_params(args.params)
    except FileNotFoundError as e:
        print(f"[오류] {e}", file=sys.stderr)
        sys.exit(1)
    except yaml.YAMLError as e:
        print(f"[오류] params.yaml 파싱 실패: {e}", file=sys.stderr)
        sys.exit(1)

    print_assumptions(params)

    print("\n[현재 상태] 단계 1 완료 — params 로드 및 가정 출력만 구현됨.")
    print("  데이터 수집, 신호 산출, 백테스트 실행은 이후 단계에서 구현 예정.\n")


if __name__ == "__main__":
    main()
