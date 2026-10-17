import json
import math
import os
import re
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

import polars as pl
from pydantic import BaseModel

from mmlab.analytics.metrics import Metrics
from mmlab.config import (
    DEFAULT_MID_SAMPLE_NS,
    SUPPORTED_CONFIG_VERSIONS,
    ExecConfig,
    RunConfig,
    RunRecord,
)
from mmlab.data.manifest import Manifest, ManifestEntry
from mmlab.settings import REPO_ROOT
from mmlab.strategies.naive import quote_sides, quote_ticks

NS_PER_S = 1_000_000_000
NS_PER_MS = 1_000_000
BPS = 1e4
MAX_POINTS = 60_000
HARD_MAX_POINTS = 250_000
NS_PER_HOUR = 3_600 * NS_PER_S
COARSE_RESOLUTIONS_NS = (NS_PER_S, 10 * NS_PER_S, 60 * NS_PER_S)
EPOCH = datetime(1970, 1, 1)
RUN_ID_FORMAT = "%Y-%m-%d_%H%M%S"
RUN_ID_STAMP_LENGTH = 17
TIMESERIES_FILE = "timeseries.parquet"
FILLS_FILE = "fills.parquet"
MARKOUTS_FILE = "markouts.parquet"
SERIES_SLOTS = 8
UI_CONFIG_DIR = REPO_ROOT / "configs" / "_ui"
NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
RUN_LINE = re.compile(r"^run (\S+)$")

RUNS_TABLE_SCHEMA = {
    "run_id": pl.String,
    "started": pl.Datetime,
    "name": pl.String,
    "data": pl.String,
    "strategy": pl.String,
    "params": pl.String,
    "status": pl.String,
    "net_pnl": pl.Float64,
    "gross_pnl": pl.Float64,
    "fees_paid": pl.Float64,
    "sharpe": pl.Float64,
    "max_drawdown": pl.Float64,
    "fills": pl.Int64,
    "markout_1s_bps": pl.Float64,
    "runtime_s": pl.Float64,
}

# label, Metrics field, format; None values show as n/a
COMPARED_METRICS = (
    ("Net PnL", "net_pnl", "{:,.2f}"),
    ("Gross PnL", "gross_pnl", "{:,.2f}"),
    ("Fees paid", "fees_paid", "{:,.2f}"),
    ("Fills", "fill_count", "{:,}"),
    ("Return over trade (bps)", "return_over_trade_bps", "{:,.2f}"),
    ("Spread captured (bps)", "spread_captured_bps", "{:,.2f}"),
    ("Markout 1 s (bps)", "avg_markout_1s_bps", "{:,.2f}"),
    ("Markout 10 s (bps)", "avg_markout_10s_bps", "{:,.2f}"),
    ("Inventory half-life (s)", "inventory_half_life_s", "{:,.1f}"),
    ("Sharpe", "sharpe_hourly_annualized", "{:,.1f}"),
    ("Max drawdown", "max_drawdown", "{:,.2f}"),
    ("Mean |position|", "mean_abs_position", "{:.4g}"),
    ("Time at limit (%)", "pct_time_at_limit", "{:.1f}"),
)


class MetricsFile(BaseModel):
    status: Literal["ok", "failed"]
    runtime_s: float
    error: str | None = None


class RunInfo(BaseModel):
    run_id: str
    path: Path
    status: Literal["ok", "failed", "incomplete", "unreadable"]
    record: RunRecord | None = None
    metrics: Metrics | None = None
    runtime_s: float | None = None
    error: str | None = None


class QuotePreview(BaseModel):
    mid: float
    bid_quote: float | None
    ask_quote: float | None


