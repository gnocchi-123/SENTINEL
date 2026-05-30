"""데이터 수집·캐싱 모듈.

yfinance로 일봉 종가를 다운로드하고 CSV에 캐싱한다.
재실행 시 캐시가 존재하면 다운로드를 건너뛰어 결정론적 재현을 보장한다.
상장 전 구간은 NaN으로 유지하며 채우거나 스플라이싱하지 않는다.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import yfinance as yf


# ──────────────────────────────────────────────
# 내부 헬퍼
# ──────────────────────────────────────────────

def _collect_all_tickers(params: dict) -> list[str]:
    """params에서 다운로드할 전체 티커 목록을 중복 없이 반환한다."""
    t = params["tickers"]
    raw: list[str] = (
        [t["market"]]
        + list(t["sectors"])
        + [t["semiconductor"], t["risk_free"], t["defense"], t["vix"]]
    )
    seen: set[str] = set()
    result: list[str] = []
    for ticker in raw:
        if ticker not in seen:
            seen.add(ticker)
            result.append(ticker)
    return result


# ──────────────────────────────────────────────
# 공개 API
# ──────────────────────────────────────────────

def load_prices(params: dict, *, refresh: bool = False) -> pd.DataFrame:
    """캐시 파일이 있으면 로드하고, 없으면 yfinance로 다운로드 후 저장한다.

    Args:
        params: params.yaml 설정 딕셔너리.
        refresh: True이면 캐시를 무시하고 재다운로드한다.

    Returns:
        일봉 수정종가 DataFrame. index=DatetimeIndex(Date), columns=티커명.
        상장 전 구간은 NaN (지수 스플라이싱 미적용).
    """
    cache_path = params["price_cache"]

    if not refresh and Path(cache_path).exists():
        print(f"[데이터] 캐시 로드: {cache_path}")
        df = pd.read_csv(cache_path, index_col=0, parse_dates=True)
        df.index = pd.to_datetime(df.index)
        df.index.name = "Date"
        return df

    tickers = _collect_all_tickers(params)
    start_date = params["start_date"]
    action = "강제 갱신" if refresh else "신규 다운로드"
    print(f"[데이터] {action} — yfinance ({len(tickers)}개 티커, {start_date} ~)")
    return download_prices(tickers, start_date, cache_path)


def download_prices(tickers: list[str], start_date: str, cache_path: str) -> pd.DataFrame:
    """yfinance로 일봉 수정종가를 다운로드하고 CSV로 저장한다.

    Args:
        tickers: 다운로드할 티커 목록 (^VIX 포함 가능).
        start_date: 데이터 시작일 ('YYYY-MM-DD').
        cache_path: 저장할 CSV 파일 경로.

    Returns:
        일봉 수정종가 DataFrame. index=DatetimeIndex, columns=티커명.
        늦은 상장 ETF의 상장 전 구간은 NaN.
    """
    raw = yf.download(tickers, start=start_date, auto_adjust=True, progress=True)

    # yfinance 1.x: MultiIndex (Price, Ticker) — 'Close' 레벨 추출
    if isinstance(raw.columns, pd.MultiIndex):
        prices: pd.DataFrame = raw["Close"].copy()
        if isinstance(prices, pd.Series):
            # 단일 티커가 Series로 반환된 경우
            prices = prices.to_frame(name=tickers[0])
    else:
        prices = raw[["Close"]].rename(columns={"Close": tickers[0]})

    # 타임존 제거 (일봉이므로 tz-naive 유지)
    if getattr(prices.index, "tz", None) is not None:
        prices.index = prices.index.tz_localize(None)
    prices.index = pd.to_datetime(prices.index)
    prices.index.name = "Date"

    # 다운로드 실패 티커는 NaN 열로 보장
    for t in tickers:
        if t not in prices.columns:
            prices[t] = float("nan")

    # 요청 순서 유지, 0→NaN 변환은 하지 않는다 (yfinance 기본값 신뢰)
    prices = prices[tickers]

    prices.to_csv(cache_path)
    print(f"[데이터] 저장 완료: {cache_path}  shape={prices.shape}")
    return prices


def resample_to_month_end(daily: pd.DataFrame) -> pd.DataFrame:
    """일봉 DataFrame을 월말 종가 기준으로 리샘플한다.

    Args:
        daily: 일봉 수정종가 DataFrame.

    Returns:
        월말 종가 DataFrame. index=월말 DatetimeIndex (ME 기준).
        NaN은 그대로 유지 (채우지 않음).
    """
    return daily.resample("ME").last()


def get_first_trading_days(daily_index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """일봉 인덱스에서 매월 첫 번째 거래일을 추출한다.

    Args:
        daily_index: 일봉 DatetimeIndex.

    Returns:
        각 월의 첫 번째 거래일 DatetimeIndex.
    """
    series = daily_index.to_series()
    first_days = series.groupby(daily_index.to_period("M")).first()
    return pd.DatetimeIndex(first_days.values)


def get_last_trading_day_of_month(
    daily_index: pd.DatetimeIndex, year: int, month: int
) -> pd.Timestamp:
    """특정 연월의 마지막 거래일을 반환한다.

    Args:
        daily_index: 일봉 DatetimeIndex.
        year: 연도.
        month: 월.

    Returns:
        해당 월의 마지막 거래일 Timestamp.

    Raises:
        ValueError: 해당 연월의 거래일이 없을 경우.
    """
    mask = (daily_index.year == year) & (daily_index.month == month)
    dates = daily_index[mask]
    if len(dates) == 0:
        raise ValueError(f"거래일 없음: {year}-{month:02d}")
    return dates[-1]


def build_universe(params: dict) -> list[str]:
    """params에서 모멘텀 순위 평가 대상 티커 목록을 반환한다.

    섹터 ETF 11개 + 반도체(SOXX 또는 SMH)를 합친 목록.

    Args:
        params: params.yaml 설정 딕셔너리.

    Returns:
        유니버스 티커 목록 (섹터 11 + 반도체 1 = 최대 12개).
    """
    t = params["tickers"]
    return list(t["sectors"]) + [t["semiconductor"]]


def report_data_integrity(daily: pd.DataFrame, monthly: pd.DataFrame) -> None:
    """티커별 시작·종료일, 총 영업일 수, NaN 개수, ^VIX 존재 여부, 월말 행 수를 출력한다.

    Args:
        daily: 일봉 수정종가 DataFrame.
        monthly: 월말 리샘플 DataFrame.
    """
    print("\n" + "=" * 74)
    print("  데이터 무결성 리포트")
    print("=" * 74)
    header = f"  {'티커':<8}  {'시작일':<12}  {'종료일':<12}  {'영업일':>7}  {'NaN':>6}"
    print(header)
    print("  " + "-" * 57)

    for ticker in daily.columns:
        col = daily[ticker]
        valid = col.dropna()
        if len(valid) > 0:
            start_d = str(valid.index[0].date())
            end_d = str(valid.index[-1].date())
            n_days = len(valid)
        else:
            start_d = end_d = "N/A"
            n_days = 0
        nan_count = int(col.isna().sum())
        print(f"  {ticker:<8}  {start_d:<12}  {end_d:<12}  {n_days:>7,}  {nan_count:>6,}")

    print()
    vix_series = daily.get("^VIX")
    vix_ok = vix_series is not None and bool(vix_series.notna().any())
    print(f"  ^VIX 존재 여부     : {'YES' if vix_ok else 'NO'}")
    print(f"  월말 리샘플 행 수  : {len(monthly):,}")
    print("=" * 74 + "\n")


# ──────────────────────────────────────────────
# 단독 실행 (무결성 확인)
# ──────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    import sys
    from pathlib import Path as _Path

    import yaml

    parser = argparse.ArgumentParser(description="SENTINEL 데이터 레이어 — 무결성 확인")
    parser.add_argument("--params", default="params.yaml", help="파라미터 파일 경로")
    parser.add_argument("--refresh", action="store_true", help="캐시 무시하고 재다운로드")
    args = parser.parse_args()

    params_path = _Path(args.params)
    if not params_path.exists():
        print(f"[오류] params 파일 없음: {params_path}", file=sys.stderr)
        sys.exit(1)

    with params_path.open(encoding="utf-8") as f:
        params = yaml.safe_load(f)

    daily = load_prices(params, refresh=args.refresh)
    monthly = resample_to_month_end(daily)
    report_data_integrity(daily, monthly)
