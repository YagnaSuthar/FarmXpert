# app/crop_planning_growth/soil_Health/service.py
"""
SoilHealthService — Production-grade rule-based analysis engine.
Config version: 2.0 — crop-aware, soil-type-weighted, weather-sensitive.

Pipeline:
  validate → analyze_soil → analyze_weather → score →
  fertilizers → conflicts → suggestions → summary → confidence → data_quality
"""

from __future__ import annotations
from typing import Any

from agents.crop_planning_growth.soil_Health.config import (
    VALID_RANGES,
    VALID_CATEGORICAL,
    GLOBAL_OPTIMAL_RANGES,
    ALERT_THRESHOLDS,
    NITROGEN_THRESHOLDS,
    CROP_CONFIG,
    SOIL_TYPE_CONFIG,
    WEATHER_IMPACT_RULES,
    SEASONAL_CONFIG,
    ALERT_DEFINITIONS,
    SEVERITY_RULES,
    FERTILIZER_RECOMMENDATION_MAP,
    SINGLE_ALERT_SUGGESTIONS,
    MULTI_CONDITION_SUGGESTIONS,
    CONFLICT_DETECTION_MAP,
    SCORE_WEIGHTS,
    CROP_SCORE_WEIGHT_OVERRIDES,
    SCORE_BANDS,
    SCORE_BASELINE,
    SUMMARY_FRAGMENTS,
    SUMMARY_TEMPLATES,
    OPTIONAL_FIELDS,
)

# =============================================================================
# MODULE-LEVEL CONSTANTS
# =============================================================================

# Schema field names → config parameter keys
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

# Config param → (low_code, crit_low_code, high_code, crit_high_code)
# None = direction not evaluated for that param
_SOIL_PARAM_ALERT_MAP: dict[str, tuple] = {
    "ph":          ("LOW_PH",        "CRITICAL_LOW_PH",       "HIGH_PH",        "CRITICAL_HIGH_PH"),
    "nitrogen":    ("LOW_N",         "CRITICAL_LOW_N",        "HIGH_N",         "CRITICAL_HIGH_N"),
    "phosphorus":  ("LOW_P",         "CRITICAL_LOW_P",        "HIGH_P",         None),
    "potassium":   ("LOW_K",         "CRITICAL_LOW_K",        "HIGH_K",         None),
    "moisture":    ("LOW_MOISTURE",  "CRITICAL_LOW_MOISTURE", "HIGH_MOISTURE",  "CRITICAL_HIGH_MOISTURE"),
    "ec":          ("LOW_EC",        None,                    "HIGH_EC",        "CRITICAL_HIGH_EC"),
    "temperature": ("LOW_SOIL_TEMP", None,                    "HIGH_SOIL_TEMP", None),
}

# Weather rule names that indicate a "low" condition (value < threshold)
_WEATHER_LOW_RULES = {"low_temperature", "low_rainfall", "low_humidity"}

# Free-text fertilizer input → CONFLICT_DETECTION_MAP keys
_FERTILIZER_KEY_MAP: dict[str, str] = {
    "urea":                   "urea",
    "dap":                    "dap",
    "di-ammonium phosphate":  "dap",
    "diammonium phosphate":   "dap",
    "mop":                    "mop",
    "muriate of potash":      "mop",
    "npk":                    "npk_complex",
    "npk complex":            "npk_complex",
    "npk_complex":            "npk_complex",
    "ssp":                    "sspa",
    "sspa":                   "sspa",
    "single super phosphate": "sspa",
    "ammonium sulfate":       "ammonium_sulfate",
    "ammonium sulphate":      "ammonium_sulfate",
    "compost":                "organic_compost",
    "organic compost":        "organic_compost",
    "organic_compost":        "organic_compost",
    "none":                   "none",
}

_SEVERITY_RANK: dict[str, int] = SEVERITY_RULES["severity_rank"]

_DEFAULT_SUGGESTION = (
    "All soil parameters are within acceptable range. "
    "Continue regular monitoring and maintain current management practices."
)


# =============================================================================
# SERVICE CLASS
# =============================================================================

