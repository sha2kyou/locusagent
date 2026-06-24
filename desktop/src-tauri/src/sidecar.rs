//! 桌面单体 Python 后端 sidecar（uvicorn :21223）

use std::{
    fs::OpenOptions,
    io::{BufRead, BufReader, Write},
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    thread,
    time::Duration,
};

#[cfg(windows)]
use std::os::windows::process::CommandExt;

use tauri::{AppHandle, Manager};
use tauri::path::BaseDirectory;
use tracing::{error, info, warn};

pub const BACKEND_PORT: u16 = 21223;
/// 桌面开发 Vite dev server（与 frontend/vite.config.ts 保持一致）
pub const DEV_FRONTEND_PORT: u16 = 5173;

pub fn backend_url() -> String {
    format!("http://127.0.0.1:{BACKEND_PORT}")
}

/// WebView 加载地址：开发走 Vite HMR，发布走 sidecar 同源 gateway。
pub fn frontend_url() -> String {
    if cfg!(debug_assertions) {
        format!("http://127.0.0.1:{DEV_FRONTEND_PORT}")
    } else {
        backend_url()
    }
}

pub fn is_app_web_url(url: &url::Url) -> bool {
    if url.scheme() == "tauri" {
        return true;
    }
    if url.as_str().starts_with(&frontend_url()) {
        return true;
    }
    url.as_str().starts_with(&backend_url())
        || url.as_str().starts_with("http://localhost:21223")
        || url.as_str().starts_with("http://localhost:5173")
}

