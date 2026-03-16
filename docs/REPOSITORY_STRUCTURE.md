# SwarmForge — Repository Structure

## 1. Monorepo Layout

```
swarmforge/
├── Cargo.toml                              # Rust workspace
├── package.json                            # Root package.json for workspace scripts
├── README.md
├── .gitignore
├── .github/
│   └── workflows/
│       └── ci.yml                          # Lint + test on PR
│
├── docs/
│   ├── PROJECT_CONTEXT.md
│   ├── ARCHITECTURE.md
│   ├── REPOSITORY_STRUCTURE.md
│   └── IMPLEMENTATION_ROADMAP.md
│
├── apps/
│   └── swarmforge-shell/                   # Tauri v2 application
│       ├── src-tauri/
│       │   ├── Cargo.toml
│       │   ├── tauri.conf.json
│       │   ├── build.rs
│       │   ├── icons/
│       │   ├── capabilities/
│       │   │   └── main.json               # Main capability set
│       │   └── src/
│       │       ├── main.rs                 # App entry, plugin registration, sidecar init
│       │       ├── lib.rs                  # Module declarations
│       │       ├── db.rs                   # SQLite init, migrations, connection pool
│       │       ├── commands/               # Tauri #[command] handlers
│       │       │   ├── mod.rs
│       │       │   ├── recipes.rs          # list_recipes, get_recipe_detail, validate_recipe
│       │       │   ├── runs.rs             # start_run, cancel_run, get_run, get_run_history, get_run_events
│       │       │   ├── schedules.rs        # create_schedule, update_schedule, delete_schedule, get_schedules
│       │       │   ├── events.rs           # query_events (historical), get_node_events
│       │       │   ├── data.rs             # query_recipe_db (read-only access to recipe output DBs)
│       │       │   └── settings.rs         # get_credentials, save_credentials
│       │       └── services/
│       │           ├── mod.rs
│       │           ├── sidecar.rs          # Python process spawn, stdin/stdout JSON protocol, lifecycle
│       │           ├── event_bus.rs        # Parse Python events → persist to SQLite → emit Tauri events
│       │           ├── scheduler.rs        # Cron-based run triggering, deduplication
│       │           └── recipe_registry.rs  # Discover recipes from filesystem, import metadata via Python
│       └── gen/                            # Tauri-generated platform code
│
├── frontend/
│   └── app/                                # SvelteKit UI
│       ├── package.json
│       ├── svelte.config.js
│       ├── vite.config.ts
│       ├── tsconfig.json
│       ├── tailwind.config.ts
│       ├── postcss.config.js
│       └── src/
│           ├── app.html
│           ├── app.css
│           ├── lib/
│           │   ├── api/
│           │   │   └── tauri/              # Typed invoke wrappers
│           │   │       ├── recipes.ts      # listRecipes, getRecipeDetail
│           │   │       ├── runs.ts         # startRun, cancelRun, getRun, getRunHistory
│           │   │       ├── events.ts       # queryEvents, getNodeEvents
│           │   │       ├── schedules.ts    # CRUD for schedules
│           │   │       ├── data.ts         # queryRecipeDb (data inspector queries)
│           │   │       └── settings.ts     # credentials management
│           │   ├── stores/
│           │   │   ├── recipes.ts          # Recipe list state
│           │   │   ├── runs.ts             # Active run state, run history
│           │   │   ├── dag.ts              # DAG visualization state (node statuses, layout)
│           │   │   ├── events.ts           # Real-time event stream from Tauri listen()
│           │   │   └── settings.ts         # User preferences
│           │   ├── features/
│           │   │   ├── dag/                # DAG viewer components
│           │   │   │   ├── DagViewer.svelte        # Main DAG canvas
│           │   │   │   ├── DagNode.svelte          # Single node (circle + label + progress ring)
│           │   │   │   ├── DagEdge.svelte          # Edge with animated data flow dots
│           │   │   │   └── dag-layout.ts           # dagre/ELK layout computation
│           │   │   ├── nodes/              # Node detail panel
│           │   │   │   ├── NodeDetail.svelte       # Tab container
│           │   │   │   ├── NodeSummary.svelte      # Status, progress, metrics
│           │   │   │   ├── NodeLogs.svelte         # Scrollable log stream (xterm.js)
│           │   │   │   ├── NodeTools.svelte        # HTTP/LLM/search call list
│           │   │   │   └── NodeData.svelte         # Output data table for this node
│           │   │   ├── runs/               # Run management
│           │   │   │   ├── RunList.svelte          # Run history sidebar
│           │   │   │   ├── RunConfig.svelte        # Config panel before launch
│           │   │   │   └── RunSummary.svelte       # Post-run summary card
│           │   │   ├── data/               # Data inspector
│           │   │   │   ├── DataBrowser.svelte      # Full-screen data browser
│           │   │   │   ├── DataTable.svelte        # Sortable/filterable table
│           │   │   │   ├── RecordDetail.svelte     # Single record view
│           │   │   │   └── CoverageDashboard.svelte # Field completion bar charts
│           │   │   └── settings/
│           │   │       ├── RecipeConfig.svelte     # Per-recipe parameter editor
│           │   │       ├── ScheduleManager.svelte  # Cron schedule CRUD
│           │   │       └── Credentials.svelte      # API key management
│           │   └── components/             # Shared UI components
│           │       ├── Layout.svelte
│           │       ├── Sidebar.svelte
│           │       ├── ProgressRing.svelte         # Animated circular progress
│           │       ├── LogViewer.svelte             # xterm.js wrapper
│           │       └── StatusBadge.svelte           # Colored status pill
│           └── routes/
│               ├── +layout.svelte
│               ├── +page.svelte                    # Home: recipe list + active run overview
│               ├── run/
│               │   └── [id]/
│               │       └── +page.svelte            # Run detail: DAG viewer + panels
│               ├── data/
│               │   └── [recipe]/
│               │       └── +page.svelte            # Data inspector for recipe output
│               └── settings/
│                   └── +page.svelte                # Credentials + schedule management
│
├── python/
│   ├── pyproject.toml                      # Python package config (deps: langchain, anthropic, httpx, pydantic, etc.)
│   ├── swarmforge/                         # Core framework library
│   │   ├── __init__.py                     # Exports: Agent, Recipe, Tool, AgentContext, AgentResult
│   │   ├── agent.py                        # Agent base class, AgentResult
│   │   ├── recipe.py                       # Recipe base class (name, agents, edges, config_schema)
│   │   ├── tool.py                         # Tool base class
│   │   ├── context.py                      # AgentContext (config, db, tools, emit)
│   │   ├── events.py                       # EventEmitter (writes JSON lines to stdout)
│   │   ├── runner.py                       # CLI entry point: reads stdin commands, executes DAG, emits events
│   │   ├── dag.py                          # DAG topological sort and execution scheduler
│   │   ├── db.py                           # SQLite helpers for recipe output databases
│   │   └── tools/                          # Built-in tools
│   │       ├── __init__.py
│   │       ├── http_tool.py                # httpx wrapper with auto event emission
│   │       ├── llm_tool.py                 # Claude API wrapper with token tracking
│   │       ├── web_search_tool.py          # Web search with result caching
│   │       ├── web_scrape_tool.py          # BeautifulSoup scraper with event emission
│   │       └── sqlite_tool.py              # Direct SQLite access for recipe DBs
│   │
│   └── recipes/                            # Recipe packages
│       └── satellite_enrichment/           # First recipe: Cosmotrak satellite enrichment
│           ├── __init__.py
│           ├── recipe.py                   # SatelliteEnrichmentRecipe class
│           ├── schema.py                   # Pydantic models for enriched satellite data
│           ├── config.yaml                 # Default config values
│           └── agents/
│               ├── __init__.py
│               ├── collector.py            # Agent 1: Space-Track, CelesTrak, DISCOS fetch
│               ├── merger.py               # Agent 2: Cross-reference by NORAD ID, merge
│               ├── researcher.py           # Agent 3: LLM web research for gaps
│               └── auditor.py              # Agent 4: Validation + coverage report
│
└── scripts/
    ├── dev.sh                              # Start Tauri dev mode
    ├── setup-python.sh                     # Create venv, install deps
    └── build.sh                            # Production build
```

