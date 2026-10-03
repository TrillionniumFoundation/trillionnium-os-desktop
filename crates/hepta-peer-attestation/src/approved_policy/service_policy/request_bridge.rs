//! Separate persistent Source/Owner and original per-request mechanism proof.
//! This bridge grants no action, durable receipt, native health or activation.
use super::*;
use crate::{ControlRequestVerifier, PeerRequestVerifier, PeerRuntimeSnapshot};
use hepta_agent_transport::RemoteRetirementReport;

pub(crate) struct ServiceSessionState {
    source: Arc<ServiceState>,
    owner: ApprovedServiceOwnerVerifier,
    active: AtomicBool,
}
impl ServiceSessionState {
    pub(crate) fn ensure_current(&self) -> Result<(), ApprovedPolicyError> {
        self.source.creator_current()?;
        self.owner.ensure_current()?;
        self.source.inspect()
    }
    // Denial-only scope for pure immutable-policy construction within this
    // original admission. Full Owner executable checks remain at the actual
    // challenge/SCM boundaries; this scope cannot grant action/report authority.
    pub(crate) fn original_owner_root_scope(&self) -> Result<(), ApprovedPolicyError> {
        self.source.creator_current()?;
        if !Arc::ptr_eq(&self.source, &self.owner.state) {
            return Err(ApprovedPolicyError::PeerRefused);
        }
        let checked = (|| {
            self.source.inspect()?;
            self.owner
                .original
                .ensure_alive()
                .map_err(|_| ApprovedPolicyError::PeerRefused)?;
            let original = self
                .owner
                .original
                .original_attested_peer()
                .map_err(|_| ApprovedPolicyError::PeerRefused)?;
            let snapshot = original.snapshot();
            let entry = &self.source.entries[2];
            // These are the original admitted metadata, not a fresh snapshot
            // or a caller assertion of current executable continuity.
            if original.attestor.proc_root != Path::new("/proc")
                || !matches!(original.executable_source, crate::ExecutableSource::Live)
                || snapshot.pid != self.source.creator.pid
                || snapshot.uid != entry.uid
                || snapshot.gid != entry.gid
                || snapshot.systemd_unit.as_deref() != Some(entry.unit.as_str())
                || snapshot.cgroup_v2_path != entry.cgroup
                || snapshot.executable_sha256 != entry.pin
            {
                return Err(ApprovedPolicyError::PeerRefused);
            }
            self.source.inspect()?;
            self.owner
                .original
                .ensure_alive()
                .map_err(|_| ApprovedPolicyError::PeerRefused)?;
            Ok(())
        })();
        self.source.creator_current()?;
        if checked.is_err() {
            // Direct original Owner/source failure retires service continuity,
            // unlike cancellation/expiry of an individual accepted request.
            self.source.retired.store(true, Ordering::SeqCst);
        }
        checked
    }
    pub(crate) fn control_policy(&self) -> Result<ControlOwnerPolicy, ApprovedPolicyError> {
        self.original_owner_root_scope()?;
        let policy = self.source.entries[0].control()?;
        self.original_owner_root_scope()?;
        Ok(policy)
    }
    pub(crate) fn verify_control(
        &self,
        attested: &AttestedPeer,
    ) -> Result<(), ApprovedPolicyError> {
        self.ensure_current()?;
        if attested.attestor.proc_root != Path::new("/proc")
            || !matches!(attested.executable_source, crate::ExecutableSource::Live)
        {
            return Err(ApprovedPolicyError::PeerRefused);
        }
        attested
            .refresh_snapshot(&ProcfsPeerAttestor::default())
            .map_err(|_| ApprovedPolicyError::PeerRefused)?;
        let entry = &self.source.entries[0];
        let snapshot = attested.snapshot();
        if snapshot.uid != entry.uid
            || snapshot.gid != entry.gid
            || snapshot.systemd_unit.as_deref() != Some(entry.unit.as_str())
            || snapshot.cgroup_v2_path != entry.cgroup
            || snapshot.executable_sha256 != entry.pin
        {
            return Err(ApprovedPolicyError::PeerRefused);
        }
        self.ensure_current()
    }
}
struct ServiceRequestSlot {
    session: Arc<ServiceSessionState>,
}
impl Drop for ServiceRequestSlot {
    fn drop(&mut self) {
        // No proc/root/lock access during foreign cleanup. Fork copies do not
        // modify the parent's private heap; closing inherited FD copies only.
        if self.session.source.creator.pid == std::process::id() {
            self.session.active.store(false, Ordering::SeqCst);
        }
    }
}
struct ServiceRequestState {
    session: Arc<ServiceSessionState>,
    deadline: Instant,
    peer: PeerIdentity,
    snapshot: PeerRuntimeSnapshot,
    control: ControlRequestVerifier,
    retired: AtomicBool,
}
impl ServiceRequestState {
    fn same_session(
        &self,
        session: &ApprovedServiceSessionVerifier,
    ) -> Result<(), ApprovedPolicyError> {
        self.session.source.creator_current()?;
        if !Arc::ptr_eq(&self.session, &session.session) {
            return Err(ApprovedPolicyError::PeerRefused);
        }
        self.session.ensure_current()
    }
    fn current(&self, original: &PeerRequestVerifier) -> Result<(), ApprovedPolicyError> {
        self.session.ensure_current()?;
        let checked = (|| {
            remaining(self.session.source.creator.pid, self.deadline)?;
            if self.retired.load(Ordering::SeqCst) {
                return Err(ApprovedPolicyError::PeerRefused);
            }
            self.control
                .verify_pair_current(original)
                .map_err(approval_error)?;
            self.session.ensure_current()?;
            remaining(self.session.source.creator.pid, self.deadline)
        })();
        if checked.is_err() {
            self.retired.store(true, Ordering::SeqCst);
        }
        checked
    }
}

