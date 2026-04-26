from pydantic import BaseModel, Field, field_validator
from typing import Optional, List


# 🔹 Base schema (used internally)
class MandiPrice(BaseModel):
    commodity: str = Field(..., example="Wheat")
    market: str = Field(..., example="Ahmedabad")
    state: str = Field(..., example="Gujarat")
    district: str = Field(..., example="Ahmedabad")

    min_price: float = Field(..., ge=0)
    max_price: float = Field(..., ge=0)
    modal_price: float = Field(..., ge=0)

    arrival_date: Optional[str] = None
    variety: Optional[str] = None
    grade: Optional[str] = None

    # 🔥 Validation: ensure prices are logical
    @field_validator("max_price")
    def validate_prices(cls, v, values):
        min_price = values.data.get("min_price")
        if min_price is not None and v < min_price:
            raise ValueError("max_price cannot be less than min_price")
        return v

    @field_validator("modal_price")
    def validate_modal_price(cls, v, values):
        min_price = values.data.get("min_price")
        max_price = values.data.get("max_price")

        if min_price is not None and max_price is not None:
            if not (min_price <= v <= max_price):
                raise ValueError("modal_price must be between min_price and max_price")
        return v


# 🔹 Response schema (clean API output)
class MandiPriceResponse(BaseModel):
    count: int
    data: List[MandiPrice]