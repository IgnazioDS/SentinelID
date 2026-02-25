#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use serde::{Deserialize, Serialize};
use std::net::TcpListener;
use std::process::{Child, Command};
use std::sync::Mutex;
use std::time::Duration;
use tauri::Manager;
use uuid::Uuid;

#[cfg(not(debug_assertions))]
use std::path::PathBuf;
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
}

#[tauri::command]
async fn start_edge(
    app: tauri::AppHandle,
    state: tauri::State<'_, Mutex<EdgeState>>,
) -> Result<EdgeInfo, String> {
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
    }

    let port = find_free_port()?;
    let token = Uuid::new_v4().to_string();
    let base_url = format!("http://127.0.0.1:{}", port);

    let mut edge_cmd = build_edge_command(&app, port, &token)?;
    let mut child = edge_cmd
        .spawn()
        .map_err(|e| format!("Failed to start edge process: {}", e))?;

    if let Err(err) = wait_for_health(&base_url).await {
        let _ = child.kill();
        let _ = child.wait();
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
        // In dev we still use source Edge for faster iteration.
        let mut cmd = Command::new("python");
        cmd.arg("-m")
            .arg("uvicorn")
            .arg("sentinelid_edge.main:app")
            .arg("--host")
            .arg("127.0.0.1")
            .arg("--port")
            .arg(port.to_string())
            .env("EDGE_HOST", "127.0.0.1")
            .env("EDGE_PORT", port.to_string())
            .env("EDGE_AUTH_TOKEN", token)
            .env("EDGE_ENV", "dev")
            .current_dir("./apps/edge");
        Ok(cmd)
    }
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
