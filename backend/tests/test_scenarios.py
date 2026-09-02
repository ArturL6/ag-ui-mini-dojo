from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from ag_ui.core import EventType, RunAgentInput

from app.langgraph_flow import build_learning_graph, run_langgraph_flow
from app.main import app
from app.scenarios import SCENARIOS, run_scenario


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


@pytest.mark.parametrize(
    ("prompt", "expected_nodes"),
    [
        ("Erzeuge eine Checkliste mit einem Tool", ["understand", "learning_tool", "respond"]),
        ("Erkläre mir den Flow direkt", ["understand", "respond"]),
    ],
)
async def test_langgraph_uses_real_conditional_node_routes(prompt, expected_nodes):
    result = await build_learning_graph().ainvoke({"prompt": prompt})

    assert result["visited_nodes"] == expected_nodes
    assert result["answer"]


async def test_langgraph_flow_maps_node_updates_to_ag_ui_events():
    events = await collect(run_langgraph_flow(input_for(), delay_ms=0))
    event_types = [event.type for event in events]
    step_names = [event.step_name for event in events if event.type == EventType.STEP_STARTED]

    assert event_types[0] == EventType.RUN_STARTED
    assert EventType.STATE_SNAPSHOT in event_types
    assert EventType.STATE_DELTA in event_types
    assert EventType.TEXT_MESSAGE_CONTENT in event_types
    assert event_types[-1] == EventType.RUN_FINISHED
    assert step_names == ["understand", "learning_tool", "respond"]


def test_langgraph_has_an_endpoint_separate_from_existing_scenarios():
    route_paths = {getattr(route, "path", None) for route in app.routes}
    assert "langgraph" not in SCENARIOS
    assert "/agent" in route_paths
    assert "/agent/langgraph" in route_paths
