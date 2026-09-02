# AG-UI Learning Lab

Eine interaktive Full-Stack-Anwendung, mit der du AG-UI **nicht nur verwendest, sondern Schritt für Schritt untersuchst**.

Du führst echte Agentenläufe aus und siehst gleichzeitig:

1. die normale Anwendungsansicht;
2. den vollständigen AG-UI-Eventstream;
3. zu jedem Event Sender, Empfänger, Zweck, Auswirkung und Codeort;
4. den Weg vom Next.js-Browserclient über FastAPI bis zurück in React.

## Architektur

```text
Browser / React
    │
    │ @ag-ui/client: HttpAgent + RunAgentInput
    ▼
Next.js 16
    │
    │ Streaming Reverse Proxy (/api/agent oder LangGraph-Endpunkte)
    ▼
Python 3.11 / FastAPI
    │
    │ typisierte Events aus ag_ui.core
    ▼
EventEncoder → Server-Sent Events
    │
    ▼
HttpAgent Subscriber
    ├── Application View
    ├── Event Timeline
    └── Event Inspector
```

Die vollständige Erklärung aller zehn Transport- und Verarbeitungsschritte steht in [`docs/REQUEST_FLOW.md`](docs/REQUEST_FLOW.md).

## Lernmodule

| Nr. | Lektion | Was du ausführst und beobachtest |
|---:|---|---|
| 01 | Run Lifecycle | `RUN_STARTED`, Steps und `RUN_FINISHED` als Laufgrenzen |
| 02 | Text Streaming | Start, mehrere Text-Deltas und Ende mit gemeinsamer `messageId` |
| 03 | Tool Calls | Tool-Name, gestreamte JSON-Argumente, Ausführung und Resultat |
| 04 | Shared State | vollständiger Snapshot plus RFC-6902-JSON-Patch-Deltas |
| 05 | Human in the Loop | Interrupt, sichtbare Freigabe und Fortsetzung in einem neuen Run |
| 06 | Error Path | `RUN_ERROR` als terminales, sichtbares Protokollereignis |
| 07 | Real LLM Stream | echter OpenAI-Stream, übersetzt in dieselben AG-UI-Text-Events |
| 08 | LangGraph Flow | echte Nodes, bedingte Kante und separater AG-UI-Adapter |
| 09 | LangGraph Functional API | `@entrypoint`, `@task`, Python-Verzweigung und echte Runtime-Chunks |

Die Lektionen 01 bis 06 sowie 08 und 09 sind deterministisch und benötigen keinen API-Key. Lektion 07 ist optional.

## Schnellstart mit Docker Compose

```bash
cd /home/hermes/ag-ui-mini-dojo
docker compose up --build
```

Danach öffnen:

- **Learning App:** http://localhost:3100
- **FastAPI Docs:** http://localhost:8765/docs
- **Backend Health:** http://localhost:8765/health

Beenden:

```bash
docker compose down
```

## Optional: OpenAI-Key für Lektion 07

```bash
cp .env.example .env
```

Dann in `.env` eintragen:

```dotenv
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
```

Anschließend neu starten:

```bash
docker compose up --build
```

Der Key bleibt ausschließlich im Python-Backend. Er wird weder in Next.js eingebettet noch an den Browser gesendet. Der Health-Endpunkt zeigt nur, **ob** ein Key konfiguriert ist, niemals seinen Wert.

## Lokal ohne Docker entwickeln

### Python-Backend

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

### Next.js-Frontend

In einem zweiten Terminal:

```bash
cd frontend
npm install
npm run dev
```

Dann http://localhost:3000 öffnen.

## Wo du anfangen solltest

1. Öffne **Lektion 01** und reduziere den Event-Abstand nicht.
2. Starte den Lauf und beobachte die Architekturleiste.
3. Klicke jedes Event in der Timeline von oben nach unten an.
4. Lies im Event Inspector jeweils „Wer sendet?“, „Wer verarbeitet?“ und „Was ändert sich?“.
5. Öffne parallel die dort angegebene Funktion in `backend/app/scenarios.py`.
6. Wiederhole das für Lektion 02 bis 06.
7. Setze erst danach optional den OpenAI-Key und vergleiche Lektion 07 mit der deterministischen Streaming-Lektion.
8. Öffne Lektion 08 und vergleiche den echten LangGraph-State mit den daraus übersetzten AG-UI-Events.
9. Vergleiche in Lektion 09 die Functional API und ihre sichtbaren `custom`-/`updates`-Runtime-Chunks mit der Graph API.

## Warum ein deterministischer Lernmodus wichtig ist

