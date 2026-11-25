//! Fresh-fixture-only proof of GDM's dynamic greeter environment writer.
//! This adds no root runtime observer and does not qualify a visible desktop.
use crate::{Result, boot_files, ensure, fs};
use serde::Deserialize;
use serde_json::{Value, json};
use std::collections::BTreeSet;
use std::path::Path;

pub const UNIT: &str = "droidloom-fixture-greeter-proof.service";
pub const CONFIG: &str = "/etc/gdm3/custom.conf";
pub const SCRIPT: &str = "/usr/libexec/droidloom-fixture-greeter-proof.py";
pub const SERVICE: &str = "/usr/lib/systemd/user/droidloom-fixture-greeter-proof.service";
pub const DROPIN: &str = "/usr/lib/systemd/user/gnome-session@gnome-login.target.d/50-droidloom-fixture-greeter-proof.conf";
pub const FILES: &[(&str, &[u8])] = &[
    (
        SCRIPT,
        include_bytes!("../qualification/gdm_greeter_proof.py"),
    ),
    (
        SERVICE,
        include_bytes!("../qualification/droidloom-fixture-greeter-proof.service"),
    ),
    (
        DROPIN,
        include_bytes!("../qualification/50-droidloom-fixture-greeter-proof.conf"),
    ),
];

pub fn timed_config_valid(bytes: &[u8]) -> bool {
    std::str::from_utf8(bytes).is_ok_and(|text| {
        let active: Vec<_> = text
            .lines()
            .map(str::trim)
            .filter(|line| !line.is_empty() && !line.starts_with('#'))
            .collect();
        active
            == [
                "[daemon]",
                "AutomaticLoginEnable=false",
                "TimedLoginEnable=true",
                "TimedLogin=alex",
                "TimedLoginDelay=20",
                "WaylandEnable=true",
                "[security]",
                "[debug]",
            ]
    })
}

/// These bytes are the selected Ubuntu 50.1 package's actual normal target
/// and GDM drop-in, not a manufactured user manager or an alternate session.
pub fn validate_public_group(bytes: &[u8]) -> Result<()> {
    let text = std::str::from_utf8(bytes)?;
    let rows: Vec<_> = text
        .lines()
        .filter(|line| line.split(':').next() == Some("gdm"))
        .collect();
    ensure(
        rows.len() == 1 && rows[0].split(':').collect::<Vec<_>>().get(2) == Some(&"121"),
        "selected GDM_GROUPNAME=gdm must retain its original public primary GID 121",
    )
}

/// This value can only be constructed from a pinned native preparation
/// receipt. A numeric CLI override cannot select a trusted journal group.
#[derive(Clone, Debug, serde::Serialize)]
pub struct GroupBinding {
    gid: u32,
    native_schema: String,
    initialization_schema: String,
}

pub fn native_group_binding(native: &Value, work: &Path) -> Result<GroupBinding> {
    let init = &native["native_initialization"];
    let expected_root = work.join("root");
    ensure(
        native["work_directory"].as_str() == work.to_str()
            && native["root"].as_str() == expected_root.to_str()
            && init["work"].as_str() == work.to_str()
            && init["root"].as_str() == expected_root.to_str()
            && native["guest_qualified"] == false
            && native["production_ready"] == false
            && init["native_initialization_complete"] == true
            && init["guest_started"] == false
            && init["guest_qualified"] == false
            && init["host_passwords_keys_homes_imported"] == false,
        "GDM group authority is not the same completed unbooted native fixture",
    )?;
    let gid = init["accounts"]["groups"]["gdm"]
        .as_u64()
        .filter(|v| (1..1000).contains(v))
        .ok_or("native preparation has no valid normal GDM group")? as u32;
    let native_schema = native["schema"]
        .as_str()
        .ok_or("native receipt schema absent")?;
    let initialization_schema = init["schema"]
        .as_str()
        .ok_or("native initialization schema absent")?;
    match (native_schema, initialization_schema) {
        ("droidloom.ubuntu-native-prepared.v1", "droidloom.native-ubuntu-initialization.v1") => {
            ensure(
                gid == 121,
                "historical public fixture must retain GDM GID 121",
            )?;
        }
        (
            "droidloom.complete-ubuntu-native-prepared.v1",
            "droidloom.complete-native-ubuntu-initialization.v1",
        ) => {
            ensure(
                init["source_stage"] == "installed"
                    && init["accounts"]["normal_service_accounts_preserved"] == true,
                "complete GDM group lacks installed native account preservation",
            )?;
        }
        _ => return Err("unrecognized native GDM group authority".into()),
    }
    let users = init["accounts"]["users"]
        .as_array()
        .ok_or("native account roster absent")?;
    let gdm: Vec<_> = users.iter().filter(|u| u["name"] == "gdm").collect();
    ensure(
        gdm.len() == 1
            && gdm[0]["gid"].as_u64() == Some(u64::from(gid))
            && gdm[0]["uid"]
                .as_u64()
                .is_some_and(|v| (1..1000).contains(&v)),
        "prepared GDM user and normal group disagree",
    )?;
    Ok(GroupBinding {
        gid,
        native_schema: native_schema.into(),
        initialization_schema: initialization_schema.into(),
    })
}

