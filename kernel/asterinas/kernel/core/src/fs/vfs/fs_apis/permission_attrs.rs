// SPDX-License-Identifier: MPL-2.0

//! Permission decisions evaluated against metadata under its owning inode lock.
//!
//! Capture caller credentials before taking inode locks.
//! A backend then evaluates the request, checks its own restrictions, and commits
//! every resulting field without releasing the lock. No callback into an LSM or
//! the caller's supplementary-group lock runs inside that critical section.
//! When the locked decision first needs an LSM capability result, it requests that
//! result without changing metadata. The caller drops the backend lock, obtains
//! only that result, then retries against fresh metadata under the owner lock.

use core::{cell::Cell, time::Duration};

use super::inode::Metadata;
use crate::{
    fs::{
        file::{InodeMode, InodeType, mkmod},
        vfs::path::Dentry,
    },
    prelude::*,
    process::{
        Gid, Uid, UserNamespace, credentials::capabilities::CapSet, posix_thread::PosixThread,
    },
    security::lsm::hooks as lsm_hooks,
    time::clocks::RealTimeCoarseClock,
};

#[cfg(all(ktest, feature = "permission-attr-smp-ktest"))]
pub(in crate::fs) mod smp_support;

/// The permission operation, before inspecting the inode's mutable attributes.
#[derive(Clone, Copy, Debug)]
pub(crate) enum PermissionAttrOp {
    Chmod(InodeMode),
    Chown { uid: Option<Uid>, gid: Option<Gid> },
    ClearSetIdBits,
}

/// Caller authority captured outside the inode critical section.
pub(crate) struct PermissionAttrRequest {
    operation: PermissionAttrOp,
    fsuid: Uid,
    fsgid: Gid,
    supplementary_gids: BTreeSet<Gid>,
    cap_chown: Option<Result<()>>,
    cap_fowner: Option<Result<()>>,
    cap_fsetid: Option<Result<()>>,
    pending_cap: Cell<Option<PermissionCap>>,
    #[cfg(all(ktest, feature = "permission-attr-smp-ktest"))]
    checkpoint: Option<Arc<smp_support::PermissionCheckpoint>>,
}

impl PermissionAttrRequest {
    pub(crate) fn run_for_context(
        operation: PermissionAttrOp,
        dentry: &Dentry,
        ctx: &Context,
    ) -> Option<Result<()>> {
        let user_ns = ctx.thread_local.borrow_user_ns();
        Self::run_for_thread(operation, dentry, ctx.posix_thread, user_ns.as_ref())
    }

    pub(in crate::fs) fn run_for_thread(
        operation: PermissionAttrOp,
        dentry: &Dentry,
        posix_thread: &PosixThread,
        user_ns: &UserNamespace,
    ) -> Option<Result<()>> {
        let credentials = posix_thread.credentials();
        let mut request = Self {
            operation,
            fsuid: credentials.fsuid(),
            fsgid: credentials.fsgid(),
            supplementary_gids: (*credentials.groups()).clone(),
            cap_chown: None,
            cap_fowner: None,
            cap_fsetid: None,
            pending_cap: Cell::new(None),
            #[cfg(all(ktest, feature = "permission-attr-smp-ktest"))]
            checkpoint: None,
        };

        // A capability hook runs only after a real locked decision needs it.
        // Its result is caller-/namespace-specific, not inode-specific, so it is
        // reusable within this operation. Credentials belong to the current
        // thread. Each of the three hooks is requested at most once.
        loop {
            let result = dentry.inode().try_permission_attr_transaction(dentry, &request);
            let Some(cap) = request.pending_cap.take() else {
                return result;
            };
            debug_assert!(result.as_ref().is_some_and(|result| {
                result.as_ref().is_err_and(|error| error.error() == Errno::EAGAIN)
            }));
            let result = lsm_hooks::on_capable(lsm_hooks::CapableContext::new(
                user_ns,
                posix_thread,
                cap.cap_set(),
            ));
            match cap {
                PermissionCap::Chown => request.cap_chown = Some(result),
                PermissionCap::Fowner => request.cap_fowner = Some(result),
                PermissionCap::Fsetid => request.cap_fsetid = Some(result),
            }
        }
    }