/// The unique persistent Owner custody. Readonly session/request verifiers do
/// not keep this custody alive. It does not reopen a Source or a product journal.
///
/// ```compile_fail
/// use hepta_peer_attestation::ApprovedServiceRequests;
/// let forged = ApprovedServiceRequests { original_owner: None, session: () };
/// ```
pub struct ApprovedServiceRequests {
    original_owner: Option<ApprovedServiceOwnerBinding>,
    session: Arc<ServiceSessionState>,
}
/// Readonly continuity of the exact original Source/session, without a deadline.
/// No caller values can create a new persistent Owner.
pub struct ApprovedServiceSessionVerifier {
    session: Arc<ServiceSessionState>,
}
/// One original root pathname connection, fixed original Control Instant and
/// one active mechanism slot. It cannot create a future request budget.
pub struct ApprovedServiceControlReceiver {
    session: Arc<ServiceSessionState>,
    receiver: Option<RootPathAttestedHandoffReceiver>,
    slot: Arc<ServiceRequestSlot>,
    original_control_deadline: Instant,
}
/// Original Agent stream, independent report owner and non-cloneable action
/// identity custody. Principal text is root metadata, not an action permit.
pub struct ApprovedServiceReceivedRequest {
    session: Arc<ServiceSessionState>,
    stream: UnixStream,
    deadline: Instant,
    custody: ControlRequestCustody,
    reporter: ApprovedServiceRetainedReporter,
    attested: AttestedPeer,
    binding: ApprovedServiceRequestBinding,
}
/// Original Agent custody tied to the same service and actual Control pair.
pub struct ApprovedServiceRequestBinding {
    state: Arc<ServiceRequestState>,
    original: PeerRequestCustody,
    slot: Arc<ServiceRequestSlot>,
}
/// Readonly original request proof. It carries no owning mechanism slot and
/// cannot prolong either original action custody or its twenty-second ceiling.
pub struct ApprovedServiceRequestVerifier {
    state: Arc<ServiceRequestState>,
    original: PeerRequestVerifier,
}
/// Reporting uses original Source/Owner/Control independently from the revoked
/// action. The report remains remote transport data, never a journal fact.
pub struct ApprovedServiceRetainedReporter {
    session: Arc<ServiceSessionState>,
    retained: Option<AttestedRetainedReceiver>,
    deadline: Instant,
    slot: Arc<ServiceRequestSlot>,
}

