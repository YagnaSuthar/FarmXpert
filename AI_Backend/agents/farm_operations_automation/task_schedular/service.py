# service.py
"""
FarmXpert Task Scheduler Agent — Service Layer
===============================================
Production FastAPI application exposing the scheduler as a REST API.

Endpoints:
    POST   /api/v1/schedule         — Generate a task plan
    POST   /api/v1/schedule/dry-run — Preview without persisting
    GET    /api/v1/plans/{plan_id}  — Retrieve a stored plan
    GET    /api/v1/health           — Liveness probe
    GET    /api/v1/ready            — Readiness probe
    GET    /api/v1/metrics          — Prometheus-style metrics

Design:
    - Fully async request handling
    - Structured JSON logging
    - Request ID propagation
    - Graceful error handling with standardized error bodies
    - OpenAPI docs auto-generated
"""

from __future__ import annotations

import asyncio
import logging
import time
import traceback
import uuid
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from agent import TaskSchedulerAgent
from config import settings
from schemas import (
    ScheduleRequest,
    ScheduleResponse,
    SchedulerInput,
    TaskPlan,
)

# ─────────────────────────────────────────────────────────────────────────────
# LOGGING SETUP
# ─────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
logger = logging.getLogger("farmxpert.service")


# ─────────────────────────────────────────────────────────────────────────────
# IN-MEMORY PLAN STORE (replace with Redis/DB in production)
# ─────────────────────────────────────────────────────────────────────────────

class PlanStore:
    """Thread-safe in-memory store for task plans."""

    def __init__(self) -> None:
        self._plans: Dict[str, TaskPlan] = {}
        self._lock = asyncio.Lock()

    async def save(self, plan: TaskPlan) -> None:
        async with self._lock:
            self._plans[plan.plan_id] = plan

    async def get(self, plan_id: str) -> Optional[TaskPlan]:
        async with self._lock:
            return self._plans.get(plan_id)

    async def count(self) -> int:
        async with self._lock:
            return len(self._plans)


# ─────────────────────────────────────────────────────────────────────────────
# METRICS COUNTERS (lightweight; swap for prometheus_client in production)
# ─────────────────────────────────────────────────────────────────────────────

class MetricsCounter:
    def __init__(self) -> None:
        self.total_requests: int = 0
        self.successful_plans: int = 0
        self.failed_plans: int = 0
        self.total_tasks_scheduled: int = 0
        self.total_conflicts_resolved: int = 0
        self.total_processing_ms: float = 0.0

    def record_success(self, plan: TaskPlan, elapsed_ms: float) -> None:
        self.total_requests += 1
        self.successful_plans += 1
        self.total_tasks_scheduled += plan.total_tasks_scheduled
        self.total_conflicts_resolved += len(plan.conflicts_detected)
        self.total_processing_ms += elapsed_ms

    def record_failure(self) -> None:
        self.total_requests += 1
        self.failed_plans += 1

    def to_dict(self) -> Dict[str, Any]:
        avg_ms = (
            self.total_processing_ms / self.successful_plans
            if self.successful_plans > 0 else 0.0
        )
        return {
            "total_requests": self.total_requests,
            "successful_plans": self.successful_plans,
            "failed_plans": self.failed_plans,
            "total_tasks_scheduled": self.total_tasks_scheduled,
            "total_conflicts_resolved": self.total_conflicts_resolved,
            "average_processing_ms": round(avg_ms, 2),
        }


# ─────────────────────────────────────────────────────────────────────────────
# APPLICATION SETUP
# ─────────────────────────────────────────────────────────────────────────────

