# agent.py
import asyncio
import json
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from AI_Backend.agents.base.base_agent import BaseAgent
from AI_Backend.agents.crop_planning_growth.crop_selector.service import CropSelectorService
from AI_Backend.agents.crop_planning_growth.crop_selector.schemas import (
    CropSelectorResponse,
    CropRecommendation,
    CropRotationPlan
)


class CropSelectorAgent(BaseAgent):
    def __init__(self, db: Optional[AsyncSession] = None):
        super().__init__("CropSelector")
        self.service = CropSelectorService(db=db, logger=self.logger)

    async def run(self, state: dict) -> dict:
        """
        Execute crop selection for the orchestrator
        
        Args:
            state: Orchestrator state containing farm/location info
            
        Returns:
            dict: Crop recommendations and metadata
        """
        try:
            response = await self.recoomend_crops(state)
            # Convert response to dict for orchestrator
            return {
                "crop_recommendation": response.dict() if hasattr(response, 'dict') else response,
                "status": "success"
            }
        except Exception as e:
            self.logger.error(f"Crop selection failed: {str(e)}")
            return {
                "crop_recommendation": None,
                "status": "error",
                "error": str(e)
            }

    async def recoomend_crops(self, input_data: dict) -> CropSelectorResponse:
        """
        Main Recommendation Logic
        
        Args:
            input_data (dict): Input payload containing farm_id, location, soil_data, etc.
            
        Returns:
            CropSelectorResponse: Structured response with recommendations
        """
        try:
            # Validate input
            self._validate_input(input_data)
            
            # Prepare payload
            payload = self._prepare_payload(input_data)
            
            # Fetch context data in parallel
            soil_data, weather_data = await self._fetch_context_data(payload)
            
            # Update payload with fetched data
            payload["soil_data"] = soil_data
            if weather_data:
                payload["weather"] = weather_data
            
            # Log unused fields (informational)
            self._log_unused_fields(payload)
            
            # Get ML predictions
            ml_scores = self.service.predict_crop_suitability(payload)
            self.logger.info(f"ML model returned {len(ml_scores)} crop recommendations")
            
            # Get LLM recommendations (with fallback)
            llm_recommendations = await self._get_llm_recommendations(
                soil_data, weather_data, ml_scores
            )
            
            # Build and return structured response
            return self._build_response(ml_scores, llm_recommendations)
            
        except ValueError as e:
            self.logger.error(f"Validation error: {str(e)}")
            raise
        except Exception as e:
            self.logger.error(f"Error in crop recommendations: {str(e)}", exc_info=True)
            # Return fallback response with ML scores only
            return self._build_fallback_response(ml_scores if 'ml_scores' in locals() else [])
    
    def _validate_input(self, input_data: dict):
        """Validate input data"""
        # Check if we have location dict or root-level lat/lon
        has_location_dict = input_data.get("location") and isinstance(input_data.get("location"), dict)
        has_root_coords = input_data.get("lat") is not None and input_data.get("lon") is not None
        has_farm_id = input_data.get("farm_id")
        
        if not (has_location_dict or has_root_coords or has_farm_id):
            raise ValueError("Either 'location' dict, root-level 'lat'/'lon', or 'farm_id' must be provided")
        
        # Validate location dict if provided
        if has_location_dict:
            location = input_data["location"]
            if "lat" not in location or "lon" not in location:
                raise ValueError("'location' must contain 'lat' and 'lon' keys")
            
            # Validate lat/lon ranges
            lat, lon = location["lat"], location["lon"]
            if not (-90 <= lat <= 90):
                raise ValueError(f"Invalid latitude: {lat}. Must be between -90 and 90")
            if not (-180 <= lon <= 180):
                raise ValueError(f"Invalid longitude: {lon}. Must be between -180 and 180")
        
        # Validate root-level lat/lon if provided
        if has_root_coords:
            lat, lon = input_data["lat"], input_data["lon"]
            if not (-90 <= lat <= 90):
                raise ValueError(f"Invalid latitude: {lat}. Must be between -90 and 90")
            if not (-180 <= lon <= 180):
                raise ValueError(f"Invalid longitude: {lon}. Must be between -180 and 180")
    
    def _prepare_payload(self, input_data: dict) -> dict:
        """Prepare and normalize payload"""
        payload = dict(input_data)
        
        # Normalize location: if root-level lat/lon exist but no location dict, create it
        if payload.get("location") is None and payload.get("lat") is not None and payload.get("lon") is not None:
            payload["location"] = {
                "lat": payload["lat"],
                "lon": payload["lon"]
            }
        
        # Handle root-level npk and ph (move to soil_data)
        root_npk = payload.get("npk")
        root_ph = payload.get("ph")
        
        if payload.get("soil_data") is None:
            payload["soil_data"] = {}
        
        if root_npk is not None:
            payload["soil_data"]["npk"] = root_npk
        if root_ph is not None:
            payload["soil_data"]["ph"] = root_ph
        
        return payload
    
    async def _fetch_context_data(self, payload: dict) -> tuple[dict, Optional[dict]]:
        """
        Fetch soil and weather data in parallel
        
        Returns:
            tuple: (soil_data, weather_data)
        """
        # Get initial soil data
        soil_data = payload.get("soil_data", {})
        
        # If no soil data but farm_id exists, fetch from DB
        if not soil_data and payload.get("farm_id"):
            try:
                soil_data = await self.service.fetch_soil_data_from_db(payload["farm_id"])
                if not soil_data:
                    soil_data = {}
            except Exception as e:
                self.logger.error(f"Failed to fetch soil data from DB: {e}")
                soil_data = {}
        
        # Create async tasks for parallel execution
        tasks = []
        task_names = []
        
        # Soil health agent enrichment task
        if soil_data:
            tasks.append(self.service.fetch_soil_data_from_agent(soil_data))
            task_names.append("soil_agent")
        else:
            tasks.append(asyncio.sleep(0, result={}))
            task_names.append("soil_agent")
        
        # Weather data task
        if payload.get("location"):
            tasks.append(self.service.get_weather_conditions(payload["location"]))
            task_names.append("weather_agent")
        else:
            tasks.append(asyncio.sleep(0, result=None))
            task_names.append("weather_agent")
        
        # Execute in parallel with error handling
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        enriched_soil_data = {}
        weather_data = None
        
        for idx, result in enumerate(results):
            task_name = task_names[idx]
            
            if isinstance(result, Exception):
                self.logger.error(f"{task_name} failed: {str(result)}")
                if task_name == "soil_agent":
                    enriched_soil_data = soil_data  # Fallback to original
                elif task_name == "weather_agent":
                    weather_data = None
            else:
                if task_name == "soil_agent":
                    enriched_soil_data = result or soil_data
                elif task_name == "weather_agent":
                    weather_data = result
        
        self.logger.info(f"Context data fetched - Soil: {bool(enriched_soil_data)}, Weather: {bool(weather_data)}")
        
        return enriched_soil_data, weather_data
    
    def _log_unused_fields(self, payload: dict):
        """Log fields that are not used in ML prediction"""
        unused_fields = []
        informational_fields = [
            "season", "water_availability", "farm_size_acres", 
            "farmer_goals", "previous_crops", "location", "farm_id"
        ]
        
        for field in informational_fields:
            if payload.get(field) is not None:
                unused_fields.append(field)
        
        if unused_fields:
            self.logger.info(
                f"Informational fields (not used in ML prediction): {', '.join(unused_fields)}. "
                "ML model uses: N, P, K, temperature, humidity, ph, rainfall."
            )
    
    async def _get_llm_recommendations(
        self, 
        soil_data: dict, 
        weather_data: Optional[dict], 
        ml_scores: list[tuple[str, float]]
    ) -> Optional[dict]:
        """Get LLM-based recommendations with error handling"""
        try:
            self.logger.info("Requesting LLM recommendations...")
            
            llm_result = await self.service.llm_ranking(
                soil_context=soil_data,
                weather_context=weather_data,
                crops={
                    "recommended_crops": [
                        {"crop_name": name, "suitability_score": score} 
                        for name, score in ml_scores
                    ]
                }
            )
            
            # llm_ranking now returns parsed dict or None
            if llm_result and isinstance(llm_result, dict):
                self.logger.info("LLM recommendations received and parsed successfully")
                return llm_result
            else:
                self.logger.warning("LLM returned no recommendations or invalid format")
                return None
            
        except Exception as e:
            self.logger.error(f"LLM recommendation failed: {str(e)}", exc_info=True)
            return None
    
    def _build_response(
        self, 
        ml_scores: list[tuple[str, float]], 
        llm_recommendations: Optional[dict]
    ) -> CropSelectorResponse:
        """
        Build structured response according to schema
        
        Args:
            ml_scores: List of (crop_name, score) tuples from ML model
            llm_recommendations: Parsed LLM response dict or None
            
        Returns:
            CropSelectorResponse: Properly structured response
        """
        recommended_crops = []
        llm_recommendation_str = None
        
        # If LLM recommendations are available, use them (enriched data)
        if llm_recommendations and isinstance(llm_recommendations, dict):
            llm_crops = llm_recommendations.get("recommended_crops", [])
            
            for crop_data in llm_crops:
                try:
                    recommended_crops.append(CropRecommendation(
                        crop_name=crop_data.get("crop_name", "Unknown"),
                        suitability_score=crop_data.get("confidence_score", crop_data.get("ml_score", 0.0)),
                        variety=None,  # Not provided by current LLM prompt
                        reasons=crop_data.get("suitability_reasons", []),
                        expected_yield=crop_data.get("expected_yield"),
                        estimated_profit=crop_data.get("estimated_profit"),
                        water_requirement=crop_data.get("water_requirement"),
                        duration_days=crop_data.get("duration_days"),
                        intercropping_options=None  # Not provided by current LLM prompt
                    ))
                except Exception as e:
                    self.logger.error(f"Error parsing LLM crop data: {e}")
                    continue
            
            # Format the LLM recommendations as readable JSON string
            llm_recommendation_str = json.dumps(llm_recommendations, indent=2, ensure_ascii=False)
            self.logger.info(f"Built response with {len(recommended_crops)} LLM-enriched recommendations")
        
        # Fallback to ML scores if LLM failed or returned no crops
        if not recommended_crops:
            self.logger.info("Using ML scores as primary recommendations")
            for crop_name, score in ml_scores[:10]:  # Top 10
                recommended_crops.append(CropRecommendation(
                    crop_name=crop_name,
                    suitability_score=float(score),
                    variety=None,
                    reasons=["Based on ML model prediction"],
                    expected_yield=None,
                    estimated_profit=None,
                    water_requirement=None,
                    duration_days=None,
                    intercropping_options=None
                ))
        
        # Build final response
        response = CropSelectorResponse(
            recommended_crops=recommended_crops,
            crop_rotation_plan=None,  # Can be implemented later
            LLM_Recommendation=llm_recommendation_str
        )
        
        return response
    
    def _build_fallback_response(self, ml_scores: list[tuple[str, float]]) -> CropSelectorResponse:
        """Build minimal fallback response when everything fails"""
        self.logger.warning("Building fallback response with limited data")
        
        if not ml_scores:
            # Complete fallback - return empty but valid response
            return CropSelectorResponse(
                recommended_crops=[],
                crop_rotation_plan=None,
                LLM_Recommendation=None
            )
        
        # Use ML scores
        recommended_crops = [
            CropRecommendation(
                crop_name=crop_name,
                suitability_score=float(score),
                variety=None,
                reasons=["Based on ML model prediction"],
                expected_yield=None,
                estimated_profit=None,
                water_requirement=None,
                duration_days=None,
                intercropping_options=None
            )
            for crop_name, score in ml_scores[:10]
        ]
        
        return CropSelectorResponse(
            recommended_crops=recommended_crops,
            crop_rotation_plan=None,
            LLM_Recommendation=None
        )