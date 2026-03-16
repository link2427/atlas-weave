use serde::Serialize;
use tauri::State;

use crate::{AppResult, AppState};

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct RecipeDto {
    pub name: String,
    pub description: String,
    pub version: String,
}

#[tauri::command]
pub fn list_recipes(state: State<'_, AppState>) -> AppResult<Vec<RecipeDto>> {
    let recipes = state.database.list_recipes()?;

    Ok(recipes
        .into_iter()
        .map(|recipe| RecipeDto {
            name: recipe.name,
            description: recipe.description,
            version: recipe.version,
        })
        .collect())
}
