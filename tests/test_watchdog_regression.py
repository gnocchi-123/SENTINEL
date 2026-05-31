"""회귀 테스트 — watchdog_enabled=false 시 단계 4와 결과가 비트 단위로 동일해야 한다.

워치독이 비활성화된 경우, 파라미터를 어떻게 바꿔도 (발동 조건을 극단적으로 설정해도)
자산곡선 및 거래 로그의 수치가 변하면 안 된다.
"""

from __future__ import annotations

import copy

import pandas as pd
import pytest
import yaml

from sentinel.data import load_prices, resample_to_month_end
from sentinel.engine import run_backtest


# ── fixture: 데이터와 기준 파라미터 ────────────────────────────

@pytest.fixture(scope="module")
def base_params():
    with open("params.yaml") as f:
        p = yaml.safe_load(f)
    assert not p.get("watchdog_enabled", False), (
        "params.yaml의 watchdog_enabled는 false여야 합니다 (기본값 확인)"
    )
    return p


@pytest.fixture(scope="module")
def price_data(base_params):
    daily = load_prices(base_params)
    monthly = resample_to_month_end(daily)
    return daily, monthly


@pytest.fixture(scope="module")
def baseline(base_params, price_data):
    """watchdog_enabled=False 기본 파라미터로 실행한 결과 (단계 4와 동일)."""
    daily, monthly = price_data
    equity, log = run_backtest(daily, monthly, base_params)
    return equity, log


# ── 헬퍼: 로그에서 정규 월별 행만 추출 ──────────────────────────

def _monthly_rows(log_df: pd.DataFrame) -> pd.DataFrame:
    if "source" in log_df.columns:
        return log_df[log_df["source"] == "monthly"]
    return log_df


# ══════════════════════════════════════════════════════════════
# 테스트 1 — disabled는 파라미터와 무관하게 동일
# ══════════════════════════════════════════════════════════════

def test_watchdog_disabled_extreme_params_no_effect(base_params, price_data, baseline):
    """watchdog_enabled=False면 발동 조건이 극단적이어도 결과가 동일해야 한다."""
    daily, monthly = price_data
    equity_base, log_base = baseline

    # 극단 파라미터: 조금이라도 빠지면 VIX 1 이상이면 발동 — 하지만 disabled
    params_extreme = copy.deepcopy(base_params)
    params_extreme["watchdog_enabled"] = False
    params_extreme["watchdog_drawdown_threshold"] = -0.001
    params_extreme["watchdog_vix_threshold"] = 1.0
    params_extreme["watchdog_derisk_fraction"] = 1.0
    params_extreme["watchdog_high_lookback_days"] = 5

    equity_ext, log_ext = run_backtest(daily, monthly, params_extreme)

    # ── equity_curve: 비트 단위 동일 ─────────────────────────
    pd.testing.assert_series_equal(
        equity_base, equity_ext,
        check_names=True, rtol=0, atol=0,
        obj="equity_curve (watchdog disabled vs extreme params disabled)",
    )

    # ── 정규 월별 로그: 핵심 수치 동일 ──────────────────────────
    m_base = _monthly_rows(log_base)
    m_ext = _monthly_rows(log_ext)

    for col in ("traded", "turnover", "cost_applied", "pv_before", "pv_after"):
        pd.testing.assert_series_equal(
            m_base[col].reset_index(drop=True),
            m_ext[col].reset_index(drop=True),
            rtol=0, atol=0,
            obj=f"monthly_log[{col}]",
        )


# ══════════════════════════════════════════════════════════════
# 테스트 2 — disabled=False vs enabled=False explicit
# ══════════════════════════════════════════════════════════════

def test_watchdog_explicit_false_identical_to_default(base_params, price_data, baseline):
    """watchdog_enabled을 명시적으로 False로 설정해도 기본 결과와 동일해야 한다."""
    daily, monthly = price_data
    equity_base, log_base = baseline

    params_explicit = copy.deepcopy(base_params)
    params_explicit["watchdog_enabled"] = False

    equity_exp, log_exp = run_backtest(daily, monthly, params_explicit)

    pd.testing.assert_series_equal(
        equity_base, equity_exp,
        rtol=0, atol=0,
        obj="equity_curve (default vs explicit watchdog_enabled=False)",
    )

    m_base = _monthly_rows(log_base)
    m_exp = _monthly_rows(log_exp)

    pd.testing.assert_series_equal(
        m_base["pv_after"].reset_index(drop=True),
        m_exp["pv_after"].reset_index(drop=True),
        rtol=0, atol=0,
        obj="monthly_log.pv_after",
    )


# ══════════════════════════════════════════════════════════════
# 테스트 3 — enabled=True 시 워치독 발동 로그 구조 검증
# ══════════════════════════════════════════════════════════════

