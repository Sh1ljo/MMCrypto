import streamlit as st
from streamlit.delta_generator import DeltaGenerator

from dashboard.charts import colors_for, ladder_figure
from dashboard.help_text import GLOSSARY, HELP
from dashboard.lib import QuotePreview, preview_quotes
from mmlab.config import RunConfig
from mmlab.strategies.naive import NaiveParams

EXAMPLE_TICK_SIZE = 0.1
EXAMPLE_BEST_BID = 84_000.0
EXAMPLE_BEST_ASK = 84_000.1
DEFAULT_RUN = RunConfig(name="default", strategy="naive", data_files=[], tick_size=1, lot_size=1)


def _card(title: str, formulas: list[str], text: str) -> None:
    with st.container(border=True):
        st.markdown(f"**{title}**")
        for formula in formulas:
            st.latex(formula)
        st.caption(text)


def _built_badge(phase: str) -> None:
    st.badge(f"Built, {phase}", icon=":material/check_circle:", color="green")


def _planned_badge(phase: str) -> None:
    st.badge(
        f"Planned, {phase}: not built yet",
        icon=":material/schedule:",
        color="orange",
        help="Shown so you can see where the lab is going. It cannot be run yet.",
    )


def _naive_rules() -> None:
    st.subheader("How it works", help=HELP["how_it_works"])
    left, right = st.columns(2)
    with left:
        _card(
            "1. Find the middle",
            [r"s = \dfrac{b + a}{2}"],
            "b is the best bid and a the best ask, both in ticks. s is the mid price.",
        )
        _card(
            "3. Respect the limit",
            [
                r"\text{buy only if } q + Q \le q_{\max}",
                r"\text{sell only if } -q + Q \le q_{\max}",
            ],
            "q is your position, Q the order size. At the limit, the side that would add to "
            "it goes quiet. There is no other inventory control.",
        )
    with right:
        _card(
            "2. Place the quotes",
            [
                r"\text{bid} = \min(\lfloor s - h \rfloor,\ b)",
                r"\text{ask} = \max(\lceil s + h \rceil,\ a)",
            ],
            "h is the half spread. The min and max keep a quote from sitting inside the best "
            "bid and ask, so it waits in line instead of trading at once.",
        )
        _card(
            "4. Refresh",
            [r"\text{every } \Delta t = 100\ \text{ms}"],
            "Cancel quotes that are no longer at the target price and place the missing ones. "
            "Quotes are post-only, so they only ever wait to be hit.",
        )


def _calculator() -> None:
    st.subheader("Try it", help=HELP["calculator"])
    market, strategy = st.columns(2, gap="large")
    with market:
        best_bid = st.number_input(
            "Best bid",
            key="calc_best_bid",
            value=EXAMPLE_BEST_BID,
            step=EXAMPLE_TICK_SIZE,
            format="%.1f",
            help=HELP["best_bid"],
        )
        best_ask = st.number_input(
            "Best ask",
            key="calc_best_ask",
            value=EXAMPLE_BEST_ASK,
            step=EXAMPLE_TICK_SIZE,
            format="%.1f",
            help=HELP["best_ask"],
        )
        position = st.number_input(
            "Your position",
            key="calc_position",
            value=0.0,
            step=DEFAULT_RUN.order_qty,
            format="%g",
            help=HELP["calc_position"],
        )
    with strategy:
        half_spread = st.number_input(
            "Half spread (ticks)",
            key="calc_half_spread",
            min_value=0.0,
            value=NaiveParams().half_spread_ticks,
            step=0.5,
            help=HELP["half_spread"],
        )
        order_qty = st.number_input(
            "Order size",
            key="calc_order_qty",
            min_value=0.0,
            value=DEFAULT_RUN.order_qty,
            step=0.001,
            format="%g",
            help=HELP["order_qty"],
        )
        max_position = st.number_input(
            "Max position",
            key="calc_max_position",
            min_value=0.0,
            value=DEFAULT_RUN.max_position,
            step=0.001,
            format="%g",
            help=HELP["max_position"],
        )
    try:
        preview = preview_quotes(
            best_bid, best_ask, half_spread, position, order_qty, max_position, EXAMPLE_TICK_SIZE
        )
    except ValueError as error:
        st.error(str(error))
        return
    _show_preview(best_bid, best_ask, preview)


