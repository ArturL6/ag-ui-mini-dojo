"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { HttpAgent } from "@ag-ui/client";
import type { BaseEvent } from "@ag-ui/core";
import { explainEvent, lessons, type Lesson } from "../lib/learning";

type LoggedEvent = { id: number; event: BaseEvent; receivedAt: string };
type PendingInterrupt = { id: string; message: string };
type BackendHealth = { openaiConfigured: boolean; openaiModel: string } | null;

const pipeline = [
  ["1", "Browser", "Benutzereingabe"],
  ["2", "HttpAgent", "RunAgentInput"],
  ["3", "Next.js", "Streaming Proxy"],
  ["4", "FastAPI", "Szenario / Agent"],
  ["5", "EventEncoder", "SSE Frames"],
  ["6", "Subscriber", "UI + State"],
];

function eventTone(type: string) {
  if (type.startsWith("RUN_")) return "lifecycle";
  if (type.startsWith("TEXT_")) return "text";
  if (type.startsWith("TOOL_")) return "tool";
  if (type.startsWith("STATE_")) return "state";
  return "step";
}

export default function LearningLab() {
  const [lesson, setLesson] = useState<Lesson>(lessons[0]);
  const [prompt, setPrompt] = useState(lessons[0].prompt);
  const [events, setEvents] = useState<LoggedEvent[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [answer, setAnswer] = useState("");
  const [agentState, setAgentState] = useState<Record<string, unknown>>({});
  const [status, setStatus] = useState<"ready" | "running" | "paused" | "done" | "error">("ready");
  const [error, setError] = useState("");
  const [delayMs, setDelayMs] = useState(180);
  const [interrupt, setInterrupt] = useState<PendingInterrupt | null>(null);
  const [health, setHealth] = useState<BackendHealth>(null);
  const agentRef = useRef<HttpAgent | null>(null);
  const eventCounter = useRef(0);

  useEffect(() => {
    fetch("/api/health")
      .then((response) => response.json())
      .then((data) => setHealth(data))
      .catch(() => setHealth(null));
  }, []);

  const selected = useMemo(
    () => events.find((entry) => entry.id === selectedId) ?? events.at(-1),
    [events, selectedId],
  );
  const explanation = selected
    ? explainEvent(
        selected.event.type,
        lesson.id.startsWith("langgraph") ? lesson.source : undefined,
      )
    : null;
  const seenTypes = new Set(events.map(({ event }) => String(event.type)));

  function chooseLesson(next: Lesson) {
    setLesson(next);
    setPrompt(next.prompt);
    setEvents([]);
    setSelectedId(null);
    setAnswer("");
    setAgentState({});
    setError("");
    setInterrupt(null);
    setStatus("ready");
    agentRef.current?.abortRun();
    agentRef.current = null;
  }

  function createSubscriber() {
    return {
      onEvent: ({ event }: { event: BaseEvent }) => {
        const id = ++eventCounter.current;
        const entry = { id, event, receivedAt: new Date().toLocaleTimeString("de-DE") };
        setEvents((current) => [...current, entry]);
        setSelectedId(id);
      },
      onTextMessageContentEvent: ({ textMessageBuffer }: { textMessageBuffer: string }) => {
        setAnswer(textMessageBuffer);
      },
      onTextMessageEndEvent: ({ textMessageBuffer }: { textMessageBuffer: string }) => {
        setAnswer(textMessageBuffer);
      },
      onStateChanged: ({ state }: { state: Readonly<Record<string, unknown>> }) => {
        setAgentState({ ...state });
      },
      onRunFinishedEvent: (result: {
        outcome: "success" | "interrupt";
        interrupts?: Array<{ id: string; message?: string }>;
      }) => {
        if (result.outcome === "interrupt" && result.interrupts?.length) {
          setInterrupt({
            id: result.interrupts[0].id,
            message: result.interrupts[0].message ?? "Der Agent wartet auf deine Eingabe.",
          });
          setStatus("paused");
        } else {
          setStatus("done");
        }
      },
      onRunErrorEvent: ({ event }: { event: { message: string } }) => {
        setError(event.message);
        setStatus("error");
      },
      onRunFailed: ({ error: runError }: { error: Error }) => {
        setError(runError.message);
        setStatus("error");
      },
    };
  }

  async function runLesson() {
    if (!prompt.trim() || status === "running") return;
    eventCounter.current = 0;
    setEvents([]);
    setSelectedId(null);
    setAnswer("");
    setAgentState({});
    setInterrupt(null);
    setError("");
    setStatus("running");

    const agent = new HttpAgent({
      url: lesson.endpoint
        ? `${lesson.endpoint}?delay_ms=${delayMs}`
        : `/api/agent?scenario=${lesson.id}&delay_ms=${delayMs}`,
      agentId: "learning-agent",
      threadId: `lesson-${lesson.id}`,
    });
    agent.messages = [
      { id: crypto.randomUUID(), role: "user", content: prompt.trim() },
    ];
    agentRef.current = agent;

    try {
      await agent.runAgent({ runId: crypto.randomUUID() }, createSubscriber());
    } catch (runError) {
      setError(runError instanceof Error ? runError.message : "Unbekannter Clientfehler");
      setStatus("error");
    }
  }

  async function resumeInterrupt(approved: boolean) {
    const agent = agentRef.current;
    if (!agent || !interrupt) return;
    setStatus("running");
    setError("");
    setInterrupt(null);
    try {
      await agent.runAgent(
        {
          runId: crypto.randomUUID(),
          resume: [
            {
              interruptId: interrupt.id,
              status: "resolved",
              payload: { approved },
            },
          ],
        },
        createSubscriber(),
      );
    } catch (runError) {
      setError(runError instanceof Error ? runError.message : "Resume fehlgeschlagen");
      setStatus("error");
    }
  }

  return (
    <main>
      <aside className="curriculum">
        <div className="brand">
          <span className="brand-mark">AG</span>
          <div><strong>AG-UI</strong><small>Learning Lab</small></div>
        </div>
        <p className="aside-intro">Eine echte Anwendung, in der du jeden Protokollschritt ausführst und untersuchst.</p>
        <nav aria-label="Lektionen">
          {lessons.map((item) => (
            <button
              key={item.id}
              onClick={() => chooseLesson(item)}
              className={item.id === lesson.id ? "lesson active" : "lesson"}
              data-testid={`lesson-${item.id}`}
            >
              <span>{item.number}</span>
              <div><strong>{item.title}</strong><small>{item.subtitle}</small></div>
              {item.badge && <em>{item.badge}</em>}
            </button>
          ))}
        </nav>
        <div className="stack-card">
          <small>LIVE STACK</small>
          <span>Next.js 16</span><span>FastAPI</span><span>@ag-ui/client</span><span>LangGraph Graph + Functional API</span><span>Docker Compose</span>
        </div>
      </aside>

      <div className="workspace">
        <header className="topbar">
          <div>
            <span className="kicker">LEKTION {lesson.number} / {String(lessons.length).padStart(2, "0")}</span>
            <h1>{lesson.title}</h1>
            <p>{lesson.goal}</p>
          </div>
          <div className="backend-status">
            <span className={health ? "dot online" : "dot"} />
            <div><strong>{health ? "Backend verbunden" : "Backend nicht erreichbar"}</strong>
              <small>{health?.openaiConfigured ? `OpenAI: ${health.openaiModel}` : "OpenAI-Key nicht gesetzt"}</small>
            </div>
          </div>
        </header>

        <section className="architecture" aria-label="Architekturfluss">
          {pipeline.map(([number, title, detail], index) => (
            <div className="pipeline-wrap" key={title}>
              <div className="pipeline-node">
                <span>{number}</span><strong>{title}</strong><small>{detail}</small>
              </div>
              {index < pipeline.length - 1 && <b>→</b>}
            </div>
          ))}
        </section>

        <section className="lesson-brief">
          <div><small>LERNZIEL</small><p>{lesson.keyIdea}</p></div>
          <div><small>SERVER-CODE</small><code>{lesson.source}</code></div>
          <div className="event-checks"><small>ERWARTETE EVENTS</small><div>
            {lesson.expectedEvents.map((type) => <span className={seenTypes.has(type) ? "seen" : ""} key={type}>{seenTypes.has(type) ? "✓" : "○"} {type}</span>)}
          </div></div>
        </section>

        <section className="runner">
          <div className="runner-input">
            <label htmlFor="prompt">RunAgentInput.messages[-1]</label>
            <textarea id="prompt" value={prompt} onChange={(event) => setPrompt(event.target.value)} />
          </div>
          <div className="runner-actions">
            <label>Event-Abstand <strong>{delayMs} ms</strong></label>
            <input aria-label="Event-Abstand" type="range" min="0" max="800" step="40" value={delayMs} onChange={(event) => setDelayMs(Number(event.target.value))} />
            <button onClick={() => void runLesson()} disabled={status === "running"} data-testid="run-lesson">
              {status === "running" ? "Run läuft …" : "Lektion ausführen"}
            </button>
          </div>
        </section>

        <div className="lab-grid">
          <section className="panel application-panel">
            <div className="panel-title"><span>APPLICATION VIEW</span><b className={`run-status ${status}`}>{status}</b></div>
            {interrupt && (
              <div className="approval" data-testid="approval-card">
                <small>HUMAN IN THE LOOP</small><h3>Agent wartet auf Freigabe</h3><p>{interrupt.message}</p>
                <div><button onClick={() => void resumeInterrupt(false)}>Ablehnen</button><button className="approve" onClick={() => void resumeInterrupt(true)} data-testid="approve">Freigeben & fortsetzen</button></div>
              </div>
            )}
            <div className="answer-card">
              <small>GESTREAMTE ASSISTANT-ANTWORT</small>
              <p data-testid="answer">{answer || "Führe die Lektion aus. Die zusammengesetzte Nachricht erscheint hier."}</p>
              {status === "running" && <i />}
            </div>
            <div className="state-card">
              <small>AKTUELLER CLIENT-STATE</small>
              <pre data-testid="client-state">{JSON.stringify(agentState, null, 2)}</pre>
            </div>
            {error && <div className="error-card" data-testid="run-error"><strong>RUN_ERROR</strong><p>{error}</p></div>}
          </section>

          <section className="panel timeline-panel">
            <div className="panel-title"><span>LIVE EVENT TIMELINE</span><b>{events.length} empfangen</b></div>
            <div className="timeline" data-testid="event-timeline">
              {events.length === 0 && <p className="empty">Noch keine Events. Nach dem Start siehst du hier den vollständigen SSE-Strom.</p>}
              {events.map((entry) => (
                <button key={entry.id} className={selected?.id === entry.id ? "event-row selected" : "event-row"} onClick={() => setSelectedId(entry.id)}>
                  <span>{String(entry.id).padStart(2, "0")}</span>
                  <i className={eventTone(entry.event.type)} />
                  <code>{entry.event.type}</code>
                  <time>{entry.receivedAt}</time>
                </button>
              ))}
            </div>
          </section>

          <section className="panel inspector-panel">
            <div className="panel-title"><span>EVENT INSPECTOR</span><b>Was · Wo · Warum</b></div>
            {!selected || !explanation ? <p className="empty">Wähle nach dem Start ein Event aus.</p> : (
              <div className="inspector" data-testid="event-inspector">
                <div className="event-head"><span className={eventTone(selected.event.type)}>{explanation.label}</span><code>{selected.event.type}</code></div>
                <dl>
                  <div><dt>Wer sendet?</dt><dd>{explanation.emittedBy}</dd></div>
                  <div><dt>Wer verarbeitet?</dt><dd>{explanation.consumedBy}</dd></div>
                  <div><dt>Warum?</dt><dd>{explanation.why}</dd></div>
                  <div><dt>Was ändert sich?</dt><dd>{explanation.changes}</dd></div>
                  <div><dt>Wo im Code?</dt><dd><code>{explanation.source}</code></dd></div>
                </dl>
                <small>ECHTER EVENT-PAYLOAD</small>
                <pre>{JSON.stringify(selected.event, null, 2)}</pre>
              </div>
            )}
          </section>
        </div>
      </div>
    </main>
  );
}
