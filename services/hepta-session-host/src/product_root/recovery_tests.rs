//! Contract and real-kernel retirement checks; no Root authority is fabricated.
use super::super::recovery_authority::writer_expiry;
use super::*;

#[test]
fn recovery_selector_is_explicit_exclusive_and_preserves_the_exact_old_id() {
    let parse = |args: &[&str]| {
        RecoverySelection::from_arguments(args.iter().map(std::ffi::OsString::from))
    };
    let exact = parse(&["--operation-id", "original-notes-17"]).unwrap();
    assert_eq!(
        serde_json::to_value(exact).unwrap(),
        serde_json::json!({"kind":"exact_operation","operation_id":"original-notes-17"})
    );
    let latest = parse(&["--latest-original-notes"]).unwrap();
    assert_eq!(
        serde_json::to_value(latest).unwrap(),
        serde_json::json!({"kind":"latest_recorded_original_notes"})
    );
    for args in [
        vec![],
        vec!["--operation-id"],
        vec!["--operation-id", ""],
        vec!["--operation-id", "bad/id"],
        vec!["--latest-original-notes", "--operation-id", "old"],
        vec!["--operation-id", "old", "--latest-original-notes"],
        vec!["--latest-original-notes", "--latest-original-notes"],
    ] {
        assert!(parse(&args).is_err(), "accepted {args:?}");
    }
}

#[test]
fn writer_window_stops_before_the_original_issuer_without_renewal() {
    assert_eq!(writer_expiry(10_000, 310_000).unwrap(), 190_000);
    assert_eq!(writer_expiry(190_001, 310_000).unwrap(), 250_000);
    assert!(writer_expiry(250_000, 310_000).is_err());
    assert!(writer_expiry(u64::MAX - 1, u64::MAX).is_err());
}

#[test]
fn recorded_session_lifetime_is_correlated_and_never_an_exit_claim() {
    let actual = session_lifetime(42, "original-boot:42:17", 60001).unwrap();
    assert_eq!(
        (actual.pid, actual.process_start_ticks, actual.uid),
        (42, 17, 60001)
    );
    for input in [
        "original-boot:41:17",
        "original-boot:42:0",
        "original-boot:42",
        "original-boot:42:17:extra",
    ] {
        assert!(session_lifetime(42, input, 60001).is_err());
    }
}

#[test]
#[ignore = "actual Root same-boot process-retirement qualification"]
fn live_original_session_is_refused_and_actual_exit_can_be_observed() {
    use std::io::{BufRead, BufReader};
    use std::process::{Command, Stdio};
    assert_eq!(unsafe { libc::geteuid() }, 0);
    // This actual disposable child drops privilege; no role/grant is assigned.
    let mut child = Command::new("/usr/bin/setpriv")
        .args([
            "--reuid=60001",
            "--regid=60001",
            "--clear-groups",
            "--no-new-privs",
            "/bin/sh",
            "-c",
            "printf 'ready\\n'; read x",
        ])
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .spawn()
        .unwrap();
    let mut line = String::new();
    BufReader::new(child.stdout.take().unwrap())
        .read_line(&mut line)
        .unwrap();
    assert_eq!(line, "ready\n");
    let pin = super::super::process::pin(child.id()).unwrap();
    let birth = super::super::packet::pinned_metadata(&pin, child.id()).unwrap();
    let lifetime = session_lifetime(child.id(), &birth, 60001).unwrap();
    assert!(RetiredCheckpointPublisher::observe(lifetime.clone()).is_err());
    child.kill().unwrap();
    child.wait().unwrap();
    assert!(RetiredCheckpointPublisher::observe(lifetime).is_ok());
}
