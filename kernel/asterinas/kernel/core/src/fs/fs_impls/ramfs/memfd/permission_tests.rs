// SPDX-License-Identifier: MPL-2.0

use ostd::prelude::ktest;

use super::*;
use crate::{
    fs::vfs::permission_attrs::{PermissionAttrOp, PermissionAttrRequest},
    process::credentials::capabilities::CapSet,
    time::clocks,
};

#[ktest]
fn permission_memfd_exec_seal_preserves_attributes_on_error() {
    clocks::init_for_ktest();
    let file = InodeHandle::new_memfd("permission".to_string(), MemfdFlags::MFD_NOEXEC_SEAL).unwrap();
    let path = file.path();
    let dentry = path.dentry();
    let inode = dentry.inode();
    inode.set_ctime(dentry, Duration::MAX);
    let before = inode.metadata().unwrap();
    assert_eq!(before.nr_hard_links, 0);
    assert!(file.get_seals().unwrap().contains(FileSeals::F_SEAL_EXEC));
    assert!(!before.mode.intersects(mkmod!(a+x)));
    let request = |mode| PermissionAttrRequest::for_test(
        PermissionAttrOp::Chmod(mode), before.uid, before.gid, BTreeSet::new(), CapSet::all(),
    );
    let denied = request(before.mode | mkmod!(u+x));
    let result = inode.try_permission_attr_transaction(dentry, &denied).unwrap();
    assert_eq!(result.unwrap_err().error(), Errno::EPERM);
    let after = inode.metadata().unwrap();
    assert_eq!(after.nr_hard_links, 0);
    assert_eq!(after.uid, before.uid);
    assert_eq!(after.gid, before.gid);
    assert_eq!(after.mode, before.mode);
    assert_eq!(after.last_meta_change_at, before.last_meta_change_at);

    // A seal forbids changing executable bits; it does not reject same-mode chmod.
    inode.try_permission_attr_transaction(dentry, &request(before.mode)).unwrap().unwrap();
    assert_eq!(inode.mode().unwrap(), before.mode);
    assert_ne!(inode.ctime(), before.last_meta_change_at);
    assert_eq!(inode.metadata().unwrap().nr_hard_links, 0);
}
