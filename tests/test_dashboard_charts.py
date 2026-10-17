from datetime import date

import numpy as np
import polars as pl
import pytest

from dashboard.charts import (
    DARK,
    LIGHT,
    colors_for,
    compare_equity_figure,
    compare_markout_figure,
    distribution_figure,
    ladder_figure,
    latency_by_file_figure,
    latency_histogram_figure,
    markout_figure,
    run_figure,
)
from mmlab.data.latency import BIN_EDGES_MS, FileLatency, LatencyReport
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


CURVE = pl.DataFrame(
    {
        "horizon_ms": [100, 1_000, 10_000],
        "fills": [50, 50, 50],
        "avg_markout": [-0.1, -0.2, -0.3],
        "avg_markout_bps": [-1.0, -2.0, -3.0],
        "stderr_bps": [0.1, 0.2, 0.3],
    }
)


def latency_report() -> LatencyReport:
    edges = BIN_EDGES_MS.tolist()
    counts = [0] * (len(edges) - 1)
    counts[20], counts[30] = 900, 100
    files = [
        FileLatency(file=f"f{n}.npz", events=500, p50_ms=2, p99_ms=9, max_ms=40) for n in (0, 1)
    ]
    return LatencyReport(
        symbol="BTCUSDT",
        day=date(2026, 10, 1),
        events=1_000,
        mean_ms=3.0,
        p50_ms=2.0,
        p90_ms=5.0,
        p99_ms=9.0,
        p999_ms=30.0,
        max_ms=40.0,
        bin_edges_ms=edges,
        counts=counts,
        files=files,
    )


def test_markout_figure_draws_the_curve_and_the_same_curve_after_the_fee():
    figure = markout_figure(CURVE, 2.0, LIGHT)

    traces = traces_by_name(figure)
    assert list(traces["Average markout"].x) == [0.1, 1.0, 10.0]
    assert list(traces["Average markout"].y) == [-1.0, -2.0, -3.0]
    assert list(traces["After 2 bps fee"].y) == [-3.0, -4.0, -5.0]
    assert figure.layout.xaxis.type == "log"
    assert list(figure.layout.xaxis.ticktext) == ["0.1 s", "1 s", "10 s"]


def test_markout_band_is_the_95_percent_range_and_stays_out_of_the_legend():
    figure = markout_figure(CURVE, 2.0, LIGHT)

    lower, upper = figure.data[0], figure.data[1]
    assert np.allclose(lower.y, np.array([-1.0, -2.0, -3.0]) - 1.96 * np.array([0.1, 0.2, 0.3]))
    assert np.allclose(upper.y, np.array([-1.0, -2.0, -3.0]) + 1.96 * np.array([0.1, 0.2, 0.3]))
    assert lower.showlegend is False and upper.showlegend is False
    assert upper.fill == "tonexty"


def test_a_horizon_with_no_fills_is_left_off_the_markout_curve():
    gapped = CURVE.with_columns(
        pl.when(pl.col("horizon_ms") == 1_000)
        .then(None)
        .otherwise(pl.col("avg_markout_bps"))
        .alias("avg_markout_bps")
    )

    traces = traces_by_name(markout_figure(gapped, 2.0, LIGHT))

    assert list(traces["Average markout"].x) == [0.1, 10.0]


def test_comparison_curves_take_the_colour_of_their_slot():
    curves = {"first": CURVE, "second": CURVE}

    traces = traces_by_name(compare_markout_figure(curves, {"first": 3, "second": 0}, DARK))

    assert traces["first"].line.color == DARK.series[3]
    assert traces["second"].line.color == DARK.series[0]


def test_comparison_equity_lines_follow_each_runs_hours_and_pnl():
    frame = pl.DataFrame({"hours": [0.0, 0.5, 1.0], "equity": [0.0, -1.0, -3.0]})

    traces = traces_by_name(compare_equity_figure({"a": frame}, {"a": 1}, LIGHT))

    assert list(traces["a"].x) == [0.0, 0.5, 1.0]
    assert list(traces["a"].y) == [0.0, -1.0, -3.0]
    assert traces["a"].line.color == LIGHT.series[1]


def test_the_series_palette_has_eight_distinct_colours_in_both_modes():
    for colors in (LIGHT, DARK):
        assert len(colors.series) == 8
        assert len(set(colors.series)) == 8
        assert colors.series[:3] == (colors.bid, colors.ask, colors.position)


def test_latency_histogram_shows_shares_and_marks_the_median_and_the_tail():
    figure = latency_histogram_figure(latency_report(), LIGHT)

    assert np.asarray(figure.data[0].y).sum() == pytest.approx(100.0)
    assert figure.layout.xaxis.type == "log" and figure.layout.yaxis.type == "log"
    assert [shape.x0 for shape in figure.layout.shapes] == [2.0, 9.0, 30.0]
    assert [a.x for a in figure.layout.annotations] == pytest.approx(np.log10([2.0, 9.0, 30.0]))
    assert [a.text for a in figure.layout.annotations] == [
        "median 2 ms",
        "p99 9 ms",
        "p99.9 30 ms",
    ]


def test_latency_by_file_has_a_point_per_file_for_each_percentile():
    figure = latency_by_file_figure(latency_report(), LIGHT)

    assert [trace.name for trace in figure.data] == ["Median", "99th percentile", "Worst"]
    assert all(len(trace.x) == 2 for trace in figure.data)
