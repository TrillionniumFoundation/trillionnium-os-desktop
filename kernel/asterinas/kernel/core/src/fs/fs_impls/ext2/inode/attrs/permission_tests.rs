// SPDX-License-Identifier: MPL-2.0

use ostd::prelude::ktest;

use super::*;
use crate::{
    fs::{
        ext2::{
            Ext2, FilePerm,
            test_utils::{create_file, default_fixture},
        },
        vfs::{
            file_system::FsFlags,
            permission_attrs::{PermissionAttrOp, PermissionAttrRequest},
        },
    },
    process::credentials::capabilities::CapSet,
};

#[ktest]
fn setgid_ext2_creation_inherits_group_and_directory_bit_before_persistent_publication() {
    let (fixture, root) = default_fixture();
    root.set_gid(60001).unwrap();
    root.set_mode(InodeMode::from_bits_truncate(0o2777))
        .unwrap();
    let file = root
        .create(
            "sgid-file",
            InodeType::File,
            FilePerm::from_bits_truncate(0o640),
        )
        .unwrap();
    let socket = root
        .create(
            "sgid-socket",
            InodeType::Socket,
            FilePerm::from_bits_truncate(0o660),
        )
        .unwrap();
    let directory = root
        .create(
            "sgid-dir",
            InodeType::Dir,
            FilePerm::from_bits_truncate(0o750),
        )
        .unwrap();
    let nested = directory
        .create(
            "nested",
            InodeType::File,
            FilePerm::from_bits_truncate(0o600),
        )
        .unwrap();
    assert_eq!(directory.metadata().mode.bits(), 0o2750);
    let ids = [file.ino(), socket.ino(), directory.ino(), nested.ino()];
    for item in [&file, &socket, &directory, &nested] {
        assert_eq!(item.gid(), 60001);
        assert_eq!(item.uid(), u32::from(crate::fs::utils::current_fs_ids().0));
    }
    fixture.ext2.sync_all().unwrap();
    let reopened = Ext2::open(
        fixture.disk.clone() as Arc<dyn BlockDevice>,
        FsFlags::empty(),
        None,
    )
    .unwrap();
    for ino in ids {
        assert_eq!(reopened.read_inode(ino).unwrap().gid(), 60001);
    }
    assert_eq!(
        reopened
            .read_inode(directory.ino())
            .unwrap()
            .metadata()
            .mode
            .bits(),
        0o2750
    );
    root.set_mode(InodeMode::from_bits_truncate(0o777)).unwrap();
    let plain = root
        .create(
            "plain",
            InodeType::File,
            FilePerm::from_bits_truncate(0o640),
        )
        .unwrap();
    assert_eq!(plain.gid(), u32::from(crate::fs::utils::current_fs_ids().1));
}

#[ktest]
fn permission_ext2_reject_then_commit() {
    let (fixture, root) = default_fixture();
    let file = create_file(&root, "permission");
    file.set_uid(1000).unwrap();
    file.set_gid(2000).unwrap();
    file.set_mode(InodeMode::from_bits_truncate(0o6755))
        .unwrap();
    let before = file.metadata();
    let operation = PermissionAttrOp::Chown {
        uid: Some(Uid::new(1002)),
        gid: Some(Gid::new(2002)),
    };
    let request = |caps| {
        PermissionAttrRequest::for_test(
            operation,
            Uid::new(1001),
            Gid::new(2000),
            BTreeSet::new(),
            caps,
        )
    };
    let error = file
        .permission_attr_transaction(&request(CapSet::CHOWN))
        .unwrap_err();
    assert_eq!(error.error(), Errno::EPERM);
    let denied = file.metadata();
    assert_eq!(denied.uid, before.uid);
    assert_eq!(denied.gid, before.gid);
    assert_eq!(denied.mode, before.mode);
    assert_eq!(denied.last_meta_change_at, before.last_meta_change_at);
    file.permission_attr_transaction(&request(CapSet::CHOWN | CapSet::FOWNER))
        .unwrap();
    let after = file.metadata();
    assert_eq!(after.uid, Uid::new(1002));
    assert_eq!(after.gid, Gid::new(2002));
    assert_eq!(after.mode.bits(), 0o755);
    // Exercise the real ext2 writeback path after the one-lock update.
    fixture.ext2.sync_all().unwrap();
    let reopened = Ext2::open(
        fixture.disk.clone() as Arc<dyn BlockDevice>,
        FsFlags::empty(),
        None,
    )
    .unwrap();
    let persisted = reopened.read_inode(file.ino()).unwrap().metadata();
    assert_eq!(persisted.uid, after.uid);
    assert_eq!(persisted.gid, after.gid);
    assert_eq!(persisted.mode, after.mode);
}

#[ktest]
fn utimes_ext2_denial_is_unchanged_and_success_is_persistent() {
    let (fixture, root) = default_fixture();
    let file = create_file(&root, "utimes");
    file.set_uid(1000).unwrap();
    file.set_gid(2000).unwrap();
    file.set_mode(InodeMode::from_bits_truncate(0o666)).unwrap();
    let operation = PermissionAttrOp::Utimes {
        atime: Some(Duration::from_secs(123)),
        mtime: Some(Duration::from_secs(456)),
        now_only: false,
    };
    let request = |uid| {
        PermissionAttrRequest::for_test(
            operation,
            Uid::new(uid),
            Gid::new(2000),
            BTreeSet::new(),
            CapSet::empty(),
        )
    };
    let before = file.metadata();
    let error = file
        .permission_attr_transaction(&request(1001))
        .unwrap_err();
    assert_eq!(error.error(), Errno::EPERM);
    let denied = file.metadata();
    assert_eq!(denied.last_access_at, before.last_access_at);
    assert_eq!(denied.last_modify_at, before.last_modify_at);
    assert_eq!(denied.last_meta_change_at, before.last_meta_change_at);
    file.permission_attr_transaction(&request(1000)).unwrap();
    fixture.ext2.sync_all().unwrap();
    let reopened = Ext2::open(
        fixture.disk.clone() as Arc<dyn BlockDevice>,
        FsFlags::empty(),
        None,
    )
    .unwrap();
    let persisted = reopened.read_inode(file.ino()).unwrap().metadata();
    assert_eq!(persisted.last_access_at, Duration::from_secs(123));
    assert_eq!(persisted.last_modify_at, Duration::from_secs(456));
}
