# Atlas Weave - Implementation Roadmap

## Phase 1 - Skeleton

### Goal
Tauri v2 + SvelteKit app running, Python project structure created, Rust <-> Python JSON protocol working end-to-end. Basic UI shows a recipe list and a "Start Run" button that launches Python and streams raw log output.

### Checklist

- [x] Create monorepo root with `Cargo.toml` workspace, `package.json`, `.gitignore`
- [x] Initialize Tauri v2 app in `apps/atlas-weave-shell/`
- [x] Initialize SvelteKit in `frontend/app/` with TypeScript, adapter-static, TailwindCSS
- [x] Configure `tauri.conf.json`: app name "Atlas Weave", window size 1400x900
- [x] Create `apps/atlas-weave-shell/src-tauri/src/db.rs`: SQLite init with schema from ARCHITECTURE.md Section 5
- [x] Create Python project in `python/` with `pyproject.toml` and `atlas_weave/` package
- [x] Implement `atlas_weave/events.py`: `EventEmitter` class that writes JSON lines to stdout
- [x] Implement `atlas_weave/runner.py`: reads `--recipe` and `--run-id` args, imports recipe, emits `run_completed` event (stub - no real execution yet)
- [x] Implement `services/sidecar.rs`: spawn Python process (`python -m atlas_weave.runner --recipe {name} --run-id {uuid}`), read stdout line-by-line, parse JSON, emit Tauri events
- [x] Implement `commands/runs.rs`: `start_run` command that triggers sidecar
- [x] Create a test recipe (`python/recipes/test_echo/recipe.py`) with one agent that emits 10 log messages with 1-second delays
- [x] Create basic frontend: recipe list page, "Start Run" button, raw scrolling log output from Tauri event listener
- [x] Verify: click Start Run -> Python spawns -> logs stream into UI in real time

### Acceptance Criteria
1. `cargo tauri dev` launches the app
2. Clicking "Start Run" spawns a Python process
3. Python events appear in the UI within 100ms of emission
4. Test recipe runs to completion and UI shows "completed" status
5. SQLite database has a run record with events persisted

---

## Phase 2 - Agent Framework

### Goal
The Python `atlas_weave` library has a complete agent framework: Agent, Recipe, Tool, AgentContext base classes. The DAG runner topologically sorts and executes agents. A test recipe with 2+ agents demonstrates dependency ordering.

### Checklist

- [x] Implement `atlas_weave/agent.py`: `Agent` abstract base class with `name`, `description`, `inputs`, `outputs`, `execute(ctx) -> AgentResult`
- [x] Implement `atlas_weave/agent.py`: `AgentResult` Pydantic model (records_processed, records_created, records_updated, errors, summary)
- [x] Implement `atlas_weave/context.py`: `AgentContext` with `run_id`, `config`, `db`, `tools`, `emit`
- [x] Implement `atlas_weave/recipe.py`: `Recipe` base class with `name`, `description`, `version`, `agents`, `edges`, `config_schema`
- [x] Implement `atlas_weave/tool.py`: `Tool` abstract base class with `name`, `description`, `call(ctx, **kwargs)`
- [x] Implement `atlas_weave/dag.py`: topological sort of agents from `edges`, detect cycles, determine execution order, identify parallelizable agents
- [x] Update `atlas_weave/runner.py`: import recipe -> build DAG -> execute agents in order -> emit `node_started`/`node_progress`/`node_completed`/`node_failed` events per agent -> emit `run_completed`/`run_failed`
- [x] Handle agent failures: if agent fails, mark downstream dependents as `skipped`
- [x] Create test recipe with 3 agents: A -> B -> C, where A produces data, B transforms it, C validates it
- [x] Verify: agents execute in correct order, events stream to Rust, failures propagate correctly

### Acceptance Criteria
1. Test recipe with A -> B -> C executes in order
2. Each agent's start/progress/completion events appear in UI
3. If B fails, C is automatically skipped
4. `AgentContext` provides config values from run configuration
5. `AgentResult` summary is included in `node_completed` event

---

## Phase 3 - DAG Viewer

### Goal
The centerpiece UI: a real-time DAG visualization where nodes light up, progress rings spin, edges animate with data flow, and clicking a node opens a detail panel.

### Checklist

#### 3A: DAG Rendering
- [x] Install dagre (`@dagrejs/dagre`) or ELK.js for graph layout
- [x] Create `frontend/app/src/lib/features/dag/dag-layout.ts`: takes recipe's agent list + edges, computes node positions and edge paths via dagre
- [x] Create `DagViewer.svelte`: SVG canvas that renders the computed layout, handles zoom/pan
- [x] Create `DagNode.svelte`: renders a single node - circle with label, color based on status, progress ring overlay
- [x] Create `DagEdge.svelte`: renders edge between nodes - bezier curve, color based on state

