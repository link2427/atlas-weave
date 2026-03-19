use serde_json::{json, Value};
use tauri::{AppHandle, Emitter};

use crate::{db::Database, AppResult};

pub fn publish_payload(app: &AppHandle, database: &Database, payload: Value) -> AppResult<()> {
    database.persist_event(&payload)?;
    app.emit("atlas-weave:event", payload)?;
    Ok(())
}

pub fn publish_invalid_json(
    app: &AppHandle,
    database: &Database,
    run_id: &str,
    error: &str,
) -> AppResult<()> {
    publish_payload(
        app,
        database,
        json!({
            "type": "run_failed",
            "run_id": run_id,
            "error": format!("invalid JSON event from Python: {error}")
        }),
    )
}

pub fn publish_stderr(
    app: &AppHandle,
    database: &Database,
    run_id: &str,
    message: &str,
) -> AppResult<()> {
    let level = parse_stderr_level(message);
    publish_payload(
        app,
        database,
        json!({
            "type": "node_log",
            "run_id": run_id,
            "node_id": "python",
            "level": level,
            "message": message
        }),
    )
}

/// Extract the Python log level from a stderr line.
///
/// Python's default logging format is: `YYYY-MM-DD HH:MM:SS,mmm LEVEL name: message`
/// so the level token is the third whitespace-separated word.
fn parse_stderr_level(message: &str) -> &'static str {
    let mut parts = message.split_whitespace();
    // skip date and time
    if parts.next().is_none() {
        return "stderr";
    }
    if parts.next().is_none() {
        return "stderr";
    }
    match parts.next() {
        Some("DEBUG") => "debug",
        Some("INFO") => "info",
        Some("WARNING") => "warning",
        Some("WARN") => "warning",
        Some("ERROR") => "error",
        Some("CRITICAL") => "error",
        _ => "stderr",
    }
}
