from pydantic import BaseModel
from datetime import datetime


from uuid import UUID

# 🔹 Base Schema (common fields)
class BlynkTokenBase(BaseModel):
    farm_id: UUID
    token: str


# 🔹 Create Schema (Swagger input)
class BlynkTokenCreate(BlynkTokenBase):
    pass


# 🔹 Response Schema
class BlynkTokenResponse(BlynkTokenBase):
    id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True   # for SQLAlchemy (Pydantic v2)