#### 3B: Real-Time Updates
- [x] Create `frontend/app/src/lib/stores/dag.ts`: reactive store that holds node statuses and progress, updated from Tauri event stream
- [x] On `node_started` event -> node transitions from `pending` to `running` with CSS animation
- [x] On `node_progress` event -> progress ring updates smoothly (CSS transition)
- [x] On `node_completed` event -> node transitions to `completed` with flash animation
- [x] On `node_failed` event -> node transitions to `failed` with shake animation
- [x] Edges animate with flowing blue dots when data passes between connected nodes (triggered on upstream `node_completed`)

#### 3C: Node Interaction
- [x] Click node -> open `NodeDetail.svelte` panel below the DAG
- [x] `NodeDetail.svelte`: tabbed panel with Summary, Logs, Tools, Data tabs
- [x] `NodeSummary.svelte`: status badge, progress bar, duration, key metrics from `node_completed` summary
- [x] `NodeLogs.svelte`: scrollable log viewer filtered to this node's events, color-coded by level
- [x] Hover node -> tooltip with name, status, progress message

#### 3D: Route Integration
- [x] Create `frontend/app/src/routes/run/[id]/+page.svelte`: loads run data, renders DagViewer + NodeDetail + LogViewer
- [x] Wire "Start Run" button to navigate to `/run/{new_run_id}` after starting

### Acceptance Criteria
1. DAG renders with correct layout (nodes positioned, edges routed)
2. Nodes transition through visual states in real time as events stream in
3. Progress rings animate smoothly during agent execution
4. Clicking a node shows its detail panel with correct data
5. Edge animations trigger when data flows between agents
6. Running the test recipe shows the full visual lifecycle from pending -> running -> completed

---

## Phase 4 - Run Management

### Goal
Full run lifecycle: persist runs to SQLite, browse run history, load historical runs into the DAG viewer, configure runs before launch, cancel running runs.

### Checklist

- [x] Implement `commands/runs.rs`: `get_run_history` - paginated list of past runs for a recipe
- [x] Implement `commands/runs.rs`: `get_run` - full run detail including all node statuses
- [x] Implement `commands/runs.rs`: `get_run_events` - paginated events for a run, filterable by node
- [x] Implement `commands/runs.rs`: `cancel_run` - sends cancel command to Python via stdin, marks run as cancelled
- [x] Implement `services/event_bus.rs`: persist every Python event to `run_events` table, update `run_nodes` status
- [x] Create `RunList.svelte`: sidebar showing past runs with status icon, timestamp, quick stats
- [x] Click historical run -> load its node states and events into DAG viewer (replay mode)
- [x] Create `RunConfig.svelte`: before launching, show config form generated from recipe's `config_schema`
- [x] Implement `commands/settings.rs`: `get_credentials`, `save_credentials` - encrypted Tauri store
- [x] Create `Credentials.svelte`: API key management (Space-Track, Claude, DISCOS, etc.)
- [x] Credential values injected as env vars when Python spawns (never in config JSON)

### Acceptance Criteria
1. Run history sidebar shows past runs with correct status icons
2. Clicking a historical run loads the DAG with that run's final node states
3. Run config panel lets you set parameters before launch
4. Cancel button sends cancel signal and run stops
5. API keys persist across app restarts (encrypted store)
6. Credentials are passed as env vars to Python, never in logs or config JSON

---

## Phase 5 - Built-in Tools

### Goal
The Python framework includes production-ready built-in tools that auto-emit events. Every HTTP request, LLM call, web search, and scrape shows up in the UI with timing and cost.

### Checklist

- [x] Implement `tools/http_tool.py`: `HttpTool` wrapping httpx - emits `tool_call` on every request (method, URL), emits `tool_result` with status code, duration, response size
- [x] Implement `tools/llm_tool.py`: `LLMTool` wrapping Claude API - emits `llm_call` (model, prompt_tokens), emits `llm_result` (completion_tokens, duration, estimated cost). Supports structured output via tool_use.
- [x] Implement `tools/web_search_tool.py`: `WebSearchTool` - emits events, caches results by query with configurable TTL (default 7 days)
- [x] Implement `tools/web_scrape_tool.py`: `WebScrapeTool` using BeautifulSoup - fetches URL via HttpTool (gets event emission for free), parses HTML, returns text/structured data
- [x] Implement `tools/sqlite_tool.py`: `SQLiteTool` - wraps SQLite access for recipe output databases, provides `execute`, `fetch_all`, `fetch_one`, `upsert` helpers
- [x] Update `NodeTools.svelte`: renders list of all tool calls for a node, expandable to show full request/response
- [x] Add LLM cost estimation: model pricing table, compute cost from token counts, show cumulative cost per run
- [x] Write tests for each tool (mock HTTP responses, verify event emission format)

