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
    publish_payload(
        app,
        database,
        json!({
            "type": "node_log",
            "run_id": run_id,
            "node_id": "python",
            "level": "error",
            "message": message
        }),
    )
}
