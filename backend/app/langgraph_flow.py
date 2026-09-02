from __future__ import annotations

import operator
from collections.abc import AsyncIterator
from typing import Annotated, Literal, TypedDict

from ag_ui.core import BaseEvent, EventType, RunAgentInput, RunErrorEvent
from langgraph.graph import END, START, StateGraph

from .langgraph_agui_translator import LangGraphAguiTranslator


class LearningGraphState(TypedDict, total=False):
    """State that LangGraph carries independently of the AG-UI client state."""

    prompt: str
    intent: str
    route: Literal["tool", "direct"]
    tool_result: list[str]
    answer: str
    visited_nodes: Annotated[list[str], operator.add]


def understand(state: LearningGraphState) -> LearningGraphState:
    prompt = state.get("prompt", "").strip()
    normalized = prompt.casefold()
    use_tool = any(word in normalized for word in ("checkliste", "tool", "lernen"))
    return {
        "intent": "Lernschritte erzeugen" if use_tool else "Direkte Erklärung erzeugen",
        "route": "tool" if use_tool else "direct",
        "visited_nodes": ["understand"],
    }


def choose_route(state: LearningGraphState) -> Literal["tool", "direct"]:
    return state.get("route", "direct")


def learning_tool(state: LearningGraphState) -> LearningGraphState:
    topic = state.get("prompt", "den LangGraph-Flow")
    return {
        "tool_result": [
            f"Eingabe analysieren: {topic}",
            "Bedingte Kante auswerten",
            "Graph-State als AG-UI-Events sichtbar machen",
        ],
        "visited_nodes": ["learning_tool"],
    }


def respond(state: LearningGraphState) -> LearningGraphState:
    tool_result = state.get("tool_result")
    if tool_result:
        steps = " · ".join(tool_result)
        answer = f"LangGraph hat den Tool-Pfad gewählt. Die erzeugten Lernschritte sind: {steps}."
    else:
        answer = (
            "LangGraph hat den direkten Pfad gewählt: understand → respond. "
            f"Die Eingabe war: {state.get('prompt', '')}."
        )
    return {"answer": answer, "visited_nodes": ["respond"]}


def build_learning_graph():
    """Build the real, keyless LangGraph used only by lesson 08."""

    builder = StateGraph(LearningGraphState)
    builder.add_node("understand", understand)
    builder.add_node("learning_tool", learning_tool)
    builder.add_node("respond", respond)
    builder.add_edge(START, "understand")
    builder.add_conditional_edges(
        "understand",
        choose_route,
        {"tool": "learning_tool", "direct": "respond"},
    )
    builder.add_edge("learning_tool", "respond")
    builder.add_edge("respond", END)
    return builder.compile()


LEARNING_GRAPH = build_learning_graph()


def latest_user_text(input_data: RunAgentInput) -> str:
    for message in reversed(input_data.messages):
        if message.role == "user" and isinstance(message.content, str) and message.content.strip():
            return message.content.strip()
    return "Erkläre mir den LangGraph-Flow"


async def run_langgraph_flow(
    input_data: RunAgentInput, delay_ms: int = 180
) -> AsyncIterator[BaseEvent]:
    """Translate native StateGraph updates through the shared translator."""

    translator = LangGraphAguiTranslator(
        input_data,
        api="graph",
        workflow="graph-state-routing",
        delay_ms=delay_ms,
    )
    for event in translator.start_events(graphUpdates={}):
        yield event

    try:
        async for graph_update in LEARNING_GRAPH.astream(
            {"prompt": latest_user_text(input_data)}, stream_mode="updates"
        ):
            yield translator.runtime_chunk_event("updates", graph_update)
            for node_name, update in graph_update.items():
                async for event in translator.translate_graph_update(node_name, update):
                    yield event
    except Exception as exc:
        yield RunErrorEvent(
            type=EventType.RUN_ERROR,
            message=f"LangGraph-Flow fehlgeschlagen: {exc}",
            code="LANGGRAPH_ERROR",
        )
        return

    yield translator.success_finished()
