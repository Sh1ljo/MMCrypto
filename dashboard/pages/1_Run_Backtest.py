import time

import streamlit as st

from dashboard.help_text import HELP
from dashboard.lib import (
    BPS,
    NS_PER_MS,
    RunForm,
    RunProcess,
    load_run,
    missing_files,
    start_run,
    write_ui_config,
)
from dashboard.ui import open_in_explorer, show_kpis
from mmlab.config import ExecConfig, RunConfig
from mmlab.data.manifest import ManifestEntry, load_manifest
from mmlab.run import STRATEGIES, runs_dir
from mmlab.settings import data_dir, manifest_path

POLL_S = 0.25
LOG_PLACEHOLDER = "starting..."
DEFAULT_RUN = RunConfig(name="default", strategy="naive", data_files=[], tick_size=1, lot_size=1)
DEFAULT_EXEC = ExecConfig()


def _entry_label(entry: ManifestEntry) -> str:
    events = entry.report.events.event_count / 1e6
    suffix = "" if entry.passed else " - VALIDATION FAILED"
    return f"{entry.symbol} {entry.day} ({events:.1f}M events){suffix}"


def _auto_name(strategy: str, half_spread_ticks: float, entry: ManifestEntry, files: int) -> str:
    name = f"{strategy}_hs{half_spread_ticks:g}_{entry.day:%Y%m%d}"
    return name if files == len(entry.paths) else f"{name}_{files}f"


def _data_inputs(entries: list[ManifestEntry]) -> tuple[ManifestEntry, int]:
    index = st.selectbox(
        "Data day",
        range(len(entries)),
        format_func=lambda i: _entry_label(entries[i]),
        help=HELP["data_day"],
    )
    entry = entries[index]
    files = len(entry.paths)
    if files > 1:
        files = st.slider(
            "Files to replay", 1, files, files, key=f"files_{index}", help=HELP["files"]
        )
    hours = entry.report.events.duration_s / 3600 * files / len(entry.paths)
    st.caption(f"About {hours:.1f} h of data. Tick {entry.tick_size:g}, lot {entry.lot_size:g}.")
    return entry, files


def _strategy_inputs() -> dict:
    strategy = st.selectbox("Strategy", STRATEGIES, help=HELP["strategy_choice"])
    half_spread_ticks = st.number_input(
        "Half spread (ticks)", min_value=0.0, value=5.0, step=0.5, help=HELP["half_spread"]
    )
    order_qty = st.number_input(
        "Order size",
        min_value=0.0,
        value=DEFAULT_RUN.order_qty,
        format="%g",
        step=0.001,
        help=HELP["order_qty"],
    )
    max_position = st.number_input(
        "Max position",
        min_value=0.0,
        value=DEFAULT_RUN.max_position,
        format="%g",
        step=0.001,
        help=HELP["max_position"],
    )
    step_ms = st.number_input(
        "Refresh every (ms)",
        min_value=1.0,
        value=DEFAULT_RUN.step_ns / NS_PER_MS,
        step=10.0,
        help=HELP["step"],
    )
    return {
        "strategy": strategy,
        "half_spread_ticks": half_spread_ticks,
        "step_ms": step_ms,
        "order_qty": order_qty,
        "max_position": max_position,
    }


def _fee_and_delay_inputs() -> dict:
    maker_fee_bps = st.number_input(
        "Maker fee (bps)",
        value=round(DEFAULT_EXEC.maker_fee * BPS, 6),
        step=0.1,
        format="%g",
        help=HELP["maker_fee"],
    )
    taker_fee_bps = st.number_input(
        "Taker fee (bps)",
        value=round(DEFAULT_EXEC.taker_fee * BPS, 6),
        step=0.1,
        format="%g",
        help=HELP["taker_fee"],
    )
    entry_latency_ms = st.number_input(
        "Order delay to exchange (ms)",
        min_value=0.0,
        value=DEFAULT_EXEC.entry_latency_ns / NS_PER_MS,
        step=1.0,
        help=HELP["entry_latency"],
    )
    resp_latency_ms = st.number_input(
        "Reply delay from exchange (ms)",
        min_value=0.0,
        value=DEFAULT_EXEC.resp_latency_ns / NS_PER_MS,
        step=1.0,
        help=HELP["resp_latency"],
    )
    return {
        "maker_fee_bps": maker_fee_bps,
        "taker_fee_bps": taker_fee_bps,
        "entry_latency_ms": entry_latency_ms,
        "resp_latency_ms": resp_latency_ms,
    }


