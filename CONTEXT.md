# CONTEXT

Running notes for AI sessions. Update at the end of every session.

## Current phase

Phase 0 — environment, repo, skeleton and tutorial done; reading (Section 4, resources 1-3) and the concept write-up below remain. Phase 1 — code and tests written and run on four real Tardis days (2026-07-01, 08-01, 09-01, 10-01; all passed; chunk boundaries checked on 10-01). Phase 2 — done (see below). Phase 3 — done (the user signed it off at the start of Phase 4). Phase 4 — done 2026-10-17 (see below): exact fills, markout curve, sensitivity study, Compare Runs page and the Data Explorer with feed latency; the written explanation of where the naive quoter loses is in the Phase 4 section. Next: Phase 5, Avellaneda–Stoikov and GLFT with calibration.

## Decisions

- Project lives in the repo root (no nested `mm-lab/` folder); package name `mm-lab`, import package `mmlab`.
- Python 3.12 pinned via `.python-version` (uv otherwise picks 3.15, which has no wheels for several dependencies).
- Native Windows, no WSL. Fall back to WSL2 only if hftbacktest/Numba misbehaves.
- Remote: https://github.com/Sh1ljo/MMCrypto.git (branch `main`).
- Agent docs: `AGENTS.md` is the entry point (`CLAUDE.md` imports it), with `docs/CODING.md` (one-line comments above code, no trailing or multi-line comments) and `docs/INFRASTRUCTURE.md` (what exists). Docs must be updated with every change; this is rule 11 in `AGENTS.md`.

## Artifact format

Frozen at version 1 in Phase 2 (`CONFIG_VERSION`), bumped to version 2 in Phase 4 (exact fills, `mids.parquet`, `markouts.parquet`, `mid_sample_ns`); version 1 run folders stay readable. See docs/INFRASTRUCTURE.md, Interfaces.

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
- Markouts, inventory half-life and exact fills were built in Phase 4. `infer_fills` (fills version 1) is gone; version 1 run folders keep their inferred `fills.parquet`.

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
- Not built in Phase 3: Data Explorer, Compare and Sweeps. Compare and a first Data Explorer (day summary and feed latency; no heatmap yet) came in Phase 4; Sweeps stay in Phase 7.

### Friendlier dashboard and Strategies page (2026-10-17, same day)

- Asked for: explain everything with a `?` icon, keep text light, and a page explaining the strategies with formulas. Done: every input, KPI, section heading and Home column has a tooltip from `dashboard/help_text.py` (a test fails if a widget lacks one); permanent captions are gone; the Run Backtest execution settings (fees, delays, queue) sit in a collapsed expander; navigation is grouped into Lab and Learn.
- New `Strategies` page: tabs for the naive quoter (built), Avellaneda–Stoikov, GLFT and alpha skew (planned, formulas copied from plan.md Section 5 and 6), the metric formulas, and a glossary. The naive tab has an interactive "Try it" calculator that draws the bid and ask the strategy would place.
- Change in `mmlab/`: the two quoting rules were pulled out of `naive_mm` into `quote_ticks` and `quote_sides` so the calculator calls the strategy's own code (as plain Python through `.py_func`, so the dashboard compiles nothing). Behaviour is unchanged: a full real day (BTCUSDT 2026-10-01, 5 ticks) was re-run and every metric, all 863,992 timeseries rows and all fill rows are identical to the earlier run. Config schema and artifact format are untouched.
- 128 tests pass (30 more). Checked in Edge again: every tab of the Strategies page, the new Run Backtest layout, a hover over a `?` icon, and the Explorer.

## Phase 4 (done 2026-10-17)

Built: exact fills, `mids.parquet` and `markouts.parquet` in every run, markout KPIs and inventory half-life, `mmlab/analytics/markouts.py`, `mmlab/strategies/recording.py` (shared by every strategy), `mmlab/data/latency.py` with the `latency` CLI command, the Compare Runs and Data Explorer pages, the markout chart in the Run Explorer, `scripts/phase4_sensitivity.py`. 196 tests pass. Config version 2.

### Decisions and deviations

