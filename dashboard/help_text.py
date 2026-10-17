HELP = {
    "net_pnl": "Profit or loss over the run, in USDT, after fees.",
    "gross_pnl": "Net PnL with the fees added back: what the quotes earned before fees.",
    "fees_paid": "Fees the exchange charged on your fills, in USDT. Negative means a rebate.",
    "sharpe": (
        "Average hourly profit divided by how much it swings, scaled to a year. "
        "Needs at least 2 hours of data. With one day, read the sign, not the number."
    ),
    "max_drawdown": "Biggest fall from a previous equity peak, in USDT.",
    "fills": "How many of your quotes were traded.",
    "fills_per_hour": "Fills divided by the hours replayed.",
    "return_over_trade_bps": (
        "Net PnL divided by the value traded, in basis points (1 bp = 0.01%). "
        "Negative means every dollar traded loses money."
    ),
    "spread_captured_bps": (
        "How far fills were from the mid just before them, in bps. Positive means you bought "
        "below or sold above the mid. Fees are not included."
    ),
    "markout_1s": (
        "What a fill was worth 1 second later, in bps. A buy gains if the mid rose after it, "
        "a sell if the mid fell. Negative means the market moved against you after you traded."
    ),
    "markout_10s": "The same as the 1 second markout, measured 10 seconds after each fill.",
    "inventory_half_life": (
        "The typical time for your position to fall to half its size after a fill made it "
        "bigger. n/a when it usually takes longer than an hour."
    ),
    "mean_abs_position": "Average inventory size, ignoring direction, in coin units.",
    "time_at_limit": "Share of time inventory sat at its limit, so one side stopped quoting.",
    "time_quoted": "Share of time both a buy and a sell quote were live.",
    "runtime": "How long the backtest took to run.",
    "started": "When the run began, in UTC.",
    "name": "The run name, set on the Run Backtest page.",
    "data": "Which recorded day was replayed, and how much of it.",
    "strategy": "The quoting rule used. The Strategies page explains each one.",
    "params": "The strategy's own settings for this run.",
    "status": (
        "ok: finished. failed: the runner hit an error. incomplete: no result file yet, "
        "so it is still running or was stopped. unreadable: the folder could not be read."
    ),
    "run_page": "Replays recorded market data through a strategy and saves the result as a run.",
    "data_section": "Which recorded market data to replay.",
    "data_day": "A recorded day from your data folder. A day that failed validation cannot be run.",
    "files": (
        "How many of the day's files to replay, starting at midnight UTC. "
        "Files are usually one hour each. Fewer files make a quicker test."
    ),
    "strategy_section": "The quoting rule and how it is sized.",
    "strategy_choice": "The quoting rule to test. Only the naive quoter is built so far.",
    "half_spread": (
        "How far each quote sits from the mid price, in ticks (1 tick = 0.1 USDT on BTCUSDT). "
        "Wider quotes fill less often but earn more per fill. They never sit inside the best "
        "bid and ask."
    ),
    "step": "How often the strategy refreshes its quotes. 100 ms means 10 times a second.",
    "order_qty": "Size of each quote, in coin units (BTC for BTCUSDT).",
    "max_position": (
        "Largest inventory you may hold, in coin units. At the limit, the side that would "
        "add to it stops quoting."
    ),
    "maker_fee": (
        "Fee when a resting quote is hit, in basis points (2 = 0.02%). Negative means the "
        "exchange pays you."
    ),
    "taker_fee": "Fee when an order takes liquidity. Quotes are post-only, so it never applies.",
    "entry_latency": "Delay before your order reaches the exchange, in ms. Slower = stale quotes.",
    "resp_latency": "Delay before the exchange's reply reaches you, in ms.",
    "queue_model": (
        "How the simulator guesses your place in line at a price. risk_adverse: you only move "
        "up when trades eat the queue ahead (pessimistic). power_prob: a probabilistic guess."
    ),
    "queue_power": "Tuning of the power_prob guess; 2 is the default. risk_adverse ignores it.",
    "run_name": "Names the run folder so you can find it later. Leave empty for the suggested one.",
    "run_button": (
        "Starts the backtest in the background. A full day takes about half a minute. "
        "The log shows the start and the finish only."
    ),
    "explorer_page": "Look inside one finished run: results, charts and distributions.",
    "explorer_run": "Pick a run. The newest is first.",
    "results": "Numbers for the whole run. The time window below only changes the charts.",
    "window": "Zoom the charts to a time range (UTC). A narrow window can show every step.",
    "resolution": "Time between plotted points. Auto picks the finest that keeps the charts fast.",
    "overview": (
        "Top: market mid price (grey), your bid and ask quotes, and your fills as triangles. "
        "Middle: your position; dashed lines are the limits. Bottom: profit after fees (black) "
        "and before fees (grey); the gap is the fee bill. Zooming is linked across panels."
    ),
    "distributions": (
        "Inventory: share of time at each position. Quoted spread: gap between your bid and "
        "ask, in ticks. Fill size: how big each fill row was."
    ),
    "markouts": (
        "Average value of a fill some time after it happened, in bps of the fill price. "
        "The dashed line subtracts the maker fee: below zero there means each fill loses "
        "money. The shaded band is the 95% range of the average, so a wide band means few "
        "fills."
    ),
    "no_markouts": "This run was made before markouts were recorded. Run it again to get them.",
    "compare_page": "Put several finished runs side by side: curves, numbers and settings.",
    "compare_runs": "Pick 2 to 8 runs. A run keeps its colour while it stays selected.",
    "compare_equity": (
        "Profit after fees over time, each run from its own start. Different days line up "
        "by hours since the run began."
    ),
    "compare_markouts": (
        "Average markout against the time after the fill. Lower curves mean worse fills. "
        "Hover to see the exact value and the number of fills."
    ),
    "compare_metrics": "Every headline number of the selected runs. n/a means not available.",
    "compare_settings": "Only the settings that differ between the selected runs.",
    "data_explorer_page": "Look at the recorded market data itself, before any strategy.",
    "explorer_day": "A recorded day from your data folder.",
    "day_summary": "Counts from the checks run when the day was registered.",
    "events": "Market events in the day: book changes and trades.",
    "trades": "Trades in the day.",
    "max_gap": "Longest stretch with no market event at all.",
    "spread_p50": "Median gap between best ask and best bid, in ticks.",
    "spread_p99": "Gap that was exceeded only 1% of the time, in ticks.",
    "trades_per_min": "Average trades per minute over the day.",
    "latency_section": (
        "Feed latency: how long after the exchange stamped an event your recorder saw it. "
        "It is the delay of the data, not of your orders."
    ),
    "latency_measure": (
        "Reads every file of the day once to measure feed latency. It takes about half a minute."
    ),
    "latency_p50": "Half of all events arrived faster than this.",
    "latency_p99": "99% of events arrived faster than this.",
    "latency_p999": "99.9% of events arrived faster than this.",
    "latency_max": "The slowest event of the day.",
    "latency_histogram": (
        "How many events arrived after each delay, as a share of all events. Both axes are "
        "logarithmic, so the rare slow events stay visible."
    ),
    "latency_by_file": (
        "Median, 99th percentile and worst feed latency of each file, in order. Busy hours "
        "are slower."
    ),
    "calculator": "Runs the strategy's own quoting code, so these are the quotes it would place.",
    "best_bid": "The highest price a buyer offers right now.",
    "best_ask": "The lowest price a seller asks right now.",
    "calc_position": "What you hold right now, in coin units. Positive is long, negative is short.",
    "calc_mid": "Halfway between the best bid and the best ask.",
    "calc_bid": "Where the buy quote goes. 'paused' means the position limit stops it.",
    "calc_ask": "Where the sell quote goes. 'paused' means the position limit stops it.",
    "how_it_works": "The four rules the naive quoter follows, every step.",
    "settings": "The numbers you can change on the Run Backtest page, with their defaults.",
}

