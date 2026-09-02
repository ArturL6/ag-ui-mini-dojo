from __future__ import annotations

import asyncio
import threading
from collections import OrderedDict
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, TypedDict

from ag_ui.core import BaseEvent, EventType, RunAgentInput, RunErrorEvent
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.config import get_stream_writer
from langgraph.func import entrypoint, task
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from .langgraph_agui_translator import LangGraphAguiTranslator


@dataclass
class WorkflowGate:
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    users: int = 0


WORKFLOW_GATES: dict[tuple[str, str], WorkflowGate] = {}


@asynccontextmanager
async def serialized_workflow(workflow: str, thread_id: str):
    """Serialize one checkpoint thread and remove the gate after all waiters leave."""

    key = (workflow, thread_id)
    gate = WORKFLOW_GATES.setdefault(key, WorkflowGate())
    gate.users += 1
    acquired = False
    try:
        await gate.lock.acquire()
        acquired = True
        yield
    finally:
        if acquired:
            gate.lock.release()
        gate.users -= 1
        if gate.users == 0 and WORKFLOW_GATES.get(key) is gate:
            WORKFLOW_GATES.pop(key, None)


@dataclass
class ProtectedActionRecord:
    done: threading.Event = field(default_factory=threading.Event)
    result: dict[str, Any] | None = None
    error: BaseException | None = None


PROTECTED_ACTION_LOCK = threading.Lock()
PROTECTED_ACTION_RECORDS: OrderedDict[str, ProtectedActionRecord] = OrderedDict()


class ToolFlowState(TypedDict, total=False):
    prompt: str
    tool_call_id: str
    tool_result: dict[str, Any]
    answer: str


class HitlFlowState(TypedDict, total=False):
    prompt: str
    tool_call_id: str
    approved: bool
    interrupt_id: str
    tool_result: dict[str, Any]
    answer: str


def latest_user_text(input_data: RunAgentInput) -> str:
    for message in reversed(input_data.messages):
        if message.role == "user" and isinstance(message.content, str) and message.content.strip():
            return message.content.strip()
    return "Zähle die Wörter mit einem Tool"


@tool
def count_words(text: str) -> dict[str, Any]:
    """The real deterministic Python tool used by both API variants."""

    words = text.split()
    return {
        "tool": "count_words",
        "wordCount": len(words),
        "words": words,
        "executed": True,
    }


@tool
def execute_protected_action(api: str) -> dict[str, Any]:
    """A harmless side effect surrogate that runs only after approval."""

    return {
        "tool": "deploy_learning_demo",
        "api": api,
        "environment": "learning",
        "executed": True,
    }


def execute_protected_once(api: str, interrupt_id: str) -> dict[str, Any]:
    """Singleflight one protected tool invocation for an interrupt in this process."""

    key = f"{api}:{interrupt_id}"
    with PROTECTED_ACTION_LOCK:
        record = PROTECTED_ACTION_RECORDS.get(key)
        owner = record is None
        if record is None:
            record = ProtectedActionRecord()
            PROTECTED_ACTION_RECORDS[key] = record

    if owner:
        try:
            result = execute_protected_action.invoke({"api": api})
        except BaseException as exc:
            with PROTECTED_ACTION_LOCK:
                record.error = exc
                record.done.set()
            raise
        else:
            with PROTECTED_ACTION_LOCK:
                record.result = result
                record.done.set()
    else:
        record.done.wait()

    if record.error is not None:
        raise RuntimeError("Die geschützte Tool-Ausführung ist fehlgeschlagen") from record.error
    if record.result is None:
        raise RuntimeError("Die geschützte Tool-Ausführung lieferte kein Ergebnis")
    return record.result


def emit(signal: dict[str, Any]) -> None:
    get_stream_writer()(signal)


def emit_step(name: str, phase: str) -> None:
    emit({"kind": f"step_{phase}", "name": name})


# ---------------------------------------------------------------------------
# Graph API: real tool execution


def graph_select_tool(state: ToolFlowState) -> ToolFlowState:
    emit_step("select_tool", "start")
    result: ToolFlowState = {"tool_call_id": "graph-count-words"}
    emit_step("select_tool", "end")
    return result


