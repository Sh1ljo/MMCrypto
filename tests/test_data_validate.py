from pathlib import Path

import numpy as np
import pytest
from conftest import LOT_SIZE, TICK_SIZE, make_day
from hftbacktest.types import BUY_EVENT, DEPTH_EVENT, TRADE_EVENT, event_dtype

from mmlab.data.convert import convert_day
from mmlab.data.validate import ValidationLimits, check_report, event_stats, validate_file

STEP_NS = 100_000_000
NS = 1_000_000_000


def _validate(raw_dir: Path, tmp_path: Path, **scenario):
    files = make_day(raw_dir, **scenario)
    output = tmp_path / "day.npz"
    convert_day(files.trades, files.book, output)
    return validate_file(output, TICK_SIZE, LOT_SIZE, STEP_NS)


def test_clean_day_passes(raw_dir: Path, tmp_path: Path):
    report = _validate(raw_dir, tmp_path, seconds=60)

    assert check_report(report, ValidationLimits()) == []
    assert report.events.trade_count == 12
    assert report.events.max_gap_s < 2.0
    assert report.book.broken_samples == 0
    assert report.book.spread_ticks_min == 1.0
    assert report.book.spread_ticks_max == 1.0


def test_large_gap_is_reported(raw_dir: Path, tmp_path: Path):
    report = _validate(raw_dir, tmp_path, seconds=150, gap=(10, 100))

    problems = check_report(report, ValidationLimits())
    assert report.events.max_gap_s > 60
    assert any("largest gap" in problem for problem in problems)


def test_wiped_book_side_is_reported(raw_dir: Path, tmp_path: Path):
    report = _validate(raw_dir, tmp_path, seconds=60, cross_at=30)

    problems = check_report(report, ValidationLimits())
    assert report.book.broken_samples > 0
    assert any("broken" in problem for problem in problems)


def _events(rows: list[tuple[int, int]]) -> np.ndarray:
    events = np.zeros(len(rows), dtype=event_dtype)
    for index, (ev, local_ts) in enumerate(rows):
        events[index]["ev"] = ev
        events[index]["local_ts"] = local_ts
        events[index]["exch_ts"] = local_ts
    return events


def test_event_stats_trade_rate_per_minute():
    trade = TRADE_EVENT | BUY_EVENT
    events = _events(
        [
            (DEPTH_EVENT, 0),
            (trade, 10 * NS),
            (trade, 20 * NS),
            (trade, 70 * NS),
            (DEPTH_EVENT, 185 * NS),
        ]
    )

    stats = event_stats(events)

    assert stats.event_count == 5
    assert stats.trade_count == 3
    assert stats.duration_s == 185
    assert stats.max_gap_s == 115
    assert stats.trades_per_min_min == 0
    assert stats.trades_per_min_max == 2
    assert stats.trades_per_min_mean == pytest.approx(0.75)


def test_event_stats_rejects_empty_array():
    with pytest.raises(ValueError, match="empty"):
        event_stats(np.zeros(0, dtype=event_dtype))
