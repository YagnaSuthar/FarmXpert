"""
Agent registry
===============
The catalog. The only module that knows which agents exist.

A bad dependency graph is rejected at registration - that is, at import time,
before the process serves a single request - rather than discovered when a
farmer asks a question. An unknown dependency or a cycle raises here.
"""

from __future__ import annotations

import logging
from typing import Dict, Iterable, List, Optional, Sequence, Set

from AI_Backend.orchestration.contracts import AgentSpec, Capability

logger = logging.getLogger("farmxpert.orchestration.registry")


class RegistryError(ValueError):
    """The agent catalog is not usable as declared."""


class AgentRegistry:
    """Registered agents, indexed by name and by capability."""

    def __init__(self) -> None:
        self._agents: Dict[str, AgentSpec] = {}

    # ── registration ────────────────────────────────────────────────────

    def register(self, spec: AgentSpec, *, replace: bool = False) -> AgentSpec:
        """Add an agent. Raises RegistryError if the catalog would break.

        Validation runs against the whole catalog after the addition, so a
        cycle is caught the moment the edge that closes it is added.
        """
        if not replace and spec.name in self._agents:
            raise RegistryError(f"Agent '{spec.name}' is already registered.")
        if not spec.capabilities:
            raise RegistryError(f"Agent '{spec.name}' declares no capabilities, "
                                "so nothing could ever select it.")

        previous = self._agents.get(spec.name)
        self._agents[spec.name] = spec
        try:
            self.validate()
        except RegistryError:
            # Leave the catalog exactly as it was.
            if previous is None:
                self._agents.pop(spec.name, None)
            else:
                self._agents[spec.name] = previous
            raise

        logger.info("Agent registered | name=%s version=%s capabilities=%s",
                    spec.name, spec.version,
                    sorted(c.value for c in spec.capabilities))
        return spec

    def unregister(self, name: str) -> None:
        self._agents.pop(name, None)

    def set_enabled(self, name: str, enabled: bool) -> AgentSpec:
        """Turn an agent off without removing it.

        A disabled agent is treated as absent by the planner: requests that
        needed it are skipped with a reason, and nothing crashes. This is the
        lever to pull when an upstream provider is down.
        """
        spec = self.require(name)
        updated = _replace(spec, enabled=enabled)
        self._agents[name] = updated
        logger.warning("Agent %s | name=%s", "enabled" if enabled else "DISABLED", name)
        return updated

    # ── lookup ──────────────────────────────────────────────────────────

    def get(self, name: str) -> Optional[AgentSpec]:
        return self._agents.get(name)

    def require(self, name: str) -> AgentSpec:
        spec = self._agents.get(name)
        if spec is None:
            raise RegistryError(f"Unknown agent '{name}'.")
        return spec

    def all(self, *, include_disabled: bool = False) -> List[AgentSpec]:
        return [s for s in self._agents.values() if include_disabled or s.enabled]

    def names(self, *, include_disabled: bool = False) -> Set[str]:
        return {s.name for s in self.all(include_disabled=include_disabled)}

    def by_capability(self, capability: Capability) -> List[AgentSpec]:
        return [s for s in self.all() if capability in s.capabilities]

    def resolve(self, names: Iterable[str]) -> List[AgentSpec]:
        """Names to specs, dropping anything unknown or disabled.

        Client- or model-supplied names pass through here, which is what keeps
        a generated string from ever reaching execution.
        """
        out: List[AgentSpec] = []
        for name in names:
            spec = self._agents.get(name)
            if spec is None:
                logger.warning("Ignoring unknown agent name | name=%s", name)
                continue
            if not spec.enabled:
                logger.info("Ignoring disabled agent | name=%s", name)
                continue
            out.append(spec)
        return out

    # ── graph validation ────────────────────────────────────────────────

    def validate(self) -> None:
        """Every dependency exists, and the graph is acyclic."""
        known = set(self._agents)
        for spec in self._agents.values():
            unknown = spec.all_dependencies - known
            if unknown:
                raise RegistryError(
                    f"Agent '{spec.name}' depends on unregistered agent(s): "
                    f"{', '.join(sorted(unknown))}.")

        cycle = self._find_cycle()
        if cycle:
            raise RegistryError(
                "Circular dependency between agents: " + " -> ".join(cycle))

    def _find_cycle(self) -> Optional[List[str]]:
        """Depth-first search returning the first cycle found, as a path."""
        WHITE, GREY, BLACK = 0, 1, 2
        colour = {name: WHITE for name in self._agents}
        path: List[str] = []

        def visit(name: str) -> Optional[List[str]]:
            colour[name] = GREY
            path.append(name)
            for dep in sorted(self._agents[name].all_dependencies):
                if colour.get(dep) == GREY:
                    return path[path.index(dep):] + [dep]
                if colour.get(dep) == WHITE:
                    found = visit(dep)
                    if found:
                        return found
            path.pop()
            colour[name] = BLACK
            return None

        for name in sorted(self._agents):
            if colour[name] == WHITE:
                found = visit(name)
                if found:
                    return found
        return None

    def expand_dependencies(self, seeds: Sequence[AgentSpec]) -> List[AgentSpec]:
        """Seeds plus everything they need, transitively.

        Asking for irrigation advice pulls in the weather agent without the
        caller having to know that irrigation needs weather.
        """
        selected: Dict[str, AgentSpec] = {}
        queue = list(seeds)
        while queue:
            spec = queue.pop()
            if spec.name in selected:
                continue
            selected[spec.name] = spec
            for dep_name in sorted(spec.all_dependencies):
                dep = self._agents.get(dep_name)
                if dep is None or not dep.enabled:
                    continue          # planner reports this as a skip
                if dep.name not in selected:
                    queue.append(dep)
        return list(selected.values())

    def catalog(self) -> List[dict]:
        """A description of the catalog for the API and the MCP server."""
        return [{
            "name": s.name,
            "version": s.version,
            "description": s.description,
            "enabled": s.enabled,
            "capabilities": sorted(c.value for c in s.capabilities),
            "requires_context": sorted(s.requires_context),
            "optional_context": sorted(s.optional_context),
            "depends_on": sorted(s.depends_on),
            "optional_depends_on": sorted(s.optional_depends_on),
            "criticality": s.criticality.value,
            "timeout_s": s.timeout_s,
            "max_attempts": s.retry.max_attempts,
            "input_schema": s.input_schema,
        } for s in sorted(self._agents.values(), key=lambda s: s.name)]


def _replace(spec: AgentSpec, **changes) -> AgentSpec:
    import dataclasses
    return dataclasses.replace(spec, **changes)


# The process-wide catalog. Populated by orchestration.agents at import.
REGISTRY = AgentRegistry()