Ein echtes LLM macht Inhalt und Anzahl der Chunks variabel. Das ist produktionsnah, aber schlecht, wenn du zunächst das Protokoll lernen willst. Deshalb trennt das Lab:

- **Protokoll lernen:** reproduzierbare Szenarien mit bekannten Eventsequenzen;
- **Provider integrieren:** echter OpenAI-Stream in Lektion 07;
- **Framework integrieren:** separat gehaltene LangGraph Graph API in Lektion 08 und Functional API in Lektion 09; ADK oder MAF können nach demselben Muster folgen.

## Projektstruktur

```text
ag-ui-mini-dojo/
├── backend/
│   ├── app/
│   │   ├── main.py            # getrennte FastAPI-Endpunkte + EventEncoder
│   │   ├── scenarios.py       # sieben unveränderte Lern-Szenarien
│   │   ├── langgraph_flow.py  # echter StateGraph + AG-UI-Adapter
│   │   └── langgraph_functional_flow.py # echte @tasks + Runtime-Stream-Adapter
│   ├── tests/
│   │   └── test_scenarios.py  # Eventsequenzen und Interrupt-Resume
│   ├── Dockerfile
│   ├── pyproject.toml
│   └── uv.lock
├── frontend/
│   ├── app/
│   │   ├── page.tsx           # HttpAgent, Subscriber und Lernoberfläche
│   │   └── globals.css
│   ├── lib/
│   │   └── learning.ts        # Lektionen und Erklärungen aller Eventtypen
│   ├── e2e/
│   │   └── learning-flow.mjs  # Browserprüfung der acht keylosen Lektionen
│   └── Dockerfile
├── docs/
│   └── REQUEST_FLOW.md        # vollständiger Hin- und Rückweg
├── compose.yaml
└── .env.example
```

## Prüfungen

Backend:

```bash
cd backend
uv run ruff check .
uv run pytest -q
```

Frontend:

```bash
cd frontend
npm run typecheck
npm run build
```

Vollständiger Browserflow gegen den laufenden Compose-Stack:

```bash
cd frontend
npm run test:e2e
```

Der E2E-Test führt Lifecycle, Streaming, Tools, State, Interrupt mit Freigabe, Fehlerpfad sowie beide separaten LangGraph-Varianten über die echte UI aus.

## Ist die LangGraph→AG-UI-Übersetzung echt?

Ja, als **echter benutzerdefinierter Runtime-Adapter**: Lektion 09 startet einen mit `@entrypoint` dekorierten LangGraph-Workflow, dessen `@task`-Funktionen über den aktiven LangGraph `StreamWriter` Ereignisse senden. `functional_workflow.astream(..., stream_mode=["custom", "updates"])` liefert diese Chunks zur Laufzeit. Erst danach ordnet `run_functional_flow()` sie AG-UI-Events zu.

Nicht behauptet wird, dass LangGraph selbst nativ AG-UI-Events ausgibt oder dass dies ein offizieller vorgefertigter Adapter ist. Die Orchestrierung und Stream-Chunks stammen real aus LangGraph; die semantische Zuordnung zu `STEP_*`, `STATE_*` und `TEXT_MESSAGE_*` ist Anwendungscode dieses Labs. Der Client-State zeigt deshalb `lastCustomLangGraphChunk` und `lastUpdateLangGraphChunk` mit Stream-Modus und Rohdaten als überprüfbare Provenienz.

## Was AG-UI hier leistet

AG-UI definiert weder dein LLM noch dein Agenten-Framework oder UI-Design. Es definiert das gemeinsame Ereignisvokabular:

- Lifecycle und Fehler;
- gestreamte Nachrichten;
- Tool-Aufrufe und Resultate;
- synchronisierten Anwendungszustand;
- Unterbrechungen und menschliche Entscheidungen.

Dadurch kann das Python-Backend später ersetzt oder erweitert werden, ohne im Frontend für jedes Agenten-Framework ein eigenes Streamingprotokoll zu erfinden.

## Offizielle Referenzen

- [AG-UI Dojo](https://dojo.ag-ui.com/)
- [AG-UI Events](https://docs.ag-ui.com/concepts/events)
- [State Management](https://docs.ag-ui.com/concepts/state)
- [Tools](https://docs.ag-ui.com/concepts/tools)
- [Interrupts](https://docs.ag-ui.com/concepts/interrupts)
- [`HttpAgent`](https://docs.ag-ui.com/sdk/js/client/http-agent)
- [AG-UI GitHub Repository](https://github.com/ag-ui-protocol/ag-ui)
