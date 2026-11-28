//! Pure wire-coherence models. None creates a Ready owner, a loop, a mount,
//! an executor receipt, or live custody; these are deliberately unit fixtures.
use super::*;
use crate::control::application_probe::InstalledApk;

fn file(device: u64, inode: u64, mode: u32, uid: u32, bytes: u64) -> CustodyFileIdentity {
    CustodyFileIdentity {
        device,
        inode,
        mode,
        uid,
        gid: uid,
        links: 1,
        bytes,
        modified: (1, 0),
        changed: (2, 0),
    }
}

fn read(argv: &[&str], stdout: &str, ordinal: u64) -> CustodyRead {
    let query = 1000 + 2 * ordinal;
    CustodyRead {
        argv: argv.iter().map(|word| (*word).into()).collect(),
        stdout: stdout.into(),
        receipt: serde_json::json!({
            "schema": 2,
            "lifecycle": {"owner":"legacy_broker","worker_pid":query+1,
                "worker_waitid_code":1,"worker_waitid_status":0},
            "query_pid": query, "query_waitid_code": 1, "query_waitid_status": 0,
            "output_bytes": stdout.len(), "output_sha256": format!("{:x}", Sha256::digest(stdout)),
            "elapsed_millis": 1, "cgroup_removed": true,
            "exec": {
                "query_start_ticks": 500 + ordinal, "original_parent_pid": 99, "tracer_tid": 99,
                "waitid_code": 4, "waitid_status": 1029, "event_previous_tid": query,
                "executable": {"dev": 1, "ino": 55, "mode": 33261, "uid": 100000,
                    "gid": 100000, "nlink": 1, "bytes": 128, "mtime": 1,
                    "mtime_nsec": 0, "ctime": 2, "ctime_nsec": 0},
                "executable_mount_id": 50, "executable_sha256": "b".repeat(64),
                "executable_selinux": "u:object_r:droidloom_query_exec:s0",
                "process_selinux": "u:r:droidloom_query:s0",
                "process_apparmor": "droidloom-production-android//&droidloom-production-broker (enforce)",
                "uid": 102000, "gid": 102000, "no_new_privileges": true, "seccomp_filter_mode": 2
            }
        }),
    }
}

