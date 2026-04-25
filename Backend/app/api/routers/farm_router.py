from fastapi import APIRouter,Depends,HTTPException,status
from geoalchemy2.shape import from_shape
from shapely.geometry import Point 
from fastapi import Form as FAST_API_FORM
from models.farms import Farm
from schemas.farm_schema import FarmCreate,FarmResponse
from core.config import get_db
from sqlalchemy.orm import Session

router = APIRouter(prefix="/farms",tags=["This API Endpoints Ensures all Farm CRUD Operations"])

# create 
@router.post("/",response_model=FarmResponse,status_code=status.HTTP_201_CREATED)
async def create_farm(farm:FarmCreate,db:Session = Depends(get_db)):
    try:
        # Convert lat/lon into geometry (POSTGIS Point)
        location_point = from_shape(Point(farm.longitude,farm.latitude),srid=4326)

        new_farm = Farm(
           user_id = farm.user_id,
           farm_size_acres = farm.farm_size_acres,
           location = location_point, 
        )
        await db.add(new_farm)
        db.commit()
        db.refresh(new_farm)

        return new_farm


    except Exception as e: 
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Error while creating farm: {str(e)}"
        )

# Read 

#update 

#delete 