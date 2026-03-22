#[cfg(target_os = "windows")]
use std::process::Command;

use crate::{AppError, AppResult};

#[tauri::command]
pub fn pick_csv_file() -> AppResult<Option<String>> {
    #[cfg(target_os = "windows")]
    {
        let script = r#"
Add-Type -AssemblyName System.Windows.Forms
$dialog = New-Object System.Windows.Forms.OpenFileDialog
$dialog.Filter = 'CSV files (*.csv)|*.csv|All files (*.*)|*.*'
$dialog.Multiselect = $false
$dialog.CheckFileExists = $true
$dialog.Title = 'Select UCS CSV file'
if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
  Write-Output $dialog.FileName
}
"#;

        let output = Command::new("powershell")
            .args(["-NoProfile", "-STA", "-Command", script])
            .output()?;

        if !output.status.success() {
            let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();
            return Err(AppError::Message(if stderr.is_empty() {
                "failed to open file picker".to_string()
            } else {
                stderr
            }));
        }

        let selected = String::from_utf8_lossy(&output.stdout).trim().to_string();
        if selected.is_empty() {
            return Ok(None);
        }
        Ok(Some(selected))
    }

    #[cfg(not(target_os = "windows"))]
    {
        Err(AppError::Message(
            "CSV file picking is only implemented for Windows in this build".to_string(),
        ))
    }
}

#[tauri::command]
pub fn pick_save_csv_file() -> AppResult<Option<String>> {
    #[cfg(target_os = "windows")]
    {
        let script = r#"
Add-Type -AssemblyName System.Windows.Forms
$dialog = New-Object System.Windows.Forms.SaveFileDialog
$dialog.Filter = 'CSV files (*.csv)|*.csv'
$dialog.Title = 'Export as CSV'
$dialog.DefaultExt = 'csv'
if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
  Write-Output $dialog.FileName
}
"#;

        let output = Command::new("powershell")
            .args(["-NoProfile", "-STA", "-Command", script])
            .output()?;

        if !output.status.success() {
            let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();
            return Err(AppError::Message(if stderr.is_empty() {
                "failed to open save dialog".to_string()
            } else {
                stderr
            }));
        }

        let selected = String::from_utf8_lossy(&output.stdout).trim().to_string();
        if selected.is_empty() {
            return Ok(None);
        }
        Ok(Some(selected))
    }

    #[cfg(not(target_os = "windows"))]
    {
        Err(AppError::Message(
            "CSV save dialog is only implemented for Windows in this build".to_string(),
        ))
    }
}
