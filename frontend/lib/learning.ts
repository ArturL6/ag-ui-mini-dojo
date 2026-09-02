export type Lesson = {
  id: string;
  number: string;
  title: string;
  subtitle: string;
  goal: string;
  prompt: string;
  expectedEvents: string[];
  source: string;
  keyIdea: string;
  optional?: boolean;
  endpoint?: string;
  badge?: string;
};

export const lessons: Lesson[] = [
  {
    id: "lifecycle",
    number: "01",
    title: "Run Lifecycle",
    subtitle: "Wo ein Agentenlauf beginnt und endet",
    goal: "RUN_STARTED, Steps und RUN_FINISHED als äußeren Rahmen verstehen.",
    prompt: "Zeige mir den Lebenszyklus eines Agentenlaufs",
    expectedEvents: ["RUN_STARTED", "STEP_STARTED", "STEP_FINISHED", "RUN_FINISHED"],
    source: "backend/app/scenarios.py → lifecycle_scenario()",
    keyIdea: "Jeder erfolgreiche Lauf hat eine eindeutige Identität und ein terminales Ende.",
  },
  {
    id: "streaming",
    number: "02",
    title: "Text Streaming",
    subtitle: "Warum Start, Deltas und Ende getrennt sind",
    goal: "Mehrere TEXT_MESSAGE_CONTENT-Deltas anhand einer messageId zusammensetzen.",
    prompt: "Erkläre AG-UI in einem Satz",
    expectedEvents: ["TEXT_MESSAGE_START", "TEXT_MESSAGE_CONTENT", "TEXT_MESSAGE_END"],
    source: "backend/app/scenarios.py → text_events()",
    keyIdea: "Streaming macht eine Antwort sofort sichtbar, bevor sie vollständig erzeugt ist.",
  },
  {
    id: "tools",
    number: "03",
    title: "Tool Calls",
    subtitle: "Von gestreamten Argumenten zum Tool-Ergebnis",
    goal: "Tool-Name, Argument-Deltas, Ausführung und Resultat verfolgen.",
    prompt: "Erzeuge eine Lerncheckliste für AG-UI",
    expectedEvents: ["TOOL_CALL_START", "TOOL_CALL_ARGS", "TOOL_CALL_END", "TOOL_CALL_RESULT"],
    source: "backend/app/scenarios.py → tools_scenario()",
    keyIdea: "Tools verbinden Agentenentscheidungen mit strukturierter Anwendungslogik.",
  },
  {
    id: "state",
    number: "04",
    title: "Shared State",
    subtitle: "Snapshot plus sparsame JSON-Patch-Deltas",
    goal: "Vollständigen Zustand etablieren und inkrementell verändern.",
    prompt: "Synchronisiere den Fortschritt mit der Oberfläche",
    expectedEvents: ["STATE_SNAPSHOT", "STATE_DELTA"],
    source: "backend/app/scenarios.py → state_scenario()",
    keyIdea: "Snapshot schafft eine Basis; Deltas übertragen anschließend nur Änderungen.",
  },
  {
    id: "interrupt",
    number: "05",
    title: "Human in the Loop",
    subtitle: "Unterbrechen, freigeben und in einem neuen Run fortsetzen",
    goal: "Interrupt-Outcome und RunAgentInput.resume als zwei verbundene Runs sehen.",
    prompt: "Führe eine Aktion aus, aber frage mich vorher",
    expectedEvents: ["TOOL_CALL_START", "STATE_SNAPSHOT", "RUN_FINISHED", "TOOL_CALL_RESULT"],
    source: "backend/app/scenarios.py → interrupt_scenario()",
    keyIdea: "Eine Freigabe setzt nicht denselben HTTP-Stream fort, sondern startet einen neuen Run.",
  },
  {
    id: "error",
    number: "06",
    title: "Error Path",
    subtitle: "Fehler als sichtbares terminales Protokollereignis",
    goal: "RUN_ERROR von Transportfehlern und erfolgreichen Abschlüssen unterscheiden.",
    prompt: "Erzeuge absichtlich einen Lernfehler",
    expectedEvents: ["RUN_STARTED", "RUN_ERROR"],
    source: "backend/app/scenarios.py → error_scenario()",
    keyIdea: "RUN_ERROR beendet einen Lauf sichtbar; danach dürfen keine normalen Events folgen.",
  },
  {
    id: "llm",
    number: "07",
    title: "Real LLM Stream",
    subtitle: "Dieselbe Transportstrecke mit OpenAI",
    goal: "Einen echten Provider-Stream in AG-UI-Text-Events übersetzen.",
    prompt: "Was ist der wichtigste Unterschied zwischen AG-UI und einer normalen Chat API?",
    expectedEvents: ["RUN_STARTED", "TEXT_MESSAGE_CONTENT", "RUN_FINISHED"],
    source: "backend/app/scenarios.py → llm_scenario()",
    keyIdea: "Der Provider ist austauschbar; die Oberfläche konsumiert weiterhin AG-UI-Events.",
    optional: true,
    badge: "KEY",
  },
  {
    id: "langgraph",
    number: "08",
    title: "LangGraph Flow",
    subtitle: "Echte Nodes und bedingte Kanten, separat adaptiert",
    goal: "LangGraph-State und Node-Updates unabhängig erzeugen und als AG-UI-Events beobachten.",
    prompt: "Erzeuge eine Checkliste mit einem Tool und zeige mir den Flow",
    expectedEvents: [
      "RUN_STARTED",
      "STATE_SNAPSHOT",
      "STEP_STARTED",
      "STATE_DELTA",
      "TEXT_MESSAGE_CONTENT",
      "RUN_FINISHED",
    ],
    source: "backend/app/langgraph_flow.py → run_langgraph_flow()",
    keyIdea: "LangGraph orchestriert den Flow; ein separater Adapter übersetzt Node-Updates in AG-UI.",
    endpoint: "/api/langgraph",
    badge: "GRAPH",
  },
  {
    id: "langgraph-functional",
    number: "09",
    title: "LangGraph Functional API",
    subtitle: "@entrypoint, @task und normale Python-Kontrolllogik",
    goal: "Echte Functional-API-Task-Streams empfangen und transparent in AG-UI übersetzen.",
    prompt: "Erzeuge eine Checkliste mit einem Tool über die Functional API",
    expectedEvents: [
      "RUN_STARTED",
      "STATE_SNAPSHOT",
      "STEP_STARTED",
      "STATE_DELTA",
      "TEXT_MESSAGE_CONTENT",
      "RUN_FINISHED",
    ],
    source: "backend/app/langgraph_functional_flow.py → run_functional_flow()",
    keyIdea: "Die AG-UI-Events werden aus echten custom/updates-Chunks des Functional-API-Runtimes erzeugt; die Zuordnung selbst ist unser Adapter.",
    endpoint: "/api/langgraph-functional",
    badge: "FUNC",
  },
];

