from pathlib import Path

import numpy as np
import pytest
from conftest import BOOK_HEADER, DAY, SYMBOL, book_row, make_day, write_gz

from mmlab.data import convert
from mmlab.data.convert import BufferTooLargeError, RowCount, convert_day, count_rows, plan_buffers


def test_count_rows_counts_data_and_snapshot_rows(tmp_path: Path):
    path = tmp_path / "book.csv.gz"
    rows = [
        book_row(0, True, "bid", 100.0, 1.0),
        book_row(0, True, "ask", 100.1, 1.0),
        book_row(1, False, "ask", 100.2, 1.0),
    ]
    write_gz(path, BOOK_HEADER, rows)
    assert count_rows(path) == RowCount(rows=3, snapshot_rows=2)


def test_count_rows_without_trailing_newline(tmp_path: Path):
    path = tmp_path / "book.csv.gz"
    write_gz(path, BOOK_HEADER, [book_row(0, True, "bid", 100.0, 1.0)], trailing_newline=False)
    assert count_rows(path) == RowCount(rows=1, snapshot_rows=1)


def test_count_rows_finds_marker_across_chunk_boundary(tmp_path: Path, monkeypatch):
    path = tmp_path / "book.csv.gz"
    rows = [book_row(n, n % 2 == 0, "bid", 100.0, 1.0) for n in range(40)]
    write_gz(path, BOOK_HEADER, rows)
    expected = count_rows(path)
    for chunk_size in (1, 2, 3, 5, 7, 11):
        monkeypatch.setattr(convert, "CHUNK_BYTES", chunk_size)
        assert count_rows(path) == expected


def test_count_rows_rejects_empty_file(tmp_path: Path):
    path = tmp_path / "empty.csv.gz"
    write_gz(path, "", [], trailing_newline=False)
    with pytest.raises(ValueError, match="empty"):
        count_rows(path)


def test_plan_buffers_is_an_upper_bound_with_clear_events():
    plan = plan_buffers(RowCount(rows=10, snapshot_rows=0), RowCount(rows=100, snapshot_rows=6))
    assert plan.buffer_rows == 10 + 100 + 12
    assert plan.ss_buffer_rows == 7
    assert plan.estimated_peak_gb == pytest.approx(122 * 64 * 4 / 1024**3)


def test_convert_day_writes_sorted_events(raw_dir: Path, tmp_path: Path):
    files = make_day(raw_dir, seconds=20)
    output = tmp_path / "npz" / "out.npz"

    plan = convert_day(files.trades, files.book, output)

    data = np.load(output)["data"]
    trade_rows, book_rows = count_rows(files.trades).rows, count_rows(files.book).rows
    assert len(data) == trade_rows + book_rows + 2
    assert len(data) <= plan.buffer_rows
    assert np.all(np.diff(data["exch_ts"]) >= 0)


def test_convert_day_refuses_when_estimate_exceeds_limit(raw_dir: Path, tmp_path: Path):
    files = make_day(raw_dir, seconds=5)
    with pytest.raises(BufferTooLargeError):
        convert_day(files.trades, files.book, tmp_path / "out.npz", max_memory_gb=1e-9)
    assert not (tmp_path / "out.npz").exists()


def test_convert_day_requires_existing_inputs(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        convert_day(tmp_path / "a.csv.gz", tmp_path / "b.csv.gz", tmp_path / "out.npz")


def test_npz_file_name():
    assert convert.npz_file_name(SYMBOL, DAY) == "btcusdt_20260901.npz"
