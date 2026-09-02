import { chromium } from "playwright";

const baseUrl = process.env.BASE_URL ?? "http://localhost:3100";
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1600, height: 1100 } });

async function runLesson(id, expectedEvent) {
  await page.getByTestId(`lesson-${id}`).click();
  await page.getByTestId("run-lesson").click();
  await page.locator(".run-status.done, .run-status.error, .run-status.paused").waitFor({ timeout: 15_000 });
  const timeline = await page.getByTestId("event-timeline").innerText();
  if (!timeline.includes(expectedEvent)) throw new Error(`${id}: ${expectedEvent} fehlt`);
}

async function verifyToolLesson(id) {
  await runLesson(id, "TOOL_CALL_RESULT");
  const answer = await page.getByTestId("answer").innerText();
  if (!answer.includes("6 Wörter gezählt")) throw new Error(`${id}: echtes Tool-Ergebnis fehlt`);
}

async function verifyHitlLesson(id, apiLabel) {
  await runLesson(id, "RUN_FINISHED");
  await page.getByTestId("approval-card").waitFor();
  const beforeApproval = await page.getByTestId("event-timeline").innerText();
  if (beforeApproval.includes("TOOL_CALL_RESULT")) {
    throw new Error(`${id}: Tool wurde vor der Freigabe ausgeführt`);
  }
  await page.getByTestId("approve").click();
  await page.locator(".run-status.done").waitFor({ timeout: 15_000 });
  const timeline = await page.getByTestId("event-timeline").innerText();
  if (!timeline.includes("TOOL_CALL_RESULT")) {
    throw new Error(`${id}: Tool-Ergebnis nach Resume fehlt`);
  }
  const answer = await page.getByTestId("answer").innerText();
  if (!answer.includes(`${apiLabel}-Tool wurde wirklich ausgeführt`)) {
    throw new Error(`${id}: Resume-Antwort fehlt`);
  }
}

async function verifyHitlRejection(id) {
  await runLesson(id, "RUN_FINISHED");
  await page.getByTestId("approval-card").waitFor();
  await page.getByTestId("reject").click();
  await page.locator(".run-status.done").waitFor({ timeout: 15_000 });
  const timeline = await page.getByTestId("event-timeline").innerText();
  if (timeline.includes("TOOL_CALL_RESULT")) {
    throw new Error(`${id}: abgelehntes Tool wurde dennoch ausgeführt`);
  }
  const answer = await page.getByTestId("answer").innerText();
  if (!answer.includes("wurde nicht ausgeführt")) {
    throw new Error(`${id}: Ablehnungsantwort fehlt`);
  }
}

try {
  await page.goto(baseUrl, { waitUntil: "networkidle" });
  await runLesson("lifecycle", "RUN_FINISHED");
  await runLesson("streaming", "TEXT_MESSAGE_CONTENT");
  await runLesson("tools", "TOOL_CALL_RESULT");
  await runLesson("state", "STATE_DELTA");

  await runLesson("interrupt", "RUN_FINISHED");
  await page.getByTestId("approval-card").waitFor();
  await page.getByTestId("approve").click();
  await page.locator(".run-status.done").waitFor({ timeout: 15_000 });
  const interruptTimeline = await page.getByTestId("event-timeline").innerText();
  if (!interruptTimeline.includes("TOOL_CALL_RESULT")) throw new Error("Resume-Tool-Result fehlt");

  await runLesson("error", "RUN_ERROR");
  await page.getByTestId("run-error").waitFor();

  await page.getByTestId("lesson-state").click();
  await page.getByTestId("run-lesson").click();
  await page.locator(".run-status.done").waitFor({ timeout: 15_000 });
  const state = await page.getByTestId("client-state").innerText();
  if (!state.includes('"progress": 100')) throw new Error("Finaler Shared State fehlt");
  if (!(await page.getByTestId("event-inspector").isVisible())) throw new Error("Event Inspector fehlt");

  await runLesson("langgraph", "STATE_DELTA");
  const graphState = await page.getByTestId("client-state").innerText();
  for (const node of ["understand", "learning_tool", "respond"]) {
    if (!graphState.includes(`"${node}"`)) throw new Error(`LangGraph-Node ${node} fehlt`);
  }
  const graphAnswer = await page.getByTestId("answer").innerText();
  if (!graphAnswer.includes("LangGraph hat den Tool-Pfad gewählt")) {
    throw new Error("LangGraph-Antwort fehlt");
  }

  await runLesson("langgraph-functional", "STATE_DELTA");
  const functionalState = await page.getByTestId("client-state").innerText();
  for (const evidence of [
    '"translation": "langgraph-runtime-to-ag-ui"',
    '"translator": "transparent-custom-v1"',
    '"streamMode": "custom"',
    '"understand_task"',
    '"learning_tool_task"',
    '"respond_task"',
  ]) {
    if (!functionalState.includes(evidence)) {
      throw new Error(`Functional-API-Evidenz fehlt: ${evidence}`);
    }
  }
  const functionalAnswer = await page.getByTestId("answer").innerText();
  if (!functionalAnswer.includes("Functional API hat den Tool-Pfad gewählt")) {
    throw new Error("Functional-API-Antwort fehlt");
  }

  await verifyToolLesson("langgraph-graph-tools");
  await verifyToolLesson("langgraph-functional-tools");
  await verifyHitlLesson("langgraph-graph-hitl", "Graph-API");
  await verifyHitlLesson("langgraph-functional-hitl", "Functional-API");
  await verifyHitlRejection("langgraph-graph-hitl");
  await verifyHitlRejection("langgraph-functional-hitl");

  await page.screenshot({ path: "../artifacts/ag-ui-learning-lab.png", fullPage: true });
  console.log(JSON.stringify({ ok: true, lessons: 12, screenshot: "artifacts/ag-ui-learning-lab.png" }));
} finally {
  await browser.close();
}
