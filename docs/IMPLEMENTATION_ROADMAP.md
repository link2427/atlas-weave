# Atlas Weave — Implementation Roadmap

## Phase 1 — Skeleton

### Goal
Tauri v2 + SvelteKit app running, Python project structure created, Rust ↔ Python JSON protocol working end-to-end. Basic UI shows a recipe list and a "Start Run" button that launches Python and streams raw log output.

### Checklist

- [x] Create monorepo root with `Cargo.toml` workspace, `package.json`, `.gitignore`
- [x] Initialize Tauri v2 app in `apps/atlas-weave-shell/`
- [x] Initialize SvelteKit in `frontend/app/` with TypeScript, adapter-static, TailwindCSS
- [x] Configure `tauri.conf.json`: app name "Atlas Weave", window size 1400x900
- [x] Create `apps/atlas-weave-shell/src-tauri/src/db.rs`: SQLite init with schema from ARCHITECTURE.md Section 5
- [x] Create Python project in `python/` with `pyproject.toml` and `atlas_weave/` package
- [x] Implement `atlas_weave/events.py`: `EventEmitter` class that writes JSON lines to stdout
- [x] Implement `atlas_weave/runner.py`: reads `--recipe` and `--run-id` args, imports recipe, emits `run_completed` event (stub — no real execution yet)
- [x] Implement `services/sidecar.rs`: spawn Python process (`python -m atlas_weave.runner --recipe {name} --run-id {uuid}`), read stdout line-by-line, parse JSON, emit Tauri events
- [x] Implement `commands/runs.rs`: `start_run` command that triggers sidecar
- [x] Create a test recipe (`python/recipes/test_echo/recipe.py`) with one agent that emits 10 log messages with 1-second delays
- [x] Create basic frontend: recipe list page, "Start Run" button, raw scrolling log output from Tauri event listener
- [x] Verify: click Start Run → Python spawns → logs stream into UI in real time

### Acceptance Criteria
1. `cargo tauri dev` launches the app
2. Clicking "Start Run" spawns a Python process
3. Python events appear in the UI within 100ms of emission
4. Test recipe runs to completion and UI shows "completed" status
5. SQLite database has a run record with events persisted

---

## Phase 2 — Agent Framework

### Goal
The Python `atlas_weave` library has a complete agent framework: Agent, Recipe, Tool, AgentContext base classes. The DAG runner topologically sorts and executes agents. A test recipe with 2+ agents demonstrates dependency ordering.

### Checklist

- [x] Implement `atlas_weave/agent.py`: `Agent` abstract base class with `name`, `description`, `inputs`, `outputs`, `execute(ctx) -> AgentResult`
- [x] Implement `atlas_weave/agent.py`: `AgentResult` Pydantic model (records_processed, records_created, records_updated, errors, summary)
- [x] Implement `atlas_weave/context.py`: `AgentContext` with `run_id`, `config`, `db`, `tools`, `emit`
- [x] Implement `atlas_weave/recipe.py`: `Recipe` base class with `name`, `description`, `version`, `agents`, `edges`, `config_schema`
- [x] Implement `atlas_weave/tool.py`: `Tool` abstract base class with `name`, `description`, `call(ctx, **kwargs)`
- [x] Implement `atlas_weave/dag.py`: topological sort of agents from `edges`, detect cycles, determine execution order, identify parallelizable agents
- [x] Update `atlas_weave/runner.py`: import recipe → build DAG → execute agents in order → emit `node_started`/`node_progress`/`node_completed`/`node_failed` events per agent → emit `run_completed`/`run_failed`
- [x] Handle agent failures: if agent fails, mark downstream dependents as `skipped`
- [x] Create test recipe with 3 agents: A → B → C, where A produces data, B transforms it, C validates it
- [x] Verify: agents execute in correct order, events stream to Rust, failures propagate correctly

### Acceptance Criteria
1. Test recipe with A → B → C executes in order
2. Each agent's start/progress/completion events appear in UI
3. If B fails, C is automatically skipped
4. `AgentContext` provides config values from run configuration
5. `AgentResult` summary is included in `node_completed` event

---

## Phase 3 — DAG Viewer

### Goal
The centerpiece UI: a real-time DAG visualization where nodes light up, progress rings spin, edges animate with data flow, and clicking a node opens a detail panel.

### Checklist