- Fill time is the exchange timestamp of the order's fill (`exch_timestamp` of a `FILLED` order; checked against the synthetic trade times, they match exactly). Price and size are `exec_price` and `exec_qty`. Fills are collected inside the Numba loop right before `clear_inactive_orders`, so each filled order is seen once. Orders come out of the hash map in arbitrary order, so the runner sorts fills by (ts, side, price, qty).
- Exact fills must reconcile with the recorder: count, total quantity and total value equal `num_trades`, `trading_volume`, `trading_value` at the last step, or the run raises. This holds on all 24 real runs.
- `partial_fill` is rejected (`ValueError` in `build_backtest`), and the dashboard checkbox is gone: exact fills record one execution per filled order, and recording an order filled in pieces exactly was not built (whether the order object keeps every piece was not checked). The field stays in `ExecConfig` so version 1 configs load.
- Fine mids need time slices finer than a decision step, so `elapse` now advances in `mid_sample_ns` slices (default 10 ms, must divide `step_ns`) and samples the mid after each. The strategy still decides once per `step_ns`. Verified on the full 2026-10-01 day: all 863,992 timeseries rows and every metric are identical to the Phase 2 run; the runtime went from 28 s to 31 s. Mids are stored only when they change (57,389 rows for that day, 0.38 MB).
- The mid at a fill is the last mid sample at or before the fill time (backward as-of join). Mids come from the local feed clock, fills from the exchange clock, so the two differ by the feed latency (median 2 ms). That matters only at horizons of about 20 ms and below.
- `markouts(fills, mids, end_ts)` takes the end of the data explicitly: mids hold only changes, so the last stored mid is not the end of the data. A fill whose horizon passes `end_ts` is left out of that horizon; the 60 s horizon drops 7 of 30,370 fills.
- `spread_captured_bps` now uses the mid at the fill, not the mid of the previous step (5 ticks on 10-01: 0.066, was 0.065).
- Inventory half-life: for every step where |position| grew, the time until |position| first falls to half of that value, within an hour; the median over all such events, with an event that does not halve counting as longer than any other, and n/a when more than half never halve.
- The dashboard reads config versions 1 and 2. A version 1 run shows n/a for the new numbers and a note instead of the markout chart.
- Feed latency is `local_ts - exch_ts` over market events, each event once (rows with the local flag, no snapshot rows), saved per day as `data/latency/<symbol>_<yyyymmdd>.json` by `python -m mmlab.data latency` or the Measure button on the Data Explorer. The range check is 0.1 ms to 10 s and raises outside it.

### Results (BTCUSDT, 100 ms steps, qty 0.001, max position 0.01, maker fee 2 bps, latency 10 ms each way, power_prob 2; all saved as `runs/*_p4_<yyyymmdd>_<case>_*`)

Markout curve of the 5-tick quoter on 2026-10-01 (30,370 fills; mean over fills, bps of the fill price, standard error in brackets). Horizons up to 50 ms were scored from the saved `fills.parquet` and `mids.parquet` after the run; the run itself stores 100 ms to 60 s.

| after the fill | 0 | 10 ms | 20 ms | 50 ms | 100 ms | 500 ms | 1 s | 5 s | 10 s | 60 s |
|---|---|---|---|---|---|---|---|---|---|---|
| markout (bps) | +0.07 | +0.02 | -0.10 | -0.44 | -0.53 | -0.73 | -0.81 | -0.98 | -1.02 | -1.02 |
| standard error | 0.000 | 0.001 | 0.002 | 0.002 | 0.003 | 0.004 | 0.005 | 0.011 | 0.016 | 0.038 |

Per traded dollar at 5 ticks: spread captured +0.07 bps, gross PnL -1.00 bps (-254.00 on 2.55M notional), fee -2.00 bps, net -3.00 bps (-764.19). Gross per dollar equals the 10 s to 60 s markout, as it should with an inventory half-life of 24.3 s.

One factor at a time on 2026-10-01 (5 ticks unless stated):

