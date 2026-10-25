//! Capabilities for previews contain business identifiers or opaque handles, never paths.
use crate::ipc::Failure;
use serde::{Deserialize, Serialize};

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct PreviewQuery {
    pub id: String,
    pub role: String,
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub asset_id: String,
}
fn uuid(value: &str) -> bool {
    value.len() == 36
        && value.bytes().enumerate().all(|(i, b)| {
            if [8, 13, 18, 23].contains(&i) {
                b == b'-'
            } else {
                b.is_ascii_hexdigit()
            }
        })
}
impl PreviewQuery {
    pub fn validate(&self) -> Result<(), Failure> {
        if !uuid(&self.id)
            || (!self.asset_id.is_empty() && !uuid(&self.asset_id))
            || !["SYMBOL", "FOOTPRINT", "DATASHEET", "MODEL_3D"].contains(&self.role.as_str())
        {
            return Err(Failure::new(
                "INVALID_PARAMS",
                "Identifiants ou rôle de ressource invalides.",
            ));
        }
        Ok(())
    }
}
pub fn handle(value: &str) -> Result<(), Failure> {
    if value.len() != 48
        || !value
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
    {
        return Err(Failure::new("INVALID_PARAMS", "Handle PDF invalide."));
    }
    Ok(())
}
pub fn offset(value: u32) -> Result<(), Failure> {
    if value >= 16 * 1024 * 1024 || value % 65536 != 0 {
        return Err(Failure::new("INVALID_PARAMS", "Position PDF hors limites."));
    }
    Ok(())
}
#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    #[test]
    fn business_ids_only() {
        let valid = json!({"id":"12345678-1234-1234-1234-123456789abc","role":"SYMBOL"});
        let query: PreviewQuery = serde_json::from_value(valid.clone()).unwrap();
        assert!(query.validate().is_ok());
        for patch in [
            json!({"id":"/private/test"}),
            json!({"role":"PATH"}),
            json!({"asset_id":"../a"}),
        ] {
            let mut v = valid.clone();
            v.as_object_mut()
                .unwrap()
                .extend(patch.as_object().unwrap().clone());
            assert!(serde_json::from_value::<PreviewQuery>(v)
                .unwrap()
                .validate()
                .is_err());
        }
        let mut v = valid;
        v["path"] = json!("/private/test");
        assert!(serde_json::from_value::<PreviewQuery>(v).is_err());
    }
    #[test]
    fn bounded_handles_and_chunks() {
        assert!(handle(&"a".repeat(48)).is_ok());
        for v in ["../a", "/tmp/doc.pdf", "", &"a".repeat(49)] {
            assert!(handle(v).is_err());
        }
        assert!(offset(0).is_ok());
        assert!(offset(65536).is_ok());
        assert!(offset(1).is_err());
        assert!(offset(16 * 1024 * 1024).is_err());
    }
}
