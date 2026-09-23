"""
Agent registration
===================
The single place agents are added to the catalog.

Adding an agent to FarmXpert is: write its adapter beside these, then add one
line to `_BUILDERS`. Nothing in the engine, planner, failure handling,
aggregation, logging or the MCP server changes.

A builder that raises is logged and skipped. That matters: a missing ML
artefact or an unreachable optional dependency must cost the farm one agent,
not the whole backend.
"""

from __future__ import annotations

import logging
from typing import Callable, List

from AI_Backend.orchestration.agents.field_agents import (
    build_crop,
    build_irrigation,
    build_market,
    build_scheduler,
    build_soil,
    build_weather,
)
from AI_Backend.orchestration.agents.retrieval_agent import build_retrieval
from AI_Backend.orchestration.contracts import AgentSpec
from AI_Backend.orchestration.registry import REGISTRY, AgentRegistry

logger = logging.getLogger("farmxpert.orchestration.registry")

# Order is irrelevant: dependencies are resolved by name, and the registry
# validates the whole graph after each addition.
_BUILDERS: List[Callable[[], AgentSpec]] = [
    build_weather,
    build_soil,
    build_irrigation,
    build_crop,
    build_scheduler,
    build_market,
    build_retrieval,
]


def register_all(registry: AgentRegistry = REGISTRY, *, replace: bool = True) -> int:
    """Build and register every agent. Returns how many are usable."""
    registered = 0
    for builder in _BUILDERS:
        name = getattr(builder, "__name__", "?")
        try:
            registry.register(builder(), replace=replace)
            registered += 1
        except Exception as exc:  # noqa: BLE001 - one agent must not stop the rest
            logger.error("Agent unavailable | builder=%s error=%s: %s",
                         name, type(exc).__name__, exc)
    logger.info("Agent catalog ready | registered=%d of %d", registered, len(_BUILDERS))
    return registered


__all__ = ["register_all", "_BUILDERS"]
