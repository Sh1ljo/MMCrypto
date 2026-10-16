# CONTEXT

Running notes for AI sessions. Update at the end of every session.

## Current phase

Phase 0 — environment, repo, skeleton and tutorial done; reading (Section 4, resources 1-3) and the concept write-up below remain. Phase 1 — code and tests written and run on one real Tardis day (2026-10-01, passed); more days still to download.

## Decisions

- Project lives in the repo root (no nested `mm-lab/` folder); package name `mm-lab`, import package `mmlab`.
- Python 3.12 pinned via `.python-version` (uv otherwise picks 3.15, which has no wheels for several dependencies).
- Native Windows, no WSL. Fall back to WSL2 only if hftbacktest/Numba misbehaves.
- Remote: https://github.com/Sh1ljo/MMCrypto.git (branch `main`).
- Agent docs: `AGENTS.md` is the entry point (`CLAUDE.md` imports it), with `docs/CODING.md` (one-line comments above code, no trailing or multi-line comments) and `docs/INFRASTRUCTURE.md` (what exists). Docs must be updated with every change; this is rule 11 in `AGENTS.md`.

## Artifact format

Not yet frozen (Phase 2). See plan.md Section 2.5.

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
- Not yet checked: the chunked output equals a single-file conversion on real data (only on synthetic data); a backtest replay across the 24 files.

## Known issues

- hftbacktest 2.4.4: `BacktestAsset.constant_latency()` is deprecated; use `constant_order_latency()`. plan.md Section 2.2 still says `constant_latency`; use the new name when building `mmlab/run.py`.
- `Stats.summary()` returns a polars DataFrame and does not print; wrap in `print()` outside notebooks.
- Converter reports `local_timestamp is ahead of exch_timestamp by ~1.27 s` on the sample files and corrects it. Relevant to Phase 4 feed-latency analysis (the correction shifts the latency baseline).

## Results so far

None yet.

## Concepts (own words, Phase 0 exit criteria)

- Reservation price:
- Inventory skew:
- Adverse selection:
- Queue position:
