# service.py
from AI_Backend.agents.crop_planning_growth.crop_selector.model_loader import model, le
import numpy as np 
import asyncio
import logging
import json
import os
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from AI_Backend.agents.crop_planning_growth.weather_watcher.agent import WeatherAgent 
from AI_Backend.agents.crop_planning_growth.soil_Health.agent import SoilHealthAgent
from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq
from dotenv import load_dotenv

load_dotenv()

## Pending work (market context RAG in payload)

class CropSelectorService:
    
    def __init__(self, db: AsyncSession = None, logger: logging.Logger = None):
        self.db = db
        self.logger = logger or logging.getLogger(__name__)

        self.model = model
        self.le = le
        
        # Initialize Groq LLM
        groq_api_key = os.getenv("Groq_API")
        if not groq_api_key:
            self.logger.warning("Groq API key not found in environment variables. LLM features may not work.")
        
        self.llm = ChatGroq(
            model="llama-3.1-8b-instant",
            temperature=0.7,
            groq_api_key=groq_api_key,
            max_tokens=1024
        )


    def predict_crop_suitability(self,input_data:dict):
        "Ml model Prediction"

        features = self.extract_features(input_data)
        X = np.array([features])

        predictions = self.model.predict_proba(X)

        # Get top Crops 
        crop_scores = {}
        for idx,score in enumerate(predictions[0]):
            crop_scores[self.le.inverse_transform([idx])[0]] = float(score)

        return sorted(
            crop_scores.items(),
            key= lambda x:x[1],
            reverse=True
        )[:10]
    
    def extract_features(self, input_data: dict):
        """
        Extract and format features for ML model prediction
        Model expects: N, P, K, temperature, humidity, ph, rainfall (7 features)
        
        Args:
            input_data (dict): Dictionary containing soil_data and weather data
        
        Returns:
            list: Ordered feature list for XGBoost model [N, P, K, temperature, humidity, ph, rainfall]
        """
        soil = input_data.get("soil_data", {})
        weather = input_data.get("weather", {})
        
        # Extract NPK from soil data
        npk = soil.get("npk", {})
        n = npk.get("n", 0)
        p = npk.get("p", 0)
        k = npk.get("k", 0)
        
        # Extract weather features
        current_weather = weather.get("current_weather", {})
        temperature = current_weather.get("temperature", soil.get("temperature", 0))
        humidity = current_weather.get("humidity", soil.get("humidity", 0))
        rainfall = current_weather.get("rainfall_today", 0)  # From OpenWeather API
        
        # Extract soil pH
        ph = soil.get("ph", 0)
        
        # Features in exact order model was trained on
        features = [n, p, k, temperature, humidity, ph, rainfall]
        
        return features
    
    async def fetch_soil_data_from_db(self, farm_id: str) -> dict:
        """
        Fetch latest soil data from database for a farm
        
        Args:
            farm_id (str): UUID of the farm
            
        Returns:
            dict: Latest soil data record
        """
        if not self.db:
            self.logger.warning("Database session not available")
            return {}
        
        try:
            try:
                from app.models.soil_data import SoilData  # type: ignore
            except ModuleNotFoundError:
                self.logger.warning("SoilData model is not available (module 'app' not found). Skipping DB fetch.")
                return {}

            result = await self.db.execute(
                select(SoilData)
                .where(SoilData.farm_id == farm_id)
                .order_by(SoilData.recorded_at.desc())
                .limit(1)
            )
            soil_record = result.scalars().first()
            
            if soil_record:
                return {
                    "ph": soil_record.soil_ph,
                    "npk": {
                        "n": soil_record.nitrogen,
                        "p": soil_record.phosphorus,
                        "k": soil_record.potassium,
                    },
                    "moisture": soil_record.soil_moisture,
                    "temperature": soil_record.soil_temperature,
                    "ec": soil_record.electrical_conductivity,
                    "soil_type": soil_record.soil_type,
                    "recorded_at": soil_record.recorded_at.isoformat() if soil_record.recorded_at else None,
                }
            return {}
        except Exception as e:
            self.logger.error(f"Error fetching soil data from DB: {str(e)}")
            return {}
    
    async def fetch_soil_data_from_agent(self, soil_data: dict) -> dict:
        """
        Enrich soil data using Soil Health Agent analysis
        
        Args:
            soil_data (dict): Raw soil data
            
        Returns:
            dict: Enriched soil data with health score and recommendations
        """
        try:
            soil_health_agent = SoilHealthAgent()

            normalized = {
                "soil_ph": soil_data.get("ph", 6.5),
                "nitrogen": soil_data.get("npk", {}).get("n", 0),
                "phosphorus": soil_data.get("npk", {}).get("p", 0),
                "potassium": soil_data.get("npk", {}).get("k", 0),
                "soil_moisture": soil_data.get("moisture", 0),
                "electrical_conductivity": soil_data.get("ec", 0),
                "fertilizer_type": soil_data.get("fertilizer_type", None),
                "soil_type": soil_data.get("soil_type", "Loam"),
            }
            analysis = await soil_health_agent.run(normalized)
            self.logger.debug("SoilHealthAgent analysis completed")
            # Enrich soil data with agent analysis
            enriched_data = soil_data.copy()
            enriched_data.update({
                "health_score": analysis.get("soil_health_score", 0),
                "health_status": analysis.get("soil_health_status", "Unknown"),
                "alerts": analysis.get("alerts", []),
                "recommendations": analysis.get("suggestions", []),
            })
            
            return enriched_data
        except Exception as e:
            self.logger.error(f"Error in Soil Health Agent: {str(e)}")
            return soil_data
    
    async def get_weather_conditions(self, location: dict):
        """
        Fetch weather conditions from Weather Watcher Agent
        
        Args:
            location (dict): Location data with keys 'lat' and 'lon'
            
        Returns:
            dict: Weather data including current weather, forecasts, and alerts
        """
        weather_agent = WeatherAgent(name="WeatherWatcher")
        weather_data = await weather_agent.run(location)
        
        return {
            "current_weather": weather_data.get("current_weather"),
            "forecast_short_term": weather_data.get("forecast_short_term"),
            "forecast_long_term": weather_data.get("forecast_long_term"),
            "alerts": weather_data.get("alerts"),
        }
    
    async def llm_ranking(self, soil_context, weather_context, crops):
        """LLM Based final ranking with explanations"""
        try:
            self.logger.debug("Running LLM ranking")
            prompt = ChatPromptTemplate.from_messages([
                ("system", """You are an expert agricultural advisor with deep knowledge of:
                - Crop requirements and growth patterns
                - Soil-crop interactions and nutrient management
                - Weather impacts on crop yield
                - Market demand and profitability
                - Risk factors and mitigation strategies
                
                Analyze the soil properties, weather conditions, and ML suitability scores to provide expert recommendations.
                Consider: soil pH, NPK levels, temperature, humidity, and seasonal factors.
                
                For each crop, provide:
                1. Why this crop is suitable (soil conditions match, temperature is favorable, etc.)
                2. Expected yield range based on conditions
                3. Key risk factors and mitigation strategies
                4. Water and nutrient requirements
                5. Estimated profitability
                6. Recommended varieties for the region
                7. Best planting season and duration
                
                IMPORTANT: Only recommend crops with ML score > 0.1. Skip low-scoring crops.
                Rank by actual suitability, not just ML score.
                Provide actionable insights that help the farmer make decisions.
                """),
                ("user", """
                SOIL CONDITIONS:
                {soil_context}
                
                WEATHER CONDITIONS:
                {weather_context}
                
                ML RECOMMENDATIONS (with suitability scores):
                {crops}
                
                Please provide your expert ranking of the TOP 3-5 most suitable crops. 
                Return ONLY valid JSON with this structure:
                {{
                  "recommended_crops": [
                    {{
                      "rank": 1,
                      "crop_name": "crop name",
                      "ml_score": 0.95,
                      "suitability_reasons": ["reason 1", "reason 2", "reason 3"],
                      "expected_yield": "X-Y quintals/acre",
                      "water_requirement": "low/moderate/high",
                      "npk_requirement": "NPK ratio recommendation",
                      "key_risks": ["risk 1", "risk 2"],
                      "risk_mitigation": ["mitigation 1", "mitigation 2"],
                      "estimated_profit": "₹X/acre",
                      "recommended_varieties": ["variety 1", "variety 2"],
                      "best_planting_season": "season name",
                      "duration_days": number,
                      "confidence_score": 0.95
                    }}
                  ],
                  "analysis_summary": "Brief overall analysis of soil and weather conditions"
                }}
                
                Return ONLY the JSON object, no additional text.
                """)
            ])
            
            self.logger.info("Creating LLM chain for crop ranking...")
            chain = prompt | self.llm
            
            self.logger.info("Invoking LLM for crop ranking...")
            result = await chain.ainvoke({
                "crops": crops,
                "weather_context": weather_context,
                "soil_context": soil_context,
            })
            
            self.logger.info(f"LLM response received: {result.content}")
            
            # Parse and format the response for readability
            try:
                parsed_response = json.loads(result.content)
                self.logger.info("Successfully parsed LLM response as JSON")
                
                # Format for readability
                formatted_response = self._format_llm_response(parsed_response)
                return formatted_response
            except json.JSONDecodeError as je:
                self.logger.error(f"Failed to parse LLM response as JSON: {str(je)}")
                self.logger.error(f"Raw response: {result.content}")
                # Return None to trigger fallback to ML scores
                return None
                
        except Exception as e:
            self.logger.error(f"Error in llm_ranking: {str(e)}", exc_info=True)
            return None
    
    def _format_llm_response(self, response: dict) -> dict:
        """
        Format and validate LLM response for better readability and structure
        
        Args:
            response (dict): Parsed LLM response
            
        Returns:
            dict: Formatted response with clean structure
        """
        try:
            formatted = {
                "recommended_crops": [],
                "analysis_summary": response.get("analysis_summary", "")
            }
            
            crops = response.get("recommended_crops", [])
            for crop in crops:
                formatted_crop = {
                    "rank": crop.get("rank", 0),
                    "crop_name": crop.get("crop_name", "Unknown"),
                    "ml_score": crop.get("ml_score", 0),
                    "confidence_score": crop.get("confidence_score", 0),
                    "suitability_reasons": crop.get("suitability_reasons", []),
                    "expected_yield": crop.get("expected_yield", "N/A"),
                    "water_requirement": crop.get("water_requirement", "N/A"),
                    "npk_requirement": crop.get("npk_requirement", "N/A"),
                    "key_risks": crop.get("key_risks", []),
                    "risk_mitigation": crop.get("risk_mitigation", []),
                    "estimated_profit": crop.get("estimated_profit", "N/A"),
                    "recommended_varieties": crop.get("recommended_varieties", []),
                    "best_planting_season": crop.get("best_planting_season", "N/A"),
                    "duration_days": crop.get("duration_days", 0),
                }
                formatted["recommended_crops"].append(formatted_crop)
            
            self.logger.info(f"Formatted LLM response with {len(formatted['recommended_crops'])} crops")
            return formatted
            
        except Exception as e:
            self.logger.error(f"Error formatting LLM response: {str(e)}")
            return response