fn model() -> ImageApplicationCustody {
    let cohort_sha = "a".repeat(64);
    let user = CustodyNamespace {
        name: "user".into(),
        device: 4,
        inode: 10,
    };
    let mut namespaces = ["mount", "pid", "ipc", "uts", "net", "cgroup"]
        .iter()
        .enumerate()
        .map(|(index, name)| CustodyNamespace {
            name: (*name).into(),
            device: 4,
            inode: 11 + index as u64,
        })
        .collect::<Vec<_>>();
    namespaces.push(user.clone());
    let image = |role: &str, device: u64, inode: u64, bytes: u64, sha: &str| CustodyImage {
        role: role.into(),
        path: format!("/var/lib/droidloom/cohorts/{cohort_sha}/images/{role}.img"),
        file: file(1, inode, 0o100644, 0, bytes),
        sha256: sha.into(),
        loop_node: file(2, inode + 50, 0o060660, 0, 0),
        loop_device: device,
        loop_number: inode as u32,
        loop_source_device: 1,
        loop_source_inode: inode,
        loop_offset: 0,
        loop_size_limit: 0,
        loop_flags: 5,
        mount_id: inode,
        mount_root: file(device, 2, 0o040755, 100000, 4096),
        mount_flags: 7,
        filesystem: "ext4".into(),
    };
    let path = GALLERY_PM_PATHS[1];
    let package_argv = [
        "/system/bin/cmd",
        "package",
        "list",
        "packages",
        "--user",
        "0",
        "-U",
        "--show-versioncode",
        GALLERY_PACKAGE,
    ];
    let path_argv = [
        "/system/bin/cmd",
        "package",
        "path",
        "--user",
        "0",
        GALLERY_PACKAGE,
    ];
    let stat_argv = ["/system/bin/toybox", "stat", "-c", "%d:%i:%s:%y:%z", path];
    let hash_argv = ["/system/bin/toybox", "sha256sum", path];
    let package_output = format!("package:{GALLERY_PACKAGE} uid:10064 versionCode:40030\n");
    let path_output = format!("package:{path}\n");
    let stat_output = format!(
        "259:123:{GALLERY_BYTES}:2026-11-20 00:00:00.0 +0000:2026-11-20 00:00:00.0 +0000\n"
    );
    let hash_output = format!("{GALLERY_SHA256}  {path}\n");
    let cohort = CustodyCohort {
        manifest_path: format!("/etc/droidloom/cohorts/{cohort_sha}.json"),
        manifest: file(1, 5, 0o100644, 0, 500),
        manifest_sha256: cohort_sha.clone(),
        host_uid: 1000,
        user_namespace: user,
        uid_range: (100000, 65536),
        gid_range: (100000, 65536),
        system: image("system", 259, 20, SYSTEM_BYTES, SYSTEM_SHA256),
        vendor: image("vendor", 260, 21, 4096, &"e".repeat(64)),
    };
    let original_apk = CustodyImageMember {
        path: GALLERY_SOURCE_PATH.into(),
        file: file(259, 123, 0o100644, 100000, GALLERY_BYTES),
        sha256: GALLERY_SHA256.into(),
        mount_id: 20,
    };
    ImageApplicationCustody {
        schema: "droidloom-image-application-custody-v1".into(),
        application: ApplicationInspection {
            package: GALLERY_PACKAGE.into(),
            user: 0,
            uid: 10064,
            version_code: 40030,
            epoch: RuntimeEpoch {
                boot_id: "00000000-0000-0000-0000-000000000001".into(),
                cell_host_pid: 321,
                framework_host_pid: 322,
                framework_start_ticks: 101,
            },
            apks: vec![InstalledApk {
                name: "base.apk".into(),
                path: path.into(),
                bytes: GALLERY_BYTES,
                sha256: GALLERY_SHA256.into(),
            }],
        },
        owner: CustodyOwner {
            host_uid: 1000,
            cell_host_pid: 321,
            cell_start_ticks: 100,
            selection_binding_sha256: "c".repeat(64),
            base_cohort_sha256: cohort_sha.clone(),
            runtime_manifest_sha256: "d".repeat(64),
            namespaces,
        },
        cohort: cohort.clone(),
        after_cohort: cohort,
        original_apk: original_apk.clone(),
        after_original_apk: original_apk,
        reads: vec![
            read(&package_argv, &package_output, 0),
            read(&path_argv, &path_output, 1),
            read(&stat_argv, &stat_output, 2),
            read(&hash_argv, &hash_output, 3),
            read(&stat_argv, &stat_output, 4),
            read(&package_argv, &package_output, 5),
            read(&path_argv, &path_output, 6),
        ],
        elapsed_millis: 100,
        data_continuity_qualified: false,
        runtime_qualified: false,
        business_qualified: false,
        production_ready: false,
    }
}

#[test]
fn complete_wire_model_is_coherent_without_granting_live_custody() {
    let value = model();
    value.validate(&value.application).unwrap();
    let roundtrip: ImageApplicationCustody =
        serde_json::from_value(serde_json::to_value(&value).unwrap()).unwrap();
    assert_eq!(value, roundtrip);
    assert!(!roundtrip.data_continuity_qualified && !roundtrip.production_ready);
}

#[test]
fn wire_observation_cannot_promote_data_or_release_gates() {
    for change in [
        (|v: &mut ImageApplicationCustody| v.data_continuity_qualified = true)
            as fn(&mut ImageApplicationCustody),
        |v| v.runtime_qualified = true,
        |v| v.business_qualified = true,
        |v| v.production_ready = true,
    ] {
        let mut value = model();
        change(&mut value);
        assert!(value.validate(&value.application).is_err());
    }
}

