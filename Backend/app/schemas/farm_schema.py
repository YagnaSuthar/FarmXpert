from pydantic import BaseModel
from typing import List,Any
from uuid import UUID
from datetime import datetime 



class FarmBase(BaseModel):
    farm_size_acres:float
    latitude:float
    longitude:float

class FarmCreate(FarmBase):
    user_id:UUID

class FarmResponse(FarmBase):
    id:UUID
    user_id:UUID
    created_at:datetime

    class Config:
        from_attributes = True