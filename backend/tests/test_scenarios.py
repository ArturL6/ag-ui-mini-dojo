from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from ag_ui.core import EventType, RunAgentInput

from app.scenarios import run_scenario


def input_for(*, resume=None) -> RunAgentInput:
    return RunAgentInput(
        thread_id="thread-test",
        run_id="run-test",
        state={},
        messages=[{"id": "user-1", "role": "user", "content": "AG-UI lernen"}],
        tools=[],
        context=[],
        forwarded_props={},
        resume=resume,
    )


async def collect(stream: AsyncIterator):
    return [event async for event in stream]


@pytest.mark.parametrize(
    ("scenario", "required"),
    [
        ("lifecycle", {EventType.RUN_STARTED, EventType.RUN_FINISHED}),
        ("streaming", {EventType.TEXT_MESSAGE_CONTENT, EventType.RUN_FINISHED}),
        ("tools", {EventType.TOOL_CALL_START, EventType.TOOL_CALL_RESULT}),
        ("state", {EventType.STATE_SNAPSHOT, EventType.STATE_DELTA}),
        ("error", {EventType.RUN_STARTED, EventType.RUN_ERROR}),
    ],
)
async def test_learning_scenarios_emit_expected_events(scenario, required):
    events = await collect(run_scenario(scenario, input_for(), delay_ms=0))
    assert required.issubset({event.type for event in events})


async def test_interrupt_can_be_resumed():
    interrupted = await collect(run_scenario("interrupt", input_for(), delay_ms=0))
    finish = interrupted[-1]
    assert finish.type == EventType.RUN_FINISHED
    assert finish.outcome.type == "interrupt"

    resumed = await collect(
        run_scenario(
            "interrupt",
            input_for(
                resume=[
                    {
                        "interrupt_id": "approve-learning-deploy",
                        "status": "resolved",
                        "payload": {"approved": True},
                    }
                ]
            ),
            delay_ms=0,
        )
    )
    assert any(event.type == EventType.TOOL_CALL_RESULT for event in resumed)
    assert resumed[-1].type == EventType.RUN_FINISHED


async def test_llm_without_key_is_visible_protocol_error(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    events = await collect(run_scenario("llm", input_for(), delay_ms=0))
    assert events[-1].type == EventType.RUN_ERROR
    assert events[-1].code == "MISSING_API_KEY"
