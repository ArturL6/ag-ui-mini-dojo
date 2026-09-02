from __future__ import annotations

import asyncio
import operator
from collections.abc import AsyncIterator
from typing import Annotated, Any, Literal, TypedDict
from uuid import uuid4

from ag_ui.core import (
    BaseEvent,
    EventType,
    RunAgentInput,
    RunErrorEvent,
    RunFinishedEvent,
    RunStartedEvent,
    StateDeltaEvent,
    StateSnapshotEvent,
    StepFinishedEvent,
    StepStartedEvent,
    TextMessageContentEvent,
    TextMessageEndEvent,
    TextMessageStartEvent,
)
from langgraph.graph import END, START, StateGraph


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


async def pause(delay_ms: int) -> None:
    await asyncio.sleep(max(delay_ms, 0) / 1000)


def state_patch(node_name: str, update: LearningGraphState) -> list[dict[str, Any]]:
    patch: list[dict[str, Any]] = [
        {"op": "replace", "path": "/currentNode", "value": node_name},
        {"op": "add", "path": "/visitedNodes/-", "value": node_name},
    ]
    for source_key, target_key in (
        ("intent", "intent"),
        ("route", "route"),
        ("tool_result", "toolResult"),
    ):
        if source_key in update:
            patch.append({"op": "replace", "path": f"/{target_key}", "value": update[source_key]})
    return patch


async def answer_events(text: str, delay_ms: int) -> AsyncIterator[BaseEvent]:
    message_id = str(uuid4())
    yield TextMessageStartEvent(
        type=EventType.TEXT_MESSAGE_START,
        message_id=message_id,
        role="assistant",
    )
    words = text.split()
    for index in range(0, len(words), 4):
        chunk = " ".join(words[index : index + 4])
        if index + 4 < len(words):
            chunk += " "
        await pause(delay_ms)
        yield TextMessageContentEvent(
            type=EventType.TEXT_MESSAGE_CONTENT,
            message_id=message_id,
            delta=chunk,
        )
    yield TextMessageEndEvent(type=EventType.TEXT_MESSAGE_END, message_id=message_id)


async def run_langgraph_flow(
    input_data: RunAgentInput, delay_ms: int = 180
) -> AsyncIterator[BaseEvent]:
    """Translate LangGraph node updates into the same AG-UI event vocabulary."""

    yield RunStartedEvent(
        type=EventType.RUN_STARTED,
        thread_id=input_data.thread_id,
        run_id=input_data.run_id,
    )
    yield StateSnapshotEvent(
        type=EventType.STATE_SNAPSHOT,
        snapshot={
            "framework": "langgraph",
            "currentNode": "START",
            "visitedNodes": [],
            "intent": None,
            "route": "pending",
            "toolResult": None,
        },
    )

    try:
        async for graph_update in LEARNING_GRAPH.astream(
            {"prompt": latest_user_text(input_data)}, stream_mode="updates"
        ):
            for node_name, update in graph_update.items():
                yield StepStartedEvent(type=EventType.STEP_STARTED, step_name=node_name)
                yield StateDeltaEvent(
                    type=EventType.STATE_DELTA,
                    delta=state_patch(node_name, update),
                )
                if answer := update.get("answer"):
                    async for event in answer_events(answer, delay_ms):
                        yield event
                await pause(delay_ms)
                yield StepFinishedEvent(type=EventType.STEP_FINISHED, step_name=node_name)
    except Exception as exc:
        yield RunErrorEvent(
            type=EventType.RUN_ERROR,
            message=f"LangGraph-Flow fehlgeschlagen: {exc}",
            code="LANGGRAPH_ERROR",
        )
        return

    yield RunFinishedEvent(
        type=EventType.RUN_FINISHED,
        thread_id=input_data.thread_id,
        run_id=input_data.run_id,
        outcome={"type": "success"},
    )
