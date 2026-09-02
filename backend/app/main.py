from __future__ import annotations

import os

from ag_ui.core import RunAgentInput
from ag_ui.encoder import EventEncoder
from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from .langgraph_advanced_flows import (
    run_functional_hitl_flow,
    run_functional_tool_flow,
    run_graph_hitl_flow,
    run_graph_tool_flow,
)
from .langgraph_flow import run_langgraph_flow
from .langgraph_functional_flow import run_functional_flow
from .scenarios import SCENARIOS, run_scenario

app = FastAPI(
    title="AG-UI Learning Lab Backend",
    description="Inspectable AG-UI event streams for guided lessons",
    version="0.2.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, object]:
    return {
        "ok": True,
        "openaiConfigured": bool(os.getenv("OPENAI_API_KEY")),
        "openaiModel": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        "scenarios": list(SCENARIOS),
    }


@app.post("/agent")
async def agent_endpoint(
    input_data: RunAgentInput,
    request: Request,
    scenario: str = Query(default="lifecycle"),
    delay_ms: int = Query(default=180, ge=0, le=2000),
) -> StreamingResponse:
    encoder = EventEncoder(accept=request.headers.get("accept"))

    async def event_stream():
        async for event in run_scenario(scenario, input_data, delay_ms):
            yield encoder.encode(event)

    return StreamingResponse(event_stream(), media_type=encoder.get_content_type())


@app.post("/agent/langgraph")
async def langgraph_agent_endpoint(
    input_data: RunAgentInput,
    request: Request,
    delay_ms: int = Query(default=180, ge=0, le=2000),
) -> StreamingResponse:
    """Run the isolated LangGraph lesson without changing the scenario runner."""

    encoder = EventEncoder(accept=request.headers.get("accept"))

    async def event_stream():
        async for event in run_langgraph_flow(input_data, delay_ms):
            yield encoder.encode(event)

    return StreamingResponse(event_stream(), media_type=encoder.get_content_type())


@app.post("/agent/langgraph-functional")
async def langgraph_functional_agent_endpoint(
    input_data: RunAgentInput,
    request: Request,
    delay_ms: int = Query(default=180, ge=0, le=2000),
) -> StreamingResponse:
    """Run the isolated Functional API lesson and translate its runtime stream."""

    encoder = EventEncoder(accept=request.headers.get("accept"))

    async def event_stream():
        async for event in run_functional_flow(input_data, delay_ms):
            yield encoder.encode(event)

    return StreamingResponse(event_stream(), media_type=encoder.get_content_type())


def translated_endpoint(runner):
    async def endpoint(
        input_data: RunAgentInput,
        request: Request,
        delay_ms: int = Query(default=180, ge=0, le=2000),
    ) -> StreamingResponse:
        encoder = EventEncoder(accept=request.headers.get("accept"))

        async def event_stream():
            async for event in runner(input_data, delay_ms):
                yield encoder.encode(event)

        return StreamingResponse(event_stream(), media_type=encoder.get_content_type())

    endpoint.__name__ = f"{runner.__name__}_endpoint"
    return endpoint


app.post("/agent/langgraph-graph-tools")(translated_endpoint(run_graph_tool_flow))
app.post("/agent/langgraph-functional-tools")(translated_endpoint(run_functional_tool_flow))
app.post("/agent/langgraph-graph-hitl")(translated_endpoint(run_graph_hitl_flow))
app.post("/agent/langgraph-functional-hitl")(translated_endpoint(run_functional_hitl_flow))
