//! Explicit additive readiness API; the legacy file inventory stays closed.
use super::*;

impl AttestedPendingHandoff {
    /// Root-approved, nonconsuming idle observation. Absence of a report is
    /// not a fresh executable assertion or a terminal fact. Ready events reach
    /// the original full path; scope/observation errors retire directly.
    pub fn poll_retirement_when_readable(
        &mut self,
    ) -> Result<Option<PeerReportedRetirement>, ControlOwnerError> {
        creator(self.owner_pid)?;
        let checked = (|| {
            remaining(self.owner_pid, self.deadline)?;
            self.owner
                .as_ref()
                .ok_or(ControlOwnerError::ChannelRetired)?
                .idle_reporting_scope()?;
            let ready = self
                .channel
                .as_mut()
                .ok_or(ControlOwnerError::ChannelRetired)?
                .report_readable_now()
                .map_err(handoff)?;
            self.owner
                .as_ref()
                .ok_or(ControlOwnerError::ChannelRetired)?
                .idle_reporting_scope()?;
            remaining(self.owner_pid, self.deadline)?;
            if ready {
                self.poll_retirement()
            } else {
                Ok(None)
            }
        })();
        if checked.is_err() {
            self.retire()?;
        }
        checked
    }
}

impl AttestedRetainedReceiver {
    /// Root-approved reporting-only readiness profile. An idle result is not a
    /// complete live executable check or an execution/terminal permit. Every
    /// actual ready packet delegates the unchanged full cancel polling path.
    pub fn poll_cancel_when_readable(&mut self) -> Result<bool, ControlOwnerError> {
        creator(self.owner_pid)?;
        let checked = (|| {
            remaining(self.owner_pid, self.deadline)?;
            self.owner
                .as_ref()
                .ok_or(ControlOwnerError::ChannelRetired)?
                .idle_reporting_scope()?;
            let ready = self
                .channel
                .as_mut()
                .ok_or(ControlOwnerError::ChannelRetired)?
                .cancel_readable_now()
                .map_err(handoff)?;
            self.owner
                .as_ref()
                .ok_or(ControlOwnerError::ChannelRetired)?
                .idle_reporting_scope()?;
            remaining(self.owner_pid, self.deadline)?;
            if ready { self.poll_cancel() } else { Ok(false) }
        })();
        if checked.is_err() {
            self.retire()?;
        }
        checked
    }
}
