import math

import polars as pl

HORIZONS_MS = (100, 500, 1_000, 5_000, 10_000, 30_000, 60_000)
NS_PER_MS = 1_000_000
BPS = 1e4
MARKOUT_COLUMNS = ("horizon_ms", "fills", "avg_markout", "avg_markout_bps", "stderr_bps")
MARKOUT_SCHEMA = {
    "horizon_ms": pl.Int64,
    "fills": pl.Int64,
    "avg_markout": pl.Float64,
    "avg_markout_bps": pl.Float64,
    "stderr_bps": pl.Float64,
}


# per-fill markout in bps at one horizon; fills whose horizon runs past end_ts are left out
def _fill_markouts_bps(
    fills: pl.DataFrame, mids: pl.DataFrame, end_ts: int, horizon_ms: int
) -> pl.DataFrame:
    horizon_ns = horizon_ms * NS_PER_MS
    return (
        fills.with_columns((pl.col("ts") + horizon_ns).alias("ts_horizon"))
        .filter(pl.col("ts_horizon") <= end_ts)
        .sort("ts_horizon")
        .join_asof(
            mids.rename({"ts": "ts_horizon", "mid": "mid_horizon"}),
            on="ts_horizon",
            strategy="backward",
        )
        .drop_nulls("mid_horizon")
        .with_columns((pl.col("side") * (pl.col("mid_horizon") - pl.col("price"))).alias("markout"))
        .with_columns((pl.col("markout") / pl.col("price") * BPS).alias("markout_bps"))
    )


def _curve_row(fills: pl.DataFrame, mids: pl.DataFrame, end_ts: int, horizon_ms: int) -> dict:
    scored = _fill_markouts_bps(fills, mids, end_ts, horizon_ms)
    count = scored.height
    if count == 0:
        return dict.fromkeys(MARKOUT_COLUMNS[2:]) | {"horizon_ms": horizon_ms, "fills": 0}
    # one fill has no spread, so its standard error is undefined
    deviation = scored["markout_bps"].std() if count > 1 else None
    return {
        "horizon_ms": horizon_ms,
        "fills": count,
        "avg_markout": scored["markout"].mean(),
        "avg_markout_bps": scored["markout_bps"].mean(),
        "stderr_bps": None if deviation is None else deviation / math.sqrt(count),
    }


# mids hold only changes, so end_ts says how far they are valid; the last mid holds until then
def markouts(
    fills: pl.DataFrame,
    mids: pl.DataFrame,
    end_ts: int,
    horizons_ms: tuple[int, ...] = HORIZONS_MS,
) -> pl.DataFrame:
    directional = fills.filter(pl.col("side") != 0)
    rows = [_curve_row(directional, mids, end_ts, horizon_ms) for horizon_ms in horizons_ms]
    return pl.DataFrame(rows, schema=MARKOUT_SCHEMA)
