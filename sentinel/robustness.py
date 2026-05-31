"""견고성 검증 — 파라미터 스윕, 워치독 유형별 비교, 발동 후 성과 분석."""

from __future__ import annotations

import copy

import numpy as np
import pandas as pd

from sentinel.engine import run_backtest
from sentinel.metrics import (
    BEAR_MARKETS,
    compute_drawdown_periods,
    compute_summary,
    prepare_series,
)


# ══════════════════════════════════════════════════════════════
# 스윕 구성 정의
# ══════════════════════════════════════════════════════════════

SWEEP_CONFIGS: list[dict] = [
    # ── A: top_n × sizing ─────────────────────────────────────
    {"group": "A", "label": "BASE n=3 equal  wd=OFF", "overrides": {}},
    {"group": "A", "label": "     n=2 equal  wd=OFF", "overrides": {"top_n_sectors": 2}},
    {"group": "A", "label": "     n=4 equal  wd=OFF", "overrides": {"top_n_sectors": 4}},
    {"group": "A", "label": "     n=3 invvol wd=OFF", "overrides": {"sizing": "inverse_vol"}},
    {"group": "A", "label": "     n=2 invvol wd=OFF", "overrides": {"top_n_sectors": 2, "sizing": "inverse_vol"}},
    {"group": "A", "label": "     n=4 invvol wd=OFF", "overrides": {"top_n_sectors": 4, "sizing": "inverse_vol"}},
    # ── B: 휩쏘 완화 토글 ──────────────────────────────────────
    {"group": "B", "label": "+buffer=4%    wd=OFF",  "overrides": {"buffer_pct": 0.04}},
    {"group": "B", "label": "+confirm=2m   wd=OFF",  "overrides": {"confirmation_months": 2}},
    {"group": "B", "label": "+partial=50%  wd=OFF",  "overrides": {"partial_exit_fraction": 0.5}},
    {"group": "B", "label": "+all toggles  wd=OFF",  "overrides": {
        "buffer_pct": 0.04, "confirmation_months": 2, "partial_exit_fraction": 0.5,
    }},
    # ── C: 워치독 ─────────────────────────────────────────────
    {"group": "C", "label": "BASE n=3 equal  wd=ON ", "overrides": {"watchdog_enabled": True}},
    {"group": "C", "label": "+all toggles  wd=ON ",   "overrides": {
        "buffer_pct": 0.04, "confirmation_months": 2,
        "partial_exit_fraction": 0.5, "watchdog_enabled": True,
    }},
]

_GROUP_HEADERS = {
    "A": "── A. top_n × sizing",
    "B": "── B. 휩쏘 완화 토글",
    "C": "── C. 워치독 on/off",
}


# ══════════════════════════════════════════════════════════════
# 스윕 실행
# ══════════════════════════════════════════════════════════════

