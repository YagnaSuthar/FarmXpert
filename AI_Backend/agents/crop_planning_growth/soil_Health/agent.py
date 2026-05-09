# app/crop_planning_growth/soil_Health/agent.py
"""
SoilHealthAgent — Orchestrates the full analysis pipeline.
Delegates all domain logic to SoilHealthService.
Config version: 2.0 — weather-aware, conflict-aware.
"""

from AI_Backend.agents.crop_planning_growth.soil_Health.service import SoilHealthService


class SoilHealthAgent:
    """
    Thin orchestrator.  Owns pipeline order only; zero business logic here.

    Pipeline:
      1.  validate          — reject or flag out-of-range inputs
      2.  analyze_soil      — deficiency / excess alerts (crop-aware)
      3.  analyze_weather   — weather-triggered alerts (air temp, humidity, rainfall)
      4.  detect_conflicts  — fertilizer applied vs. persisting condition
      5.  inject conflicts  — append conflict alerts into unified alert list
      6.  calculate_score   — weighted, crop/soil/season-adjusted score
      7.  get_status        — band label (Excellent → Critical)
      8.  recommend_fertilizers — map alert codes → fertilizer objects
      9.  suggestions       — per-alert + compound + conflict tips
      10. generate_summary  — natural-language one-liner
      11. compute_confidence  — rule-based confidence (0.0–1.0)
      12. compute_data_quality — optional-field completeness score
      13. extract_critical_factors — HIGH/CRITICAL alert codes for dashboard
    """

    def __init__(self) -> None:
        self.service = SoilHealthService()
    async def __call__(self, state):

        return await self.run(state)
    async def run(self, soil_data) -> dict:
        svc = self.service

        # ── 1. Validate ──────────────────────────────────────────────────────
        _, validation_errors = svc.validate(soil_data)

        # ── 2. Soil Analysis ─────────────────────────────────────────────────
        soil_alerts = svc.analyze_soil(soil_data)

        # ── 3. Weather Analysis ──────────────────────────────────────────────
        weather_alerts = svc.analyze_weather(soil_data)

        # ── 4. Conflict Detection ────────────────────────────────────────────
        # Runs against soil alerts only; weather codes do not generate conflicts.
        conflicts = svc.detect_conflicts(soil_data, soil_alerts)

        # ── 5. Build Unified Alert List ──────────────────────────────────────
        # Order: soil → weather → conflict summary alerts
        all_alerts = list(soil_alerts) + list(weather_alerts)

        for conflict in conflicts:
            all_alerts.append({
                "type":     "CONFLICT",
                "message":  conflict["reason"],
                "severity": "high",
                "source":   "conflict",
                "score_impact": 5,
            })

        # ── 6. Score + Status ────────────────────────────────────────────────
        score  = svc.calculate_score(soil_data, all_alerts)
        status = svc.get_status(score, alert_count=len(all_alerts))

        # ── 7. Fertilizer Recommendations ────────────────────────────────────
        # Based on soil alerts only (weather alerts don't map to fertilizers)
        fertilizers = svc.recommend_fertilizers(soil_alerts)

        # ── 8. Suggestions ───────────────────────────────────────────────────
        suggestions = svc.suggestions(soil_data, all_alerts, conflicts)

        # ── 9. Summary ───────────────────────────────────────────────────────
        summary = svc.generate_summary(
            status,
            score,
            all_alerts,
            crop_type=getattr(soil_data, "crop_type", None),
        )

        # ── 10. Confidence + Data Quality ────────────────────────────────────
        confidence    = svc.compute_confidence(validation_errors, all_alerts)
        data_quality  = svc.compute_data_quality(soil_data, validation_errors)

        # ── 11. Critical Factors ─────────────────────────────────────────────
        critical_factors = svc.extract_critical_factors(all_alerts)

        return {
            # Core output
            "soil_health_score":  score,
            "soil_health_status": status,
            "summary":            summary,

            # Quality signals
            "confidence":         confidence,
            "data_quality_score": data_quality,
            "validation_errors":  validation_errors,

            # Alerts — separated for consumers that need granular routing
            "alerts":             all_alerts,
            "soil_alerts":        soil_alerts,
            "weather_alerts":     weather_alerts,
            "critical_factors":   critical_factors,

            # Recommendations
            "fertilizers":        fertilizers,
            "suggestions":        suggestions,
            "conflicts":          conflicts,
        }