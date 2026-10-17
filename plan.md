\# MM-Lab: A Crypto Market-Making Research Lab



> A phased build guide for a limit-order-book market-making simulator on crypto perpetuals, with a graphical dashboard for running and analysing backtests.

> Stack: Python · hftbacktest · Numba · Polars · DuckDB · Streamlit · Plotly



\---



\## 0. Read this first: what this project is (and isn't)



\*\*What it is:\*\* a research lab for learning market microstructure, stochastic optimal control and event-driven simulation. You'll build it phase by phase, mostly AI-assisted, and every result will be visible in a dashboard.



\*\*What it isn't:\*\* a money printer. At retail fee tiers (roughly 0.02% maker on Binance USDⓈ-M VIP0; check the current schedule), passive market making on liquid perps usually loses money once you account for adverse selection. You'll likely \*prove\* that in Phase 4, which is a valuable result in itself. Edge, if it exists anywhere for you, will come from Phase 6 (alpha skew) and from less competitive symbols.



\*\*Ground rules\*\*

1\. Every number in the dashboard must be reproducible from a saved config.

2\. A backtest is not trusted until it passes the sanity tests (Section 9).

3\. A Sharpe above about 3, near-zero drawdown or a too-smooth equity curve means \*\*look for a bug first\*\*.

4\. Move to the next phase only when the current phase's exit criteria are met.



\---



\## 1. Architecture overview



```mermaid

flowchart LR

&#x20;   A\[Tardis.dev / Binance raw data<br/>CSV.gz] --> B\[Converter<br/>mmlab.data]

&#x20;   B --> C\[(data/npz<br/>hftbacktest format)]

&#x20;   C --> D\[Backtest runner<br/>mmlab.run]

&#x20;   E\[configs/\*.json] --> D

&#x20;   D --> F\[(runs/\&lt;run\_id\&gt;/<br/>config · metrics · timeseries · fills)]

&#x20;   F --> G\[Streamlit dashboard]

&#x20;   G -- launches runs via subprocess --> D

&#x20;   C --> G

```



The core design decision is that \*\*the dashboard never runs backtest logic itself.\*\* It writes a config, launches the runner as a subprocess, and reads the saved artifacts. That keeps Numba compilation, crashes and long runs out of the UI process, and it means every run is a reproducible folder on disk.



\---



\## 2. Project structure



```

mm-lab/

├── pyproject.toml

├── README.md

├── CONTEXT.md                 # running notes for AI sessions (see Section 10)

├── configs/

│   └── naive\_btcusdt.json

├── data/

│   ├── raw/                   # downloaded CSV.gz (gitignored)

│   └── npz/                   # converted hftbacktest files (gitignored)

├── runs/                      # one folder per backtest run (gitignored)

├── mmlab/

│   ├── \_\_init\_\_.py

│   ├── config.py              # pydantic config models

│   ├── data/

│   │   ├── download.py        # Tardis download

│   │   ├── convert.py         # CSV -> npz (+ end-of-day snapshots)

│   │   └── validate.py        # data integrity checks

│   ├── strategies/

│   │   ├── naive.py           # Phase 2

│   │   ├── avellaneda.py      # Phase 5

│   │   ├── glft.py            # Phase 5

│   │   └── alpha\_skew.py      # Phase 6

│   ├── calibration/

│   │   ├── volatility.py

│   │   └── intensity.py       # fit lambda(delta) = A \* exp(-k \* delta)

│   ├── analytics/

│   │   ├── metrics.py

│   │   └── markouts.py

│   ├── run.py                 # CLI: python -m mmlab.run --config ...

│   └── sweep.py               # parameter grids and walk-forward

├── dashboard/

│   ├── app.py                 # home: run list

│   ├── lib.py                 # shared loaders and plot helpers

│   └── pages/

│       ├── 1\_Run\_Backtest.py

│       ├── 2\_Run\_Explorer.py

│       ├── 3\_Compare\_Runs.py

│       ├── 4\_Sweeps.py

│       └── 5\_Data\_Explorer.py

└── tests/

&#x20;   ├── test\_sanity.py

&#x20;   ├── test\_metrics.py

&#x20;   └── test\_data.py

```



\---



\## 3. Environment setup



