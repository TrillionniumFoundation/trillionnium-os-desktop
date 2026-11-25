//! Opt-in facts from the existing native window callbacks; no control endpoint.
use serde::Serialize;

const LIMIT: u64 = 65_536;
const SCHEMA: &str = "p4-presenter-window-event-v1";

#[derive(Clone, Debug)]
pub(super) struct WindowIdentity {
    object: u64,
    surface: u32,
    creation_sequence: u64,
    package: String,
}

#[derive(Clone, Copy, Debug, Serialize)]
#[serde(rename_all = "snake_case")]
pub(super) enum Stage {
    Created,
    Bound,
    CloseSent,
    Unmapped,
}

#[derive(Serialize)]
struct Record<'a> {
    schema: &'static str,
    pid: u32,
    sequence: u64,
    creation_sequence: u64,
    object: u64,
    surface: u32,
    package: &'a str,
    android_task: Option<u64>,
    observed_ns: u64,
    stage: Stage,
}

/// Event ordering belongs to this actual App instance, not to caller JSON.
#[derive(Default)]
pub(super) struct Audit {
    sequence: u64,
}

fn enabled() -> bool {
    *super::KEY_TRACE.get_or_init(|| {
        std::env::var_os("DROIDLOOM_INPUT_TRACE").as_deref() == Some(std::ffi::OsStr::new("1"))
    })
}

fn encode(
    identity: &WindowIdentity,
    sequence: u64,
    stage: Stage,
    task: Option<u64>,
    pid: u32,
    observed_ns: u64,
) -> Option<String> {
    // A missing/invalid trace stays missing evidence, never a window operation.
    if identity.object == 0
        || identity.surface == 0
        || identity.creation_sequence == 0
        || sequence < identity.creation_sequence
        || sequence > LIMIT
        || pid <= 1
        || observed_ns == 0
        || identity.package.is_empty()
        || identity.package.len() > 255
        || !identity
            .package
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'.' | b'_'))
        || task.is_some_and(|task| task > i32::MAX as u64)
    {
        return None;
    }
    serde_json::to_string(&Record {
        schema: SCHEMA,
        pid,
        sequence,
        creation_sequence: identity.creation_sequence,
        object: identity.object,
        surface: identity.surface,
        package: &identity.package,
        android_task: task,
        observed_ns,
        stage,
    })
    .ok()
}

impl Audit {
    fn next(&mut self) -> Option<u64> {
        if self.sequence >= LIMIT {
            return None;
        }
        self.sequence += 1;
        Some(self.sequence)
    }

    /// Called only after the actual native Window and its surface exist.
    pub(super) fn created(
        &mut self,
        object: u64,
        surface: u32,
        package: &str,
    ) -> Option<WindowIdentity> {
        if !enabled() {
            return None;
        }
        let sequence = self.next()?;
        let identity = WindowIdentity {
            object,
            surface,
            creation_sequence: sequence,
            package: package.to_owned(),
        };
        let record = encode(
            &identity,
            sequence,
            Stage::Created,
            None,
            std::process::id(),
            super::monotonic_timestamp_nanos().ok()?,
        )?;
        eprintln!("Droidloom window trace: {record}");
        Some(identity)
    }

    /// Called at the actual bind, successful close-send, or role-destroy site.
    pub(super) fn event(
        &mut self,
        stage: Stage,
        identity: &Option<WindowIdentity>,
        task: Option<u64>,
    ) {
        let Some(identity) = identity.as_ref().filter(|_| enabled()) else {
            return;
        };
        let Some(sequence) = self.next() else {
            return;
        };
        let Ok(observed_ns) = super::monotonic_timestamp_nanos() else {
            return;
        };
        if let Some(record) = encode(
            identity,
            sequence,
            stage,
            task,
            std::process::id(),
            observed_ns,
        ) {
            eprintln!("Droidloom window trace: {record}");
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn identity() -> WindowIdentity {
        WindowIdentity {
            object: 7,
            surface: 15,
            creation_sequence: 2,
            package: "org.example.app".into(),
        }
    }

    #[test]
    fn window_trace_preserves_actual_creation_identity_and_does_not_claim_android_close() {
        let created: serde_json::Value =
            serde_json::from_str(&encode(&identity(), 2, Stage::Created, None, 100, 900).unwrap())
                .unwrap();
        let sent: serde_json::Value = serde_json::from_str(
            &encode(&identity(), 4, Stage::CloseSent, Some(9), 100, 950).unwrap(),
        )
        .unwrap();
        assert_eq!(created["android_task"], serde_json::Value::Null);
        assert_eq!(sent["stage"], "close_sent");
        assert_eq!(sent["creation_sequence"], created["sequence"]);
        assert_eq!(sent["object"], created["object"]);
        assert_eq!(sent["surface"], created["surface"]);
        assert_eq!(sent["package"], created["package"]);
        assert!(sent.get("task_removed").is_none());
        assert!(sent.get("business_accepted").is_none());
    }

    #[test]
    fn window_trace_rejects_malformed_identity_and_has_a_fixed_event_bound() {
        let good = identity();
        for kind in 0..5 {
            let mut bad = good.clone();
            match kind {
                0 => bad.object = 0,
                1 => bad.surface = 0,
                2 => bad.creation_sequence = 0,
                3 => bad.package.push('\n'),
                _ => bad.package = "x".repeat(256),
            }
            assert!(encode(&bad, 3, Stage::Bound, Some(9), 100, 950).is_none());
        }
        assert!(encode(&good, 1, Stage::Bound, Some(9), 100, 950).is_none());
        // Android observation IDs are nonnegative; zero is not control authority.
        let zero: serde_json::Value =
            serde_json::from_str(&encode(&good, 3, Stage::Bound, Some(0), 100, 950).unwrap())
                .unwrap();
        assert_eq!(zero["android_task"], 0);
        assert!(encode(&good, 3, Stage::Bound, Some(i32::MAX as u64), 100, 950).is_some());
        assert!(encode(&good, 3, Stage::Bound, Some(i32::MAX as u64 + 1), 100, 950).is_none());
        assert!(encode(&good, 3, Stage::Bound, Some(9), 0, 950).is_none());
        assert!(encode(&good, 3, Stage::Bound, Some(9), 100, 0).is_none());
        let mut audit = Audit {
            sequence: LIMIT - 1,
        };
        assert_eq!(audit.next(), Some(LIMIT));
        assert_eq!(audit.next(), None);
        assert_eq!(audit.next(), None);
    }
}
