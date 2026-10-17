import argparse
import hashlib
import json
import math
import subprocess
import time
import traceback
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

import numpy as np
import polars as pl
from hftbacktest import BacktestAsset, HashMapMarketDepthBacktest
from hftbacktest.recorder import Recorder

from mmlab.analytics.markouts import markouts
from mmlab.analytics.metrics import compute_metrics
from mmlab.config import RunConfig, RunRecord
from mmlab.settings import REPO_ROOT, data_dir
from mmlab.strategies.naive import QUOTE_COLUMNS, NaiveParams, naive_mm
from mmlab.strategies.recording import FILL_DTYPE, MID_DTYPE

STEP_MARGIN = 10
HASH_LENGTH = 6
STRATEGIES = ("naive",)
# a step submits at most two orders and an order fills at most once
FILLS_PER_STEP = 2
RECONCILE_TOLERANCE = 1e-9


def runs_dir() -> Path:
    return REPO_ROOT / "runs"


def _resolve(path: str) -> str:
    return str(Path(path) if Path(path).is_absolute() else data_dir() / path)


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def build_run_record(config: RunConfig) -> RunRecord:
    return RunRecord(
        git_commit=_git("rev-parse", "HEAD"),
        git_dirty=bool(_git("status", "--porcelain")),
        hftbacktest_version=version("hftbacktest"),
        config=config,
    )


# a fresh backtest, since a backtest object cannot be reused
def build_backtest(config: RunConfig) -> HashMapMarketDepthBacktest:
    exec_config = config.exec
    if exec_config.partial_fill:
        raise ValueError(
            "partial_fill is not supported: exact fills record one execution per filled order, "
            "and recording an order filled in pieces exactly has not been built"
        )
    asset = (
        BacktestAsset()
        .data([_resolve(path) for path in config.data_files])
        .linear_asset(1.0)
        .constant_order_latency(exec_config.entry_latency_ns, exec_config.resp_latency_ns)
        .trading_value_fee_model(exec_config.maker_fee, exec_config.taker_fee)
        .tick_size(config.tick_size)
        .lot_size(config.lot_size)
    )
    if config.initial_snapshot:
        asset = asset.initial_snapshot(_resolve(config.initial_snapshot))
    if exec_config.queue_model == "power_prob":
        asset = asset.power_prob_queue_model(exec_config.queue_power)
    else:
        asset = asset.risk_adverse_queue_model()
    return HashMapMarketDepthBacktest([asset.no_partial_fill_exchange()])


# local timestamp span of the data in ns, read from the first and last file only
def data_span_ns(config: RunConfig) -> int:
    first = np.load(_resolve(config.data_files[0]))["data"]["local_ts"]
    start = int(first.min())
    last = (
        first
        if len(config.data_files) == 1
        else np.load(_resolve(config.data_files[-1]))["data"]["local_ts"]
    )
    return int(last.max()) - start


class _Buffers:
    def __init__(self, config: RunConfig, steps: int) -> None:
        samples_per_step = config.step_ns // config.mid_sample_ns
        self.recorder = Recorder(1, steps)
        self.quotes = np.full((steps, QUOTE_COLUMNS), np.nan)
        self.fills = np.zeros(FILLS_PER_STEP * steps, dtype=FILL_DTYPE)
        self.mids = np.zeros(steps * samples_per_step, dtype=MID_DTYPE)


def _run_strategy(config: RunConfig, hbt, buffers: _Buffers) -> tuple[int, int, int]:
    if config.strategy != "naive":
        raise ValueError(f"unknown strategy {config.strategy!r}, expected one of {STRATEGIES}")
    params = NaiveParams.model_validate(config.params)
    return naive_mm(
        hbt,
        buffers.recorder.recorder,
        buffers.quotes,
        buffers.fills,
        buffers.mids,
        params.half_spread_ticks,
        config.order_qty,
        config.max_position,
        config.step_ns,
        config.mid_sample_ns,
    )


# the first steps can precede a built book (mid is NaN); a NaN mid after that is a bug
def _drop_warmup(raw: pl.DataFrame) -> pl.DataFrame:
    ready = raw.filter(pl.col("mid").is_not_nan())
    if ready.height == 0:
        raise ValueError("the book never became ready, mid is NaN at every step")
    trimmed = raw.slice(raw.height - ready.height)
    if trimmed["mid"].is_nan().any():
        raise ValueError("mid is NaN after the book became ready")
    return trimmed


def _records_frame(records: np.ndarray) -> pl.DataFrame:
    return pl.DataFrame({name: records[name] for name in records.dtype.names})


