"""백테스트 실행 엔진 — 모듈 4 (체결·비용·자산곡선).

월별 루프:
  점검일(당월 첫 거래일) → 신호기준일(직전 월말) 데이터로 목표 비중 산출
  → 전월 목표 티커 집합과 비교 → 다르면 리밸런싱, 같으면 무행동
  → 거래비용 차감 → 다음 점검일까지 일별 가치 갱신

워치독: 단계 5에서 추가 예정.
"""

from __future__ import annotations

import pandas as pd

from sentinel.data import get_first_trading_days, get_last_trading_day_of_month
from sentinel.signals import compute_target_weights


# ══════════════════════════════════════════════════════════════
# 내부 헬퍼
# ══════════════════════════════════════════════════════════════

def _target_key(weights: dict[str, float]) -> frozenset[str]:
    """목표 포트폴리오의 티커 집합을 해시 가능한 키로 반환한다.

    '무신호=무행동' 비교 기준 = (국면 상태 + 보유 섹터 집합).
    비중 drift는 이 비교에 포함되지 않는다 (rebalance_on_weight_drift 참조).
    """
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
    """partial_exit_fraction을 적용해 새 보유 주식 수를 반환한다.

    탈락 티커(prev에 있고 new_target에 없는 것): partial_exit 비율만 청산,
    (1 - partial_exit) 비율은 '잔류 포지션'으로 유지.
    유지·신규 티커: freed 자본을 new_target 비중으로 완전 배분.
    """
    prev_tickers = set(shares.keys())
    new_tickers = set(new_target.keys())
    exiting = prev_tickers - new_tickers

    # 탈락 포지션 → partial_exit만 매도, 나머지 잔류
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

    # 유지 + 신규 티커의 현재 보유분 전량 freed pool에 합산
    for t in prev_tickers - exiting:
        p = exec_prices.get(t, float("nan"))
        if not pd.isna(p) and float(p) > 0:
            freed += shares.get(t, 0.0) * float(p)

    # freed 자본을 new_target 비중으로 배분
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


# ══════════════════════════════════════════════════════════════
# 공개 API
# ══════════════════════════════════════════════════════════════

def compute_turnover(
    prev_weights: dict[str, float],
    new_weights: dict[str, float],
) -> float:
    """두 포트폴리오 비중 간 편도 회전율을 계산한다.

    turnover = 0.5 × Σ|new_w - prev_w|

    Args:
        prev_weights: 이전 포트폴리오 비중 {티커: 비중}.
        new_weights: 새 포트폴리오 비중 {티커: 비중}.

    Returns:
        편도 회전율 (0.0~1.0).
    """
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
    """거래비용을 차감한 포트폴리오 가치를 반환한다.

    cost = portfolio_value × turnover × cost_bps / 10_000

    Args:
        portfolio_value: 거래 전 포트폴리오 가치.
        turnover: 편도 회전율.
        cost_bps: 편도 거래비용 (bp 단위, 예: 5).

    Returns:
        거래비용 차감 후 포트폴리오 가치.
    """
    return portfolio_value - portfolio_value * turnover * cost_bps / 10_000.0


