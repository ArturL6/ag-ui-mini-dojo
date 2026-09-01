import React, { useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import { HttpAgent } from "@ag-ui/client";
import type { BaseEvent } from "@ag-ui/core";
import "./styles.css";

type DemoState = {
  goal?: string;
  status?: string;
  steps?: Array<{ label: string; done: boolean }>;
};

type LoggedEvent = {
  id: number;
  type: string;
  event: BaseEvent;
};

function App() {
  const [prompt, setPrompt] = useState("Plane mir einen einfachen Lerntag für AG-UI");
  const [answer, setAnswer] = useState("");
  const [state, setState] = useState<DemoState>({});
  const [events, setEvents] = useState<LoggedEvent[]>([]);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");

  const agent = useMemo(
    () =>
      new HttpAgent({
        url: "/agent",
        agentId: "mini-dojo-agent",
        threadId: "learning-thread",
      }),
    [],
  );

  async function runDemo() {
    const text = prompt.trim();
    if (!text || running) return;

    setRunning(true);
    setError("");
    setAnswer("");
    setState({});
    setEvents([]);
    let eventNumber = 0;

    agent.messages = [
      {
        id: crypto.randomUUID(),
        role: "user",
        content: text,
      },
    ];

    try {
      await agent.runAgent(
        { runId: crypto.randomUUID() },
        {
          onEvent: ({ event }) => {
            const id = ++eventNumber;
            setEvents((current) => [
              ...current,
              { id, type: event.type, event },
            ]);
          },
          onTextMessageContentEvent: ({ textMessageBuffer }) => {
            setAnswer(textMessageBuffer);
          },
          onTextMessageEndEvent: ({ textMessageBuffer }) => {
            setAnswer(textMessageBuffer);
          },
          onStateChanged: ({ state: nextState }) => {
            setState(nextState as DemoState);
          },
          onRunFailed: ({ error: runError }) => {
            setError(runError.message);
          },
        },
      );
    } catch (runError) {
      setError(runError instanceof Error ? runError.message : "Unbekannter Fehler");
    } finally {
      setRunning(false);
    }
  }

  return (
    <main>
      <header>
        <span className="eyebrow">AG-UI MINI DOJO</span>
        <h1>Ein Agentenlauf, sichtbar gemacht</h1>
        <p>
          Links siehst du die Anwendung. Rechts siehst du exakt die standardisierten
          AG-UI-Events, aus denen die Oberfläche entsteht.
        </p>
      </header>

      <section className="controls" aria-label="Demo starten">
        <label htmlFor="prompt">Aufgabe an den Demo-Agenten</label>
        <div className="input-row">
          <input
            id="prompt"
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") void runDemo();
            }}
          />
          <button onClick={() => void runDemo()} disabled={running}>
            {running ? "Agent läuft …" : "Demo starten"}
          </button>
        </div>
        <p className="hint">Kein API-Key nötig: Der Agent ist bewusst deterministisch.</p>
      </section>

      {error && <div className="error">{error}</div>}

      <div className="grid">
        <section className="panel app-panel" aria-labelledby="app-title">
          <div className="panel-heading">
            <div>
              <span className="number">01</span>
              <h2 id="app-title">Anwendung</h2>
            </div>
            <span className={`status ${running ? "active" : ""}`}>
              {state.status ?? "bereit"}
            </span>
          </div>

          <div className="goal-card">
            <small>Gemeinsamer Zustand</small>
            <strong>{state.goal ?? "Starte die Demo"}</strong>
          </div>

          <ol className="steps">
            {(state.steps ?? [
              { label: "Anfrage verstehen", done: false },
              { label: "Checkliste erzeugen", done: false },
              { label: "Antwort streamen", done: false },
            ]).map((step) => (
              <li className={step.done ? "done" : ""} key={step.label}>
                <span>{step.done ? "✓" : "○"}</span>
                {step.label}
              </li>
            ))}
          </ol>

          <div className="answer" aria-live="polite">
            <small>Gestreamte Antwort</small>
            <p>{answer || "Die Antwort erscheint hier Stück für Stück."}</p>
            {running && <span className="cursor" />}
          </div>
        </section>

        <section className="panel event-panel" aria-labelledby="events-title">
          <div className="panel-heading">
            <div>
              <span className="number">02</span>
              <h2 id="events-title">AG-UI Event Stream</h2>
            </div>
            <span className="count">{events.length} Events</span>
          </div>

          <div className="event-list" aria-live="polite">
            {events.length === 0 && (
              <p className="empty">Noch keine Events. Starte links den Agentenlauf.</p>
            )}
            {events.map((entry) => (
              <details key={entry.id} open={entry.type.includes("STATE")}>
                <summary>
                  <span>{String(entry.id).padStart(2, "0")}</span>
                  <code>{entry.type}</code>
                </summary>
                <pre>{JSON.stringify(entry.event, null, 2)}</pre>
              </details>
            ))}
          </div>
        </section>
      </div>

      <footer>
        <strong>Was AG-UI hier übernimmt:</strong> ein gemeinsames Vokabular für
        Lifecycle, Fortschritt, Tool-Aufrufe, Text-Streaming und State-Synchronisation.
      </footer>
    </main>
  );
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