GLOSSARY = [
    ("Tick", "The smallest price step. 0.1 USDT on BTCUSDT."),
    ("Mid price", "Halfway between the best bid and the best ask."),
    ("Spread", "The gap between the best ask and the best bid."),
    ("Quote", "A resting buy (bid) or sell (ask) order that you keep in the book."),
    ("Fill", "A quote that traded."),
    ("Maker / taker", "A maker rests in the book. A taker trades against it. Makers pay less."),
    (
        "Post-only",
        "An order that is rejected rather than trade at once, so it can never be a taker.",
    ),
    ("Basis point (bp)", "0.01%. A 2 bp fee costs 2 USDT per 10,000 USDT traded."),
    ("Position", "What you hold now. Positive is long, negative is short."),
    ("Adverse selection", "Being filled just before the price moves against you."),
    (
        "Queue position",
        "Your place in line at a price. You fill only after those ahead have traded.",
    ),
    ("Latency", "The delay between sending an order and the exchange acting on it."),
    ("Step", "One tick of the simulation clock, when the strategy looks at the book."),
    (
        "Markout",
        "What a fill was worth some time later. Negative means the market moved against you.",
    ),
    ("Inventory half-life", "How long inventory takes to fall to half after it grew."),
    (
        "Feed latency",
        "The delay between the exchange stamping an event and your recorder seeing it.",
    ),
]
