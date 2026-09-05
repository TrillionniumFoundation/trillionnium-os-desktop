//! Request-scoped custody of an existing attestation, across an in-process queue.
//! This is identity continuity, not a capability or semantic authorization.
use super::{AttestationError, AttestedPeer};
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};

#[derive(Debug)]
struct LeaseState {
    peer: AttestedPeer,
    revoked: AtomicBool,
}

/// The single request owner. Dropping it revokes every verifier clone, even
/// when an engine queue or backend still retains one. It is not cloneable.
///
/// ```compile_fail
/// use hepta_peer_attestation::PeerRequestCustody;
/// fn requires_clone<T: Clone>() {}
/// requires_clone::<PeerRequestCustody>();
/// ```
#[derive(Debug)]
pub struct PeerRequestCustody {
    state: Arc<LeaseState>,
}

/// Cloneable identity verifier retaining the *same* pidfd and executable source.
/// It cannot extend custody, reset revocation or choose a replacement process.
#[derive(Debug, Clone)]
pub struct PeerRequestVerifier {
    state: Arc<LeaseState>,
}

impl AttestedPeer {
    /// Duplicate this pidfd with CLOEXEC, keeping the original attestation's
    /// snapshot, procfs root and live-or-trusted-path executable source. No new
    /// PID lookup is allowed to substitute for the originally retained pidfd.
    pub fn request_custody(&self) -> Result<PeerRequestCustody, AttestationError> {
        self.ensure_alive()?;
        let peer = AttestedPeer {
            snapshot: self.snapshot.clone(),
            pidfd: self.pidfd.try_clone().map_err(AttestationError::Pidfd)?,
            executable_source: self.executable_source.clone(),
            attestor: self.attestor.clone(),
        };
        let custody = PeerRequestCustody {
            state: Arc::new(LeaseState {
                peer,
                revoked: AtomicBool::new(false),
            }),
        };
        custody.verifier().verify_current()?;
        Ok(custody)
    }
}

impl PeerRequestCustody {
    pub fn verifier(&self) -> PeerRequestVerifier {
        PeerRequestVerifier {
            state: self.state.clone(),
        }
    }

    /// One-way revocation, independent from cancellation and the wall clock.
    pub fn revoke(&self) {
        self.state.revoked.store(true, Ordering::SeqCst);
    }
}
impl Drop for PeerRequestCustody {
    fn drop(&mut self) {
        self.revoke();
    }
}

impl PeerRequestVerifier {
    /// Cheap liveness check for wait loops: no procfs reads or image hashing.
    pub fn ensure_alive(&self) -> Result<(), AttestationError> {
        if self.state.revoked.load(Ordering::SeqCst) {
            return Err(AttestationError::RequestCustodyRevoked);
        }
        if let Err(error) = self.state.peer.ensure_alive() {
            self.state.revoked.store(true, Ordering::SeqCst);
            return Err(error);
        }
        if self.state.revoked.load(Ordering::SeqCst) {
            return Err(AttestationError::RequestCustodyRevoked);
        }
        Ok(())
    }

