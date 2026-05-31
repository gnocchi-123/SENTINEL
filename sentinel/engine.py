"""백테스트 실행 엔진 — 모듈 4 (체결·비용·자산곡선) + 워치독 오버레이.

월별 루프:
  점검일(당월 첫 거래일) → 신호기준일(직전 월말) 데이터로 목표 비중 산출
  → 전월 목표 티커 집합과 비교 → 다르면 리밸런싱, 같으면 무행동
  → 거래비용 차감 → 다음 점검일까지 일별 가치 갱신

워치독 오버레이 (watchdog_enabled=True 시에만):
  매 거래일 종가로 SPY 낙폭 AND VIX 조건 체크 → 발동 시 50% 디리스크
  → 재진입은 다음 정규 월초 점검에서 국면 필터 재충족 시에만
  정규 리밸런싱 로직은 변경 없음. 워치독은 그 위에 얹는 별개 장치.
"""

from __future__ import annotations

import pandas as pd

from sentinel.data import get_first_trading_days, get_last_trading_day_of_month
from sentinel.signals import compute_target_weights
from sentinel.watchdog import apply_watchdog


# ══════════════════════════════════════════════════════════════
# 내부 헬퍼
# ══════════════════════════════════════════════════════════════

def _target_key(weights: dict[str, float]) -> frozenset[str]:
    """목표 포트폴리오의 티커 집합을 해시 가능한 키로 반환한다."""
    return frozenset(weights.keys())


def _portfolio_value(shares: dict[str, float], prices_row: pd.Series) -> float:
    """보유 주식 수와 당일 가격으로 포트폴리오 가치를 계산한다."""
    total = 0.0
    for ticker, qty in shares.items():
        p = prices_row.get(ticker, float("nan"))
        if not pd.isna(p):
            total += qty * float(p)
    return total


def _weight_vector(
    shares: dict[str, float], prices_row: pd.Series, pv: float
) -> dict[str, float]:
    """현재 보유 비중 딕셔너리를 반환한다. pv=0이면 빈 딕셔너리."""
    if pv <= 0:
        return {}
    result = {}
    for t, qty in shares.items():
        p = prices_row.get(t, float("nan"))
        if not pd.isna(p):
            result[t] = qty * float(p) / pv
    return result


def _execute_partial_exit(
    shares: dict[str, float],
    new_target: dict[str, float],
    exec_prices: pd.Series,
    partial_exit: float,
) -> dict[str, float]:
    """partial_exit_fraction을 적용해 새 보유 주식 수를 반환한다."""
    prev_tickers = set(shares.keys())
    new_tickers = set(new_target.keys())
    exiting = prev_tickers - new_tickers

    retained: dict[str, float] = {}
    freed = 0.0

    for t in exiting:
        p = exec_prices.get(t, float("nan"))
        if pd.isna(p) or float(p) <= 0:
            continue
        held_val = shares[t] * float(p)
        freed += held_val * partial_exit
        keep_qty = shares[t] * (1.0 - partial_exit)
        if keep_qty > 1e-12:
            retained[t] = keep_qty

    for t in prev_tickers - exiting:
        p = exec_prices.get(t, float("nan"))
        if not pd.isna(p) and float(p) > 0:
            freed += shares.get(t, 0.0) * float(p)

    new_shares: dict[str, float] = dict(retained)
    for t, w in new_target.items():
        p = exec_prices.get(t, float("nan"))
        if not pd.isna(p) and float(p) > 0:
            new_shares[t] = new_shares.get(t, 0.0) + freed * w / float(p)

    return new_shares


def _full_rebalance(
    new_target: dict[str, float],
    exec_prices: pd.Series,
    pv: float,
) -> dict[str, float]:
    """목표 비중으로 완전 리밸런싱한 주식 수를 반환한다."""
    new_shares: dict[str, float] = {}
    total_w = 0.0
    valid: list[tuple[str, float, float]] = []

    for t, w in new_target.items():
        p = exec_prices.get(t, float("nan"))
        if not pd.isna(p) and float(p) > 0:
            valid.append((t, w, float(p)))
            total_w += w

    if total_w <= 0:
        return new_shares

    for t, w, p in valid:
        new_shares[t] = pv * (w / total_w) / p

    return new_shares


