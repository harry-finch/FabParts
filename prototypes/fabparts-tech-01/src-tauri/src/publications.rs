//! M7 queries and native-owned reconstruction destinations; no WebView paths/manifests.
use crate::{
    ipc::{Failure, Reply},
    Engine,
};
use serde::{Deserialize, Serialize};
use serde_json::json;
use std::time::Duration;
use tauri::{Manager, State};
use tauri_plugin_dialog::DialogExt;

#[derive(Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Query {
    action: String,
    id: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    version: Option<u32>,
    #[serde(default)]
    offset: u32,
}
impl Query {
    fn validate(&self) -> Result<(), Failure> {
        let historical = ["status", "details", "verify"].contains(&self.action.as_str());
        if !["history", "prepare", "status", "details", "verify"].contains(&self.action.as_str())
            || self.id.len() > 36
            || uuid::Uuid::parse_str(&self.id).is_err()
            || self.offset > 1_000_000
            || historical != self.version.is_some()
            || self.version.is_some_and(|v| !(1..=999999).contains(&v))
            || (["status", "verify"].contains(&self.action.as_str()) && self.offset != 0)
        {
            return Err(Failure::new("INVALID_PARAMS", "Invalid publication query"));
        }
        Ok(())
    }
}
pub fn timeout(method: &str) -> Duration {
    Duration::from_secs(match method {
        "publication_publish" | "publication_rebuild" => 600,
        "publication_prepare" | "publication_history" | "publication_verify" => 300,
        "publication_status" | "publication_details" => 60,
        _ => 8,
    })
}
pub fn authorize(writable: bool, preparing: bool, method: &str) -> Result<(), Failure> {
    if ["publication_publish", "publication_rebuild"].contains(&method) && !writable {
        return Err(Failure::new("READ_ONLY", "Publication writes unavailable"));
    }
    if preparing {
        return Err(Failure::new("BUSY", "Finish the current preparation first"));
    }
    Ok(())
}
#[tauri::command]
pub async fn publication_query(engine: State<'_, Engine>, query: Query) -> Reply {
    query.validate()?;
    let mut params = json!({"id":query.id});
    if let Some(version) = query.version {
        params["version"] = json!(version);
    }
    if ["history", "prepare", "details"].contains(&query.action.as_str()) {
        params["offset"] = json!(query.offset);
    }
    engine
        .call(&format!("publication_{}", query.action), params)
        .await
}
#[tauri::command]
pub async fn publish_version(
    engine: State<'_, Engine>,
    id: String,
    version: u32,
    handle: String,
) -> Reply {
    Query {
        action: "status".into(),
        id: id.clone(),
        version: Some(version),
        offset: 0,
    }
    .validate()?;
    crate::previews::handle(&handle)?;
    engine
        .call(
            "publication_publish",
            json!({"id":id,"version":version,"handle":handle}),
        )
        .await
}
#[tauri::command]
pub async fn rebuild_publication(
    app: tauri::AppHandle,
    engine: State<'_, Engine>,
    id: String,
    version: u32,
    locale: String,
) -> Reply {
    Query {
        action: "status".into(),
        id: id.clone(),
        version: Some(version),
        offset: 0,
    }
    .validate()?;
    authorize(engine.writable(), false, "publication_rebuild")?;
    let _picking = engine
        .picking
        .try_lock()
        .map_err(|_| Failure::new("BUSY", "Picker already open"))?;
    let (send, receive) = tokio::sync::oneshot::channel();
    let window = app
        .get_webview_window("main")
        .ok_or_else(|| Failure::new("APP_CLOSING", "Window unavailable"))?;
    app.dialog()
        .file()
        .set_parent(&window)
        .set_title(if locale == "en" {
            "FabParts — Parent folder for a new reconstruction"
        } else {
            "FabParts — Dossier parent de la nouvelle reconstruction"
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
    let parent = path
        .into_path()
        .map_err(|_| Failure::new("INVALID_PARAMS", "Local folder required"))?;
    let parent = parent
        .canonicalize()
        .map_err(|_| Failure::new("INVALID_PARAMS", "Existing local folder required"))?;
    if engine
        .data_dir
        .lock()
        .await
        .as_ref()
        .is_some_and(|root| parent.starts_with(root))
    {
        return Err(Failure::new(
            "INVALID_PARAMS",
            "Destination inside workspace refused",
        ));
    }
    let destination = parent.join(format!(
        "FabParts-v{:06}-{}",
        version,
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map_err(|_| Failure::new("CLOCK", "Clock unavailable"))?
            .as_nanos()
    ));
    let mut result = engine
        .call(
            "publication_rebuild",
            json!({"id":id,"version":version,"destination":destination}),
        )
        .await?;
    result["destination"] = json!(destination);
    Ok(result)
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn strict_queries_and_guards() {
        let valid = json!({"action":"history","id":uuid::Uuid::nil()});
        assert!(serde_json::from_value::<Query>(valid.clone())
            .unwrap()
            .validate()
            .is_ok());
        for extra in ["destination", "manifest", "handle"] {
            let mut bad = valid.clone();
            bad[extra] = json!("arbitrary");
            assert!(serde_json::from_value::<Query>(bad).is_err());
        }
        for value in [
            json!({"action":"publish","id":uuid::Uuid::nil()}),
            json!({"action":"verify","id":uuid::Uuid::nil(),"version":0}),
            json!({"action":"history","id":"/tmp"}),
        ] {
            assert!(serde_json::from_value::<Query>(value)
                .unwrap()
                .validate()
                .is_err());
        }
        assert!(authorize(false, false, "publication_verify").is_ok());
        assert_eq!(
            authorize(false, false, "publication_publish")
                .unwrap_err()
                .code,
            "READ_ONLY"
        );
        assert_eq!(
            authorize(false, false, "publication_rebuild")
                .unwrap_err()
                .code,
            "READ_ONLY"
        );
        assert_eq!(
            authorize(true, true, "publication_publish")
                .unwrap_err()
                .code,
            "BUSY"
        );
        assert_eq!(timeout("health"), Duration::from_secs(8));
        assert_eq!(timeout("publication_publish"), Duration::from_secs(600));
    }
}