#### 3A: DAG Rendering
- [ ] Install dagre (`@dagrejs/dagre`) or ELK.js for graph layout
- [ ] Create `frontend/app/src/lib/features/dag/dag-layout.ts`: takes recipe's agent list + edges, computes node positions and edge paths via dagre
- [ ] Create `DagViewer.svelte`: SVG canvas that renders the computed layout, handles zoom/pan
- [ ] Create `DagNode.svelte`: renders a single node — circle with label, color based on status, progress ring overlay
- [ ] Create `DagEdge.svelte`: renders edge between nodes — bezier curve, color based on state

#### 3B: Real-Time Updates
- [ ] Create `frontend/app/src/lib/stores/dag.ts`: reactive store that holds node statuses and progress, updated from Tauri event stream
- [ ] On `node_started` event → node transitions from `pending` to `running` with CSS animation
- [ ] On `node_progress` event → progress ring updates smoothly (CSS transition)
- [ ] On `node_completed` event → node transitions to `completed` with flash animation
- [ ] On `node_failed` event → node transitions to `failed` with shake animation
- [ ] Edges animate with flowing blue dots when data passes between connected nodes (triggered on upstream `node_completed`)

#### 3C: Node Interaction
- [ ] Click node → open `NodeDetail.svelte` panel below the DAG
- [ ] `NodeDetail.svelte`: tabbed panel with Summary, Logs, Tools, Data tabs
- [ ] `NodeSummary.svelte`: status badge, progress bar, duration, key metrics from `node_completed` summary
- [ ] `NodeLogs.svelte`: scrollable log viewer filtered to this node's events, color-coded by level
- [ ] Hover node → tooltip with name, status, progress message

#### 3D: Route Integration
- [ ] Create `frontend/app/src/routes/run/[id]/+page.svelte`: loads run data, renders DagViewer + NodeDetail + LogViewer
- [ ] Wire "Start Run" button to navigate to `/run/{new_run_id}` after starting

### Acceptance Criteria
1. DAG renders with correct layout (nodes positioned, edges routed)
2. Nodes transition through visual states in real time as events stream in
3. Progress rings animate smoothly during agent execution
4. Clicking a node shows its detail panel with correct data
5. Edge animations trigger when data flows between agents
6. Running the test recipe shows the full visual lifecycle from pending → running → completed

---

## Phase 4 — Run Management

### Goal
Full run lifecycle: persist runs to SQLite, browse run history, load historical runs into the DAG viewer, configure runs before launch, cancel running runs.

### Checklist

- [ ] Implement `commands/runs.rs`: `get_run_history` — paginated list of past runs for a recipe
- [ ] Implement `commands/runs.rs`: `get_run` — full run detail including all node statuses
- [ ] Implement `commands/runs.rs`: `get_run_events` — paginated events for a run, filterable by node
- [ ] Implement `commands/runs.rs`: `cancel_run` — sends cancel command to Python via stdin, marks run as cancelled
- [ ] Implement `services/event_bus.rs`: persist every Python event to `run_events` table, update `run_nodes` status
- [ ] Create `RunList.svelte`: sidebar showing past runs with status icon, timestamp, quick stats
- [ ] Click historical run → load its node states and events into DAG viewer (replay mode)
- [ ] Create `RunConfig.svelte`: before launching, show config form generated from recipe's `config_schema`
- [ ] Implement `commands/settings.rs`: `get_credentials`, `save_credentials` — encrypted Tauri store
- [ ] Create `Credentials.svelte`: API key management (Space-Track, Claude, DISCOS, etc.)
- [ ] Credential values injected as env vars when Python spawns (never in config JSON)

### Acceptance Criteria
1. Run history sidebar shows past runs with correct status icons
2. Clicking a historical run loads the DAG with that run's final node states
3. Run config panel lets you set parameters before launch
4. Cancel button sends cancel signal and run stops
5. API keys persist across app restarts (encrypted store)
6. Credentials are passed as env vars to Python, never in logs or config JSON

---

## Phase 5 — Built-in Tools

### Goal
The Python framework includes production-ready built-in tools that auto-emit events. Every HTTP request, LLM call, web search, and scrape shows up in the UI with timing and cost.

### Checklist

