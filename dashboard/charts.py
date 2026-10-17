from typing import NamedTuple

import numpy as np
import plotly.graph_objects as go
import polars as pl
from plotly.subplots import make_subplots

TRANSPARENT = "rgba(0,0,0,0)"
FONT_FAMILY = "system-ui, -apple-system, Segoe UI, sans-serif"
LINE_WIDTH = 2
MARKER_SIZE = 8
MARKER_OPACITY = 0.7
BAR_WIDTH_SHARE = 0.7
SPREAD_CUT_QUANTILE = 0.99
PRICE_ROW, POSITION_ROW, EQUITY_ROW = 1, 2, 3
BUY, SELL, MERGED = 1, -1, 0
MARKET_ROW, QUOTE_ROW = 1, 0
LADDER_HEIGHT = 190
LADDER_PAD_SHARE = 0.12


class ChartColors(NamedTuple):
    surface: str
    ink: str
    secondary: str
    muted: str
    grid: str
    axis: str
    bid: str
    ask: str
    position: str


LIGHT = ChartColors(
    surface="#fcfcfb",
    ink="#0b0b0b",
    secondary="#52514e",
    muted="#898781",
    grid="#e1e0d9",
    axis="#c3c2b7",
    bid="#2a78d6",
    ask="#eb6834",
    position="#1baf7a",
)
DARK = ChartColors(
    surface="#1a1a19",
    ink="#f0efec",
    secondary="#c3c2b7",
    muted="#898781",
    grid="#2c2c2a",
    axis="#383835",
    bid="#3987e5",
    ask="#d95926",
    position="#199e70",
)


def colors_for(theme_type: str | None) -> ChartColors:
    return DARK if theme_type == "dark" else LIGHT


# x values in UTC milliseconds, which is finer than any decision step
def _times(frame: pl.DataFrame) -> np.ndarray:
    return pl.from_epoch(frame["ts"], time_unit="ns").dt.cast_time_unit("ms").to_numpy()


def _line(
    frame: pl.DataFrame, column: str, name: str, color: str, template: str, width: int = LINE_WIDTH
) -> go.Scattergl:
    return go.Scattergl(
        x=_times(frame),
        y=frame[column].to_numpy(),
        mode="lines",
        name=name,
        line={"color": color, "width": width},
        hovertemplate=template,
    )


def _fill_trace(fills: pl.DataFrame, side: int, colors: ChartColors) -> go.Scattergl:
    style = {
        BUY: ("Buy fills", "triangle-up", colors.bid),
        SELL: ("Sell fills", "triangle-down", colors.ask),
        MERGED: ("Merged fills", "diamond", colors.muted),
    }[side]
    name, symbol, color = style
    chosen = fills.filter(pl.col("side") == side)
    return go.Scattergl(
        x=_times(chosen),
        y=chosen["price"].to_numpy(),
        mode="markers",
        name=name,
        customdata=chosen["qty"].to_numpy(),
        marker={
            "symbol": symbol,
            "size": MARKER_SIZE,
            "color": color,
            "opacity": MARKER_OPACITY,
            "line": {"color": colors.surface, "width": 1},
        },
        hovertemplate=f"{name[:-1].lower()} %{{customdata:.4g}} @ %{{y:,.1f}}<extra></extra>",
    )


def _add_price_panel(
    figure: go.Figure, timeseries: pl.DataFrame, fills: pl.DataFrame, colors: ChartColors
) -> None:
    lines = [
        _line(timeseries, "mid", "Mid", colors.muted, "mid %{y:,.2f}<extra></extra>", width=1),
        _line(timeseries, "bid_quote", "Bid quote", colors.bid, "bid %{y:,.1f}<extra></extra>"),
        _line(timeseries, "ask_quote", "Ask quote", colors.ask, "ask %{y:,.1f}<extra></extra>"),
    ]
    markers = [_fill_trace(fills, BUY, colors), _fill_trace(fills, SELL, colors)]
    if fills.filter(pl.col("side") == MERGED).height > 0:
        markers.append(_fill_trace(fills, MERGED, colors))
    for rank, trace in enumerate(lines + markers):
        trace.legendrank = rank
    # fills go first so that thousands of markers never hide the quote lines
    figure.add_traces(markers + lines, rows=PRICE_ROW, cols=1)