def _quote_metric(
    column: DeltaGenerator, label: str, price: float | None, mid: float, help_text: str
) -> None:
    if price is None:
        column.metric(label, "paused", help=help_text)
        return
    ticks = (price - mid) / EXAMPLE_TICK_SIZE
    column.metric(
        label, f"{price:,.1f}", f"{ticks:+.1f} ticks from mid", delta_color="off", help=help_text
    )


def _show_preview(best_bid: float, best_ask: float, preview: QuotePreview) -> None:
    mid_column, bid_column, ask_column = st.columns(3)
    mid_column.metric("Mid", f"{preview.mid:,.2f}", help=HELP["calc_mid"])
    _quote_metric(bid_column, "Your bid", preview.bid_quote, preview.mid, HELP["calc_bid"])
    _quote_metric(ask_column, "Your ask", preview.ask_quote, preview.mid, HELP["calc_ask"])
    figure = ladder_figure(
        best_bid,
        best_ask,
        preview.mid,
        preview.bid_quote,
        preview.ask_quote,
        colors_for(st.context.theme.type),
    )
    st.plotly_chart(figure, theme=None, config={"displaylogo": False})


def _settings_table() -> None:
    st.subheader("Settings", help=HELP["settings"])
    st.markdown(
        "| Setting | Default | What it does |\n|---|---|---|\n"
        f"| Half spread `h` | {NaiveParams().half_spread_ticks:g} ticks | Distance from mid |\n"
        f"| Order size `Q` | {DEFAULT_RUN.order_qty:g} | Size of each quote |\n"
        f"| Max position `q_max` | {DEFAULT_RUN.max_position:g} | Inventory cap, both ways |\n"
        f"| Refresh every | {DEFAULT_RUN.step_ns // 1_000_000} ms | How often quotes are updated |"
    )


def _naive_tab() -> None:
    _built_badge("Phase 2")
    st.markdown(
        "**In one sentence:** keep one buy and one sell order the same distance from the "
        "middle of the market, and move them as the market moves. It never trades against "
        "the book. It only waits to be hit."
    )
    _naive_rules()
    _calculator()
    _settings_table()
    st.info(
        "**Result so far:** on all four recorded days this quoter loses about 3 bps for every "
        "dollar traded at 5 ticks. 2 bps is fees and about 1 bp is the price moving against "
        "its fills (adverse selection). It is the baseline later strategies have to beat."
    )


def _symbols_table(rows: list[tuple[str, str]]) -> None:
    lines = ["| Symbol | Meaning |", "|---|---|"] + [
        f"| {symbol} | {text} |" for symbol, text in rows
    ]
    st.markdown("\n".join(lines))


def _avellaneda_tab() -> None:
    _planned_badge("Phase 5")
    st.markdown(
        "**Idea:** quote around a *reservation price* that leans against your inventory. "
        "Hold too much and it drops below the mid, so you quote lower and sell more easily."
    )
    st.latex(r"r = s - q\,\gamma\,\sigma^2\,(T - t)")
    st.latex(
        r"\delta_a + \delta_b = \gamma\,\sigma^2\,(T - t) + "
        r"\frac{2}{\gamma}\ln\!\left(1 + \frac{\gamma}{k}\right)"
    )
    st.latex(
        r"\text{bid} = r - \tfrac12(\delta_a + \delta_b), \qquad "
        r"\text{ask} = r + \tfrac12(\delta_a + \delta_b)"
    )
    _symbols_table(
        [
            ("s", "mid price"),
            ("q", "inventory, in order-size units"),
            ("γ", "risk aversion: higher leans harder against inventory"),
            ("σ", "volatility, from past data only"),
            ("T − t", "time left in the horizon"),
            ("k", "how fast fills drop off with distance, from the arrival model λ(δ) = A·e^(−kδ)"),
        ]
    )


def _glft_tab() -> None:
    _planned_badge("Phase 5")
    st.markdown(
        "**Idea:** the same inventory lean as Avellaneda–Stoikov, but with no end time, which "
        "suits perpetuals because they never expire. Everything is worked in ticks."
    )
    st.latex(r"c_1 = \frac{1}{\xi\Delta}\ln\!\left(1 + \frac{\xi\Delta}{k}\right)")
    st.latex(
        r"c_2 = \sqrt{\frac{\gamma}{2A\Delta k}"
        r"\left(1 + \frac{\xi\Delta}{k}\right)^{\frac{k}{\xi\Delta} + 1}}"
    )
    st.latex(
        r"\text{half spread} = c_1 + \tfrac{\Delta}{2}\,\sigma c_2, \qquad \text{skew} = \sigma c_2"
    )
    st.latex(
        r"\text{bid} = \text{fair} - (\text{half spread} + \text{skew}\cdot q), \quad "
        r"\text{ask} = \text{fair} + (\text{half spread} - \text{skew}\cdot q)"
    )
    st.caption("Here ξ = γ and Δ = 1 (one order-size unit). A and k come from the arrival model.")


