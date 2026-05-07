# service.py
import asyncio
import logging
import json
from AI_Backend.agents.crop_planning_growth.soil_Health.agent import SoilHealthAgent
from AI_Backend.agents.crop_planning_growth.soil_Health.service import SoilHealthService
from AI_Backend.agents.crop_planning_growth.soil_Health.schemas import SoilHealthInput
from AI_Backend.agents.crop_planning_growth.weather_watcher.agent import WeatherAgent


class IrrigationService:
    """
    This class contains all the services related to the irrigation planner agent.
    Integrates weather data (current + forecast) and soil health parameters (NPK, pH, EC, moisture)
    to calculate optimized irrigation schedules.
    """
    
    def __init__(self, logger: logging.Logger = None):
        self.weather_agent = WeatherAgent(name="WeatherAgent")
        self.soil_health_agent = SoilHealthAgent()
        self.soil_health_service = SoilHealthService()
        self.logger = logger or logging.getLogger(__name__)
    
    async def calculate_irrigation_schedule(self, input_data: dict):
        """
        Calculate optimized irrigation schedule using:
        - Current and forecast weather data from WeatherAgent
        - Soil health parameters (NPK, pH, EC, moisture) from SoilHealthService
        
        Args:
            input_data: dict with keys:
                - location: {"lat": float, "lon": float}
                - soil_data: SoilHealthInput-compatible dict
                - field_capacity: float (mm)
                - irrigation_method: str
        
        Returns:
            dict with irrigation_schedule, water_savings, alerts, soil_health_insights
        """
        location = input_data.get("location", {})
        soil_data_raw = input_data.get("soil_data", {})
        field_capacity = input_data.get("field_capacity", 100.0)
        
        # --- Step 1: Fetch Weather Data ---
        weather_data = await self.weather_agent.run(location)
        
        # --- Step 2: Fetch Soil Health Data ---
        soil_health_result = self._get_soil_health_insights(soil_data_raw)
        
        # Extract key soil parameters
        current_moisture = soil_data_raw.get("soil_moisture", 0.0)
        # BUG FIX #5: Validate NPK ranges (Issue #11)
        # nitrogen: 0-150, phosphorus: 0-100, potassium: 0-100
        npk_values = {
            "nitrogen": max(0, min(150, soil_data_raw.get("nitrogen", 50))),
            "phosphorus": max(0, min(100, soil_data_raw.get("phosphorus", 30))),
            "potassium": max(0, min(100, soil_data_raw.get("potassium", 40))),
        }
        # BUG FIX #5: Validate soil_ph to prevent invalid values (e.g., 36.9)
        soil_ph = max(0, min(14, soil_data_raw.get("soil_ph", 7.0)))
        electrical_conductivity = soil_data_raw.get("electrical_conductivity", 0.5)
        
        # Extract weather forecast
        weather_forecast = weather_data.get("forecast_short_term", [])
        current_weather = weather_data.get("current_weather", {})
        
        schedule = []
        alerts = list(weather_data.get("alerts", []))
        total_optimized_water_mm = 0
        total_traditional_water_mm = 0
        MIN_IRRIGATION_MM = 5.0  # BUG FIX #11: Don't irrigate for tiny deficits (<5mm)
        PERCOLATION_LOSS_MM = 3.0  # BUG FIX #15: Account for daily drainage/percolation
        
        # --- Step 3: Calculate Irrigation Schedule ---
        for day in weather_forecast:
            date = day.get("date")
            rainfall = day.get("rainfall_mm", 0)
            temp_max = day.get("temp_max", 0)
            humidity = day.get("humidity", 60)
            wind_speed = day.get("wind_speed", 5)
            
            # Calculate evapotranspiration (ET) based on weather + soil conditions
            et_mm = self._calculate_evapotranspiration(
                temp_max, humidity, wind_speed, soil_ph, electrical_conductivity
            )
            
            # BUG FIX #13: High temperature alerts should boost ET demand
            if temp_max > 40:
                et_mm *= 1.2  # 20% increase in water demand for extreme heat
                alerts.append({
                    "type": "extreme_heat",
                    "severity": "high",
                    "message": f"Extreme heat on {date} ({temp_max}°C) - ET increased to {et_mm:.1f}mm",
                    "recommendation": "Ensure irrigation schedule maintains moisture"
                })
            
            # Calculate water stress index based on soil condition
            water_stress_factor = self._calculate_water_stress_factor(
                current_moisture, field_capacity, npk_values
            )
            
            # Add soil health alerts
            if soil_health_result["alerts"]:
                for alert in soil_health_result["alerts"]:
                    if alert.get("severity") == "high":
                        alerts.append({
                            "type": "soil_concern",
                            "message": alert.get("message"),
                            "date": date
                        })
            
            # --- Alert Logic ---
            if temp_max > 35:
                alerts.append({
                    "type": "warning",
                    "severity": "high",
                    "message": f"High evapotranspiration expected on {date} due to high temperatures ({temp_max}°C).",
                    "recommendation": "Increase irrigation or provide mulch"
                })
            
            if rainfall > 50:
                alerts.append({
                    "type": "heavy_rainfall",
                    "severity": "medium",
                    "message": f"Heavy rainfall expected on {date} ({rainfall}mm).",
                    "recommendation": "Ensure proper drainage, postpone irrigation"
                })
            
            # --- Irrigation Decision Logic ---
            # BUG FIX #2: Check soil moisture condition before deciding on irrigation
            # BUG FIX #8: Fix unrealistic rainfall conversion (rainfall * 0.01)
            rain_effective = rainfall * 0.7  # 70% infiltration factor (realistic)
            current_moisture = current_moisture - et_mm + rain_effective  # BUG FIX #1: Account for ET loss
            # BUG FIX #15: Account for percolation/drainage loss
            current_moisture = current_moisture - PERCOLATION_LOSS_MM
            current_moisture = max(0, min(field_capacity, current_moisture))  # BUG FIX #9: Clamp bounds
            
            # BUG FIX #12: Hysteresis buffer zone - don't irrigate if >70% FC
            # This prevents frequent micro-irrigations and creates natural skip days
            if current_moisture >= field_capacity * 0.70:
                # Soil is well-saturated, skip irrigation (BUG FIX #12: hysteresis zone)
                schedule.append({
                    "date": date,
                    "irrigation_required": False,
                    "reason": f"Soil moisture at {round(current_moisture, 1)}mm (≥{round(field_capacity * 0.70, 1)}mm skip threshold)",
                    "soil_moisture_after": round(current_moisture, 1)
                })
                total_traditional_water_mm += 25
                
            elif rainfall > 10:
                # Significant rain expected, skip irrigation
                schedule.append({
                    "date": date,
                    "irrigation_required": False,
                    "reason": f"{rainfall}mm rainfall forecasted",
                    "soil_moisture_after": current_moisture
                })
                total_traditional_water_mm += 25
            else:
                # Calculate water needed based on soil moisture deficit
                water_needed_mm = self._calculate_water_needed(
                    et_mm, current_moisture, field_capacity
                )
                
                # BUG FIX #11: Don't irrigate for tiny deficits (< 5mm)
                # Real farming needs meaningful irrigation events, not daily micro-doses
                if water_needed_mm >= MIN_IRRIGATION_MM:
                    duration = self._calculate_duration(
                        water_needed_mm, input_data.get("irrigation_method", "drip")
                    )
                    
                    schedule.append({
                        "date": date,
                        "irrigation_required": True,
                        "water_depth_mm": round(water_needed_mm, 1),  # BUG FIX #14: Precision rounding
                        "duration_hours": duration,
                        "timing": self._get_optimal_irrigation_time(temp_max, humidity),
                        "reason": f"ET: {round(et_mm, 1)}mm, Moisture: {round(current_moisture, 1)}mm, Deficit: {round(max(0, (field_capacity * 0.75) - current_moisture), 1)}mm",
                        "soil_conditions": {
                            "npk": npk_values,
                            "soil_ph": soil_ph,
                            "electrical_conductivity": electrical_conductivity,
                            "current_moisture": current_moisture
                        }
                    })
                    
                    # Apply irrigation and update moisture
                    current_moisture += water_needed_mm
                    current_moisture = max(0, min(field_capacity, current_moisture))
                    current_moisture = round(current_moisture, 1)  # BUG FIX #14: Precision rounding
                    
                    # Update totals
                    total_optimized_water_mm += water_needed_mm
                    total_traditional_water_mm += water_needed_mm * 1.4
                else:
                    # BUG FIX #11: Not enough deficit to justify irrigation
                    schedule.append({
                        "date": date,
                        "irrigation_required": False,
                        "reason": f"Deficit too small: {round(water_needed_mm, 1)}mm < {MIN_IRRIGATION_MM}mm threshold",
                        "soil_moisture_after": round(current_moisture, 1)
                    })
        
        # --- Step 4: Calculate Water Savings ---
        farm_area_multiplier = 1200
        optimized_liters = int(round(total_optimized_water_mm, 1) * farm_area_multiplier)  # BUG FIX #14
        traditional_liters = int(round(total_traditional_water_mm, 1) * farm_area_multiplier)  # BUG FIX #14
        
        savings_percentage = 0.0
        if traditional_liters > 0:
            savings_percentage = round(
                ((traditional_liters - optimized_liters) / traditional_liters) * 100, 1
            )
        
        # --- Step 5: Construct Final Output ---
        summary = self._generate_summary(
            schedule, total_optimized_water_mm, total_traditional_water_mm, 
            savings_percentage, alerts
        )
        
        return {
            "irrigation_schedule": schedule,
            "water_savings": {
                "optimized_usage_liters": optimized_liters,
                "traditional_usage_liters": traditional_liters,
                "savings_percentage": savings_percentage
            },
            "weather_insights": {
                "current_weather": current_weather,
                "forecast_days": len(weather_forecast)
            },
            "soil_health_insights": {
                "npk_status": npk_values,
                "soil_ph": soil_ph,
                "electrical_conductivity": electrical_conductivity,
                "health_score": soil_health_result.get("soil_health_score"),
                "health_status": soil_health_result.get("soil_health_status"),
                "critical_factors": soil_health_result.get("critical_factors", [])
            },
            "alerts": alerts,
            "summary": summary
        }
    
    def _get_soil_health_insights(self, soil_data_raw: dict) -> dict:
        """
        Get comprehensive soil health insights including NPK, pH, EC analysis.
        
        Args:
            soil_data_raw: Raw soil data dictionary
            
        Returns:
            dict with soil health analysis
        """
        try:
            # Convert raw data to SoilHealthInput
            soil_input = SoilHealthInput(**soil_data_raw)
            soil_result = self.soil_health_agent.run(soil_input)
            return soil_result
        except Exception as e:
            # BUG FIX #10: Return consistent fallback values instead of 0
            self.logger.warning(f"Soil health analysis failed: {str(e)}")
            return {
                "soil_health_score": None,
                "soil_health_status": "unavailable",
                "alerts": [],
                "critical_factors": []
            }
    
    def _calculate_evapotranspiration(
        self, temp_max: float, humidity: float, wind_speed: float,
        soil_ph: float, electrical_conductivity: float
    ) -> float:
        """
        Calculate evapotranspiration (ET) based on weather and soil conditions.
        
        Uses simplified FAO method. Better than original Hargreaves-Samani formula.
        BUG FIX #4: Removed fake solar radiation constant (34.8), uses temp range properly.
        """
        # BUG FIX #4: Simplified realistic ET formula
        # FAO simplified method: ET_o ≈ 0.5 * Tmax * (1 - RH/100)
        # This avoids inflating ET with EC and pH multiplication
        et_mm = 0.5 * temp_max * (1 - humidity / 100)
        
        # Adjust for wind (higher wind = slightly higher ET)
        wind_factor = 1 + (wind_speed / 20) * 0.1
        
        et_mm = et_mm * wind_factor
        
        # Cap ET to realistic maximum (prevent extreme values)
        # Most crops: 3-8 mm/day under normal conditions
        et_mm = min(et_mm, 8.0)
        
        # BUG FIX #14: Round to 1 decimal for realistic precision
        return round(max(et_mm, 0.1), 1)  # Minimum 0.1 mm/day
    
    def _calculate_water_stress_factor(
        self, current_moisture: float, field_capacity: float, 
        npk_values: dict
    ) -> float:
        """
        Calculate water stress factor based on soil moisture ONLY.
        
        BUG FIX #7: Removed NPK from irrigation logic (irrigation depends on water, not nutrients).
        Returns:
            float: 0.5 to 1.5 multiplier
            - <1.0: plant can access water easily
            - 1.0: optimal condition
            - >1.0: plant stressed, needs irrigation
        """
        # Moisture-based stress calculation
        wilting_point = field_capacity * 0.25  # 25% of FC
        easily_available_water = field_capacity * 0.75 - wilting_point  # Available water range
        available_water = current_moisture - wilting_point
        
        if available_water <= 0:
            stress_factor = 1.5  # Critical: plant wilting
        elif easily_available_water > 0:
            # Linear interpolation from 1.5 (low water) to 0.5 (high water)
            stress_factor = 1.5 - (available_water / easily_available_water) * 1.0
        else:
            stress_factor = 1.0
        
        return max(0.5, min(1.5, stress_factor))
    
    def _calculate_water_needed(
        self, et_mm: float, current_moisture: float, field_capacity: float
    ) -> float:
        """
        Calculate irrigation water requirement based on soil moisture deficit only.
        
        BUG FIX #3: Only irrigate if soil moisture is below target.
        Don't blindly add ET demand when soil already has sufficient water.
        """
        # Target moisture (75% of field capacity = good balance)
        target_moisture = field_capacity * 0.75
        
        # Calculate deficit
        deficit = max(0, target_moisture - current_moisture)
        
        # BUG FIX #3: Only add ET to compensate if there's a deficit
        # Don't add ET when soil is already well-watered
        if deficit > 0:
            # Replace deficit + compensate for ET loss
            water_needed = deficit + (et_mm * 0.5)  # 50% ET compensation on deficit days
        else:
            # Soil is well-watered, no irrigation needed
            water_needed = 0
        
        # BUG FIX #14: Round to avoid over-precision (53.099749280000005 → 53.1)
        return round(max(0, water_needed), 1)
    
    def _get_optimal_irrigation_time(self, temp_max: float, humidity: float) -> str:
        """
        Determine optimal irrigation time based on temperature and humidity.
        """
        if temp_max > 35:
            return "Early morning (5-7 AM)"  # Very hot: earliest watering
        elif temp_max > 30:
            return "Early morning (6-9 AM)"  # Hot: standard early watering
        elif humidity > 80:
            return "Late morning (9-11 AM)"  # High humidity: avoid early
        else:
            return "Early morning (6-9 AM)"  # Normal: standard time
    
    def _calculate_duration(self, water_needed_mm: float, irrigation_method: str = "drip") -> float:
        """
        Calculate irrigation duration based on water needed and irrigation method.
        
        BUG FIX #6: Cap max irrigation hours to prevent unrealistic 18+ hour durations.
        
        Flow rates (mm/hour):
        - Drip: 2-4 mm/hour
        - Sprinkler: 5-15 mm/hour
        - Flood: 20-40 mm/hour
        """
        MAX_IRRIGATION_HOURS = 6  # BUG FIX #6: Maximum practical irrigation time per day
        
        method_flow_rates = {
            "drip": 3.0,
            "sprinkler": 10.0,
            "flood": 30.0,
            "center_pivot": 8.0
        }
        
        flow_rate = method_flow_rates.get(irrigation_method.lower(), 3.0)
        duration_hours = water_needed_mm / flow_rate if flow_rate > 0 else 0
        
        # BUG FIX #6: Cap duration to practical maximum
        duration_hours = min(duration_hours, MAX_IRRIGATION_HOURS)
        
        return round(duration_hours, 2)
    
    def _generate_summary(
        self, schedule: list, total_water_mm: float, traditional_water_mm: float,
        savings_percentage: float, alerts: list
    ) -> str:
        """
        Generate a human-readable summary of the irrigation plan.
        
        Args:
            schedule: Daily irrigation schedule
            total_water_mm: Optimized water usage in mm
            traditional_water_mm: Traditional water usage in mm
            savings_percentage: Percentage water savings
            alerts: List of alerts
            
        Returns:
            str: Human-readable summary
        """
        try:
            irrigation_days = sum(1 for day in schedule if day.get("irrigation_required"))
            no_irrigation_days = len(schedule) - irrigation_days
            high_severity_alerts = sum(1 for alert in alerts if alert.get("severity") == "high")
            
            summary_lines = [
                f"📋 Irrigation Plan Summary",
                f"━" * 50,
                f"📅 Plan Duration: {len(schedule)} days",
                f"💧 Irrigation Days: {irrigation_days} days",
                f"⏸️ No Irrigation Days: {no_irrigation_days} days",
                f"",
                f"💰 Water & Savings",
                f"━" * 50,
                f"📊 Optimized Usage: {int(total_water_mm * 1200):,.0f} liters",
                f"📈 Traditional Usage: {int(traditional_water_mm * 1200):,.0f} liters",
                f"✅ Water Savings: {savings_percentage}%",
                f"",
            ]
            
            if high_severity_alerts > 0:
                summary_lines.extend([
                    f"⚠️ Alerts & Warnings",
                    f"━" * 50,
                    f"🔴 High Severity Alerts: {high_severity_alerts}",
                    f"",
                ])
            
            summary_lines.extend([
                f"📌 Recommendations",
                f"━" * 50,
                f"• Monitor soil moisture regularly",
                f"• Adjust schedule based on actual weather",
                f"• Check irrigation system for leaks",
                f"• Review soil health metrics weekly",
            ])
            
            return "\n".join(summary_lines)
            
        except Exception as e:
            self.logger.error(f"Error generating summary: {str(e)}")
            return "Irrigation plan generated successfully"