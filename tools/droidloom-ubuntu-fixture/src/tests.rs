use crate::{capture, fs, materialize, model::*, paths};
use std::fs as stdfs;
use std::os::unix::fs::{PermissionsExt, symlink};
use tempfile::TempDir;

fn owner() -> u32 {
    rustix::process::geteuid().as_raw()
}
fn chmod(p: impl AsRef<std::path::Path>, mode: u32) {
    stdfs::set_permissions(p, stdfs::Permissions::from_mode(mode)).unwrap();
}
fn fixture() -> (TempDir, Selection) {
    let dir = tempfile::tempdir().unwrap();
    stdfs::create_dir_all(dir.path().join("source/usr/bin")).unwrap();
    chmod(dir.path().join("source"), 0o755);
    chmod(dir.path().join("source/usr"), 0o755);
    chmod(dir.path().join("source/usr/bin"), 0o755);
    stdfs::write(
        dir.path().join("source/usr/bin/tool"),
        b"synthetic-test-input\n",
    )
    .unwrap();
    chmod(dir.path().join("source/usr/bin/tool"), 0o755);
    let selection = Selection {
        schema: SELECTION_SCHEMA.into(),
        source_root: dir.path().join("source").to_str().unwrap().into(),
        audit_sha256: "a".repeat(64),
        target_kernel_release: "6.18.64-fixture-test".into(),
        kernel: None,
        entries: vec![SelectedPath {
            path: "/usr/bin/tool".into(),
            component: Component::Native,
            origin: "synthetic-tests-only".into(),
            expected_sha256: None,
            expected_size: None,
        }],
        unresolved_requirements: vec![],
    };
    (dir, selection)
}
fn cap(s: Selection) -> Manifest {
    capture::capture(s, &"b".repeat(64), owner()).unwrap()
}
fn path(d: &TempDir, name: &str) -> String {
    d.path().join(name).to_str().unwrap().into()
}

#[test]
fn copies_native_bytes_modes_and_reports_unqualified() {
    let (d, s) = fixture();
    let m = cap(s);
    let r = materialize::materialize(&m, &"c".repeat(64), &path(&d, "out"), owner()).unwrap();
    assert!(r.materialization_complete);
    assert!(!r.guest_qualified);
    assert!(!r.kernel_modules_content_verified);
    assert_eq!(
        stdfs::read(d.path().join("out/usr/bin/tool")).unwrap(),
        b"synthetic-test-input\n"
    );
    assert_eq!(
        stdfs::metadata(d.path().join("out/usr/bin/tool"))
            .unwrap()
            .permissions()
            .mode()
            & 0o7777,
        0o755
    );
    assert!(
        r.unresolved_requirements
            .iter()
            .any(|x| x.contains("SSH host keys"))
    );
}

#[test]
fn refuses_existing_destination_without_modifying_it() {
    let (d, s) = fixture();
    let m = cap(s);
    stdfs::create_dir(d.path().join("out")).unwrap();
    stdfs::write(d.path().join("out/keep"), b"keep").unwrap();
    assert!(materialize::materialize(&m, &"c".repeat(64), &path(&d, "out"), owner()).is_err());
    assert_eq!(stdfs::read(d.path().join("out/keep")).unwrap(), b"keep");
}

#[test]
fn private_sources_and_wrong_kernel_are_rejected_before_read() {
    for name in [
        "/home/u/key",
        "/etc/shadow",
        "/etc/gshadow",
        "/etc/ssh/ssh_host_ed25519_key",
        "/etc/ssl/private/server.key",
        "/etc/NetworkManager/system-connections/a",
        "/var/lib/bluetooth/a",
        "/var/lib/snapd/state.json",
        "/data/a",
        "/usr/lib/modules/7.0/bad.ko",
    ] {
        let (_d, mut s) = fixture();
        s.entries[0].path = name.into();
        assert!(
            capture::capture(s, &"b".repeat(64), owner()).is_err(),
            "{name}"
        );
    }
    assert!(
        paths::validate(
            "/usr/lib/modules/7.0",
            &Component::AncestorDirectory,
            "6.18.test"
        )
        .is_err()
    );
}

