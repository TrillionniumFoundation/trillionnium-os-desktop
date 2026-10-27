//! Real file/lock mechanics only. Fixtures confer no Root or effect authority.
use super::*;
use std::os::unix::fs::{PermissionsExt, symlink};

fn private_admin() -> tempfile::TempDir {
    let directory = tempfile::tempdir().unwrap();
    std::fs::set_permissions(directory.path(), std::fs::Permissions::from_mode(0o700)).unwrap();
    directory
}

fn admission(operation: &str) -> Value {
    serde_json::json!({
        "original_owner":{"agent":"original-agent", "generation":7},
        "old_target":"original-notes-incarnation",
        "original_thread":"original-thread",
        "operation_selector":{"kind":"exact_operation", "operation_id":operation},
    })
}

#[test]
fn interrupted_pre_spawn_preparation_reopens_exact_identity_without_rewriting() {
    let directory = private_admin();
    let admitted = admission("original-operation");
    let sockets = serde_json::json!({"paths":["original-socket"], "scope":"observation only"});
    let first = RecoveryPreparation::lock_directory(directory.path()).unwrap();
    first.admit(&admitted).unwrap();
    let saved = std::fs::read(first.directory.join(ADMITTED)).unwrap();
    let inode = std::fs::metadata(first.directory.join(ADMITTED))
        .unwrap()
        .ino();
    drop(first); // Equivalent lock release to interrupted lease waiting.

    let second = RecoveryPreparation::lock_directory(directory.path()).unwrap();
    second.admit(&admitted).unwrap();
    second.sockets_retired(&sockets).unwrap();
    assert!(second.admit(&admission("replacement-operation")).is_err());
    assert_eq!(
        std::fs::read(second.directory.join(ADMITTED)).unwrap(),
        saved
    );
    assert_eq!(
        std::fs::metadata(second.directory.join(ADMITTED))
            .unwrap()
            .ino(),
        inode
    );
    drop(second);

    let third = RecoveryPreparation::lock_directory(directory.path()).unwrap();
    third.admit(&admitted).unwrap();
    third.sockets_retired(&sockets).unwrap();
    assert!(
        third
            .sockets_retired(&serde_json::json!({"paths":[]}))
            .is_err()
    );
    third.consume_spawn().unwrap();
    assert!(third.consume_spawn().is_err());
    assert!(third.sockets_retired(&sockets).is_err());
    drop(third);

    let fourth = RecoveryPreparation::lock_directory(directory.path()).unwrap();
    assert!(fourth.admit(&admitted).is_err());
    assert_eq!(fourth.read(ADMITTED).unwrap(), admitted);
}

#[test]
fn actual_exclusive_lock_blocks_another_invocation_until_owner_drop() {
    let directory = private_admin();
    let first = std::sync::Arc::new(RecoveryPreparation::lock_directory(directory.path()).unwrap());
    let mount_cleanup_owner = first.clone();
    assert!(RecoveryPreparation::lock_directory(directory.path()).is_err());
    let lock_inode = std::fs::metadata(directory.path().join("recovery.lock"))
        .unwrap()
        .ino();
    drop(first);
    // Dropping Existing on an error cannot release the kernel lock while the
    // Product still owns mount cleanup.
    assert!(RecoveryPreparation::lock_directory(directory.path()).is_err());
    drop(mount_cleanup_owner);
    let next = RecoveryPreparation::lock_directory(directory.path()).unwrap();
    assert_eq!(next._lock.metadata().unwrap().ino(), lock_inode);
}

#[test]
fn possible_legacy_or_partial_spawn_never_rearms_preparation() {
    for name in [
        SPAWN_CONSUMED,
        "session.stdout",
        "session.stderr",
        "authority-config.json",
        "10-writer-rotated.json",
        "unexpected.json",
    ] {
        let directory = private_admin();
        let preparation = RecoveryPreparation::lock_directory(directory.path()).unwrap();
        preparation.admit(&admission("old")).unwrap();
        // An empty consume marker is still an uncertain attempt, not absence.
        File::create(preparation.directory.join(name)).unwrap();
        drop(preparation);
        let retry = RecoveryPreparation::lock_directory(directory.path()).unwrap();
        assert!(retry.admit(&admission("old")).is_err(), "accepted {name}");
        assert_eq!(
            std::fs::metadata(retry.directory.join(name)).unwrap().len(),
            0
        );
    }
}

#[test]
fn malformed_oversized_and_aliased_admission_remain_rejected_and_intact() {
    for bytes in [b"{partial".to_vec(), vec![b' '; 65_537]] {
        let directory = private_admin();
        let preparation = RecoveryPreparation::lock_directory(directory.path()).unwrap();
        preparation.admit(&admission("old")).unwrap();
        std::fs::write(preparation.directory.join(ADMITTED), &bytes).unwrap();
        assert!(preparation.admit(&admission("old")).is_err());
        assert_eq!(
            std::fs::read(preparation.directory.join(ADMITTED)).unwrap(),
            bytes
        );
    }
    let directory = private_admin();
    let preparation = RecoveryPreparation::lock_directory(directory.path()).unwrap();
    preparation.admit(&admission("old")).unwrap();
    let original = preparation.directory.join(ADMITTED);
    let alias = directory.path().join("preserved-admission");
    std::fs::hard_link(&original, &alias).unwrap();
    assert!(preparation.admit(&admission("old")).is_err());
    std::fs::remove_file(&original).unwrap();
    symlink(&alias, &original).unwrap();
    assert!(preparation.admit(&admission("old")).is_err());
    assert_eq!(
        serde_json::from_slice::<Value>(&std::fs::read(alias).unwrap()).unwrap(),
        admission("old")
    );
}

#[test]
fn incomplete_stage_order_cannot_consume_a_spawn() {
    let directory = private_admin();
    let preparation = RecoveryPreparation::lock_directory(directory.path()).unwrap();
    preparation.admit(&admission("old")).unwrap();
    assert!(preparation.consume_spawn().is_err());
    assert!(!preparation.directory.join(SPAWN_CONSUMED).exists());
    std::fs::remove_file(preparation.directory.join(ADMITTED)).unwrap();
    fs::json_new(
        &preparation.directory.join(SOCKETS_RETIRED),
        &serde_json::json!({}),
    )
    .unwrap();
    assert!(preparation.admit(&admission("old")).is_err());
    assert!(!preparation.directory.join(ADMITTED).exists());
}

#[test]
fn lock_custody_rejects_shared_writes_aliases_and_nonempty_state() {
    let directory = private_admin();
    let path = directory.path().join("recovery.lock");
    std::fs::write(&path, b"preserve").unwrap();
    std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o600)).unwrap();
    assert!(RecoveryPreparation::lock_directory(directory.path()).is_err());
    assert_eq!(std::fs::read(&path).unwrap(), b"preserve");
    std::fs::write(&path, b"").unwrap();
    std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o666)).unwrap();
    assert!(RecoveryPreparation::lock_directory(directory.path()).is_err());
    std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o600)).unwrap();
    let alias = directory.path().join("lock-alias");
    std::fs::hard_link(&path, &alias).unwrap();
    assert!(RecoveryPreparation::lock_directory(directory.path()).is_err());
    std::fs::remove_file(&path).unwrap();
    symlink(alias, path).unwrap();
    assert!(RecoveryPreparation::lock_directory(directory.path()).is_err());
}
