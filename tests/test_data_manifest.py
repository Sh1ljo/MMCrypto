from datetime import date
from pathlib import Path

import pytest

from mmlab.data.manifest import load_manifest, upsert_entry
from tests.synthetic_manifest import manifest_entry, validation_report


def test_missing_manifest_loads_empty(tmp_path: Path):
    assert load_manifest(tmp_path / "manifest.json").files == []


def test_upsert_round_trips_and_sorts_by_day(tmp_path: Path):
    path = tmp_path / "manifest.json"
    upsert_entry(path, manifest_entry(["npz/b.npz"], date(2026, 10, 1)))
    upsert_entry(path, manifest_entry(["npz/a.npz"], date(2026, 9, 1)))

    manifest = load_manifest(path)

    assert [f.paths for f in manifest.files] == [["npz/a.npz"], ["npz/b.npz"]]
    assert manifest.files[0].report == validation_report()
    assert not list(tmp_path.glob("*.tmp"))


def test_upsert_replaces_entry_for_same_day(tmp_path: Path):
    path = tmp_path / "manifest.json"
    upsert_entry(path, manifest_entry(["npz/a.npz"], date(2026, 9, 1)))
    upsert_entry(path, manifest_entry(["npz/a2.npz"], date(2026, 9, 1), problems=["gap"]))

    files = load_manifest(path).files

    assert len(files) == 1
    assert not files[0].passed


def test_unknown_manifest_version_is_rejected(tmp_path: Path):
    path = tmp_path / "manifest.json"
    path.write_text('{"version": 99, "files": []}', encoding="utf-8")
    with pytest.raises(ValueError, match="version"):
        load_manifest(path)
