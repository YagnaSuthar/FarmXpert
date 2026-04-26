# ── MARKET INTELLIGENCE AGENT CONFIG ──────────────────────

import os

BACKEND_BASE_URL = os.getenv("BACKEND_BASE_URL", "http://localhost:8000")

# Endpoint on the Backend that returns latest mandi prices
MANDI_QUERY_ENDPOINT = f"{BACKEND_BASE_URL}/api/v1/market/prices"

# Default commodities the agent monitors
DEFAULT_COMMODITIES = ["Wheat", "Rice", "Tomato", "Onion", "Potato"]

# Confidence thresholds
CONFIDENCE_LOW_THRESHOLD = 5
CONFIDENCE_MEDIUM_THRESHOLD = 20
