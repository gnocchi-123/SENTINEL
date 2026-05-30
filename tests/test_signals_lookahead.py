"""룩어헤드 방지 단위 테스트.

as_of_month_end 이후 데이터를 NaN 또는 임의 노이즈로 오염시켜도
compute_target_weights 결과가 변하지 않음을 검증한다.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
import yaml

from sentinel.data import load_prices, resample_to_month_end
from sentinel.signals import compute_target_weights


# ── 픽스처 ────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def params():
    with open("params.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="module")
def data(params):
    return load_prices(params)


@pytest.fixture(scope="module")
def month_ends(data):
    return resample_to_month_end(data).index


# ── 테스트 시점: 다양한 시장 국면을 커버 ─────────────────────
AS_OF_LABELS = [
    ("2007-06", "금융위기 직전 강세장"),
    ("2008-09", "리먼 붕괴 직전"),
    ("2008-11", "금융위기 저점권"),
    ("2009-06", "반등 초입"),
    ("2020-02", "COVID 직전"),
    ("2020-03", "COVID 급락"),
    ("2022-09", "금리 인상 약세장"),
    ("2010-06", "중간 평범 시점"),
]


def _find_month_end(month_ends: pd.DatetimeIndex, ym: str) -> pd.Timestamp:
    """'YYYY-MM' 문자열로 해당 월의 month-end Timestamp를 반환한다."""
    year, month = int(ym[:4]), int(ym[5:7])
    matches = month_ends[(month_ends.year == year) & (month_ends.month == month)]
    assert len(matches) == 1, f"{ym}에 해당하는 월말 없음"
    return matches[0]


@pytest.mark.parametrize("ym,label", AS_OF_LABELS)
def test_no_lookahead_nan(data, params, month_ends, ym, label):
    """as_of 이후 전체를 NaN으로 덮어써도 신호가 달라지지 않아야 한다. ({label})"""
    as_of = _find_month_end(month_ends, ym)

    signal_original = compute_target_weights(data, as_of, params)

    data_corrupted = data.copy()
    data_corrupted.loc[data_corrupted.index > as_of] = np.nan

    signal_corrupted = compute_target_weights(data_corrupted, as_of, params)

    assert signal_original == signal_corrupted, (
        f"[{ym} / {label}] 룩어헤드 의심\n"
        f"  원본:  {signal_original}\n"
        f"  NaN오염: {signal_corrupted}"
    )


@pytest.mark.parametrize("ym,label", AS_OF_LABELS)
def test_no_lookahead_random_noise(data, params, month_ends, ym, label):
    """as_of 이후에 임의 배율 노이즈를 곱해도 신호가 달라지지 않아야 한다. ({label})"""
    as_of = _find_month_end(month_ends, ym)

    signal_original = compute_target_weights(data, as_of, params)

    rng = np.random.default_rng(seed=42)
    data_noisy = data.copy()
    future = data_noisy.index > as_of
    n_rows = int(future.sum())
    n_cols = data_noisy.shape[1]
    noise = rng.uniform(0.05, 20.0, size=(n_rows, n_cols))
    data_noisy.loc[future] = data_noisy.loc[future].to_numpy() * noise

    signal_noisy = compute_target_weights(data_noisy, as_of, params)

    assert signal_original == signal_noisy, (
        f"[{ym} / {label}] 룩어헤드 의심\n"
        f"  원본:    {signal_original}\n"
        f"  노이즈:  {signal_noisy}"
    )


def test_weights_sum_to_one(data, params, month_ends):
    """모든 샘플 시점에서 비중 합계가 1.0이어야 한다."""
    for ym, _ in AS_OF_LABELS:
        as_of = _find_month_end(month_ends, ym)
        weights = compute_target_weights(data, as_of, params)
        total = sum(weights.values())
        assert abs(total - 1.0) < 1e-9, (
            f"[{ym}] 비중 합계 {total:.6f} ≠ 1.0  weights={weights}"
        )


def test_defense_on_crisis_month(data, params, month_ends):
    """금융위기 한복판(2008-11)에는 방어자산이 100%여야 한다."""
    as_of = _find_month_end(month_ends, "2008-11")
    weights = compute_target_weights(data, as_of, params)
    defense = params["tickers"]["defense"]
    assert weights == {defense: 1.0}, (
        f"2008-11 방어 미전환: {weights}"
    )
