use std::{
    fs,
    path::{Path, PathBuf},
};

use anyhow::{Context, Result as AnyhowResult};
use chrono::Utc;
use rusqlite::{params, Connection, OptionalExtension};
use serde_json::Value;

use crate::AppResult;

#[derive(Debug, Clone)]
pub struct Database {
    path: PathBuf,
}

#[derive(Debug, Clone)]
pub struct RecipeRecord {
    pub name: String,
    pub description: String,
    pub version: String,
}

#[derive(Debug, Clone)]
pub struct RecipeDetailRecord {
    pub name: String,
    pub description: String,
    pub version: String,
    pub config_schema: Value,
    pub dag: Value,
}

#[derive(Debug, Clone)]
pub struct RunRecord {
    pub id: String,
    pub recipe_name: String,
    pub status: String,
    pub started_at: Option<String>,
    pub completed_at: Option<String>,
    pub error: Option<String>,
    pub nodes: Vec<RunNodeRecord>,
}

#[derive(Debug, Clone)]
pub struct RunNodeRecord {
    pub node_id: String,
    pub status: String,
    pub progress: f64,
    pub message: Option<String>,
    pub started_at: Option<String>,
    pub completed_at: Option<String>,
    pub duration_ms: Option<i64>,
    pub summary: Option<Value>,
    pub error: Option<String>,
}