    // The outer error means "obtain this capability result and retry", not an
    // LSM denial. The inner result preserves the LSM error for required checks
    // and lets optional FSETID/FOWNER checks preserve their existing behavior.
    fn capability(&self, cap: PermissionCap) -> Result<Result<()>> {
        let result = match cap {
            PermissionCap::Chown => self.cap_chown,
            PermissionCap::Fowner => self.cap_fowner,
            PermissionCap::Fsetid => self.cap_fsetid,
        };
        if let Some(result) = result {
            return Ok(result);
        }
        self.pending_cap.set(Some(cap));
        Err(Error::with_message(Errno::EAGAIN, "capability evidence required"))
    }

    fn has_group(&self, gid: Gid) -> bool {
        self.fsgid == gid || self.supplementary_gids.contains(&gid)
    }

    /// Evaluates a request against a snapshot protected by the backend's lock.
    /// The caller must retain that same lock through restriction checks and commit.
    pub(in crate::fs) fn evaluate(&self, attrs: PermissionAttrs) -> Result<PermissionAttrUpdate> {
        let is_owner = self.fsuid == attrs.uid;
        let mut update = PermissionAttrUpdate::default();

        match self.operation {
            PermissionAttrOp::Chmod(mut mode) => {
                if !is_owner {
                    self.capability(PermissionCap::Fowner)??;
                }
                if mode.has_set_gid()
                    && !self.has_group(attrs.gid)
                    && self.capability(PermissionCap::Fsetid)?.is_err()
                {
                    mode.remove(InodeMode::S_ISGID);
                }
                // Even a same-mode chmod must run the backend's mode restrictions.
                update.mode = Some(mode);
            }
            PermissionAttrOp::Chown { uid, gid } => {
                let needs_cap_chown = uid.is_some_and(|uid| !is_owner || uid != attrs.uid)
                    || gid.is_some_and(|gid| {
                        !is_owner || (gid != attrs.gid && !self.has_group(gid))
                    });
                if needs_cap_chown {
                    self.capability(PermissionCap::Chown)??;
                }

                let mut mode = attrs.mode;
                if attrs.type_ != InodeType::Dir {
                    mode.remove(InodeMode::S_ISUID);
                    if mode.has_set_gid()
                        && (mode.is_group_executable()
                            || (!self.has_group(attrs.gid)
                                && self.capability(PermissionCap::Fsetid)?.is_err()))
                    {
                        mode.remove(InodeMode::S_ISGID);
                    }
                }
                if mode != attrs.mode {
                    if !is_owner && self.capability(PermissionCap::Fowner)?.is_err() {
                        return_errno_with_message!(Errno::EPERM, "cannot change the file mode");
                    }
                    update.mode = Some(mode);
                }
                update.uid = uid;
                update.gid = gid;
                // Includes chown(-1, -1) with no set-ID bits and no owner check.
                update.touch_ctime = true;
            }
            PermissionAttrOp::ClearSetIdBits => {
                if attrs.type_ != InodeType::File
                    || !attrs.mode.intersects(InodeMode::S_ISUID | InodeMode::S_ISGID)
                    || self.capability(PermissionCap::Fsetid)?.is_ok()
                {
                    return Ok(update);
                }
                let mut mode = attrs.mode;
                mode.remove(InodeMode::S_ISUID);
                if mode.has_set_gid()
                    && (mode.is_group_executable() || !self.has_group(attrs.gid))
                {
                    mode.remove(InodeMode::S_ISGID);
                }
                if mode != attrs.mode {
                    update.mode = Some(mode);
                }
            }
        }
        Ok(update)
    }

    /// Applies a complete request to an already exclusively locked `Metadata`.
    pub(in crate::fs) fn apply_to_metadata(
        &self,
        metadata: &mut Metadata,
        mode_policy: PermissionModePolicy,
        ctime_policy: PermissionCtimePolicy,
    ) -> Result<()> {
        let update = self.evaluate(PermissionAttrs::from(&*metadata))?;
        mode_policy.check(metadata.mode, update.mode)?;
        if let Some(mode) = update.mode {
            metadata.mode = mode;
        }
        if let Some(uid) = update.uid {
            metadata.uid = uid;
        }
        if let Some(gid) = update.gid {
            metadata.gid = gid;
        }
        if let Some(ctime) = update.ctime(ctime_policy) {
            metadata.last_meta_change_at = ctime;
        }
        Ok(())
    }