def run_sweep(
    daily: pd.DataFrame,
    monthly: pd.DataFrame,
    params_base: dict,
    configs: list[dict] | None = None,
    verbose: bool = True,
) -> list[dict]:
    """스윕 구성 목록을 순서대로 실행하고 지표 딕셔너리 목록을 반환한다.

    Args:
        daily: 일봉 수정종가 DataFrame.
        monthly: 월말 리샘플 DataFrame.
        params_base: 기준 파라미터 딕셔너리 (params.yaml 로드값).
        configs: 스윕 구성 목록. None이면 SWEEP_CONFIGS 사용.
        verbose: 진행 상황 출력 여부.

    Returns:
        각 구성의 결과 딕셔너리 목록.
    """
    if configs is None:
        configs = SWEEP_CONFIGS

    spy_raw = daily["SPY"].dropna()
    results: list[dict] = []

    for i, cfg in enumerate(configs):
        label = cfg["label"]
        if verbose:
            print(f"  [{i+1:>2}/{len(configs)}] {label.strip()}", end="", flush=True)

        params = copy.deepcopy(params_base)
        params.update(cfg.get("overrides", {}))

        try:
            equity, log_df = run_backtest(daily, monthly, params)
            eq_filled = prepare_series(equity, daily.index)
            spy_start = eq_filled.index[0]
            spy_sub = spy_raw[spy_raw.index >= spy_start]
            benchmark = spy_sub / spy_sub.iloc[0]
            summary = compute_summary(eq_filled, benchmark, params, log_df)
        except Exception as e:
            if verbose:
                print(f"  ✗ {e}")
            results.append({"group": cfg.get("group", "?"), "label": label, "error": str(e)})
            continue

        row: dict = {
            "group":        cfg.get("group", "?"),
            "label":        label,
            "top_n":        params.get("top_n_sectors", 3),
            "sizing":       params.get("sizing", "equal"),
            "buffer":       params.get("buffer_pct", 0.0),
            "confirm":      params.get("confirmation_months", 1),
            "partial":      params.get("partial_exit_fraction", 1.0),
            "watchdog":     params.get("watchdog_enabled", False),
            "mdd":          summary.get("mdd"),
            "sharpe":       summary.get("sharpe"),
            "cagr":         summary.get("cagr"),
            "avg_turnover": summary.get("avg_turnover"),
            "n_trades":     summary.get("n_trades"),
            "bh_mdd":       summary.get("bh_mdd"),
            "bh_sharpe":    summary.get("bh_sharpe"),
            "bh_cagr":      summary.get("bh_cagr"),
        }
        results.append(row)

        if verbose:
            mdd_s   = f"{row['mdd']:.1%}"   if row.get("mdd")   is not None else "N/A"
            shr_s   = f"{row['sharpe']:.2f}" if row.get("sharpe") is not None else "N/A"
            cag_s   = f"{row['cagr']:.1%}"   if row.get("cagr")   is not None else "N/A"
            print(f"  MDD={mdd_s}  Sharpe={shr_s}  CAGR={cag_s}")

    return results


# ══════════════════════════════════════════════════════════════
# 스윕 결과 출력
# ══════════════════════════════════════════════════════════════

def _p(v: float | None, fmt: str = "+.1%") -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "N/A"
    return format(v, fmt)


def print_sweep_table(results: list[dict]) -> None:
    """스윕 결과를 그룹별로 정렬하여 한 표에 출력한다."""
    valid = [r for r in results if "error" not in r]
    if not valid:
        print("  [오류] 스윕 결과 없음")
        return

    # SPY 기준값 (모든 구성의 기준선은 동일)
    spy_mdd    = valid[0].get("bh_mdd",    float("nan"))
    spy_sharpe = valid[0].get("bh_sharpe", float("nan"))
    spy_cagr   = valid[0].get("bh_cagr",   float("nan"))

    W = 92
    print("\n" + "=" * W)
    print("  견고성 스윕 — 파라미터 조합별 성과")
    print(f"  ★ 기준선 SPY B&H:  MDD={spy_mdd:.1%}  Sharpe={spy_sharpe:.2f}  CAGR={spy_cagr:.1%}")
    print("=" * W)
    print(f"  {'구성':<29} {'N':>2}  {'siz':<6} {'buf':>4} {'con':>3} {'prt':>3} {'wd':>3}  "
          f"{'MDD':>7}  {'Sharpe':>6}  {'CAGR':>6}  {'회전율':>6}  판정")
    print("  " + "─" * (W - 2))

    current_group: str | None = None
    beats_spy = 0

    for row in valid:
        grp = row.get("group", "?")
        if grp != current_group:
            current_group = grp
            print(f"\n  {_GROUP_HEADERS.get(grp, grp)}")

        n      = row.get("top_n", 3)
        siz    = "eq" if row.get("sizing") == "equal" else "iv"
        buf_s  = f"{row['buffer']*100:.0f}%" if row.get("buffer", 0) > 0 else "  -"
        con_s  = str(row.get("confirm", 1))
        prt_s  = f"{row['partial']*100:.0f}%" if row.get("partial", 1.0) < 1.0 else "100"
        wd_s   = "ON " if row.get("watchdog") else "OFF"

        mdd    = row.get("mdd")
        sharpe = row.get("sharpe")
        cagr   = row.get("cagr")
        turn   = row.get("avg_turnover")

        mdd_s  = _p(mdd)
        shr_s  = _p(sharpe, ".2f")
        cag_s  = _p(cagr)
        turn_s = _p(turn, ".1%") if turn else "N/A"

        # 견고성 판정: mdd는 음수 — 더 크면(덜 빠지면) SPY보다 MDD 우위
        if mdd is not None and not np.isnan(mdd) and not np.isnan(spy_mdd):
            if mdd > spy_mdd:
                flag = "✓ MDD↓"
                beats_spy += 1
            else:
                flag = "✗ MDD↑"
        else:
            flag = "  N/A"

        star = "★" if "BASE" in row["label"] and row.get("group") == "A" else " "
        print(f"  {star}{row['label']:<28} {n:>2}  {siz:<6} {buf_s:>4} {con_s:>3} "
              f"{prt_s:>3} {wd_s:>3}  "
              f"{mdd_s:>7}  {shr_s:>6}  {cag_s:>6}  {turn_s:>6}  {flag}")

    # SPY B&H 참고행
    print(f"\n  {'─'*(W-2)}")
    print(f"  {'[SPY 매수보유]':<29} {'—':>2}  {'—':<6} {'—':>4} {'—':>3} "
          f"{'—':>3} {'—':>3}  "
          f"{_p(spy_mdd):>7}  {_p(spy_sharpe, '.2f'):>6}  {_p(spy_cagr):>6}  "
          f"{'—':>6}  기준선")
    print("=" * W)

    # 견고성 결론
    n_total = len(valid)
    print(f"\n  견고성 판정: {beats_spy}/{n_total}개 구성에서 SENTINEL MDD < SPY MDD")
    if beats_spy == n_total:
        print("  ✓ 모든 파라미터 조합에서 MDD 우위 유지 → 1순위 목표 견고성 확인")
    else:
        fails = [r["label"].strip() for r in valid
                 if r.get("mdd") is None or np.isnan(r["mdd"])
                 or r["mdd"] <= spy_mdd]
        print(f"  ✗ MDD 우위 실패: {', '.join(fails)}")
    print()


