import argparse
import json
from datetime import date

from mmlab.config import RunConfig
from mmlab.data.manifest import load_manifest
from mmlab.run import run_backtest
from mmlab.settings import manifest_path

BPS = 1e4
NS_PER_MS = 1_000_000
BASE_HALF_SPREAD_TICKS = 5.0
WIDE_HALF_SPREAD_TICKS = 100.0
REBATE_FEE = -0.00005
COLUMNS = (
    "name",
    "fill_count",
    "net_pnl",
    "gross_pnl",
    "fees_paid",
    "return_over_trade_bps",
    "spread_captured_bps",
    "avg_markout_1s_bps",
    "avg_markout_10s_bps",
    "inventory_half_life_s",
)


def case(name: str, half_spread_ticks: float = BASE_HALF_SPREAD_TICKS, **exec_overrides) -> tuple:
    return name, half_spread_ticks, exec_overrides


def latency(milliseconds: float) -> dict:
    nanoseconds = round(milliseconds * NS_PER_MS)
    return {"entry_latency_ns": nanoseconds, "resp_latency_ns": nanoseconds}


# one factor at a time around the naive quoter at 5 ticks, 10 ms each way, power_prob 2, 2 bps fee
def cases() -> list[tuple]:
    half_spreads = [case(f"hs{ticks:g}", ticks) for ticks in (0, 1, 2, 5, 10, 20, 50, 100, 200)]
    queues = [
        case("hs5_risk_adverse", queue_model="risk_adverse"),
        case("hs5_power3", queue_power=3.0),
        case("hs0_risk_adverse", 0, queue_model="risk_adverse"),
        case("hs0_power3", 0, queue_power=3.0),
    ]
    latencies = [
        case(f"hs{ticks:g}_lat{ms:g}ms", ticks, **latency(ms))
        for ticks in (BASE_HALF_SPREAD_TICKS, WIDE_HALF_SPREAD_TICKS)
        for ms in (1, 50, 200)
    ]
    fees = [
        case("hs5_fee_rebate", maker_fee=REBATE_FEE),
        case("hs5_fee_zero", maker_fee=0.0),
    ]
    return half_spreads + queues + latencies + fees


def build_config(entry, name: str, half_spread_ticks: float, exec_overrides: dict) -> RunConfig:
    return RunConfig(
        name=f"p4_{entry.day:%Y%m%d}_{name}",
        strategy="naive",
        data_files=entry.paths,
        initial_snapshot=entry.initial_snapshot,
        tick_size=entry.tick_size,
        lot_size=entry.lot_size,
        params={"half_spread_ticks": half_spread_ticks},
        exec=exec_overrides,
    )


def format_row(name: str, metrics: dict) -> str:
    cells = [name]
    for column in COLUMNS[1:]:
        value = metrics[column]
        cells.append("n/a" if value is None else f"{value:,.2f}")
    return " | ".join(cells)


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 4 sensitivity runs of the naive quoter")
    parser.add_argument("--date", type=date.fromisoformat, required=True)
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--only-base", action="store_true", help="run only the 5-tick base case")
    args = parser.parse_args()

    entries = load_manifest(manifest_path()).files
    entry = next(e for e in entries if (e.symbol, e.day) == (args.symbol, args.date))
    selected = [case("hs5")] if args.only_base else cases()
    print(" | ".join(COLUMNS), flush=True)
    for name, half_spread_ticks, exec_overrides in selected:
        run_dir = run_backtest(build_config(entry, name, half_spread_ticks, exec_overrides))
        metrics = json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))
        print(format_row(f"{args.date:%Y%m%d}_{name}", metrics), flush=True)


if __name__ == "__main__":
    main()
