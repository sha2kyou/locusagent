//! 开发者工具开关：关闭 settings.json 中的 devtools 时收起已打开的 Inspector。

use tauri::{AppHandle, Manager};

use crate::app_settings;

pub fn apply_devtools_settings(app: &AppHandle) {
    if app_settings::devtools_enabled() {
        return;
    }
    if let Some(window) = app.get_webview_window("main") {
        if window.is_devtools_open() {
            window.close_devtools();
        }
    }
}

#[tauri::command]
pub fn desktop_apply_devtools_settings(app: AppHandle) -> Result<(), String> {
    apply_devtools_settings(&app);
    Ok(())
}
