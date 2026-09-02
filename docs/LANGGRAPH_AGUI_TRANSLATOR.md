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

Das Paket `ag-ui-langgraph` bietet zusätzlich einen umfangreichen offiziellen Adapter für `CompiledStateGraph`-Agenten. Dieses Lab verwendet daraus die offizielle Interrupt-Konvertierung `lg_interrupts_to_agui`, damit echte Interrupt-IDs und Metadaten korrekt erhalten bleiben. Den gesamten offiziellen Agent-Wrapper verwenden die Lektionen bewusst nicht: Er unterstützt die Graph API, während dieses Lab Graph API und Functional API mit derselben sichtbaren Übersetzungsgrenze vergleichen soll.

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
  → Command(resume=True|False)
  → pausierte LangGraph-Ausführung wird fortgesetzt
  → Tool läuft nur bei True
  → TOOL_CALL_RESULT
  → success outcome
```

`InMemorySaver` ist für das lokale Lern-Lab geeignet. Für mehrere Prozesse, Neustartfestigkeit oder Produktion wäre ein dauerhafter LangGraph-Checkpointer erforderlich.
