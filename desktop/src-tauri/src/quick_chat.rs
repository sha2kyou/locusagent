//! 系统级快捷键唤起的精简对话窗口。

use std::sync::Mutex;

use tauri::{
    App, AppHandle, Emitter, LogicalPosition, Manager, PhysicalPosition, WebviewUrl,
    webview::{NewWindowResponse, WebviewWindowBuilder},
};
#[cfg(target_os = "macos")]
use tauri::TitleBarStyle;
use tauri_plugin_global_shortcut::{GlobalShortcutExt, ShortcutState};
use tauri_plugin_opener::OpenerExt;

use crate::desktop_prefs::{self, DesktopPrefs};
use crate::sidecar;

pub const QUICK_CHAT_WINDOW_LABEL: &str = "quick-chat";
pub const QUICK_CHAT_OPEN_EVENT: &str = "quick-chat:open";
pub const QUICK_CHAT_FOCUS_COMPOSER_EVENT: &str = "quick-chat:focus-composer";

pub const DEFAULT_QUICK_CHAT_SHORTCUT: &str = "cmd+shift+Space";

static REGISTERED_SHORTCUT: Mutex<Option<String>> = Mutex::new(None);
static SHORTCUT_SYNC_ERROR: Mutex<Option<String>> = Mutex::new(None);

pub fn last_shortcut_sync_error() -> Option<String> {
    SHORTCUT_SYNC_ERROR
        .lock()
        .ok()
        .and_then(|guard| guard.clone())
}

pub fn is_shortcut_registered(app: &AppHandle, prefs: &DesktopPrefs) -> bool {
    if !prefs.quick_chat_enabled {
        return false;
    }
    let shortcut = normalize_shortcut_string(&prefs.quick_chat_shortcut);
    app.global_shortcut().is_registered(shortcut.as_str())
}

fn app_origin() -> String {
    sidecar::backend_url()
}

fn is_app_url(url: &url::Url) -> bool {
    let origin = app_origin();
    url.as_str().starts_with(&origin)
        || url.as_str().starts_with("http://localhost:21223")
        || url.scheme() == "tauri"
}

fn open_in_system_browser(app: &AppHandle, url: &url::Url) {
    let app = app.clone();
    let target = url.to_string();
    tauri::async_runtime::spawn(async move {
        let _ = app.opener().open_url(target, None::<&str>);
    });
}

pub fn create_quick_chat_window(app: &App) -> Result<(), String> {
    let handle = app.handle().clone();
    let quick_url: url::Url = format!("{}/quick-chat", app_origin())
        .parse::<url::Url>()
        .map_err(|e: url::ParseError| e.to_string())?;

    let mut builder = WebviewWindowBuilder::new(
        app,
        QUICK_CHAT_WINDOW_LABEL,
        WebviewUrl::External(quick_url),
    )
    .title("AgentPod")
    .inner_size(440.0, 580.0)
    .min_inner_size(360.0, 420.0)
    .resizable(true)
    .visible(false);

    #[cfg(target_os = "macos")]
    {
        builder = builder
            .decorations(true)
            .title_bar_style(TitleBarStyle::Overlay)
            .hidden_title(true)
            .traffic_light_position(LogicalPosition::new(16.0, 20.0));
    }

    #[cfg(not(target_os = "macos"))]
    {
        builder = builder.decorations(true);
    }

    builder
        .devtools(false)
        .on_navigation({
            let handle = handle.clone();
            move |url| {
                if is_app_url(url) {
                    return true;
                }
                if matches!(url.scheme(), "http" | "https" | "mailto" | "tel") {
                    open_in_system_browser(&handle, url);
                    return false;
                }
                false
            }
        })
        .on_new_window({
            let handle = handle.clone();
            move |url, _features| {
                open_in_system_browser(&handle, &url);
                NewWindowResponse::Deny
            }
        })
        .build()
        .map_err(|e| e.to_string())?;

    Ok(())
}

fn center_quick_chat_window(app: &AppHandle) {
    let Some(window) = app.get_webview_window(QUICK_CHAT_WINDOW_LABEL) else {
        return;
    };
    let monitor = window
        .current_monitor()
        .ok()
        .flatten()
        .or_else(|| window.primary_monitor().ok().flatten());
    let Some(monitor) = monitor else {
        return;
    };
    let Ok(size) = window.outer_size() else {
        return;
    };
    let monitor_size = monitor.size();
    let monitor_pos = monitor.position();
    let x = monitor_pos.x + (monitor_size.width as i32 - size.width as i32) / 2;
    let y = monitor_pos.y + (monitor_size.height as i32 - size.height as i32) / 2;
    let _ = window.set_position(PhysicalPosition::new(x, y));
}