def _run_watchdog_step(
    shares: dict[str, float],
    day_prices: pd.Series,
    pv: float,
    daily_prices: pd.DataFrame,
    check_date: pd.Timestamp,
    wd_fired: bool,
    params: dict,
    cost_bps: float,
) -> tuple[dict[str, float], float, bool, dict | None]:
    """워치독 1회 체크를 실행한다.

    Returns:
        (new_shares, new_pv, fired_this_call, log_entry_or_None)
        발동 안 하면 (shares, pv, False, None) 그대로 반환.
    """
    defense = params["tickers"]["defense"]

    # 주식 포지션 없으면 체크 불필요
    if not any(t != defense for t in shares):
        return shares, pv, False, None

    cur_w = _weight_vector(shares, day_prices, pv)

    new_w, fired = apply_watchdog(cur_w, daily_prices, check_date, wd_fired, params)
    if not fired:
        return shares, pv, False, None

    # 디리스크 실행
    new_shares_raw = _full_rebalance(new_w, day_prices, pv)
    pv_raw = _portfolio_value(new_shares_raw, day_prices)
    if pv_raw <= 0:
        # 가격 누락 — 발동 플래그만 세우고 포지션 유지
        return shares, pv, True, None

    wd_w = _weight_vector(new_shares_raw, day_prices, pv_raw)
    turnover = compute_turnover(cur_w, wd_w)
    pv_after = apply_transaction_cost(pv_raw, turnover, cost_bps)
    scale = pv_after / pv_raw
    new_shares = {t: s * scale for t, s in new_shares_raw.items() if s > 1e-12}

    all_t = set(cur_w) | set(wd_w)
    trades_dict = {
        t: round(wd_w.get(t, 0.0) - cur_w.get(t, 0.0), 6)
        for t in sorted(all_t)
        if abs(wd_w.get(t, 0.0) - cur_w.get(t, 0.0)) > 1e-4
    }

    log_entry = {
        "date": check_date,
        "source": "watchdog",
        "signal_date": check_date,
        "phase": "WD",
        "holdings": sorted(new_w.keys()),
        "target_weights": new_w,
        "traded": True,
        "turnover": round(turnover, 6),
        "cost_applied": round(pv_raw - pv_after, 8),
        "pv_before": pv,
        "pv_after": pv_after,
        "trades": trades_dict,
    }

    return new_shares, pv_after, True, log_entry


# ══════════════════════════════════════════════════════════════
# 공개 API
# ══════════════════════════════════════════════════════════════

def compute_turnover(
    prev_weights: dict[str, float],
    new_weights: dict[str, float],
) -> float:
    """편도 회전율 = 0.5 × Σ|new_w - prev_w|."""
    all_tickers = set(prev_weights) | set(new_weights)
    return 0.5 * sum(
        abs(new_weights.get(t, 0.0) - prev_weights.get(t, 0.0))
        for t in all_tickers
    )


def apply_transaction_cost(
    portfolio_value: float,
    turnover: float,
    cost_bps: float,
) -> float:
    """거래비용 차감 후 포트폴리오 가치를 반환한다."""
    return portfolio_value - portfolio_value * turnover * cost_bps / 10_000.0


def assert_no_lookahead(
    signal_date: pd.Timestamp,
    execution_date: pd.Timestamp,
    data_used_up_to: pd.Timestamp,
) -> None:
    """룩어헤드 금지 조건을 검증한다 (data_used_up_to <= signal_date < execution_date)."""
    assert data_used_up_to <= signal_date, (
        f"룩어헤드 감지: 데이터 최신일({data_used_up_to}) > 신호기준일({signal_date})"
    )
    assert signal_date < execution_date, (
        f"룩어헤드 감지: 신호기준일({signal_date}) >= 체결일({execution_date})"
    )


