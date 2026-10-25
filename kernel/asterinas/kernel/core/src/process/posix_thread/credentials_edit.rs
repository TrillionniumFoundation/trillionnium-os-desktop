// SPDX-License-Identifier: MPL-2.0

//! Publication transaction for already-live credentials and their memory image.

use core::ops::Deref;

use aster_rights::ReadWriteOp;

use crate::{
    prelude::*,
    process::{Credentials, Gid, Uid, credentials::capabilities::CapSet},
};

/// The shared image mutex, not a per-process mutex, serializes CLONE_VM peers.
/// All sensitive alien-access checks take this lock before reading credentials
/// and retain it until the authorized resource has been captured. Credentials
/// may change inside the transaction, but cannot be observed by these checks
/// before the matching dumpability reset. Writable capabilities cannot escape.
pub(super) struct CredentialsEdit<'a> {
    credentials: &'a Credentials<ReadWriteOp>,
    dumpable: MutexGuard<'a, bool>,
    old_ids: (Uid, Gid, Uid, Gid),
    old_permitted: CapSet,
}

impl<'a> CredentialsEdit<'a> {
    pub(super) fn new(
        credentials: &'a Credentials<ReadWriteOp>,
        dumpable: MutexGuard<'a, bool>,
    ) -> Self {
        Self {
            credentials,
            dumpable,
            old_ids: Self::ids(credentials),
            old_permitted: credentials.permitted_capset(),
        }
    }

    fn ids(credentials: &Credentials<ReadWriteOp>) -> (Uid, Gid, Uid, Gid) {
        (
            credentials.euid(),
            credentials.egid(),
            credentials.fsuid(),
            credentials.fsgid(),
        )
    }
}

impl Deref for CredentialsEdit<'_> {
    type Target = Credentials<ReadWriteOp>;

    fn deref(&self) -> &Self::Target {
        self.credentials
    }
}

impl Drop for CredentialsEdit<'_> {
    fn drop(&mut self) {
        // Linux commit_creds: unchanged IDs and a mere decrease in permitted
        // capabilities preserve dumpability. Failed/no-op/query calls do too.
        if self.old_ids != Self::ids(self.credentials)
            || !self
                .old_permitted
                .contains(self.credentials.permitted_capset())
        {
            *self.dumpable = false;
        }
    }
}

#[cfg(ktest)]
mod tests;
