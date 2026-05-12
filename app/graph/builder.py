from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.core.enums import ConversationState
from app.graph.nodes import (
    closing_node,
    confirming_node,
    escalating_node,
    greeting_node,
    negotiating_node,
    understanding_node,
    voicemail_node,
)
from app.graph.state import GraphState
from app.schemas.parsed_intent import ParsedIntent


def build_conversation_graph(intent: ParsedIntent):
    graph = StateGraph(GraphState)

    graph.add_node("greeting", lambda state: greeting_node(state, intent))
    graph.add_node("understanding", lambda state: understanding_node(state, intent))
    graph.add_node("negotiating", lambda state: negotiating_node(state, intent))
    graph.add_node("confirming", lambda state: confirming_node(state, intent))
    graph.add_node("closing", lambda state: closing_node(state, intent))
    graph.add_node("escalating", lambda state: escalating_node(state, intent))
    graph.add_node("voicemail", lambda state: voicemail_node(state, intent))

    def route_from_start(state: GraphState) -> str:
        return state.get("current_state", ConversationState.GREETING.value)

    graph.add_conditional_edges(
        START,
        route_from_start,
        {
            ConversationState.GREETING.value: "greeting",
            ConversationState.UNDERSTANDING.value: "understanding",
            ConversationState.NEGOTIATING.value: "negotiating",
            ConversationState.CONFIRMING.value: "confirming",
            ConversationState.CLOSING.value: "closing",
            ConversationState.ESCALATING.value: "escalating",
            ConversationState.VOICEMAIL.value: "voicemail",
        },
    )

    graph.add_edge("greeting", END)
    graph.add_edge("understanding", END)
    graph.add_edge("negotiating", END)
    graph.add_edge("confirming", END)
    graph.add_edge("closing", END)
    graph.add_edge("escalating", END)
    graph.add_edge("voicemail", END)
    return graph.compile()
