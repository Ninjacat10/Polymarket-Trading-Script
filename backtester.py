"""
Backtesting engine for the Polymarket weather trading strategy.

Simulates historical trading by:
1. Fetching real weather forecast data (ECMWF/GFS/ICON) from Open-Meteo
2. Generating simulated Polymarket bin prices
3. Running the strategy pipeline on each day × city
4. Tracking P&L assuming limit order execution
"""

import statistics
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from strategy.config import STRATEGY_CONFIG, CITIES
from strategy.weather_data import fetch_complete_dataset
from strategy.market_simulator import (
    generate_bins,
    simulate_market_prices,
    resolve_bins,
    select_tradeable_bins,
    TemperatureBin,
)
from strategy.signals import generate_trade_signal, TradeSignal


@dataclass
class Trade:
    """Record of a single executed trade."""
    city: str
    date: str
    bins_bought: List[dict]         # Simplified bin info
    total_cost_usd: float           # Amount spent
    payout_usd: float               # Amount received at resolution
    pnl_usd: float                  # Net profit/loss
    consensus_score: float
    ev_per_dollar: float
    verdict: str
    winning_bin: Optional[str]      # Which bin resolved YES
    forecast_mean: float
    actual_temp: float


@dataclass
class BacktestResult:
    """Aggregated backtest results."""
    trades: List[Trade] = field(default_factory=list)
    starting_balance: float = 100.0
    final_balance: float = 100.0
    total_pnl: float = 0.0
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    skipped_events: int = 0
    win_rate: float = 0.0
    roi_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    sharpe_ratio: float = 0.0
    per_city_stats: Dict = field(default_factory=dict)
    balance_history: List[float] = field(default_factory=list)
    date_range: str = ""


