"""결과 시각화·보고 모듈.

백테스트 수행 시 반드시 과최적화 경고와 면책 문구를 함께 출력한다.
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import pandas as pd

from sentinel.metrics import (
    BEAR_MARKETS,
    compute_drawdown_series,
    compute_drawdown_periods,
)


DISCLAIMER = (
    "\n[주의] 이 결과는 과거 데이터 기반 역사적 시뮬레이션입니다.\n"
    "과최적화(curve fitting) 위험이 있으며, 과거 성과는 미래 수익을 보장하지 않습니다.\n"
    "투자 자문이 아닌 방법론 검증 목적으로만 사용하십시오.\n"
)

_W = 72  # 출력 폭


def _fmt_pct(v, decimals: int = 1) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "N/A"
    return f"{v * 100:+.{decimals}f}%"


def _fmt_x(v, decimals: int = 2) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "N/A"
    return f"{v:.{decimals}f}"


def _fmt_date(v) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "미회복"
    try:
        return str(pd.Timestamp(v).date())
    except Exception:
        return str(v)


def _row(label: str, sentinel_val: str, bh_val: str, indent: int = 0) -> None:
    pad = "  " * indent
    print(f"  {pad}{label:<34} {sentinel_val:>12}  {bh_val:>12}")


def _section(title: str) -> None:
    print(f"\n  ── {title}")


# ══════════════════════════════════════════════════════════════
# 메인 리포트 출력
# ══════════════════════════════════════════════════════════════

def print_report(
    summary: dict,
    bear_df: pd.DataFrame,
    params: dict,
) -> None:
    """성과 요약 전체를 콘솔에 출력한다. 항상 DISCLAIMER를 포함한다."""
    print(DISCLAIMER)

    wd_label = "ON" if params.get("watchdog_enabled") else "OFF"
    print("=" * _W)
    print(f"  SENTINEL vs SPY 매수보유 — 성과 요약  [워치독: {wd_label}]")
    print("=" * _W)
    print(f"  {'지표':<34} {'SENTINEL':>12}  {'SPY B&H':>12}")
    print("  " + "-" * (_W - 2))

    # ── 1. MDD (최우선) ───────────────────────────────────────
    _section("낙폭 — 최우선 평가 지표")
    _row("최대낙폭 (MDD)",
         _fmt_pct(summary.get("mdd")),
         _fmt_pct(summary.get("bh_mdd")))

    peak_s  = _fmt_date(summary.get("mdd_peak_date"))
    trough_s = _fmt_date(summary.get("mdd_trough_date"))
    bh_peak_s = _fmt_date(summary.get("bh_mdd_peak_date"))
    bh_trough_s = _fmt_date(summary.get("bh_mdd_trough_date"))
    _row("  고점 → 저점",
         f"{peak_s}→{trough_s}",
         f"{bh_peak_s}→{bh_trough_s}")

    dur_s  = f"{summary['mdd_days_to_trough']}일" if summary.get("mdd_days_to_trough") else "N/A"
    bh_dur = f"{summary['bh_mdd_days_to_trough']}일" if summary.get("bh_mdd_days_to_trough") else "N/A"
    _row("  고점→저점 기간", dur_s, bh_dur)

    recov_s = _fmt_date(summary.get("mdd_recovery_date"))
    recov_days = summary.get("mdd_days_to_recovery")
    recov_str = f"{recov_s} ({recov_days}일)" if recov_days else recov_s
    _row("  회복일 (저점 기준)", recov_str, "")

    # ── 2. 위험조정수익 ───────────────────────────────────────
    _section("위험조정수익")
    _row("Sharpe  (연환산, rf=0%)",
         _fmt_x(summary.get("sharpe")),
         _fmt_x(summary.get("bh_sharpe")))
    _row("Sortino (하방변동성 기준)",
         _fmt_x(summary.get("sortino")),
         _fmt_x(summary.get("bh_sortino")))
    _row("Calmar  (CAGR / |MDD|)",
         _fmt_x(summary.get("calmar")),
         _fmt_x(summary.get("bh_calmar")))
    _row("연변동성",
         _fmt_pct(summary.get("annual_vol")),
         _fmt_pct(summary.get("bh_annual_vol")))

    # ── 3. 수익 (참고용) ──────────────────────────────────────
    _section("수익 — 참고용 (후순위)")
    _row("CAGR",
         _fmt_pct(summary.get("cagr")),
         _fmt_pct(summary.get("bh_cagr")))
    _row("누적수익",
         _fmt_pct(summary.get("total_return")),
         _fmt_pct(summary.get("bh_total_return")))

    # ── 4. 운용 통계 ──────────────────────────────────────────
    _section("운용 통계")
    n_tr = summary.get("n_trades")
    _row("총 매매 횟수", str(n_tr) if n_tr is not None else "N/A", "—")
    avg_to = summary.get("avg_turnover")
    _row("평균 회전율 (매매 달)",
         f"{avg_to * 100:.1f}%" if avg_to is not None else "N/A", "—")
    def_r = summary.get("defense_ratio")
    _row("방어 모드 비율",
         f"{def_r * 100:.1f}%" if def_r is not None else "N/A", "—")

    print("\n" + "=" * _W)

    # ── 5. 하락장 구간 비교 ───────────────────────────────────
    if bear_df is not None and not bear_df.empty:
        _print_bear_table(bear_df)


def _print_bear_table(bear_df: pd.DataFrame) -> None:
    """하락장 구간별 비교 테이블을 출력한다."""
    print(f"\n  {'─'*(_W-2)}")
    print("  하락장 구간별 성과 (SENTINEL vs SPY 매수보유)")
    print(f"  {'─'*(_W-2)}")
    print(f"  {'구간':<14} {'유형':<8} {'SENT수익':>8} {'SPY수익':>8} "
          f"{'수익차':>7} {'SENT_MDD':>9} {'SPY_MDD':>8} {'MDD차':>7}")
    print("  " + "-" * (_W - 2))

    for _, row in bear_df.iterrows():
        s_r = _fmt_pct(row["SENTINEL_수익"])
        b_r = _fmt_pct(row["SPY_수익"])
        diff_r = _fmt_pct(row["수익차이"])
        s_m = _fmt_pct(row["SENTINEL_MDD"])
        b_m = _fmt_pct(row["SPY_MDD"])
        diff_m = _fmt_pct(row["MDD_차이"])
        label = row["구간"]
        htype = row["유형"]
        period_str = f"  ({row['시작']}~{row['종료']})"

        print(f"  {label:<14} {htype:<8} {s_r:>8} {b_r:>8} "
              f"{diff_r:>7} {s_m:>9} {b_m:>8} {diff_m:>7}")
        print(f"  {period_str}")

    print(f"\n  ※ 닷컴·GFC 구간의 SENTINEL 현금 보유는 BIL 미상장으로 인한 "
          f"데이터 한계 (index_splicing=false)이며 전략 의도와 다릅니다.")
    print(f"  {'─'*(_W-2)}\n")


# ══════════════════════════════════════════════════════════════
# CSV 저장
# ══════════════════════════════════════════════════════════════

def save_validation_csv(
    summary: dict,
    bear_df: pd.DataFrame,
    output_path: str = "validation_results.csv",
    params: dict | None = None,
) -> None:
    """성과 요약과 하락장 구간 비교를 CSV로 저장한다."""
    rows: list[dict] = []

    # 섹션 A: 요약 지표
    def _add(key: str, label: str, sentinel_val, bh_val=None) -> None:
        rows.append({
            "section": "summary",
            "key": key,
            "label": label,
            "sentinel": sentinel_val if sentinel_val is not None else "",
            "spy_bh": bh_val if bh_val is not None else "",
        })

    _add("mdd",           "MDD",           summary.get("mdd"),           summary.get("bh_mdd"))
    _add("mdd_peak",      "MDD 고점",      _fmt_date(summary.get("mdd_peak_date")))
    _add("mdd_trough",    "MDD 저점",      _fmt_date(summary.get("mdd_trough_date")))
    _add("mdd_recovery",  "MDD 회복일",    _fmt_date(summary.get("mdd_recovery_date")))
    _add("mdd_days",      "고점→저점 일수", summary.get("mdd_days_to_trough"),
                                           summary.get("bh_mdd_days_to_trough"))
    _add("sharpe",        "Sharpe",        summary.get("sharpe"),         summary.get("bh_sharpe"))
    _add("sortino",       "Sortino",       summary.get("sortino"),        summary.get("bh_sortino"))
    _add("calmar",        "Calmar",        summary.get("calmar"),         summary.get("bh_calmar"))
    _add("annual_vol",    "연변동성",      summary.get("annual_vol"),     summary.get("bh_annual_vol"))
    _add("cagr",          "CAGR",          summary.get("cagr"),           summary.get("bh_cagr"))
    _add("total_return",  "누적수익",      summary.get("total_return"),   summary.get("bh_total_return"))
    _add("n_trades",      "총 매매 횟수",  summary.get("n_trades"))
    _add("avg_turnover",  "평균 회전율",   summary.get("avg_turnover"))
    _add("defense_ratio", "방어 모드 비율", summary.get("defense_ratio"))

    # 섹션 B: 하락장 구간
    if bear_df is not None and not bear_df.empty:
        for _, r in bear_df.iterrows():
            rows.append({
                "section": "bear_market",
                "key": r["구간"],
                "label": f"{r['구간']} ({r['유형']}) {r['시작']}~{r['종료']}",
                "sentinel": r["SENTINEL_수익"],
                "spy_bh":   r["SPY_수익"],
            })

    # params 스냅숏
    if params:
        rows.append({"section": "params", "key": "watchdog_enabled",
                     "label": "워치독 활성화",
                     "sentinel": params.get("watchdog_enabled"), "spy_bh": ""})
        rows.append({"section": "params", "key": "top_n_sectors",
                     "label": "보유 섹터 수",
                     "sentinel": params.get("top_n_sectors"), "spy_bh": ""})
        rows.append({"section": "params", "key": "transaction_cost_bps",
                     "label": "거래비용 (bp)",
                     "sentinel": params.get("transaction_cost_bps"), "spy_bh": ""})

    path = Path(output_path)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["section", "key", "label", "sentinel", "spy_bh"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"[리포트] 검증 결과 저장: {path.resolve()}")


# ══════════════════════════════════════════════════════════════
# 차트 (matplotlib, --chart 플래그 시 호출)
# ══════════════════════════════════════════════════════════════

def plot_equity_and_drawdown(
    portfolio_values: pd.Series,
    benchmark_values: pd.Series,
    output_path: str | None = None,
    params: dict | None = None,
) -> None:
    """자산곡선 + 드로다운 2-panel 차트를 생성한다."""
    try:
        import matplotlib
        matplotlib.use("Agg" if output_path else "TkAgg")
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
    except ImportError:
        print("[차트] matplotlib 없음 — 차트 생략")
        return

    bv = benchmark_values.reindex(portfolio_values.index).ffill()
    first_valid = bv.first_valid_index()
    if first_valid:
        bv = bv.loc[first_valid:] / bv.loc[first_valid]

    dd_s = compute_drawdown_series(portfolio_values) * 100
    dd_b = compute_drawdown_series(bv) * 100

    fig, axes = plt.subplots(2, 1, figsize=(14, 8), sharex=True,
                             gridspec_kw={"height_ratios": [2, 1]})
    fig.suptitle("SENTINEL vs SPY 매수보유", fontsize=13, fontweight="bold")

    # ── 상단: 자산곡선 ────────────────────────────────────────
    ax1 = axes[0]
    ax1.plot(portfolio_values.index, portfolio_values.values,
             label="SENTINEL", color="#1f77b4", linewidth=1.5)
    ax1.plot(bv.index, bv.values,
             label="SPY B&H", color="#ff7f0e", linewidth=1.2, linestyle="--")

    # 하락장 구간 음영
    _shade_bear_markets(ax1, portfolio_values.index)

    ax1.set_ylabel("자산 (시작=1.0)")
    ax1.legend(loc="upper left", fontsize=9)
    ax1.grid(True, alpha=0.3)
    ax1.set_yscale("log")

    # ── 하단: 드로다운 ────────────────────────────────────────
    ax2 = axes[1]
    ax2.fill_between(dd_s.index, dd_s.values, 0,
                     alpha=0.4, color="#1f77b4", label="SENTINEL DD")
    ax2.plot(dd_b.index, dd_b.values,
             color="#ff7f0e", linewidth=0.8, linestyle="--", label="SPY DD")

    _shade_bear_markets(ax2, portfolio_values.index)

    ax2.set_ylabel("낙폭 (%)")
    ax2.legend(loc="lower left", fontsize=8)
    ax2.grid(True, alpha=0.3)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax2.xaxis.set_major_locator(mdates.YearLocator(2))

    plt.xticks(rotation=30)
    plt.tight_layout()

    if output_path:
        fig.savefig(output_path, dpi=150, bbox_inches="tight")
        print(f"[차트] 저장: {output_path}")
    else:
        plt.show()

    plt.close(fig)


def _shade_bear_markets(ax, date_index: pd.DatetimeIndex) -> None:
    """하락장 구간에 연한 빨간 음영을 추가한다."""
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        return
    for _, start, end, _ in BEAR_MARKETS:
        s = pd.Timestamp(start)
        e = pd.Timestamp(end)
        if s <= date_index[-1] and e >= date_index[0]:
            ax.axvspan(max(s, date_index[0]), min(e, date_index[-1]),
                       alpha=0.08, color="red", zorder=0)


# ── 하위호환용 단일 차트 stubs (스펙 stub 유지) ────────────────

def plot_equity_curve(
    portfolio_values: pd.Series,
    benchmark_values: pd.Series,
    output_path: str | None = None,
) -> None:
    """자산곡선 단독 플롯 (plot_equity_and_drawdown 호출)."""
    plot_equity_and_drawdown(portfolio_values, benchmark_values, output_path)


def plot_drawdown(
    portfolio_values: pd.Series,
    benchmark_values: pd.Series,
    output_path: str | None = None,
) -> None:
    """드로다운 단독 플롯 (plot_equity_and_drawdown 호출)."""
    plot_equity_and_drawdown(portfolio_values, benchmark_values, output_path)


def plot_sector_allocation(
    weights_history: pd.DataFrame,
    output_path: str | None = None,
) -> None:
    """월별 섹터 비중 스택 영역 차트."""
    try:
        import matplotlib
        matplotlib.use("Agg" if output_path else "TkAgg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("[차트] matplotlib 없음 — 차트 생략")
        return

    fig, ax = plt.subplots(figsize=(14, 5))
    weights_history.plot.area(ax=ax, linewidth=0, alpha=0.8)
    ax.set_ylabel("비중")
    ax.set_title("SENTINEL 월별 섹터 배분")
    ax.legend(loc="upper left", fontsize=8, ncol=4)
    plt.tight_layout()

    if output_path:
        fig.savefig(output_path, dpi=150, bbox_inches="tight")
        print(f"[차트] 저장: {output_path}")
    else:
        plt.show()
    plt.close(fig)


def print_params(params: dict) -> None:
    """적용된 파라미터를 출력한다."""
    print(f"  top_n={params.get('top_n_sectors')}  "
          f"cost={params.get('transaction_cost_bps')}bp  "
          f"sizing={params.get('sizing')}  "
          f"buffer={params.get('buffer_pct')}  "
          f"confirm={params.get('confirmation_months')}m  "
          f"watchdog={'ON' if params.get('watchdog_enabled') else 'OFF'}")


def print_summary(summary: dict, params: dict) -> None:
    """성과 요약 간략 출력 (하위호환 stub)."""
    bear_df = pd.DataFrame()
    print_report(summary, bear_df, params)
