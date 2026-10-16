import argparse
import sys
from datetime import date

from mmlab import settings
from mmlab.data import download
from mmlab.data.convert import convert_day, npz_file_name
from mmlab.data.instruments import fetch_symbol_filters
from mmlab.data.manifest import ManifestEntry, upsert_entry
from mmlab.data.validate import (
    DEFAULT_STEP_NS,
    ValidationLimits,
    check_report,
    validate_file,
)


def _day(text: str) -> date:
    return date.fromisoformat(text)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m mmlab.data")
    sub = parser.add_subparsers(dest="command", required=True)

    fetch = sub.add_parser("download", help="download raw Tardis files (to-date is exclusive)")
    fetch.add_argument("--symbol", required=True)
    fetch.add_argument("--from", dest="from_date", type=_day, required=True)
    fetch.add_argument("--to", dest="to_date", type=_day, required=True)

    ingest = sub.add_parser("ingest", help="convert, validate and register one day")
    ingest.add_argument("--symbol", required=True)
    ingest.add_argument("--date", dest="day", type=_day, required=True)
    ingest.add_argument("--tick-size", type=float, help="fetched from Binance when omitted")
    ingest.add_argument("--lot-size", type=float, help="fetched from Binance when omitted")
    ingest.add_argument("--max-memory-gb", type=float, help="refuse to convert above this estimate")
    ingest.add_argument("--step-ms", type=float, default=DEFAULT_STEP_NS / 1e6)
    return parser


def _run_download(args: argparse.Namespace) -> int:
    files = download.download_days(settings.raw_dir(), args.symbol, args.from_date, args.to_date)
    for day_files in files:
        print(f"{day_files.day}: {day_files.trades.name}, {day_files.book.name}")
    return 0


def _run_ingest(args: argparse.Namespace) -> int:
    tick_size, lot_size = args.tick_size, args.lot_size
    if tick_size is None or lot_size is None:
        filters = fetch_symbol_filters(args.symbol)
        tick_size, lot_size = filters.tick_size, filters.lot_size
    print(f"tick size {tick_size}, lot size {lot_size}")

    files = download.expected_files(settings.raw_dir(), args.symbol, args.day)
    output = settings.npz_dir() / npz_file_name(args.symbol, args.day)
    plan = convert_day(files.trades, files.book, output, args.max_memory_gb)
    print(f"converted {plan.buffer_rows} events (estimated peak {plan.estimated_peak_gb:.1f} GB)")

    report = validate_file(output, tick_size, lot_size, int(args.step_ms * 1e6))
    problems = check_report(report, ValidationLimits())
    entry = ManifestEntry(
        path=output.relative_to(settings.data_dir()).as_posix(),
        symbol=args.symbol,
        day=args.day,
        tick_size=tick_size,
        lot_size=lot_size,
        report=report,
        problems=problems,
    )
    upsert_entry(settings.manifest_path(), entry)
    print(report.model_dump_json(indent=2))
    for problem in problems:
        print(f"FAILED: {problem}")
    return 1 if problems else 0


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    handlers = {"download": _run_download, "ingest": _run_ingest}
    return handlers[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
