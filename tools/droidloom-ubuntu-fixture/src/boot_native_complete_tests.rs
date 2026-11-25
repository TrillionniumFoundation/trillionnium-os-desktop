use super::*;
use std::os::unix::fs::{PermissionsExt, symlink};

fn baseline() -> [Vec<u8>; 4] {
    let passwd = "root:x:0:0:root:/root:/bin/bash\ngdm:x:981:981:Gnome Display Manager:/var/lib/gdm3:/bin/false\nnobody:x:65534:65534:nobody:/nonexistent:/usr/sbin/nologin\n";
    let group = "root:x:0:\ngdm:x:981:\nnogroup:x:65534:\naudio:x:29:gdm\nvideo:x:44:\nrender:x:989:\ninput:x:993:\nnetdev:x:103:\n";
    let shadow =
        "root:!:20000:0:99999:7:::\ngdm:!*:20000:0:99999:7:::\nnobody:*:20000:0:99999:7:::\n";
    let gshadow = group
        .lines()
        .map(|line| {
            let c: Vec<_> = line.split(':').collect();
            format!("{}:!::{}\n", c[0], c[3])
        })
        .collect::<String>();
    [
        passwd.as_bytes().to_vec(),
        group.as_bytes().to_vec(),
        shadow.as_bytes().to_vec(),
        gshadow.into_bytes(),
    ]
}

fn initialized(contents: &[Vec<u8>; 4]) -> [Vec<u8>; 4] {
    let mut result = contents.clone();
    result[0].extend_from_slice(b"alex:x:1000:1000:Pocket4 qualification user:/home/alex:/bin/bash\ndroidloom-cell-u1000:x:976:976:Droidloom Android cell for host UID 1000:/nonexistent:/usr/sbin/nologin\n");
    result[2].extend_from_slice(
        b"alex:!*:20000:0:99999:7:::\ndroidloom-cell-u1000:!*:20000:0:99999:7:::\n",
    );
    for index in [1, 3] {
        let mut text = String::new();
        for line in std::str::from_utf8(&contents[index]).unwrap().lines() {
            let mut cols: Vec<_> = line.split(':').map(str::to_owned).collect();
            if MEMBERSHIPS.contains(&cols[0].as_str()) {
                if !cols[3].is_empty() {
                    cols[3].push(',');
                }
                cols[3].push_str("alex");
            }
            text.push_str(&cols.join(":"));
            text.push('\n');
        }
        text.push_str(if index == 1 {
            "alex:x:1000:\ndroidloom-cell-u1000:x:976:\n"
        } else {
            "alex:!::\ndroidloom-cell-u1000:!::\n"
        });
        result[index] = text.into_bytes();
    }
    result
}

#[test]
fn complete_native_preserves_service_ids_rows_and_memberships() {
    let initial = baseline();
    let before = accounts_before(&initial).unwrap();
    let after = initialized(&initial);
    let summary = accounts_after(&before, &after).unwrap();
    assert_eq!(summary["groups"]["gdm"], 981);
    assert_eq!(summary["groups"]["render"], 989);
    assert_eq!(summary["groups"]["input"], 993);
    assert_eq!(summary["cell_home"], "/nonexistent");
    assert_eq!(summary["normal_service_accounts_preserved"], true);
    let lines = sysusers_lines();
    assert_eq!(lines.iter().filter(|s| s.starts_with("u ")).count(), 2);
    assert!(
        !lines
            .iter()
            .any(|s| s.starts_with("u gdm") || s.starts_with("g gdm"))
    );
    let mut altered = after.clone();
    altered[0] = String::from_utf8(altered[0].clone())
        .unwrap()
        .replace("gdm:x:981:981", "gdm:x:121:981")
        .into_bytes();
    assert!(accounts_after(&before, &altered).is_err());
    let mut lost_member = after;
    lost_member[1] = String::from_utf8(lost_member[1].clone())
        .unwrap()
        .replace("audio:x:29:gdm,alex", "audio:x:29:alex")
        .into_bytes();
    assert!(accounts_after(&before, &lost_member).is_err());
}

