from fastapi import APIRouter,Depends,HTTPException,status
# from geoalchemy2.shape import from_shape
# from shapely.geometry import Point 
from fastapi import Form as FAST_API_FORM
from pydantic import BaseModel
from uuid import UUID
from sqlalchemy import select
from app.models.farms import Farm
from app.schemas.farm_schema import FarmCreate,FarmResponse
from app.core.config import get_db
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/farms",tags=["This API Endpoints Ensures all Farm CRUD Operations"])

class FarmUpdate(BaseModel):
    farm_size_acres: float | None = None
    latitude: float | None = None
    longitude: float | None = None

# create 
@router.post("/",response_model=FarmResponse,status_code=status.HTTP_201_CREATED)
async def create_farm(farm:FarmCreate,db:AsyncSession = Depends(get_db)):
    try:
        # TODO: Uncomment PostGIS code when installed
        # Convert lat/lon into geometry (POSTGIS Point)
        # location_point = from_shape(Point(farm.longitude,farm.latitude),srid=4326)

        new_farm = Farm(
           user_id = farm.user_id,
           farm_size_acres = farm.farm_size_acres,
           latitude = farm.latitude,
           longitude = farm.longitude,
           # location = location_point, 
        )
        db.add(new_farm)
        await db.commit()
        await db.refresh(new_farm)

        return new_farm


    except Exception as e: 
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Error while creating farm: {str(e)}"
        )

# Read 

@router.get("/", response_model=list[FarmResponse])
async def list_farms(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Farm))
    return list(result.scalars().all())


@router.get("/{farm_id}", response_model=FarmResponse)
async def get_farm(farm_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Farm).where(Farm.id == farm_id))
    farm = result.scalar_one_or_none()
    if farm is None:
        raise HTTPException(status_code=404, detail="Farm not found")
    return farm

#update 

@router.put("/{farm_id}", response_model=FarmResponse)
async def update_farm(farm_id: UUID, payload: FarmUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Farm).where(Farm.id == farm_id))
    farm = result.scalar_one_or_none()
    if farm is None:
        raise HTTPException(status_code=404, detail="Farm not found")

    if payload.farm_size_acres is not None:
        farm.farm_size_acres = payload.farm_size_acres
    if payload.latitude is not None:
        farm.latitude = payload.latitude
    if payload.longitude is not None:
        farm.longitude = payload.longitude

    try:
        await db.commit()
        await db.refresh(farm)
        return farm
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Error while updating farm: {str(e)}")

#delete

@router.delete("/{farm_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_farm(farm_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Farm).where(Farm.id == farm_id))
    farm = result.scalar_one_or_none()
    if farm is None:
        raise HTTPException(status_code=404, detail="Farm not found")

    try:
        await db.delete(farm)
        await db.commit()
        return None
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Error while deleting farm: {str(e)}")