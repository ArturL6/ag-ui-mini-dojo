# LangGraph → AG-UI Translator

## Zweck

`backend/app/langgraph_agui_translator.py` ist die gemeinsame, sichtbare Übersetzungsgrenze für alle LangGraph-Lektionen 08–13.

```text
LangGraph Graph API / Functional API
        │
        ├── native updates-Chunks
        ├── custom StreamWriter-Signale
        └── echte Interrupt-Objekte
                │
                ▼
LangGraphAguiTranslator
        │
        ├── RUN_*
        ├── STEP_*
        ├── STATE_*
        ├── TOOL_CALL_*
        └── TEXT_MESSAGE_*
                │
                ▼
EventEncoder → SSE → @ag-ui/client
```

## Was nativ aus LangGraph stammt

- `StateGraph.astream(..., stream_mode=["custom", "updates"])`
- Functional-API-`@entrypoint` und `@task`
- `get_stream_writer()` als aktiver Runtime-Kanal
- `interrupt()` mit einer echten LangGraph-Interrupt-ID
- `InMemorySaver` als Checkpointer
- `Command(resume=...)` für die Fortsetzung
- `__interrupt__`- und `updates`-Chunks

## Was der Lern-Translator macht

| Beobachtbares LangGraph-Signal | AG-UI-Ausgabe |
|---|---|
| Start eines HTTP-Runs | `RUN_STARTED` |
| nativer `updates`-Chunk | `STATE_DELTA` mit Roh-Chunk-Provenienz |
| `step_start` / Task-Start über `StreamWriter` | `STEP_STARTED` |
| `step_end` / Task-Ende über `StreamWriter` | `STEP_FINISHED` |
| `tool_call_start` mit Name und Args | `TOOL_CALL_START` → `TOOL_CALL_ARGS` → `TOOL_CALL_END` |
| `tool_call_result` nach echter Python-Ausführung | `TOOL_CALL_RESULT` |
| Antwortsignal | `TEXT_MESSAGE_START` → Deltas → `TEXT_MESSAGE_END` |
| echtes LangGraph-Interruptobjekt | `RUN_FINISHED` mit `outcome.type = "interrupt"` |
| vollständiger Runtime-Lauf | `RUN_FINISHED` mit `outcome.type = "success"` |

Jeder Runtime-Chunk bleibt zusätzlich in `lastCustomLangGraphChunk` beziehungsweise `lastUpdateLangGraphChunk` sichtbar. So kann man im Event Inspector Quellsignal und Zielereignis vergleichen.

## Ehrliche Grenze

LangGraph gibt nicht automatisch für jedes beliebige Tool AG-UI-Tool-Events aus. Die Tool-Lektionen führen echte, mit `@tool` dekorierte Tools über `.invoke(...)` aus und instrumentieren den Aufruf innerhalb der laufenden Node beziehungsweise `@task` über `get_stream_writer()`. Der Translator interpretiert diese expliziten Runtime-Signale. Das Tool selbst wird wirklich ausgeführt; bei HITL erst nach erfolgreichem Resume.

Das Paket `ag-ui-langgraph` bietet zusätzlich einen umfangreichen offiziellen Adapter für `CompiledStateGraph`-Agenten. Dieses Lab verwendet ihn bewusst nicht als Runtime-Abhängigkeit: Er versteckt einen großen Teil des didaktisch relevanten Mappings, bringt zusätzliche LangChain/A2UI-Abhängigkeiten mit und deckt die Functional API nicht über denselben klaren Vertrag ab. Der kleine Lern-Translator übernimmt Interrupt-ID, Payload und LangGraph-Metadaten direkt aus dem echten Interruptobjekt. `ag-ui-langgraph` bleibt eine verlinkte Produktionsreferenz, nicht die hier ausgeführte Übersetzung.

Roh-Chunks werden vor der Übergabe an den Browser JSON-sicher konvertiert und auf 4.000 Zeichen begrenzt. Der Translator ist damit wiederverwendbar für die Dojo-Workflows, aber ausdrücklich kein universeller Ersatz für den offiziellen Adapter.

## HITL-Lauf

```text
Run A
  Tool-Vorschlag
  → LangGraph interrupt(...)
  → Checkpoint im InMemorySaver
  → __interrupt__-Chunk
  → AG-UI interrupt outcome

Run B
  RunAgentInput.resume[]
  → status, Payload-Typ und exakter Boolean werden validiert
  → Interrupt-ID wird gegen den offenen Checkpoint geprüft
  → Command(resume=True|False)
  → pausierte LangGraph-Ausführung wird fortgesetzt
  → Tool läuft nur bei True
  → TOOL_CALL_RESULT
  → success outcome
```

Ein prozesslokales Async-Gate serialisiert initiale und fortgesetzte Runs pro Workflow/Thread. Dadurch kann derselbe Interrupt bei zwei gleichzeitigen Requests in diesem Ein-Prozess-Lab nur einmal konsumiert werden; der zweite Request erhält `RUN_ERROR`. Die Gates werden entfernt, sobald keine laufenden oder wartenden Requests mehr existieren.

`InMemorySaver` ist ausschließlich für das lokale Ein-Prozess-Lern-Lab geeignet. Er behält Checkpoints für die Lebensdauer des Prozesses und implementiert hier keine fachliche Retention oder Bereinigung. Bei Neustart gehen offene Interrupts verloren. Mehrere Worker/Prozesse würden außerdem eine dauerhafte gemeinsame Checkpoint-Ablage mit atomarem Resume-Claim beziehungsweise idempotenter Tool-Ausführung benötigen.
