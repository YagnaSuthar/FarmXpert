from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select,desc
from Backend.app.models.soil_data import SoilData

class SoilRepository:
    async def get_latest_soil_data(self,farm_id:str,db:AsyncSession):
        # data fetch from the db 
       result = await db.execute(
           select(SoilData)
           .where(SoilData.farm_id == farm_id)
           .order_by(desc(SoilData.recorded_at))
           .limit(1)
       )  


       soil = result.scalars().first()


       print("Latest Soil Data is given By :\n\n\n\n\n\n")
       print(f"""
        Soil Data:
        moisture: {soil.soil_moisture}
        temperature: {soil.soil_temperature}
        ph: {soil.soil_ph}
        nitrogen: {soil.nitrogen}
        phosphorus: {soil.phosphorus}
        potassium: {soil.potassium}
        EC: {soil.electrical_conductivity}
        """)
       print("\n\n\n\n\n\n")


       if not soil:
           return "Soil Data Not Founded!!!!!!!!!!!!!!"
       
       return {
            "soil_moisture": soil.soil_moisture,
            "electrical_conductivity": soil.electrical_conductivity,
            "nitrogen": soil.nitrogen,
            "phosphorus": soil.phosphorus,
            "potassium": soil.potassium,
            "soil_ph": soil.soil_ph
        }