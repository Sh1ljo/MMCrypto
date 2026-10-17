import json
from pathlib import Path

import polars as pl
import pytest

from mmlab.run import run_backtest
from tests.synthetic_events import synthetic_config, write_synthetic_day


def read_metrics(run_dir: Path) -> dict:
    return json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))


@pytest.fixture
def day(tmp_path: Path) -> Path:
    return write_synthetic_day(tmp_path / "day.npz")


def run(day: Path, tmp_path: Path, name: str = "out", **overrides) -> Path:
    return run_backtest(synthetic_config(day, **overrides), tmp_path / name)


def test_run_folder_has_all_artifacts(day, tmp_path):
    run_dir = run(day, tmp_path)
    for name in ("config.json", "metrics.json", "timeseries.parquet", "fills.parquet", "log.txt"):
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
    assert record["config_version"] == 1
    assert record["config"]["name"] == "synthetic"
    assert record["hftbacktest_version"]


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
