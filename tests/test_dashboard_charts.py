import numpy as np
import polars as pl
import pytest

from dashboard.charts import (
    DARK,
    LIGHT,
    colors_for,
    distribution_figure,
    ladder_figure,
    run_figure,
)
from mmlab.run import run_backtest
from tests.synthetic_events import synthetic_config, write_synthetic_day

TICK_SIZE = 0.1
LOT_SIZE = 0.001


@pytest.fixture(scope="module")
def tables(tmp_path_factory) -> tuple[pl.DataFrame, pl.DataFrame]:
    data = write_synthetic_day(tmp_path_factory.mktemp("data") / "day.npz")
    run_dir = run_backtest(synthetic_config(data), tmp_path_factory.mktemp("runs"))
    return (
        pl.read_parquet(run_dir / "timeseries.parquet"),
        pl.read_parquet(run_dir / "fills.parquet"),
    )


def traces_by_name(figure) -> dict:
    return {trace.name: trace for trace in figure.data}


def test_theme_type_picks_the_matching_palette():
    assert colors_for("dark") is DARK
    assert colors_for("light") is LIGHT
    assert colors_for(None) is LIGHT


def test_run_figure_has_one_trace_per_series_with_matching_lengths(tables):
    timeseries, fills = tables

    traces = traces_by_name(run_figure(timeseries, fills, 0.01, LIGHT))

    for name in ("Mid", "Bid quote", "Ask quote", "Position", "Net equity", "Equity before fees"):
        assert len(traces[name].x) == timeseries.height
    fill_rows = sum(len(traces[n].x) for n in traces if n.endswith("fills"))
    assert fill_rows == fills.height


def test_fills_are_split_by_side_with_distinct_shapes(tables):
    timeseries, fills = tables

    traces = traces_by_name(run_figure(timeseries, fills, 0.01, LIGHT))

    assert len(traces["Buy fills"].x) == fills.filter(pl.col("side") == 1).height
    assert len(traces["Sell fills"].x) == fills.filter(pl.col("side") == -1).height
    assert traces["Buy fills"].marker.symbol != traces["Sell fills"].marker.symbol
    assert traces["Buy fills"].marker.color != traces["Sell fills"].marker.color


def test_quote_lines_are_drawn_above_fill_markers(tables):
    timeseries, fills = tables

    figure = run_figure(timeseries, fills, 0.01, LIGHT)

    order = [trace.name for trace in figure.data]
    assert order.index("Buy fills") < order.index("Bid quote")
    assert order.index("Sell fills") < order.index("Ask quote")


def test_equity_before_fees_adds_fees_back(tables):
    timeseries, fills = tables

    traces = traces_by_name(run_figure(timeseries, fills, 0.01, LIGHT))

    expected = (timeseries["equity"] + timeseries["fee"]).to_numpy()
    assert np.allclose(np.asarray(traces["Equity before fees"].y), expected)
    assert np.allclose(np.asarray(traces["Net equity"].y), timeseries["equity"].to_numpy())


def test_position_limit_is_drawn_on_both_sides(tables):
    timeseries, fills = tables

    figure = run_figure(timeseries, fills, 0.25, LIGHT)

    limits = sorted(shape.y0 for shape in figure.layout.shapes)
    assert limits == [-0.25, 0.25]


def test_unquoted_steps_become_gaps_not_zeros(tables):
    timeseries, fills = tables
    gapped = timeseries.with_columns(
        pl.when(pl.int_range(pl.len()) % 2 == 0)
        .then(None)
        .otherwise(pl.col("bid_quote"))
        .alias("bid_quote")
    )

    traces = traces_by_name(run_figure(gapped, fills, 0.01, LIGHT))

    assert np.isnan(np.asarray(traces["Bid quote"].y)).sum() >= gapped.height // 2


def test_run_figure_without_fills_still_builds(tables):
    timeseries, fills = tables

    figure = run_figure(timeseries, fills.clear(), 0.01, DARK)

    assert len(traces_by_name(figure)["Buy fills"].x) == 0


