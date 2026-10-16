from pathlib import Path

from hftbacktest.data.utils import binancefutures
from hftbacktest.data.utils.snapshot import create_last_snapshot

RAW = Path("data/raw")
NPZ = Path("data/npz")
TICK_SIZE = 0.1
LOT_SIZE = 0.001


# convert both sample days to npz; the 08-08 end-of-day snapshot seeds 08-09
def main() -> None:
    NPZ.mkdir(parents=True, exist_ok=True)

    for day in ("20240808", "20240809"):
        out = NPZ / f"btcusdt_{day}.npz"
        print(f"converting {day} -> {out}")
        binancefutures.convert(str(RAW / f"btcusdt_{day}.gz"), output_filename=str(out))

    eod = NPZ / "btcusdt_20240808_eod.npz"
    print(f"creating end-of-day snapshot -> {eod}")
    create_last_snapshot(
        [str(NPZ / "btcusdt_20240808.npz")],
        tick_size=TICK_SIZE,
        lot_size=LOT_SIZE,
        output_snapshot_filename=str(eod),
    )


if __name__ == "__main__":
    main()