def _add_position_panel(
    figure: go.Figure, timeseries: pl.DataFrame, max_position: float, colors: ChartColors
) -> None:
    position = _line(
        timeseries, "position", "Position", colors.position, "position %{y:.4g}<extra></extra>"
    )
    position.line.shape = "hv"
    figure.add_trace(position, row=POSITION_ROW, col=1)
    limit = {"color": colors.muted, "width": 1, "dash": "dash"}
    figure.add_hline(
        y=max_position,
        row=POSITION_ROW,
        col=1,
        line=limit,
        annotation_text=f"limit ±{max_position:g}",
        annotation_position="top right",
        annotation_font_color=colors.secondary,
    )
    figure.add_hline(y=-max_position, row=POSITION_ROW, col=1, line=limit)


def _add_equity_panel(figure: go.Figure, timeseries: pl.DataFrame, colors: ChartColors) -> None:
    before_fees = timeseries.with_columns((pl.col("equity") + pl.col("fee")).alias("gross_equity"))
    figure.add_trace(
        _line(
            before_fees,
            "gross_equity",
            "Equity before fees",
            colors.muted,
            "before fees %{y:,.2f}<extra></extra>",
        ),
        row=EQUITY_ROW,
        col=1,
    )
    figure.add_trace(
        _line(
            timeseries, "equity", "Net equity", colors.ink, "net equity %{y:,.2f}<extra></extra>"
        ),
        row=EQUITY_ROW,
        col=1,
    )


def _style(figure: go.Figure, colors: ChartColors, height: int) -> None:
    figure.update_layout(
        height=height,
        margin={"l": 70, "r": 24, "t": 90, "b": 40},
        paper_bgcolor=TRANSPARENT,
        plot_bgcolor=colors.surface,
        font={"family": FONT_FAMILY, "color": colors.secondary, "size": 13},
        hovermode="x unified",
        hoverlabel={"bgcolor": colors.surface, "font": {"color": colors.ink}},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.0, "xanchor": "left", "x": 0},
    )
    figure.update_xaxes(
        gridcolor=colors.grid,
        linecolor=colors.axis,
        showspikes=True,
        spikemode="across",
        spikesnap="cursor",
        spikethickness=1,
        spikecolor=colors.axis,
        spikedash="solid",
    )
    figure.update_yaxes(gridcolor=colors.grid, linecolor=colors.axis, zerolinecolor=colors.axis)


# price, position and equity panels sharing one zoomable time axis
def run_figure(
    timeseries: pl.DataFrame, fills: pl.DataFrame, max_position: float, colors: ChartColors
) -> go.Figure:
    figure = make_subplots(
        rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.04, row_heights=[0.5, 0.2, 0.3]
    )
    _add_price_panel(figure, timeseries, fills, colors)
    _add_position_panel(figure, timeseries, max_position, colors)
    _add_equity_panel(figure, timeseries, colors)
    _style(figure, colors, height=820)
    figure.update_yaxes(title_text="Price (USDT)", row=PRICE_ROW, col=1)
    figure.update_yaxes(title_text="Position", row=POSITION_ROW, col=1)
    figure.update_yaxes(title_text="PnL (USDT)", row=EQUITY_ROW, col=1)
    figure.update_xaxes(title_text="Time (UTC)", row=EQUITY_ROW, col=1)
    return figure


# percent share of each value on a grid of `unit`, ordered by value
def _discrete_share(values: pl.Series, unit: float) -> tuple[np.ndarray, np.ndarray]:
    steps = (values.drop_nulls() / unit).round().cast(pl.Int64).alias("step")
    counts = steps.value_counts().sort("step")
    share = counts["count"].to_numpy() / max(len(steps), 1) * 100
    return counts["step"].to_numpy() * unit, share


def _bars(values: pl.Series, unit: float, color: str) -> go.Bar:
    x, share = _discrete_share(values, unit)
    return go.Bar(
        x=x,
        y=share,
        width=unit * BAR_WIDTH_SHARE,
        marker_color=color,
        hovertemplate="%{x:.4g}: %{y:.1f}%<extra></extra>",
    )


# cut the spread axis where a rare tail would shrink the bulk to a hairline, and say so in the title
def _spread_axis_title(figure: go.Figure, spread: pl.Series) -> str:
    title = "Spread (ticks)"
    valid = spread.drop_nulls()
    if valid.len() == 0:
        return title
    cut = valid.quantile(SPREAD_CUT_QUANTILE)
    if valid.max() <= cut:
        return title
    figure.update_xaxes(range=[valid.min() - 1, cut + 1], row=1, col=2)
    return f"{title}, axis cut at p{SPREAD_CUT_QUANTILE * 100:g} = {cut:g}"


