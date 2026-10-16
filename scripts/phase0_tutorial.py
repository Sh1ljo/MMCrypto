"""Phase 0: hftbacktest Getting Started tutorial (v2.x API), run end-to-end.

Source: https://hftbacktest.readthedocs.io/en/latest/tutorials/Getting%20Started.html
Run phase0_convert.py first.
"""

import numpy as np
from numba import njit

from hftbacktest import (
    GTX,
    LIMIT,
    BacktestAsset,
    HashMapMarketDepthBacktest,
    Recorder,
)
from hftbacktest.stats import LinearAssetRecord

DATA = ["data/npz/btcusdt_20240809.npz"]
SNAPSHOT = "data/npz/btcusdt_20240808_eod.npz"


def build_asset() -> BacktestAsset:
    return (
        BacktestAsset()
        .data(DATA)
        .initial_snapshot(SNAPSHOT)
        .linear_asset(1.0)
        .constant_order_latency(10_000_000, 10_000_000)  # 10 ms entry / response
        .risk_adverse_queue_model()
        .no_partial_fill_exchange()
        .trading_value_fee_model(0.0002, 0.0007)  # maker, taker
        .tick_size(0.1)
        .lot_size(0.001)
    )


@njit
def print_bbo(hbt):
    while hbt.elapse(60 * 1e9) == 0:
        depth = hbt.depth(0)
        print(
            "current_timestamp:", hbt.current_timestamp,
            ", best_bid:", np.round(depth.best_bid, 1),
            ", best_ask:", np.round(depth.best_ask, 1),
        )
    return True


@njit
def submit_order_stats(hbt, recorder):
    buy_order_id = 1
    sell_order_id = 2
    half_spread = 5 * hbt.depth(0).tick_size

    while hbt.elapse(1 * 1e9) == 0:
        hbt.clear_inactive_orders(0)
        depth = hbt.depth(0)
        mid_price = (depth.best_bid + depth.best_ask) / 2.0

        if buy_order_id not in hbt.orders(0):
            price = round((mid_price - half_spread) / depth.tick_size) * depth.tick_size
            hbt.submit_buy_order(0, buy_order_id, price, 1, GTX, LIMIT, False)
        else:
            hbt.cancel(0, buy_order_id, False)

        if sell_order_id not in hbt.orders(0):
            price = round((mid_price + half_spread) / depth.tick_size) * depth.tick_size
            hbt.submit_sell_order(0, sell_order_id, price, 1, GTX, LIMIT, False)
        else:
            hbt.cancel(0, sell_order_id, False)

        recorder.record(hbt)
    return True


def main() -> None:
    # A backtest object cannot be reused: build a fresh one per run.
    print("=== BBO every 60 s ===")
    hbt = HashMapMarketDepthBacktest([build_asset()])
    print_bbo(hbt)
    hbt.close()

    print("=== Quoting at +/-5 ticks, GTX, qty 1 ===")
    hbt = HashMapMarketDepthBacktest([build_asset()])
    recorder = Recorder(hbt.num_assets, 1_000_000)
    submit_order_stats(hbt, recorder.recorder)
    hbt.close()

    rec = recorder.get(0)
    print("recorder fields:", rec.dtype.names)
    print("rows:", len(rec))

    stats = LinearAssetRecord(rec).stats()
    # summary() returns a DataFrame (it only displays itself in a notebook)
    print(stats.summary())


if __name__ == "__main__":
    main()