- [ ] Implement `tools/http_tool.py`: `HttpTool` wrapping httpx — emits `tool_call` on every request (method, URL), emits `tool_result` with status code, duration, response size
- [ ] Implement `tools/llm_tool.py`: `LLMTool` wrapping Claude API — emits `llm_call` (model, prompt_tokens), emits `llm_result` (completion_tokens, duration, estimated cost). Supports structured output via tool_use.
- [ ] Implement `tools/web_search_tool.py`: `WebSearchTool` — emits events, caches results by query with configurable TTL (default 7 days)
- [ ] Implement `tools/web_scrape_tool.py`: `WebScrapeTool` using BeautifulSoup — fetches URL via HttpTool (gets event emission for free), parses HTML, returns text/structured data
- [ ] Implement `tools/sqlite_tool.py`: `SQLiteTool` — wraps SQLite access for recipe output databases, provides `execute`, `fetch_all`, `fetch_one`, `upsert` helpers
- [ ] Update `NodeTools.svelte`: renders list of all tool calls for a node, expandable to show full request/response
- [ ] Add LLM cost estimation: model pricing table, compute cost from token counts, show cumulative cost per run
- [ ] Write tests for each tool (mock HTTP responses, verify event emission format)

### Acceptance Criteria
1. HttpTool emits events for every request — visible in NodeTools panel
2. LLMTool tracks tokens and shows estimated cost
3. WebSearchTool caches results and skips duplicate queries
4. All tool events appear in the Tools tab of node detail
5. Cumulative LLM cost shown in run summary

---

## Phase 6 — Satellite Enrichment Recipe

### Goal
The first real recipe: the Cosmotrak satellite enrichment pipeline. 4 agents, pulling from Space-Track/CelesTrak/DISCOS/UCS, merging, LLM gap-filling, and validating. Produces a SQLite database that the Cosmotrak API can consume.

### Checklist

#### 6A: Output Schema
- [ ] Implement `recipes/satellite_enrichment/schema.py`: Pydantic models for the enriched satellite with 50+ fields (identity, ownership, mission, orbit, physical, launch, contractor, visual, metadata)
- [ ] Define SQLite output schema matching the Cosmotrak API's expectations

#### 6B: StructuredDataCollector Agent
- [ ] Implement Space-Track SATCAT fetcher (requires auth — username/password from config)
- [ ] Implement Space-Track GP data fetcher (live orbital parameters)
- [ ] Implement CelesTrak SATCAT fetcher (48 categories)
- [ ] Implement ESA DISCOS fetcher (paginated, requires auth token)
- [ ] Store raw data in staging tables in the output DB
- [ ] Emit progress per source (e.g., "Fetching CelesTrak: 22/48 categories")
- [ ] Rate limit handling: 200ms between CelesTrak requests, batch Space-Track queries, handle 429s

#### 6C: RecordMerger Agent
- [ ] For each NORAD ID in Space-Track SATCAT: look up in CelesTrak, DISCOS, UCS data
- [ ] Merge fields using priority: Space-Track > DISCOS > UCS > derived
- [ ] Derive orbit_class from altitude (LEO <2000km, MEO 2000-35786km, GEO ~35786km)
- [ ] Derive constellation_name from Celestrak category or name patterns
- [ ] Compute `data_completeness_pct` per record
- [ ] Flag records with completeness < threshold (default 0.5) for LLM research
- [ ] Emit progress and key metrics (total merged, completeness distribution)

#### 6D: LLMResearcher Agent
- [ ] For each low-completeness satellite: search web for specs, operator, purpose
- [ ] Use Claude to extract structured data from search results (JSON output)
- [ ] Validate extracted data (mass ranges, country codes, lifetime bounds)
- [ ] Only merge results with confidence > threshold (default 0.7)
- [ ] Cache search results (7-day TTL)
- [ ] Emit progress per satellite researched, log LLM extractions

#### 6E: QualityAuditor Agent
- [ ] Validate: NORAD IDs unique, orbital parameters plausible, dates valid, countries valid
- [ ] Compute final `data_completeness_pct` and `enrichment_confidence` per record
- [ ] Generate summary: total records, coverage stats, field completion rates, source breakdown
- [ ] Flag anomalies (emit as warnings)

#### 6F: Integration Test
- [ ] Run full pipeline end-to-end
- [ ] Verify output DB has 10,000+ records with TLEs and enrichment
- [ ] Verify coverage targets: ≥80% with operator+purpose, ≥70% with mass data
- [ ] Verify Cosmotrak API can read the output DB

