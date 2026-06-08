mod external_links;
mod gateway;
mod sidecar;

use std::sync::Mutex;
use std::time::Duration;

use tauri::RunEvent;

static BACKEND_CHILD: Mutex<Option<std::process::Child>> = Mutex::new(None);

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_window_state::Builder::default().build())
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_notification::init())
        .setup(|app| {
            let backend = sidecar::spawn_backend(app.handle()).map_err(|err| format!("backend spawn failed: {err}"))?;
            {
                let mut slot = BACKEND_CHILD.lock().expect("backend child lock");
                *slot = Some(backend);
            }

            let runtime = tokio::runtime::Builder::new_current_thread()
                .enable_all()
                .build()
                .expect("backend readiness runtime");
            runtime
                .block_on(sidecar::wait_until_backend_ready(Duration::from_secs(120)))
                .map_err(|err| format!("backend not ready: {err}"))?;

            let upstream = std::env::var("AGENTPOD_API_URL")
                .unwrap_or_else(|_| sidecar::backend_url());
            let static_dir = gateway::resolve_static_dir(app.handle());

            gateway::spawn_gateway(static_dir, upstream);

            runtime
                .block_on(gateway::wait_until_ready(Duration::from_secs(10)))
                .map_err(|err| format!("gateway not ready: {err}"))?;

            external_links::create_main_window(app).map_err(|err| format!("main window: {err}"))?;

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|_app, event| {
            if matches!(event, RunEvent::Exit) {
                if let Some(child) = BACKEND_CHILD.lock().expect("backend child lock").take() {
                    sidecar::stop_backend(child);
                }
            }
        });
}