# ══════════════════════════════════════════════════════════════
# 워치독 하락장 유형별 비교
# ══════════════════════════════════════════════════════════════

def compare_watchdog_by_bear_type(
    daily: pd.DataFrame,
    monthly: pd.DataFrame,
    params_base: dict,
    verbose: bool = True,
) -> None:
    """워치독 ON/OFF를 느린하락 vs V자 유형별로 비교하고 발동 후 60거래일 성과를 출력한다."""

    params_off = copy.deepcopy(params_base)
    params_off["watchdog_enabled"] = False

    params_on = copy.deepcopy(params_base)
    params_on["watchdog_enabled"] = True

    if verbose:
        print("  워치독 OFF 실행...", end="", flush=True)
    equity_off, _ = run_backtest(daily, monthly, params_off)
    eq_off = prepare_series(equity_off, daily.index)
    if verbose:
        print(" 완료")

    if verbose:
        print("  워치독 ON  실행...", end="", flush=True)
    equity_on, log_on = run_backtest(daily, monthly, params_on)
    eq_on = prepare_series(equity_on, daily.index)
    if verbose:
        print(" 완료")

    spy_raw = daily["SPY"].dropna()
    spy_start = eq_off.index[0]
    spy_bh = spy_raw[spy_raw.index >= spy_start]
    spy_bh = spy_bh / spy_bh.iloc[0]

    bear_off = compute_drawdown_periods(eq_off, spy_bh)
    bear_on  = compute_drawdown_periods(eq_on,  spy_bh)

    # ── 유형별 비교표 ─────────────────────────────────────────
    W = 88
    print(f"\n{'=' * W}")
    print("  워치독 ON vs OFF — 하락장 유형별 MDD·수익 비교")
    print("=" * W)
    hdr = (f"  {'구간':<14} {'유형':<8} {'OFF수익':>8} {'ON수익':>8} {'수익Δ':>7}  "
           f"{'OFF_MDD':>8} {'ON_MDD':>8} {'MDD_Δ':>7}  판정")
    print(hdr)
    print("  " + "─" * (W - 2))

    for i in range(len(bear_off)):
        off_row = bear_off.iloc[i]
        on_row  = bear_on.iloc[i]

        label  = off_row["구간"]
        htype  = off_row["유형"]
        period = f"  ({off_row['시작']}~{off_row['종료']})"

        s_off = off_row["SENTINEL_수익"]
        s_on  = on_row["SENTINEL_수익"]
        m_off = off_row["SENTINEL_MDD"]
        m_on  = on_row["SENTINEL_MDD"]

        def _v(a, b):
            return (a - b) if not (np.isnan(a) or np.isnan(b)) else float("nan")

        diff_r = _v(s_on, s_off)
        diff_m = _v(m_on, m_off)   # 음수끼리: 더 크면(덜 빠지면) ON이 개선

        if htype == "느린하락":
            if not np.isnan(diff_m) and diff_m > 0:
                verdict = "✓ WD MDD↓"
            elif not np.isnan(diff_m) and diff_m < -0.005:
                verdict = "✗ WD 역효과"
            else:
                verdict = "— 중립"
        else:  # V자
            if not np.isnan(diff_r) and diff_r < -0.01:
                verdict = "★ 휩쏘 손해"
            elif not np.isnan(diff_r) and diff_r > 0.01:
                verdict = "✓ WD 효과"
            else:
                verdict = "— 중립"

        print(f"  {label:<14} {htype:<8} {_p(s_off):>8} {_p(s_on):>8} {_p(diff_r):>7}  "
              f"{_p(m_off):>8} {_p(m_on):>8} {_p(diff_m):>7}  {verdict}")
        print(period)

    print("=" * W)

    # ── 워치독 발동 후 60거래일 분석 ─────────────────────────
    _print_postfire_analysis(daily, log_on, eq_off, eq_on)


