//! Explicit original Root connection transfer, without callback authority.
//! The failure guard revokes only this original connection's kernel/path proof.
use super::*;
use std::result::Result;

struct OriginalTransferGuard {
    scope: Arc<ConnectionScope>,
    completed: bool,
}
impl Drop for OriginalTransferGuard {
    fn drop(&mut self) {
        // No FD access, inherited lock, shutdown, policy or shared path mutation.
        // Escaped custody/verifiers retain this exact scope, so errors and
        // callback unwind remain closed even if a caller leaks the custody.
        if !self.completed {
            self.scope.current.store(false, Ordering::Release);
        }
    }
}

fn verify_moved(scope: &ConnectionScope, fd: RawFd) -> Result<(), RootControlPathError> {
    creator(scope.owner_pid)?;
    remaining(scope.owner_pid, scope.deadline)?;
    scope.check()?;
    // Unlike the old clone-only scope check, these reads address the actual FD
    // moved into the consumer. The expected identity was captured at admission.
    let flags = unsafe { libc::fcntl(fd, libc::F_GETFD) };
    if flags < 0
        || flags & libc::FD_CLOEXEC == 0
        || option::<libc::c_int>(fd, libc::SO_DOMAIN)? != libc::AF_UNIX
        || option::<libc::c_int>(fd, libc::SO_TYPE)? != libc::SOCK_SEQPACKET
        || option::<libc::c_int>(fd, libc::SO_ACCEPTCONN)? != 0
        || scope.socket_identity != Identity::from(&stat(fd)?)
        || scope.cookie == 0
        || scope.cookie != option::<u64>(fd, libc::SO_COOKIE)?
    {
        return Err(RootControlPathError::PeerRefused);
    }
    let cred = option::<libc::ucred>(fd, libc::SO_PEERCRED)?;
    if cred.pid <= 0
        || scope.identity
            != (PeerIdentity {
                pid: Some(cred.pid as u32),
                uid: cred.uid,
                gid: cred.gid,
            })
    {
        return Err(RootControlPathError::PeerRefused);
    }
    scope.check()?;
    remaining(scope.owner_pid, scope.deadline)?;
    Ok(())
}

impl RootPathControlConnection {
    /// Transfer the original FD with admission-time identity checks on the
    /// actual moved endpoint before and after the callback. This versioned
    /// mechanism API grants no permission for the callback's side effects.
    /// The product factory constructs a receiver that still owns this FD.
    pub fn consume_service_control_before<T>(
        self,
        consumer: impl FnOnce(OwnedFd, Instant, RootControlPathCustody) -> T,
    ) -> Result<T, RootControlPathError> {
        creator(self.owner_pid)?;
        let scope = Arc::clone(
            &self
                .custody
                .as_ref()
                .ok_or(RootControlPathError::Retired)?
                .scope,
        );
        let mut guard = OriginalTransferGuard {
            scope,
            completed: false,
        };
        remaining(self.owner_pid, self.deadline)?;
        self.deadline()?;
        let fd = self
            .socket
            .as_ref()
            .ok_or(RootControlPathError::Retired)?
            .as_raw_fd();
        verify_moved(&guard.scope, fd)?;
        // Delegate the complete unchanged legacy movement once. No recapture,
        // duplicate FD, new future Instant or replacement custody is created.
        let result = self.consume_before(consumer)?;
        if let Err(error) = verify_moved(&guard.scope, fd) {
            // Revoke before dropping T; its destructor or leaked verifier must
            // not observe a still-current scope after this failed post-proof.
            guard.scope.current.store(false, Ordering::Release);
            return Err(error);
        }
        guard.completed = true;
        Ok(result)
    }
}
