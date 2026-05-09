# ── MARKET INTELLIGENCE — MODEL LOADER ────────────────────
# Loads and manages the LSTM price-forecasting model.
# Gracefully degrades to weighted moving average when model is absent
# or when insufficient history is available.
#
# Thread-safety note: load_model() is called once at service startup.
# predict_price_trend() is stateless and safe to call concurrently.

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

import numpy as np

if TYPE_CHECKING:
    # Avoid hard import at module load — TF is optional
    pass

logger = logging.getLogger(__name__)


# ═════════════════════════════════════════════════════════════
# MODULE-LEVEL SINGLETONS  (loaded once, reused across requests)
# ═════════════════════════════════════════════════════════════

_model: Optional[Any] = None          # keras Model
_scaler: Optional[Any] = None         # sklearn MinMaxScaler / StandardScaler
_model_ready: bool = False            # True only after successful load
_scaler_ready: bool = False


# ═════════════════════════════════════════════════════════════
# PRIVATE HELPERS
# ═════════════════════════════════════════════════════════════

def _try_import_tensorflow() -> Optional[Any]:
    """Return the tensorflow module, or None if not installed."""
    try:
        import tensorflow as tf
        return tf
    except ImportError:
        logger.warning(
            "TensorFlow not installed — LSTM forecasting disabled. "
            "Install: pip install tensorflow"
        )
        return None


def _try_import_joblib() -> Optional[Any]:
    try:
        import joblib
        return joblib
    except ImportError:
        return None


# ═════════════════════════════════════════════════════════════
# PUBLIC API — MODEL LIFECYCLE
# ═════════════════════════════════════════════════════════════

def load_model(
    model_path: Path,
    scaler_path: Optional[Path] = None,
) -> bool:
    """
    Load the LSTM model (and optional price scaler) from disk.

    Called once at service startup via service._ensure_model_loaded().
    Idempotent — subsequent calls are no-ops if already loaded.

    Args:
        model_path:  Path to the saved Keras model (.h5 or SavedModel dir).
        scaler_path: Optional path to a joblib-serialised sklearn scaler.

    Returns:
        True  — model loaded successfully (LSTM predictions available).
        False — model not found or failed to load (WMA fallback will be used).
    """
    global _model, _scaler, _model_ready, _scaler_ready

    if _model_ready:
        return True   # already loaded

    tf = _try_import_tensorflow()
    if tf is None:
        return False

    # ── Load LSTM model ──────────────────────────────────────
    if not model_path.exists():
        logger.warning(
            "LSTM model not found at '%s'. "
            "Forecasting will use weighted moving average fallback.",
            model_path,
        )
        return False

    try:
        _model = tf.keras.models.load_model(str(model_path), compile=False)
        _model_ready = True
        logger.info(
            "LSTM model loaded from '%s'. "
            "Input shape: %s | Parameters: %s",
            model_path,
            _model.input_shape,
            f"{_model.count_params():,}",
        )
    except Exception:
        logger.exception("Failed to load LSTM model from '%s'.", model_path)
        return False

    # ── Load price scaler (optional but recommended) ─────────
    if scaler_path is not None:
        joblib = _try_import_joblib()
        if joblib is None:
            logger.warning("joblib not installed — scaler loading skipped.")
        elif not scaler_path.exists():
            logger.warning(
                "Scaler file not found at '%s'. "
                "Predictions will use min-max normalisation fallback.",
                scaler_path,
            )
        else:
            try:
                _scaler = joblib.load(str(scaler_path))
                _scaler_ready = True
                logger.info("Price scaler loaded from '%s'.", scaler_path)
            except Exception:
                logger.warning(
                    "Could not load scaler from '%s' — using built-in normalisation.",
                    scaler_path,
                    exc_info=True,
                )

    return True


def is_model_ready() -> bool:
    """Return True if the LSTM model is loaded and available."""
    return _model_ready and _model is not None


# ═════════════════════════════════════════════════════════════
# PRIVATE — SEQUENCE BUILDERS
# ═════════════════════════════════════════════════════════════

def _build_input_sequence(
    prices: List[float],
    sequence_length: int,
) -> Optional[np.ndarray]:
    """
    Construct the (1, sequence_length, 1) tensor expected by the LSTM.

    Uses the LAST `sequence_length` prices so the model sees the most
    recent window of market activity.

    Returns None if insufficient data.
    """
    if len(prices) < sequence_length:
        return None

    window = np.array(prices[-sequence_length:], dtype=np.float32).reshape(-1, 1)
    return window


def _scale(arr: np.ndarray) -> tuple[np.ndarray, float]:
    """
    Normalise a (N,1) price array to [0,1] using per-window min-max.

    Returns (scaled_arr, max_val) so the inverse transform can recover
    the original scale.  Used only when _scaler is not available.
    """
    max_val = float(arr.max())
    min_val = float(arr.min())
    rng     = max_val - min_val

    if rng == 0:
        return np.ones_like(arr, dtype=np.float32), max_val

    scaled = (arr - min_val) / rng
    return scaled.astype(np.float32), max_val


def _inverse_scale_minmax(value: float, arr_original: np.ndarray) -> float:
    """Inverse of _scale using the original (unscaled) window."""
    max_val = float(arr_original.max())
    min_val = float(arr_original.min())
    rng     = max_val - min_val

    if rng == 0:
        return max_val

    return value * rng + min_val


# ═════════════════════════════════════════════════════════════
# PRIVATE — FALLBACK FORECASTER  (weighted moving average)
# ═════════════════════════════════════════════════════════════

