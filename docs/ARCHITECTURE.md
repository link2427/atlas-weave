# SwarmForge — Architecture

## 1. System Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        SwarmForge UI                             │
│                   SvelteKit + TypeScript + Tailwind              │
│                                                                  │
│  ┌──────────┐  ┌──────────────┐  ┌───────────┐  ┌───────────┐  │
│  │  Recipe   │  │  DAG Viewer  │  │   Data    │  │   Run     │  │
│  │  Browser  │  │  (live node  │  │  Inspector│  │  History  │  │
│  │          │  │   execution) │  │  (tables) │  │  & Logs   │  │
│  └──────────┘  └──────────────┘  └───────────┘  └───────────┘  │
└───────────────────────┬─────────────────────────────────────────┘
                        │
                   Tauri invoke / events
                   (commands + real-time streaming)
                        │
┌───────────────────────▼─────────────────────────────────────────┐
│                     Rust Core (Tauri Shell)                       │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────┐    │
│  │  Run Manager  │  │  Scheduler   │  │  Recipe Registry   │    │
│  │  (lifecycle,  │  │  (cron-based │  │  (discover, load,  │    │
│  │   state,      │  │   triggers)  │  │   validate recipes)│    │
│  │   persistence)│  └──────────────┘  └────────────────────┘    │
│  └──────┬───────┘                                                │
│         │         ┌──────────────┐  ┌────────────────────┐      │
│         │         │  Event Bus   │  │  Data Store        │      │
│         │         │  (Rust→UI    │  │  (SQLite for runs, │      │
│         │         │   streaming) │  │   logs, artifacts)  │      │
│         │         └──────────────┘  └────────────────────┘      │
└─────────┼───────────────────────────────────────────────────────┘
          │
     subprocess management
     (stdin/stdout JSON protocol)
          │
┌─────────▼───────────────────────────────────────────────────────┐
│                    Python Sidecar                                 │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────┐    │
│  │  Agent       │  │  Tool        │  │  LLM Integration   │    │
│  │  Runtime     │  │  Registry    │  │  (LangChain,       │    │
│  │  (execute    │  │  (API clients│  │   Claude API,      │    │
│  │   agents,    │  │   web search │  │   tool use)        │    │
│  │   manage     │  │   scrapers,  │  │                    │    │
│  │   state)     │  │   LLM calls) │  │                    │    │
│  └──────────────┘  └──────────────┘  └────────────────────┘    │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Recipe Packages (Python modules)                         │   │
│  │  - satellite-enrichment/                                  │   │
│  │  - (future recipes)                                       │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. Layer Boundaries

### UI Layer (SvelteKit)
- **MAY**: Render DAG visualization, display logs, show data tables, manage run configuration
- **MUST NOT**: Communicate with Python directly. All data flows through Rust via Tauri invoke/events.

### Rust Core (Tauri Shell)
- **MAY**: Manage Python subprocess lifecycle, route events from Python to UI, persist run data to SQLite, trigger scheduled runs, discover recipes
- **MUST NOT**: Execute agent logic. All agent execution happens in Python.

### Python Sidecar
- **MAY**: Execute agents, call APIs, run LLM queries, produce output databases, emit events
- **MUST NOT**: Access the Tauri UI or Rust state directly. Communication is exclusively via stdin/stdout JSON.

---

## 3. Rust ↔ Python Communication Protocol

### Rust → Python (stdin)

```json
{"type": "start_run", "run_id": "uuid", "recipe": "satellite-enrichment", "config": {...}}
{"type": "cancel_run", "run_id": "uuid"}
{"type": "get_status", "run_id": "uuid"}
```

### Python → Rust (stdout)

#### Node Lifecycle Events
```json
{"type": "node_started", "run_id": "uuid", "node_id": "collector", "timestamp": "iso8601"}
{"type": "node_progress", "run_id": "uuid", "node_id": "collector", "progress": 0.45, "message": "Fetched 22/48 categories"}
{"type": "node_completed", "run_id": "uuid", "node_id": "collector", "duration_ms": 45000, "summary": {"records_processed": 8432}}
{"type": "node_failed", "run_id": "uuid", "node_id": "collector", "error": "Space-Track returned 429"}
```