#[test]
fn private_and_escaping_symlinks_are_rejected() {
    for target in ["/etc/shadow", "/home/u/private", "../../../../outside"] {
        let (d, mut s) = fixture();
        symlink(target, d.path().join("source/usr/bin/link")).unwrap();
        s.entries.push(SelectedPath {
            path: "/usr/bin/link".into(),
            component: Component::Native,
            origin: "test".into(),
            expected_sha256: None,
            expected_size: None,
        });
        assert!(capture::capture(s, &"b".repeat(64), owner()).is_err());
    }
}

#[test]
fn no_follow_rejects_source_ancestor_symlink() {
    let (d, mut s) = fixture();
    symlink("bin", d.path().join("source/usr/alias")).unwrap();
    s.entries[0].path = "/usr/alias/tool".into();
    assert!(capture::capture(s, &"b".repeat(64), owner()).is_err());
}

#[test]
fn no_follow_rejects_destination_ancestor_symlink() {
    let (d, s) = fixture();
    let m = cap(s);
    symlink(d.path(), d.path().join("alias")).unwrap();
    let target = d.path().join("alias/out").to_str().unwrap().to_owned();
    assert!(materialize::materialize(&m, &"c".repeat(64), &target, owner()).is_err());
    assert!(!d.path().join("out").exists());
}

#[test]
fn rejects_group_writable_source_and_parent() {
    let (d, s) = fixture();
    chmod(d.path().join("source/usr/bin/tool"), 0o775);
    assert!(capture::capture(s, &"b".repeat(64), owner()).is_err());
    let (d, s) = fixture();
    chmod(d.path().join("source/usr/bin"), 0o775);
    assert!(capture::capture(s, &"b".repeat(64), owner()).is_err());
}

#[test]
fn content_change_after_capture_prevents_destination_creation() {
    let (d, s) = fixture();
    let m = cap(s);
    stdfs::write(d.path().join("source/usr/bin/tool"), b"changed").unwrap();
    assert!(materialize::materialize(&m, &"c".repeat(64), &path(&d, "out"), owner()).is_err());
    assert!(!d.path().join("out").exists());
}

#[test]
fn same_bytes_replacement_has_a_different_source_identity() {
    let (d, s) = fixture();
    let m = cap(s);
    stdfs::rename(d.path().join("source/usr/bin/tool"), d.path().join("old")).unwrap();
    stdfs::write(
        d.path().join("source/usr/bin/tool"),
        b"synthetic-test-input\n",
    )
    .unwrap();
    chmod(d.path().join("source/usr/bin/tool"), 0o755);
    assert!(materialize::materialize(&m, &"c".repeat(64), &path(&d, "out"), owner()).is_err());
}

#[test]
fn hardlinks_and_public_usrmerge_links_are_preserved() {
    let (d, mut s) = fixture();
    stdfs::hard_link(
        d.path().join("source/usr/bin/tool"),
        d.path().join("source/usr/bin/alias-tool"),
    )
    .unwrap();
    symlink("usr/bin", d.path().join("source/bin")).unwrap();
    for name in ["/usr/bin/alias-tool", "/bin"] {
        s.entries.push(SelectedPath {
            path: name.into(),
            component: Component::Native,
            origin: "test".into(),
            expected_sha256: None,
            expected_size: None,
        });
    }
    let m = cap(s);
    materialize::materialize(&m, &"c".repeat(64), &path(&d, "out"), owner()).unwrap();
    let t = fs::Tree::open(&path(&d, "out"), owner()).unwrap();
    assert_eq!(
        t.identity("/usr/bin/tool").unwrap().ino,
        t.identity("/usr/bin/alias-tool").unwrap().ino
    );
    assert_eq!(
        stdfs::read_link(d.path().join("out/bin"))
            .unwrap()
            .to_str()
            .unwrap(),
        "usr/bin"
    );
}

