"""신호 산출 모듈 (모듈 1·2·3).

모든 신호는 점검일(M월 첫 거래일) 직전 월말 종가까지의 데이터로만 산출한다.
점검일 당일 데이터는 절대 사용하지 않는다 (룩어헤드 금지).
"""

from __future__ import annotations

import pandas as pd


def compute_market_filter(
    daily_prices: pd.DataFrame,
    monthly_prices: pd.DataFrame,
    signal_date: pd.Timestamp,
    params: dict,
) -> bool:
    """모듈 1 — 시장 국면 필터.

    다음 두 조건을 모두 충족해야 True(공격 모드).
    하나라도 미충족 시 False(방어 모드) → 이하 모듈 건너뜀.

    조건 1: signal_date 기준 SPY 종가 > 200일 이동평균
    조건 2: SPY의 최근 12개월 총수익률 > BIL의 최근 12개월 총수익률

    휩쏘 완화: buffer_pct > 0이면 200일선에 ±buffer_pct 버퍼 적용.
    confirmation_months > 1이면 연속 N개월 신호 일치 후 전환.

    Args:
        daily_prices: 일봉 수정종가 DataFrame.
        monthly_prices: 월말 수정종가 DataFrame.
        signal_date: 신호 산출 기준일 (직전 월말). 이 날짜 이후 데이터 사용 금지.
        params: params.yaml 설정 딕셔너리.

    Returns:
        True=공격 모드, False=방어 모드.

    Raises:
        NotImplementedError: 미구현.
    """
    raise NotImplementedError


def compute_sector_momentum(
    monthly_prices: pd.DataFrame,
    signal_date: pd.Timestamp,
    params: dict,
) -> pd.Series:
    """모듈 2 — 섹터 상대모멘텀 순위.

    유니버스(섹터 ETF + 반도체) 각 종목의 3·6·12개월 총수익률을
    momentum_weights로 가중평균한 뒤 내림차순 순위를 반환한다.

    상장 전 구간이 NaN인 종목은 해당 시점 순위 풀에서 자동 제외.
    SOXX는 특별 로직 없이 동일 풀에서 경쟁.

    Args:
        monthly_prices: 월말 수정종가 DataFrame.
        signal_date: 신호 산출 기준일 (직전 월말). 이 날짜 이후 데이터 사용 금지.
        params: params.yaml 설정 딕셔너리.

    Returns:
        티커를 인덱스로, 혼합 모멘텀 점수를 값으로 하는 Series (내림차순 정렬).

    Raises:
        NotImplementedError: 미구현.
    """
    raise NotImplementedError


def select_top_sectors(momentum_scores: pd.Series, params: dict) -> list[str]:
    """모멘텀 점수 상위 N개 섹터를 선택한다.

    Args:
        momentum_scores: compute_sector_momentum()의 반환값.
        params: params.yaml 설정 딕셔너리 (top_n_sectors 참조).

    Returns:
        선택된 티커 목록 (최대 top_n_sectors개).

    Raises:
        NotImplementedError: 미구현.
    """
    raise NotImplementedError


def compute_target_weights(
    selected_sectors: list[str],
    monthly_prices: pd.DataFrame,
    signal_date: pd.Timestamp,
    market_on: bool,
    params: dict,
) -> dict[str, float]:
    """모듈 3 — 목표 포트폴리오 비중 산출.

    market_on=False이면 방어자산 100%.
    market_on=True이면 selected_sectors를 sizing 방식으로 배분.
      - equal: 균등배분 (1/N)
      - inverse_vol: 변동성 역가중 (inverse_vol_lookback_months 기준 월별 수익률 표준편차)

    Args:
        selected_sectors: 보유할 섹터 티커 목록.
        monthly_prices: 월말 수정종가 DataFrame.
        signal_date: 신호 산출 기준일 (직전 월말).
        market_on: 국면 필터 통과 여부.
        params: params.yaml 설정 딕셔너리.

    Returns:
        {티커: 비중} 딕셔너리. 비중 합계 = 1.0.

    Raises:
        NotImplementedError: 미구현.
    """
    raise NotImplementedError


def compute_monthly_signal(
    daily_prices: pd.DataFrame,
    monthly_prices: pd.DataFrame,
    signal_date: pd.Timestamp,
    params: dict,
) -> dict[str, float]:
    """점검일 직전 월말 기준 목표 포트폴리오 비중을 반환한다.

    모듈 1→2→3을 순서대로 실행하는 통합 함수.
    signal_date 이후 데이터를 사용하지 않음을 assert로 보장.

    Args:
        daily_prices: 일봉 수정종가 DataFrame.
        monthly_prices: 월말 수정종가 DataFrame.
        signal_date: 신호 산출 기준일 (직전 월말 마지막 거래일).
        params: params.yaml 설정 딕셔너리.

    Returns:
        {티커: 비중} 딕셔너리. 비중 합계 = 1.0.

    Raises:
        AssertionError: signal_date 이후 데이터가 참조된 경우.
        NotImplementedError: 미구현.
    """
    raise NotImplementedError
