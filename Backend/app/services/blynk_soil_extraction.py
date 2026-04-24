import requests
from datetime import datetime
from sqlalchemy import select
from app.models.blynk_token import BlynkToken
from app.models.soil_data import SoilData

class BlynkSoilService:

    BASE_URL = "https://blynk.cloud/external/api/get"

    def __init__(self, db):
        self.db = db

    # 🔑 Get active token
    async def get_active_token(self, farm_id: str):
        result = await self.db.execute(
            select(BlynkToken).where(
                BlynkToken.farm_id == farm_id,
                BlynkToken.is_active == True
            )
        )
        return result.scalars().first()

    # 📡 Fetch from Blynk
    def fetch_data(self, token: str):
        params = {
            "token": token,
            "V0": "", "V1": "", "V2": "", "V3": "",
            "V4": "", "V5": "", "V6": "", "V7": "", "V8": ""
        }

        response = requests.get(self.BASE_URL, params=params)
        return response.json()

    # 💾 Save soil data
    async def save_soil_data(self, farm_id: str, data: dict):

        soil = SoilData(
            farm_id=farm_id,
            timestamp=datetime.utcnow(),

            soil_moisture=float(data.get("V0", 0)),
            soil_temperature=float(data.get("V1", 0)),
            soil_ph=float(data.get("V2", 0)),
            nitrogen=float(data.get("V3", 0)),
            phosphorus=float(data.get("V4", 0)),
            potassium=float(data.get("V5", 0)),
            electrical_conductivity=float(data.get("V6", 0)),

            air_temperature=float(data.get("V7", 0)),
            air_humidity=float(data.get("V8", 0)),
        )

        self.db.add(soil)
        await self.db.commit()
        await self.db.refresh(soil)

        return soil

    # 🔥 Main flow
    async def run(self, farm_id: str):

        token_obj = await self.get_active_token(farm_id)

        if not token_obj:
            raise Exception("No active token found")

        data = self.fetch_data(token_obj.token)

        return await self.save_soil_data(farm_id, data)