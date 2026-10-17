import argparse
import sys
from datetime import date

from mmlab import settings
from mmlab.data import download
from mmlab.data.convert import convert_day_chunked
from mmlab.data.instruments import fetch_symbol_filters
from mmlab.data.latency import latency_path, measure_feed_latency, save_latency
from mmlab.data.manifest import ManifestEntry, load_manifest, upsert_entry
from mmlab.data.validate import (
    DEFAULT_STEP_NS,
    ValidationLimits,
    check_report,
    validate_files,
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
    ingest.add_argument("--max-memory-gb", type=float, help="refuse any slice estimated above this")
    ingest.add_argument(
        "--chunk-hours", type=float, default=1.0, help="convert in slices of this many hours"
    )
    ingest.add_argument("--step-ms", type=float, default=DEFAULT_STEP_NS / 1e6)

    latency = sub.add_parser("latency", help="measure the feed latency of one ingested day")
    latency.add_argument("--symbol", required=True)
    latency.add_argument("--date", dest="day", type=_day, required=True)
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
    result = convert_day_chunked(
        files.trades,
        files.book,
        settings.npz_dir(),
        args.symbol,
        args.day,
        args.chunk_hours,
        args.max_memory_gb,
    )
    print(
        f"converted up to {result.buffer_rows} events in {len(result.paths)} files "
        f"(largest slice estimated peak {result.max_chunk_peak_gb:.1f} GB)"
    )

    report = validate_files(result.paths, tick_size, lot_size, int(args.step_ms * 1e6))
    problems = check_report(report, ValidationLimits())
    entry = ManifestEntry(
        paths=[p.relative_to(settings.data_dir()).as_posix() for p in result.paths],
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


def _run_latency(args: argparse.Namespace) -> int:
    manifest = load_manifest(settings.manifest_path())
    entry = next((e for e in manifest.files if (e.symbol, e.day) == (args.symbol, args.day)), None)
    if entry is None:
        print(f"{args.symbol} {args.day} is not in the manifest; run ingest first")
        return 1
    report = measure_feed_latency(entry, settings.data_dir())
    path = latency_path(settings.latency_dir(), args.symbol, args.day)
    save_latency(path, report)
    print(
        f"{report.events} events, feed latency p50 {report.p50_ms:.2f} ms, "
        f"p99 {report.p99_ms:.2f} ms, p99.9 {report.p999_ms:.2f} ms, max {report.max_ms:.1f} ms"
    )
    print(f"saved {path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    handlers = {"download": _run_download, "ingest": _run_ingest, "latency": _run_latency}
    return handlers[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
