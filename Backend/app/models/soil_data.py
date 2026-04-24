from sqlalchemy import Column, Float, String, Integer, TIMESTAMP, ForeignKey, DateTime, Text
from sqlalchemy.dialects.postgresql import UUID
from app.core.config import Base
from sqlalchemy import func
from datetime import datetime
from sqlalchemy.dialects.postgresql import UUID

class SoilData(Base):
    """
    Stores soil health and nutrient data for a farm
    """

    __tablename__ = "soil_data"

    id = Column(Integer, primary_key=True, index=True)



    # Farm relation
    farm_id = Column(UUID(as_uuid=True), ForeignKey("farms.id"), nullable=True)

    # Timestamp
    recorded_at = Column(DateTime,server_default=func.now(),nullable=False) # Timestamp of the data 

    # --- Soil Parameters (7) ---
    soil_moisture = Column(Float)        # %
    soil_temperature = Column(Float)     # °C
    soil_ph = Column(Float)              # pH level
    nitrogen = Column(Float)             # mg/kg
    phosphorus = Column(Float)           # mg/kg
    potassium = Column(Float)            # mg/kg
    electrical_conductivity = Column(Float)  # dS/m

    # --- Air Parameters (2) ---
    air_temperature = Column(Float)      # °C
    air_humidity = Column(Float)         # %

    # --- Context Data ---
    soil_type = Column(String(50))       # Clay, Sandy, Peaty, Silt, Loam
    rainfall = Column(Float)             # mm (past or recent rainfall)
    irrigation_type = Column(String(50)) # Examples: Drip, Sprinkler, Flood, Manual
    irrigation_amount = Column(Float)    # mm or liters per day (important for analysis)
    fertilizer_type = Column(String(100))# Example: Urea, DAP, NPK, Organic Compost
    fertilizer_amount = Column(Float)    # kg per hectare
    crop_type = Column(String(50))       # Important for recommendation

    # --- AI Outputs ---
    soil_health_score = Column(Float)     # 0–100
    soil_health_status = Column(String(20))  # Excellent / Good / Alert / Critical
    alerts = Column(Text)                 # JSON or comma-separated
    recommendations = Column(Text)        # AI-generated suggestions