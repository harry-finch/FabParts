use serde::Serialize;
use serde_json::Value;
use std::time::Duration;
use tauri::async_runtime::Receiver;
use tauri_plugin_shell::process::CommandEvent;
use tokio::sync::watch;

pub fn request_limit(method: &str) -> usize {
    if method == "assistance_prepare" {
        256 * 1024
    } else {
        16 * 1024
    }
}

pub const MAX_FRAME: usize = 2 * 1024 * 1024;
pub const TIMEOUT: Duration = Duration::from_secs(8);
pub const STARTUP_TIMEOUT: Duration = Duration::from_secs(30);

pub async fn unless_closing<T>(
    mut closing: watch::Receiver<bool>,
    future: impl std::future::Future<Output = Result<T, Failure>>,
) -> Result<T, Failure> {
    if *closing.borrow() {
        return Err(Failure::new(
            "APP_CLOSING",
            "Application en cours de fermeture.",
        ));
    }
    tokio::select! {
        biased;
        _ = closing.changed() => Err(Failure::new("APP_CLOSING", "Application en cours de fermeture.")),
        result = future => result,
    }
}

#[derive(Debug, Clone, Serialize)]
pub struct Failure {
    pub code: String,
    pub message: String,
}
impl Failure {
    pub fn new(code: &str, message: &str) -> Self {
        Self {
            code: code.into(),
            message: message.into(),
        }
    }
}
pub type Reply = Result<Value, Failure>;

pub fn decode(bytes: &[u8], identity: &str) -> Reply {
    if bytes.len() > MAX_FRAME {
        return Err(Failure::new("FRAME_TOO_LARGE", "Réponse trop volumineuse."));
    }
    let message: Value = serde_json::from_slice(bytes)
        .map_err(|_| Failure::new("INVALID_RESPONSE", "Réponse moteur illisible."))?;
    if message["protocol_version"].as_u64() != Some(1) {
        return Err(Failure::new(
            "VERSION_MISMATCH",
            "Version du moteur incompatible.",
        ));
    }
    if message["request_id"].as_str() != Some(identity) {
        return Err(Failure::new(
            "CORRELATION_ERROR",
            "Réponse moteur non corrélée.",
        ));
    }
    match message["ok"].as_bool() {
        Some(true) if message.get("result").is_some() => Ok(message["result"].clone()),
        Some(false) => {
            let code = message["error"]["code"]
                .as_str()
                .ok_or_else(|| Failure::new("INVALID_RESPONSE", "Erreur moteur invalide."))?;
            let detail = message["error"]["message"]
                .as_str()
                .ok_or_else(|| Failure::new("INVALID_RESPONSE", "Erreur moteur invalide."))?;
            Err(Failure::new(code, detail))
        }
        _ => Err(Failure::new(
            "INVALID_RESPONSE",
            "Enveloppe moteur invalide.",
        )),
    }
}

pub async fn receive(rx: &mut Receiver<CommandEvent>, identity: &str, timeout: Duration) -> Reply {
    let response = async {
        let mut buffer = Vec::new();
        loop {
            match rx.recv().await {
                Some(CommandEvent::Stdout(bytes)) => {
                    if buffer.len() + bytes.len() > MAX_FRAME {
                        return Err(Failure::new("FRAME_TOO_LARGE", "Réponse trop volumineuse."));
                    }
                    buffer.extend(bytes);
                    if let Some(end) = buffer.iter().position(|b| *b == b'\n') {
                        if end + 1 != buffer.len() {
                            return Err(Failure::new(
                                "INVALID_RESPONSE",
                                "Plusieurs réponses inattendues.",
                            ));
                        }
                        return decode(&buffer[..end], identity);
                    }
                }
                Some(CommandEvent::Stderr(bytes)) => crate::diagnostics::event(
                    "sidecar_stderr",
                    serde_json::json!({"bytes": bytes.len()}),
                ),
                Some(CommandEvent::Terminated(status)) => {
                    crate::diagnostics::event(
                        "sidecar_exited",
                        serde_json::json!({"exit_code":status.code,"signal":status.signal}),
                    );
                    return Err(Failure::new(
                        "ENGINE_EXITED",
                        "Le moteur s’est arrêté. Redémarrez-le.",
                    ));
                }
                None => {
                    return Err(Failure::new(
                        "ENGINE_EXITED",
                        "Le canal du moteur est fermé.",
                    ))
                }
                Some(CommandEvent::Error(_)) => {
                    return Err(Failure::new(
                        "ENGINE_IO",
                        "Communication avec le moteur interrompue.",
                    ))
                }
                _ => (),
            }
        }
    };
    tokio::time::timeout(timeout, response)
        .await
        .map_err(|_| Failure::new("TIMEOUT", "Le moteur ne répond pas. Redémarrez-le."))?
}