### Acceptance Criteria
1. HttpTool emits events for every request - visible in NodeTools panel
2. LLMTool tracks tokens and shows estimated cost
3. WebSearchTool caches results and skips duplicate queries
4. All tool events appear in the Tools tab of node detail
5. Cumulative LLM cost shown in run summary

---

## Phase 6 - Satellite Enrichment Recipe

### Goal
The first real recipe: the Cosmotrak satellite enrichment pipeline. 4 agents, pulling from Space-Track/CelesTrak/DISCOS/UCS, merging, LLM gap-filling, and validating. Produces a SQLite database that the Cosmotrak API can consume.

### Checklist

#### 6A: Output Schema
- [x] Implement `recipes/satellite_enrichment/schema.py`: Pydantic models for the enriched satellite with 50+ fields (identity, ownership, mission, orbit, physical, launch, contractor, visual, metadata)
- [x] Define SQLite output schema matching the Cosmotrak API's expectations

#### 6B: StructuredDataCollector Agent
- [x] Implement Space-Track SATCAT fetcher (requires auth - username/password from config)
- [x] Implement Space-Track GP data fetcher (live orbital parameters)
- [x] Implement CelesTrak SATCAT fetcher (48 categories)
- [x] Implement ESA DISCOS fetcher (paginated, requires auth token)
- [x] Store raw data in staging tables in the output DB
- [x] Emit progress per source (e.g., "Fetching CelesTrak: 22/48 categories")
- [x] Rate limit handling: 200ms between CelesTrak requests, batch Space-Track queries, handle 429s

#### 6C: RecordMerger Agent
- [x] For each NORAD ID in Space-Track SATCAT: look up in CelesTrak, DISCOS, UCS data
- [x] Merge fields using priority: Space-Track > DISCOS > UCS > derived
- [x] Derive orbit_class from altitude (LEO <2000km, MEO 2000-35786km, GEO ~35786km)
- [x] Derive constellation_name from Celestrak category or name patterns
- [x] Compute `data_completeness_pct` per record
- [x] Flag records with completeness < threshold (default 0.5) for LLM research
- [x] Emit progress and key metrics (total merged, completeness distribution)

#### 6D: LLMResearcher Agent
- [x] For each low-completeness satellite: search web for specs, operator, purpose
- [x] Use Claude to extract structured data from search results (JSON output)
- [x] Validate extracted data (mass ranges, country codes, lifetime bounds)
- [x] Only merge results with confidence > threshold (default 0.7)
- [x] Cache search results (7-day TTL)
- [x] Emit progress per satellite researched, log LLM extractions

#### 6E: QualityAuditor Agent
- [x] Validate: NORAD IDs unique, orbital parameters plausible, dates valid, countries valid
- [x] Compute final `data_completeness_pct` and `enrichment_confidence` per record
- [x] Generate summary: total records, coverage stats, field completion rates, source breakdown
- [x] Flag anomalies (emit as warnings)

#### 6F: Integration Test
- [x] Run full pipeline end-to-end
- [x] Verify output DB has 10,000+ records with TLEs and enrichment
- [x] Verify coverage targets: >=80% with operator+purpose, >=70% with mass data
- [x] Verify Cosmotrak API can read the output DB

### Acceptance Criteria
1. Full pipeline runs to completion in the Atlas Weave UI
2. DAG shows all 4 agents executing with real progress
3. Output SQLite has 10,000+ satellite records
4. >=80% of records have operator + purpose populated
5. LLM researcher fills gaps for low-completeness records
6. Quality auditor summary matches validation criteria
7. Output DB schema matches Cosmotrak API expectations

---

## Phase 7 - Data Inspector

### Goal
A full-screen data browser for inspecting recipe output databases. Browse records, sort/filter, view details, see coverage stats.

### Checklist

- [x] Implement `commands/data.rs`: `query_recipe_db` - opens recipe output DB in read-only mode, executes paginated queries with sort/filter params
- [x] Create `DataBrowser.svelte`: full-screen view with table + sidebar
- [x] Create `DataTable.svelte`: paginated table with column sorting, text search, column filtering
- [x] Create `RecordDetail.svelte`: click a row to see all fields for one record in a formatted view
- [x] Create `CoverageDashboard.svelte`: bar charts showing field completion rates across all records
- [x] Add export to CSV button
- [x] Create `/data/[recipe]/+page.svelte` route
- [x] Add "View Data" link in recipe list and run summary

