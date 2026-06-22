use std::fs;
use std::path::PathBuf;
use std::sync::Mutex;

use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};
use tauri::{AppHandle, Manager, State};

use crate::locusagent_paths::locusagent_home;

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
pub struct QuickChatWindowBounds {
    pub x: i32,
    pub y: i32,
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
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub quick_chat_window_bounds: Option<QuickChatWindowBounds>,
}

impl Default for DesktopPrefs {
    fn default() -> Self {
        Self {
            run_in_background: false,
            launch_at_login: false,
            quick_chat_enabled: default_quick_chat_enabled(),
            quick_chat_shortcut: default_quick_chat_shortcut(),
            quick_chat_always_on_top: true,
            quick_chat_window_bounds: None,
        }
    }
}

pub struct PrefsState(pub Mutex<DesktopPrefs>);

#[derive(Serialize)]
pub struct DesktopPrefsView {
    #[serde(flatten)]
    pub prefs: DesktopPrefs,
    pub quick_chat_shortcut_registered: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub quick_chat_shortcut_error: Option<String>,
}

fn settings_path() -> PathBuf {
    locusagent_home().join("settings.json")
}

fn legacy_prefs_path() -> PathBuf {
    locusagent_home().join("desktop.prefs.json")
}

fn read_settings_root() -> Map<String, Value> {
    let path = settings_path();
    if !path.is_file() {
        return Map::new();
    }
    fs::read_to_string(path)
        .ok()
        .and_then(|raw| serde_json::from_str::<Value>(&raw).ok())
        .and_then(|value| value.as_object().cloned())
        .unwrap_or_default()
}

fn write_settings_root(root: Map<String, Value>) -> Result<(), String> {
    let path = settings_path();
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    }
    let json = serde_json::to_string_pretty(&Value::Object(root)).map_err(|e| e.to_string())?;
    fs::write(path, format!("{json}\n")).map_err(|e| e.to_string())
}

fn load_desktop_from_settings() -> Option<DesktopPrefs> {
    read_settings_root()
        .get("desktop")
        .and_then(|value| serde_json::from_value(value.clone()).ok())
}

fn migrate_legacy_prefs_file() -> Option<DesktopPrefs> {
    let path = legacy_prefs_path();
    if !path.is_file() {
        return None;
    }
    let prefs = fs::read_to_string(&path)
        .ok()
        .and_then(|raw| serde_json::from_str::<DesktopPrefs>(&raw).ok())?;
    let _ = fs::remove_file(&path);
    Some(prefs)
}

pub fn load_prefs() -> DesktopPrefs {
    if let Some(prefs) = load_desktop_from_settings() {
        return prefs;
    }
    if let Some(prefs) = migrate_legacy_prefs_file() {
        let _ = save_prefs(&prefs);
        return prefs;
    }
    DesktopPrefs::default()
}

fn save_prefs(prefs: &DesktopPrefs) -> Result<(), String> {
    let mut root = read_settings_root();
    let desktop = serde_json::to_value(prefs).map_err(|e| e.to_string())?;
    root.insert("desktop".to_string(), desktop);
    write_settings_root(root)
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
    for name in ["Locus Agent.plist", "locusagent-desktop.plist", "locusagent.plist"] {
        let _ = fs::remove_file(dir.join(name));
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

pub fn remember_quick_chat_window_bounds(app: &AppHandle) {
    let Some(window) = app.get_webview_window(crate::quick_chat::QUICK_CHAT_WINDOW_LABEL) else {
        return;
    };
    let Ok(position) = window.outer_position() else {
        return;
    };
    let mut prefs = read_prefs(app);
    prefs.quick_chat_window_bounds = Some(QuickChatWindowBounds {
        x: position.x,
        y: position.y,
    });
    if let Some(state) = app.try_state::<PrefsState>() {
        *state.0.lock().expect("prefs lock") = prefs.clone();
    }
    let _ = save_prefs(&prefs);
}

pub fn apply_quick_chat_window_bounds(app: &AppHandle) -> bool {
    let prefs = read_prefs(app);
    let Some(bounds) = prefs.quick_chat_window_bounds else {
        return false;
    };
    let Some(window) = app.get_webview_window(crate::quick_chat::QUICK_CHAT_WINDOW_LABEL) else {
        return false;
    };
    let _ = window.set_position(tauri::PhysicalPosition::new(bounds.x, bounds.y));
    true
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
pub fn desktop_get_prefs(app: AppHandle, state: State<PrefsState>) -> DesktopPrefsView {
    let prefs = state.0.lock().expect("prefs lock poisoned").clone();
    DesktopPrefsView {
        quick_chat_shortcut_registered: crate::quick_chat::is_shortcut_registered(&app, &prefs),
        quick_chat_shortcut_error: crate::quick_chat::last_shortcut_sync_error(),
        prefs,
    }
}

#[tauri::command]
pub fn desktop_set_prefs(
    app: AppHandle,
    state: State<PrefsState>,
    prefs: DesktopPrefs,
) -> Result<DesktopPrefs, String> {
    let previous = state.0.lock().expect("prefs lock poisoned").clone();
    let mut prefs = prefs;
    prefs.quick_chat_window_bounds = previous.quick_chat_window_bounds;
    *state.0.lock().expect("prefs lock poisoned") = prefs.clone();
    save_prefs(&prefs)?;
    if let Err(err) = apply_autostart(&app, prefs.launch_at_login) {
        return Err(format!("偏好已保存，但开机自启设置失败: {err}"));
    }
    if let Err(err) = crate::quick_chat::sync_quick_chat_shortcut(&app, &prefs) {
        return Err(format!("偏好已保存，但快捷对话快捷键更新失败: {err}"));
    }
    crate::quick_chat::apply_quick_chat_always_on_top(&app, prefs.quick_chat_always_on_top);
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
