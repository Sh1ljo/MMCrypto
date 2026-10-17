import numpy as np
from hftbacktest import BUY, FILLED
from numba import njit

NO_BID_TICK = np.iinfo(np.int64).min
NO_ASK_TICK = np.iinfo(np.int64).max
BUY_SIDE = 1
SELL_SIDE = -1
FILL_DTYPE = np.dtype(
    [("ts", np.int64), ("side", np.int8), ("price", np.float64), ("qty", np.float64)]
)
MID_DTYPE = np.dtype([("ts", np.int64), ("mid", np.float64)])


# the book mid at the current time, appended only when it differs from the last stored mid
@njit
def sample_mid(hbt, mids_out, mid_count):
    depth = hbt.depth(0)
    if depth.best_bid_tick == NO_BID_TICK or depth.best_ask_tick == NO_ASK_TICK:
        return mid_count
    mid = (depth.best_bid + depth.best_ask) / 2.0
    if mid_count > 0 and mids_out[mid_count - 1].mid == mid:
        return mid_count
    if mid_count >= len(mids_out):
        raise ValueError("mids buffer is full")
    mids_out[mid_count].ts = hbt.current_timestamp
    mids_out[mid_count].mid = mid
    return mid_count + 1


# advance one step in sample_ns slices, sampling the mid after each; True once the data ends
@njit
def elapse_step(hbt, mids_out, mid_count, samples_per_step, sample_ns):
    for _ in range(samples_per_step):
        if hbt.elapse(sample_ns) != 0:
            return True, mid_count
        mid_count = sample_mid(hbt, mids_out, mid_count)
    return False, mid_count


# store each filled order once, at its exchange time; call before clear_inactive_orders removes them
@njit
def record_fills(hbt, fills_out, fill_count):
    orders = hbt.orders(0)
    it = orders.values()
    while it.has_next():
        order = it.get()
        if order.status != FILLED:
            continue
        if fill_count >= len(fills_out):
            raise ValueError("fills buffer is full")
        fills_out[fill_count].ts = order.exch_timestamp
        fills_out[fill_count].side = BUY_SIDE if order.side == BUY else SELL_SIDE
        fills_out[fill_count].price = order.exec_price
        fills_out[fill_count].qty = order.exec_qty
        fill_count += 1
    return fill_count
