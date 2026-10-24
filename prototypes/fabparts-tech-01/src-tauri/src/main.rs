#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]
mod diagnostics;
mod ipc;

use ipc::{Failure, Reply, STARTUP_TIMEOUT, TIMEOUT};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::{
    path::PathBuf,
    time::{Duration, Instant},
};
use tauri::{async_runtime::Receiver, Manager, State};
use tauri_plugin_shell::{
    process::{CommandChild, CommandEvent},
    ShellExt,
};
use tokio::sync::{watch, Mutex};

struct Session {
    child: Option<CommandChild>,
    rx: Receiver<CommandEvent>,
    sequence: u64,
}
impl Session {
    async fn call(
        &mut self,
        method: &str,
        params: Value,
        timeout: Duration,
        closing: watch::Receiver<bool>,
    ) -> Reply {
        let started = Instant::now();
        // Include failures before receive (notably a broken stdin after an idle crash).
        let result = self.exchange(method, params, timeout, closing).await;
        let pid = self.child.as_ref().map(CommandChild::pid);
        match &result {
            Ok(_) if diagnostics::requests_enabled() && method != "health" => diagnostics::event(
                "request_ok",
                json!({"sidecar_pid":pid,"method":method,"elapsed_ms":started.elapsed().as_millis()}),
            ),
            Err(error) => diagnostics::event(
                "request_failed",
                json!({"sidecar_pid":pid,"method":method,"code":error.code,"elapsed_ms":started.elapsed().as_millis()}),
            ),
            _ => (),
        }
        result
    }
    async fn exchange(
        &mut self,
        method: &str,
        params: Value,
        timeout: Duration,
        closing: watch::Receiver<bool>,
    ) -> Reply {
        self.sequence += 1;
        let id = format!("req-{}", self.sequence);
        let request = json!({"protocol_version":1,"request_id":id,"method":method,"params":params});
        let mut bytes = serde_json::to_vec(&request)
            .map_err(|_| Failure::new("INVALID_REQUEST", "Requête invalide."))?;
        bytes.push(b'\n');
        if bytes.len() > 16384 {
            return Err(Failure::new("FRAME_TOO_LARGE", "Requête trop volumineuse."));
        }
        self.child
            .as_mut()
            .ok_or_else(|| Failure::new("ENGINE_UNAVAILABLE", "Moteur arrêté."))?
            .write(&bytes)
            .map_err(|_| Failure::new("ENGINE_IO", "Le moteur est indisponible."))?;
        ipc::unless_closing(closing, ipc::receive(&mut self.rx, &id, timeout)).await
    }
    async fn stop(mut self) {
        let pid = self.child.as_ref().map(CommandChild::pid);
        diagnostics::event("stopping", json!({"sidecar_pid":pid,"state":"stopping"}));
        if let Some(child) = self.child.as_mut() {
            let _ = child.write(b"{\"protocol_version\":1,\"request_id\":\"close\",\"method\":\"shutdown\",\"params\":{}}\n");
        }
        let status = tokio::time::timeout(Duration::from_secs(2), async {
            while let Some(event) = self.rx.recv().await {
                if let CommandEvent::Terminated(status) = event {
                    return Some(status);
                }
            }
            None
        })
        .await
        .ok()
        .flatten();
        if let Some(child) = self.child.take() {
            if let Some(status) = status {
                diagnostics::event(
                    "stopped",
                    json!({"sidecar_pid":pid,"cooperative":true,"exit_code":status.code,"signal":status.signal}),
                );
            } else {
                let killed = child.kill().is_ok();
                diagnostics::event(
                    "stopped",
                    json!({"sidecar_pid":pid,"cooperative":false,"code":if killed {"FORCED_STOP"} else {"KILL_FAILED"}}),
                );
            }
        }
    }
}
impl Drop for Session {
    fn drop(&mut self) {
        if let Some(child) = self.child.take() {
            let pid = child.pid();
            let killed = child.kill().is_ok();
            diagnostics::event(
                "session_discarded",
                json!({"sidecar_pid":pid,"code":if killed {"STOP_REQUESTED"} else {"KILL_FAILED"}}),
            );
        }
    }
}
struct Engine {
    data_dir: Mutex<Option<PathBuf>>,
    session: Mutex<Option<Session>>,
    closing: watch::Sender<bool>,
}
impl Engine {
    async fn call(&self, method: &str, params: Value) -> Reply {
        let mut guard = ipc::unless_closing(self.closing.subscribe(), async {
            tokio::time::timeout(TIMEOUT, self.session.lock())
                .await
                .map_err(|_| Failure::new("BUSY", "Le moteur est occupé."))
        })
        .await?;
        let result = guard
            .as_mut()
            .ok_or_else(|| {
                Failure::new("ENGINE_UNAVAILABLE", "Moteur indisponible. Redémarrez-le.")
            })?
            .call(method, params, TIMEOUT, self.closing.subscribe())
            .await;
        if let Err(error) = &result {
            if !matches!(
                error.code.as_str(),
                "DOMAIN_ERROR" | "INVALID_PARAMS" | "READ_FAILED" | "RESPONSE_TOO_LARGE"
            ) {
                // Discard a failed stream, including all late responses.
                guard.take();
            }
        }
        result
    }
}
#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct ListQuery {
    library: String,
    search: String,
    category: String,
    package: String,
    state: String,
    limit: u32,
    offset: u32,
}
#[tauri::command]
async fn health(engine: State<'_, Engine>) -> Reply {
    engine.call("health", json!({})).await
}
#[tauri::command]
async fn list_libraries(engine: State<'_, Engine>) -> Reply {
    engine.call("list_libraries", json!({})).await
}
#[tauri::command]
async fn list_components(engine: State<'_, Engine>, query: ListQuery) -> Reply {
    engine.call("list_components", json!(query)).await
}
#[tauri::command]
async fn get_component(engine: State<'_, Engine>, id: String) -> Reply {
    engine.call("get_component", json!({"id":id})).await
}
#[tauri::command]
async fn restart_engine(
    app: tauri::AppHandle,
    engine: State<'_, Engine>,
    data_dir: Option<String>,
) -> Reply {
    let result = restart_session(&app, &engine, data_dir).await;
    if let Err(error) = &result {
        diagnostics::event(
            "startup_failed",
            json!({"code":error.code,"state":"failed"}),
        );
    }
    result
}
async fn restart_session(
    app: &tauri::AppHandle,
    engine: &Engine,
    data_dir: Option<String>,
) -> Reply {
    let mut guard = ipc::unless_closing(engine.closing.subscribe(), async {
        tokio::time::timeout(STARTUP_TIMEOUT, engine.session.lock())
            .await
            .map_err(|_| Failure::new("BUSY", "Le moteur est occupé."))
    })
    .await?;
    if let Some(old) = guard.take() {
        old.stop().await;
    }
    if *engine.closing.borrow() {
        return Err(Failure::new(
            "APP_CLOSING",
            "Application en cours de fermeture.",
        ));
    }
    diagnostics::event("starting", json!({"state":"starting"}));
    let mut configured = engine.data_dir.lock().await;
    if let Some(path) = data_dir {
        if path.is_empty() || path.len() > 4096 || !PathBuf::from(&path).is_absolute() {
            return Err(Failure::new(
                "INVALID_DATA_DIR",
                "Un chemin absolu vers une copie contrôlée est requis.",
            ));
        }
        *configured = Some(PathBuf::from(path));
    }
    let directory = configured.as_ref().ok_or_else(|| {
        Failure::new(
            "DATA_DIR_REQUIRED",
            "Lancez TECH-01 avec --data-dir et une copie contrôlée du catalogue.",
        )
    })?;
    if !directory.is_dir() {
        return Err(Failure::new(
            "INVALID_DATA_DIR",
            "Le dossier de la copie est introuvable.",
        ));
    }
    let command = app
        .shell()
        .sidecar("fabparts-engine")
        .map_err(|_| Failure::new("LAUNCH_FAILED", "Sidecar absent du paquet."))?
        .args(["--data-dir".as_ref(), directory.as_os_str()])
        .env_clear()
        .env("TMPDIR", std::env::temp_dir())
        .set_raw_out(true)
        .set_process_group(true);
    let (rx, child) = command
        .spawn()
        .map_err(|_| Failure::new("LAUNCH_FAILED", "Impossible de lancer le moteur embarqué."))?;
    let pid = child.pid();
    diagnostics::event(
        "spawned",
        json!({"sidecar_pid":pid,"pgid":diagnostics::process_group(pid),"state":"starting"}),
    );
    let mut session = Session {
        child: Some(child),
        rx,
        sequence: 0,
    };
    let result = session
        .call(
            "health",
            json!({}),
            STARTUP_TIMEOUT,
            engine.closing.subscribe(),
        )
        .await
        .map_err(|error| {
            if error.code == "ENGINE_EXITED" {
                Failure::new(
                    "STARTUP_FAILED",
                    "Le moteur n’a pas pu ouvrir la copie. Vérifiez son dossier et son schéma.",
                )
            } else {
                error
            }
        })?;
    diagnostics::event(
        "ready",
        json!({"sidecar_pid":pid,"worker_pid":result["pid"],"state":"ready"}),
    );
    *guard = Some(session);
    Ok(result)
}
fn main() {
    let mut args = std::env::args_os().skip(1);
    let data_dir = match args.next().as_deref() {
        Some(arg) if arg == "--data-dir" => args.next().map(PathBuf::from),
        _ => None,
    };
    let (closing, _) = watch::channel(false);
    diagnostics::event("app_started", json!({"state":"starting"}));
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(Engine {
            data_dir: Mutex::new(data_dir),
            session: Mutex::new(None),
            closing,
        })
        .invoke_handler(tauri::generate_handler![
            health,
            list_libraries,
            list_components,
            get_component,
            restart_engine
        ])
        .build(tauri::generate_context!())
        .expect("FabParts TECH-01 startup");
    app.run(|app, event| {
        if matches!(event, tauri::RunEvent::Exit) {
            tauri::async_runtime::block_on(async {
                let state = app.state::<Engine>();
                state.closing.send_replace(true);
                diagnostics::event("app_closing", json!({"state":"closing"}));
                if let Some(session) = state.session.lock().await.take() {
                    session.stop().await;
                };
                diagnostics::event("app_closed", json!({"state":"closed"}));
            });
        }
    });
}
