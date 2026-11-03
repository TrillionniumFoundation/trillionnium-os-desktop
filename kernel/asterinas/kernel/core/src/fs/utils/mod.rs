// SPDX-License-Identifier: MPL-2.0

//! Miscellaneous filesystem utilities shared across `fs` modules.

pub(crate) use dirent_visitor::DirentVisitor;
pub(crate) use direntry_vec::DirEntryVecExt;
pub(crate) use endpoint::{Endpoint, EndpointState};
pub(crate) use id_bitmap::IdBitmap;

use crate::{
    fs::file::{InodeMode, InodeType},
    process::{
        Gid, Uid, UserNamespace, credentials::capabilities::CapSet, posix_thread::AsPosixThread,
    },
    security::lsm::hooks as lsm_hooks,
    thread::Thread,
};

mod dirent_visitor;
mod direntry_vec;
mod endpoint;
mod id_bitmap;
pub(crate) mod systree_inode;

/// Maximum bytes in a path
pub(crate) const PATH_MAX: usize = 4096;

/// Maximum bytes in a file name
pub(crate) const NAME_MAX: usize = 255;

/// The upper limit for resolving symbolic links
pub(crate) const SYMLINKS_MAX: usize = 40;

pub(crate) type CStr256 = aster_util::fixed_str::FixedCStr<256>;
pub(crate) type Str16 = aster_util::fixed_str::FixedNonTerminatedCStr<16>;
pub(crate) type Str64 = aster_util::fixed_str::FixedNonTerminatedCStr<64>;

/// Returns the current thread's filesystem IDs, or root IDs for kernel threads.
pub(crate) fn current_fs_ids() -> (Uid, Gid) {
    Thread::current()
        .and_then(|thread| {
            let posix_thread = thread.as_posix_thread()?;
            let credentials = posix_thread.credentials();
            Some((credentials.fsuid(), credentials.fsgid()))
        })
        .unwrap_or((Uid::new_root(), Gid::new_root()))
}

/// Original inode creation ownership: setgid directories supply the child's
/// group and pass setgid onto subdirectories. A non-member cannot create a
/// group-executable setgid non-directory for that inherited group without
/// original CAP_FSETID. Non-executable setgid files retain their requested bit.
/// Callers capture parent mode/group together and hold no IRQ-disabled lock.
pub(crate) fn child_creation_attrs(
    parent_mode: InodeMode,
    parent_gid: Gid,
    type_: InodeType,
    mut mode: InodeMode,
) -> (Uid, Gid, InodeMode) {
    let current = Thread::current();
    let posix = current.as_ref().and_then(|thread| thread.as_posix_thread());
    let (uid, mut gid) = posix.map_or((Uid::new_root(), Gid::new_root()), |thread| {
        let credentials = thread.credentials();
        (credentials.fsuid(), credentials.fsgid())
    });
    if parent_mode.has_set_gid() {
        gid = parent_gid;
        if type_ == InodeType::Dir {
            mode.insert(InodeMode::S_ISGID);
        }
    }
    if type_ != InodeType::Dir
        && mode.contains(InodeMode::S_ISGID | InodeMode::S_IXGRP)
        && let Some(thread) = posix
        && !thread.credentials().has_group_for_fs_access(gid)
        && lsm_hooks::on_capable(lsm_hooks::CapableContext::new(
            UserNamespace::get_init_singleton().as_ref(),
            thread,
            CapSet::FSETID,
        ))
        .is_err()
    {
        mode.remove(InodeMode::S_ISGID);
    }
    (uid, gid, mode)
}