class RunForm(BaseModel):
    name: str
    strategy: str
    files: int
    half_spread_ticks: float
    step_ms: float
    order_qty: float
    max_position: float
    maker_fee_bps: float
    taker_fee_bps: float
    entry_latency_ms: float
    resp_latency_ms: float
    queue_model: Literal["power_prob", "risk_adverse"]
    queue_power: float

    # the runner config for the first `files` files of one manifest day
    def to_config(self, entry: ManifestEntry) -> RunConfig:
        if not NAME_PATTERN.match(self.name):
            raise ValueError(
                f"run name {self.name!r} must start with a letter or digit and contain only "
                "letters, digits, '_', '-' and '.'"
            )
        if not 1 <= self.files <= len(entry.paths):
            raise ValueError(f"files must be between 1 and {len(entry.paths)}, got {self.files}")
        step_ns = _ms_to_ns(self.step_ms)
        return RunConfig(
            name=self.name,
            strategy=self.strategy,
            data_files=entry.paths[: self.files],
            initial_snapshot=entry.initial_snapshot,
            tick_size=entry.tick_size,
            lot_size=entry.lot_size,
            step_ns=step_ns,
            mid_sample_ns=math.gcd(step_ns, DEFAULT_MID_SAMPLE_NS),
            order_qty=self.order_qty,
            max_position=self.max_position,
            params={"half_spread_ticks": self.half_spread_ticks},
            exec=ExecConfig(
                maker_fee=self.maker_fee_bps / BPS,
                taker_fee=self.taker_fee_bps / BPS,
                entry_latency_ns=_ms_to_ns(self.entry_latency_ms),
                resp_latency_ns=_ms_to_ns(self.resp_latency_ms),
                queue_model=self.queue_model,
                queue_power=self.queue_power,
            ),
        )


def _ms_to_ns(milliseconds: float) -> int:
    return round(milliseconds * NS_PER_MS)


# the quotes the naive strategy would place, from its own functions run as plain Python
def preview_quotes(
    best_bid: float,
    best_ask: float,
    half_spread_ticks: float,
    position: float,
    order_qty: float,
    max_position: float,
    tick_size: float,
) -> QuotePreview:
    best_bid_tick = round(best_bid / tick_size)
    best_ask_tick = round(best_ask / tick_size)
    if best_ask_tick <= best_bid_tick:
        raise ValueError(f"best ask {best_ask} must be above best bid {best_bid}")
    bid_tick, ask_tick = quote_ticks.py_func(best_bid_tick, best_ask_tick, half_spread_ticks)
    can_buy, can_sell = quote_sides.py_func(position, order_qty, max_position)
    return QuotePreview(
        mid=(best_bid_tick + best_ask_tick) / 2 * tick_size,
        bid_quote=float(bid_tick * tick_size) if can_buy else None,
        ask_quote=float(ask_tick * tick_size) if can_sell else None,
    )


def missing_files(config: RunConfig, root: Path) -> list[str]:
    return [path for path in config.data_files if not (root / path).is_file()]


def write_ui_config(config: RunConfig, directory: Path = UI_CONFIG_DIR) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{config.name}.json"
    path.write_text(config.model_dump_json(indent=2), encoding="utf-8")
    return path


def _read_run(run_dir: Path) -> RunInfo:
    record = RunRecord.model_validate_json((run_dir / "config.json").read_text(encoding="utf-8"))
    if record.config_version not in SUPPORTED_CONFIG_VERSIONS:
        raise ValueError(f"unsupported config version {record.config_version}")
    metrics_path = run_dir / "metrics.json"
    if not metrics_path.is_file():
        return RunInfo(run_id=run_dir.name, path=run_dir, status="incomplete", record=record)
    payload = json.loads(metrics_path.read_text(encoding="utf-8"))
    outcome = MetricsFile.model_validate(payload)
    metrics = Metrics.model_validate(payload) if outcome.status == "ok" else None
    return RunInfo(
        run_id=run_dir.name,
        path=run_dir,
        status=outcome.status,
        record=record,
        metrics=metrics,
        runtime_s=outcome.runtime_s,
        error=outcome.error,
    )


# a folder that cannot be parsed becomes a visible "unreadable" row instead of hiding the others
def load_run(run_dir: Path) -> RunInfo:
    try:
        return _read_run(run_dir)
    except (OSError, ValueError) as error:
        return RunInfo(run_id=run_dir.name, path=run_dir, status="unreadable", error=repr(error))


# every run folder, newest first (folder names start with a UTC timestamp)
def list_runs(runs_dir: Path) -> list[RunInfo]:
    if not runs_dir.is_dir():
        return []
    folders = sorted((path for path in runs_dir.iterdir() if path.is_dir()), reverse=True)
    return [load_run(folder) for folder in folders]


def started_at(run_id: str) -> datetime | None:
    try:
        return datetime.strptime(run_id[:RUN_ID_STAMP_LENGTH], RUN_ID_FORMAT)
    except ValueError:
        return None


# the manifest day whose files begin with the files this config replays
def find_entry(manifest: Manifest, config: RunConfig) -> ManifestEntry | None:
    count = len(config.data_files)
    return next(
        (entry for entry in manifest.files if entry.paths[:count] == config.data_files), None
    )


