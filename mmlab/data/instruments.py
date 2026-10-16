import json
import urllib.request
from typing import NamedTuple

BINANCE_EXCHANGE_INFO_URL = "https://fapi.binance.com/fapi/v1/exchangeInfo"
REQUEST_TIMEOUT_S = 30


class SymbolFilters(NamedTuple):
    tick_size: float
    lot_size: float


# read tick and lot size for one symbol from a Binance exchangeInfo payload
def parse_symbol_filters(payload: dict, symbol: str) -> SymbolFilters:
    for entry in payload.get("symbols", []):
        if entry.get("symbol") != symbol:
            continue
        filters = {f["filterType"]: f for f in entry.get("filters", [])}
        try:
            tick = float(filters["PRICE_FILTER"]["tickSize"])
            lot = float(filters["LOT_SIZE"]["stepSize"])
        except KeyError as exc:
            raise ValueError(f"{symbol} is missing filter field {exc}") from exc
        return SymbolFilters(tick_size=tick, lot_size=lot)
    raise ValueError(f"symbol {symbol} not found in exchange info")


# public Binance endpoint, no API key needed
def fetch_symbol_filters(symbol: str) -> SymbolFilters:
    with urllib.request.urlopen(BINANCE_EXCHANGE_INFO_URL, timeout=REQUEST_TIMEOUT_S) as response:
        payload = json.load(response)
    return parse_symbol_filters(payload, symbol)
