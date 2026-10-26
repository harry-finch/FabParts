//! Host-owned KiCad targets and bounded commands. No path or shell authority in WebView.
use crate::{
    ipc::{Failure, Reply},
    Engine,
};
use serde::{Deserialize, Serialize};
use serde_json::json;
use std::path::PathBuf;
use tauri::State;

#[derive(Default)]
pub struct Configuration {
    pub root: Option<PathBuf>,
    pub versions: Vec<String>,
}
impl Configuration {
    pub fn discover() -> Self {
        #[cfg(not(target_os = "macos"))]
        {
            return Self::default();
        }
        #[cfg(target_os = "macos")]
        {
            let Some(home) = std::env::var_os("HOME") else {
                return Self::default();
            };
            let root = std::env::var_os("FABPARTS_KICAD_CONFIG_ROOT")
                .or_else(|| std::env::var_os("KICAD_CONFIG_HOME"))
                .map(PathBuf::from)
                .unwrap_or_else(|| PathBuf::from(home).join("Library/Preferences/kicad"));
            let mut candidates = Vec::new();
            for parent in [
                PathBuf::from("/Applications"),
                PathBuf::from("/Applications/KiCad"),
                PathBuf::from(std::env::var_os("HOME").unwrap_or_default()).join("Applications"),
                PathBuf::from(std::env::var_os("HOME").unwrap_or_default())
                    .join("Applications/KiCad"),
            ] {
                if let Ok(entries) = std::fs::read_dir(parent) {
                    for entry in entries.flatten() {
                        let path = entry.path();
                        if path
                            .file_name()
                            .is_some_and(|n| n.to_string_lossy().starts_with("KiCad"))
                            && path.extension().is_some_and(|e| e == "app")
                        {
                            candidates.push(path.join("Contents/MacOS/kicad-cli"));
                        }
                    }
                }
            }
            let probe = std::env::temp_dir().join(format!(
                "fabparts-kicad-probe-{}-{}",
                std::process::id(),
                std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)
                    .unwrap_or_default()
                    .as_nanos()
            ));
            if std::fs::create_dir(&probe).is_err() {
                return Self::default();
            }
            let mut versions = Vec::new();
            for binary in candidates {
                if let Some(version) = probe_version(&binary, &probe) {
                    if supported(&version) && !versions.contains(&version) {
                        versions.push(version);
                    }
                }
            }
            let _ = std::fs::remove_dir_all(&probe);
            versions.sort_by_key(|v| {
                v.split('.')
                    .next()
                    .unwrap_or("0")
                    .parse::<u32>()
                    .unwrap_or(0)
            });
            Self {
                root: Some(root),
                versions,
            }
        }
    }
}
fn probe_version(binary: &std::path::Path, probe: &std::path::Path) -> Option<String> {
    let output = std::process::Command::new(binary)
        .arg("version")
        .env("KICAD_CONFIG_HOME", probe)
        .env("KICAD_DOCUMENTS_HOME", probe.join("documents"))
        .output()
        .ok()?;
    if !output.status.success() {
        return None;
    }
    let text = String::from_utf8_lossy(&output.stdout);
    let parts: Vec<_> = text.trim().split('.').collect();
    (parts.len() >= 2).then(|| format!("{}.{}", parts[0], parts[1]))
}
fn supported(value: &str) -> bool {
    ["6.0", "7.0", "8.0", "9.0", "10.0"].contains(&value)
}
fn writes(method: &str) -> bool {
    !["integration_get", "integration_verify"].contains(&method)
}
pub fn authorize(writable: bool, preparing: bool, open: bool, method: &str) -> Result<(), Failure> {
    if writes(method) && !writable {
        return Err(Failure::new("READ_ONLY", "Integration writes unavailable"));
    }
    if preparing {
        return Err(Failure::new("BUSY", "Finish the current preparation first"));
    }
    if writes(method) && open {
        return Err(Failure::new(
            "KICAD_OPEN",
            "Close KiCad editors and manager before changing global tables",
        ));
    }
    Ok(())
}
pub fn running() -> Result<bool, Failure> {
    let output = std::process::Command::new("/bin/ps")
        .args(["-axo", "comm="])
        .output()
        .map_err(|_| {
            Failure::new(
                "KICAD_STATUS_UNAVAILABLE",
                "Cannot determine whether KiCad is open",
            )
        })?;
    if !output.status.success() {
        return Err(Failure::new(
            "KICAD_STATUS_UNAVAILABLE",
            "Cannot determine whether KiCad is open",
        ));
    }
    Ok(String::from_utf8_lossy(&output.stdout).lines().any(|line| {
        ["kicad", "eeschema", "pcbnew"]
            .iter()
            .any(|name| line.trim() == *name || line.trim().ends_with(&format!("/{}", name)))
    }))
}
#[derive(Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Request {
    action: String,
    id: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    target: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    version: Option<u32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    handle: Option<String>,
}
impl Request {
    fn validate(&self) -> Result<(), Failure> {
        if ![
            "get", "prepare", "activate", "verify", "recovery", "recover",
        ]
        .contains(&self.action.as_str())
            || self.id.len() > 36
            || uuid::Uuid::parse_str(&self.id).is_err()
            || (self.action != "get" && self.target.is_none())
            || self.target.as_ref().is_some_and(|t| !supported(t))
            || (self.action == "prepare") != self.version.is_some()
            || self.version.is_some_and(|v| !(1..=999999).contains(&v))
            || ["activate", "recover"].contains(&self.action.as_str()) != self.handle.is_some()
        {
            return Err(Failure::new(
                "INVALID_PARAMS",
                "Invalid integration request",
            ));
        }
        if let Some(handle) = &self.handle {
            crate::previews::handle(handle)?;
        }
        Ok(())
    }
}
#[tauri::command]
pub async fn integration_command(engine: State<'_, Engine>, request: Request) -> Reply {
    request.validate()?;
    let method = format!("integration_{}", request.action);
    let mut params = json!(request);
    params.as_object_mut().unwrap().remove("action");
    let mut result = engine.call(&method, params).await?;
    result["kicad_open"] = json!(running().unwrap_or(true));
    Ok(result)
}
#[cfg(test)]
mod tests {
    use super::*;
    #[cfg(unix)]
    #[test]
    fn version_probe_uses_private_configuration() {
        use std::os::unix::fs::PermissionsExt;
        let root = std::env::temp_dir().join(format!(
            "fabparts-probe-test-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        std::fs::create_dir(&root).unwrap();
        let binary = root.join("cli");
        std::fs::write(&binary,b"#!/bin/sh\nprintf '10.0.7\\n'\nprintf '%s' \"$KICAD_DOCUMENTS_HOME\" > \"$KICAD_CONFIG_HOME/probe\"\n").unwrap();
        std::fs::set_permissions(&binary, std::fs::Permissions::from_mode(0o700)).unwrap();
        assert_eq!(probe_version(&binary, &root), Some("10.0".into()));
        assert_eq!(
            std::fs::read_to_string(root.join("probe")).unwrap(),
            root.join("documents").to_string_lossy()
        );
        std::fs::remove_dir_all(root).unwrap();
    }
    #[test]
    fn bounded_requests_and_host_guards() {
        let valid = json!({"action":"prepare","id":uuid::Uuid::nil(),"target":"10.0","version":1});
        assert!(serde_json::from_value::<Request>(valid.clone())
            .unwrap()
            .validate()
            .is_ok());
        for field in ["path", "manifest", "shell"] {
            let mut bad = valid.clone();
            bad[field] = json!("arbitrary");
            assert!(serde_json::from_value::<Request>(bad).is_err());
        }
        for bad in [
            json!({"action":"activate","id":uuid::Uuid::nil(),"target":"10.0"}),
            json!({"action":"get","id":"/tmp"}),
            json!({"action":"prepare","id":uuid::Uuid::nil(),"target":"11.0","version":1}),
        ] {
            assert!(serde_json::from_value::<Request>(bad)
                .unwrap()
                .validate()
                .is_err());
        }
        assert_eq!(
            authorize(false, false, false, "integration_activate")
                .unwrap_err()
                .code,
            "READ_ONLY"
        );
        assert_eq!(
            authorize(true, true, false, "integration_prepare")
                .unwrap_err()
                .code,
            "BUSY"
        );
        assert_eq!(
            authorize(true, false, true, "integration_activate")
                .unwrap_err()
                .code,
            "KICAD_OPEN"
        );
        assert!(authorize(false, false, true, "integration_verify").is_ok());
    }
}
