"""성과 지표 산출 모듈.

평가 우선순위: MDD·하락장 구간 성과 → 샤프/소르티노 → CAGR.
과최적화(curve fitting) 위험과 "과거 성과는 미래 수익을 보장하지 않는다"는
점을 항상 결과와 함께 전달한다.
"""

from __future__ import annotations

import pandas as pd


def compute_cagr(portfolio_values: pd.Series) -> float:
    """연복리 수익률(CAGR)을 계산한다.

    Args:
        portfolio_values: 일별 포트폴리오 가치 Series (index=DatetimeIndex).

    Returns:
        CAGR (소수점, 예: 0.08 = 8%).

    Raises:
        NotImplementedError: 미구현.
    """
    raise NotImplementedError


def compute_max_drawdown(portfolio_values: pd.Series) -> float:
    """최대낙폭(MDD)을 계산한다.

    MDD = min((V_t - peak_t) / peak_t) for all t

    Args:
        portfolio_values: 일별 포트폴리오 가치 Series.

    Returns:
        MDD (음수 소수점, 예: -0.35 = -35%).

    Raises:
        NotImplementedError: 미구현.
    """
    raise NotImplementedError


def compute_sharpe(
    portfolio_values: pd.Series,
    risk_free_annual: float = 0.0,
    periods_per_year: int = 252,
) -> float:
    """샤프 비율을 계산한다.

    Args:
        portfolio_values: 일별 포트폴리오 가치 Series.
        risk_free_annual: 연환산 무위험 수익률 (소수점).
        periods_per_year: 연간 거래일 수 (기본 252).

    Returns:
        샤프 비율.

    Raises:
        NotImplementedError: 미구현.
    """
    raise NotImplementedError


def compute_sortino(
    portfolio_values: pd.Series,
    risk_free_annual: float = 0.0,
    periods_per_year: int = 252,
) -> float:
    """소르티노 비율을 계산한다. 하방 변동성만을 위험으로 사용.

    Args:
        portfolio_values: 일별 포트폴리오 가치 Series.
        risk_free_annual: 연환산 무위험 수익률 (소수점).
        periods_per_year: 연간 거래일 수 (기본 252).

    Returns:
        소르티노 비율.

    Raises:
        NotImplementedError: 미구현.
    """
    raise NotImplementedError


def compute_drawdown_periods(
    portfolio_values: pd.Series,
    benchmark_values: pd.Series,
    bear_markets: list[tuple[str, str]] | None = None,
) -> pd.DataFrame:
    """하락장 구간별 성과를 비교한다.

    bear_markets가 None이면 주요 하락장(2000~02, 2008~09, 2020-03, 2022)
    구간을 기본값으로 사용한다.

    Args:
        portfolio_values: SENTINEL 일별 포트폴리오 가치.
        benchmark_values: 벤치마크(SPY) 일별 가치.
        bear_markets: [(시작일, 종료일)] 하락장 구간 목록.

    Returns:
        하락장 구간별 SENTINEL vs 벤치마크 수익률 비교 DataFrame.

    Raises:
        NotImplementedError: 미구현.
    """
    raise NotImplementedError


def compute_summary(
    portfolio_values: pd.Series,
    benchmark_values: pd.Series,
    params: dict,
) -> dict[str, float]:
    """SENTINEL vs 벤치마크 전체 성과 요약을 반환한다.

    반환 항목: CAGR, MDD, Sharpe, Sortino, 연간 거래 횟수(avg).

    Args:
        portfolio_values: SENTINEL 일별 포트폴리오 가치.
        benchmark_values: 벤치마크(SPY) 일별 가치.
        params: params.yaml 설정 딕셔너리.

    Returns:
        {지표명: 값} 딕셔너리.

    Raises:
        NotImplementedError: 미구현.
    """
    raise NotImplementedError