def graph_execute_tool(state: ToolFlowState) -> ToolFlowState:
    emit_step("execute_tool", "start")
    args = {"text": state["prompt"]}
    emit(
        {
            "kind": "tool_call_start",
            "toolCallId": state["tool_call_id"],
            "toolName": "count_words",
            "args": args,
        }
    )
    result = count_words.invoke(args)
    emit(
        {
            "kind": "tool_call_result",
            "toolCallId": state["tool_call_id"],
            "result": result,
        }
    )
    emit_step("execute_tool", "end")
    return {"tool_result": result}


def graph_tool_response(state: ToolFlowState) -> ToolFlowState:
    emit_step("respond", "start")
    answer = f"Das echte Python-Tool hat {state['tool_result']['wordCount']} Wörter gezählt."
    emit({"kind": "text", "text": answer})
    emit_step("respond", "end")
    return {"answer": answer}


def build_graph_tool_workflow():
    builder = StateGraph(ToolFlowState)
    builder.add_node("select_tool", graph_select_tool)
    builder.add_node("execute_tool", graph_execute_tool)
    builder.add_node("respond", graph_tool_response)
    builder.add_edge(START, "select_tool")
    builder.add_edge("select_tool", "execute_tool")
    builder.add_edge("execute_tool", "respond")
    builder.add_edge("respond", END)
    return builder.compile()


GRAPH_TOOL_WORKFLOW = build_graph_tool_workflow()


# ---------------------------------------------------------------------------
# Functional API: real tool execution


@task
def functional_count_words_task(payload: dict[str, str]) -> dict[str, Any]:
    emit_step("functional_count_words_task", "start")
    emit(
        {
            "kind": "tool_call_start",
            "toolCallId": payload["tool_call_id"],
            "toolName": "count_words",
            "args": {"text": payload["prompt"]},
        }
    )
    result = count_words.invoke({"text": payload["prompt"]})
    emit(
        {
            "kind": "tool_call_result",
            "toolCallId": payload["tool_call_id"],
            "result": result,
        }
    )
    emit_step("functional_count_words_task", "end")
    return result


@entrypoint()
def functional_tool_workflow(inputs: dict[str, str]) -> dict[str, Any]:
    tool_call_id = "functional-count-words"
    result = functional_count_words_task(
        {"prompt": inputs["prompt"], "tool_call_id": tool_call_id}
    ).result()
    answer = f"Das Functional-API-Tool hat {result['wordCount']} Wörter gezählt."
    emit({"kind": "text", "text": answer})
    return {"tool_result": result, "answer": answer}


# ---------------------------------------------------------------------------
# Graph API: real interrupt + checkpoint + Command(resume=...)


def graph_propose_protected_tool(state: HitlFlowState) -> HitlFlowState:
    emit_step("propose_protected_tool", "start")
    emit(
        {
            "kind": "tool_call_start",
            "toolCallId": "graph-protected-action",
            "toolName": "deploy_learning_demo",
            "args": {"environment": "learning"},
        }
    )
    emit_step("propose_protected_tool", "end")
    return {"tool_call_id": "graph-protected-action"}


def graph_request_approval(state: HitlFlowState) -> HitlFlowState:
    decision = interrupt(
        {
            "api": "graph",
            "reason": "tool_call",
            "message": "Soll LangGraph das geschützte Graph-API-Tool ausführen?",
            "toolCallId": state["tool_call_id"],
            "responseSchema": {
                "type": "object",
                "properties": {"approved": {"type": "boolean"}},
                "required": ["approved"],
            },
        }
    )
    return {
        "approved": decision["approved"],
        "interrupt_id": decision["interrupt_id"],
    }


def route_graph_approval(state: HitlFlowState) -> str:
    return "execute" if state.get("approved") else "reject"


def graph_execute_protected_tool(state: HitlFlowState) -> HitlFlowState:
    emit_step("execute_after_approval", "start")
    result = execute_protected_once("graph", state["interrupt_id"])
    emit(
        {
            "kind": "tool_call_result",
            "toolCallId": state["tool_call_id"],
            "result": result,
        }
    )
    answer = "Freigabe erhalten: Das Graph-API-Tool wurde wirklich ausgeführt."
    emit({"kind": "text", "text": answer})
    emit_step("execute_after_approval", "end")
    return {"tool_result": result, "answer": answer}


