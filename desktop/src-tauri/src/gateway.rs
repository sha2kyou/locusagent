use std::path::PathBuf;

use tauri::Manager;

pub fn resolve_static_dir(app: &tauri::AppHandle) -> PathBuf {
    use tauri::path::BaseDirectory;

    if cfg!(debug_assertions) {
        let dev = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../frontend/dist-desktop");
        if dev.join("index.html").is_file() {
            return dev;
        }
    }

    app.path()
        .resolve("dist-desktop", BaseDirectory::Resource)
        .unwrap_or_else(|_| PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../frontend/dist-desktop"))
}
