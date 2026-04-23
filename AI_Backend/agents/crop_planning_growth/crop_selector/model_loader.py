from ml.models import Crop_selector
import joblib

model = joblib.load("Crop_selector/crop_model.pkl")
le = joblib.load("Crop_selector/label_encoder.pkl")