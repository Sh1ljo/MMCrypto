import streamlit as st

from dashboard.charts import colors_for, latency_by_file_figure, latency_histogram_figure
from dashboard.help_text import HELP
from mmlab.data.latency import (
    LatencyReport,
    latency_path,
    load_latency,
    measure_feed_latency,
    save_latency,
)
from mmlab.data.manifest import ManifestEntry, load_manifest
from mmlab.settings import data_dir, latency_dir, manifest_path

PLOT_CONFIG = {"displaylogo": False}
MILLION = 1e6


def _entry_label(entry: ManifestEntry) -> str:
    return f"{entry.symbol} {entry.day} ({entry.report.events.event_count / MILLION:.1f}M events)"


def _ticks(value: float) -> str:
    return f"{value:g} tick" if value == 1 else f"{value:g} ticks"


def _show_day_summary(entry: ManifestEntry) -> None:
    events, book = entry.report.events, entry.report.book
    columns = st.columns(6)
    columns[0].metric("Events", f"{events.event_count / MILLION:.1f}M", help=HELP["events"])
    columns[1].metric("Trades", f"{events.trade_count / MILLION:.2f}M", help=HELP["trades"])
    columns[2].metric("Longest gap", f"{events.max_gap_s:.2f} s", help=HELP["max_gap"])
    columns[3].metric("Spread median", _ticks(book.spread_ticks_p50), help=HELP["spread_p50"])
    columns[4].metric("Spread p99", _ticks(book.spread_ticks_p99), help=HELP["spread_p99"])
    columns[5].metric(
        "Trades / min", f"{events.trades_per_min_mean:,.0f}", help=HELP["trades_per_min"]
    )


def _show_latency(report: LatencyReport) -> None:
    columns = st.columns(5)
    columns[0].metric("Median", f"{report.p50_ms:.2f} ms", help=HELP["latency_p50"])
    columns[1].metric("99th percentile", f"{report.p99_ms:.1f} ms", help=HELP["latency_p99"])
    columns[2].metric("99.9th percentile", f"{report.p999_ms:.1f} ms", help=HELP["latency_p999"])
    columns[3].metric("Worst", f"{report.max_ms:,.0f} ms", help=HELP["latency_max"])
    columns[4].metric("Events measured", f"{report.events / MILLION:.1f}M", help=HELP["events"])
    colors = colors_for(st.context.theme.type)
    histogram_column, file_column = st.columns(2, gap="large")
    with histogram_column:
        st.markdown("**Distribution**", help=HELP["latency_histogram"])
        st.plotly_chart(latency_histogram_figure(report, colors), theme=None, config=PLOT_CONFIG)
    with file_column:
        st.markdown("**Through the day**", help=HELP["latency_by_file"])
        st.plotly_chart(latency_by_file_figure(report, colors), theme=None, config=PLOT_CONFIG)


st.title("Data explorer", help=HELP["data_explorer_page"])

entries = load_manifest(manifest_path()).files
if not entries:
    st.warning("No data registered. Run the download and ingest commands first (see README).")
    st.stop()

index = st.selectbox(
    "Data day",
    range(len(entries)),
    format_func=lambda i: _entry_label(entries[i]),
    help=HELP["explorer_day"],
)
entry = entries[index]

st.subheader("The day", help=HELP["day_summary"])
_show_day_summary(entry)

st.subheader("Feed latency", help=HELP["latency_section"])
path = latency_path(latency_dir(), entry.symbol, entry.day)
report = load_latency(path)
is_measure_clicked = report is None and st.button(
    "Measure feed latency", type="primary", help=HELP["latency_measure"]
)
if is_measure_clicked:
    with st.spinner("Reading the day's files..."):
        report = measure_feed_latency(entry, data_dir())
        save_latency(path, report)
if report is not None:
    _show_latency(report)
