"""데이터 수집·캐싱 모듈.

yfinance로 일봉 종가를 다운로드하고 CSV에 캐싱한다.
재실행 시 캐시가 존재하면 다운로드를 건너뛰어 결정론적 재현을 보장한다.
"""

from __future__ import annotations

import pandas as pd


def load_prices(params: dict) -> pd.DataFrame:
    """캐시 파일이 있으면 로드하고, 없으면 yfinance로 다운로드 후 저장한다.

    Args:
        params: params.yaml에서 로드한 설정 딕셔너리.
            - tickers: 시장·섹터·반도체·무위험·방어·VIX 티커 정보
            - start_date: 데이터 시작일 (str, 'YYYY-MM-DD')
            - price_cache: 캐시 CSV 경로 (str)

    Returns:
        일봉 수정종가 DataFrame. index=DatetimeIndex, columns=티커명.
        상장 전 구간은 NaN (지수 스플라이싱 미적용).

    Raises:
        NotImplementedError: 미구현.
    """
    raise NotImplementedError


def download_prices(tickers: list[str], start_date: str, cache_path: str) -> pd.DataFrame:
    """yfinance로 일봉 수정종가를 다운로드하고 CSV로 저장한다.

    Args:
        tickers: 다운로드할 티커 목록.
        start_date: 데이터 시작일 ('YYYY-MM-DD').
        cache_path: 저장할 CSV 파일 경로.

    Returns:
        일봉 수정종가 DataFrame. index=DatetimeIndex, columns=티커명.

    Raises:
        NotImplementedError: 미구현.
    """
    raise NotImplementedError


def resample_to_month_end(daily: pd.DataFrame) -> pd.DataFrame:
    """일봉 DataFrame을 월말 종가 기준으로 리샘플한다.

    Args:
        daily: 일봉 수정종가 DataFrame.

    Returns:
        월말 종가 DataFrame. index=월말 DatetimeIndex.

    Raises:
        NotImplementedError: 미구현.
    """
    raise NotImplementedError


def get_first_trading_days(daily_index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """일봉 인덱스에서 매월 첫 번째 거래일을 추출한다.

    점검일(리밸런싱 트리거) 목록 산출에 사용.

    Args:
        daily_index: 일봉 DatetimeIndex.

    Returns:
        각 월의 첫 번째 거래일 DatetimeIndex.

    Raises:
        NotImplementedError: 미구현.
    """
    raise NotImplementedError


def get_last_trading_day_of_month(daily_index: pd.DatetimeIndex, year: int, month: int) -> pd.Timestamp:
    """특정 연월의 마지막 거래일을 반환한다.

    신호 산출 기준일(직전 월말) 확정에 사용.

    Args:
        daily_index: 일봉 DatetimeIndex.
        year: 연도.
        month: 월.

    Returns:
        해당 월의 마지막 거래일 Timestamp.

    Raises:
        NotImplementedError: 미구현.
    """
    raise NotImplementedError


def build_universe(params: dict) -> list[str]:
    """params에서 모멘텀 순위 평가 대상 티커 목록을 반환한다.

    섹터 ETF 11개 + 반도체(SOXX 또는 SMH)를 합친 목록.
    SOXX/XLK 중복은 그대로 허용 (별도 처리 없음).

    Args:
        params: params.yaml 설정 딕셔너리.

    Returns:
        유니버스 티커 목록.

    Raises:
        NotImplementedError: 미구현.
    """
    raise NotImplementedError
