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
| 10 | Graph API Tool Execution | echter Python-Tool-Aufruf mit vollständigem AG-UI-Tool-Lifecycle |
| 11 | Functional API Tool Execution | derselbe Tool-Aufruf innerhalb einer echten `@task` |
| 12 | Graph API HITL | `InMemorySaver`, echter `interrupt()` und `Command(resume=...)` |
| 13 | Functional API HITL | Interrupt innerhalb einer Task und kontrollierte Fortsetzung |

Die Lektionen 01 bis 06 sowie 08 bis 13 sind deterministisch und benötigen keinen API-Key. Lektion 07 ist optional.

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
10. Führe in Lektion 10 und 11 dasselbe echte Tool einmal über jede LangGraph-API aus.
11. Pausiere in Lektion 12 und 13 vor der Tool-Ausführung und beobachte Checkpoint, Interrupt und Resume.

## Warum ein deterministischer Lernmodus wichtig ist

Ein echtes LLM macht Inhalt und Anzahl der Chunks variabel. Das ist produktionsnah, aber schlecht, wenn du zunächst das Protokoll lernen willst. Deshalb trennt das Lab:

- **Protokoll lernen:** reproduzierbare Szenarien mit bekannten Eventsequenzen;
- **Provider integrieren:** echter OpenAI-Stream in Lektion 07;
- **Framework integrieren:** LangGraph Graph und Functional API mit getrennten Routing-, Tool- und HITL-Lektionen; ADK oder MAF können nach demselben Muster folgen.

## Projektstruktur

```text
ag-ui-mini-dojo/
├── backend/
│   ├── app/
│   │   ├── main.py            # getrennte FastAPI-Endpunkte + EventEncoder
│   │   ├── scenarios.py       # sieben unveränderte Lern-Szenarien
│   │   ├── langgraph_agui_translator.py # gemeinsame Übersetzungsgrenze
│   │   ├── langgraph_flow.py  # echter StateGraph + zentraler Translator
│   │   ├── langgraph_functional_flow.py # echte @tasks + zentraler Translator
│   │   └── langgraph_advanced_flows.py # Tool- und HITL-Flows beider APIs
│   ├── tests/
│   │   ├── test_scenarios.py
│   │   └── test_langgraph_advanced.py # Translator, Tools und echte Resumes
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
│   │   └── learning-flow.mjs  # Browserprüfung der zwölf keylosen Lektionen
│   └── Dockerfile
├── docs/
│   ├── REQUEST_FLOW.md        # vollständiger Hin- und Rückweg
│   └── LANGGRAPH_AGUI_TRANSLATOR.md # exaktes Mapping und Grenzen
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

Der E2E-Test führt zwölf keylose Lektionen aus. Für beide LangGraph-APIs beweist er echte Tool-Ausführung sowie: kein `TOOL_CALL_RESULT` vor Freigabe, Interrupt-Anzeige, Resume, Tool-Ergebnis nach Freigabe und kein Tool-Ergebnis nach Ablehnung.

Zusätzliche Backend-Regressionstests decken malformed Resume-Payloads, falsche Interrupt-IDs, parallele doppelte Resumes, abgebrochene Lock-Waiter sowie Functional-API-Cancellation mit anschließendem Retry ab. Die Demo kombiniert dafür prozesslokale Workflow-Gates mit einem Singleflight-Register pro Interrupt-ID. Für mehrere Worker ist ein persistenter Checkpointer mit atomarem Claim beziehungsweise idempotenter Tool-Ausführung erforderlich.

## Ist die LangGraph→AG-UI-Übersetzung echt?

Ja, als **echter, zentraler und benutzerdefinierter Runtime-Adapter**: [`LangGraphAguiTranslator`](backend/app/langgraph_agui_translator.py) verarbeitet die Runtime-Ausgaben aller LangGraph-Lektionen. `astream(..., stream_mode=["custom", "updates"])` liefert echte Chunks zur Laufzeit; erst danach ordnet der Translator sie AG-UI-Events zu.

Nicht behauptet wird, dass LangGraph selbst nativ AG-UI-Events ausgibt. Die Orchestrierung, Checkpoints, Interrupt-IDs und Stream-Chunks stammen real aus LangGraph; die semantische Zuordnung zu `STEP_*`, `STATE_*`, `TOOL_CALL_*` und `TEXT_MESSAGE_*` ist Anwendungscode dieses Labs. Der Lern-Translator erhält Interrupt-ID, Payload und Metadaten direkt aus dem echten LangGraph-Objekt, ohne den schwereren offiziellen Gesamtadapter als Runtime-Abhängigkeit einzubauen. Alle Details und Grenzen stehen in [`docs/LANGGRAPH_AGUI_TRANSLATOR.md`](docs/LANGGRAPH_AGUI_TRANSLATOR.md).

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
- [LangGraph Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)
- [`ag-ui-langgraph`](https://pypi.org/project/ag-ui-langgraph/)