class SoilHealthService:
    """
    Stateless analysis engine.  All methods are pure functions over input data.
    The agent orchestrates call order; this class owns the domain logic.
    """

    # ─────────────────────────────────────────────────────────────────────────
    # 1. Input Validation
    # ─────────────────────────────────────────────────────────────────────────

    def validate(self, data) -> tuple[bool, list[dict]]:
        """
        Check numeric fields against VALID_RANGES and categorical fields
        against VALID_CATEGORICAL.  Returns (is_valid, errors).
        """
        errors: list[dict] = []

        # Numeric range validation
        for schema_field, config_key in _SCHEMA_TO_CONFIG.items():
            val = getattr(data, schema_field, None)
            if val is None:
                continue
            bounds = VALID_RANGES.get(config_key)
            if not bounds:
                continue
            lo, hi = bounds["min"], bounds["max"]
            if not (lo <= val <= hi):
                errors.append({
                    "field":       schema_field,
                    "config_key":  config_key,
                    "value":       val,
                    "valid_range": [lo, hi],
                    "message":     (
                        f"'{schema_field}' value {val} is outside valid range "
                        f"[{lo}, {hi}]."
                    ),
                })

        # Categorical validation
        for cat_field in ("soil_type", "crop_type"):
            val = getattr(data, cat_field, None)
            if val is None:
                continue
            allowed = VALID_CATEGORICAL.get(cat_field, [])
            if val.lower() not in allowed:
                errors.append({
                    "field":   cat_field,
                    "value":   val,
                    "allowed": allowed,
                    "message": (
                        f"'{cat_field}' value '{val}' is not recognised. "
                        f"Allowed: {allowed}."
                    ),
                })

        return (len(errors) == 0, errors)

    # ─────────────────────────────────────────────────────────────────────────
    # 2. Soil Parameter Analysis
    # ─────────────────────────────────────────────────────────────────────────

    def analyze_soil(self, data) -> list[dict]:
        """
        Risk detection for soil parameters.

        IMPORTANT: Alerts are triggered using ALERT_THRESHOLDS (danger thresholds),
        not crop "optimal_ranges" (used for scoring).

        Crop optimal ranges still matter for score calculation, but mild deviation
        from optimal should not create farmer-facing alerts.
        """
        critical = SEVERITY_RULES["critical_thresholds"]
        alerts: list[dict] = []

        # ── SOFT ALERT LAYER — tolerance-buffered optimal range ────────
        # Alerts fire only when a value falls OUTSIDE a 10% tolerance buffer
        # around the optimal range.  This absorbs normal sensor noise and
        # natural field variation without generating false positives.
        #
        #   lower_bound = optimal_min - (range_size * 0.10)
        #   upper_bound = optimal_max + (range_size * 0.10)
        #
        # Hard alerts (ALERT_THRESHOLDS) always take priority; soft alerts
        # for the same parameter are dropped during deduplication below.
        # Soft alert score_impact is capped at 4 to prevent over-penalising.
        crop_type = getattr(data, "crop_type", None)
        soil_type = getattr(data, "soil_type", None)
        optimal = self._get_optimal_ranges(crop_type, soil_type)

        _SOFT_IMPACT_CAP = 4
        soft_alerts: list[dict] = []

        for config_key, (low_code, _, high_code, _) in _SOIL_PARAM_ALERT_MAP.items():
            # Temperature uses ALERT_THRESHOLDS (safe limit = 35 °C) exclusively;
            # crop optimal max (e.g. 25 °C for wheat) is for scoring only.
            if config_key == "temperature":
                continue
            schema_field = self._config_to_schema(config_key)
            val = getattr(data, schema_field, None)
            if val is None:
                continue
            param_range = optimal.get(config_key)
            if not param_range:
                continue

            opt_min, opt_max = param_range["min"], param_range["max"]
            opt_span = opt_max - opt_min
            if opt_span < 1e-9:
                continue

            # 10% tolerance buffer around optimal range
            tolerance = opt_span * 0.10
            lower_bound = opt_min - tolerance
            upper_bound = opt_max + tolerance

            if val < lower_bound and low_code:
                alert = self._build_alert(low_code, val, opt_min, "below", config_key)
                alert["severity"] = "low"
                alert["score_impact"] = min(alert.get("score_impact", 0), _SOFT_IMPACT_CAP)
                alert["soft_alert"] = True
                soft_alerts.append(alert)
            elif val > upper_bound and high_code:
                alert = self._build_alert(high_code, val, opt_max, "above", config_key)
                alert["severity"] = "low"
                alert["score_impact"] = min(alert.get("score_impact", 0), _SOFT_IMPACT_CAP)
                alert["soft_alert"] = True
                soft_alerts.append(alert)

        # ── HARD ALERT LAYER — ALERT_THRESHOLDS (danger detection) ──────
        for config_key, (low_code, crit_low_code, high_code, crit_high_code) in _SOIL_PARAM_ALERT_MAP.items():
            schema_field = self._config_to_schema(config_key)
            val = getattr(data, schema_field, None)
            if val is None:
                continue

            # Alerting uses separate danger thresholds (risk detection)
            thresholds = ALERT_THRESHOLDS.get(config_key)
            if not thresholds:
                continue

            ct = critical.get(config_key, {})

            def _severity_from_threshold(direction: str, boundary: float, value: float) -> str:
                """Escalate severity based on % deviation beyond the alert threshold."""
                # Use boundary-relative deviation (works across units)
                denom = abs(boundary) if abs(boundary) > 1e-9 else 1.0
                deviation_pct = (abs(value - boundary) / denom) * 100.0

                # below-threshold already implies "moderate" concern; scale up from there
                if deviation_pct < 10.0:
                    return "low"
                if deviation_pct < 25.0:
                    return "medium"
                if deviation_pct < 50.0:
                    return "high"
                return "critical"

            # LOW side
            low_thr = thresholds.get("low")
            if low_thr is not None and val < low_thr:
                is_critical = (
                    crit_low_code is not None
                    and ct.get("low") is not None
                    and val < ct["low"]
                )
                code = crit_low_code if is_critical else low_code
                if code:
                    alert = self._build_alert(code, val, low_thr, "below", config_key)
                    if not is_critical:
                        alert["severity"] = _severity_from_threshold("below", low_thr, val)
                    alerts.append(alert)
                continue

            # HIGH side
            high_thr = thresholds.get("high")
            if high_thr is not None and val > high_thr:
                is_critical = (
                    crit_high_code is not None
                    and ct.get("high") is not None
                    and val > ct["high"]
                )
                code = crit_high_code if is_critical else high_code
                if code:
                    alert = self._build_alert(code, val, high_thr, "above", config_key)
                    if config_key == "nitrogen" and not is_critical:
                        # Tiered agronomy calibration: high-but-normal N should not be CRITICAL.
                        # N ≤ 90 → no alert (covered by high_thr); 90–120 low; 120–180 medium;
                        # 180–220 high; >220 critical (handled by critical_thresholds).
                        if val <= NITROGEN_THRESHOLDS["medium"]:
                            alert["severity"] = "low"
                            alert["score_impact"] = min(alert.get("score_impact", 0), 2)
                        elif val <= NITROGEN_THRESHOLDS["high"]:
                            alert["severity"] = "medium"
                            alert["score_impact"] = min(alert.get("score_impact", 0), 3)
                        else:
                            alert["severity"] = "high"
                            alert["score_impact"] = min(alert.get("score_impact", 0), 5)
                    elif not is_critical:
                        alert["severity"] = _severity_from_threshold("above", high_thr, val)
                    alerts.append(alert)

        # Extreme value override — apply compounding penalty flag
        extreme = SEVERITY_RULES["extreme_value_override"]
        ph_val  = getattr(data, "soil_ph", None)
        ec_val  = getattr(data, "electrical_conductivity", None)
        moi_val = getattr(data, "soil_moisture", None)
        for a in alerts:
            if (
                (ph_val  is not None and ph_val  < extreme["ph_below"])
                or (ec_val  is not None and ec_val  > extreme["ec_above"])
                or (moi_val is not None and moi_val < extreme["moisture_below"])
                or (moi_val is not None and moi_val > extreme["moisture_above"])
            ):
                a["severity"] = "critical"
                a["extreme_override"] = True

        # ── Merge soft alerts — skip params already covered by hard alerts
        hard_alert_params = {a["parameter"] for a in alerts}
        for sa in soft_alerts:
            if sa["parameter"] not in hard_alert_params:
                alerts.append(sa)

        return alerts

    # ─────────────────────────────────────────────────────────────────────────
    # 3. Weather Impact Analysis
    # ─────────────────────────────────────────────────────────────────────────

    def analyze_weather(self, data) -> list[dict]:
        """
        Evaluate air/weather parameters against WEATHER_IMPACT_RULES.
        Returns weather-triggered alerts with severity escalation at
        critical_threshold.
        """
        alerts: list[dict] = []

        # Map config weather param → schema field name
        weather_schema_map = {
            "air_temperature": "air_temperature",
            "rainfall":        "rainfall",
            "humidity":        "air_humidity",
        }

        for rule_name, rule in WEATHER_IMPACT_RULES.items():
            config_param = rule["parameter"]
            schema_field = weather_schema_map.get(config_param)
            if not schema_field:
                continue

            val = getattr(data, schema_field, None)
            if val is None:
                continue

            threshold       = rule["threshold"]
            critical_thresh = rule["critical_threshold"]
            alert_code      = rule["alert_code"]
            base_severity   = rule["severity"]

            triggered = (
                (rule_name in _WEATHER_LOW_RULES and val < threshold)
                or (rule_name not in _WEATHER_LOW_RULES and val > threshold)
            )
            if not triggered:
                continue

            # Escalate severity if past critical threshold
            severity = base_severity
            if rule_name in _WEATHER_LOW_RULES and val < critical_thresh:
                severity = "critical"
            elif rule_name not in _WEATHER_LOW_RULES and val > critical_thresh:
                severity = "critical"

            defn = ALERT_DEFINITIONS.get(alert_code, {})
            alerts.append({
                "type":            alert_code,
                "message":         defn.get("message", rule.get("action", alert_code)),
                "severity":        severity,
                "score_impact":    defn.get("score_impact", rule.get("score_penalty", 0)),
                "parameter":       config_param,
                "observed_value":  val,
                "source":          "weather",
            })

        return alerts

    # ─────────────────────────────────────────────────────────────────────────
    # 4. Health Score (0–100)
    # ─────────────────────────────────────────────────────────────────────────

    def calculate_score(self, data, all_alerts: list[dict]) -> float:
        """
        Weighted score using SCORE_WEIGHTS, adjusted by:
          - Crop-specific weight overrides (CROP_SCORE_WEIGHT_OVERRIDES)
          - Soil-type score modifiers     (SOIL_TYPE_CONFIG[soil_type].score_modifiers)
          - Seasonal score modifier       (SEASONAL_CONFIG[season].score_modifier)
          - Multi-issue compounding penalty
        """
        crop_type  = getattr(data, "crop_type",  None)
        soil_type  = getattr(data, "soil_type",  None)
        season     = getattr(data, "season",     None)

        # Step 1: Build effective weight map
        weights: dict[str, float] = dict(SCORE_WEIGHTS)
        if crop_type and crop_type.lower() in CROP_SCORE_WEIGHT_OVERRIDES:
            weights.update(CROP_SCORE_WEIGHT_OVERRIDES[crop_type.lower()])

        # Step 2: Apply soil-type score modifiers
        if soil_type and soil_type.lower() in SOIL_TYPE_CONFIG:
            modifiers = SOIL_TYPE_CONFIG[soil_type.lower()].get("score_modifiers", {})
            for param, multiplier in modifiers.items():
                if param in weights:
                    weights[param] = weights[param] * multiplier

        # Re-normalise so weights still sum to 1.0
        total_w = sum(weights.values()) or 1.0
        weights = {k: v / total_w for k, v in weights.items()}

        # Step 3: Score each parameter
        optimal = self._get_optimal_ranges(crop_type, soil_type)
        weighted_score = 0.0
        for config_key, weight in weights.items():
            schema_field = self._config_to_schema(config_key)
            val = getattr(data, schema_field, None)
            if val is None:
                # Missing optional param — treat as neutral, reduce weight contribution
                weighted_score += weight * 0.70
                continue
            param_range = optimal.get(config_key)
            if param_range:
                weighted_score += self._score_param(val, param_range, weight)
            else:
                weighted_score += weight  # no range defined → neutral

        score = round(weighted_score * 100, 2)

        # Step 4: Subtract alert-driven score impacts
        for alert in all_alerts:
            raw_impact = alert.get(
                "score_impact",
                ALERT_DEFINITIONS.get(alert.get("type", ""), {}).get("score_impact", 0),
            )
            if isinstance(raw_impact, (int, float)):
                impact = float(raw_impact)
            else:
                try:
                    impact = float(raw_impact)
                except (TypeError, ValueError):
                    impact = 0.0
            # Low-severity alerts carry 80% of their score impact
            if alert.get("severity") == "low":
                impact *= 0.8
            score -= impact

        # Step 5: Multi-issue compounding (soft alerts excluded from count)
        non_soft_count = sum(1 for a in all_alerts if not a.get("soft_alert"))
        override_cfg = SEVERITY_RULES["multi_issue_overrides"]
        if non_soft_count >= override_cfg["min_alerts_for_override"]:
            score *= (1.0 / override_cfg["score_penalty_multiplier"])

        # Step 6: Seasonal modifier
        if season and season.lower() in SEASONAL_CONFIG:
            score *= SEASONAL_CONFIG[season.lower()].get("score_modifier", 1.0)

        return round(max(min(score, 100.0), 0.0), 2)

    # ─────────────────────────────────────────────────────────────────────────
    # 5. Fertilizer Recommendations
    # ─────────────────────────────────────────────────────────────────────────

    def recommend_fertilizers(self, alerts: list[dict]) -> list[dict]:
        """
        Map each alert code to FERTILIZER_RECOMMENDATION_MAP.
        Deduplicated by fertilizer key.  Returns rich recommendation objects.
        """
        seen:   set[str]  = set()
        result: list[dict] = []

        for alert in alerts:
            code  = alert["type"]
            entry = FERTILIZER_RECOMMENDATION_MAP.get(code)
            if not entry:
                continue
            fert_key = entry.get("fertilizer", "none")
            if fert_key in seen or fert_key == "none":
                continue
            seen.add(fert_key)
            result.append({
                "triggered_by": code,
                "fertilizer":   fert_key,
                "display_name": entry.get("display_name", fert_key),
                "dosage":       entry.get("dosage", "—"),
                "timing":       entry.get("timing", "—"),
                "method":       entry.get("method", "—"),
                "cautions":     entry.get("cautions", []),
            })

        return result

    # ─────────────────────────────────────────────────────────────────────────
    # 6. Conflict Detection
    # ─────────────────────────────────────────────────────────────────────────

    def detect_conflicts(self, data, alerts: list[dict]) -> list[dict]:
        """
        Two conflict types:
          (a) INEFFECTIVE  — fertilizer applied but the deficiency it should fix
                             still persists (fertilizer not working / insufficient).
          (b) CONTRAINDICATED — fertilizer applied while a condition exists that
                             makes it counter-productive (e.g. MOP + HIGH_EC).
        """
        fert_raw = getattr(data, "fertilizer_type", None)
        if not fert_raw:
            return []

        fert_key = _FERTILIZER_KEY_MAP.get(fert_raw.strip().lower())
        if not fert_key or fert_key == "none":
            return []

        entry = CONFLICT_DETECTION_MAP.get(fert_key)
        if not entry:
            return []

        active_codes = {a["type"] for a in alerts}
        conflicts: list[dict] = []

        # Expected-condition suppression:
        # after applying N-containing fertilizers, moderately high N is not a conflict.
        n_ferts = {"urea", "dap", "npk_complex"}
        if fert_key in n_ferts and "HIGH_N" in active_codes and "CRITICAL_HIGH_N" not in active_codes:
            active_codes = set(active_codes)
            active_codes.discard("HIGH_N")

        # (a) INEFFECTIVE: expected_fix alert still present
        persistent = [c for c in entry.get("expected_fix", []) if c in active_codes]
        if persistent:
            expected_window = entry.get("expected_window")
            conflicts.append({
                "conflict_type":       "ineffective",
                "fertilizer_applied":  fert_raw,
                "fertilizer_key":      fert_key,
                "expected_to_fix":     entry["expected_fix"],
                "still_present":       persistent,
                "expected_window_days": (
                    "—" if expected_window is None else str(expected_window)
                ),
                "reason":              (
                    f"'{fert_raw}' was applied but the following deficiencies "
                    f"persist: {', '.join(persistent)}. "
                    f"Expected improvement window: {expected_window if expected_window is not None else '?'} days."
                ),
                "alternative":         entry.get("alternative", "—"),
            })

        # (b) CONTRAINDICATED: conflict condition is active
        contraindicated = [c for c in entry.get("conflict_if_present", []) if c in active_codes]
        if contraindicated:
            conflicts.append({
                "conflict_type":      "contraindicated",
                "fertilizer_applied": fert_raw,
                "fertilizer_key":     fert_key,
                "active_conditions":  contraindicated,
                "reason":             entry.get(
                    "conflict_reason",
                    f"'{fert_raw}' is not recommended given active conditions: "
                    f"{', '.join(contraindicated)}.",
                ),
                "alternative":        entry.get("alternative", "—"),
            })

        return conflicts

    # ─────────────────────────────────────────────────────────────────────────
    # 7. Suggestions
    # ─────────────────────────────────────────────────────────────────────────

    def suggestions(
        self,
        data,
        alerts:    list[dict],
        conflicts: list[dict],
    ) -> list[dict]:
        """
        Three suggestion sources (deduplicated):
          1. SINGLE_ALERT_SUGGESTIONS  — per-alert actionable tips
          2. MULTI_CONDITION_SUGGESTIONS — compound scenario tips
          3. Conflict-specific tips
        Falls back to DEFAULT_SUGGESTION if nothing is triggered.
        """
        seen: set[str] = set()
        tips: list[dict] = []
        active_codes = {a["type"] for a in alerts}

        def _add(msg: str, priority: str = "medium", source: str = "alert") -> None:
            if msg not in seen:
                seen.add(msg)
                tips.append({"message": msg, "priority": priority, "source": source})

        # 1. Per-alert suggestions (sorted high → low)
        ranked = sorted(alerts, key=lambda a: _SEVERITY_RANK.get(a["severity"], 3), reverse=True)
        for alert in ranked:
            for msg in SINGLE_ALERT_SUGGESTIONS.get(alert["type"], []):
                _add(msg, priority=alert["severity"], source="alert")

        # 2. Multi-condition compound suggestions
        for compound in MULTI_CONDITION_SUGGESTIONS:
            required = set(compound["conditions"])
            if required.issubset(active_codes):
                _add(
                    compound["suggestion"],
                    priority=compound.get("priority", "medium"),
                    source="compound",
                )

        # 3. Conflict-driven suggestions
        for conflict in conflicts:
            alt = conflict.get("alternative", "—")
            msg = (
                f"{conflict['reason']} "
                f"Consider switching to: {alt}."
            )
            _add(msg, priority="high", source="conflict")

        if not tips:
            _add(_DEFAULT_SUGGESTION, priority="info", source="default")

        return tips

    # ─────────────────────────────────────────────────────────────────────────
    # 8. Summary Generation
    # ─────────────────────────────────────────────────────────────────────────

    def generate_summary(
        self,
        status:    str,
        score:     float,
        alerts:    list[dict],
        crop_type: str | None = None,
    ) -> str:
        """
        Builds a one-sentence natural-language summary.
        Uses SUMMARY_TEMPLATES keyed by severity band.
        High-severity alerts always appear before medium/low ones.
        HIGH_EC is guaranteed inclusion if present.
        """
        crop_label = crop_type.capitalize() if crop_type else "this crop"

        if not alerts:
            return "All soil parameters are within acceptable range."

        # Soft-alert-only summary — all alerts are low severity
        if all(a.get("severity") == "low" for a in alerts):
            # Build context-aware summary from active soft alert types
            _issue_phrases = []
            _active_codes = {a["type"] for a in alerts}
            if _active_codes & {"LOW_N", "LOW_P", "LOW_K", "HIGH_N", "HIGH_P", "HIGH_K"}:
                _issue_phrases.append("minor nutrient imbalance")
            if _active_codes & {"HIGH_EC", "LOW_EC"}:
                _issue_phrases.append("mild salinity stress")
            if _active_codes & {"LOW_MOISTURE", "HIGH_MOISTURE"}:
                _issue_phrases.append("borderline moisture levels")
            if _active_codes & {"HIGH_SOIL_TEMP", "LOW_SOIL_TEMP"}:
                _issue_phrases.append("sub-optimal soil temperature")
            if _active_codes & {"LOW_PH", "HIGH_PH"}:
                _issue_phrases.append("slight pH deviation")
            detail = " and ".join(_issue_phrases) if _issue_phrases else "minor deviations from optimal conditions"
            return (
                f"Soil health is good with {detail} "
                f"for {crop_label}. Score: {score}/100."
            )

        # Sort high → medium → low (stable)
        ranked = sorted(
            alerts,
            key=lambda a: _SEVERITY_RANK.get(a["severity"], 3),
            reverse=True,
        )

        # Collect top-3 unique fragments
        frags: list[str] = []
        for a in ranked:
            frag = SUMMARY_FRAGMENTS.get(a["type"])
            if frag and frag not in frags:
                frags.append(frag)
            if len(frags) == 3:
                break

        # Guarantee HIGH_EC inclusion if present
        ec_frag = SUMMARY_FRAGMENTS.get("HIGH_EC")
        if ec_frag and any(a["type"] == "HIGH_EC" for a in alerts) and ec_frag not in frags:
            if len(frags) >= 3:
                frags[2] = ec_frag
            else:
                frags.append(ec_frag)

        if not frags:
            return SUMMARY_TEMPLATES["no_alerts"].format(
                score_label=status.lower(), crop_type=crop_label
            )

        # Format fragment list
        if len(frags) == 1:
            alert_list = frags[0]
        elif len(frags) == 2:
            alert_list = f"{frags[0]} and {frags[1]}"
        else:
            alert_list = f"{frags[0]}, {frags[1]}, and {frags[2]}"

        # Choose template by status
        top_alert = ranked[0]
        top_rec   = FERTILIZER_RECOMMENDATION_MAP.get(
            top_alert["type"], {}
        ).get("timing", "review recommendations above")

        if status == "Critical":
            return SUMMARY_TEMPLATES["critical"].format(
                score=score,
                primary_alert=frags[0],
            )
        elif len(alerts) == 1:
            return SUMMARY_TEMPLATES["single_alert"].format(
                score_label=status.lower(),
                score=score,
                alert_fragment=alert_list,
                recommendation=top_rec,
            )
        else:
            return SUMMARY_TEMPLATES["multi_alert"].format(
                score=score,
                score_label=status.lower(),
                alert_count=len(alerts),
                alert_list=alert_list,
                top_recommendation=top_rec,
            )

    # ─────────────────────────────────────────────────────────────────────────
    # 9. Confidence Score
    # ─────────────────────────────────────────────────────────────────────────

    def compute_confidence(
        self,
        validation_errors: list[dict],
        alerts:            list[dict],
    ) -> dict:
        """
        Returns {"type": "rule-based", "score": 0.0–1.0}.
        Primary deduction: validation errors (proportional to overshoot magnitude).
        Secondary deduction: high-severity alert count.
        """
        score = 1.0

        for err in validation_errors:
            config_key = err.get("config_key", err.get("field", ""))
            bounds = VALID_RANGES.get(config_key, {})
            lo = bounds.get("min", 0.0)
            hi = bounds.get("max", 1.0)
            span = (hi - lo) if hi != lo else 1.0
            val = err["value"]
            overshoot = max(lo - val, val - hi, 0) / span
            if overshoot > 0.5:
                score -= 0.25
            elif overshoot > 0.2:
                score -= 0.15
            else:
                score -= 0.10

        # Secondary: high-severity burden
        high_count = sum(1 for a in alerts if a["severity"] in ("high", "critical"))
        if high_count >= 4:
            score -= 0.05
        elif high_count >= 2:
            score -= 0.02

        return {"type": "rule-based", "score": round(max(score, 0.0), 2)}

    # ─────────────────────────────────────────────────────────────────────────
    # 10. Data Quality Score
    # ─────────────────────────────────────────────────────────────────────────

    def compute_data_quality(
        self,
        data,
        validation_errors: list[dict],
    ) -> float:
        """
        Starts at 1.0.
        Deducts per missing optional field (weighted by field importance).
        Deducts for validation errors.
        """
        score = 1.0

        # Weighted deduction per missing optional field
        for field, meta in OPTIONAL_FIELDS.items():
            if getattr(data, field, None) is None:
                score -= meta.get("weight", 0.04)

        # Per validation error
        score -= len(validation_errors) * 0.10

        return round(max(score, 0.0), 2)

    # ─────────────────────────────────────────────────────────────────────────
    # 11. Status Band
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def get_status(score: float, alert_count: int = 0) -> str:
        for band_name, band in SCORE_BANDS.items():
            if band["min"] <= score <= band["max"]:
                label = band["label"]
                # Prevent 'Excellent' classification when any alerts exist
                if label == "Excellent" and alert_count > 0:
                    return "Good"
                return label
        return "Critical"

    # ─────────────────────────────────────────────────────────────────────────
    # 12. Critical Factors
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def extract_critical_factors(alerts: list[dict]) -> list[str]:
        """Return unique alert type codes for HIGH or CRITICAL severity alerts."""
        seen:   set[str]  = set()
        result: list[str] = []
        for a in sorted(
            alerts,
            key=lambda x: _SEVERITY_RANK.get(x["severity"], 3),
            reverse=True,
        ):
            if a["severity"] in ("high", "critical") and a["type"] not in seen:
                seen.add(a["type"])
                result.append(a["type"])
        return result

    # ─────────────────────────────────────────────────────────────────────────
    # Private Helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _get_optimal_ranges(
        self,
        crop_type: str | None,
        soil_type: str | None,
    ) -> dict[str, dict[str, float]]:
        """
        Returns per-parameter optimal ranges.
        Priority: crop_type config → GLOBAL_OPTIMAL_RANGES.
        Soil type does not shift optimal ranges directly — it affects scoring weights.
        """
        if crop_type and crop_type.lower() in CROP_CONFIG:
            return CROP_CONFIG[crop_type.lower()]["optimal_ranges"]
        return GLOBAL_OPTIMAL_RANGES

    def _build_alert(
        self,
        code:       str,
        value:      float,
        boundary:   float,
        direction:  str,
        config_key: str,
    ) -> dict:
        """Construct a normalised alert dict from an alert code and observed value."""
        defn = ALERT_DEFINITIONS.get(code, {})
        return {
            "type":           code,
            "message":        defn.get("message", code),
            "severity":       defn.get("base_severity", "medium"),
            "score_impact":   defn.get("score_impact", 0),
            "parameter":      config_key,
            "observed_value": value,
            "boundary":       boundary,
            "direction":      direction,
            "source":         "soil",
        }

    @staticmethod
    def _score_param(
        value:   float,
        optimal: dict[str, float],
        weight:  float,
    ) -> float:
        """
        Score a parameter relative to its optimal range.

        Within-range scoring uses an edge penalty: values at the exact
        boundary receive 70% of weight, linearly ramping to 100% at 30%
        into the range.  This prevents edge-of-range values from
        inflating the overall score.

        Outside-range scoring linearly decrements to 0 as deviation
        reaches 100% of range span.  Span-relative deviation prevents
        pH (0–14) and nitrogen (0–1000) from receiving disproportionate
        penalties.
        """
        lo, hi = optimal["min"], optimal["max"]
        span   = (hi - lo) if hi != lo else 1.0

        if lo <= value <= hi:
            # Edge penalty: outer 30% of range gets partial credit
            dist_from_lo = (value - lo) / span
            dist_from_hi = (hi - value) / span
            edge_fraction = min(dist_from_lo, dist_from_hi)  # 0 at boundary, 0.5 at centre
            if edge_fraction < 0.30:
                # Linear ramp: 70% at boundary → 100% at 30% in
                edge_factor = 0.70 + (0.30 * edge_fraction / 0.30)
                return weight * edge_factor
            return weight

        dev = (lo - value) / span if value < lo else (value - hi) / span
        return max(weight * (1.0 - min(dev * 2.0, 1.0)), 0.0)

    @staticmethod
    def _config_to_schema(config_key: str) -> str:
        """Reverse map: config parameter key → schema field attribute name."""
        _reverse = {v: k for k, v in _SCHEMA_TO_CONFIG.items()}
        return _reverse.get(config_key, config_key)