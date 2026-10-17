import math

import numpy as np
import polars as pl
from pydantic import BaseModel

NS_PER_HOUR = 3_600_000_000_000
HOURS_PER_YEAR = 24 * 365
BPS = 1e4
POSITION_EPS = 1e-9


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


# fills inferred from changes in the recorder state between consecutive steps (fills version 1)
def infer_fills(raw: pl.DataFrame) -> pl.DataFrame:
    stepped = raw.with_columns(
        pl.col("trading_volume").diff().alias("qty"),
        pl.col("trading_value").diff().alias("value"),
        pl.col("position").diff().alias("position_change"),
        pl.col("mid").shift(1).alias("mid_at_fill"),
    )
    return stepped.filter(pl.col("qty") > 0).select(
        pl.col("ts"),
        pl.col("position_change").sign().cast(pl.Int8).alias("side"),
        (pl.col("value") / pl.col("qty")).alias("price"),
        pl.col("qty"),
        pl.col("mid_at_fill"),
    )


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


# summary metrics from a timeseries (plan.md Section 2.5 columns) and its fills
def compute_metrics(timeseries: pl.DataFrame, fills: pl.DataFrame, max_position: float) -> Metrics:
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
    )
