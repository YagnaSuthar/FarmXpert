"""
IrrigationService 3.0 — FAO-56 root-zone water balance planning.

For each forecast day the root-zone depletion Dr is projected with the
day's crop water use (ETc = Kc · ET₀) and likely rain, then:

  heavy rain likely today ............... POSTPONE_STORM
  Dr near total available water ......... EMERGENCY_IRRIGATE  (before wilting)
  Dr near zero .......................... SKIP_SATURATED
  Dr within readily available water ..... SKIP_DEFICIT_SMALL  (no stress yet)
  Dr past RAW, likely rain will cover it  SKIP_RAIN           (wait for it)
  Dr past RAW ........................... IRRIGATE            (refill to capacity)

The net depth refills the root zone; the farmer applies the gross depth,
net ÷ the method's application efficiency (and the FAO-29 leaching
fraction when irrigation water EC is known). ET₀ is the Weather Watcher's
FAO-56 Penman–Monteith value, with Hargreaves–Samani as the fallback.
Rice follows the standing-water branch.

Output keys are unchanged from 2.x - the task-scheduler adapter reads them.
"""

from __future__ import annotations

import logging
import math
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from AI_Backend.agents.crop_planning_growth.irrigation_planner import water_balance as wb
from AI_Backend.agents.crop_planning_growth.irrigation_planner.config import (
    AGENT_ID,
    AGENT_VERSION,
    BASELINE_METHOD,
    CRITICAL_STAGE_P_FACTOR,
    CROP_ALIASES,
    CROP_CONFIG,
    DEFAULT_SOIL,
    DEFAULT_STAGE,
    EMERGENCY_DEPLETION,
    FROZEN_SOIL_TMAX_C,
    GENERIC_CROP,
    GROWTH_STAGES,
    HIGH_TEMP_C,
    HIGH_WIND_KMH,
    MAX_IRRIGATION_HOURS,
    METHODS,
    MIN_EVENT_MM,
    NEAR_FC_DEPLETION,
    PAST_SEASON_FACTOR,
    RAIN_LIKELY_PERCENT,
    RAIN_WAIT_DAYS,
    SOIL_ALIASES,
    SOIL_CONFIG,
    STORM_POSTPONE_MM,
    Decision,
    Reason,
)

# ET₀ used when neither Penman-Monteith nor temperatures are available.
_FALLBACK_ET0_MM = 5.0


