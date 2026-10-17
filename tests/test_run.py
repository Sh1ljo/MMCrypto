import json
from pathlib import Path

import polars as pl
import pytest

from mmlab.run import _check_fills, run_backtest
from tests.synthetic_events import (
    ASK_PRICE,
    BID_PRICE,
    NS_PER_S,
    SELL_PHASE_SECONDS,
    T0_NS,
    synthetic_config,
    write_synthetic_day,
)


def read_metrics(run_dir: Path) -> dict:
    return json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))


@pytest.fixture
def day(tmp_path: Path) -> Path:
    return write_synthetic_day(tmp_path / "day.npz")


def run(day: Path, tmp_path: Path, name: str = "out", **overrides) -> Path:
    return run_backtest(synthetic_config(day, **overrides), tmp_path / name)


def test_run_folder_has_all_artifacts(day, tmp_path):
    run_dir = run(day, tmp_path)
    artifacts = (
        "config.json",
        "metrics.json",
        "timeseries.parquet",
        "fills.parquet",
        "mids.parquet",
        "markouts.parquet",
        "log.txt",
    )
    for name in artifacts:
        assert (run_dir / name).is_file()
    assert pl.read_parquet(run_dir / "timeseries.parquet").columns == [
        "ts",
        "mid",
        "bid_quote",
        "ask_quote",
        "position",
        "balance",
        "fee",
        "equity",
        "num_trades",
    ]
    assert pl.read_parquet(run_dir / "fills.parquet").columns == [
        "ts",
        "side",
        "price",
        "qty",
        "mid_at_fill",
    ]
    record = json.loads((run_dir / "config.json").read_text(encoding="utf-8"))
    assert record["config_version"] == 2
    assert record["config"]["name"] == "synthetic"
    assert record["hftbacktest_version"]


def test_exact_fills_are_priced_and_timed_by_the_trades_that_hit_them(day, tmp_path):
    fills = pl.read_parquet(run(day, tmp_path) / "fills.parquet")

    assert ((fills["ts"] - T0_NS) % NS_PER_S == 0).all()
    assert fills["ts"].is_sorted()
    bought = fills.filter(pl.col("ts") <= T0_NS + SELL_PHASE_SECONDS * NS_PER_S)
    sold = fills.filter(pl.col("ts") > T0_NS + SELL_PHASE_SECONDS * NS_PER_S)
    assert bought.height > 0 and sold.height > 0
    assert set(bought["side"]) == {1}
    assert set(sold["side"]) == {-1}
    assert bought["price"].to_list() == [pytest.approx(BID_PRICE)] * bought.height
    assert sold["price"].to_list() == [pytest.approx(ASK_PRICE)] * sold.height


def test_exact_fills_add_up_to_the_reported_metrics(day, tmp_path):
    run_dir = run(day, tmp_path)
    fills = pl.read_parquet(run_dir / "fills.parquet")
    metrics = read_metrics(run_dir)

    assert fills.height == metrics["fill_count"]
    assert fills["qty"].sum() == pytest.approx(metrics["traded_qty"])
    assert (fills["price"] * fills["qty"]).sum() == pytest.approx(metrics["traded_notional"])


def test_mid_at_fill_is_the_book_mid_when_the_fill_happened(day, tmp_path):
    fills = pl.read_parquet(run(day, tmp_path) / "fills.parquet")

    assert fills["mid_at_fill"].to_list() == [pytest.approx((BID_PRICE + ASK_PRICE) / 2)] * (
        fills.height
    )


def test_mids_are_stored_only_when_they_change(day, tmp_path):
    mids = pl.read_parquet(run(day, tmp_path) / "mids.parquet")

    assert mids.columns == ["ts", "mid"]
    assert mids["ts"].is_sorted()
    assert (mids["mid"].diff().drop_nulls() != 0).all()
    assert mids["mid"][0] == pytest.approx((BID_PRICE + ASK_PRICE) / 2)