pub fn validate_bound_group(bytes: &[u8], binding: &GroupBinding) -> Result<()> {
    let mut names = BTreeSet::new();
    let mut gids = BTreeSet::new();
    let mut found = false;
    for line in std::str::from_utf8(bytes)?.lines() {
        let fields: Vec<_> = line.split(':').collect();
        ensure(
            fields.len() == 4
                && !fields[0].is_empty()
                && fields[0]
                    .bytes()
                    .all(|b| b.is_ascii_alphanumeric() || b"_-".contains(&b))
                && ["x", "!", "*", ""].contains(&fields[1])
                && names.insert(fields[0]),
            "ended native group file has an invalid or duplicate row",
        )?;
        let gid: u32 = fields[2].parse()?;
        ensure(
            gids.insert(gid),
            "ended native group file aliases a numeric group",
        )?;
        if fields[0] == "gdm" {
            ensure(
                gid == binding.gid,
                "ended GDM group differs from pinned native preparation",
            )?;
            found = true;
        }
    }
    ensure(found, "ended native group file has no GDM group")
}

pub fn original_session(tree: &fs::Tree) -> Result<Value> {
    let mut originals = Vec::new();
    for (path, bytes, sha) in [
        (
            "/usr/lib/systemd/user/gnome-session@.target",
            546,
            "a5056b08f3a3827cb2e3159790b03f5b056156b5c444ec6b67f3f0aceb7e7dec",
        ),
        (
            "/usr/lib/systemd/user/gnome-session@gnome-login.target.d/gnome-login.session.conf",
            88,
            "1da5dbbc7edeff89181fa1f4ba025bdf1f6b80973409e879cbb8b1a7265ac1a0",
        ),
    ] {
        let (id, digest, _) = fs::read_regular(tree, path)?;
        ensure(
            id.uid == 0 && id.gid == 0 && id.mode & 0o022 == 0 && id.size == bytes && digest == sha,
            "selected normal GNOME greeter user target differs",
        )?;
        originals.push(json!({"path":path,"identity":id,"sha256":digest}));
    }
    let (python, sha, _) = fs::read_regular(tree, "/usr/bin/python3.14")?;
    ensure(
        python.uid == 0
            && python.gid == 0
            && python.mode & 0o022 == 0
            && python.mode & 0o111 != 0
            && python.size > 0,
        "selected native Python interpreter is absent or writable",
    )?;
    Ok(json!({"normal_greeter_targets":originals,
        "interpreter":{"path":"/usr/bin/python3.14","identity":python,"sha256":sha},
        "source":"already verified normal native clone",
        "extra_runtime_privileges":false,"runtime_proof_observed":false}))
}

