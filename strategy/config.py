"""
Strategy configuration and city definitions for the Polymarket weather backtester.
"""

# ============================================================
# STRATEGY PARAMETERS
# ============================================================
STRATEGY_CONFIG = {
    # Model consensus
    "min_consensus_score": 0.90,       # Below this → skip the event
    "strong_consensus_score": 0.97,    # Above this → full position

    # Expected value
    "min_ev_per_dollar": 0.10,         # Minimum 10% EV on deployed capital

    # Sum check (the 96 rule)
    "max_bin_sum_cents": 96.0,         # Sum of selected bin costs must be < this

    # Entry / exit thresholds
    "entry_threshold_cents": 15.0,     # Only buy bins priced below this
    "exit_threshold_cents": 45.0,      # Sell when market corrects above this

    # Position sizing
    "max_position_size_usd": 2.00,     # Max $ per bin position
    "default_shares_per_bin": 10,      # Default shares to buy per bin

    # Portfolio
    "starting_balance_usd": 100.00,    # Initial bankroll
    "max_trades_per_day": 5,           # Cap daily trades

    # Bin generation
    "bin_width_c": 1.0,                # Temperature bin width in °C
    "num_bins_each_side": 4,           # Bins on each side of forecast mean
}


# ============================================================
# CITY DEFINITIONS
# Each city has: name, latitude, longitude, timezone
# ============================================================
CITIES = {
    "NYC": {
        "name": "New York City",
        "lat": 40.7128,
        "lon": -74.0060,
        "timezone": "America/New_York",
    },
    "Chicago": {
        "name": "Chicago",
        "lat": 41.8781,
        "lon": -87.6298,
        "timezone": "America/Chicago",
    },
    "Seoul": {
        "name": "Seoul",
        "lat": 37.5665,
        "lon": 126.9780,
        "timezone": "Asia/Seoul",
    },
    "Tokyo": {
        "name": "Tokyo",
        "lat": 35.6762,
        "lon": 139.6503,
        "timezone": "Asia/Tokyo",
    },
    "London": {
        "name": "London",
        "lat": 51.5074,
        "lon": -0.1278,
        "timezone": "Europe/London",
    },
    "Sydney": {
        "name": "Sydney",
        "lat": -33.8688,
        "lon": 151.2093,
        "timezone": "Australia/Sydney",
    },
}
