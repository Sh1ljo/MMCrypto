import streamlit as st

from dashboard.help_text import HELP
from dashboard.lib import list_runs, runs_table
from dashboard.ui import open_in_explorer
from mmlab.data.manifest import load_manifest
from mmlab.run import runs_dir
from mmlab.settings import manifest_path

COLUMN_ORDER = [
    "started",
    "name",
    "data",
    "strategy",
    "params",
    "status",
    "net_pnl",
    "gross_pnl",
    "fees_paid",
    "sharpe",
    "max_drawdown",
    "fills",
    "runtime_s",
]
COLUMN_CONFIG = {
    "started": st.column_config.DatetimeColumn(
        "Started (UTC)", format="YYYY-MM-DD HH:mm:ss", help=HELP["started"]
    ),
    "name": st.column_config.TextColumn("Name", help=HELP["name"]),
    "data": st.column_config.TextColumn("Data", help=HELP["data"]),
    "strategy": st.column_config.TextColumn("Strategy", help=HELP["strategy"]),
    "params": st.column_config.TextColumn("Params", help=HELP["params"]),
    "status": st.column_config.TextColumn("Status", help=HELP["status"]),
    "net_pnl": st.column_config.NumberColumn("Net PnL", format="%.2f", help=HELP["net_pnl"]),
    "gross_pnl": st.column_config.NumberColumn("Gross PnL", format="%.2f", help=HELP["gross_pnl"]),
    "fees_paid": st.column_config.NumberColumn("Fees", format="%.2f", help=HELP["fees_paid"]),
    "sharpe": st.column_config.NumberColumn("Sharpe", format="%.1f", help=HELP["sharpe"]),
    "max_drawdown": st.column_config.NumberColumn(
        "Max drawdown", format="%.2f", help=HELP["max_drawdown"]
    ),
    "fills": st.column_config.NumberColumn("Fills", format="%d", help=HELP["fills"]),
    "runtime_s": st.column_config.NumberColumn("Runtime (s)", format="%.1f", help=HELP["runtime"]),
}

st.title("Your runs", help="Every backtest saved under runs/. Select a row to inspect it.")

runs = list_runs(runs_dir())
if not runs:
    st.info("No runs yet. Start one from the Run Backtest page.")
    st.page_link("pages/1_Run_Backtest.py", label="Run Backtest", icon=":material/play_arrow:")
    st.stop()

table = runs_table(runs, load_manifest(manifest_path()))
event = st.dataframe(
    table,
    key="runs_table",
    on_select="rerun",
    selection_mode="single-row",
    hide_index=True,
    width="stretch",
    column_order=COLUMN_ORDER,
    column_config=COLUMN_CONFIG,
)
selected_rows = event.selection.rows
if st.button("Open in explorer", type="primary", disabled=not selected_rows):
    open_in_explorer(table["run_id"][selected_rows[0]])
