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

Der Browser ruft `/api/agent` auf. Next.js leitet den Request im Docker-Netz an `http://backend:8000/agent` weiter. Dadurch muss der Browser keine internen Docker-Hostnamen kennen und der SSE-Stream bleibt erhalten.

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

## Was in dieser Version bewusst nicht enthalten ist

- **Datenbank:** Für stateless Lernläufe noch nicht erforderlich.
- **Redis/Queue:** Die Szenarien sind kurz und laufen im Requestprozess.
- **Authentifizierung:** Würde vom AG-UI-Protokoll getrennt an Proxy/API ergänzt.
- **Framework-Adapter:** LangGraph, ADK oder MAF können später dieselbe Eventgrenze bedienen.

Diese Dienste sollten erst ergänzt werden, wenn eine Lektion ihren konkreten Nutzen demonstriert. Docker Compose ist bereits so strukturiert, dass weitere Services ergänzt werden können.
