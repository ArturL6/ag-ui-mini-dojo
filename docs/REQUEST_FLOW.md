# Der vollständige Request- und Eventfluss

Dieses Dokument ist die textuelle Begleitung zur Architekturleiste in der Anwendung. Führe zuerst Lektion 01 aus und verfolge dann jeden Schritt hier.

## Hinweg: vom Menschen zum Python-Agenten

### 1. Eingabe im Browser

**Datei:** `frontend/app/page.tsx`  
**Funktion:** `runLesson()`

Die React-Anwendung liest deine Eingabe und legt eine AG-UI-User-Message an:

```ts
agent.messages = [
  { id: crypto.randomUUID(), role: "user", content: prompt }
];
```

Das ist noch kein Netzwerkaufruf. Es ist lokaler Client-Zustand des `HttpAgent`.

### 2. `HttpAgent.runAgent()` baut `RunAgentInput`

**Paket:** `@ag-ui/client`  
**Datei:** `frontend/app/page.tsx`

```ts
await agent.runAgent({ runId: crypto.randomUUID() }, subscriber);
```

Der Client ergänzt unter anderem:

- `threadId`: Identität der Unterhaltung;
- `runId`: Identität dieses einzelnen Laufs;
- `messages`: bisherige Nachrichten;
- `state`: aktueller gemeinsamer Zustand;
- `tools`: optional vom Frontend angebotene Tools;
- `resume`: optional Antworten auf offene Interrupts.

Der HTTP-Request ist ein `POST` mit JSON-Body und `Accept`-Header für einen AG-UI-Eventstream.

### 3. Next.js ist der Reverse Proxy

**Datei:** `frontend/next.config.ts`

Der Browser ruft für die bisherigen Lektionen `/api/agent` auf. Next.js leitet den Request im Docker-Netz an `http://backend:8000/agent` weiter. Die LangGraph-Lektionen 08–13 besitzen jeweils eigene Proxy- und Backend-Endpunkte für Graph/Functional Basics, Tools und HITL. Dadurch muss der Browser keine internen Docker-Hostnamen kennen und der SSE-Stream bleibt erhalten.

### 4. FastAPI validiert `RunAgentInput`

**Datei:** `backend/app/main.py`  
**Funktion:** `agent_endpoint()`

FastAPI erzeugt das Pydantic-Modell `RunAgentInput` aus `ag_ui.core`. Ungültige Requests erreichen die Agentenlogik nicht.

Der Query-Parameter `scenario` wählt die Lernlektion. In einer echten Anwendung würde hier meist ein konkreter Agent oder Framework-Adapter ausgewählt.

### 5. Die Szenariofunktion erzeugt typisierte Events

**Datei:** `backend/app/scenarios.py`

Jede Lektion ist ein `async` Generator. Beispiel:

```python
yield RunStartedEvent(...)
yield TextMessageStartEvent(...)
yield TextMessageContentEvent(...)
yield TextMessageEndEvent(...)
yield RunFinishedEvent(...)
```

Der Generator ist der lehrbare Ersatz für einen echten Agenten-Workflow. Lektion 07 ersetzt nur die Textquelle durch einen realen OpenAI-Stream; das AG-UI-Protokoll bleibt gleich.

### 5a. Der separate LangGraph-Pfad in Lektion 08

**Datei:** `backend/app/langgraph_flow.py`
**Endpunkt:** `POST /agent/langgraph`

Dieser Pfad ist absichtlich nicht in `SCENARIOS` registriert. Ein echter `StateGraph` führt aus:

```text
START → understand ─┬─ tool → learning_tool → respond → END
                    └─ direct ─────────────→ respond → END
```

`LEARNING_GRAPH.astream(..., stream_mode="updates")` liefert nach jedem Node dessen State-Update. `run_langgraph_flow()` übersetzt diese Updates anschließend in `STEP_*`, `STATE_*` und `TEXT_MESSAGE_*`. LangGraph entscheidet damit den internen Ablauf, während AG-UI ausschließlich die sichtbare Grenze zur Oberfläche bildet.

### 5b. Functional API und überprüfbare Übersetzung in Lektion 09

**Datei:** `backend/app/langgraph_functional_flow.py`
**Endpunkt:** `POST /agent/langgraph-functional`