def run_backtest(
    daily_prices: pd.DataFrame,
    monthly_prices: pd.DataFrame,
    params: dict,
) -> tuple[pd.Series, pd.DataFrame]:
    """SENTINEL 월별 백테스트를 실행한다.

    정규 리밸런싱 + 워치독 오버레이 (watchdog_enabled=True 시에만 활성화).
    watchdog_enabled=False 시 단계 4와 자산곡선·거래로그 값이 동일하다.

    Returns:
        (equity_curve, log_df) tuple.
          equity_curve: 일별 포트폴리오 가치 Series (시작값=1.0).
          log_df: 월별 거래·신호 로그 + 워치독 이벤트 로그 (혼합, date 오름차순).
                  source 컬럼: "monthly" | "watchdog"
    """
    defense = params["tickers"]["defense"]
    cost_bps = float(params.get("transaction_cost_bps", 5))
    partial_exit = float(params.get("partial_exit_fraction", 1.0))
    rebalance_on_drift = bool(params.get("rebalance_on_weight_drift", False))
    wd_enabled = bool(params.get("watchdog_enabled", False))

    shares: dict[str, float] = {}
    prev_target_key: frozenset[str] | None = None

    daily_pv: dict[pd.Timestamp, float] = {}
    log_rows: list[dict] = []          # 정규 월별 로그
    wd_log_rows: list[dict] = []       # 워치독 이벤트 로그

    # 워치독 상태 (정규 리밸런싱과 독립적으로 관리)
    wd_fired_this_month: bool = False  # 이번 월중 발동 여부 (exec_date마다 리셋)

    first_trading_days = list(get_first_trading_days(daily_prices.index))

    periods: list[tuple[pd.Timestamp, pd.Timestamp]] = []
    for exec_date in first_trading_days:
        py = exec_date.year if exec_date.month > 1 else exec_date.year - 1
        pm = exec_date.month - 1 if exec_date.month > 1 else 12
        try:
            sig_date = get_last_trading_day_of_month(daily_prices.index, py, pm)
        except ValueError:
            continue
        periods.append((exec_date, sig_date))

    for i, (exec_date, signal_date) in enumerate(periods):
        if exec_date not in daily_prices.index:
            continue

        exec_prices: pd.Series = daily_prices.loc[exec_date]

        # ── 새 월 시작: 워치독 플래그 리셋 ─────────────────────────
        # "다음 정규 월초 점검 전까지 추가 발동 안 함" → 월초 점검 시 리셋
        wd_fired_this_month = False

        # ── 직전 구간 일별 가치 + 워치독 체크 ─────────────────────
        if i > 0:
            prev_exec = periods[i - 1][0]
            fill_range = daily_prices.index[
                (daily_prices.index > prev_exec) & (daily_prices.index < exec_date)
            ]
            for d in fill_range:
                d_prices = daily_prices.loc[d]
                pv = _portfolio_value(shares, d_prices)

                # ── 워치독 오버레이 (enabled 시에만) ─────────────
                if wd_enabled and pv > 0:
                    shares, pv, fired, wd_entry = _run_watchdog_step(
                        shares, d_prices, pv, daily_prices, d,
                        wd_fired_this_month, params, cost_bps,
                    )
                    if fired:
                        wd_fired_this_month = True
                        # 워치독 발동 → 다음 정규 점검에서 강제 재평가
                        prev_target_key = None
                        if wd_entry is not None:
                            wd_log_rows.append(wd_entry)

                if pv > 0:
                    daily_pv[d] = pv

        # ── 체결 전 포트폴리오 가치 ─────────────────────────────────
        pv_before = _portfolio_value(shares, exec_prices) if shares else 1.0

        # ── 룩어헤드 검증 ────────────────────────────────────────────
        assert_no_lookahead(signal_date, exec_date, signal_date)

        # ── 신호 산출 ────────────────────────────────────────────────
        new_target = compute_target_weights(daily_prices, signal_date, params)
        new_target_key = _target_key(new_target)
        is_equity = not (len(new_target) == 1 and defense in new_target)
        phase = "ON" if is_equity else "OFF"

        # ── 무신호=무행동 판단 ──────────────────────────────────────
        signal_same = (
            prev_target_key is not None
            and new_target_key == prev_target_key
            and not rebalance_on_drift
        )

        if signal_same:
            daily_pv[exec_date] = pv_before
            log_rows.append({
                "date": exec_date,
                "source": "monthly",
                "signal_date": signal_date,
                "phase": phase,
                "holdings": sorted(new_target_key),
                "target_weights": new_target,
                "traded": False,
                "turnover": 0.0,
                "cost_applied": 0.0,
                "pv_before": pv_before,
                "pv_after": pv_before,
                "trades": {},
            })
            prev_target_key = new_target_key

        else:
            # ── 리밸런싱 실행 ─────────────────────────────────────────
            prev_w = _weight_vector(shares, exec_prices, pv_before)

            if partial_exit < 1.0 and prev_target_key is not None:
                new_shares_raw = _execute_partial_exit(
                    shares, new_target, exec_prices, partial_exit
                )
            else:
                new_shares_raw = _full_rebalance(new_target, exec_prices, pv_before)

            pv_after_raw = _portfolio_value(new_shares_raw, exec_prices)
            if pv_after_raw <= 0:
                pv_after_raw = pv_before

            new_w = _weight_vector(new_shares_raw, exec_prices, pv_after_raw)
            turnover = compute_turnover(prev_w, new_w)
            pv_after = apply_transaction_cost(pv_after_raw, turnover, cost_bps)

            scale = pv_after / pv_after_raw if pv_after_raw > 0 else 1.0
            shares = {t: s * scale for t, s in new_shares_raw.items() if s > 1e-12}

            all_t = set(prev_w) | set(new_w)
            trades = {
                t: round(new_w.get(t, 0.0) - prev_w.get(t, 0.0), 6)
                for t in sorted(all_t)
                if abs(new_w.get(t, 0.0) - prev_w.get(t, 0.0)) > 1e-4
            }

            daily_pv[exec_date] = pv_after
            log_rows.append({
                "date": exec_date,
                "source": "monthly",
                "signal_date": signal_date,
                "phase": phase,
                "holdings": sorted(new_target_key),
                "target_weights": new_target,
                "traded": True,
                "turnover": round(turnover, 6),
                "cost_applied": round(pv_after_raw - pv_after, 8),
                "pv_before": pv_before,
                "pv_after": pv_after,
                "trades": trades,
            })

            prev_target_key = new_target_key

        # ── 워치독: exec_date 당일도 체크 (정규 리밸런싱 이후) ───────
        if wd_enabled and shares:
            pv_exec = daily_pv.get(exec_date, pv_before)
            shares, pv_exec, fired, wd_entry = _run_watchdog_step(
                shares, exec_prices, pv_exec, daily_prices, exec_date,
                wd_fired_this_month, params, cost_bps,
            )
            if fired:
                wd_fired_this_month = True
                prev_target_key = None
                daily_pv[exec_date] = pv_exec
                if wd_entry is not None:
                    wd_log_rows.append(wd_entry)

    # ── 마지막 구간 일별 가치 + 워치독 ────────────────────────────
    if periods:
        last_exec = periods[-1][0]
        fill_range = daily_prices.index[daily_prices.index > last_exec]
        for d in fill_range:
            d_prices = daily_prices.loc[d]
            pv = _portfolio_value(shares, d_prices)

            if wd_enabled and pv > 0:
                shares, pv, fired, wd_entry = _run_watchdog_step(
                    shares, d_prices, pv, daily_prices, d,
                    wd_fired_this_month, params, cost_bps,
                )
                if fired:
                    wd_fired_this_month = True
                    prev_target_key = None
                    if wd_entry is not None:
                        wd_log_rows.append(wd_entry)

            if pv > 0:
                daily_pv[d] = pv

    # ── 결과 구성 ─────────────────────────────────────────────────
    equity_curve = pd.Series(daily_pv, name="portfolio", dtype=float).sort_index()

    all_rows = sorted(log_rows + wd_log_rows, key=lambda r: r["date"])
    if all_rows:
        log_df = pd.DataFrame(all_rows).set_index("date")
    else:
        log_df = pd.DataFrame()

    return equity_curve, log_df


