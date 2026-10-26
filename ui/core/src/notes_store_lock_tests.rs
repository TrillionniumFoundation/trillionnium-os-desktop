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
