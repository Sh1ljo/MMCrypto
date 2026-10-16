import os
from datetime import date
from pathlib import Path

from pydantic import BaseModel

from mmlab.data.validate import ValidationReport

MANIFEST_VERSION = 2


class ManifestEntry(BaseModel):
    paths: list[str]
    symbol: str
    day: date
    tick_size: float
    lot_size: float
    initial_snapshot: str | None = None
    report: ValidationReport
    problems: list[str]

    @property
    def passed(self) -> bool:
        return not self.problems


class Manifest(BaseModel):
    version: int = MANIFEST_VERSION
    files: list[ManifestEntry] = []


# read the manifest, or an empty one when the file does not exist yet
def load_manifest(path: Path) -> Manifest:
    if not path.is_file():
        return Manifest()
    manifest = Manifest.model_validate_json(path.read_text(encoding="utf-8"))
    if manifest.version != MANIFEST_VERSION:
        raise ValueError(f"unsupported manifest version {manifest.version} in {path}")
    return manifest


# replace the entry for the same symbol and day or append a new one, then write atomically
def upsert_entry(path: Path, entry: ManifestEntry) -> Manifest:
    manifest = load_manifest(path)
    key = (entry.symbol, entry.day)
    manifest.files = [f for f in manifest.files if (f.symbol, f.day) != key] + [entry]
    manifest.files.sort(key=lambda f: (f.symbol, f.day))
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    os.replace(temp, path)
    return manifest