def assert_no_lookahead(
    signal_date: pd.Timestamp,
    execution_date: pd.Timestamp,
    data_used_up_to: pd.Timestamp,
) -> None:
    """룩어헤드 금지 조건을 검증한다.

    data_used_up_to <= signal_date < execution_date 를 보장한다.

    Args:
        signal_date: 신호 산출 기준일 (직전 월말).
        execution_date: 체결일 (당월 첫 거래일).
        data_used_up_to: 신호 산출에 실제로 사용된 데이터의 최신 날짜.

    Raises:
        AssertionError: 룩어헤드 조건 위반 시.
    """
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
    """SENTINEL 월별 백테스트를 실행한다. (워치독 미포함 — 단계 5에서 추가)

    월별 루프:
      1. 점검일(당월 첫 거래일) 직전 월말 → 신호기준일
      2. compute_target_weights()로 목표 비중 산출
      3. 전월 목표 티커 집합과 비교 → 다르면 리밸런싱, 같으면 무행동
      4. partial_exit_fraction < 1이면 탈락분 부분 청산
      5. 거래비용 차감 (매매 발생 시에만)
      6. 다음 점검일까지 일별 포트폴리오 가치 갱신

    Args:
        daily_prices: 일봉 수정종가 DataFrame (load_prices 반환값).
        monthly_prices: 월말 수정종가 DataFrame (현재 미사용).
        params: params.yaml 설정 딕셔너리.

    Returns:
        (equity_curve, trade_log) tuple.
          equity_curve: 일별 포트폴리오 가치 Series (시작값=1.0).
          trade_log: 월별 거래·신호 로그 DataFrame.
    """
    defense = params["tickers"]["defense"]
    cost_bps = float(params.get("transaction_cost_bps", 5))
    partial_exit = float(params.get("partial_exit_fraction", 1.0))
    rebalance_on_drift = bool(params.get("rebalance_on_weight_drift", False))

    shares: dict[str, float] = {}
    prev_target_key: frozenset[str] | None = None

    daily_pv: dict[pd.Timestamp, float] = {}
    log_rows: list[dict] = []

    first_trading_days = list(get_first_trading_days(daily_prices.index))

    # (체결일, 신호기준일) 페어 구축
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

        # ── 직전 구간(전월 체결일 익일 ~ 당월 체결일 전날) 일별 가치 ──
        if i > 0:
            prev_exec = periods[i - 1][0]
            fill_range = daily_prices.index[
                (daily_prices.index > prev_exec) & (daily_prices.index < exec_date)
            ]
            for d in fill_range:
                pv = _portfolio_value(shares, daily_prices.loc[d])
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
            # target_key는 같으므로 갱신 불필요하지만 명시적으로 유지
            prev_target_key = new_target_key
            continue

        # ── 리밸런싱 실행 ─────────────────────────────────────────────
        # 체결 전 비중 (회전율 계산 기준)
        prev_w = _weight_vector(shares, exec_prices, pv_before)

        # 신규 주식 수 계산
        if partial_exit < 1.0 and prev_target_key is not None:
            new_shares_raw = _execute_partial_exit(
                shares, new_target, exec_prices, partial_exit
            )
        else:
            new_shares_raw = _full_rebalance(new_target, exec_prices, pv_before)

        # 체결 후 가치 및 비중 (거래비용 차감 전)
        pv_after_raw = _portfolio_value(new_shares_raw, exec_prices)
        if pv_after_raw <= 0:
            pv_after_raw = pv_before  # 안전장치 (가격 누락 시)

        new_w = _weight_vector(new_shares_raw, exec_prices, pv_after_raw)

        # 편도 회전율 및 거래비용
        turnover = compute_turnover(prev_w, new_w)
        pv_after = apply_transaction_cost(pv_after_raw, turnover, cost_bps)

        # 거래비용 반영: 주식 수를 비례 축소
        scale = pv_after / pv_after_raw if pv_after_raw > 0 else 1.0
        shares = {t: s * scale for t, s in new_shares_raw.items() if s > 1e-12}

        # 거래 내역: 비중 변화 ≥ 0.01%인 항목만
        all_t = set(prev_w) | set(new_w)
        trades = {
            t: round(new_w.get(t, 0.0) - prev_w.get(t, 0.0), 6)
            for t in sorted(all_t)
            if abs(new_w.get(t, 0.0) - prev_w.get(t, 0.0)) > 1e-4
        }

        daily_pv[exec_date] = pv_after

        log_rows.append({
            "date": exec_date,
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

    # ── 마지막 점검일 이후 구간 일별 가치 ───────────────────────────
    if periods:
        last_exec = periods[-1][0]
        fill_range = daily_prices.index[daily_prices.index > last_exec]
        for d in fill_range:
            pv = _portfolio_value(shares, daily_prices.loc[d])
            if pv > 0:
                daily_pv[d] = pv

    # ── 결과 구성 ─────────────────────────────────────────────────
    equity_curve = pd.Series(daily_pv, name="portfolio", dtype=float).sort_index()

    if log_rows:
        log_df = (
            pd.DataFrame(log_rows)
            .set_index("date")
        )
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

    traded_months = int(log_df["traded"].sum()) if "traded" in log_df.columns else 0
    skipped_months = int((~log_df["traded"]).sum()) if "traded" in log_df.columns else 0
    total_months = traded_months + skipped_months

    print("\n" + "=" * 70)
    print("  SENTINEL 백테스트 — 전 구간 요약")
    print("=" * 70)
    print(f"  백테스트 기간   : {str(equity.index[0].date())} ~ {str(equity.index[-1].date())}")
    print(f"  시작 자산       : {start_val:.4f}")
    print(f"  종료 자산       : {end_val:.4f}  ({total_return:+.1f}%)")
    print(f"  점검 월 합계    : {total_months}")
    print(f"  매매 발생 달    : {traded_months}")
    print(f"  무신호 건너뜀   : {skipped_months}달  ({skipped_months/total_months*100:.1f}%)")
    print("=" * 70)

    if log_df.empty:
        return

    # 샘플 로그: 매매가 발생한 행만, 최대 25건
    traded_log = log_df[log_df["traded"]].head(25) if "traded" in log_df.columns else log_df.head(25)

    print("\n  샘플 거래 로그 (매매 발생 달, 최초 25건)")
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

    print()