pub fn toggle_quick_chat(app: &AppHandle) {
    let prefs = desktop_prefs::read_prefs(app);
    if !prefs.quick_chat_enabled {
        return;
    }
    let Some(window) = app.get_webview_window(QUICK_CHAT_WINDOW_LABEL) else {
        return;
    };
    if window.is_visible().unwrap_or(false) {
        if window.is_focused().unwrap_or(false) {
            let _ = window.hide();
            return;
        }
        let _ = window.set_focus();
        return;
    }
    show_quick_chat(app);
}

pub fn show_quick_chat(app: &AppHandle) {
    let Some(window) = app.get_webview_window(QUICK_CHAT_WINDOW_LABEL) else {
        return;
    };
    let prefs = desktop_prefs::read_prefs(app);
    center_quick_chat_window(app);
    let _ = window.set_always_on_top(prefs.quick_chat_always_on_top);
    let _ = window.show();
    let _ = window.unminimize();
    let _ = window.set_focus();
    let _ = window.emit(QUICK_CHAT_OPEN_EVENT, ());
    let _ = window.emit(QUICK_CHAT_FOCUS_COMPOSER_EVENT, ());
}

pub fn hide_quick_chat(app: &AppHandle) {
    if let Some(window) = app.get_webview_window(QUICK_CHAT_WINDOW_LABEL) {
        let _ = window.hide();
    }
}

pub fn sync_quick_chat_shortcut(app: &AppHandle, prefs: &DesktopPrefs) -> Result<(), String> {
    let global_shortcut = app.global_shortcut();
    if let Some(previous) = REGISTERED_SHORTCUT.lock().expect("shortcut lock").take() {
        let _ = global_shortcut.unregister(previous.as_str());
    }

    if !prefs.quick_chat_enabled {
        if let Ok(mut err) = SHORTCUT_SYNC_ERROR.lock() {
            *err = None;
        }
        return Ok(());
    }

    let shortcut = normalize_shortcut_string(&prefs.quick_chat_shortcut);
    // on_shortcut 内部已 register；不可再先 register 同一快捷键，否则会重复注册崩溃。
    let result = global_shortcut.on_shortcut(shortcut.as_str(), move |app, _shortcut, event| {
        if event.state == ShortcutState::Pressed {
            let handle = app.clone();
            let _ = app.run_on_main_thread(move || {
                toggle_quick_chat(&handle);
            });
        }
    });
    match result {
        Ok(()) => {
            *REGISTERED_SHORTCUT
                .lock()
                .expect("shortcut lock") = Some(shortcut);
            if let Ok(mut err) = SHORTCUT_SYNC_ERROR.lock() {
                *err = None;
            }
            Ok(())
        }
        Err(e) => {
            let message = format!("快捷键注册失败: {e}");
            if let Ok(mut err) = SHORTCUT_SYNC_ERROR.lock() {
                *err = Some(message.clone());
            }
            Err(message)
        }
    }
}

fn normalize_shortcut_string(raw: &str) -> String {
    let trimmed = raw.trim();
    if trimmed.is_empty() {
        return DEFAULT_QUICK_CHAT_SHORTCUT.to_string();
    }
    trimmed
        .replace("Command", "cmd")
        .replace("command", "cmd")
        .replace("Cmd", "cmd")
        .replace("Control", "ctrl")
        .replace("control", "ctrl")
        .replace("Ctrl", "ctrl")
        .replace("Option", "alt")
        .replace("option", "alt")
        .replace("Alt", "alt")
        .replace("Shift", "shift")
        .replace("shift", "shift")
}

#[tauri::command]
pub fn desktop_open_session_in_main(
    app: AppHandle,
    session_id: Option<String>,
) -> Result<(), String> {
    desktop_prefs::show_main_window(&app);
    if let Some(main) = app.get_webview_window("main") {
        let path = session_id
            .filter(|id| !id.is_empty())
            .map(|id| format!("/chat/{}", id))
            .unwrap_or_else(|| "/chat".to_string());
        let url = format!("{}{}", app_origin(), path);
        let _ = main.eval(&format!("window.location.assign({:?});", url));
    }
    hide_quick_chat(&app);
    Ok(())
}