def graph_reject_protected_tool(_state: HitlFlowState) -> HitlFlowState:
    answer = "Freigabe abgelehnt: Das Graph-API-Tool wurde nicht ausgeführt."
    emit({"kind": "text", "text": answer})
    return {"answer": answer}


def build_graph_hitl_workflow():
    builder = StateGraph(HitlFlowState)
    builder.add_node("propose", graph_propose_protected_tool)
    builder.add_node("approval", graph_request_approval)
    builder.add_node("execute", graph_execute_protected_tool)
    builder.add_node("reject", graph_reject_protected_tool)
    builder.add_edge(START, "propose")
    builder.add_edge("propose", "approval")
    builder.add_conditional_edges(
        "approval",
        route_graph_approval,
        {"execute": "execute", "reject": "reject"},
    )
    builder.add_edge("execute", END)
    builder.add_edge("reject", END)
    return builder.compile(checkpointer=InMemorySaver())


GRAPH_HITL_WORKFLOW = build_graph_hitl_workflow()


# ---------------------------------------------------------------------------
# Functional API: real interrupt + checkpoint + Command(resume=...)


@task
def functional_propose_protected_tool(_prompt: str) -> dict[str, str]:
    emit_step("functional_propose_task", "start")
    proposal = {"tool_call_id": "functional-protected-action"}
    emit(
        {
            "kind": "tool_call_start",
            "toolCallId": proposal["tool_call_id"],
            "toolName": "deploy_learning_demo",
            "args": {"environment": "learning"},
        }
    )
    emit_step("functional_propose_task", "end")
    return proposal


@task
def functional_approval_task(proposal: dict[str, str]) -> dict[str, Any]:
    return interrupt(
        {
            "api": "functional",
            "reason": "tool_call",
            "message": "Soll LangGraph das geschützte Functional-API-Tool ausführen?",
            "toolCallId": proposal["tool_call_id"],
            "responseSchema": {
                "type": "object",
                "properties": {"approved": {"type": "boolean"}},
                "required": ["approved"],
            },
        }
    )


@task
def functional_execute_protected_tool(proposal: dict[str, Any]) -> dict[str, Any]:
    emit_step("functional_execute_after_approval", "start")
    result = execute_protected_once("functional", proposal["interrupt_id"])
    emit(
        {
            "kind": "tool_call_result",
            "toolCallId": proposal["tool_call_id"],
            "result": result,
        }
    )
    emit_step("functional_execute_after_approval", "end")
    return result


@entrypoint(checkpointer=InMemorySaver())
def functional_hitl_workflow(inputs: dict[str, str]) -> dict[str, Any]:
    proposal = functional_propose_protected_tool(inputs["prompt"]).result()
    decision = functional_approval_task(proposal).result()
    approved = decision["approved"]
    if approved:
        proposal["interrupt_id"] = decision["interrupt_id"]
        result = functional_execute_protected_tool(proposal).result()
        answer = "Freigabe erhalten: Das Functional-API-Tool wurde wirklich ausgeführt."
    else:
        result = None
        answer = "Freigabe abgelehnt: Das Functional-API-Tool wurde nicht ausgeführt."
    emit({"kind": "text", "text": answer})
    return {"approved": approved, "tool_result": result, "answer": answer}


# ---------------------------------------------------------------------------
# AG-UI endpoint runners


async def resume_input(
    runnable,
    input_data: RunAgentInput,
    initial: dict[str, str],
    config: dict[str, Any],
):
    if not input_data.resume:
        return initial
    if len(input_data.resume) != 1:
        raise ValueError("Genau ein Resume-Eintrag wird für diese Lernlektion erwartet")
    entry = input_data.resume[0]
    if entry.status != "resolved":
        raise ValueError("Resume-Status muss 'resolved' sein")
    if not isinstance(entry.payload, Mapping):
        raise ValueError("Resume-Payload muss ein Objekt mit approved: boolean sein")
    if "approved" not in entry.payload or type(entry.payload["approved"]) is not bool:
        raise ValueError("Resume-Payload benötigt approved als echten Boolean")
    state = await runnable.aget_state(config)
    pending_ids = {item.id for item in state.interrupts}
    if entry.interrupt_id not in pending_ids:
        raise ValueError(
            f"Interrupt-ID {entry.interrupt_id!r} gehört nicht zum offenen LangGraph-Checkpoint"
        )
    return Command(
        resume={
            "approved": entry.payload["approved"],
            "interrupt_id": entry.interrupt_id,
        }
    )


