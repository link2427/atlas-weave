use std::process::Stdio;

use anyhow::{anyhow, Context};
use serde_json::{json, Value};
use tauri::{AppHandle, Emitter};
use tokio::{
    io::{AsyncBufReadExt, AsyncReadExt, BufReader},
    process::Command,
};

use crate::{db::Database, AppResult};

use super::paths;

pub async fn spawn_run(
    app: AppHandle,
    database: Database,
    recipe: String,
    run_id: String,
    config: Value,
) -> AppResult<()> {
    let repo_root = paths::repo_root()?;
    let python_dir = repo_root.join("python");
    let config_json = serde_json::to_string(&config)?;

    let mut command = Command::new("python");
    command
        .arg("-u")
        .arg("-m")
        .arg("atlas_weave.runner")
        .arg("--recipe")
        .arg(&recipe)
        .arg("--run-id")
        .arg(&run_id)
        .arg("--config-json")
        .arg(config_json)
        .current_dir(&repo_root)
        .env("PYTHONPATH", python_dir.to_string_lossy().to_string())
        .env("PYTHONUNBUFFERED", "1")
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());

    let mut child = command
        .spawn()
        .with_context(|| format!("failed to spawn Python runner for recipe {recipe}"))?;

    let stdout = child
        .stdout
        .take()
        .ok_or_else(|| anyhow!("python runner stdout pipe was not available"))?;
    let stderr = child
        .stderr
        .take()
        .ok_or_else(|| anyhow!("python runner stderr pipe was not available"))?;

    let app_for_stdout = app.clone();
    let database_for_stdout = database.clone();
    let run_id_for_stdout = run_id.clone();
    tokio::spawn(async move {
        let mut lines = BufReader::new(stdout).lines();

        while let Ok(Some(line)) = lines.next_line().await {
            if line.trim().is_empty() {
                continue;
            }

            match serde_json::from_str::<Value>(&line) {
                Ok(payload) => {
                    if let Err(error) = database_for_stdout.persist_event(&payload) {
                        eprintln!("failed to persist event: {error}");
                    }

                    if let Err(error) = app_for_stdout.emit("atlas-weave:event", payload) {
                        eprintln!("failed to emit tauri event: {error}");
                    }
                }
                Err(error) => {
                    let payload = json!({
                        "type": "run_failed",
                        "run_id": run_id_for_stdout,
                        "error": format!("invalid JSON event from Python: {error}"),
                    });
                    let _ = database_for_stdout.persist_event(&payload);
                    let _ = app_for_stdout.emit("atlas-weave:event", payload);
                }
            }
        }
    });

    let app_for_stderr = app.clone();
    let database_for_stderr = database.clone();
    let run_id_for_stderr = run_id.clone();
    tokio::spawn(async move {
        let mut stderr_output = String::new();
        let mut reader = BufReader::new(stderr);
        let _ = reader.read_to_string(&mut stderr_output).await;

        if !stderr_output.trim().is_empty() {
            let payload = json!({
                "type": "node_log",
                "run_id": run_id_for_stderr,
                "node_id": "python",
                "level": "error",
                "message": stderr_output.trim(),
            });
            let _ = database_for_stderr.persist_event(&payload);
            let _ = app_for_stderr.emit("atlas-weave:event", payload);
        }
    });

    let app_for_exit = app.clone();
    let database_for_exit = database.clone();
    tokio::spawn(async move {
        match child.wait().await {
            Ok(status) if !status.success() => {
                if !matches!(
                    database_for_exit.run_status(&run_id),
                    Ok(Some(current)) if current == "failed" || current == "completed"
                ) {
                    let payload = json!({
                        "type": "run_failed",
                        "run_id": run_id,
                        "error": format!("Python process exited with status {status}"),
                    });
                    let _ = database_for_exit.persist_event(&payload);
                    let _ = app_for_exit.emit("atlas-weave:event", payload);
                }
            }
            Ok(_) => {}
            Err(error) => {
                let payload = json!({
                    "type": "run_failed",
                    "run_id": run_id,
                    "error": format!("failed waiting for Python process: {error}"),
                });
                let _ = database_for_exit.persist_event(&payload);
                let _ = app_for_exit.emit("atlas-weave:event", payload);
            }
        }
    });

    Ok(())
}
