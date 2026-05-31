"""워치독 모듈 — 월중 방어 전용 비대칭 장치.

기본 OFF (watchdog_enabled=false). 백테스트 검증 후 채택 결정.

시간축 비대칭 원칙:
  - 나갈 때(방어 전환)는 빠르게 — 일봉 종가 기준, 매 거래일 점검
  - 들어올 때(재진입)는 느리게 — 다음 정규 월초 점검으로만

발동 조건(AND):
  1. SPY 종가 < 최근 252거래일 최고 종가 × (1 + drawdown_threshold)
  2. VIX 종가 > vix_threshold

발동 시: 주식 보유분 derisk_fraction만큼 부분 청산 → 방어자산.
재발동: watchdog_refire=false(기본)이면 당월 내 추가 발동 없음.
재진입: 다음 정규 월초 점검에서 국면 필터 재충족 시에만. 자동 복귀 없음.
"""

from __future__ import annotations

import pandas as pd


def check_watchdog_trigger(
    daily_prices: pd.DataFrame,
    check_date: pd.Timestamp,
    params: dict,
) -> bool:
    """당일 종가 기준으로 워치독 발동 조건을 확인한다.

    check_date 이후 데이터를 절대 사용하지 않는다 (룩어헤드 금지 assert).

    조건 1: SPY[check_date] / rolling_high(lookback) - 1 <= drawdown_threshold
    조건 2: VIX[check_date] > vix_threshold

    Args:
        daily_prices: 일봉 수정종가 DataFrame (SPY, ^VIX 포함).
        check_date: 판단 기준일 (당일 종가까지만 사용).
        params: params.yaml 설정 딕셔너리.

    Returns:
        True=발동 조건 충족, False=미충족.
    """
    check_date = pd.Timestamp(check_date)

    # ── 룩어헤드 금지 assert ─────────────────────────────────────
    sliced = daily_prices.loc[:check_date]
    if len(sliced) > 0:
        assert sliced.index.max() <= check_date, (
            f"워치독 룩어헤드 감지: 슬라이스 최신일({sliced.index.max()}) > check_date({check_date})"
        )

    if check_date not in daily_prices.index:
        return False

    spy_col = params["tickers"]["market"]   # "SPY"
    vix_col = params["tickers"]["vix"]      # "^VIX"
    lookback = int(params.get("watchdog_high_lookback_days", 252))
    drawdown_thresh = float(params.get("watchdog_drawdown_threshold", -0.10))
    vix_thresh = float(params.get("watchdog_vix_threshold", 28))

    # ── 조건 1: SPY 낙폭 ─────────────────────────────────────────
    if spy_col not in daily_prices.columns:
        return False

    spy_series = sliced[spy_col].dropna()
    if len(spy_series) < 2:
        return False

    spy_today = float(spy_series.iloc[-1])
    rolling_high = float(spy_series.tail(lookback).max())

    if rolling_high <= 0:
        return False

    drawdown = (spy_today - rolling_high) / rolling_high
    if drawdown > drawdown_thresh:  # 아직 충분히 안 빠짐 (예: -0.05 > -0.10)
        return False

    # ── 조건 2: VIX 수준 ─────────────────────────────────────────
    if vix_col not in daily_prices.columns:
        return False

    vix_series = sliced[vix_col].dropna()
    if len(vix_series) == 0:
        return False

    vix_today = float(vix_series.iloc[-1])
    return vix_today > vix_thresh


def apply_watchdog(
    current_weights: dict[str, float],
    daily_prices: pd.DataFrame,
    check_date: pd.Timestamp,
    watchdog_fired_this_month: bool,
    params: dict,
) -> tuple[dict[str, float], bool]:
    """워치독 발동 여부를 확인하고, 필요 시 포트폴리오 비중을 조정한다.

    watchdog_enabled=False이면 즉시 (current_weights, False) 반환.
    watchdog_refire=False이고 watchdog_fired_this_month=True이면 재발동 없음.

    Args:
        current_weights: 현재 포트폴리오 비중 {티커: 비중}.
        daily_prices: 일봉 수정종가 DataFrame.
        check_date: 판단 기준일.
        watchdog_fired_this_month: 이번 달 이미 발동 여부.
        params: params.yaml 설정 딕셔너리.

    Returns:
        (조정된 비중 딕셔너리, 이번 호출에서 발동되었는지 여부).
    """
    if not bool(params.get("watchdog_enabled", False)):
        return current_weights, False

    if not bool(params.get("watchdog_refire", False)) and watchdog_fired_this_month:
        return current_weights, False

    if not check_watchdog_trigger(daily_prices, check_date, params):
        return current_weights, False

    defense = params["tickers"]["defense"]
    derisk_fraction = float(params.get("watchdog_derisk_fraction", 0.50))

    new_weights = derisk_weights(current_weights, defense, derisk_fraction)
    return new_weights, True


def derisk_weights(
    current_weights: dict[str, float],
    defense_ticker: str,
    derisk_fraction: float,
) -> dict[str, float]:
    """주식 보유분의 derisk_fraction을 방어자산으로 전환한 비중을 반환한다.

    예: {XLK: 0.5, XLV: 0.5}, defense=AGG, fraction=0.5
     → {XLK: 0.25, XLV: 0.25, AGG: 0.5}

    Args:
        current_weights: 현재 포트폴리오 비중 {티커: 비중}.
        defense_ticker: 방어자산 티커 (AGG 등).
        derisk_fraction: 주식분 중 청산 비율 (0.0~1.0).

    Returns:
        조정된 비중 딕셔너리. 비중 합계 = 1.0.
    """
    equity = {t: w for t, w in current_weights.items() if t != defense_ticker}
    defense_w = current_weights.get(defense_ticker, 0.0)

    total_equity = sum(equity.values())

    # 주식분: (1 - derisk_fraction) 비율 유지
    new_equity = {t: w * (1.0 - derisk_fraction) for t, w in equity.items()}
    # 방어분: 기존 방어 + 청산된 주식분
    new_defense = defense_w + total_equity * derisk_fraction

    result = {t: w for t, w in new_equity.items() if w > 1e-12}
    if new_defense > 1e-12:
        result[defense_ticker] = new_defense

    return result
