use std::{fs, process::Command};

use anyhow::{anyhow, Context};
use serde::Deserialize;
use serde_json::Value;

use crate::{db::Database, AppResult};

use super::paths;

#[derive(Debug, Deserialize)]
struct RecipeMetadata {
    name: String,
    description: String,
    version: String,
    config_schema: Value,
    dag: Value,
}

pub fn discover_and_seed(database: &Database) -> AppResult<()> {
    let repo_root = paths::repo_root()?;
    let recipes_dir = repo_root.join("python").join("recipes");
    let python_dir = repo_root.join("python");

    if !recipes_dir.exists() {
        return Ok(());
    }

    for entry in fs::read_dir(recipes_dir)? {
        let entry = entry?;
        let path = entry.path();
        let recipe_file = path.join("recipe.py");

        if !recipe_file.exists() {
            continue;
        }

        let name = entry.file_name().to_string_lossy().to_string();
        let output = Command::new("python")
            .arg("-m")
            .arg("atlas_weave.runner")
            .arg("--describe-recipe")
            .arg(&name)
            .current_dir(&repo_root)
            .env("PYTHONPATH", python_dir.to_string_lossy().to_string())
            .output()
            .with_context(|| format!("failed to describe recipe {name}"))?;

        if !output.status.success() {
            return Err(anyhow!(
                "python describe-recipe failed for {name}: {}",
                String::from_utf8_lossy(&output.stderr).trim()
            )
            .into());
        }

        let metadata: RecipeMetadata = serde_json::from_slice(&output.stdout)
            .with_context(|| format!("invalid recipe metadata JSON for {name}"))?;

        database.upsert_recipe(
            &metadata.name,
            &metadata.description,
            &metadata.version,
            &path,
            &metadata.config_schema.to_string(),
            &metadata.dag.to_string(),
        )?;
    }

    Ok(())
}