#[test]
fn complete_native_rejects_unlocked_existing_user_and_uid_gid_collision() {
    for change in 0..5 {
        let mut c = baseline();
        match change {
            0 => c[2].clear(),
            1 => {
                c[2] = String::from_utf8(c[2].clone())
                    .unwrap()
                    .replace("root:!:", "root:$6$hash:")
                    .into_bytes()
            }
            2 => {
                c[0].extend_from_slice(b"prior:x:1000:0:prior:/home/prior:/bin/bash\n");
                c[2].extend_from_slice(b"prior:!:20000:0:99999:7:::\n");
            }
            3 => {
                c[0].extend_from_slice(b"collision:x:976:0:service:/nonexistent:/bin/false\n");
                c[2].extend_from_slice(b"collision:!:20000:0:99999:7:::\n");
            }
            _ => {
                c[1].extend_from_slice(b"collision:x:976:\n");
                c[3].extend_from_slice(b"collision:!::\n");
            }
        }
        assert!(accounts_before(&c).is_err(), "case {change}");
    }
    let mut missing = baseline();
    missing[1] = String::from_utf8(missing[1].clone())
        .unwrap()
        .replace("render:x:989:\n", "")
        .into_bytes();
    missing[3] = String::from_utf8(missing[3].clone())
        .unwrap()
        .replace("render:!::\n", "")
        .into_bytes();
    assert!(accounts_before(&missing).is_err());
}

fn entry(path: &str, file: &Path) -> CompleteEntry {
    let f = File::open(file).unwrap();
    let mut source = fs::stat(&f).unwrap();
    // A copied root has independent inode custody. This tests that boundary,
    // without requiring or inventing a production CompleteManifest authority.
    source.ino += 1;
    CompleteEntry {
        path: path.into(),
        source,
        content: Content::Regular {
            sha256: fs::hash(&f).unwrap(),
        },
        xattrs: BTreeMap::new(),
    }
}

#[test]
fn complete_native_exact_preimage_and_replacement_scope() {
    let d = tempfile::tempdir().unwrap();
    let root = d.path().join("root");
    std::fs::create_dir(&root).unwrap();
    std::fs::create_dir(root.join("etc")).unwrap();
    std::fs::write(root.join("etc/hostname"), b"baseline\n").unwrap();
    std::fs::set_permissions(
        root.join("etc/hostname"),
        std::fs::Permissions::from_mode(0o644),
    )
    .unwrap();
    let snapshot = Snapshot::test_open(&root).unwrap();
    let e = entry("/etc/hostname", &root.join("etc/hostname"));
    let p = verify_file(&snapshot, &e).unwrap();
    assert!(unchanged(&snapshot, &p).is_ok());
    let mut wrong = e.clone();
    wrong.content = Content::Regular {
        sha256: "0".repeat(64),
    };
    assert!(verify_file(&snapshot, &wrong).is_err());
    let mut same_inode = e.clone();
    same_inode.source.ino -= 1;
    assert!(verify_file(&snapshot, &same_inode).is_err());
    std::fs::write(root.join("etc/hostname"), b"tampered\n").unwrap();
    assert!(unchanged(&snapshot, &p).is_err());
    for p in [
        "/etc/passwd",
        "/etc/group",
        "/etc/shadow",
        "/etc/gshadow",
        "/var/lib/dpkg/status",
        "/home/old/.ssh/id_ed25519",
        "/usr/bin/systemd",
    ] {
        assert!(!replaceable(p), "{p}");
    }
    for p in REPLACEMENTS.iter().chain(HOST_KEYS) {
        assert!(replaceable(p));
    }
}

