from datetime import date
from pathlib import Path

import pytest

from mmlab.data.manifest import ManifestEntry, load_manifest, upsert_entry
from mmlab.data.validate import BookStats, EventStats, ValidationReport


def _report() -> ValidationReport:
    events = EventStats(
        event_count=10,
        trade_count=2,
        start_ts_ns=0,
        end_ts_ns=60,
        duration_s=60.0,
        max_gap_s=1.0,
        trades_per_min_mean=2.0,
        trades_per_min_min=2,
        trades_per_min_max=2,
    )
    book = BookStats(
        step_ms=10.0,
        samples=100,
        broken_samples=0,
        spread_ticks_min=1.0,
        spread_ticks_mean=1.0,
        spread_ticks_p50=1.0,
        spread_ticks_p95=1.0,
        spread_ticks_p99=1.0,
        spread_ticks_max=1.0,
    )
    return ValidationReport(events=events, book=book)


def _entry(path: str, day: date, problems: list[str] | None = None) -> ManifestEntry:
    return ManifestEntry(
        path=path,
        symbol="BTCUSDT",
        day=day,
        tick_size=0.1,
        lot_size=0.001,
        report=_report(),
        problems=problems or [],
    )


def test_missing_manifest_loads_empty(tmp_path: Path):
    assert load_manifest(tmp_path / "manifest.json").files == []


def test_upsert_round_trips_and_sorts_by_day(tmp_path: Path):
    path = tmp_path / "manifest.json"
    upsert_entry(path, _entry("npz/b.npz", date(2026, 10, 1)))
    upsert_entry(path, _entry("npz/a.npz", date(2026, 9, 1)))

    manifest = load_manifest(path)

    assert [f.path for f in manifest.files] == ["npz/a.npz", "npz/b.npz"]
    assert manifest.files[0].report == _report()
    assert not list(tmp_path.glob("*.tmp"))


def test_upsert_replaces_entry_with_same_path(tmp_path: Path):
    path = tmp_path / "manifest.json"
    upsert_entry(path, _entry("npz/a.npz", date(2026, 9, 1)))
    upsert_entry(path, _entry("npz/a.npz", date(2026, 9, 1), problems=["gap"]))

    files = load_manifest(path).files

    assert len(files) == 1
    assert not files[0].passed


def test_unknown_manifest_version_is_rejected(tmp_path: Path):
    path = tmp_path / "manifest.json"
    path.write_text('{"version": 99, "files": []}', encoding="utf-8")
    with pytest.raises(ValueError, match="version"):
        load_manifest(path)
