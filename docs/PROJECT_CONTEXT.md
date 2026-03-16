# Atlas Weave — Project Context

## 1. What Is Atlas Weave

Atlas Weave is a **desktop agent swarm orchestrator** with a real-time execution visualizer. You define multi-agent research and data pipelines as Python code, and Atlas Weave provides the runtime, scheduling, data layer, and a polished UI that lets you watch your agents work through a live DAG visualization.

Think of it as a local-first Airflow for LLM-powered agent pipelines, with a UI that actually shows you what's happening in real time — nodes lighting up, logs streaming, data flowing between agents, progress bars filling.

The satellite enrichment pipeline for Cosmotrak is the first recipe built on Atlas Weave, but the framework is generic. Any multi-step research, data collection, or enrichment workflow can be defined as a Atlas Weave recipe.

---

## 2. Core Concepts

### Recipe
A self-contained Python package that defines a complete agent pipeline. Contains agents, a DAG (dependency graph), configuration schema, and an output data model. Recipes live as directories under `python/recipes/`. Adding a new recipe = drop a new Python package and restart the app.

### Agent
A Python class with a `name`, declared `inputs` (upstream dependencies), declared `outputs` (artifacts produced), `tools` (API clients, LLM, web search), and an `execute()` method. Agents emit structured events during execution that the UI renders in real time.

### Node
A single execution instance of an agent within a run. The DAG is made of nodes. Each node has a lifecycle: `pending` → `queued` → `running` → `completed` / `failed` / `skipped`.

### Run
A single execution of a recipe's DAG. Has a unique ID, start/end time, status of every node, all logs and events, and a final summary. Runs are persisted to SQLite so you can inspect any previous execution.

### Tool
A capability an agent can use — an HTTP client, a web scraper, an LLM call, a database query. Tools are Python classes with a standard interface. They automatically emit events (HTTP requests, LLM token usage, etc.) that show up in the UI without manual instrumentation.

---

## 3. Target Platforms

| Platform | Priority | Notes |
|----------|----------|-------|
| Windows  | P0       | Primary target |
| macOS    | P0       | Second target |
| Linux    | P1       | After desktop assumptions settle |

Mobile is not a target. This is a power-user desktop tool.

---

## 4. Technology Stack

### Frontend
- **SvelteKit** — app shell, SPA mode (SSR disabled)
- **TypeScript** — strict mode, all UI logic
- **TailwindCSS** — styling
- **D3.js or dagre/ELK.js** — DAG graph layout and rendering
- **xterm.js** — terminal-style log viewer
- **Svelte stores** — reactive state management

### Application Host
- **Tauri v2** — desktop runtime
- **Tauri plugins**: store (encrypted credential storage), notification, log

### Rust Core
- **tokio** — async runtime for subprocess management and event streaming
- **rusqlite** — SQLite for run history, logs, events
- **serde_json** — JSON message protocol with Python sidecar
- **tokio-cron-scheduler** or custom timer — scheduled run triggering

### Python Sidecar
- **Python 3.11+** — agent runtime
- **LangChain** — agent framework
- **LangGraph** — multi-agent orchestration and state machines
- **anthropic** / **langchain-anthropic** — Claude API integration
- **httpx** — async HTTP client
- **beautifulsoup4** — HTML parsing for web scraping
- **pydantic** — data validation and schema definition
- **structlog** — structured logging

---

## 5. Communication Model

Rust spawns the Python sidecar as a child process. They communicate over **stdin/stdout using newline-delimited JSON messages**.

- **Rust → Python (stdin)**: Commands like `start_run`, `cancel_run`, `get_status`
- **Python → Rust (stdout)**: Events like `node_started`, `node_progress`, `node_log`, `node_completed`, `tool_call`, `llm_call`, `run_completed`

Rust receives events, persists them to SQLite, and forwards them as Tauri events to the frontend. The UI reactively updates the DAG visualization, log viewer, and detail panels.

Latency target: <50ms from Python event emission to UI render.

---

## 6. Design Philosophy

1. **Code-first, UI for monitoring.** Recipes are Python code. The UI is an operations dashboard for launching, monitoring, and inspecting — not a no-code visual builder.
2. **Framework handles instrumentation.** Built-in tools (HttpTool, LLMTool, WebSearchTool) automatically emit events. You don't manually instrument your agents — every HTTP request, every LLM call, every web scrape shows up in the UI with timing and cost.
3. **Recipes are self-contained.** A recipe is a Python package with no dependency on the Rust shell or the UI. You can run a recipe from the command line without Atlas Weave for testing.
4. **Runs are reproducible.** Every run's config, events, and output are persisted. You can load any historical run and see exactly what happened.
5. **Local-first.** All data stays on your machine. API keys are stored in Tauri's encrypted store. No cloud dependency for the orchestration layer.

---

## 7. Non-Goals for V1

- Visual recipe builder / no-code editor
- Cloud deployment of the Atlas Weave app itself
- Multi-user collaboration
- Recipe marketplace or sharing
- Mobile support
- Running agents inside the Rust process (Python sidecar is the runtime)
- Distributed execution across multiple machines

---

## 8. First Recipe: Satellite Enrichment

The first recipe built on Atlas Weave is the Cosmotrak satellite enrichment pipeline. It has 4 agents:

1. **StructuredDataCollector** — fetches from Space-Track SATCAT, Space-Track GP, CelesTrak, ESA DISCOS
2. **RecordMerger** — cross-references all sources by NORAD ID, merges fields with priority ordering
3. **LLMResearcher** — for satellites with <50% field coverage, uses Claude to search the web and extract structured metadata
4. **QualityAuditor** — validates all records, computes completeness scores, generates coverage report

Output: a SQLite database with 50+ fields per satellite (vs UCS's 28), covering 95%+ of active satellites (vs UCS's ~7,000), updated every 6 hours (vs UCS's quarterly). This database feeds the Cosmotrak API.
