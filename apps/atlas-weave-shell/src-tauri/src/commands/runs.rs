use serde::Serialize;
use serde_json::{json, Value};
use tauri::{AppHandle, State};
use uuid::Uuid;

use crate::{services::sidecar, AppError, AppResult, AppState};

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct StartRunResponse {
    pub run_id: String,
    pub status: String,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct RunNodeDto {
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

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct RunDetailDto {
    pub id: String,
    pub recipe_name: String,
    pub status: String,
    pub started_at: Option<String>,
    pub completed_at: Option<String>,
    pub error: Option<String>,
    pub nodes: Vec<RunNodeDto>,
}

#[tauri::command]
pub async fn start_run(
    app: AppHandle,
    state: State<'_, AppState>,
    recipe: String,
    config: Option<Value>,
) -> AppResult<StartRunResponse> {
    let run_id = Uuid::new_v4().to_string();
    let database = state.database.as_ref().clone();
    let run_id_for_task = run_id.clone();
    let run_config = config.unwrap_or_else(|| json!({}));

    database.insert_run(&run_id, &recipe, &run_config)?;
    tokio::spawn(async move {
        let _ = sidecar::spawn_run(app, database, recipe, run_id_for_task, run_config).await;
    });

    Ok(StartRunResponse {
        run_id,
        status: "running".to_string(),
    })
}

#[tauri::command]
pub fn get_run(state: State<'_, AppState>, run_id: String) -> AppResult<RunDetailDto> {
    let run = state
        .database
        .get_run(&run_id)?
        .ok_or_else(|| AppError::Message(format!("run not found: {run_id}")))?;

    Ok(RunDetailDto {
        id: run.id,
        recipe_name: run.recipe_name,
        status: run.status,
        started_at: run.started_at,
        completed_at: run.completed_at,
        error: run.error,
        nodes: run
            .nodes
            .into_iter()
            .map(|node| RunNodeDto {
                node_id: node.node_id,
                status: node.status,
                progress: node.progress,
                message: node.message,
                started_at: node.started_at,
                completed_at: node.completed_at,
                duration_ms: node.duration_ms,
                summary: node.summary,
                error: node.error,
            })
            .collect(),
    })
}

#[tauri::command]
pub fn get_run_events(
    state: State<'_, AppState>,
    run_id: String,
    node_id: Option<String>,
) -> AppResult<Vec<Value>> {
    state.database.get_run_events(&run_id, node_id.as_deref())
}
