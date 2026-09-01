import cors from "cors";
import express from "express";
import { randomUUID } from "node:crypto";
import { fileURLToPath } from "node:url";
import path from "node:path";
import {
  EventType,
  RunAgentInputSchema,
  type BaseEvent,
  type RunAgentInput,
} from "@ag-ui/core";
import { EventEncoder } from "@ag-ui/encoder";

export type DemoState = {
  goal: string;
  status: "gestartet" | "läuft" | "fertig";
  steps: Array<{ label: string; done: boolean }>;
};

const wait = (milliseconds: number) =>
  new Promise((resolve) => setTimeout(resolve, milliseconds));

function latestUserText(input: RunAgentInput): string {
  const message = [...input.messages]
    .reverse()
    .find((entry) => entry.role === "user");
  return typeof message?.content === "string" && message.content.trim()
    ? message.content.trim()
    : "AG-UI verstehen";
}

export async function* buildDemoEvents(
  input: RunAgentInput,
  delayMs = 180,
): AsyncGenerator<BaseEvent> {
  const goal = latestUserText(input);
  const messageId = randomUUID();
  const toolCallId = randomUUID();
  const toolMessageId = randomUUID();
  const steps = [
    "Anfrage verstehen",
    "Checkliste erzeugen",
    "Antwort streamen",
  ];

  yield {
    type: EventType.RUN_STARTED,
    threadId: input.threadId,
    runId: input.runId,
  };
  yield {
    type: EventType.STATE_SNAPSHOT,
    snapshot: {
      goal,
      status: "gestartet",
      steps: steps.map((label) => ({ label, done: false })),
    } satisfies DemoState,
  };

  yield { type: EventType.STEP_STARTED, stepName: steps[0] };
  await wait(delayMs);
  yield {
    type: EventType.STATE_DELTA,
    delta: [
      { op: "replace", path: "/status", value: "läuft" },
      { op: "replace", path: "/steps/0/done", value: true },
    ],
  };
  yield { type: EventType.STEP_FINISHED, stepName: steps[0] };

  yield { type: EventType.STEP_STARTED, stepName: steps[1] };
  yield {
    type: EventType.TOOL_CALL_START,
    toolCallId,
    toolCallName: "create_checklist",
  };
  yield {
    type: EventType.TOOL_CALL_ARGS,
    toolCallId,
    delta: JSON.stringify({ goal, count: 3 }),
  };
  yield { type: EventType.TOOL_CALL_END, toolCallId };
  await wait(delayMs);
  yield {
    type: EventType.TOOL_CALL_RESULT,
    messageId: toolMessageId,
    toolCallId,
    content: JSON.stringify({ created: true, items: steps }),
    role: "tool",
  };
  yield {
    type: EventType.STATE_DELTA,
    delta: [{ op: "replace", path: "/steps/1/done", value: true }],
  };
  yield { type: EventType.STEP_FINISHED, stepName: steps[1] };

  yield { type: EventType.STEP_STARTED, stepName: steps[2] };
  yield {
    type: EventType.TEXT_MESSAGE_START,
    messageId,
    role: "assistant",
  };
  const chunks = [
    `Für „${goal}“ ist hier der Kern: `,
    "AG-UI standardisiert nicht den Agenten selbst, sondern dessen Kommunikation mit der Oberfläche. ",
    "Die UI erhält strukturierte Events für Laufstatus, Text, Tool-Aufrufe und gemeinsamen Zustand — und kann diese sofort passend darstellen.",
  ];
  for (const delta of chunks) {
    await wait(delayMs);
    yield { type: EventType.TEXT_MESSAGE_CONTENT, messageId, delta };
  }
  yield { type: EventType.TEXT_MESSAGE_END, messageId };
  yield {
    type: EventType.STATE_DELTA,
    delta: [
      { op: "replace", path: "/steps/2/done", value: true },
      { op: "replace", path: "/status", value: "fertig" },
    ],
  };
  yield { type: EventType.STEP_FINISHED, stepName: steps[2] };
  yield {
    type: EventType.RUN_FINISHED,
    threadId: input.threadId,
    runId: input.runId,
    outcome: { type: "success" },
  };
}

export function createApp() {
  const app = express();
  app.use(cors());
  app.use(express.json());

  app.get("/health", (_request, response) => {
    response.json({ ok: true });
  });

  app.post("/agent", async (request, response) => {
    const parsed = RunAgentInputSchema.safeParse(request.body);
    if (!parsed.success) {
      response.status(400).json({ error: parsed.error.flatten() });
      return;
    }

    const encoder = new EventEncoder({ accept: request.header("accept") });
    response.status(200);
    response.setHeader("Content-Type", encoder.getContentType());
    response.setHeader("Cache-Control", "no-cache, no-transform");
    response.setHeader("Connection", "keep-alive");
    response.flushHeaders();

    try {
      for await (const event of buildDemoEvents(parsed.data)) {
        response.write(encoder.encode(event));
      }
    } catch (error) {
      response.write(
        encoder.encode({
          type: EventType.RUN_ERROR,
          message: error instanceof Error ? error.message : "Unbekannter Fehler",
        }),
      );
    } finally {
      response.end();
    }
  });

  const distPath = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../dist");
  app.use(express.static(distPath));
  app.get("/{*path}", (_request, response) => {
    response.sendFile(path.join(distPath, "index.html"));
  });

  return app;
}

if (process.env.NODE_ENV !== "test") {
  const port = Number(process.env.PORT ?? 8765);
  createApp().listen(port, () => {
    console.log(`AG-UI Mini Dojo läuft auf http://localhost:${port}`);
  });
}
