import asyncio

from langgraph.graph import StateGraph, START, END
from AI_Backend.agents.orchestrator.state import FarmState

from AI_Backend.agents.crop_planning_growth.weather_watcher.agent import WeatherAgent
from AI_Backend.agents.crop_planning_growth.soil_Health.agent import SoilHealthAgent
from AI_Backend.agents.crop_planning_growth.crop_selector.agent import CropSelectorAgent
from AI_Backend.agents.crop_planning_growth.irrigation_planner.agent import IrrigationAgent

weather_agent = WeatherAgent("weather")

soil_agent = SoilHealthAgent()

crop_selector_agent = CropSelectorAgent()

irrigation_agent = IrrigationAgent()


def build_graph():
    workflow = StateGraph(FarmState)

    workflow.add_node("weather", weather_agent)
    workflow.add_node("soil", soil_agent)
    workflow.add_node("cropselector", crop_selector_agent)
    workflow.add_node("irrigation", irrigation_agent)

    workflow.add_edge(START, "weather")
    workflow.add_edge(START, "soil")

    workflow.add_edge("weather", "cropselector")
    workflow.add_edge("soil", "cropselector")

    workflow.add_edge("weather", "irrigation")
    workflow.add_edge("soil", "irrigation")

    workflow.add_edge("cropselector", END)
    workflow.add_edge("irrigation", END)

    return workflow.compile()


async def main():
    graph = build_graph()
    result = await graph.ainvoke({
        "query": "Should I irrigate tomorrow?",
        "lat": 23.0225,
        "lon": 72.5714,
        "weather_data": None,
        "soil_data": None,
        "irrigation_advice": None,
        "crop_recommendation": None,
    })
    print(result)

# To run the main function, you would need to call asyncio.run(main()) from another script