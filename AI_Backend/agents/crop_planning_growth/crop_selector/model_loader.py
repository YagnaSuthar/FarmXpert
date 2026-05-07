import os
import joblib

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_MODEL_DIR = os.path.normpath(os.path.join(_BASE_DIR, "..", "..", "..", "ml", "models", "Crop_selector"))

model = joblib.load(os.path.join(_MODEL_DIR, "crop_model.pkl"))
le = joblib.load(os.path.join(_MODEL_DIR, "label_encoder.pkl"))