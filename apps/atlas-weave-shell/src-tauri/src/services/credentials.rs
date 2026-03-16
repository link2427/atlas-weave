use std::{
    collections::HashMap,
    fs,
    path::{Path, PathBuf},
};

use anyhow::Context;
use tauri_plugin_stronghold::stronghold::Stronghold;
use uuid::Uuid;

use crate::AppResult;

const CLIENT_ID: &[u8] = b"atlas-weave";

#[derive(Clone)]
pub struct CredentialStore {
    snapshot_path: PathBuf,
    key_path: PathBuf,
}

impl CredentialStore {
    pub fn new(base_dir: &Path) -> AppResult<Self> {
        fs::create_dir_all(base_dir).with_context(|| {
            format!(
                "failed to create credential directory at {}",
                base_dir.display()
            )
        })?;

        Ok(Self {
            snapshot_path: base_dir.join("credentials.hold"),
            key_path: base_dir.join("credentials.key"),
        })
    }

    pub fn presence(&self, keys: &[String]) -> AppResult<HashMap<String, bool>> {
        let mut result = HashMap::new();
        if keys.is_empty() {
            return Ok(result);
        }
        if !self.snapshot_path.exists() {
            for key in keys {
                result.insert(key.clone(), false);
            }
            return Ok(result);
        }

        let stronghold = self.open()?;
        let client = self.client(&stronghold)?;

        for key in keys {
            let present = client.store().contains_key(key.as_bytes())?;
            result.insert(key.clone(), present);
        }

        Ok(result)
    }

    pub fn get_values(&self, keys: &[String]) -> AppResult<HashMap<String, String>> {
        let mut result = HashMap::new();
        if keys.is_empty() {
            return Ok(result);
        }
        if !self.snapshot_path.exists() {
            return Ok(result);
        }

        let stronghold = self.open()?;
        let client = self.client(&stronghold)?;

        for key in keys {
            if let Some(bytes) = client.store().get(key.as_bytes())? {
                let value = String::from_utf8(bytes)
                    .with_context(|| format!("credential {key} is not valid UTF-8"))?;
                result.insert(key.clone(), value);
            }
        }

        Ok(result)
    }

    pub fn save(&self, values: &HashMap<String, Option<String>>) -> AppResult<()> {
        if values.is_empty() {
            return Ok(());
        }

        let stronghold = self.open()?;
        let client = self.client(&stronghold)?;

        for (key, value) in values {
            match value {
                Some(value) => {
                    client.store().insert(
                        key.as_bytes().to_vec(),
                        value.clone().into_bytes(),
                        None,
                    )?;
                }
                None => {
                    let _ = client.store().delete(key.as_bytes())?;
                }
            }
        }

        stronghold.save()?;
        Ok(())
    }

    fn open(&self) -> AppResult<Stronghold> {
        let password = self.password()?;
        Ok(Stronghold::new(&self.snapshot_path, password)?)
    }

    fn client(&self, stronghold: &Stronghold) -> AppResult<iota_stronghold::Client> {
        match stronghold.load_client(CLIENT_ID) {
            Ok(client) => Ok(client),
            Err(_) => Ok(stronghold.create_client(CLIENT_ID)?),
        }
    }

    fn password(&self) -> AppResult<Vec<u8>> {
        if self.key_path.exists() {
            let value = fs::read(&self.key_path).with_context(|| {
                format!(
                    "failed to read credential key at {}",
                    self.key_path.display()
                )
            })?;
            if value.len() == 32 {
                return Ok(value);
            }
            if self.snapshot_path.exists() {
                return Err(anyhow::anyhow!(
                    "credential key at {} is invalid for an existing snapshot",
                    self.key_path.display()
                )
                .into());
            }
        }

        let generated = generate_key_bytes();
        fs::write(&self.key_path, &generated).with_context(|| {
            format!(
                "failed to persist credential key at {}",
                self.key_path.display()
            )
        })?;
        Ok(generated)
    }
}

fn generate_key_bytes() -> Vec<u8> {
    let mut generated = Vec::with_capacity(32);
    generated.extend_from_slice(Uuid::new_v4().as_bytes());
    generated.extend_from_slice(Uuid::new_v4().as_bytes());
    generated
}

#[cfg(test)]
mod tests {
    use std::{collections::HashMap, fs};

    use tempfile::tempdir;

    use super::CredentialStore;

    #[test]
    fn empty_store_reports_missing_keys_without_snapshot() {
        let temp_dir = tempdir().expect("tempdir should exist");
        let store = CredentialStore::new(temp_dir.path()).expect("store should initialize");
        let keys = vec!["openrouter_api_key".to_string(), "claude_api_key".to_string()];

        let presence = store.presence(&keys).expect("presence lookup should succeed");
        let values = store.get_values(&keys).expect("get_values should succeed");

        assert_eq!(presence.get("openrouter_api_key").copied(), Some(false));
        assert_eq!(presence.get("claude_api_key").copied(), Some(false));
        assert!(values.is_empty());
        assert!(!temp_dir.path().join("credentials.hold").exists());
    }

    #[test]
    fn save_creates_snapshot_and_round_trips_values() {
        let temp_dir = tempdir().expect("tempdir should exist");
        let store = CredentialStore::new(temp_dir.path()).expect("store should initialize");
        let mut values = HashMap::new();
        values.insert("openrouter_api_key".to_string(), Some("secret-123".to_string()));

        store.save(&values).expect("save should succeed");

        let keys = vec!["openrouter_api_key".to_string()];
        let presence = store.presence(&keys).expect("presence lookup should succeed");
        let loaded = store.get_values(&keys).expect("values should load");

        assert_eq!(presence.get("openrouter_api_key").copied(), Some(true));
        assert_eq!(
            loaded.get("openrouter_api_key").map(String::as_str),
            Some("secret-123")
        );

        fs::remove_file(temp_dir.path().join("credentials.hold")).ok();
        fs::remove_file(temp_dir.path().join("credentials.key")).ok();
    }

    #[test]
    fn invalid_first_run_key_is_replaced_before_save() {
        let temp_dir = tempdir().expect("tempdir should exist");
        let store = CredentialStore::new(temp_dir.path()).expect("store should initialize");
        fs::write(temp_dir.path().join("credentials.key"), b"atlas-weave-invalid-length")
            .expect("invalid key should be written");
        let mut values = HashMap::new();
        values.insert("claude_api_key".to_string(), Some("secret-456".to_string()));

        store.save(&values).expect("save should succeed");

        let rewritten = fs::read(temp_dir.path().join("credentials.key")).expect("key should exist");
        assert_eq!(rewritten.len(), 32);
        assert!(temp_dir.path().join("credentials.hold").exists());
    }
}
