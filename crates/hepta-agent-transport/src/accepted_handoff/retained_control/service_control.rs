//! Explicit service-transport Control identity. This is mechanism continuity,
//! not root policy, action authority, durability or a new lifetime.
use super::*;
use crate::MAX_HANDOFF_BUDGET;
use std::time::Duration;

impl HandoffReceiver {
    /// Consume the unchanged raw receive with the creation-time Control socket
    /// identity checked before SCM and on the actual returned transaction.
    /// The bounded wait is independent of the original accepted clock ceiling.
    pub fn receive_retained_service_control(
        self,
        wait_budget: Duration,
    ) -> Result<RetainedReceivedAcceptedStream, HandoffError> {
        self.channel.owner()?;
        if wait_budget.is_zero() || wait_budget > MAX_HANDOFF_BUDGET {
            return Err(HandoffError::InvalidConfiguration);
        }
        let fd = self.channel.verify()?;
        self.channel.original_identity.verify(fd)?;
        let mut transferred = self.receive_retained(wait_budget)?;
        let checked = (|| {
            // The old receiver is moved. Only the actual returned endpoint is
            // relevant, with its original identity carried by the same stream.
            let pending = &mut transferred.pending;
            pending.transaction.channel.owner()?;
            let fd = pending.transaction.channel.verify()?;
            pending.transaction.channel.original_identity.verify(fd)?;
            pending.transaction.readiness_enabled = true;
            pending.ensure_current()?;
            transferred.received.verify()?;
            Ok(())
        })();
        if checked.is_err() {
            transferred.pending.transaction.channel.retire();
        }
        checked?;
        Ok(transferred)
    }
}

impl HandoffSender {
    /// Strengthen only mechanism identity. Root-selected service admission is
    /// the responsibility of a distinct owner factory, not this transport API.
    pub fn send_retained_service_control(
        self,
        custody: AcceptedStreamCustody,
    ) -> Result<PendingHandoffSender, HandoffError> {
        self.channel.owner()?;
        let fd = self.channel.verify()?;
        self.channel.original_identity.verify(fd)?;
        let mut pending = self.send_retained(custody)?;
        let checked = (|| {
            pending.transaction.channel.owner()?;
            let fd = pending.transaction.channel.verify()?;
            pending.transaction.channel.original_identity.verify(fd)?;
            pending.transaction.readiness_enabled = true;
            pending.ensure_current()?;
            Ok(())
        })();
        if checked.is_err() {
            pending.transaction.channel.retire();
        }
        checked?;
        Ok(pending)
    }
}