def _queue_inputs() -> dict:
    queue_model = st.selectbox(
        "Queue model", ["power_prob", "risk_adverse"], help=HELP["queue_model"]
    )
    queue_power = st.number_input(
        "Queue power",
        min_value=1.0,
        value=DEFAULT_EXEC.queue_power,
        step=0.5,
        disabled=queue_model != "power_prob",
        help=HELP["queue_power"],
    )
    partial_fill = st.checkbox(
        "Partial fills", value=DEFAULT_EXEC.partial_fill, help=HELP["partial_fill"]
    )
    return {"queue_model": queue_model, "queue_power": queue_power, "partial_fill": partial_fill}


def _watch(process: RunProcess) -> None:
    label = "Running backtest" if process.is_running else "Backtest finished"
    with st.status(label, expanded=process.is_running) as status:
        log_box = st.empty()
        while process.is_running:
            status.update(label=f"Running backtest... {process.elapsed_s:.0f} s", expanded=True)
            log_box.code("\n".join(process.lines) or LOG_PLACEHOLDER)
            time.sleep(POLL_S)
        log_box.code("\n".join(process.lines))
        is_ok = process.returncode == 0
        status.update(
            label=f"{'Done' if is_ok else 'Failed'} in {process.elapsed_s:.0f} s",
            state="complete" if is_ok else "error",
            expanded=not is_ok,
        )


def _report(process: RunProcess) -> None:
    run_id = process.run_id
    if run_id is None:
        st.error("The runner exited before creating a run folder. See the log above.")
        return
    run = load_run(runs_dir() / run_id)
    if run.status != "ok" or run.metrics is None:
        st.error(f"Run {run_id} ended with status {run.status}: {run.error}")
        return
    show_kpis(run.metrics)
    if st.button("Open in explorer", type="primary"):
        open_in_explorer(run_id)


st.title("Run a backtest", help=HELP["run_page"])

entries = load_manifest(manifest_path()).files
if not entries:
    st.warning("No data registered. Run the download and ingest commands first (see README).")
    st.stop()

data_column, strategy_column = st.columns(2, gap="large")
with data_column:
    st.subheader("Data", help=HELP["data_section"])
    entry, files = _data_inputs(entries)
with strategy_column:
    st.subheader("Strategy", help=HELP["strategy_section"])
    strategy_values = _strategy_inputs()

with st.expander("Execution assumptions: fees, delays, queue"):
    fees_column, queue_column = st.columns(2, gap="large")
    with fees_column:
        execution_values = _fee_and_delay_inputs()
    with queue_column:
        execution_values |= _queue_inputs()

auto_name = _auto_name(
    strategy_values["strategy"], strategy_values["half_spread_ticks"], entry, files
)
typed_name = st.text_input("Run name", placeholder=auto_name, help=HELP["run_name"])
form = RunForm(name=typed_name or auto_name, files=files, **strategy_values, **execution_values)

try:
    config = form.to_config(entry)
except ValueError as error:
    st.error(str(error))
    st.stop()

missing = missing_files(config, data_dir())
if missing:
    st.error(f"{len(missing)} data file(s) not found under {data_dir()}, first: {missing[0]}")
if not entry.passed:
    st.error("This day failed validation: " + "; ".join(entry.problems))

can_run = not missing and entry.passed
if st.button("Run backtest", type="primary", disabled=not can_run, help=HELP["run_button"]):
    st.session_state["run_process"] = start_run(write_ui_config(config))

with st.expander("Show the exact config"):
    st.code(config.model_dump_json(indent=2), language="json")

process = st.session_state.get("run_process")
if process is not None:
    _watch(process)
    _report(process)
