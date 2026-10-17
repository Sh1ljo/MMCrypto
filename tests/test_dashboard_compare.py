import json
import shutil
from datetime import date
from pathlib import Path

import polars as pl
import pytest

from dashboard.lib import (
    SERIES_SLOTS,
    RunForm,
    assign_slots,
    compare_labels,
    config_diff,
    list_runs,
    load_run,
    metrics_comparison,
    read_equity,
    read_markouts,
    run_label,
)
from mmlab.analytics.metrics import Metrics
from mmlab.run import run_backtest
from tests.synthetic_events import synthetic_config, write_synthetic_day
from tests.synthetic_manifest import manifest_entry
from tests.synthetic_runs import make_version_1_run


@pytest.fixture(scope="module")
def run_dir(tmp_path_factory) -> Path:
    data = write_synthetic_day(tmp_path_factory.mktemp("data") / "day.npz")
    return run_backtest(synthetic_config(data), tmp_path_factory.mktemp("runs"))


def copy_run(run_dir: Path, root: Path, run_id: str) -> Path:
    return shutil.copytree(run_dir, root / run_id)


def test_a_run_from_before_markouts_still_loads(run_dir, tmp_path):
    old = copy_run(run_dir, tmp_path, "2026-10-17_120000_old_a")
    make_version_1_run(old)

    run = load_run(old)

    assert run.status == "ok"
    assert run.record.config_version == 1
    assert run.metrics.avg_markout_1s_bps is None
    assert read_markouts(old) is None


def test_an_unknown_config_version_is_flagged_not_loaded(run_dir, tmp_path):
    odd = copy_run(run_dir, tmp_path, "2026-10-17_120000_odd_a")
    record = json.loads((odd / "config.json").read_text(encoding="utf-8"))
    record["config_version"] = 99
    (odd / "config.json").write_text(json.dumps(record), encoding="utf-8")

    run = load_run(odd)

    assert run.status == "unreadable"
    assert "unsupported config version 99" in run.error


def test_a_new_run_has_its_markout_curve(run_dir):
    curve = read_markouts(run_dir)

    assert curve["horizon_ms"].to_list()[0] == 100
    assert curve.height == 7


def test_the_form_samples_the_mid_on_a_grid_that_divides_the_step():
    entry = manifest_entry(["a"], date(2026, 10, 1))

    def sample_ns(step_ms: float) -> int:
        form = RunForm(
            name="x",
            strategy="naive",
            files=1,
            half_spread_ticks=5.0,
            step_ms=step_ms,
            order_qty=0.001,
            max_position=0.01,
            maker_fee_bps=2.0,
            taker_fee_bps=5.0,
            entry_latency_ms=10.0,
            resp_latency_ms=10.0,
            queue_model="power_prob",
            queue_power=2.0,
        )
        return form.to_config(entry).mid_sample_ns

    assert sample_ns(100.0) == 10_000_000
    assert sample_ns(15.0) == 5_000_000
    assert sample_ns(7.0) == 1_000_000


def test_a_colour_slot_stays_with_its_run_when_others_change():
    first = assign_slots(["a", "b", "c"], {})
    assert first == {"a": 0, "b": 1, "c": 2}

    without_a = assign_slots(["b", "c"], first)
    assert without_a == {"b": 1, "c": 2}

    with_new = assign_slots(["b", "c", "d"], without_a)
    assert with_new == {"b": 1, "c": 2, "d": 0}


def test_more_runs_than_colour_slots_is_an_error():
    runs = [f"run{n}" for n in range(SERIES_SLOTS + 1)]

    with pytest.raises(ValueError, match="at most 8 runs"):
        assign_slots(runs, {})


def test_labels_use_the_run_name_and_add_the_time_only_when_names_repeat(run_dir, tmp_path):
    root = tmp_path / "runs"
    copy_run(run_dir, root, "2026-10-17_120000_ok_a")
    copy_run(run_dir, root, "2026-10-17_130000_ok_b")
    runs = list_runs(root)

    assert compare_labels(runs) == {
        "2026-10-17_130000_ok_b": "synthetic 13:00:00",
        "2026-10-17_120000_ok_a": "synthetic 12:00:00",
    }
    assert compare_labels(runs[:1]) == {"2026-10-17_130000_ok_b": "synthetic"}


def test_labels_fall_back_to_folder_names_when_times_also_repeat(run_dir, tmp_path):
    root = tmp_path / "runs"
    copy_run(run_dir, root, "2026-10-17_120000_ok_a")
    copy_run(run_dir, root, "2026-10-17_120000_ok_b")

    labels = compare_labels(list_runs(root))

    assert sorted(labels.values()) == ["2026-10-17_120000_ok_a", "2026-10-17_120000_ok_b"]


def test_run_label_shows_time_name_and_status(run_dir, tmp_path):
    copy_run(run_dir, tmp_path, "2026-10-17_120000_ok_a")

    assert (
        run_label(load_run(tmp_path / "2026-10-17_120000_ok_a"))
        == "10-17 12:00:00 - synthetic - ok"
    )


def test_config_diff_lists_only_the_settings_that_differ():
    base = synthetic_config(Path("x.npz"))
    slower = synthetic_config(
        Path("x.npz"),
        params={"half_spread_ticks": 4},
        exec={"queue_model": "risk_adverse", "entry_latency_ns": 50_000_000},
    )

    diff = config_diff({"base": base, "slower": slower})

    assert diff.columns == ["setting", "base", "slower"]
    assert diff.rows() == [
        ("params.half_spread_ticks", "0", "4"),
        ("exec.entry_latency_ns", "10,000,000", "50,000,000"),
    ]


def test_config_diff_is_empty_for_identical_settings():
    config = synthetic_config(Path("x.npz"))

    diff = config_diff({"a": config, "b": config})

    assert diff.height == 0
    assert diff.columns == ["setting", "a", "b"]


def test_config_diff_summarises_data_files_instead_of_listing_them():
    one_hour = synthetic_config(Path("x.npz"), data_files=["npz/d_p000.npz"])
    two_hours = synthetic_config(Path("x.npz"), data_files=["npz/d_p000.npz", "npz/d_p001.npz"])

    diff = config_diff({"short": one_hour, "long": two_hours})

    assert diff.rows() == [("data", "1 files from d_p000", "2 files from d_p000")]


def test_metrics_comparison_formats_numbers_and_marks_missing_ones(run_dir, tmp_path):
    old = copy_run(run_dir, tmp_path, "2026-10-17_120000_old_a")
    make_version_1_run(old)
    new_metrics = load_run(run_dir).metrics
    old_metrics = load_run(old).metrics
    assert isinstance(new_metrics, Metrics)

    table = metrics_comparison({"new": new_metrics, "old": old_metrics})

    rows = {row["metric"]: row for row in table.iter_rows(named=True)}
    assert table.columns == ["metric", "new", "old"]
    assert rows["Markout 1 s (bps)"]["old"] == "n/a"
    assert rows["Markout 1 s (bps)"]["new"] != "n/a"
    assert rows["Fills"]["new"] == rows["Fills"]["old"] == f"{new_metrics.fill_count:,}"


def test_equity_is_read_against_hours_since_the_start(run_dir, tmp_path):
    equity = read_equity(run_dir, 100_000_000)

    assert equity.columns == ["hours", "equity"]
    assert equity["hours"][0] == 0.0
    assert equity["hours"].is_sorted()
    assert equity["hours"][-1] == pytest.approx(59.9 / 3600, rel=0.02)
    assert pl.read_parquet(run_dir / "timeseries.parquet")["equity"][-1] == equity["equity"][-1]