---

## 2. Workspace Cargo.toml

```toml
[workspace]
resolver = "2"
members = [
    "apps/swarmforge-shell/src-tauri",
]

[workspace.dependencies]
serde = { version = "1", features = ["derive"] }
serde_json = "1"
tokio = { version = "1", features = ["full"] }
rusqlite = { version = "0.31", features = ["bundled"] }
thiserror = "2"
anyhow = "1"
chrono = { version = "0.4", features = ["serde"] }
uuid = { version = "1", features = ["v4", "serde"] }
```

---

## 3. Python pyproject.toml

```toml
[project]
name = "swarmforge"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "langchain>=0.3",
    "langgraph>=0.2",
    "langchain-anthropic>=0.3",
    "anthropic>=0.40",
    "httpx>=0.27",
    "beautifulsoup4>=4.12",
    "pydantic>=2.9",
    "structlog>=24.0",
]

[project.optional-dependencies]
dev = ["pytest", "pytest-asyncio", "ruff"]

[project.scripts]
swarmforge-runner = "swarmforge.runner:main"
```

---

## 4. What Goes Where — Decision Guide

| I need to... | Put it in... |
|--------------|-------------|
| Define a new recipe | `python/recipes/{recipe_name}/recipe.py` |
| Add a new agent to a recipe | `python/recipes/{recipe_name}/agents/{agent_name}.py` |
| Add a new built-in tool | `python/swarmforge/tools/{tool_name}.py` |
| Add a new Tauri command | `apps/swarmforge-shell/src-tauri/src/commands/` |
| Add a new UI feature | `frontend/app/src/lib/features/{feature}/` |
| Add a new Tauri event listener | `frontend/app/src/lib/stores/events.ts` |
| Handle Python subprocess comms | `apps/swarmforge-shell/src-tauri/src/services/sidecar.rs` |
| Persist run history | `apps/swarmforge-shell/src-tauri/src/db.rs` |
| Define recipe output schema | `python/recipes/{recipe_name}/schema.py` |
| Query recipe output data for UI | `apps/swarmforge-shell/src-tauri/src/commands/data.rs` (read-only) |

---

## 5. Naming Conventions

| Context | Convention | Example |
|---------|-----------|---------|
| Rust file names | snake_case | `recipe_registry.rs` |
| Rust struct/enum names | PascalCase | `RunStatus` |
| Tauri command names | snake_case | `start_run` |
| Tauri event names | `namespace:action` | `swarm:event` |
| Python module names | snake_case | `http_tool.py` |
| Python class names | PascalCase | `StructuredDataCollector` |
| Recipe directory names | kebab-case | `satellite-enrichment/` |
| TypeScript file names | camelCase | `recipes.ts` |
| Svelte component files | PascalCase | `DagViewer.svelte` |
| SQL table names | snake_case | `run_events` |