    /// Re-read all bounded identity facts through the original source. Any
    /// observed error irreversibly revokes the lease; restoring old bytes later
    /// cannot revive it. Revocation and pidfd liveness are rechecked afterwards.
    /// This may perform file I/O; it does not promise a hard realtime bound.
    pub fn verify_current(&self) -> Result<(), AttestationError> {
        self.ensure_alive()?;
        if let Err(error) = self.state.peer.refresh_snapshot(&self.state.peer.attestor) {
            self.state.revoked.store(true, Ordering::SeqCst);
            return Err(error);
        }
        self.ensure_alive()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{PeerRuntimePolicy, ProcfsPeerAttestor, hash_executable};
    use hepta_agent_transport::PeerIdentity;
    use std::fs;
    use std::os::fd::AsRawFd;
    use std::os::unix::net::UnixStream;
    use std::path::PathBuf;
    use std::process::{Child, Command, Stdio};
    use std::sync::atomic::AtomicU64;
    use std::thread;

    static NEXT: AtomicU64 = AtomicU64::new(0);
    fn self_peer() -> (ProcfsPeerAttestor, AttestedPeer) {
        let (left, _right) = UnixStream::pair().unwrap();
        let peer = PeerIdentity::from_stream(&left).unwrap();
        let attestor = ProcfsPeerAttestor::default();
        let snapshot = attestor.read_snapshot(peer.pid.unwrap()).unwrap();
        let attested = attestor
            .attest(peer, &PeerRuntimePolicy::exact(&snapshot))
            .unwrap();
        (attestor, attested)
    }
    struct Temp(PathBuf);
    impl Temp {
        fn new() -> Self {
            let path = std::env::temp_dir().join(format!(
                "request-lease-{}-{}",
                std::process::id(),
                NEXT.fetch_add(1, Ordering::SeqCst)
            ));
            fs::create_dir(&path).unwrap();
            Self(path)
        }
    }
    impl Drop for Temp {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.0);
        }
    }
    fn fake_peer(root: &Temp) -> (ProcfsPeerAttestor, AttestedPeer) {
        let pid = std::process::id();
        let dir = root.0.join(pid.to_string());
        fs::create_dir(&dir).unwrap();
        fs::write(
            dir.join("status"),
            "Uid:\t1000\t1000\t1000\t1000\nGid:\t1001\t1001\t1001\t1001\n",
        )
        .unwrap();
        let mut stat = vec!["S"; 20];
        stat[19] = "987654";
        fs::write(
            dir.join("stat"),
            format!("{pid} (fixture) {}\n", stat.join(" ")),
        )
        .unwrap();
        fs::write(dir.join("cgroup"), "0::/system.slice/fixture.service\n").unwrap();
        fs::write(dir.join("exe"), b"fixture").unwrap();
        let attestor = ProcfsPeerAttestor::new(&root.0);
        let snapshot = attestor.read_snapshot(pid).unwrap();
        let peer = PeerIdentity {
            pid: Some(pid),
            uid: 1000,
            gid: 1001,
        };
        let attested = attestor
            .attest(peer, &PeerRuntimePolicy::exact(&snapshot))
            .unwrap();
        (attestor, attested)
    }

    #[test]
    fn lease_verifier_is_send_sync_and_live_procfs_refreshes_on_other_thread() {
        fn send_sync<T: Send + Sync>() {}
        send_sync::<PeerRequestVerifier>();
        let (_attestor, peer) = self_peer();
        let custody = peer.request_custody().unwrap();
        let verifier = custody.verifier();
        thread::spawn(move || verifier.verify_current())
            .join()
            .unwrap()
            .unwrap();
    }
    #[test]
    fn custody_drop_revokes_all_retained_clones() {
        let (_a, p) = self_peer();
        let custody = p.request_custody().unwrap();
        let a = custody.verifier();
        let b = a.clone();
        drop(custody);
        assert!(matches!(
            a.ensure_alive(),
            Err(AttestationError::RequestCustodyRevoked)
        ));
        assert!(matches!(
            b.verify_current(),
            Err(AttestationError::RequestCustodyRevoked)
        ));
    }
    #[test]
    fn explicit_revoke_cannot_be_reset_but_new_request_has_new_custody() {
        let (_a, p) = self_peer();
        let one = p.request_custody().unwrap();
        let old = one.verifier();
        one.revoke();
        one.revoke();
        let fresh = p.request_custody().unwrap();
        fresh.verifier().verify_current().unwrap();
        assert!(old.verify_current().is_err());
    }
    #[test]
    fn original_peer_drop_keeps_only_request_scoped_pidfd_custody() {
        let (_a, p) = self_peer();
        let custody = p.request_custody().unwrap();
        let verifier = custody.verifier();
        drop(p);
        verifier.verify_current().unwrap();
        drop(custody);
        assert!(verifier.ensure_alive().is_err());
    }
    #[test]
    fn duplicated_pidfd_is_distinct_cloexec_and_tracks_same_live_peer() {
        let (_a, p) = self_peer();
        let custody = p.request_custody().unwrap();
        let fd = custody.state.peer.pidfd.as_raw_fd();
        assert_ne!(fd, p.pidfd.as_raw_fd());
        // SAFETY: fcntl F_GETFD observes a live owned descriptor and retains no pointer.
        let flags = unsafe { libc::fcntl(fd, libc::F_GETFD) };
        assert!(flags >= 0);
        assert_ne!(flags & libc::FD_CLOEXEC, 0);
        custody.verifier().ensure_alive().unwrap();
    }
    #[test]
    fn revoked_scope_is_seen_by_waiting_foreign_thread() {
        let (_a, p) = self_peer();
        let custody = p.request_custody().unwrap();
        let verifier = custody.verifier();
        let (tx, rx) = std::sync::mpsc::sync_channel(1);
        let thread = thread::spawn(move || {
            rx.recv().unwrap();
            verifier.verify_current()
        });
        drop(custody);
        tx.send(()).unwrap();
        assert!(thread.join().unwrap().is_err());
    }
    #[test]
    fn changed_executable_identity_latches_failure_even_after_bytes_restored() {
        let root = Temp::new();
        let (_a, p) = fake_peer(&root);
        let custody = p.request_custody().unwrap();
        let verifier = custody.verifier();
        let exe = root.0.join(std::process::id().to_string()).join("exe");
        fs::write(&exe, b"changed").unwrap();
        assert!(verifier.verify_current().is_err());
        fs::write(exe, b"fixture").unwrap();
        assert!(matches!(
            verifier.verify_current(),
            Err(AttestationError::RequestCustodyRevoked)
        ));
    }
    #[test]
    fn identical_snapshot_from_replacement_proc_root_is_not_original_source() {
        let root = Temp::new();
        let (original, p) = fake_peer(&root);
        let replacement = Temp::new();
        let (other, _) = fake_peer(&replacement);
        assert_eq!(
            original.read_snapshot(std::process::id()).unwrap(),
            other.read_snapshot(std::process::id()).unwrap()
        );
        assert!(matches!(
            p.refresh_snapshot(&other),
            Err(AttestationError::AttestorSourceChanged)
        ));
        p.request_custody()
            .unwrap()
            .verifier()
            .verify_current()
            .unwrap();
    }
    #[test]
    fn unreadable_source_is_not_retried_as_cached_identity() {
        let root = Temp::new();
        let (_a, p) = fake_peer(&root);
        let custody = p.request_custody().unwrap();
        let verifier = custody.verifier();
        fs::remove_file(root.0.join(std::process::id().to_string()).join("stat")).unwrap();
        assert!(verifier.verify_current().is_err());
        assert!(verifier.ensure_alive().is_err());
    }
    struct ChildGuard(Child);
    impl Drop for ChildGuard {
        fn drop(&mut self) {
            let _ = self.0.kill();
            let _ = self.0.wait();
        }
    }
    #[test]
    fn actual_child_exit_revokes_live_pidfd_request() {
        let mut child = ChildGuard(
            Command::new("/usr/bin/sleep")
                .arg("30")
                .stdin(Stdio::null())
                .stdout(Stdio::null())
                .stderr(Stdio::null())
                .spawn()
                .unwrap(),
        );
        let attestor = ProcfsPeerAttestor::default();
        let pid = child.0.id();
        // /proc may briefly expose the pre-exec image. Wait for exact sleep
        // identity before creating the attestation; this is test setup only.
        let expected = hash_executable(std::path::Path::new("/usr/bin/sleep")).unwrap();
        let deadline = std::time::Instant::now() + std::time::Duration::from_secs(5);
        let snapshot = loop {
            let s = attestor.read_snapshot(pid).unwrap();
            if s.executable_sha256 == expected {
                break s;
            }
            assert!(std::time::Instant::now() < deadline);
            thread::yield_now();
        };
        let peer = attestor
            .attest(
                PeerIdentity {
                    pid: Some(pid),
                    uid: snapshot.uid,
                    gid: snapshot.gid,
                },
                &PeerRuntimePolicy::exact(&snapshot),
            )
            .unwrap();
        let custody = peer.request_custody().unwrap();
        let verifier = custody.verifier();
        verifier.verify_current().unwrap();
        child.0.kill().unwrap();
        child.0.wait().unwrap();
        assert!(matches!(
            verifier.ensure_alive(),
            Err(AttestationError::PeerProcessExited)
        ));
        assert!(matches!(
            verifier.verify_current(),
            Err(AttestationError::RequestCustodyRevoked)
        ));
        assert!(peer.request_custody().is_err());
    }
    #[cfg(any(
        feature = "qualification-static-attestation",
        feature = "development-static-attestation"
    ))]
    #[test]
    fn lease_preserves_static_path_source_instead_of_substituting_live_exe() {
        let (attestor, p) = self_peer();
        let trusted = crate::hash_trusted_executable("/usr/bin/true").unwrap();
        let peer = PeerIdentity {
            pid: Some(p.snapshot.pid),
            uid: p.snapshot.uid,
            gid: p.snapshot.gid,
        };
        let snapshot = attestor
            .read_snapshot_with_source(
                p.snapshot.pid,
                &super::super::ExecutableSource::Static(trusted.clone()),
            )
            .unwrap();
        let p = attestor
            .attest_with_static_executable_digest(
                peer,
                &PeerRuntimePolicy::exact(&snapshot),
                &trusted,
            )
            .unwrap();
        assert_ne!(
            p.snapshot.executable_sha256,
            attestor
                .read_snapshot(peer.pid.unwrap())
                .unwrap()
                .executable_sha256
        );
        let custody = p.request_custody().unwrap();
        let verifier = custody.verifier();
        thread::spawn(move || verifier.verify_current())
            .join()
            .unwrap()
            .unwrap();
    }
}