### Acceptance Criteria
1. Data inspector opens and displays satellite enrichment output
2. Table supports sorting, filtering, and text search
3. Clicking a record shows all 50+ fields
4. Coverage dashboard shows accurate field completion percentages
5. CSV export produces valid file

---

## Phase 8 - Scheduling

### Goal
Recipes can be scheduled to run on a cron interval. The scheduler triggers runs automatically and prevents overlapping executions.

### Checklist

- [x] Implement `services/scheduler.rs`: reads schedules from SQLite, computes next run times, triggers `start_run` when due
- [x] Implement run deduplication: if a run for the same recipe is already in `running` status, skip
- [x] Implement `commands/schedules.rs`: `create_schedule`, `update_schedule`, `delete_schedule`, `get_schedules`
- [x] Create `SchedulePanel.svelte`: create/edit schedule with cron expression, toggle enabled/disabled, human-readable description
- [x] Show next scheduled run time in schedule panel
- [x] Scheduler starts on app launch, persists across restarts

### Acceptance Criteria
1. Creating a schedule with "0 */6 * * *" triggers a run every 6 hours
2. If a run is already in progress, the scheduled trigger is skipped
3. Schedules persist across app restarts
4. Disabling a schedule stops future triggers
5. UI shows next scheduled run time

---

## Phase 9 - Polish

### Goal
Final polish: cost tracking, dark/light theme, notifications, error recovery, and UX refinements.

### Checklist

- [x] Add cumulative cost tracking per run (LLM token costs, displayed in run summary)
- [x] Implement dark/light theme toggle (Tailwind dark mode)
- [x] Desktop notifications on run completion/failure via Tauri notification plugin
- [x] Error recovery: "Retry Failed Nodes" button that re-runs only failed/skipped agents from a completed run
- [x] Node detail tools tab: expandable HTTP/LLM call details with full request/response
- [x] Improve DAG viewer: mini-map for large DAGs, zoom controls, auto-fit on recipe load
- [x] Loading states for all async operations
- [x] Empty states for first-launch experience (no runs yet, no recipes configured)
- [x] Keyboard shortcuts: `Ctrl+R` to start run, `Escape` to close panels

### Acceptance Criteria
1. Cost tracking shows estimated spend per run
2. Theme toggle works
3. Notification appears when a background scheduled run completes
4. Retry button re-runs only failed nodes
5. App feels polished on first launch

---

## Phase 10 - Testing & CI/CD Foundation

### Goal
Establish a CI pipeline that gates PRs on lint, type-check, and unit tests across all three layers, plus E2E smoke tests that exercise the full Tauri-Python loop.

### Checklist

#### 10A: CI Pipeline
- [ ] Create multi-job GitHub Actions workflow: `lint`, `test-python`, `test-rust`, `test-frontend`, `build`
- [ ] `lint` job: `ruff check` + `ruff format --check`, `cargo clippy -- -D warnings` + `cargo fmt --check`, `svelte-check`
- [ ] `test-python` job: `pytest python/tests/ -x --tb=short` with mocked network calls
- [ ] `test-rust` job: `cargo test --workspace`
- [ ] `test-frontend` job: run vitest for store/utility unit tests
- [ ] `build` job: `cargo tauri build --debug` (depends on lint + test jobs)
- [ ] Add branch protection requiring CI pass before merge to `main`

#### 10B: Frontend Unit Tests
- [ ] Add vitest + `@testing-library/svelte` to `frontend/app/`
- [ ] Write tests for `dag.ts` store: `hydrate`, `applyEvent` for each event type, edge state derivation
- [ ] Write tests for `events.ts` store: `push`, `setRun`, `getNodeEvents`
- [ ] Write tests for `dag-layout.ts`: layout correctness for linear, diamond, and parallel shapes
- [ ] Add `test` script to `frontend/app/package.json`

#### 10C: E2E Smoke Test
- [ ] Create `tests/e2e/` with a Playwright config targeting Tauri
- [ ] Smoke test: launch app → verify recipe list → start `test_pipeline` → verify DAG renders → wait for completion → verify node statuses
- [ ] Add E2E job to CI (`continue-on-error: true` initially)

#### 10D: Python Test Coverage
- [ ] Add `pytest-cov`, configure `--cov=atlas_weave --cov-fail-under=60`
- [ ] Write tests for `runner.py`: resume state, cancellation mid-run, failure propagation
- [ ] Write tests for `events.py`: verify each emitter method produces correct JSON shape

