//! Runtime metadata only: never log paths, query parameters or catalogue responses.
use serde_json::{json, Value};
use std::time::{SystemTime, UNIX_EPOCH};

pub fn event(name: &str, details: Value) {
    let mut record = json!({
        "component": "fabparts-runtime", "event": name,
        "app_pid": std::process::id(),
        "time_ms": SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_millis()
    });
    if let Some(fields) = details.as_object() {
        // A fixed allowlist also protects future callers from logging business data.
        for key in [
            "sidecar_pid",
            "worker_pid",
            "pgid",
            "method",
            "code",
            "exit_code",
            "signal",
            "elapsed_ms",
            "cooperative",
            "bytes",
            "state",
        ] {
            if let Some(value) = fields.get(key) {
                record[key] = value.clone();
            }
        }
    }
    eprintln!("{record}");
}

pub fn process_group(pid: u32) -> Option<i32> {
    #[cfg(unix)]
    {
        // Read-only process metadata; the child handle remains the signal authority.
        let group = unsafe { libc::getpgid(pid as i32) };
        (group >= 0).then_some(group)
    }
    #[cfg(not(unix))]
    {
        let _ = pid;
        None
    }
}

pub fn requests_enabled() -> bool {
    std::env::var("FABPARTS_DIAGNOSTICS").as_deref() == Ok("1")
}
