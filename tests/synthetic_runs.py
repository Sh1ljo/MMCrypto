import json
from pathlib import Path

NEW_METRICS = ("avg_markout_1s_bps", "avg_markout_10s_bps", "inventory_half_life_s")


# rewrite a finished run folder as a version 1 run, which has no markouts or mid samples
def make_version_1_run(folder: Path) -> None:
    record = json.loads((folder / "config.json").read_text(encoding="utf-8"))
    record["config_version"] = 1
    del record["config"]["mid_sample_ns"]
    (folder / "config.json").write_text(json.dumps(record), encoding="utf-8")
    metrics = json.loads((folder / "metrics.json").read_text(encoding="utf-8"))
    for name in NEW_METRICS:
        del metrics[name]
    (folder / "metrics.json").write_text(json.dumps(metrics), encoding="utf-8")
    (folder / "markouts.parquet").unlink()
    (folder / "mids.parquet").unlink()