### Acceptance Criteria
1. PRs to `main` are blocked until lint + test + build pass
2. `cargo test` runs 13+ Rust tests green
3. `pytest` runs 20+ Python tests with coverage above 60%
4. `vitest` runs 10+ frontend store/utility tests green
5. E2E smoke test launches the app and completes a test run
6. CI completes in under 10 minutes

---

## Phase 11 - Agent Framework Hardening

### Goal
Make the DAG runner production-ready with per-agent timeouts, automatic retries, conditional/branching execution, and structured inter-agent messaging replacing raw shared-state mutation.

### Checklist

#### 11A: Agent Timeouts & Retries
- [ ] Add `timeout_seconds: ClassVar[int | None] = None` to `Agent` base class
- [ ] Implement `asyncio.wait_for` wrapper in `_execute_agent` enforcing the timeout
- [ ] Add `max_retries: ClassVar[int] = 0` and `retry_delay_seconds: ClassVar[float] = 1.0` to `Agent`
- [ ] Implement retry loop in `_execute_agent` with exponential backoff, emitting `node_log` on each retry

#### 11B: Conditional Execution
- [ ] Extend `Recipe.edges` to accept `tuple[str, str, dict]` with an optional `{"when": "lambda state: ..."}` condition
- [ ] Update `build_execution_plan` to store conditions on edges
- [ ] Before executing an agent, evaluate incoming edge conditions; if any return `False`, skip with `"skipped_conditional"`
- [ ] Add `skipped_conditional` status to frontend DAG store with a distinct visual (dimmed with "?" badge)

#### 11C: Inter-Agent Mailbox
- [ ] Create `atlas_weave/mailbox.py`: typed `Mailbox` with `send(channel, message)` and `receive(channel)`
- [ ] Messages are Pydantic models serialized to JSON, stored under `state["_mailbox"]`
- [ ] Inject per-agent `Mailbox` view into `AgentContext`
- [ ] Mailbox contents included in `node_completed` summary

#### 11D: Agent Hooks
- [ ] Add `on_start(ctx)` and `on_complete(ctx, result)` optional lifecycle hooks to `Agent` base class (default no-op)
- [ ] Hooks run within the timeout envelope; failures are logged but do not fail the agent

### Acceptance Criteria
1. An agent with `timeout_seconds = 5` is killed after 5s and downstream dependents are skipped
2. An agent with `max_retries = 2` retries twice before marking as failed
3. A conditional edge with `{"when": "lambda state: False"}` skips the target agent
4. `ctx.mailbox.send("data", payload)` in Agent A is receivable by Agent B
5. Frontend displays `skipped_conditional` nodes with a distinct visual
6. All new features have pytest coverage

---

## Phase 12 - Analytics Dashboard

### Goal
A dedicated analytics page with charts showing run history trends, cost tracking over time, agent duration breakdowns, and per-recipe success rates.

### Checklist

#### 12A: Charting Infrastructure
- [ ] Add a charting library (chart.js or layerchart) to frontend dependencies
- [ ] Create reusable chart components: `BarChart.svelte`, `LineChart.svelte`, `DonutChart.svelte`

#### 12B: Analytics Rust Commands
- [ ] Implement `commands/analytics.rs`: `get_run_stats` — success/fail/cancel counts per recipe over a date range
- [ ] Implement `get_cost_trend` — daily/weekly LLM cost totals from `run_events` where `event_type = 'llm_result'`
- [ ] Implement `get_duration_breakdown` — per-agent avg/p50/p95 durations from `run_nodes`
- [ ] Implement `get_tool_usage` — tool call counts by tool name from `run_events`
- [ ] Add typed invoke wrappers in `frontend/app/src/lib/api/tauri/analytics.ts`

#### 12C: Analytics Page
- [ ] Create `/analytics/+page.svelte` route with navigation link
- [ ] Run History section: line chart of runs per day colored by status
- [ ] Cost Tracking section: stacked bar chart of daily LLM spend by model
- [ ] Duration Breakdown section: horizontal bar chart of average agent durations per recipe
- [ ] Tool Usage section: donut chart of tool call distribution
- [ ] Date range picker (7d, 30d, 90d, all time)

#### 12D: Run Comparison
- [ ] Create `RunComparison.svelte`: side-by-side view of two runs for the same recipe
- [ ] Show delta for each agent: duration change, record count change, error count change
- [ ] Accessible from run history via "Compare with..." button

### Acceptance Criteria
1. Analytics page shows charts for a recipe with 3+ historical runs
2. Cost trend chart accurately reflects LLM spend from `llm_result` events
3. Duration breakdown shows per-agent timing for the selected recipe
4. Run comparison highlights differences between two runs
5. Charts render correctly in both dark and light themes
6. Date range picker filters all charts simultaneously

