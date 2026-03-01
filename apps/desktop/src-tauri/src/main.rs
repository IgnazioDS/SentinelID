#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use serde::{Deserialize, Serialize};
use std::net::TcpListener;
use std::path::PathBuf;
use std::process::{Child, Command};
use std::sync::Mutex;
use std::time::Duration;
use tauri::Manager;
use uuid::Uuid;

#[cfg(not(debug_assertions))]
use std::process::Stdio;

#[derive(Clone, Serialize, Deserialize)]
struct EdgeInfo {
    base_url: String,
    token: String,
}

struct EdgeState {
    edge_process: Option<Child>,
    edge_info: Option<EdgeInfo>,
    starting: bool,
}

#[tauri::command]
async fn start_edge(
    app: tauri::AppHandle,
    state: tauri::State<'_, Mutex<EdgeState>>,
) -> Result<EdgeInfo, String> {
    let mut should_start = false;
    {
        let mut guard = state.lock().map_err(|e| e.to_string())?;
        let mut stale = false;
        if let Some(child) = guard.edge_process.as_mut() {
            match child.try_wait() {
                Ok(None) => {
                    if let Some(info) = guard.edge_info.clone() {
                        return Ok(info);
                    }
                    stale = true;
                }
                Ok(Some(_)) | Err(_) => {
                    stale = true;
                }
            }
        }
        if stale {
            if let Some(mut child) = guard.edge_process.take() {
                let _ = child.kill();
                let _ = child.wait();
            }
            guard.edge_info = None;
        }

        if guard.starting {
            // Another caller is currently launching edge; wait below.
        } else {
            guard.starting = true;
            should_start = true;
        }
    }

    if !should_start {
        for _ in 0..50 {
            tokio::time::sleep(Duration::from_millis(100)).await;
            let mut guard = state.lock().map_err(|e| e.to_string())?;

            if let Some(child) = guard.edge_process.as_mut() {
                if let Ok(None) = child.try_wait() {
                    if let Some(info) = guard.edge_info.clone() {
                        return Ok(info);
                    }
                }
            }

            if !guard.starting {
                break;
            }
        }
        // Retry as launcher if previous startup failed/finished without a healthy child.
        let mut guard = state.lock().map_err(|e| e.to_string())?;
        if !guard.starting {
            guard.starting = true;
            should_start = true;
        }
    }

    if !should_start {
        return Err("Timed out waiting for edge startup".to_string());
    }

    let port = find_free_port()?;
    let token = Uuid::new_v4().to_string();
    let base_url = format!("http://127.0.0.1:{}", port);

    let mut edge_cmd = build_edge_command(&app, port, &token)?;
    let mut child = match edge_cmd.spawn() {
        Ok(child) => child,
        Err(e) => {
            let mut guard = state.lock().map_err(|lock_err| lock_err.to_string())?;
            guard.starting = false;
            return Err(format!("Failed to start edge process: {}", e));
        }
    };

    if let Err(err) = wait_for_health(&base_url).await {
        let _ = child.kill();
        let _ = child.wait();
        let mut guard = state.lock().map_err(|e| e.to_string())?;
        guard.starting = false;
        return Err(err);
    }

    let edge_info = EdgeInfo {
        base_url: base_url.clone(),
        token: token.clone(),
    };

    {
        let mut guard = state.lock().map_err(|e| e.to_string())?;
        guard.edge_process = Some(child);
        guard.edge_info = Some(edge_info.clone());
        guard.starting = false;
    }

    Ok(edge_info)
}

#[tauri::command]
fn get_edge_info(state: tauri::State<Mutex<EdgeState>>) -> Result<EdgeInfo, String> {
    let mut state = state.lock().map_err(|e| e.to_string())?;
    if let Some(child) = state.edge_process.as_mut() {
        match child.try_wait() {
            Ok(None) => {
                return state
                    .edge_info
                    .clone()
                    .ok_or_else(|| "Edge not started".to_string());
            }
            Ok(Some(_)) | Err(_) => {
                if let Some(mut old_child) = state.edge_process.take() {
                    let _ = old_child.wait();
                }
                state.edge_info = None;
                return Err("Edge not started".to_string());
            }
        }
    }
    state.edge_info = None;
    Err("Edge not started".to_string())
}