#[test]
fn whole_image_and_same_inode_are_required_even_with_matching_apk_hash() {
    for change in [
        (|v: &mut ImageApplicationCustody| v.cohort.system.sha256 = "f".repeat(64))
            as fn(&mut ImageApplicationCustody),
        |v| v.cohort.system.file.bytes -= 512,
        |v| v.cohort.system.loop_source_inode += 1,
        |v| v.cohort.system.loop_offset = 4096,
        |v| v.cohort.system.loop_flags = 1,
        |v| v.cohort.system.mount_flags = 6,
        |v| v.original_apk.file.inode += 1,
        |v| v.original_apk.mount_id += 1,
        |v| {
            v.cohort.vendor.file.inode = v.cohort.system.file.inode;
            v.cohort.vendor.loop_source_inode = v.cohort.vendor.file.inode;
        },
    ] {
        let mut value = model();
        change(&mut value);
        value.after_cohort = value.cohort.clone();
        value.after_original_apk = value.original_apk.clone();
        let error = value.validate(&value.application).unwrap_err();
        assert_ne!(
            error,
            "image custody scope, identity, or unqualified gates differ"
        );
    }
    // These specifically exercise the independent complete after-byte gate.
    for change in [
        (|v: &mut ImageApplicationCustody| v.after_cohort.system.sha256 = "f".repeat(64))
            as fn(&mut ImageApplicationCustody),
        |v| v.after_cohort.vendor.file.inode += 1,
        |v| v.after_original_apk.file.inode += 1,
    ] {
        let mut value = model();
        change(&mut value);
        assert_eq!(
            value.validate(&value.application).unwrap_err(),
            "image custody scope, identity, or unqualified gates differ"
        );
    }
    // Keep the whole official image and its member correct, but make the PM
    // installed byte observation and its complete transcript coherently wrong.
    let mut value = model();
    let wrong = "f".repeat(64);
    value.application.apks[0].sha256 = wrong.clone();
    let output = format!("{wrong}  {}\n", value.application.apks[0].path);
    let hash_read = &mut value.reads[3];
    hash_read.stdout = output;
    hash_read.receipt["output_bytes"] = (hash_read.stdout.len() as u64).into();
    hash_read.receipt["output_sha256"] =
        format!("{:x}", Sha256::digest(hash_read.stdout.as_bytes())).into();
    let mut transcript = Transcript {
        epoch: &value.application.epoch,
        reads: &value.reads,
        cursor: 0,
    };
    let parsed =
        crate::control::application_probe::inspect(&mut transcript, GALLERY_PACKAGE, 0).unwrap();
    assert_eq!(parsed, value.application);
    assert_eq!(transcript.cursor, 7);
    assert_eq!(value.cohort.system.sha256, SYSTEM_SHA256);
    assert_eq!(value.original_apk.sha256, GALLERY_SHA256);
    assert_eq!(
        value.validate(&value.application).unwrap_err(),
        "image custody APK is not the exact original CP3A Gallery"
    );
}

#[test]
fn current_owner_and_all_original_namespaces_are_bound() {
    for change in [
        (|v: &mut ImageApplicationCustody| v.owner.cell_host_pid += 1)
            as fn(&mut ImageApplicationCustody),
        |v| v.owner.host_uid += 1,
        |v| v.owner.base_cohort_sha256 = "f".repeat(64),
        |v| {
            v.owner.namespaces.pop();
        },
        |v| v.cohort.user_namespace.inode += 1,
    ] {
        let mut value = model();
        change(&mut value);
        value.after_cohort = value.cohort.clone();
        value.after_original_apk = value.original_apk.clone();
        let error = value.validate(&value.application).unwrap_err();
        assert_ne!(
            error,
            "image custody scope, identity, or unqualified gates differ"
        );
    }
}

