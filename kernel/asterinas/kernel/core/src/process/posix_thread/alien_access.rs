// SPDX-License-Identifier: MPL-2.0

//! Alien access permission check for POSIX threads.
//!
//! An alien thread is one outside the current thread's thread group (the process).

use crate::{
    prelude::*,
    process::{
        credentials::capabilities::CapSet, posix_thread::PosixThread, process_vm::ProcessVmarGuard,
    },
    security::lsm::hooks as lsm_hooks,
};

/// Keeps the target image policy stable until the authorized resource is captured.
#[must_use]
pub(crate) struct AlienAccessGuard<'a> {
    _dumpable: Option<MutexGuard<'a, bool>>,
}

impl PosixThread {
    /// Checks whether `accessor` may access resources of `self`.
    ///
    /// NOTE: In Linux, the corresponding check is named `ptrace_may_access`,
    /// but not every call to it is actually related to `ptrace`.
    // Reference: <https://elixir.bootlin.com/linux/v6.16.5/source/kernel/ptrace.c#L276>.
    pub(crate) fn check_alien_access_from<'a>(
        &self,
        accessor: &PosixThread,
        mode: AlienAccessMode,
        vmar: &'a ProcessVmarGuard<'_>,
    ) -> Result<AlienAccessGuard<'a>> {
        debug_assert!(vmar.belongs_to(&self.process()));
        if Weak::ptr_eq(accessor.weak_process(), self.weak_process()) {
            return Ok(AlienAccessGuard { _dumpable: None });
        }

        // The caller holds this target's VMAR guard. The shared image mutex
        // also serializes credential publication by distinct CLONE_VM peers.
        // Keep it through the original LSM checks and the caller's capture.
        let dumpable = vmar
            .as_ref()
            .map(|vmar| vmar.process_vm().dumpable().lock());
        if dumpable.as_ref().is_some_and(|dumpable| !**dumpable) {
            let process = self.process();
            let user_ns = process.user_ns().lock();
            lsm_hooks::on_capable(lsm_hooks::CapableContext::new(
                user_ns.as_ref(),
                accessor,
                CapSet::SYS_PTRACE,
            ))?;
        }
        self.check_original_alien_access_from(accessor, mode)?;
        Ok(AlienAccessGuard {
            _dumpable: dumpable,
        })
    }

    /// Voluntary TRACEME retains its original LSM/trusted-image policy.
    /// It is not an external ptrace_may_access request and gains no dumpability gate.
    pub(crate) fn check_traceme_access_from(&self, accessor: &PosixThread) -> Result<()> {
        self.check_original_alien_access_from(accessor, AlienAccessMode::ATTACH_WITH_REAL_CREDS)
    }

    fn check_original_alien_access_from(
        &self,
        accessor: &PosixThread,
        mode: AlienAccessMode,
    ) -> Result<()> {
        #[cfg(feature = "g1c-trusted-observe")]
        if mode.kind() == AlienAccessKind::Attach && self.process().has_initial_observe_authority()
        {
            return_errno_with_message!(
                Errno::EPERM,
                "alien attachment to the trusted initial image is forbidden"
            )
        }

        lsm_hooks::on_alien_access(lsm_hooks::AlienAccessContext::new(accessor, self, mode))
    }
}

/// The credentials used by an alien access check.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) enum CredsSource {
    FsCreds,
    RealCreds,
}

/// The strength of an alien access check.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) enum AlienAccessKind {
    Read,
    Attach,
}

/// An alien access check mode.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) struct AlienAccessMode {
    kind: AlienAccessKind,
    creds: CredsSource,
}

impl AlienAccessMode {
    /// Read-only alien access check using real credentials.
    #[expect(dead_code)]
    pub(crate) const READ_WITH_REAL_CREDS: Self =
        Self::new(AlienAccessKind::Read, CredsSource::RealCreds);
    /// Attach-level alien access check using real credentials.
    pub(crate) const ATTACH_WITH_REAL_CREDS: Self =
        Self::new(AlienAccessKind::Attach, CredsSource::RealCreds);
    /// Read-only alien access check using filesystem credentials.
    pub(crate) const READ_WITH_FS_CREDS: Self =
        Self::new(AlienAccessKind::Read, CredsSource::FsCreds);
    /// Attach-level alien access check using filesystem credentials.
    pub(crate) const ATTACH_WITH_FS_CREDS: Self =
        Self::new(AlienAccessKind::Attach, CredsSource::FsCreds);

    pub(crate) const fn new(kind: AlienAccessKind, creds: CredsSource) -> Self {
        Self { kind, creds }
    }

    pub(crate) const fn kind(self) -> AlienAccessKind {
        self.kind
    }

    pub(crate) const fn creds(self) -> CredsSource {
        self.creds
    }
}
