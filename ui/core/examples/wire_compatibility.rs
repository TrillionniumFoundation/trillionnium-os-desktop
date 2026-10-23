//! Deterministic observer/IPC compatibility corpus. It performs no I/O to a
//! Session, owner, socket or device. CI checks exact aligned bytes and the
//! single reviewed exponent spelling against the actual Desktop 64736996
//! original-source/original-lock output; it does not canonicalize other JSON.
use serde::Serialize;
use std::collections::BTreeMap;
use trill_ui_core::conversation::{ContextRef, LocalDraft};
use trill_ui_core::{
    parse_host_request, AppKind, HostResources, HostWaylandObservation, Request, Response,
    TaskRecord, TaskState, Workspace,
};

fn task(state: TaskState) -> TaskRecord {
    TaskRecord {
        id: u64::MAX,
        workspace: Workspace::Personal,
        app: AppKind::Notes,
        state,
        pid: Some(1),
        exit_code: None,
        detail: "观察记录 · 中文 📝\nquotes: \" \\".into(),
        created_unix_ms: 1,
        updated_unix_ms: 2,
        execution_mode: "linux_host_process".into(),
        hos2_revision: None,
        ui_first_frame_unix_ms: None,
        wayland_socket_epoch_at_launch: None,
        notes_destination: None,
    }
}

fn capture(out: &mut BTreeMap<String, String>, key: String, value: &impl Serialize) {
    out.insert(key, serde_json::to_string(value).unwrap());
}

fn main() {
    let mut output = BTreeMap::new();
    capture(&mut output, "request/snapshot".into(), &Request::Snapshot);
    for workspace in Workspace::ALL {
        for app in AppKind::ALL {
            capture(
                &mut output,
                format!("request/launch/{workspace:?}/{app:?}"),
                &Request::Launch {
                    workspace,
                    app,
                    expected_instance: "11111111111111111111111111111111".into(),
                },
            );
        }
    }
    for id in [0, 1, u64::MAX] {
        capture(
            &mut output,
            format!("request/cancel/{id}"),
            &Request::Cancel {
                id,
                expected_instance: "11111111111111111111111111111111".into(),
            },
        );
    }
    for state in [
        TaskState::Pending,
        TaskState::Running,
        TaskState::Completed,
        TaskState::Failed,
        TaskState::Partial,
        TaskState::Unknown,
        TaskState::CancelRequested,
        TaskState::Cancelled,
    ] {
        capture(
            &mut output,
            format!("response/task/{state:?}"),
            &Response::Task {
                task: task(state),
                session_instance: "11111111111111111111111111111111".into(),
            },
        );
    }
    for bits in [
        0_u32,
        0x8000_0000,
        0x3dcc_cccd,
        0x3f80_0000,
        0x7f7f_ffff,
        1,
        0x7f80_0000,
        0x7fc0_0000,
    ] {
        capture(
            &mut output,
            format!("response/resources/f32-{bits:08x}"),
            &Response::Snapshot {
                tasks: vec![task(TaskState::Unknown)],
                resources: HostResources {
                    sampled_unix_ms: 3,
                    mem_total_kib: Some(u64::MAX),
                    mem_available_kib: None,
                    load_average_1m: Some(f32::from_bits(bits)),
                    source: "host observation only".into(),
                    wayland: HostWaylandObservation::default(),
                },
                session_instance: "11111111111111111111111111111111".into(),
                hepta: Default::default(),
            },
        );
    }
    // The shared original package enables serde_json/float_roundtrip. Compare
    // the actual observation field's parsed bits as well as serialized bytes;
    // reserializing alone could hide a boundary rounding change.
    for (name, number) in [
        ("positive-zero", "0"),
        ("negative-zero", "-0.0"),
        ("decimal-tenth", "0.1"),
        ("half-ulp-at-one", "1.000000059604644775390625"),
        ("above-half-ulp-at-one", "1.000000059604644775390626"),
        ("smallest-subnormal", "1.401298464324817e-45"),
        ("largest-finite", "3.4028234663852886e38"),
        ("f32-overflow", "3.4028236e38"),
        ("json-number-overflow", "1e400"),
    ] {
        let json = format!(
            r#"{{"sampled_unix_ms":3,"mem_total_kib":null,"mem_available_kib":null,"load_average_1m":{number},"source":"float boundary"}}"#
        );
        let parsed: Result<HostResources, _> = serde_json::from_str(&json);
        output.insert(
            format!("response/parse-f32/{name}"),
            match parsed {
                Ok(resources) => format!("{:08x}", resources.load_average_1m.unwrap().to_bits()),
                Err(_) => "rejected".into(),
            },
        );
    }
    let draft = LocalDraft {
        workspace: Workspace::Personal,
        text: "unsent / 未发送\n\"quoted\" \\ 📝".into(),
        contexts: vec![ContextRef::host_task(
            "11111111111111111111111111111111",
            &task(TaskState::Unknown),
            3,
        )],
    };
    draft.validate().unwrap();
    capture(&mut output, "draft/context-reference".into(), &draft);
    let older = r#"{"type":"snapshot","tasks":[],"resources":{"sampled_unix_ms":5,"mem_total_kib":null,"mem_available_kib":null,"load_average_1m":null,"source":"old host"},"session_instance":"old"}"#;
    let parsed: Response = serde_json::from_str(older).unwrap();
    capture(&mut output, "response/old-defaults".into(), &parsed);
    for (name, input) in [
        ("snapshot", r#"{"type":"snapshot"}"#),
        ("unknown-field", r#"{"type":"snapshot","launch":true}"#),
        ("duplicate-type", r#"{"type":"snapshot","type":"snapshot"}"#),
        (
            "cancel",
            r#"{"type":"cancel","id":1,"expected_instance":"observed"}"#,
        ),
        (
            "duplicate-id",
            r#"{"type":"cancel","id":1,"id":2,"expected_instance":"observed"}"#,
        ),
        (
            "negative-id",
            r#"{"type":"cancel","id":-1,"expected_instance":"observed"}"#,
        ),
        (
            "fractional-id",
            r#"{"type":"cancel","id":1.5,"expected_instance":"observed"}"#,
        ),
        (
            "overflow-id",
            r#"{"type":"cancel","id":18446744073709551616,"expected_instance":"observed"}"#,
        ),
        ("missing-instance", r#"{"type":"cancel","id":1}"#),
        ("unknown-command", r#"{"type":"signed_objective","id":1}"#),
    ] {
        output.insert(
            format!("request/acceptance/{name}"),
            parse_host_request(input.as_bytes()).is_ok().to_string(),
        );
    }
    for (name, fixture) in [
        (
            "notes-target",
            include_str!("../../../tests/ui/notes-target-v1.json"),
        ),
        (
            "notes-bootstrap",
            include_str!("../../../tests/ui/notes-bootstrap-v1.json"),
        ),
    ] {
        let value: serde_json::Value = serde_json::from_str(fixture).unwrap();
        capture(&mut output, format!("existing-golden/{name}"), &value);
    }
    println!("{}", serde_json::to_string_pretty(&output).unwrap());
}