#[tauri::command]
fn kill_edge(state: tauri::State<Mutex<EdgeState>>) -> Result<(), String> {
    let mut state = state.lock().map_err(|e| e.to_string())?;
    if let Some(mut child) = state.edge_process.take() {
        let _ = child.kill();
        let _ = child.wait();
    }
    state.edge_info = None;
    Ok(())
}

fn find_free_port() -> Result<u16, String> {
    let listener = TcpListener::bind("127.0.0.1:0")
        .map_err(|e| format!("Failed to find free port: {}", e))?;
    let port = listener
        .local_addr()
        .map_err(|e| format!("Failed to get local port: {}", e))?
        .port();
    drop(listener);
    Ok(port)
}

fn build_edge_command(_app: &tauri::AppHandle, port: u16, token: &str) -> Result<Command, String> {
    #[cfg(not(debug_assertions))]
    {
        let launcher = resolve_launcher_path(_app)?;
        let mut cmd = Command::new(launcher);
        cmd.arg(port.to_string())
            .arg(token)
            .arg("prod")
            .env("EDGE_HOST", "127.0.0.1")
            .env("EDGE_PORT", port.to_string())
            .env("EDGE_AUTH_TOKEN", token)
            .env("EDGE_ENV", "prod")
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null());
        return Ok(cmd);
    }

    #[cfg(debug_assertions)]
    {
        // In dev, route through edge_env.sh to avoid wrong-venv leakage.
        let repo_root = resolve_repo_root()?;
        let launcher = repo_root.join("scripts").join("dev").join("edge_env.sh");
        if !launcher.exists() {
            return Err(format!(
                "Failed to resolve edge launcher script at {}",
                launcher.display()
            ));
        }

        let fallback_embeddings = std::env::var("ALLOW_FALLBACK_EMBEDDINGS")
            .unwrap_or_else(|_| "1".to_string());

        let mut cmd = Command::new(launcher);
        cmd.arg("run")
            .env("EDGE_HOST", "127.0.0.1")
            .env("EDGE_PORT", port.to_string())
            .env("EDGE_AUTH_TOKEN", token)
            .env("EDGE_ENV", "dev")
            .env("ALLOW_FALLBACK_EMBEDDINGS", fallback_embeddings)
            .current_dir(repo_root);
        Ok(cmd)
    }
}

#[cfg(debug_assertions)]
fn resolve_repo_root() -> Result<PathBuf, String> {
    let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let repo_root = manifest_dir
        .parent()
        .and_then(|path| path.parent())
        .and_then(|path| path.parent())
        .ok_or_else(|| "Failed to compute repository root from CARGO_MANIFEST_DIR".to_string())?;
    Ok(repo_root.to_path_buf())
}

#[cfg(not(debug_assertions))]
fn resolve_launcher_path(app: &tauri::AppHandle) -> Result<PathBuf, String> {
    app.path_resolver()
        .resolve_resource("resources/edge/run_edge.sh")
        .or_else(|| app.path_resolver().resolve_resource("edge/run_edge.sh"))
        .ok_or_else(|| "Failed to resolve bundled edge launcher (run_edge.sh)".to_string())
}

async fn wait_for_health(base_url: &str) -> Result<(), String> {
    let health_url = format!("{}/api/v1/health", base_url);
    for _ in 0..20 {
        match reqwest::Client::new()
            .get(&health_url)
            .timeout(Duration::from_secs(1))
            .send()
            .await
        {
            Ok(resp) if resp.status().is_success() => return Ok(()),
            _ => tokio::time::sleep(Duration::from_millis(250)).await,
        }
    }
    Err("Failed to connect to edge health endpoint".to_string())
}

fn main() {
    let app = tauri::Builder::default()
        .manage(Mutex::new(EdgeState {
            edge_process: None,
            edge_info: None,
            starting: false,
        }))
        .invoke_handler(tauri::generate_handler![start_edge, get_edge_info, kill_edge])
        .build(tauri::generate_context!())
        .expect("error while building tauri application");

    app.run(|app_handle, event| {
            if matches!(
                event,
                tauri::RunEvent::Exit | tauri::RunEvent::ExitRequested { .. }
            ) {
                if let Some(state) = app_handle.try_state::<Mutex<EdgeState>>() {
                    if let Ok(mut guard) = state.lock() {
                        if let Some(mut child) = guard.edge_process.take() {
                            let _ = child.kill();
                            let _ = child.wait();
                        }
                        guard.edge_info = None;
                    }
                }
            }
        });
}
