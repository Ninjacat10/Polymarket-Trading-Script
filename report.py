"""
Report generator — pretty-prints backtest results.
"""

from typing import List
from backtester import BacktestResult, Trade
from tabulate import tabulate


def print_report(result: BacktestResult):
    """Print a comprehensive backtest report."""

    print("\n")
    print("╔═══════════════════════════════════════════════════════════════╗")
    print("║       POLYMARKET WEATHER TRADING STRATEGY — BACKTEST        ║")
    print("╚═══════════════════════════════════════════════════════════════╝")
    print()

    # ── Summary ──────────────────────────────────────────────
    print("┌─────────────────────────────────────────────────────────────┐")
    print("│  PORTFOLIO SUMMARY                                         │")
    print("├─────────────────────────────────────────────────────────────┤")

    summary_data = [
        ["Date Range", result.date_range],
        ["Starting Balance", f"${result.starting_balance:.2f}"],
        ["Final Balance", f"${result.final_balance:.2f}"],
        ["Total P&L", f"${result.total_pnl:+.2f}"],
        ["ROI", f"{result.roi_pct:+.1f}%"],
        ["", ""],
        ["Total Trades", str(result.total_trades)],
        ["Winning Trades", f"{result.winning_trades} ✓"],
        ["Losing Trades", f"{result.losing_trades} ✗"],
        ["Win Rate", f"{result.win_rate:.1f}%"],
        ["Skipped Events", str(result.skipped_events)],
        ["", ""],
        ["Max Drawdown", f"{result.max_drawdown_pct:.1f}%"],
        ["Sharpe Ratio (ann.)", f"{result.sharpe_ratio:.2f}"],
    ]

    for label, value in summary_data:
        if label == "":
            print("│                                                             │")
        else:
            print(f"│  {label:<22} {value:>36} │")

    print("└─────────────────────────────────────────────────────────────┘")
    print()

    # ── Per-City Breakdown ───────────────────────────────────
    if result.per_city_stats:
        print("┌─────────────────────────────────────────────────────────────┐")
        print("│  PER-CITY BREAKDOWN                                        │")
        print("├─────────────────────────────────────────────────────────────┤")

        city_table = []
        for city, stats in sorted(result.per_city_stats.items()):
            city_table.append([
                city,
                stats["trades"],
                stats["wins"],
                f"{stats['win_rate']:.1f}%",
                f"${stats['total_pnl']:+.2f}",
            ])

        print(tabulate(
            city_table,
            headers=["City", "Trades", "Wins", "Win Rate", "P&L"],
            tablefmt="simple",
            colalign=("left", "right", "right", "right", "right"),
        ))
        print()
        print("└─────────────────────────────────────────────────────────────┘")
        print()

    # ── Best & Worst Trades ──────────────────────────────────
    if result.trades:
        sorted_trades = sorted(result.trades, key=lambda t: t.pnl_usd, reverse=True)

        print("┌─────────────────────────────────────────────────────────────┐")
        print("│  TOP 5 BEST TRADES                                         │")
        print("├─────────────────────────────────────────────────────────────┤")
        _print_trade_table(sorted_trades[:5])
        print("└─────────────────────────────────────────────────────────────┘")
        print()

        print("┌─────────────────────────────────────────────────────────────┐")
        print("│  TOP 5 WORST TRADES                                        │")
        print("├─────────────────────────────────────────────────────────────┤")
        _print_trade_table(sorted_trades[-5:])
        print("└─────────────────────────────────────────────────────────────┘")
        print()

    # ── Trade Log ────────────────────────────────────────────
    if result.trades:
        print("┌─────────────────────────────────────────────────────────────┐")
        print(f"│  FULL TRADE LOG ({len(result.trades)} trades)              │")
        print("├─────────────────────────────────────────────────────────────┤")
        _print_trade_table(result.trades[:50])  # Cap at 50 for readability
        if len(result.trades) > 50:
            print(f"  ... and {len(result.trades) - 50} more trades")
        print("└─────────────────────────────────────────────────────────────┘")
        print()

    # ── Equity Curve (text-based) ────────────────────────────
    if len(result.balance_history) > 1:
        print("┌─────────────────────────────────────────────────────────────┐")
        print("│  EQUITY CURVE                                               │")
        print("├─────────────────────────────────────────────────────────────┤")
        _print_equity_curve(result.balance_history)
        print("└─────────────────────────────────────────────────────────────┘")
        print()


def _print_trade_table(trades: List[Trade]):
    """Print a table of trades."""
    table = []
    for t in trades:
        bins_str = ", ".join(b["label"] for b in t.bins_bought)
        table.append([
            t.date,
            t.city,
            f"{t.consensus_score:.3f}",
            f"${t.total_cost_usd:.2f}",
            f"${t.pnl_usd:+.2f}",
            t.winning_bin or "—",
            f"{t.forecast_mean:.0f}→{t.actual_temp:.0f}°C",
        ])

    print(tabulate(
        table,
        headers=["Date", "City", "Cons.", "Cost", "P&L", "Winner", "Fcast→Act"],
        tablefmt="simple",
        colalign=("left", "left", "right", "right", "right", "left", "left"),
    ))


def _print_equity_curve(history: List[float], width: int = 55):
    """Print a simple text-based equity curve."""
    if not history:
        return

    min_val = min(history)
    max_val = max(history)
    val_range = max_val - min_val if max_val > min_val else 1.0

    # Downsample if too many points
    if len(history) > width:
        step = len(history) / width
        sampled = [history[int(i * step)] for i in range(width)]
    else:
        sampled = history

    height = 12
    for row in range(height, -1, -1):
        threshold = min_val + (row / height) * val_range
        line = "  "
        if row == height:
            line += f"${max_val:>7.2f} │"
        elif row == 0:
            line += f"${min_val:>7.2f} │"
        elif row == height // 2:
            mid = (max_val + min_val) / 2
            line += f"${mid:>7.2f} │"
        else:
            line += "         │"

        for val in sampled:
            if val >= threshold:
                line += "█"
            else:
                line += " "

        print(line)

    print(f"           └{'─' * len(sampled)}")
    print(f"            Trade # 1{' ' * (len(sampled) - 5)}→ {len(history)}")
