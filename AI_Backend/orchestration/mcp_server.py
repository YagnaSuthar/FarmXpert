"""
MCP server — FarmXpert agents as tools
=======================================
Generated from the registry, so every registered agent is an MCP tool
automatically. Adding an agent gives it an MCP tool for free; there is no
second list to keep in sync and no chance of the two drifting apart.

Three kinds of tool are exposed:

  farm_<agent>        one agent, called directly
  farm_orchestrate    the full orchestration - selection, dependencies,
                      concurrency, conflict detection - as one call
  farm_agents         the catalog, so a client can discover what exists

Run it over stdio:

    python -m AI_Backend.orchestration.mcp_server

Safety: a tool name is resolved against the registry, exactly like the HTTP
path, so a client cannot invoke anything that is not registered and enabled.
The MCP layer calls the same in-process functions as the API - there is no
duplicated business logic anywhere in this file.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from typing import Any, Dict, List, Optional

from AI_Backend.orchestration.agents import register_all
from AI_Backend.orchestration.contracts import AgentSpec, ExecutionContext
from AI_Backend.orchestration.registry import REGISTRY
from AI_Backend.orchestration.schemas import OrchestrationRequest
from AI_Backend.orchestration.service import OrchestratorService

logger = logging.getLogger("farmxpert.mcp")

SERVER_NAME = "farmxpert"
SERVER_VERSION = "1.0.0"
PROTOCOL_VERSION = "2024-11-05"

TOOL_PREFIX = "farm_"
ORCHESTRATE_TOOL = f"{TOOL_PREFIX}orchestrate"
CATALOG_TOOL = f"{TOOL_PREFIX}agents"


# ── tool definitions, built from the registry ───────────────────────────────

def tool_definitions() -> List[Dict[str, Any]]:
    """Every enabled agent, plus orchestration and catalog tools."""
    tools: List[Dict[str, Any]] = [{
        "name": ORCHESTRATE_TOOL,
        "description": ("Answer a farm question end to end: FarmXpert picks the right "
                        "agents, runs them in dependency order, and returns their "
                        "combined findings with provenance. Prefer this over calling "
                        "single agents when the question is not narrowly technical."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The farmer's question."},
                "farm_id": {"type": "string"},
                "lat": {"type": "number"}, "lon": {"type": "number"},
                "crop": {"type": "string", "description": "Crop currently grown."},
                "growth_stage": {"type": "string"},
                "soil": {"type": "object",
                         "description": "Readings, e.g. soil_ph, electrical_conductivity."},
                "intents": {"type": "array", "items": {"type": "string"},
                            "description": "daily_plan | irrigation | crop_choice | soil | "
                                           "weather | market | ask"},
            },
        },
    }, {
        "name": CATALOG_TOOL,
        "description": "List FarmXpert agents, what each needs, and what it depends on.",
        "inputSchema": {"type": "object", "properties": {}},
    }]

    for spec in sorted(REGISTRY.all(), key=lambda s: s.name):
        tools.append(_tool_for(spec))
    return tools


def _tool_for(spec: AgentSpec) -> Dict[str, Any]:
    schema = spec.input_schema or {"type": "object", "properties": {}}
    needs = ", ".join(sorted(spec.requires_context)) or "nothing"
    return {
        "name": f"{TOOL_PREFIX}{spec.name}",
        "description": f"{spec.description} (v{spec.version}; needs {needs})",
        "inputSchema": schema,
    }


# ── dispatch ────────────────────────────────────────────────────────────────

async def call_tool(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Run one tool. Unknown names are refused, never guessed at."""
    arguments = arguments or {}

    if name == CATALOG_TOOL:
        return {"agents": REGISTRY.catalog()}

    if name == ORCHESTRATE_TOOL:
        return await _orchestrate(arguments)

    if not name.startswith(TOOL_PREFIX):
        raise ValueError(f"Unknown tool: {name}")

    spec = REGISTRY.get(name[len(TOOL_PREFIX):])
    if spec is None or not spec.enabled:
        raise ValueError(f"Unknown or disabled agent tool: {name}")
    return await _single_agent(spec, arguments)


