use std::path::PathBuf;

pub fn agentpod_home() -> PathBuf {
    if let Ok(raw) = std::env::var("AGENTPOD_HOME") {
        return PathBuf::from(raw);
    }
    #[cfg(windows)]
    {
        std::env::var("USERPROFILE")
            .map(PathBuf::from)
            .unwrap_or_default()
            .join(".agentpod")
    }
    #[cfg(not(windows))]
    {
        std::env::var("HOME")
            .map(PathBuf::from)
            .unwrap_or_default()
            .join(".agentpod")
    }
}
