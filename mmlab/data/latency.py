from datetime import date
from pathlib import Path

import numpy as np
from hftbacktest import DEPTH_SNAPSHOT_EVENT, LOCAL_EVENT
from pydantic import BaseModel

from mmlab.data.manifest import ManifestEntry

NS_PER_MS = 1_000_000
MIN_BIN_MS = 0.1
MAX_BIN_MS = 10_000.0
BINS_PER_DECADE = 20
DECADES = 5
BIN_EDGES_MS = np.geomspace(MIN_BIN_MS, MAX_BIN_MS, BINS_PER_DECADE * DECADES + 1)


class FileLatency(BaseModel):
    file: str
    events: int
    p50_ms: float
    p99_ms: float
    max_ms: float


class LatencyReport(BaseModel):
    symbol: str
    day: date
    events: int
    mean_ms: float
    p50_ms: float
    p90_ms: float
    p99_ms: float
    p999_ms: float
    max_ms: float
    bin_edges_ms: list[float]
    counts: list[int]
    files: list[FileLatency]


def latency_path(directory: Path, symbol: str, day: date) -> Path:
    return directory / f"{symbol.lower()}_{day:%Y%m%d}.json"


# local minus exchange timestamp per market event in ms; an event split in two is counted once
def file_latency_ms(npz: Path) -> np.ndarray:
    events = np.load(npz)["data"]
    is_local = (events["ev"] & LOCAL_EVENT) != 0
    is_snapshot = (events["ev"] & DEPTH_SNAPSHOT_EVENT) != 0
    chosen = events[is_local & ~is_snapshot]
    latency_ms = (chosen["local_ts"] - chosen["exch_ts"]) / NS_PER_MS
    if (
        len(latency_ms)
        and not BIN_EDGES_MS[0] <= latency_ms.min() <= latency_ms.max() <= BIN_EDGES_MS[-1]
    ):
        raise ValueError(
            f"{npz.name}: feed latency {latency_ms.min():.3f} to {latency_ms.max():.3f} ms is "
            f"outside {MIN_BIN_MS} to {MAX_BIN_MS} ms"
        )
    return latency_ms.astype(np.float32)


def _file_summary(npz: Path, latency_ms: np.ndarray) -> FileLatency:
    p50, p99 = np.percentile(latency_ms, [50, 99])
    return FileLatency(
        file=npz.name,
        events=len(latency_ms),
        p50_ms=float(p50),
        p99_ms=float(p99),
        max_ms=float(latency_ms.max()),
    )


# feed latency of one registered day: distribution over the day and a summary per file
def measure_feed_latency(entry: ManifestEntry, root: Path) -> LatencyReport:
    paths = [root / relative for relative in entry.paths]
    per_file = [file_latency_ms(path) for path in paths]
    all_ms = np.concatenate(per_file)
    if len(all_ms) == 0:
        raise ValueError(f"no market events in {entry.symbol} {entry.day}")
    p50, p90, p99, p999 = np.percentile(all_ms, [50, 90, 99, 99.9])
    counts, _ = np.histogram(all_ms, bins=BIN_EDGES_MS)
    return LatencyReport(
        symbol=entry.symbol,
        day=entry.day,
        events=len(all_ms),
        mean_ms=float(all_ms.mean(dtype=np.float64)),
        p50_ms=float(p50),
        p90_ms=float(p90),
        p99_ms=float(p99),
        p999_ms=float(p999),
        max_ms=float(all_ms.max()),
        bin_edges_ms=BIN_EDGES_MS.tolist(),
        counts=counts.tolist(),
        files=[
            _file_summary(path, ms) for path, ms in zip(paths, per_file, strict=True) if len(ms)
        ],
    )


def save_latency(path: Path, report: LatencyReport) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report.model_dump_json(indent=2), encoding="utf-8")


# the saved report, or None when this day has not been measured yet
def load_latency(path: Path) -> LatencyReport | None:
    if not path.is_file():
        return None
    return LatencyReport.model_validate_json(path.read_text(encoding="utf-8"))
