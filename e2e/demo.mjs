import { chromium } from "playwright";

const baseUrl = process.env.BASE_URL ?? "http://localhost:8765";
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });

try {
  await page.goto(baseUrl, { waitUntil: "networkidle" });
  await page.getByRole("button", { name: "Demo starten" }).click();
  await page.getByText("fertig", { exact: true }).waitFor({ timeout: 10_000 });

  const eventCount = await page.locator("details").count();
  const body = await page.locator("body").innerText();
  if (eventCount < 15) throw new Error(`Zu wenige AG-UI-Events: ${eventCount}`);
  if (!body.includes("TOOL_CALL_RESULT")) throw new Error("Tool-Result fehlt im Event-Log");
  if (!body.includes("Die UI erhält strukturierte Events")) throw new Error("Gestreamte Antwort ist unvollständig");
  if (!body.includes("✓\nAntwort streamen")) throw new Error("State-Synchronisation unvollständig");
  const firstEventNumber = await page.locator("details summary span").first().innerText();
  if (firstEventNumber !== "01") throw new Error(`Event-Nummerierung beginnt mit ${firstEventNumber}`);

  await page.screenshot({ path: "artifacts/ag-ui-mini-dojo.png", fullPage: true });
  console.log(JSON.stringify({ ok: true, eventCount, screenshot: "artifacts/ag-ui-mini-dojo.png" }));
} finally {
  await browser.close();
}
