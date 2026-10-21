// SPDX-License-Identifier: MPL-2.0

//! Real RamInode operations; concurrency is covered by a separate 2-CPU profile.

use ostd::prelude::ktest;

use super::*;
use crate::{
    fs::vfs::permission_attrs::{PermissionAttrOp, PermissionAttrRequest},
    process::credentials::capabilities::CapSet,
    time::clocks,
};

pub(super) fn new_aliases(mode: InodeMode) -> (Arc<RamFs>, Arc<Dentry>, Arc<Dentry>) {
    clocks::init_for_ktest();
    let fs = RamFs::new();
    let root = Dentry::new_root(fs.root_inode());
    let dir = root.as_dir_dentry_or_err().unwrap();
    let file = dir.create_child("original", || {
        dir.inode().create(&dir, "original", InodeType::File, mode)
    }).unwrap();
    file.inode().set_owner(&file, Uid::new(1000)).unwrap();
    file.inode().set_group(&file, Gid::new(2000)).unwrap();
    dir.link(&file, "alias").unwrap();
    let alias = dir.lookup_child("alias").unwrap();
    assert!(!Arc::ptr_eq(&file, &alias));
    assert!(Arc::ptr_eq(file.inode(), alias.inode()));
    assert_eq!(file.inode().metadata().unwrap().nr_hard_links, 2);
    (fs, file, alias)
}

pub(super) fn request(operation: PermissionAttrOp, uid: u32, caps: CapSet) -> PermissionAttrRequest {
    PermissionAttrRequest::for_test(
        operation,
        Uid::new(uid),
        Gid::new(2000),
        BTreeSet::new(),
        caps,
    )
}

fn assert_attributes_eq(before: &Metadata, after: &Metadata) {
    assert_eq!(after.ino, before.ino);
    assert_eq!(after.container_dev_id, before.container_dev_id);
    assert_eq!(after.mode, before.mode);
    assert_eq!(after.uid, before.uid);
    assert_eq!(after.gid, before.gid);
    assert_eq!(after.last_meta_change_at, before.last_meta_change_at);
}

#[ktest]
fn permission_rejection_has_no_partial_update() {
    let (_fs, file, alias) = new_aliases(InodeMode::from_bits_truncate(0o6755));
    file.inode().set_ctime(&file, Duration::MAX);
    let before = file.inode().metadata().unwrap();
    let operation = PermissionAttrOp::Chown {
        uid: Some(Uid::new(1002)),
        gid: Some(Gid::new(2002)),
    };
    // CAP_CHOWN authorizes IDs, but the non-owner also needs CAP_FOWNER
    // for the necessary set-ID clearing. A denial must precede every write.
    let denied = request(operation, 1001, CapSet::CHOWN);
    let result = alias.inode().try_permission_attr_transaction(&alias, &denied).unwrap();
    assert_eq!(result.unwrap_err().error(), Errno::EPERM);
    assert_attributes_eq(&before, &file.inode().metadata().unwrap());

    let allowed = request(operation, 1001, CapSet::CHOWN | CapSet::FOWNER);
    alias.inode().try_permission_attr_transaction(&alias, &allowed).unwrap().unwrap();
    let after = file.inode().metadata().unwrap();
    assert_eq!(after.uid, Uid::new(1002));
    assert_eq!(after.gid, Gid::new(2002));
    assert_eq!(after.mode.bits(), 0o755);
    assert_ne!(after.last_meta_change_at, before.last_meta_change_at);
}

#[ktest]
fn permission_noop_chown_updates_ctime() {
    let (_fs, file, alias) = new_aliases(InodeMode::from_bits_truncate(0o644));
    // A sentinel makes the timestamp assertion deterministic without sleeping
    // or depending on whether the coarse clock advances during this test.
    file.inode().set_ctime(&file, Duration::MAX);
    let before = file.inode().metadata().unwrap();
    let noop = request(PermissionAttrOp::Chown { uid: None, gid: None }, 1001, CapSet::empty());
    alias.inode().try_permission_attr_transaction(&alias, &noop).unwrap().unwrap();
    let after = file.inode().metadata().unwrap();
    assert_eq!(after.uid, before.uid);
    assert_eq!(after.gid, before.gid);
    assert_eq!(after.mode, before.mode);
    assert_eq!(after.ino, before.ino);
    assert_eq!(after.container_dev_id, before.container_dev_id);
    assert_ne!(after.last_meta_change_at, before.last_meta_change_at);
}

#[ktest]
fn permission_alias_observes_new_owner() {
    let (_fs, file, alias) = new_aliases(InodeMode::from_bits_truncate(0o4755));
    let chown = request(
        PermissionAttrOp::Chown { uid: Some(Uid::new(1002)), gid: None },
        1001,
        CapSet::CHOWN | CapSet::FOWNER,
    );
    alias.inode().try_permission_attr_transaction(&alias, &chown).unwrap().unwrap();
    let before = file.inode().metadata().unwrap();
    assert_eq!(before.uid, Uid::new(1002));
    assert_eq!(before.mode.bits(), 0o755);
    let chmod = PermissionAttrOp::Chmod(InodeMode::from_bits_truncate(0o4755));
    let old_owner = request(chmod, 1000, CapSet::empty());
    let result = file.inode().try_permission_attr_transaction(&file, &old_owner).unwrap();
    assert_eq!(result.unwrap_err().error(), Errno::EPERM);
    assert_attributes_eq(&before, &alias.inode().metadata().unwrap());
    let new_owner = request(chmod, 1002, CapSet::empty());
    alias.inode().try_permission_attr_transaction(&alias, &new_owner).unwrap().unwrap();
    assert_eq!(file.inode().mode().unwrap().bits(), 0o4755);
}
