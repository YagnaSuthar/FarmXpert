# ── MARKET INTELLIGENCE — CONFIG ──────────────────────────
# All constants, thresholds, and environment-driven settings.
# NEVER hardcode values in logic.py or service.py — pull from here.

import os
from pathlib import Path
from typing import Dict, Set

# ── Backend API ────────────────────────────────────────────
BACKEND_BASE_URL: str = os.getenv("BACKEND_BASE_URL", "http://localhost:8000")
MANDI_PRICES_ENDPOINT: str = "/api/v1/market/prices"

# ── HTTP Client ────────────────────────────────────────────
HTTP_TIMEOUT_SECONDS: float = float(os.getenv("HTTP_TIMEOUT_SECONDS", "15.0"))
HTTP_MAX_RETRIES: int = int(os.getenv("HTTP_MAX_RETRIES", "3"))
HTTP_RETRY_BACKOFF: float = float(os.getenv("HTTP_RETRY_BACKOFF", "1.5"))  # seconds, multiplied by attempt

# ── Data Fetch Limits ─────────────────────────────────────
DEFAULT_FETCH_LIMIT: int = int(os.getenv("DEFAULT_FETCH_LIMIT", "200"))
MIN_RECORDS_FOR_RECOMMENDATION: int = 1
MIN_RECORDS_FOR_TREND: int = 5       # need at least N prices for regression
MIN_RECORDS_FOR_LSTM: int = 30       # need at least LSTM_SEQUENCE_LENGTH records

# ── Default Commodities ───────────────────────────────────
DEFAULT_COMMODITIES = ["Wheat", "Rice", "Tomato", "Onion", "Potato", "Soybean", "Cotton", "Maize"]

# ── LSTM Model Paths ──────────────────────────────────────
_ML_MODELS_DIR_ENV = os.getenv("ML_MODELS_DIR", "AI_Backend/ml/models")
ML_MODELS_DIR: Path = Path(_ML_MODELS_DIR_ENV)

LSTM_MODEL_PATH: Path = ML_MODELS_DIR / os.getenv("LSTM_MODEL_FILE", "mandi_price_lstm.h5")
LSTM_SCALER_PATH: Path = ML_MODELS_DIR / os.getenv("LSTM_SCALER_FILE", "price_scaler.pkl")

LSTM_SEQUENCE_LENGTH: int = int(os.getenv("LSTM_SEQUENCE_LENGTH", "30"))

# Feature columns expected by model (order matters)
LSTM_FEATURE_COLUMNS = ["modal_price"]   # extend to ["modal_price","min_price","max_price"] if multi-feature
LSTM_PRIMARY_FEATURE = "modal_price"

# ── Trend Thresholds ──────────────────────────────────────
# Normalised slope (slope / mean_price) required to classify as increasing/decreasing
TREND_INCREASE_THRESHOLD: float = float(os.getenv("TREND_INCREASE_THRESHOLD", "0.02"))
TREND_DECREASE_THRESHOLD: float = float(os.getenv("TREND_DECREASE_THRESHOLD", "-0.02"))

# % change in predicted price to call it increasing/decreasing
FORECAST_INCREASE_THRESHOLD: float = 0.02   # +2%
FORECAST_DECREASE_THRESHOLD: float = -0.02  # -2%

# ── Transport Cost Tiers (₹ per quintal, approximate) ─────
# Adjust these via env for regional calibration
TRANSPORT_SAME_MARKET: float    = float(os.getenv("TRANSPORT_SAME_MARKET",    "0.0"))
TRANSPORT_SAME_DISTRICT: float  = float(os.getenv("TRANSPORT_SAME_DISTRICT",  "50.0"))
TRANSPORT_SAME_STATE: float     = float(os.getenv("TRANSPORT_SAME_STATE",     "150.0"))
TRANSPORT_ADJACENT_STATE: float = float(os.getenv("TRANSPORT_ADJACENT_STATE", "300.0"))
TRANSPORT_DISTANT_STATE: float  = float(os.getenv("TRANSPORT_DISTANT_STATE",  "500.0"))

# State adjacency map — undirected (both directions handled in logic)
STATE_ADJACENCY: Dict[str, Set[str]] = {
    "gujarat":              {"rajasthan", "madhya pradesh", "maharashtra",
                             "dadra and nagar haveli", "daman and diu"},
    "rajasthan":            {"gujarat", "madhya pradesh", "uttar pradesh",
                             "haryana", "punjab", "himachal pradesh"},
    "maharashtra":          {"gujarat", "madhya pradesh", "chhattisgarh",
                             "telangana", "karnataka", "goa"},
    "madhya pradesh":       {"gujarat", "rajasthan", "uttar pradesh",
                             "chhattisgarh", "maharashtra"},
    "uttar pradesh":        {"rajasthan", "madhya pradesh", "chhattisgarh",
                             "jharkhand", "bihar", "haryana", "uttarakhand",
                             "himachal pradesh"},
    "punjab":               {"haryana", "rajasthan", "himachal pradesh",
                             "jammu and kashmir"},
    "haryana":              {"punjab", "rajasthan", "uttar pradesh",
                             "himachal pradesh", "delhi"},
    "karnataka":            {"maharashtra", "goa", "kerala", "tamil nadu",
                             "andhra pradesh", "telangana"},
    "andhra pradesh":       {"karnataka", "telangana", "odisha", "tamil nadu",
                             "chhattisgarh"},
    "telangana":            {"maharashtra", "karnataka", "andhra pradesh",
                             "chhattisgarh", "odisha"},
    "west bengal":          {"odisha", "jharkhand", "bihar", "sikkim",
                             "assam", "tripura", "nagaland", "meghalaya"},
    "bihar":                {"uttar pradesh", "jharkhand", "west bengal"},
    "odisha":               {"west bengal", "jharkhand", "chhattisgarh",
                             "andhra pradesh", "telangana"},
    "chhattisgarh":         {"madhya pradesh", "uttar pradesh", "jharkhand",
                             "odisha", "telangana", "andhra pradesh", "maharashtra"},
    "kerala":               {"karnataka", "tamil nadu"},
    "tamil nadu":           {"karnataka", "kerala", "andhra pradesh", "puducherry"},
    "assam":                {"arunachal pradesh", "nagaland", "manipur",
                             "mizoram", "tripura", "meghalaya", "west bengal"},
    "uttarakhand":          {"uttar pradesh", "himachal pradesh"},
    "himachal pradesh":     {"punjab", "haryana", "uttar pradesh",
                             "uttarakhand", "jammu and kashmir"},
    "jharkhand":            {"bihar", "west bengal", "odisha", "chhattisgarh",
                             "uttar pradesh"},
    "goa":                  {"maharashtra", "karnataka"},
}

# ── Action / Confidence Thresholds ───────────────────────
HOLD_MIN_CONFIDENCE: float  = float(os.getenv("HOLD_MIN_CONFIDENCE", "0.40"))
# Minimum profit advantage to justify travelling to another mandi (₹)
MIN_PROFIT_TO_TRAVEL: float = float(os.getenv("MIN_PROFIT_TO_TRAVEL", "100.0"))

# ── Confidence Score Band Labels ─────────────────────────
CONFIDENCE_HIGH: float   = 0.70
CONFIDENCE_MEDIUM: float = 0.45
CONFIDENCE_LOW: float    = 0.25