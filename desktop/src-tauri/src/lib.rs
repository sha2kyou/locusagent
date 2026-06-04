mod gateway;

use std::time::Duration;

use tauri::{Manager, Url};
use tauri_plugin_deep_link::DeepLinkExt;

const DEFAULT_API_URL: &str = "http://127.0.0.1:1223";
const OAUTH_LOGIN_URL: &str = "http://127.0.0.1:1420/api/oauth/github/login?client=desktop";

fn handle_oauth_deep_link(app: &tauri::AppHandle, urls: &[Url]) {
    for raw in urls {
        if raw.scheme() != "agentpod" || raw.host_str() != Some("oauth") {
            continue;
        }
        let Some(exchange) = raw
            .query_pairs()
            .find(|(key, _)| key == "exchange")
            .map(|(_, value)| value.into_owned())
        else {
            continue;
        };
        let target = format!(
            "http://127.0.0.1:{}/api/oauth/desktop/exchange?exchange={}",
            gateway::GATEWAY_PORT,
            exchange
        );
        if let Some(window) = app.get_webview_window("main") {
            if let Ok(parsed) = target.parse::<Url>() {
                let _ = window.navigate(parsed);
            }
        }
        break;
    }
}

#[tauri::command]
fn open_oauth_login() -> Result<(), String> {
    #[cfg(target_os = "macos")]
    {
        std::process::Command::new("open")
            .arg(OAUTH_LOGIN_URL)
            .spawn()
            .map_err(|err| err.to_string())?;
        return Ok(());
    }

    #[cfg(not(target_os = "macos"))]
    {
        Err("unsupported platform".into())
    }
}

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_window_state::Builder::default().build())
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_deep_link::init())
        .invoke_handler(tauri::generate_handler![open_oauth_login])
        .setup(|app| {
            let handle = app.handle().clone();
            app.deep_link().on_open_url(move |event| {
                handle_oauth_deep_link(&handle, &event.urls());
            });

            if let Ok(Some(urls)) = app.deep_link().get_current() {
                handle_oauth_deep_link(app.handle(), &urls);
            }

            let upstream = std::env::var("AGENTPOD_API_URL")
                .unwrap_or_else(|_| DEFAULT_API_URL.to_string());
            let static_dir = gateway::resolve_static_dir(app.handle());

            gateway::spawn_gateway(static_dir, upstream);

            let runtime = tokio::runtime::Builder::new_current_thread()
                .enable_all()
                .build()
                .expect("gateway readiness runtime");
            runtime
                .block_on(gateway::wait_until_ready(Duration::from_secs(10)))
                .map_err(|err| format!("gateway not ready: {err}"))?;

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