#[test]
fn missing_reordered_or_unreaped_commands_do_not_replay_as_observations() {
    for change in [
        (|v: &mut ImageApplicationCustody| {
            v.reads.pop();
        }) as fn(&mut ImageApplicationCustody),
        |v| v.reads.swap(0, 1),
        |v| v.reads[3].receipt["query_waitid_status"] = 1.into(),
        |v| v.reads[3].receipt["cgroup_removed"] = false.into(),
        |v| v.reads[3].stdout.push('x'),
        |v| v.reads[3].receipt["exec"] = serde_json::json!({}),
        |v| v.reads[3].receipt["exec"]["event_previous_tid"] = 1.into(),
        |v| v.reads[3].receipt["exec"]["uid"] = 0.into(),
        |v| v.reads[3].receipt["claimed_success"] = true.into(),
    ] {
        let mut value = model();
        change(&mut value);
        assert!(value.validate(&value.application).is_err());
    }
}

#[test]
fn custody_wire_rejects_an_added_authority_field() {
    let mut raw = serde_json::to_value(model()).unwrap();
    raw["reuse_pid_as_authority"] = 321.into();
    assert!(serde_json::from_value::<ImageApplicationCustody>(raw).is_err());
}

#[test]
fn optional_response_preserves_legacy_wire_but_request_cannot_import_custody() {
    let legacy: crate::control::ControlResponse = serde_json::from_value(serde_json::json!({
        "ok": true, "state": "running", "message": "metadata only"
    }))
    .unwrap();
    assert!(legacy.image_custody.is_none());
    assert!(
        serde_json::from_value::<crate::control::ControlRequest>(serde_json::json!({
            "command": "inspect_application", "package": GALLERY_PACKAGE, "user": 0,
            "image_custody": model()
        }))
        .is_err()
    );
}

fn factory_model() -> ImageApplicationCustody {
    let mut value = model();
    for read in &mut value.reads {
        let query = read.receipt["query_pid"].as_u64().unwrap();
        read.receipt["lifecycle"] = serde_json::json!({
            "owner":"instance_factory","factory_pid":99,"factory_tid":99,
            "factory_pidfd_device":7,"factory_pidfd_inode":100,
            "query_pidfd_device":7,"query_pidfd_inode":query+100,
            "stdio_creator":{"pid":query+1,"waitid_code":1,"waitid_status":0},
            "release_acknowledged":true
        });
        read.receipt["exec"]["process_apparmor"] = "droidloom-production-android (enforce)".into();
    }
    value
}
#[test]
fn factory_wire_keeps_query_wait_owner_separate_from_stdio_creator() {
    let value = factory_model();
    value.validate(&value.application).unwrap();
    assert!(!value.production_ready);
    for change in [
        (|r: &mut serde_json::Value| r["lifecycle"]["factory_tid"] = 100.into())
            as fn(&mut serde_json::Value),
        |r| r["exec"]["original_parent_pid"] = 100.into(),
        |r| r["exec"]["tracer_tid"] = 100.into(),
        |r| r["lifecycle"]["stdio_creator"]["pid"] = r["query_pid"].clone(),
        |r| r["lifecycle"]["stdio_creator"]["waitid_code"] = 2.into(),
        |r| r["lifecycle"]["stdio_creator"]["waitid_status"] = 9.into(),
        |r| r["lifecycle"]["release_acknowledged"] = false.into(),
        |r| r["lifecycle"]["query_pidfd_inode"] = r["lifecycle"]["factory_pidfd_inode"].clone(),
        |r| r["lifecycle"]["worker_pid"] = 999.into(),
        |r| {
            r["exec"]["process_apparmor"] =
                "droidloom-production-android//&droidloom-production-broker (enforce)".into()
        },
    ] {
        let mut value = factory_model();
        change(&mut value.reads[0].receipt);
        assert!(value.validate(&value.application).is_err());
    }
}
#[test]
fn legacy_join_worker_cannot_be_relabelled_as_factory_evidence() {
    let mut value = model();
    value.reads[0].receipt["lifecycle"]["owner"] = "instance_factory".into();
    assert!(value.validate(&value.application).is_err());
}