def test_watchdog_enabled_fires_in_equity_periods(base_params, price_data):
    """watchdog_enabled=True 시 주식 보유 구간에서 워치독이 발동되어야 한다.

    2008년은 포트폴리오가 이미 100% AGG(방어)여서 주식이 없으므로 워치독 미발동.
    (워치독은 주식 보유분을 디리스크하는 장치 — 방어자산만 있으면 발동 불필요)
    실제 발동 구간: 2020-02 (V자 직전), 2022-02/04 (추세 하락 구간).
    """
    daily, monthly = price_data

    params_wd = copy.deepcopy(base_params)
    params_wd["watchdog_enabled"] = True

    equity_wd, log_wd = run_backtest(daily, monthly, params_wd)

    assert "source" in log_wd.columns, "워치독 활성 시 source 컬럼이 있어야 함"
    wd_events = log_wd[log_wd["source"] == "watchdog"]

    assert len(wd_events) > 0, "watchdog_enabled=True 시 전 기간에 최소 1회 발동되어야 함"

    defense = base_params["tickers"]["defense"]

    # 모든 발동 이벤트의 공통 불변 조건
    for date, row in wd_events.iterrows():
        assert defense in row["holdings"], (
            f"{date.date()}: 워치독 발동 후 {defense}가 포함되어야 함"
        )
        assert row["traded"] is True, f"{date.date()}: traded=True이어야 함"
        assert row["turnover"] > 0, f"{date.date()}: turnover > 0이어야 함"
        assert row["cost_applied"] > 0, f"{date.date()}: cost_applied > 0이어야 함"
        # derisk_fraction=0.5이므로 발동 후 AGG ≈ 50%, 주식 ≈ 50%
        agg_w = row["target_weights"].get(defense, 0.0)
        assert 0.40 < agg_w < 0.65, (
            f"{date.date()}: AGG 비중({agg_w:.1%})이 50% 근방이어야 함"
        )

    # 2020년 구간 발동 확인
    wd_2020 = wd_events[
        (wd_events.index >= "2020-01-01") & (wd_events.index <= "2020-12-31")
    ]
    assert len(wd_2020) > 0, "2020년에 워치독 발동이 있어야 함"

    # 2022년 구간 발동 확인
    wd_2022 = wd_events[
        (wd_events.index >= "2022-01-01") & (wd_events.index <= "2022-12-31")
    ]
    assert len(wd_2022) > 0, "2022년에 워치독 발동이 있어야 함"

    # 2008년은 포트폴리오가 이미 100% 방어(AGG)여서 발동 없어야 함
    wd_2008 = wd_events[
        (wd_events.index >= "2007-01-01") & (wd_events.index <= "2010-01-01")
    ]
    # 2009-11 이전 구간은 방어여서 발동 불가, 2010-05에 발동 가능
    wd_pre2009 = wd_events[wd_events.index < "2009-11-01"]
    assert len(wd_pre2009) == 0, (
        "2009-11(첫 ON) 이전은 포트폴리오가 100% AGG이므로 워치독 발동 없어야 함"
    )


# ══════════════════════════════════════════════════════════════
# 테스트 4 — derisk_weights 단위 테스트
# ══════════════════════════════════════════════════════════════

def test_derisk_weights_basic():
    """derisk_weights가 비중 합계 1.0을 보장해야 한다."""
    from sentinel.watchdog import derisk_weights

    # 균등 배분 → 50% 디리스크
    weights = {"XLK": 0.5, "XLV": 0.5}
    result = derisk_weights(weights, "AGG", 0.5)

    assert abs(sum(result.values()) - 1.0) < 1e-10, "비중 합계는 1.0이어야 함"
    assert abs(result.get("AGG", 0) - 0.5) < 1e-10, "AGG 비중은 0.5이어야 함"
    assert abs(result.get("XLK", 0) - 0.25) < 1e-10
    assert abs(result.get("XLV", 0) - 0.25) < 1e-10


def test_derisk_weights_100pct_derisk():
    """100% 디리스크 시 전량 방어자산으로 이동해야 한다."""
    from sentinel.watchdog import derisk_weights

    weights = {"XLK": 0.33, "XLY": 0.33, "XLE": 0.34}
    result = derisk_weights(weights, "AGG", 1.0)

    assert abs(sum(result.values()) - 1.0) < 1e-10
    # 모든 주식 포지션이 0이 되거나 사라져야 함
    for t in ("XLK", "XLY", "XLE"):
        assert result.get(t, 0.0) < 1e-10, f"{t}는 0에 가까워야 함"
    assert abs(result.get("AGG", 0.0) - 1.0) < 1e-10, "AGG가 100%이어야 함"


def test_derisk_weights_already_in_defense():
    """이미 100% 방어자산이면 디리스크 후에도 같아야 한다."""
    from sentinel.watchdog import derisk_weights

    weights = {"AGG": 1.0}
    result = derisk_weights(weights, "AGG", 0.5)

    assert abs(sum(result.values()) - 1.0) < 1e-10
    assert abs(result.get("AGG", 0) - 1.0) < 1e-10, "방어자산 비중 유지"


def test_derisk_weights_mixed_portfolio():
    """주식+방어 혼합 포트폴리오에서 디리스크가 올바르게 동작해야 한다."""
    from sentinel.watchdog import derisk_weights

    # 50% 주식, 50% AGG → 0.5 디리스크
    weights = {"XLK": 0.25, "XLV": 0.25, "AGG": 0.5}
    result = derisk_weights(weights, "AGG", 0.5)

    assert abs(sum(result.values()) - 1.0) < 1e-10
    # 주식 총계: 0.5 → 0.25 (50% 감소)
    equity_after = result.get("XLK", 0) + result.get("XLV", 0)
    assert abs(equity_after - 0.25) < 1e-10, f"주식 총계 = {equity_after}, 0.25 기대"
    # AGG: 0.5 + 0.5*0.5 = 0.75
    assert abs(result.get("AGG", 0) - 0.75) < 1e-10, f"AGG = {result.get('AGG')}, 0.75 기대"
