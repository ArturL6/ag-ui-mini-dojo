from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator
from typing import Any
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
    ToolCallArgsEvent,
    ToolCallEndEvent,
    ToolCallResultEvent,
    ToolCallStartEvent,
)

ScenarioStream = AsyncIterator[BaseEvent]


def latest_user_text(input_data: RunAgentInput) -> str:
    for message in reversed(input_data.messages):
        if message.role == "user" and isinstance(message.content, str) and message.content.strip():
            return message.content.strip()
    return "Erkläre mir AG-UI"


async def pause(delay_ms: int) -> None:
    await asyncio.sleep(max(delay_ms, 0) / 1000)


async def text_events(text: str, delay_ms: int, *, chunk_words: int = 4) -> ScenarioStream:
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
        await pause(delay_ms)
        yield TextMessageContentEvent(
            type=EventType.TEXT_MESSAGE_CONTENT,
            message_id=message_id,
            delta=chunk,
        )
    yield TextMessageEndEvent(type=EventType.TEXT_MESSAGE_END, message_id=message_id)


async def lifecycle_scenario(input_data: RunAgentInput, delay_ms: int) -> ScenarioStream:
    yield RunStartedEvent(
        type=EventType.RUN_STARTED,
        thread_id=input_data.thread_id,
        run_id=input_data.run_id,
    )
    yield StepStartedEvent(type=EventType.STEP_STARTED, step_name="request-verstehen")
    await pause(delay_ms)
    async for event in text_events(
        "Ein AG-UI-Lauf besitzt klare Grenzen. RUN_STARTED eröffnet ihn, "
        "RUN_FINISHED schließt ihn.",
        delay_ms,
    ):
        yield event
    yield StepFinishedEvent(type=EventType.STEP_FINISHED, step_name="request-verstehen")
    yield RunFinishedEvent(
        type=EventType.RUN_FINISHED,
        thread_id=input_data.thread_id,
        run_id=input_data.run_id,
        outcome={"type": "success"},
    )


async def streaming_scenario(input_data: RunAgentInput, delay_ms: int) -> ScenarioStream:
    yield RunStartedEvent(
        type=EventType.RUN_STARTED,
        thread_id=input_data.thread_id,
        run_id=input_data.run_id,
    )
    prompt = latest_user_text(input_data)
    async for event in text_events(
        f"Deine Anfrage lautet: {prompt}. Der Server sendet diese Antwort in kleinen Deltas. "
        "Der Client fügt sie anhand derselben messageId wieder zu einer Nachricht zusammen.",
        delay_ms,
        chunk_words=2,
    ):
        yield event
    yield RunFinishedEvent(
        type=EventType.RUN_FINISHED,
        thread_id=input_data.thread_id,
        run_id=input_data.run_id,
        outcome={"type": "success"},
    )


async def tools_scenario(input_data: RunAgentInput, delay_ms: int) -> ScenarioStream:
    yield RunStartedEvent(
        type=EventType.RUN_STARTED,
        thread_id=input_data.thread_id,
        run_id=input_data.run_id,
    )
    tool_call_id = str(uuid4())
    result_message_id = str(uuid4())
    arguments = json.dumps(
        {"topic": latest_user_text(input_data), "maxItems": 3}, ensure_ascii=False
    )

    yield StepStartedEvent(type=EventType.STEP_STARTED, step_name="tool-auswählen")
    yield ToolCallStartEvent(
        type=EventType.TOOL_CALL_START,
        tool_call_id=tool_call_id,
        tool_call_name="create_learning_checklist",
    )
    midpoint = len(arguments) // 2
    for delta in (arguments[:midpoint], arguments[midpoint:]):
        await pause(delay_ms)
        yield ToolCallArgsEvent(
            type=EventType.TOOL_CALL_ARGS,
            tool_call_id=tool_call_id,
            delta=delta,
        )
    yield ToolCallEndEvent(type=EventType.TOOL_CALL_END, tool_call_id=tool_call_id)
    yield StepFinishedEvent(type=EventType.STEP_FINISHED, step_name="tool-auswählen")

    await pause(delay_ms)
    result = {
        "items": [
            "Request im Browser erzeugen",
            "SSE-Events im Client verarbeiten",
            "State und Tool-Ergebnis rendern",
        ]
    }
    yield ToolCallResultEvent(
        type=EventType.TOOL_CALL_RESULT,
        message_id=result_message_id,
        tool_call_id=tool_call_id,
        content=json.dumps(result, ensure_ascii=False),
        role="tool",
    )
    async for event in text_events(
        "Das Backend-Tool wurde ausgeführt. Sein strukturiertes Ergebnis ist nun Teil "
        "der Nachrichtenhistorie.",
        delay_ms,
    ):
        yield event
    yield RunFinishedEvent(
        type=EventType.RUN_FINISHED,
        thread_id=input_data.thread_id,
        run_id=input_data.run_id,
        outcome={"type": "success"},
    )