#### Log Events
```json
{"type": "node_log", "run_id": "uuid", "node_id": "collector", "level": "info", "message": "Fetched Space Stations (342 satellites)"}
```

#### Data Events
```json
{"type": "node_data", "run_id": "uuid", "node_id": "collector", "key": "satellites_fetched", "value": 8432}
```

#### Tool Call Events
```json
{"type": "tool_call", "run_id": "uuid", "node_id": "researcher", "tool": "web_search", "input": "ISS satellite specifications", "request_id": "uuid"}
{"type": "tool_result", "run_id": "uuid", "node_id": "researcher", "tool": "web_search", "request_id": "uuid", "output": "...", "duration_ms": 1200}
```

#### LLM Call Events
```json
{"type": "llm_call", "run_id": "uuid", "node_id": "researcher", "model": "claude-sonnet-4-20250514", "prompt_tokens": 1500, "request_id": "uuid"}
{"type": "llm_result", "run_id": "uuid", "node_id": "researcher", "request_id": "uuid", "completion_tokens": 450, "duration_ms": 2300}
```

#### Run Lifecycle Events
```json
{"type": "run_completed", "run_id": "uuid", "summary": {"total_records": 10432, "enriched": 8901, "completeness_avg": 0.72}}
{"type": "run_failed", "run_id": "uuid", "error": "..."}
```

---

## 4. Real-Time Event Flow

```
Python agent emits event
    → stdout JSON line
    → Rust sidecar.rs reads line via tokio::io::BufReader
    → Rust persists to run_events table (async SQLite write)
    → Rust emits Tauri event ("swarm:event", payload)
    → Frontend events store receives via listen()
    → DAG viewer reactively updates node visuals
    → Log viewer appends entry
    → Node detail panel updates metrics
```

Latency target: <50ms from Python emission to UI render.

---

## 5. SQLite Schema (SwarmForge Internal)

This database stores run history, logs, and events. It does NOT store recipe output data — each recipe manages its own output database.

```sql
CREATE TABLE recipes (
    name            TEXT PRIMARY KEY,
    description     TEXT,
    version         TEXT,
    path            TEXT NOT NULL,
    config_schema   TEXT,                -- JSON schema
    dag_json        TEXT,                -- Serialized DAG (nodes + edges)
    discovered_at   TEXT NOT NULL
);

CREATE TABLE runs (
    id              TEXT PRIMARY KEY,    -- UUID
    recipe_name     TEXT NOT NULL REFERENCES recipes(name),
    config_json     TEXT,                -- Config used (secrets redacted)
    status          TEXT NOT NULL DEFAULT 'pending',
    started_at      TEXT,
    completed_at    TEXT,
    summary_json    TEXT,
    error           TEXT
);
CREATE INDEX idx_runs_recipe ON runs(recipe_name);
CREATE INDEX idx_runs_status ON runs(status);

CREATE TABLE run_nodes (
    run_id          TEXT NOT NULL REFERENCES runs(id),
    node_id         TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending',
    progress        REAL DEFAULT 0,
    message         TEXT,
    started_at      TEXT,
    completed_at    TEXT,
    duration_ms     INTEGER,
    summary_json    TEXT,
    error           TEXT,
    PRIMARY KEY (run_id, node_id)
);

CREATE TABLE run_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          TEXT NOT NULL REFERENCES runs(id),
    node_id         TEXT,
    event_type      TEXT NOT NULL,
    timestamp       TEXT NOT NULL,
    payload_json    TEXT NOT NULL
);
CREATE INDEX idx_events_run ON run_events(run_id);
CREATE INDEX idx_events_run_node ON run_events(run_id, node_id);

CREATE TABLE schedules (
    id              TEXT PRIMARY KEY,
    recipe_name     TEXT NOT NULL REFERENCES recipes(name),
    cron_expression TEXT NOT NULL,
    config_json     TEXT,
    enabled         INTEGER NOT NULL DEFAULT 1,
    last_run_id     TEXT REFERENCES runs(id),
    next_run_at     TEXT,
    created_at      TEXT NOT NULL
);
```

