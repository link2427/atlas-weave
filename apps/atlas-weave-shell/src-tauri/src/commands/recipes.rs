use serde::Serialize;
use serde_json::Value;
use tauri::State;

use crate::{AppError, AppResult, AppState};

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct RecipeDto {
    pub name: String,
    pub description: String,
    pub version: String,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct RecipeDetailDto {
    pub name: String,
    pub description: String,
    pub version: String,
    pub config_schema: Value,
    pub dag: Value,
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

#[tauri::command]
pub fn get_recipe_detail(state: State<'_, AppState>, name: String) -> AppResult<RecipeDetailDto> {
    let recipe = state
        .database
        .get_recipe_detail(&name)?
        .ok_or_else(|| AppError::Message(format!("recipe not found: {name}")))?;

    Ok(RecipeDetailDto {
        name: recipe.name,
        description: recipe.description,
        version: recipe.version,
        config_schema: recipe.config_schema,
        dag: recipe.dag,
    })
}
