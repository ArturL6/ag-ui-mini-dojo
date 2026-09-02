from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Iterable
from typing import Any, Literal
from uuid import uuid4

from ag_ui.core import (
    BaseEvent,
    EventType,
    RunAgentInput,
    RunFinishedEvent,
    RunStartedEvent,
    StateDeltaEvent,
    StateSnapshotEvent,
    StepFinishedEvent,
    StepStartedEvent,
    TextMessageContentEvent,
    TextMessageEndEvent,
    TextMessageStartEvent,
    ToolCallArgsEvent,
    ToolCallEndEvent,
    ToolCallResultEvent,
    ToolCallStartEvent,
)
from ag_ui_langgraph import make_json_safe
from ag_ui_langgraph.interrupts import lg_interrupts_to_agui


class LangGraphAguiTranslator:
    """Transparent adapter from observable LangGraph runtime data to AG-UI events.

    LangGraph owns orchestration, tasks, checkpoints, and interrupts. This class owns
    only the explicit semantic mapping to AG-UI and keeps each raw runtime chunk in
    shared state so the mapping remains inspectable in the learning UI.
    """

    def __init__(
        self,
        input_data: RunAgentInput,
        *,
        api: Literal["graph", "functional"],
        workflow: str,
        delay_ms: int = 180,
    ) -> None:
        self.input_data = input_data
        self.api = api
        self.workflow = workflow
        self.delay_ms = delay_ms

    def start_events(self, **state: Any) -> list[BaseEvent]:
        snapshot = {
            "framework": "langgraph",
            "api": self.api,
            "workflow": self.workflow,
            "translator": "transparent-custom-v1",
            "translation": "langgraph-runtime-to-ag-ui",
            "currentStep": "START",
            "lastLangGraphChunk": None,
            "lastCustomLangGraphChunk": None,
            "lastUpdateLangGraphChunk": None,
            **state,
        }
        return [
            RunStartedEvent(
                type=EventType.RUN_STARTED,
                thread_id=self.input_data.thread_id,
                run_id=self.input_data.run_id,
            ),
            StateSnapshotEvent(type=EventType.STATE_SNAPSHOT, snapshot=snapshot),
        ]

    def runtime_chunk_event(self, stream_mode: str, chunk: Any) -> StateDeltaEvent:
        safe_chunk = make_json_safe(chunk)
        wrapped = {"streamMode": stream_mode, "chunk": safe_chunk}
        mode_path = (
            "/lastCustomLangGraphChunk" if stream_mode == "custom" else "/lastUpdateLangGraphChunk"
        )
        return StateDeltaEvent(
            type=EventType.STATE_DELTA,
            delta=[
                {"op": "replace", "path": "/lastLangGraphChunk", "value": wrapped},
                {"op": "replace", "path": mode_path, "value": wrapped},
            ],
        )

    async def translate_graph_update(
        self, node_name: str, update: dict[str, Any]
    ) -> AsyncIterator[BaseEvent]:
        """Map one native StateGraph updates chunk to visible AG-UI events."""

        yield StepStartedEvent(type=EventType.STEP_STARTED, step_name=node_name)
        yield StateDeltaEvent(
            type=EventType.STATE_DELTA,
            delta=[
                {"op": "replace", "path": "/currentStep", "value": node_name},
                {
                    "op": "add",
                    "path": f"/graphUpdates/{node_name}",
                    "value": make_json_safe(update),
                },
            ],
        )
        if isinstance(update.get("answer"), str):
            async for event in self.text_events(update["answer"]):
                yield event
        yield StepFinishedEvent(type=EventType.STEP_FINISHED, step_name=node_name)

    def functional_task_state_event(self, signal: dict[str, Any]) -> StateDeltaEvent | None:
        task_name = signal.get("task")
        if not task_name:
            return None
        delta: list[dict[str, Any]] = [
            {"op": "replace", "path": "/currentStep", "value": task_name}
        ]
        if signal.get("phase") == "finished":
            delta.append(
                {
                    "op": "add",
                    "path": f"/taskOutputs/{task_name}",
                    "value": make_json_safe(signal.get("output")),
                }
            )
        return StateDeltaEvent(type=EventType.STATE_DELTA, delta=delta)

    async def translate_custom_signal(self, signal: dict[str, Any]) -> AsyncIterator[BaseEvent]:
        kind = signal.get("kind")

        if kind == "step_start":
            yield StepStartedEvent(
                type=EventType.STEP_STARTED,
                step_name=signal["name"],
            )
            return

        if kind == "step_end":
            yield StepFinishedEvent(
                type=EventType.STEP_FINISHED,
                step_name=signal["name"],
            )
            return

        if kind == "tool_call_start":
            tool_call_id = signal["toolCallId"]
            yield ToolCallStartEvent(
                type=EventType.TOOL_CALL_START,
                tool_call_id=tool_call_id,
                tool_call_name=signal["toolName"],
            )
            yield ToolCallArgsEvent(
                type=EventType.TOOL_CALL_ARGS,
                tool_call_id=tool_call_id,
                delta=json.dumps(signal.get("args", {}), ensure_ascii=False),
            )
            yield ToolCallEndEvent(
                type=EventType.TOOL_CALL_END,
                tool_call_id=tool_call_id,
            )
            return

        if kind == "tool_call_result":
            yield ToolCallResultEvent(
                type=EventType.TOOL_CALL_RESULT,
                message_id=str(uuid4()),
                tool_call_id=signal["toolCallId"],
                content=json.dumps(signal.get("result"), ensure_ascii=False),
                role="tool",
            )
            return

        if kind == "text":
            async for event in self.text_events(str(signal.get("text", ""))):
                yield event
            return

        task_name = signal.get("task")
        phase = signal.get("phase")
        if task_name and phase == "started":
            yield StepStartedEvent(type=EventType.STEP_STARTED, step_name=task_name)
        elif task_name and phase == "finished":
            output = signal.get("output")
            if task_name == "respond_task" and isinstance(output, str):
                async for event in self.text_events(output):
                    yield event
            yield StepFinishedEvent(type=EventType.STEP_FINISHED, step_name=task_name)

    async def text_events(self, text: str, *, chunk_words: int = 4) -> AsyncIterator[BaseEvent]:
        message_id = str(uuid4())
        yield TextMessageStartEvent(
            type=EventType.TEXT_MESSAGE_START,
            message_id=message_id,
            role="assistant",
        )
        words = text.split()
        for index in range(0, len(words), chunk_words):
            chunk = " ".join(words[index : index + chunk_words])
            if index + chunk_words < len(words):
                chunk += " "
            await asyncio.sleep(max(self.delay_ms, 0) / 1000)
            yield TextMessageContentEvent(
                type=EventType.TEXT_MESSAGE_CONTENT,
                message_id=message_id,
                delta=chunk,
            )
        yield TextMessageEndEvent(type=EventType.TEXT_MESSAGE_END, message_id=message_id)

    def interrupt_finished(self, interrupts: Iterable[Any]) -> RunFinishedEvent:
        return RunFinishedEvent(
            type=EventType.RUN_FINISHED,
            thread_id=self.input_data.thread_id,
            run_id=self.input_data.run_id,
            outcome={
                "type": "interrupt",
                "interrupts": lg_interrupts_to_agui(interrupts),
            },
        )

    def success_finished(self) -> RunFinishedEvent:
        return RunFinishedEvent(
            type=EventType.RUN_FINISHED,
            thread_id=self.input_data.thread_id,
            run_id=self.input_data.run_id,
            outcome={"type": "success"},
        )