---

## 6. UI Design

### 6.1 Main Layout

```
┌──────────────────────────────────────────────────────────────┐
│  SwarmForge                                    [Settings] [?] │
├────────┬─────────────────────────────────────────────────────┤
│        │                                                      │
│ Recipe │              DAG Viewer (main area)                   │
│ List   │                                                      │
│        │    ┌─────┐     ┌─────┐     ┌─────┐                 │
│ ● Sat  │    │ Col │────▶│ Mer │────▶│ Aud │                 │
│   Enr. │    │lect │     │ger  │     │itor │                 │
│        │    └─────┘     └──┬──┘     └─────┘                 │
│ ○ (add │                   │                                  │
│   new) │              ┌────▼────┐                             │
│        │              │Research │                             │
│        │              │  er     │                             │
│        │              └─────────┘                             │
│        │                                                      │
├────────┼──────────────────────────────────┬───────────────────┤
│        │         Node Detail Panel        │    Run Log        │
│ Run    │  ┌─────────────────────────┐    │    Stream         │
│ Hist.  │  │ Collector               │    │                   │
│        │  │ Status: Running (45%)   │    │ 14:32:01 [INFO]  │
│ #1 ✓   │  │ Fetched: 22/48 cats     │    │ Fetched NOAA     │
│ #2 ✓   │  │ Satellites: 5,432       │    │ (14 satellites)  │
│ #3 ●   │  │ Errors: 0               │    │                   │
│        │  │ Duration: 0:45          │    │ 14:32:02 [INFO]  │
│        │  │                         │    │ Fetched GOES     │
│        │  │ [View Data] [View Logs] │    │ (19 satellites)  │
│        │  └─────────────────────────┘    │                   │
└────────┴──────────────────────────────────┴───────────────────┘
```

### 6.2 DAG Viewer — Visual States

**Node states:**

| State | Visual | Animation |
|-------|--------|-----------|
| Pending | Gray circle, dashed border | None |
| Queued | Blue circle, solid border | Subtle pulse |
| Running | Green circle, glowing border | Spinning progress ring |
| Completed | Green filled circle, checkmark | Brief flash |
| Failed | Red filled circle, X mark | Shake |
| Skipped | Gray filled circle, skip icon | None |

**Edge states:**

| State | Visual |
|-------|--------|
| Inactive | Gray dashed line |
| Data flowing | Animated blue dots moving along the edge |
| Completed | Solid green line |
| Error propagation | Red line |

**Node interaction:**
- Hover: show tooltip with name, status, progress
- Click: open detail panel (summary, data, logs, tools tabs)
- Layout: dagre/ELK.js layered graph algorithm, recomputed only when recipe changes

### 6.3 Node Detail Panel Tabs

**Summary**: Status, progress bar, duration, key metrics (records in/out, errors, LLM calls, tokens used), config parameters.

**Data**: Paginated table of agent output data, column sorting/filtering, export to CSV.

**Logs**: Scrollable log stream (xterm.js style), color-coded by level, clickable tool/LLM calls expand to show full request/response.

**Tools**: Every tool call listed — HTTP requests (method, URL, status, duration), LLM calls (model, tokens, duration, cost estimate), web searches (query, results count).

### 6.4 Data Inspector

Full-screen data browser for recipe output databases:
- Table view with all columns, sortable/filterable
- Record detail view (click row to see all fields)
- Coverage dashboard: bar charts showing field completion rates
- Quality metrics: enrichment confidence distribution, data source breakdown
- Export to CSV

---

## 7. Python Agent Framework

### 7.1 Base Classes

