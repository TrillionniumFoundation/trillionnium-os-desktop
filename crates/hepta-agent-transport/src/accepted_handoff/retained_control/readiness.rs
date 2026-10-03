//! Explicit additive readiness API; the legacy file inventory stays closed.
use super::*;

impl PendingHandoffReceiver {
    /// Observe the original Control endpoint without consuming a packet. This
    /// opt-in profile has no FD/deadline input and grants no execution/report
    /// authority. Subsequent packet/report checks retain its original identity.
    pub fn cancel_readable_now(&mut self) -> Result<bool, HandoffError> {
        self.transaction.channel.owner()?;
        self.transaction.readiness_enabled = true;
        let result = (|| {
            let ready = readable_now(self.transaction.verify()?)?;
            self.transaction.verify()?;
            Ok(ready)
        })();
        if result.is_err() {
            self.transaction.channel.retire();
        }
        result
    }
}