def test_distributions_are_percentages_that_sum_to_one_hundred(tables):
    timeseries, fills = tables

    figure = distribution_figure(timeseries, fills, TICK_SIZE, LOT_SIZE, LIGHT)

    assert len(figure.data) == 3
    for bars in figure.data:
        assert np.asarray(bars.y).sum() == pytest.approx(100.0)


def test_inventory_bars_sit_on_the_lot_grid(tables):
    timeseries, fills = tables

    figure = distribution_figure(timeseries, fills, TICK_SIZE, LOT_SIZE, LIGHT)

    lots = np.asarray(figure.data[0].x) / LOT_SIZE
    assert np.allclose(lots, np.round(lots))


def test_spread_axis_is_cut_at_the_tail_and_says_so():
    steps = 2_000
    spread_ticks = np.full(steps, 10.0)
    spread_ticks[:5] = 500.0
    timeseries = pl.DataFrame(
        {
            "position": np.zeros(steps),
            "bid_quote": np.full(steps, 100.0),
            "ask_quote": 100.0 + spread_ticks * TICK_SIZE,
        }
    )
    fills = pl.DataFrame({"qty": [LOT_SIZE]})

    figure = distribution_figure(timeseries, fills, TICK_SIZE, LOT_SIZE, LIGHT)

    assert figure.layout.xaxis2.title.text == "Spread (ticks), axis cut at p99 = 10"
    assert list(figure.layout.xaxis2.range) == [9.0, 11.0]


def test_spread_axis_is_left_alone_without_a_tail():
    steps = 500
    timeseries = pl.DataFrame(
        {
            "position": np.zeros(steps),
            "bid_quote": np.full(steps, 100.0),
            "ask_quote": np.full(steps, 101.0),
        }
    )
    fills = pl.DataFrame({"qty": [LOT_SIZE]})

    figure = distribution_figure(timeseries, fills, TICK_SIZE, LOT_SIZE, LIGHT)

    assert figure.layout.xaxis2.title.text == "Spread (ticks)"
    assert figure.layout.xaxis2.range is None


def test_distributions_survive_a_run_that_never_quoted_or_filled():
    timeseries = pl.DataFrame(
        {
            "position": [0.0, 0.0],
            "bid_quote": pl.Series([None, None], dtype=pl.Float64),
            "ask_quote": pl.Series([None, None], dtype=pl.Float64),
        }
    )
    fills = pl.DataFrame({"qty": pl.Series([], dtype=pl.Float64)})

    figure = distribution_figure(timeseries, fills, TICK_SIZE, LOT_SIZE, LIGHT)

    assert [len(bars.x) for bars in figure.data] == [1, 0, 0]


def test_ladder_has_market_and_quote_markers_on_separate_rows():
    figure = ladder_figure(84_000.0, 84_000.1, 84_000.05, 83_999.5, 84_000.6, LIGHT)

    traces = traces_by_name(figure)
    assert set(traces) == {"Best bid", "Best ask", "Your bid", "Your ask"}
    assert traces["Best bid"].y[0] == traces["Best ask"].y[0]
    assert traces["Your bid"].y[0] == traces["Your ask"].y[0]
    assert traces["Best bid"].y[0] != traces["Your bid"].y[0]
    assert [shape.x0 for shape in figure.layout.shapes] == [84_000.05]


def test_ladder_leaves_out_a_paused_side_and_still_frames_the_rest():
    figure = ladder_figure(84_000.0, 84_000.1, 84_000.05, None, 84_000.6, LIGHT)

    assert set(traces_by_name(figure)) == {"Best bid", "Best ask", "Your ask"}
    low, high = figure.layout.xaxis.range
    assert low < 84_000.0 and high > 84_000.6


def test_ladder_survives_quotes_at_the_touch():
    figure = ladder_figure(100.0, 100.0, 100.0, 100.0, 100.0, DARK)

    low, high = figure.layout.xaxis.range
    assert low < 100.0 < high