#[test]
fn full_readback_rejects_modified_content_or_extra_files() {
    let (d, s) = fixture();
    let m = cap(s);
    materialize::materialize(&m, &"c".repeat(64), &path(&d, "out"), owner()).unwrap();
    stdfs::write(d.path().join("out/usr/bin/tool"), b"modified").unwrap();
    assert!(materialize::verify(&m, &"c".repeat(64), &path(&d, "out"), owner()).is_err());
    let (d, s) = fixture();
    let m = cap(s);
    materialize::materialize(&m, &"c".repeat(64), &path(&d, "out"), owner()).unwrap();
    stdfs::write(d.path().join("out/extra"), b"extra").unwrap();
    assert!(materialize::verify(&m, &"c".repeat(64), &path(&d, "out"), owner()).is_err());
}

#[test]
fn json_digest_is_bound_to_the_same_decoded_buffer() {
    let d = tempfile::tempdir().unwrap();
    let p = path(&d, "input.json");
    stdfs::write(&p, b"{\"ok\":true}").unwrap();
    assert!(fs::read_json::<serde_json::Value>(&p, &"0".repeat(64)).is_err());
    let v = fs::read_json::<serde_json::Value>(&p, &fs::digest(b"{\"ok\":true}")).unwrap();
    assert_eq!(v["ok"], true);
}

#[test]
fn configured_public_file_requires_reviewed_digest() {
    let (d, mut s) = fixture();
    stdfs::create_dir(d.path().join("source/etc")).unwrap();
    stdfs::write(
        d.path().join("source/etc/nsswitch.conf"),
        b"passwd: files\n",
    )
    .unwrap();
    s.entries.push(SelectedPath {
        path: "/etc/nsswitch.conf".into(),
        component: Component::PublicConfig,
        origin: "test".into(),
        expected_sha256: None,
        expected_size: None,
    });
    assert!(capture::capture(s.clone(), &"b".repeat(64), owner()).is_err());
    s.entries.last_mut().unwrap().expected_sha256 = Some(fs::digest(b"passwd: files\n"));
    assert!(capture::capture(s, &"b".repeat(64), owner()).is_ok());
}

#[test]
fn rejects_forged_qualification_or_ancestor_file() {
    let (_d, s) = fixture();
    let mut m = cap(s);
    m.guest_qualified = true;
    assert!(materialize::validate(&m).is_err());
    m.guest_qualified = false;
    m.entries
        .iter_mut()
        .find(|x| x.path == "/usr/bin/tool")
        .unwrap()
        .component = Component::AncestorDirectory;
    assert!(materialize::validate(&m).is_err());
}

#[test]
fn rejects_duplicate_paths_and_parent_traversal() {
    let (_d, mut s) = fixture();
    let mut duplicate = s.entries[0].clone();
    duplicate.expected_sha256 = Some("0".repeat(64));
    s.entries.push(duplicate);
    assert!(capture::capture(s, &"b".repeat(64), owner()).is_err());
    for p in [
        "usr/bin/a",
        "/usr/../etc/shadow",
        "/usr//bin/a",
        "/usr/./bin/a",
    ] {
        assert!(paths::parts(p).is_err());
    }
}

#[test]
fn artifact_is_create_only_and_exactly_read_back() {
    let d = tempfile::tempdir().unwrap();
    let p = path(&d, "receipt.json");
    let v = serde_json::json!({"materialization_complete":false});
    let sha = fs::write_json(&p, &v, owner()).unwrap();
    assert_eq!(fs::read_json::<serde_json::Value>(&p, &sha).unwrap(), v);
    assert!(fs::write_json(&p, &v, owner()).is_err());
}
