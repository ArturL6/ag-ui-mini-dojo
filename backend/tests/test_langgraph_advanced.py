from __future__ import annotations

import json
from collections.abc import AsyncIterator

import pytest
from ag_ui.core import EventType, RunAgentInput

from app.langgraph_advanced_flows import (
    run_functional_hitl_flow,
    run_functional_tool_flow,
    run_graph_hitl_flow,
    run_graph_tool_flow,
)
from app.langgraph_agui_translator import LangGraphAguiTranslator
from app.main import app


def input_for(*, thread_id: str, prompt: str = "Zähle die Wörter mit einem Tool", resume=None):
    return RunAgentInput(
        thread_id=thread_id,
        run_id=f"run-{thread_id}",
        state={},
        messages=[{"id": "user-1", "role": "user", "content": prompt}],
        tools=[],
        context=[],
        forwarded_props={},
        resume=resume,
    )


async def collect(stream: AsyncIterator):
    return [event async for event in stream]


async def test_shared_translator_maps_tool_signals_to_ag_ui_protocol():
    translator = LangGraphAguiTranslator(
        input_for(thread_id="translator"),
        api="graph",
        workflow="translator-test",
        delay_ms=0,
    )
    started = await collect(
        translator.translate_custom_signal(
            {
                "kind": "tool_call_start",
                "toolCallId": "tool-1",
                "toolName": "count_words",
                "args": {"text": "eins zwei"},
            }
        )
    )
    finished = await collect(
        translator.translate_custom_signal(
            {
                "kind": "tool_call_result",
                "toolCallId": "tool-1",
                "result": {"wordCount": 2},
            }
        )
    )

    assert [event.type for event in started] == [
        EventType.TOOL_CALL_START,
        EventType.TOOL_CALL_ARGS,
        EventType.TOOL_CALL_END,
    ]
    assert finished[0].type == EventType.TOOL_CALL_RESULT
    assert json.loads(finished[0].content) == {"wordCount": 2}
    assert {event.tool_call_id for event in [*started, *finished]} == {"tool-1"}


def test_translator_bounds_raw_runtime_provenance():
    translator = LangGraphAguiTranslator(
        input_for(thread_id="bounded-provenance"),
        api="functional",
        workflow="translator-test",
        delay_ms=0,
    )
    event = translator.runtime_chunk_event("custom", {"large": "x" * 5_000})
    chunk = event.delta[0]["value"]["chunk"]

    assert chunk["truncated"] is True
    assert chunk["originalCharacters"] > 4_000
    assert len(chunk["preview"]) == 4_000


@pytest.mark.parametrize(
    ("runner", "thread_id", "api"),
    [
        (run_graph_tool_flow, "graph-tool", "graph"),
        (run_functional_tool_flow, "functional-tool", "functional"),
    ],
)
async def test_real_tool_execution_is_a_separate_translated_flow(runner, thread_id, api):
    events = await collect(runner(input_for(thread_id=thread_id), delay_ms=0))
    event_types = [event.type for event in events]
    result = next(event for event in events if event.type == EventType.TOOL_CALL_RESULT)
    snapshots = [event for event in events if event.type == EventType.STATE_SNAPSHOT]

    assert snapshots[0].snapshot["api"] == api
    assert snapshots[0].snapshot["translator"] == "transparent-custom-v1"
    assert EventType.TOOL_CALL_START in event_types
    assert EventType.TOOL_CALL_ARGS in event_types
    assert EventType.TOOL_CALL_END in event_types
    assert event_types.count(EventType.TOOL_CALL_RESULT) == 1
    assert json.loads(result.content)["wordCount"] == 6
    assert EventType.TEXT_MESSAGE_CONTENT in event_types
    assert event_types[-1] == EventType.RUN_FINISHED