#[test]
fn complete_native_rejects_old_home_state_and_parent_symlink() {
    let d = tempfile::tempdir().unwrap();
    std::fs::create_dir(d.path().join("home")).unwrap();
    let tree = Snapshot::test_open(d.path()).unwrap();
    assert!(empty_if_present(&tree, "/home").is_ok());
    std::fs::create_dir(d.path().join("home/alex")).unwrap();
    assert!(empty_if_present(&tree, "/home").is_err());
    symlink("/tmp", d.path().join("root")).unwrap();
    assert!(empty_if_present(&tree, "/root/.ssh").is_err());
    assert!(absent(&tree, "/root/.ssh/id_ed25519").is_err());
}

#[test]
fn complete_native_snap_roster_and_readonly_units_are_exact() {
    let d = tempfile::tempdir().unwrap();
    let f = d.path().join("public.snap");
    std::fs::write(&f, b"public snap fixture").unwrap();
    std::fs::set_permissions(&f, std::fs::Permissions::from_mode(0o644)).unwrap();
    let mut entries: Vec<_> = SNAP_NAMES
        .iter()
        .map(|name| {
            let mut e = entry(&format!("/var/lib/snapd/snaps/{name}_1.snap"), &f);
            e.source.uid = 0;
            e.source.gid = 0;
            e
        })
        .collect();
    let map: BTreeMap<_, _> = entries.iter().map(|e| (e.path.as_str(), e)).collect();
    let specs = snap_specs(&map).unwrap();
    assert_eq!(specs.len(), 7);
    for (s, bytes) in specs {
        let text = String::from_utf8(bytes).unwrap();
        assert!(text.contains("Options=nodev,ro,x-gdu.hide,x-gvfs-hide"));
        assert!(text.contains(&format!("What={}", s.image)));
    }
    entries.pop();
    let map = entries.iter().map(|e| (e.path.as_str(), e)).collect();
    assert!(snap_specs(&map).is_err());
    entries.push(entry("/var/lib/snapd/snaps/unknown_2.snap", &f));
    let map = entries.iter().map(|e| (e.path.as_str(), e)).collect();
    assert!(snap_specs(&map).is_err());
}

#[test]
fn complete_native_input_uuid_boundary_is_strict() {
    let mut inputs = CompleteNativeInputs {
        hostname: "pocket4-complete".into(),
        root_filesystem_uuid: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee".into(),
        network_connection_uuid: "11111111-2222-3333-4444-555555555555".into(),
        generate_fixture_ssh: true,
    };
    validate_inputs(&inputs).unwrap();
    inputs.network_connection_uuid = inputs.root_filesystem_uuid.clone();
    assert!(validate_inputs(&inputs).is_err());
    inputs.hostname = "../../physical-root".into();
    assert!(validate_inputs(&inputs).is_err());
}

#[test]
fn complete_native_retirement_preserves_verified_original_and_refuses_reuse() {
    let d = tempfile::tempdir().unwrap();
    let root = d.path().join("root");
    let archive_path = d.path().join("preimages");
    std::fs::create_dir(&root).unwrap();
    std::fs::create_dir(root.join("etc")).unwrap();
    std::fs::create_dir(&archive_path).unwrap();
    let path = root.join("etc/hostname");
    std::fs::write(&path, b"original clone identity\n").unwrap();
    std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o644)).unwrap();
    let snapshot = Snapshot::test_open(&root).unwrap();
    let preimage = verify_file(&snapshot, &entry("/etc/hostname", &path)).unwrap();
    let archive = fs::Tree::open(
        archive_path.to_str().unwrap(),
        rustix::process::geteuid().as_raw(),
    )
    .unwrap();
    let mut actions = Vec::new();
    let saved = retire(&snapshot, &archive, &preimage, &mut actions).unwrap();
    assert!(!path.exists());
    assert_eq!(
        std::fs::read(archive_path.join(saved)).unwrap(),
        b"original clone identity\n"
    );
    assert_eq!(actions.len(), 1);
    std::fs::write(&path, b"new identity\n").unwrap();
    assert!(retire(&snapshot, &archive, &preimage, &mut actions).is_err());
    assert_eq!(std::fs::read(&path).unwrap(), b"new identity\n");
}

