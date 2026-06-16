mod desktop_prefs;
mod external_links;
mod gateway;
mod sidecar;
mod tray;

#[cfg(target_os = "macos")]
mod menu_bar_icon;

use std::sync::Mutex;
use std::time::Duration;

use desktop_prefs::{
    desktop_get_prefs, desktop_get_system_locale, desktop_set_prefs, load_prefs,
    install_window_close_handler, show_main_window, sync_autostart, PrefsState,
};
use tauri::{Manager, RunEvent};

static BACKEND_CHILD: Mutex<Option<std::process::Child>> = Mutex::new(None);

pub fn run() {
    tauri::Builder::default()
        .plugin(
            tauri_plugin_autostart::Builder::new()
                .app_name("AgentPod")
                .macos_launcher(tauri_plugin_autostart::MacosLauncher::AppleScript)
                .build(),
        )
        .plugin(tauri_plugin_window_state::Builder::default().build())
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_notification::init())
        .invoke_handler(tauri::generate_handler![
            desktop_get_prefs,
            desktop_get_system_locale,
            desktop_set_prefs,
        ])
        .setup(|app| {
            let prefs = load_prefs();
            if let Err(err) = sync_autostart(app.handle(), &prefs) {
                eprintln!("[desktop] autostart sync failed: {err}");
            }
            app.manage(PrefsState(Mutex::new(prefs)));

            tray::setup_tray(app.handle()).map_err(|err| format!("tray setup failed: {err}"))?;

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

            external_links::create_main_window(app).map_err(|err| format!("main window: {err}"))?;
            install_window_close_handler(app.handle());

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app, event| {
            #[cfg(target_os = "macos")]
            if matches!(event, RunEvent::Reopen { .. }) {
                show_main_window(app);
            }
            if matches!(event, RunEvent::Exit) {
                if let Some(child) = BACKEND_CHILD.lock().expect("backend child lock").take() {
                    sidecar::stop_backend(child);
                }
            }
        });
}
