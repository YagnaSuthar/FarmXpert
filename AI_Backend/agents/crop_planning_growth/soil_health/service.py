"""
SoilHealthService — rule-based soil analysis against agronomic standards.

Pipeline (the agent owns the order):
  validate → analyze_soil → analyze_weather → detect_conflicts → score →
  fertilizers → suggestions → summary → confidence → data quality

v3.0:
  • Moisture is read as plant-available water for the soil type (FAO-56
    field capacity / wilting point), with the crop's own depletion fraction
    deciding when stress begins. The same 25 % reading is field capacity on
    a loam and near wilting on a clay.
  • Salinity is judged against the crop's Maas-Hoffman tolerance and reports
    the expected yield; a tolerant crop is not alarmed at 2.5 dS/m.
  • An extreme value escalates only its own alert, not every alert.
  • Legumes get Rhizobium advice for low nitrogen, saline soils get leaching
    (gypsum only when sodic), and crop-specific practice is suggested.
  • Unknown crop or soil names are reported, never crash the analysis.
"""

from __future__ import annotations

from typing import Any, Optional

from AI_Backend.agents.crop_planning_growth.soil_health.config import (
    ALERT_DEFINITIONS,
    ALERT_THRESHOLDS,
    CONFLICT_DETECTION_MAP,
    CROP_ALIASES,
    CROP_CONFIG,
    CROP_SCORE_WEIGHT_OVERRIDES,
    DATA_QUALITY_WEIGHTS,
    DEFAULT_SOIL_FOR_MOISTURE,
    FERTILIZER_ALIASES,
    FERTILIZER_RECOMMENDATION_MAP,
    GLOBAL_OPTIMAL_RANGES,
    LEGUME_LOW_N_RECOMMENDATION,
    MOISTURE_RULES,
    MULTI_CONDITION_SUGGESTIONS,
    NITROGEN_THRESHOLDS,
    SCORE_BANDS,
    SCORE_WEIGHTS,
    SEVERITY_RULES,
    SINGLE_ALERT_SUGGESTIONS,
    SENSOR_NUTRIENT_IMPACT_FACTOR,
    SENSOR_NUTRIENT_PARAMETERS,
    SENSOR_NUTRIENT_SEVERITY_CAP,
    SENSOR_NUTRIENT_SUFFIX,
    SODIC_PH,
    SOIL_ALIASES,
    SOIL_TEST_FIRST_RECOMMENDATION,
    SOIL_HYDRAULICS,
    SOIL_TYPE_CONFIG,
    SUMMARY_FRAGMENTS,
    SUMMARY_TEMPLATES,
    VALID_RANGES,
    WEATHER_IMPACT_RULES,
    _IRRIGATION_CROPS,
)

# Schema field → config parameter key
_SCHEMA_TO_CONFIG: dict[str, str] = {
    "soil_moisture":           "moisture",
    "soil_temperature":        "temperature",
    "soil_ph":                 "ph",
    "nitrogen":                "nitrogen",
    "phosphorus":              "phosphorus",
    "potassium":               "potassium",
    "electrical_conductivity": "ec",
    "air_temperature":         "air_temperature",
    "air_humidity":            "humidity",
    "rainfall":                "rainfall",
}
_CONFIG_TO_SCHEMA = {v: k for k, v in _SCHEMA_TO_CONFIG.items()}

# Parameter → (low, critical low, high, critical high) alert codes.
# Moisture is handled separately (plant-available water).
_SOIL_PARAM_ALERT_MAP: dict[str, tuple] = {
    "ph":          ("LOW_PH",        "CRITICAL_LOW_PH", "HIGH_PH",        "CRITICAL_HIGH_PH"),
    "nitrogen":    ("LOW_N",         "CRITICAL_LOW_N",  "HIGH_N",         "CRITICAL_HIGH_N"),
    "phosphorus":  ("LOW_P",         "CRITICAL_LOW_P",  "HIGH_P",         None),
    "potassium":   ("LOW_K",         "CRITICAL_LOW_K",  "HIGH_K",         None),
    "ec":          ("LOW_EC",        None,              "HIGH_EC",        "CRITICAL_HIGH_EC"),
    "temperature": ("LOW_SOIL_TEMP", None,              "HIGH_SOIL_TEMP", None),
}

