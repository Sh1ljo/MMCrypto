from pathlib import Path

import numpy as np
from hftbacktest import (
    BUY_EVENT,
    DEPTH_SNAPSHOT_EVENT,
    EXCH_EVENT,
    LOCAL_EVENT,
    SELL_EVENT,
    TRADE_EVENT,
)
from hftbacktest.types import event_dtype

from mmlab.config import RunConfig

NS_PER_S = 1_000_000_000
T0_NS = 1_788_220_800 * NS_PER_S
BID_PRICE = 100.0
ASK_PRICE = 100.1
BOOK_QTY = 1.0
TRADE_QTY = 5.0
BOTH_FEEDS = EXCH_EVENT | LOCAL_EVENT
SELL_PHASE_SECONDS = 30


def _event(flags: int, second: float, price: float, qty: float) -> tuple:
    ts = T0_NS + int(second * NS_PER_S)
    return (flags | BOTH_FEEDS, ts, ts, price, qty, 0, 0, 0.0)


# a static book, sellers hitting the bid for the first 30 s and buyers lifting the ask afterwards
def write_synthetic_day(path: Path, seconds: int = 60) -> Path:
    rows = [
        _event(DEPTH_SNAPSHOT_EVENT | BUY_EVENT, 0, BID_PRICE, BOOK_QTY),
        _event(DEPTH_SNAPSHOT_EVENT | SELL_EVENT, 0, ASK_PRICE, BOOK_QTY),
    ]
    for second in range(1, seconds + 1):
        is_sell_phase = second <= SELL_PHASE_SECONDS
        flags = TRADE_EVENT | (SELL_EVENT if is_sell_phase else BUY_EVENT)
        price = BID_PRICE if is_sell_phase else ASK_PRICE
        rows.append(_event(flags, second, price, TRADE_QTY))
    np.savez_compressed(path, data=np.array(rows, dtype=event_dtype))
    return path


def synthetic_config(data_file: Path, **overrides) -> RunConfig:
    fields = {
        "name": "synthetic",
        "strategy": "naive",
        "data_files": [str(data_file)],
        "tick_size": 0.1,
        "lot_size": 0.001,
        "params": {"half_spread_ticks": 0},
        "exec": {"queue_model": "risk_adverse"},
    }
    return RunConfig.model_validate(fields | overrides)
