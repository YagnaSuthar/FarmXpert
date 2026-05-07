# service.py
import logging
from datetime import datetime
import httpx


class WeatherService:
    def __init__(self, api_key: str | None, base_url: str, logger: logging.Logger | None = None):
        self.api_key = api_key
        self.base_url = base_url
        self.logger = logger or logging.getLogger(__name__)

    async def fetch_current_weather(self, location: dict):
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/weather",
                params={
                    "lat": location["lat"],
                    "lon": location["lon"],
                    "appid": self.api_key,
                    "units": "metric",
                },
            )

            data = response.json()

        return {
            "temperature": data["main"]["temp"],
            "humidity": data["main"]["humidity"],
            "wind_speed": data["wind"]["speed"],
            "conditions": data["weather"][0]["main"],
            "rainfall_today": data.get("rain", {}).get("1h", 0),
        }

    async def fetch_openweather_forecast(self, location: dict):
        "Fetches 1 Week (7 days forecast data )"

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/forecast",
                params={
                    "lat": location["lat"],
                    "lon": location["lon"],
                    "appid": self.api_key,
                    "units": "metric",
                    "cnt": 56  # 7 days * 8 (3-hour intervals)
                }
            )
            data = response.json()

        # Aggregating Daily Forecasts
        daily_forecast = []
        for i in range(0, len(data["list"]), 8):
            day_data = data["list"][i:i+8]
            if not day_data:
                continue
            temps = [d["main"]["temp"] for d in day_data]
            rainfall = sum([d.get("rain", {}).get("3h", 0) for d in day_data])
            mid = len(day_data) // 2

            daily_forecast.append({
                "date": datetime.fromtimestamp(day_data[0]["dt"]).strftime("%Y-%m-%d"),
                "temp_min": min(temps),
                "temp_max": max(temps),
                "rainfall_mm": rainfall,
                "humidity": day_data[mid]["main"]["humidity"],
                "wind_speed": day_data[mid]["wind"]["speed"]
            })
        
        return daily_forecast[:7]

    async def fetch_openmeteo_forecast(self, location: dict):
        "Forecasts upto 10 days"
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": location["lat"],
                    "longitude": location["lon"],
                    "daily": [
                        "temperature_2m_max",
                        "temperature_2m_min",
                        "precipitation_sum",
                        "windspeed_10m_max"
                    ],
                    "timezone": "auto",
                    "forecast_days": 14
                }
            )

            data = response.json()

        daily = data.get("daily", {})

        forecast = []

        for i in range(len(daily.get("time", []))):
            forecast.append({
                "date": daily["time"][i],
                "temp_min": daily["temperature_2m_min"][i],
                "temp_max": daily["temperature_2m_max"][i],
                "rainfall_mm": daily["precipitation_sum"][i],
                "humidity": None,  # not available directly
                "wind_speed": daily["windspeed_10m_max"][i]
            })

        return forecast

    def generate_alerts(self, current, forecast):
        """Generate weather alerts"""
        
        alerts = []
        
        # Heatwave alert
        if current["temperature"] > 35:
            alerts.append({
                "type": "heatwave",
                "severity": "high",
                "message": f"High temperature ({current['temperature']}°C). Increase irrigation.",
                "recommendations": [
                    "Irrigate early morning or evening",
                    "Provide shade for sensitive crops"
                ]
            })
        
        # Heavy rainfall alert
        for day in forecast:
            if day["rainfall_mm"] > 50:
                alerts.append({
                    "type": "heavy_rainfall",
                    "severity": "medium",
                    "message": f"Heavy rainfall expected on {day['date']} ({day['rainfall_mm']}mm)",
                    "recommendations": [
                        "Ensure proper drainage",
                        "Postpone fertilizer application",
                        "Delay harvesting if possible"
                    ]
                })
        
        return alerts
    

    async def generate_farming_advisories(self):
        pass