// SPDX-License-Identifier: MPL-2.0

use ostd::prelude::ktest;

use super::*;
use crate::{
    fs::{
        ext2::{Ext2, test_utils::{create_file, default_fixture}},
        vfs::{
            file_system::FsFlags,
            permission_attrs::{PermissionAttrOp, PermissionAttrRequest},
        },
    },
    process::credentials::capabilities::CapSet,
};

#[ktest]
fn permission_ext2_reject_then_commit() {
    let (fixture, root) = default_fixture();
    let file = create_file(&root, "permission");
    file.set_uid(1000).unwrap();
    file.set_gid(2000).unwrap();
    file.set_mode(InodeMode::from_bits_truncate(0o6755)).unwrap();
    let before = file.metadata();
    let operation = PermissionAttrOp::Chown {
        uid: Some(Uid::new(1002)),
        gid: Some(Gid::new(2002)),
    };
    let request = |caps| PermissionAttrRequest::for_test(
        operation, Uid::new(1001), Gid::new(2000), BTreeSet::new(), caps,
    );
    let error = file.permission_attr_transaction(&request(CapSet::CHOWN)).unwrap_err();
    assert_eq!(error.error(), Errno::EPERM);
    let denied = file.metadata();
    assert_eq!(denied.uid, before.uid);
    assert_eq!(denied.gid, before.gid);
    assert_eq!(denied.mode, before.mode);
    assert_eq!(denied.last_meta_change_at, before.last_meta_change_at);
    file.permission_attr_transaction(&request(CapSet::CHOWN | CapSet::FOWNER)).unwrap();
    let after = file.metadata();
    assert_eq!(after.uid, Uid::new(1002));
    assert_eq!(after.gid, Gid::new(2002));
    assert_eq!(after.mode.bits(), 0o755);
    // Exercise the real ext2 writeback path after the one-lock update.
    fixture.ext2.sync_all().unwrap();
    let reopened = Ext2::open(fixture.disk.clone() as Arc<dyn BlockDevice>, FsFlags::empty(), None)
        .unwrap();
    let persisted = reopened.read_inode(file.ino()).unwrap().metadata();
    assert_eq!(persisted.uid, after.uid);
    assert_eq!(persisted.gid, after.gid);
    assert_eq!(persisted.mode, after.mode);
}
