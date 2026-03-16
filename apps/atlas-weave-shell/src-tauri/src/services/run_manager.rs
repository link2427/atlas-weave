use std::{
    collections::HashMap,
    sync::{
        atomic::{AtomicBool, Ordering},
        Arc,
    },
};

use serde_json::json;
use tokio::{
    io::AsyncWriteExt,
    process::{Child, ChildStdin},
    sync::Mutex,
};

use crate::{AppError, AppResult};

#[derive(Clone)]
pub struct ActiveRunHandle {
    child: Arc<Mutex<Child>>,
    stdin: Arc<Mutex<Option<ChildStdin>>>,
    cancel_requested: Arc<AtomicBool>,
}

impl ActiveRunHandle {
    pub fn new(child: Arc<Mutex<Child>>, stdin: ChildStdin) -> Self {
        Self {
            child,
            stdin: Arc::new(Mutex::new(Some(stdin))),
            cancel_requested: Arc::new(AtomicBool::new(false)),
        }
    }

    pub fn cancel_requested(&self) -> bool {
        self.cancel_requested.load(Ordering::SeqCst)
    }
}

#[derive(Default)]
pub struct RunManager {
    active_runs: Mutex<HashMap<String, ActiveRunHandle>>,
}

impl RunManager {
    pub async fn register(&self, run_id: String, handle: ActiveRunHandle) {
        self.active_runs.lock().await.insert(run_id, handle);
    }

    pub async fn get(&self, run_id: &str) -> Option<ActiveRunHandle> {
        self.active_runs.lock().await.get(run_id).cloned()
    }

    pub async fn is_active(&self, run_id: &str) -> bool {
        self.active_runs.lock().await.contains_key(run_id)
    }

    pub async fn cancel(&self, run_id: &str) -> AppResult<bool> {
        let handle = self.get(run_id).await;
        let Some(handle) = handle else {
            return Ok(false);
        };

        handle.cancel_requested.store(true, Ordering::SeqCst);
        let mut stdin_guard = handle.stdin.lock().await;
        let Some(stdin) = stdin_guard.as_mut() else {
            return Ok(false);
        };

        let command = serde_json::to_string(&json!({
            "type": "cancel_run",
            "run_id": run_id,
        }))?;
        stdin.write_all(command.as_bytes()).await?;
        stdin.write_all(b"\n").await?;
        stdin.flush().await?;

        Ok(true)
    }

    pub async fn terminate(&self, run_id: &str) -> AppResult<bool> {
        let handle = self.get(run_id).await;
        let Some(handle) = handle else {
            return Ok(false);
        };

        let mut child = handle.child.lock().await;
        child.kill().await.map_err(AppError::from)?;
        Ok(true)
    }

    pub async fn cleanup(&self, run_id: &str) {
        self.active_runs.lock().await.remove(run_id);
    }
}