# the exact fills must add up to what the recorder counted, or the replay and the fills disagree
def _check_fills(fills: pl.DataFrame, raw: pl.DataFrame) -> None:
    last = raw.tail(1)
    expected = {
        "count": float(last["num_trades"][0]),
        "qty": float(last["trading_volume"][0]),
        "value": float(last["trading_value"][0]),
    }
    actual = {
        "count": float(fills.height),
        "qty": float(fills["qty"].sum()),
        "value": float((fills["price"] * fills["qty"]).sum()),
    }
    for name, value in expected.items():
        if not math.isclose(actual[name], value, rel_tol=RECONCILE_TOLERANCE, abs_tol=1e-9):
            raise ValueError(
                f"exact fills do not match the recorder: {name} {actual[name]} != {value}"
            )


def _build_fills(buffers: _Buffers, fill_count: int, mids: pl.DataFrame) -> pl.DataFrame:
    fills = _records_frame(buffers.fills[:fill_count]).sort("ts", "side", "price", "qty")
    with_mid = fills.join_asof(mids.rename({"mid": "mid_at_fill"}), on="ts", strategy="backward")
    if with_mid["mid_at_fill"].null_count() > 0:
        raise ValueError("a fill happened before the first mid sample")
    return with_mid


def _build_tables(
    buffers: _Buffers, fill_count: int, mid_count: int
) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    records = buffers.recorder.get(0)
    quote_frame = pl.DataFrame(
        {
            "bid_quote": buffers.quotes[: len(records), 1],
            "ask_quote": buffers.quotes[: len(records), 2],
        }
    ).fill_nan(None)
    raw = pl.DataFrame(
        {
            "ts": records["timestamp"],
            "mid": records["price"],
            "position": records["position"],
            "balance": records["balance"],
            "fee": records["fee"],
            "num_trades": records["num_trades"],
            "trading_volume": records["trading_volume"],
            "trading_value": records["trading_value"],
        }
    ).hstack(quote_frame)
    raw = _drop_warmup(raw)
    mids = _records_frame(buffers.mids[:mid_count])
    fills = _build_fills(buffers, fill_count, mids)
    _check_fills(fills, raw)
    timeseries = raw.with_columns(
        (pl.col("balance") + pl.col("position") * pl.col("mid") - pl.col("fee")).alias("equity")
    )
    columns = [
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
    return timeseries.select(columns), fills, mids


def _run_id(config: RunConfig) -> str:
    digest = hashlib.sha1(config.model_dump_json().encode()).hexdigest()[:HASH_LENGTH]
    stamp = datetime.now(UTC).strftime("%Y-%m-%d_%H%M%S")
    return f"{stamp}_{config.name}_{digest}"


class _Log:
    def __init__(self, path: Path) -> None:
        self.path = path

    def __call__(self, message: str) -> None:
        print(message, flush=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(message + "\n")


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


# run one backtest and write its run folder; returns the folder
def run_backtest(config: RunConfig, output_dir: Path | None = None) -> Path:
    run_dir = (output_dir or runs_dir()) / _run_id(config)
    run_dir.mkdir(parents=True)
    log = _Log(run_dir / "log.txt")
    started = time.perf_counter()
    _write_json(run_dir / "config.json", build_run_record(config).model_dump())
    try:
        log(f"run {run_dir.name}")
        span_ns = data_span_ns(config)
        steps = span_ns // config.step_ns + STEP_MARGIN
        log(f"data span {span_ns / 3.6e12:.2f} h, up to {steps} steps")
        hbt = build_backtest(config)
        buffers = _Buffers(config, steps)
        _, fill_count, mid_count = _run_strategy(config, hbt, buffers)
        hbt.close()
        timeseries, fills, mids = _build_tables(buffers, fill_count, mid_count)
        warmup_steps = buffers.recorder.get(0).shape[0] - timeseries.height
        log(
            f"replay done: {timeseries.height} steps ({warmup_steps} warm-up dropped), "
            f"{fills.height} fills, {mids.height} mid samples"
        )
        curve = markouts(fills, mids, int(timeseries["ts"][-1]))
        timeseries.write_parquet(run_dir / "timeseries.parquet")
        fills.write_parquet(run_dir / "fills.parquet")
        mids.write_parquet(run_dir / "mids.parquet")
        curve.write_parquet(run_dir / "markouts.parquet")
        metrics = compute_metrics(timeseries, fills, config.max_position, curve)
        payload = {"status": "ok", "runtime_s": time.perf_counter() - started}
        _write_json(run_dir / "metrics.json", payload | metrics.model_dump())
        log(
            f"net_pnl {metrics.net_pnl:.4f} fees {metrics.fees_paid:.4f} fills {metrics.fill_count}"
        )
    except Exception as error:
        log(traceback.format_exc())
        failure = {"status": "failed", "error": repr(error)}
        _write_json(
            run_dir / "metrics.json", failure | {"runtime_s": time.perf_counter() - started}
        )
        raise
    return run_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one MM-Lab backtest")
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    config = RunConfig.model_validate_json(args.config.read_text(encoding="utf-8"))
    run_dir = run_backtest(config)
    print(f"run folder: {run_dir}")


if __name__ == "__main__":
    main()
