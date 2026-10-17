import polars as pl
import pytest

from mmlab.analytics.markouts import HORIZONS_MS, MARKOUT_SCHEMA, markouts

NS_PER_S = 1_000_000_000


def fills_frame(rows: list[tuple[float, int, float]]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "ts": [round(second * NS_PER_S) for second, _, _ in rows],
            "side": [side for _, side, _ in rows],
            "price": [price for _, _, price in rows],
        },
        schema={"ts": pl.Int64, "side": pl.Int8, "price": pl.Float64},
    )


def mids_frame(rows: list[tuple[float, float]]) -> pl.DataFrame:
    return pl.DataFrame(
        {"ts": [round(second * NS_PER_S) for second, _ in rows], "mid": [m for _, m in rows]},
        schema={"ts": pl.Int64, "mid": pl.Float64},
    )


def one_horizon(fills, mids, end_second: float, horizon_ms: int) -> dict:
    curve = markouts(fills, mids, round(end_second * NS_PER_S), (horizon_ms,))
    return curve.row(0, named=True)


def test_a_buy_gains_when_the_mid_rises_and_a_sell_gains_when_it_falls():
    fills = fills_frame([(0, 1, 100.0), (0, -1, 102.0)])
    mids = mids_frame([(0, 100.0), (1, 101.0)])

    row = one_horizon(fills, mids, end_second=1, horizon_ms=1_000)

    assert row["fills"] == 2
    assert row["avg_markout"] == pytest.approx(1.0)
    assert row["avg_markout_bps"] == pytest.approx((1 / 100 + 1 / 102) / 2 * 1e4)


def test_a_fill_the_market_moves_against_has_a_negative_markout():
    fills = fills_frame([(0, 1, 100.0), (0, -1, 100.0)])
    mids = mids_frame([(0, 100.0), (1, 101.0)])

    row = one_horizon(fills, mids, end_second=1, horizon_ms=1_000)

    assert row["avg_markout"] == pytest.approx(0.0)
    assert row["avg_markout_bps"] == pytest.approx(0.0)


def test_the_mid_used_is_the_last_one_at_or_before_the_horizon():
    fills = fills_frame([(0, 1, 100.0)])
    mids = mids_frame([(0, 100.0), (1, 101.0), (2, 99.0)])

    row = one_horizon(fills, mids, end_second=2, horizon_ms=1_500)

    assert row["avg_markout"] == pytest.approx(1.0)


def test_a_mid_exactly_at_the_horizon_counts():
    fills = fills_frame([(0, 1, 100.0)])
    mids = mids_frame([(0, 100.0), (1, 101.0)])

    assert one_horizon(fills, mids, end_second=1, horizon_ms=1_000)["avg_markout"] == 1.0


def test_fills_whose_horizon_passes_the_end_of_the_data_are_left_out():
    fills = fills_frame([(0, 1, 100.0), (2, 1, 99.0)])
    mids = mids_frame([(0, 100.0), (1, 101.0), (2, 99.0), (3, 100.0)])

    assert one_horizon(fills, mids, end_second=3, horizon_ms=1_000)["fills"] == 2
    assert one_horizon(fills, mids, end_second=3, horizon_ms=2_000)["fills"] == 1


def test_a_static_book_still_scores_fills_because_the_end_is_given():
    fills = fills_frame([(5, 1, 100.0)])
    mids = mids_frame([(0, 100.05)])

    row = one_horizon(fills, mids, end_second=60, horizon_ms=10_000)

    assert row["fills"] == 1
    assert row["avg_markout"] == pytest.approx(0.05)


def test_fills_with_no_direction_are_ignored():
    fills = fills_frame([(0, 0, 100.0), (0, 1, 100.0)])
    mids = mids_frame([(0, 100.0), (1, 101.0)])

    assert one_horizon(fills, mids, end_second=1, horizon_ms=1_000)["fills"] == 1


def test_standard_error_is_the_spread_of_the_fills_over_the_square_root_of_their_count():
    fills = fills_frame([(0, 1, 100.0), (0, -1, 100.0)])
    mids = mids_frame([(0, 100.0), (1, 101.0)])

    row = one_horizon(fills, mids, end_second=1, horizon_ms=1_000)

    assert row["stderr_bps"] == pytest.approx(100.0)


def test_one_fill_has_a_markout_but_no_standard_error():
    row = one_horizon(fills_frame([(0, 1, 100.0)]), mids_frame([(0, 100.0), (1, 101.0)]), 1, 1_000)

    assert row["avg_markout_bps"] == pytest.approx(100.0)
    assert row["stderr_bps"] is None


def test_no_fills_give_a_row_of_nulls_not_an_error():
    row = one_horizon(fills_frame([]), mids_frame([(0, 100.0)]), end_second=1, horizon_ms=100)

    assert row == {
        "horizon_ms": 100,
        "fills": 0,
        "avg_markout": None,
        "avg_markout_bps": None,
        "stderr_bps": None,
    }


def test_default_curve_has_every_horizon_in_order():
    curve = markouts(fills_frame([(0, 1, 100.0)]), mids_frame([(0, 100.0)]), 100 * NS_PER_S)

    assert curve["horizon_ms"].to_list() == list(HORIZONS_MS)
    assert curve.schema == pl.Schema(MARKOUT_SCHEMA)