impl Database {
    pub fn new(path: PathBuf) -> AppResult<Self> {
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent).with_context(|| {
                format!(
                    "failed to create database directory at {}",
                    parent.display()
                )
            })?;
        }

        Ok(Self { path })
    }

    pub fn initialize(&self) -> AppResult<()> {
        let connection = self.connect()?;

        connection.execute_batch(
            r#"
            PRAGMA journal_mode = WAL;

            CREATE TABLE IF NOT EXISTS recipes (
                name            TEXT PRIMARY KEY,
                description     TEXT,
                version         TEXT,
                path            TEXT NOT NULL,
                config_schema   TEXT,
                dag_json        TEXT,
                discovered_at   TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS runs (
                id              TEXT PRIMARY KEY,
                recipe_name     TEXT NOT NULL REFERENCES recipes(name),
                config_json     TEXT,
                status          TEXT NOT NULL DEFAULT 'pending',
                started_at      TEXT,
                completed_at    TEXT,
                summary_json    TEXT,
                error           TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_runs_recipe ON runs(recipe_name);
            CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status);

            CREATE TABLE IF NOT EXISTS run_nodes (
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

            CREATE TABLE IF NOT EXISTS run_events (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id          TEXT NOT NULL REFERENCES runs(id),
                node_id         TEXT,
                event_type      TEXT NOT NULL,
                timestamp       TEXT NOT NULL,
                payload_json    TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_events_run ON run_events(run_id);
            CREATE INDEX IF NOT EXISTS idx_events_run_node ON run_events(run_id, node_id);

            CREATE TABLE IF NOT EXISTS schedules (
                id              TEXT PRIMARY KEY,
                recipe_name     TEXT NOT NULL REFERENCES recipes(name),
                cron_expression TEXT NOT NULL,
                config_json     TEXT,
                enabled         INTEGER NOT NULL DEFAULT 1,
                last_run_id     TEXT REFERENCES runs(id),
                next_run_at     TEXT,
                created_at      TEXT NOT NULL
            );
            "#,
        )?;

        Ok(())
    }

    pub fn upsert_recipe(
        &self,
        name: &str,
        description: &str,
        version: &str,
        path: &Path,
        config_schema: &str,
        dag_json: &str,
    ) -> AppResult<()> {
        let connection = self.connect()?;

        connection.execute(
            r#"
            INSERT INTO recipes (name, description, version, path, config_schema, dag_json, discovered_at)
            VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)
            ON CONFLICT(name) DO UPDATE SET
                description = excluded.description,
                version = excluded.version,
                path = excluded.path,
                config_schema = excluded.config_schema,
                dag_json = excluded.dag_json,
                discovered_at = excluded.discovered_at
            "#,
            params![
                name,
                description,
                version,
                path.to_string_lossy().to_string(),
                config_schema,
                dag_json,
                Utc::now().to_rfc3339()
            ],
        )?;

        Ok(())
    }

    pub fn list_recipes(&self) -> AppResult<Vec<RecipeRecord>> {
        let connection = self.connect()?;
        let mut statement = connection.prepare(
            "SELECT name, COALESCE(description, ''), COALESCE(version, '0.1.0') FROM recipes ORDER BY name ASC",
        )?;

        let rows = statement.query_map([], |row| {
            Ok(RecipeRecord {
                name: row.get(0)?,
                description: row.get(1)?,
                version: row.get(2)?,
            })
        })?;

        let recipes = rows.collect::<Result<Vec<_>, _>>()?;
        Ok(recipes)
    }

    pub fn get_recipe_detail(&self, name: &str) -> AppResult<Option<RecipeDetailRecord>> {
        let connection = self.connect()?;
        let record = connection
            .query_row(
                r#"
                SELECT
                    name,
                    COALESCE(description, ''),
                    COALESCE(version, '0.1.0'),
                    COALESCE(config_schema, '{}'),
                    COALESCE(dag_json, '{"nodes":[],"edges":[]}')
                FROM recipes
                WHERE name = ?1
                "#,
                [name],
                |row| {
                    Ok(RecipeDetailRecord {
                        name: row.get(0)?,
                        description: row.get(1)?,
                        version: row.get(2)?,
                        config_schema: parse_json_column(&row.get::<_, String>(3)?, "config_schema")
                            .map_err(|error| {
                                rusqlite::Error::ToSqlConversionFailure(error.into())
                            })?,
                        dag: parse_json_column(&row.get::<_, String>(4)?, "dag_json").map_err(
                            |error| rusqlite::Error::ToSqlConversionFailure(error.into()),
                        )?,
                    })
                },
            )
            .optional()?;

        Ok(record)
    }

    pub fn insert_run(
        &self,
        run_id: &str,
        recipe_name: &str,
        config_json: &serde_json::Value,
    ) -> AppResult<()> {
        let connection = self.connect()?;

        connection.execute(
            r#"
            INSERT INTO runs (id, recipe_name, config_json, status, started_at)
            VALUES (?1, ?2, ?3, 'running', ?4)
            "#,
            params![
                run_id,
                recipe_name,
                serde_json::to_string(config_json)?,
                Utc::now().to_rfc3339()
            ],
        )?;

        Ok(())
    }

    pub fn persist_event(&self, payload: &Value) -> AppResult<()> {
        let connection = self.connect()?;
        let event_type = payload
            .get("type")
            .and_then(Value::as_str)
            .unwrap_or("unknown");
        let run_id = payload
            .get("run_id")
            .and_then(Value::as_str)
            .unwrap_or_default();
        let node_id = payload
            .get("node_id")
            .and_then(Value::as_str)
            .map(ToString::to_string);
        let timestamp = payload
            .get("timestamp")
            .and_then(Value::as_str)
            .map(ToString::to_string)
            .unwrap_or_else(|| Utc::now().to_rfc3339());
        let payload_json = serde_json::to_string(payload)?;

        connection.execute(
            r#"
            INSERT INTO run_events (run_id, node_id, event_type, timestamp, payload_json)
            VALUES (?1, ?2, ?3, ?4, ?5)
            "#,
            params![run_id, node_id, event_type, timestamp, payload_json],
        )?;

        match event_type {
            "node_started" => {
                connection.execute(
                    r#"
                    INSERT INTO run_nodes (run_id, node_id, status, progress, message, started_at)
                    VALUES (?1, ?2, 'running', 0.0, NULL, ?3)
                    ON CONFLICT(run_id, node_id) DO UPDATE SET
                        status = 'running',
                        started_at = excluded.started_at
                    "#,
                    params![run_id, node_id, timestamp],
                )?;
            }
            "node_progress" => {
                let progress = payload
                    .get("progress")
                    .and_then(Value::as_f64)
                    .unwrap_or(0.0);
                let message = payload
                    .get("message")
                    .and_then(Value::as_str)
                    .unwrap_or_default();

                connection.execute(
                    r#"
                    INSERT INTO run_nodes (run_id, node_id, status, progress, message)
                    VALUES (?1, ?2, 'running', ?3, ?4)
                    ON CONFLICT(run_id, node_id) DO UPDATE SET
                        status = 'running',
                        progress = excluded.progress,
                        message = excluded.message
                    "#,
                    params![run_id, node_id, progress, message],
                )?;
            }
            "node_log" => {
                let message = payload
                    .get("message")
                    .and_then(Value::as_str)
                    .unwrap_or_default();
                connection.execute(
                    "UPDATE run_nodes SET message = ?3 WHERE run_id = ?1 AND node_id = ?2",
                    params![run_id, node_id, message],
                )?;
            }
            "node_completed" => {
                let duration_ms = payload.get("duration_ms").and_then(Value::as_i64);
                let summary_json = payload.get("summary").map(Value::to_string);

                connection.execute(
                    r#"
                    INSERT INTO run_nodes (run_id, node_id, status, progress, completed_at, duration_ms, summary_json)
                    VALUES (?1, ?2, 'completed', 1.0, ?3, ?4, ?5)
                    ON CONFLICT(run_id, node_id) DO UPDATE SET
                        status = 'completed',
                        progress = 1.0,
                        completed_at = excluded.completed_at,
                        duration_ms = excluded.duration_ms,
                        summary_json = excluded.summary_json
                    "#,
                    params![run_id, node_id, timestamp, duration_ms, summary_json],
                )?;
            }
            "node_failed" => {
                let error = payload
                    .get("error")
                    .and_then(Value::as_str)
                    .unwrap_or_default();
                connection.execute(
                    r#"
                    INSERT INTO run_nodes (run_id, node_id, status, completed_at, error)
                    VALUES (?1, ?2, 'failed', ?3, ?4)
                    ON CONFLICT(run_id, node_id) DO UPDATE SET
                        status = 'failed',
                        completed_at = excluded.completed_at,
                        error = excluded.error
                    "#,
                    params![run_id, node_id, timestamp, error],
                )?;
            }
            "node_skipped" => {
                let message = payload
                    .get("message")
                    .and_then(Value::as_str)
                    .unwrap_or_default();
                connection.execute(
                    r#"
                    INSERT INTO run_nodes (run_id, node_id, status, message, completed_at)
                    VALUES (?1, ?2, 'skipped', ?3, ?4)
                    ON CONFLICT(run_id, node_id) DO UPDATE SET
                        status = 'skipped',
                        message = excluded.message,
                        completed_at = excluded.completed_at
                    "#,
                    params![run_id, node_id, message, timestamp],
                )?;
            }
            "run_completed" => {
                let summary_json = payload.get("summary").map(Value::to_string);
                connection.execute(
                    r#"
                    UPDATE runs
                    SET status = 'completed', completed_at = ?2, summary_json = ?3, error = NULL
                    WHERE id = ?1
                    "#,
                    params![run_id, timestamp, summary_json],
                )?;
            }
            "run_failed" => {
                let error = payload
                    .get("error")
                    .and_then(Value::as_str)
                    .unwrap_or_default();
                connection.execute(
                    r#"
                    UPDATE runs
                    SET status = 'failed', completed_at = ?2, error = ?3
                    WHERE id = ?1
                    "#,
                    params![run_id, timestamp, error],
                )?;
            }
            _ => {}
        }

        Ok(())
    }

    pub fn run_status(&self, run_id: &str) -> AppResult<Option<String>> {
        let connection = self.connect()?;
        let status = connection
            .query_row("SELECT status FROM runs WHERE id = ?1", [run_id], |row| {
                row.get(0)
            })
            .optional()?;

        Ok(status)
    }

    pub fn get_run(&self, run_id: &str) -> AppResult<Option<RunRecord>> {
        let connection = self.connect()?;
        let mut run = connection
            .query_row(
                r#"
                SELECT id, recipe_name, status, started_at, completed_at, error
                FROM runs
                WHERE id = ?1
                "#,
                [run_id],
                |row| {
                    Ok(RunRecord {
                        id: row.get(0)?,
                        recipe_name: row.get(1)?,
                        status: row.get(2)?,
                        started_at: row.get(3)?,
                        completed_at: row.get(4)?,
                        error: row.get(5)?,
                        nodes: Vec::new(),
                    })
                },
            )
            .optional()?;

        let Some(ref mut run_record) = run else {
            return Ok(None);
        };

        let mut statement = connection.prepare(
            r#"
            SELECT
                node_id,
                status,
                COALESCE(progress, 0.0),
                message,
                started_at,
                completed_at,
                duration_ms,
                summary_json,
                error
            FROM run_nodes
            WHERE run_id = ?1
            ORDER BY node_id ASC
            "#,
        )?;

        let rows = statement.query_map([run_id], |row| {
            let summary_json: Option<String> = row.get(7)?;
            Ok(RunNodeRecord {
                node_id: row.get(0)?,
                status: row.get(1)?,
                progress: row.get(2)?,
                message: row.get(3)?,
                started_at: row.get(4)?,
                completed_at: row.get(5)?,
                duration_ms: row.get(6)?,
                summary: summary_json
                    .as_deref()
                    .map(|value| parse_json_column(value, "summary_json"))
                    .transpose()
                    .map_err(|error| rusqlite::Error::ToSqlConversionFailure(error.into()))?,
                error: row.get(8)?,
            })
        })?;

        run_record.nodes = rows.collect::<Result<Vec<_>, _>>()?;
        Ok(run)
    }

    pub fn get_run_events(&self, run_id: &str, node_id: Option<&str>) -> AppResult<Vec<Value>> {
        let connection = self.connect()?;
        let mut statement = match node_id {
            Some(_) => connection.prepare(
                r#"
                SELECT payload_json
                FROM run_events
                WHERE run_id = ?1 AND node_id = ?2
                ORDER BY id ASC
                "#,
            )?,
            None => connection.prepare(
                r#"
                SELECT payload_json
                FROM run_events
                WHERE run_id = ?1
                ORDER BY id ASC
                "#,
            )?,
        };

        let values = match node_id {
            Some(node) => statement
                .query_map(params![run_id, node], |row| {
                    let payload_json: String = row.get(0)?;
                    parse_json_column(&payload_json, "payload_json")
                        .map_err(|error| rusqlite::Error::ToSqlConversionFailure(error.into()))
                })?
                .collect::<Result<Vec<_>, _>>()?,
            None => statement
                .query_map([run_id], |row| {
                    let payload_json: String = row.get(0)?;
                    parse_json_column(&payload_json, "payload_json")
                        .map_err(|error| rusqlite::Error::ToSqlConversionFailure(error.into()))
                })?
                .collect::<Result<Vec<_>, _>>()?,
        };

        Ok(values)
    }

    fn connect(&self) -> AppResult<Connection> {
        Ok(Connection::open(&self.path)?)
    }
}

fn parse_json_column(value: &str, column_name: &str) -> AnyhowResult<Value> {
    serde_json::from_str(value)
        .with_context(|| format!("failed to parse {column_name} as JSON: {value}"))
}

#[cfg(test)]
mod tests {
    use std::fs;

    use serde_json::{json, Value};
    use uuid::Uuid;

    use super::Database;

    #[test]
    fn database_persists_run_completion() {
        let db_path = std::env::temp_dir().join(format!("atlas-weave-{}.db", Uuid::new_v4()));
        let wal_path = db_path.with_extension("db-wal");
        let shm_path = db_path.with_extension("db-shm");
        let database = Database::new(db_path.clone()).expect("database should initialize");

        database.initialize().expect("schema should be created");
        database
            .upsert_recipe(
                "test_echo",
                "test",
                "0.1.0",
                std::path::Path::new("python/recipes/test_echo"),
                "{}",
                r#"{"nodes":[],"edges":[]}"#,
            )
            .expect("recipe should be stored");
        database
            .insert_run("run-1", "test_echo", &json!({}))
            .expect("run should insert");
        database
            .persist_event(&json!({
                "type": "node_started",
                "run_id": "run-1",
                "node_id": "echo_agent",
                "timestamp": "2026-03-16T00:00:00Z"
            }))
            .expect("node start should persist");
        database
            .persist_event(&json!({
                "type": "run_completed",
                "run_id": "run-1",
                "timestamp": "2026-03-16T00:00:10Z",
                "summary": {
                    "messages_emitted": 10
                }
            }))
            .expect("run completion should persist");

        let status = database
            .run_status("run-1")
            .expect("query should succeed")
            .expect("run should exist");

        assert_eq!(status, "completed");

        let _ = fs::remove_file(db_path);
        let _ = fs::remove_file(wal_path);
        let _ = fs::remove_file(shm_path);
    }

    #[test]
    fn database_persists_skipped_nodes() {
        let db_path = std::env::temp_dir().join(format!("atlas-weave-{}.db", Uuid::new_v4()));
        let wal_path = db_path.with_extension("db-wal");
        let shm_path = db_path.with_extension("db-shm");
        let database = Database::new(db_path.clone()).expect("database should initialize");

        database.initialize().expect("schema should be created");
        database
            .upsert_recipe(
                "test_pipeline",
                "test",
                "0.1.0",
                std::path::Path::new("python/recipes/test_pipeline"),
                r#"{"fail_b":{"type":"boolean","default":false}}"#,
                r#"{"nodes":[],"edges":[]}"#,
            )
            .expect("recipe should be stored");
        database
            .insert_run("run-2", "test_pipeline", &json!({"fail_b": true}))
            .expect("run should insert");
        database
            .persist_event(&json!({
                "type": "node_skipped",
                "run_id": "run-2",
                "node_id": "validate_agent",
                "timestamp": "2026-03-16T00:00:10Z",
                "message": "Skipped because dependency transform_agent failed"
            }))
            .expect("node skip should persist");

        let connection = database.connect().expect("database should open");
        let status: String = connection
            .query_row(
                "SELECT status FROM run_nodes WHERE run_id = ?1 AND node_id = ?2",
                ["run-2", "validate_agent"],
                |row| row.get(0),
            )
            .expect("node should exist");

        assert_eq!(status, "skipped");

        let _ = fs::remove_file(db_path);
        let _ = fs::remove_file(wal_path);
        let _ = fs::remove_file(shm_path);
    }

    #[test]
    fn database_reads_recipe_detail_and_run_events() {
        let db_path = std::env::temp_dir().join(format!("atlas-weave-{}.db", Uuid::new_v4()));
        let wal_path = db_path.with_extension("db-wal");
        let shm_path = db_path.with_extension("db-shm");
        let database = Database::new(db_path.clone()).expect("database should initialize");

        database.initialize().expect("schema should be created");
        database
            .upsert_recipe(
                "test_pipeline",
                "pipeline",
                "0.2.0",
                std::path::Path::new("python/recipes/test_pipeline"),
                r#"{"type":"object","properties":{"fail_b":{"type":"boolean"}}}"#,
                r#"{"nodes":[{"id":"a","label":"A","description":"first"}],"edges":[]}"#,
            )
            .expect("recipe should be stored");
        database
            .insert_run("run-2", "test_pipeline", &json!({}))
            .expect("run should insert");
        database
            .persist_event(&json!({
                "type": "node_started",
                "run_id": "run-2",
                "node_id": "source_agent",
                "timestamp": "2026-03-16T00:00:00Z"
            }))
            .expect("start should persist");
        database
            .persist_event(&json!({
                "type": "node_log",
                "run_id": "run-2",
                "node_id": "source_agent",
                "level": "info",
                "message": "hello",
                "timestamp": "2026-03-16T00:00:01Z"
            }))
            .expect("log should persist");

        let recipe = database
            .get_recipe_detail("test_pipeline")
            .expect("query should succeed")
            .expect("recipe should exist");
        let run = database
            .get_run("run-2")
            .expect("query should succeed")
            .expect("run should exist");
        let events = database
            .get_run_events("run-2", Some("source_agent"))
            .expect("events should load");

        assert_eq!(recipe.name, "test_pipeline");
        assert_eq!(recipe.version, "0.2.0");
        assert_eq!(run.recipe_name, "test_pipeline");
        assert_eq!(run.nodes.len(), 1);
        assert_eq!(events.len(), 2);
        assert_eq!(events[0].get("type").and_then(Value::as_str), Some("node_started"));
        assert_eq!(events[1].get("message").and_then(Value::as_str), Some("hello"));

        let _ = fs::remove_file(db_path);
        let _ = fs::remove_file(wal_path);
        let _ = fs::remove_file(shm_path);
    }
}
