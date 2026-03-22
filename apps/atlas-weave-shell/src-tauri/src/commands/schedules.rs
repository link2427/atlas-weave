use serde::Serialize;
use serde_json::Value;
use tauri::State;
use uuid::Uuid;

use crate::db::ScheduleRecord;
use crate::services::scheduler::compute_next_fire;
use crate::{AppError, AppResult, AppState};

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ScheduleDto {
    pub id: String,
    pub recipe_name: String,
    pub cron_expression: String,
    pub config: Option<Value>,
    pub enabled: bool,
    pub last_run_id: Option<String>,
    pub next_run_at: Option<String>,
    pub created_at: String,
}

fn record_to_dto(record: ScheduleRecord) -> ScheduleDto {
    let config = record
        .config_json
        .as_deref()
        .and_then(|json| serde_json::from_str(json).ok());

    ScheduleDto {
        id: record.id,
        recipe_name: record.recipe_name,
        cron_expression: record.cron_expression,
        config,
        enabled: record.enabled,
        last_run_id: record.last_run_id,
        next_run_at: record.next_run_at,
        created_at: record.created_at,
    }
}

fn validate_cron(expression: &str) -> AppResult<()> {
    croner::Cron::new(expression)
        .parse()
        .map_err(|e| AppError::Message(format!("invalid cron expression: {e}")))?;
    Ok(())
}

#[tauri::command]
pub fn create_schedule(
    state: State<'_, AppState>,
    recipe_name: String,
    cron_expression: String,
    config: Option<Value>,
) -> AppResult<ScheduleDto> {
    validate_cron(&cron_expression)?;

    let database = state.database.as_ref();

    // Verify recipe exists
    database
        .get_recipe_detail(&recipe_name)?
        .ok_or_else(|| AppError::Message(format!("recipe not found: {recipe_name}")))?;

    // Enforce one schedule per recipe
    let existing = database.get_schedules(Some(&recipe_name))?;
    if !existing.is_empty() {
        return Err(AppError::Message(format!(
            "a schedule already exists for recipe '{recipe_name}'"
        )));
    }

    let id = Uuid::new_v4().to_string();
    let next_run_at = compute_next_fire(&cron_expression);
    let config_json = config
        .as_ref()
        .map(serde_json::to_string)
        .transpose()?;

    database.insert_schedule(
        &id,
        &recipe_name,
        &cron_expression,
        config_json.as_deref(),
        next_run_at.as_deref(),
    )?;

    let record = database
        .get_schedule(&id)?
        .ok_or_else(|| AppError::Message("failed to read created schedule".to_string()))?;

    Ok(record_to_dto(record))
}

#[tauri::command]
pub fn update_schedule(
    state: State<'_, AppState>,
    id: String,
    cron_expression: Option<String>,
    config: Option<Value>,
    enabled: Option<bool>,
) -> AppResult<ScheduleDto> {
    let database = state.database.as_ref();

    database
        .get_schedule(&id)?
        .ok_or_else(|| AppError::Message(format!("schedule not found: {id}")))?;

    if let Some(ref cron) = cron_expression {
        validate_cron(cron)?;
    }

    let config_json = config
        .as_ref()
        .map(serde_json::to_string)
        .transpose()?;

    // Determine the effective cron expression for recomputing next_run_at
    let effective_cron = match &cron_expression {
        Some(c) => c.clone(),
        None => {
            database
                .get_schedule(&id)?
                .map(|s| s.cron_expression)
                .unwrap_or_default()
        }
    };

    let next_run_at = compute_next_fire(&effective_cron);

    database.update_schedule(
        &id,
        cron_expression.as_deref(),
        config_json.as_ref().map(|s| Some(s.as_str())),
        enabled,
        Some(next_run_at.as_deref()),
    )?;

    let record = database
        .get_schedule(&id)?
        .ok_or_else(|| AppError::Message("failed to read updated schedule".to_string()))?;

    Ok(record_to_dto(record))
}

#[tauri::command]
pub fn delete_schedule(state: State<'_, AppState>, id: String) -> AppResult<()> {
    state.database.delete_schedule(&id)?;
    Ok(())
}

#[tauri::command]
pub fn get_schedules(
    state: State<'_, AppState>,
    recipe_name: Option<String>,
) -> AppResult<Vec<ScheduleDto>> {
    let records = state
        .database
        .get_schedules(recipe_name.as_deref())?;
    Ok(records.into_iter().map(record_to_dto).collect())
}