fn default_locusagent_home() -> PathBuf {
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

fn locusagent_home() -> PathBuf {
    std::env::var("LOCUSAGENT_HOME")
        .ok()
        .map(PathBuf::from)
        .unwrap_or_else(default_locusagent_home)
}

fn backend_log_path() -> PathBuf {
    locusagent_home().join("desktop-backend.log")
}

/// 持续读取子进程输出并写入 desktop-backend.log，避免管道写满导致子进程阻塞。
fn spawn_log_drainer(stream: impl std::io::Read + Send + 'static) {
    thread::spawn(move || {
        let home = locusagent_home();
        let _ = std::fs::create_dir_all(&home);
        let mut log_file = OpenOptions::new()
            .create(true)
            .append(true)
            .open(backend_log_path())
            .ok();
        let reader = BufReader::new(stream);
        for line in reader.lines() {
            match line {
                Ok(text) if !text.is_empty() => {
                    if let Some(file) = log_file.as_mut() {
                        let _ = writeln!(file, "{text}");
                        let _ = file.flush();
                    }
                }
                Ok(_) => {}
                Err(_) => break,
            }
        }
    });
}

fn repo_root() -> PathBuf {
    if let Ok(root) = std::env::var("LOCUSAGENT_REPO_ROOT") {
        let path = PathBuf::from(root);
        if path.join("sidecar").is_dir() {
            return path;
        }
    }
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .canonicalize()
        .unwrap_or_else(|_| PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../.."))
}

fn bundled_python(app: &AppHandle) -> Option<PathBuf> {
    #[cfg(windows)]
    let rel_paths = [
        "sidecar-venv/python.exe",
        "sidecar-venv/Scripts/python.exe",
        "sidecar-venv/python3.exe",
    ];
    #[cfg(not(windows))]
    let rel_paths = [
        "sidecar-venv/bin/python3.11",
        "sidecar-venv/bin/python3",
        "sidecar-venv/bin/python",
    ];

    for rel in rel_paths {
        let Ok(path) = app.path().resolve(rel, BaseDirectory::Resource) else {
            continue;
        };
        if path.is_file() {
            return Some(path);
        }
    }
    None
}

fn bundled_agent_doc(app: &AppHandle) -> Option<PathBuf> {
    app.path()
        .resolve("LOCUSAGENT.md", BaseDirectory::Resource)
        .ok()
        .filter(|p| p.is_file())
}

fn bundled_skills_dir(app: &AppHandle) -> Option<PathBuf> {
    app.path()
        .resolve("shared-skills", BaseDirectory::Resource)
        .ok()
        .filter(|p| p.is_dir())
}

fn dev_python(root: &Path) -> Option<PathBuf> {
    if let Ok(py) = std::env::var("LOCUSAGENT_PYTHON") {
        let path = PathBuf::from(py);
        if path.is_file() {
            return Some(path);
        }
    }
    #[cfg(windows)]
    let venv_py = root.join("sidecar/.venv/Scripts/python.exe");
    #[cfg(not(windows))]
    let venv_py = root.join("sidecar/.venv/bin/python");
    if venv_py.is_file() {
        return Some(venv_py);
    }
    None
}

fn python_executable(app: &AppHandle) -> (PathBuf, Option<PathBuf>, Option<PathBuf>) {
    if let Some(py) = bundled_python(app) {
        return (py, None, bundled_skills_dir(app));
    }
    let root = repo_root();
    if let Some(py) = dev_python(&root) {
        return (py, Some(root.join("sidecar")), None);
    }
    #[cfg(windows)]
    let fallback = PathBuf::from("python");
    #[cfg(not(windows))]
    let fallback = PathBuf::from("python3");
    (fallback, Some(root.join("sidecar")), None)
}

pub fn spawn_backend(app: &AppHandle) -> std::io::Result<Child> {
    let (python, workdir, skills_dir) = python_executable(app);
    info!(python = %python.display(), "spawning locusagent backend");

    let mut command = Command::new(&python);
    command
        .arg("-m")
        .arg("locusagent.cli")
        .env("LOCUSAGENT_MONOLITH", "1");
    if let Some(dir) = workdir {
        command.current_dir(dir);
    }
    if let Some(skills) = skills_dir {
        command.env("LOCUSAGENT_BUNDLED_SKILLS_DIR", skills);
    }
    if let Some(agent_doc) = bundled_agent_doc(app) {
        command.env("LOCUSAGENT_AGENT_DOC_PATH", agent_doc);
    }
    if !cfg!(debug_assertions) {
        let static_dir = crate::gateway::resolve_static_dir(app);
        if static_dir.join("index.html").is_file() {
            command.env("LOCUSAGENT_STATIC_DIR", static_dir);
        }
    }
    command.env(
        "MCP_OAUTH_REDIRECT_URI",
        format!("http://127.0.0.1:{BACKEND_PORT}/api/oauth/mcp/callback"),
    );

    #[cfg(windows)]
    command.creation_flags(0x0800_0000); // CREATE_NO_WINDOW

    let mut child = command
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()?;

    if let Some(stdout) = child.stdout.take() {
        spawn_log_drainer(stdout);
    }
    if let Some(stderr) = child.stderr.take() {
        spawn_log_drainer(stderr);
    }

    Ok(child)
}

pub async fn wait_until_backend_ready(timeout: Duration) -> Result<(), String> {
    let url = format!("{}/health", backend_url());
    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(2))
        .build()
        .map_err(|e| e.to_string())?;
    let deadline = tokio::time::Instant::now() + timeout;
    loop {
        match client.get(&url).send().await {
            Ok(resp) if resp.status().is_success() => {
                info!("backend ready at {url}");
                return Ok(());
            }
            Ok(resp) => {
                warn!("backend health status {}", resp.status());
            }
            Err(err) => {
                warn!("backend not ready: {err}");
            }
        }
        if tokio::time::Instant::now() >= deadline {
            return Err(format!("backend not ready at {url}"));
        }
        tokio::time::sleep(Duration::from_millis(250)).await;
    }
}

pub fn stop_backend(mut child: Child) {
    if let Err(err) = child.kill() {
        error!("failed to kill backend sidecar: {err}");
    }
    let _ = child.wait();
}