async def _orchestrate(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """The full pipeline, through the same service the HTTP API uses."""
    from AI_Backend.orchestration.planner import Intent

    request: Dict[str, Any] = {
        "query": arguments.get("query"),
        "farm_id": arguments.get("farm_id"),
        "soil": arguments.get("soil"),
        "explain": bool(arguments.get("explain", False)),
    }
    if arguments.get("lat") is not None and arguments.get("lon") is not None:
        request["location"] = {"lat": arguments["lat"], "lon": arguments["lon"]}
    crop = {k: arguments[k] for k in ("crop", "growth_stage") if arguments.get(k)}
    if crop:
        request["crop"] = {"name": crop.get("crop"),
                           "growth_stage": crop.get("growth_stage")}
    intents = []
    for value in arguments.get("intents") or []:
        try:
            intents.append(Intent(str(value)))
        except ValueError:
            logger.warning("Ignoring unknown intent from MCP client: %r", value)
    if intents:
        request["intents"] = intents
    if not any((request.get("query"), intents)):
        request["intents"] = [Intent.DAILY_PLAN]

    response = await OrchestratorService().run(
        OrchestrationRequest.model_validate({k: v for k, v in request.items() if v is not None}))
    return response.model_dump(mode="json")


async def _single_agent(spec: AgentSpec, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """One agent, with its own timeout and validation still applied.

    It runs through the same engine as any other execution, so an MCP caller
    gets the same timeout, retry and output-validation guarantees as the API.
    """
    from AI_Backend.orchestration.engine import ExecutionEngine
    from AI_Backend.orchestration.planner import ExecutionPlan

    context = _context_from(arguments)
    missing = spec.missing_context(context.available_context())
    if missing:
        return {"status": "skipped",
                "reason": f"This agent needs: {', '.join(sorted(missing))}."}

    plan = ExecutionPlan(levels=[[spec]], skipped=[], selected_names=[spec.name])
    results = await ExecutionEngine().run(plan, context)
    result = results[spec.name]
    return {
        "status": result.status.value,
        "result": result.output.data if result.output else None,
        "confidence": result.output.confidence if result.output else None,
        "duration_ms": round(result.duration_ms, 1),
        "error": result.error_message,
        "error_code": result.error_code.value if result.error_code else None,
    }


def _context_from(arguments: Dict[str, Any]) -> ExecutionContext:
    import uuid

    location = None
    if arguments.get("lat") is not None and arguments.get("lon") is not None:
        location = {"lat": float(arguments["lat"]), "lon": float(arguments["lon"])}

    soil = arguments.get("soil")
    if soil is None:
        soil = {k: arguments[k] for k in
                ("soil_ph", "ph", "electrical_conductivity", "ec_ds_m",
                 "soil_moisture", "soil_type") if arguments.get(k) is not None} or None

    crop = {k: v for k, v in (("name", arguments.get("crop")),
                              ("growth_stage", arguments.get("growth_stage"))) if v}

    return ExecutionContext(
        request_id=f"mcp-{uuid.uuid4().hex[:10]}",
        farm_id=arguments.get("farm_id"),
        farmer_query=arguments.get("question") or arguments.get("query"),
        location=location,
        soil=soil,
        crop=crop or None,
        market={k: arguments[k] for k in ("commodity", "state", "district")
                if arguments.get(k)} or None)


# ── stdio transport ─────────────────────────────────────────────────────────

async def _serve_stdio() -> None:
    """Minimal JSON-RPC over stdio.

    Reads stdin on a worker thread rather than through
    `loop.connect_read_pipe`: that call raises NotImplementedError on
    Windows' Proactor loop, which would make this server refuse to start on
    exactly the machine FarmXpert is developed on. A thread works on every
    platform and stdin is not a throughput concern here.

    Written against the protocol directly rather than pulling in an SDK: the
    surface used is three methods, and a new dependency in a farm backend
    needs a better reason than saving forty lines.
    """
    register_all()
    loop = asyncio.get_running_loop()

    while True:
        line = await loop.run_in_executor(None, sys.stdin.readline)
        if not line:
            break
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except ValueError:
            logger.warning("Ignoring malformed JSON-RPC line.")
            continue

        try:
            response = await _handle(message)
        except Exception:  # noqa: BLE001 - the server must outlive one bad call
            logger.error("MCP request failed", exc_info=True)
            response = {"jsonrpc": "2.0", "id": message.get("id"),
                        "error": {"code": -32603, "message": "Internal error"}}
        if response is not None:
            sys.stdout.write(json.dumps(response, default=str) + "\n")
            sys.stdout.flush()


async def _handle(message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    method = message.get("method")
    message_id = message.get("id")

    if method == "initialize":
        return _ok(message_id, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION}})

    if method == "tools/list":
        return _ok(message_id, {"tools": tool_definitions()})

    if method == "tools/call":
        params = message.get("params") or {}
        try:
            result = await call_tool(params.get("name", ""), params.get("arguments") or {})
            return _ok(message_id, {
                "content": [{"type": "text", "text": json.dumps(result, default=str)}]})
        except ValueError as exc:
            return _ok(message_id, {
                "content": [{"type": "text", "text": str(exc)}], "isError": True})
        except Exception as exc:  # noqa: BLE001 - transport boundary
            logger.error("MCP tool failed | tool=%s", params.get("name"), exc_info=True)
            return _ok(message_id, {
                "content": [{"type": "text",
                             "text": f"{params.get('name')} failed: {type(exc).__name__}"}],
                "isError": True})

    if message_id is None:
        return None            # a notification needs no reply
    return {"jsonrpc": "2.0", "id": message_id,
            "error": {"code": -32601, "message": f"Unknown method: {method}"}}


def _ok(message_id: Any, result: Dict[str, Any]) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": message_id, "result": result}


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
    asyncio.run(_serve_stdio())