# ══════════════════════════════════════════════════════════════
# 결과 출력
# ══════════════════════════════════════════════════════════════

def print_backtest_summary(
    equity: pd.Series,
    log_df: pd.DataFrame,
    params: dict,
) -> None:
    """자산곡선 요약과 샘플 거래 로그를 출력한다."""
    if equity.empty:
        print("[경고] 자산곡선이 비어 있습니다.")
        return

    start_val = float(equity.iloc[0])
    end_val = float(equity.iloc[-1])
    total_return = (end_val / start_val - 1.0) * 100.0

    monthly_log = log_df[log_df["source"] == "monthly"] if "source" in log_df.columns else log_df
    wd_log = log_df[log_df["source"] == "watchdog"] if "source" in log_df.columns else pd.DataFrame()

    traded_months = int(monthly_log["traded"].sum()) if "traded" in monthly_log.columns else 0
    skipped_months = int((~monthly_log["traded"]).sum()) if "traded" in monthly_log.columns else 0
    total_months = traded_months + skipped_months

    wd_enabled = bool(params.get("watchdog_enabled", False))

    print("\n" + "=" * 70)
    print(f"  SENTINEL 백테스트 — 전 구간 요약  [워치독: {'ON' if wd_enabled else 'OFF'}]")
    print("=" * 70)
    print(f"  백테스트 기간   : {str(equity.index[0].date())} ~ {str(equity.index[-1].date())}")
    print(f"  시작 자산       : {start_val:.4f}")
    print(f"  종료 자산       : {end_val:.4f}  ({total_return:+.1f}%)")
    print(f"  점검 월 합계    : {total_months}")
    print(f"  매매 발생 달    : {traded_months}")
    print(f"  무신호 건너뜀   : {skipped_months}달  ({skipped_months/total_months*100:.1f}%)" if total_months else "")
    if wd_enabled and not wd_log.empty:
        print(f"  워치독 발동 횟수 : {len(wd_log)}회")
    print("=" * 70)

    if monthly_log.empty:
        return

    # 정규 매매 샘플 로그
    traded_log = monthly_log[monthly_log["traded"]].head(25)
    print("\n  정규 거래 로그 (매매 발생 달, 최초 25건)")
    print(f"  {'날짜':<12} {'신호기준일':<12} {'국면':<5} {'보유':<30} {'회전율':>7} {'비용':>9}")
    print("  " + "-" * 82)
    for date, row in traded_log.iterrows():
        holdings_str = " ".join(
            f"{t}({row['target_weights'].get(t, 0.0):.0%})"
            for t in row["holdings"]
        )
        turnover_pct = row["turnover"] * 100
        cost_bp = row["cost_applied"] / row["pv_before"] * 10_000 if row["pv_before"] > 0 else 0.0
        print(
            f"  {str(date.date()):<12} {str(row['signal_date'].date()):<12} "
            f"{row['phase']:<5} {holdings_str:<30} "
            f"{turnover_pct:>6.1f}%  {cost_bp:>6.2f}bp"
        )

    # 워치독 발동 로그
    if wd_enabled and not wd_log.empty:
        print(f"\n  워치독 발동 로그 (총 {len(wd_log)}건)")
        print(f"  {'발동일':<12} {'포트폴리오 (디리스크 후)':<44} {'회전율':>7} {'비용':>9}")
        print("  " + "-" * 78)
        for date, row in wd_log.iterrows():
            holdings_str = " ".join(
                f"{t}({row['target_weights'].get(t, 0.0):.0%})"
                for t in row["holdings"]
            )
            turnover_pct = row["turnover"] * 100
            cost_bp = row["cost_applied"] / row["pv_before"] * 10_000 if row["pv_before"] > 0 else 0.0
            print(
                f"  {str(date.date()):<12} {holdings_str:<44} "
                f"{turnover_pct:>6.1f}%  {cost_bp:>6.2f}bp"
            )

    print()
