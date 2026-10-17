# CONTEXT

Running notes for AI sessions. Update at the end of every session.

## Current phase

Phase 0 — environment, repo, skeleton and tutorial done; reading (Section 4, resources 1-3) and the concept write-up below remain. Phase 1 — code and tests written and run on four real Tardis days (2026-07-01, 08-01, 09-01, 10-01; all passed; chunk boundaries checked on 10-01). Phase 2 — done (see below). Phase 3 — Home, Run Backtest and Run Explorer built and checked in a browser (see below); the Data Explorer page is not built and the user's own test of the dashboard is pending. Next: user test of Phase 3, then Phase 4 markouts and exact fills.

## Decisions

- Project lives in the repo root (no nested `mm-lab/` folder); package name `mm-lab`, import package `mmlab`.
- Python 3.12 pinned via `.python-version` (uv otherwise picks 3.15, which has no wheels for several dependencies).
- Native Windows, no WSL. Fall back to WSL2 only if hftbacktest/Numba misbehaves.
- Remote: https://github.com/Sh1ljo/MMCrypto.git (branch `main`).
- Agent docs: `AGENTS.md` is the entry point (`CLAUDE.md` imports it), with `docs/CODING.md` (one-line comments above code, no trailing or multi-line comments) and `docs/INFRASTRUCTURE.md` (what exists). Docs must be updated with every change; this is rule 11 in `AGENTS.md`.

## Artifact format

Frozen at version 1 in Phase 2 (`CONFIG_VERSION`). See docs/INFRASTRUCTURE.md, Interfaces.

## Phase 0 tutorial (done)

- `scripts/phase0_convert.py`: converts the hftbacktest sample feed dumps (`data/raw/btcusdt_2024080{8,9}.gz`, from `nkaz001/hftbacktest/examples/usdm`) to `.npz` plus an end-of-day snapshot via `hftbacktest.data.utils.binancefutures.convert` and `snapshot.create_last_snapshot`.
- `scripts/phase0_tutorial.py`: BBO printer, then a symmetric +/-5 tick GTX quoter, then `LinearAssetRecord(...).stats()`.
- The sample day is only about 5 minutes (00:00-00:05 UTC, 2024-08-09, about 302 one-second rows), so the stats are illustrative only. Sharpe -624 and similar are annualization artifacts, not results.
- Recorder fields (v2.4.4): `timestamp, price, position, balance, fee, num_trades, trading_volume, trading_value`.

## Phase 1 (code written, not yet run on real data)

- Built on a work laptop with no downloads: all of `mmlab/data/` is covered by 31 tests on synthetic Tardis-format files. Real data has to be run on the main PC (about 30-40 GB reserved, 32 GB RAM).
- Machine independence: data location via `MMLAB_DATA_DIR`; converter buffers sized from an exact row count instead of a fixed number; optional `--max-memory-gb` guard.
- Deviations from plan.md: (1) buffers come from counting rows, not `buffer_size=200_000_000` (about 12.8 GB), because the depth loop is Numba-compiled without bounds checks so an undersized buffer is unsafe; (2) tardis_dev 5.x uses `download_datasets`; (3) end-of-day snapshots are not built per day, since Tardis supplies a start-of-day snapshot and free days are not consecutive; (4) the crossed-book check is "broken samples" (wiped side or inverted book), because hftbacktest deletes stale levels on a crossing so `bid >= ask` never appears.
- Validation smoke test on the 5-minute Binance sample: 666,731 events, largest gap 0.59 s, median spread 1 tick, 0 broken samples out of 30,130.
- First real-data steps: `download` one free first-of-month day (check disk space first), `ingest` it with `--max-memory-gb`, and compare the printed `estimated_peak_gb` with the actual memory used to calibrate `PEAK_MEMORY_FACTOR`. Confirm the free tier works without an API key.
- Open risk: a full BTCUSDT day may need more than 32 GB at the 4x estimate; if so, split conversion by time range (hftbacktest accepts a list of npz files).
- Open limitation: a crossing that leaves both book sides non-empty is invisible to the sampled check; an event-level book check could be added if real data shows a need.

## Real-data run (2026-10-17)

- Phase 0: sample feeds re-fetched from `nkaz001/hftbacktest` and converted; tutorial runs. On Windows set `PYTHONIOENCODING=utf-8` or `stats.summary()` raises `UnicodeEncodeError` (cp1250 console).
- Phase 1 download: `2026-10-01` BTCUSDT downloaded with no API key (free first-of-month tier confirmed). Trades 24 MB, book L2 796 MB gzipped.
- Phase 1 ingest: `count_rows` estimates 35.4 GB peak (buffer about 8.9 GB at 4x). With a 22 GB watchdog the single-shot `tardis.convert` was killed at 22.1 GB, so the full day does not fit comfortably in 32 GB RAM. No npz was written.
- Fix: chunked conversion (`mmlab/data/split.py`, `convert_day_chunked`). Hourly slices; no snapshots needed between slices because hftbacktest carries book state across a list of npz files. Manifest bumped to version 2 (`paths` list per symbol and day).
- Result for 2026-10-01 BTCUSDT: 24 files, 1.1 GB npz, peak process memory 4.4 GB (largest slice estimated 2.8 GB; the 4x factor is conservative). 152.6M events, 3.37M trades, 0 broken book samples of 8.64M, max gap 0.39 s, spread p50/p99 = 1 tick, max 368 ticks (brief dislocation, worth a look). Validation passed.
- Boundary check (2026-10-17, one-off script, not in repo), all passed: (1) event timestamps are non-decreasing inside every slice, for both local and exchange timestamps; (2) gaps across the 23 slice boundaries are 1-29 ms, with no lost or repeated events; (3) hftbacktest replays all 24 files in one run, 86,399 one-second rows, 0 bad rows (NaN or bid >= ask); (4) spread is 1 tick on both sides of every boundary; (5) last trade vs mid: p50 0.5 ticks, p99 6.5, p99.9 71; (6) the largest mid jumps (up to 1262 ticks in 1 s, about 126 USD) and the 368-tick spread coincide with trade bursts of 1k-5k trades per second and the new mid matches the traded prices, so they are real moves, not artifacts. Mid jumps at hour boundaries (up to 247 ticks) also coincide with busy seconds.
- Still not checked: the chunked output equals a single-file conversion on real data (only on synthetic data; it does not fit in RAM, so the boundary check above stands in for it).
- Note for Phase 2: 1 s mid moves are fat-tailed on this day (p99 about 191 ticks), so a fixed small-tick quote distance gets run over in bursts.

## Phase 2 (done 2026-10-17)

- Built: `mmlab/config.py`, `mmlab/strategies/naive.py`, `mmlab/analytics/metrics.py`, `mmlab/run.py`, `configs/naive_btcusdt.json`, tests `test_run` and `test_metrics`. 47 tests pass; the plan Section 9 sanity tests no-trade, determinism, fee sign, post-only and inventory limit are all covered.
- Deviations from plan.md: (1) order ids are `2 x tick` (buy) and `2 x tick + 1` (sell) so a cancelling buy cannot collide with a new sell at the same tick; (2) the quote on a side is null (not quoted) when the position limit blocks it; (3) `constant_order_latency` replaces the deprecated `constant_latency`; (4) the first few steps before the book exists are dropped, and counted in the log; (5) run folder names use seconds (`HHMMSS`) so two runs in a minute cannot collide; (6) determinism holds for `metrics.json` except `runtime_s`.
- Runtime: a full day (864k steps of 100 ms, 152M events) replays in about 28 s.
- Not built yet: markouts and inventory half-life (Phase 4), exact fills (Phase 4).

## More days (2026-10-17)

- Downloaded and ingested the free first-of-month days 2026-07-01, 08-01 and 09-01 (BTCUSDT), alongside 10-01. All validate with 0 broken samples. Events: 181.1M (07-01), 75.7M (08-01, a Saturday), 141.6M (09-01), 152.6M (10-01). Max gap 0.4-0.9 s. Max spread 360-1019 ticks (brief dislocations). Ingest of a day takes a few minutes; peak slice estimate 2.4-3.2 GB.
- Naive quoter on each day (same config as the 10-01 run, 100 ms steps, 2 bps maker fee):

| day | hourly vol (bps) | 5 ticks: fills / net / gross | 5 ticks return over trade (bps) | 100 ticks: fills / net / gross |
|---|---|---|---|---|
| 2026-07-01 | 55 | 47,555 / -839 / -275 | -2.98 | 2,967 / -70 / -35 |
| 2026-08-01 | 14 | 5,738 / -109 / -37 | -3.02 | 222 / -7 / -4 |
| 2026-09-01 | 33 | 27,315 / -656 / -230 | -3.08 | 2,529 / -77 / -37 |
| 2026-10-01 | 31 | 30,370 / -764 / -254 | -3.00 | 2,774 / -66 / -19 |

