import argparse
import hashlib
import json
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

from mmlab.analytics.metrics import compute_metrics, infer_fills
from mmlab.config import RunConfig, RunRecord
from mmlab.settings import REPO_ROOT, data_dir
from mmlab.strategies.naive import QUOTE_COLUMNS, NaiveParams, naive_mm

STEP_MARGIN = 10
HASH_LENGTH = 6
STRATEGIES = ("naive",)


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
    asset = (
        asset.partial_fill_exchange()
        if exec_config.partial_fill
        else asset.no_partial_fill_exchange()
    )
    return HashMapMarketDepthBacktest([asset])


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


def _run_strategy(config: RunConfig, hbt, recorder: Recorder, quotes: np.ndarray) -> int:
    if config.strategy != "naive":
        raise ValueError(f"unknown strategy {config.strategy!r}, expected one of {STRATEGIES}")
    params = NaiveParams.model_validate(config.params)
    return naive_mm(
        hbt,
        recorder.recorder,
        quotes,
        params.half_spread_ticks,
        config.order_qty,
        config.max_position,
        config.step_ns,
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


def _build_tables(recorder: Recorder, quotes: np.ndarray) -> tuple[pl.DataFrame, pl.DataFrame]:
    records = recorder.get(0)
    quote_frame = pl.DataFrame(
        {"bid_quote": quotes[: len(records), 1], "ask_quote": quotes[: len(records), 2]}
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
    timeseries = raw.with_columns(
        (pl.col("balance") + pl.col("position") * pl.col("mid") - pl.col("fee")).alias("equity")
    )
    fills = infer_fills(raw)
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
    return timeseries.select(columns), fills


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
        recorder = Recorder(hbt.num_assets, steps)
        quotes = np.full((steps, QUOTE_COLUMNS), np.nan)
        _run_strategy(config, hbt, recorder, quotes)
        hbt.close()
        timeseries, fills = _build_tables(recorder, quotes)
        warmup_steps = recorder.get(0).shape[0] - timeseries.height
        log(
            f"replay done: {timeseries.height} steps ({warmup_steps} warm-up dropped), "
            f"{fills.height} fill rows"
        )
        timeseries.write_parquet(run_dir / "timeseries.parquet")
        fills.write_parquet(run_dir / "fills.parquet")
        metrics = compute_metrics(timeseries, fills, config.max_position)
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
