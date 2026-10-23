//! Linear local send permission, independent of a renderer or transport.
//!
//! The injected original request owner retains durable intent. This type stores
//! only its opaque ticket and a local permission; it is not another ledger.

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum LocalSubmissionPhase {
    PendingRetained,
    SubmissionStartedOrUnknown,
    OriginalAttemptRetained,
    LocalSendCancelled,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) enum LocalSubmissionError {
    SendPermissionConsumed,
    OriginalOwnerCancellationRequired,
    NoStartedAttempt,
}

pub(crate) struct PendingPermission<Prepared, Ticket> {
    prepared: Option<Prepared>,
    ticket: Ticket,
    phase: LocalSubmissionPhase,
}

impl<Prepared, Ticket> PendingPermission<Prepared, Ticket> {
    pub(crate) fn retain<E>(
        prepared: Prepared,
        retain: impl FnOnce(&Prepared) -> Result<Ticket, E>,
    ) -> Result<Self, E> {
        // Failure never exposes the transport to a sender. The original owner
        // must treat an ambiguous retention failure according to its own store.
        let ticket = retain(&prepared)?;
        Ok(Self {
            prepared: Some(prepared),
            ticket,
            phase: LocalSubmissionPhase::PendingRetained,
        })
    }

    pub(crate) fn recover_unknown(ticket: Ticket) -> Self {
        // Recovery cannot manufacture another local send permission.
        Self {
            prepared: None,
            ticket,
            phase: LocalSubmissionPhase::SubmissionStartedOrUnknown,
        }
    }

    pub(crate) fn phase(&self) -> LocalSubmissionPhase {
        self.phase
    }

    pub(crate) fn ticket(&self) -> &Ticket {
        &self.ticket
    }

    pub(crate) fn begin_send(&mut self) -> Result<Prepared, LocalSubmissionError> {
        let prepared = self
            .prepared
            .take()
            .ok_or(LocalSubmissionError::SendPermissionConsumed)?;
        // Fence first, including a panic or dropped result after this boundary.
        self.phase = LocalSubmissionPhase::SubmissionStartedOrUnknown;
        Ok(prepared)
    }

    pub(crate) fn retain_attempt<E>(
        &mut self,
        retain: impl FnOnce(&Ticket) -> Result<(), E>,
    ) -> Result<(), RetainAttemptError<E>> {
        if self.phase != LocalSubmissionPhase::SubmissionStartedOrUnknown {
            return Err(RetainAttemptError::State(
                LocalSubmissionError::NoStartedAttempt,
            ));
        }
        retain(&self.ticket).map_err(RetainAttemptError::Owner)?;
        self.phase = LocalSubmissionPhase::OriginalAttemptRetained;
        Ok(())
    }

    pub(crate) fn cancel_before_send(&mut self) -> Result<Prepared, LocalSubmissionError> {
        let prepared = self
            .prepared
            .take()
            .ok_or(LocalSubmissionError::OriginalOwnerCancellationRequired)?;
        self.phase = LocalSubmissionPhase::LocalSendCancelled;
        Ok(prepared)
    }
}

#[derive(Debug, Eq, PartialEq)]
pub(crate) enum RetainAttemptError<E> {
    State(LocalSubmissionError),
    Owner(E),
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::cell::RefCell;
    use std::rc::Rc;

    #[test]
    fn original_owner_retention_precedes_any_send_permission() {
        let events = RefCell::new(Vec::new());
        let mut pending = PendingPermission::retain("original", |original| {
            assert_eq!(*original, "original");
            events.borrow_mut().push("retained");
            Ok::<_, ()>("original-owner-ticket")
        })
        .unwrap();
        assert_eq!(pending.ticket(), &"original-owner-ticket");
        assert_eq!(pending.begin_send(), Ok("original"));
        events.borrow_mut().push("sent");
        assert_eq!(*events.borrow(), ["retained", "sent"]);
    }

    #[test]
    fn refused_retention_drops_prepared_input_without_exposing_a_sender() {
        struct DropProbe(Rc<RefCell<usize>>);
        impl Drop for DropProbe {
            fn drop(&mut self) {
                *self.0.borrow_mut() += 1;
            }
        }
        let drops = Rc::new(RefCell::new(0));
        let result = PendingPermission::<_, ()>::retain(DropProbe(Rc::clone(&drops)), |_| {
            Err("owner unavailable")
        });
        assert!(matches!(result, Err("owner unavailable")));
        assert_eq!(*drops.borrow(), 1);
    }

