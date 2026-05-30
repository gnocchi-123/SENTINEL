"""신호 산출 모듈 — 모듈 1(국면 필터)·2(섹터 모멘텀)·3(포지션 크기).

핵심 계약:
  compute_target_weights(data, as_of_month_end, params) -> dict[ticker, weight]

  as_of_month_end(M-1월 마지막 거래일) 이후 데이터는 절대 참조하지 않는다.
  함수 진입 즉시 data를 as_of로 슬라이싱하고, assert로 경계를 검증한다.
"""

from __future__ import annotations

import pandas as pd
import numpy as np

from sentinel.data import build_universe


# ══════════════════════════════════════════════════════════════
# 내부 헬퍼
# ══════════════════════════════════════════════════════════════

def _raw_phase_signal(daily_slice: pd.DataFrame, params: dict) -> bool:
    """daily_slice 마지막 날 기준 원시 국면 신호를 반환한다 (True=주식 ON).

    조건 A: SPY 종가 > 200일 SMA  (buffer_pct > 0이면 SMA×(1+buffer) 기준)
    조건 B: SPY 12개월 수익률 > BIL 12개월 수익률 (월말 종가 기준)
    """
    spy_daily = daily_slice["SPY"].dropna()

    if len(spy_daily) < 200:
        return False  # 데이터 부족 → 방어(보수)

    # ── 조건 A ───────────────────────────────────────────────
    sma_200 = float(spy_daily.rolling(200).mean().iloc[-1])
    spy_close = float(spy_daily.iloc[-1])
    buffer = float(params.get("buffer_pct", 0.0))

    # buffer > 0: 중립 구간(SMA±buffer 사이)은 방어 처리(방어 우선)
    threshold = sma_200 * (1.0 + buffer)
    if not (spy_close > threshold):
        return False  # 단락: A 실패면 B 계산 불필요

    # ── 조건 B ───────────────────────────────────────────────
    monthly = daily_slice[["SPY", "BIL"]].resample("ME").last()

    if len(monthly) < 13:
        return False  # 12개월 수익률 계산 불가 → 방어(보수)

    spy_now = monthly["SPY"].iloc[-1]
    spy_ago = monthly["SPY"].iloc[-13]
    bil_now = monthly["BIL"].iloc[-1]
    bil_ago = monthly["BIL"].iloc[-13]

    if any(pd.isna(v) for v in (spy_now, spy_ago, bil_now, bil_ago)):
        return False  # BIL 미상장 등 데이터 공백 → 방어(보수)

    return float(spy_now / spy_ago) - 1.0 > float(bil_now / bil_ago) - 1.0


def _compute_phase_filter(
    daily_as_of: pd.DataFrame,
    monthly_as_of: pd.DataFrame,
    params: dict,
) -> bool:
    """confirmation_months를 반영한 국면 필터 결과를 반환한다.

    최근 confirmation_months개 월말 원시 신호가 모두 True여야 주식 ON.
    (하나라도 False → OFF; 방어 우선 정책)
    """
    n = int(params.get("confirmation_months", 1))

    if len(monthly_as_of) < n:
        return False

    for me in monthly_as_of.index[-n:]:
        if not _raw_phase_signal(daily_as_of.loc[:me], params):
            return False

    return True


def _compute_momentum_scores(
    monthly_as_of: pd.DataFrame,
    universe: list[str],
    params: dict,
) -> pd.Series:
    """유니버스 각 티커의 가중평균 모멘텀 점수를 반환한다.

    히스토리 부족 또는 상장 전 NaN이 있으면 해당 티커는 NaN (순위 풀 자동 제외).
    """
    lookbacks: list[int] = params.get("momentum_lookbacks_months", [3, 6, 12])
    weights: list[float] = [float(w) for w in params.get("momentum_weights", [1, 1, 1])]
    total_w = sum(weights)

    scores: dict[str, float] = {}

    for ticker in universe:
        if ticker not in monthly_as_of.columns:
            scores[ticker] = float("nan")
            continue

        prices = monthly_as_of[ticker]
        weighted_ret = 0.0
        ok = True

        for lb, w in zip(lookbacks, weights):
            if len(prices) < lb + 1:
                ok = False
                break
            p_now = prices.iloc[-1]
            p_ago = prices.iloc[-(lb + 1)]
            if pd.isna(p_now) or pd.isna(p_ago) or p_ago == 0:
                ok = False
                break
            weighted_ret += w * (float(p_now / p_ago) - 1.0)

        scores[ticker] = (weighted_ret / total_w) if ok else float("nan")

    return pd.Series(scores, dtype=float)


def _weights_equal(selected: list[str]) -> dict[str, float]:
    w = 1.0 / len(selected)
    return {t: w for t in selected}


