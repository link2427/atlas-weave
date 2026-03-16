use serde::Serialize;
use tauri::{AppHandle, State};
use uuid::Uuid;

use crate::{services::sidecar, AppResult, AppState};

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct StartRunResponse {
    pub run_id: String,
    pub status: String,
}

#[tauri::command]
pub async fn start_run(
    app: AppHandle,
    state: State<'_, AppState>,
    recipe: String,
) -> AppResult<StartRunResponse> {
    let run_id = Uuid::new_v4().to_string();
    let database = state.database.as_ref().clone();
    let run_id_for_task = run_id.clone();

    database.insert_run(&run_id, &recipe)?;
    tokio::spawn(async move {
        let _ = sidecar::spawn_run(app, database, recipe, run_id_for_task).await;
    });

    Ok(StartRunResponse {
        run_id,
        status: "running".to_string(),
    })
}
