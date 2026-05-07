from fastapi import APIRouter, HTTPException, status

from AI_Backend.agents.orchestrator.service import OrchestratorService


router = APIRouter(prefix="/orchestrator", tags=["Orchestrator"])

service = OrchestratorService()


@router.post("/run")
async def run_orchestrator(payload: dict):
    try:
        return await service.run(payload)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Orchestration failed: {str(e)}",
        )
