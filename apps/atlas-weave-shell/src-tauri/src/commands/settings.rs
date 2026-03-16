use std::collections::HashMap;

use serde::Serialize;
use tauri::State;

use crate::{AppResult, AppState};

#[derive(Debug, Clone, Serialize)]
pub struct CredentialPresenceDto {
    pub present: bool,
}

#[tauri::command]
pub fn get_credentials(
    state: State<'_, AppState>,
    keys: Option<Vec<String>>,
) -> AppResult<HashMap<String, CredentialPresenceDto>> {
    let keys = keys.unwrap_or_default();
    let presence = state.credentials.presence(&keys)?;

    Ok(presence
        .into_iter()
        .map(|(key, present)| (key, CredentialPresenceDto { present }))
        .collect())
}

#[tauri::command]
pub fn save_credentials(
    state: State<'_, AppState>,
    values: HashMap<String, Option<String>>,
) -> AppResult<()> {
    state.credentials.save(&values)
}