```python
class AgentContext:
    """Passed to every agent — provides tools, config, and event emission."""
    run_id: str
    config: dict
    db: DatabaseConnection
    tools: ToolRegistry
    emit: EventEmitter

class AgentResult(BaseModel):
    records_processed: int = 0
    records_created: int = 0
    records_updated: int = 0
    errors: int = 0
    summary: dict = {}

class Agent(ABC):
    name: str
    description: str
    inputs: list[str] = []
    outputs: list[str] = []

    @abstractmethod
    async def execute(self, ctx: AgentContext) -> AgentResult:
        ...
```

### 7.2 Tool Interface

```python
class Tool(ABC):
    name: str
    description: str

    @abstractmethod
    async def call(self, ctx: AgentContext, **kwargs) -> Any:
        ...

class HttpTool(Tool):
    """Wraps httpx — auto-emits events for every request."""

class LLMTool(Tool):
    """Wraps Claude API — auto-tracks tokens and cost."""

class WebSearchTool(Tool):
    """Web search with result caching."""

class WebScrapeTool(Tool):
    """HTML scraping with BeautifulSoup — auto-emits events."""

class SQLiteTool(Tool):
    """Database access for recipe output DB."""
```

### 7.3 Recipe Definition

```python
class SatelliteEnrichmentRecipe(Recipe):
    name = "satellite-enrichment"
    description = "Comprehensive satellite metadata enrichment pipeline"
    version = "1.0.0"

    agents = [StructuredDataCollector, RecordMerger, LLMResearcher, QualityAuditor]

    edges = [
        ("collector", "merger"),
        ("merger", "researcher"),
        ("merger", "auditor"),
        ("researcher", "auditor"),
    ]

    config_schema = {
        "spacetrack_username": {"type": "string", "required": True, "secret": True},
        "spacetrack_password": {"type": "string", "required": True, "secret": True},
        "claude_api_key": {"type": "string", "required": True, "secret": True},
        "llm_confidence_threshold": {"type": "float", "default": 0.7},
        ...
    }
```

### 7.4 Event Emission Pattern

```python
async def execute(self, ctx: AgentContext) -> AgentResult:
    for i, (name, url) in enumerate(categories):
        ctx.emit.progress(progress=(i + 1) / len(categories), message=f"Fetching {name}")
        ctx.emit.log("info", f"Fetching category: {name}")
        response = await ctx.tools.http.get(ctx, url)
        satellites = parse_tle_response(response.text, category=name)
        ctx.emit.data("category_result", {"category": name, "count": len(satellites)})
        await upsert_satellites(ctx.db, satellites)
    return AgentResult(records_processed=total)
```

---

## 8. Key Implementation Details

### 8.1 Python Sidecar Lifecycle

1. On app startup, Rust checks for Python and the virtual environment
2. If venv missing, prompt user to run setup (or auto-create)
3. When a run triggers: `python -m swarmforge.runner --recipe {name} --run-id {uuid}`
4. Rust reads stdout line-by-line, parsing JSON events
5. Rust sends commands via stdin
6. On process exit, check exit code, mark run completed/failed
7. Multiple runs can execute concurrently (separate Python processes)

### 8.2 DAG Execution

The Python runner topologically sorts the DAG and executes agents in dependency order:
1. Parse recipe's `agents` and `edges`
2. Topological sort → execution order
3. For each agent with all dependencies satisfied → execute
4. Agents with no dependency between them can run concurrently (async)
5. If an agent fails, downstream dependents are skipped

### 8.3 Recipe Discovery

Rust scans `python/recipes/` on startup:
1. For each subdirectory with `recipe.py`
2. Spawns Python to import and serialize metadata (name, agents, edges, config_schema)
3. Stores in `recipes` table
4. UI renders recipe list

### 8.4 Credential Storage

API keys stored in Tauri's encrypted store plugin. Passed to Python sidecar as environment variables at spawn time — never written to disk in plaintext, never in run config JSON.

### 8.5 Recipe Output Databases

Each recipe manages its own SQLite database (path defined in recipe config). SwarmForge reads it in read-only mode for the Data Inspector. The schema is defined by the recipe's `schema.py`, not by SwarmForge.
