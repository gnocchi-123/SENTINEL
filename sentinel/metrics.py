"""성과 지표 산출 모듈.

평가 우선순위: MDD·하락장 구간 성과 → 샤프/소르티노/칼마 → CAGR.
과최적화 위험과 "과거 ≠ 미래"를 항상 결과와 함께 전달한다.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


# ══════════════════════════════════════════════════════════════
# 하락장 구간 기본값
# ══════════════════════════════════════════════════════════════

BEAR_MARKETS: list[tuple[str, str, str, str]] = [
    # (레이블, 시작, 종료, 유형)
    ("닷컴 버블",   "2000-03-24", "2002-10-09", "느린하락"),
    ("GFC",         "2007-10-09", "2009-03-09", "느린하락"),
    ("코로나",      "2020-02-19", "2020-03-23", "V자"),
    ("2022 금리",   "2022-01-03", "2022-10-12", "느린하락"),
]


# ══════════════════════════════════════════════════════════════
# 헬퍼
# ══════════════════════════════════════════════════════════════

def prepare_series(
    equity_curve: pd.Series,
    daily_index: pd.DatetimeIndex,
) -> pd.Series:
    """일봉 인덱스 전체로 전진 채움한 자산곡선을 반환한다.

    equity_curve가 점검일(월초)만 있는 구간도 모든 거래일로 채워
    일별 수익률 계산이 올바르게 동작하도록 한다.
    """
    full_idx = daily_index[
        (daily_index >= equity_curve.index[0])
        & (daily_index <= equity_curve.index[-1])
    ]
    return equity_curve.reindex(full_idx).ffill()


def _safe_div(a: float, b: float) -> float:
    return a / b if (b and not np.isnan(b) and abs(b) > 1e-12) else float("nan")


# ══════════════════════════════════════════════════════════════
# 공개 API
# ══════════════════════════════════════════════════════════════

def compute_cagr(portfolio_values: pd.Series) -> float:
    """연복리 수익률(CAGR)을 계산한다. 캘린더 연수 기준."""
    years = (portfolio_values.index[-1] - portfolio_values.index[0]).days / 365.25
    if years <= 0 or portfolio_values.iloc[0] <= 0:
        return float("nan")
    return float((portfolio_values.iloc[-1] / portfolio_values.iloc[0]) ** (1.0 / years) - 1.0)


def compute_drawdown_series(portfolio_values: pd.Series) -> pd.Series:
    """일별 수중(underwater) 낙폭 계열을 반환한다 (0 이하 값)."""
    rolling_max = portfolio_values.cummax()
    return (portfolio_values - rolling_max) / rolling_max


def compute_max_drawdown(portfolio_values: pd.Series) -> float:
    """최대낙폭(MDD)을 반환한다 (음수 소수점, 예: -0.35 = -35%)."""
    return float(compute_drawdown_series(portfolio_values).min())


def compute_max_drawdown_details(portfolio_values: pd.Series) -> dict:
    """MDD 고점·저점·회복일·기간을 반환한다."""
    dd = compute_drawdown_series(portfolio_values)
    mdd_val = float(dd.min())

    trough_date = dd.idxmin()
    peak_date = portfolio_values.loc[:trough_date].idxmax()

    # 저점 이후 고점 가치 회복 시점
    peak_value = float(portfolio_values.loc[peak_date])
    after_trough = portfolio_values.loc[trough_date:].iloc[1:]  # 저점 당일 제외
    recovered = after_trough[after_trough >= peak_value * (1.0 - 1e-6)]
    recovery_date: pd.Timestamp | None = recovered.index[0] if len(recovered) > 0 else None

    return {
        "mdd":                        mdd_val,
        "peak_date":                  peak_date,
        "trough_date":                trough_date,
        "recovery_date":              recovery_date,
        "days_to_trough":             int((trough_date - peak_date).days),
        "days_to_recovery":           int((recovery_date - trough_date).days) if recovery_date else None,
    }


def compute_annual_volatility(
    portfolio_values: pd.Series,
    periods_per_year: int = 252,
) -> float:
    """연환산 변동성(일별 수익률 표준편차 × √252)을 반환한다."""
    returns = portfolio_values.pct_change().dropna()
    return float(returns.std() * np.sqrt(periods_per_year))


def compute_sharpe(
    portfolio_values: pd.Series,
    risk_free_annual: float = 0.0,
    periods_per_year: int = 252,
) -> float:
    """샤프 비율 (연환산, rf=0% 기본)."""
    returns = portfolio_values.pct_change().dropna()
    rf_daily = (1.0 + risk_free_annual) ** (1.0 / periods_per_year) - 1.0
    excess = returns - rf_daily
    std = float(excess.std())
    return _safe_div(float(excess.mean()) * np.sqrt(periods_per_year), std)


def compute_sortino(
    portfolio_values: pd.Series,
    risk_free_annual: float = 0.0,
    periods_per_year: int = 252,
) -> float:
    """소르티노 비율 (하방 변동성 기준)."""
    returns = portfolio_values.pct_change().dropna()
    rf_daily = (1.0 + risk_free_annual) ** (1.0 / periods_per_year) - 1.0
    excess = returns - rf_daily
    downside = excess[excess < 0]
    if len(downside) == 0:
        return float("nan")
    downside_std = float(np.sqrt((downside ** 2).mean()))
    return _safe_div(float(excess.mean()) * np.sqrt(periods_per_year), downside_std)


def compute_calmar(portfolio_values: pd.Series) -> float:
    """칼마 비율 = CAGR / |MDD|."""
    return _safe_div(compute_cagr(portfolio_values), abs(compute_max_drawdown(portfolio_values)))


def compute_drawdown_periods(
    portfolio_values: pd.Series,
    benchmark_values: pd.Series,
    bear_markets: list[tuple[str, str, str, str]] | None = None,
) -> pd.DataFrame:
    """하락장 구간별 SENTINEL vs 벤치마크 수익률·MDD 비교 DataFrame을 반환한다.

    bear_markets가 None이면 BEAR_MARKETS 기본값을 사용한다.

    Args:
        portfolio_values: SENTINEL 일별 가치 Series.
        benchmark_values: 벤치마크 일별 가치 Series (동일 기준점 정규화).
        bear_markets: [(레이블, 시작, 종료, 유형)] 목록.

    Returns:
        구간별 비교 DataFrame.
    """
    if bear_markets is None:
        bear_markets = BEAR_MARKETS

    rows = []
    for label, start, end, htype in bear_markets:
        def _ret(pv: pd.Series) -> float:
            sub = pv.loc[start:end].dropna()
            return float(sub.iloc[-1] / sub.iloc[0] - 1.0) if len(sub) >= 2 else float("nan")

        def _mdd(pv: pd.Series) -> float:
            sub = pv.loc[start:end].dropna()
            return compute_max_drawdown(sub) if len(sub) >= 2 else float("nan")

        s_ret = _ret(portfolio_values)
        b_ret = _ret(benchmark_values)
        s_mdd = _mdd(portfolio_values)
        b_mdd = _mdd(benchmark_values)

        rows.append({
            "구간":           label,
            "유형":           htype,
            "시작":           start,
            "종료":           end,
            "SENTINEL_수익":  s_ret,
            "SPY_수익":       b_ret,
            "수익차이":       (s_ret - b_ret) if not (np.isnan(s_ret) or np.isnan(b_ret)) else float("nan"),
            "SENTINEL_MDD":   s_mdd,
            "SPY_MDD":        b_mdd,
            "MDD_차이":       (s_mdd - b_mdd) if not (np.isnan(s_mdd) or np.isnan(b_mdd)) else float("nan"),
        })

    return pd.DataFrame(rows)


def compute_summary(
    portfolio_values: pd.Series,
    benchmark_values: pd.Series,
    params: dict,
    log_df: pd.DataFrame | None = None,
) -> dict:
    """SENTINEL vs 벤치마크 전체 성과 요약 딕셔너리를 반환한다.

    Args:
        portfolio_values: SENTINEL 일별 가치 Series (ffill 완료).
        benchmark_values: 벤치마크 일별 가치 Series (동일 기간 정규화).
        params: params.yaml 설정 딕셔너리.
        log_df: run_backtest()의 log_df (거래 통계용, optional).

    Returns:
        지표명 → 값 딕셔너리. SENTINEL 지표는 prefix 없음, 벤치마크는 "bh_" prefix.
    """
    pv = portfolio_values
    bv = benchmark_values

    # 벤치마크를 SENTINEL 기간에 정렬·정규화
    bv_sub = bv.reindex(pv.index).ffill()
    first_valid = bv_sub.first_valid_index()
    if first_valid is None:
        bv_sub = pd.Series(dtype=float)
    else:
        bv_sub = bv_sub.loc[first_valid:] / bv_sub.loc[first_valid]

    # ── SENTINEL ──────────────────────────────────────────────
    mdd_det = compute_max_drawdown_details(pv)

    result: dict = {
        # 1. MDD
        "mdd":                        mdd_det["mdd"],
        "mdd_peak_date":              mdd_det["peak_date"],
        "mdd_trough_date":            mdd_det["trough_date"],
        "mdd_recovery_date":          mdd_det["recovery_date"],
        "mdd_days_to_trough":         mdd_det["days_to_trough"],
        "mdd_days_to_recovery":       mdd_det["days_to_recovery"],

        # 2. 위험조정수익
        "sharpe":                     compute_sharpe(pv),
        "sortino":                    compute_sortino(pv),
        "calmar":                     compute_calmar(pv),
        "annual_vol":                 compute_annual_volatility(pv),

        # 3. 수익
        "cagr":                       compute_cagr(pv),
        "total_return":               float(pv.iloc[-1] / pv.iloc[0] - 1.0),
    }

    # ── 벤치마크 ──────────────────────────────────────────────
    if len(bv_sub) >= 2:
        bh_mdd_det = compute_max_drawdown_details(bv_sub)
        result.update({
            "bh_mdd":             bh_mdd_det["mdd"],
            "bh_mdd_peak_date":   bh_mdd_det["peak_date"],
            "bh_mdd_trough_date": bh_mdd_det["trough_date"],
            "bh_mdd_days_to_trough": bh_mdd_det["days_to_trough"],
            "bh_sharpe":          compute_sharpe(bv_sub),
            "bh_sortino":         compute_sortino(bv_sub),
            "bh_calmar":          compute_calmar(bv_sub),
            "bh_annual_vol":      compute_annual_volatility(bv_sub),
            "bh_cagr":            compute_cagr(bv_sub),
            "bh_total_return":    float(bv_sub.iloc[-1] / bv_sub.iloc[0] - 1.0),
        })

    # ── 거래 통계 ─────────────────────────────────────────────
    if log_df is not None and not log_df.empty:
        mon = log_df[log_df["source"] == "monthly"] if "source" in log_df.columns else log_df
        if not mon.empty:
            traded = mon[mon["traded"] == True]
            n_total = len(mon)
            n_def = len(mon[mon["phase"] == "OFF"])
            result.update({
                "n_trades":       int(mon["traded"].sum()),
                "avg_turnover":   float(traded["turnover"].mean()) if len(traded) else 0.0,
                "defense_ratio":  n_def / n_total if n_total else 0.0,
                "n_months":       n_total,
            })

    return result