async def state_scenario(input_data: RunAgentInput, delay_ms: int) -> ScenarioStream:
    yield RunStartedEvent(
        type=EventType.RUN_STARTED,
        thread_id=input_data.thread_id,
        run_id=input_data.run_id,
    )
    steps = [
        {"label": "Snapshot empfangen", "done": False},
        {"label": "Delta anwenden", "done": False},
        {"label": "UI neu rendern", "done": False},
    ]
    yield StateSnapshotEvent(
        type=EventType.STATE_SNAPSHOT,
        snapshot={"status": "gestartet", "progress": 0, "steps": steps},
    )
    for index, progress in enumerate((33, 66, 100)):
        await pause(delay_ms)
        delta: list[dict[str, Any]] = [
            {"op": "replace", "path": f"/steps/{index}/done", "value": True},
            {"op": "replace", "path": "/progress", "value": progress},
        ]
        if progress == 100:
            delta.append({"op": "replace", "path": "/status", "value": "fertig"})
        yield StateDeltaEvent(type=EventType.STATE_DELTA, delta=delta)
    async for event in text_events(
        "Der Client hat einen vollständigen Snapshot und danach drei kleine "
        "JSON-Patch-Deltas verarbeitet.",
        delay_ms,
    ):
        yield event
    yield RunFinishedEvent(
        type=EventType.RUN_FINISHED,
        thread_id=input_data.thread_id,
        run_id=input_data.run_id,
        outcome={"type": "success"},
    )


async def interrupt_scenario(input_data: RunAgentInput, delay_ms: int) -> ScenarioStream:
    yield RunStartedEvent(
        type=EventType.RUN_STARTED,
        thread_id=input_data.thread_id,
        run_id=input_data.run_id,
    )
    resume_entries = input_data.resume or []
    if resume_entries:
        decision = resume_entries[0]
        approved = decision.status == "resolved" and bool((decision.payload or {}).get("approved"))
        yield ToolCallResultEvent(
            type=EventType.TOOL_CALL_RESULT,
            message_id=str(uuid4()),
            tool_call_id="learning-deploy-tool",
            content=json.dumps({"approved": approved, "executed": approved}),
            role="tool",
        )
        async for event in text_events(
            "Freigabe erhalten: Die Beispielaktion wurde ausgeführt."
            if approved
            else "Die Beispielaktion wurde abgelehnt und nicht ausgeführt.",
            delay_ms,
        ):
            yield event
        yield RunFinishedEvent(
            type=EventType.RUN_FINISHED,
            thread_id=input_data.thread_id,
            run_id=input_data.run_id,
            outcome={"type": "success"},
        )
        return

    tool_call_id = "learning-deploy-tool"
    yield ToolCallStartEvent(
        type=EventType.TOOL_CALL_START,
        tool_call_id=tool_call_id,
        tool_call_name="deploy_demo",
    )
    yield ToolCallArgsEvent(
        type=EventType.TOOL_CALL_ARGS,
        tool_call_id=tool_call_id,
        delta='{"environment":"learning"}',
    )
    yield ToolCallEndEvent(type=EventType.TOOL_CALL_END, tool_call_id=tool_call_id)
    yield StateSnapshotEvent(
        type=EventType.STATE_SNAPSHOT,
        snapshot={"status": "wartet_auf_freigabe", "action": "deploy_demo"},
    )
    yield RunFinishedEvent(
        type=EventType.RUN_FINISHED,
        thread_id=input_data.thread_id,
        run_id=input_data.run_id,
        outcome={
            "type": "interrupt",
            "interrupts": [
                {
                    "id": "approve-learning-deploy",
                    "reason": "tool_call",
                    "message": "Soll die ungefährliche Beispielaktion ausgeführt werden?",
                    "toolCallId": tool_call_id,
                    "responseSchema": {
                        "type": "object",
                        "properties": {"approved": {"type": "boolean"}},
                        "required": ["approved"],
                    },
                }
            ],
        },
    )