def _print_postfire_analysis(
    daily: pd.DataFrame,
    log_on: pd.DataFrame,
    eq_off: pd.Series,
    eq_on: pd.Series,
) -> None:
    """워치독 발동 후 60거래일 성과를 출력한다 (휩쏘 여부 판정)."""
    if "source" not in log_on.columns:
        return
    wd_events = log_on[log_on["source"] == "watchdog"]
    if wd_events.empty:
        print("  [워치독 발동 없음]\n")
        return

    spy = daily["SPY"].dropna()

    W = 88
    print(f"\n{'=' * W}")
    print("  워치독 발동 후 60거래일 성과 — 휩쏘 판정")
    print(f"  ★ V자 휩쏘: SPY 60일 내 +5% 이상 반등 → 워치독이 바닥 매도였을 가능성")
    print(f"  ✓ 추세 하락: SPY 60일 내 -5% 이하   → 워치독이 방어에 효과적")
    print("=" * W)
    print(f"  {'발동일':<12} {'발동 전 주식':<20} "
          f"{'SPY_60d':>8} {'WD_ON_60d':>10} {'WD_OFF_60d':>11}  판정")
    print("  " + "─" * (W - 2))

    for fire_date, wd_row in wd_events.iterrows():
        future = daily.index[daily.index > fire_date]
        if len(future) < 60:
            continue
        end_date = future[59]

        def _ret(s: pd.Series) -> float:
            sub = s.loc[fire_date:end_date]
            return float(sub.iloc[-1] / sub.iloc[0] - 1.0) if len(sub) >= 2 else float("nan")

        spy_r = _ret(spy)
        on_r  = _ret(eq_on)
        off_r = _ret(eq_off)

        # 발동 직전 보유 주식(AGG 제외)
        pre_equity = [t for t in wd_row["holdings"] if t != "AGG"][:3]
        pre_str    = "/".join(pre_equity)[:18]

        # 판정
        if not np.isnan(spy_r):
            if spy_r > 0.05:
                verdict = "★ V자 휩쏘"
            elif spy_r < -0.05:
                verdict = "✓ 추세 하락"
            else:
                verdict = "— 중립"
        else:
            verdict = "N/A"

        print(f"  {str(fire_date.date()):<12} {pre_str:<20} "
              f"{_p(spy_r):>8} {_p(on_r):>10} {_p(off_r):>11}  {verdict}")

    print(f"\n  WD_ON vs WD_OFF 60일 수익 차이: "
          f"ON이 낮으면 워치독이 그 기간 동안 성과를 낮춘 것.")
    print("=" * W + "\n")
