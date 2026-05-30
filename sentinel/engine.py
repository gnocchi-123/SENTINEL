"""백테스트 실행 엔진.

월별 루프를 돌며 신호 산출 → 매매 결정 → 수익률 누적을 수행한다.

핵심 규칙:
  - 점검일: 매월 첫 번째 거래일
  - 신호 기준일: 점검일 직전 월말 마지막 거래일 (룩어헤드 금지)
  - 체결일: 당월 첫 번째 거래일 종가 (= 점검일)
  - 무신호 = 무행동: 목표 비중이 전월과 동일하면 거래하지 않음
  - 워치독: 일봉 루프에서 별도로 점검 (기본 OFF)
"""

from __future__ import annotations

import pandas as pd


def run_backtest(
    daily_prices: pd.DataFrame,
    monthly_prices: pd.DataFrame,
    params: dict,
) -> pd.DataFrame:
    """SENTINEL 백테스트를 실행하고 일별 포트폴리오 가치를 반환한다.

    월별 루프:
      1. 점검일(매월 첫 거래일) 직전 월말로 신호 기준일 설정
      2. signals.compute_monthly_signal()로 목표 비중 산출
      3. 전월 목표 비중과 비교 → 다르면 거래, 같으면 무행동
      4. 거래비용 차감 (transaction_cost_bps × 회전율)
      5. 다음 점검일까지 보유 수익률 반영

    워치독(enabled=True 시):
      - 일봉 루프에서 watchdog.apply_watchdog() 호출
      - 발동 시 비중 즉시 조정 (정규 월초 점검과 별개)

    Args:
        daily_prices: 일봉 수정종가 DataFrame.
        monthly_prices: 월말 수정종가 DataFrame.
        params: params.yaml 설정 딕셔너리.

    Returns:
        일별 포트폴리오 가치 DataFrame.
        columns: ['portfolio', 'benchmark(SPY)', 'weights_json']

    Raises:
        NotImplementedError: 미구현.
    """
    raise NotImplementedError


def compute_turnover(
    prev_weights: dict[str, float],
    new_weights: dict[str, float],
) -> float:
    """두 포트폴리오 비중 간 회전율(편도)을 계산한다.

    turnover = 0.5 × Σ|new_w - prev_w| (편도 기준)

    Args:
        prev_weights: 이전 포트폴리오 비중 {티커: 비중}.
        new_weights: 새 포트폴리오 비중 {티커: 비중}.

    Returns:
        편도 회전율 (0.0~1.0).

    Raises:
        NotImplementedError: 미구현.
    """
    raise NotImplementedError


def apply_transaction_cost(
    portfolio_value: float,
    turnover: float,
    cost_bps: float,
) -> float:
    """거래비용을 차감한 포트폴리오 가치를 반환한다.

    cost = portfolio_value × turnover × cost_bps / 10000

    Args:
        portfolio_value: 거래 전 포트폴리오 가치.
        turnover: 편도 회전율.
        cost_bps: 편도 거래비용 (bp 단위, 예: 5).

    Returns:
        거래비용 차감 후 포트폴리오 가치.

    Raises:
        NotImplementedError: 미구현.
    """
    raise NotImplementedError


def assert_no_lookahead(
    signal_date: pd.Timestamp,
    execution_date: pd.Timestamp,
    data_used_up_to: pd.Timestamp,
) -> None:
    """룩어헤드 금지 조건을 검증한다.

    data_used_up_to <= signal_date < execution_date 를 보장한다.
    위반 시 AssertionError를 발생시킨다.

    Args:
        signal_date: 신호 산출 기준일 (직전 월말).
        execution_date: 체결일 (당월 첫 거래일).
        data_used_up_to: 신호 산출에 실제로 사용된 데이터의 최신 날짜.

    Raises:
        AssertionError: 룩어헤드 조건 위반 시.
        NotImplementedError: 미구현.
    """
    raise NotImplementedError
