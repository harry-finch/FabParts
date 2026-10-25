//! Typed business commands and a native-picker-only file capability.
use crate::{
    ipc::{Failure, Reply},
    previews, Engine,
};
use base64::{engine::general_purpose::STANDARD, Engine as _};
use serde::{Deserialize, Serialize};
use serde_json::json;
use sha2::{Digest, Sha256};
use std::{
    collections::BTreeMap,
    fs::{File, Metadata, OpenOptions},
    io::Read,
    path::PathBuf,
};
use tauri::State;
use tauri_plugin_dialog::DialogExt;

pub const FILE_LIMIT: u64 = 16 * 1024 * 1024;

pub fn authorize(
    writable: bool,
    current: Option<&str>,
    method: &str,
    params: &serde_json::Value,
) -> Result<(), Failure> {
    if !writable {
        return Err(Failure::new(
            "READ_ONLY",
            "Cette session est ouverte en lecture seule.",
        ));
    }
    if !["ingestion_begin", "ingestion_result"].contains(&method)
        && (current.is_none() || current != params["preparation"].as_str())
    {
        return Err(Failure::new(
            "INVALID_PARAMS",
            "Préparation expirée ou appartenant à un autre moteur.",
        ));
    }
    Ok(())
}

fn invalid() -> Failure {
    Failure::new("INVALID_PARAMS", "Paramètres d’ingestion invalides.")
}
fn identifier(value: &str, optional: bool) -> Result<(), Failure> {
    if optional && value.is_empty() {
        return Ok(());
    }
    uuid::Uuid::parse_str(value)
        .map(|_| ())
        .map_err(|_| invalid())
}
fn text(value: &str, limit: usize) -> Result<(), Failure> {
    if value.chars().count() > limit || value.contains('\0') {
        Err(invalid())
    } else {
        Ok(())
    }
}

#[derive(Debug, Deserialize, Serialize, Default)]
#[serde(deny_unknown_fields, default)]
pub struct Fields {
    reference: String,
    mpn: String,
    manufacturer: String,
    description: String,
    category: String,
    package_id: String,
    package_name: String,
    collections: Vec<String>,
}
impl Fields {
    fn validate(&self) -> Result<(), Failure> {
        for value in [
            &self.reference,
            &self.mpn,
            &self.manufacturer,
            &self.description,
            &self.category,
            &self.package_name,
        ] {
            text(value, 2048)?;
        }
        identifier(&self.package_id, true)?;
        if self.collections.len() > 32 {
            return Err(invalid());
        }
        for id in &self.collections {
            identifier(id, false)?;
        }
        Ok(())
    }
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Begin {
    #[serde(default)]
    part_id: String,
}
#[derive(Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Preparation {
    preparation: String,
}
#[derive(Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Inspect {
    preparation: String,
    fields: Fields,
}
#[derive(Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Search {
    preparation: String,
    role: String,
    #[serde(default)]
    query: String,
}
#[derive(Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Preview {
    preparation: String,
    token: String,
}
#[derive(Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Removal {
    preparation: String,
    handle: String,
}
#[derive(Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Operation {
    operation_id: String,
}
#[derive(Debug, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Action {
    Save,
    Variant,
    Membership,
}
fn save_action() -> Action {
    Action::Save
}
#[derive(Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Commit {
    preparation: String,
    operation_id: String,
    fields: Fields,
    selections: BTreeMap<String, String>,
    #[serde(default = "save_action")]
    action: Action,
    #[serde(default)]
    existing_id: String,
}
#[derive(Debug, Deserialize, Serialize)]
#[serde(tag = "method", content = "params", deny_unknown_fields)]
pub enum Request {
    #[serde(rename = "ingestion_begin")]
    Begin(Begin),
    #[serde(rename = "ingestion_inspect")]
    Inspect(Inspect),
    #[serde(rename = "ingestion_search")]
    Search(Search),
    #[serde(rename = "ingestion_preview")]
    Preview(Preview),
    #[serde(rename = "ingestion_commit")]
    Commit(Commit),
    #[serde(rename = "ingestion_result")]
    Result(Operation),
    #[serde(rename = "ingestion_remove")]
    Remove(Removal),
    #[serde(rename = "ingestion_cancel")]
    Cancel(Preparation),
}
fn role(value: &str) -> Result<(), Failure> {
    if ["SYMBOL", "FOOTPRINT", "MODEL_3D", "DATASHEET"].contains(&value) {
        Ok(())
    } else {
        Err(invalid())
    }
}
impl Request {
    pub fn validate(&self) -> Result<(), Failure> {
        match self {
            Self::Begin(v) => identifier(&v.part_id, true),
            Self::Result(v) => identifier(&v.operation_id, false),
            Self::Cancel(v) => previews::handle(&v.preparation),
            Self::Remove(v) => {
                previews::handle(&v.preparation)?;
                previews::handle(&v.handle)
            }
            Self::Inspect(v) => {
                previews::handle(&v.preparation)?;
                v.fields.validate()
            }
            Self::Search(v) => {
                previews::handle(&v.preparation)?;
                role(&v.role)?;
                text(&v.query, 255)
            }
            Self::Preview(v) => {
                previews::handle(&v.preparation)?;
                previews::handle(&v.token)
            }
            Self::Commit(v) => {
                previews::handle(&v.preparation)?;
                identifier(&v.operation_id, false)?;
                identifier(&v.existing_id, true)?;
                v.fields.validate()?;
                if v.selections.len() > 4 {
                    return Err(invalid());
                }
                for (key, token) in &v.selections {
                    role(key)?;
                    previews::handle(token)?;
                }
                Ok(())
            }
        }
    }
}

