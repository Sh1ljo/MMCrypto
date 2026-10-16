import gzip
from datetime import date
from pathlib import Path

import pytest

from mmlab.data.download import DayFiles, expected_files

DAY = date(2026, 9, 1)
SYMBOL = "BTCUSDT"
TICK_SIZE = 0.1
LOT_SIZE = 0.001
T0_US = 1_788_220_800_000_000
LATENCY_US = 1_000
BOOK_HEADER = "exchange,symbol,timestamp,local_timestamp,is_snapshot,side,price,amount"
TRADES_HEADER = "exchange,symbol,timestamp,local_timestamp,id,side,price,amount"
EXCHANGE = "binance-futures"


# write a gzipped CSV, optionally without a trailing newline
def write_gz(path: Path, header: str, rows: list[str], trailing_newline: bool = True) -> None:
    text = "\n".join([header, *rows]) + ("\n" if trailing_newline else "")
    with gzip.open(path, "wt", newline="") as handle:
        handle.write(text)


def book_row(second: float, snapshot: bool, side: str, price: float, amount: float) -> str:
    ts = T0_US + int(second * 1_000_000)
    flag = "true" if snapshot else "false"
    return f"{EXCHANGE},{SYMBOL},{ts},{ts + LATENCY_US},{flag},{side},{price},{amount}"


def trade_row(second: float, trade_id: int, side: str, price: float, amount: float) -> str:
    ts = T0_US + int(second * 1_000_000)
    return f"{EXCHANGE},{SYMBOL},{ts},{ts + LATENCY_US},{trade_id},{side},{price},{amount}"


# one bid and one ask at start of day, an ask update every second, a trade every 5 seconds
def synthetic_rows(
    seconds: int = 60,
    gap: tuple[int, int] | None = None,
    cross_at: int | None = None,
) -> tuple[list[str], list[str]]:
    book = [
        book_row(0, True, "bid", 100.0, 1.0),
        book_row(0, True, "ask", 100.1, 1.0),
    ]
    trades = []
    for second in range(1, seconds + 1):
        if gap and gap[0] <= second < gap[1]:
            continue
        book.append(book_row(second, False, "ask", 100.2, 1.0 + second % 2))
        if cross_at is not None and second == cross_at:
            book.append(book_row(second, False, "ask", 99.9, 1.0))
        if second % 5 == 0:
            trades.append(trade_row(second, second, "buy", 100.1, 0.5))
    return trades, book


# write a synthetic day under raw_dir using Tardis naming
def make_day(raw_dir: Path, **kwargs) -> DayFiles:
    raw_dir.mkdir(parents=True, exist_ok=True)
    files = expected_files(raw_dir, SYMBOL, DAY)
    trades, book = synthetic_rows(**kwargs)
    write_gz(files.trades, TRADES_HEADER, trades)
    write_gz(files.book, BOOK_HEADER, book)
    return files


@pytest.fixture
def raw_dir(tmp_path: Path) -> Path:
    return tmp_path / "raw"