def data_label(config: RunConfig, manifest: Manifest) -> str:
    entry = find_entry(manifest, config)
    if entry is None:
        return Path(config.data_files[0]).stem
    label = f"{entry.symbol} {entry.day}"
    if len(config.data_files) < len(entry.paths):
        label += f" (first {len(config.data_files)} of {len(entry.paths)} files)"
    return label


def run_label(run: RunInfo) -> str:
    started = started_at(run.run_id)
    when = f"{started:%m-%d %H:%M:%S}" if started else "unknown time"
    name = run.record.config.name if run.record else run.run_id
    return f"{when} - {name} - {run.status}"


def _params_text(config: RunConfig) -> str:
    return ", ".join(f"{key}={value}" for key, value in config.params.items())


def _table_row(run: RunInfo, manifest: Manifest) -> dict:
    row = dict.fromkeys(RUNS_TABLE_SCHEMA)
    row |= {
        "run_id": run.run_id,
        "started": started_at(run.run_id),
        "name": run.run_id,
        "status": run.status,
        "runtime_s": run.runtime_s,
    }
    if run.record is not None:
        config = run.record.config
        row |= {
            "name": config.name,
            "data": data_label(config, manifest),
            "strategy": config.strategy,
            "params": _params_text(config),
        }
    if run.metrics is not None:
        row |= {
            "net_pnl": run.metrics.net_pnl,
            "gross_pnl": run.metrics.gross_pnl,
            "fees_paid": run.metrics.fees_paid,
            "sharpe": run.metrics.sharpe_hourly_annualized,
            "max_drawdown": run.metrics.max_drawdown,
            "fills": run.metrics.fill_count,
            "markout_1s_bps": run.metrics.avg_markout_1s_bps,
        }
    return row


def runs_table(runs: list[RunInfo], manifest: Manifest) -> pl.DataFrame:
    rows = [_table_row(run, manifest) for run in runs]
    return pl.DataFrame(rows, schema=RUNS_TABLE_SCHEMA)


