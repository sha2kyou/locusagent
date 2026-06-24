//! 拦截 webview 内外链，统一在系统默认浏览器打开。

use tauri::{
    App, WebviewUrl,
    webview::{NewWindowResponse, WebviewWindowBuilder},
};
#[cfg(target_os = "macos")]
use tauri::{LogicalPosition, TitleBarStyle};
use tauri_plugin_opener::OpenerExt;

use crate::sidecar;

fn open_in_system_browser(app: &tauri::AppHandle, url: &url::Url) {
    let app = app.clone();
    let target = url.to_string();
    tauri::async_runtime::spawn(async move {
        let _ = app.opener().open_url(target, None::<&str>);
    });
}

pub fn create_main_window(app: &App) -> tauri::Result<()> {
    let handle = app.handle().clone();
    let app_url: url::Url = sidecar::frontend_url().parse().expect("app url");

    let mut builder = WebviewWindowBuilder::new(app, "main", WebviewUrl::External(app_url))
        .title("Locus Agent")
        .inner_size(1280.0, 840.0)
        .resizable(true);

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

    builder = builder.devtools(crate::webview_devtools::initial_webview_devtools_enabled());

    builder
        .on_navigation({
            let handle = handle.clone();
            move |url| {
                if sidecar::is_app_web_url(url) {
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
