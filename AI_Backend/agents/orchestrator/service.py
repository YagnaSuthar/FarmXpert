from AI_Backend.agents.orchestrator.graph import get_graph


class OrchestratorService:
    async def run(self, state: dict) -> dict:
        graph = get_graph()
        return await graph.ainvoke(state)