@pytest.mark.parametrize(
    ("runner", "thread_id", "api"),
    [
        (run_graph_hitl_flow, "graph-hitl", "graph"),
        (run_functional_hitl_flow, "functional-hitl", "functional"),
    ],
)
async def test_real_langgraph_interrupt_resumes_before_tool_execution(runner, thread_id, api):
    first_run = await collect(
        runner(input_for(thread_id=thread_id, prompt="Führe die geschützte Aktion aus"), delay_ms=0)
    )
    interrupted = first_run[-1]

    assert interrupted.type == EventType.RUN_FINISHED
    assert interrupted.outcome.type == "interrupt"
    assert len(interrupted.outcome.interrupts) == 1
    assert interrupted.outcome.interrupts[0].id
    assert interrupted.outcome.interrupts[0].metadata["langgraph"]["raw"]["api"] == api
    assert not any(event.type == EventType.TOOL_CALL_RESULT for event in first_run)

    resumed = await collect(
        runner(
            input_for(
                thread_id=thread_id,
                prompt="Führe die geschützte Aktion aus",
                resume=[
                    {
                        "interrupt_id": interrupted.outcome.interrupts[0].id,
                        "status": "resolved",
                        "payload": {"approved": True},
                    }
                ],
            ),
            delay_ms=0,
        )
    )
    result = next(event for event in resumed if event.type == EventType.TOOL_CALL_RESULT)

    assert json.loads(result.content)["executed"] is True
    assert sum(event.type == EventType.TOOL_CALL_RESULT for event in resumed) == 1
    assert resumed[-1].type == EventType.RUN_FINISHED
    assert resumed[-1].outcome.type == "success"


@pytest.mark.parametrize(
    ("runner", "thread_id"),
    [
        (run_graph_hitl_flow, "graph-hitl-rejected"),
        (run_functional_hitl_flow, "functional-hitl-rejected"),
    ],
)
async def test_rejected_hitl_resume_never_executes_the_tool(runner, thread_id):
    first_run = await collect(runner(input_for(thread_id=thread_id), delay_ms=0))
    interrupt_id = first_run[-1].outcome.interrupts[0].id
    rejected = await collect(
        runner(
            input_for(
                thread_id=thread_id,
                resume=[
                    {
                        "interrupt_id": interrupt_id,
                        "status": "resolved",
                        "payload": {"approved": False},
                    }
                ],
            ),
            delay_ms=0,
        )
    )

    assert not any(event.type == EventType.TOOL_CALL_RESULT for event in rejected)
    text = "".join(
        event.delta for event in rejected if event.type == EventType.TEXT_MESSAGE_CONTENT
    )
    assert "nicht ausgeführt" in text
    assert rejected[-1].outcome.type == "success"


@pytest.mark.parametrize(
    ("runner", "thread_id"),
    [
        (run_graph_hitl_flow, "graph-hitl-wrong-id"),
        (run_functional_hitl_flow, "functional-hitl-wrong-id"),
    ],
)
async def test_resume_rejects_an_interrupt_id_from_another_checkpoint(runner, thread_id):
    await collect(runner(input_for(thread_id=thread_id), delay_ms=0))
    invalid = await collect(
        runner(
            input_for(
                thread_id=thread_id,
                resume=[
                    {
                        "interrupt_id": "wrong-interrupt-id",
                        "status": "resolved",
                        "payload": {"approved": True},
                    }
                ],
            ),
            delay_ms=0,
        )
    )

    assert len(invalid) == 1
    assert invalid[0].type == EventType.RUN_ERROR
    assert invalid[0].code == "INVALID_INTERRUPT_ID"


def test_every_advanced_langgraph_lesson_has_a_separate_endpoint():
    route_paths = {getattr(route, "path", None) for route in app.routes}
    assert {
        "/agent/langgraph-graph-tools",
        "/agent/langgraph-functional-tools",
        "/agent/langgraph-graph-hitl",
        "/agent/langgraph-functional-hitl",
    }.issubset(route_paths)