| case | fills | net | gross | return over trade (bps) | markout 1 s / 10 s (bps) |
|---|---|---|---|---|---|
| half spread 0 / 1 / 2 ticks | 41,957 / 31,811 / 31,253 | -999 / -805 / -792 | -294 / -271 / -267 | -2.83 / -3.01 / -3.02 | -0.65 / -0.83 / -0.83 and -0.85 / -1.05 / -1.05 |
| 5 / 10 / 20 ticks | 30,370 / 29,072 / 26,054 | -764 / -722 / -630 | -254 / -233 / -193 | -3.00 / -2.95 / -2.88 | -0.81 / -0.78 / -0.72 and -1.02 / -1.00 / -0.91 |
| 50 / 100 / 200 ticks | 13,729 / 2,774 / 407 | -321 / -66 / -2.7 | -91 / -19 / +4.2 | -2.79 / -2.83 / -0.78 | -0.63 / -0.66 / -0.47 and -0.76 / -0.69 / -0.34 |
| queue risk_adverse / power 3, at 5 ticks | 30,370 / 30,370 | -764 / -764 | -254 / -254 | -3.00 / -3.00 | -0.81 / -0.81 and -1.02 / -1.02 |
| queue power 2 / power 3 / risk_adverse, at 0 ticks | 41,957 / 41,555 / 37,994 | -999 / -991 / -924 | -294 / -293 / -285 | -2.83 / -2.84 / -2.89 | -0.65 / -0.66 / -0.71 and -0.85 / -0.85 / -0.91 |
| latency 1 / 10 / 50 / 200 ms | 33,702 / 30,370 / 26,347 / 22,270 | -850 / -764 / -662 / -563 | -283 / -254 / -219 / -189 | -3.00 / -3.00 / -2.99 / -3.01 | -0.81 / -0.81 / -0.82 / -0.83 and -1.01 / -1.02 / -1.04 / -1.06 |
| latency 1 / 10 / 50 / 200 ms, at 100 ticks | 2,658 / 2,774 / 3,463 / 5,614 | -66 / -66 / -81 / -144 | -21 / -19 / -23 / -49 | -2.94 / -2.83 / -2.80 / -3.04 | -0.66 / -0.66 / -0.66 / -0.65 and -0.69 / -0.69 / -0.76 / -0.79 |
| maker fee -0.5 bps / 0 / 2 bps | 30,370 each | -126 / -254 / -764 | -254 each | -0.50 / -1.00 / -3.00 | -0.81 each |

The same 5-tick quoter on the other three free days (all four days: markout 10 s is -0.95 to -1.05 bps, 1 s is -0.74 to -0.86):

| day | fills | net | gross | markout 1 s / 10 s (bps) | inventory half-life (s) |
|---|---|---|---|---|---|
| 2026-07-01 | 47,555 | -839.21 | -275.07 | -0.86 / -0.95 | 17.6 |
| 2026-08-01 | 5,738 | -108.67 | -36.67 | -0.74 / -0.95 | 104.1 |
| 2026-09-01 | 27,315 | -655.52 | -230.22 | -0.85 / -1.05 | 31.1 |
| 2026-10-01 | 30,370 | -764.19 | -254.00 | -0.81 / -1.02 | 24.3 |

Feed latency, 2026-10-01 (148.4M events): median 1.95 ms, p90 3.0, p99 19.6, p99.9 54.5, max 3,351 ms. Per file (hour) the median is 1.5 to 2.9 ms, the p99 3 to 44 ms, and the worst event is between 26 ms and 3.35 s; 8 of 24 hours have a worst event over 1 s. This is the delay of the data feed, not of orders. The 10 ms order latency assumed in every run is a separate assumption and is not tested by it.

### Questions from plan.md

1. How much of gross PnL survives fees? None, because gross is already negative: -1.00 bps per traded dollar against a 2 bps fee. At zero fee the day still loses 254 USDT; at a 0.5 bp rebate it loses 126. Break-even at 5 ticks needs a rebate of about 1 bp. The same holds on all four days.
2. At which horizon do markouts turn negative, and by how much? About 10 to 20 ms after the fill (+0.02 at 10 ms, -0.10 at 20 ms), so before the shortest standard horizon. By 50 ms it is -0.44 bps, by 100 ms -0.53, by 1 s -0.81, and it levels off at about -1.0 bps from 5 s on. Close to half of the final damage is done within 50 ms. At 100 ticks the shape is the same with a bigger head start: +0.86 bps at the fill, negative from 50 ms, -0.69 at 10 s.
3. How sensitive is PnL to the queue model? At 1 tick or more it does not matter at all: quotes behind the best price have no queue, so fill counts and every metric are identical across models. At the touch (0 ticks) risk_adverse gives 9.4% fewer fills than power 2 (power 3: 1% fewer), and net PnL changes by up to 7.5% (-999 to -924), but return over trade moves only from -2.83 to -2.89 bps and the sign never changes.
4. At what latency does the strategy go from viable to dead? It is never viable: gross PnL is negative at 1 ms, 10 ms, 50 ms and 200 ms alike. At 5 ticks latency changes how often you are filled (33,702 fills at 1 ms, 22,270 at 200 ms) but not what a fill costs: markout 10 s is -1.01 to -1.06 bps and return over trade -2.99 to -3.01 bps throughout. At 100 ticks more latency means more fills of stale quotes and a worse result at 200 ms (spread captured falls from 0.90 to 0.56 bps).

