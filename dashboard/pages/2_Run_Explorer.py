from datetime import timedelta

import polars as pl
import streamlit as st

from dashboard.charts import colors_for, distribution_figure, markout_figure, run_figure
from dashboard.help_text import HELP
from dashboard.lib import (
    BPS,
    HARD_MAX_POINTS,
    NS_PER_HOUR,
    NS_PER_S,
    RunInfo,
    datetime_to_ns,
    list_runs,
    ns_to_datetime,
    pick_resolution_ns,
    read_fills,
    read_markouts,
    read_timeseries,
    run_label,
    time_range_ns,
)
from dashboard.ui import show_detail_kpis, show_kpis, show_markout_kpis
from mmlab.run import runs_dir

AUTO = "Auto"
RESOLUTIONS_NS = {
    "Full (every step)": 0,
    "1 s": NS_PER_S,
    "10 s": 10 * NS_PER_S,
    "1 min": 60 * NS_PER_S,
}
PLOT_CONFIG = {"displaylogo": False}


def _pick_run(runs: list[RunInfo]) -> RunInfo:
    by_id = {run.run_id: run for run in runs}
    requested = st.session_state.pop("selected_run", None)
    if requested in by_id:
        st.session_state["explorer_run"] = requested
    chosen = st.selectbox(
        "Run",
        list(by_id),
        key="explorer_run",
        format_func=lambda run_id: run_label(by_id[run_id]),
        help=HELP["explorer_run"],
    )
    return by_id[chosen]


def _show_log(run: RunInfo) -> None:
    log_path = run.path / "log.txt"
    if log_path.is_file():
        with st.expander("Log", expanded=run.status != "ok"):
            st.code(log_path.read_text(encoding="utf-8"))


def _show_problem(run: RunInfo) -> None:
    if run.status == "incomplete":
        st.warning("This run has no metrics.json: it is still running or was killed.")
    else:
        st.error(f"Run status is {run.status}: {run.error}")
    _show_log(run)


def _window(run_id: str, start_ns: int, end_ns: int) -> tuple[int, int]:
    step = timedelta(seconds=1) if end_ns - start_ns <= NS_PER_HOUR else timedelta(minutes=1)
    first, last = ns_to_datetime(start_ns), ns_to_datetime(end_ns)
    if last - first <= step:
        return start_ns, end_ns
    low, high = st.slider(
        "Window (UTC)",
        min_value=first,
        max_value=last,
        value=(first, last),
        step=step,
        format="MM-DD HH:mm:ss",
        key=f"window_{run_id}",
        help=HELP["window"],
    )
    return (
        start_ns if low == first else datetime_to_ns(low),
        end_ns if high == last else datetime_to_ns(high),
    )


def _resolution_ns(choice: str, window_ns: int, step_ns: int) -> int:
    if choice == AUTO:
        return pick_resolution_ns(window_ns, step_ns)
    return max(RESOLUTIONS_NS[choice], step_ns)


def _table_views(timeseries: pl.DataFrame, fills: pl.DataFrame) -> None:
    with st.expander("Table view"):
        steps_tab, fills_tab = st.tabs(["Steps", "Fills"])
        for tab, frame in ((steps_tab, timeseries), (fills_tab, fills)):
            readable = frame.with_columns(time_utc=pl.from_epoch("ts", time_unit="ns")).drop("ts")
            tab.dataframe(readable, hide_index=True, width="stretch")


def _show_record(run: RunInfo) -> None:
    record = run.record
    dirty = " (uncommitted changes)" if record.git_dirty else ""
    st.caption(
        f"Run folder {run.run_id}. Code commit {record.git_commit[:8]}{dirty}, "
        f"hftbacktest {record.hftbacktest_version}, runtime {run.runtime_s:.1f} s."
    )
    with st.expander("Config"):
        st.json(record.model_dump(mode="json"))
    _show_log(run)


st.title("Run Explorer", help=HELP["explorer_page"])

runs = list_runs(runs_dir())
if not runs:
    st.info("No runs yet. Start one from the Run Backtest page.")
    st.stop()

run = _pick_run(runs)
if run.status != "ok":
    _show_problem(run)
    st.stop()

config = run.record.config
st.subheader("Results", help=HELP["results"])
show_kpis(run.metrics)
show_detail_kpis(run.metrics)
show_markout_kpis(run.metrics)

st.subheader("Overview", help=HELP["overview"])
start_ns, end_ns = time_range_ns(run.path)
window_column, resolution_column = st.columns([3, 1], gap="large")
with window_column:
    window_start_ns, window_end_ns = _window(run.run_id, start_ns, end_ns)
with resolution_column:
    choice = st.selectbox(
        "Resolution",
        [AUTO, *RESOLUTIONS_NS],
        key=f"resolution_{run.run_id}",
        help=HELP["resolution"],
    )

every_ns = _resolution_ns(choice, window_end_ns - window_start_ns, config.step_ns)
points = (window_end_ns - window_start_ns) / every_ns
if points > HARD_MAX_POINTS:
    st.error(
        f"{points:,.0f} points is too many to draw (limit {HARD_MAX_POINTS:,}). "
        "Narrow the window or pick a coarser resolution."
    )
    st.stop()

timeseries = read_timeseries(run.path, window_start_ns, window_end_ns, every_ns, config.step_ns)
fills = read_fills(run.path, window_start_ns, window_end_ns)
colors = colors_for(st.context.theme.type)
st.caption(
    f"{timeseries.height:,} points (one per {every_ns / NS_PER_S:g} s), "
    f"{fills.height:,} fills in this window"
)
st.plotly_chart(
    run_figure(timeseries, fills, config.max_position, colors), theme=None, config=PLOT_CONFIG
)

raw_steps = (
    timeseries
    if every_ns == config.step_ns
    else read_timeseries(run.path, window_start_ns, window_end_ns, config.step_ns, config.step_ns)
)
st.subheader("Markouts", help=HELP["markouts"])
markouts = read_markouts(run.path)
if markouts is None:
    st.info(HELP["no_markouts"])
else:
    st.plotly_chart(
        markout_figure(markouts, config.exec.maker_fee * BPS, colors),
        theme=None,
        config=PLOT_CONFIG,
    )

st.subheader("Distributions", help=HELP["distributions"])
st.plotly_chart(
    distribution_figure(raw_steps, fills, config.tick_size, config.lot_size, colors),
    theme=None,
    config=PLOT_CONFIG,
)
_table_views(timeseries, fills)
_show_record(run)
