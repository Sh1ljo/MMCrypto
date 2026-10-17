# MM-Lab

A crypto market-making research lab: limit-order-book simulation on perpetuals (hftbacktest), with a Streamlit dashboard for running and analysing backtests. See [plan.md](plan.md) for the phased build guide.

## Documentation

- [AGENTS.md](AGENTS.md): entry point for AI agents and contributors, with the rules that always apply
- [docs/CODING.md](docs/CODING.md): code style and comment rules
- [docs/INFRASTRUCTURE.md](docs/INFRASTRUCTURE.md): layout, modules, data flow, current status
- [CONTEXT.md](CONTEXT.md): running notes, decisions, results

## Setup

Requires [uv](https://docs.astral.sh/uv/). Python 3.12 is pinned in `.python-version`.

```bash
uv sync
uv run python -c "import hftbacktest, numba, polars, streamlit; print('ok')"
```

## Common commands

```bash
uv run python -m mmlab.data download --symbol BTCUSDT --from 2026-09-01 --to 2026-09-02
uv run python -m mmlab.data ingest --symbol BTCUSDT --date 2026-09-01 --max-memory-gb 8
uv run python -m mmlab.data latency --symbol BTCUSDT --date 2026-09-01   # feed latency of an ingested day
uv run python -m mmlab.run --config configs/naive_btcusdt.json   # one backtest, writes runs/<id>/
uv run python -m scripts.phase4_sensitivity --date 2026-10-01   # the Phase 4 sensitivity grid (21 runs, about 12 minutes)
uv run pytest                           # sanity tests
uv run ruff check .                     # lint
uv run python -m streamlit run dashboard/app.py   # dashboard at http://localhost:8501
```

The dashboard has six pages: **Home** (every run folder, select one to open it), **Run Backtest** (pick a registered day, strategy and execution settings, watch the run), **Run Explorer** (KPIs, price, position and equity panels, the markout curve, distributions), **Compare Runs** (2 to 8 runs side by side: numbers, PnL, markouts and the settings that differ), **Data Explorer** (a registered day and its feed latency) and **Strategies** (what each strategy does, with formulas, a quote calculator and a glossary). Open pages from the sidebar rather than by typing their URL. Hover the `?` icons for a short explanation of anything on screen. It needs at least one ingested day in `data/manifest.json`. Run it with `python -m streamlit`, not the bare `streamlit` command: `mmlab` is not installed as a package, and `python -m` is what puts the repository root on the import path.

Data (`data/raw`, `data/npz`) and run artifacts (`runs/`) are gitignored. To keep data on another drive, set `MMLAB_DATA_DIR` to that folder. Tardis downloads outside the free first-of-month days need `TARDIS_API_KEY`.
