#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request


def _build_payload(args: argparse.Namespace) -> dict:
    payload = {
        "ticker": args.ticker,
        "side": args.side,
        "entry": args.entry,
        "stop": args.stop,
        "tp": args.tp,
    }
    if args.timeframe:
        payload["timeframe"] = args.timeframe
    if args.note:
        payload["note"] = args.note
    return payload


def _send_request(url: str, payload: dict, headers: dict) -> int:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            body = response.read().decode("utf-8")
            print(body)
            return response.status
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        print(body, file=sys.stderr)
        return exc.code
    except urllib.error.URLError as exc:
        print(f"Request failed: {exc}", file=sys.stderr)
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Send an emulated TradingView webhook.")
    parser.add_argument("--url", default="http://127.0.0.1:3000/api/webhook", help="Webhook URL.")
    parser.add_argument("--strategy-key", default="test", help="Strategy key or path segment.")
    parser.add_argument("--ticker", default="BTCUSDT", help="Instrument symbol, e.g. BTCUSDT.")
    parser.add_argument("--side", default="LONG", choices=("LONG", "SHORT"))
    parser.add_argument("--entry", type=float, default=None, help="Entry price (omit for market).")
    parser.add_argument("--stop", type=float, default=90000.0, help="Stop price.")
    parser.add_argument("--tp", type=float, default=92700.0, help="Take profit price.")
    parser.add_argument("--timeframe", default=None, help="Optional timeframe override.")
    parser.add_argument("--note", default=None, help="Optional note.")

    args = parser.parse_args()

    headers = {"Content-Type": "application/json"}

    if args.url.rstrip("/").endswith("/webhook"):
        headers["X-Strategy-Key"] = args.strategy_key
        url = args.url
    else:
        url = f"{args.url.rstrip('/')}/{args.strategy_key}"

    payload = _build_payload(args)
    return _send_request(url, payload, headers)


if __name__ == "__main__":
    raise SystemExit(main())
