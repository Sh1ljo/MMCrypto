# MM-Lab

A crypto market-making research lab: limit-order-book simulation on perpetuals (hftbacktest), with a Streamlit dashboard for running and analysing backtests. See [plan.md](plan.md) for the phased build guide.

## Setup

Requires [uv](https://docs.astral.sh/uv/). Python 3.12 is pinned in `.python-version`.

```bash
uv sync
uv run python -c "import hftbacktest, numba, polars, streamlit; print('ok')"
```

## Common commands

```bash
uv run pytest                           # sanity tests
uv run ruff check .                     # lint
uv run streamlit run dashboard/app.py   # dashboard (Phase 3)
```

Data (`data/raw`, `data/npz`) and run artifacts (`runs/`) are gitignored.
