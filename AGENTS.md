# AGENTS.md

Entry point for any AI agent working in this repository. Read this file first, then the documents it links to.

## What this project is

MM-Lab is a research lab for crypto market making. It simulates a limit-order-book market maker on perpetual futures (Binance USDⓈ-M, BTCUSDT first) with hftbacktest, and will expose a Streamlit dashboard for running and analysing backtests.

It is a learning and research tool, not a trading bot. A negative result (a strategy that loses after fees) is a valid result.

The full phased build guide is [plan.md](plan.md). Running notes, decisions, and results are in [CONTEXT.md](CONTEXT.md).

## Documents

| File | Read it when |
|---|---|
| [plan.md](plan.md) | You need the phase goals, formulas, config schema, artifact format, or exit criteria. It is the source of truth for intent. |
| [docs/CODING.md](docs/CODING.md) | Before writing or editing any code. Style and comment rules are strict. |
| [docs/INFRASTRUCTURE.md](docs/INFRASTRUCTURE.md) | You need to know what exists today: layout, modules, data flow, commands, environment. |
| [CONTEXT.md](CONTEXT.md) | At the start of a session (current phase, decisions, known issues) and at the end (update it). |
| [README.md](README.md) | Human-facing setup and common commands. |

## Current status

Phase 0 (setup and theory) is done except the reading and the concept write-up. Phase 1 (data pipeline, `mmlab/data/`) is done and has run on four real Tardis days (BTCUSDT 2026-07-01, 08-01, 09-01, 10-01). Phase 2 is done: `mmlab/config.py`, `mmlab/strategies/naive.py`, `mmlab/analytics/metrics.py` and the runner `mmlab/run.py` produce a run folder, and the Phase 2 sanity tests pass. Phase 3 (dashboard, `dashboard/`) is done: Home, Run Backtest, Run Explorer and a Strategies page, with a `?` tooltip on every input and number. Phase 4 is done: exact fills, `mids.parquet` and `markouts.parquet` in every run (config and artifact version 2; version 1 runs still load), the markout curve and inventory half-life, a sensitivity study, feed latency from the data, and the Compare Runs and Data Explorer pages. The result: the naive quoter loses on every day tried because its fills are adversely selected (about -1 bp per traded dollar before a 2 bp fee); the written explanation is in [CONTEXT.md](CONTEXT.md). Next is Phase 5 (Avellaneda–Stoikov and GLFT). The authoritative status is in [CONTEXT.md](CONTEXT.md).

## Commands

All commands run from the repository root with uv. Python 3.12 is pinned.

```bash
uv sync                                      # install dependencies
uv run pytest                                # tests
uv run ruff check .                          # lint
uv run ruff format .                         # format
uv run python -m mmlab.data download --symbol BTCUSDT --from 2026-09-01 --to 2026-09-02
uv run python -m mmlab.data ingest --symbol BTCUSDT --date 2026-09-01 --max-memory-gb 8   # convert, validate, register
uv run python -m mmlab.data latency --symbol BTCUSDT --date 2026-09-01   # feed latency of an ingested day
uv run python -m mmlab.run --config configs/naive_btcusdt.json   # run one backtest, writes runs/<id>/
uv run python -m scripts.phase4_sensitivity --date 2026-10-01   # Phase 4 sensitivity grid, 21 runs
uv run python scripts/phase0_convert.py      # convert sample data to npz
uv run python scripts/phase0_tutorial.py     # run the Phase 0 tutorial
uv run python -m streamlit run dashboard/app.py   # dashboard (python -m puts the repo root on the import path)
```

## Architecture in one paragraph

Raw Tardis/Binance data is converted to hftbacktest `.npz` files (`mmlab.data`). A CLI runner (`mmlab.run`) reads a JSON config, replays the data through a Numba-compiled strategy, and writes a run folder under `runs/` (config, metrics, timeseries, exact fills, mid samples, markouts). The Streamlit dashboard never runs backtest logic: it writes a config, launches the runner as a subprocess, and reads the saved artifacts. Details are in [docs/INFRASTRUCTURE.md](docs/INFRASTRUCTURE.md).

## Rules that always apply

1. Follow [docs/CODING.md](docs/CODING.md). Comments are one line, above the code, and only when needed.
2. Do not guess hftbacktest APIs. When a call fails, read the docs (https://hftbacktest.readthedocs.io/) or the installed source. The library is v2.4.x and has already drifted from older examples (for example `constant_latency` is deprecated).
3. Causality: a value at time `t` must never depend on data after `t`. Check every feature, signal and calibration for this.
4. Units: work in ticks for prices and depths, nanoseconds for time. State the unit in the name when it is not obvious (`step_ns`, `half_spread_ticks`).
5. Reproducibility: every result must be reproducible from a saved config. The config schema and the run artifact format are frozen interfaces; change them only deliberately, with a version bump.
6. Be suspicious of good results. A Sharpe above about 3, near-zero drawdown, or a too-smooth equity curve means look for a bug first.
7. Sanity tests (plan.md Section 9) gate each phase. A failing test blocks moving on.
8. Do not swallow errors or add fallbacks that hide failures. Fail loudly.
9. Do not commit data, run artifacts, or secrets. `data/raw/`, `data/npz/`, `runs/` and `.env` are gitignored.
10. Do not push, publish, or delete data without the user's explicit approval.
11. Always update the documentation after every change. A change is not finished until the docs match the code (see below).

## Keeping docs current (mandatory)

Documentation is part of the change, not a follow-up. Update it in the same commit as the code, before reporting the work as done.

| If you change... | Update |
|---|---|
| A module, file, folder, data file, or data flow | [docs/INFRASTRUCTURE.md](docs/INFRASTRUCTURE.md) (layout, modules table, data inventory, status markers) |
| A command, setup step, or dependency | [docs/INFRASTRUCTURE.md](docs/INFRASTRUCTURE.md), the Commands section of this file, and [README.md](README.md) |
| Coding conventions or tooling | [docs/CODING.md](docs/CODING.md) |
| Project status, scope, or these rules | The Current status section of this file |
| Config schema or run artifact format | [docs/INFRASTRUCTURE.md](docs/INFRASTRUCTURE.md) (Interfaces) and bump the version |
| Anything learned, decided, or measured | [CONTEXT.md](CONTEXT.md): decisions, results, known issues, current phase |
| A phase milestone or exit criterion | The milestone checklist in [plan.md](plan.md) |

Before finishing, re-read the docs you touched and confirm they describe what the code does now. If nothing needed updating, say so explicitly in the summary.
