//! Typed M11 commands; credentials are host-only and never part of a DTO.
use crate::{
    ipc::{Failure, Reply},
    previews, Engine,
};
use serde::{Deserialize, Serialize};
use tauri::State;

#[derive(Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Configuration {
    enabled: bool,
    backend: String,
    endpoint: String,
    model: String,
}
#[derive(Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Identity {
    id: String,
}
#[derive(Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Preparation {
    id: String,
    text: String,
    include: bool,
}
#[derive(Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Session {
    id: String,
    handle: String,
}
#[derive(Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Start {
    id: String,
    handle: String,
    consent: bool,
}
#[derive(Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Acceptance {
    id: String,
    handle: String,
    fields: Vec<String>,
    replace_existing: bool,
}
#[derive(Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Empty {}
#[derive(Debug, Deserialize, Serialize)]
#[serde(tag = "method", content = "params", deny_unknown_fields)]
pub enum Request {
    #[serde(rename = "assistance_configuration")]
    Configuration(Empty),
    #[serde(rename = "assistance_configure")]
    Configure(Configuration),
    #[serde(rename = "assistance_identification")]
    Identification(Identity),
    #[serde(rename = "assistance_prepare")]
    Prepare(Preparation),
    #[serde(rename = "assistance_start")]
    Start(Start),
    #[serde(rename = "assistance_status")]
    Status(Session),
    #[serde(rename = "assistance_accept")]
    Accept(Acceptance),
    #[serde(rename = "assistance_cancel")]
    Cancel(Session),
}
fn invalid() -> Failure {
    Failure::new("INVALID_PARAMS", "Invalid assistance request")
}
fn text(value: &str, limit: usize) -> Result<(), Failure> {
    if value.chars().count() > limit || value.contains('\0') {
        Err(invalid())
    } else {
        Ok(())
    }
}
fn id(value: &str) -> Result<(), Failure> {
    uuid::Uuid::parse_str(value)
        .map(|_| ())
        .map_err(|_| invalid())
}
impl Request {
    fn validate(&self) -> Result<(), Failure> {
        match self {
            Self::Configuration(_) => Ok(()),
            Self::Configure(v) => {
                if !["gemini", "chat", "ollama"].contains(&v.backend.as_str()) {
                    return Err(invalid());
                }
                text(&v.endpoint, 512)?;
                text(&v.model, 128)
            }
            Self::Identification(v) => id(&v.id),
            Self::Prepare(v) => {
                id(&v.id)?;
                text(&v.text, 16000)
            }
            Self::Start(v) => {
                id(&v.id)?;
                previews::handle(&v.handle)
            }
            Self::Status(v) | Self::Cancel(v) => {
                id(&v.id)?;
                previews::handle(&v.handle)
            }
            Self::Accept(v) => {
                id(&v.id)?;
                previews::handle(&v.handle)?;
                if v.fields.is_empty()
                    || v.fields.len() > 4
                    || v.fields.iter().any(|f| {
                        !["manufacturer", "mpn", "category", "notes"].contains(&f.as_str())
                    })
                {
                    return Err(invalid());
                }
                Ok(())
            }
        }
    }
}
pub fn authorize(writable: bool, preparation: bool) -> Result<(), Failure> {
    if !writable {
        return Err(Failure::new("READ_ONLY", "Assistance unavailable"));
    }
    if preparation {
        return Err(Failure::new("BUSY", "Finish the active preparation first"));
    }
    Ok(())
}
/// Read only these two variables after env_clear. Never enumerate the environment.
pub fn credentials(read: impl Fn(&str) -> Option<String>) -> Vec<(&'static str, String)> {
    ["GEMINI_API_KEY", "KIPART_AI_API_KEY"]
        .into_iter()
        .filter_map(|key| {
            read(key)
                .filter(|value| {
                    !value.trim().is_empty()
                        && value.len() <= 8192
                        && !value.chars().any(char::is_control)
                })
                .map(|value| (key, value))
        })
        .collect()
}
#[tauri::command]
pub async fn assistance_command(engine: State<'_, Engine>, request: Request) -> Reply {
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
    fn credentials_are_an_explicit_allowlist() {
        let values = credentials(|name| match name {
            "GEMINI_API_KEY" => Some("fixture-google".into()),
            "KIPART_AI_API_KEY" => Some("fixture-chat".into()),
            _ => panic!("Unexpected environment read"),
        });
        assert_eq!(values.len(), 2);
        assert!(credentials(|_| Some("bad\nvalue".into())).is_empty());
        assert!(credentials(|_| Some("x".repeat(8193))).is_empty());
    }
    #[test]
    fn typed_bounds_readonly_and_no_client_proposal() {
        assert!(authorize(false, false).is_err());
        assert!(authorize(true, true).is_err());
        assert!(authorize(true, false).is_ok());
        assert!(serde_json::from_value::<Request>(json!({"method":"assistance_accept","params":{"id":"x","handle":"a".repeat(48),"fields":["mpn"],"replace_existing":false,"proposal":{"mpn":"injected"}}})).is_err());
        for text in ["🙂".repeat(16000), "é".repeat(16000)] {
            let request:Request=serde_json::from_value(json!({"method":"assistance_prepare","params":{"id":uuid::Uuid::nil().to_string(),"text":text,"include":false}})).unwrap();
            assert!(request.validate().is_ok());
        }
        let request:Request=serde_json::from_value(json!({"method":"assistance_prepare","params":{"id":uuid::Uuid::nil().to_string(),"text":"x".repeat(16001),"include":false}})).unwrap();
        assert!(request.validate().is_err());
    }
}

#[cfg(test)]
mod frame_tests {
    #[test]
    fn only_context_preparation_has_the_unicode_frame_budget() {
        assert_eq!(crate::ipc::request_limit("assistance_prepare"), 256 * 1024);
        assert_eq!(crate::ipc::request_limit("assistance_accept"), 16 * 1024);
        assert_eq!(crate::ipc::request_limit("health"), 16 * 1024);
        assert_eq!(crate::ipc::TIMEOUT.as_secs(), 8);
    }
}