def _weights_inverse_vol(
    selected: list[str],
    monthly_as_of: pd.DataFrame,
    params: dict,
) -> dict[str, float]:
    """선택 섹터를 변동성 역가중(inverse_vol_lookback_months 월별 수익률 σ)으로 배분한다."""
    lb = int(params.get("inverse_vol_lookback_months", 12))

    inv_vols: dict[str, float] = {}
    for ticker in selected:
        rets = monthly_as_of[ticker].iloc[-(lb + 1):].pct_change().dropna()
        vol = float(rets.std())
        inv_vols[ticker] = (1.0 / vol) if vol > 1e-12 else 0.0

    total = sum(inv_vols.values())
    if total < 1e-12:
        return _weights_equal(selected)  # 변동성 모두 0이면 균등 배분

    return {t: v / total for t, v in inv_vols.items()}


# ══════════════════════════════════════════════════════════════
# 공개 API
# ══════════════════════════════════════════════════════════════

def compute_target_weights(
    data: pd.DataFrame,
    as_of_month_end: pd.Timestamp,
    params: dict,
) -> dict[str, float]:
    """as_of_month_end 종가까지의 데이터로 목표 포트폴리오 비중을 산출한다.

    Args:
        data: 전체 일봉 수정종가 DataFrame (load_prices 반환값).
        as_of_month_end: 신호 기준일 — M-1월 마지막 거래일(또는 해당 월말 날짜).
                         이 날 이후 데이터는 이 함수 내부에서 참조하지 않는다.
        params: params.yaml 설정 딕셔너리.

    Returns:
        {ticker: weight} — 비중 합계 = 1.0.

    Raises:
        AssertionError: 슬라이싱 후 데이터에 as_of 초과 날짜가 발견된 경우.
    """
    # ── 룩어헤드 방지 ─────────────────────────────────────────
    daily_as_of = data.loc[:as_of_month_end].copy()

    if len(daily_as_of) > 0:
        actual_max = daily_as_of.index.max()
        assert actual_max <= pd.Timestamp(as_of_month_end), (
            f"룩어헤드 감지: 슬라이싱 후 최종일({actual_max}) > as_of({as_of_month_end})"
        )

    monthly_as_of = daily_as_of.resample("ME").last()
    defense = params["tickers"]["defense"]

    # ── 모듈 1: 국면 필터 ─────────────────────────────────────
    if not _compute_phase_filter(daily_as_of, monthly_as_of, params):
        return {defense: 1.0}

    # ── 모듈 2: 섹터 모멘텀 ──────────────────────────────────
    universe = build_universe(params)
    scores = _compute_momentum_scores(monthly_as_of, universe, params)

    top_n = int(params.get("top_n_sectors", 3))
    selected = list(scores.dropna().sort_values(ascending=False).head(top_n).index)

    if not selected:
        return {defense: 1.0}  # 유효 섹터 없으면 방어

    # ── 모듈 3: 포지션 크기 ──────────────────────────────────
    sizing = params.get("sizing", "equal")

    if sizing == "equal":
        return _weights_equal(selected)
    elif sizing == "inverse_vol":
        return _weights_inverse_vol(selected, monthly_as_of, params)
    else:
        raise ValueError(f"알 수 없는 sizing 값: {sizing!r}")


# ══════════════════════════════════════════════════════════════
# 샘플 출력 (단독 실행)
# ══════════════════════════════════════════════════════════════

def _print_sample(params: dict, data: pd.DataFrame, start: str, end: str) -> None:
    from sentinel.data import resample_to_month_end

    monthly = resample_to_month_end(data)
    period = monthly.index[(monthly.index >= start) & (monthly.index <= end)]
    defense = params["tickers"]["defense"]

    print(f"\n{'=' * 80}")
    print(f"  샘플 월별 목표 포트폴리오  ({start[:7]} ~ {end[:7]})")
    print(f"{'=' * 80}")
    print(f"  {'날짜':<12}  {'국면':<5}  포트폴리오")
    print(f"  {'-' * 68}")

    for as_of in period:
        weights = compute_target_weights(data, as_of, params)
        is_equity = not (len(weights) == 1 and defense in weights)
        phase = "ON " if is_equity else "OFF"
        portfolio = "  ".join(f"{t}({w:.1%})" for t, w in weights.items())
        print(f"  {str(as_of.date()):<12}  {phase}   {portfolio}")

    print(f"{'=' * 80}\n")


if __name__ == "__main__":
    import sys
    import yaml
    from pathlib import Path
    from sentinel.data import load_prices

    params_path = Path("params.yaml")
    if not params_path.exists():
        print("[오류] params.yaml 없음", file=sys.stderr)
        sys.exit(1)

    with params_path.open(encoding="utf-8") as f:
        params = yaml.safe_load(f)

    data = load_prices(params)
    _print_sample(params, data, "2007-01-01", "2009-12-31")
