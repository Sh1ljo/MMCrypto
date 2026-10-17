import os
from pathlib import Path

DATA_DIR_ENV = "MMLAB_DATA_DIR"
REPO_ROOT = Path(__file__).resolve().parent.parent


# data root, overridable with MMLAB_DATA_DIR to point at a larger drive
def data_dir() -> Path:
    override = os.environ.get(DATA_DIR_ENV)
    if override:
        return Path(override).expanduser().resolve()
    return REPO_ROOT / "data"


def raw_dir() -> Path:
    return data_dir() / "raw"


def npz_dir() -> Path:
    return data_dir() / "npz"


def manifest_path() -> Path:
    return data_dir() / "manifest.json"


def latency_dir() -> Path:
    return data_dir() / "latency"