def _weighted_moving_average_forecast(prices: List[float]) -> float:
    """
    Linearly-weighted moving average over the last 7 prices.

    More recent prices receive higher weight.
    w_i = i + 1  for i in [0 .. window-1]

    Example (window=3, prices=[100, 110, 120]):
        wma = (1×100 + 2×110 + 3×120) / (1+2+3) = 113.3
    """
    window  = prices[-min(7, len(prices)):]
    weights = list(range(1, len(window) + 1))
    wma     = sum(p * w for p, w in zip(window, weights)) / sum(weights)
    return round(wma, 2)


# ═════════════════════════════════════════════════════════════
# PRIVATE — TREND CLASSIFIER
# ═════════════════════════════════════════════════════════════

def _classify_trend(
    current_price: float,
    predicted_price: float,
    increase_threshold: float = 0.02,
    decrease_threshold: float = -0.02,
) -> str:
    """
    Classify direction of predicted price change.

    Returns "increasing" | "decreasing" | "stable".
    """
    if current_price <= 0:
        return "stable"

    pct_change = (predicted_price - current_price) / current_price

    if pct_change > increase_threshold:
        return "increasing"
    if pct_change < decrease_threshold:
        return "decreasing"
    return "stable"


# ═════════════════════════════════════════════════════════════
# PUBLIC API — PRICE PREDICTION
# ═════════════════════════════════════════════════════════════

def predict_price_trend(
    records: List[Any],           # List[PriceRecord] — typed loosely to avoid circular import
    sequence_length: int = 30,
    current_price: Optional[float] = None,
    increase_threshold: float = 0.02,
    decrease_threshold: float = -0.02,
) -> Dict[str, Any]:
    """
    Forecast the next mandi price and its directional trend.

    Strategy (waterfall — uses first strategy that has enough data):
        1. LSTM model     — if model loaded AND len(prices) ≥ sequence_length
        2. WMA fallback   — if len(prices) ≥ 3
        3. Last price     — if only 1–2 prices available

    Args:
        records:            List of PriceRecord DTOs, ideally sorted oldest→newest.
        sequence_length:    LSTM input window (must match training config).
        current_price:      Explicit latest price override (optional).
        increase_threshold: % change to classify as "increasing" (default +2%).
        decrease_threshold: % change to classify as "decreasing" (default -2%).

    Returns:
        {
            "predicted_price":  float,
            "predicted_trend":  "increasing" | "decreasing" | "stable",
            "model_used":       "lstm" | "moving_average" | "fallback",
        }
    """
    # Extract prices (modal_price only; validates > 0)
    prices: List[float] = [
        float(r.modal_price)
        for r in records
        if hasattr(r, "modal_price") and r.modal_price and float(r.modal_price) > 0
    ]

    last_price = current_price or (prices[-1] if prices else 0.0)

    # ── No price data at all ─────────────────────────────────
    if not prices:
        logger.warning("predict_price_trend: no valid prices — returning fallback.")
        return {
            "predicted_price": last_price,
            "predicted_trend": "stable",
            "model_used":      "fallback",
        }

    # ════════════════════════════════════════════════════════
    # Strategy 1: LSTM
    # ════════════════════════════════════════════════════════
    if _model_ready and _model is not None and len(prices) >= sequence_length:
        try:
            window = _build_input_sequence(prices, sequence_length)
            if window is not None:

                # Scale
                if _scaler_ready and _scaler is not None:
                    scaled_window = _scaler.transform(window)
                else:
                    scaled_window, _ = _scale(window)

                # Reshape → (1, sequence_length, 1)
                model_input = scaled_window.reshape(1, sequence_length, 1)

                raw_pred = _model.predict(model_input, verbose=0)
                raw_val  = float(raw_pred[0][0])

                # Inverse scale
                if _scaler_ready and _scaler is not None:
                    predicted_price = float(
                        _scaler.inverse_transform([[raw_val]])[0][0]
                    )
                else:
                    predicted_price = _inverse_scale_minmax(raw_val, window)

                predicted_price = max(0.0, round(predicted_price, 2))
                trend           = _classify_trend(
                    last_price, predicted_price,
                    increase_threshold, decrease_threshold,
                )

                pct = (predicted_price - last_price) / last_price * 100 if last_price > 0 else 0
                logger.info(
                    "LSTM forecast: ₹%.2f → ₹%.2f (%+.1f%%) | trend=%s",
                    last_price, predicted_price, pct, trend,
                )

                return {
                    "predicted_price": predicted_price,
                    "predicted_trend": trend,
                    "model_used":      "lstm",
                }

        except Exception:
            logger.exception(
                "LSTM prediction failed for %d prices — falling back to WMA.", len(prices)
            )

    # ════════════════════════════════════════════════════════
    # Strategy 2: Weighted moving average
    # ════════════════════════════════════════════════════════
    if len(prices) >= 3:
        predicted_price = _weighted_moving_average_forecast(prices)
        trend           = _classify_trend(
            last_price, predicted_price,
            increase_threshold, decrease_threshold,
        )

        pct = (predicted_price - last_price) / last_price * 100 if last_price > 0 else 0
        logger.info(
            "WMA forecast: ₹%.2f → ₹%.2f (%+.1f%%) | trend=%s",
            last_price, predicted_price, pct, trend,
        )

        return {
            "predicted_price": predicted_price,
            "predicted_trend": trend,
            "model_used":      "moving_average",
        }

    # ════════════════════════════════════════════════════════
    # Strategy 3: Return last known price (no forecast possible)
    # ════════════════════════════════════════════════════════
    logger.warning(
        "predict_price_trend: only %d price record(s) — returning last price as forecast.",
        len(prices),
    )
    return {
        "predicted_price": round(last_price, 2),
        "predicted_trend": "stable",
        "model_used":      "fallback",
    }