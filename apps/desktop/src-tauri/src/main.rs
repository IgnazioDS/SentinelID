// Prevents additional console window on Windows in release, DO NOT REMOVE!!
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use serde::{Deserialize, Serialize};
use std::process::{Command, Child};
use std::sync::Mutex;
use uuid::Uuid;
use std::time::Duration;

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
async fn start_edge(state: tauri::State<'_, Mutex<EdgeState>>) -> Result<EdgeInfo, String> {
    // Select a random free port between 8000-9000
    // Use rand::random instead of thread_rng to avoid Send issues across await
    let port: u16 = rand::random::<u16>() % 1000 + 8000;

    // Generate a random token (UUID)
    let token = Uuid::new_v4().to_string();

    // Start edge process (in dev mode, it's in apps/edge)
    #[cfg(debug_assertions)]
    let mut edge_cmd = {
        // Dev mode: run edge from source using uvicorn
        // Assuming we're running from project root or have proper paths
        let mut cmd = Command::new("python");
        cmd.arg("-m")
            .arg("uvicorn")
            .arg("sentinelid_edge.main:app")
            .arg("--host")
            .arg("127.0.0.1")
            .arg("--port")
            .arg(port.to_string())
            .env("EDGE_AUTH_TOKEN", &token)
            .env("EDGE_ENV", "dev");
        cmd.current_dir("./apps/edge");
        cmd
    };

    #[cfg(not(debug_assertions))]
    let mut edge_cmd = {
        // Production: would use bundled binary (TODO: bundle edge binary)
        panic!("Production edge bundling not yet implemented")
    };

    let child = edge_cmd
        .spawn()
        .map_err(|e| format!("Failed to start edge process: {}", e))?;

    // Poll health endpoint until ready (max 10 attempts)
    let base_url = format!("http://127.0.0.1:{}", port);
    let health_url = format!("{}/api/v1/", base_url);

    for attempt in 0..10 {
        match reqwest::Client::new()
            .get(&health_url)
            .timeout(Duration::from_secs(1))
            .send()
            .await
        {
            Ok(resp) if resp.status().is_success() => {
                let edge_info = EdgeInfo {
                    base_url: base_url.clone(),
                    token: token.clone(),
                };

                // Store edge process and info in state
                {
                    let mut app_state = state.lock().map_err(|e| e.to_string())?;
                    app_state.edge_process = Some(child);
                    app_state.edge_info = Some(edge_info.clone());
                }

                return Ok(edge_info);
            }
            _ => {
                if attempt < 9 {
                    tokio::time::sleep(Duration::from_millis(500)).await;
                }
            }
        }
    }

    Err("Failed to connect to edge after 5 seconds".to_string())
}

#[tauri::command]
fn get_edge_info(state: tauri::State<Mutex<EdgeState>>) -> Result<EdgeInfo, String> {
    let state = state.lock().map_err(|e| e.to_string())?;
    state
        .edge_info
        .clone()
        .ok_or_else(|| "Edge not started".to_string())
}

#[tauri::command]
fn kill_edge(state: tauri::State<Mutex<EdgeState>>) -> Result<(), String> {
    let mut state = state.lock().map_err(|e| e.to_string())?;
    if let Some(mut child) = state.edge_process.take() {
        let _ = child.kill();
    }
    Ok(())
}

fn main() {
    tauri::Builder::default()
        .manage(Mutex::new(EdgeState {
            edge_process: None,
            edge_info: None,
        }))
        .invoke_handler(tauri::generate_handler![start_edge, get_edge_info, kill_edge])
        .on_window_event(|_window_event| {})
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
