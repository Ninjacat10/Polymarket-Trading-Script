"""
Simulate realistic Polymarket temperature bin prices.

Since we can't reliably access historical Polymarket weather market data,
this module generates synthetic but realistic market prices based on
patterns described by successful weather traders:

- Temperature events have discrete 1°C bins (e.g., "11-12°C", "12-13°C")
- Markets are often mispriced by retail participants
- Correct bins are frequently underpriced (10-30¢ when models say 50-70%)
- The sum of all bin prices often reveals structural edge when < 96¢
"""

import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class TemperatureBin:
    """Represents a single temperature outcome bin on Polymarket."""
    label: str              # e.g., "12-13°C"
    lower_bound: float      # Lower edge of bin (°C)
    upper_bound: float      # Upper edge of bin (°C)
    true_probability: float # Our model-estimated P(this bin resolves YES)
    market_price: float     # Simulated market price in cents (0-100)
    fair_price: float       # Model-implied fair price in cents

    @property
    def is_winner(self) -> bool:
        """Will be set after resolution."""
        return self._is_winner if hasattr(self, '_is_winner') else False

    @is_winner.setter
    def is_winner(self, value: bool):
        self._is_winner = value


def _normal_prob(x: float, mean: float, std: float) -> float:
    """Simple normal PDF (unnormalized is fine, we normalize after)."""
    return np.exp(-0.5 * ((x - mean) / std) ** 2)


def generate_bins(
    forecast_mean: float,
    forecast_std: float,
    bin_width: float = 1.0,
    num_bins_each_side: int = 4,
) -> List[TemperatureBin]:
    """
    Generate temperature bins centered around the forecast mean.

    Args:
        forecast_mean: Mean of model forecasts (°C)
        forecast_std: Std dev across models (measure of uncertainty)
        bin_width: Width of each bin in °C
        num_bins_each_side: Bins on each side of center

    Returns:
        List of TemperatureBin objects with true probabilities assigned
    """
    # Center bin starts at floor of forecast_mean
    center = np.floor(forecast_mean)

    bins = []
    raw_probs = []

    for i in range(-num_bins_each_side, num_bins_each_side + 1):
        lower = center + i * bin_width
        upper = lower + bin_width
        mid = (lower + upper) / 2

        # True probability based on normal distribution around forecast
        # Use forecast_std but add a minimum of 1.5°C to avoid overconfidence
        effective_std = max(forecast_std, 1.5)
        prob = _normal_prob(mid, forecast_mean, effective_std)
        raw_probs.append(prob)

        bins.append(TemperatureBin(
            label=f"{lower:.0f}-{upper:.0f}°C",
            lower_bound=lower,
            upper_bound=upper,
            true_probability=0.0,  # Will be set after normalization
            market_price=0.0,      # Will be set by simulate_prices
            fair_price=0.0,
        ))

    # Normalize probabilities to sum to ~1.0
    total = sum(raw_probs)
    for i, bin_obj in enumerate(bins):
        bin_obj.true_probability = raw_probs[i] / total if total > 0 else 0.0
        bin_obj.fair_price = round(bin_obj.true_probability * 100, 1)

    return bins


def simulate_market_prices(
    bins: List[TemperatureBin],
    noise_factor: float = 0.50,
    mispricing_bias: float = 0.75,
    rng: Optional[np.random.Generator] = None,
) -> List[TemperatureBin]:
    """
    Simulate realistic market prices for temperature bins.
    """
    if rng is None:
        rng = np.random.default_rng()

    for bin_obj in bins:
        fair = bin_obj.true_probability * 100  # Convert to cents

        # Simulate market mispricing:
        # 1. Add random noise
        noise = rng.normal(0, noise_factor * max(fair, 5.0))

        # 2. Apply systematic bias: retail underprices likely outcomes
        if bin_obj.true_probability > 0.15:
            # High-prob bins get significantly underpriced
            bias = -fair * mispricing_bias * rng.uniform(0.2, 0.6)
        else:
            # Low-prob bins get overpriced
            bias = fair * rng.uniform(0.1, 0.5)

        market_price = fair + noise + bias
        bin_obj.market_price = round(max(0.5, min(98.0, market_price)), 1)

    return bins


def resolve_bins(
    bins: List[TemperatureBin],
    actual_temperature: float,
) -> List[TemperatureBin]:
    """Mark which bin won based on actual observed temperature."""
    for bin_obj in bins:
        bin_obj.is_winner = (
            bin_obj.lower_bound <= actual_temperature < bin_obj.upper_bound
        )
    return bins


def select_tradeable_bins(
    bins: List[TemperatureBin],
    entry_threshold: float = 40.0,
    min_probability: float = 0.05,
    max_bins: int = 3,
) -> List[TemperatureBin]:
    """
    Select the best bins to trade.
    """
    # 1. Look for bins below our value threshold
    candidates = [
        b for b in bins
        if b.market_price <= entry_threshold and b.true_probability >= min_probability
    ]

    if candidates:
        # Sort candidates by edge (EV)
        candidates.sort(
            key=lambda b: b.true_probability * 100 - b.market_price,
            reverse=True,
        )
    else:
        # 2. Fallback: No cheap bins? Pick the most likely ones (highest probability)
        # This ensures we don't skip events just because the simulator is "efficient"
        candidates = [b for b in bins if b.true_probability >= min_probability]
        candidates.sort(key=lambda b: b.true_probability, reverse=True)

    return candidates[:max_bins]
