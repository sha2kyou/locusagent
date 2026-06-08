//! 拦截 webview 内外链，统一在系统默认浏览器打开。

use tauri::{
    App, LogicalPosition, TitleBarStyle, WebviewUrl,
    webview::{NewWindowResponse, WebviewWindowBuilder},
};
use tauri_plugin_opener::OpenerExt;

use crate::gateway::{GATEWAY_HOST, GATEWAY_PORT};

fn gateway_origin() -> String {
    format!("http://{GATEWAY_HOST}:{GATEWAY_PORT}")
}

fn is_app_url(url: &url::Url) -> bool {
    let origin = gateway_origin();
    url.as_str().starts_with(&origin)
        || url.as_str().starts_with("http://localhost:1420")
        || url.scheme() == "tauri"
}

fn open_in_system_browser(app: &tauri::AppHandle, url: &url::Url) {
    let app = app.clone();
    let target = url.to_string();
    tauri::async_runtime::spawn(async move {
        let _ = app.opener().open_url(target, None::<&str>);
    });
}

pub fn create_main_window(app: &App) -> tauri::Result<()> {
    let handle = app.handle().clone();
    let gateway_url: url::Url = gateway_origin().parse().expect("gateway url");

    WebviewWindowBuilder::new(app, "main", WebviewUrl::External(gateway_url))
        .title("AgentPod")
        .inner_size(1280.0, 840.0)
        .resizable(true)
        .decorations(true)
        .title_bar_style(TitleBarStyle::Overlay)
        .hidden_title(true)
        .traffic_light_position(LogicalPosition::new(16.0, 20.0))
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
        .build()?;

    Ok(())
}
