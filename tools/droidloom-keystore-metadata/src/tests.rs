use super::*;
use rusqlite::{Connection, params};
use serde_json::{Value, json};
use std::collections::BTreeSet;
use std::fs;
use std::os::unix::fs::{PermissionsExt, symlink};
use std::path::{Path, PathBuf};
use tempfile::TempDir;

struct Fixture {
    _root: TempDir,
    input: PathBuf,
    workspace: PathBuf,
    evidence_dir: PathBuf,
}
fn add_key(
    db: &Connection,
    id: i64,
    kind: i64,
    state: i64,
    uuid: &[u8],
    levels: &[i64],
    has_blob: bool,
) {
    db.execute(
        "INSERT INTO keyentry VALUES(?1,?2,0,10001,?3,?4,?5)",
        params![id, kind, b"private-synthetic-alias".as_slice(), state, uuid],
    )
    .unwrap();
    for (i, level) in levels.iter().enumerate() {
        db.execute(
            "INSERT INTO keyparameter VALUES(?1,?2,?3,?4)",
            params![id, 805306773_i64 + i as i64, 3_i64 + i as i64, level],
        )
        .unwrap();
    }
    if has_blob {
        db.execute("INSERT INTO blobentry(id,subcomponent_type,keyentryid,blob,state) VALUES(?1,0,?1,?2,0)",
            params![id,b"synthetic encrypted KMR stand-in".as_slice()]).unwrap();
    }
}
fn fixture() -> Fixture {
    let root = tempfile::tempdir().unwrap();
    let input_dir = root.path().join("input");
    fs::create_dir(&input_dir).unwrap();
    let workspace = root.path().join("workspace");
    fs::create_dir(&workspace).unwrap();
    let evidence_dir = root.path().join("evidence");
    fs::create_dir(&evidence_dir).unwrap();
    let input = input_dir.join("persistent.sqlite");
    let db = Connection::open(&input).unwrap();
    for (_, sql) in database::TABLES.iter().chain(database::INDEXES) {
        db.execute(sql, []).unwrap();
    }
    db.execute("INSERT INTO version VALUES(0,2)", []).unwrap();
    let uuid = database::DEFAULT_UUID;
    let mut strongbox = uuid.to_vec();
    strongbox[15] = 2;
    add_key(&db, 1, 0, 1, uuid, &[1, 1, 0, 100], true);
    add_key(&db, 2, 0, 1, uuid, &[0], true); // already software
    add_key(&db, 3, 0, 1, &strongbox, &[1], true); // other backend
    add_key(&db, 4, 1, 1, uuid, &[1], true); // super key
    add_key(&db, 5, 0, 2, uuid, &[1], true); // unreferenced
    add_key(&db, 6, 0, 1, &[0x41; 16], &[1], false); // certificate only
    add_key(&db, 7, 0, 1, uuid, &[1, 2], true); // ambiguous StrongBox bucket
    add_key(&db, 8, 0, 1, uuid, &[1], true); // mismatched blob UUID
    add_key(&db, 9, 0, 1, uuid, &[1], true); // outer-encrypted, not offline authenticated
    db.execute(
        "INSERT INTO blobmetadata(blobentryid,tag,data) VALUES(8,4,?1)",
        [strongbox],
    )
    .unwrap();
    db.execute(
        "INSERT INTO blobmetadata(blobentryid,tag,data) VALUES(9,0,700)",
        [],
    )
    .unwrap();
    db.execute(
        "INSERT INTO blobmetadata(blobentryid,tag,data) VALUES(9,2,x'010203')",
        [],
    )
    .unwrap();
    db.execute(
        "INSERT INTO keyparameter VALUES(1,-1610612234,1234567,1)",
        [],
    )
    .unwrap(); // USER_SECURE_ID
    db.execute("INSERT INTO keyparameter VALUES(1,805306873,30,1)", [])
        .unwrap(); // AUTH_TIMEOUT
    db.execute("INSERT INTO keyparameter VALUES(1,805306772,7,1)", [])
        .unwrap(); // MAX_USES_PER_BOOT
    db.execute("INSERT INTO keymetadata VALUES(1,0,100000)", [])
        .unwrap();
    db.execute("INSERT INTO grant VALUES(50,10002,1,63)", [])
        .unwrap();
    for (id, key, levels) in [
        (101, 1, Some((1, 1))),
        (103, 3, Some((2, 2))),
        (106, 6, None),
    ] {
        let cert = certificates::tests::fixture(levels);
        db.execute(
            "INSERT INTO blobentry VALUES(?1,1,?2,?3,0)",
            params![id, key, cert],
        )
        .unwrap();
    }
    drop(db);
    fs::set_permissions(&input, fs::Permissions::from_mode(0o600)).unwrap();
    Fixture {
        _root: root,
        input,
        workspace,
        evidence_dir,
    }
}
fn artifact(path: &Path, content: &[u8]) -> Value {
    fs::write(path, content).unwrap();
    json!({"path":path,"sha256":snapshot::hash_file(path).unwrap().sha256})
}
fn artifact_json(path: &Path, value: Value) -> Value {
    artifact(path, &serde_json::to_vec_pretty(&value).unwrap())
}
fn evidence(f: &Fixture, security_level: i32) -> PathBuf {
    let sha = snapshot::hash_file(&f.input).unwrap().sha256;
    let stand_in = artifact(
        &f.evidence_dir.join("SYNTHETIC-ARTIFACT"),
        b"SYNTHETIC TEST ONLY; not runtime evidence",
    );
    let snapshot_receipt = artifact_json(
        &f.evidence_dir.join("snapshot.json"),
        json!({
            "schema":1,"method":"isolated-offline-filesystem-copy","input_sha256":sha,
            "sqlite_sidecars_absent":true,"cold_image_copy_receipt":stand_in
        }),
    );
    let legacy = artifact_json(
        &f.evidence_dir.join("legacy.json"),
        json!({
            "schema":1,"implementation":"aosp-rust-keymint-nonsecure",
            "keymint_source_commit":"cfeefc94bf8c4f19d19dca193d376a1fc05e8e3e",
            "interfaces_source_commit":"0162af698935100a590b7359581ac8b1b80693e5",
            "default_service_executable":stand_in,"custody_receipt":stand_in
        }),
    );
    let replacement = artifact_json(
        &f.evidence_dir.join("replacement.json"),
        json!({
            "schema":1,"service":"android.hardware.security.keymint.IKeyMintDevice/default",
            "observation_method":"binder-getHardwareInfo",
            "source_commit":"0b764333d79c4ce6875a43d81e796fe32a0794a5",
            "security_level":security_level,"implementation_name":"Droidloom software KeyMint (KMR legacy v1)",
            "default_service_executable":stand_in,"candidate_vendor_image":stand_in,"runtime_receipt":stand_in
        }),
    );
    let path = f.evidence_dir.join("envelope.json");
    artifact_json(
        &path,
        json!({
            "schema":1,"input_sha256":sha,"snapshot_receipt":snapshot_receipt,
            "legacy_provenance":legacy,"replacement_observation":replacement
        }),
    );
    path
}
fn request(f: &Fixture, evidence: Option<PathBuf>) -> Request {
    Request {
        input: f.input.clone(),
        workspace: f.workspace.clone(),
        evidence,
    }
}
#[test]
fn audit_is_readonly_redacted_and_does_not_qualify_uuid() {
    let f = fixture();
    let before = snapshot::hash_file(&f.input).unwrap();
    let report = run(&request(&f, None)).unwrap();
    assert_eq!(report["counts"]["candidate_key_entries"], 2);
    assert_eq!(report["counts"]["candidate_authorization_rows"], 6);
    assert_eq!(report["changed_authorization_rows"], 0);
    assert_eq!(report["uuid_is_backend_identity"], false);
    assert_eq!(report["backend_binding"], Value::Null);
    assert_eq!(report["offline_keyblob_authentication_performed"], false);
    assert_eq!(report["before"], report["after"]);
    assert_eq!(snapshot::hash_file(&f.input).unwrap(), before);
    assert_eq!(fs::read_dir(&f.workspace).unwrap().count(), 0);
    let text = serde_json::to_string(&report).unwrap();
    for forbidden in [
        "private-synthetic-alias",
        "synthetic encrypted KMR stand-in",
        "synthetic ID never logged",
    ] {
        assert!(!text.contains(forbidden));
    }
    assert_eq!(
        report["historical_certificate_attestation"]["all_stored_certificate_blobs"]["android_attestation_oid_certificates"],
        2
    );
    assert_eq!(
        report["historical_certificate_attestation"]["live_default_route_client_certificate_blobs"]
            ["declared_security_level_pairs"]["attestation_1_keymint_1"],
        1
    );
}
#[test]
fn clone_changes_only_selected_level_cells_and_keeps_usage_sid_grants_blobs() {
    let f = fixture();
    let proof = evidence(&f, 0);
    let before = snapshot::hash_file(&f.input).unwrap();
    let report = run(&request(&f, Some(proof))).unwrap();
    assert_eq!(report["changed_authorization_rows"], 6);
    assert_eq!(report["invariants_verified"], true);
    assert_eq!(report["production_approved"], false);
    assert_eq!(
        report["backend_binding"]["external_observation_claims_independently_attested_by_tool"],
        false
    );
    assert_eq!(snapshot::hash_file(&f.input).unwrap(), before);
    let out = PathBuf::from(report["output_directory"].as_str().unwrap());
    assert_ne!(out, f.input.parent().unwrap());
    assert_eq!(
        fs::metadata(&out).unwrap().permissions().mode() & 0o777,
        0o700
    );
    assert_eq!(
        fs::metadata(out.join("persistent.sqlite"))
            .unwrap()
            .permissions()
            .mode()
            & 0o777,
        0o600
    );
    for (table, _) in database::TABLES {
        if *table != "keyparameter" {
            assert_eq!(report["before"][*table], report["after"][*table]);
        }
    }
    let db = database::open(out.join("persistent.sqlite")).unwrap();
    assert_eq!(
        database::candidates(&db)
            .unwrap()
            .counts
            .candidate_authorization_rows,
        0
    );
    for (tag, data) in [
        (805306773_i64, 3_i64),
        (-1610612234, 1234567),
        (805306873, 30),
        (805306772, 7),
    ] {
        let actual: (i64, i64) = db
            .query_row(
                "SELECT data,security_level FROM keyparameter WHERE keyentryid=1 AND tag=?1",
                [tag],
                |r| Ok((r.get(0)?, r.get(1)?)),
            )
            .unwrap();
        assert_eq!(actual, (data, 0));
    }
    for id in [3, 4, 5, 6, 7, 8] {
        let n: i64 = db
            .query_row(
                "SELECT count(*) FROM keyparameter WHERE keyentryid=?1 AND security_level=1",
                [id],
                |r| r.get(0),
            )
            .unwrap();
        assert_eq!(n, 1);
    }
}
#[test]
fn second_clone_is_idempotent_after_rebinding_snapshot_evidence() {
    let f = fixture();
    let report = run(&request(&f, Some(evidence(&f, 0)))).unwrap();
    let out = PathBuf::from(report["output_directory"].as_str().unwrap());
    let second = fixture();
    fs::copy(out.join("persistent.sqlite"), &second.input).unwrap();
    let second_proof = evidence(&second, 0);
    let report = run(&request(&second, Some(second_proof))).unwrap();
    assert_eq!(report["changed_authorization_rows"], 0);
    assert_eq!(report["before"], report["after"]);
}
#[test]
fn missing_identity_wrong_security_and_changed_evidence_fail_closed() {
    let f = fixture();
    let proof = f.evidence_dir.join("uuid-only.json");
    artifact_json(&proof, json!({"uuid":"00000000000000000000000000000001"}));
    assert_eq!(
        run(&request(&f, Some(proof))).unwrap_err(),
        "evidence_envelope_invalid"
    );
    let f = fixture();
    let proof = evidence(&f, 1);
    assert_eq!(
        run(&request(&f, Some(proof))).unwrap_err(),
        "honest_software_runtime_observation_missing"
    );
    let f = fixture();
    let proof = evidence(&f, 0);
    fs::write(f.evidence_dir.join("SYNTHETIC-ARTIFACT"), b"changed").unwrap();
    assert_eq!(
        run(&request(&f, Some(proof))).unwrap_err(),
        "evidence_artifact_digest_mismatch"
    );
}
#[test]
fn unknown_schema_triggers_constraints_and_version_are_refused() {
    for sql in [
        "CREATE TRIGGER forbidden AFTER UPDATE ON keyparameter BEGIN UPDATE grant SET access_vector=0; END",
        "ALTER TABLE keyparameter ADD COLUMN unexpected INTEGER",
        "UPDATE version SET version=3",
    ] {
        let f = fixture();
        let db = Connection::open(&f.input).unwrap();
        db.execute_batch(sql).unwrap();
        drop(db);
        assert!(run(&request(&f, None)).is_err());
        assert_eq!(fs::read_dir(&f.workspace).unwrap().count(), 0);
    }
}
#[test]
fn all_sidecars_including_empty_files_are_refused() {
    for suffix in ["-wal", "-shm", "-journal"] {
        let f = fixture();
        fs::write(format!("{}{suffix}", f.input.display()), b"").unwrap();
        assert_eq!(
            run(&request(&f, None)).unwrap_err(),
            "sqlite_sidecar_requires_reviewed_snapshot_workflow"
        );
        assert_eq!(fs::read_dir(&f.workspace).unwrap().count(), 0);
    }
}
#[test]
fn hardlinks_symlinks_and_input_workspace_are_refused() {
    let f = fixture();
    fs::hard_link(&f.input, f.evidence_dir.join("linked")).unwrap();
    assert_eq!(
        run(&request(&f, None)).unwrap_err(),
        "nonregular_or_hardlinked_input_refused"
    );
    let f = fixture();
    let old = f.input.parent().unwrap().join("real.sqlite");
    fs::rename(&f.input, &old).unwrap();
    symlink(&old, &f.input).unwrap();
    assert_eq!(run(&request(&f, None)).unwrap_err(), "symlink_refused");
    let f = fixture();
    let linked = f.evidence_dir.join("linked-parent");
    symlink(f.input.parent().unwrap(), &linked).unwrap();
    let r = Request {
        input: linked.join("persistent.sqlite"),
        workspace: f.workspace.clone(),
        evidence: None,
    };
    assert_eq!(run(&r).unwrap_err(), "symlink_refused");
    let f = fixture();
    let r = Request {
        input: f.input.clone(),
        workspace: f.input.parent().unwrap().to_owned(),
        evidence: None,
    };
    assert_eq!(run(&r).unwrap_err(), "workspace_inside_input_refused");
}
#[test]
fn failed_logical_postcondition_rolls_back_the_entire_private_transaction() {
    let f = fixture();
    let copy = snapshot::PrivateCopy::new(&f.input, &f.workspace).unwrap();
    let mut db = database::open(copy.database_path()).unwrap();
    database::validate_schema(&db).unwrap();
    let candidates = database::candidates(&db).unwrap();
    let original = database::fingerprints(&db, &BTreeSet::new()).unwrap();
    assert_eq!(
        database::apply_to_private_copy(&mut db, &candidates, &original).unwrap_err(),
        "logical_invariant_mismatch_rolled_back"
    );
    assert_eq!(
        database::fingerprints(&db, &BTreeSet::new()).unwrap(),
        original
    );
    copy.verify_input_unchanged().unwrap();
}

#[test]
fn decoded_json_bytes_must_match_the_bound_digest() {
    let f = fixture();
    let proof = evidence(&f, 0);
    let path = f.evidence_dir.join("legacy.json");
    let mut value: Value = serde_json::from_slice(&fs::read(&path).unwrap()).unwrap();
    value["implementation"] = json!("changed but otherwise valid JSON");
    fs::write(&path, serde_json::to_vec_pretty(&value).unwrap()).unwrap();
    assert_eq!(
        run(&request(&f, Some(proof))).unwrap_err(),
        "evidence_artifact_digest_mismatch"
    );
}
