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
            if !value.is_empty() {
                return Ok(value);
            }
        }

        let generated = format!("atlas-weave-{}", Uuid::new_v4()).into_bytes();
        fs::write(&self.key_path, &generated).with_context(|| {
            format!(
                "failed to persist credential key at {}",
                self.key_path.display()
            )
        })?;
        Ok(generated)
    }
}
