from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any, Literal, TypedDict
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
from langgraph.config import get_stream_writer
from langgraph.func import entrypoint, task


class Decision(TypedDict):
    intent: str
    route: Literal["tool", "direct"]


class FunctionalResult(TypedDict):
    route: Literal["tool", "direct"]
    answer: str
    task_order: list[str]


def emit_task_event(task_name: str, phase: Literal["started", "finished"], **data: Any) -> None:
    """Emit data through LangGraph's active custom StreamWriter."""

    get_stream_writer()(
        {
            "source": "langgraph-functional-api",
            "task": task_name,
            "phase": phase,
            **data,
        }
    )


@task
def understand_task(prompt: str) -> Decision:
    emit_task_event("understand_task", "started", input={"prompt": prompt})
    normalized = prompt.casefold()
    use_tool = any(word in normalized for word in ("checkliste", "tool", "lernen"))
    result: Decision = {
        "intent": "Lernschritte erzeugen" if use_tool else "Direkte Erklärung erzeugen",
        "route": "tool" if use_tool else "direct",
    }
    emit_task_event("understand_task", "finished", output=result)
    return result


@task
def learning_tool_task(prompt: str) -> list[str]:
    emit_task_event("learning_tool_task", "started", input={"prompt": prompt})
    result = [
        f"Eingabe analysieren: {prompt}",
        "Python-Verzweigung im @entrypoint auswerten",
        "Functional-API-Stream als AG-UI-Events sichtbar machen",
    ]
    emit_task_event("learning_tool_task", "finished", output=result)
    return result


@task
def respond_task(payload: dict[str, Any]) -> str:
    emit_task_event("respond_task", "started", input=payload)
    tool_result = payload.get("tool_result")
    if tool_result:
        answer = (
            "Die LangGraph Functional API hat den Tool-Pfad gewählt. "
            f"Die Task-Ergebnisse sind: {' · '.join(tool_result)}."
        )
    else:
        answer = (
            "Die LangGraph Functional API hat den direkten Python-Pfad gewählt. "
            f"Die Eingabe war: {payload['prompt']}."
        )
    emit_task_event("respond_task", "finished", output=answer)
    return answer


@entrypoint()
def functional_workflow(inputs: dict[str, str]) -> FunctionalResult:
    """Real LangGraph Functional API workflow with ordinary Python control flow."""

    prompt = inputs["prompt"]
    decision = understand_task(prompt).result()
    task_order = ["understand_task"]
    tool_result: list[str] | None = None

    if decision["route"] == "tool":
        tool_result = learning_tool_task(prompt).result()
        task_order.append("learning_tool_task")

    answer = respond_task({"prompt": prompt, "tool_result": tool_result}).result()
    task_order.append("respond_task")
    return {"route": decision["route"], "answer": answer, "task_order": task_order}


def latest_user_text(input_data: RunAgentInput) -> str:
    for message in reversed(input_data.messages):
        if message.role == "user" and isinstance(message.content, str) and message.content.strip():
            return message.content.strip()
    return "Erkläre mir die LangGraph Functional API"


async def pause(delay_ms: int) -> None:
    await asyncio.sleep(max(delay_ms, 0) / 1000)


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


def runtime_chunk_patch(stream_mode: str, chunk: Any) -> list[dict[str, Any]]:
    patch = [
        {
            "op": "replace",
            "path": "/lastLangGraphChunk",
            "value": {"streamMode": stream_mode, "chunk": chunk},
        }
    ]
    mode_path = (
        "/lastCustomLangGraphChunk" if stream_mode == "custom" else "/lastUpdateLangGraphChunk"
    )
    patch.append(
        {
            "op": "replace",
            "path": mode_path,
            "value": {"streamMode": stream_mode, "chunk": chunk},
        }
    )
    return patch


async def run_functional_flow(
    input_data: RunAgentInput, delay_ms: int = 180
) -> AsyncIterator[BaseEvent]:
    """Translate actual Functional API runtime chunks into AG-UI events."""

    yield RunStartedEvent(
        type=EventType.RUN_STARTED,
        thread_id=input_data.thread_id,
        run_id=input_data.run_id,
    )
    yield StateSnapshotEvent(
        type=EventType.STATE_SNAPSHOT,
        snapshot={
            "framework": "langgraph",
            "api": "functional",
            "translation": "runtime-stream-to-ag-ui",
            "currentTask": "START",
            "taskOutputs": {},
            "lastLangGraphChunk": None,
            "lastCustomLangGraphChunk": None,
            "lastUpdateLangGraphChunk": None,
        },
    )

    try:
        async for stream_mode, runtime_chunk in functional_workflow.astream(
            {"prompt": latest_user_text(input_data)},
            stream_mode=["custom", "updates"],
        ):
            if stream_mode == "custom" and runtime_chunk.get("phase") == "started":
                yield StepStartedEvent(
                    type=EventType.STEP_STARTED,
                    step_name=runtime_chunk["task"],
                )

            patch = runtime_chunk_patch(stream_mode, runtime_chunk)
            if stream_mode == "custom":
                task_name = runtime_chunk["task"]
                patch.append(
                    {
                        "op": "replace",
                        "path": "/currentTask",
                        "value": task_name,
                    }
                )
                if runtime_chunk.get("phase") == "finished":
                    patch.append(
                        {
                            "op": "add",
                            "path": f"/taskOutputs/{task_name}",
                            "value": runtime_chunk.get("output"),
                        }
                    )
            yield StateDeltaEvent(type=EventType.STATE_DELTA, delta=patch)

            if stream_mode == "custom" and runtime_chunk.get("phase") == "finished":
                if runtime_chunk["task"] == "respond_task":
                    async for event in answer_events(runtime_chunk["output"], delay_ms):
                        yield event
                yield StepFinishedEvent(
                    type=EventType.STEP_FINISHED,
                    step_name=runtime_chunk["task"],
                )
            await pause(delay_ms)
    except Exception as exc:
        yield RunErrorEvent(
            type=EventType.RUN_ERROR,
            message=f"LangGraph Functional API fehlgeschlagen: {exc}",
            code="LANGGRAPH_FUNCTIONAL_ERROR",
        )
        return

    yield RunFinishedEvent(
        type=EventType.RUN_FINISHED,
        thread_id=input_data.thread_id,
        run_id=input_data.run_id,
        outcome={"type": "success"},
    )