`functional_workflow` ist ein echter `@entrypoint`; `understand_task`, `learning_tool_task` und `respond_task` sind echte `@task`-Funktionen. Der Entry Point verwendet normale Python-Kontrolllogik:

```text
@entrypoint → understand_task → if route == "tool": learning_tool_task → respond_task
```

Jede Task schreibt über `get_stream_writer()` in den aktiven LangGraph-Runtime-Stream. Der Adapter konsumiert gleichzeitig `custom` und `updates`:

```python
async for stream_mode, runtime_chunk in functional_workflow.astream(
    inputs,
    stream_mode=["custom", "updates"],
):
    # runtime_chunk → AG-UI STEP/STATE/TEXT event
```

Damit ist die Übersetzung real, aber benutzerdefiniert: Die Quell-Chunks kommen aus der tatsächlichen LangGraph-Ausführung; `LangGraphAguiTranslator` definiert zentral die fachliche Zuordnung zum AG-UI-Vokabular. `lastCustomLangGraphChunk` und `lastUpdateLangGraphChunk` legen im sichtbaren Client-State beide Stream-Modi samt Rohdaten offen.

### 5c. Tool-Ausführung in Lektion 10 und 11

**Dateien:** `backend/app/langgraph_advanced_flows.py`, `backend/app/langgraph_agui_translator.py`

Beide APIs führen dasselbe echte, mit `@tool` dekorierte Tool `count_words` über `.invoke(...)` aus. Die Graph API ruft es in einer StateGraph-Node auf; die Functional API ruft es innerhalb einer `@task` auf. Vor und nach dem Aufruf schreibt die laufende Node/Task explizite Signale über LangGraphs `get_stream_writer()`:

```text
tool_call_start → count_words(...) → tool_call_result
```

Der zentrale Translator erzeugt daraus `TOOL_CALL_START`, `TOOL_CALL_ARGS`, `TOOL_CALL_END` und erst nach der tatsächlichen Ausführung `TOOL_CALL_RESULT`. Das Tool-Ergebnis enthält die gezählten Wörter und `executed: true`; es ist kein vorab festgelegtes AG-UI-Demoresultat.

### 5d. Echte HITL-Interrupts in Lektion 12 und 13

Beide Workflows verwenden einen `InMemorySaver`. Der erste Run schlägt das Tool vor und erreicht danach LangGraphs echtes `interrupt()`:

```text
Graph/Task → interrupt(payload) → Checkpoint → __interrupt__ update
```

Der Translator übernimmt das echte LangGraph-Interruptobjekt einschließlich ID, Payload und Metadaten direkt in die AG-UI-Repräsentation. Die UI sendet ihre Entscheidung in einem neuen `RunAgentInput.resume[]`; das Backend prüft die Interrupt-ID gegen den offenen Checkpoint und setzt denselben LangGraph-Thread mit `Command(resume=True|False)` fort.

Das geschützte Tool liegt hinter der Approval-Kante beziehungsweise hinter der Functional-API-Verzweigung und kann deshalb vor der Freigabe nicht laufen. Resume akzeptiert nur `status = "resolved"` und ein Objekt mit einem echten booleschen `approved`-Wert. Ein prozesslokales Gate serialisiert denselben Workflow/Thread. Zusätzlich bindet ein Singleflight-Register die geschützte Tool-Ausführung an die echte Interrupt-ID. Dadurch bleibt der Aufruf auch dann einmalig, wenn bei der Functional API der HTTP-Consumer abbricht, während die synchrone Tool-Task noch läuft, und danach ein Retry eintrifft. Der E2E-Test prüft explizit, dass im ersten Run kein `TOOL_CALL_RESULT` existiert und es erst nach Freigabe erscheint.

Die vollständige Mapping-Tabelle und die Grenze zwischen nativen Runtime-Daten und Anwendungscode stehen in [`LANGGRAPH_AGUI_TRANSLATOR.md`](LANGGRAPH_AGUI_TRANSLATOR.md).

## Rückweg: vom Python-Agenten zur sichtbaren UI

### 6. `EventEncoder` serialisiert jedes Event

**Datei:** `backend/app/main.py`

