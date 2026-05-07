# app/crop_planning_growth/soil_Health/agent.py

from AI_Backend.agents.crop_planning_growth.soil_Health.service import SoilHealthService


class SoilHealthAgent:
    """Orchestrator — delegates all logic to SoilHealthService."""

    def __init__(self):
        self.service = SoilHealthService()
    async def __call__(self, state):

        return await self.run(state)
    async def run(self, soil_data) -> dict:
        svc = self.service

        # 1. Validate inputs
        _, validation_errors = svc.validate(soil_data)

        # 2. Analyze (deficiency + excess)
        alerts = svc.analyze(soil_data)

        # 3. Detect conflicts (fertilizer applied but nutrient still low)
        conflicts = svc.detect_conflicts(soil_data, alerts)

        # 3a. Add conflict alerts (severity = high — deficiency persists despite treatment)
        for c in conflicts:
            alerts.append({
                "type": "CONFLICT",
                "message": f"Fertilizer '{c['fertilizer_applied']}' may be insufficient for {c['message']}",
                "severity": "high",
            })

        # 4. Score + Status
        score = svc.calculate_score(soil_data)
        status = svc.get_status(score)

        # 5. Fertilizers (deduplicated)
        fertilizers = svc.recommend_fertilizer(alerts)

        # 6. Suggestions (includes conflict tips, always ≥ 1)
        suggestions = svc.suggestions(soil_data, alerts, conflicts)

        # 7. Summary (top 2–3 high-severity issues)
        summary = svc.generate_summary(status, alerts)

        # 8. Confidence + Data Quality
        confidence = svc.compute_confidence(validation_errors, alerts)
        data_quality = svc.compute_data_quality(soil_data, validation_errors)

        # 9. Critical factors (HIGH severity alert types only)
        critical_factors = svc.extract_critical_factors(alerts)

        return {
            "soil_health_score": score,
            "soil_health_status": status,
            "summary": summary,
            "confidence": confidence,
            "data_quality_score": data_quality,
            "critical_factors": critical_factors,
            "alerts": alerts,
            "fertilizers": fertilizers,
            "suggestions": suggestions,
        }