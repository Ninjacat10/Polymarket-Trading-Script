"""
Polymarket Weather Trading Strategy — Backtest Runner

Usage:
    python main.py
    python main.py --start 2025-01-01 --end 2025-03-01
    python main.py --cities NYC,Seoul,Tokyo
    python main.py --start 2025-01-01 --end 2025-03-01 --cities NYC,Seoul --seed 123
"""

import argparse
import sys
from datetime import datetime, timedelta

from backtester import run_backtest
from report import print_report
from strategy.config import CITIES


def main():
    parser = argparse.ArgumentParser(
        description="Polymarket Weather Trading Strategy Backtester"
    )
    parser.add_argument(
        "--start",
        type=str,
        default=None,
        help="Start date (YYYY-MM-DD). Default: 60 days ago",
    )
    parser.add_argument(
        "--end",
        type=str,
        default=None,
        help="End date (YYYY-MM-DD). Default: 7 days ago",
    )
    parser.add_argument(
        "--cities",
        type=str,
        default=None,
        help=f"Comma-separated city keys. Available: {', '.join(CITIES.keys())}",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for market price simulation (default: 42)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress progress output",
    )

    args = parser.parse_args()

    # Default dates: last 60 days (ending 7 days ago to ensure data availability)
    if args.end is None:
        end_dt = datetime.now() - timedelta(days=7)
        args.end = end_dt.strftime("%Y-%m-%d")

    if args.start is None:
        start_dt = datetime.strptime(args.end, "%Y-%m-%d") - timedelta(days=60)
        args.start = start_dt.strftime("%Y-%m-%d")

    # Parse cities
    city_keys = None
    if args.cities:
        city_keys = [c.strip() for c in args.cities.split(",")]
        invalid = [c for c in city_keys if c not in CITIES]
        if invalid:
            print(f"⚠ Unknown cities: {', '.join(invalid)}")
            print(f"  Available: {', '.join(CITIES.keys())}")
            sys.exit(1)

    # Banner
    print()
    print("╔═══════════════════════════════════════════════════════════════╗")
    print("║  🌡️  POLYMARKET WEATHER EDGE — BACKTEST ENGINE  🌡️          ║")
    print("║                                                               ║")
    print("║  Strategy: Multi-bin EV + Model Consensus + Sum Check         ║")
    print("║  Based on ECMWF / GFS / ICON forecast consensus              ║")
    print("╚═══════════════════════════════════════════════════════════════╝")
    print()
    print(f"  📅 Period:  {args.start} → {args.end}")
    print(f"  🌍 Cities:  {', '.join(city_keys) if city_keys else 'All (' + ', '.join(CITIES.keys()) + ')'}")
    print(f"  🎲 Seed:    {args.seed}")
    print()

    # Run backtest
    result = run_backtest(
        start_date=args.start,
        end_date=args.end,
        city_keys=city_keys,
        seed=args.seed,
        verbose=not args.quiet,
    )

    # Print report
    print_report(result)


if __name__ == "__main__":
    main()
