//! Host-owned workspace operations: native backup selection, opaque restore authority.
use crate::{
    ipc::{Failure, Reply},
    Engine,
};
use serde_json::json;
use tauri::{Manager, State};
use tauri_plugin_dialog::{DialogExt, MessageDialogButtons, MessageDialogKind};

#[tauri::command]
pub async fn workspace_info(engine: State<'_, Engine>) -> Reply {
    engine.call("workspace_info", json!({})).await
}
#[tauri::command]
pub async fn backup_workspace(engine: State<'_, Engine>) -> Reply {
    engine.call("workspace_backup", json!({})).await
}
#[tauri::command]
pub async fn choose_workspace_backup(
    app: tauri::AppHandle,
    engine: State<'_, Engine>,
    locale: String,
) -> Reply {
    if !engine.personal {
        return Err(Failure::new("READ_ONLY", "Personal workspace required"));
    }
    let _picking = engine
        .picking
        .try_lock()
        .map_err(|_| Failure::new("BUSY", "Picker already open"))?;
    let (send, receive) = tokio::sync::oneshot::channel();
    app.dialog()
        .file()
        .set_title(if locale == "en" {
            "FabParts — Select backup folder"
        } else {
            "FabParts — Choisir le dossier de sauvegarde"
        })
        .pick_folder(move |path| {
            let _ = send.send(path);
        });
    let path = crate::ipc::unless_closing(engine.closing.subscribe(), async {
        receive
            .await
            .map_err(|_| Failure::new("FILE_PICKER", "Picker unavailable"))
    })
    .await?;
    let Some(path) = path else {
        return Ok(json!({"cancelled":true}));
    };
    let path = path
        .into_path()
        .map_err(|_| Failure::new("INVALID_PARAMS", "Local folder required"))?;
    engine.call("workspace_verify", json!({"path":path})).await
}
#[tauri::command]
pub async fn restore_workspace(
    app: tauri::AppHandle,
    engine: State<'_, Engine>,
    handle: String,
    locale: String,
) -> Reply {
    crate::previews::handle(&handle)?;
    if !engine.personal {
        return Err(Failure::new("READ_ONLY", "Personal workspace required"));
    }
    let _picking = engine
        .picking
        .try_lock()
        .map_err(|_| Failure::new("BUSY", "Decision already open"))?;
    let window = app
        .get_webview_window("main")
        .ok_or_else(|| Failure::new("APP_CLOSING", "Window unavailable"))?;
    let (send, receive) = tokio::sync::oneshot::channel();
    app.dialog().message(if locale=="en" {
        "Restore into a new workspace? Your current data will be backed up and retained. Restart is required."
    } else {"Restaurer dans un nouvel espace ? Vos données actuelles seront sauvegardées et conservées. Un redémarrage sera nécessaire."})
        .title("FabParts").parent(&window).kind(MessageDialogKind::Warning).buttons(MessageDialogButtons::OkCancel).show(move |confirmed| { let _ = send.send(confirmed); });
    let confirmed = crate::ipc::unless_closing(engine.closing.subscribe(), async {
        receive
            .await
            .map_err(|_| Failure::new("FILE_PICKER", "Confirmation unavailable"))
    })
    .await?;
    if !confirmed {
        return Ok(json!({"cancelled":true}));
    }
    engine
        .call("workspace_restore", json!({"handle":handle}))
        .await
}