#[tauri::command]
pub async fn ingestion_command(engine: State<'_, Engine>, request: Request) -> Reply {
    request.validate()?;
    let value = serde_json::to_value(request).map_err(|_| invalid())?;
    engine
        .call(
            value["method"].as_str().ok_or_else(invalid)?,
            value["params"].clone(),
        )
        .await
}

/// Only construct from a native dialog result. Never serialized or sent to Python.
pub struct SelectedFile {
    pub filename: String,
    pub size: u64,
    file: File,
    before: Metadata,
    path: PathBuf,
}
impl SelectedFile {
    pub fn open(path: PathBuf) -> Result<Self, Failure> {
        let denied = || {
            Failure::new(
                "FILE_REFUSED",
                "Fichier absent, trop volumineux, lié ou inaccessible.",
            )
        };
        if !path.is_absolute() || path.canonicalize().map_err(|_| denied())? != path {
            return Err(denied());
        }
        let filename = path
            .file_name()
            .and_then(|v| v.to_str())
            .ok_or_else(denied)?
            .to_owned();
        if filename.len() > 255 || filename.chars().any(char::is_control) {
            return Err(denied());
        }
        let extension = path
            .extension()
            .and_then(|v| v.to_str())
            .unwrap_or("")
            .to_lowercase();
        if !["pdf", "kicad_sym", "kicad_mod", "step", "stp", "wrl"].contains(&extension.as_str()) {
            return Err(denied());
        }
        let mut options = OpenOptions::new();
        options.read(true);
        #[cfg(unix)]
        {
            use std::os::unix::fs::OpenOptionsExt;
            options.custom_flags(libc::O_NOFOLLOW | libc::O_NONBLOCK);
        }
        let file = options.open(&path).map_err(|_| denied())?;
        let before = file.metadata().map_err(|_| denied())?;
        if !before.is_file() || before.len() == 0 || before.len() > FILE_LIMIT {
            return Err(denied());
        }
        Ok(Self {
            filename,
            size: before.len(),
            file,
            before,
            path,
        })
    }
    fn stable(&self) -> Result<(), Failure> {
        let changed = || {
            Failure::new(
                "FILE_CHANGED",
                "Le fichier a changé pendant sa lecture ; le sélectionner à nouveau.",
            )
        };
        let now = self.file.metadata().map_err(|_| changed())?;
        if now.len() != self.before.len()
            || now.modified().ok() != self.before.modified().ok()
            || self.path.canonicalize().map_err(|_| changed())? != self.path
        {
            return Err(changed());
        }
        #[cfg(unix)]
        {
            use std::os::unix::fs::MetadataExt;
            let path = std::fs::symlink_metadata(&self.path).map_err(|_| changed())?;
            if path.ino() != self.before.ino()
                || path.dev() != self.before.dev()
                || now.ctime() != self.before.ctime()
                || now.ctime_nsec() != self.before.ctime_nsec()
            {
                return Err(changed());
            }
        }
        Ok(())
    }
    async fn transfer(&mut self, engine: &Engine, preparation: &str) -> Reply {
        let started = engine
            .call(
                "ingestion_file_start",
                json!({"preparation":preparation,"filename":self.filename,"size":self.size}),
            )
            .await?;
        let handle = started["handle"].as_str().ok_or_else(invalid)?.to_owned();
        previews::handle(&handle)?;
        let result = self.stream(engine, preparation, &handle).await;
        if result.is_err() {
            let _ = engine
                .call(
                    "ingestion_file_discard",
                    json!({"preparation":preparation,"handle":handle}),
                )
                .await;
        }
        result
    }
    async fn stream(&mut self, engine: &Engine, preparation: &str, handle: &str) -> Reply {
        let mut hash = Sha256::new();
        let mut offset = 0u64;
        let mut buffer = [0u8; 8192];
        loop {
            let count = self
                .file
                .read(&mut buffer)
                .map_err(|_| Failure::new("FILE_READ", "Lecture du fichier interrompue."))?;
            if count == 0 {
                break;
            }
            if offset + count as u64 > self.size {
                return Err(Failure::new(
                    "FILE_CHANGED",
                    "Le fichier a grandi pendant la lecture.",
                ));
            }
            hash.update(&buffer[..count]);
            engine.call("ingestion_file_chunk", json!({"preparation":preparation,"handle":handle,"offset":offset,"data":STANDARD.encode(&buffer[..count])})).await?;
            offset += count as u64;
        }
        self.stable()?;
        if offset != self.size {
            return Err(Failure::new(
                "FILE_CHANGED",
                "Fichier tronqué pendant la lecture.",
            ));
        }
        engine.call("ingestion_file_finish", json!({"preparation":preparation,"handle":handle,"sha256":format!("{:x}", hash.finalize())})).await
    }
}