```python
encoder = EventEncoder(accept=request.headers.get("accept"))
yield encoder.encode(event)
```

Im lesbaren SSE-Modus sieht ein Frame vereinfacht so aus:

```text
data: {"type":"TEXT_MESSAGE_CONTENT","messageId":"...","delta":"Hallo"}

```

AG-UI definiert die Events; SSE ist hier der gewählte Transport.

### 7. `StreamingResponse` sendet sofort

FastAPI wartet nicht auf den gesamten Lauf. Sobald der Generator ein Event liefert, kann es über die bestehende HTTP-Verbindung zum Client fließen. Deshalb erscheinen Text und Fortschritt schrittweise.

### 8. `HttpAgent` dekodiert und reduziert Events

`@ag-ui/client` verarbeitet den Stream in Reihenfolge und führt interne Puffer:

- Textdeltas werden anhand `messageId` zusammengefügt;
- Toolargumente werden anhand `toolCallId` zusammengesetzt;
- `STATE_SNAPSHOT` ersetzt den State;
- `STATE_DELTA` wird als JSON Patch angewandt;
- Run-Lifecycle und Interrupts werden geprüft.

### 9. Subscriber übersetzen Protokoll in React-State

**Datei:** `frontend/app/page.tsx`  
**Funktion:** `createSubscriber()`

Die Lernanwendung nutzt zwei Ebenen gleichzeitig:

- `onEvent`: speichert jedes rohe Event in der Timeline;
- spezifische Callbacks wie `onTextMessageContentEvent` und `onStateChanged`: aktualisieren die sichtbare Anwendung.

Genau das ist der Kernnutzen von AG-UI: Die Anwendung reagiert auf semantische Ereignisse statt auf einen proprietären Response-Blob.

### 10. React rendert Anwendung und Lernwerkzeuge

Drei Ansichten werden aus demselben Lauf gespeist:

1. **Application View:** das, was ein Endnutzer sehen würde;
2. **Event Timeline:** der empfangene Protokollstrom;
3. **Event Inspector:** Bedeutung, Sender, Empfänger, Codeort und echter Payload.

## Sonderfall: Human in the Loop

Lektion 05 besteht absichtlich aus zwei Runs:

1. Run A sendet einen Tool Call und endet mit `RUN_FINISHED` plus `outcome.type = "interrupt"`.
2. Die UI zeigt eine Freigabe.
3. Deine Entscheidung wird in einem neuen `RunAgentInput.resume[]` gesendet.
4. Run B sendet das `TOOL_CALL_RESULT` gegen die ursprüngliche `toolCallId` und endet erfolgreich.

Ein Interrupt hält also nicht unbegrenzt denselben HTTP-Request offen. Er schafft eine robuste, auditierbare Grenze zwischen Vorschlag und menschlicher Entscheidung.

Lektion 12 und 13 demonstrieren denselben AG-UI-Ablauf mit tatsächlicher LangGraph-Persistenzsemantik: `interrupt()` pausiert, der Checkpointer hält den Zustand und `Command(resume=...)` liefert die Entscheidung zurück in die pausierte Node beziehungsweise Task.

## Was in dieser Version bewusst nicht enthalten ist

- **Dauerhafter Checkpointer:** HITL verwendet bewusst `InMemorySaver` und ein prozesslokales Singleflight-Register; ein Prozessneustart verwirft offene Lern-Interrupts und Idempotency-Einträge. Beide Speicher werden im Demo-Prozess nicht fachlich bereinigt. Mehrere Worker erfordern eine gemeinsame Ablage mit atomarem Resume-Claim oder idempotenter Tool-Ausführung.
- **Redis/Queue:** Die Szenarien sind kurz und laufen im Requestprozess.
- **Authentifizierung:** Würde vom AG-UI-Protokoll getrennt an Proxy/API ergänzt.
- **Weitere Framework-Adapter:** LangGraph Graph API und Functional API sind exemplarisch vorhanden; ADK oder MAF könnten später dieselbe Eventgrenze bedienen.

Diese Dienste sollten erst ergänzt werden, wenn eine Lektion ihren konkreten Nutzen demonstriert. Docker Compose ist bereits so strukturiert, dass weitere Services ergänzt werden können.
