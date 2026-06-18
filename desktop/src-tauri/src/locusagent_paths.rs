use std::path::PathBuf;

pub fn locusagent_home() -> PathBuf {
    if let Ok(raw) = std::env::var("LOCUSAGENT_HOME") {
        return PathBuf::from(raw);
    }
    #[cfg(windows)]
    {
        std::env::var("USERPROFILE")
            .map(PathBuf::from)
            .unwrap_or_default()
            .join(".locusagent")
    }
    #[cfg(not(windows))]
    {
        std::env::var("HOME")
            .map(PathBuf::from)
            .unwrap_or_default()
            .join(".locusagent")
    }
}
