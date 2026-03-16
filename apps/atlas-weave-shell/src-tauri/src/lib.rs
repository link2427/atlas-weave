mod commands;
mod db;
mod services;

use std::sync::Arc;

use commands::{
    recipes::{get_recipe_detail, list_recipes},
    runs::{get_run, get_run_events, start_run},
};
use db::Database;
use serde::Serialize;
use tauri::Manager;
use thiserror::Error;

#[derive(Clone)]
pub struct AppState {
    pub database: Arc<Database>,
}

pub type AppResult<T> = Result<T, AppError>;

#[derive(Debug, Error, Serialize)]
#[serde(tag = "kind", content = "message")]
pub enum AppError {
    #[error("{0}")]
    Message(String),
}

impl From<anyhow::Error> for AppError {
    fn from(value: anyhow::Error) -> Self {
        Self::Message(value.to_string())
    }
}

impl From<std::io::Error> for AppError {
    fn from(value: std::io::Error) -> Self {
        Self::Message(value.to_string())
    }
}

impl From<rusqlite::Error> for AppError {
    fn from(value: rusqlite::Error) -> Self {
        Self::Message(value.to_string())
    }
}

impl From<serde_json::Error> for AppError {
    fn from(value: serde_json::Error) -> Self {
        Self::Message(value.to_string())
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .setup(|app| {
            let repo_root = services::paths::repo_root()?;
            let database = Arc::new(Database::new(
                repo_root.join(".atlas-weave").join("atlas-weave.db"),
            )?);

            database.initialize()?;
            services::recipe_registry::discover_and_seed(&database)?;

            app.manage(AppState { database });

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            list_recipes,
            get_recipe_detail,
            start_run,
            get_run,
            get_run_events
        ])
        .run(tauri::generate_context!())
        .expect("failed to run Atlas Weave application");
}
