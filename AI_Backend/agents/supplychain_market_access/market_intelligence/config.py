# ── MARKET INTELLIGENCE — CONFIG (insights-only, v3.0) ────
# All constants, thresholds, and env-driven settings.
# v3.0 dropped: transport tiers, state adjacency, action thresholds.

import os
from pathlib import Path
from typing import Final


# ── Agent identity ────────────────────────────────────────
AGENT_ID:      Final[str] = "market_intelligence_agent"
AGENT_VERSION: Final[str] = "3.0.0"
AGENT_NAME:    Final[str] = "Market Intelligence"


# ── Backend API ───────────────────────────────────────────
BACKEND_BASE_URL:      str = os.getenv("BACKEND_BASE_URL", "http://localhost:4000")  # the Node backend
MANDI_PRICES_ENDPOINT: str = "/api/v1/market/prices"


# ── HTTP Client ───────────────────────────────────────────
HTTP_TIMEOUT_SECONDS: float = float(os.getenv("HTTP_TIMEOUT_SECONDS", "15.0"))
HTTP_MAX_RETRIES:     int   = int(os.getenv("HTTP_MAX_RETRIES",       "3"))
HTTP_RETRY_BACKOFF:   float = float(os.getenv("HTTP_RETRY_BACKOFF",   "1.5"))


# ── Data Fetch Limits ─────────────────────────────────────
DEFAULT_FETCH_LIMIT:              int = int(os.getenv("DEFAULT_FETCH_LIMIT", "200"))
MIN_RECORDS_FOR_INSIGHTS:         int = 1     # below this → return error
MIN_RECORDS_FOR_TREND:            int = 5
MIN_RECORDS_FOR_LSTM:             int = 30
FRESH_RECORD_WINDOW_DAYS:         int = 7     # for fresh_records_pct
MARKETS_TO_RETURN:                int = int(os.getenv("MARKETS_TO_RETURN", "10"))


# ── Default Commodities ───────────────────────────────────
DEFAULT_COMMODITIES = ["Wheat", "Rice", "Tomato", "Onion", "Potato",
                       "Soybean", "Cotton", "Maize"]


# ── LSTM Model Paths ──────────────────────────────────────
_ML_MODELS_DIR_ENV = os.getenv("ML_MODELS_DIR", "AI_Backend/ml/models")
ML_MODELS_DIR: Path = Path(_ML_MODELS_DIR_ENV)

LSTM_MODEL_PATH:  Path = ML_MODELS_DIR / os.getenv("LSTM_MODEL_FILE",  "mandi_price_lstm.h5")
LSTM_SCALER_PATH: Path = ML_MODELS_DIR / os.getenv("LSTM_SCALER_FILE", "price_scaler.pkl")

LSTM_SEQUENCE_LENGTH: int = int(os.getenv("LSTM_SEQUENCE_LENGTH", "30"))

LSTM_FEATURE_COLUMNS = ["modal_price"]
LSTM_PRIMARY_FEATURE = "modal_price"


# ── Trend Thresholds (normalised slope: slope / mean_price) ──
TREND_INCREASE_THRESHOLD: float = float(os.getenv("TREND_INCREASE_THRESHOLD",  "0.02"))   # +2 %
TREND_DECREASE_THRESHOLD: float = float(os.getenv("TREND_DECREASE_THRESHOLD", "-0.02"))   # −2 %

# % change in predicted price to label as increasing / decreasing
FORECAST_INCREASE_THRESHOLD: float =  0.02
FORECAST_DECREASE_THRESHOLD: float = -0.02


# ── Confidence Score Band Labels (informational) ───────────
CONFIDENCE_HIGH:   float = 0.70
CONFIDENCE_MEDIUM: float = 0.45
CONFIDENCE_LOW:    float = 0.25
