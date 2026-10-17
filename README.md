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
uv run python -m mmlab.run --config configs/naive_btcusdt.json   # one backtest, writes runs/<id>/
uv run pytest                           # sanity tests
uv run ruff check .                     # lint
uv run streamlit run dashboard/app.py   # dashboard (Phase 3)
```

Data (`data/raw`, `data/npz`) and run artifacts (`runs/`) are gitignored. To keep data on another drive, set `MMLAB_DATA_DIR` to that folder. Tardis downloads outside the free first-of-month days need `TARDIS_API_KEY`.
