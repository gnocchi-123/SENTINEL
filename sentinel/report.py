"""결과 시각화·보고 모듈.

백테스트 수행 시 반드시 과최적화 경고와 면책 문구를 함께 출력한다.
"""

from __future__ import annotations

import pandas as pd


DISCLAIMER = (
    "\n[주의] 백테스트 결과는 과거 데이터 기반 시뮬레이션입니다.\n"
    "과최적화(curve fitting) 위험이 있으며, 과거 성과는 미래 수익을 보장하지 않습니다.\n"
    "이 결과는 투자 자문이 아닌 방법론 검증 목적으로만 사용하십시오.\n"
)


def print_summary(summary: dict[str, float], params: dict) -> None:
    """성과 요약 테이블과 적용된 파라미터를 출력한다.

    항상 DISCLAIMER를 함께 출력한다.

    Args:
        summary: metrics.compute_summary()의 반환값.
        params: params.yaml 설정 딕셔너리.

    Raises:
        NotImplementedError: 미구현.
    """
    raise NotImplementedError


def plot_equity_curve(
    portfolio_values: pd.Series,
    benchmark_values: pd.Series,
    output_path: str | None = None,
) -> None:
    """SENTINEL과 벤치마크(SPY 매수보유)의 자산곡선을 플롯한다.

    output_path가 None이면 화면에 표시, str이면 파일로 저장.

    Args:
        portfolio_values: SENTINEL 일별 포트폴리오 가치.
        benchmark_values: 벤치마크(SPY) 일별 가치.
        output_path: 저장 경로 (None=화면 표시).

    Raises:
        NotImplementedError: 미구현.
    """
    raise NotImplementedError


def plot_drawdown(
    portfolio_values: pd.Series,
    benchmark_values: pd.Series,
    output_path: str | None = None,
) -> None:
    """낙폭(drawdown) 차트를 플롯한다.

    Args:
        portfolio_values: SENTINEL 일별 포트폴리오 가치.
        benchmark_values: 벤치마크(SPY) 일별 가치.
        output_path: 저장 경로 (None=화면 표시).

    Raises:
        NotImplementedError: 미구현.
    """
    raise NotImplementedError


def plot_sector_allocation(
    weights_history: pd.DataFrame,
    output_path: str | None = None,
) -> None:
    """월별 섹터 비중 변화를 스택 영역 차트로 플롯한다.

    Args:
        weights_history: 월별 포트폴리오 비중 DataFrame (index=날짜, columns=티커).
        output_path: 저장 경로 (None=화면 표시).

    Raises:
        NotImplementedError: 미구현.
    """
    raise NotImplementedError


def print_params(params: dict) -> None:
    """적용된 파라미터를 읽기 좋은 형태로 출력한다.

    Args:
        params: params.yaml 설정 딕셔너리.

    Raises:
        NotImplementedError: 미구현.
    """
    raise NotImplementedError
