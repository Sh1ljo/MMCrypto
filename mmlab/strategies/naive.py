import numpy as np
from hftbacktest import BUY, GTX, LIMIT, SELL
from numba import njit
from pydantic import BaseModel, ConfigDict

from mmlab.strategies.recording import NO_ASK_TICK, NO_BID_TICK, elapse_step, record_fills

POSITION_EPS = 1e-9
QUOTE_COLUMNS = 3


class NaiveParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    half_spread_ticks: float = 5.0


# buy ids are even and sell ids odd, so a cancelling buy never collides with a new sell at its tick
@njit
def _order_id(side_is_buy, price_tick):
    return np.uint64(price_tick * 2 + (0 if side_is_buy else 1))


# target ticks of the two quotes: half_spread_ticks from mid, never inside the best bid and ask
@njit
def quote_ticks(best_bid_tick, best_ask_tick, half_spread_ticks):
    mid_tick = (best_bid_tick + best_ask_tick) / 2.0
    bid_tick = np.int64(min(np.floor(mid_tick - half_spread_ticks), best_bid_tick))
    ask_tick = np.int64(max(np.ceil(mid_tick + half_spread_ticks), best_ask_tick))
    return bid_tick, ask_tick


# a side stops quoting when one more fill of order_qty would pass the position limit
@njit
def quote_sides(position, order_qty, max_position):
    can_buy = position + order_qty <= max_position + POSITION_EPS
    can_sell = -position + order_qty <= max_position + POSITION_EPS
    return can_buy, can_sell


# cancel resting quotes that are no longer at the target tick
@njit
def _cancel_stale(hbt, bid_tick, ask_tick):
    orders = hbt.orders(0)
    it = orders.values()
    while it.has_next():
        order = it.get()
        if not order.cancellable:
            continue
        is_stale_bid = order.side == BUY and order.price_tick != bid_tick
        is_stale_ask = order.side == SELL and order.price_tick != ask_tick
        if is_stale_bid or is_stale_ask:
            hbt.cancel(0, order.order_id, False)


# symmetric post-only quotes around mid; quotes_out rows are (mid, bid, ask), NaN if not quoted
@njit
def naive_mm(
    hbt,
    recorder,
    quotes_out,
    fills_out,
    mids_out,
    half_spread_ticks,
    order_qty,
    max_position,
    step_ns,
    sample_ns,
):
    samples_per_step = step_ns // sample_ns
    step = 0
    fill_count = 0
    mid_count = 0
    while True:
        is_over, mid_count = elapse_step(hbt, mids_out, mid_count, samples_per_step, sample_ns)
        if is_over:
            break
        fill_count = record_fills(hbt, fills_out, fill_count)
        hbt.clear_inactive_orders(0)
        depth = hbt.depth(0)
        tick_size = depth.tick_size
        quotes_out[step, 0] = np.nan
        quotes_out[step, 1] = np.nan
        quotes_out[step, 2] = np.nan

        if depth.best_bid_tick == NO_BID_TICK or depth.best_ask_tick == NO_ASK_TICK:
            recorder.record(hbt)
            step += 1
            continue

        position = hbt.position(0)
        mid_tick = (depth.best_bid_tick + depth.best_ask_tick) / 2.0
        bid_tick, ask_tick = quote_ticks(
            depth.best_bid_tick, depth.best_ask_tick, half_spread_ticks
        )
        can_buy, can_sell = quote_sides(position, order_qty, max_position)

        _cancel_stale(
            hbt, bid_tick if can_buy else NO_BID_TICK, ask_tick if can_sell else NO_ASK_TICK
        )

        orders = hbt.orders(0)
        quotes_out[step, 0] = mid_tick * tick_size
        if can_buy:
            quotes_out[step, 1] = bid_tick * tick_size
            bid_id = _order_id(True, bid_tick)
            if bid_id not in orders:
                code = hbt.submit_buy_order(
                    0, bid_id, bid_tick * tick_size, order_qty, GTX, LIMIT, False
                )
                if code != 0:
                    raise ValueError("buy order rejected")
        if can_sell:
            quotes_out[step, 2] = ask_tick * tick_size
            ask_id = _order_id(False, ask_tick)
            if ask_id not in orders:
                code = hbt.submit_sell_order(
                    0, ask_id, ask_tick * tick_size, order_qty, GTX, LIMIT, False
                )
                if code != 0:
                    raise ValueError("sell order rejected")

        recorder.record(hbt)
        step += 1
    return step, fill_count, mid_count