_SEVERITY_RANK: dict[str, int] = SEVERITY_RULES["severity_rank"]
_SOFT_IMPACT_CAP = 4

_DEFAULT_SUGGESTION = ("All soil parameters are within acceptable range. Continue regular "
                       "monitoring and maintain current management practices.")


def canonical_crop(name: Optional[str]) -> Optional[str]:
    """Known crop key for `name`, or None."""
    if not name:
        return None
    key = " ".join(str(name).lower().replace("_", " ").split())
    key = CROP_ALIASES.get(key, key)
    return key if key in CROP_CONFIG else None


def canonical_soil(name: Optional[str]) -> Optional[str]:
    """Known soil key for `name`, or None."""
    if not name:
        return None
    raw = " ".join(str(name).lower().split())
    key = SOIL_ALIASES.get(raw, raw.replace(" ", "_").replace("-", "_"))
    return key if key in SOIL_TYPE_CONFIG else None


class SoilHealthService:
    """Stateless analysis engine; every method is a pure function of its input."""

    # ─────────────────────────────────────────────────────────────────────────
    # 1. Validation
    # ─────────────────────────────────────────────────────────────────────────

    def validate(self, data) -> tuple[bool, list[dict]]:
        errors: list[dict] = []
        for schema_field, config_key in _SCHEMA_TO_CONFIG.items():
            val = getattr(data, schema_field, None)
            bounds = VALID_RANGES.get(config_key)
            if val is None or not bounds:
                continue
            if not bounds["min"] <= val <= bounds["max"]:
                errors.append({
                    "field": schema_field, "config_key": config_key, "value": val,
                    "valid_range": [bounds["min"], bounds["max"]],
                    "message": f"'{schema_field}' value {val} is outside the plausible range "
                               f"[{bounds['min']}, {bounds['max']}] - check the sensor.",
                })
        for field, known, resolve in (("crop_type", sorted(CROP_CONFIG), canonical_crop),
                                      ("soil_type", sorted(SOIL_TYPE_CONFIG), canonical_soil)):
            val = getattr(data, field, None)
            if val and resolve(val) is None:
                errors.append({
                    "field": field, "value": None, "allowed": known,
                    "message": f"'{field}' value '{val}' is not recognised - general ranges "
                               f"used. Known: {', '.join(known)}.",
                })
        return (not errors, errors)

    # ─────────────────────────────────────────────────────────────────────────
    # 2. Soil analysis
    # ─────────────────────────────────────────────────────────────────────────

    def analyze_soil(self, data) -> list[dict]:
        """Soft alerts near the crop's optimum; hard alerts at agronomic risk
        thresholds; moisture and salinity judged for this soil and this crop."""
        crop = canonical_crop(getattr(data, "crop_type", None))
        optimal = self._optimal_ranges(crop)
        critical = SEVERITY_RULES["critical_thresholds"]
        alerts: list[dict] = []
        soft: list[dict] = []

        # Soft layer: outside the crop's optimum by more than a 10 % buffer.
        for key, (low_code, _, high_code, _) in _SOIL_PARAM_ALERT_MAP.items():
            if key in ("temperature", "ec"):
                continue   # temperature: hard threshold only; EC: crop salt tolerance below
            val = self._value(data, key)
            band = optimal.get(key)
            if val is None or not band:
                continue
            tolerance = (band["max"] - band["min"]) * 0.10
            if val < band["min"] - tolerance and low_code:
                soft.append(self._soft(low_code, val, band["min"], "below", key))
            elif val > band["max"] + tolerance and high_code:
                soft.append(self._soft(high_code, val, band["max"], "above", key))

        # Hard layer: agronomic risk thresholds.
        for key, (low_code, crit_low, high_code, crit_high) in _SOIL_PARAM_ALERT_MAP.items():
            if key == "ec" and crop and CROP_CONFIG[crop].get("salinity"):
                continue   # judged against the crop's own tolerance below
            val = self._value(data, key)
            thresholds = ALERT_THRESHOLDS.get(key)
            if val is None or not thresholds:
                continue
            ct = critical.get(key, {})
            low_thr, high_thr = thresholds.get("low"), thresholds.get("high")
            if low_thr is not None and val < low_thr:
                is_crit = crit_low is not None and ct.get("low") is not None and val < ct["low"]
                code = crit_low if is_crit else low_code
                if code:
                    alert = self._build_alert(code, val, low_thr, "below", key)
                    if not is_crit:
                        alert["severity"] = self._deviation_severity(low_thr, val)
                    alerts.append(alert)
            elif high_thr is not None and val > high_thr:
                is_crit = crit_high is not None and ct.get("high") is not None and val > ct["high"]
                code = crit_high if is_crit else high_code
                if code:
                    alert = self._build_alert(code, val, high_thr, "above", key)
                    if key == "nitrogen" and not is_crit:
                        alert.update(self._nitrogen_tier(val, alert))
                    elif not is_crit:
                        alert["severity"] = self._deviation_severity(high_thr, val)
                    alerts.append(alert)

        salinity = self._salinity_alert(data, crop)
        if salinity:
            alerts.append(salinity)
        alerts.extend(self._moisture_alerts(data, crop))

        # An extreme reading makes its own alert critical - not every alert.
        extreme = SEVERITY_RULES["extreme_value_override"]
        ph, ec = self._value(data, "ph"), self._value(data, "ec")
        for a in alerts:
            if ((a.get("parameter") == "ph" and ph is not None and ph < extreme["ph_below"])
                    or (a.get("parameter") == "ec" and ec is not None and ec > extreme["ec_above"])):
                a["severity"] = "critical"
                a["extreme_override"] = True

        covered = {a["parameter"] for a in alerts}
        alerts.extend(s for s in soft if s["parameter"] not in covered)

        if getattr(data, "nutrient_source", "sensor") == "sensor":
            cap = _SEVERITY_RANK[SENSOR_NUTRIENT_SEVERITY_CAP]
            for a in alerts:
                if a.get("parameter") in SENSOR_NUTRIENT_PARAMETERS:
                    if _SEVERITY_RANK.get(a["severity"], 3) > cap:
                        a["severity"] = SENSOR_NUTRIENT_SEVERITY_CAP
                    a["score_impact"] = _as_float(a.get("score_impact")) * SENSOR_NUTRIENT_IMPACT_FACTOR
                    a["message"] = a["message"] + SENSOR_NUTRIENT_SUFFIX
                    a["estimated"] = True
        return alerts

    def moisture_status(self, data) -> Optional[dict]:
        """Plant-available water for this soil, or None without a reading."""
        theta_pct = getattr(data, "soil_moisture", None)
        if theta_pct is None:
            return None
        soil = canonical_soil(getattr(data, "soil_type", None))
        hydraulics = SOIL_HYDRAULICS[soil or DEFAULT_SOIL_FOR_MOISTURE]
        fc, wp = hydraulics["theta_fc"], hydraulics["theta_wp"]
        theta = theta_pct / 100.0
        crop = canonical_crop(getattr(data, "crop_type", None))
        p = (_IRRIGATION_CROPS.get(crop, {}).get("p") if crop else None) or MOISTURE_RULES["default_p"]
        return {
            "volumetric_percent": round(theta_pct, 1),
            "available_water_percent": round((theta - wp) / (fc - wp) * 100.0, 1),
            "field_capacity_percent": round(fc * 100, 1),
            "wilting_point_percent": round(wp * 100, 1),
            "stress_starts_below_percent": round((1 - p) * 100, 1),
            "soil_type_used": soil or DEFAULT_SOIL_FOR_MOISTURE,
            "soil_type_assumed": soil is None,
        }

    def _moisture_alerts(self, data, crop: Optional[str]) -> list[dict]:
        status = self.moisture_status(data)
        if status is None:
            return []
        aw = status["available_water_percent"]
        theta = status["volumetric_percent"] / 100.0
        fc = status["field_capacity_percent"] / 100.0
        rules = MOISTURE_RULES
        paddy = bool(crop and CROP_CONFIG[crop].get("paddy"))

        if paddy:
            if aw < rules["paddy_critical_low_aw"]:
                return [self._moisture_alert("CRITICAL_LOW_MOISTURE", aw, rules["paddy_critical_low_aw"], "below")]
            if aw < rules["paddy_low_aw"]:
                return [self._moisture_alert("LOW_MOISTURE", aw, rules["paddy_low_aw"], "below",
                                             severity="medium")]
            return []   # standing water is the target for paddy

        if theta >= fc + rules["critical_high_above_fc"]:
            return [self._moisture_alert("CRITICAL_HIGH_MOISTURE", aw, 100.0, "above")]
        if theta >= fc + rules["high_above_fc"]:
            return [self._moisture_alert("HIGH_MOISTURE", aw, 100.0, "above")]
        if aw <= rules["critical_low_aw"]:
            return [self._moisture_alert("CRITICAL_LOW_MOISTURE", aw, rules["critical_low_aw"], "below")]
        stress = status["stress_starts_below_percent"]
        if aw < stress:
            # Deeper into the stress zone -> more severe.
            depth = (stress - aw) / max(stress, 1.0)
            severity = "high" if depth > 0.5 else "medium" if depth > 0.2 else "low"
            return [self._moisture_alert("LOW_MOISTURE", aw, stress, "below", severity=severity)]
        return []

    def _moisture_alert(self, code, aw, boundary, direction, severity=None) -> dict:
        alert = self._build_alert(code, aw, boundary, direction, "moisture")
        alert["unit"] = "% plant-available water"
        if severity:
            alert["severity"] = severity
        return alert

    def _salinity_alert(self, data, crop: Optional[str]) -> Optional[dict]:
        """EC against the crop's Maas-Hoffman tolerance, with the expected yield."""
        ec = self._value(data, "ec")
        tolerance = CROP_CONFIG[crop].get("salinity") if crop else None
        if ec is None or not tolerance:
            return None
        threshold, slope = tolerance["threshold"], tolerance["slope"]
        if ec <= threshold:
            return None
        yield_pct = max(0.0, 100.0 - slope * (ec - threshold))
        loss = 100.0 - yield_pct
        code = "CRITICAL_HIGH_EC" if ec > SEVERITY_RULES["critical_thresholds"]["ec"]["high"] else "HIGH_EC"
        alert = self._build_alert(code, ec, threshold, "above", "ec")
        alert["severity"] = ("critical" if loss >= 50 else "high" if loss >= 25
                             else "medium" if loss >= 10 else "low")
        name = CROP_CONFIG[crop]["display_name"]
        alert["message"] = (f"EC {ec:.1f} dS/m is above {name}'s salt tolerance "
                            f"({threshold:.1f} dS/m) - expected yield about {yield_pct:.0f}% "
                            "of a non-saline field (Maas-Hoffman).")
        alert["expected_relative_yield"] = round(yield_pct, 1)
        return alert

    # ─────────────────────────────────────────────────────────────────────────
    # 3. Weather (in-field air sensors)
    # ─────────────────────────────────────────────────────────────────────────

    def analyze_weather(self, data) -> list[dict]:
        alerts: list[dict] = []
        for rule in WEATHER_IMPACT_RULES.values():
            val = getattr(data, _CONFIG_TO_SCHEMA.get(rule["parameter"], rule["parameter"]), None)
            if val is None:
                continue
            below = rule["direction"] == "below"
            if (val < rule["threshold"]) if below else (val > rule["threshold"]):
                past_critical = (val < rule["critical_threshold"]) if below else (val > rule["critical_threshold"])
                defn = ALERT_DEFINITIONS.get(rule["alert_code"], {})
                alerts.append({
                    "type": rule["alert_code"], "message": defn.get("message", rule["alert_code"]),
                    "severity": "critical" if past_critical else rule["severity"],
                    "score_impact": defn.get("score_impact", 0),
                    "parameter": rule["parameter"], "observed_value": val, "source": "weather",
                })
        return alerts

    # ─────────────────────────────────────────────────────────────────────────
    # 4. Score (0-100)
    # ─────────────────────────────────────────────────────────────────────────

    def calculate_score(self, data, all_alerts: list[dict]) -> float:
        """Weighted closeness to the crop's optimum, minus alert impacts.

        A soil's health does not change with the calendar, so there is no
        seasonal multiplier (v2 lowered identical soils by up to 9 % in the
        monsoon).
        """
        crop = canonical_crop(getattr(data, "crop_type", None))
        soil = canonical_soil(getattr(data, "soil_type", None))

        weights = dict(SCORE_WEIGHTS)
        if crop in CROP_SCORE_WEIGHT_OVERRIDES:
            weights.update(CROP_SCORE_WEIGHT_OVERRIDES[crop])
        if soil:
            for param, multiplier in SOIL_TYPE_CONFIG[soil]["score_modifiers"].items():
                if param in weights:
                    weights[param] *= multiplier
        total = sum(weights.values()) or 1.0
        weights = {k: v / total for k, v in weights.items()}

        optimal = self._optimal_ranges(crop)
        moisture = self.moisture_status(data)
        weighted = 0.0
        for key, weight in weights.items():
            if key == "moisture":
                if moisture is None:
                    weighted += weight * 0.70
                    continue
                stress = moisture["stress_starts_below_percent"]
                band = ({"min": 100.0, "max": 150.0}
                        if crop and CROP_CONFIG[crop].get("paddy")
                        else {"min": stress, "max": 100.0 + MOISTURE_RULES["high_above_fc"] * 100
                              / max(1e-6, moisture["field_capacity_percent"] / 100
                                    - moisture["wilting_point_percent"] / 100)})
                weighted += self._score_param(moisture["available_water_percent"], band, weight)
                continue
            val = self._value(data, key)
            if val is None:
                weighted += weight * 0.70     # unknown: partial credit
                continue
            band = optimal.get(key)
            weighted += self._score_param(val, band, weight) if band else weight

        score = weighted * 100
        for alert in all_alerts:
            impact = _as_float(alert.get("score_impact",
                                         ALERT_DEFINITIONS.get(alert.get("type", ""), {}).get("score_impact", 0)))
            if alert.get("severity") == "low":
                impact *= 0.8
            score -= impact

        hard = sum(1 for a in all_alerts if not a.get("soft_alert"))
        overrides = SEVERITY_RULES["multi_issue_overrides"]
        if hard >= overrides["min_alerts_for_override"]:
            score /= overrides["score_penalty_multiplier"]
        return round(max(min(score, 100.0), 0.0), 2)

    # ─────────────────────────────────────────────────────────────────────────
    # 5. Fertilizer / amendment recommendations
    # ─────────────────────────────────────────────────────────────────────────

    def recommend_fertilizers(self, alerts: list[dict], data=None) -> list[dict]:
        crop = canonical_crop(getattr(data, "crop_type", None)) if data is not None else None
        legume = bool(crop and CROP_CONFIG[crop].get("legume"))
        ph = self._value(data, "ph") if data is not None else None

        sensor_npk = (data is not None
                      and getattr(data, "nutrient_source", "sensor") == "sensor")
        seen: set[str] = set()
        result: list[dict] = []
        for alert in sorted(alerts, key=lambda a: _SEVERITY_RANK.get(a["severity"], 3), reverse=True):
            code = alert["type"]
            if sensor_npk and alert.get("parameter") in SENSOR_NUTRIENT_PARAMETERS:
                if "soil_test_first" not in seen:
                    seen.add("soil_test_first")
                    result.append({"triggered_by": code, **{
                        k: SOIL_TEST_FIRST_RECOMMENDATION[k] for k in
                        ("fertilizer", "display_name", "dosage", "timing", "method")},
                        "cautions": list(SOIL_TEST_FIRST_RECOMMENDATION["cautions"])})
                continue
            entry = FERTILIZER_RECOMMENDATION_MAP.get(code)
            if code in ("LOW_N", "CRITICAL_LOW_N") and legume:
                entry = LEGUME_LOW_N_RECOMMENDATION
            elif code == "CRITICAL_HIGH_EC" and ph is not None and ph >= SODIC_PH:
                entry = FERTILIZER_RECOMMENDATION_MAP["CRITICAL_HIGH_EC_SODIC"]
            if not entry:
                continue
            key = entry.get("fertilizer", "none")
            dedupe = key if key != "none" else f"none:{code}"
            if dedupe in seen:
                continue
            seen.add(dedupe)
            result.append({
                "triggered_by": code, "fertilizer": key,
                "display_name": entry.get("display_name", key),
                "dosage": entry.get("dosage", "—"), "timing": entry.get("timing", "—"),
                "method": entry.get("method", "—"), "cautions": list(entry.get("cautions", [])),
            })
        return result

    # ─────────────────────────────────────────────────────────────────────────
    # 6. Conflict detection
    # ─────────────────────────────────────────────────────────────────────────

    def detect_conflicts(self, data, alerts: list[dict]) -> list[dict]:
        """(a) ineffective: applied but the deficiency persists;
        (b) contraindicated: applied while a condition makes it harmful."""
        raw = getattr(data, "fertilizer_type", None)
        key = FERTILIZER_ALIASES.get(str(raw).strip().lower()) if raw else None
        entry = CONFLICT_DETECTION_MAP.get(key) if key and key != "none" else None
        if not entry:
            return []

        active = {a["type"] for a in alerts}
        # After nitrogen fertilizer, moderately high N is expected, not a conflict.
        if key in {"urea", "dap", "npk_complex", "ammonium_sulfate"} and "CRITICAL_HIGH_N" not in active:
            active.discard("HIGH_N")

        conflicts: list[dict] = []
        persistent = [c for c in entry["expected_fix"] if c in active]
        if persistent:
            window = entry.get("expected_window")
            conflicts.append({
                "conflict_type": "ineffective", "fertilizer_applied": raw, "fertilizer_key": key,
                "expected_to_fix": entry["expected_fix"], "still_present": persistent,
                "expected_window_days": str(window) if window is not None else "—",
                "reason": (f"'{raw}' was applied but {', '.join(persistent)} persists. If it "
                           f"was applied more than {window} days ago, it has not worked."),
                "alternative": entry.get("alternative", "—"),
            })
        blocking = [c for c in entry.get("conflict_if_present", []) if c in active]
        if blocking:
            conflicts.append({
                "conflict_type": "contraindicated", "fertilizer_applied": raw, "fertilizer_key": key,
                "active_conditions": blocking,
                "reason": entry.get("conflict_reason") or
                          f"'{raw}' is not recommended with: {', '.join(blocking)}.",
                "alternative": entry.get("alternative", "—"),
            })
        return conflicts

    # ─────────────────────────────────────────────────────────────────────────
    # 7. Suggestions
    # ─────────────────────────────────────────────────────────────────────────

    def suggestions(self, data, alerts: list[dict], conflicts: list[dict]) -> list[dict]:
        seen: set[str] = set()
        tips: list[dict] = []
        active = {a["type"] for a in alerts}

        def add(message: str, priority: str = "medium", source: str = "alert") -> None:
            if message not in seen:
                seen.add(message)
                tips.append({"message": message, "priority": priority, "source": source})

        for alert in sorted(alerts, key=lambda a: _SEVERITY_RANK.get(a["severity"], 3), reverse=True):
            for message in SINGLE_ALERT_SUGGESTIONS.get(alert["type"], []):
                add(message, alert["severity"], "alert")
        for compound in MULTI_CONDITION_SUGGESTIONS:
            if set(compound["conditions"]) <= active:
                add(compound["suggestion"], compound.get("priority", "medium"), "compound")
        for conflict in conflicts:
            add(f"{conflict['reason']} Consider: {conflict.get('alternative', '—')}.", "high", "conflict")

        crop = canonical_crop(getattr(data, "crop_type", None))
        if crop:
            for message in CROP_CONFIG[crop].get("crop_advice", []):
                add(message, "info", "crop")
        moisture = self.moisture_status(data)
        if moisture and moisture["soil_type_assumed"]:
            add("Send soil_type - moisture was read against loam properties; the same reading "
                "means very different water on sand and clay.", "low", "data")
        if not tips:
            add(_DEFAULT_SUGGESTION, "info", "default")
        return tips

    # ─────────────────────────────────────────────────────────────────────────
    # 8. Summary
    # ─────────────────────────────────────────────────────────────────────────

    def generate_summary(self, status: str, score: float, alerts: list[dict],
                         crop_type: Optional[str] = None) -> str:
        crop = canonical_crop(crop_type)
        crop_label = CROP_CONFIG[crop]["display_name"] if crop else (crop_type or "this crop")
        if not alerts:
            return SUMMARY_TEMPLATES["no_alerts"].format(score_label=status.lower(), crop_type=crop_label)

        if all(a.get("severity") in ("low", "info") for a in alerts):
            codes = {a["type"] for a in alerts}
            phrases = []
            if codes & {"LOW_N", "LOW_P", "LOW_K", "HIGH_N", "HIGH_P", "HIGH_K"}:
                phrases.append("minor nutrient imbalance")
            if codes & {"HIGH_EC", "LOW_EC"}:
                phrases.append("mild salinity")
            if codes & {"LOW_MOISTURE", "HIGH_MOISTURE"}:
                phrases.append("borderline moisture")
            if codes & {"HIGH_SOIL_TEMP", "LOW_SOIL_TEMP"}:
                phrases.append("sub-optimal soil temperature")
            if codes & {"LOW_PH", "HIGH_PH"}:
                phrases.append("slight pH deviation")
            detail = " and ".join(phrases) or "minor deviations from optimal conditions"
            return f"Soil health is good with {detail} for {crop_label}. Score: {score}/100."

        ranked = sorted(alerts, key=lambda a: _SEVERITY_RANK.get(a["severity"], 3), reverse=True)
        fragments: list[str] = []
        for a in ranked:
            fragment = SUMMARY_FRAGMENTS.get(a["type"])
            if fragment and fragment not in fragments:
                fragments.append(fragment)
            if len(fragments) == 3:
                break
        if not fragments:
            return SUMMARY_TEMPLATES["no_alerts"].format(score_label=status.lower(), crop_type=crop_label)
        alert_list = (fragments[0] if len(fragments) == 1 else
                      f"{fragments[0]} and {fragments[1]}" if len(fragments) == 2 else
                      f"{fragments[0]}, {fragments[1]}, and {fragments[2]}")
        top_rec = FERTILIZER_RECOMMENDATION_MAP.get(ranked[0]["type"], {}).get(
            "timing", "review the recommendations")
        if status == "Critical":
            return SUMMARY_TEMPLATES["critical"].format(score=score, primary_alert=fragments[0])
        if len(alerts) == 1:
            return SUMMARY_TEMPLATES["single_alert"].format(
                score_label=status.lower(), score=score, alert_fragment=alert_list,
                recommendation=top_rec)
        return SUMMARY_TEMPLATES["multi_alert"].format(
            score=score, score_label=status.lower(), alert_count=len(alerts),
            alert_list=alert_list, top_recommendation=top_rec)

    # ─────────────────────────────────────────────────────────────────────────
    # 9-12. Confidence, data quality, status, critical factors
    # ─────────────────────────────────────────────────────────────────────────

    def compute_confidence(self, validation_errors: list[dict], alerts: list[dict]) -> dict:
        score = 1.0
        for err in validation_errors:
            value = err.get("value")
            bounds = VALID_RANGES.get(err.get("config_key", ""))
            if not isinstance(value, (int, float)) or not bounds:
                score -= 0.10          # unrecognised name: general ranges were used
                continue
            span = (bounds["max"] - bounds["min"]) or 1.0
            overshoot = max(bounds["min"] - value, value - bounds["max"], 0) / span
            score -= 0.25 if overshoot > 0.5 else 0.15 if overshoot > 0.2 else 0.10
        high = sum(1 for a in alerts if a["severity"] in ("high", "critical"))
        score -= 0.05 if high >= 4 else 0.02 if high >= 2 else 0.0
        return {"type": "rule-based", "score": round(max(score, 0.0), 2)}

    def compute_data_quality(self, data, validation_errors: list[dict]) -> float:
        score = 1.0
        for field, weight in DATA_QUALITY_WEIGHTS.items():
            value = getattr(data, field, None)
            if value is None:
                score -= weight
            elif field == "crop_type" and canonical_crop(value) is None:
                score -= weight
            elif field == "soil_type" and canonical_soil(value) is None:
                score -= weight
        score -= 0.10 * sum(1 for e in validation_errors if isinstance(e.get("value"), (int, float)))
        return round(max(score, 0.0), 2)

    @staticmethod
    def get_status(score: float, alert_count: int = 0) -> str:
        for band in SCORE_BANDS.values():
            if band["min"] <= score <= band["max"]:
                if band["label"] == "Excellent" and alert_count > 0:
                    return "Good"
                return band["label"]
        return "Critical"

    @staticmethod
    def extract_critical_factors(alerts: list[dict]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for a in sorted(alerts, key=lambda x: _SEVERITY_RANK.get(x["severity"], 3), reverse=True):
            if a["severity"] in ("high", "critical") and a["type"] not in seen:
                seen.add(a["type"])
                out.append(a["type"])
        return out

    # ─────────────────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _optimal_ranges(crop: Optional[str]) -> dict[str, dict[str, float]]:
        return CROP_CONFIG[crop]["optimal_ranges"] if crop else GLOBAL_OPTIMAL_RANGES

    @staticmethod
    def _value(data, config_key: str):
        return getattr(data, _CONFIG_TO_SCHEMA.get(config_key, config_key), None)

    def _soft(self, code, val, boundary, direction, key) -> dict:
        alert = self._build_alert(code, val, boundary, direction, key)
        alert["severity"] = "low"
        alert["score_impact"] = min(alert.get("score_impact", 0), _SOFT_IMPACT_CAP)
        alert["soft_alert"] = True
        return alert

    @staticmethod
    def _deviation_severity(boundary: float, value: float) -> str:
        pct = abs(value - boundary) / (abs(boundary) if abs(boundary) > 1e-9 else 1.0) * 100.0
        return "low" if pct < 10 else "medium" if pct < 25 else "high" if pct < 50 else "critical"

    @staticmethod
    def _nitrogen_tier(val: float, alert: dict) -> dict:
        if val <= NITROGEN_THRESHOLDS["medium"]:
            return {"severity": "low", "score_impact": min(alert.get("score_impact", 0), 2)}
        if val <= NITROGEN_THRESHOLDS["high"]:
            return {"severity": "medium", "score_impact": min(alert.get("score_impact", 0), 3)}
        return {"severity": "high", "score_impact": min(alert.get("score_impact", 0), 5)}

    @staticmethod
    def _build_alert(code, value, boundary, direction, config_key) -> dict:
        defn = ALERT_DEFINITIONS.get(code, {})
        return {
            "type": code, "message": defn.get("message", code),
            "severity": defn.get("base_severity", "medium"),
            "score_impact": defn.get("score_impact", 0),
            "parameter": config_key, "observed_value": value, "boundary": boundary,
            "direction": direction, "source": "soil",
        }

    @staticmethod
    def _score_param(value: float, optimal: dict[str, float], weight: float) -> float:
        """Full weight well inside the band, 70 % at its edge, falling to 0
        as the value moves one half-span outside it."""
        lo, hi = optimal["min"], optimal["max"]
        span = (hi - lo) if hi != lo else 1.0
        if lo <= value <= hi:
            edge = min((value - lo) / span, (hi - value) / span)
            return weight * (0.70 + edge) if edge < 0.30 else weight
        dev = (lo - value) / span if value < lo else (value - hi) / span
        return max(weight * (1.0 - min(dev * 2.0, 1.0)), 0.0)


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
