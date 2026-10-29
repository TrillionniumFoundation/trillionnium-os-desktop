// SPDX-License-Identifier: MPL-2.0

//! Owner and mode decisions made before a new inode is published.

use ostd::task::Task;

use crate::{
    fs::file::{InodeMode, InodeType},
    prelude::*,
    process::{Gid, Uid, credentials::capabilities::CapSet, posix_thread::AsPosixThread},
    security::lsm::hooks as lsm_hooks,
    thread::Thread,
};

/// Caller state captured before taking the parent's metadata lock.
pub(in crate::fs) struct InodeCreation {
    type_: InodeType,
    mode: InodeMode,
    fsuid: Uid,
    fsgid: Gid,
    groups: Option<Arc<BTreeSet<Gid>>>,
    cap_fsetid: bool,
}

impl InodeCreation {
    pub(in crate::fs) fn current(type_: InodeType, mode: InodeMode) -> Self {
        let mut result = Self {
            type_,
            mode,
            fsuid: Uid::new_root(),
            fsgid: Gid::new_root(),
            groups: None,
            cap_fsetid: true,
        };
        let Some(thread) = Thread::current() else {
            return result;
        };
        let Some(posix_thread) = thread.as_posix_thread() else {
            return result;
        };
        let credentials = posix_thread.credentials();
        result.fsuid = credentials.fsuid();
        result.fsgid = credentials.fsgid();
        result.groups = Some(credentials.groups());
        // Only this requested combination can need the capability result.
        // Resolve the namespace-specific hook before the parent metadata lock.
        result.cap_fsetid = type_ != InodeType::Dir
            && mode.contains(InodeMode::S_ISGID | InodeMode::S_IXGRP)
            && Task::current().is_some_and(|task| {
                task.as_thread_local().is_some_and(|local| {
                    let user_ns = local.borrow_user_ns();
                    lsm_hooks::on_capable(lsm_hooks::CapableContext::new(
                        user_ns.as_ref(),
                        posix_thread,
                        CapSet::FSETID,
                    ))
                    .is_ok()
                })
            });
        result
    }

    /// Evaluate one coherent parent mode/GID pair under its owner lock.
    /// This does not allocate, acquire a credential lock, or invoke an LSM.
    pub(in crate::fs) fn under_parent(
        &self,
        parent_mode: InodeMode,
        parent_gid: Gid,
    ) -> (InodeMode, Uid, Gid) {
        let mut mode = self.mode;
        let gid = if parent_mode.has_set_gid() {
            if self.type_ == InodeType::Dir {
                mode.insert(InodeMode::S_ISGID);
            } else if mode.contains(InodeMode::S_ISGID | InodeMode::S_IXGRP)
                && self.fsgid != parent_gid
                && !self
                    .groups
                    .as_ref()
                    .is_some_and(|groups| groups.contains(&parent_gid))
                && !self.cap_fsetid
            {
                mode.remove(InodeMode::S_ISGID);
            }
            parent_gid
        } else {
            self.fsgid
        };
        (mode, self.fsuid, gid)
    }
}