class IrrigationService:
    """
    Stateless planner. Standalone it fetches weather and soil health itself;
    in the orchestrator the caller passes `weather_data` / `soil_health_data`.
    """

    AGENT_ID = AGENT_ID
    AGENT_VERSION = AGENT_VERSION

    def __init__(self, logger: Optional[logging.Logger] = None) -> None:
        self.logger = logger or logging.getLogger("farmxpert.irrigation")
        self._weather_agent = None
        self._soil_health_agent = None

    # ─────────────────────────────────────────────────────────────────────
    # PUBLIC ENTRY POINT
    # ─────────────────────────────────────────────────────────────────────

    async def calculate_irrigation_schedule(self, input_data: dict) -> dict:
        """Build the plan. Raises ValueError for an unknown crop, stage, soil or method."""
        warnings: List[str] = []
        soil_raw = dict(input_data.get("soil_data") or {})

        crop_key, crop_cfg = self._resolve_crop(input_data.get("crop"), warnings)
        stage = self._resolve_stage(input_data, crop_cfg, warnings)
        soil_key, soil_cfg = self._resolve_soil(
            input_data.get("soil_type") or soil_raw.get("soil_type"), warnings)
        method = self._resolve_method(input_data.get("irrigation_method"), crop_cfg,
                                      soil_cfg, warnings)
        area_ha = float(input_data.get("farm_area_hectares") or 1.0)
        horizon = int(input_data.get("planning_horizon_days") or 7)
        water_ec = input_data.get("water_ec_ds_m")

        # ── Root zone ─────────────────────────────────────────────────────
        root_depth = float(crop_cfg["root_depth_m"])
        fc_mm = 1000.0 * soil_cfg["theta_fc"] * root_depth
        wp_mm = 1000.0 * soil_cfg["theta_wp"] * root_depth
        if input_data.get("field_capacity") and input_data.get("wilting_point"):
            fc_mm, wp_mm = float(input_data["field_capacity"]), float(input_data["wilting_point"])
        taw = max(1.0, fc_mm - wp_mm)
        is_critical = stage in set(crop_cfg.get("critical_stages") or [])
        p_table = float(crop_cfg["p"]) * (CRITICAL_STAGE_P_FACTOR if is_critical else 1.0)
        kc = float(crop_cfg["kc_by_stage"].get(stage, 1.0))

        # ── Data sources ──────────────────────────────────────────────────
        weather = await self._get_weather(input_data)
        soil_health = await self._get_soil_health(input_data, soil_raw)
        days = (list(weather.get("forecast_short_term") or [])
                + list(weather.get("forecast_long_term") or []))[:horizon]
        lat = self._latitude(input_data, weather)

        # ── Current state ─────────────────────────────────────────────────
        moisture = input_data.get("soil_moisture_percent", soil_raw.get("soil_moisture"))
        depletion, measured = None, False
        if moisture is not None:
            depletion, problem = wb.depletion_from_sensor(
                float(moisture), soil_cfg["theta_fc"], soil_cfg["theta_wp"], root_depth)
            if problem:
                warnings.append(problem)
            measured = depletion is not None
        if depletion is None:
            depletion = 0.5 * p_table * taw
            warnings.append("No usable soil moisture reading - the plan assumes the root "
                            "zone is half-way to its irrigation point. A moisture sensor "
                            "makes the first days far more accurate.")

        soil_ec = input_data.get("electrical_conductivity", soil_raw.get("electrical_conductivity"))
        soil_ec = float(soil_ec) if soil_ec is not None else None
        salinity = self._salinity(crop_cfg, soil_ec, water_ec, warnings)

        # ── Daily plan ────────────────────────────────────────────────────
        is_paddy = crop_cfg.get("water_management") == "paddy"
        schedule: List[dict] = []
        et0_sources: set = set()
        net_total = gross_total = 0.0
        standing = float((crop_cfg.get("standing_water_mm") or {}).get("target", 75.0))

        for i, day in enumerate(days):
            et0, source = self._et0(day, lat)
            et0_sources.add(source)
            etc = kc * et0
            if is_paddy:
                item, standing, net = self._paddy_day(day, standing, etc, crop_cfg, soil_cfg,
                                                      stage, method, kc, et0)
                gross = net / METHODS[method]["efficiency"] if net else 0.0
            else:
                item, depletion, net, gross = self._upland_day(
                    day=day, following=days[i + 1:i + 1 + RAIN_WAIT_DAYS],
                    depletion=depletion, taw=taw, fc_mm=fc_mm, p_table=p_table,
                    et0=et0, etc=etc, kc=kc, stage=stage, is_critical=is_critical,
                    method=method, soil_cfg=soil_cfg, salinity=salinity,
                    dry_down=bool(crop_cfg.get("dry_down_at_maturity")))
            if item.get("water_depth_mm"):
                item["water_volume_liters"] = round(item["water_depth_mm"] * area_ha * 10_000, 0)
            schedule.append(item)
            net_total += net
            gross_total += gross

        if not days:
            warnings.append("No weather forecast available - no daily plan could be built. "
                            "Check the soil by hand and irrigate if the top 10 cm is dry.")
        if "hargreaves_fallback" in et0_sources:
            warnings.append("Crop water use estimated from temperatures (Hargreaves); "
                            "Penman-Monteith ET0 was not available for some days.")
        if "assumed" in et0_sources:
            warnings.append(f"No temperatures or ET0 for some days - {_FALLBACK_ET0_MM} mm/day "
                            "assumed. Treat those days as rough guidance.")

        alerts = self._normalise_weather_alerts(weather.get("alerts") or [])
        alerts += self._salinity_alerts(salinity, schedule)
        alerts += self._soil_health_alerts(soil_health, schedule)

        # ── Water savings vs flood irrigation of the same need ────────────
        area_m2 = area_ha * 10_000.0
        baseline_total = net_total / METHODS[BASELINE_METHOD]["efficiency"]
        savings = (round((baseline_total - gross_total) / baseline_total * 100, 1)
                   if baseline_total > 0 else 0.0)

        irrigation_days = sum(1 for s in schedule if s["irrigation_required"])
        next_event = next((s for s in schedule if s["irrigation_required"]), None)
        final_water = (fc_mm - depletion) if not is_paddy else standing

        return {
            "agent_id": self.AGENT_ID,
            "agent_version": self.AGENT_VERSION,
            "processed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "status": "ok" if days and (measured or is_paddy) else "partial",

            "irrigation_schedule": schedule,

            "crop_profile": {
                "crop": crop_key,
                "growth_stage": stage,
                "soil_type": soil_key,
                "water_management": crop_cfg.get("water_management", "upland"),
                "root_depth_m": root_depth,
                "field_capacity_mm": round(fc_mm, 1),
                "wilting_point_mm": round(wp_mm, 1),
                "total_available_water_mm": round(taw, 1),
                "readily_available_water_mm": round(p_table * taw, 1),
                "depletion_fraction_p": round(p_table, 2),
                "application_efficiency": METHODS[method]["efficiency"],
                "et0_source": self._et0_label(et0_sources),
                "preferred_method": method,
                "notes": [n for n in (crop_cfg.get("notes"), soil_cfg.get("notes")) if n],
            },

            "water_savings": {
                "optimized_usage_liters": round(gross_total * area_m2, 1),
                "traditional_usage_liters": round(baseline_total * area_m2, 1),
                "savings_percentage": max(0.0, savings),
            },

            "weather_insights": {
                "current_weather": weather.get("current_weather") or {},
                "forecast_days": len(days),
                "source": "weather_agent",
            },

            "soil_health_insights": {
                "npk_status": {k: soil_raw.get(k) for k in ("nitrogen", "phosphorus", "potassium")},
                "soil_ph": soil_raw.get("soil_ph"),
                "electrical_conductivity": soil_ec,
                "salinity_relative_yield_percent": salinity.get("relative_yield"),
                "health_score": soil_health.get("soil_health_score"),
                "health_status": soil_health.get("soil_health_status"),
                "critical_factors": soil_health.get("critical_factors") or [],
            },

            "summary": {
                "plan_horizon_days": len(schedule),
                "irrigation_days": irrigation_days,
                "skip_days": len(schedule) - irrigation_days,
                "total_water_mm": round(gross_total, 1),
                "total_water_liters": round(gross_total * area_m2, 1),
                "high_severity_alerts": sum(1 for a in alerts
                                            if a.get("severity") in ("high", "critical")),
                "headline": self._headline(crop_cfg, stage, irrigation_days, len(schedule),
                                           final_water, fc_mm, wp_mm, is_paddy),
            },
            "next_irrigation": {
                "date": next_event["date"] if next_event else None,
                "water_depth_mm": next_event.get("water_depth_mm") if next_event else None,
                "method": next_event.get("method") if next_event else method,
                "timing": next_event.get("timing") if next_event else None,
                "reason": (next_event.get("recommendation") if next_event
                           else "No irrigation needed in the planning horizon."),
            },
            "farmer_actions": self._farmer_actions(schedule, salinity, measured),
            "crop_specific_advice": self._crop_advice(crop_cfg, stage, soil_cfg, method),
            "alerts": alerts,

            "confidence": self._confidence(days, measured, et0_sources),
            "data_quality_score": self._data_quality(measured, soil_ec, days, et0_sources),
            "warnings": warnings + list(weather.get("warnings") or []),
        }

    # ─────────────────────────────────────────────────────────────────────
    # UPLAND DAY — FAO-56 depletion
    # ─────────────────────────────────────────────────────────────────────

    def _upland_day(self, *, day, following, depletion, taw, fc_mm, p_table, et0, etc,
                    kc, stage, is_critical, method, soil_cfg, salinity, dry_down=False):
        date_str = day.get("date")
        rain = _num(day.get("rainfall_mm")) or 0.0
        pop = _num(day.get("rain_probability_percent"))
        temp_max = _num(day.get("temp_max"))
        wind = _num(day.get("wind_speed")) or 0.0

        p = wb.depletion_fraction(p_table, etc)
        raw = p * taw
        rain_eff = wb.effective_rain(rain, pop)
        ks = wb.stress_coefficient(depletion, taw, p)
        projected = min(taw, max(0.0, depletion - rain_eff + ks * etc))

        reasons: List[dict] = []
        net = 0.0
        heavy_rain_likely = rain >= STORM_POSTPONE_MM and (pop is None or pop >= 50)

        frozen = temp_max is not None and temp_max <= FROZEN_SOIL_TMAX_C
        if frozen:
            code = Decision.POSTPONE_FROZEN
            reasons.append(_reason(Reason.FROZEN_SOIL, "temp_max", temp_max,
                                   FROZEN_SOIL_TMAX_C, "C", "high"))
        elif dry_down and stage == "harvest_ready":
            code = Decision.SKIP_CROP_MATURE
            reasons.append(_reason(Reason.CROP_MATURE, "growth_stage", None, None, None, "info"))
        elif heavy_rain_likely:
            code = Decision.POSTPONE_STORM
            reasons.append(_reason(Reason.STORM_FORECAST, "rainfall_mm", rain,
                                   STORM_POSTPONE_MM, "mm", "high"))
        elif projected >= EMERGENCY_DEPLETION * taw:
            code = Decision.EMERGENCY_IRRIGATE
            net = projected
            reasons.append(_reason(Reason.SOIL_BELOW_WILTING, "root_zone_depletion",
                                   projected, EMERGENCY_DEPLETION * taw, "mm", "critical"))
        elif projected <= NEAR_FC_DEPLETION * taw:
            code = Decision.SKIP_SATURATED
            reasons.append(_reason(Reason.SOIL_NEAR_FC, "root_zone_depletion",
                                   projected, NEAR_FC_DEPLETION * taw, "mm", "info"))
        elif projected <= raw:
            code = Decision.SKIP_DEFICIT_SMALL
            reasons.append(_reason(Reason.DEFICIT_BELOW_MIN, "root_zone_depletion",
                                   projected, raw, "mm", "low"))
        else:
            coming = sum(wb.effective_rain(_num(d.get("rainfall_mm")) or 0.0,
                                           _num(d.get("rain_probability_percent")))
                         for d in following
                         if (_num(d.get("rain_probability_percent")) or 0) >= RAIN_LIKELY_PERCENT)
            # Wait when likely rain brings the crop back inside its readily
            # available water - irrigating first would only waste water ahead
            # of the rain - provided the days of waiting cannot reach wilting.
            safe_to_wait = projected + len(following) * etc < EMERGENCY_DEPLETION * taw
            if following and coming > 0 and projected - coming <= raw and safe_to_wait:
                code = Decision.SKIP_RAIN
                reasons.append(_reason(Reason.RAIN_FORECAST, "likely_rain_next_days_mm",
                                       coming, projected, "mm", "low"))
            elif projected < MIN_EVENT_MM:
                code = Decision.SKIP_DEFICIT_SMALL
                reasons.append(_reason(Reason.DEFICIT_BELOW_MIN, "root_zone_depletion",
                                       projected, MIN_EVENT_MM, "mm", "low"))
            else:
                code = Decision.IRRIGATE
                net = projected
                reasons.append(_reason(Reason.SOIL_BELOW_TARGET, "root_zone_depletion",
                                       projected, raw, "mm", "medium"))

        if net > 0 and is_critical:
            reasons.append(_reason(Reason.CROP_CRITICAL_STAGE, "growth_stage", None, None,
                                   None, "high"))
        if kc < 0.5:
            reasons.append(_reason(Reason.CROP_KC_LOW, "kc", kc, 0.5, None, "low"))
        frequency = soil_cfg.get("irrigation_frequency")
        if frequency == "high":
            reasons.append(_reason(Reason.SOIL_TYPE_FAST_DRAIN, "soil_type", None, None, None, "info"))
        elif frequency == "low":
            reasons.append(_reason(Reason.SOIL_TYPE_SLOW_DRAIN, "soil_type", None, None, None, "info"))
        if net > 0 and temp_max is not None and temp_max >= HIGH_TEMP_C:
            reasons.append(_reason(Reason.HIGH_ET_HEAT, "temp_max", temp_max, HIGH_TEMP_C,
                                   "C", "high"))

        # Method for the day: sprinklers drift and apply unevenly in wind.
        chosen, alternative = method, None
        if net > 0 and method == "sprinkler" and wind > HIGH_WIND_KMH:
            chosen = "furrow"
            alternative = (f"Wind {wind:.0f} km/h is above {HIGH_WIND_KMH:.0f} km/h - sprinkling "
                           "would drift; irrigate by furrow or wait for a calm early morning.")
            reasons.append(_reason(Reason.WIND_SPRAY_LIMIT, "wind_speed", wind, HIGH_WIND_KMH,
                                   "km/h", "high"))

        gross, duration, sets = 0.0, None, None
        if net > 0:
            gross = net / METHODS[chosen]["efficiency"]
            lr = salinity.get("leaching_fraction")
            if lr:
                gross /= (1.0 - lr)
                reasons.append(_reason(Reason.SALINITY_LEACHING, "leaching_fraction",
                                       round(lr, 3), None, None, "medium"))
            hours = gross / METHODS[chosen]["rate_mm_h"]
            sets = max(1, math.ceil(hours / MAX_IRRIGATION_HOURS))
            duration = round(hours / sets, 2)
            if sets > 1:
                reasons.append(_reason(Reason.SPLIT_APPLICATION, "duration_hours",
                                       round(hours, 1), MAX_IRRIGATION_HOURS, "h", "info"))

        after = max(0.0, projected - net)
        timing = self._timing(chosen, temp_max) if net > 0 else None
        item = {
            "date": date_str,
            "decision_code": code,
            "irrigation_required": net > 0,
            "water_depth_mm": round(gross, 1) if net > 0 else None,
            "net_irrigation_mm": round(net, 1) if net > 0 else None,
            "sets": sets,
            "duration_hours": duration,
            "timing": timing,
            "method": chosen if net > 0 else None,
            "reasons": reasons,
            "recommendation": self._recommendation(code, gross, chosen, timing, sets,
                                                   is_critical),
            "alternative": alternative,
            "water_balance_mm": {
                "moisture_before": round(fc_mm - depletion, 1),
                "et0_mm": round(et0, 2),
                "etc_mm": round(ks * etc, 2),
                "effective_rain_mm": round(rain_eff, 1),
                "irrigation_mm": round(net, 1),
                "depletion_mm": round(projected, 1),
                "raw_mm": round(raw, 1),
                "moisture_after": round(fc_mm - after, 1),
            },
            "crop_coefficient_kc": round(kc, 2),
            "growth_stage": stage,
        }
        return item, after, net, gross

    # ─────────────────────────────────────────────────────────────────────
    # PADDY DAY — standing water
    # ─────────────────────────────────────────────────────────────────────

    def _paddy_day(self, day, standing, etc, crop_cfg, soil_cfg, stage, method, kc, et0):
        sw = crop_cfg.get("standing_water_mm") or {}
        target, low, high = (float(sw.get("target", 75)), float(sw.get("min", 50)),
                             float(sw.get("max", 100)))
        rain = _num(day.get("rainfall_mm")) or 0.0
        rain_eff = wb.effective_rain(rain, _num(day.get("rain_probability_percent")))
        seepage = float(soil_cfg["percolation_mm_d"])
        before = standing
        natural = max(0.0, standing + rain_eff - etc - seepage)
        reasons: List[dict] = []
        net = 0.0

        if stage in set(crop_cfg.get("drainage_stages") or []):
            code = Decision.DRAIN_FIELD
            reasons.append(_reason(Reason.PADDY_DRAINAGE_PHASE, "growth_stage", None, None,
                                   None, "high"))
            after = 0.0
            text = "Drain the field - withholding water now hardens the grain."
        elif natural >= low:
            code = Decision.SKIP_RAIN if rain_eff >= etc + seepage else Decision.SKIP_SATURATED
            reasons.append(_reason(Reason.RAIN_FORECAST if code == Decision.SKIP_RAIN
                                   else Reason.SOIL_NEAR_FC, "standing_water", natural, low,
                                   "mm", "info"))
            after = min(high, natural)
            text = f"Standing water ~{after:.0f} mm is enough - no irrigation today."
        else:
            code = Decision.MAINTAIN_FLOOD
            net = target - natural
            reasons.append(_reason(Reason.PADDY_FLOOD_MAINTAIN, "standing_water", natural, low,
                                   "mm", "medium"))
            after = target
            text = f"Top up with ~{net:.0f} mm to restore ~{target:.0f} mm standing water."

        gross = net / METHODS[method]["efficiency"] if net else 0.0
        item = {
            "date": day.get("date"), "decision_code": code,
            "irrigation_required": net > 0,
            "water_depth_mm": round(gross, 1) if net > 0 else None,
            "net_irrigation_mm": round(net, 1) if net > 0 else None,
            "sets": 1 if net > 0 else None,
            "duration_hours": (round(min(MAX_IRRIGATION_HOURS, gross / METHODS[method]["rate_mm_h"]), 2)
                               if net > 0 else None),
            "timing": "early_morning" if net > 0 else None,
            "method": method if net > 0 else None,
            "reasons": reasons, "recommendation": text, "alternative": None,
            "water_balance_mm": {
                "moisture_before": round(before, 1), "et0_mm": round(et0, 2),
                "etc_mm": round(etc, 2), "effective_rain_mm": round(rain_eff, 1),
                "percolation_mm": round(seepage, 1), "irrigation_mm": round(net, 1),
                "moisture_after": round(after, 1),
            },
            "crop_coefficient_kc": round(kc, 2),
            "growth_stage": stage,
        }
        return item, after, net

    # ─────────────────────────────────────────────────────────────────────
    # INPUT RESOLUTION
    # ─────────────────────────────────────────────────────────────────────

    @staticmethod
    def _resolve_crop(crop: Optional[str], warnings: List[str]) -> Tuple[str, dict]:
        if not crop or not str(crop).strip():
            warnings.append("No crop given - planned for a reference crop (Kc 1.0). Name the "
                            "crop for a plan that fits its roots and growth stage.")
            return "unspecified", GENERIC_CROP
        key = " ".join(str(crop).lower().replace("_", " ").split())
        key = CROP_ALIASES.get(key, key)
        if key not in CROP_CONFIG:
            raise ValueError(f"Unknown crop '{crop}'. Supported: {', '.join(sorted(CROP_CONFIG))}.")
        return key, CROP_CONFIG[key]

    @staticmethod
    def _resolve_stage(data: dict, crop_cfg: dict, warnings: List[str]) -> str:
        stage = data.get("growth_stage")
        if stage:
            key = str(stage).lower().strip().replace(" ", "_")
            if key not in GROWTH_STAGES:
                raise ValueError(f"Unknown growth stage '{stage}'. Use one of: "
                                 f"{', '.join(GROWTH_STAGES)}.")
            return key
        das = data.get("days_after_sowing")
        if das is None and data.get("sowing_date"):
            sown = data["sowing_date"]
            sown = sown if isinstance(sown, date) else date.fromisoformat(str(sown))
            das = (date.today() - sown).days
            if das < 0:
                raise ValueError("sowing_date is in the future.")
        if das is not None and not crop_cfg.get("season_days") and crop_cfg is not GENERIC_CROP:
            warnings.append(f"{crop_cfg.get('display_name', 'This crop')} is perennial - days "
                            "after sowing do not set its stage. Send growth_stage (e.g. flowering, "
                            f"fruiting); '{DEFAULT_STAGE}' assumed.")
            return DEFAULT_STAGE
        if das is not None and crop_cfg.get("season_days"):
            season = int(crop_cfg["season_days"])
            stage = wb.stage_from_days(int(das), season)
            warnings.append(f"Growth stage '{stage}' derived from {das} days after sowing.")
            if das > season * PAST_SEASON_FACTOR:
                warnings.append(f"{das} days after sowing is well past the ~{season}-day season - "
                                "the crop should already be harvested. Check the sowing date.")
            return stage
        if crop_cfg is not GENERIC_CROP:
            warnings.append(f"No growth stage given - '{DEFAULT_STAGE}' assumed. Send "
                            "growth_stage or days_after_sowing for the right crop coefficient.")
        return DEFAULT_STAGE

    @staticmethod
    def _resolve_soil(soil: Optional[str], warnings: List[str]) -> Tuple[str, dict]:
        if not soil or not str(soil).strip():
            warnings.append(f"No soil type given - '{DEFAULT_SOIL}' assumed.")
            return DEFAULT_SOIL, SOIL_CONFIG[DEFAULT_SOIL]
        raw = " ".join(str(soil).lower().split())
        key = SOIL_ALIASES.get(raw, raw.replace(" ", "_").replace("-", "_"))
        if key not in SOIL_CONFIG:
            raise ValueError(f"Unknown soil type '{soil}'. Supported: "
                             f"{', '.join(sorted(SOIL_CONFIG))}.")
        if raw in ("saline-alkaline", "saline alkaline"):
            warnings.append("Saline-alkaline soil planned with loam water properties; "
                            "salinity is handled through the EC reading.")
        return key, SOIL_CONFIG[key]

    @staticmethod
    def _resolve_method(hint: Optional[str], crop_cfg: dict, soil_cfg: dict,
                        warnings: List[str]) -> str:
        if hint:
            key = str(hint).lower().strip().replace(" ", "_")
            if key not in METHODS:
                raise ValueError(f"Unknown irrigation method '{hint}'. Supported: "
                                 f"{', '.join(METHODS)}.")
            for cfg, label in ((crop_cfg, crop_cfg.get("display_name", "this crop")),
                               (soil_cfg, soil_cfg.get("display_name", "this soil"))):
                if key in (cfg.get("discouraged_methods") or []):
                    warnings.append(f"'{key}' is discouraged for {label}.")
            return key
        crop_pref = crop_cfg.get("preferred_methods") or []
        soil_pref = soil_cfg.get("preferred_methods") or []
        both = [m for m in crop_pref if m in soil_pref]
        return (both or crop_pref or soil_pref or ["drip"])[0]

    # ─────────────────────────────────────────────────────────────────────
    # ET₀ AND SALINITY
    # ─────────────────────────────────────────────────────────────────────

    @staticmethod
    def _latitude(data: dict, weather: dict) -> Optional[float]:
        for loc in (data.get("location"), weather.get("location")):
            if isinstance(loc, dict) and loc.get("lat") is not None:
                return float(loc["lat"])
        return None

    @staticmethod
    def _et0(day: dict, lat: Optional[float]) -> Tuple[float, str]:
        et0 = _num(day.get("et0_mm"))
        if et0 is not None and 0 <= et0 <= 20:
            return et0, "fao56_penman_monteith"
        tmin, tmax = _num(day.get("temp_min")), _num(day.get("temp_max"))
        if tmin is not None and tmax is not None and lat is not None and day.get("date"):
            try:
                return (wb.et0_hargreaves(tmin, tmax, lat, date.fromisoformat(str(day["date"]))),
                        "hargreaves_fallback")
            except ValueError:
                pass
        return _FALLBACK_ET0_MM, "assumed"

    @staticmethod
    def _et0_label(sources: set) -> str:
        for label in ("assumed", "hargreaves_fallback", "fao56_penman_monteith"):
            if label in sources:
                return label if label != "assumed" else "none"
        return "none"

    @staticmethod
    def _salinity(crop_cfg: dict, soil_ec: Optional[float], water_ec: Optional[float],
                  warnings: List[str]) -> dict:
        tolerance = crop_cfg.get("salinity")
        out: Dict[str, Any] = {"soil_ec": soil_ec, "water_ec": water_ec}
        if not tolerance:
            return out
        out["threshold"] = tolerance["threshold"]
        if soil_ec is not None:
            out["relative_yield"] = round(wb.relative_yield_percent(
                soil_ec, tolerance["threshold"], tolerance["slope"]), 1)
        if water_ec is not None:
            lr = wb.leaching_requirement(float(water_ec), tolerance["threshold"])
            if lr is None:
                warnings.append(f"Irrigation water EC {water_ec} dS/m is too saline for "
                                f"{crop_cfg['display_name']} to be leached - find a better "
                                "water source or blend it.")
            else:
                out["leaching_fraction"] = lr
        return out

    @staticmethod
    def _salinity_alerts(salinity: dict, schedule: List[dict]) -> List[dict]:
        rel = salinity.get("relative_yield")
        if rel is None or rel >= 100.0:
            return []
        severity = "critical" if rel < 50 else "high" if rel < 80 else "medium"
        return [{
            "type": "salinity", "severity": severity,
            "date": schedule[0]["date"] if schedule else None,
            "message": (f"Soil EC {salinity['soil_ec']:.1f} dS/m is above this crop's "
                        f"{salinity['threshold']:.1f} dS/m tolerance - expected yield about "
                        f"{rel:.0f}% of a non-saline field (Maas-Hoffman)."),
            "recommendation": ("Confirm with a lab saturated-paste ECe test; leach with good-"
                               "quality water and send water_ec_ds_m to size the leaching dose."),
        }]

    @staticmethod
    def _soil_health_alerts(soil_health: dict, schedule: List[dict]) -> List[dict]:
        out = []
        for a in soil_health.get("alerts") or soil_health.get("soil_alerts") or []:
            severity = (a.get("severity") or "").lower()
            if severity in ("high", "critical"):
                out.append({"type": "soil_concern", "severity": severity,
                            "message": a.get("message", a.get("type", "soil alert")),
                            "date": schedule[0]["date"] if schedule else None,
                            "recommendation": "review_soil_health_advisory"})
        return out

    # ─────────────────────────────────────────────────────────────────────
    # DATA SOURCES
    # ─────────────────────────────────────────────────────────────────────

    async def _get_weather(self, data: dict) -> dict:
        pre = data.get("weather_data")
        if pre:
            return pre if isinstance(pre, dict) else (pre.model_dump() if hasattr(pre, "model_dump") else {})
        location = data.get("location")
        if not location:
            return {"forecast_short_term": [], "alerts": [],
                    "warnings": ["No location given - weather forecast not fetched."]}
        if self._weather_agent is None:
            from AI_Backend.agents.crop_planning_growth.weather_watcher.agent import WeatherAgent
            self._weather_agent = WeatherAgent("WeatherWatcher")
        try:
            return await self._weather_agent.run(location)
        except Exception as exc:  # noqa: BLE001 - weather must never fail the plan
            self.logger.warning("Weather fetch failed: %s", exc)
            return {"forecast_short_term": [], "alerts": [],
                    "warnings": ["Weather forecast unavailable."]}

    async def _get_soil_health(self, data: dict, soil_raw: dict) -> dict:
        pre = data.get("soil_health_data")
        if pre:
            return pre if isinstance(pre, dict) else (pre.model_dump() if hasattr(pre, "model_dump") else {})
        if soil_raw.get("soil_ph") is None or soil_raw.get("electrical_conductivity") is None:
            return {}   # the Soil Health agent needs at least pH and EC
        soil_raw = {**{k: data[k] for k in ("soil_type",) if data.get(k)},
                    "crop_type": data.get("crop"), **soil_raw}
        if self._soil_health_agent is None:
            from AI_Backend.agents.crop_planning_growth.soil_health.agent import SoilHealthAgent
            self._soil_health_agent = SoilHealthAgent()
        try:
            return await self._soil_health_agent.run(soil_raw)
        except Exception as exc:  # noqa: BLE001
            self.logger.warning("Soil health analysis failed: %s", exc)
            return {}

    # ─────────────────────────────────────────────────────────────────────
    # FARMER-FACING TEXT
    # ─────────────────────────────────────────────────────────────────────

    @staticmethod
    def _timing(method: str, temp_max: Optional[float]) -> str:
        """Sprinklers in the calm early morning (foliage dries before night);
        surface methods at night in heat to cut evaporation."""
        hot = temp_max is not None and temp_max >= HIGH_TEMP_C
        if method in ("sprinkler", "center_pivot"):
            return "early_morning"
        if method in ("flood", "furrow", "border", "basin") and hot:
            return "night"
        return "evening" if hot else "early_morning"

    @staticmethod
    def _recommendation(code, gross, method, timing, sets, is_critical) -> str:
        if code == Decision.SKIP_RAIN:
            return "Skip - likely rain in the next days will refill the root zone."
        if code == Decision.SKIP_SATURATED:
            return "Skip - the root zone is close to field capacity."
        if code == Decision.SKIP_DEFICIT_SMALL:
            return "Skip - the crop still has easily available water."
        if code == Decision.POSTPONE_STORM:
            return "Postpone - heavy rain is likely today; keep drains open."
        if code == Decision.POSTPONE_FROZEN:
            return "Do not irrigate - the ground is frozen; water will pond and ice. Wait for a thaw."
        if code == Decision.SKIP_CROP_MATURE:
            return "Stop irrigating - the crop is maturing; dry soil hastens ripening and harvest."
        when = f" in the {timing.replace('_', ' ')}" if timing else ""
        split = f", split over {sets} days" if sets and sets > 1 else ""
        if code == Decision.EMERGENCY_IRRIGATE:
            return (f"URGENT: apply ~{gross:.0f} mm by {method}{when}{split} - the crop is "
                    "close to wilting.")
        tail = " Critical growth stage - do not skip." if is_critical else ""
        return f"Apply ~{gross:.0f} mm by {method}{when}{split}.{tail}"

    @staticmethod
    def _headline(crop_cfg, stage, irrigation_days, total, water_mm, fc, wp, is_paddy) -> str:
        crop = crop_cfg.get("display_name", "Crop")
        if is_paddy:
            state = f"standing water ~{water_mm:.0f} mm"
        else:
            available = (water_mm - wp) / (fc - wp) * 100 if fc > wp else 0
            state = f"soil holds {max(0, available):.0f}% of its available water"
        return f"{crop} at {stage} stage: {irrigation_days} of {total} days need irrigation; {state}."

    @staticmethod
    def _farmer_actions(schedule, salinity, measured) -> List[dict]:
        actions: List[dict] = []
        if schedule and schedule[0]["irrigation_required"]:
            d = schedule[0]
            actions.append({
                "action_code": "IRRIGATE_TODAY",
                "priority": "critical" if d["decision_code"] == Decision.EMERGENCY_IRRIGATE else "high",
                "summary": f"Apply {d['water_depth_mm']:.0f} mm by {d['method']} today.",
                "target_date": d["date"],
            })
        if not measured:
            actions.append({"action_code": "INSPECT_SOIL", "priority": "medium",
                            "summary": "No moisture reading - check the soil at root depth "
                                       "before irrigating."})
        if (salinity.get("relative_yield") or 100) < 100:
            actions.append({"action_code": "LEACH_SALT", "priority": "medium",
                            "summary": "Soil salinity is limiting yield - test ECe and plan a "
                                       "leaching irrigation with good-quality water."})
        if any(s["decision_code"] == Decision.DRAIN_FIELD for s in schedule):
            actions.append({"action_code": "DRAIN_FIELD", "priority": "high",
                            "summary": "Drain the field this week - the crop is in its "
                                       "drainage phase."})
        if not actions:
            actions.append({"action_code": "NO_ACTION", "priority": "low",
                            "summary": "No urgent action - follow the schedule."})
        return actions

    @staticmethod
    def _crop_advice(crop_cfg, stage, soil_cfg, method) -> List[str]:
        crop = crop_cfg.get("display_name", "The crop")
        tips: List[str] = []
        if crop_cfg.get("water_management") == "paddy":
            tips.append(f"{crop}: keep 50-100 mm standing water outside drainage phases.")
        if stage in (crop_cfg.get("critical_stages") or []):
            tips.append(f"{crop} is at a yield-critical stage ({stage}) - irrigation starts "
                        "earlier than usual to avoid any stress.")
        if soil_cfg.get("irrigation_frequency") == "high":
            tips.append(f"{soil_cfg['display_name']} holds little water - irrigate little and often.")
        elif soil_cfg.get("irrigation_frequency") == "low":
            tips.append(f"{soil_cfg['display_name']} holds water well - irrigate less often, deeper.")
        efficiency = METHODS[method]["efficiency"]
        if efficiency < 0.7:
            tips.append(f"{method.title()} irrigation delivers only ~{efficiency:.0%} of the water "
                        "to the roots; drip (~90%) would cut water use sharply.")
        return tips

    @staticmethod
    def _confidence(days, measured, sources) -> float:
        score = 0.4
        if days:
            score += 0.2
        if measured:
            score += 0.25
        if sources == {"fao56_penman_monteith"}:
            score += 0.15
        return round(min(1.0, score), 2)

    @staticmethod
    def _data_quality(measured, soil_ec, days, sources) -> float:
        score = 1.0
        if not measured:
            score -= 0.3
        if soil_ec is None:
            score -= 0.1
        if not days:
            score -= 0.4
        if "assumed" in sources:
            score -= 0.2
        return round(max(0.0, score), 2)

    @staticmethod
    def _normalise_weather_alerts(alerts: List[dict]) -> List[dict]:
        return [{
            "type": a.get("type", "warning"),
            "severity": (a.get("severity") or "medium").lower(),
            "message": a.get("message", ""),
            "date": a.get("date"),
            "recommendation": ((a.get("recommendations") or [None])[0]
                               if a.get("recommendations") else a.get("recommendation")),
        } for a in alerts or []]


def _num(value: Any) -> Optional[float]:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _reason(code, factor, value, threshold, unit, severity) -> dict:
    return {"code": code, "factor": factor,
            "value": round(value, 2) if isinstance(value, float) else value,
            "threshold": round(threshold, 2) if isinstance(threshold, float) else threshold,
            "unit": unit, "severity": severity}
