//! 读取 ~/.agentpod/settings.json 中的应用配置（桌面壳侧）。

use serde::Deserialize;

use crate::agentpod_paths::agentpod_home;

#[derive(Deserialize, Default)]
struct DeveloperSection {
    #[serde(default)]
    devtools_enabled: bool,
}

#[derive(Deserialize, Default)]
struct SettingsDocument {
    #[serde(default)]
    developer: DeveloperSection,
}

fn load_settings() -> SettingsDocument {
    let path = agentpod_home().join("settings.json");
    if !path.is_file() {
        return SettingsDocument::default();
    }
    std::fs::read_to_string(path)
        .ok()
        .and_then(|raw| serde_json::from_str(&raw).ok())
        .unwrap_or_default()
}

pub fn devtools_enabled() -> bool {
    load_settings().developer.devtools_enabled
}
