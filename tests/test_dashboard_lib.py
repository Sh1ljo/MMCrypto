import shutil
import sys
import time
from datetime import date, datetime
from pathlib import Path

import polars as pl
import pytest

from dashboard.lib import (
    NS_PER_S,
    RunForm,
    RunProcess,
    data_label,
    datetime_to_ns,
    list_runs,
    missing_files,
    ns_to_datetime,
    pick_resolution_ns,
    preview_quotes,
    read_fills,
    read_timeseries,
    runs_table,
    started_at,
    time_range_ns,
    write_ui_config,
)
from mmlab.config import ExecConfig, RunConfig
from mmlab.data.manifest import Manifest
from mmlab.run import run_backtest
from tests.synthetic_events import synthetic_config, write_synthetic_day
from tests.synthetic_manifest import manifest_entry

STEP_NS = 100_000_000
BASE_NS = 10 * NS_PER_S


def default_form(**overrides) -> RunForm:
    fields = {
        "name": "naive_hs5",
        "strategy": "naive",
        "files": 2,
        "half_spread_ticks": 5.0,
        "step_ms": 100.0,
        "order_qty": 0.001,
        "max_position": 0.01,
        "maker_fee_bps": 2.0,
        "taker_fee_bps": 5.0,
        "entry_latency_ms": 10.0,
        "resp_latency_ms": 10.0,
        "queue_model": "power_prob",
        "queue_power": 2.0,
        "partial_fill": False,
    }
    return RunForm.model_validate(fields | overrides)


@pytest.fixture(scope="module")
def run_dir(tmp_path_factory) -> Path:
    data = write_synthetic_day(tmp_path_factory.mktemp("data") / "day.npz")
    return run_backtest(synthetic_config(data), tmp_path_factory.mktemp("runs"))


def write_steps(path: Path, rows: int) -> Path:
    frame = pl.DataFrame(
        {"ts": [BASE_NS + k * STEP_NS for k in range(rows)], "position": list(range(rows))}
    )
    frame.write_parquet(path / "timeseries.parquet")
    return path


def test_form_defaults_reproduce_the_runner_defaults():
    entry = manifest_entry(["a", "b", "c"], date(2026, 10, 1))

    config = default_form().to_config(entry)

    assert config.exec == ExecConfig()
    assert config.step_ns == RunConfig.model_fields["step_ns"].default
    assert config.data_files == ["a", "b"]
    assert (config.tick_size, config.lot_size) == (0.1, 0.001)
    assert config.params == {"half_spread_ticks": 5.0}


def test_form_converts_bps_and_milliseconds():
    entry = manifest_entry(["a"], date(2026, 10, 1))

    config = default_form(
        files=1, maker_fee_bps=-1.5, entry_latency_ms=0.5, resp_latency_ms=50.0, step_ms=250.0
    ).to_config(entry)

    assert config.exec.maker_fee == pytest.approx(-0.00015)
    assert config.exec.entry_latency_ns == 500_000
    assert config.exec.resp_latency_ns == 50_000_000
    assert config.step_ns == 250_000_000


@pytest.mark.parametrize("name", ["", "has space", "../escape", "-leading", "a/b"])
def test_form_rejects_unsafe_run_names(name):
    entry = manifest_entry(["a", "b"], date(2026, 10, 1))
    with pytest.raises(ValueError, match="run name"):
        default_form(name=name).to_config(entry)


@pytest.mark.parametrize("files", [0, 3])
def test_form_rejects_file_counts_outside_the_day(files):
    entry = manifest_entry(["a", "b"], date(2026, 10, 1))
    with pytest.raises(ValueError, match="files must be between 1 and 2"):
        default_form(files=files).to_config(entry)


def test_missing_files_lists_only_absent_paths(tmp_path):
    (tmp_path / "here.npz").write_bytes(b"")
    config = synthetic_config(tmp_path / "x.npz", data_files=["here.npz", "gone.npz"])

    assert missing_files(config, tmp_path) == ["gone.npz"]


def test_ui_config_round_trips_through_the_runner_loader(tmp_path):
    config = default_form().to_config(manifest_entry(["a", "b"], date(2026, 10, 1)))

    path = write_ui_config(config, tmp_path / "_ui")

    assert path.name == "naive_hs5.json"
    assert RunConfig.model_validate_json(path.read_text(encoding="utf-8")) == config