Use \*\*Python 3.12\*\* and \[`uv`](https://docs.astral.sh/uv/) for environment management.



```bash

uv init mm-lab \&\& cd mm-lab

uv add hftbacktest numba numpy polars pyarrow duckdb \\

&#x20;      streamlit plotly pydantic scipy statsmodels tardis-dev

uv add --dev pytest ruff ipykernel

```



\*\*Windows note:\*\* hftbacktest ships compiled wheels. If installation or Numba compilation misbehaves on native Windows, run the project inside \*\*WSL2 (Ubuntu)\*\* and open the folder from VS Code. The dashboard will still open in your Windows browser at `localhost:8501`.



Verify the install:

```bash

uv run python -c "import hftbacktest, numba, polars, streamlit; print('ok')"

```



\*\*API caveat:\*\* the snippets below follow the hftbacktest \*\*v2.x\*\* Python API (`BacktestAsset`, `HashMapMarketDepthBacktest`). The library evolves, so if a method name fails, check the \[official docs](https://hftbacktest.readthedocs.io/) and tutorials before letting an AI "fix" it by guessing.



\---



\## 4. Reading list (Phase 0)



Read these in order. You don't need to master the proofs; you need the intuition and the formulas.



| # | Resource | Why |

|---|----------|-----|

| 1 | hftbacktest docs: \*Getting Started\*, \*Data Preparation\*, \*Probability Queue Models\*, \*GLFT Market Making\* tutorials | The tool you'll actually use |

| 2 | Avellaneda \& Stoikov (2008), \*High-frequency trading in a limit order book\* | The foundational model: reservation price plus optimal spread |

| 3 | Guéant, Lehalle \& Fernandez-Tapia (2013), \*Dealing with the inventory risk\* | Inventory-bounded solution (GLFT) |

| 4 | Guéant (2017), \*Optimal market making\* | Closed-form approximations you'll implement |

| 5 | Cartea, Jaimungal \& Penalva (2015), \*Algorithmic and High-Frequency Trading\*, chapters on market making | The textbook; reference as needed |

| 6 | Cont, Kukanov \& Stoikov (2014), \*The price impact of order book events\* | Order-flow imbalance (OFI) for Phase 6 |

| 7 | Bouchaud et al. (2018), \*Trades, Quotes and Prices\* | Microstructure intuition, adverse selection |



\---



\## 5. Key concepts and formulas (keep this as a reference)



\*\*Notation:\*\* `s` = mid price, `q` = inventory (in units of order size), `σ` = volatility, `γ` = risk aversion, `k` = order-arrival decay, `A` = arrival intensity scale, `δ` = quote distance from mid.



\### 5.1 Order arrival model

The probability of your quote being hit decays with distance from mid:



```

λ(δ) = A · exp(−k · δ)

```



You estimate `A` and `k` from trade data (Phase 5).



\### 5.2 Avellaneda–Stoikov (finite horizon T)

```

reservation price:  r = s − q · γ · σ² · (T − t)

total spread:       δ\_a + δ\_b = γ · σ² · (T − t) + (2/γ) · ln(1 + γ/k)

quotes:             bid = r − spread/2,   ask = r + spread/2

```

When you're long (`q > 0`), `r` drops below mid, so you quote lower and sell more readily. That's inventory skew.



\### 5.3 GLFT closed-form approximation (infinite horizon; preferred for perps)

With `ξ = γ` and `Δ = 1` (one order-size unit):

```

c1 = (1 / (ξΔ)) · ln(1 + ξΔ / k)

c2 = sqrt( γ / (2·A·Δ·k) · (1 + ξΔ/k)^(k/(ξΔ) + 1) )



half\_spread = c1 + (Δ/2) · σ · c2

skew        = σ · c2



bid\_depth = half\_spread + skew · q

ask\_depth = half\_spread − skew · q

bid = fair\_price − bid\_depth,   ask = fair\_price + ask\_depth

```

Work in \*\*ticks\*\* throughout (σ in ticks per √time-unit, depths in ticks). Unit mismatches are the most common bug here.



\### 5.4 Adverse selection and markouts

A \*\*markout\*\* is how much a fill is worth `τ` seconds later:

```

buy fill:  markout(τ) = mid(t\_fill + τ) − fill\_price

sell fill: markout(τ) = fill\_price − mid(t\_fill + τ)

```

Plot the average markout against τ (100 ms → 60 s). If it goes negative after a few seconds, you're being picked off by informed flow, and that is usually what kills naive market makers.



\### 5.5 Queue position

Your limit order sits \*behind\* existing volume at that price. You only get filled after the queue ahead of you is consumed. hftbacktest models this probabilistically (`power\_prob\_queue\_model`, `risk\_adverse\_queue\_model`). Ignoring queue position is the single biggest source of fake market-making profits.



\---



\## 6. The phases



Each phase has a \*\*goal\*\*, \*\*tasks\*\*, \*\*deliverables\*\* and \*\*exit criteria\*\*. Time estimates assume hobby pace (evenings and weekends).



\---



\### Phase 0 — Theory and setup \*(about 1 week)\*



\*\*Goal:\*\* understand what you're about to build before any AI writes code.



\*\*Tasks\*\*

\- \[ ] Set up the environment (Section 3) and git repo; add `data/`, `runs/` and `.venv/` to `.gitignore`.

\- \[ ] Run the hftbacktest \*Getting Started\* tutorial end-to-end with its sample data.

\- \[ ] Read resources 1–3 from Section 4.

\- \[ ] In `CONTEXT.md`, explain in your own words: reservation price, inventory skew, adverse selection, queue position.



\*\*Exit criteria:\*\* you can explain why a market maker who quotes symmetrically around mid with no inventory control eventually blows up, and why being filled is often \*bad news\*.



\---



\### Phase 1 — Data pipeline \*(about 1 week)\*



\*\*Goal:\*\* reliable, validated L2 order-book plus trade data in hftbacktest format.



\*\*Data source:\*\* \[Tardis.dev](https://tardis.dev) offers historical tick-level crypto data. The first day of each month is (as far as I know) downloadable for free without an API key, which is enough to learn on. Use `binance-futures` with the data types `incremental\_book\_L2` and `trades`.



\*\*Symbols:\*\* start with \*\*BTCUSDT\*\* (deep and liquid, so data is clean), then add one \*\*mid-cap perp\*\* later. Wider spreads make market making look easier there, but adverse selection is usually worse, which makes for a good comparison.



\*\*Tasks\*\*

\- \[ ] `mmlab/data/download.py`: download 2–3 free days.

&#x20; ```python

&#x20; from tardis\_dev import datasets



&#x20; datasets.download(

&#x20;     exchange="binance-futures",

&#x20;     data\_types=\["incremental\_book\_L2", "trades"],

&#x20;     from\_date="2026-09-01",

&#x20;     to\_date="2026-09-02",          # exclusive

&#x20;     symbols=\["BTCUSDT"],

&#x20;     download\_dir="data/raw",

&#x20; )

&#x20; ```

\- \[ ] `mmlab/data/convert.py`: convert to `.npz` using hftbacktest's Tardis utility, and build an end-of-day snapshot for chaining days.

&#x20; ```python

&#x20; from hftbacktest.data.utils import tardis

&#x20; from hftbacktest.data.utils.snapshot import create\_last\_snapshot



&#x20; tardis.convert(

&#x20;     \[

&#x20;         "data/raw/binance-futures\_trades\_2026-09-01\_BTCUSDT.csv.gz",

&#x20;         "data/raw/binance-futures\_incremental\_book\_L2\_2026-09-01\_BTCUSDT.csv.gz",

&#x20;     ],

&#x20;     output\_filename="data/npz/btcusdt\_20260901.npz",

&#x20;     buffer\_size=200\_000\_000,

&#x20; )



&#x20; create\_last\_snapshot(

&#x20;     \["data/npz/btcusdt\_20260901.npz"],

&#x20;     tick\_size=0.1,

&#x20;     lot\_size=0.001,

&#x20;     output\_snapshot\_filename="data/npz/btcusdt\_20260901\_eod.npz",

&#x20; )

&#x20; ```

&#x20; Check the current tick and lot size for each symbol in the exchange info; don't hardcode blindly.

\- \[ ] `mmlab/data/validate.py`: report per file:

&#x20; - event count, time span, largest gap between events

&#x20; - number of crossed-book moments (best bid ≥ best ask) after replay

&#x20; - spread distribution (in ticks)

&#x20; - trades per minute

\- \[ ] Write a `data/manifest.json` listing every converted file with symbol, date, tick size, lot size and validation summary. The dashboard reads this.



\*\*Deliverables:\*\* converted `.npz` files, snapshots, manifest, validation report.



\*\*Exit criteria:\*\* validation passes on all files (no large unexplained gaps, crossed-book moments are negligible), and you can replay a day and print best bid/ask every minute.



\---



\### Phase 2 — First backtest and run artifacts \*(about 1 week)\*



\*\*Goal:\*\* a naive symmetric market maker, a CLI runner and a fixed artifact format that the dashboard will consume.



\*\*2.1 Config model\*\* (`mmlab/config.py`)

```python

from pydantic import BaseModel



class ExecConfig(BaseModel):

&#x20;   maker\_fee: float = 0.0002          # positive = you pay; negative = rebate

&#x20;   taker\_fee: float = 0.0005

&#x20;   entry\_latency\_ns: int = 10\_000\_000 # 10 ms

&#x20;   resp\_latency\_ns: int = 10\_000\_000

&#x20;   queue\_model: str = "power\_prob"    # "power\_prob" | "risk\_adverse"

&#x20;   queue\_power: float = 2.0

&#x20;   partial\_fill: bool = False



class RunConfig(BaseModel):

&#x20;   name: str

&#x20;   strategy: str                      # "naive" | "avellaneda" | "glft" | "alpha\_skew"

&#x20;   data\_files: list\[str]

&#x20;   initial\_snapshot: str | None = None

&#x20;   tick\_size: float

&#x20;   lot\_size: float

&#x20;   step\_ns: int = 100\_000\_000         # 100 ms decision interval

&#x20;   order\_qty: float = 0.001

&#x20;   max\_position: float = 0.01

&#x20;   params: dict = {}                  # strategy-specific

&#x20;   exec: ExecConfig = ExecConfig()

```



\*\*2.2 Building the backtest asset\*\*

```python

from hftbacktest import BacktestAsset, HashMapMarketDepthBacktest



def build\_backtest(cfg: RunConfig):

&#x20;   asset = (

&#x20;       BacktestAsset()

&#x20;       .data(cfg.data\_files)

&#x20;       .linear\_asset(1.0)

&#x20;       .constant\_latency(cfg.exec.entry\_latency\_ns, cfg.exec.resp\_latency\_ns)

&#x20;       .trading\_value\_fee\_model(cfg.exec.maker\_fee, cfg.exec.taker\_fee)

&#x20;       .tick\_size(cfg.tick\_size)

&#x20;       .lot\_size(cfg.lot\_size)

&#x20;   )

&#x20;   if cfg.initial\_snapshot:

&#x20;       asset = asset.initial\_snapshot(cfg.initial\_snapshot)

&#x20;   asset = (asset.power\_prob\_queue\_model(cfg.exec.queue\_power)

&#x20;            if cfg.exec.queue\_model == "power\_prob"

&#x20;            else asset.risk\_adverse\_queue\_model())

&#x20;   asset = asset.partial\_fill\_exchange() if cfg.exec.partial\_fill else asset.no\_partial\_fill\_exchange()

&#x20;   return HashMapMarketDepthBacktest(\[asset])

```

A backtest object \*\*cannot be reused\*\*, so build a fresh one per run.



\*\*2.3 Naive strategy\*\* (`mmlab/strategies/naive.py`)

```python

import numpy as np

from numba import njit

from hftbacktest import BUY, SELL, GTX, LIMIT



@njit

def naive\_mm(hbt, recorder, quotes\_out, half\_spread\_ticks, order\_qty, max\_pos, step\_ns):

&#x20;   """Symmetric quotes around mid. quotes\_out: preallocated float64 array (N, 4)."""

&#x20;   a = 0

&#x20;   i = 0

&#x20;   while hbt.elapse(step\_ns) == 0:

&#x20;       hbt.clear\_inactive\_orders(a)

&#x20;       depth = hbt.depth(a)

&#x20;       pos = hbt.position(a)

&#x20;       tick = depth.tick\_size



&#x20;       mid\_tick = (depth.best\_bid\_tick + depth.best\_ask\_tick) / 2.0

&#x20;       bid\_tick = min(np.floor(mid\_tick - half\_spread\_ticks), depth.best\_bid\_tick)

&#x20;       ask\_tick = max(np.ceil(mid\_tick + half\_spread\_ticks), depth.best\_ask\_tick)



&#x20;       # Cancel quotes that are no longer at the target price

&#x20;       orders = hbt.orders(a)

&#x20;       it = orders.values()

&#x20;       while it.has\_next():

&#x20;           o = it.get()

&#x20;           if o.cancellable:

&#x20;               if (o.side == BUY and o.price\_tick != bid\_tick) or \\

&#x20;                  (o.side == SELL and o.price\_tick != ask\_tick):

&#x20;                   hbt.cancel(a, o.order\_id, False)



&#x20;       # Submit new quotes (order\_id = price tick, a common hftbacktest pattern)

&#x20;       if pos < max\_pos:

&#x20;           oid = np.uint64(bid\_tick)

&#x20;           if oid not in orders:

&#x20;               hbt.submit\_buy\_order(a, oid, bid\_tick \* tick, order\_qty, GTX, LIMIT, False)

&#x20;       if pos > -max\_pos:

&#x20;           oid = np.uint64(ask\_tick)

&#x20;           if oid not in orders:

&#x20;               hbt.submit\_sell\_order(a, oid, ask\_tick \* tick, order\_qty, GTX, LIMIT, False)



&#x20;       if i < quotes\_out.shape\[0]:

&#x20;           quotes\_out\[i, 0] = hbt.current\_timestamp

&#x20;           quotes\_out\[i, 1] = mid\_tick \* tick

&#x20;           quotes\_out\[i, 2] = bid\_tick \* tick

&#x20;           quotes\_out\[i, 3] = ask\_tick \* tick

&#x20;           i += 1

&#x20;       recorder.record(hbt)

&#x20;   return i

```

`GTX` = post-only, so you never accidentally pay taker fees as a market maker.



\*\*2.4 Runner\*\* (`mmlab/run.py`). Responsibilities:

1\. Parse `--config path.json` into a `RunConfig`.

2\. Build the backtest; preallocate a `Recorder` (`from hftbacktest.recorder import Recorder`) and a `quotes\_out` array sized `duration / step\_ns + margin`.

3\. Dispatch to the strategy function by name.

4\. Save artifacts (below), compute metrics, print progress lines (the dashboard streams stdout).

5\. Fail loudly on any exception, and write `status: "failed"` into `metrics.json`.



\*\*2.5 Artifact format.\*\* Freeze this early; the dashboard depends on it.

```

runs/2026-10-16\_1430\_naive\_btcusdt\_a1b2c3/

├── config.json        # exact RunConfig used (+ git commit hash, hftbacktest version)

├── metrics.json       # summary metrics + status + runtime

├── timeseries.parquet # ts, mid, bid\_quote, ask\_quote, position, balance, fee, equity, num\_trades

├── fills.parquet      # ts, side, price, qty, mid\_at\_fill

└── log.txt

```

\- \*\*Timeseries:\*\* merge `recorder.get(0)` (inspect `rec.dtype.names`; expect timestamp, price, position, balance, fee, num\_trades, trading volume/value) with `quotes\_out` on timestamp. Equity = `balance + position × price − fee`.

\- \*\*Fills, version 1:\*\* infer from changes in `num\_trades`/`position` between recorder rows (approximate; several fills can merge within one step).

\- \*\*Fills, version 2 (Phase 4):\*\* record exact fills inside the strategy by inspecting orders with status `FILLED` \*before\* `clear\_inactive\_orders`, using their execution price/qty fields. Verify field names in the docs.



\*\*Exit criteria:\*\* `uv run python -m mmlab.run --config configs/naive\_btcusdt.json` produces a complete run folder, and the sanity tests in Section 9 (no-trade, determinism, fee sign) pass.



\---



\### Phase 3 — Dashboard v1 \*(about 1 week)\*



\*\*Goal:\*\* stop living in the terminal. Launch runs and explore results graphically.



\*\*Tech:\*\* Streamlit (multipage) plus Plotly. Launch with:

```bash

uv run streamlit run dashboard/app.py

```



\*\*3.1 Pages\*\*



| Page | What it does |

|------|--------------|

| \*\*Home\*\* (`app.py`) | Table of all runs: name, strategy, symbol, date range, PnL, Sharpe, max drawdown, status. Click to open in Explorer. |

| \*\*1 · Run Backtest\*\* | Form: choose data files from the manifest, strategy, params (sliders/inputs), execution settings. "Run" writes a config and launches the runner; live log output; link to the result. |

| \*\*2 · Run Explorer\*\* | Deep dive into one run (charts below). |

| \*\*3 · Compare Runs\*\* \*(Phase 5+)\* | Overlay equity curves; metrics side by side; config diff. |

| \*\*4 · Sweeps\*\* \*(Phase 7)\* | Parameter heatmaps, train vs test. |

| \*\*5 · Data Explorer\*\* | Order-book heatmap, spread over time, trade intensity, volatility, for a chosen data file and time window. |



\*\*3.2 Run Explorer charts\*\*

1\. \*\*KPI row:\*\* net PnL, gross PnL (before fees), fees paid, Sharpe, max drawdown, number of fills, average markout at 1 s and 10 s.

2\. \*\*Price panel:\*\* mid line, bid/ask quote lines, fills as markers (green for buys, red for sells).

3\. \*\*Position panel:\*\* inventory over time, with ±max\_position bands.

4\. \*\*Equity panel:\*\* net equity vs equity before fees. The gap between them is your fee bill.

5\. \*\*Markout curve:\*\* average markout vs horizon (Phase 4).

6\. \*\*Distributions:\*\* inventory histogram, quoted spread histogram, fill size histogram.



Use one `make\_subplots(rows=3, shared\_xaxes=True)` for panels 2–4 so zooming is synchronized. Use `go.Scattergl` for anything over about 10k points.



\*\*3.3 Launching a run from Streamlit\*\* (`pages/1\_Run\_Backtest.py` sketch)

```python

import json, subprocess, sys, time

from pathlib import Path

import streamlit as st



st.title("Run Backtest")

manifest = json.loads(Path("data/manifest.json").read\_text())

files = st.multiselect("Data files", \[m\["path"] for m in manifest])

strategy = st.selectbox("Strategy", \["naive", "avellaneda", "glft", "alpha\_skew"])

half\_spread = st.slider("Half spread (ticks)", 0.5, 20.0, 2.0, 0.5)

maker\_fee = st.number\_input("Maker fee", value=0.0002, format="%.5f")



if st.button("Run", type="primary", disabled=not files):

&#x20;   cfg = {

&#x20;       "name": f"{strategy}\_{int(time.time())}",

&#x20;       "strategy": strategy,

&#x20;       "data\_files": files,

&#x20;       "tick\_size": 0.1,

&#x20;       "lot\_size": 0.001,

&#x20;       "params": {"half\_spread\_ticks": half\_spread},

&#x20;       "exec": {"maker\_fee": maker\_fee},

&#x20;   }

&#x20;   cfg\_path = Path("configs/\_ui") / f"{cfg\['name']}.json"

&#x20;   cfg\_path.parent.mkdir(parents=True, exist\_ok=True)

&#x20;   cfg\_path.write\_text(json.dumps(cfg, indent=2))



&#x20;   with st.status("Running backtest…", expanded=True) as status:

&#x20;       proc = subprocess.Popen(

&#x20;           \[sys.executable, "-m", "mmlab.run", "--config", str(cfg\_path)],

&#x20;           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,

&#x20;       )

&#x20;       for line in proc.stdout:

&#x20;           st.write(line.rstrip())

&#x20;       ok = proc.wait() == 0

&#x20;       status.update(label="Done" if ok else "Failed", state="complete" if ok else "error")

```



\*\*3.4 Loading and downsampling\*\* (`dashboard/lib.py`)

```python

import polars as pl

import streamlit as st



@st.cache\_data

def load\_timeseries(run\_dir: str, every: str = "1s") -> pl.DataFrame:

&#x20;   df = pl.read\_parquet(f"{run\_dir}/timeseries.parquet")

&#x20;   df = df.with\_columns(pl.from\_epoch("ts", time\_unit="ns").alias("dt"))

&#x20;   return (df.sort("dt")

&#x20;             .group\_by\_dynamic("dt", every=every)

&#x20;             .agg(pl.all().last()))

```

Let the user pick the resample interval (100 ms / 1 s / 10 s / 1 min) and a time window, so zooming into a few minutes shows full resolution.



\*\*3.5 Data Explorer: order-book heatmap.\*\* Replay the `.npz` with hftbacktest, sample depth every N ms into a grid (time × price level → qty), and render with `go.Heatmap` (log-scaled colour). Overlay trades as dots. Cache the grid to Parquet per file and window, since computing it is slow.



\*\*Exit criteria:\*\* you can run a naive backtest \*from the browser\*, watch progress, and inspect quotes, fills, inventory and equity without touching the terminal.



\---



\### Phase 4 — Realism and the death of the naive market maker \*(about 1–2 weeks)\*



\*\*Goal:\*\* make the simulation honest, then measure \*why\* naive quoting loses.



\*\*Tasks\*\*

\- \[ ] \*\*Exact fill recording\*\* (fills version 2, Section 2.5).

\- \[ ] \*\*Markout analysis\*\* (`mmlab/analytics/markouts.py`):

&#x20; ```python

&#x20; import polars as pl



&#x20; HORIZONS\_MS = \[100, 500, 1\_000, 5\_000, 10\_000, 30\_000, 60\_000]



&#x20; def markouts(fills: pl.DataFrame, mids: pl.DataFrame) -> pl.DataFrame:

&#x20;     """fills: ts, side(+1 buy/-1 sell), price ; mids: ts, mid (sorted, fine resolution)"""

&#x20;     out = \[]

&#x20;     for h in HORIZONS\_MS:

&#x20;         f = fills.with\_columns((pl.col("ts") + h \* 1\_000\_000).alias("ts\_h")).sort("ts\_h")

&#x20;         j = f.join\_asof(mids.rename({"ts": "ts\_h"}), on="ts\_h", strategy="backward")

&#x20;         j = j.with\_columns((pl.col("side") \* (pl.col("mid") - pl.col("price"))).alias("mo"))

&#x20;         out.append({"horizon\_ms": h, "avg\_markout": j\["mo"].mean(),

&#x20;                     "avg\_markout\_bps": (j\["mo"] / j\["price"]).mean() \* 1e4})

&#x20;     return pl.DataFrame(out)

&#x20; ```

&#x20; For fine-resolution mids, save a separate `mids.parquet` at every book update (or every 10 ms), not just at the 100 ms decision steps.

\- \[ ] \*\*Sensitivity experiments\*\*, each a separate run compared in the dashboard:

&#x20; - queue model: `power\_prob` (power 2, 3) vs `risk\_adverse`

&#x20; - latency: 1 ms, 10 ms, 50 ms, 200 ms

&#x20; - fees: rebate (−0.00005), zero, VIP0 maker

&#x20; - half spread: 1, 2, 5, 10 ticks

\- \[ ] \*\*Latency from data:\*\* the feed's `local\_ts − exch\_ts` gives you \*feed\* latency. Plot its distribution in the Data Explorer. Later, replace constant latency with `intp\_order\_latency` built from a latency series.

\- \[ ] Add a \*\*Compare Runs\*\* page (overlay equity, metrics table, config diff).



\*\*Questions to answer in `CONTEXT.md`\*\*

1\. How much of gross PnL survives fees?

2\. At which horizon do markouts turn negative, and by how much?

3\. How sensitive is PnL to the queue model? If very sensitive, results are fragile.

4\. At what latency does the strategy go from viable to dead?



\*\*Exit criteria:\*\* you have a markout curve, a sensitivity table, and a written explanation of where naive market making loses money.



\---



\### Phase 5 — Avellaneda–Stoikov and GLFT \*(about 2 weeks)\*



\*\*Goal:\*\* implement inventory-aware optimal quoting with parameters calibrated from data.



\*\*5.1 Calibration\*\* (`mmlab/calibration/`)

\- \*\*Volatility σ:\*\* standard deviation of mid changes (in ticks) over a rolling window (for example, last 10 minutes of 100 ms steps), scaled to your time unit. Computed \*only from past data\* at each step.

\- \*\*Intensity A, k:\*\* at each step, for a set of depths δ (in ticks), measure how often trades reached at least δ away from the mid at the time of the step. Count per window, giving an arrival rate λ(δ). Fit:

&#x20; ```

&#x20; ln λ(δ) = ln A − k · δ      (ordinary least squares on log-rates)

&#x20; ```

&#x20; Re-fit on a rolling window inside the strategy (or precompute rolling estimates causally). Follow the hftbacktest GLFT tutorial's approach and check your fit visually: plot the empirical λ(δ) with the fitted curve on a Calibration tab in the dashboard.



\*\*5.2 Strategies\*\*

\- \[ ] `avellaneda.py`: Section 5.2 formulas with a rolling horizon `T − t` (for example, reset every hour). Params: `gamma`, `horizon\_s`, `window\_s`.

\- \[ ] `glft.py`: Section 5.3 formulas. Params: `gamma`, `window\_s`, `max\_position`, optional `skew\_multiplier`.

\- \[ ] Clip quotes to post-only (never cross the opposite best price).

\- \[ ] Hard inventory limit: stop quoting on the side that would grow inventory past `max\_position`.



\*\*5.3 Dashboard additions\*\*

\- Run Explorer: plot σ, A, k, reservation price and half spread over time.

\- Show the inventory-skew effect: scatter of quote offset vs position.



\*\*Exit criteria:\*\* GLFT shows clearly tighter inventory control than naive quoting (narrower inventory histogram, smaller drawdowns). You can explain each parameter's effect from dashboard comparisons. Don't expect it to be profitable at VIP0 fees on BTCUSDT.



\---



\### Phase 6 — Alpha skew: order-book imbalance and OFI \*(about 2 weeks)\*



\*\*Goal:\*\* shift your fair price using a short-horizon predictive signal, so you lean away from flow that's about to hurt you.



\*\*Signals\*\* (compute causally at each step)

\- \*\*Book imbalance:\*\* `I = (bid\_qty\_L1..n − ask\_qty\_L1..n) / (bid\_qty + ask\_qty)` over the top n levels (try n = 1, 5, 10).

\- \*\*OFI\*\* (Cont–Kukanov–Stoikov): sum of signed changes at the best bid/ask over a window. Reuse logic from your earlier OFI pipeline.

\- \*\*Trade flow:\*\* signed trade volume over the last X seconds.



\*\*Implementation\*\*

```

fair\_price = mid + β · signal · tick\_size

```

then apply GLFT around `fair\_price` instead of `mid`. Fit β on a \*\*training\*\* day, evaluate on a \*\*different\*\* day.



\*\*Signal research before trading it\*\* (do this in a notebook, then add a Signals tab to the dashboard):

\- correlation of the signal with mid change over the next 100 ms / 1 s / 5 s

\- signal decay curve: predictive power vs horizon

\- does the signal improve \*\*markouts\*\*? This is the key metric, more than PnL.



\*\*Exit criteria:\*\* the signal shows out-of-sample predictive power, and markouts with alpha skew are measurably better than without it \*\*on held-out days\*\*. If not, write down that it didn't work; that's still a valid result.



\---



\### Phase 7 — Robustness: sweeps, walk-forward, regimes \*(about 2 weeks)\*



\*\*Goal:\*\* find out whether anything you found is real or a fit to a handful of days.



\*\*Tasks\*\*

\- \[ ] `mmlab/sweep.py`: run a parameter grid (for example, γ × skew\_multiplier × β) in parallel with `concurrent.futures.ProcessPoolExecutor` (each process runs one backtest). Save each as a normal run plus a `sweeps/<sweep\_id>/index.parquet`.

\- \[ ] \*\*Walk-forward:\*\* calibrate or choose params on day N, test on day N+1, roll forward. Report \*only\* the out-of-sample stitched result as "the" performance.

\- \[ ] \*\*Regime split:\*\* label days or hours by realized volatility (low/mid/high) and trend strength; report metrics per regime.

\- \[ ] \*\*Second symbol:\*\* repeat the best config on the mid-cap perp.

\- \[ ] Get more data: more free first-of-month days, or a paid Tardis month for one symbol if you're committed.



\*\*Sweeps page\*\*

\- Heatmap of chosen metric over two parameters (e.g. γ vs β → net PnL or Sharpe).

\- Toggle between \*\*train\*\* and \*\*test\*\* heatmaps. If the best cell in train is unremarkable in test, you've found overfitting.

\- \*\*Parameter-stability view:\*\* a good region is a \*plateau\* (neighbouring cells also good), not a single bright spike.



\*\*Exit criteria:\*\* a written verdict in `CONTEXT.md`: which components (inventory control, alpha skew) hold up out-of-sample, in which regimes, and at what fee level the strategy breaks even.



\---



\### Phase 8 — Optional extensions



Pick based on interest:

\- \*\*Hawkes processes\*\* for order arrival: model self-exciting trade intensity (`tick` library or your own MLE), and widen quotes when intensity spikes.

\- \*\*Multi-level quoting:\*\* place orders at several depths with sizes from the GLFT model.

\- \*\*Cross-venue fair price:\*\* use Bybit or OKX mid as a lead signal for Binance quotes (needs synchronized multi-venue data).

\- \*\*Live paper trading:\*\* hftbacktest has a live-trading path (Rust connector), and `nautilus\_trader` offers backtest-to-live parity. Use \*\*Binance Futures testnet only\*\*. Note that testnet liquidity and fills don't reflect real markets.

\- \*\*Your own data collector:\*\* record Binance websocket depth and trade streams 24/7 with `cryptofeed` on a cheap VPS, and convert to `.npz` nightly.



\---



\## 7. Metrics reference (`mmlab/analytics/metrics.py`)



| Metric | Definition | Watch for |

|--------|------------|-----------|

| Net PnL | final equity − initial equity (after fees) | |

| Gross PnL | net PnL + fees | Gross > 0 but net < 0 means fees are the killer |

| Fees paid | sum of fees | |

| Sharpe | mean / std of \*\*daily\*\* (or hourly) PnL, annualized with √365 for crypto | Don't annualize 100 ms returns; it's meaningless |

| Max drawdown | max peak-to-trough of equity | |

| Return over trade | net PnL / traded notional, in bps | Compare directly against the fee in bps |

| Fill count / rate | fills, fills per hour | |

| Avg markout (τ) | Section 5.4, in bps | Negative at 1–10 s means adverse selection |

| Spread captured | average (fill price vs mid at fill), in bps | |

| Inventory stats | mean \\|q\\|, % time at limit, histogram | Pinned at the limit means skew too weak |

| Inventory half-life | time for \\|q\\| to halve after a fill | |

| Time quoted | % of steps with both sides live | |



\---



\## 8. Data budget and storage



\- One day of BTCUSDT L2 plus trades is roughly a few hundred MB compressed CSV and a similar size `.npz`. Budget 1–2 GB of disk per day per symbol, raw plus converted.

\- Delete `raw/` after successful conversion and validation (keep the manifest).

\- Run folders are small if you downsample `timeseries.parquet` to the decision step and keep `mids.parquet` only when needed for markouts.



\---



\## 9. Sanity tests (`tests/`): mandatory



Run with `uv run pytest`. A failing test blocks the next phase.



| Test | Expected |

|------|----------|

| \*\*No-trade strategy\*\* (never submits) | PnL = 0, fees = 0, position = 0 |

| \*\*Determinism\*\* | Same config twice → identical `metrics.json` |

| \*\*Fee sign\*\* | With maker fee > 0, fees > 0; with rebate, fees < 0 |

| \*\*Post-only\*\* | No fill ever recorded as taker |

| \*\*Inventory limit\*\* | \\|position\\| never exceeds `max\_position + order\_qty` |

| \*\*Signal shift\*\* (Phase 6) | Shifting the alpha signal one step into the \*\*future\*\* improves results a lot. If it doesn't, your "real" signal may already be leaking future data |

| \*\*Random signal\*\* (Phase 6) | Replacing the alpha with noise does \*\*not\*\* improve markouts |

| \*\*Data integrity\*\* | Validation checks pass on every manifest file |

| \*\*Metrics unit test\*\* | Hand-built tiny equity curve → known Sharpe/drawdown |



\---



\## 10. Working with AI on this project



AI-written backtest code is where subtle bugs live. This workflow keeps it honest:



1\. \*\*One phase (or sub-task) per session.\*\* Paste the relevant section of this file plus `CONTEXT.md`.

2\. \*\*`CONTEXT.md` is the project's memory:\*\* current phase, decisions made, the artifact format, known issues, results so far. Update it at the end of every session.

3\. \*\*Tests before trust.\*\* Ask the AI to write the sanity test for a feature \*before or together with\* the feature.

4\. \*\*Don't let it guess APIs.\*\* When an hftbacktest call fails, have it read the docs or source (link the page) rather than inventing methods.

5\. \*\*Causality review:\*\* for any feature or signal code, ask explicitly: \*"Show me every line where a value at time t could depend on data after t."\*

6\. \*\*Freeze interfaces.\*\* Config schema and artifact format change only deliberately, with a version bump in `config.json`.

7\. \*\*Read the diff.\*\* You're the lead on this; the AI is the junior. Ask it to explain anything you don't understand, since that's the learning goal.



\---



\## 11. Milestone checklist



\- \[ ] \*\*P0:\*\* Environment works; tutorial run; concepts written down

\- \[ ] \*\*P1:\*\* 2–3 validated days in `.npz` with manifest

\- \[x] \*\*P2:\*\* Naive market maker via CLI; artifact format frozen; first sanity tests green

\- \[ ] \*\*P3:\*\* Dashboard: launch runs and explore them in the browser

\- \[ ] \*\*P4:\*\* Exact fills, markout curve, sensitivity study, Compare page

\- \[ ] \*\*P5:\*\* Calibrated AS and GLFT; calibration tab; inventory control demonstrated

\- \[ ] \*\*P6:\*\* Imbalance/OFI alpha skew; signal research; out-of-sample markout comparison

\- \[ ] \*\*P7:\*\* Sweeps, walk-forward, regimes; written verdict

\- \[ ] \*\*P8:\*\* (optional) Hawkes / multi-level / cross-venue / testnet



\---



\## 12. Useful links



\- hftbacktest docs and tutorials: https://hftbacktest.readthedocs.io/

\- hftbacktest source: https://github.com/nkaz001/hftbacktest

\- Tardis.dev (data): https://tardis.dev and https://docs.tardis.dev

\- Binance public bulk data: https://data.binance.vision

\- Streamlit docs: https://docs.streamlit.io

\- Plotly Python: https://plotly.com/python/

\- Polars: https://docs.pola.rs

