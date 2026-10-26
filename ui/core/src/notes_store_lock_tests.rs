use super::*;

struct Directory(std::path::PathBuf);

impl Directory {
    fn new() -> Self {
        let mut random = [0_u8; 16];
        File::open("/dev/urandom")
            .unwrap()
            .read_exact(&mut random)
            .unwrap();
        let suffix = random
            .iter()
            .map(|byte| format!("{byte:02x}"))
            .collect::<String>();
        let path = std::env::temp_dir().join(format!("trill-notes-lock-{suffix}"));
        DirBuilder::new().mode(0o700).create(&path).unwrap();
        Self(path)
    }
}

impl Drop for Directory {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

#[test]
fn retired_owner_releases_lock_despite_a_retained_open_description() {
    let root = Directory::new();
    let identity = NotesTargetIdentity {
        session_instance: "a".repeat(32),
        task_id: 1,
        incarnation: "b".repeat(32),
    };
    let app = NotesStore::create(&root.0, identity.clone()).unwrap();
    // fork retains this same open description until exec closes CLOEXEC fds.
    // A duplicate deterministically holds that kernel reference without a race.
    let inherited = app._lock.try_clone().unwrap();
    drop(app);
    let recovered = NotesStore::recover(&root.0, &identity);
    drop(inherited);
    let recovered = recovered.expect("a retired owner must release its incarnation lock");
    assert_eq!(recovered.target(), &identity);
    assert_eq!(recovered.revision(), 0);
    assert!(
        NotesStore::recover(&root.0, &identity).is_err(),
        "closing the old duplicate must not release the replacement owner's lock"
    );
}

#[test]
fn construction_error_releases_an_acquired_lock_before_store_construction() {
    let root = Directory::new();
    let identity = NotesTargetIdentity {
        session_instance: "c".repeat(32),
        task_id: 1,
        incarnation: "d".repeat(32),
    };
    drop(NotesStore::create(&root.0, identity.clone()).unwrap());
    let directory = open_directory(&root.0, &identity, Mode::RecoveryOnly).unwrap();
    let mut inherited = None;
    let failed: io::Result<()> = (|| {
        let lock = lock_directory(&directory)?;
        inherited = Some(lock.try_clone()?);
        Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "constructor validation",
        ))
    })();
    let recovered = NotesStore::recover(&root.0, &identity);
    drop(inherited);
    assert_eq!(failed.unwrap_err().kind(), io::ErrorKind::InvalidData);
    let recovered = recovered.expect("constructor failure must retire its acquired lock");
    assert_eq!(recovered.target(), &identity);
}
