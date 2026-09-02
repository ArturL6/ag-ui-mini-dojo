from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Literal, TypedDict

from ag_ui.core import BaseEvent, EventType, RunAgentInput, RunErrorEvent
from langgraph.config import get_stream_writer
from langgraph.func import entrypoint, task

from .langgraph_agui_translator import LangGraphAguiTranslator


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


async def run_functional_flow(
    input_data: RunAgentInput, delay_ms: int = 180
) -> AsyncIterator[BaseEvent]:
    """Translate actual Functional API runtime chunks through the shared translator."""

    translator = LangGraphAguiTranslator(
        input_data,
        api="functional",
        workflow="functional-tasks-routing",
        delay_ms=delay_ms,
    )
    for event in translator.start_events(taskOutputs={}):
        yield event

    try:
        async for stream_mode, runtime_chunk in functional_workflow.astream(
            {"prompt": latest_user_text(input_data)},
            stream_mode=["custom", "updates"],
        ):
            yield translator.runtime_chunk_event(stream_mode, runtime_chunk)
            if stream_mode == "custom":
                if state_event := translator.functional_task_state_event(runtime_chunk):
                    yield state_event
                async for event in translator.translate_custom_signal(runtime_chunk):
                    yield event
    except Exception as exc:
        yield RunErrorEvent(
            type=EventType.RUN_ERROR,
            message=f"LangGraph Functional API fehlgeschlagen: {exc}",
            code="LANGGRAPH_FUNCTIONAL_ERROR",
        )
        return

    yield translator.success_finished()