impl ApprovedServiceRequests {
    pub fn from_owner(owner: ApprovedServiceOwnerBinding) -> Result<Self, ApprovedPolicyError> {
        owner.ensure_current()?;
        let source = Arc::clone(&owner.state);
        let verifier = owner.verifier()?;
        if !Arc::ptr_eq(&source, &verifier.state) {
            return Err(ApprovedPolicyError::PeerRefused);
        }
        let result = Self {
            original_owner: Some(owner),
            session: Arc::new(ServiceSessionState {
                source,
                owner: verifier,
                active: AtomicBool::new(false),
            }),
        };
        result.ensure_current()?;
        Ok(result)
    }
    pub fn ensure_current(&self) -> Result<(), ApprovedPolicyError> {
        self.session.source.creator_current()?;
        self.original_owner
            .as_ref()
            .ok_or(ApprovedPolicyError::PeerRefused)?
            .ensure_current()?;
        self.session.ensure_current()
    }
    pub fn session_verifier(&self) -> Result<ApprovedServiceSessionVerifier, ApprovedPolicyError> {
        self.ensure_current()?;
        Ok(ApprovedServiceSessionVerifier {
            session: Arc::clone(&self.session),
        })
    }
    pub fn bind_control(
        &mut self,
        connection: RootPathControlConnection,
        expected_agent_path: &Path,
    ) -> Result<ApprovedServiceControlReceiver, ApprovedPolicyError> {
        self.ensure_current()?;
        if self
            .session
            .active
            .compare_exchange(false, true, Ordering::SeqCst, Ordering::SeqCst)
            .is_err()
        {
            return Err(ApprovedPolicyError::PeerRefused);
        }
        let slot = Arc::new(ServiceRequestSlot {
            session: Arc::clone(&self.session),
        });
        let mut receiver = RootPathAttestedHandoffReceiver::from_service_control(
            connection,
            &self.session,
            expected_agent_path,
        )
        .map_err(approval_error)?;
        let original_control_deadline = receiver.ensure_current().map_err(approval_error)?;
        remaining(self.session.source.creator.pid, original_control_deadline)?;
        self.ensure_current()?;
        Ok(ApprovedServiceControlReceiver {
            session: Arc::clone(&self.session),
            receiver: Some(receiver),
            slot,
            original_control_deadline,
        })
    }
}
impl ApprovedServiceSessionVerifier {
    pub fn ensure_current(&self) -> Result<(), ApprovedPolicyError> {
        self.session.ensure_current()
    }
}
impl ApprovedServiceControlReceiver {
    pub fn receive_request(self) -> Result<ApprovedServiceReceivedRequest, ApprovedPolicyError> {
        self.session.ensure_current()?;
        remaining(
            self.session.source.creator.pid,
            self.original_control_deadline,
        )?;
        let mut receiver = self.receiver.ok_or(ApprovedPolicyError::PeerRefused)?;
        let transferred = receiver
            .receive_service_control(&self.session)
            .map_err(approval_error)?;
        let session = Arc::clone(&self.session);
        let slot = Arc::clone(&self.slot);
        let original_control_deadline = self.original_control_deadline;
        transferred
            .consume_before(|stream, deadline, custody, mut retained| {
                session.ensure_current()?;
                if deadline > original_control_deadline {
                    return Err(ApprovedPolicyError::PeerRefused);
                }
                remaining(session.source.creator.pid, deadline)?;
                let peer = PeerIdentity::from_stream(&stream)
                    .map_err(|_| ApprovedPolicyError::PeerRefused)?;
                let entry = &session.source.entries[1];
                let attested = ProcfsPeerAttestor::default()
                    .attest(peer, &entry.runtime())
                    .map_err(|_| ApprovedPolicyError::PeerRefused)?;
                if attested.snapshot().executable_sha256 != entry.pin {
                    return Err(ApprovedPolicyError::PeerRefused);
                }
                let original = attested
                    .request_custody()
                    .map_err(|_| ApprovedPolicyError::PeerRefused)?;
                let control = custody.verifier().map_err(approval_error)?;
                control
                    .verify_pair_current(&original.verifier())
                    .map_err(approval_error)?;
                let report_deadline = retained.ensure_current().map_err(approval_error)?;
                if report_deadline != deadline {
                    return Err(ApprovedPolicyError::PeerRefused);
                }
                session.ensure_current()?;
                remaining(session.source.creator.pid, deadline)?;
                let state = Arc::new(ServiceRequestState {
                    session: Arc::clone(&session),
                    deadline,
                    peer,
                    snapshot: attested.snapshot().clone(),
                    control,
                    retired: AtomicBool::new(false),
                });
                let binding = ApprovedServiceRequestBinding {
                    state,
                    original,
                    slot: Arc::clone(&slot),
                };
                let reporter = ApprovedServiceRetainedReporter {
                    session: Arc::clone(&session),
                    retained: Some(retained),
                    deadline,
                    slot,
                };
                Ok(ApprovedServiceReceivedRequest {
                    session,
                    stream,
                    deadline,
                    custody,
                    reporter,
                    attested,
                    binding,
                })
            })
            .map_err(approval_error)?
    }
}
impl ApprovedServiceReceivedRequest {
    pub fn original_deadline(&self) -> Result<Instant, ApprovedPolicyError> {
        self.binding.slot_current()?;
        self.binding
            .state
            .current(&self.binding.original.verifier())?;
        Ok(self.deadline)
    }
    // One owned consume only: the unchanged Reporter post guard is the
    // immediately adjacent full Source/Owner pre guard of the original pair.
    // This returns no reusable proof and keeps both real Control refreshes.
    fn ensure_consume_current(&mut self) -> Result<(), ApprovedPolicyError> {
        self.session.source.creator_current()?;
        if !Arc::ptr_eq(&self.session, &self.reporter.session)
            || !Arc::ptr_eq(&self.session, &self.binding.state.session)
            || !Arc::ptr_eq(&self.reporter.slot, &self.binding.slot)
            || self.deadline != self.reporter.deadline
            || self.deadline != self.binding.state.deadline
        {
            return Err(ApprovedPolicyError::PeerRefused);
        }
        self.reporter.ensure_current()?;
        let state = &self.binding.state;
        let checked = (|| {
            remaining(state.session.source.creator.pid, state.deadline)?;
            if state.retired.load(Ordering::SeqCst) {
                return Err(ApprovedPolicyError::PeerRefused);
            }
            state
                .control
                .verify_pair_current(&self.binding.original.verifier())
                .map_err(approval_error)?;
            state.session.ensure_current()?;
            remaining(state.session.source.creator.pid, state.deadline)
        })();
        if checked.is_err() {
            state.retired.store(true, Ordering::SeqCst);
        }
        checked
    }
    pub fn consume_with_request_binding<T>(
        self,
        consumer: impl FnOnce(
            UnixStream,
            Instant,
            ControlRequestCustody,
            ApprovedServiceRetainedReporter,
            AttestedPeer,
            &str,
            ApprovedServiceRequestBinding,
        ) -> T,
    ) -> Result<T, ApprovedPolicyError> {
        self.binding.slot_current()?;
        remaining(self.session.source.creator.pid, self.deadline)?;
        let mut received = self;
        received.ensure_consume_current()?;
        let Self {
            session,
            stream,
            deadline,
            custody,
            reporter,
            attested,
            binding,
        } = received;
        let principal = session.source.entries[1].principal.as_str();
        let result = consumer(
            stream, deadline, custody, reporter, attested, principal, binding,
        );
        // Consumer may legitimately retire action/report custody. Do not make
        // those retired requests a prerequisite of persistent Source lifetime.
        session.ensure_current()?;
        remaining(session.source.creator.pid, deadline)?;
        Ok(result)
    }
}
impl ApprovedServiceRequestBinding {
    fn slot_current(&self) -> Result<(), ApprovedPolicyError> {
        self.state.session.source.creator_current()?;
        if !Arc::ptr_eq(&self.slot.session, &self.state.session)
            || !self.state.session.active.load(Ordering::SeqCst)
        {
            return Err(ApprovedPolicyError::PeerRefused);
        }
        Ok(())
    }
    pub fn verify_for_service(
        &self,
        session: &ApprovedServiceSessionVerifier,
    ) -> Result<(PeerIdentity, PeerRuntimeSnapshot, String), ApprovedPolicyError> {
        self.state.same_session(session)?;
        self.slot_current()?;
        self.state.current(&self.original.verifier())?;
        Ok((
            self.state.peer,
            self.state.snapshot.clone(),
            self.state.session.source.entries[1].principal.clone(),
        ))
    }
    pub fn verifier_for_service(
        &self,
        session: &ApprovedServiceSessionVerifier,
    ) -> Result<ApprovedServiceRequestVerifier, ApprovedPolicyError> {
        self.state.same_session(session)?;
        self.slot_current()?;
        self.state.current(&self.original.verifier())?;
        Ok(ApprovedServiceRequestVerifier {
            state: Arc::clone(&self.state),
            original: self.original.verifier(),
        })
    }
}
impl ApprovedServiceRequestVerifier {
    pub fn verify_for_service(
        &self,
        session: &ApprovedServiceSessionVerifier,
    ) -> Result<(), ApprovedPolicyError> {
        self.state.same_session(session)?;
        self.state.current(&self.original)
    }
    pub fn with_original_pair<T>(
        &self,
        session: &ApprovedServiceSessionVerifier,
        consumer: impl FnOnce(&ProcfsPeerAttestor, &AttestedPeer, &ControlRequestVerifier, Instant) -> T,
    ) -> Result<T, ApprovedPolicyError> {
        self.verify_for_service(session)?;
        let original = self
            .original
            .original_attested_peer()
            .map_err(|_| ApprovedPolicyError::PeerRefused)?;
        let result = consumer(
            &ProcfsPeerAttestor::default(),
            original,
            &self.state.control,
            self.state.deadline,
        );
        self.verify_for_service(session)?;
        Ok(result)
    }
}
impl ApprovedServiceRetainedReporter {
    fn ensure_current(&mut self) -> Result<Instant, ApprovedPolicyError> {
        self.session.source.creator_current()?;
        if !Arc::ptr_eq(&self.slot.session, &self.session)
            || !self.session.active.load(Ordering::SeqCst)
        {
            return Err(ApprovedPolicyError::PeerRefused);
        }
        let checked = (|| {
            self.session.ensure_current()?;
            remaining(self.session.source.creator.pid, self.deadline)?;
            let deadline = self
                .retained
                .as_mut()
                .ok_or(ApprovedPolicyError::PeerRefused)?
                .ensure_current()
                .map_err(approval_error)?;
            if deadline != self.deadline {
                return Err(ApprovedPolicyError::PeerRefused);
            }
            self.session.ensure_current()?;
            remaining(self.session.source.creator.pid, deadline)?;
            Ok(deadline)
        })();
        if checked.is_err() {
            self.retained.take();
        }
        checked
    }
    pub fn original_deadline(&mut self) -> Result<Instant, ApprovedPolicyError> {
        self.ensure_current()
    }
    pub fn poll_cancel(&mut self) -> Result<bool, ApprovedPolicyError> {
        self.ensure_current()?;
        let checked = (|| {
            let cancelled = self
                .retained
                .as_mut()
                .ok_or(ApprovedPolicyError::PeerRefused)?
                .poll_cancel()
                .map_err(approval_error)?;
            self.session.ensure_current()?;
            remaining(self.session.source.creator.pid, self.deadline)?;
            Ok(cancelled)
        })();
        if checked.is_err() {
            self.retained.take();
        }
        checked
    }
    pub fn send_remote_report(
        &mut self,
        report: RemoteRetirementReport,
    ) -> Result<(), ApprovedPolicyError> {
        self.ensure_current()?;
        let checked = (|| {
            let mut retained = self
                .retained
                .take()
                .ok_or(ApprovedPolicyError::PeerRefused)?;
            retained
                .send_remote_report(report)
                .map_err(approval_error)?;
            self.session.ensure_current()?;
            remaining(self.session.source.creator.pid, self.deadline)
        })();
        self.retained.take();
        checked
    }
}
