//! Configured-source product admission. The retained terminal path stays in
//! its legacy module; this additive entry supplies no public principal grant.

use super::product_control_wait::{ProductControlMonitor, RetainedProductConnection};
use super::*;
use hepta_peer_attestation::ControlRetainedAcceptedStream;

/// Approved configuration and the same original Agent/control scopes. Principal
/// fields are private; this grants no TaskFlow operations or PageOwner authority.
pub struct ApprovedRetainedProductConnection {
    owner_pid: u32,
    inner: RetainedProductConnection,
    principal: TaskFlowPrincipal,
}
impl ApprovedRetainedProductConnection {
    pub fn from_received(
        received: ControlRetainedAcceptedStream,
        selection: hepta_peer_attestation::ApprovedAgentSelection,
    ) -> Result<(Self, ProductControlMonitor), ProductDispatchError> {
        selection
            .admit_retained(received)
            .map_err(approved_error)?
            .consume_before(
                |stream, deadline, custody, mut retained, attested, principal_id| {
                    let owner_pid = std::process::id();
                    product_time_remaining(deadline)?;
                    let snapshot = attested.snapshot();
                    // Every field below was already compared with the selected
                    // configured Agent entry by the fixed live admission route.
                    let principal = TaskFlowPrincipal {
                        principal_id: principal_id.to_owned(),
                        expected_uid: snapshot.uid,
                        expected_gid: snapshot.gid,
                        expected_systemd_unit: snapshot
                            .systemd_unit
                            .clone()
                            .ok_or(ProductDispatchError::PeerRefused)?,
                        expected_cgroup_v2_path: snapshot.cgroup_v2_path.clone(),
                        expected_executable_sha256: snapshot.executable_sha256.clone(),
                    };
                    let peer = PeerIdentity::from_stream(&stream)
                        .map_err(|_| ProductDispatchError::PeerRefused)?;
                    if peer.pid != Some(snapshot.pid)
                        || peer.uid != snapshot.uid
                        || peer.gid != snapshot.gid
                    {
                        return Err(ProductDispatchError::PeerRefused);
                    }
                    let interrupt = stream
                        .try_clone()
                        .map_err(|_| ProductDispatchError::PeerRefused)?;
                    product_time_remaining(deadline)?;
                    let connection = AcceptedProductConnection {
                        stream: Some(stream),
                        peer,
                        attestor: ProcfsPeerAttestor::default(),
                        attested,
                        deadline,
                        control: Arc::new(ConnectionControl {
                            owner_pid,
                            transport: Mutex::new(Some(interrupt)),
                            custodian: Some(custody),
                            ..ConnectionControl::default()
                        }),
                    };
                    connection.ensure_control_current()?;
                    let report_deadline =
                        deadline.min(retained.ensure_current().map_err(control_error)?);
                    let cancellation = connection.cancellation();
                    let (sender, receiver) = mpsc::sync_channel(1);
                    product_time_remaining(deadline)?;
                    Ok((
                        Self {
                            owner_pid,
                            principal,
                            inner: RetainedProductConnection {
                                owner_pid,
                                connection: Some(connection),
                                terminal: Some(sender),
                                deadline,
                                report_deadline,
                            },
                        },
                        ProductControlMonitor {
                            owner_pid,
                            deadline: report_deadline,
                            retained: Some(retained),
                            cancellation,
                            receiver: Some(receiver),
                            finished: false,
                        },
                    ))
                },
            )
            .map_err(approved_error)?
    }
    pub fn deadline(&self) -> Result<Instant, ProductDispatchError> {
        if self.owner_pid != std::process::id() {
            return Err(ProductDispatchError::PeerRefused);
        }
        self.inner
            .connection
            .as_ref()
            .ok_or(ProductDispatchError::Closed)?
            .ensure_control_current()?;
        self.inner.deadline()
    }
    pub fn cancellation(&self) -> Result<ProductConnectionCancellation, ProductDispatchError> {
        self.deadline()?;
        self.inner.cancellation()
    }
}
fn approved_error(error: hepta_peer_attestation::ApprovedPolicyError) -> ProductDispatchError {
    match error {
        hepta_peer_attestation::ApprovedPolicyError::DeadlineExceeded => {
            ProductDispatchError::DeadlineExceeded
        }
        hepta_peer_attestation::ApprovedPolicyError::InvalidConfiguration => {
            ProductDispatchError::InvalidConfiguration
        }
        _ => ProductDispatchError::PeerRefused,
    }
}
impl ProductRequestCoordinator {
    pub fn from_approved_retained_connection(
        bootstrap: &ApprovedRetainedProductConnection,
        endpoint: ServoRuntimeEndpoint,
        journal: ReceiptJournal,
        image_id: String,
        restart_policy: RestartPolicy,
    ) -> Result<Self, ProductDispatchError> {
        bootstrap.deadline()?;
        Self::from_retained_connection(
            bootstrap.principal.clone(),
            &bootstrap.inner,
            endpoint,
            journal,
            image_id,
            restart_policy,
        )
    }
    pub fn serve_approved_retained_connection(
        &mut self,
        connection: ApprovedRetainedProductConnection,
    ) -> Result<ServiceEvidence, ProductDispatchError> {
        self.ensure_owner()?;
        connection.deadline()?;
        if connection.owner_pid != self.owner_pid || connection.principal != self.principal {
            return Err(ProductDispatchError::PeerRefused);
        }
        self.serve_retained_connection(connection.inner)
    }
}
