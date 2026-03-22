use serde_json::{json, Value};
use tauri::{AppHandle, Emitter};
use tauri_plugin_notification::NotificationExt;

use crate::{db::Database, AppResult};

pub fn publish_payload(app: &AppHandle, database: &Database, payload: Value) -> AppResult<()> {
    database.persist_event(&payload)?;
    maybe_notify(app, &payload);
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

fn maybe_notify(app: &AppHandle, payload: &Value) {
    let event_type = payload.get("type").and_then(Value::as_str).unwrap_or("");
    let run_id = payload.get("run_id").and_then(Value::as_str).unwrap_or("");
    let short_id = &run_id[..run_id.len().min(8)];

    let (title, body) = match event_type {
        "run_completed" => (
            "Run Complete",
            format!("Run {short_id}… finished successfully"),
        ),
        "run_failed" => {
            let err = payload
                .get("error")
                .and_then(Value::as_str)
                .unwrap_or("Unknown error");
            ("Run Failed", format!("Run {short_id}…: {err}"))
        }
        "run_cancelled" => (
            "Run Cancelled",
            format!("Run {short_id}… was cancelled"),
        ),
        _ => return,
    };

    let _ = app
        .notification()
        .builder()
        .title(format!("Atlas Weave: {title}"))
        .body(body)
        .show();
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
