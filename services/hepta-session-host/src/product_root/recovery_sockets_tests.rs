//! Actual privileged filesystem/socket boundary; not a source owner or grant.
use super::*;
use std::os::unix::fs::PermissionsExt;
use std::os::unix::net::UnixListener;

#[test]
#[ignore = "actual Root path-custody qualification"]
fn live_foreign_or_rebound_socket_is_not_removed_but_exact_stale_socket_retires() {
    assert_eq!(unsafe { libc::geteuid() }, 0);
    let root = std::path::PathBuf::from(format!(
        "/run/trill-recovery-socket-test-{}",
        std::process::id()
    ));
    std::fs::create_dir(&root).unwrap();
    std::fs::set_permissions(&root, std::fs::Permissions::from_mode(0o700)).unwrap();
    let path = root.join("owner.sock");
    let live = UnixListener::bind(&path).unwrap();
    std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o600)).unwrap();
    let gid = unsafe { libc::getgid() };
    let before = std::fs::symlink_metadata(&path).unwrap();
    assert!(stale(&path, 0, gid, 0o600).is_err());
    assert_eq!(
        std::fs::symlink_metadata(&path).unwrap().ino(),
        before.ino()
    );
    drop(live);
    assert!(stale(&path, 60001, gid, 0o600).is_err());
    assert!(path.exists());
    stale(&path, 0, gid, 0o600).unwrap();
    assert!(!path.exists());
    std::fs::write(&path, b"unrelated file").unwrap();
    assert!(stale(&path, 0, gid, 0o600).is_err());
    assert_eq!(std::fs::read(&path).unwrap(), b"unrelated file");
    std::fs::remove_file(&path).unwrap();
    std::fs::remove_dir(root).unwrap();
}
