use std::{collections::HashMap, sync::Arc, time::Duration};

use serde::Serialize;
use serde_json::{json, Map, Value};
use tauri::{AppHandle, State};
use tokio::time::sleep;
use uuid::Uuid;

use crate::{
    db::{Database, Paginated},
    services::{credentials::CredentialStore, event_bus, run_manager::RunManager, sidecar},
    AppError, AppResult, AppState,
};

const DEFAULT_PAGE: u32 = 1;
const DEFAULT_PAGE_SIZE: u32 = 200;
const HISTORY_PAGE_SIZE: u32 = 20;
const CANCEL_KILL_TIMEOUT: Duration = Duration::from_secs(2);

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct StartRunResponse {
    pub run_id: String,
    pub status: String,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct CancelRunResponse {
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
pub struct RunGraphNodeDto {
    pub id: String,
    pub label: String,
    pub description: String,
    pub kind: String,
    pub parent_id: Option<String>,
    pub group_key: Option<String>,
    pub collapsed_by_default: bool,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct RunGraphDto {
    pub nodes: Vec<RunGraphNodeDto>,
    pub edges: Vec<[String; 2]>,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct RunDetailDto {
    pub id: String,
    pub recipe_name: String,
    pub status: String,
    pub started_at: Option<String>,
    pub completed_at: Option<String>,
    pub config: Value,
    pub summary: Option<Value>,
    pub error: Option<String>,
    pub nodes: Vec<RunNodeDto>,
    pub graph: RunGraphDto,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct RunHistoryItemDto {
    pub id: String,
    pub recipe_name: String,
    pub status: String,
    pub started_at: Option<String>,
    pub completed_at: Option<String>,
    pub error: Option<String>,
    pub pending_nodes: i64,
    pub running_nodes: i64,
    pub completed_nodes: i64,
    pub failed_nodes: i64,
    pub skipped_nodes: i64,
    pub cancelled_nodes: i64,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct PaginatedDto<T> {
    pub items: Vec<T>,
    pub total: i64,
    pub page: u32,
    pub page_size: u32,
}

pub async fn trigger_run(
    app: &AppHandle,
    database: &Database,
    run_manager: &Arc<RunManager>,
    credentials: &Arc<CredentialStore>,
    recipe_name: &str,
    config: Option<Value>,
) -> AppResult<String> {
    let run_id = Uuid::new_v4().to_string();
    let recipe_record = database
        .get_recipe_detail(recipe_name)?
        .ok_or_else(|| AppError::Message(format!("recipe not found: {recipe_name}")))?;
    let requested_config = normalize_config_object(config)?;
    let secret_fields = secret_fields(&recipe_record.config_schema);
    let persisted_config = redact_secrets(&requested_config, &secret_fields);
    let required_secret_keys = secret_fields
        .iter()
        .filter(|field| field.required)
        .map(|field| field.name.clone())
        .collect::<Vec<_>>();
    let secret_values = credentials.get_values(
        &secret_fields
            .iter()
            .map(|field| field.name.clone())
            .collect::<Vec<_>>(),
    )?;

    for key in required_secret_keys {
        if !secret_values.contains_key(&key) {
            return Err(AppError::Message(format!(
                "missing required credential in Settings: {key}"
            )));
        }
    }

    let env_vars = secret_values
        .into_iter()
        .map(|(key, value)| (secret_env_var(&key), value))
        .collect::<HashMap<_, _>>();

    database.insert_run(&run_id, recipe_name, &persisted_config)?;
    let app_for_sidecar = app.clone();
    let app_for_event = app.clone();
    let database_clone = database.clone();
    let run_manager_clone = run_manager.clone();
    let recipe_owned = recipe_name.to_string();
    let run_id_for_task = run_id.clone();
    tokio::spawn(async move {
        if let Err(error) = sidecar::spawn_run(
            app_for_sidecar,
            database_clone.clone(),
            run_manager_clone,
            recipe_owned,
            run_id_for_task.clone(),
            requested_config,
            env_vars,
        )
        .await
        {
            let _ = event_bus::publish_payload(
                &app_for_event,
                &database_clone,
                json!({
                    "type": "run_failed",
                    "run_id": run_id_for_task,
                    "error": error.to_string()
                }),
            );
        }
    });

    Ok(run_id)
}

#[tauri::command]
pub async fn start_run(
    app: AppHandle,
    state: State<'_, AppState>,
    recipe: String,
    config: Option<Value>,
) -> AppResult<StartRunResponse> {
    let database = state.database.as_ref().clone();
    let run_manager = state.run_manager.clone();
    let credentials = state.credentials.clone();
    let run_id = trigger_run(&app, &database, &run_manager, &credentials, &recipe, config).await?;
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
    let recipe = state
        .database
        .get_recipe_detail(&run.recipe_name)?
        .ok_or_else(|| AppError::Message(format!("recipe not found: {}", run.recipe_name)))?;
    let graph = merge_run_graph(&recipe.dag, &run);

    Ok(RunDetailDto {
        id: run.id,
        recipe_name: run.recipe_name,
        status: run.status,
        started_at: run.started_at,
        completed_at: run.completed_at,
        config: run.config,
        summary: run.summary,
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
        graph,
    })
}

#[tauri::command]
pub fn get_run_history(
    state: State<'_, AppState>,
    recipe_name: String,
    page: Option<u32>,
    page_size: Option<u32>,
) -> AppResult<PaginatedDto<RunHistoryItemDto>> {
    let history = state.database.get_run_history(
        &recipe_name,
        page.unwrap_or(DEFAULT_PAGE),
        page_size.unwrap_or(HISTORY_PAGE_SIZE),
    )?;
    Ok(map_paginated(history, |item| RunHistoryItemDto {
        id: item.id,
        recipe_name: item.recipe_name,
        status: item.status,
        started_at: item.started_at,
        completed_at: item.completed_at,
        error: item.error,
        pending_nodes: item.pending_nodes,
        running_nodes: item.running_nodes,
        completed_nodes: item.completed_nodes,
        failed_nodes: item.failed_nodes,
        skipped_nodes: item.skipped_nodes,
        cancelled_nodes: item.cancelled_nodes,
    }))
}

#[tauri::command]
pub fn get_run_events(
    state: State<'_, AppState>,
    run_id: String,
    node_id: Option<String>,
    page: Option<u32>,
    page_size: Option<u32>,
) -> AppResult<PaginatedDto<Value>> {
    let events = state.database.get_run_events(
        &run_id,
        node_id.as_deref(),
        page.unwrap_or(DEFAULT_PAGE),
        page_size.unwrap_or(DEFAULT_PAGE_SIZE),
    )?;
    Ok(map_paginated(events, |value| value))
}

#[tauri::command]
pub async fn cancel_run(
    app: AppHandle,
    state: State<'_, AppState>,
    run_id: String,
) -> AppResult<CancelRunResponse> {
    let database = state.database.as_ref().clone();
    let run_manager = state.run_manager.clone();
    let cancelled = run_manager.cancel(&run_id).await?;
    if !cancelled {
        return Err(AppError::Message(format!("run not active: {run_id}")));
    }

    let app_for_kill = app.clone();
    let run_id_for_kill = run_id.clone();
    tokio::spawn(async move {
        sleep(CANCEL_KILL_TIMEOUT).await;
        if run_manager.is_active(&run_id_for_kill).await {
            let _ = run_manager.terminate(&run_id_for_kill).await;
            if matches!(
                database.run_status(&run_id_for_kill),
                Ok(Some(status)) if status == "running"
            ) {
                let _ = event_bus::publish_payload(
                    &app_for_kill,
                    &database,
                    json!({
                        "type": "run_cancelled",
                        "run_id": run_id_for_kill,
                        "message": "Run cancelled after timeout waiting for Python sidecar"
                    }),
                );
            }
        }
    });

    Ok(CancelRunResponse {
        status: "cancelling".to_string(),
    })
}

fn map_paginated<T, U>(value: Paginated<T>, map: impl Fn(T) -> U) -> PaginatedDto<U> {
    PaginatedDto {
        items: value.items.into_iter().map(map).collect(),
        total: value.total,
        page: value.page,
        page_size: value.page_size,
    }
}

#[derive(Debug, Clone)]
struct SecretField {
    name: String,
    required: bool,
}

fn normalize_config_object(config: Option<Value>) -> AppResult<Value> {
    match config {
        Some(Value::Object(map)) => Ok(Value::Object(map)),
        Some(Value::Null) | None => Ok(json!({})),
        _ => Err(AppError::Message(
            "run config must be a JSON object".to_string(),
        )),
    }
}

fn secret_fields(config_schema: &Value) -> Vec<SecretField> {
    let Some(fields) = config_schema.as_object() else {
        return Vec::new();
    };

    fields
        .iter()
        .filter_map(|(name, field)| {
            let secret = field
                .get("secret")
                .and_then(Value::as_bool)
                .unwrap_or(false);
            if !secret {
                return None;
            }

            Some(SecretField {
                name: name.clone(),
                required: field
                    .get("required")
                    .and_then(Value::as_bool)
                    .unwrap_or(false),
            })
        })
        .collect()
}

fn redact_secrets(config: &Value, secret_fields: &[SecretField]) -> Value {
    let Some(map) = config.as_object() else {
        return json!({});
    };
    let secret_names = secret_fields
        .iter()
        .map(|field| field.name.as_str())
        .collect::<Vec<_>>();
    let redacted = map
        .iter()
        .filter(|(key, _)| !secret_names.contains(&key.as_str()))
        .map(|(key, value)| (key.clone(), value.clone()))
        .collect::<Map<String, Value>>();
    Value::Object(redacted)
}

fn secret_env_var(key: &str) -> String {
    key.chars()
        .map(|char| {
            if char.is_ascii_alphanumeric() {
                char.to_ascii_uppercase()
            } else {
                '_'
            }
        })
        .collect()
}

fn merge_run_graph(recipe_dag: &Value, run: &crate::db::RunRecord) -> RunGraphDto {
    let mut nodes: Vec<RunGraphNodeDto> = recipe_dag
        .get("nodes")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .filter_map(|node| {
            Some(RunGraphNodeDto {
                id: node.get("id")?.as_str()?.to_string(),
                label: node
                    .get("label")
                    .and_then(Value::as_str)
                    .unwrap_or_default()
                    .to_string(),
                description: node
                    .get("description")
                    .and_then(Value::as_str)
                    .unwrap_or_default()
                    .to_string(),
                kind: "static".to_string(),
                parent_id: None,
                group_key: None,
                collapsed_by_default: false,
            })
        })
        .collect();

    let mut existing_ids = nodes
        .iter()
        .map(|node| node.id.clone())
        .collect::<std::collections::HashSet<_>>();

    for node in &run.graph_nodes {
        if existing_ids.insert(node.id.clone()) {
            nodes.push(RunGraphNodeDto {
                id: node.id.clone(),
                label: node.label.clone(),
                description: node.description.clone(),
                kind: node.kind.clone(),
                parent_id: node.parent_id.clone(),
                group_key: node.group_key.clone(),
                collapsed_by_default: node.collapsed_by_default,
            });
        }
    }

    let mut edges: Vec<[String; 2]> = recipe_dag
        .get("edges")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .filter_map(|edge| {
            let pair = edge.as_array()?;
            Some([
                pair.first()?.as_str()?.to_string(),
                pair.get(1)?.as_str()?.to_string(),
            ])
        })
        .collect();

    let mut seen_edges = edges
        .iter()
        .map(|pair| (pair[0].clone(), pair[1].clone()))
        .collect::<std::collections::HashSet<_>>();
    for edge in &run.graph_edges {
        if seen_edges.insert((edge.source.clone(), edge.target.clone())) {
            edges.push([edge.source.clone(), edge.target.clone()]);
        }
    }

    RunGraphDto { nodes, edges }
}