def _alpha_tab() -> None:
    _planned_badge("Phase 6")
    st.markdown(
        "**Idea:** shift the fair price with a short-term signal, so you lean away from "
        "trading that is about to hurt you, then quote around it like GLFT."
    )
    st.latex(r"\text{fair} = s + \beta\cdot\text{signal}\cdot\text{tick}")
    st.latex(
        r"I = \frac{\sum_{i=1}^{n} Q^{\text{bid}}_i - \sum_{i=1}^{n} Q^{\text{ask}}_i}"
        r"{\sum_{i=1}^{n} Q^{\text{bid}}_i + \sum_{i=1}^{n} Q^{\text{ask}}_i}"
    )
    _symbols_table(
        [
            ("I", "book imbalance over the top n levels, between −1 and 1"),
            ("OFI", "signed changes at the best bid and ask over a window"),
            ("Trade flow", "signed trade volume over the last few seconds"),
            ("β", "fitted on one day, tested on a different day"),
        ]
    )
    st.caption("If the signal does not predict out of sample, that gets written down as a result.")


def _metrics_tab() -> None:
    left, right = st.columns(2)
    with left:
        _card(
            "Equity",
            [r"E_t = B_t + q_t\,s_t - F_t"],
            "Cash, plus position at the mid price, minus fees paid so far.",
        )
        _card(
            "Net and gross PnL",
            [
                r"\text{net} = E_{\text{end}} - E_{\text{start}}",
                r"\text{gross} = \text{net} + F_{\text{end}}",
            ],
            "Gross is what the quotes earned before paying the exchange.",
        )
        _card(
            "Fees",
            [r"F = f \times \sum \text{price}\times\text{qty}"],
            "Fee rate f times the value traded. Negative f is a rebate.",
        )
        _card(
            "Return over trade",
            [r"10^4 \times \dfrac{\text{net}}{\sum \text{price}\times\text{qty}}"],
            "Basis points of profit per dollar traded.",
        )
    with right:
        _card(
            "Spread captured",
            [
                r"10^4 \times \dfrac{\sum \text{qty}\cdot\text{side}\cdot"
                r"(s_{\text{before}} - \text{price})/s_{\text{before}}}{\sum \text{qty}}"
            ],
            "Side is +1 for a buy and −1 for a sell. Positive beats the mid.",
        )
        _card(
            "Max drawdown",
            [r"\max_t\Big(\max_{u \le t} E_u - E_t\Big)"],
            "The biggest fall from a previous equity peak.",
        )
        _card(
            "Sharpe",
            [
                r"\sqrt{8760}\times"
                r"\dfrac{\text{mean}(\Delta E_{\text{hour}})}{\text{std}(\Delta E_{\text{hour}})}"
            ],
            "Hourly profit, scaled to a year (8,760 hours). Needs at least 2 hours of data.",
        )
        _card(
            "Markout (Phase 4, planned)",
            [r"\text{buy: } s_{t+\tau} - \text{price}", r"\text{sell: } \text{price} - s_{t+\tau}"],
            "What a fill is worth τ seconds later. Negative means you were picked off.",
        )


def _glossary_tab() -> None:
    lines = ["| Term | Meaning |", "|---|---|"] + [
        f"| **{term}** | {text} |" for term, text in GLOSSARY
    ]
    st.markdown("\n".join(lines))


st.title("Strategies", help="What each strategy does, in plain words and formulas.")
tabs = st.tabs(
    [
        "Naive (built)",
        "Avellaneda–Stoikov (Phase 5)",
        "GLFT (Phase 5)",
        "Alpha skew (Phase 6)",
        "How results are measured",
        "Glossary",
    ]
)
for tab, render in zip(
    tabs,
    [_naive_tab, _avellaneda_tab, _glft_tab, _alpha_tab, _metrics_tab, _glossary_tab],
    strict=True,
):
    with tab:
        render()
