"""
Execution planner
==================
Decides WHICH agents run and IN WHAT ORDER. It runs nothing itself.

Selection is deterministic: an intent maps to capabilities, capabilities map
to registered agents, dependencies are pulled in transitively. A language
model may propose an intent, but it can never name an agent - whatever it
proposes is intersected with the catalog before it reaches this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Sequence, Set

from AI_Backend.orchestration.contracts import AgentSpec, Capability, ExecutionContext
from AI_Backend.orchestration.registry import AgentRegistry


class Intent(str, Enum):
    """What the farmer is asking for, in a closed set.

    Closed on purpose: every value here has been thought about, and an
    unrecognised intent falls back to ASK rather than inventing a workflow.
    """
    DAILY_PLAN  = "daily_plan"      # "what should I do today?"
    IRRIGATION  = "irrigation"      # "should I water?"
    CROP_CHOICE = "crop_choice"     # "what should I sow?"
    SOIL        = "soil"
    WEATHER     = "weather"
    MARKET      = "market"
    ASK         = "ask"             # a free-text question -> knowledge answer
    FULL_SCAN   = "full_scan"       # everything that can run, for a dashboard


# An intent asks for capabilities, never for agents. Adding an agent that
# provides an existing capability needs no change here.
INTENT_CAPABILITIES: Dict[Intent, Set[Capability]] = {
    Intent.DAILY_PLAN:  {Capability.WORK_PLAN},
    Intent.IRRIGATION:  {Capability.IRRIGATION_ADVICE},
    Intent.CROP_CHOICE: {Capability.CROP_SELECTION},
    Intent.SOIL:        {Capability.SOIL_ASSESSMENT},
    Intent.WEATHER:     {Capability.WEATHER_FORECAST},
    Intent.MARKET:      {Capability.MARKET_INTELLIGENCE},
    Intent.ASK:         {Capability.KNOWLEDGE_ANSWER},
    Intent.FULL_SCAN:   set(Capability),
}


@dataclass
class SkippedAgent:
    name: str
    reason: str
    missing: List[str] = field(default_factory=list)


@dataclass
class ExecutionPlan:
    """What will run, in which order, and what will not run and why."""
    levels: List[List[AgentSpec]]
    skipped: List[SkippedAgent]
    selected_names: List[str]

    @property
    def is_empty(self) -> bool:
        return not any(self.levels)

    def describe(self) -> List[List[str]]:
        return [[spec.name for spec in level] for level in self.levels]


class Planner:
    """Turns a request into an ordered, validated execution plan."""

    def __init__(self, registry: AgentRegistry) -> None:
        self.registry = registry

    def plan(self,
             context: ExecutionContext,
             *,
             intents: Sequence[Intent] = (),
             capabilities: Sequence[Capability] = (),
             agent_names: Sequence[str] = ()) -> ExecutionPlan:
        """Select agents, resolve dependencies, and order them into levels."""
        seeds = self._seeds(intents, capabilities, agent_names)
        selected = self.registry.expand_dependencies(seeds)

        runnable, skipped = self._drop_unsatisfiable(selected, context)
        levels = self._levels(runnable)

        return ExecutionPlan(levels=levels, skipped=skipped,
                             selected_names=sorted(s.name for s in runnable))

    # ── selection ───────────────────────────────────────────────────────

    def _seeds(self,
               intents: Sequence[Intent],
               capabilities: Sequence[Capability],
               agent_names: Sequence[str]) -> List[AgentSpec]:
        wanted: Set[Capability] = set(capabilities)
        for intent in intents:
            wanted |= INTENT_CAPABILITIES.get(intent, set())

        seeds: Dict[str, AgentSpec] = {}
        for capability in wanted:
            for spec in self.registry.by_capability(capability):
                seeds[spec.name] = spec

        # Explicit names are allowed, but only ones in the catalog. This is
        # the single gate that client- and model-supplied names pass through.
        for spec in self.registry.resolve(agent_names):
            seeds[spec.name] = spec

        return list(seeds.values())

    def _drop_unsatisfiable(self,
                            selected: Sequence[AgentSpec],
                            context: ExecutionContext):
        """Remove agents that cannot possibly work, and say why.

        Done before execution so a farmer is told "no location was provided"
        instead of waiting for a timeout and getting a generic failure. It
        repeats until stable, because dropping one agent can strand another
        that required it.
        """
        available = context.available_context()
        alive: Dict[str, AgentSpec] = {s.name: s for s in selected}
        skipped: List[SkippedAgent] = []

        for spec in list(alive.values()):
            missing = spec.missing_context(available)
            if missing:
                del alive[spec.name]
                skipped.append(SkippedAgent(
                    name=spec.name,
                    reason="Required information was not provided.",
                    missing=sorted(missing)))

        changed = True
        while changed:
            changed = False
            for spec in list(alive.values()):
                stranded = sorted(spec.depends_on - set(alive))
                if stranded:
                    del alive[spec.name]
                    skipped.append(SkippedAgent(
                        name=spec.name,
                        reason=f"Depends on {', '.join(stranded)}, which cannot run.",
                        missing=stranded))
                    changed = True

        return list(alive.values()), skipped

    # ── ordering ────────────────────────────────────────────────────────

    @staticmethod
    def _levels(specs: Sequence[AgentSpec]) -> List[List[AgentSpec]]:
        """Kahn's algorithm, grouped into levels.

        Everything in one level is independent of everything else in it, so
        the engine can run a whole level concurrently. Only dependencies
        WITHIN the selection count: a dependency that was not selected has
        already been handled by _drop_unsatisfiable.
        """
        by_name = {s.name: s for s in specs}
        pending = {s.name: set(s.all_dependencies) & set(by_name) for s in specs}

        levels: List[List[AgentSpec]] = []
        while pending:
            ready = sorted(name for name, deps in pending.items() if not deps)
            if not ready:
                # The registry rejects cycles at registration, so reaching
                # this point means the catalog was mutated unsafely. Fail
                # loudly rather than deadlock or drop work silently.
                raise RuntimeError(
                    "Cycle detected while ordering agents: "
                    + ", ".join(sorted(pending)))
            levels.append([by_name[name] for name in ready])
            for name in ready:
                del pending[name]
            for deps in pending.values():
                deps.difference_update(ready)

        return levels
