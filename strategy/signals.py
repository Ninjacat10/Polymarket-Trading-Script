"""
Trading signal generation — the core strategy logic.

Implements the four key checks from the article:
1. Model Consensus Score (ECMWF/GFS/ICON agreement)
2. Multi-Bin Expected Value calculation
3. Sum Check (the <96¢ rule)
4. Limit Order Alpha (slippage savings)
"""

import statistics
from typing import List, Tuple, Optional
from dataclasses import dataclass

from strategy.market_simulator import TemperatureBin
from strategy.config import STRATEGY_CONFIG


@dataclass
class TradeSignal:
    """Complete trade analysis result."""
    city: str
    date: str
    consensus_score: float
    consensus_signal: str       # STRONG / MODERATE / WEAK
    selected_bins: List[TemperatureBin]
    total_cost_cents: float     # Sum of market prices for selected bins
    total_ev_cents: float       # Expected value in cents
    ev_per_dollar: float        # EV as fraction of cost
    sum_check_passed: bool
    limit_alpha_cents: float    # Savings from limit orders
    verdict: str                # ENTER / HOLD / SKIP
    forecast_mean: float
    forecast_std: float


# ============================================================
# FORMULA 1: MODEL CONSENSUS
# ============================================================
def model_consensus(ecmwf: float, gfs: float, icon: float) -> Tuple[float, str]:
    """
    Calculate consensus score across three weather models.

    Consensus = 1 - (σ / |T̄|)

    Where σ = std dev of model outputs, T̄ = mean temperature.

    Returns:
        (score, signal_label) where score ∈ [0, 1]
    """
    temps = [t for t in [ecmwf, gfs, icon] if t is not None]

    if len(temps) < 2:
        return 0.0, "INSUFFICIENT_DATA"

    mean_t = statistics.mean(temps)
    std_t = statistics.stdev(temps) if len(temps) > 1 else 0.0

    if abs(mean_t) < 0.01:
        # Near zero — use absolute threshold instead
        score = max(0.0, 1.0 - std_t / 5.0)
    else:
        score = max(0.0, 1.0 - (std_t / abs(mean_t)))

    score = min(score, 1.0)

    if score >= STRATEGY_CONFIG["strong_consensus_score"]:
        signal = "STRONG"
    elif score >= STRATEGY_CONFIG["min_consensus_score"]:
        signal = "MODERATE"
    else:
        signal = "WEAK"

    return round(score, 4), signal


# ============================================================
# FORMULA 2: MULTI-BIN EXPECTED VALUE
# ============================================================
def calculate_ev(bins: List[TemperatureBin]) -> Tuple[float, float]:
    """
    Calculate expected value across selected bins.

    EV_i = P_i × (100 - C_i) - (1 - P_i) × C_i

    Where P_i = model probability, C_i = cost in cents.

    Returns:
        (total_ev_cents, ev_per_dollar)
    """
    if not bins:
        return 0.0, 0.0

    total_ev = 0.0
    total_cost = 0.0

    for b in bins:
        cost = b.market_price
        prob = b.true_probability

        # EV for this bin
        ev_i = prob * (100 - cost) - (1 - prob) * cost
        total_ev += ev_i
        total_cost += cost

    ev_per_dollar = total_ev / total_cost if total_cost > 0 else 0.0

    return round(total_ev, 2), round(ev_per_dollar, 4)


# ============================================================
# FORMULA 3: SUM CHECK (THE 96 RULE)
# ============================================================
def passes_sum_check(
    bins: List[TemperatureBin],
    threshold: float = None,
) -> Tuple[bool, float]:
    """
    Check if the sum of selected bin prices is below the threshold.

    If you buy all selected bins and one of them must hit,
    you need the total cost < 96¢ to have structural edge.

    Returns:
        (passes, total_cost_cents)
    """
    if threshold is None:
        threshold = STRATEGY_CONFIG["max_bin_sum_cents"]

    total = sum(b.market_price for b in bins)
    return total < threshold, round(total, 2)


# ============================================================
# FORMULA 4: LIMIT ORDER ALPHA
# ============================================================
def limit_order_alpha(bins: List[TemperatureBin]) -> float:
    """
    Calculate how much edge is saved by using limit orders at fair price
    instead of buying at market ask.

    Returns:
        Total slippage in cents across all bins
    """
    total = 0.0
    for b in bins:
        slippage = b.market_price - b.fair_price
        if slippage > 0:
            total += slippage

    return round(total, 2)


# ============================================================
# MAIN SIGNAL GENERATOR
# ============================================================
def generate_trade_signal(
    city: str,
    date: str,
    ecmwf_temp: float,
    gfs_temp: float,
    icon_temp: float,
    selected_bins: List[TemperatureBin],
    forecast_mean: float,
    forecast_std: float,
) -> TradeSignal:
    """
    Full strategy pipeline: consensus → EV → sum check → verdict.

    Args:
        city: City name
        date: Date string
        ecmwf_temp, gfs_temp, icon_temp: Model forecasts
        selected_bins: Pre-selected tradeable bins
        forecast_mean: Mean of model forecasts
        forecast_std: Std dev of model forecasts

    Returns:
        TradeSignal with final verdict
    """
    config = STRATEGY_CONFIG

    # Step 1: Consensus
    consensus, consensus_signal = model_consensus(ecmwf_temp, gfs_temp, icon_temp)

    # Step 2: EV
    total_ev, ev_per_dollar = calculate_ev(selected_bins)

    # Step 3: Sum check
    sum_ok, total_cost = passes_sum_check(selected_bins)

    # Step 4: Limit alpha
    alpha = limit_order_alpha(selected_bins)

    # Step 5: Verdict
    if not selected_bins:
        verdict = "SKIP — no tradeable bins found"
    elif consensus_signal == "WEAK":
        verdict = "SKIP — weak model consensus"
    elif consensus_signal == "INSUFFICIENT_DATA":
        verdict = "SKIP — insufficient forecast data"
    elif not sum_ok:
        verdict = "SKIP — bin sum too high, no structural edge"
    elif ev_per_dollar < config["min_ev_per_dollar"]:
        verdict = "SKIP — EV too thin"
    elif consensus_signal == "MODERATE":
        verdict = "ENTER — moderate consensus, reduced size"
    else:
        verdict = "ENTER — strong signal, set limit orders"

    return TradeSignal(
        city=city,
        date=date,
        consensus_score=consensus,
        consensus_signal=consensus_signal,
        selected_bins=selected_bins,
        total_cost_cents=total_cost,
        total_ev_cents=total_ev,
        ev_per_dollar=ev_per_dollar,
        sum_check_passed=sum_ok,
        limit_alpha_cents=alpha,
        verdict=verdict,
        forecast_mean=forecast_mean,
        forecast_std=forecast_std,
    )
