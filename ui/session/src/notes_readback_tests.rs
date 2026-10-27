use super::*;
use std::os::unix::fs::{DirBuilderExt, PermissionsExt};

struct Directory(PathBuf);

impl Directory {
    fn new() -> Self {
        let mut nonce = [0_u8; 16];
        File::open("/dev/urandom")
            .unwrap()
            .read_exact(&mut nonce)
            .unwrap();
        let name = nonce
            .iter()
            .map(|byte| format!("{byte:02x}"))
            .collect::<String>();
        let path = std::env::temp_dir().join(format!("trill-readback-unit-{name}"));
        std::fs::DirBuilder::new()
            .mode(0o700)
            .create(&path)
            .unwrap();
        Self(path)
    }
}

impl Drop for Directory {
    fn drop(&mut self) {
        let _ = std::fs::remove_dir_all(&self.0);
    }
}

fn target() -> NotesTargetIdentity {
    NotesTargetIdentity {
        session_instance: "1".repeat(32),
        task_id: 1,
        incarnation: "2".repeat(32),
    }
}

fn standby(root: &Directory) -> Standby {
    let helper = Path::new("/usr/bin/true").canonicalize().unwrap();
    Standby::prepare(
        &helper,
        &sha256_hex(&std::fs::read(&helper).unwrap()),
        root.0.clone(),
    )
    .unwrap()
}

#[test]
fn readback_seals_exact_elf_and_refuses_mismatched_unsafe_or_linked_sources() {
    let root = Directory::new();
    let helper = root.0.join("helper");
    let raw = std::fs::read("/usr/bin/true").unwrap();
    std::fs::write(&helper, &raw).unwrap();
    std::fs::set_permissions(&helper, std::fs::Permissions::from_mode(0o700)).unwrap();
    assert!(Standby::prepare(&helper, &"0".repeat(64), root.0.clone()).is_err());
    assert!(Standby::prepare(&helper, &"a".repeat(64), root.0.clone()).is_err());
    let mut prepared = Standby::prepare(&helper, &sha256_hex(&raw), root.0.clone()).unwrap();
    assert!(prepared.executable.write_all(b"changed").is_err());
    std::fs::write(&helper, b"changed path cannot change sealed ELF").unwrap();
    let mut sealed =
        File::open(format!("/proc/self/fd/{}", prepared.executable.as_raw_fd())).unwrap();
    let mut bytes = Vec::new();
    sealed.read_to_end(&mut bytes).unwrap();
    assert_eq!(bytes, raw);
    std::fs::write(&helper, &raw).unwrap();
    std::fs::set_permissions(&helper, std::fs::Permissions::from_mode(0o722)).unwrap();
    assert!(Standby::prepare(&helper, &sha256_hex(&raw), root.0.clone()).is_err());
    std::fs::set_permissions(&helper, std::fs::Permissions::from_mode(0o700)).unwrap();
    std::fs::hard_link(&helper, root.0.join("alias")).unwrap();
    assert!(Standby::prepare(&helper, &sha256_hex(&raw), root.0.clone()).is_err());
}

#[test]
fn readback_requires_the_same_pinned_reaped_child_and_never_consumes_a_live_app() {
    let root = Directory::new();
    let mut prepared = standby(&root);
    let (_owner, app_peer) = UnixDatagram::pair().unwrap();
    prepared.bind(target(), &app_peer).unwrap();
    assert!(prepared.bind(target(), &app_peer).is_err());
    let mut app = Command::new("/bin/sleep").arg("10").spawn().unwrap();
    prepared.pin_original(&mut app).unwrap();
    assert!(prepared.after_reap(&mut app).is_err());
    assert!(!prepared.consumed);
    assert!(prepared.running.is_none());
    let mut foreign = Command::new("/bin/true").spawn().unwrap();
    foreign.wait().unwrap();
    assert!(prepared.after_reap(&mut foreign).is_err());
    assert!(!prepared.consumed);
    assert!(prepared.running.is_none());
    app.kill().unwrap();
    app.wait().unwrap();
}

#[test]
fn readback_refuses_noninitial_targets_and_a_child_that_was_not_pinned_alive() {
    let root = Directory::new();
    let mut prepared = standby(&root);
    let (_owner, app_peer) = UnixDatagram::pair().unwrap();
    let mut wrong = target();
    wrong.task_id = 2;
    assert!(prepared.bind(wrong, &app_peer).is_err());
    prepared.bind(target(), &app_peer).unwrap();
    let mut exited = Command::new("/bin/true").spawn().unwrap();
    exited.wait().unwrap();
    assert!(prepared.pin_original(&mut exited).is_err());
    assert!(prepared.after_reap(&mut exited).is_err());
    assert!(!prepared.consumed);
}

#[test]
fn sealed_bytes_must_match_the_original_digest_not_only_the_source_observation() {
    let expected = b"\x7fELForiginal";
    let changed = b"\x7fELFmodified";
    assert_eq!(expected.len(), changed.len());
    // SAFETY: creates a new test-owned anonymous file, never a product handle.
    let raw = unsafe {
        libc::memfd_create(
            c"readback-image-negative".as_ptr(),
            libc::MFD_CLOEXEC | libc::MFD_ALLOW_SEALING,
        )
    };
    assert!(raw >= 0);
    // SAFETY: owns exactly the descriptor returned above.
    let mut file = unsafe { File::from_raw_fd(raw) };
    file.write_all(changed).unwrap();
    // SAFETY: the file is held exclusively throughout mode/seal setup.
    assert_eq!(unsafe { libc::fchmod(raw, 0o500) }, 0);
    let seals = libc::F_SEAL_WRITE | libc::F_SEAL_GROW | libc::F_SEAL_SHRINK | libc::F_SEAL_SEAL;
    assert_eq!(unsafe { libc::fcntl(raw, libc::F_ADD_SEALS, seals) }, 0);
    assert!(
        verify_sealed_program(&mut file, &sha256_hex(expected), expected.len() as u64).is_err()
    );
    verify_sealed_program(&mut file, &sha256_hex(changed), changed.len() as u64).unwrap();
}