pub fn validate_labels(labels: &Value) -> Result<()> {
    let rows = labels["labels"]
        .as_array()
        .ok_or("source label inventory absent")?;
    for (path, label) in [
        (SCRIPT, "u:object_r:p4_linux_native_bin_t:s0"),
        (SERVICE, "u:object_r:p4_linux_runtime_lib_t:s0"),
        (DROPIN, "u:object_r:p4_linux_runtime_lib_t:s0"),
    ] {
        let row = rows
            .iter()
            .find(|r| r["path"] == path)
            .ok_or("fixture greeter proof source label missing")?;
        let raw = hex::decode(
            row["label_hex"]
                .as_str()
                .ok_or("invalid proof source label")?,
        )?;
        ensure(
            raw.strip_suffix(&[0]).unwrap_or(&raw) == label.as_bytes(),
            "fixture greeter proof has an unexpected native object type",
        )?;
    }
    Ok(())
}

/// Content is verified independently of the common exact inode/xattr
/// readback. Old prepared roots without the proof cannot pass this new gate.
pub fn verify_image(root: &Path, work: &Path, image: &Path) -> Result<Value> {
    let tree = fs::Tree::open(&fs::absolute_string(root)?, 0)?;
    let check = work.join("gdm-greeter-proof-image-readback");
    boot_files::private_dir(&check)?;
    let mut rows = Vec::new();
    let config = boot_files::pin_file(&boot_files::guest_path(root, CONFIG)?)?;
    let config_bytes = boot_files::read_pin(&config, 65536)?;
    ensure(
        timed_config_valid(&config_bytes),
        "fixture GDM timed-login settings differ",
    )?;
    let mut source_files: Vec<_> = FILES
        .iter()
        .map(|(path, bytes)| (*path, *bytes, 0o444))
        .collect();
    source_files.push((CONFIG, &config_bytes, 0o644));
    for (index, (path, expected, mode)) in source_files.iter().enumerate() {
        let (id, digest, _) = fs::read_regular(&tree, path)?;
        ensure(
            id.uid == 0
                && id.gid == 0
                && id.nlink == 1
                && id.mode & 0o7777 == *mode
                && id.size == expected.len() as u64
                && digest == fs::digest(expected),
            "fixture proof source bytes or metadata differ",
        )?;
        let extracted = check.join(format!("file-{index}"));
        let command = format!(
            "dump -p {} {}",
            crate::boot_runtime::debugfs_command_path(path)?,
            crate::boot_runtime::debugfs_command_path(&fs::absolute_string(&extracted)?)?
        );
        let dump = boot_files::run_logged(
            &check,
            &format!("file-{index}"),
            "/usr/sbin/debugfs",
            &["-R".into(), command, image.to_string_lossy().into()],
            30,
        )?;
        let actual = boot_files::pin_file(&extracted)?;
        ensure(
            actual.bytes == id.size && actual.sha256 == digest,
            "actual ext4 greeter proof bytes differ from the frozen producer",
        )?;
        rows.push(json!({"path":path,"source_identity":id,"sha256":digest,
            "image_file":actual,"dump":dump}));
    }
    Ok(
        json!({"schema":"droidloom.fixture-gdm-proof-image.v1","files":rows,
        "all_matched":true,"runtime_proof_observed":false}),
    )
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Proof {
    schema: String,
    result: String,
    uid: u32,
    gid: u32,
    pid: u32,
    unit: String,
    invocation_id: String,
    guest_clock: String,
    guest_monotonic_ns_start: u64,
    guest_monotonic_ns_end: u64,
    requires_trusted_journal_identity: bool,
    file_bytes: u64,
    file_sha256: String,
    file_device: u64,
    file_inode: u64,
    file_owner_uid: u32,
    file_owner_gid: u32,
    file_mode: String,
    private_directory_mode: String,
    checked_environment_fields: Vec<String>,
    source_body_emitted: bool,
}

fn nonzero_id(value: &str) -> bool {
    value.len() == 32
        && value
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
        && value.bytes().any(|b| b != b'0')
}

fn trusted_record(row: &Value, proof: &Proof, boot: &str, expected_gid: u32) -> bool {
    let uid = proof.uid.to_string();
    let gid = expected_gid.to_string();
    let user_manager = format!("user@{}.service", proof.uid);
    let journal_time = row["__MONOTONIC_TIMESTAMP"]
        .as_str()
        .and_then(|s| s.parse::<u64>().ok())
        .and_then(|v| v.checked_add(1))
        .and_then(|v| v.checked_mul(1000));
    proof.schema == "droidloom.fixture-gdm-greeter-proof.v1"
        && proof.result == "passed"
        && (60578..=60705).contains(&proof.uid)
        && proof.gid == expected_gid
        && proof.pid > 1
        && proof.unit == UNIT
        && nonzero_id(&proof.invocation_id)
        && proof.guest_clock == "CLOCK_MONOTONIC"
        && proof.guest_monotonic_ns_end >= proof.guest_monotonic_ns_start
        && proof.guest_monotonic_ns_end - proof.guest_monotonic_ns_start <= 12_000_000_000
        && journal_time.is_some_and(|v| v >= proof.guest_monotonic_ns_end)
        && proof.requires_trusted_journal_identity
        && (1..=65536).contains(&proof.file_bytes)
        && fs::valid_digest(&proof.file_sha256)
        && proof.file_device > 0
        && proof.file_inode > 0
        && proof.file_owner_uid == proof.uid
        && proof.file_owner_gid == 65534
        && proof.file_mode == "0600"
        && proof.private_directory_mode == "0700"
        && proof.checked_environment_fields == ["USER", "LOGNAME", "HOME", "GDM_SEAT_ID"]
        && !proof.source_body_emitted
        && row["_UID"] == uid
        && row["_GID"] == gid
        && row["_SYSTEMD_OWNER_UID"] == uid
        && row["_PID"] == proof.pid.to_string()
        && row["_SYSTEMD_UNIT"] == user_manager
        && row["_SYSTEMD_USER_UNIT"] == UNIT
        && row["_SYSTEMD_INVOCATION_ID"] == proof.invocation_id
        && row["_BOOT_ID"] == boot
        && row["_EXE"] == "/usr/bin/python3.14"
        && row["_TRANSPORT"] == "stdout"
}

/// Called only on the original, verified native journals extracted by the
/// existing ended-VM collector. JSON text and SyslogIdentifier are insufficient.
#[cfg(test)]
pub fn journal_evidence(
    rows: &[Value],
    boot_ids: &BTreeSet<String>,
    source_verified: bool,
) -> Value {
    journal_evidence_for_gid(rows, boot_ids, source_verified, 121)
}

pub fn journal_evidence_bound(
    rows: &[Value],
    boot_ids: &BTreeSet<String>,
    source_verified: bool,
    binding: &GroupBinding,
) -> Value {
    let mut evidence = journal_evidence_for_gid(rows, boot_ids, source_verified, binding.gid);
    evidence["native_group_binding"] = json!(binding);
    evidence
}

fn journal_evidence_for_gid(
    rows: &[Value],
    boot_ids: &BTreeSet<String>,
    source_verified: bool,
    expected_gid: u32,
) -> Value {
    let boot = boot_ids.iter().next().map(String::as_str).unwrap_or("");
    let mut observations = Vec::new();
    let mut invalid = 0usize;
    for row in rows.iter().filter(|r| r["_SYSTEMD_USER_UNIT"] == UNIT) {
        let proof = row["MESSAGE"]
            .as_str()
            .filter(|s| s.len() <= 4096)
            .and_then(|s| serde_json::from_str::<Proof>(s).ok());
        if let Some(proof) = proof.filter(|p| trusted_record(row, p, boot, expected_gid)) {
            let uid = proof.uid.to_string();
            let manager = format!("user@{}.service", proof.uid);
            let terminal: Vec<_> = rows
                .iter()
                .filter(|r| {
                    r["_UID"] == uid
                        && r["_SYSTEMD_UNIT"] == manager
                        && r["_EXE"] == "/usr/lib/systemd/systemd"
                        && r["_TRANSPORT"] == "journal"
                        && r["_BOOT_ID"] == boot
                        && r["USER_UNIT"] == UNIT
                        && r["USER_INVOCATION_ID"] == proof.invocation_id
                })
                .collect();
            // With the frozen Type=oneshot/RemainAfterExit unit and no ignored
            // commands, the actual manager's start-job success follows exit 0.
            let done = terminal.iter().any(|r| {
                r["MESSAGE_ID"] == "39f53479d3a045ac8e11786248231fbf"
                    && r["JOB_TYPE"] == "start"
                    && r["JOB_RESULT"] == "done"
            });
            let failed = terminal.iter().any(|r| {
                r["JOB_RESULT"]
                    .as_str()
                    .is_some_and(|s| ["failed", "dependency", "timeout", "canceled"].contains(&s))
                    || r["UNIT_RESULT"].as_str().is_some_and(|s| s != "success")
                    || (!r["EXIT_CODE"].is_null() && r["EXIT_CODE"] != "exited")
                    || (!r["EXIT_STATUS"].is_null()
                        && r["EXIT_STATUS"] != "0"
                        && r["EXIT_STATUS"] != 0)
            });
            observations.push(json!({"original_journal_record":row,
                "user_manager_terminal_records":terminal,"normal_oneshot_completion":done && !failed}));
        } else {
            invalid += 1;
        }
    }
    let accepted = source_verified
        && boot_ids.len() == 1
        && nonzero_id(boot)
        && invalid == 0
        && observations.len() == 1
        && observations[0]["normal_oneshot_completion"] == true;
    json!({"schema":"droidloom.fixture-gdm-greeter-evidence.v1",
        "proof_source_files_verified":source_verified,"observations":observations,
        "invalid_proof_unit_records":invalid,"dynamic_environment_writer_proven":accepted,
        "visible_greeter_proven":false,"desktop_proven":false,"production_ready":false})
}

#[cfg(test)]
mod tests {
    use super::*;

    fn observed() -> (Vec<Value>, BTreeSet<String>) {
        let boot = "1234567890abcdef1234567890abcdef";
        let invocation = "abcdef1234567890abcdef1234567890";
        let proof = json!({"schema":"droidloom.fixture-gdm-greeter-proof.v1","result":"passed",
            "uid":60578,"gid":121,"pid":789,"unit":UNIT,"invocation_id":invocation,
            "guest_clock":"CLOCK_MONOTONIC","guest_monotonic_ns_start":1000000000u64,
            "guest_monotonic_ns_end":1100000000u64,"requires_trusted_journal_identity":true,
            "file_bytes":150,"file_sha256":"a".repeat(64),"file_device":1,"file_inode":50,
            "file_owner_uid":60578,"file_owner_gid":65534,"file_mode":"0600",
            "private_directory_mode":"0700","checked_environment_fields":["USER","LOGNAME","HOME","GDM_SEAT_ID"],
            "source_body_emitted":false});
        (
            vec![
                json!({"MESSAGE":proof.to_string(),"_UID":"60578","_GID":"121",
            "_SYSTEMD_OWNER_UID":"60578","_PID":"789","_SYSTEMD_UNIT":"user@60578.service",
            "_SYSTEMD_USER_UNIT":UNIT,"_SYSTEMD_INVOCATION_ID":invocation,"_BOOT_ID":boot,
            "_EXE":"/usr/bin/python3.14","_TRANSPORT":"stdout","__MONOTONIC_TIMESTAMP":"1100001"}),
                json!({"_UID":"60578","_SYSTEMD_UNIT":"user@60578.service",
            "_EXE":"/usr/lib/systemd/systemd","_TRANSPORT":"journal","_BOOT_ID":boot,
            "USER_UNIT":UNIT,"USER_INVOCATION_ID":invocation,
            "MESSAGE_ID":"39f53479d3a045ac8e11786248231fbf","JOB_TYPE":"start","JOB_RESULT":"done"}),
            ],
            [boot.into()].into_iter().collect(),
        )
    }

    fn native_receipt(gid: u32, complete: bool) -> Value {
        let work = "/var/lib/droidloom-qualification/test";
        json!({
            "schema":if complete {"droidloom.complete-ubuntu-native-prepared.v1"} else {"droidloom.ubuntu-native-prepared.v1"},
            "work_directory":work,"root":format!("{work}/root"),"guest_qualified":false,"production_ready":false,
            "native_initialization":{
                "schema":if complete {"droidloom.complete-native-ubuntu-initialization.v1"} else {"droidloom.native-ubuntu-initialization.v1"},
                "root":format!("{work}/root"),"work":work,"source_stage":"installed",
                "native_initialization_complete":true,"guest_started":false,"guest_qualified":false,
                "host_passwords_keys_homes_imported":false,
                "accounts":{"groups":{"gdm":gid},"users":[{"name":"gdm","uid":981,"gid":gid}],
                    "normal_service_accounts_preserved":true}
            }
        })
    }

    #[test]
    fn prepared_normal_gdm_group_and_actual_group_file_are_both_required() {
        let work = Path::new("/var/lib/droidloom-qualification/test");
        let native = native_receipt(981, true);
        let binding = native_group_binding(&native, work).unwrap();
        assert!(validate_bound_group(b"root:x:0:\ngdm:x:981:\n", &binding).is_ok());
        for bytes in [
            b"root:x:0:\ngdm:x:121:\n".as_slice(),
            b"root:x:0:\ngdm:x:981:\nalias:x:981:\n".as_slice(),
            b"root:x:0:\ngdm:x:981:\ngdm:x:982:\n".as_slice(),
            b"root:x:0:\n".as_slice(),
        ] {
            assert!(validate_bound_group(bytes, &binding).is_err());
        }
        assert!(native_group_binding(&native_receipt(121, false), work).is_ok());
        assert!(native_group_binding(&native_receipt(981, false), work).is_err());
        assert!(native_group_binding(&native_receipt(0, true), work).is_err());
        assert!(native_group_binding(&native_receipt(1000, true), work).is_err());
        assert!(
            native_group_binding(&native, Path::new("/var/lib/droidloom-qualification/other"))
                .is_err()
        );
        let mut wrong = native.clone();
        wrong["native_initialization"]["accounts"]["users"][0]["gid"] = json!(121);
        assert!(native_group_binding(&wrong, work).is_err());
        let mut unprepared = native;
        unprepared["native_initialization"]["native_initialization_complete"] = json!(false);
        assert!(native_group_binding(&unprepared, work).is_err());
        validate_public_group(b"gdm:x:121:\n").unwrap();
        assert!(validate_public_group(b"gdm:x:981:\n").is_err());
    }

    #[test]
    fn journal_trusted_gid_and_payload_gid_must_match_bound_normal_group() {
        let (mut rows, boots) = observed();
        let binding = native_group_binding(
            &native_receipt(981, true),
            Path::new("/var/lib/droidloom-qualification/test"),
        )
        .unwrap();
        assert_eq!(
            journal_evidence_bound(&rows, &boots, true, &binding)["dynamic_environment_writer_proven"],
            false
        );
        rows[0]["_GID"] = json!("981");
        assert_eq!(
            journal_evidence_bound(&rows, &boots, true, &binding)["dynamic_environment_writer_proven"],
            false
        );
        let mut body: Value = serde_json::from_str(rows[0]["MESSAGE"].as_str().unwrap()).unwrap();
        body["gid"] = json!(981);
        rows[0]["MESSAGE"] = json!(body.to_string());
        assert_eq!(
            journal_evidence_bound(&rows, &boots, true, &binding)["dynamic_environment_writer_proven"],
            true
        );
        assert_eq!(
            journal_evidence_bound(&rows, &boots, false, &binding)["dynamic_environment_writer_proven"],
            false
        );
        assert_eq!(
            journal_evidence(&rows, &boots, true)["dynamic_environment_writer_proven"],
            false
        );
        rows[0]["_GID"] = json!("121");
        assert_eq!(
            journal_evidence_bound(&rows, &boots, true, &binding)["dynamic_environment_writer_proven"],
            false
        );
    }

    #[test]
    fn original_user_manager_identity_and_completion_are_both_required() {
        let (rows, boots) = observed();
        assert_eq!(
            journal_evidence(&rows, &boots, true)["dynamic_environment_writer_proven"],
            true
        );
        assert_eq!(
            journal_evidence(&rows, &boots, false)["dynamic_environment_writer_proven"],
            false
        );
        assert_eq!(
            journal_evidence(&rows[..1], &boots, true)["dynamic_environment_writer_proven"],
            false
        );
        for (index, key, wrong) in [
            (0, "_UID", "1000"),
            (0, "_GID", "1000"),
            (0, "_SYSTEMD_OWNER_UID", "1000"),
            (0, "_SYSTEMD_UNIT", "user@1000.service"),
            (0, "_SYSTEMD_INVOCATION_ID", "0"),
            (0, "_SYSTEMD_USER_UNIT", "other.service"),
            (0, "_BOOT_ID", "different"),
            (0, "_EXE", "/bin/echo"),
            (0, "_TRANSPORT", "journal"),
            (1, "_EXE", "/usr/bin/python3.14"),
            (1, "USER_INVOCATION_ID", "different"),
            (1, "JOB_RESULT", "failed"),
        ] {
            let mut changed = rows.clone();
            changed[index][key] = wrong.into();
            assert_eq!(
                journal_evidence(&changed, &boots, true)["dynamic_environment_writer_proven"],
                false,
                "accepted invalid {index}/{key}"
            );
        }
    }

    #[test]
    fn text_forgery_extra_payload_fields_and_multiple_boots_are_rejected() {
        let (rows, mut boots) = observed();
        for (key, value) in [
            ("uid", json!(1000)),
            ("file_owner_uid", json!(1000)),
            ("source_body_emitted", json!(true)),
            ("unreviewed", json!(true)),
        ] {
            let mut changed = rows.clone();
            let mut body: Value =
                serde_json::from_str(changed[0]["MESSAGE"].as_str().unwrap()).unwrap();
            body[key] = value;
            changed[0]["MESSAGE"] = body.to_string().into();
            assert_eq!(
                journal_evidence(&changed, &boots, true)["dynamic_environment_writer_proven"],
                false
            );
        }
        let mut changed = rows.clone();
        changed.push(json!({"_SYSTEMD_USER_UNIT":UNIT,"MESSAGE":"not a proof"}));
        assert_eq!(
            journal_evidence(&changed, &boots, true)["dynamic_environment_writer_proven"],
            false
        );
        boots.insert("11111111111111111111111111111111".into());
        assert_eq!(
            journal_evidence(&rows, &boots, true)["dynamic_environment_writer_proven"],
            false
        );
    }

    #[test]
    fn later_real_failure_cannot_be_hidden_by_prior_job_done() {
        let (mut rows, boots) = observed();
        let mut failed = rows[1].clone();
        failed["UNIT_RESULT"] = "timeout".into();
        rows.push(failed);
        assert_eq!(
            journal_evidence(&rows, &boots, true)["dynamic_environment_writer_proven"],
            false
        );
    }

    #[test]
    fn fixed_greeter_target_and_timed_login_never_enable_alex_proof() {
        let service = std::str::from_utf8(FILES[1].1).unwrap();
        let dropin = std::str::from_utf8(FILES[2].1).unwrap();
        assert!(service.contains("Requisite=gnome-session-initialized.target\n"));
        assert!(service.contains("PartOf=gnome-session@gnome-login.target\n"));
        assert!(service.contains("Type=oneshot\n") && service.contains("RemainAfterExit=yes\n"));
        assert!(
            !service.contains("User=")
                && !service.contains("ExecStart=-")
                && !service.contains("[Install]")
        );
        assert_eq!(
            dropin
                .lines()
                .filter(|line| line.starts_with("Wants="))
                .collect::<Vec<_>>(),
            ["Wants=droidloom-fixture-greeter-proof.service"]
        );
        let good = b"[daemon]\nAutomaticLoginEnable=false\nTimedLoginEnable=true\nTimedLogin=alex\nTimedLoginDelay=20\nWaylandEnable=true\n[security]\n[debug]\n";
        assert!(timed_config_valid(good));
        assert!(!timed_config_valid(
            &String::from_utf8_lossy(good)
                .replace("AutomaticLoginEnable=false", "AutomaticLoginEnable=true")
                .into_bytes()
        ));
        assert!(!timed_config_valid(
            &String::from_utf8_lossy(good)
                .replace("TimedLoginDelay=20", "TimedLoginDelay=0")
                .into_bytes()
        ));
    }

    #[test]
    #[ignore = "requires root, mke2fs/debugfs, and an explicit private qualification work path"]
    fn actual_greeter_proof_ext4_body_readback() -> Result<()> {
        use std::os::unix::fs::PermissionsExt;
        ensure(
            rustix::process::geteuid().as_raw() == 0,
            "actual proof image test requires root",
        )?;
        let work = std::path::PathBuf::from(
            std::env::var_os("DROIDLOOM_GDM_PROOF_IMAGE_WORK")
                .ok_or("actual proof image work absent")?,
        );
        ensure(
            work.parent() == Some(Path::new("/var/lib/droidloom-qualification")),
            "proof image test requires a private qualification root",
        )?;
        boot_files::private_dir(&work)?;
        let root = work.join("root");
        boot_files::private_dir(&root)?;
        let config = b"[daemon]\nAutomaticLoginEnable=false\nTimedLoginEnable=true\nTimedLogin=alex\nTimedLoginDelay=20\nWaylandEnable=true\n[security]\n[debug]\n";
        for (path, bytes, mode) in FILES
            .iter()
            .map(|(path, bytes)| (*path, *bytes, 0o444))
            .chain(std::iter::once((CONFIG, config.as_slice(), 0o644)))
        {
            let output = root.join(path.trim_start_matches('/'));
            std::fs::create_dir_all(output.parent().ok_or("missing fixed parent")?)?;
            boot_files::write_new(&output, bytes, mode)?;
        }
        let image = work.join("proof.ext4");
        let file = boot_files::new_file(&image, 0o600)?;
        file.set_len(32 * 1024 * 1024)?;
        file.sync_all()?;
        boot_files::run_logged(
            &work,
            "mkfs",
            "/usr/sbin/mke2fs",
            &[
                "-q".into(),
                "-F".into(),
                "-t".into(),
                "ext4".into(),
                "-d".into(),
                root.to_string_lossy().into(),
                image.to_string_lossy().into(),
            ],
            30,
        )?;
        let positive = verify_image(&root, &work, &image)?;
        ensure(
            positive["all_matched"] == true,
            "actual proof image positive did not pass",
        )?;
        let replacement = work.join("replacement");
        boot_files::write_new(&replacement, b"changed\n", 0o600)?;
        let commands = work.join("corrupt.commands");
        boot_files::write_new(
            &commands,
            format!(
                "rm {SCRIPT}\nwrite {} {SCRIPT}\n",
                crate::boot_runtime::debugfs_command_path(&fs::absolute_string(&replacement)?)?
            )
            .as_bytes(),
            0o600,
        )?;
        boot_files::run_logged(
            &work,
            "actual-corruption",
            "/usr/sbin/debugfs",
            &[
                "-w".into(),
                "-f".into(),
                commands.to_string_lossy().into(),
                image.to_string_lossy().into(),
            ],
            30,
        )?;
        let negative = work.join("negative");
        boot_files::private_dir(&negative)?;
        ensure(
            verify_image(&root, &negative, &image).is_err(),
            "actual corrupted proof image was accepted",
        )?;
        let script = root.join(SCRIPT.trim_start_matches('/'));
        std::fs::set_permissions(&script, std::fs::Permissions::from_mode(0o644))?;
        let bad_mode = work.join("wrong-source-mode");
        boot_files::private_dir(&bad_mode)?;
        ensure(
            verify_image(&root, &bad_mode, &image).is_err(),
            "writable proof source was accepted",
        )?;
        Ok(())
    }
}