---

## Phase 13 - Plugin & Extension System

### Goal
Make Atlas Weave extensible with a manifest format for third-party recipes, tools, and agent libraries that can be installed from a local directory.

### Checklist

#### 13A: Plugin Manifest
- [ ] Define `atlas-weave-plugin.json` manifest: `name`, `version`, `description`, `author`, `type` (recipe | tool | agent-library), `entry_point`, `dependencies`, `min_atlas_weave_version`
- [ ] Create `atlas_weave/plugin.py`: `PluginManifest` Pydantic model
- [ ] Create `atlas_weave/plugin_loader.py`: discover plugins from `~/.atlas-weave/plugins/` and `{repo}/plugins/`

#### 13B: Plugin Lifecycle in Rust
- [ ] Implement `services/plugin_manager.rs`: scan, validate, maintain plugin registry in SQLite
- [ ] Add `plugins` table: `name`, `version`, `type`, `path`, `enabled`, `installed_at`
- [ ] Implement `commands/plugins.rs`: `list_plugins`, `enable_plugin`, `disable_plugin`, `get_plugin_detail`
- [ ] On startup, load enabled plugins and merge their recipes/tools into registries

#### 13C: Tool Extension API
- [ ] Create `atlas_weave/plugin_tools.py`: `load_plugin_tools(manifest) -> list[Tool]`
- [ ] Update `register_builtin_tools` to also register plugin-provided tools
- [ ] Verify external tools emit events correctly through existing helpers

#### 13D: Plugin Management UI
- [ ] Create `/plugins/+page.svelte` route with enable/disable toggles and detail views
- [ ] "Install from folder" button that validates and copies a plugin directory
- [ ] Add "Plugins" link to main layout navigation

### Acceptance Criteria
1. A plugin placed in `~/.atlas-weave/plugins/` appears in the Plugins page
2. Enabling a recipe plugin makes it appear in the launcher
3. Enabling a tool plugin makes the tool available to all agents
4. Disabling a plugin removes its recipes/tools without deleting files
5. Invalid manifests show a clear error
6. Plugin tool events appear correctly in node detail

---

## Phase 14 - Advanced DAG Features

### Goal
Support complex pipeline topologies: collapsible sub-graphs, dynamic node creation at runtime, and a visual recipe editor for building DAGs without code.

### Checklist

#### 14A: Sub-Graphs / Agent Groups
- [ ] Add `group: ClassVar[str | None] = None` to `Agent` for static grouping
- [ ] Update `build_execution_plan` to compute group-level status
- [ ] Render groups in `DagViewer.svelte` as collapsible containers with shared border and label
- [ ] Collapsed view shows summary status pill

#### 14B: Dynamic Node Spawning
- [ ] Create `atlas_weave/dynamic.py`: `DynamicAgentPool` helper for spawning N sub-agents at runtime
- [ ] Dynamic agents emit `graph_patch` to add themselves, then standard lifecycle events
- [ ] Update frontend `mergeRuntimeNodes` with animated transitions for new nodes
- [ ] Dynamic nodes are visually distinct (dashed border) and grouped under parent

#### 14C: Recipe Editor UI
- [ ] Create `/editor/+page.svelte` with split-pane: visual DAG canvas (left) + property panel (right)
- [ ] Drag-and-drop node palette listing available agent types
- [ ] Click-and-drag between nodes to create edges; click edge to delete
- [ ] Property panel: agent config, conditional edges, timeout/retry
- [ ] "Export Recipe" generates a valid Python recipe file
- [ ] "Validate" checks for cycles, missing deps, invalid configs

### Acceptance Criteria
1. Grouped agents render inside a collapsible container
2. Collapsing shows a summary node; expanding shows all children
3. Dynamic spawning of 5 workers shows 5 nodes appearing with animation
4. Recipe editor creates a 3-agent pipeline via drag-and-drop
5. Exported recipe is valid Python loadable by the runner
6. Cycle detection prevents invalid edge creation

---

## Phase 15 - Production Builds & Auto-Update

### Goal
Ship Atlas Weave as a signed, installable desktop application with automatic update checks.

### Checklist

#### 15A: Build Pipeline
- [ ] Enable `bundle.active = true` in `tauri.conf.json`, configure NSIS (Windows), DMG (macOS), AppImage + deb (Linux)
- [ ] Add `tauri-plugin-updater` to Cargo dependencies
- [ ] Generate app icon set from base SVG (16x16 through 512x512 + .ico)
- [ ] GitHub Actions release workflow: on tag `v*`, build all platforms, upload to GitHub Releases
- [ ] Configure code signing for Windows and macOS via GitHub secrets

