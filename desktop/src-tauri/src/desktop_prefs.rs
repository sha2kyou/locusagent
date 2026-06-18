use std::fs;
use std::path::PathBuf;
use std::sync::Mutex;

use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Manager, State};

use crate::agentpod_paths::agentpod_home;

fn default_quick_chat_enabled() -> bool {
    true
}

fn default_quick_chat_shortcut() -> String {
    crate::quick_chat::DEFAULT_QUICK_CHAT_SHORTCUT.to_string()
}

fn default_quick_chat_always_on_top() -> bool {
    true
}

#[derive(Clone, Serialize, Deserialize)]
pub struct DesktopPrefs {
    #[serde(default)]
    pub run_in_background: bool,
    #[serde(default)]
    pub launch_at_login: bool,
    #[serde(default = "default_quick_chat_enabled")]
    pub quick_chat_enabled: bool,
    #[serde(default = "default_quick_chat_shortcut")]
    pub quick_chat_shortcut: String,
    #[serde(default = "default_quick_chat_always_on_top")]
    pub quick_chat_always_on_top: bool,
}

impl Default for DesktopPrefs {
    fn default() -> Self {
        Self {
            run_in_background: false,
            launch_at_login: false,
            quick_chat_enabled: default_quick_chat_enabled(),
            quick_chat_shortcut: default_quick_chat_shortcut(),
            quick_chat_always_on_top: default_quick_chat_always_on_top(),
        }
    }
}

pub struct PrefsState(pub Mutex<DesktopPrefs>);

fn prefs_file() -> PathBuf {
    agentpod_home().join("desktop.prefs.json")
}

pub fn load_prefs() -> DesktopPrefs {
    let path = prefs_file();
    if !path.is_file() {
        return DesktopPrefs::default();
    }
    fs::read_to_string(path)
        .ok()
        .and_then(|raw| serde_json::from_str(&raw).ok())
        .unwrap_or_default()
}

fn save_prefs(prefs: &DesktopPrefs) -> Result<(), String> {
    let path = prefs_file();
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    }
    let json = serde_json::to_string_pretty(prefs).map_err(|e| e.to_string())?;
    fs::write(path, json).map_err(|e| e.to_string())
}

pub fn run_in_background(app: &AppHandle) -> bool {
    app.try_state::<PrefsState>()
        .and_then(|state| state.0.lock().ok().map(|prefs| prefs.run_in_background))
        .unwrap_or(false)
}

fn apply_autostart(app: &AppHandle, enabled: bool) -> Result<(), String> {
    use tauri_plugin_autostart::ManagerExt;

    #[cfg(target_os = "macos")]
    remove_legacy_launch_agent_plists();

    let autolaunch = app.autolaunch();
    if enabled {
        return autolaunch.enable().map_err(|e| e.to_string());
    }
    match autolaunch.is_enabled() {
        Ok(true) => autolaunch.disable().map_err(|e| e.to_string()),
        Ok(false) => Ok(()),
        Err(e) => Err(e.to_string()),
    }
}

#[cfg(target_os = "macos")]
fn remove_legacy_launch_agent_plists() {
    let Ok(home) = std::env::var("HOME") else {
        return;
    };
    let dir = PathBuf::from(home).join("Library/LaunchAgents");
    for name in ["AgentPod.plist", "agentpod-desktop.plist", "agentpod.plist"] {
        let _ = std::fs::remove_file(dir.join(name));
    }
}

pub fn sync_autostart(app: &AppHandle, prefs: &DesktopPrefs) -> Result<(), String> {
    apply_autostart(app, prefs.launch_at_login)
}

pub fn read_prefs(app: &AppHandle) -> DesktopPrefs {
    app.try_state::<PrefsState>()
        .map(|state| state.0.lock().expect("prefs lock").clone())
        .unwrap_or_default()
}

pub fn show_main_window(app: &AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.show();
        let _ = window.unminimize();
        let _ = window.set_focus();
    }
}

pub fn hide_main_window(app: &AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.hide();
    }
}

#[tauri::command]
pub fn desktop_get_system_locale() -> Option<String> {
    sys_locale::get_locale()
}

#[tauri::command]
pub fn desktop_get_prefs(state: State<PrefsState>) -> DesktopPrefs {
    state.0.lock().expect("prefs lock poisoned").clone()
}

#[tauri::command]
pub fn desktop_set_prefs(
    app: AppHandle,
    state: State<PrefsState>,
    prefs: DesktopPrefs,
) -> Result<DesktopPrefs, String> {
    *state.0.lock().expect("prefs lock poisoned") = prefs.clone();
    save_prefs(&prefs)?;
    if let Err(err) = apply_autostart(&app, prefs.launch_at_login) {
        return Err(format!("偏好已保存，但开机自启设置失败: {err}"));
    }
    if let Err(err) = crate::quick_chat::sync_quick_chat_shortcut(&app, &prefs) {
        return Err(format!("偏好已保存，但快捷对话快捷键更新失败: {err}"));
    }
    Ok(prefs)
}

pub fn install_window_close_handler(app: &AppHandle) {
    let handle = app.clone();
    if let Some(window) = app.get_webview_window("main") {
        window.on_window_event(move |event| {
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                if run_in_background(&handle) {
                    api.prevent_close();
                    hide_main_window(&handle);
                }
            }
        });
    }
}
