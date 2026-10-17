from datetime import date

from mmlab.data.manifest import ManifestEntry
from mmlab.data.validate import BookStats, EventStats, ValidationReport


def validation_report() -> ValidationReport:
    events = EventStats(
        event_count=10,
        trade_count=2,
        start_ts_ns=0,
        end_ts_ns=60,
        duration_s=60.0,
        max_gap_s=1.0,
        trades_per_min_mean=2.0,
        trades_per_min_min=2,
        trades_per_min_max=2,
    )
    book = BookStats(
        step_ms=10.0,
        samples=100,
        broken_samples=0,
        spread_ticks_min=1.0,
        spread_ticks_mean=1.0,
        spread_ticks_p50=1.0,
        spread_ticks_p95=1.0,
        spread_ticks_p99=1.0,
        spread_ticks_max=1.0,
    )
    return ValidationReport(events=events, book=book)


def manifest_entry(paths: list[str], day: date, problems: list[str] | None = None) -> ManifestEntry:
    return ManifestEntry(
        paths=paths,
        symbol="BTCUSDT",
        day=day,
        tick_size=0.1,
        lot_size=0.001,
        report=validation_report(),
        problems=problems or [],
    )
