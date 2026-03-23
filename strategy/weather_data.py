"""
Fetch historical weather forecast data and actual observed temperatures
from the Open-Meteo API.

Data sources:
- Historical Forecast API: archived forecasts from ECMWF IFS, GFS, DWD ICON
- Historical Weather API:  ERA5 reanalysis (actual observed temps)
"""

import requests
import pandas as pd
from datetime import datetime, timedelta
import time


# ============================================================
# API ENDPOINTS
# ============================================================
HISTORICAL_FORECAST_URL = "https://historical-forecast-api.open-meteo.com/v1/forecast"
HISTORICAL_WEATHER_URL = "https://archive-api.open-meteo.com/v1/archive"

# All models use the unified historical forecast endpoint with model selection
HISTORICAL_FORECAST_BASE = "https://historical-forecast-api.open-meteo.com/v1/forecast"

# Model identifiers for the 'models' parameter
MODEL_IDS = {
    "ecmwf": "ecmwf_ifs025",
    "gfs":   "gfs_seamless",
    "icon":  "icon_seamless",
}


def _safe_request(url: str, params: dict, retries: int = 3) -> dict:
    """Make an API request with retry logic."""
    for attempt in range(retries):
        try:
            resp = requests.get(url, params=params, timeout=30)
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 429:
                # Rate limited — wait and retry
                wait = min(2 ** attempt * 2, 30)
                print(f"  ⏳ Rate limited, waiting {wait}s...")
                time.sleep(wait)
            else:
                print(f"  ⚠ API returned {resp.status_code}: {resp.text[:200]}")
                if attempt < retries - 1:
                    time.sleep(1)
        except requests.exceptions.RequestException as e:
            print(f"  ⚠ Request error: {e}")
            if attempt < retries - 1:
                time.sleep(1)
    return {}


def fetch_model_forecast(
    lat: float,
    lon: float,
    start_date: str,
    end_date: str,
    model: str = "gfs",
) -> pd.DataFrame:
    """
    Fetch daily max temperature forecasts from a specific weather model.

    Args:
        lat, lon: Location coordinates
        start_date, end_date: Date range in 'YYYY-MM-DD' format
        model: One of 'ecmwf', 'gfs', 'icon'

    Returns:
        DataFrame with columns: ['date', 'temperature_max']
    """
    url = HISTORICAL_FORECAST_BASE
    model_id = MODEL_IDS.get(model, MODEL_IDS["gfs"])

    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start_date,
        "end_date": end_date,
        "daily": "temperature_2m_max",
        "timezone": "auto",
        "models": model_id,
    }

    data = _safe_request(url, params)

    if not data or "daily" not in data:
        print(f"  ⚠ No data returned for model={model}")
        return pd.DataFrame(columns=["date", "temperature_max"])

    daily = data["daily"]
    df = pd.DataFrame({
        "date": pd.to_datetime(daily["time"]),
        "temperature_max": daily["temperature_2m_max"],
    })

    return df.dropna(subset=["temperature_max"])


def fetch_actual_weather(
    lat: float,
    lon: float,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    """
    Fetch actual observed daily max temperatures (ERA5 reanalysis).

    Returns:
        DataFrame with columns: ['date', 'actual_max']
    """
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start_date,
        "end_date": end_date,
        "daily": "temperature_2m_max",
        "timezone": "auto",
    }

    data = _safe_request(HISTORICAL_WEATHER_URL, params)

    if not data or "daily" not in data:
        print(f"  ⚠ No actual weather data returned")
        return pd.DataFrame(columns=["date", "actual_max"])

    daily = data["daily"]
    df = pd.DataFrame({
        "date": pd.to_datetime(daily["time"]),
        "actual_max": daily["temperature_2m_max"],
    })

    return df.dropna(subset=["actual_max"])


def fetch_all_model_forecasts(
    lat: float,
    lon: float,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    """
    Fetch forecasts from all three models and merge into a single DataFrame.

    Returns:
        DataFrame with columns: ['date', 'ecmwf_max', 'gfs_max', 'icon_max']
    """
    print("  📡 Fetching ECMWF forecasts...")
    ecmwf = fetch_model_forecast(lat, lon, start_date, end_date, "ecmwf")
    time.sleep(0.5)  # Be polite to the API

    print("  📡 Fetching GFS forecasts...")
    gfs = fetch_model_forecast(lat, lon, start_date, end_date, "gfs")
    time.sleep(0.5)

    print("  📡 Fetching ICON forecasts...")
    icon = fetch_model_forecast(lat, lon, start_date, end_date, "icon")

    # Merge all three on date
    merged = ecmwf.rename(columns={"temperature_max": "ecmwf_max"})

    if not gfs.empty:
        gfs = gfs.rename(columns={"temperature_max": "gfs_max"})
        merged = merged.merge(gfs, on="date", how="outer")
    else:
        merged["gfs_max"] = None

    if not icon.empty:
        icon = icon.rename(columns={"temperature_max": "icon_max"})
        merged = merged.merge(icon, on="date", how="outer")
    else:
        merged["icon_max"] = None

    return merged.sort_values("date").reset_index(drop=True)


def fetch_complete_dataset(
    lat: float,
    lon: float,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    """
    Fetch all model forecasts + actual observed temps, merged by date.

    Returns:
        DataFrame with columns:
        ['date', 'ecmwf_max', 'gfs_max', 'icon_max', 'actual_max']
    """
    forecasts = fetch_all_model_forecasts(lat, lon, start_date, end_date)
    time.sleep(0.5)

    print("  📡 Fetching actual observed temperatures...")
    actuals = fetch_actual_weather(lat, lon, start_date, end_date)

    if forecasts.empty:
        return pd.DataFrame()

    if not actuals.empty:
        merged = forecasts.merge(actuals, on="date", how="left")
    else:
        merged = forecasts
        merged["actual_max"] = None

    return merged
