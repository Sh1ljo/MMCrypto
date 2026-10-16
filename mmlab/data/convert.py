import gzip
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from hftbacktest.data.utils import tardis
from hftbacktest.data.utils.snapshot import create_last_snapshot
from hftbacktest.types import event_dtype

CHUNK_BYTES = 8 * 1024 * 1024
SNAPSHOT_MARKER = b",true,"
BYTES_PER_EVENT = event_dtype.itemsize
GIB = 1024**3
# rough multiple of the event buffer that the CSV frame and sort copies add; confirm on real data
PEAK_MEMORY_FACTOR = 4


class BufferTooLargeError(RuntimeError):
    pass


@dataclass(frozen=True)
class RowCount:
    rows: int
    snapshot_rows: int


@dataclass(frozen=True)
class BufferPlan:
    buffer_rows: int
    ss_buffer_rows: int
    estimated_peak_gb: float


# count data rows and snapshot rows in a gzipped CSV without loading it into memory
def count_rows(path: Path) -> RowCount:
    newlines = 0
    snapshot_rows = 0
    tail = b""
    last_byte = b""
    with gzip.open(path, "rb") as handle:
        while chunk := handle.read(CHUNK_BYTES):
            newlines += chunk.count(b"\n")
            window = tail + chunk
            snapshot_rows += window.count(SNAPSHOT_MARKER)
            tail = window[-(len(SNAPSHOT_MARKER) - 1) :]
            last_byte = chunk[-1:]
    if not last_byte:
        raise ValueError(f"{path} is empty")
    lines = newlines + (0 if last_byte == b"\n" else 1)
    return RowCount(rows=max(lines - 1, 0), snapshot_rows=snapshot_rows)


# exact upper bound on converted events: every row, plus two clear events per snapshot row at worst
def plan_buffers(trades: RowCount, book: RowCount) -> BufferPlan:
    buffer_rows = trades.rows + book.rows + 2 * book.snapshot_rows
    peak_gb = buffer_rows * BYTES_PER_EVENT * PEAK_MEMORY_FACTOR / GIB
    return BufferPlan(
        buffer_rows=buffer_rows,
        ss_buffer_rows=book.snapshot_rows + 1,
        estimated_peak_gb=peak_gb,
    )


def npz_file_name(symbol: str, day: date) -> str:
    return f"{symbol.lower()}_{day:%Y%m%d}.npz"


# convert one day of Tardis trades and book files to an hftbacktest npz, trades first
def convert_day(
    trades_file: Path,
    book_file: Path,
    output: Path,
    max_memory_gb: float | None = None,
) -> BufferPlan:
    for path in (trades_file, book_file):
        if not path.is_file():
            raise FileNotFoundError(path)
    plan = plan_buffers(count_rows(trades_file), count_rows(book_file))
    if max_memory_gb is not None and plan.estimated_peak_gb > max_memory_gb:
        raise BufferTooLargeError(
            f"estimated peak {plan.estimated_peak_gb:.1f} GB "
            f"exceeds the limit of {max_memory_gb} GB"
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    tardis.convert(
        [str(trades_file), str(book_file)],
        output_filename=str(output),
        buffer_size=plan.buffer_rows,
        ss_buffer_size=plan.ss_buffer_rows,
    )
    return plan


# snapshot of the last book state, only needed when chaining consecutive days
def write_eod_snapshot(npz_files: list[Path], tick_size: float, lot_size: float, output: Path):
    create_last_snapshot(
        [str(path) for path in npz_files],
        tick_size=tick_size,
        lot_size=lot_size,
        output_snapshot_filename=str(output),
    )
