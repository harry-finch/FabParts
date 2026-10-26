#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]
mod assistance;
mod diagnostics;
mod external;
mod ingestion;
mod integration;
mod ipc;
mod previews;
mod publications;
mod validation;
mod workspace;

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
    pdf_handles: std::collections::VecDeque<String>,
    model_handles: std::collections::VecDeque<String>,
    preparation: Option<String>,
    prepared_pdf: std::collections::VecDeque<String>,
    prepared_models: std::collections::VecDeque<String>,
    restore_handle: Option<String>,
}
impl Session {
    async fn call(
        &mut self,
        method: &str,
        params: &Value,
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
        params: &Value,
        timeout: Duration,
        closing: watch::Receiver<bool>,
    ) -> Reply {
        self.sequence += 1;
        let id = format!("req-{}", self.sequence);
        let request = json!({"protocol_version":1,"request_id":id,"method":method,"params":params});
        let mut bytes = serde_json::to_vec(&request)
            .map_err(|_| Failure::new("INVALID_REQUEST", "Requête invalide."))?;
        bytes.push(b'\n');
        if bytes.len() > ipc::request_limit(method) {
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
    integration: integration::Configuration,
    data_dir: Mutex<Option<PathBuf>>,
    sandbox_dir: Option<PathBuf>,
    personal: bool,
    picking: Mutex<()>,
    session: Mutex<Option<Session>>,
    closing: watch::Sender<bool>,
}
impl Engine {
    fn writable(&self) -> bool {
        self.personal || self.sandbox_dir.is_some()
    }
    async fn authorize_preparation(&self, preparation: &str) -> Result<(), Failure> {
        let guard = self.session.lock().await;
        ingestion::authorize(
            self.writable(),
            guard.as_ref().and_then(|s| s.preparation.as_deref()),
            "ingestion_file_start",
            &json!({"preparation":preparation}),
        )
    }
    async fn call(&self, method: &str, params: Value) -> Reply {
        let mut guard = ipc::unless_closing(self.closing.subscribe(), async {
            tokio::time::timeout(TIMEOUT, self.session.lock())
                .await
                .map_err(|_| Failure::new("BUSY", "Le moteur est occupé."))
        })
        .await?;
        if method.starts_with("integration_") {
            integration::authorize(
                self.writable(),
                guard.as_ref().is_some_and(|s| s.preparation.is_some()),
                false,
                method,
            )?;
            if !["integration_get", "integration_verify"].contains(&method) {
                integration::authorize(true, false, integration::running()?, method)?;
            }
        }
        if method.starts_with("publication_") {
            publications::authorize(
                self.writable(),
                guard.as_ref().is_some_and(|s| s.preparation.is_some()),
                method,
            )?;
        }
        if method.starts_with("validation_") {
            validation::authorize(
                self.writable(),
                guard.as_ref().is_some_and(|s| s.preparation.is_some()),
                method,
            )?;
        }
        if method.starts_with("workspace_") {
            if !self.personal {
                return Err(Failure::new("READ_ONLY", "Personal workspace required"));
            }
            if guard.as_ref().is_some_and(|s| s.preparation.is_some()) {
                return Err(Failure::new("BUSY", "Finish the current preparation first"));
            }
            if method == "workspace_restore"
                && !guard
                    .as_ref()
                    .is_some_and(|s| s.restore_handle.as_deref() == params["handle"].as_str())
            {
                return Err(Failure::new("INVALID_PARAMS", "Backup capability required"));
            }
        }
        if method.starts_with("assistance_") {
            assistance::authorize(
                self.writable(),
                guard.as_ref().is_some_and(|s| s.preparation.is_some()),
            )?;
        }
        if method.starts_with("external_") {
            external::authorize(
                self.writable(),
                guard.as_ref().and_then(|s| s.preparation.as_deref()),
                method,
                &params,
            )?;
        }
        if method.starts_with("ingestion_") {
            ingestion::authorize(
                self.writable(),
                guard.as_ref().and_then(|s| s.preparation.as_deref()),
                method,
                &params,
            )?;
        }
        if ["get_model_status", "read_mesh_chunk"].contains(&method)
            && !guard.as_ref().is_some_and(|s| {
                s.model_handles
                    .iter()
                    .any(|h| Some(h.as_str()) == params["handle"].as_str())
            })
        {
            return Err(Failure::new(
                "INVALID_PARAMS",
                "Session 3D absente de ce moteur.",
            ));
        }
        if method == "read_pdf_chunk"
            && !guard.as_ref().is_some_and(|s| {
                s.pdf_handles
                    .iter()
                    .any(|h| Some(h.as_str()) == params["handle"].as_str())
            })
        {
            return Err(Failure::new(
                "INVALID_PARAMS",
                "Aperçu PDF absent de cette session.",
            ));
        }
        let result = guard
            .as_mut()
            .ok_or_else(|| {
                Failure::new("ENGINE_UNAVAILABLE", "Moteur indisponible. Redémarrez-le.")
            })?
            .call(
                method,
                &params,
                if method.starts_with("integration_") {
                    Duration::from_secs(600)
                } else if method.starts_with("publication_") {
                    publications::timeout(method)
                } else if method.starts_with("workspace_") || method.starts_with("validation_") {
                    Duration::from_secs(300)
                } else if method == "ingestion_commit" {
                    STARTUP_TIMEOUT
                } else {
                    TIMEOUT
                },
                self.closing.subscribe(),
            )
            .await;
        Self::finish_call(&mut guard, method, &params, result)
    }
    // Apply sidecar acknowledgements while the caller still holds the session lock.
    fn finish_call(
        guard: &mut Option<Session>,
        method: &str,
        params: &Value,
        result: Reply,
    ) -> Reply {
        if method == "get_model_status" {
            if let Ok(value) = &result {
                if let Err(error) = previews::mesh_descriptor(value) {
                    guard.take();
                    return Err(error);
                }
            }
        }
        if let (Ok(value), Some(session)) = (&result, guard.as_mut()) {
            if ["get_asset_preview", "ingestion_preview"].contains(&method) {
                if let Some(handle) = value["handle"].as_str() {
                    previews::handle(handle)?;
                    let handles = if value["kind"] == "MODEL_3D" {
                        &mut session.model_handles
                    } else {
                        &mut session.pdf_handles
                    };
                    while handles.len() >= 2 {
                        handles.pop_front();
                    }
                    handles.push_back(handle.to_owned());
                    if method == "ingestion_preview" {
                        let owned = if value["kind"] == "MODEL_3D" {
                            &mut session.prepared_models
                        } else {
                            &mut session.prepared_pdf
                        };
                        while owned.len() >= 2 {
                            owned.pop_front();
                        }
                        owned.push_back(handle.to_owned());
                    }
                }
            } else if ["release_preview", "release_model_preview"].contains(&method)
                && value["released"].as_bool() == Some(true)
            {
                if let Some(handle) = params["handle"].as_str() {
                    // Releases can arrive out of creation order. Remove only the
                    // acknowledged handle so the next preview cannot evict a live one.
                    let handles = if method == "release_model_preview" {
                        &mut session.model_handles
                    } else {
                        &mut session.pdf_handles
                    };
                    handles.retain(|registered| registered != handle);
                    let owned = if method == "release_model_preview" {
                        &mut session.prepared_models
                    } else {
                        &mut session.prepared_pdf
                    };
                    owned.retain(|registered| registered != handle);
                }
            }
        }
        if let (Ok(value), Some(session)) = (&result, guard.as_mut()) {
            if method == "workspace_verify" {
                session.restore_handle = value["handle"].as_str().map(str::to_owned);
            }
            if method == "workspace_restore" {
                session.restore_handle = None;
            }
            if (method == "ingestion_begin")
                || (method == "ingestion_cancel" && value["cancelled"] == true)
                || (method == "ingestion_commit" && value["status"] == "saved")
            {
                session
                    .pdf_handles
                    .retain(|h| !session.prepared_pdf.contains(h));
                session
                    .model_handles
                    .retain(|h| !session.prepared_models.contains(h));
                session.prepared_pdf.clear();
                session.prepared_models.clear();
                session.preparation = if method == "ingestion_begin" {
                    let handle = value["preparation"]
                        .as_str()
                        .ok_or_else(|| Failure::new("INVALID_RESPONSE", "Préparation absente."))?;
                    previews::handle(handle)?;
                    Some(handle.to_owned())
                } else {
                    None
                };
            }
        }
        if let Err(error) = &result {
            if !matches!(
                error.code.as_str(),
                "DOMAIN_ERROR"
                    | "INVALID_PARAMS"
                    | "READ_FAILED"
                    | "INTEGRATION_IO"
                    | "RESPONSE_TOO_LARGE"
                    | "READ_ONLY"
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
async fn get_asset_preview(engine: State<'_, Engine>, query: previews::PreviewQuery) -> Reply {
    query.validate()?;
    engine.call("get_asset_preview", json!(query)).await
}
#[tauri::command]
async fn read_pdf_chunk(engine: State<'_, Engine>, handle: String, offset: u32) -> Reply {
    previews::handle(&handle)?;
    previews::offset(offset)?;
    engine
        .call("read_pdf_chunk", json!({"handle":handle,"offset":offset}))
        .await
}
#[tauri::command]
async fn release_preview(engine: State<'_, Engine>, handle: String) -> Reply {
    previews::handle(&handle)?;
    engine
        .call("release_preview", json!({"handle":handle}))
        .await
}
#[tauri::command]
async fn get_model_status(engine: State<'_, Engine>, handle: String) -> Reply {
    previews::handle(&handle)?;
    engine
        .call("get_model_status", json!({"handle":handle}))
        .await
}
#[tauri::command]
async fn read_mesh_chunk(engine: State<'_, Engine>, handle: String, offset: u32) -> Reply {
    previews::handle(&handle)?;
    previews::offset(offset)?;
    engine
        .call("read_mesh_chunk", json!({"handle":handle,"offset":offset}))
        .await
}
#[tauri::command]
async fn release_model_preview(engine: State<'_, Engine>, handle: String) -> Reply {
    previews::handle(&handle)?;
    engine
        .call("release_model_preview", json!({"handle":handle}))
        .await
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
    if engine.writable() && data_dir.is_some() {
        return Err(Failure::new(
            "READ_ONLY",
            "Le dossier writable est fixé par l’hôte au lancement.",
        ));
    }
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
    let directory = configured.as_ref();
    if !engine.personal && !directory.is_some_and(|p| p.is_dir()) {
        return Err(Failure::new(
            "INVALID_DATA_DIR",
            "A controlled data directory is required",
        ));
    }
    let mut command = app
        .shell()
        .sidecar("fabparts-engine")
        .map_err(|_| Failure::new("LAUNCH_FAILED", "Sidecar absent du paquet."))?
        .env_clear()
        .env("TMPDIR", std::env::temp_dir())
        .set_raw_out(true)
        .set_process_group(true);
    if let Some(root) = &engine.integration.root {
        command = command.args(["--kicad-config-root".as_ref(), root.as_os_str()]);
        for version in &engine.integration.versions {
            command = command.args(["--kicad-version", version]);
        }
    }
    if let Some(path) = directory {
        command = command.args(["--data-dir".as_ref(), path.as_os_str()]);
    }
    if engine.personal {
        command = command.args(["--personal"]);
    }
    if engine.sandbox_dir.is_some() {
        command = command.args(["--sandbox"]);
    }
    // Optional local converter chosen by the launching user, never by the WebView.
    if let Some(path) = std::env::var_os("KIPART_FREECAD_CMD") {
        command = command.env("KIPART_FREECAD_CMD", path);
    }
    // Only M11 keys are forwarded; no general inheritance, DTO or diagnostic output.
    for (name, value) in assistance::credentials(|name| std::env::var(name).ok()) {
        command = command.env(name, value);
    }
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
        pdf_handles: Default::default(),
        model_handles: Default::default(),
        preparation: None,
        prepared_pdf: Default::default(),
        prepared_models: Default::default(),
        restore_handle: None,
    };
    let result = session
        .call(
            "health",
            &json!({}),
            if engine.personal { Duration::from_secs(300) } else { STARTUP_TIMEOUT },
            engine.closing.subscribe(),
        )
        .await
        .map_err(|error| {
            if error.code == "ENGINE_EXITED" {
                Failure::new(
                    if engine.personal {"WORKSPACE_UNAVAILABLE"} else if engine.sandbox_dir.is_some() { "SANDBOX_UNAVAILABLE" } else { "STARTUP_FAILED" },
                    if engine.sandbox_dir.is_some() { "Sandbox inaccessible, déjà ouvert ou incompatible. Fermez l’autre session avant de réessayer." } else { "Le moteur n’a pas pu ouvrir la copie. Vérifiez son dossier et son schéma." },
                )
            } else {
                error
            }
        })?;
    if result["read_only"].as_bool() != Some(!engine.writable()) {
        return Err(Failure::new(
            "INVALID_RESPONSE",
            "Le mode du moteur ne correspond pas à celui de l’hôte.",
        ));
    }
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
    let sandbox_dir = std::env::var_os("FABPARTS_SANDBOX_DIR").map(PathBuf::from);
    let personal = sandbox_dir.is_none() && data_dir.is_none();
    // Host-only isolation for qualification; never supplied by JavaScript.
    let personal_test = if personal {
        std::env::var_os("FABPARTS_USER_DATA_DIR").map(PathBuf::from)
    } else {
        None
    };
    let data_dir = sandbox_dir.clone().or(data_dir).or(personal_test);
    let (closing, _) = watch::channel(false);
    diagnostics::event("app_started", json!({"state":"starting"}));
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .manage(Engine {
            integration: integration::Configuration::discover(),
            data_dir: Mutex::new(data_dir),
            sandbox_dir,
            personal,
            picking: Mutex::new(()),
            session: Mutex::new(None),
            closing,
        })
        .setup(|app| {
            if app.state::<Engine>().personal {
                if let Some(window) = app.get_webview_window("main") {
                    window.set_title("FabParts")?;
                }
            } else if app.state::<Engine>().sandbox_dir.is_some() {
                if let Some(window) = app.get_webview_window("main") {
                    window.set_title("FabParts — TECH-03 · Sandbox")?;
                }
            }
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            health,
            list_libraries,
            list_components,
            get_component,
            restart_engine,
            get_asset_preview,
            read_pdf_chunk,
            release_preview,
            get_model_status,
            read_mesh_chunk,
            release_model_preview,
            ingestion::ingestion_command,
            external::external_command,
            assistance::assistance_command,
            ingestion::choose_ingestion_files,
            workspace::workspace_info,
            workspace::backup_workspace,
            workspace::choose_workspace_backup,
            workspace::restore_workspace,
            validation::get_validation,
            validation::run_validation,
            validation::accept_validation_warnings,
            integration::integration_command,
            publications::publication_query,
            publications::publish_version,
            publications::rebuild_publication
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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn preparation_cancel_and_commit_revoke_only_owned_preview_handles() {
        for (method, reply) in [
            ("ingestion_cancel", json!({"cancelled":true})),
            (
                "ingestion_commit",
                json!({"status":"saved","part_id":"confirmed"}),
            ),
        ] {
            let mut session = Some(empty_session());
            let regular = "a".repeat(48);
            let prepared = "b".repeat(48);
            issue(&mut session, &regular);
            Engine::finish_call(
                &mut session,
                "ingestion_begin",
                &json!({}),
                Ok(json!({"preparation":"c".repeat(48)})),
            )
            .unwrap();
            Engine::finish_call(
                &mut session,
                "ingestion_preview",
                &json!({}),
                Ok(json!({"kind":"DATASHEET","handle":prepared})),
            )
            .unwrap();
            assert_eq!(handles(&session), [regular.as_str(), prepared.as_str()]);
            Engine::finish_call(&mut session, method, &json!({}), Ok(reply)).unwrap();
            assert_eq!(handles(&session), [regular.as_str()]);
            assert!(session.as_ref().unwrap().preparation.is_none());
            assert!(session.as_ref().unwrap().prepared_pdf.is_empty());
        }
    }

    #[test]
    fn personal_workspace_capabilities_and_busy_preparation_are_host_gated() {
        tauri::async_runtime::block_on(async {
            let (closing, _) = watch::channel(false);
            let engine = Engine {
                integration: integration::Configuration::default(),
                data_dir: Mutex::new(None),
                sandbox_dir: None,
                personal: true,
                picking: Mutex::new(()),
                session: Mutex::new(Some(empty_session())),
                closing,
            };
            assert!(engine.writable());
            let handle = "a".repeat(48);
            assert_eq!(
                engine
                    .call("workspace_restore", json!({"handle":handle}))
                    .await
                    .unwrap_err()
                    .code,
                "INVALID_PARAMS"
            );
            {
                let mut session = engine.session.lock().await;
                Engine::finish_call(
                    &mut session,
                    "workspace_verify",
                    &json!({}),
                    Ok(json!({"handle":handle})),
                )
                .unwrap();
                assert_eq!(
                    session.as_ref().unwrap().restore_handle.as_deref(),
                    Some(handle.as_str())
                );
                session.as_mut().unwrap().preparation = Some("b".repeat(48));
            }
            assert_eq!(
                engine
                    .call("workspace_backup", json!({}))
                    .await
                    .unwrap_err()
                    .code,
                "BUSY"
            );
        });
    }

    fn empty_session() -> Session {
        let (_tx, rx) = tauri::async_runtime::channel(1);
        Session {
            child: None,
            rx,
            sequence: 0,
            pdf_handles: Default::default(),
            model_handles: Default::default(),
            preparation: None,
            prepared_pdf: Default::default(),
            prepared_models: Default::default(),
            restore_handle: None,
        }
    }
    fn issue(session: &mut Option<Session>, handle: &str) {
        Engine::finish_call(
            session,
            "get_asset_preview",
            &json!({}),
            Ok(json!({"status":"ready", "handle":handle})),
        )
        .unwrap();
    }
    fn release(session: &mut Option<Session>, handle: &str) {
        Engine::finish_call(
            session,
            "release_preview",
            &json!({"handle":handle}),
            Ok(json!({"released":true})),
        )
        .unwrap();
    }
    fn handles(session: &Option<Session>) -> Vec<&str> {
        session
            .as_ref()
            .unwrap()
            .pdf_handles
            .iter()
            .map(String::as_str)
            .collect()
    }

    fn issue_model(session: &mut Option<Session>, handle: &str) {
        Engine::finish_call(
            session,
            "get_asset_preview",
            &json!({}),
            Ok(json!({"status":"loading", "kind":"MODEL_3D", "handle":handle})),
        )
        .unwrap();
    }
    #[test]
    fn models_release_out_of_order_and_keep_pdf_authority_separate() {
        let (h1, h2, h3) = ("a".repeat(48), "b".repeat(48), "c".repeat(48));
        let mut session = Some(empty_session());
        issue(&mut session, &h1);
        issue_model(&mut session, &h1);
        issue_model(&mut session, &h2);
        Engine::finish_call(
            &mut session,
            "release_model_preview",
            &json!({"handle":h2}),
            Ok(json!({"released":true})),
        )
        .unwrap();
        issue_model(&mut session, &h3);
        assert_eq!(
            session.as_ref().unwrap().model_handles,
            [h1.clone(), h3.clone()]
        );
        assert_eq!(handles(&session), [h1.as_str()]);
        for reply in [
            Err(Failure::new("DOMAIN_ERROR", "expired")),
            Ok(json!({"released":false})),
        ] {
            let _ = Engine::finish_call(
                &mut session,
                "release_model_preview",
                &json!({"handle":h1}),
                reply,
            );
            assert_eq!(
                session.as_ref().unwrap().model_handles,
                [h1.clone(), h3.clone()]
            );
        }
        let _ = Engine::finish_call(
            &mut session,
            "get_model_status",
            &json!({"handle":h1}),
            Ok(json!({"status":"ready","size_bytes":17000000})),
        );
        assert!(session.is_none());
    }
    #[test]
    fn stale_model_handles_cannot_cross_restart_or_pdf_registry() {
        tauri::async_runtime::block_on(async {
            let handle = "a".repeat(48);
            let mut session = Some(empty_session());
            issue(&mut session, &handle);
            let (closing, _) = watch::channel(false);
            let engine = Engine {
                integration: integration::Configuration::default(),
                data_dir: Mutex::new(None),
                sandbox_dir: None,
                personal: false,
                picking: Mutex::new(()),
                session: Mutex::new(session),
                closing,
            };
            for method in ["get_model_status", "read_mesh_chunk"] {
                assert_eq!(
                    engine
                        .call(method, json!({"handle":handle,"offset":0}))
                        .await
                        .unwrap_err()
                        .code,
                    "INVALID_PARAMS"
                );
            }
            let mut guard = engine.session.lock().await;
            issue_model(&mut guard, &handle);
            guard.take().unwrap().stop().await;
            *guard = Some(empty_session());
            drop(guard);
            assert_eq!(
                engine
                    .call("get_model_status", json!({"handle":handle}))
                    .await
                    .unwrap_err()
                    .code,
                "INVALID_PARAMS"
            );
        });
    }

    #[test]
    fn h1_h2_h3_release_order_preserves_the_remaining_handle() {
        let (h1, h2, h3) = ("a".repeat(48), "b".repeat(48), "c".repeat(48));
        // In particular, releasing H2 must not cause H3 to evict the still-live H1.
        for (released, remaining) in [(&h2, &h1), (&h1, &h2)] {
            let mut session = Some(empty_session());
            issue(&mut session, &h1);
            issue(&mut session, &h2);
            release(&mut session, released);
            issue(&mut session, &h3);
            assert_eq!(handles(&session), [remaining.as_str(), h3.as_str()]);
        }
    }

    #[test]
    fn repeated_or_unknown_release_is_idempotent_and_fifo_stays_bounded() {
        let (h1, h2, h3) = ("a".repeat(48), "b".repeat(48), "c".repeat(48));
        let mut session = Some(empty_session());
        issue(&mut session, &h1);
        issue(&mut session, &h2);
        release(&mut session, &h1);
        release(&mut session, &h1);
        release(&mut session, &h3);
        assert_eq!(handles(&session), [h2.as_str()]);
        issue(&mut session, &h3);
        issue(&mut session, &h1);
        assert_eq!(handles(&session), [h3.as_str(), h1.as_str()]);
    }

    #[test]
    fn failed_or_unconfirmed_release_keeps_live_capabilities() {
        let (h1, h2) = ("a".repeat(48), "b".repeat(48));
        let mut session = Some(empty_session());
        issue(&mut session, &h1);
        issue(&mut session, &h2);
        for reply in [
            Err(Failure::new("DOMAIN_ERROR", "Release failed")),
            Err(Failure::new("INVALID_PARAMS", "Invalid release")),
            Err(Failure::new("READ_FAILED", "Read failed")),
            Err(Failure::new("RESPONSE_TOO_LARGE", "Response too large")),
            Ok(json!({"released":false})),
            Ok(json!({})),
        ] {
            let failed = reply.is_err();
            let result = Engine::finish_call(
                &mut session,
                "release_preview",
                &json!({"handle":h2}),
                reply,
            );
            assert_eq!(result.is_err(), failed);
            assert_eq!(handles(&session), [h1.as_str(), h2.as_str()]);
        }
        release(&mut session, &h2);
        assert_eq!(handles(&session), [h1.as_str()]);
    }

    #[test]
    fn integration_io_failure_keeps_session_for_recovery() {
        let mut session = Some(empty_session());
        let result = Engine::finish_call(
            &mut session,
            "integration_activate",
            &json!({}),
            Err(Failure::new("INTEGRATION_IO", "Permission denied")),
        );
        assert!(result.is_err());
        assert!(session.is_some());
    }
    #[test]
    fn failed_transport_discards_all_session_capabilities() {
        let h1 = "a".repeat(48);
        for code in [
            "TIMEOUT",
            "ENGINE_IO",
            "ENGINE_EXITED",
            "INVALID_RESPONSE",
            "APP_CLOSING",
        ] {
            let mut session = Some(empty_session());
            issue(&mut session, &h1);
            let result = Engine::finish_call(
                &mut session,
                "release_preview",
                &json!({"handle":h1}),
                Err(Failure::new(code, "Transport failed")),
            );
            assert_eq!(result.unwrap_err().code, code);
            assert!(session.is_none());
        }
    }

    #[test]
    fn expired_pdf_read_preserves_other_handles_and_release_cleans_up() {
        let (h1, h2, h3) = ("a".repeat(48), "b".repeat(48), "c".repeat(48));
        let mut session = Some(empty_session());
        issue(&mut session, &h1);
        issue(&mut session, &h2);
        let result = Engine::finish_call(
            &mut session,
            "read_pdf_chunk",
            &json!({"handle":h1,"offset":0}),
            Err(Failure::new(
                "DOMAIN_ERROR",
                "Aperçu PDF expiré. Rouvrez le document.",
            )),
        );
        assert_eq!(result.unwrap_err().code, "DOMAIN_ERROR");
        // IPC v1 also uses DOMAIN_ERROR for invalid offsets: do not infer expiry
        // from this generic code or localized text. Python remains authoritative.
        assert_eq!(handles(&session), [h1.as_str(), h2.as_str()]);
        release(&mut session, &h1);
        issue(&mut session, &h3);
        assert_eq!(handles(&session), [h2.as_str(), h3.as_str()]);
    }

    #[test]
    fn released_and_previous_session_handles_are_denied_before_ipc() {
        tauri::async_runtime::block_on(async {
            let (h1, h2) = ("a".repeat(48), "b".repeat(48));
            let mut session = Some(empty_session());
            issue(&mut session, &h1);
            issue(&mut session, &h2);
            release(&mut session, &h2);
            let (closing, _) = watch::channel(false);
            let engine = Engine {
                integration: integration::Configuration::default(),
                data_dir: Mutex::new(None),
                sandbox_dir: None,
                personal: false,
                picking: Mutex::new(()),
                session: Mutex::new(session),
                closing,
            };
            assert_eq!(
                engine
                    .call("read_pdf_chunk", json!({"handle":h2,"offset":0}))
                    .await
                    .unwrap_err()
                    .code,
                "INVALID_PARAMS"
            );
            assert!(engine.session.lock().await.is_some());
            // The restart path takes/stops the old Session and installs a fresh one.
            let mut guard = engine.session.lock().await;
            guard.take().unwrap().stop().await;
            *guard = Some(empty_session());
            drop(guard);
            assert_eq!(
                engine
                    .call("read_pdf_chunk", json!({"handle":h1,"offset":0}))
                    .await
                    .unwrap_err()
                    .code,
                "INVALID_PARAMS"
            );
            assert!(engine
                .session
                .lock()
                .await
                .as_ref()
                .unwrap()
                .pdf_handles
                .is_empty());
        });
    }
}
