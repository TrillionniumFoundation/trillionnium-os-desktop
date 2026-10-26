//! Selector/shape/outcome checks only; no Root, signing key or authority created.
use super::*;
use serde_json::json;

fn args(values: &[&str]) -> impl Iterator<Item = OsString> {
    values
        .iter()
        .map(OsString::from)
        .collect::<Vec<_>>()
        .into_iter()
}

#[test]
fn finite_grant_selectors_refuse_ambiguity_and_duplicate_flags() -> Result<()> {
    let latest = parse_command(args(&["observe-grant", "--latest"]))?;
    assert!(matches!(
        latest.action,
        RootAdminAction::ObserveIssuedNotesGrant {
            selection: RootIssuedNotesGrantSelection::Latest {}
        }
    ));
    let exact = parse_command(args(&[
        "observe-grant",
        "--grant-id",
        "original:1:2",
        "--export-grant",
        "/root/private/artifact.json",
    ]))?;
    assert_eq!(
        exact.export,
        Some(PathBuf::from("/root/private/artifact.json"))
    );
    for bad in [
        vec!["observe-grant"],
        vec!["observe-grant", "--latest", "--grant-id", "original:1:2"],
        vec!["observe-grant", "--grant-id", ""],
        vec!["observe-grant", "--latest", "--latest"],
        vec!["observe-grant", "--latest", "--export-grant"],
        vec![
            "observe-grant",
            "--latest",
            "--export-grant",
            "/a",
            "--export-grant",
            "/b",
        ],
        vec![
            "revoke-grant",
            "--signed-grant-file",
            "/not-opened",
            "--expected-effect-lease-revision",
            "0",
        ],
        vec![
            "revoke-grant",
            "--signed-grant-file",
            "/not-opened",
            "--expected-effect-lease-revision",
            "01",
        ],
        vec![
            "revoke-grant",
            "--signed-grant-file",
            "/not-opened",
            "--expected-effect-lease-revision",
            "1",
            "--expected-effect-lease-revision",
            "1",
        ],
    ] {
        assert!(parse_command(args(&bad)).is_err());
    }
    Ok(())
}

fn artifact() -> String {
    // Synthetic shape only: never used to request permission or a successful revoke.
    json!({"grant": {"schema_version":1,"signer_id":"original","authority_epoch":1,"grant_id":"original:1:1","nonce":vec![7;32],"binding":{"subject_id":"original-owner","destination_id":"original-note","request_sha256":vec![1;32],"scope_sha256":vec![2;32],"payload_sha256":vec![3;32]},"not_before_unix_ms":10,"expires_at_unix_ms":20},"signature":vec![8;64]}).to_string()
}

#[test]
fn export_shape_preserves_exact_bytes_and_refuses_digest_or_schema_changes() -> Result<()> {
    let raw = artifact();
    let digest = json!(Sha256Digest::for_bytes(raw.as_bytes()));
    validate_artifact(&raw, &digest)?;
    assert!(validate_artifact(&(raw.clone() + " "), &digest).is_err());
    for changed in [
        raw.replace("\"grant\":", "\"extra\":1,\"grant\":"),
        raw.replace(
            "\"schema_version\":1",
            "\"schema_version\":1,\"schema_version\":1",
        ),
        raw.replace("\"subject_id\":", "\"unknown\":1,\"subject_id\":"),
    ] {
        assert!(
            validate_artifact(
                &changed,
                &json!(Sha256Digest::for_bytes(changed.as_bytes()))
            )
            .is_err()
        );
    }
    Ok(())
}

#[test]
fn partial_or_unconfirmed_original_revoke_never_reports_success() {
    for value in [
        json!({"status":"unavailable"}),
        json!({"status":"issued_notes_grant_observed","observation":{"status":"unknown"}}),
        json!({"status":"original_notes_grant_revocation","effect_lease_receipt":{"original":"known"},"final_use_head":null,"synchronization":{"state":"confirmed"}}),
        json!({"status":"original_notes_grant_revocation","effect_lease_receipt":{"original":"known"},"final_use_head":{"revision":2},"synchronization":{"state":"pending"}}),
    ] {
        assert!(finish_response(&value, None).is_err());
    }
}
