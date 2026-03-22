use std::{collections::HashMap, process::Stdio, sync::Arc};

use anyhow::{anyhow, Context};
use serde_json::{json, Value};
use tauri::AppHandle;
use tokio::{
    io::{AsyncBufReadExt, AsyncWriteExt, BufReader},
    process::Command,
    sync::Mutex,
};

use crate::{db::Database, AppResult};

use super::{
    event_bus, paths,
    run_manager::{ActiveRunHandle, RunManager},
};

pub async fn spawn_run(
    app: AppHandle,
    database: Database,
    run_manager: Arc<RunManager>,
    recipe: String,
    run_id: String,
    config: Value,
    env_vars: HashMap<String, String>,
    resume_state: Option<HashMap<String, String>>,
) -> AppResult<()> {
    let repo_root = paths::repo_root()?;
    let python_dir = repo_root.join("python");
    let atlas_data_dir = repo_root.join(".atlas-weave");

    let mut command = Command::new("python");
    command
        .arg("-u")
        .arg("-m")
        .arg("atlas_weave.runner")
        .current_dir(&repo_root)
        .env(
            "ATLAS_WEAVE_DATA_DIR",
            atlas_data_dir.to_string_lossy().to_string(),
        )
        .env("PYTHONPATH", python_dir.to_string_lossy().to_string())
        .env("PYTHONUNBUFFERED", "1")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());

    for (key, value) in env_vars {
        command.env(key, value);
    }

    let mut child = command
        .spawn()
        .with_context(|| format!("failed to spawn Python runner for recipe {recipe}"))?;

    let mut stdin = child
        .stdin
        .take()
        .ok_or_else(|| anyhow!("python runner stdin pipe was not available"))?;
    let stdout = child
        .stdout
        .take()
        .ok_or_else(|| anyhow!("python runner stdout pipe was not available"))?;
    let stderr = child
        .stderr
        .take()
        .ok_or_else(|| anyhow!("python runner stderr pipe was not available"))?;
    let child = Arc::new(Mutex::new(child));

    let mut start_cmd = json!({
        "type": "start_run",
        "run_id": run_id,
        "recipe": recipe,
        "config": config,
    });
    if let Some(state) = resume_state {
        start_cmd["resume_state"] = json!(state);
    }
    let start_command = serde_json::to_string(&start_cmd)?;
    stdin.write_all(start_command.as_bytes()).await?;
    stdin.write_all(b"\n").await?;
    stdin.flush().await?;

    run_manager
        .register(run_id.clone(), ActiveRunHandle::new(child.clone(), stdin))
        .await;

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
                    let _ =
                        event_bus::publish_payload(&app_for_stdout, &database_for_stdout, payload);
                }
                Err(error) => {
                    let _ = event_bus::publish_invalid_json(
                        &app_for_stdout,
                        &database_for_stdout,
                        &run_id_for_stdout,
                        &error.to_string(),
                    );
                }
            }
        }
    });

    let app_for_stderr = app.clone();
    let database_for_stderr = database.clone();
    let run_id_for_stderr = run_id.clone();
    tokio::spawn(async move {
        let mut lines = BufReader::new(stderr).lines();
        while let Ok(Some(line)) = lines.next_line().await {
            if !line.trim().is_empty() {
                let _ = event_bus::publish_stderr(
                    &app_for_stderr,
                    &database_for_stderr,
                    &run_id_for_stderr,
                    line.trim(),
                );
            }
        }
    });

    let app_for_exit = app.clone();
    let database_for_exit = database.clone();
    let run_manager_for_exit = run_manager.clone();
    let run_id_for_exit = run_id.clone();
    tokio::spawn(async move {
        let wait_result = {
            let mut child_guard = child.lock().await;
            child_guard.wait().await
        };

        run_manager_for_exit.cleanup(&run_id_for_exit).await;

        match wait_result {
            Ok(status) if !status.success() => {
                if !matches!(
                    database_for_exit.run_status(&run_id_for_exit),
                    Ok(Some(current))
                        if current == "failed"
                            || current == "completed"
                            || current == "cancelled"
                ) {
                    let _ = event_bus::publish_payload(
                        &app_for_exit,
                        &database_for_exit,
                        json!({
                            "type": "run_failed",
                            "run_id": run_id_for_exit,
                            "error": format!("Python process exited with status {status}"),
                        }),
                    );
                }
            }
            Ok(_) => {}
            Err(error) => {
                let _ = event_bus::publish_payload(
                    &app_for_exit,
                    &database_for_exit,
                    json!({
                        "type": "run_failed",
                        "run_id": run_id_for_exit,
                        "error": format!("failed waiting for Python process: {error}"),
                    }),
                );
            }
        }
    });

    Ok(())
}