async def translated_stream(
    runnable,
    graph_input,
    input_data: RunAgentInput,
    *,
    api: str,
    workflow: str,
    delay_ms: int,
    config: dict[str, Any] | None = None,
) -> AsyncIterator[BaseEvent]:
    translator = LangGraphAguiTranslator(
        input_data,
        api=api,
        workflow=workflow,
        delay_ms=delay_ms,
    )
    for event in translator.start_events(
        resumed=bool(input_data.resume),
        toolExecution="pending",
    ):
        yield event

    try:
        async for stream_mode, runtime_chunk in runnable.astream(
            graph_input,
            config=config,
            stream_mode=["custom", "updates"],
        ):
            yield translator.runtime_chunk_event(stream_mode, runtime_chunk)
            if stream_mode == "custom":
                async for event in translator.translate_custom_signal(runtime_chunk):
                    yield event
            elif "__interrupt__" in runtime_chunk:
                yield translator.interrupt_finished(runtime_chunk["__interrupt__"])
                return
    except Exception as exc:
        yield RunErrorEvent(
            type=EventType.RUN_ERROR,
            message=f"LangGraph-{workflow}-Flow fehlgeschlagen: {exc}",
            code="LANGGRAPH_ADVANCED_ERROR",
        )
        return

    yield translator.success_finished()


async def run_graph_tool_flow(
    input_data: RunAgentInput, delay_ms: int = 180
) -> AsyncIterator[BaseEvent]:
    async for event in translated_stream(
        GRAPH_TOOL_WORKFLOW,
        {"prompt": latest_user_text(input_data)},
        input_data,
        api="graph",
        workflow="graph-tool-execution",
        delay_ms=delay_ms,
    ):
        yield event


async def run_functional_tool_flow(
    input_data: RunAgentInput, delay_ms: int = 180
) -> AsyncIterator[BaseEvent]:
    async for event in translated_stream(
        functional_tool_workflow,
        {"prompt": latest_user_text(input_data)},
        input_data,
        api="functional",
        workflow="functional-tool-execution",
        delay_ms=delay_ms,
    ):
        yield event


async def run_graph_hitl_flow(
    input_data: RunAgentInput, delay_ms: int = 180
) -> AsyncIterator[BaseEvent]:
    config = {"configurable": {"thread_id": f"graph-hitl:{input_data.thread_id}"}}
    async with serialized_workflow("graph-hitl", input_data.thread_id):
        try:
            graph_input = await resume_input(
                GRAPH_HITL_WORKFLOW,
                input_data,
                {"prompt": latest_user_text(input_data)},
                config,
            )
        except ValueError as exc:
            yield RunErrorEvent(
                type=EventType.RUN_ERROR,
                message=str(exc),
                code="INVALID_RESUME",
            )
            return
        async for event in translated_stream(
            GRAPH_HITL_WORKFLOW,
            graph_input,
            input_data,
            api="graph",
            workflow="graph-hitl",
            delay_ms=delay_ms,
            config=config,
        ):
            yield event


async def run_functional_hitl_flow(
    input_data: RunAgentInput, delay_ms: int = 180
) -> AsyncIterator[BaseEvent]:
    config = {"configurable": {"thread_id": f"functional-hitl:{input_data.thread_id}"}}
    async with serialized_workflow("functional-hitl", input_data.thread_id):
        try:
            graph_input = await resume_input(
                functional_hitl_workflow,
                input_data,
                {"prompt": latest_user_text(input_data)},
                config,
            )
        except ValueError as exc:
            yield RunErrorEvent(
                type=EventType.RUN_ERROR,
                message=str(exc),
                code="INVALID_RESUME",
            )
            return
        async for event in translated_stream(
            functional_hitl_workflow,
            graph_input,
            input_data,
            api="functional",
            workflow="functional-hitl",
            delay_ms=delay_ms,
            config=config,
        ):
            yield event
