from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.core.enums import ConversationState
from app.graph.nodes import agent_node
from app.graph.state import GraphState
from app.schemas.parsed_intent import ParsedIntent


def build_conversation_graph(intent: ParsedIntent):
    graph = StateGraph(GraphState)

    async def _run_agent_node(state: GraphState) -> GraphState:
        return await agent_node(state, intent)

    graph.add_node("agent", _run_agent_node)

    graph.add_edge(START, "agent")
    graph.add_edge("agent", END)
    return graph.compile()