def ns_to_datetime(ts_ns: int) -> datetime:
    return EPOCH + timedelta(microseconds=ts_ns // 1000)


def datetime_to_ns(moment: datetime) -> int:
    return (moment - EPOCH) // timedelta(microseconds=1) * 1000


# the finest of the raw step and the coarse resolutions that keeps a window under MAX_POINTS
def pick_resolution_ns(window_ns: int, step_ns: int) -> int:
    candidates = [step_ns] + [every for every in COARSE_RESOLUTIONS_NS if every > step_ns]
    for every_ns in candidates:
        if window_ns / every_ns <= MAX_POINTS:
            return every_ns
    return candidates[-1]


def time_range_ns(run_dir: Path) -> tuple[int, int]:
    bounds = (
        pl.scan_parquet(run_dir / TIMESERIES_FILE)
        .select(pl.col("ts").min().alias("start"), pl.col("ts").max().alias("end"))
        .collect()
    )
    return int(bounds["start"][0]), int(bounds["end"][0])


# timeseries rows in [start_ns, end_ns], reduced to the last row of each every_ns bucket
def read_timeseries(
    run_dir: Path, start_ns: int, end_ns: int, every_ns: int, step_ns: int
) -> pl.DataFrame:
    frame = pl.scan_parquet(run_dir / TIMESERIES_FILE).filter(
        pl.col("ts").is_between(start_ns, end_ns)
    )
    if every_ns > step_ns:
        bucket = (pl.col("ts") // every_ns).alias("bucket")
        frame = frame.group_by(bucket, maintain_order=True).agg(pl.all().last()).drop("bucket")
    return frame.collect()


def read_fills(run_dir: Path, start_ns: int, end_ns: int) -> pl.DataFrame:
    return (
        pl.scan_parquet(run_dir / FILLS_FILE)
        .filter(pl.col("ts").is_between(start_ns, end_ns))
        .collect()
    )


# the markout curve of a run, or None for a run made before markouts existed
def read_markouts(run_dir: Path) -> pl.DataFrame | None:
    path = run_dir / MARKOUTS_FILE
    return pl.read_parquet(path) if path.is_file() else None


# net equity against hours since the run began, thinned to keep the point count down
def read_equity(run_dir: Path, step_ns: int) -> pl.DataFrame:
    start_ns, end_ns = time_range_ns(run_dir)
    every_ns = pick_resolution_ns(end_ns - start_ns, step_ns)
    steps = read_timeseries(run_dir, start_ns, end_ns, every_ns, step_ns)
    return steps.select(((pl.col("ts") - start_ns) / NS_PER_HOUR).alias("hours"), "equity")


# a stable colour slot per run: a run keeps its slot while it stays selected
def assign_slots(selected: list[str], previous: dict[str, int]) -> dict[str, int]:
    if len(selected) > SERIES_SLOTS:
        raise ValueError(f"at most {SERIES_SLOTS} runs can be compared, got {len(selected)}")
    slots = {run_id: previous[run_id] for run_id in selected if run_id in previous}
    for run_id in selected:
        if run_id not in slots:
            slots[run_id] = next(s for s in range(SERIES_SLOTS) if s not in slots.values())
    return slots


# the run name, made unique by the start time and then the folder name when names repeat
def compare_labels(runs: list[RunInfo]) -> dict[str, str]:
    names = [run.record.config.name if run.record else run.run_id for run in runs]
    labels = {}
    for run, name in zip(runs, names, strict=True):
        if names.count(name) == 1:
            labels[run.run_id] = name
            continue
        started = started_at(run.run_id)
        labels[run.run_id] = f"{name} {started:%H:%M:%S}" if started else run.run_id
    if len(set(labels.values())) < len(labels):
        return {run.run_id: run.run_id for run in runs}
    return labels


def _format_setting(value: object) -> str:
    if isinstance(value, float):
        return f"{value:g}"
    if isinstance(value, int) and not isinstance(value, bool):
        return f"{value:,}"
    return str(value)


def _flat_settings(config: RunConfig) -> dict[str, str]:
    flat = {}
    for key, value in config.model_dump(exclude={"name"}).items():
        if key == "data_files":
            flat["data"] = f"{len(value)} files from {Path(value[0]).stem}"
        elif isinstance(value, dict):
            flat |= {f"{key}.{inner}": _format_setting(v) for inner, v in value.items()}
        else:
            flat[key] = _format_setting(value)
    return flat


# the settings that differ between runs, one row per setting and one column per run
def config_diff(configs: dict[str, RunConfig]) -> pl.DataFrame:
    flat = {label: _flat_settings(config) for label, config in configs.items()}
    keys = list(dict.fromkeys(key for settings in flat.values() for key in settings))
    rows = [
        {"setting": key} | {label: settings.get(key, "-") for label, settings in flat.items()}
        for key in keys
        if len({settings.get(key, "-") for settings in flat.values()}) > 1
    ]
    return pl.DataFrame(rows, schema={"setting": pl.String, **dict.fromkeys(configs, pl.String)})


def _metric_text(metrics: Metrics, field: str, template: str) -> str:
    value = getattr(metrics, field)
    return "n/a" if value is None else template.format(value)


# every compared metric, one row per metric and one column per run
def metrics_comparison(metrics: dict[str, Metrics]) -> pl.DataFrame:
    rows = [
        {"metric": label} | {run: _metric_text(m, field, template) for run, m in metrics.items()}
        for label, field, template in COMPARED_METRICS
    ]
    return pl.DataFrame(rows, schema={"metric": pl.String, **dict.fromkeys(metrics, pl.String)})


# a backtest subprocess whose merged output is collected by a reader thread
class RunProcess:
    def __init__(self, command: list[str]) -> None:
        environment = os.environ | {"PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}
        self._process = subprocess.Popen(
            command,
            cwd=REPO_ROOT,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
        )
        self._lines: list[str] = []
        self._started = time.perf_counter()
        self._ended: float | None = None
        self._reader = threading.Thread(target=self._read, daemon=True)
        self._reader.start()

    def _read(self) -> None:
        for line in self._process.stdout:
            self._lines.append(line.rstrip("\n"))
        self._process.wait()
        self._ended = time.perf_counter()

    @property
    def lines(self) -> list[str]:
        return list(self._lines)

    @property
    def elapsed_s(self) -> float:
        return (self._ended or time.perf_counter()) - self._started

    @property
    def is_running(self) -> bool:
        return self._reader.is_alive()

    @property
    def returncode(self) -> int | None:
        return self._process.returncode if not self.is_running else None

    # the run folder name, which the runner prints as its first line
    @property
    def run_id(self) -> str | None:
        matches = (RUN_LINE.match(line) for line in self._lines)
        return next((match.group(1) for match in matches if match), None)


def start_run(config_path: Path) -> RunProcess:
    return RunProcess([sys.executable, "-m", "mmlab.run", "--config", str(config_path)])