### Acceptance Criteria
1. Full pipeline runs to completion in the Atlas Weave UI
2. DAG shows all 4 agents executing with real progress
3. Output SQLite has 10,000+ satellite records
4. ≥80% of records have operator + purpose populated
5. LLM researcher fills gaps for low-completeness records
6. Quality auditor summary matches validation criteria
7. Output DB schema matches Cosmotrak API expectations

---

## Phase 7 — Data Inspector

### Goal
A full-screen data browser for inspecting recipe output databases. Browse records, sort/filter, view details, see coverage stats.

### Checklist

- [ ] Implement `commands/data.rs`: `query_recipe_db` — opens recipe output DB in read-only mode, executes paginated queries with sort/filter params
- [ ] Create `DataBrowser.svelte`: full-screen view with table + sidebar
- [ ] Create `DataTable.svelte`: paginated table with column sorting, text search, column filtering
- [ ] Create `RecordDetail.svelte`: click a row to see all fields for one record in a formatted view
- [ ] Create `CoverageDashboard.svelte`: bar charts showing field completion rates across all records
- [ ] Add export to CSV button
- [ ] Create `/data/[recipe]/+page.svelte` route
- [ ] Add "View Data" link in recipe list and run summary

### Acceptance Criteria
1. Data inspector opens and displays satellite enrichment output
2. Table supports sorting, filtering, and text search
3. Clicking a record shows all 50+ fields
4. Coverage dashboard shows accurate field completion percentages
5. CSV export produces valid file

---

## Phase 8 — Scheduling

### Goal
Recipes can be scheduled to run on a cron interval. The scheduler triggers runs automatically and prevents overlapping executions.

### Checklist

- [ ] Implement `services/scheduler.rs`: reads schedules from SQLite, computes next run times, triggers `start_run` when due
- [ ] Implement run deduplication: if a run for the same recipe is already in `running` status, skip
- [ ] Implement `commands/schedules.rs`: `create_schedule`, `update_schedule`, `delete_schedule`, `get_schedules`
- [ ] Create `ScheduleManager.svelte`: list schedules, create/edit with cron expression, toggle enabled/disabled
- [ ] Show next scheduled run time in recipe list
- [ ] Scheduler starts on app launch, persists across restarts

### Acceptance Criteria
1. Creating a schedule with "0 */6 * * *" triggers a run every 6 hours
2. If a run is already in progress, the scheduled trigger is skipped
3. Schedules persist across app restarts
4. Disabling a schedule stops future triggers
5. UI shows next scheduled run time

---

## Phase 9 — Polish

### Goal
Final polish: cost tracking, dark/light theme, notifications, error recovery, and UX refinements.

### Checklist

- [ ] Add cumulative cost tracking per run (LLM token costs, displayed in run summary)
- [ ] Implement dark/light theme toggle (Tailwind dark mode)
- [ ] Desktop notifications on run completion/failure via Tauri notification plugin
- [ ] Error recovery: "Retry Failed Nodes" button that re-runs only failed/skipped agents from a completed run
- [ ] Node detail tools tab: expandable HTTP/LLM call details with full request/response
- [ ] Improve DAG viewer: mini-map for large DAGs, zoom controls, auto-fit on recipe load
- [ ] Loading states for all async operations
- [ ] Empty states for first-launch experience (no runs yet, no recipes configured)
- [ ] Keyboard shortcuts: `Ctrl+R` to start run, `Escape` to close panels

### Acceptance Criteria
1. Cost tracking shows estimated spend per run
2. Theme toggle works
3. Notification appears when a background scheduled run completes
4. Retry button re-runs only failed nodes
5. App feels polished on first launch

---

## Coding Standards

### Rust
- `cargo clippy -- -D warnings` must pass
- `cargo fmt --check` must pass
- All commands return `Result<T, AppError>`
- No `.unwrap()` in non-test code

### TypeScript
- `strict: true`
- No `any` types
- All Tauri invokes go through typed wrappers

### Python
- `ruff check` must pass
- Type hints on all public functions
- Pydantic models for all data contracts
- `async def` for all agent execute methods and tool calls
- Structured logging via `structlog` (feeds into JSON event protocol)

### Git
- Conventional commits: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`
- One logical change per commit