    #[test]
    fn starting_or_losing_a_result_never_rearms_the_transport() {
        let mut pending = PendingPermission::retain(7, |_| Ok::<_, ()>(())).unwrap();
        assert_eq!(pending.begin_send(), Ok(7));
        assert_eq!(
            pending.phase(),
            LocalSubmissionPhase::SubmissionStartedOrUnknown
        );
        assert_eq!(
            pending.begin_send(),
            Err(LocalSubmissionError::SendPermissionConsumed)
        );
        assert_eq!(
            pending.cancel_before_send(),
            Err(LocalSubmissionError::OriginalOwnerCancellationRequired)
        );
    }

    #[test]
    fn local_cancellation_consumes_only_a_never_started_send() {
        let mut pending = PendingPermission::retain(7, |_| Ok::<_, ()>(())).unwrap();
        assert_eq!(pending.cancel_before_send(), Ok(7));
        assert_eq!(pending.phase(), LocalSubmissionPhase::LocalSendCancelled);
        assert_eq!(
            pending.begin_send(),
            Err(LocalSubmissionError::SendPermissionConsumed)
        );
        assert_eq!(
            pending.cancel_before_send(),
            Err(LocalSubmissionError::OriginalOwnerCancellationRequired)
        );
    }

    #[test]
    fn failed_receipt_handoff_keeps_unknown_and_cannot_trigger_another_send() {
        let mut pending = PendingPermission::retain(7, |_| Ok::<_, ()>(())).unwrap();
        pending.begin_send().unwrap();
        assert_eq!(
            pending.retain_attempt(|_| Err("not durable")),
            Err(RetainAttemptError::Owner("not durable"))
        );
        assert_eq!(
            pending.phase(),
            LocalSubmissionPhase::SubmissionStartedOrUnknown
        );
        assert_eq!(
            pending.begin_send(),
            Err(LocalSubmissionError::SendPermissionConsumed)
        );
    }

    #[test]
    fn an_original_attempt_is_retained_only_after_owner_acknowledgement() {
        let mut pending = PendingPermission::retain(7, |_| Ok::<_, ()>(())).unwrap();
        assert_eq!(
            pending.retain_attempt(|_| Ok::<_, ()>(())),
            Err(RetainAttemptError::State(
                LocalSubmissionError::NoStartedAttempt
            ))
        );
        pending.begin_send().unwrap();
        pending.retain_attempt(|_| Ok::<_, ()>(())).unwrap();
        assert_eq!(
            pending.phase(),
            LocalSubmissionPhase::OriginalAttemptRetained
        );
        assert_eq!(
            pending.begin_send(),
            Err(LocalSubmissionError::SendPermissionConsumed)
        );
    }

    #[test]
    fn recovered_pending_intent_has_no_submission_or_local_cancel_capability() {
        let mut pending = PendingPermission::<u8, _>::recover_unknown("original-owner-ticket");
        assert_eq!(pending.ticket(), &"original-owner-ticket");
        assert_eq!(
            pending.phase(),
            LocalSubmissionPhase::SubmissionStartedOrUnknown
        );
        assert_eq!(
            pending.begin_send(),
            Err(LocalSubmissionError::SendPermissionConsumed)
        );
        assert_eq!(
            pending.cancel_before_send(),
            Err(LocalSubmissionError::OriginalOwnerCancellationRequired)
        );
    }

    #[test]
    fn unwinding_after_start_preserves_the_unknown_fence() {
        let mut pending = PendingPermission::retain(7, |_| Ok::<_, ()>(())).unwrap();
        let panic = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
            pending.begin_send().unwrap();
            panic!("lost original transport result");
        }));
        assert!(panic.is_err());
        assert_eq!(
            pending.phase(),
            LocalSubmissionPhase::SubmissionStartedOrUnknown
        );
        assert_eq!(
            pending.begin_send(),
            Err(LocalSubmissionError::SendPermissionConsumed)
        );
    }
}
