# app/crop_planning_growth/soil_Health/service.py
"""
SoilHealthService — Production-grade rule-based analysis engine.

Pipeline:
  validate → analyze → score → fertilizers → conflicts → suggestions → summary → confidence → data_quality
"""

from agents.crop_planning_growth.soil_Health.config import (
    VALID_RANGES,
    OPTIMAL_RANGES,
    ALERT_DEFS,
    CRITICAL_THRESHOLDS,
    FERTILIZER_MAP,
    SUGGESTION_MAP,
    SCORE_WEIGHTS,
    SUMMARY_FRAGMENTS,
    LOW_DEVIATION_THRESHOLD,
    DEFAULT_SUGGESTION,
    CONFLICT_MAP,
    OPTIONAL_FIELDS,
)

_SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


class SoilHealthService:

    # ─── 1. Input Validation ─────────────────────────────
    def validate(self, data) -> tuple:
        errors = []
        for field, (lo, hi) in VALID_RANGES.items():
            val = getattr(data, field, None)
            if val is None:
                continue
            if not (lo <= val <= hi):
                errors.append({
                    "field": field,
                    "value": val,
                    "valid_range": [lo, hi],
                    "message": f"{field} value {val} is outside valid range [{lo}, {hi}]",
                })
        return (len(errors) == 0, errors)

    # ─── 2. Analyze (deficiency + excess) ────────────────
    def analyze(self, data) -> list:
        alerts = []
        checks = [
            ("soil_ph",     "ACIDIC",       "ALKALINE"),
            ("nitrogen",    "LOW_N",        "HIGH_N"),
            ("phosphorus",  "LOW_P",        "HIGH_P"),
            ("potassium",   "LOW_K",        "HIGH_K"),
            ("soil_moisture", "LOW_MOISTURE", "HIGH_MOISTURE"),
        ]
        for param, low_key, high_key in checks:
            lo, hi = OPTIMAL_RANGES[param]
            val = getattr(data, param)
            if val < lo:
                alerts.append(self._build_alert(low_key, val, lo, "below"))
            elif val > hi:
                alerts.append(self._build_alert(high_key, val, hi, "above"))

        # EC — only high matters
        ec_max = OPTIMAL_RANGES["electrical_conductivity"][1]
        if data.electrical_conductivity > ec_max:
            alerts.append(self._build_alert("HIGH_EC", data.electrical_conductivity, ec_max, "above"))

        return alerts

    # ─── 3. Score (0–100) ────────────────────────────────
    def calculate_score(self, data) -> float:
        total = 0
        weight_sum = sum(SCORE_WEIGHTS.values())
        for param, w in SCORE_WEIGHTS.items():
            total += self._score_param(getattr(data, param), OPTIMAL_RANGES[param], w)
        return round((total / weight_sum) * 100, 2)

    # ─── 4. Fertilizers (deduplicated) ───────────────────
    def recommend_fertilizer(self, alerts: list) -> list:
        seen, out = set(), []
        for a in alerts:
            entry = FERTILIZER_MAP.get(a["message"])
            if entry and entry["name"] not in seen:
                seen.add(entry["name"])
                out.append({"name": entry["name"], "advice": entry["advice"]})
        return out

    # ─── 5. Conflict Detection ───────────────────────────
    def detect_conflicts(self, data, alerts: list) -> list:
        """
        If user already applied a fertilizer that should fix a detected
        deficiency, flag it — the fertilizer may be insufficient or
        the soil is not absorbing it.
        """
        fert = getattr(data, "fertilizer_type", None)
        if not fert:
            return []

        fert_lower = fert.strip().lower()
        alert_types = {a["type"] for a in alerts}
        conflicts = []

        for keyword, related in CONFLICT_MAP.items():
            if keyword in fert_lower:
                for alert_type in related:
                    if alert_type in alert_types:
                        conflicts.append({
                            "alert_type": alert_type,
                            "fertilizer_applied": fert,
                            "message": ALERT_DEFS[alert_type]["message"],
                        })
        return conflicts

    # ─── 6. Suggestions (deduplicated, ≥ 1) ─────────────
    def suggestions(self, data, alerts: list, conflicts: list) -> list:
        seen, tips = set(), []

        for a in alerts:
            msg = SUGGESTION_MAP.get(a["type"])
            if msg and msg not in seen:
                seen.add(msg)
                tips.append({"message": msg})

        # Conflict-based suggestions
        for c in conflicts:
            msg = (
                f"'{c['fertilizer_applied']}' is already applied but "
                f"'{c['message']}' persists — increase dosage or check soil absorption capacity"
            )
            if msg not in seen:
                seen.add(msg)
                tips.append({"message": msg})

        if not tips:
            tips.append({"message": DEFAULT_SUGGESTION})
        return tips

    # ─── 7. Summary (top 2–3 HIGH severity, 1 sentence) ─
    def generate_summary(self, status: str, alerts: list) -> str:
        if not alerts:
            return f"Soil health is {status.lower()} — no issues detected."

        # Sort: high → medium → low (deterministic)
        ranked = sorted(alerts, key=lambda a: _SEVERITY_ORDER.get(a["severity"], 1))

        # Collect top 3 unique fragments, prioritizing high severity
        frags = []
        for a in ranked:
            f = SUMMARY_FRAGMENTS.get(a["type"])
            if f and f not in frags:
                frags.append(f)
            if len(frags) == 3:
                break

        # Ensure HIGH_EC is always included if present
        ec_frag = SUMMARY_FRAGMENTS.get("HIGH_EC")
        if ec_frag and any(a["type"] == "HIGH_EC" for a in alerts):
            if ec_frag not in frags:
                if len(frags) >= 3:
                    frags[2] = ec_frag   # replace lowest-priority slot
                else:
                    frags.append(ec_frag)

        if not frags:
            return f"Soil health is {status.lower()} — review alerts for details."

        if len(frags) == 1:
            txt = frags[0]
        elif len(frags) == 2:
            txt = f"{frags[0]} and {frags[1]}"
        else:
            txt = f"{frags[0]}, {frags[1]}, and {frags[2]}"

        return f"Soil health is {status.lower()} due to {txt}."

    # ─── 8. Confidence Score ─────────────────────────────
    def compute_confidence(self, validation_errors: list, alerts: list) -> dict:
        """
        Returns {"type": "rule-based", "score": 0.0–1.0}
        Factors: validation errors (primary) + alert severity load (secondary).
        No errors → 1.0 | minor → 0.8–0.9 | severe → < 0.7
        """
        score = 1.0

        # Deduct for validation errors (primary factor)
        for err in validation_errors:
            lo, hi = VALID_RANGES.get(err["field"], (0, 1))
            span = hi - lo if hi != lo else 1
            overshoot = max(lo - err["value"], err["value"] - hi, 0) / span
            if overshoot > 0.5:
                score -= 0.25      # severe → drops below 0.7 fast
            elif overshoot > 0.2:
                score -= 0.15      # moderate
            else:
                score -= 0.10      # minor

        # Secondary: deduct slightly if many high-severity alerts
        high_count = sum(1 for a in alerts if a["severity"] == "high")
        if high_count >= 4:
            score -= 0.05
        elif high_count >= 2:
            score -= 0.02

        return {"type": "rule-based", "score": round(max(score, 0.0), 2)}

    # ─── 9. Data Quality Score ───────────────────────────
    def compute_data_quality(self, data, validation_errors: list) -> float:
        """
        Starts at 1.0.
        Deducts for missing optional fields and validation errors.
        """
        score = 1.0

        # Deduct for each missing optional field
        for field in OPTIONAL_FIELDS:
            if getattr(data, field, None) is None:
                score -= 0.04   # ~0.28 max deduction for 7 missing fields

        # Deduct for each validation error
        score -= len(validation_errors) * 0.10

        return round(max(score, 0.0), 2)

    # ─── Status ──────────────────────────────────────────
    @staticmethod
    def get_status(score: float) -> str:
        if score >= 85:
            return "Excellent"
        elif score >= 70:
            return "Good"
        elif score >= 50:
            return "Alert"
        return "Critical"

    # ─── Critical Factors Extraction ─────────────────────
    @staticmethod
    def extract_critical_factors(alerts: list) -> list:
        """Return list of alert types with HIGH severity."""
        seen = []
        for a in alerts:
            if a["severity"] == "high" and a["type"] not in seen:
                seen.append(a["type"])
        return seen

    # ─── Private Helpers ─────────────────────────────────
    def _build_alert(self, key: str, value: float, boundary: float, direction: str) -> dict:
        defn = ALERT_DEFS[key]
        return {
            "type":     defn["type"],
            "message":  defn["message"],
            "severity": self._compute_severity(key, defn["param"], value, boundary, direction),
        }

    @staticmethod
    def _compute_severity(key: str, param: str, value: float, boundary: float, direction: str) -> str:
        # Step 1: Critical thresholds → "high"
        ct = CRITICAL_THRESHOLDS.get(param)
        if ct:
            if direction == "below" and "low" in ct and value < ct["low"]:
                return "high"
            if direction == "above" and "high" in ct and value > ct["high"]:
                return "high"

        # Step 2: Minor deviation → "low"
        if boundary != 0:
            dev = abs(value - boundary) / abs(boundary)
            if dev < LOW_DEVIATION_THRESHOLD:
                return "low"

        # Step 3: Default
        return ALERT_DEFS[key]["base_severity"]

    @staticmethod
    def _score_param(value: float, optimal: tuple, weight: float) -> float:
        lo, hi = optimal
        if lo <= value <= hi:
            return weight
        if value < lo:
            dev = (lo - value) / lo if lo else 0
        else:
            dev = (value - hi) / hi if hi else 0
        return max(weight - weight * min(dev, 1.0), 0)