#### 15B: Auto-Update
- [ ] Configure `tauri-plugin-updater` with GitHub Releases as the update endpoint
- [ ] On launch, background check; if update available, show `UpdateBanner.svelte`: "Update v{version} available. [Install Now] [Later]"
- [ ] "Install Now" downloads, applies, prompts restart
- [ ] Show release notes from GitHub Release body

#### 15C: Python Bundling
- [ ] Bundle Python sidecar via PyInstaller/Nuitka into a single executable
- [ ] Update `sidecar.rs` to detect bundled vs dev mode
- [ ] Include pip dependencies (httpx, pydantic, beautifulsoup4) in the bundle
- [ ] Test bundled sidecar runs recipes on all platforms

#### 15D: Version Management
- [ ] Version display in Settings: app version, Python version, last update check
- [ ] `scripts/bump-version.sh` to coordinate `tauri.conf.json`, `Cargo.toml`, `pyproject.toml`

### Acceptance Criteria
1. `cargo tauri build` produces a working installer on Windows
2. Built app starts without a development environment
3. Bundled Python sidecar executes `test_pipeline` to completion
4. Auto-update finds newer releases and shows the banner
5. "Install Now" downloads, applies, and prompts restart
6. Settings page shows current app version

---

## Phase 16 - Multi-Provider LLM Support & Model Routing

### Goal
Support multiple LLM providers (Anthropic, OpenRouter, OpenAI, Ollama) with configurable routing rules and automatic fallback.

### Checklist

#### 16A: Provider Abstraction
- [ ] Create `atlas_weave/providers/base.py`: `LLMProvider` ABC with `complete(messages, **kwargs) -> LLMProviderResponse`
- [ ] Create concrete providers: `anthropic.py`, `openrouter.py` (extract from llm_tool), `openai.py`, `ollama.py`
- [ ] Create `ProviderRegistry` mapping provider names to instances

#### 16B: Model Router
- [ ] Create `atlas_weave/model_router.py`: selects provider+model based on routing rules
- [ ] Routing: `preferred_model`, `fallback_models`, `max_cost_per_call_usd`, `min_context_window`
- [ ] Fallback chain: if preferred provider unavailable, try fallbacks in order
- [ ] Emit `llm_call` events with actual provider/model used
- [ ] Unified pricing table merging Anthropic, OpenRouter, and OpenAI

#### 16C: Provider Configuration UI
- [ ] Add "LLM Providers" section to Settings: API key, "Test Connection" button, status indicator per provider
- [ ] Ollama auto-detection of local instance, list available models
- [ ] Drag-to-reorder model preference editor

#### 16D: Recipe-Level Model Config
- [ ] Support `model_routing` field type in `config_schema` rendering as preference editor
- [ ] Recipes can specify default routing rules; users override per-run

### Acceptance Criteria
1. Anthropic provider works with a valid API key
2. Missing Anthropic key falls back to OpenRouter automatically
3. Ollama provider works with a local instance
4. "Test Connection" verifies each provider
5. Run events show the actual provider/model used after routing
6. Cost tracking attributes costs to the actual provider

---

## Phase 17 - Collaboration & Portability

### Goal
Enable sharing runs, recipes, and configurations through import/export, configuration profiles, and an audit log.

### Checklist

#### 17A: Run Export & Import
- [ ] Implement `export_run`: packages run into a `.atw` zip (metadata, events, node summaries, output DB, recipe snapshot)
- [ ] Implement `import_run`: reads `.atw`, inserts into local DB, restores output DB
- [ ] "Export Run" / "Import Run" buttons in UI with file dialogs
- [ ] Imported runs show an "imported" badge in history

#### 17B: Recipe Packaging
- [ ] Define `.atwrecipe` format: zip with manifest + Python source + sample config
- [ ] Implement `export_recipe` and `import_recipe` commands
- [ ] Export/import buttons on recipe detail and launcher

#### 17C: Configuration Profiles
- [ ] Add `config_profiles` table: `id`, `recipe_name`, `profile_name`, `config_json`, `created_at`
- [ ] Implement CRUD commands for profiles
- [ ] Profile dropdown in `RunConfig.svelte`: "Save as Profile...", "Load Profile", "Delete Profile"

#### 17D: Audit Log
- [ ] Add `audit_log` table: `id`, `timestamp`, `actor`, `action`, `details_json`
- [ ] Write entries for all state-changing operations (run start/cancel, schedule changes, plugin toggles)
- [ ] `AuditLog.svelte` viewable from Settings, searchable/filterable