#[tauri::command]
pub async fn choose_ingestion_files(
    app: tauri::AppHandle,
    engine: State<'_, Engine>,
    preparation: String,
) -> Reply {
    previews::handle(&preparation)?;
    engine.authorize_preparation(&preparation).await?;
    let _picking = engine
        .picking
        .try_lock()
        .map_err(|_| Failure::new("BUSY", "Un sélecteur de fichiers est déjà ouvert."))?;
    let (send, receive) = tokio::sync::oneshot::channel();
    app.dialog()
        .file()
        .set_title("FabParts — Fichiers du composant")
        .add_filter(
            "KiCad / 3D / PDF",
            &["kicad_sym", "kicad_mod", "step", "stp", "wrl", "pdf"],
        )
        .pick_files(move |files| {
            let _ = send.send(files);
        });
    let files = crate::ipc::unless_closing(engine.closing.subscribe(), async {
        receive
            .await
            .map_err(|_| Failure::new("FILE_PICKER", "Sélecteur indisponible."))
    })
    .await?;
    let Some(paths) = files else {
        return Ok(json!({"cancelled":true,"files":[],"errors":[]}));
    };
    engine.authorize_preparation(&preparation).await?;
    if paths.len() > 8 {
        return Err(Failure::new(
            "FILE_LIMIT",
            "Sélection limitée à 8 fichiers.",
        ));
    }
    let mut files = Vec::new();
    let mut errors = Vec::new();
    let mut total = 0;
    for chosen in paths {
        let result = match chosen.into_path() {
            Ok(path) => match SelectedFile::open(path) {
                Ok(mut file) => {
                    total += file.size;
                    if total > 64 * 1024 * 1024 {
                        Err(Failure::new("FILE_LIMIT", "Sélection limitée à 64 Mio."))
                    } else {
                        file.transfer(&engine, &preparation).await
                    }
                }
                Err(error) => Err(error),
            },
            Err(_) => Err(Failure::new(
                "FILE_REFUSED",
                "Seuls les fichiers locaux sont acceptés.",
            )),
        };
        match result {
            Ok(file) => files.push(file),
            Err(error) => errors.push(error),
        }
    }
    Ok(json!({"cancelled":false,"files":files,"errors":errors}))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn only_host_mode_enables_writes_and_restart_revokes_preparation() {
        let params = json!({"preparation":"a".repeat(48)});
        assert!(authorize(false, None, "ingestion_begin", &json!({})).is_err());
        assert!(authorize(true, None, "ingestion_begin", &json!({})).is_ok());
        assert!(authorize(true, None, "ingestion_result", &json!({})).is_ok());
        assert!(authorize(true, None, "ingestion_commit", &params).is_err());
        assert!(authorize(true, Some(&"b".repeat(48)), "ingestion_file_start", &params).is_err());
        assert!(authorize(true, Some(&"a".repeat(48)), "ingestion_commit", &params).is_ok());
        assert!(authorize(false, Some(&"a".repeat(48)), "ingestion_commit", &params).is_err());
    }
    #[test]
    fn typed_request_rejects_paths_internal_commands_and_unknown_fields() {
        for raw in [
            json!({"method":"ingestion_file_start","params":{}}),
            json!({"method":"ingestion_begin","params":{"path":"/anywhere"}}),
            json!({"method":"ingestion_begin","params":{"part_id":1}}),
            json!({"method":"ingestion_commit","params":{"fields":{"sql":"DROP"}}}),
        ] {
            assert!(serde_json::from_value::<Request>(raw).is_err());
        }
        let value: Request =
            serde_json::from_value(json!({"method":"ingestion_begin","params":{}})).unwrap();
        assert!(value.validate().is_ok());
    }
    #[test]
    fn field_and_capability_bounds_are_checked() {
        for params in [
            json!({"preparation":"a".repeat(48),"role":"SQL","query":""}),
            json!({"preparation":"../path","role":"SYMBOL","query":""}),
            json!({"preparation":"a".repeat(48),"role":"SYMBOL","query":"a".repeat(256)}),
        ] {
            let request: Request =
                serde_json::from_value(json!({"method":"ingestion_search","params":params}))
                    .unwrap();
            assert!(request.validate().is_err());
        }
    }
    #[test]
    fn native_capability_checks_source_stability_and_symlinks() {
        let dir = std::env::temp_dir()
            .canonicalize()
            .unwrap()
            .join(format!("fabparts-file-test-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let source = dir.join("source.pdf");
        std::fs::write(&source, b"%PDF-test").unwrap();
        let selected = SelectedFile::open(source.clone()).unwrap();
        selected.stable().unwrap();
        std::fs::write(&source, b"changed").unwrap();
        assert!(selected.stable().is_err());
        #[cfg(unix)]
        {
            let link = dir.join("link.pdf");
            std::os::unix::fs::symlink(&source, &link).unwrap();
            assert!(SelectedFile::open(link).is_err());
        }
        assert!(SelectedFile::open(dir.join("missing.pdf")).is_err());
        let huge = dir.join("huge.step");
        File::create(&huge)
            .unwrap()
            .set_len(FILE_LIMIT + 1)
            .unwrap();
        assert!(SelectedFile::open(huge).is_err());
        std::fs::remove_dir_all(dir).unwrap();
    }
}
