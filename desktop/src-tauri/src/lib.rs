mod agentpod_paths;
mod app_settings;
mod desktop_prefs;
mod external_links;
mod gateway;
mod quick_chat;
mod sidecar;
mod tray;
mod webview_devtools;

#[cfg(target_os = "macos")]
mod menu_bar_icon;

use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Mutex;
use std::time::Duration;

use desktop_prefs::{
    desktop_get_prefs, desktop_get_system_locale, desktop_set_prefs, load_prefs,
    install_window_close_handler, sync_autostart, PrefsState,
};
#[cfg(target_os = "macos")]
use desktop_prefs::show_main_window;
use tauri::{Manager, RunEvent};
use tauri_plugin_global_shortcut::ShortcutState;

static BACKEND_CHILD: Mutex<Option<std::process::Child>> = Mutex::new(None);
static QUICK_CHAT_SHORTCUT_SYNCED: AtomicBool = AtomicBool::new(false);

pub fn run() {
    tauri::Builder::default()
        .plugin({
            let autostart = tauri_plugin_autostart::Builder::new().app_name("AgentPod");
            #[cfg(target_os = "macos")]
            let autostart = autostart
                .macos_launcher(tauri_plugin_autostart::MacosLauncher::AppleScript);
            autostart.build()
        })
        .plugin(
            tauri_plugin_window_state::Builder::default()
                .with_filter(|label| label != quick_chat::QUICK_CHAT_WINDOW_LABEL)
                .build(),
        )
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_notification::init())
        .plugin(
            tauri_plugin_global_shortcut::Builder::new()
                .with_handler(|app, _shortcut, event| {
                    if event.state == ShortcutState::Pressed {
                        let handle = app.clone();
                        let _ = app.run_on_main_thread(move || {
                            quick_chat::toggle_quick_chat(&handle);
                        });
                    }
                })
                .build(),
        )
        .invoke_handler(tauri::generate_handler![
            desktop_get_prefs,
            desktop_get_system_locale,
            desktop_set_prefs,
            webview_devtools::desktop_apply_devtools_settings,
            quick_chat::desktop_open_session_in_main,
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
            quick_chat::create_quick_chat_window(app)
                .map_err(|err| format!("quick chat window: {err}"))?;
            quick_chat::hide_quick_chat(app.handle());
            quick_chat::install_quick_chat_window_handler(app.handle());
            webview_devtools::sync_devtools_runtime(app.handle())
                .map_err(|err| format!("webview devtools: {err}"))?;
            install_window_close_handler(app.handle());

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app, event| {
            if matches!(event, RunEvent::Ready) {
                if !QUICK_CHAT_SHORTCUT_SYNCED.swap(true, Ordering::SeqCst) {
                    let prefs = desktop_prefs::read_prefs(app);
                    if let Err(err) = quick_chat::sync_quick_chat_shortcut(app, &prefs) {
                        eprintln!("[desktop] quick chat shortcut: {err}");
                    }
                }
            }
            #[cfg(target_os = "macos")]
            if matches!(event, RunEvent::Reopen { .. }) {
                show_main_window(app);
            }
            #[cfg(not(target_os = "macos"))]
            let _ = app;
            if matches!(event, RunEvent::Exit) {
                desktop_prefs::remember_quick_chat_window_bounds(app);
                if let Some(child) = BACKEND_CHILD.lock().expect("backend child lock").take() {
                    sidecar::stop_backend(child);
                }
            }
        });
}
