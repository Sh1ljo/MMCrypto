import math

import polars as pl
import pytest

from mmlab.analytics.metrics import NS_PER_HOUR, compute_metrics, infer_fills


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


def test_sharpe_and_drawdown_on_known_curve():
    metrics = compute_metrics(hourly_frame([0.0, 2.0, 1.0, 4.0]), EMPTY_FILLS, 0.01)
    assert metrics.net_pnl == 4.0
    assert metrics.max_drawdown == 1.0
    expected = 1.0 / math.sqrt(10 / 3) * math.sqrt(24 * 365)
    assert metrics.sharpe_hourly_annualized == pytest.approx(expected)


def test_sharpe_is_none_for_flat_curve():
    metrics = compute_metrics(hourly_frame([0.0, 0.0, 0.0]), EMPTY_FILLS, 0.01)
    assert metrics.sharpe_hourly_annualized is None


def test_gross_pnl_adds_back_fees():
    frame = hourly_frame([0.0, 1.0]).with_columns(pl.Series("fee", [0.0, 0.25]))
    metrics = compute_metrics(frame, EMPTY_FILLS, 0.01)
    assert metrics.gross_pnl == metrics.net_pnl + 0.25


def test_infer_fills_prices_buy_and_sell():
    raw = pl.DataFrame(
        {
            "ts": [0, 1, 2, 3],
            "mid": [100.0, 100.0, 101.0, 101.0],
            "position": [0.0, 1.0, 1.0, 0.0],
            "trading_volume": [0.0, 1.0, 1.0, 2.0],
            "trading_value": [0.0, 99.5, 99.5, 200.5],
        }
    )
    fills = infer_fills(raw)
    assert fills["side"].to_list() == [1, -1]
    assert fills["price"].to_list() == [99.5, 101.0]
    assert fills["mid_at_fill"].to_list() == [100.0, 101.0]
