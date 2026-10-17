from datetime import date

import pytest
from conftest import DAY, LATENCY_US, make_day
from hftbacktest import DEPTH_SNAPSHOT_EVENT, EXCH_EVENT, LOCAL_EVENT, TRADE_EVENT

from mmlab import settings
from mmlab.data.__main__ import main
from mmlab.data.latency import (
    BIN_EDGES_MS,
    file_latency_ms,
    latency_path,
    load_latency,
    measure_feed_latency,
    save_latency,
)
from tests.synthetic_events import write_feed_events
from tests.synthetic_manifest import manifest_entry

BOTH = EXCH_EVENT | LOCAL_EVENT


def test_latency_is_local_minus_exchange_in_milliseconds(tmp_path):
    path = write_feed_events(
        tmp_path / "a.npz", [(BOTH | TRADE_EVENT, 2.0), (BOTH, 4.0), (BOTH, 6.0)]
    )

    assert file_latency_ms(path).tolist() == [2.0, 4.0, 6.0]


def test_snapshot_rows_are_not_feed_latency(tmp_path):
    path = write_feed_events(tmp_path / "a.npz", [(BOTH | DEPTH_SNAPSHOT_EVENT, 0.0), (BOTH, 3.0)])

    assert file_latency_ms(path).tolist() == [3.0]


def test_an_event_split_into_two_rows_is_counted_once(tmp_path):
    path = write_feed_events(
        tmp_path / "a.npz", [(EXCH_EVENT, 5.0), (LOCAL_EVENT, 5.0), (BOTH, 3.0)]
    )

    assert file_latency_ms(path).tolist() == [5.0, 3.0]


def test_latency_outside_the_histogram_range_fails_loudly(tmp_path):
    path = write_feed_events(tmp_path / "a.npz", [(BOTH, 20_000.0)])

    with pytest.raises(ValueError, match="outside"):
        file_latency_ms(path)


def test_day_report_summarises_every_file(tmp_path):
    first = write_feed_events(tmp_path / "a.npz", [(BOTH, 1.0), (BOTH, 2.0), (BOTH, 3.0)])
    second = write_feed_events(tmp_path / "b.npz", [(BOTH, 4.0), (BOTH, 50.0)])
    entry = manifest_entry([first.name, second.name], date(2026, 10, 1))

    report = measure_feed_latency(entry, tmp_path)

    assert report.events == 5
    assert report.p50_ms == pytest.approx(3.0)
    assert report.max_ms == 50.0
    assert report.mean_ms == pytest.approx(12.0)
    assert sum(report.counts) == 5
    assert len(report.counts) == len(BIN_EDGES_MS) - 1
    assert [(f.file, f.events, f.max_ms) for f in report.files] == [
        ("a.npz", 3, 3.0),
        ("b.npz", 2, 50.0),
    ]


def test_a_day_without_market_events_is_an_error(tmp_path):
    only_snapshot = write_feed_events(tmp_path / "a.npz", [(BOTH | DEPTH_SNAPSHOT_EVENT, 0.0)])
    entry = manifest_entry([only_snapshot.name], date(2026, 10, 1))

    with pytest.raises(ValueError, match="no market events"):
        measure_feed_latency(entry, tmp_path)


def test_report_survives_a_save_and_load(tmp_path):
    path = write_feed_events(tmp_path / "a.npz", [(BOTH, 2.0), (BOTH, 4.0)])
    report = measure_feed_latency(manifest_entry([path.name], date(2026, 10, 1)), tmp_path)
    target = latency_path(tmp_path / "latency", "BTCUSDT", date(2026, 10, 1))

    save_latency(target, report)

    assert target.name == "btcusdt_20261001.json"
    assert load_latency(target) == report


def test_loading_a_day_that_was_not_measured_gives_none(tmp_path):
    assert load_latency(tmp_path / "missing.json") is None


def test_latency_command_measures_an_ingested_day(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv(settings.DATA_DIR_ENV, str(tmp_path))
    make_day(settings.raw_dir(), seconds=60)
    ingest = ["ingest", "--symbol", "BTCUSDT", "--date", DAY.isoformat()]
    assert main([*ingest, "--tick-size", "0.1", "--lot-size", "0.001"]) == 0

    assert main(["latency", "--symbol", "BTCUSDT", "--date", DAY.isoformat()]) == 0

    report = load_latency(latency_path(settings.latency_dir(), "BTCUSDT", DAY))
    assert report.p50_ms == pytest.approx(LATENCY_US / 1_000)
    assert "p50 1.00 ms" in capsys.readouterr().out


def test_latency_command_needs_an_ingested_day(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv(settings.DATA_DIR_ENV, str(tmp_path))

    assert main(["latency", "--symbol", "BTCUSDT", "--date", DAY.isoformat()]) == 1
    assert "run ingest first" in capsys.readouterr().out