# inventory, quoted spread and fill size distributions
def distribution_figure(
    timeseries: pl.DataFrame,
    fills: pl.DataFrame,
    tick_size: float,
    lot_size: float,
    colors: ChartColors,
) -> go.Figure:
    figure = make_subplots(
        rows=1,
        cols=3,
        subplot_titles=("Inventory", "Quoted spread", "Fill size"),
        horizontal_spacing=0.08,
    )
    quoted_spread = (timeseries["ask_quote"] - timeseries["bid_quote"]) / tick_size
    figure.add_trace(_bars(timeseries["position"], lot_size, colors.position), row=1, col=1)
    figure.add_trace(_bars(quoted_spread, 1.0, colors.muted), row=1, col=2)
    figure.add_trace(_bars(fills["qty"], lot_size, colors.muted), row=1, col=3)
    _style(figure, colors, height=300)
    figure.update_layout(showlegend=False, hovermode="closest", margin={"t": 40})
    figure.update_xaxes(showspikes=False)
    figure.update_xaxes(title_text="Position", row=1, col=1)
    figure.update_xaxes(title_text=_spread_axis_title(figure, quoted_spread), row=1, col=2)
    figure.update_xaxes(title_text="Quantity per fill", row=1, col=3)
    figure.update_yaxes(title_text="% of steps", row=1, col=1)
    figure.update_yaxes(title_text="% of quoted steps", row=1, col=2)
    figure.update_yaxes(title_text="% of fill rows", row=1, col=3)
    figure.update_annotations(font={"color": colors.secondary, "size": 13})
    return figure


# one labelled marker on the price ladder
def _ladder_marker(
    price: float, row: int, name: str, symbol: str, color: str, colors: ChartColors
) -> go.Scatter:
    return go.Scatter(
        x=[price],
        y=[row],
        mode="markers+text",
        name=name,
        text=[f"{price:,.1f}"],
        textposition="top center",
        textfont={"color": colors.secondary},
        marker={"symbol": symbol, "size": MARKER_SIZE + 4, "color": color},
        hovertemplate=f"{name} %{{x:,.1f}}<extra></extra>",
    )


# the market's best prices above, and the strategy's own quotes below, on one price axis
def ladder_figure(
    best_bid: float,
    best_ask: float,
    mid: float,
    bid_quote: float | None,
    ask_quote: float | None,
    colors: ChartColors,
) -> go.Figure:
    figure = go.Figure()
    figure.add_trace(
        _ladder_marker(best_bid, MARKET_ROW, "Best bid", "square", colors.muted, colors)
    )
    figure.add_trace(
        _ladder_marker(best_ask, MARKET_ROW, "Best ask", "square", colors.muted, colors)
    )
    if bid_quote is not None:
        figure.add_trace(
            _ladder_marker(bid_quote, QUOTE_ROW, "Your bid", "triangle-up", colors.bid, colors)
        )
    if ask_quote is not None:
        figure.add_trace(
            _ladder_marker(ask_quote, QUOTE_ROW, "Your ask", "triangle-down", colors.ask, colors)
        )
    prices = [p for p in (best_bid, best_ask, bid_quote, ask_quote) if p is not None]
    pad = (max(prices) - min(prices)) * LADDER_PAD_SHARE or 1.0
    figure.add_vline(x=mid, line={"color": colors.axis, "width": 1, "dash": "dot"})
    figure.add_annotation(
        x=mid,
        y=(MARKET_ROW + QUOTE_ROW) / 2,
        text="mid",
        showarrow=False,
        xanchor="left",
        xshift=4,
        font={"color": colors.secondary},
    )
    figure.update_layout(
        height=LADDER_HEIGHT,
        margin={"l": 90, "r": 24, "t": 24, "b": 36},
        paper_bgcolor=TRANSPARENT,
        plot_bgcolor=colors.surface,
        font={"family": FONT_FAMILY, "color": colors.secondary, "size": 13},
        showlegend=False,
        hovermode="closest",
    )
    figure.update_xaxes(
        range=[min(prices) - pad, max(prices) + pad],
        tickformat=",.1f",
        gridcolor=colors.grid,
        linecolor=colors.axis,
    )
    figure.update_yaxes(
        range=[-0.7, 1.7],
        tickvals=[QUOTE_ROW, MARKET_ROW],
        ticktext=["Your quotes", "Market"],
        showgrid=False,
        zeroline=False,
        linecolor=colors.axis,
    )
    return figure
