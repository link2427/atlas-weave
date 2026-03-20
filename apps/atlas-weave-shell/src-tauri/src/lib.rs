mod commands;
mod db;
mod services;

use std::sync::Arc;

use commands::{
    data::{export_csv, get_recipe_db_tables, query_recipe_db, resolve_recipe_db_path},
    files::{pick_csv_file, pick_save_csv_file},
    recipes::{get_recipe_detail, list_recipes},
    runs::{cancel_run, get_run, get_run_events, get_run_history, start_run},
    settings::{get_credentials, save_credentials},
};
use db::Database;
use serde::Serialize;
use tauri::Manager;
use thiserror::Error;

#[derive(Clone)]
pub struct AppState {
    pub database: Arc<Database>,
    pub credentials: Arc<services::credentials::CredentialStore>,
    pub run_manager: Arc<services::run_manager::RunManager>,
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

impl From<tauri::Error> for AppError {
    fn from(value: tauri::Error) -> Self {
        Self::Message(value.to_string())
    }
}

impl From<iota_stronghold::ClientError> for AppError {
    fn from(value: iota_stronghold::ClientError) -> Self {
        Self::Message(value.to_string())
    }
}

impl From<tauri_plugin_stronghold::stronghold::Error> for AppError {
    fn from(value: tauri_plugin_stronghold::stronghold::Error) -> Self {
        Self::Message(value.to_string())
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .setup(|app| {
            let repo_root = services::paths::repo_root()?;
            let data_dir = repo_root.join(".atlas-weave");
            let database = Arc::new(Database::new(data_dir.join("atlas-weave.db"))?);
            let credentials = Arc::new(services::credentials::CredentialStore::new(&data_dir)?);
            let run_manager = Arc::new(services::run_manager::RunManager::default());

            database.initialize()?;
            services::recipe_registry::discover_and_seed(&database)?;

            app.manage(AppState {
                database,
                credentials,
                run_manager,
            });

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            list_recipes,
            get_recipe_detail,
            start_run,
            get_run,
            get_run_events,
            get_run_history,
            cancel_run,
            pick_csv_file,
            pick_save_csv_file,
            get_recipe_db_tables,
            query_recipe_db,
            resolve_recipe_db_path,
            export_csv,
            get_credentials,
            save_credentials
        ])
        .run(tauri::generate_context!())
        .expect("failed to run Atlas Weave application");
}
