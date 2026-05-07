# Irrigation Planner - plans irrigation based on weather soil conditions and best for best crop 
import json
import asyncio
from datetime import datetime
from AI_Backend.agents.base.base_agent import BaseAgent
from AI_Backend.agents.crop_planning_growth.irrigation_planner.service import IrrigationService
from AI_Backend.agents.crop_planning_growth.irrigation_planner.schemas import IrrigationPlannerResponse
from AI_Backend.services.soil_repository import SoilRepository

class IrrigationAgent(BaseAgent):
    """
    Irrigation planner agent - generates optimized irrigation schedules based on 
    weather, soil conditions, and crop requirements
    """
    def __init__(self):
        super().__init__("Irrigation_Planner")
        self.service = IrrigationService(logger=self.logger)

    async def run(self, input_data: dict) -> IrrigationPlannerResponse:
        """
        Main Recommendation Logic
        
        Args:
            input_data (dict): Input payload containing location, soil_data, etc.
            
        Returns:
            IrrigationPlannerResponse: Structured response with irrigation plan
        """
        try:
            self.logger.info("Starting Irrigation Planning Agent")
            
            # Validate input
            self._validate_input(input_data)
            
            # Prepare and normalize payload
            normalized_data = self._prepare_payload(input_data)
            
            # Prepare payload
            data = self.preprocess(normalized_data)
            
            # Calculate irrigation schedule
            result = await self.service.calculate_irrigation_schedule(input_data=data)
            
            # Build structured response
            response = self._build_response(result)
            
            # Add timestamp
            response = self.postprocess(response)
            
            self.logger.info("Irrigation plan generated successfully")
            return response
            
        except ValueError as e:
            self.logger.error(f"Validation error: {str(e)}")
            raise
        except Exception as e:
            self.logger.error(f"Error in irrigation planning: {str(e)}", exc_info=True)
            raise
    
    def _validate_input(self, input_data: dict):
        """Validate input data"""
        # Check if we have location dict or root-level lat/lon
        has_location_dict = input_data.get("location") and isinstance(input_data.get("location"), dict)
        has_root_coords = input_data.get("lat") is not None and input_data.get("lon") is not None
        
        if not (has_location_dict or has_root_coords):
            raise ValueError("'location' dict or root-level 'lat' and 'lon' is required")
        
        # Validate location dict if provided
        if has_location_dict:
            location = input_data["location"]
            if "lat" not in location or "lon" not in location:
                raise ValueError("'location' must contain 'lat' and 'lon' keys")
            
            lat, lon = location["lat"], location["lon"]
            if not (-90 <= lat <= 90):
                raise ValueError(f"Invalid latitude: {lat}. Must be between -90 and 90")
            if not (-180 <= lon <= 180):
                raise ValueError(f"Invalid longitude: {lon}. Must be between -180 and 180")
            self.logger.info(f"Input validation passed for location: {location}")
        
        # Validate root-level lat/lon if provided
        if has_root_coords:
            lat, lon = input_data["lat"], input_data["lon"]
            if not (-90 <= lat <= 90):
                raise ValueError(f"Invalid latitude: {lat}. Must be between -90 and 90")
            if not (-180 <= lon <= 180):
                raise ValueError(f"Invalid longitude: {lon}. Must be between -180 and 180")
            self.logger.info(f"Input validation passed for coordinates: lat={lat}, lon={lon}")
    
    def _prepare_payload(self, input_data: dict) -> dict:
        """Prepare and normalize payload"""
        payload = dict(input_data)
        
        # Normalize location: if root-level lat/lon exist but no location dict, create it
        if payload.get("location") is None and payload.get("lat") is not None and payload.get("lon") is not None:
            payload["location"] = {
                "lat": payload["lat"],
                "lon": payload["lon"]
            }
        
        return payload
    
    def _build_response(self, result: dict) -> IrrigationPlannerResponse:
        """
        Build structured response from service result
        
        Args:
            result (dict): Raw result from service
            
        Returns:
            IrrigationPlannerResponse: Properly structured response
        """
        try:
            # Extract and format schedule items
            schedule_items = []
            for item in result.get("irrigation_schedule", []):
                try:
                    # Convert dict to DailyScheduleItem with proper formatting
                    schedule_items.append({
                        "date": item.get("date"),
                        "irrigation_required": item.get("irrigation_required", False),
                        "water_depth_mm": item.get("water_depth_mm"),
                        "duration_hours": item.get("duration_hours"),
                        "timing": item.get("timing"),
                        "reason": item.get("reason", ""),
                        "soil_conditions": item.get("soil_conditions"),
                    })
                except Exception as e:
                    self.logger.warning(f"Error formatting schedule item: {e}")
                    continue
            
            # Extract water savings data
            water_savings = result.get("water_savings", {})
            
            # Extract weather insights
            weather_insights = result.get("weather_insights", {})
            
            # Extract soil health data
            soil_health = result.get("soil_health_insights", {})
            
            # Format alerts
            alerts = []
            for alert in result.get("alerts", []):
                try:
                    alerts.append({
                        "type": alert.get("type", "info"),
                        "severity": alert.get("severity"),
                        "message": alert.get("message", ""),
                        "date": alert.get("date"),
                        "recommendation": alert.get("recommendation"),
                    })
                except Exception as e:
                    self.logger.warning(f"Error formatting alert: {e}")
                    continue
            
            # Build response
            response = IrrigationPlannerResponse(
                irrigation_schedule=schedule_items,
                water_savings=water_savings,
                weather_insights=weather_insights,
                soil_health_insights=soil_health,
                alerts=alerts,
                processed_at=datetime.utcnow().isoformat(),
                summary=result.get("summary")
            )
            
            # Convert to dict for JSON serialization
            response_dict = response.model_dump()
            
            self.logger.info(f"Response built with {len(schedule_items)} schedule items and {len(alerts)} alerts")
            return response_dict
            
        except Exception as e:
            self.logger.error(f"Error building response: {str(e)}", exc_info=True)
            raise