plan_store = PlanStore()
metrics = MetricsCounter()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle hooks."""
    logger.info("=" * 60)
    logger.info("%s v%s starting", settings.APP_NAME, settings.APP_VERSION)
    logger.info("Environment : %s", settings.ENVIRONMENT)
    logger.info("Planning horizon : %d days (max %d)", settings.DEFAULT_PLANNING_HORIZON_DAYS, settings.MAX_PLANNING_HORIZON_DAYS)
    logger.info("=" * 60)
    yield
    logger.info("%s shutting down gracefully.", settings.APP_NAME)


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "FarmXpert Task Scheduler Agent — converts specialist agent recommendations "
        "into a prioritized, conflict-free, time-based farm execution plan."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────────────────────────────────────
# MIDDLEWARE
# ─────────────────────────────────────────────────────────────────────────────

@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    """Log every request with timing and inject request-id header."""
    request_id = request.headers.get("X-Request-ID", uuid.uuid4().hex)
    start = time.perf_counter()

    logger.info(
        "→ %s %s | request_id=%s | client=%s",
        request.method, request.url.path, request_id, request.client.host if request.client else "unknown"
    )

    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - start) * 1000

    response.headers["X-Request-ID"] = request_id
    response.headers["X-Processing-Time-Ms"] = f"{elapsed_ms:.2f}"

    logger.info(
        "← %s %s | status=%d | %.2fms | request_id=%s",
        request.method, request.url.path, response.status_code, elapsed_ms, request_id
    )
    return response


# ─────────────────────────────────────────────────────────────────────────────
# EXCEPTION HANDLERS
# ─────────────────────────────────────────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("Unhandled exception: %s\n%s", str(exc), traceback.format_exc())
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "success": False,
            "error": "Internal server error — see server logs.",
            "request_id": request.headers.get("X-Request-ID", ""),
        },
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": exc.detail,
            "request_id": request.headers.get("X-Request-ID", ""),
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# CORE ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

@app.post(
    "/api/v1/schedule",
    response_model=ScheduleResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate a task plan",
    tags=["Scheduling"],
)
async def create_schedule(request_body: ScheduleRequest) -> ScheduleResponse:
    """
    **Generate a prioritized, conflict-free task plan** from multi-agent recommendations.

    The scheduler:
    1. Validates all incoming recommendations (staleness, structure)
    2. Scores each recommendation using weighted urgency/risk/impact
    3. Applies weather, resource, and dependency constraints
    4. Resolves conflicts (same-category tasks on same day, etc.)
    5. Assigns time slots within working hours
    6. Enriches tasks with instructions, KPIs, and precautions
    7. Returns a structured `TaskPlan`

    Set `dry_run=true` to preview without persisting the plan.
    """
    t0 = time.perf_counter()
    request_id = request_body.scheduler_input.request_id

    logger.info(
        "Schedule request | request_id=%s | farm=%s | recs=%d | horizon=%dd",
        request_id,
        request_body.scheduler_input.farm_context.farm_id,
        len(request_body.scheduler_input.recommendations),
        request_body.scheduler_input.planning_horizon_days,
    )

    try:
        # Apply priority overrides if provided
        scheduler_input = request_body.scheduler_input
        if request_body.priority_override:
            scheduler_input = _apply_priority_overrides(
                scheduler_input, request_body.priority_override
            )

        # Run scheduler in executor to avoid blocking the event loop
        agent = TaskSchedulerAgent()
        loop = asyncio.get_running_loop()
        plan: TaskPlan = await loop.run_in_executor(None, agent.run, scheduler_input)

        elapsed_ms = (time.perf_counter() - t0) * 1000
        metrics.record_success(plan, elapsed_ms)

        # Persist (unless dry_run)
        if not scheduler_input.dry_run:
            await plan_store.save(plan)
            logger.info("Plan %s saved | farm=%s", plan.plan_id, plan.farm_id)

        return ScheduleResponse(
            success=True,
            request_id=request_id,
            plan=plan,
            processing_time_ms=round(elapsed_ms, 2),
        )

    except ValueError as exc:
        metrics.record_failure()
        logger.warning("Validation error for request %s: %s", request_id, str(exc))
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Input validation error: {str(exc)}",
        )
    except Exception as exc:
        metrics.record_failure()
        logger.error("Scheduling failed for request %s: %s", request_id, traceback.format_exc())
        elapsed_ms = (time.perf_counter() - t0) * 1000
        return ScheduleResponse(
            success=False,
            request_id=request_id,
            error=f"Scheduling failed: {str(exc)}",
            processing_time_ms=round(elapsed_ms, 2),
        )


@app.post(
    "/api/v1/schedule/dry-run",
    response_model=ScheduleResponse,
    status_code=status.HTTP_200_OK,
    summary="Preview a task plan (no persistence)",
    tags=["Scheduling"],
)
async def dry_run_schedule(request_body: ScheduleRequest) -> ScheduleResponse:
    """
    **Preview** a task plan without persisting it. Identical logic to `/schedule`
    but the plan is never saved. Use for testing or client-side previews.
    """
    # Force dry_run
    modified_input = request_body.scheduler_input.model_copy(update={"dry_run": True})
    modified_request = request_body.model_copy(
        update={"scheduler_input": modified_input}
    )
    return await create_schedule(modified_request)


@app.get(
    "/api/v1/plans/{plan_id}",
    response_model=ScheduleResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve a stored task plan",
    tags=["Plans"],
)
async def get_plan(plan_id: str) -> ScheduleResponse:
    """
    Retrieve a previously generated `TaskPlan` by its `plan_id`.
    Returns 404 if the plan is not found.
    """
    plan = await plan_store.get(plan_id)
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plan '{plan_id}' not found. It may have expired or was a dry-run.",
        )
    return ScheduleResponse(
        success=True,
        request_id=plan.request_id,
        plan=plan,
        processing_time_ms=0.0,
    )


# ─────────────────────────────────────────────────────────────────────────────
# OPERATIONS ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

@app.get(
    "/api/v1/health",
    status_code=status.HTTP_200_OK,
    summary="Liveness probe",
    tags=["Operations"],
)
async def health_check() -> Dict[str, Any]:
    """Kubernetes liveness probe — always returns 200 if the app is running."""
    return {
        "status": "ok",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
    }


@app.get(
    "/api/v1/ready",
    status_code=status.HTTP_200_OK,
    summary="Readiness probe",
    tags=["Operations"],
)
async def readiness_check() -> Dict[str, Any]:
    """
    Kubernetes readiness probe.
    Checks that the scheduler engine and plan store are operational.
    """
    checks: Dict[str, str] = {}
    overall = "ready"

    # Basic agent instantiation check
    try:
        _ = TaskSchedulerAgent()
        checks["scheduler_engine"] = "ok"
    except Exception as exc:
        checks["scheduler_engine"] = f"error: {exc}"
        overall = "degraded"

    # Plan store check
    try:
        count = await plan_store.count()
        checks["plan_store"] = f"ok ({count} plans cached)"
    except Exception as exc:
        checks["plan_store"] = f"error: {exc}"
        overall = "degraded"

    return {
        "status": overall,
        "checks": checks,
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
    }


@app.get(
    "/api/v1/metrics",
    status_code=status.HTTP_200_OK,
    summary="Service metrics",
    tags=["Operations"],
)
async def get_metrics() -> Dict[str, Any]:
    """Return lightweight service metrics for monitoring dashboards."""
    store_count = await plan_store.count()
    return {
        **metrics.to_dict(),
        "plans_cached": store_count,
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
    }


@app.get(
    "/api/v1/config",
    status_code=status.HTTP_200_OK,
    summary="Runtime configuration",
    tags=["Operations"],
)
async def get_config() -> Dict[str, Any]:
    """
    Return non-sensitive runtime configuration for debugging.
    Sensitive fields (DB URLs, DSNs) are masked.
    """
    return {
        "app_name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "planning_horizon_days": settings.DEFAULT_PLANNING_HORIZON_DAYS,
        "priority_weights": {
            "urgency": settings.PRIORITY_WEIGHT_URGENCY,
            "risk": settings.PRIORITY_WEIGHT_RISK,
            "impact": settings.PRIORITY_WEIGHT_IMPACT,
        },
        "weather_thresholds": {
            "rain_delay_percent": settings.RAIN_PROBABILITY_DELAY_THRESHOLD,
            "wind_spray_max_kmh": settings.WIND_SPEED_SPRAY_MAX_KMH,
            "heat_stress_c": settings.HEAT_STRESS_TEMP_C,
        },
        "max_tasks_per_day": settings.MAX_TASKS_PER_DAY,
        "working_hours": f"{settings.DEFAULT_WORK_START_HOUR:02d}:00 – {settings.DEFAULT_WORK_END_HOUR:02d}:00",
        "recommendation_stale_hours": settings.RECOMMENDATION_STALE_HOURS,
    }


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _apply_priority_overrides(
    scheduler_input: SchedulerInput,
    overrides: Dict[str, float],
) -> SchedulerInput:
    """
    Mutate score fields on specific recommendations based on caller-supplied
    override map: { recommendation_id: urgency_score_override }.
    """
    updated_recs = []
    for rec in scheduler_input.recommendations:
        if rec.recommendation_id in overrides:
            override_urgency = float(overrides[rec.recommendation_id])
            rec = rec.model_copy(update={"urgency_score": override_urgency})
            logger.info(
                "Priority override applied to %s → urgency_score=%s",
                rec.recommendation_id, override_urgency
            )
        updated_recs.append(rec)

    return scheduler_input.model_copy(update={"recommendations": updated_recs})


# ─────────────────────────────────────────────────────────────────────────────
# ENTRYPOINT
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        "service:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        workers=settings.API_WORKERS,
        log_level=settings.LOG_LEVEL.lower(),
        reload=settings.ENVIRONMENT == "development",
        access_log=True,
    )