def run_backtest(
    start_date: str,
    end_date: str,
    city_keys: Optional[List[str]] = None,
    seed: int = 42,
    verbose: bool = True,
) -> BacktestResult:
    """
    Run the full backtest over a date range and set of cities.

    Args:
        start_date: Start date 'YYYY-MM-DD'
        end_date: End date 'YYYY-MM-DD'
        city_keys: List of city keys from CITIES dict. None = all cities
        seed: Random seed for reproducible market simulation
        verbose: Print progress

    Returns:
        BacktestResult with all trades and statistics
    """
    config = STRATEGY_CONFIG
    rng = np.random.default_rng(seed)

    if city_keys is None:
        city_keys = list(CITIES.keys())

    # Validate cities
    city_keys = [k for k in city_keys if k in CITIES]
    if not city_keys:
        print("❌ No valid cities specified")
        return BacktestResult()

    result = BacktestResult(
        starting_balance=config["starting_balance_usd"],
        final_balance=config["starting_balance_usd"],
        date_range=f"{start_date} to {end_date}",
    )

    balance = config["starting_balance_usd"]
    peak_balance = balance
    max_drawdown = 0.0
    result.balance_history.append(balance)

    daily_returns = []

    # ========================================================
    # FETCH DATA FOR EACH CITY
    # ========================================================
    for city_key in city_keys:
        city = CITIES[city_key]
        if verbose:
            print(f"\n{'='*55}")
            print(f"🌍 {city['name']} ({city_key})")
            print(f"{'='*55}")

        # Fetch all forecast + actual data
        dataset = fetch_complete_dataset(
            lat=city["lat"],
            lon=city["lon"],
            start_date=start_date,
            end_date=end_date,
        )

        if dataset.empty:
            if verbose:
                print(f"  ⚠ No data available for {city_key}")
            continue

        if verbose:
            print(f"  ✓ Got {len(dataset)} days of data")

        # ====================================================
        # PROCESS EACH DAY
        # ====================================================
        trades_today = 0

        for _, row in dataset.iterrows():
            date_str = row["date"].strftime("%Y-%m-%d")

            # Skip if missing critical data
            ecmwf = row.get("ecmwf_max")
            gfs = row.get("gfs_max")
            icon = row.get("icon_max")
            actual = row.get("actual_max")

            available = [t for t in [ecmwf, gfs, icon] if pd.notna(t)]
            if len(available) < 2 or pd.isna(actual):
                result.skipped_events += 1
                continue

            # Fill None for missing models
            ecmwf = ecmwf if pd.notna(ecmwf) else None
            gfs = gfs if pd.notna(gfs) else None
            icon = icon if pd.notna(icon) else None

            # Calculate forecast stats
            forecast_mean = statistics.mean(available)
            forecast_std = statistics.stdev(available) if len(available) > 1 else 0.5

            # ------------------------------------------------
            # Step 1: Generate temperature bins
            # ------------------------------------------------
            bins = generate_bins(
                forecast_mean=forecast_mean,
                forecast_std=forecast_std,
                bin_width=config["bin_width_c"],
                num_bins_each_side=config["num_bins_each_side"],
            )

            # ------------------------------------------------
            # Step 2: Simulate market prices (with mispricing)
            # ------------------------------------------------
            bins = simulate_market_prices(bins, rng=rng)

            # ------------------------------------------------
            # Step 3: Select tradeable bins
            # ------------------------------------------------
            selected = select_tradeable_bins(
                bins,
                entry_threshold=config["entry_threshold_cents"],
                max_bins=3,
            )

            # ------------------------------------------------
            # Step 4: Generate trade signal
            # ------------------------------------------------
            signal = generate_trade_signal(
                city=city_key,
                date=date_str,
                ecmwf_temp=ecmwf,
                gfs_temp=gfs,
                icon_temp=icon,
                selected_bins=selected,
                forecast_mean=forecast_mean,
                forecast_std=forecast_std,
            )

            # ------------------------------------------------
            # Step 5: Execute if ENTER signal
            # ------------------------------------------------
            if not signal.verdict.startswith("ENTER"):
                result.skipped_events += 1
                continue

            if trades_today >= config["max_trades_per_day"]:
                result.skipped_events += 1
                continue

            # Calculate position size
            shares = config["default_shares_per_bin"]
            total_cost_usd = signal.total_cost_cents * shares / 100.0

            # Cap at max position size
            if total_cost_usd > config["max_position_size_usd"] * len(selected):
                shares = int(config["max_position_size_usd"] * len(selected) * 100 / signal.total_cost_cents)
                total_cost_usd = signal.total_cost_cents * shares / 100.0

            # Check if we have enough balance
            if total_cost_usd > balance:
                result.skipped_events += 1
                continue

            # ------------------------------------------------
            # Step 6: Resolve — did we win?
            # ------------------------------------------------
            bins = resolve_bins(bins, actual)
            winner = next((b for b in bins if b.is_winner), None)

            # Check if any of our selected bins won
            selected_labels = {b.label for b in selected}
            payout_usd = 0.0
            winning_bin_label = None

            if winner and winner.label in selected_labels:
                # We bought the winning bin — payout is $1 per share
                payout_usd = shares * 1.0  # $1 per share
                winning_bin_label = winner.label
            elif winner:
                winning_bin_label = f"{winner.label} (not in our spread)"

            pnl = payout_usd - total_cost_usd

            # Update balance
            balance += pnl
            result.balance_history.append(balance)

            # Track drawdown
            if balance > peak_balance:
                peak_balance = balance
            dd = (peak_balance - balance) / peak_balance if peak_balance > 0 else 0
            max_drawdown = max(max_drawdown, dd)

            # Track daily return
            if total_cost_usd > 0:
                daily_returns.append(pnl / total_cost_usd)

            # Record the trade
            trade = Trade(
                city=city_key,
                date=date_str,
                bins_bought=[
                    {"label": b.label, "price": b.market_price, "prob": round(b.true_probability, 3)}
                    for b in selected
                ],
                total_cost_usd=round(total_cost_usd, 4),
                payout_usd=round(payout_usd, 4),
                pnl_usd=round(pnl, 4),
                consensus_score=signal.consensus_score,
                ev_per_dollar=signal.ev_per_dollar,
                verdict=signal.verdict,
                winning_bin=winning_bin_label,
                forecast_mean=round(forecast_mean, 1),
                actual_temp=round(actual, 1),
            )
            result.trades.append(trade)
            trades_today += 1

        # Reset daily counter (simplified — resets per city)
        trades_today = 0

    # ========================================================
    # CALCULATE FINAL STATS
    # ========================================================
    result.final_balance = round(balance, 2)
    result.total_pnl = round(balance - config["starting_balance_usd"], 2)
    result.total_trades = len(result.trades)
    result.winning_trades = sum(1 for t in result.trades if t.pnl_usd > 0)
    result.losing_trades = sum(1 for t in result.trades if t.pnl_usd <= 0)
    result.win_rate = (
        round(result.winning_trades / result.total_trades * 100, 1)
        if result.total_trades > 0 else 0.0
    )
    result.roi_pct = round(result.total_pnl / config["starting_balance_usd"] * 100, 1)
    result.max_drawdown_pct = round(max_drawdown * 100, 1)

    # Sharpe ratio (simplified)
    if daily_returns and len(daily_returns) > 1:
        mean_ret = statistics.mean(daily_returns)
        std_ret = statistics.stdev(daily_returns)
        result.sharpe_ratio = round(mean_ret / std_ret * (252 ** 0.5), 2) if std_ret > 0 else 0.0
    else:
        result.sharpe_ratio = 0.0

    # Per-city stats
    for city_key in city_keys:
        city_trades = [t for t in result.trades if t.city == city_key]
        if city_trades:
            wins = sum(1 for t in city_trades if t.pnl_usd > 0)
            result.per_city_stats[city_key] = {
                "trades": len(city_trades),
                "wins": wins,
                "win_rate": round(wins / len(city_trades) * 100, 1),
                "total_pnl": round(sum(t.pnl_usd for t in city_trades), 2),
            }

    return result
