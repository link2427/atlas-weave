use std::path::PathBuf;

use anyhow::{anyhow, Context};

use crate::AppResult;

pub fn repo_root() -> AppResult<PathBuf> {
    let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    manifest_dir
        .parent()
        .and_then(|path| path.parent())
        .and_then(|path| path.parent())
        .map(PathBuf::from)
        .with_context(|| anyhow!("failed to resolve repository root from CARGO_MANIFEST_DIR"))
        .map_err(Into::into)
}
