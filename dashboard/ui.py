import streamlit as st

from dashboard.help_text import HELP
from mmlab.analytics.metrics import Metrics

EXPLORER_PAGE = "pages/2_Run_Explorer.py"


def _optional(value: float | None, template: str) -> str:
    return "n/a" if value is None else template.format(value)


def open_in_explorer(run_id: str) -> None:
    st.session_state["selected_run"] = run_id
    st.switch_page(EXPLORER_PAGE)


# headline numbers of one run, in quote currency (USDT)
def show_kpis(metrics: Metrics) -> None:
    columns = st.columns(6)
    columns[0].metric("Net PnL", f"{metrics.net_pnl:,.2f}", help=HELP["net_pnl"])
    columns[1].metric("Gross PnL", f"{metrics.gross_pnl:,.2f}", help=HELP["gross_pnl"])
    columns[2].metric("Fees paid", f"{metrics.fees_paid:,.2f}", help=HELP["fees_paid"])
    columns[3].metric(
        "Sharpe", _optional(metrics.sharpe_hourly_annualized, "{:,.1f}"), help=HELP["sharpe"]
    )
    columns[4].metric("Max drawdown", f"{metrics.max_drawdown:,.2f}", help=HELP["max_drawdown"])
    columns[5].metric("Fills", f"{metrics.fill_count:,}", help=HELP["fills"])


def show_detail_kpis(metrics: Metrics) -> None:
    columns = st.columns(6)
    columns[0].metric("Fills / hour", f"{metrics.fills_per_hour:,.0f}", help=HELP["fills_per_hour"])
    columns[1].metric(
        "Return over trade (bps)",
        _optional(metrics.return_over_trade_bps, "{:,.2f}"),
        help=HELP["return_over_trade_bps"],
    )
    columns[2].metric(
        "Spread captured (bps)",
        _optional(metrics.spread_captured_bps, "{:,.2f}"),
        help=HELP["spread_captured_bps"],
    )
    columns[3].metric(
        "Mean |position|", f"{metrics.mean_abs_position:.4g}", help=HELP["mean_abs_position"]
    )
    columns[4].metric(
        "Time at limit", f"{metrics.pct_time_at_limit:.1f}%", help=HELP["time_at_limit"]
    )
    columns[5].metric("Time quoted", f"{metrics.pct_time_quoted:.1f}%", help=HELP["time_quoted"])


# adverse selection: what fills were worth afterwards, and how long inventory lingers
def show_markout_kpis(metrics: Metrics) -> None:
    columns = st.columns(6)
    columns[0].metric(
        "Markout 1 s (bps)",
        _optional(metrics.avg_markout_1s_bps, "{:,.2f}"),
        help=HELP["markout_1s"],
    )
    columns[1].metric(
        "Markout 10 s (bps)",
        _optional(metrics.avg_markout_10s_bps, "{:,.2f}"),
        help=HELP["markout_10s"],
    )
    columns[2].metric(
        "Inventory half-life",
        _optional(metrics.inventory_half_life_s, "{:,.1f} s"),
        help=HELP["inventory_half_life"],
    )
