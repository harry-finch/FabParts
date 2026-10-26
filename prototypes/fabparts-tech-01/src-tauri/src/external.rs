//! Bounded optional-source requests. Network work happens outside the IPC loop.
use crate::{
    ipc::{Failure, Reply},
    previews, Engine,
};
use serde::{Deserialize, Serialize};
use tauri::State;

#[derive(Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Config {
    source: String,
    enabled: bool,
    revision: String,
    domains: Vec<String>,
}
#[derive(Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Search {
    preparation: String,
    role: String,
    library: String,
    query: String,
}
#[derive(Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Download {
    preparation: String,
    token: String,
}
#[derive(Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Pdf {
    preparation: String,
    url: String,
    consent: bool,
}
#[derive(Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Job {
    preparation: String,
    handle: String,
}
#[derive(Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Empty {}
#[derive(Debug, Deserialize, Serialize)]
#[serde(tag = "method", content = "params", deny_unknown_fields)]
pub enum Request {
    #[serde(rename = "external_configuration")]
    Configuration(Empty),
    #[serde(rename = "external_configure")]
    Configure(Config),
    #[serde(rename = "external_search")]
    Search(Search),
    #[serde(rename = "external_download")]
    Download(Download),
    #[serde(rename = "external_pdf")]
    Pdf(Pdf),
    #[serde(rename = "external_status")]
    Status(Job),
    #[serde(rename = "external_cancel")]
    Cancel(Job),
}
fn invalid() -> Failure {
    Failure::new("INVALID_PARAMS", "Invalid external source request")
}
fn text(value: &str, limit: usize) -> Result<(), Failure> {
    if value.chars().count() > limit || value.chars().any(char::is_control) {
        Err(invalid())
    } else {
        Ok(())
    }
}
impl Request {
    fn validate(&self) -> Result<(), Failure> {
        match self {
            Self::Configuration(_) => Ok(()),
            Self::Configure(v) => {
                if !["kicad", "pdf"].contains(&v.source.as_str()) || v.domains.len() > 32 {
                    return Err(invalid());
                }
                text(&v.revision, 80)?;
                for domain in &v.domains {
                    text(domain, 253)?;
                }
                Ok(())
            }
            Self::Search(v) => {
                previews::handle(&v.preparation)?;
                if !["SYMBOL", "FOOTPRINT", "MODEL_3D"].contains(&v.role.as_str()) {
                    return Err(invalid());
                }
                text(&v.library, 255)?;
                text(&v.query, 255)
            }
            Self::Download(v) => {
                previews::handle(&v.preparation)?;
                previews::handle(&v.token)
            }
            Self::Pdf(v) => {
                previews::handle(&v.preparation)?;
                text(&v.url, 2048)
            }
            Self::Status(v) | Self::Cancel(v) => {
                previews::handle(&v.preparation)?;
                previews::handle(&v.handle)
            }
        }
    }
}
pub fn authorize(
    writable: bool,
    current: Option<&str>,
    method: &str,
    params: &serde_json::Value,
) -> Result<(), Failure> {
    if !writable {
        return Err(Failure::new("READ_ONLY", "External sources unavailable"));
    }
    if !["external_configuration", "external_configure"].contains(&method)
        && (current.is_none() || current != params["preparation"].as_str())
    {
        return Err(invalid());
    }
    Ok(())
}
#[tauri::command]
pub async fn external_command(engine: State<'_, Engine>, request: Request) -> Reply {
    request.validate()?;
    let value = serde_json::to_value(request).map_err(|_| invalid())?;
    engine
        .call(
            value["method"].as_str().ok_or_else(invalid)?,
            value["params"].clone(),
        )
        .await
}
#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    #[test]
    fn readonly_preparation_and_strict_candidate_capabilities() {
        let params = json!({"preparation":"a".repeat(48),"token":"b".repeat(48)});
        assert!(authorize(false, None, "external_configuration", &json!({})).is_err());
        assert!(authorize(true, None, "external_download", &params).is_err());
        assert!(authorize(true, Some(&"c".repeat(48)), "external_download", &params).is_err());
        assert!(authorize(true, Some(&"a".repeat(48)), "external_download", &params).is_ok());
        assert!(serde_json::from_value::<Request>(json!({"method":"external_download","params":{"preparation":"a".repeat(48),"candidate":{},"url":"https://evil"}})).is_err());
        let req:Request=serde_json::from_value(json!({"method":"external_pdf","params":{"preparation":"a".repeat(48),"url":"x".repeat(2049),"consent":true}})).unwrap();
        assert!(req.validate().is_err());
        assert!(serde_json::from_value::<Request>(json!({"method":"external_configure","params":{"source":"pdf","enabled":"true","revision":"9.0.0","domains":[]}})).is_err());
    }
}
