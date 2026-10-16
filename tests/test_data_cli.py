from pathlib import Path

from conftest import DAY, LOT_SIZE, SYMBOL, TICK_SIZE, make_day

from mmlab import settings
from mmlab.data.__main__ import main
from mmlab.data.manifest import load_manifest

INGEST_ARGS = [
    "ingest",
    "--symbol",
    SYMBOL,
    "--date",
    DAY.isoformat(),
    "--tick-size",
    str(TICK_SIZE),
    "--lot-size",
    str(LOT_SIZE),
    "--step-ms",
    "100",
]


def test_ingest_converts_validates_and_registers(monkeypatch, tmp_path: Path):
    monkeypatch.setenv(settings.DATA_DIR_ENV, str(tmp_path))
    make_day(settings.raw_dir(), seconds=60)

    assert main(INGEST_ARGS) == 0

    files = load_manifest(settings.manifest_path()).files
    assert [f.path for f in files] == ["npz/btcusdt_20260901.npz"]
    assert files[0].passed
    assert (settings.npz_dir() / "btcusdt_20260901.npz").is_file()


def test_ingest_exits_nonzero_when_validation_fails(monkeypatch, tmp_path: Path):
    monkeypatch.setenv(settings.DATA_DIR_ENV, str(tmp_path))
    make_day(settings.raw_dir(), seconds=150, gap=(10, 100))

    assert main(INGEST_ARGS) == 1

    files = load_manifest(settings.manifest_path()).files
    assert len(files) == 1
    assert not files[0].passed
