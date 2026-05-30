"""워치독 모듈 — 월중 방어 전용 비대칭 장치.

기본 OFF (watchdog_enabled=false). 백테스트 검증 후 채택 결정.

시간축 비대칭 원칙:
  - 나갈 때(방어 전환)는 빠르게 — 일봉 종가 기준, 매 거래일 점검
  - 들어올 때(재진입)는 느리게 — 다음 정규 월초 점검으로만

발동 조건(AND):
  1. SPY 종가 < 최근 252거래일 최고 종가 × (1 + watchdog_drawdown_threshold)
  2. VIX 종가 > watchdog_vix_threshold

발동 시: 주식 보유분 watchdog_derisk_fraction만큼 부분 청산 → 방어자산.
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

    check_date 이후 데이터를 절대 사용하지 않는다 (룩어헤드 금지).

    조건 1: SPY[check_date] <= rolling_high(252) * (1 + drawdown_threshold)
    조건 2: VIX[check_date] > vix_threshold

    Args:
        daily_prices: 일봉 수정종가 DataFrame (SPY, ^VIX 포함).
        check_date: 판단 기준일 (당일 종가까지만 사용).
        params: params.yaml 설정 딕셔너리.

    Returns:
        True=발동 조건 충족, False=미충족.

    Raises:
        NotImplementedError: 미구현.
    """
    raise NotImplementedError


def apply_watchdog(
    current_weights: dict[str, float],
    daily_prices: pd.DataFrame,
    check_date: pd.Timestamp,
    watchdog_fired_this_month: bool,
    params: dict,
) -> tuple[dict[str, float], bool]:
    """워치독 발동 여부를 확인하고, 필요 시 포트폴리오 비중을 조정한다.

    watchdog_enabled=False이면 즉시 (current_weights, False)를 반환.
    watchdog_refire=False이고 watchdog_fired_this_month=True이면 재발동 없음.

    Args:
        current_weights: 현재 포트폴리오 비중 {티커: 비중}.
        daily_prices: 일봉 수정종가 DataFrame.
        check_date: 판단 기준일.
        watchdog_fired_this_month: 이번 달 이미 발동 여부.
        params: params.yaml 설정 딕셔너리.

    Returns:
        (조정된 비중 딕셔너리, 이번 호출에서 발동되었는지 여부).

    Raises:
        NotImplementedError: 미구현.
    """
    raise NotImplementedError


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

    Raises:
        NotImplementedError: 미구현.
    """
    raise NotImplementedError
