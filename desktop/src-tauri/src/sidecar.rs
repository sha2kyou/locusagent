//! 桌面单体 Python 后端 sidecar（uvicorn :21223）

use std::{
    fs::OpenOptions,
    io::{BufRead, BufReader, Write},
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    thread,
    time::Duration,
};

use tauri::{AppHandle, Manager};
use tauri::path::BaseDirectory;
use tracing::{error, info, warn};

pub const BACKEND_PORT: u16 = 21223;

pub fn backend_url() -> String {
    format!("http://127.0.0.1:{BACKEND_PORT}")
}

fn agentpod_home() -> PathBuf {
    std::env::var("AGENTPOD_HOME")
        .map(PathBuf::from)
        .unwrap_or_else(|_| {
            std::env::var("HOME")
                .map(PathBuf::from)
                .unwrap_or_default()
                .join(".agentpod")
        })
}

fn backend_log_path() -> PathBuf {
    agentpod_home().join("desktop-backend.log")
}

/// 持续读取子进程输出并写入 desktop-backend.log，避免管道写满导致子进程阻塞。
fn spawn_log_drainer(stream: impl std::io::Read + Send + 'static) {
    thread::spawn(move || {
        let home = agentpod_home();
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
    if let Ok(root) = std::env::var("AGENTPOD_REPO_ROOT") {
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
    for name in ["python3.11", "python3", "python"] {
        let Ok(path) = app
            .path()
            .resolve(format!("sidecar-venv/bin/{name}"), BaseDirectory::Resource)
        else {
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
        .resolve("AGENT.md", BaseDirectory::Resource)
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
    if let Ok(py) = std::env::var("AGENTPOD_PYTHON") {
        let path = PathBuf::from(py);
        if path.is_file() {
            return Some(path);
        }
    }
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
    (PathBuf::from("python3"), Some(root.join("sidecar")), None)
}

pub fn spawn_backend(app: &AppHandle) -> std::io::Result<Child> {
    let (python, workdir, skills_dir) = python_executable(app);
    info!(python = %python.display(), "spawning agentpod backend");

    let mut command = Command::new(&python);
    command
        .arg("-m")
        .arg("agentpod.cli")
        .env("AGENTPOD_MONOLITH", "1");
    if let Some(dir) = workdir {
        command.current_dir(dir);
    }
    if let Some(skills) = skills_dir {
        command.env("AGENTPOD_BUNDLED_SKILLS_DIR", skills);
    }
    if let Some(agent_doc) = bundled_agent_doc(app) {
        command.env("AGENTPOD_AGENT_DOC_PATH", agent_doc);
    }
    let static_dir = crate::gateway::resolve_static_dir(app);
    if static_dir.join("index.html").is_file() {
        command.env("AGENTPOD_STATIC_DIR", static_dir);
    }
    command.env(
        "MCP_OAUTH_REDIRECT_URI",
        format!("http://127.0.0.1:{BACKEND_PORT}/api/oauth/mcp/callback"),
    );

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
