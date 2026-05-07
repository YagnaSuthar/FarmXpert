from fastapi import FastAPI 
import os 
from dotenv import load_dotenv 
from AI_Backend.agents.base.base_agent import BaseAgent
from AI_Backend.agents.crop_planning_growth.weather_watcher.service import WeatherService

load_dotenv()

class WeatherAgent(BaseAgent):
    def __init__(self,name:str):
        super().__init__(name)
        self.api_key = os.getenv("OPENWEATHER_API_KEY")
        self.base_url = "https://api.openweathermap.org/data/2.5"
        self.service = WeatherService(api_key=self.api_key, base_url=self.base_url, logger=self.logger)
        

    async def __call__(self, state):

        return await self.run(state)

    async def run(self, input_data: dict) -> dict:
        self.logger.info("Running Weather Agent Successfully")
        
        data = self.preprocess(input_data)

        result = await self.get_weather_data(data)

        return self.postprocess(result)


    async def get_weather_data(self,location:dict):
        """
        Fetches weather data from openWhether API (External)
            -- current 
            -- forecast
            -- alerts from llm 
        """

        current = await self.service.fetch_current_weather(location)
        short_forecast = await self.service.fetch_openweather_forecast(location)
        long_forecast = await self.service.fetch_openmeteo_forecast(location)

        # remove overlapping dates
        short_dates = {d["date"] for d in short_forecast}

        filtered_long_forecast = [
            d for d in long_forecast if d["date"] not in short_dates
        ]
        alerts = self.service.generate_alerts(current, short_forecast + filtered_long_forecast)
        return {
        "current_weather": current,
        "forecast_short_term": short_forecast,   # 5 days (accurate)
        "forecast_long_term": filtered_long_forecast ,     # 10–15 days (trend)
        "alerts": alerts,
        }