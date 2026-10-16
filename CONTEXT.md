# CONTEXT

Running notes for AI sessions. Update at the end of every session.

## Current phase

Phase 0 — environment, repo, skeleton and hftbacktest Getting Started tutorial done. Remaining: reading (Section 4, resources 1-3) and the concept write-up below.

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