- The 5-tick return over trade is -3.0 bps on all four days, so about -1 bp before fees on top of the 2 bps fee. Fill count and PnL scale with volatility and volume, the per-trade result does not. The sign of the Phase 2 result holds on every day tried.
- Not yet done: a single run across several days (state between non-consecutive days, per-day metrics), and consecutive days for walk-forward (needs a paid Tardis key).

## Phase 3 (built 2026-10-17, user test pending)

- Built: `dashboard/` (`app.py` router, `home.py`, `lib.py`, `charts.py`, `ui.py`, `pages/1_Run_Backtest.py`, `pages/2_Run_Explorer.py`), `.streamlit/config.toml`, and tests `test_dashboard_lib`, `test_dashboard_charts`, `test_dashboard_pages`. 98 tests pass. No change to `mmlab/`, so the config schema and run artifact format are unchanged (still version 1).
- Start it with `uv run python -m streamlit run dashboard/app.py`. The bare `streamlit run` fails to import `mmlab` because the project is not installed as a package (Streamlit adds only the script's folder to `sys.path`; `python -m` adds the working directory).
- Checked in Edge through Playwright (throwaway venv in the session scratchpad, not in the repo): all three pages in light and dark, hover tooltip, linked drag zoom, and a run launched from the form. A 3-file prefix of 2026-07-01 ran in 13.8 s and a 1-file prefix in 9.2 s; "Open in explorer" landed on the new run. Reads and figure builds take under 150 ms on a full day with 31,572 fills.
- Bugs found while building and fixed: a day stored as one file crashed the file slider (min equals max); 8,000 fill markers hid the quote lines (fills are now drawn under the lines, 70% opaque); the quoted-spread histogram collapsed to a hairline when a rare tail stretched the axis (axis is now cut at p99 and the title says so); the first page was labelled "app" (now `st.navigation` with Home).
- Decisions: buys and sells are blue and orange with different marker shapes, not green and red (colour-blind safety, and red and green read as good and bad); the run form replays a prefix of one day's files rather than any selection, because a later file alone starts with an empty book; several days in one run stay unavailable until state across non-consecutive days is checked.
- Limits worth knowing: the log shows no per-step progress because the replay is one compiled loop (adding progress would mean running `naive_mm` in chunks, a change to the Phase 2 runner); Sharpe is `n/a` under 2 hours of data; KPI rows are whole-run, not for the selected window; the markout KPIs wait for Phase 4.
- Two test runs made while checking sit in `runs/` (`naive_hs5_20260701_3f`, `naive_hs5_20260701_1f`); they are gitignored and safe to delete. The 3-file one is a high-turnover 5-tick quoter on 2026-07-01 and loses 157 net over 3 hours (gross -59, fees 98), the same sign as every other run.
- Not built: Data Explorer (order-book heatmap, spread, trade intensity), Compare (Phase 5 and later) and Sweeps (Phase 7).

### Friendlier dashboard and Strategies page (2026-10-17, same day)

- Asked for: explain everything with a `?` icon, keep text light, and a page explaining the strategies with formulas. Done: every input, KPI, section heading and Home column has a tooltip from `dashboard/help_text.py` (a test fails if a widget lacks one); permanent captions are gone; the Run Backtest execution settings (fees, delays, queue) sit in a collapsed expander; navigation is grouped into Lab and Learn.
- New `Strategies` page: tabs for the naive quoter (built), Avellaneda–Stoikov, GLFT and alpha skew (planned, formulas copied from plan.md Section 5 and 6), the metric formulas, and a glossary. The naive tab has an interactive "Try it" calculator that draws the bid and ask the strategy would place.
- Change in `mmlab/`: the two quoting rules were pulled out of `naive_mm` into `quote_ticks` and `quote_sides` so the calculator calls the strategy's own code (as plain Python through `.py_func`, so the dashboard compiles nothing). Behaviour is unchanged: a full real day (BTCUSDT 2026-10-01, 5 ticks) was re-run and every metric, all 863,992 timeseries rows and all fill rows are identical to the earlier run. Config schema and artifact format are untouched.
- 128 tests pass (30 more). Checked in Edge again: every tab of the Strategies page, the new Run Backtest layout, a hover over a `?` icon, and the Explorer.

## Known issues

- hftbacktest 2.4.4: `BacktestAsset.constant_latency()` is deprecated; use `constant_order_latency()`. plan.md Section 2.2 still says `constant_latency`; use the new name when building `mmlab/run.py`.
- `Stats.summary()` returns a polars DataFrame and does not print; wrap in `print()` outside notebooks.
- Dashboard: `st.context.theme.type` can be wrong for a moment after first load or a theme change, so chart colours may briefly use the other mode's palette.
- Converter reports `local_timestamp is ahead of exch_timestamp by ~1.27 s` on the sample files and corrects it. Relevant to Phase 4 feed-latency analysis (the correction shifts the latency baseline).

## Results so far

Naive symmetric post-only quoter, BTCUSDT 2026-10-01 (one day), 100 ms steps, qty 0.001, max position 0.01, maker fee 2 bps, latency 10 ms each way, power-prob queue (power 2). One day, one regime; nothing here is a conclusion about the strategy class.

| half spread (ticks) | net PnL (USDT) | gross PnL | fees | fills | return over trade (bps) | spread captured (bps) |
|---|---|---|---|---|---|---|
| 1 | -805.2 | -270.8 | 534.4 | 31,811 | -3.01 | 0.02 |
| 5 | -764.2 | -254.0 | 510.2 | 30,370 | -3.00 | 0.06 |
| 20 | -630.2 | -192.5 | 437.7 | 26,054 | -2.88 | 0.24 |
| 100 | -66.0 | -19.3 | 46.6 | 2,774 | -2.83 | 1.08 |
| 200 | -2.7 | +4.2 | 6.8 | 407 | -0.78 | 2.24 |

- Fees equal exactly 2 bps of traded notional at every setting, so no fill was a taker (post-only holds on real data).
- Gross PnL is negative at 1-100 ticks: even before fees the quotes lose money. Spread captured is tiny against a fee of 2 bps per side, and the loss is the price moving against inventory right after fills (adverse selection). Only the 200-tick run is gross-positive, on 407 fills, which is noise-sized.
- Hourly Sharpe is about -129 for the 5-tick run; with only 24 hourly samples treat it as "consistently negative", not as a number.
- Break-even needs a half spread of roughly 2 bps of price, about 170 ticks (about 17 USD), which almost never fills. Phase 4 markouts should confirm the adverse-selection reading.

## Concepts (own words, Phase 0 exit criteria)

- Reservation price:
- Inventory skew:
- Adverse selection:
- Queue position:

## Result checks (2026-10-17, one-off scripts, not in repo)

Fill audit of the 5-tick run (30,044 inferred fill rows against the raw trade events): 98.8% of directional fills have a trade of the right aggressor side and price within the 130 ms before the row; 99.0% are priced at one of the previous four steps' quotes. The failures break down as 295 merged-step rows (two fills in one step give an average price that is not a quote, an artifact of fills version 1), 327 of 366 single fills whose trade is up to 1 s away (feed latency spikes in busy moments), and 39 (0.13%) with no trade at all, all at the touch while the book moved through the quote (fills by book crossing). No fill is unexplained by the data. Buys priced above the previous mid: 151 of 30,014.

Sensitivity (BTCUSDT 2026-10-01, all fees 2 bps):

| case | fills | net PnL | gross PnL |
|---|---|---|---|
| 5 ticks, queue model risk_adverse / power 1 / 2 / 3 | 30,370 (all) | -764 (all) | -254 (all) |
| 5 ticks, latency 1 ms each way | 33,702 | -850 | -283 |
| 5 ticks, latency 50 ms | 26,347 | -662 | -219 |
| 5 ticks, latency 100 ms | 24,266 | -614 | -206 |
| 100 ticks, latency 1 / 10 / 50 / 100 ms | 2,658 / 2,774 / 3,463 / 4,348 | -66 / -66 / -81 / -108 | -21 / -19 / -23 / -35 |
| 0 ticks (at the touch), risk_adverse | 37,994 | -924 | -285 |
| 0 ticks, power 1 / 2 / 3 | 45,080 / 41,957 / 41,555 | -1058 / -999 / -991 | -301 / -294 / -293 |

- The queue model has no effect at 1 tick or more: those quotes sit behind the best price, so there is no queue to wait in. It matters only at the touch (0 ticks), where risk_adverse gives about 10% fewer fills than power 2.
- Latency changes the fill count (more latency means fewer fills at 5 ticks, more at 100 ticks) and the spread captured turns negative at 50-100 ms (stale quotes picked off), but net and gross PnL stay negative in every case. The sign of the result does not depend on the queue model or latency.