async def error_scenario(input_data: RunAgentInput, delay_ms: int) -> ScenarioStream:
    yield RunStartedEvent(
        type=EventType.RUN_STARTED,
        thread_id=input_data.thread_id,
        run_id=input_data.run_id,
    )
    await pause(delay_ms)
    yield RunErrorEvent(
        type=EventType.RUN_ERROR,
        message="Absichtlich erzeugter Lernfehler: RUN_ERROR beendet den Lauf.",
        code="LEARNING_ERROR",
    )


async def llm_scenario(input_data: RunAgentInput, delay_ms: int) -> ScenarioStream:
    yield RunStartedEvent(
        type=EventType.RUN_STARTED,
        thread_id=input_data.thread_id,
        run_id=input_data.run_id,
    )
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        yield RunErrorEvent(
            type=EventType.RUN_ERROR,
            message="OPENAI_API_KEY fehlt. Trage ihn in .env ein und starte das Backend neu.",
            code="MISSING_API_KEY",
        )
        return

    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=api_key)
    message_id = str(uuid4())
    yield TextMessageStartEvent(
        type=EventType.TEXT_MESSAGE_START,
        message_id=message_id,
        role="assistant",
    )
    try:
        stream = await client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[
                {
                    "role": "system",
                    "content": "Du bist ein präziser AG-UI-Tutor. Antworte kurz auf Deutsch.",
                },
                {"role": "user", "content": latest_user_text(input_data)},
            ],
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                yield TextMessageContentEvent(
                    type=EventType.TEXT_MESSAGE_CONTENT,
                    message_id=message_id,
                    delta=delta,
                )
        yield TextMessageEndEvent(type=EventType.TEXT_MESSAGE_END, message_id=message_id)
        yield RunFinishedEvent(
            type=EventType.RUN_FINISHED,
            thread_id=input_data.thread_id,
            run_id=input_data.run_id,
            outcome={"type": "success"},
        )
    except Exception as exc:  # provider errors are surfaced as protocol events
        yield RunErrorEvent(
            type=EventType.RUN_ERROR,
            message=f"OpenAI-Aufruf fehlgeschlagen: {exc}",
            code="PROVIDER_ERROR",
        )


SCENARIOS = {
    "lifecycle": lifecycle_scenario,
    "streaming": streaming_scenario,
    "tools": tools_scenario,
    "state": state_scenario,
    "interrupt": interrupt_scenario,
    "error": error_scenario,
    "llm": llm_scenario,
}


async def run_scenario(
    scenario: str, input_data: RunAgentInput, delay_ms: int = 180
) -> ScenarioStream:
    handler = SCENARIOS.get(scenario)
    if handler is None:
        yield RunErrorEvent(
            type=EventType.RUN_ERROR,
            message=f"Unbekanntes Szenario: {scenario}",
            code="UNKNOWN_SCENARIO",
        )
        return
    async for event in handler(input_data, delay_ms):
        yield event
