import streamlit as st

from dashboard.charts import colors_for, compare_equity_figure, compare_markout_figure
from dashboard.help_text import HELP
from dashboard.lib import (
    SERIES_SLOTS,
    RunInfo,
    assign_slots,
    compare_labels,
    config_diff,
    list_runs,
    metrics_comparison,
    read_equity,
    read_markouts,
    run_label,
)
from mmlab.run import runs_dir

PLOT_CONFIG = {"displaylogo": False}
SLOTS_KEY = "compare_slots"
DEFAULT_PICKS = 2


def _pick_runs(finished: list[RunInfo]) -> list[RunInfo]:
    by_id = {run.run_id: run for run in finished}
    chosen = st.multiselect(
        "Runs",
        list(by_id),
        default=list(by_id)[:DEFAULT_PICKS],
        max_selections=SERIES_SLOTS,
        format_func=lambda run_id: run_label(by_id[run_id]),
        help=HELP["compare_runs"],
    )
    return [by_id[run_id] for run_id in chosen]


st.title("Compare runs", help=HELP["compare_page"])

finished = [run for run in list_runs(runs_dir()) if run.status == "ok"]
if len(finished) < 2:
    st.info("Compare needs at least two finished runs. Start some from the Run Backtest page.")
    st.stop()

picked = _pick_runs(finished)
if len(picked) < 2:
    st.info("Pick at least two runs.")
    st.stop()

labels = compare_labels(picked)
slots = assign_slots([run.run_id for run in picked], st.session_state.get(SLOTS_KEY, {}))
st.session_state[SLOTS_KEY] = slots
slot_by_label = {labels[run_id]: slot for run_id, slot in slots.items()}
colors = colors_for(st.context.theme.type)

st.subheader("Numbers", help=HELP["compare_metrics"])
st.dataframe(
    metrics_comparison({labels[run.run_id]: run.metrics for run in picked}),
    hide_index=True,
    width="stretch",
    height="content",
)

equity_column, markout_column = st.columns(2, gap="large")
with equity_column:
    st.subheader("Net PnL over time", help=HELP["compare_equity"])
    equities = {
        labels[run.run_id]: read_equity(run.path, run.record.config.step_ns) for run in picked
    }
    st.plotly_chart(
        compare_equity_figure(equities, slot_by_label, colors), theme=None, config=PLOT_CONFIG
    )

with markout_column:
    st.subheader("Markouts", help=HELP["compare_markouts"])
    curves = {labels[run.run_id]: read_markouts(run.path) for run in picked}
    present = {label: curve for label, curve in curves.items() if curve is not None}
    if len(present) < len(curves):
        missing = ", ".join(label for label in curves if label not in present)
        st.warning(f"No markouts recorded for: {missing}. They were run before markouts existed.")
    if present:
        st.plotly_chart(
            compare_markout_figure(present, slot_by_label, colors),
            theme=None,
            config=PLOT_CONFIG,
        )

st.subheader("What differs", help=HELP["compare_settings"])
differences = config_diff({labels[run.run_id]: run.record.config for run in picked})
if differences.height == 0:
    st.info("These runs have identical settings.")
else:
    st.dataframe(differences, hide_index=True, width="stretch")