def test_markout_curve_of_a_static_book_is_the_half_spread(day, tmp_path):
    curve = pl.read_parquet(run(day, tmp_path) / "markouts.parquet")
    half_spread_bps = (ASK_PRICE - BID_PRICE) / 2 / BID_PRICE * 1e4

    short = curve.filter(pl.col("horizon_ms") == 1_000)
    assert short["fills"][0] > 0
    assert short["avg_markout_bps"][0] == pytest.approx(half_spread_bps, rel=1e-2)
    assert read_metrics(run(day, tmp_path, "again"))["avg_markout_1s_bps"] == pytest.approx(
        short["avg_markout_bps"][0]
    )


def test_sampling_the_mid_more_finely_does_not_change_the_strategy(day, tmp_path):
    coarse = run(day, tmp_path, "coarse", mid_sample_ns=100_000_000)
    fine = run(day, tmp_path, "fine", mid_sample_ns=10_000_000)

    for name in ("timeseries.parquet", "fills.parquet"):
        assert pl.read_parquet(coarse / name).equals(pl.read_parquet(fine / name))


def test_mid_sample_must_divide_the_step(day, tmp_path):
    with pytest.raises(ValueError, match="multiple of mid_sample_ns"):
        run(day, tmp_path, mid_sample_ns=30_000_000)


def test_partial_fills_are_rejected_because_exact_fills_would_lose_quantity(day, tmp_path):
    with pytest.raises(ValueError, match="partial_fill is not supported"):
        run(day, tmp_path, exec={"queue_model": "risk_adverse", "partial_fill": True})


def test_fills_that_disagree_with_the_recorder_fail_loudly():
    fills = pl.DataFrame({"price": [100.0], "qty": [1.0]})
    raw = pl.DataFrame({"num_trades": [2], "trading_volume": [1.0], "trading_value": [100.0]})

    with pytest.raises(ValueError, match="count 1.0 != 2.0"):
        _check_fills(fills, raw)


def test_strategy_actually_trades(day, tmp_path):
    metrics = read_metrics(run(day, tmp_path))
    assert metrics["status"] == "ok"
    assert metrics["fill_count"] > 0
    assert metrics["fees_paid"] > 0


def test_no_trade_strategy_has_zero_pnl_fees_and_position(day, tmp_path):
    run_dir = run(day, tmp_path, max_position=0.0)
    metrics = read_metrics(run_dir)
    timeseries = pl.read_parquet(run_dir / "timeseries.parquet")
    assert metrics["net_pnl"] == 0
    assert metrics["fees_paid"] == 0
    assert metrics["fill_count"] == 0
    assert timeseries["position"].abs().max() == 0


def test_determinism(day, tmp_path):
    first = read_metrics(run(day, tmp_path, "a"))
    second = read_metrics(run(day, tmp_path, "b"))
    first.pop("runtime_s")
    second.pop("runtime_s")
    assert first == second


def test_fee_sign(day, tmp_path):
    paid = read_metrics(run(day, tmp_path, "paid", exec={"queue_model": "risk_adverse"}))
    rebate = read_metrics(
        run(day, tmp_path, "rebate", exec={"queue_model": "risk_adverse", "maker_fee": -0.0001})
    )
    assert paid["fees_paid"] > 0
    assert rebate["fees_paid"] < 0


def test_post_only_never_pays_taker_fee(day, tmp_path):
    exec_config = {"queue_model": "risk_adverse", "maker_fee": 0.0002, "taker_fee": 0.01}
    metrics = read_metrics(run(day, tmp_path, exec=exec_config))
    assert metrics["fees_paid"] == pytest.approx(0.0002 * metrics["traded_notional"])


def test_inventory_never_exceeds_limit(day, tmp_path):
    run_dir = run(day, tmp_path, max_position=0.005, order_qty=0.001)
    timeseries = pl.read_parquet(run_dir / "timeseries.parquet")
    assert timeseries["position"].abs().max() <= 0.005 + 0.001
    assert read_metrics(run_dir)["pct_time_at_limit"] > 0


def test_failed_run_writes_failed_status(day, tmp_path):
    with pytest.raises(ValueError, match="unknown strategy"):
        run(day, tmp_path, strategy="missing")
    (run_dir,) = (tmp_path / "out").iterdir()
    assert read_metrics(run_dir)["status"] == "failed"


def test_unknown_param_is_rejected(day, tmp_path):
    with pytest.raises(ValueError, match="half_spred_ticks"):
        run(day, tmp_path, params={"half_spred_ticks": 1})
