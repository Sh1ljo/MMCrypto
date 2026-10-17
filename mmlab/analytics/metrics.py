import math

import numpy as np
import polars as pl
from numba import njit
from pydantic import BaseModel

NS_PER_HOUR = 3_600_000_000_000
NS_PER_S = 1_000_000_000
HOURS_PER_YEAR = 24 * 365
BPS = 1e4
POSITION_EPS = 1e-9
SHORT_MARKOUT_MS = 1_000
LONG_MARKOUT_MS = 10_000
HALF_LIFE_SCAN_NS = NS_PER_HOUR


class Metrics(BaseModel):
    net_pnl: float
    gross_pnl: float
    fees_paid: float
    sharpe_hourly_annualized: float | None
    max_drawdown: float
    traded_notional: float
    traded_qty: float
    return_over_trade_bps: float | None
    fill_count: int
    fills_per_hour: float
    spread_captured_bps: float | None
    mean_abs_position: float
    pct_time_at_limit: float
    pct_time_quoted: float
    duration_h: float
    avg_markout_1s_bps: float | None = None
    avg_markout_10s_bps: float | None = None
    inventory_half_life_s: float | None = None


# last equity value of each UTC hour, the unit Sharpe is computed on
def _hourly_equity(timeseries: pl.DataFrame) -> np.ndarray:
    hourly = (
        timeseries.with_columns((pl.col("ts") // NS_PER_HOUR).alias("hour"))
        .group_by("hour", maintain_order=True)
        .agg(pl.col("equity").last())
    )
    return hourly["equity"].to_numpy()


def _sharpe_hourly_annualized(timeseries: pl.DataFrame) -> float | None:
    equity = _hourly_equity(timeseries)
    pnl = np.diff(np.concatenate([[timeseries["equity"][0]], equity]))
    if len(pnl) < 2:
        return None
    std = float(np.std(pnl, ddof=1))
    if std == 0.0:
        return None
    return float(np.mean(pnl) / std * math.sqrt(HOURS_PER_YEAR))


def _spread_captured_bps(fills: pl.DataFrame) -> float | None:
    directional = fills.filter((pl.col("side") != 0) & pl.col("mid_at_fill").is_not_null())
    if directional.height == 0:
        return None
    captured = (
        directional["side"].cast(pl.Float64)
        * (directional["mid_at_fill"] - directional["price"])
        / directional["mid_at_fill"]
        * BPS
    )
    weights = directional["qty"]
    return float((captured * weights).sum() / weights.sum())


# seconds until |position| halves after each step that grew it; inf if not within scan_ns
@njit
def _halving_times_s(ts, abs_position, scan_ns):
    times = np.full(len(ts), np.inf)
    count = 0
    for i in range(1, len(ts)):
        if abs_position[i] <= abs_position[i - 1] + POSITION_EPS:
            continue
        count += 1
        target = abs_position[i] / 2.0
        j = i + 1
        while j < len(ts) and ts[j] - ts[i] <= scan_ns:
            if abs_position[j] <= target:
                times[count - 1] = (ts[j] - ts[i]) / NS_PER_S
                break
            j += 1
    return times[:count]


# median halving time; an event that never halves counts as longer than any other
def _inventory_half_life_s(timeseries: pl.DataFrame) -> float | None:
    times = _halving_times_s(
        timeseries["ts"].to_numpy(), timeseries["position"].abs().to_numpy(), HALF_LIFE_SCAN_NS
    )
    if len(times) == 0:
        return None
    median = float(np.median(times))
    return None if math.isinf(median) else median


def _markout_bps(curve: pl.DataFrame, horizon_ms: int) -> float | None:
    return curve.filter(pl.col("horizon_ms") == horizon_ms)["avg_markout_bps"].item()


# summary metrics from a timeseries (plan.md Section 2.5 columns), its fills and its markout curve
def compute_metrics(
    timeseries: pl.DataFrame, fills: pl.DataFrame, max_position: float, markout_curve: pl.DataFrame
) -> Metrics:
    equity = timeseries["equity"]
    fees_paid = float(timeseries["fee"][-1])
    net_pnl = float(equity[-1] - equity[0])
    duration_h = float(timeseries["ts"][-1] - timeseries["ts"][0]) / NS_PER_HOUR
    traded_qty = float(fills["qty"].sum())
    traded_notional = float((fills["price"] * fills["qty"]).sum())
    fill_count = int(timeseries["num_trades"][-1])
    drawdown = equity.cum_max() - equity
    position = timeseries["position"].abs()
    is_quoted = timeseries["bid_quote"].is_not_null() & timeseries["ask_quote"].is_not_null()
    return Metrics(
        net_pnl=net_pnl,
        gross_pnl=net_pnl + fees_paid,
        fees_paid=fees_paid,
        sharpe_hourly_annualized=_sharpe_hourly_annualized(timeseries),
        max_drawdown=float(drawdown.max()),
        traded_notional=traded_notional,
        traded_qty=traded_qty,
        return_over_trade_bps=net_pnl / traded_notional * BPS if traded_notional > 0 else None,
        fill_count=fill_count,
        fills_per_hour=fill_count / duration_h if duration_h > 0 else 0.0,
        spread_captured_bps=_spread_captured_bps(fills),
        mean_abs_position=float(position.mean()),
        pct_time_at_limit=float((position >= max_position - POSITION_EPS).mean() * 100),
        pct_time_quoted=float(is_quoted.mean() * 100),
        duration_h=duration_h,
        avg_markout_1s_bps=_markout_bps(markout_curve, SHORT_MARKOUT_MS),
        avg_markout_10s_bps=_markout_bps(markout_curve, LONG_MARKOUT_MS),
        inventory_half_life_s=_inventory_half_life_s(timeseries),
    )
