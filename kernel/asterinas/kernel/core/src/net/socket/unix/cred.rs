// SPDX-License-Identifier: MPL-2.0

use aster_rights::{Dup, Read, ReadDupOp, ReadOp, TRights};
use aster_rights_proc::require;

use crate::{
    prelude::*,
    process::{Credentials, Gid, Pid, Uid, posix_thread::AsPosixThread},
};

/// Identity captured at connection creation or message send, never a live view
/// of the sender's mutable credential object. Group snapshots share the original
/// immutable owner, so message capture does not copy or allocate a group list.
pub(super) struct SocketCred<R = ReadOp> {
    real: CUserCred,
    effective: CUserCred,
    groups: Arc<BTreeSet<Gid>>,
    rights: R,
}

impl SocketCred<ReadOp> {
    #[cfg(ktest)]
    pub(super) fn from_posix_thread_for_test(
        thread: &crate::process::posix_thread::PosixThread,
    ) -> Self {
        Self::capture(thread.process().pid(), &thread.credentials())
    }

    pub(super) fn new_current() -> Self {
        let pid = current!().pid();
        let cred = current_thread!().as_posix_thread().unwrap().credentials();
        Self::capture(pid, &cred)
    }
}

impl SocketCred<ReadDupOp> {
    pub(super) fn new_current() -> Self {
        let pid = current!().pid();
        let cred = current_thread!().as_posix_thread().unwrap().credentials();
        Self::capture(pid, &cred)
    }
}

impl<R: TRights> SocketCred<R> {
    // Production capture reads only the current thread's credentials. Other
    // threads cannot mutate that owner; live updates use its original image
    // transaction. The test constructor accepts only controlled fixture owners.
    fn capture(pid: Pid, cred: &Credentials<ReadOp>) -> Self {
        Self {
            real: CUserCred {
                pid,
                uid: cred.ruid(),
                gid: cred.rgid(),
            },
            effective: CUserCred {
                pid,
                uid: cred.euid(),
                gid: cred.egid(),
            },
            groups: cred.groups(),
            rights: R::new(),
        }
    }

    #[require(R > Read)]
    pub(super) fn to_effective_c_cred(&self) -> CUserCred {
        self.effective
    }

    #[require(R > Read)]
    pub(super) fn to_real_c_cred(&self) -> CUserCred {
        self.real
    }

    #[require(R > Read)]
    pub(super) fn groups(&self) -> Arc<[Gid]> {
        self.groups.iter().cloned().collect()
    }

    #[require(R > R1)]
    pub(super) fn restrict<R1: TRights>(self) -> SocketCred<R1> {
        let Self {
            real,
            effective,
            groups,
            ..
        } = self;
        SocketCred {
            real,
            effective,
            groups,
            rights: R1::new(),
        }
    }

    #[require(R > Dup)]
    pub(super) fn dup(&self) -> Self {
        Self {
            real: self.real,
            effective: self.effective,
            groups: self.groups.clone(),
            rights: self.rights,
        }
    }
}

/// `struct ucred` in Linux.
///
/// Reference: <https://elixir.bootlin.com/linux/v6.15/source/include/linux/socket.h#L183>.
#[repr(C)]
#[derive(Clone, Copy, Debug, Eq, PartialEq, Pod)]
pub(crate) struct CUserCred {
    pid: Pid,
    uid: Uid,
    gid: Gid,
}

impl CUserCred {
    pub(in crate::net) const fn new_invalid() -> Self {
        Self {
            pid: 0,
            uid: Uid::INVALID,
            gid: Gid::INVALID,
        }
    }

    pub(in crate::net) const fn new_overflow() -> Self {
        Self {
            pid: 0,
            uid: Uid::OVERFLOW,
            gid: Gid::OVERFLOW,
        }
    }
}

#[cfg(ktest)]
mod tests;