#[cfg(test)]
mod tests {
    use super::*;
    use tauri::async_runtime::channel;
    fn frame() -> Vec<u8> {
        br#"{"protocol_version":1,"request_id":"r1","ok":true,"result":{"total":12}}"#.to_vec()
    }
    #[test]
    fn closing_cancels_pending_reply_and_late_reply() {
        tauri::async_runtime::block_on(async {
            let (closing, receiver) = watch::channel(false);
            let (tx, mut rx) = channel(8);
            let pending = unless_closing(receiver, receive(&mut rx, "r1", STARTUP_TIMEOUT));
            let shutdown = async {
                tokio::task::yield_now().await;
                closing.send_replace(true);
                let mut bytes = frame();
                bytes.push(b'\n');
                let _ = tx.send(CommandEvent::Stdout(bytes)).await;
            };
            let (result, _) = tokio::join!(pending, shutdown);
            assert_eq!(result.unwrap_err().code, "APP_CLOSING");
        });
    }
    #[test]
    fn closed_application_does_not_start_work() {
        tauri::async_runtime::block_on(async {
            let (closing, receiver) = watch::channel(false);
            closing.send_replace(true);
            let polled = std::cell::Cell::new(false);
            let result = unless_closing(receiver, async {
                polled.set(true);
                Ok(())
            })
            .await;
            assert_eq!(result.unwrap_err().code, "APP_CLOSING");
            assert!(!polled.get());
        });
    }
    #[test]
    fn closing_guard_preserves_normal_reply() {
        tauri::async_runtime::block_on(async {
            let (_closing, receiver) = watch::channel(false);
            assert_eq!(
                unless_closing(receiver, async { Ok(42) }).await.unwrap(),
                42
            );
        });
    }
    #[test]
    fn correlation() {
        assert_eq!(decode(&frame(), "r1").unwrap()["total"], 12);
        assert_eq!(
            decode(&frame(), "r2").unwrap_err().code,
            "CORRELATION_ERROR"
        );
    }
    #[test]
    fn malformed() {
        assert_eq!(
            decode(b"{broken", "r1").unwrap_err().code,
            "INVALID_RESPONSE"
        );
    }
    #[test]
    fn version() {
        let s = String::from_utf8(frame())
            .unwrap()
            .replace("version\":1", "version\":2");
        assert_eq!(
            decode(s.as_bytes(), "r1").unwrap_err().code,
            "VERSION_MISMATCH"
        );
    }
    #[test]
    fn engine_error() {
        assert_eq!(decode(br#"{"protocol_version":1,"request_id":"r1","ok":false,"error":{"code":"DOMAIN_ERROR","message":"Absent"}}"#, "r1").unwrap_err().code, "DOMAIN_ERROR");
    }
    #[test]
    fn bounded() {
        assert_eq!(
            decode(&vec![b'x'; MAX_FRAME + 1], "r1").unwrap_err().code,
            "FRAME_TOO_LARGE"
        );
    }
    #[test]
    fn async_lifecycle() {
        tauri::async_runtime::block_on(async {
            let (tx, mut rx) = channel(8);
            let mut bytes = frame();
            bytes.push(b'\n');
            tx.send(CommandEvent::Stdout(bytes[..20].to_vec()))
                .await
                .unwrap();
            tx.send(CommandEvent::Stdout(bytes[20..].to_vec()))
                .await
                .unwrap();
            assert_eq!(receive(&mut rx, "r1", TIMEOUT).await.unwrap()["total"], 12);
            assert_eq!(
                receive(&mut rx, "r1", Duration::from_millis(10))
                    .await
                    .unwrap_err()
                    .code,
                "TIMEOUT"
            );
            drop(tx);
            assert_eq!(
                receive(&mut rx, "r1", TIMEOUT).await.unwrap_err().code,
                "ENGINE_EXITED"
            );
        });
    }
}
