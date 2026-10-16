import bisect
import gzip
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

SNAPSHOT_MARKER = b",true,"
LOCAL_TS_FIELD = 3
US_PER_HOUR = 3_600_000_000


@dataclass(frozen=True)
class Slice:
    path: Path
    start_ts_us: int


def day_start_us(day: date) -> int:
    return int(datetime(day.year, day.month, day.day, tzinfo=UTC).timestamp()) * 1_000_000


def _local_ts_us(line: bytes) -> int:
    return int(line.split(b",", LOCAL_TS_FIELD + 1)[LOCAL_TS_FIELD])


def _slice_path(dest_dir: Path, source: Path, part: int) -> Path:
    return dest_dir / f"part{part:03d}_{source.name}"


# split the book file into time slices; a cut never falls inside a snapshot block
def split_book(book_file: Path, dest_dir: Path, day: date, chunk_hours: float) -> list[Slice]:
    chunk_us = int(chunk_hours * US_PER_HOUR)
    origin = day_start_us(day)
    slices: list[Slice] = []
    bucket = -1
    previous_snapshot = False
    out = None
    try:
        with gzip.open(book_file, "rb") as handle:
            header = handle.readline()
            for line in handle:
                ts = _local_ts_us(line)
                snapshot = SNAPSHOT_MARKER in line
                target = (ts - origin) // chunk_us
                if out is None or (target > bucket and not snapshot and not previous_snapshot):
                    if out is not None:
                        out.close()
                    path = _slice_path(dest_dir, book_file, len(slices))
                    out = gzip.open(path, "wb", compresslevel=1)
                    out.write(header)
                    slices.append(Slice(path, ts))
                    bucket = target
                out.write(line)
                previous_snapshot = snapshot
    finally:
        if out is not None:
            out.close()
    return slices


# split the trades file at the same instants the book was cut; returns part index to file
def split_trades(trades_file: Path, dest_dir: Path, book_slices: list[Slice]) -> dict[int, Path]:
    cuts = [s.start_ts_us for s in book_slices[1:]]
    paths: dict[int, Path] = {}
    part = -1
    out = None
    try:
        with gzip.open(trades_file, "rb") as handle:
            header = handle.readline()
            for line in handle:
                target = bisect.bisect_right(cuts, _local_ts_us(line))
                if out is None or target > part:
                    if out is not None:
                        out.close()
                    part = target
                    path = _slice_path(dest_dir, trades_file, part)
                    out = gzip.open(path, "wb", compresslevel=1)
                    out.write(header)
                    paths[part] = path
                out.write(line)
    finally:
        if out is not None:
            out.close()
    return paths
