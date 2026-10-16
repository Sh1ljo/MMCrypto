from pathlib import Path

from mmlab import settings


def test_default_data_dir_is_inside_repo(monkeypatch):
    monkeypatch.delenv(settings.DATA_DIR_ENV, raising=False)
    assert settings.data_dir() == settings.REPO_ROOT / "data"


def test_env_overrides_data_dir(monkeypatch, tmp_path: Path):
    monkeypatch.setenv(settings.DATA_DIR_ENV, str(tmp_path))
    assert settings.data_dir() == tmp_path.resolve()
    assert settings.raw_dir() == tmp_path.resolve() / "raw"
    assert settings.npz_dir() == tmp_path.resolve() / "npz"
    assert settings.manifest_path() == tmp_path.resolve() / "manifest.json"
