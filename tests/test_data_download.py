from datetime import date
from pathlib import Path

import pytest

from mmlab.data import download


def test_raw_file_path_uses_tardis_naming(raw_dir: Path):
    path = download.raw_file_path(
        raw_dir, download.TRADES, date(2026, 9, 1), "BTCUSDT", download.DEFAULT_EXCHANGE
    )
    assert path.name == "binance-futures_trades_2026-09-01_BTCUSDT.csv.gz"


def test_days_between_excludes_end_date():
    days = download.days_between(date(2026, 9, 1), date(2026, 9, 4))
    assert days == [date(2026, 9, 1), date(2026, 9, 2), date(2026, 9, 3)]


@pytest.mark.parametrize("end", [date(2026, 9, 1), date(2026, 8, 1)])
def test_days_between_rejects_empty_range(end: date):
    with pytest.raises(ValueError):
        download.days_between(date(2026, 9, 1), end)


def _fake_downloader(calls: list[dict], create: bool):
    def fake(**kwargs):
        calls.append(kwargs)
        if create:
            files = download.expected_files(
                Path(kwargs["download_dir"]), "BTCUSDT", date(2026, 9, 1)
            )
            files.trades.write_bytes(b"x")
            files.book.write_bytes(b"x")

    return fake


def test_download_days_passes_arguments(monkeypatch, raw_dir: Path):
    calls: list[dict] = []
    monkeypatch.setattr(download, "download_datasets", _fake_downloader(calls, create=True))
    monkeypatch.setenv(download.API_KEY_ENV, "secret")

    files = download.download_days(raw_dir, "BTCUSDT", date(2026, 9, 1), date(2026, 9, 2))

    assert len(files) == 1
    call = calls[0]
    assert call["exchange"] == "binance-futures"
    assert call["data_types"] == ["trades", "incremental_book_L2"]
    assert call["symbols"] == ["BTCUSDT"]
    assert call["from_date"] == "2026-09-01"
    assert call["to_date"] == "2026-09-02"
    assert call["api_key"] == "secret"
    assert call["download_dir"] == str(raw_dir)


def test_download_days_fails_when_files_missing(monkeypatch, raw_dir: Path):
    monkeypatch.setattr(download, "download_datasets", _fake_downloader([], create=False))
    with pytest.raises(FileNotFoundError):
        download.download_days(raw_dir, "BTCUSDT", date(2026, 9, 1), date(2026, 9, 2))
