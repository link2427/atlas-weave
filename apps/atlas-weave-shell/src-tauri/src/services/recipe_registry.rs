use std::fs;

use serde_json::json;

use crate::{db::Database, AppResult};

use super::paths;

pub fn discover_and_seed(database: &Database) -> AppResult<()> {
    let recipes_dir = paths::repo_root()?.join("python").join("recipes");

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
        let description = match name.as_str() {
            "test_echo" => "Phase 1 test recipe that streams timed log events.",
            _ => "Atlas Weave recipe",
        };
        let dag_json = if name == "test_echo" {
            json!({
                "nodes": [
                    {"id": "echo_agent", "label": "Echo Agent"}
                ],
                "edges": []
            })
            .to_string()
        } else {
            json!({ "nodes": [], "edges": [] }).to_string()
        };

        database.upsert_recipe(&name, description, "0.1.0", &path, &dag_json)?;
    }

    Ok(())
}
