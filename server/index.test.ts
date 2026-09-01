import { describe, expect, it } from "vitest";
import { EventType, RunAgentInputSchema } from "@ag-ui/core";
import { buildDemoEvents } from "./index.js";

describe("AG-UI demo event stream", () => {
  it("emits a valid lifecycle with text, tools and synchronized state", async () => {
    const input = RunAgentInputSchema.parse({
      threadId: "thread-test",
      runId: "run-test",
      state: {},
      messages: [
        { id: "user-1", role: "user", content: "Erkläre AG-UI" },
      ],
      tools: [],
      context: [],
      forwardedProps: {},
    });

    const events = [];
    for await (const event of buildDemoEvents(input, 0)) events.push(event);

    expect(events[0]).toMatchObject({
      type: EventType.RUN_STARTED,
      threadId: "thread-test",
      runId: "run-test",
    });
    expect(events.at(-1)).toMatchObject({
      type: EventType.RUN_FINISHED,
      threadId: "thread-test",
      runId: "run-test",
    });
    expect(events.some((event) => event.type === EventType.STATE_SNAPSHOT)).toBe(true);
    expect(events.some((event) => event.type === EventType.STATE_DELTA)).toBe(true);
    expect(events.some((event) => event.type === EventType.TOOL_CALL_START)).toBe(true);
    expect(events.some((event) => event.type === EventType.TOOL_CALL_RESULT)).toBe(true);

    const text = events
      .filter((event) => event.type === EventType.TEXT_MESSAGE_CONTENT)
      .map((event) => event.delta)
      .join("");
    expect(text).toContain("AG-UI standardisiert");
    expect(events.filter((event) => event.type === EventType.STEP_STARTED)).toHaveLength(3);
    expect(events.filter((event) => event.type === EventType.STEP_FINISHED)).toHaveLength(3);
  });
});
