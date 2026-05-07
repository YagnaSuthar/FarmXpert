
from pydantic import BaseModel, ConfigDict, Field


class LocationSchema(BaseModel):
    lat: float = Field(..., example=23.02)
    lon: float = Field(..., example=72.57)


class NPKSchema(BaseModel):
    n: float | int | None = Field(default=None, example=280)
    p: float | int | None = Field(default=None, example=45)
    k: float | int | None = Field(default=None, example=210)


class SoilDataSchema(BaseModel):
    ph: float | None = Field(default=None, example=6.5)
    npk: NPKSchema | None = None
    organic_matter: float | None = Field(default=None, example=2.1)
    texture: str | None = Field(default=None, example="loamy")
    moisture: float | None = Field(default=None, example=45.0)
    temperature: float | None = Field(default=None, example=25.0)
    ec: float | None = Field(default=None, example=0.5)
    humidity: float | None = Field(default=None, example=70.0)
    soil_type: str | None = Field(default=None, example="Loam")


class CropSelectorRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "farm_id": "farm_123",
                    "location": {"lat": 23.02, "lon": 72.57},
                    "season": "kharif",
                    "water_availability": "moderate",
                }
            ]
        }
    )

    farm_id: str | None = None
    soil_data: SoilDataSchema | None = None
    location: LocationSchema | None = None
    season: str | None = None
    water_availability: str | None = None
    farm_size_acres: float | None = None
    farmer_goals: list[str] | None = None
    previous_crops: list[str] | None = None


class CropRecommendation(BaseModel):
    crop_name: str
    suitability_score: float
    variety: str | None = None
    reasons: list[str] | None = None
    expected_yield: str | None = None
    estimated_profit: str | None = None
    water_requirement: str | None = None
    duration_days: int | None = None
    intercropping_options: list[str] | None = None


class CropRotationPlan(BaseModel):
    kharif: str | None = None
    rabi: str | None = None
    zaid: str | None = None


class CropSelectorResponse(BaseModel):
    recommended_crops: list[CropRecommendation]
    crop_rotation_plan: CropRotationPlan | None = None
    LLM_Recommendation: str | None = Field(default=None, description="LLM-based detailed recommendations and reasoning")