### Where the naive quoter loses

A resting quote at distance d from the mid is only filled when the market trades through that price, which is when the price is already moving against it. The fill itself pays a little (+0.07 bps at 5 ticks, +0.86 at 100 ticks) and the market then keeps going: within 50 ms the average fill is about 0.4 bps under water and within 10 s about 1 bp. That 1 bp is adverse selection, and it is the same size whether the quote sits 0, 5, 20 or 100 ticks away, so wider quotes lose less only because they are filled less (net -999 at 0 ticks, -764 at 5, -66 at 100). The fee then adds 2 bps on top. The quoter refreshes every 100 ms and its orders take 10 ms, and most of the damage lands in the first 50 ms. The refresh interval was not varied, but order latency from 1 to 200 ms moved the per-fill result by less than 0.05 bps at 5 ticks, which points at the nature of the fills rather than at slow reaction. The quoter looks only at the best bid and ask and the position limit, so nothing in it can lower the adverse selection except being filled less. That is what Phase 5 (inventory skew) and Phase 6 (a short-horizon signal that predicts these moves) have to change.

### Caveats

- Four days, one symbol. The sign is the same on every day; the size is stable (about -1 bps gross per dollar) but four days is not a regime study.
- Horizons of about 20 ms and below sit inside the feed latency range (median 2 ms, p99 20 ms) and the 10 ms mid sampling, so read them as the shape of the curve, not as exact values. From 100 ms up they do not.
- A markout is the value of the fill, not the PnL of the strategy: PnL also includes how inventory is carried and unwound. The two agree here (gross per dollar -1.00 bps against markout -1.02 bps at 10 s) because inventory turns over in about 24 s.
- The 200-tick case has 407 fills and a markout standard error of about 0.1 bps at 10 s; its small gross profit (+4.18) is noise-sized.
- `runs/` holds about 40 folders. Four of them (`p4_20260701_hs5`, `p4_20260801_hs5`, `p4_20260901_hs5`, `p4_20261001_hs0`) exist twice: a first launch of the sensitivity script stopped on a column-name bug after one run each, and the relaunch repeated them with identical results. The older copy of each is safe to delete.

## Known issues

- hftbacktest 2.4.4: `BacktestAsset.constant_latency()` is deprecated; use `constant_order_latency()`. plan.md Section 2.2 still says `constant_latency`; use the new name when building `mmlab/run.py`.
- `Stats.summary()` returns a polars DataFrame and does not print; wrap in `print()` outside notebooks.
- Dashboard: `st.context.theme.type` can be wrong for a moment after first load or a theme change, so chart colours may briefly use the other mode's palette.
- Converter reports `local_timestamp is ahead of exch_timestamp by ~1.27 s` on the Phase 0 sample files and corrects it, which shifts their latency baseline. On 2026-10-01, the only real day measured so far, every feed latency is positive and inside 0.1 ms to 10 s (the measurement raises otherwise), so no correction was needed there.

## Results so far

Naive symmetric post-only quoter, BTCUSDT 2026-10-01 (one day), 100 ms steps, qty 0.001, max position 0.01, maker fee 2 bps, latency 10 ms each way, power-prob queue (power 2). One day, one regime; nothing here is a conclusion about the strategy class.

| half spread (ticks) | net PnL (USDT) | gross PnL | fees | fills | return over trade (bps) | spread captured (bps) |
|---|---|---|---|---|---|---|
| 1 | -805.2 | -270.8 | 534.4 | 31,811 | -3.01 | 0.02 |
| 5 | -764.2 | -254.0 | 510.2 | 30,370 | -3.00 | 0.06 |
| 20 | -630.2 | -192.5 | 437.7 | 26,054 | -2.88 | 0.24 |
| 100 | -66.0 | -19.3 | 46.6 | 2,774 | -2.83 | 1.08 |
| 200 | -2.7 | +4.2 | 6.8 | 407 | -0.78 | 2.24 |

- Phase 4 re-ran these cases with exact fills (see the Phase 4 section): fills, net, gross and fees are unchanged to the cent. Spread captured is now measured against the mid at the fill instead of the mid up to 100 ms earlier, so it is lower at wide quotes (0.86 at 100 ticks and 1.94 at 200, not 1.08 and 2.24). Everything below this point was measured with fills version 1.
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
