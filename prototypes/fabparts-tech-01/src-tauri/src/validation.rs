//! Fixed validation commands: UUID subjects and session-bound viewed-report capabilities.
use crate::{
    ipc::{Failure, Reply},
    Engine,
};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use tauri::State;

#[derive(Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Subject {
    kind: String,
    id: String,
}
impl Subject {
    fn validate(&self) -> Result<(), Failure> {
        if !["Part", "Collection"].contains(&self.kind.as_str())
            || self.id.len() > 36
            || uuid::Uuid::parse_str(&self.id).is_err()
        {
            return Err(Failure::new("INVALID_PARAMS", "Invalid validation subject"));
        }
        Ok(())
    }
}
#[derive(Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Query {
    kind: String,
    id: String,
    #[serde(default)]
    offset: u32,
    #[serde(default)]
    member_offset: u32,
}
impl Query {
    fn validate(&self) -> Result<(), Failure> {
        Subject {
            kind: self.kind.clone(),
            id: self.id.clone(),
        }
        .validate()?;
        if self.offset > 1_000_000 || self.member_offset > 1_000_000 {
            return Err(Failure::new("INVALID_PARAMS", "Invalid page offset"));
        }
        Ok(())
    }
}
// Used at the host boundary as well as Python: writes are never sent to readonly.
pub fn authorize(writable: bool, preparing: bool, method: &str) -> Result<(), Failure> {
    if method != "validation_get" && !writable {
        return Err(Failure::new("READ_ONLY", "Validation writes unavailable"));
    }
    if preparing {
        return Err(Failure::new("BUSY", "Finish the current preparation first"));
    }
    Ok(())
}
#[tauri::command]
pub async fn get_validation(engine: State<'_, Engine>, query: Query) -> Reply {
    query.validate()?;
    engine.call("validation_get", json!(query)).await
}
#[tauri::command]
pub async fn run_validation(engine: State<'_, Engine>, subject: Subject) -> Reply {
    subject.validate()?;
    engine.call("validation_run", json!(subject)).await
}
#[tauri::command]
pub async fn accept_validation_warnings(
    engine: State<'_, Engine>,
    subject: Subject,
    handle: String,
) -> Reply {
    subject.validate()?;
    crate::previews::handle(&handle)?;
    let mut params: Value = json!(subject);
    params["handle"] = json!(handle);
    engine.call("validation_accept", params).await
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn subjects_and_offsets_are_bounded() {
        let valid = Subject {
            kind: "Part".into(),
            id: uuid::Uuid::nil().to_string(),
        };
        assert!(valid.validate().is_ok());
        assert!(Subject {
            kind: "Asset".into(),
            id: valid.id.clone()
        }
        .validate()
        .is_err());
        assert!(Subject {
            kind: "Part".into(),
            id: "path/to/data".into()
        }
        .validate()
        .is_err());
        assert!(Query {
            kind: valid.kind,
            id: valid.id,
            offset: 1_000_001,
            member_offset: 0
        }
        .validate()
        .is_err());
        assert!(serde_json::from_value::<Query>(
            json!({"kind":"Part","id":uuid::Uuid::nil(),"offset":0,"member_offset":0})
        )
        .unwrap()
        .validate()
        .is_ok());
        assert!(serde_json::from_value::<Subject>(
            json!({"kind":"Part","id":uuid::Uuid::nil(),"report":{}})
        )
        .is_err());
    }
    #[test]
    fn read_only_and_preparation_guards() {
        assert!(authorize(false, false, "validation_get").is_ok());
        assert_eq!(
            authorize(false, false, "validation_run").unwrap_err().code,
            "READ_ONLY"
        );
        assert_eq!(
            authorize(false, false, "validation_accept")
                .unwrap_err()
                .code,
            "READ_ONLY"
        );
        assert_eq!(
            authorize(true, true, "validation_run").unwrap_err().code,
            "BUSY"
        );
        assert!(authorize(true, false, "validation_run").is_ok());
    }
}