    #[cfg(ktest)]
    pub(crate) fn for_test(
        operation: PermissionAttrOp,
        fsuid: Uid,
        fsgid: Gid,
        supplementary_gids: BTreeSet<Gid>,
        caps: CapSet,
    ) -> Self {
        let capable = |cap| {
            if caps.contains(cap) {
                Ok(())
            } else {
                Err(Error::new(Errno::EPERM))
            }
        };
        Self {
            operation,
            fsuid,
            fsgid,
            supplementary_gids,
            cap_chown: Some(capable(CapSet::CHOWN)),
            cap_fowner: Some(capable(CapSet::FOWNER)),
            cap_fsetid: Some(capable(CapSet::FSETID)),
            pending_cap: Cell::new(None),
            #[cfg(all(ktest, feature = "permission-attr-smp-ktest"))]
            checkpoint: None,
        }
    }

    #[cfg(all(ktest, feature = "permission-attr-smp-ktest"))]
    pub(in crate::fs) fn with_checkpoint(
        mut self,
        checkpoint: Arc<smp_support::PermissionCheckpoint>,
    ) -> Self {
        self.checkpoint = Some(checkpoint);
        self
    }

    #[cfg(all(ktest, feature = "permission-attr-smp-ktest"))]
    pub(in crate::fs) fn after_check_for_test(&self, stage: smp_support::CheckpointStage) {
        if let Some(checkpoint) = &self.checkpoint {
            checkpoint.after_check(stage);
        }
    }
}

#[derive(Clone, Copy)]
enum PermissionCap {
    Chown,
    Fowner,
    Fsetid,
}

impl PermissionCap {
    fn cap_set(self) -> CapSet {
        match self {
            Self::Chown => CapSet::CHOWN,
            Self::Fowner => CapSet::FOWNER,
            Self::Fsetid => CapSet::FSETID,
        }
    }
}

/// Only the inode attributes needed for permission decisions.
#[derive(Clone, Copy)]
pub(in crate::fs) struct PermissionAttrs {
    pub type_: InodeType,
    pub mode: InodeMode,
    pub uid: Uid,
    pub gid: Gid,
}

impl From<&Metadata> for PermissionAttrs {
    fn from(metadata: &Metadata) -> Self {
        Self {
            type_: metadata.type_,
            mode: metadata.mode,
            uid: metadata.uid,
            gid: metadata.gid,
        }
    }
}

/// Fields to commit only after every check has succeeded.
#[derive(Default)]
pub(in crate::fs) struct PermissionAttrUpdate {
    pub mode: Option<InodeMode>,
    pub uid: Option<Uid>,
    pub gid: Option<Gid>,
    touch_ctime: bool,
}

impl PermissionAttrUpdate {
    pub(in crate::fs) fn ctime(&self, policy: PermissionCtimePolicy) -> Option<Duration> {
        let changes_attr = self.mode.is_some() || self.uid.is_some() || self.gid.is_some();
        (self.touch_ctime || (policy == PermissionCtimePolicy::OnAttributeChange && changes_attr))
            .then(|| RealTimeCoarseClock::get().read_time())
    }
}

/// Backend-specific mode restrictions, checked before any field changes.
#[derive(Clone, Copy)]
pub(in crate::fs) enum PermissionModePolicy {
    Writable,
    Forbidden(Errno),
    PreserveExecutableBits,
}

impl PermissionModePolicy {
    pub(in crate::fs) fn check(&self, old: InodeMode, new: Option<InodeMode>) -> Result<()> {
        let Some(new) = new else {
            return Ok(());
        };
        match self {
            Self::Writable => Ok(()),
            Self::Forbidden(errno) => Err(Error::new(*errno)),
            Self::PreserveExecutableBits if (old ^ new).intersects(mkmod!(a+x)) => {
                return_errno_with_message!(
                    Errno::EPERM,
                    "the file is sealed against modifying executable bits"
                );
            }
            Self::PreserveExecutableBits => Ok(()),
        }
    }
}

/// Preserve the existing timestamp rule of each migrated backend.
#[derive(Clone, Copy, PartialEq, Eq)]
pub(in crate::fs) enum PermissionCtimePolicy {
    OnAttributeChange,
    OnChown,
}