def test_list_runs_reports_every_status_newest_first(run_dir, tmp_path):
    root = tmp_path / "runs"
    shutil.copytree(run_dir, root / "2026-10-17_120000_ok_a")
    failed = shutil.copytree(run_dir, root / "2026-10-17_120001_failed_b")
    (failed / "metrics.json").write_text(
        '{"status": "failed", "error": "ValueError(boom)", "runtime_s": 1.5}', encoding="utf-8"
    )
    incomplete = shutil.copytree(run_dir, root / "2026-10-17_120002_incomplete_c")
    (incomplete / "metrics.json").unlink()
    broken = shutil.copytree(run_dir, root / "2026-10-17_120003_broken_d")
    (broken / "config.json").write_text("{not json", encoding="utf-8")
    (root / "notes.txt").write_text("a stray file is ignored", encoding="utf-8")

    runs = list_runs(root)

    assert [(r.run_id, r.status) for r in runs] == [
        ("2026-10-17_120003_broken_d", "unreadable"),
        ("2026-10-17_120002_incomplete_c", "incomplete"),
        ("2026-10-17_120001_failed_b", "failed"),
        ("2026-10-17_120000_ok_a", "ok"),
    ]
    assert runs[2].error == "ValueError(boom)"
    assert runs[3].metrics.fill_count > 0
    assert runs[0].error


def test_list_runs_of_a_missing_folder_is_empty(tmp_path):
    assert list_runs(tmp_path / "nope") == []


def test_runs_table_has_one_row_per_run(run_dir, tmp_path):
    root = tmp_path / "runs"
    shutil.copytree(run_dir, root / "2026-10-17_120000_ok_a")
    shutil.copytree(run_dir, root / "2026-10-17_120001_ok_b")

    table = runs_table(list_runs(root), Manifest())

    assert table["run_id"].to_list() == ["2026-10-17_120001_ok_b", "2026-10-17_120000_ok_a"]
    assert table["started"][0] == datetime(2026, 10, 17, 12, 0, 1)
    assert table["status"].unique().to_list() == ["ok"]
    assert table["fills"].min() > 0
    assert table["params"][0] == "half_spread_ticks=0"


def test_started_at_parses_run_folder_names_only():
    assert started_at("2026-10-17_145719_naive_btcusdt_e5cc13") == datetime(
        2026, 10, 17, 14, 57, 19
    )
    assert started_at("scratch") is None


def test_data_label_names_the_day_and_a_prefix_of_its_files():
    manifest = Manifest(files=[manifest_entry(["a", "b", "c"], date(2026, 10, 1))])

    def label(files: list[str]) -> str:
        return data_label(synthetic_config(Path("x.npz"), data_files=files), manifest)

    assert label(["a", "b", "c"]) == "BTCUSDT 2026-10-01"
    assert label(["a", "b"]) == "BTCUSDT 2026-10-01 (first 2 of 3 files)"
    assert label(["elsewhere/other.npz"]) == "other"


@pytest.mark.parametrize(
    ("window_s", "step_ns", "expected_ns"),
    [
        (3_600, STEP_NS, STEP_NS),
        (86_400, STEP_NS, 10 * NS_PER_S),
        (30 * 86_400, NS_PER_S, 60 * NS_PER_S),
        (30 * 86_400, 120 * NS_PER_S, 120 * NS_PER_S),
    ],
)
def test_auto_resolution_keeps_the_window_under_the_point_budget(window_s, step_ns, expected_ns):
    assert pick_resolution_ns(window_s * NS_PER_S, step_ns) == expected_ns


def test_datetime_conversion_round_trips_microseconds():
    ts_ns = 1_782_864_000_060_616_000
    moment = ns_to_datetime(ts_ns)

    assert moment == datetime(2026, 7, 1, 0, 0, 0, 60616)
    assert datetime_to_ns(moment) == ts_ns


def test_time_range_reads_first_and_last_step(tmp_path):
    write_steps(tmp_path, rows=30)

    assert time_range_ns(tmp_path) == (BASE_NS, BASE_NS + 29 * STEP_NS)


