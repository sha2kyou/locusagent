//! 运行时切换 WebView Inspector（原生右键菜单中的「检查元素」）。

use tauri::{AppHandle, Manager, WebviewWindow};

use crate::app_settings;

pub fn initial_webview_devtools_enabled() -> bool {
    app_settings::devtools_enabled()
}

fn set_webview_inspector_enabled(window: &WebviewWindow, enabled: bool) -> Result<(), String> {
    window
        .with_webview(move |platform| {
            #[cfg(target_os = "macos")]
            {
                use objc2_foundation::{ns_string, NSNumber, NSObjectNSKeyValueCoding};
                use objc2_web_kit::WKWebView;

                unsafe {
                    let view: &WKWebView = &*platform.inner().cast();
                    view.setInspectable(enabled);
                    let prefs = view.configuration().preferences();
                    let value = NSNumber::new_bool(enabled);
                    prefs.setValue_forKey(Some(&value), ns_string!("developerExtrasEnabled"));
                }
            }
        })
        .map_err(|e| e.to_string())
}

pub fn sync_devtools_runtime(app: &AppHandle) -> Result<(), String> {
    let enabled = app_settings::devtools_enabled();
    if let Some(window) = app.get_webview_window("main") {
        set_webview_inspector_enabled(&window, enabled)?;
        if !enabled && window.is_devtools_open() {
            window.close_devtools();
        }
    }
    Ok(())
}

#[tauri::command]
pub fn desktop_apply_devtools_settings(app: AppHandle) -> Result<(), String> {
    sync_devtools_runtime(&app)
}
