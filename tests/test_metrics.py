import math

import polars as pl
import pytest

from mmlab.analytics.markouts import MARKOUT_SCHEMA
from mmlab.analytics.metrics import NS_PER_HOUR, NS_PER_S, compute_metrics


def hourly_frame(equity: list[float]) -> pl.DataFrame:
    count = len(equity)
    return pl.DataFrame(
        {
            "ts": [hour * NS_PER_HOUR for hour in range(count)],
            "mid": [100.0] * count,
            "bid_quote": [99.9] * count,
            "ask_quote": [100.1] * count,
            "position": [0.0] * count,
            "balance": equity,
            "fee": [0.0] * count,
            "equity": equity,
            "num_trades": [0] * count,
        }
    )


EMPTY_FILLS = pl.DataFrame(
    schema={
        "ts": pl.Int64,
        "side": pl.Int8,
        "price": pl.Float64,
        "qty": pl.Float64,
        "mid_at_fill": pl.Float64,
    }
)


NO_CURVE = pl.DataFrame(
    {
        "horizon_ms": [1_000, 10_000],
        "fills": [0, 0],
        "avg_markout": [None, None],
        "avg_markout_bps": [None, None],
        "stderr_bps": [None, None],
    },
    schema=MARKOUT_SCHEMA,
)


def position_frame(positions: list[float]) -> pl.DataFrame:
    count = len(positions)
    return hourly_frame([0.0] * count).with_columns(
        pl.Series("ts", [step * NS_PER_S for step in range(count)]),
        pl.Series("position", positions),
    )


def half_life(positions: list[float]) -> float | None:
    metrics = compute_metrics(position_frame(positions), EMPTY_FILLS, 0.01, NO_CURVE)
    return metrics.inventory_half_life_s


def test_sharpe_and_drawdown_on_known_curve():
    metrics = compute_metrics(hourly_frame([0.0, 2.0, 1.0, 4.0]), EMPTY_FILLS, 0.01, NO_CURVE)
    assert metrics.net_pnl == 4.0
    assert metrics.max_drawdown == 1.0
    expected = 1.0 / math.sqrt(10 / 3) * math.sqrt(24 * 365)
    assert metrics.sharpe_hourly_annualized == pytest.approx(expected)


def test_sharpe_is_none_for_flat_curve():
    metrics = compute_metrics(hourly_frame([0.0, 0.0, 0.0]), EMPTY_FILLS, 0.01, NO_CURVE)
    assert metrics.sharpe_hourly_annualized is None


def test_gross_pnl_adds_back_fees():
    frame = hourly_frame([0.0, 1.0]).with_columns(pl.Series("fee", [0.0, 0.25]))
    metrics = compute_metrics(frame, EMPTY_FILLS, 0.01, NO_CURVE)
    assert metrics.gross_pnl == metrics.net_pnl + 0.25


def test_markout_kpis_come_from_the_curve():
    curve = NO_CURVE.with_columns(pl.Series("avg_markout_bps", [-1.5, -3.0]))
    metrics = compute_metrics(hourly_frame([0.0, 1.0]), EMPTY_FILLS, 0.01, curve)
    assert (metrics.avg_markout_1s_bps, metrics.avg_markout_10s_bps) == (-1.5, -3.0)


def test_half_life_is_the_time_for_inventory_to_halve():
    assert half_life([0.0, 4.0, 3.0, 2.0, 0.0]) == 2.0


def test_half_life_is_the_median_over_every_inventory_increase():
    assert half_life([0.0, 2.0, 1.0, 0.0, 2.0, 2.0, 2.0, 1.0, 0.0]) == 2.0


def test_half_life_ignores_steps_that_reduce_inventory():
    assert half_life([0.0, 0.0, 0.0]) is None


def test_half_life_is_none_when_inventory_never_halves():
    assert half_life([0.0, 4.0, 4.0, 4.0]) is None


def test_half_life_treats_a_short_position_like_a_long_one():
    assert half_life([0.0, -4.0, -3.0, -1.0]) == 2.0
