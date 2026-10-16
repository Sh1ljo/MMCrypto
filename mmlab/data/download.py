import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from tardis_dev import default_file_name, download_datasets

DEFAULT_EXCHANGE = "binance-futures"
TRADES = "trades"
BOOK = "incremental_book_L2"
API_KEY_ENV = "TARDIS_API_KEY"


@dataclass(frozen=True)
class DayFiles:
    day: date
    trades: Path
    book: Path


# raw file path Tardis writes for one data type, symbol and day
def raw_file_path(raw_dir: Path, data_type: str, day: date, symbol: str, exchange: str) -> Path:
    moment = datetime(day.year, day.month, day.day)
    return raw_dir / default_file_name(exchange, data_type, moment, symbol, "csv")


# every day in [from_date, to_date), matching Tardis' exclusive end date
def days_between(from_date: date, to_date: date) -> list[date]:
    if to_date <= from_date:
        raise ValueError(f"to_date {to_date} must be after from_date {from_date}")
    return [from_date + timedelta(days=n) for n in range((to_date - from_date).days)]


def expected_files(raw_dir: Path, symbol: str, day: date, exchange: str = DEFAULT_EXCHANGE):
    return DayFiles(
        day=day,
        trades=raw_file_path(raw_dir, TRADES, day, symbol, exchange),
        book=raw_file_path(raw_dir, BOOK, day, symbol, exchange),
    )


# download trades and book files for each day; the API key is read from TARDIS_API_KEY
def download_days(
    raw_dir: Path,
    symbol: str,
    from_date: date,
    to_date: date,
    exchange: str = DEFAULT_EXCHANGE,
) -> list[DayFiles]:
    days = days_between(from_date, to_date)
    raw_dir.mkdir(parents=True, exist_ok=True)
    download_datasets(
        exchange=exchange,
        data_types=[TRADES, BOOK],
        symbols=[symbol],
        from_date=from_date.isoformat(),
        to_date=to_date.isoformat(),
        api_key=os.environ.get(API_KEY_ENV, ""),
        download_dir=str(raw_dir),
    )
    files = [expected_files(raw_dir, symbol, day, exchange) for day in days]
    missing = [p for f in files for p in (f.trades, f.book) if not p.is_file()]
    if missing:
        raise FileNotFoundError(f"download finished but files are missing: {missing}")
    return files
