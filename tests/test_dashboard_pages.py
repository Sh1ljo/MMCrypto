import shutil
from datetime import date
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from mmlab.data.manifest import upsert_entry
from mmlab.run import run_backtest
from tests.synthetic_events import synthetic_config, write_synthetic_day
from tests.synthetic_manifest import manifest_entry

DASHBOARD = Path(__file__).resolve().parents[1] / "dashboard"
OK_ID = "2026-10-17_120000_ok_a"
FAILED_ID = "2026-10-17_120001_failed_b"


def open_page(name: str) -> AppTest:
    return AppTest.from_file(str(DASHBOARD / name), default_timeout=60)


@pytest.fixture(scope="module")
def finished_run(tmp_path_factory) -> Path:
    data = write_synthetic_day(tmp_path_factory.mktemp("data") / "day.npz")
    return run_backtest(synthetic_config(data), tmp_path_factory.mktemp("runs"))


@pytest.fixture
def workspace(finished_run, tmp_path, monkeypatch) -> Path:
    runs = tmp_path / "runs"
    shutil.copytree(finished_run, runs / OK_ID)
    failed = shutil.copytree(finished_run, runs / FAILED_ID)
    (failed / "metrics.json").write_text(
        '{"status": "failed", "error": "ValueError(boom)", "runtime_s": 1.0}', encoding="utf-8"
    )
    data_root = tmp_path / "data"
    data_root.mkdir()
    (data_root / "day.npz").write_bytes(b"")
    manifest = data_root / "manifest.json"
    upsert_entry(manifest, manifest_entry(["day.npz"], date(2026, 10, 1)))
    monkeypatch.setattr("mmlab.run.runs_dir", lambda: runs)
    monkeypatch.setattr("mmlab.settings.manifest_path", lambda: manifest)
    monkeypatch.setattr("mmlab.settings.data_dir", lambda: data_root)
    return tmp_path


def test_home_lists_every_run_and_waits_for_a_selection(workspace):
    app = open_page("home.py").run()

    assert not app.exception
    assert len(app.dataframe[0].value) == 2
    assert app.button[0].disabled


def test_home_without_runs_points_to_the_run_page(workspace, monkeypatch):
    empty = workspace / "empty"
    empty.mkdir()
    monkeypatch.setattr("mmlab.run.runs_dir", lambda: empty)

    app = open_page("home.py").run()

    assert not app.exception
    assert "No runs yet" in app.info[0].value


def test_explorer_shows_a_failed_run_as_an_error_with_its_log(workspace):
    app = open_page("pages/2_Run_Explorer.py").run()

    assert not app.exception
    assert app.selectbox(key="explorer_run").value == FAILED_ID
    assert "failed" in app.error[0].value
    assert "ValueError(boom)" in app.error[0].value
    assert not app.metric


def test_explorer_draws_kpis_and_charts_for_a_finished_run(workspace):
    app = open_page("pages/2_Run_Explorer.py").run()

    app.selectbox(key="explorer_run").select(OK_ID).run()

    assert not app.exception
    assert not app.error
    assert len(app.metric) == 12
    assert [m.label for m in app.metric][:3] == ["Net PnL", "Gross PnL", "Fees paid"]
    assert len(app.get("plotly_chart")) == 2


def test_explorer_opens_the_run_requested_by_another_page(workspace):
    app = open_page("pages/2_Run_Explorer.py")
    app.session_state["selected_run"] = OK_ID

    app.run()

    assert app.selectbox(key="explorer_run").value == OK_ID
    assert len(app.metric) == 12


def test_explorer_resolution_choice_changes_the_point_spacing(workspace):
    app = open_page("pages/2_Run_Explorer.py").run()
    app.selectbox(key="explorer_run").select(OK_ID).run()
    assert "one per 0.1 s" in app.caption[0].value

    app.selectbox(key=f"resolution_{OK_ID}").select("10 s").run()

    assert not app.exception
    assert "one per 10 s" in app.caption[0].value


def test_run_page_builds_the_config_and_enables_the_button(workspace):
    app = open_page("pages/1_Run_Backtest.py").run()

    assert not app.exception
    assert not app.error
    assert not app.slider
    assert app.button[0].label == "Run backtest"
    assert not app.button[0].disabled
    assert '"half_spread_ticks": 5.0' in app.code[0].value


def test_run_page_blocks_an_unsafe_run_name(workspace):
    app = open_page("pages/1_Run_Backtest.py").run()

    app.text_input[0].set_value("../escape").run()

    assert "run name" in app.error[0].value
    assert len(app.button) == 0


def test_run_page_blocks_a_day_whose_files_are_missing(workspace):
    (workspace / "data" / "day.npz").unlink()

    app = open_page("pages/1_Run_Backtest.py").run()

    assert "not found" in app.error[0].value
    assert app.button[0].disabled


def test_run_page_without_data_asks_for_ingest(workspace):
    (workspace / "data" / "manifest.json").unlink()

    app = open_page("pages/1_Run_Backtest.py").run()

    assert not app.exception
    assert "No data registered" in app.warning[0].value


def widgets_without_help(app: AppTest) -> list[str]:
    kinds = (app.number_input, app.selectbox, app.slider, app.checkbox, app.text_input, app.button)
    return [widget.label for kind in kinds for widget in kind if not widget.help]


def test_every_input_on_the_run_page_explains_itself(workspace):
    app = open_page("pages/1_Run_Backtest.py").run()

    assert not app.exception
    assert widgets_without_help(app) == []
    assert len(app.number_input) == 9


def test_every_number_on_the_explorer_explains_itself(workspace):
    app = open_page("pages/2_Run_Explorer.py").run()
    app.selectbox(key="explorer_run").select(OK_ID).run()

    assert not app.exception
    assert widgets_without_help(app) == []
    assert [m.label for m in app.metric if not m.help] == []


def test_strategies_page_lists_every_phase_and_explains_the_calculator(workspace):
    app = open_page("pages/3_Strategies.py").run()

    assert not app.exception
    assert [tab.label for tab in app.tabs] == [
        "Naive (built)",
        "Avellaneda–Stoikov (Phase 5)",
        "GLFT (Phase 5)",
        "Alpha skew (Phase 6)",
        "How results are measured",
        "Glossary",
    ]
    assert widgets_without_help(app) == []
    assert [m.label for m in app.metric if not m.help] == []
    assert len(app.get("latex")) > 10


def test_calculator_defaults_match_the_hand_worked_example(workspace):
    app = open_page("pages/3_Strategies.py").run()

    values = {metric.label: metric.value for metric in app.metric}

    assert values == {"Mid": "84,000.05", "Your bid": "83,999.5", "Your ask": "84,000.6"}
    assert len(app.get("plotly_chart")) == 1


def test_calculator_follows_the_half_spread_and_the_position_limit(workspace):
    app = open_page("pages/3_Strategies.py").run()

    app.number_input(key="calc_half_spread").set_value(2.0).run()
    values = {metric.label: metric.value for metric in app.metric}
    assert (values["Your bid"], values["Your ask"]) == ("83,999.8", "84,000.3")

    app.number_input(key="calc_position").set_value(0.01).run()
    values = {metric.label: metric.value for metric in app.metric}
    assert (values["Your bid"], values["Your ask"]) == ("paused", "84,000.3")


def test_calculator_rejects_a_crossed_book_without_crashing(workspace):
    app = open_page("pages/3_Strategies.py").run()

    app.number_input(key="calc_best_ask").set_value(83_999.0).run()

    assert not app.exception
    assert "must be above" in app.error[0].value
    assert not app.metric
