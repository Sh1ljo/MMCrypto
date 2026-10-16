from pathlib import Path

import numpy as np
from hftbacktest import BacktestAsset, HashMapMarketDepthBacktest
from hftbacktest.types import TRADE_EVENT
from numba import njit
from pydantic import BaseModel

NS_PER_S = 1_000_000_000
NS_PER_MIN = 60 * NS_PER_S
EVENT_TYPE_MASK = 0xFF
NO_BID = np.iinfo(np.int64).min
NO_ASK = np.iinfo(np.int64).max
DEFAULT_STEP_NS = 10_000_000
# the replay needs a latency and queue model to build an asset; neither affects the book
PLACEHOLDER_LATENCY_NS = 1


class ValidationLimits(BaseModel):
    min_events: int = 1
    max_gap_s: float = 60.0
    max_broken_fraction: float = 1e-4


class EventStats(BaseModel):
    event_count: int
    trade_count: int
    start_ts_ns: int
    end_ts_ns: int
    duration_s: float
    max_gap_s: float
    trades_per_min_mean: float
    trades_per_min_min: int
    trades_per_min_max: int


class BookStats(BaseModel):
    step_ms: float
    samples: int
    broken_samples: int
    spread_ticks_min: float
    spread_ticks_mean: float
    spread_ticks_p50: float
    spread_ticks_p95: float
    spread_ticks_p99: float
    spread_ticks_max: float


class ValidationReport(BaseModel):
    events: EventStats
    book: BookStats


# count, span, largest gap and trade rate of a converted event array
def event_stats(events: np.ndarray) -> EventStats:
    if len(events) == 0:
        raise ValueError("event array is empty")
    local_ts = np.sort(events["local_ts"])
    start, end = int(local_ts[0]), int(local_ts[-1])
    is_trade = (events["ev"] & EVENT_TYPE_MASK) == TRADE_EVENT
    trade_ts = events["local_ts"][is_trade]
    minutes = (end - start) // NS_PER_MIN + 1
    per_minute = np.bincount((trade_ts - start) // NS_PER_MIN, minlength=minutes)
    return EventStats(
        event_count=len(events),
        trade_count=int(is_trade.sum()),
        start_ts_ns=start,
        end_ts_ns=end,
        duration_s=(end - start) / NS_PER_S,
        max_gap_s=float(np.diff(local_ts).max(initial=0)) / NS_PER_S,
        trades_per_min_mean=float(per_minute.mean()),
        trades_per_min_min=int(per_minute.min()),
        trades_per_min_max=int(per_minute.max()),
    )


# sample the book every step_ns once it has both sides; count empty-side or inverted samples
@njit
def replay_book(hbt, step_ns, spreads_ticks):
    samples = 0
    spread_count = 0
    broken = 0
    initialized = False
    while hbt.elapse(step_ns) == 0:
        depth = hbt.depth(0)
        bid = depth.best_bid_tick
        ask = depth.best_ask_tick
        has_both = bid != NO_BID and ask != NO_ASK
        if not initialized:
            if not has_both:
                continue
            initialized = True
        samples += 1
        if not has_both or bid >= ask:
            broken += 1
        elif spread_count < spreads_ticks.shape[0]:
            spreads_ticks[spread_count] = ask - bid
            spread_count += 1
    return samples, spread_count, broken


def _build_asset(data, tick_size: float, lot_size: float) -> BacktestAsset:
    return (
        BacktestAsset()
        .data(data)
        .linear_asset(1.0)
        .constant_order_latency(PLACEHOLDER_LATENCY_NS, PLACEHOLDER_LATENCY_NS)
        .risk_adverse_queue_model()
        .no_partial_fill_exchange()
        .trading_value_fee_model(0.0, 0.0)
        .tick_size(tick_size)
        .lot_size(lot_size)
    )


# replay an npz file and summarise the sampled book
def book_stats(
    npz: Path,
    tick_size: float,
    lot_size: float,
    start_ts_ns: int,
    end_ts_ns: int,
    step_ns: int = DEFAULT_STEP_NS,
) -> BookStats:
    max_samples = (end_ts_ns - start_ts_ns) // step_ns + 2
    spreads = np.zeros(max_samples, dtype=np.int32)
    hbt = HashMapMarketDepthBacktest([_build_asset([str(npz)], tick_size, lot_size)])
    try:
        samples, spread_count, broken = replay_book(hbt, step_ns, spreads)
    finally:
        hbt.close()
    if spread_count == 0:
        raise ValueError(f"no valid two-sided book samples found in {npz}")
    valid = spreads[:spread_count]
    return BookStats(
        step_ms=step_ns / 1e6,
        samples=samples,
        broken_samples=broken,
        spread_ticks_min=float(valid.min()),
        spread_ticks_mean=float(valid.mean()),
        spread_ticks_p50=float(np.percentile(valid, 50)),
        spread_ticks_p95=float(np.percentile(valid, 95)),
        spread_ticks_p99=float(np.percentile(valid, 99)),
        spread_ticks_max=float(valid.max()),
    )


# validate one converted file: event statistics plus a sampled book replay
def validate_file(
    npz: Path, tick_size: float, lot_size: float, step_ns: int = DEFAULT_STEP_NS
) -> ValidationReport:
    with np.load(npz) as archive:
        events = archive["data"]
    stats = event_stats(events)
    del events
    book = book_stats(npz, tick_size, lot_size, stats.start_ts_ns, stats.end_ts_ns, step_ns)
    return ValidationReport(events=stats, book=book)


# list every limit the report breaks; an empty list means the file passed
def check_report(report: ValidationReport, limits: ValidationLimits) -> list[str]:
    problems = []
    if report.events.event_count < limits.min_events:
        problems.append(f"only {report.events.event_count} events")
    if report.events.max_gap_s > limits.max_gap_s:
        problems.append(f"largest gap {report.events.max_gap_s:.1f}s exceeds {limits.max_gap_s}s")
    broken_fraction = report.book.broken_samples / max(report.book.samples, 1)
    if broken_fraction > limits.max_broken_fraction:
        problems.append(
            f"{report.book.broken_samples} of {report.book.samples} book samples were broken "
            f"({broken_fraction:.2e} exceeds {limits.max_broken_fraction:.0e})"
        )
    return problems
