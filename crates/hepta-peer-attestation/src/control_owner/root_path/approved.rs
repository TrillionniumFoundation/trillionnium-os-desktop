//! Private configured-source admission before the first handoff challenge.
//! Kept separate from the unchanged legacy rooted bridge API inventory.

use super::*;

impl RootPathAttestedHandoffSender {
    pub(crate) fn from_approved(
        connection: RootPathControlConnection,
        accepted: AcceptedStreamCustody,
        policy: ControlOwnerPolicy,
        approved: crate::approved_policy::ApprovedGuard,
    ) -> Result<Self, ControlOwnerError> {
        approved.current()?;
        connection
            .consume_before(|control, deadline, custody| {
                let owner_pid = std::process::id();
                approved.current()?;
                let path = Arc::new(RetainedRootPath::new(custody, deadline)?);
                path.current()?;
                approved.current()?;
                let (mut owner, control, kernel) =
                    ControlPeerOwner::admit(control, policy, owner_pid, deadline)?;
                owner.root_path = Some(path);
                // Install full source custody BEFORE any low-level challenge use.
                owner.retain_approved(&approved)?;
                let budget = owner.current()?;
                let effective = owner.deadline;
                let channel =
                    HandoffSender::from_control(control, kernel, budget).map_err(handoff)?;
                owner.current()?;
                Ok(Self {
                    inner: AttestedHandoffSender {
                        owner_pid,
                        deadline: effective,
                        owner: Some(owner),
                        channel: Some(channel),
                        custody: Some(accepted),
                        cancelled: false,
                    },
                })
            })
            .map_err(path_error)?
    }
}

impl RootPathAttestedHandoffReceiver {
    pub(crate) fn from_approved(
        connection: RootPathControlConnection,
        policy: ControlOwnerPolicy,
        expected_local_path: &Path,
        approved: crate::approved_policy::ApprovedGuard,
    ) -> Result<Self, ControlOwnerError> {
        approved.current()?;
        connection
            .consume_before(|control, deadline, custody| {
                let owner_pid = std::process::id();
                approved.current()?;
                let path = Arc::new(RetainedRootPath::new(custody, deadline)?);
                path.current()?;
                approved.current()?;
                let (mut owner, control, kernel) =
                    ControlPeerOwner::admit(control, policy, owner_pid, deadline)?;
                owner.root_path = Some(path);
                owner.retain_approved(&approved)?;
                owner.current()?;
                let effective = owner.deadline;
                // HandoffReceiver publishes its challenge only after this guard.
                let channel = HandoffReceiver::from_control(control, kernel, expected_local_path)
                    .map_err(handoff)?;
                owner.current()?;
                Ok(Self {
                    inner: AttestedHandoffReceiver {
                        owner_pid,
                        deadline: effective,
                        owner: Some(owner),
                        channel: Some(channel),
                        cancelled: false,
                    },
                })
            })
            .map_err(path_error)?
    }
}