def test_resampling_keeps_the_last_row_of_each_bucket(tmp_path):
    write_steps(tmp_path, rows=30)

    coarse = read_timeseries(tmp_path, 0, BASE_NS + 10 * NS_PER_S, NS_PER_S, STEP_NS)

    assert coarse["position"].to_list() == [9, 19, 29]
    assert coarse["ts"].to_list() == [BASE_NS + 900_000_000 + i * NS_PER_S for i in range(3)]


def test_window_bounds_are_inclusive_and_full_resolution_is_untouched(tmp_path):
    write_steps(tmp_path, rows=30)

    window = read_timeseries(
        tmp_path, BASE_NS + NS_PER_S, BASE_NS + 2_500_000_000, STEP_NS, STEP_NS
    )

    assert window["position"].to_list() == list(range(10, 26))


def test_real_run_reads_back_through_the_dashboard_loaders(run_dir):
    config = synthetic_config(Path("x.npz"))
    start_ns, end_ns = time_range_ns(run_dir)

    steps = read_timeseries(run_dir, start_ns, end_ns, config.step_ns, config.step_ns)
    fills = read_fills(run_dir, start_ns, end_ns)

    assert steps.height == pl.read_parquet(run_dir / "timeseries.parquet").height
    assert fills.height == pl.read_parquet(run_dir / "fills.parquet").height > 0
    assert steps["ts"].is_sorted()


def wait_for(process: RunProcess, timeout_s: float = 30.0) -> None:
    deadline = time.perf_counter() + timeout_s
    while process.is_running:
        assert time.perf_counter() < deadline, "process did not finish"
        time.sleep(0.02)


def test_run_process_collects_output_exit_code_and_run_id():
    code = "print('run 2026-10-17_x_abc'); print('caf\\u00e9 \\u017e'); print('done')"
    process = RunProcess([sys.executable, "-c", code])

    wait_for(process)

    assert process.lines == ["run 2026-10-17_x_abc", "café ž", "done"]
    assert process.returncode == 0
    assert process.run_id == "2026-10-17_x_abc"
    assert process.elapsed_s > 0


def test_run_process_reports_failure_and_merges_stderr():
    code = "import sys; print('out'); print('err', file=sys.stderr); sys.exit(3)"
    process = RunProcess([sys.executable, "-c", code])

    wait_for(process)

    assert process.returncode == 3
    assert sorted(process.lines) == ["err", "out"]
    assert process.run_id is None


def test_run_process_has_no_exit_code_while_running():
    process = RunProcess([sys.executable, "-c", "import time; time.sleep(1)"])

    assert process.is_running
    assert process.returncode is None

    wait_for(process)

    assert process.returncode == 0


def same_quote(actual: float | None, expected: float | None) -> bool:
    if expected is None:
        return actual is None
    return actual == pytest.approx(expected)


@pytest.mark.parametrize(
    ("half_spread", "position", "expected_bid", "expected_ask"),
    [
        (5.0, 0.0, 83_999.5, 84_000.6),
        (0.0, 0.0, 84_000.0, 84_000.1),
        (5.0, 0.01, None, 84_000.6),
        (5.0, -0.01, 83_999.5, None),
    ],
)
def test_preview_matches_hand_worked_quotes(half_spread, position, expected_bid, expected_ask):
    preview = preview_quotes(84_000.0, 84_000.1, half_spread, position, 0.001, 0.01, 0.1)

    assert preview.mid == pytest.approx(84_000.05)
    assert same_quote(preview.bid_quote, expected_bid)
    assert same_quote(preview.ask_quote, expected_ask)


def test_preview_rejects_a_crossed_book():
    with pytest.raises(ValueError, match="must be above"):
        preview_quotes(100.1, 100.0, 5.0, 0.0, 0.001, 0.01, 0.1)


def test_preview_agrees_with_every_step_of_a_real_run(tmp_path):
    data = write_synthetic_day(tmp_path / "day.npz")
    config = synthetic_config(data, max_position=0.003, order_qty=0.001)
    run = run_backtest(config, tmp_path / "runs")
    steps = pl.read_parquet(run / "timeseries.parquet")

    for row in steps.iter_rows(named=True):
        preview = preview_quotes(100.0, 100.1, 0.0, row["position"], 0.001, 0.003, 0.1)
        assert same_quote(row["bid_quote"], preview.bid_quote)
        assert same_quote(row["ask_quote"], preview.ask_quote)
    assert steps["bid_quote"].is_null().any()
    assert steps["ask_quote"].is_null().any()
