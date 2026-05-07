from langgraph.graph.state import CompiledStateGraph

from AI_Backend.agents.orchestrator.workflow import build_graph


_GRAPH: CompiledStateGraph | None = None


def get_graph() -> CompiledStateGraph:
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_graph()
    return _GRAPH