/// Run explicitly with existing sudo rights. A normal unprivileged unit run
/// reports this as ignored, never as a successful native-command execution.
#[test]
#[ignore = "requires root; run this test explicitly against a new temporary root"]
fn complete_native_real_sysusers_firstboot_and_preimage_replacement() {
    assert_eq!(
        rustix::process::geteuid().as_raw(),
        0,
        "existing root rights required"
    );
    let d = tempfile::tempdir().unwrap();
    let root = d.path().join("root");
    std::fs::create_dir(&root).unwrap();
    for path in ["etc", "usr", "usr/bin", "preimages"] {
        std::fs::create_dir_all(root.join(path)).unwrap();
    }
    let initial = baseline();
    for (path, bytes) in ACCOUNT_FILES.iter().zip(&initial) {
        std::fs::write(root.join(path.trim_start_matches('/')), bytes).unwrap();
    }
    for program in ["systemd-sysusers", "systemd-firstboot"] {
        std::fs::copy(
            format!("/usr/bin/{program}"),
            root.join(format!("usr/bin/{program}")),
        )
        .unwrap();
    }
    let tree = fs::Tree::open(root.to_str().unwrap(), 0).unwrap();
    let snapshot = Snapshot::test_open(&root).unwrap();
    let before = accounts_before(&initial).unwrap();
    let mut args = vec![format!("--root={}", root.display()), "--inline".into()];
    args.extend(sysusers_lines());
    let mut commands = Vec::new();
    run_native(
        &root,
        d.path(),
        &tree,
        "test-sysusers",
        "/usr/bin/systemd-sysusers",
        &args,
        &mut commands,
    )
    .unwrap();
    let actual = accounts_after(&before, &account_contents(&snapshot).unwrap()).unwrap();
    assert_eq!(actual["groups"]["gdm"], 981);
    assert_eq!(actual["groups"]["alex"], 1000);
    let old = b"ca24b4d172cc4b5991a1a7be0de6e6b2\n";
    std::fs::write(root.join("etc/machine-id"), old).unwrap();
    std::fs::write(root.join("etc/hostname"), b"baseline\n").unwrap();
    let machine = verify_file(
        &snapshot,
        &entry("/etc/machine-id", &root.join("etc/machine-id")),
    )
    .unwrap();
    let hostname = verify_file(
        &snapshot,
        &entry("/etc/hostname", &root.join("etc/hostname")),
    )
    .unwrap();
    let archive = fs::Tree::open(root.join("preimages").to_str().unwrap(), 0).unwrap();
    let mut actions = Vec::new();
    retire(&snapshot, &archive, &machine, &mut actions).unwrap();
    run_native(
        &root,
        d.path(),
        &tree,
        "test-firstboot",
        "/usr/bin/systemd-firstboot",
        &[
            format!("--root={}", root.display()),
            "--setup-machine-id".into(),
            "--welcome=no".into(),
        ],
        &mut commands,
    )
    .unwrap();
    let fresh = snapshot.bytes("/etc/machine-id", 128).unwrap();
    assert_eq!(fresh.len(), 33);
    assert_ne!(fresh, old);
    replace(
        &root,
        &snapshot,
        &archive,
        &hostname,
        b"fresh-complete\n",
        0o644,
        &mut actions,
    )
    .unwrap();
    assert_eq!(
        snapshot.bytes("/etc/hostname", 128).unwrap(),
        b"fresh-complete\n"
    );
    assert_eq!(commands.len(), 2);
    assert!(
        replace(
            &root,
            &snapshot,
            &archive,
            &hostname,
            b"again\n",
            0o644,
            &mut actions
        )
        .is_err()
    );
    assert_eq!(
        snapshot.bytes("/etc/hostname", 128).unwrap(),
        b"fresh-complete\n"
    );
}