### Acceptance Criteria
1. Exported `.atw` file reimports on a fresh install with correct DAG and events
2. Recipe export/import preserves agents, edges, and config schema
3. Config profiles persist and load correctly before run launch
4. Audit log records every run start, cancel, schedule change, and plugin toggle
5. Audit log is searchable by action type
6. Imported runs display correctly in the DAG viewer

---

## Phase 18 - Performance & Scale

### Goal
Handle large DAGs (50+ nodes), high-frequency event streams (1000+ events/sec), and large output databases (100K+ rows) without UI jank.

### Checklist

#### 18A: Event Stream Optimization
- [ ] Event batching in `event_bus.rs`: accumulate up to 16ms before emitting `atlas-weave:event-batch`
- [ ] Frontend processes batches in a single store `update` to minimize re-renders
- [ ] Consecutive `node_progress` events for the same node within a batch are merged
- [ ] Event pruning in `eventStore`: keep last 5000 in memory, page older from SQLite on demand

#### 18B: Virtual Scrolling
- [ ] Add virtual scroll component to frontend
- [ ] Replace scroll containers in `NodeLogs.svelte`, `RunLogViewer.svelte`, `DataTable.svelte`
- [ ] Lazy-load log entries: fetch pages of 200 as user scrolls
- [ ] Virtual-scroll data table: render only visible rows, lazy-load pages of 100

#### 18C: DAG Layout Performance
- [ ] For 20+ node DAGs, switch to ELK.js in a web worker for non-blocking layout
- [ ] Incremental layout: `graph_patch` additions recompute only affected sub-graph
- [ ] Level-of-detail: below 50% zoom, simplified circles; below 25%, dots
- [ ] Edge bundling for 50+ edge DAGs

#### 18D: Database Query Performance
- [ ] Add indices on `run_events(event_type)` and `run_events(timestamp)`
- [ ] Query result caching in Rust with 30s TTL for data inspector queries
- [ ] `EXPLAIN QUERY PLAN` logging in debug mode for slow queries
- [ ] Server-side column filtering to avoid transferring unused columns

### Acceptance Criteria
1. 50-node recipe renders without dropping below 30fps
2. 10,000 log entries scroll at smooth 60fps
3. 100K-row data inspector loads first page in under 500ms
4. Event batching reduces IPC messages by at least 5x
5. Memory stays under 500MB with 50K events in a run
6. 50-node layout completes in under 200ms

---

## Phase 19 - Recipe Templates & Cookbook

### Goal
Ship a library of recipe templates and a guided creation flow so new users can build pipelines in minutes, establishing Atlas Weave as a general-purpose orchestration tool beyond the satellite domain.

### Checklist

#### 19A: Template Engine
- [ ] Create `python/templates/` with template recipes: `web_scrape_and_summarize`, `data_etl_pipeline`, `research_report_generator`, `api_monitor`, `content_aggregator`
- [ ] Create `atlas_weave/template.py`: `RecipeTemplate` with `name`, `description`, `category`, `parameters`
- [ ] Implement `instantiate_template(template, values) -> Recipe` that substitutes parameters

#### 19B: Template Gallery UI
- [ ] Create `/templates/+page.svelte` with card grid of templates
- [ ] Each card: name, description, category badge, agent count, estimated run time
- [ ] Guided setup wizard: configure parameters → set credentials → preview DAG → save and launch
- [ ] "Use Template" generates recipe files and installs them
- [ ] Add "Templates" link to navigation

#### 19C: Built-in Templates
- [ ] `web_scrape_and_summarize`: 3 agents (Scraper → Processor → Summarizer)
- [ ] `data_etl_pipeline`: 3 agents (Extractor → Transformer → Loader) with configurable source
- [ ] `research_report_generator`: 4 agents (QueryBuilder → WebResearcher → Synthesizer → ReportWriter)
- [ ] `api_monitor`: 2 agents (Poller → Analyzer) with anomaly alerts
- [ ] `content_aggregator`: 3 agents (FeedFetcher → Deduplicator → Ranker) with LLM ranking

#### 19D: Documentation
- [ ] Create `docs/RECIPE_AUTHORING.md`: guide to writing custom recipes
- [ ] Create `docs/TEMPLATE_GUIDE.md`: how to create and share templates
- [ ] Inline help tooltips in the template wizard
- [ ] Each template includes a README with usage and example output

### Acceptance Criteria
1. Template gallery shows 5+ templates with category filtering
2. Guided wizard produces a runnable recipe in under 2 minutes
3. Each built-in template runs to completion with test data
4. Generated recipes follow existing conventions (RECIPE export, config_schema)
5. Recipe authoring guide covers agent creation, tool usage, testing, events
6. Templates are installable via the Phase 13 plugin system

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