export type EventExplanation = {
  label: string;
  emittedBy: string;
  consumedBy: string;
  why: string;
  changes: string;
  source: string;
};

const generic: EventExplanation = {
  label: "AG-UI Event",
  emittedBy: "Python-Agent",
  consumedBy: "HttpAgent Subscriber",
  why: "Strukturierte Information zwischen Agent und Oberfläche übertragen.",
  changes: "Abhängig vom konkreten Event.",
  source: "backend/app/scenarios.py",
};

export const eventExplanations: Record<string, EventExplanation> = {
  RUN_STARTED: {
    label: "Run startet",
    emittedBy: "FastAPI-Agent",
    consumedBy: "@ag-ui/client / onRunStartedEvent",
    why: "Eröffnet einen eindeutig identifizierbaren Agentenlauf.",
    changes: "Die UI kann Loading, Run-ID und Laufzeit initialisieren.",
    source: "backend/app/scenarios.py → *scenario()",
  },
  RUN_FINISHED: {
    label: "Run endet",
    emittedBy: "FastAPI-Agent",
    consumedBy: "@ag-ui/client / onRunFinishedEvent",
    why: "Markiert Erfolg oder einen Interrupt als terminales Ergebnis.",
    changes: "Die UI beendet Loading oder zeigt eine Freigabe an.",
    source: "backend/app/scenarios.py",
  },
  RUN_ERROR: {
    label: "Run fehlerhaft beendet",
    emittedBy: "FastAPI-Agent oder Provider-Adapter",
    consumedBy: "@ag-ui/client / onRunErrorEvent",
    why: "Macht Fehler als Teil des Protokolls sichtbar und maschinenlesbar.",
    changes: "Die UI wechselt in einen Fehlerzustand.",
    source: "backend/app/scenarios.py → error_scenario() / llm_scenario()",
  },
  STEP_STARTED: {
    label: "Arbeitsschritt startet",
    emittedBy: "Agenten-Workflow",
    consumedBy: "Timeline / Fortschrittsanzeige",
    why: "Lange Läufe werden in nachvollziehbare Phasen zerlegt.",
    changes: "Ein Teilschritt erscheint als aktiv.",
    source: "backend/app/scenarios.py",
  },
  STEP_FINISHED: {
    label: "Arbeitsschritt endet",
    emittedBy: "Agenten-Workflow",
    consumedBy: "Timeline / Fortschrittsanzeige",
    why: "Schließt den zuvor gestarteten, gleichnamigen Schritt.",
    changes: "Der Teilschritt kann als erledigt markiert werden.",
    source: "backend/app/scenarios.py",
  },
  TEXT_MESSAGE_START: {
    label: "Nachrichtenstream startet",
    emittedBy: "Agent oder LLM-Adapter",
    consumedBy: "@ag-ui/client Nachrichtenpuffer",
    why: "Legt messageId und Rolle fest, bevor Inhalt eintrifft.",
    changes: "Die UI kann eine leere Assistant-Sprechblase anlegen.",
    source: "backend/app/scenarios.py → text_events()",
  },
  TEXT_MESSAGE_CONTENT: {
    label: "Text-Delta",
    emittedBy: "Agent oder LLM-Adapter",
    consumedBy: "onTextMessageContentEvent",
    why: "Überträgt nur den neu erzeugten Textabschnitt.",
    changes: "Der Client hängt delta an den Puffer derselben messageId.",
    source: "backend/app/scenarios.py → text_events() / llm_scenario()",
  },
  TEXT_MESSAGE_END: {
    label: "Nachrichtenstream endet",
    emittedBy: "Agent oder LLM-Adapter",
    consumedBy: "@ag-ui/client Nachrichtenpuffer",
    why: "Signalisiert, dass für diese messageId keine weiteren Deltas folgen.",
    changes: "Die Nachricht kann final gerendert werden.",
    source: "backend/app/scenarios.py → text_events()",
  },
  TOOL_CALL_START: {
    label: "Tool-Aufruf startet",
    emittedBy: "Agent",
    consumedBy: "@ag-ui/client Tool-Puffer",
    why: "Legt toolCallId und Tool-Namen fest.",
    changes: "Die UI kann eine Tool-Aktivität anzeigen.",
    source: "backend/app/scenarios.py → tools_scenario()",
  },
  TOOL_CALL_ARGS: {
    label: "Tool-Argument-Delta",
    emittedBy: "Agent",
    consumedBy: "@ag-ui/client Tool-Puffer",
    why: "Auch umfangreiche JSON-Argumente können progressiv gestreamt werden.",
    changes: "Deltas werden bis zu gültigem JSON zusammengefügt.",
    source: "backend/app/scenarios.py → tools_scenario()",
  },
  TOOL_CALL_END: {
    label: "Tool-Aufruf vollständig beschrieben",
    emittedBy: "Agent",
    consumedBy: "Tool Executor oder UI",
    why: "Alle Argumente sind angekommen; das Tool kann ausgeführt werden.",
    changes: "Der Tool-Puffer wird finalisiert.",
    source: "backend/app/scenarios.py → tools_scenario()",
  },
  TOOL_CALL_RESULT: {
    label: "Tool-Ergebnis",
    emittedBy: "Tool Executor / Agent-Backend",
    consumedBy: "Nachrichtenhistorie und Agent",
    why: "Verknüpft das Ausführungsergebnis über toolCallId mit dem Aufruf.",
    changes: "Eine Tool-Nachricht wird Teil der Konversation.",
    source: "backend/app/scenarios.py → tools_scenario() / interrupt_scenario()",
  },
  STATE_SNAPSHOT: {
    label: "Vollständiger State",
    emittedBy: "Agent",
    consumedBy: "@ag-ui/client State Store",
    why: "Stellt einen vollständigen, bekannten Synchronisationspunkt her.",
    changes: "Der bisherige Client-State wird vollständig ersetzt.",
    source: "backend/app/scenarios.py → state_scenario()",
  },
  STATE_DELTA: {
    label: "Inkrementeller State Patch",
    emittedBy: "Agent",
    consumedBy: "@ag-ui/client State Store",
    why: "Überträgt kleine Änderungen effizient als RFC-6902 JSON Patch.",
    changes: "Die Patch-Operationen werden sequenziell auf den State angewandt.",
    source: "backend/app/scenarios.py → state_scenario()",
  },
};

export function explainEvent(type: string, sourceOverride?: string): EventExplanation {
  const explanation = eventExplanations[type] ?? { ...generic, label: type };
  return sourceOverride ? { ...explanation, source: sourceOverride } : explanation;
}
