use std::time::Duration;

use chrono::Utc;
use croner::Cron;
use tauri::Manager;
use crate::commands::runs::trigger_run;
use crate::AppState;

const TICK_INTERVAL: Duration = Duration::from_secs(30);

pub struct Scheduler {
    _handle: tauri::async_runtime::JoinHandle<()>,
}

impl Scheduler {
    pub fn start(app: tauri::AppHandle) -> Self {
        let handle = tauri::async_runtime::spawn(async move {
            // Give the app a moment to finish setup
            tokio::time::sleep(Duration::from_secs(2)).await;
            recompute_all_next_runs(&app);
            loop {
                tokio::time::sleep(TICK_INTERVAL).await;
                tick(&app).await;
            }
        });
        Self { _handle: handle }
    }
}

fn recompute_all_next_runs(app: &tauri::AppHandle) {
    let state = app.state::<AppState>();
    let database = state.database.as_ref();

    let schedules = match database.get_enabled_schedules() {
        Ok(s) => s,
        Err(error) => {
            eprintln!("[scheduler] failed to load schedules for recompute: {error}");
            return;
        }
    };

    for schedule in schedules {
        let next = match compute_next_fire(&schedule.cron_expression) {
            Some(t) => t,
            None => {
                eprintln!(
                    "[scheduler] invalid cron for schedule {}: {}",
                    schedule.id, schedule.cron_expression
                );
                continue;
            }
        };

        if let Err(error) = database.update_schedule(
            &schedule.id,
            None,
            None,
            None,
            Some(Some(&next)),
        ) {
            eprintln!(
                "[scheduler] failed to update next_run_at for {}: {error}",
                schedule.id
            );
        } else {
            eprintln!(
                "[scheduler] recomputed next_run_at for {} -> {}",
                schedule.id, next
            );
        }
    }
}

async fn tick(app: &tauri::AppHandle) {
    let state = app.state::<AppState>();
    let database = state.database.as_ref().clone();
    let run_manager = state.run_manager.clone();
    let credentials = state.credentials.clone();
    let now = Utc::now();

    let schedules = match database.get_enabled_schedules() {
        Ok(s) => s,
        Err(error) => {
            eprintln!("[scheduler] failed to load enabled schedules: {error}");
            return;
        }
    };

    for schedule in schedules {
        let should_fire = match &schedule.next_run_at {
            Some(next_str) => match next_str.parse::<chrono::DateTime<Utc>>() {
                Ok(next_time) => next_time <= now,
                Err(_) => {
                    eprintln!(
                        "[scheduler] invalid next_run_at for {}: {}",
                        schedule.id, next_str
                    );
                    true
                }
            },
            None => true,
        };

        if !should_fire {
            continue;
        }

        match database.has_running_run(&schedule.recipe_name) {
            Ok(true) => {
                eprintln!(
                    "[scheduler] skipping {} — run already active for {}",
                    schedule.id, schedule.recipe_name
                );
                // Still advance next_run_at so we don't keep retrying
                if let Some(next) = compute_next_fire(&schedule.cron_expression) {
                    let _ = database.update_schedule(
                        &schedule.id,
                        None,
                        None,
                        None,
                        Some(Some(&next)),
                    );
                }
                continue;
            }
            Ok(false) => {}
            Err(error) => {
                eprintln!(
                    "[scheduler] failed to check running state for {}: {error}",
                    schedule.recipe_name
                );
                continue;
            }
        }

        let config = schedule
            .config_json
            .as_deref()
            .and_then(|json| serde_json::from_str(json).ok());

        match trigger_run(
            app,
            &database,
            &run_manager,
            &credentials,
            &schedule.recipe_name,
            config,
            None,
        )
        .await
        {
            Ok(run_id) => {
                let next = compute_next_fire(&schedule.cron_expression)
                    .unwrap_or_else(|| Utc::now().to_rfc3339());
                if let Err(error) =
                    database.update_schedule_after_trigger(&schedule.id, &run_id, &next)
                {
                    eprintln!(
                        "[scheduler] triggered run {run_id} but failed to update schedule: {error}"
                    );
                } else {
                    eprintln!(
                        "[scheduler] triggered run {run_id} for schedule {}, next at {next}",
                        schedule.id
                    );
                }
            }
            Err(error) => {
                eprintln!(
                    "[scheduler] failed to trigger run for schedule {}: {error}",
                    schedule.id
                );
                // Advance next_run_at even on failure
                if let Some(next) = compute_next_fire(&schedule.cron_expression) {
                    let _ = database.update_schedule(
                        &schedule.id,
                        None,
                        None,
                        None,
                        Some(Some(&next)),
                    );
                }
            }
        }
    }
}

pub fn compute_next_fire(cron_expression: &str) -> Option<String> {
    let cron = Cron::new(cron_expression).parse().ok()?;
    let now = Utc::now();
    let next = cron.find_next_occurrence(&now, false).ok()?;
    Some(next.to_rfc3339())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn compute_next_fire_every_minute() {
        let result = compute_next_fire("* * * * *");
        assert!(result.is_some());
        let next: chrono::DateTime<Utc> = result.unwrap().parse().unwrap();
        assert!(next > Utc::now());
    }

    #[test]
    fn compute_next_fire_every_two_minutes() {
        let result = compute_next_fire("*/2 * * * *");
        assert!(result.is_some());
        let next: chrono::DateTime<Utc> = result.unwrap().parse().unwrap();
        assert!(next > Utc::now());
    }

    #[test]
    fn compute_next_fire_invalid_cron() {
        let result = compute_next_fire("not a cron");
        assert!(result.is_none());
    }
}
