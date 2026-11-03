//! Parser, real local frame and lifetime negatives; no Root service is started.
use super::*;
use std::io::Write;

fn args(values: &[&str]) -> impl Iterator<Item = OsString> {
    values
        .iter()
        .map(|value| OsString::from(*value))
        .collect::<Vec<_>>()
        .into_iter()
}

#[test]
fn finite_admin_cli_rejects_duplicates_missing_versions_and_reasons() -> Result<()> {
    assert!(matches!(
        parse_action(args(&["observe"]))?,
        RootAdminAction::Observe {}
    ));
    for invalid in [
        vec!["observe", "observe"],
        vec!["observe", "--reason-sha256", "11"],
        vec!["revoke-writer"],
        vec!["revoke-writer", "--expected-revision", "1"],
        vec![
            "revoke-writer",
            "--expected-revision",
            "1",
            "--reason-sha256",
            "00",
        ],
        vec![
            "revoke-writer",
            "--expected-revision",
            "1",
            "--expected-revision",
            "2",
        ],
        vec!["revoke-any", "--lease", "unrelated"],
    ] {
        assert!(parse_action(args(&invalid)).is_err());
    }
    assert!(reason(&"0".repeat(64)).is_err());
    assert!(reason(&"F".repeat(64)).is_err());
    assert_eq!(reason(&"ab".repeat(32))?, [0xab; 32]);
    Ok(())
}

#[test]
fn real_admin_frame_rejects_oversize_before_body_and_preserves_exact_bytes() -> Result<()> {
    let (mut sender, mut receiver) = UnixStream::pair()?;
    sender.write_all(&((codex_hepta_agentd::ROOT_ADMIN_FRAME_BOUND + 1) as u32).to_be_bytes())?;
    assert!(admin::read_frame(&mut receiver).is_err());
    let (mut sender, mut receiver) = UnixStream::pair()?;
    let original = br#"{"schema_version":1,"action":{"kind":"observe"}}"#;
    admin::write_frame(&mut sender, original)?;
    assert_eq!(admin::read_frame(&mut receiver)?, original);
    Ok(())
}

#[test]
fn original_admin_descriptor_refuses_unknown_and_duplicate_fields() -> Result<()> {
    let descriptor = admin::Descriptor {
        schema: "trill.original-root-admin.v1".into(),
        socket: "/var/lib/trill/a/admin/root-admin.sock".into(),
        instance: RootAdminInstance {
            boot_id: "original-boot".into(),
            root_pid: 101,
            process_start_ticks: 9,
            episode_nonce: [7; 32],
        },
    };
    let good = serde_json::to_string(&descriptor)?;
    assert!(serde_json::from_str::<admin::Descriptor>(&good).is_ok());
    for invalid in [
        good.replace("\"schema\":", "\"extra\":1,\"schema\":"),
        good.replace("\"root_pid\":101", "\"root_pid\":101,\"root_pid\":102"),
        good.replace(
            "\"process_start_ticks\":9",
            "\"process_start_ticks\":9,\"other\":1",
        ),
    ] {
        assert!(serde_json::from_str::<admin::Descriptor>(&invalid).is_err());
    }
    Ok(())
}

#[test]
fn actual_process_cannot_match_descriptor_with_wrong_boot_or_birth() -> Result<()> {
    let mut instance = RootAdminInstance {
        boot_id: "wrong-boot".into(),
        root_pid: std::process::id(),
        process_start_ticks: 0,
        episode_nonce: [3; 32],
    };
    assert!(verify_birth(&instance).is_err());
    instance.boot_id = std::fs::read_to_string("/proc/sys/kernel/random/boot_id")?
        .trim()
        .into();
    assert!(verify_birth(&instance).is_err());
    Ok(())
}

#[test]
fn cumulative_deadline_does_not_restart_for_a_ready_frame_or_connect() -> Result<()> {
    let (mut sender, mut receiver) = UnixStream::pair()?;
    admin::write_frame(&mut sender, b"actual-frame")?;
    let elapsed = std::time::Instant::now()
        .checked_sub(std::time::Duration::from_secs(1))
        .ok_or("monotonic clock range")?;
    assert!(admin::read_frame_before(&mut receiver, elapsed).is_err());
    assert_eq!(admin::read_frame(&mut receiver)?, b"actual-frame");
    assert!(connect_before(Path::new("/does-not-exist"), elapsed).is_err());
    Ok(())
}
