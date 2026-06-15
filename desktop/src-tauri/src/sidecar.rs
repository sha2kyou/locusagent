//! 桌面单体 Python 后端 sidecar（uvicorn :21223）

use std::{
    io::{BufRead, BufReader},
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

fn bundled_readme(app: &AppHandle) -> Option<PathBuf> {
    app.path()
        .resolve("README.md", BaseDirectory::Resource)
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
    if let Some(readme) = bundled_readme(app) {
        command.env("AGENTPOD_README_PATH", readme);
    }
    let static_dir = crate::gateway::resolve_static_dir(app);
    if static_dir.join("index.html").is_file() {
        command.env("AGENTPOD_STATIC_DIR", static_dir);
    }

    let mut child = command.stdout(Stdio::piped()).stderr(Stdio::piped()).spawn()?;

    if let Some(stderr) = child.stderr.take() {
        thread::spawn(move || {
            let reader = BufReader::new(stderr);
            for line in reader.lines().map_while(Result::ok) {
                eprintln!("[backend] {line}");
            }
        });
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
