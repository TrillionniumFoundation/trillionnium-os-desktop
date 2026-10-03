//! Complete original managed writer. No extraction, reset or recovery ACK.
use super::*;

pub(super) struct JournalInvocation {
    nonce: Arc<InvocationNonce>,
    deadline: Instant,
    request_id: String,
    request_sha256: Digest,
    event: ReceiptEvent,
    pub(super) requested: bool,
    pub(super) dispatched: bool,
    pub(super) may_dispatch: bool,
    pub(super) terminal: Option<ReceiptLifecycleState>,
}

pub(super) struct ServiceTerminalSeal {
    nonce: Arc<InvocationNonce>,
    writer: Arc<WriterNonce>,
    deadline: Instant,
    request_sha256: Digest,
    record_sha256: Digest,
    lifecycle: ReceiptLifecycleState,
}

impl ServiceTerminalSeal {
    pub(super) fn consume_report(
        self,
        nonce: &Arc<InvocationNonce>,
        writer: &Arc<WriterNonce>,
        deadline: Instant,
    ) -> Result<RemoteRetirementReport, ProductDispatchError> {
        if !Arc::ptr_eq(&self.nonce, nonce)
            || !Arc::ptr_eq(&self.writer, writer)
            || self.deadline != deadline
        {
            return Err(ProductDispatchError::PeerRefused);
        }
        let state = match self.lifecycle {
            ReceiptLifecycleState::Completed => RemoteTerminalState::Completed,
            ReceiptLifecycleState::Interrupted => RemoteTerminalState::Interrupted,
            ReceiptLifecycleState::Indeterminate => RemoteTerminalState::Indeterminate,
            _ => return Err(ProductDispatchError::StorageUnavailable),
        };
        product_time_remaining(deadline)?;
        RemoteRetirementReport::new(state, self.request_sha256, self.record_sha256)
            .map_err(|_| ProductDispatchError::StorageUnavailable)
    }
}

pub(super) struct ServiceManagedLifecycle {
    journal: ReceiptJournal,
    session: ApprovedServiceSessionVerifier,
    writer: Arc<WriterNonce>,
    image_id: String,
    logical_clock: u64,
    active: Option<Arc<InvocationNonce>>,
    failed: bool,
    uncertain: bool,
}

impl ServiceManagedLifecycle {
    pub(super) fn new(
        mut journal: ReceiptJournal,
        session: ApprovedServiceSessionVerifier,
        image_id: String,
    ) -> Result<Self, ProductDispatchError> {
        session
            .ensure_current()
            .map_err(|_| ProductDispatchError::PeerRefused)?;
        if image_id.is_empty()
            || image_id.len() > 128
            || image_id
                .chars()
                .any(|c| c.is_control() || c.is_whitespace())
        {
            return Err(ProductDispatchError::InvalidConfiguration);
        }
        validate_managed_history(&mut journal)?;
        session
            .ensure_current()
            .map_err(|_| ProductDispatchError::PeerRefused)?;
        let logical_clock = journal.last_monotonic_ms();
        Ok(Self {
            journal,
            session,
            writer: Arc::new(WriterNonce),
            image_id,
            logical_clock,
            active: None,
            failed: false,
            uncertain: false,
        })
    }

    pub(super) fn writer_identity(&self) -> Arc<WriterNonce> {
        self.writer.clone()
    }

    pub(super) fn idle_current(&mut self) -> Result<(), ProductDispatchError> {
        self.session.ensure_current().map_err(|_| {
            self.failed = true;
            ProductDispatchError::PeerRefused
        })?;
        if self.failed || self.uncertain || self.active.is_some() {
            return Err(ProductDispatchError::RecoveryRequired);
        }
        self.failed = true;
        validate_managed_history(&mut self.journal)?;
        self.session
            .ensure_current()
            .map_err(|_| ProductDispatchError::PeerRefused)?;
        self.failed = false;
        Ok(())
    }

    pub(super) fn duplicate(&mut self, request_id: &str) -> Result<bool, ProductDispatchError> {
        self.idle_current()?;
        self.failed = true;
        let result = self
            .journal
            .contains_receipt(request_id)
            .map_err(|_| ProductDispatchError::StorageUnavailable);
        self.session
            .ensure_current()
            .map_err(|_| ProductDispatchError::PeerRefused)?;
        if result.is_ok() {
            self.failed = false;
        }
        result
    }

    pub(super) fn begin(
        &mut self,
        nonce: Arc<InvocationNonce>,
        original_deadline: Instant,
        decoded: &DecodedOriginal,
        page: Option<PageOwnerSnapshot>,
        principal: &str,
    ) -> Result<JournalInvocation, ProductDispatchError> {
        self.idle_current()?;
        product_time_remaining(decoded.context.effective_deadline)?;
        if decoded.context.effective_deadline > original_deadline {
            return Err(ProductDispatchError::PeerRefused);
        }
        let request_sha256 = parse_digest(&decoded.context.canonical_request_sha256)?;
        let (
            session_id,
            session_generation,
            document_generation,
            snapshot_revision,
            mutation_epoch,
        ) = match page {
            Some(page) => {
                let r = page.session.revisions;
                (
                    page.session_id,
                    r.session_generation,
                    r.document_generation,
                    r.semantic_snapshot_revision,
                    r.mutation_epoch,
                )
            }
            None => ("pre-session".to_owned(), 1, 1, 0, 0),
        };
        let event = ReceiptEvent {
            receipt_id: decoded.request.request_id.clone(),
            plan_revision: "2026-08-29-d6".to_owned(),
            image_id: self.image_id.clone(),
            servo_commit: "670ae8a70801b162e186f81cbb5bdd2d59c39108".to_owned(),
            browserd_version: env!("CARGO_PKG_VERSION").to_owned(),
            session_id,
            session_generation,
            document_generation,
            semantic_snapshot_revision: snapshot_revision,
            mutation_epoch,
            source: ReceiptSource::Agent,
            operation: operation_name(&decoded.request.operation).to_owned(),
            lifecycle: ReceiptLifecycleState::Requested,
            outcome: None,
            effect_class: receipt_effect(decoded.context.effect_class),
            privacy_class: PrivacyClass::Internal,
            request_sha256,
            response_sha256: None,
            error_code: None,
            detail: Some(format!("principal={principal}")),
            monotonic_ms: 0,
            wall_clock_unix_ms: 0,
        };
        self.session
            .ensure_current()
            .map_err(|_| ProductDispatchError::PeerRefused)?;
        self.active = Some(nonce.clone());
        Ok(JournalInvocation {
            nonce,
            deadline: original_deadline,
            request_id: decoded.request.request_id.clone(),
            request_sha256,
            event,
            requested: false,
            dispatched: false,
            may_dispatch: false,
            terminal: None,
        })
    }

    pub(super) fn requested(
        &mut self,
        invocation: &mut JournalInvocation,
    ) -> Result<(), ProductDispatchError> {
        self.append(
            invocation,
            ReceiptLifecycleState::Requested,
            None,
            None,
            None,
        )?;
        invocation.requested = true;
        Ok(())
    }

    pub(super) fn dispatched(
        &mut self,
        invocation: &mut JournalInvocation,
    ) -> Result<(), ProductDispatchError> {
        if !invocation.requested {
            return Err(ProductDispatchError::StorageUnavailable);
        }
        self.append(
            invocation,
            ReceiptLifecycleState::Dispatched,
            None,
            None,
            None,
        )?;
        invocation.dispatched = true;
        Ok(())
    }

    pub(super) fn completed(
        &mut self,
        invocation: &mut JournalInvocation,
        response: &PreparedResponse,
    ) -> Result<ServiceTerminalSeal, ProductDispatchError> {
        if !invocation.dispatched {
            return Err(ProductDispatchError::StorageUnavailable);
        }
        let (lifecycle, outcome, error) = match &response.value.outcome {
            Ok(_) => (
                ReceiptLifecycleState::Completed,
                Some(ReceiptOutcome::Succeeded),
                None,
            ),
            Err(error)
                if matches!(
                    error.code,
                    BrowserErrorCode::Indeterminate
                        | BrowserErrorCode::BrowserCrashed
                        | BrowserErrorCode::Cancelled
                        | BrowserErrorCode::DeadlineExceeded
                        | BrowserErrorCode::Internal
                ) =>
            {
                (
                    ReceiptLifecycleState::Indeterminate,
                    None,
                    Some(error.code.as_str().to_owned()),
                )
            }
            Err(error) => (
                ReceiptLifecycleState::Completed,
                Some(
                    if matches!(
                        error.code,
                        BrowserErrorCode::PolicyDenied | BrowserErrorCode::Unsupported
                    ) {
                        ReceiptOutcome::Refused
                    } else {
                        ReceiptOutcome::Failed
                    },
                ),
                Some(error.code.as_str().to_owned()),
            ),
        };
        let digest = if lifecycle == ReceiptLifecycleState::Completed {
            Some(parse_digest(&response.sha256)?)
        } else {
            None
        };
        self.append(invocation, lifecycle, outcome, digest, error)?;
        if lifecycle != ReceiptLifecycleState::Completed {
            self.uncertain = true;
        }
        self.seal(invocation)
    }

    pub(super) fn interrupted(
        &mut self,
        invocation: &mut JournalInvocation,
    ) -> Result<Option<ServiceTerminalSeal>, ProductDispatchError> {
        if invocation.terminal.is_some() || !invocation.requested {
            return Ok(None);
        }
        // No new per-invocation blocking IO once the genuine original clock expires.
        product_time_remaining(invocation.deadline)?;
        let lifecycle = if invocation.dispatched || invocation.may_dispatch {
            ReceiptLifecycleState::Indeterminate
        } else {
            ReceiptLifecycleState::Interrupted
        };
        self.append(
            invocation,
            lifecycle,
            None,
            None,
            Some(
                if lifecycle == ReceiptLifecycleState::Indeterminate {
                    BrowserErrorCode::Indeterminate
                } else {
                    BrowserErrorCode::Internal
                }
                .as_str()
                .to_owned(),
            ),
        )?;
        if lifecycle == ReceiptLifecycleState::Indeterminate {
            self.uncertain = true;
        }
        self.seal(invocation).map(Some)
    }

    pub(super) fn finish(
        &mut self,
        invocation: &JournalInvocation,
    ) -> Result<(), ProductDispatchError> {
        self.session
            .ensure_current()
            .map_err(|_| ProductDispatchError::PeerRefused)?;
        if self.failed
            || self.uncertain
            || invocation.terminal.is_none()
            || !self
                .active
                .as_ref()
                .is_some_and(|active| Arc::ptr_eq(active, &invocation.nonce))
        {
            return Err(ProductDispatchError::RecoveryRequired);
        }
        self.active.take();
        self.idle_current()
    }

    fn append(
        &mut self,
        invocation: &mut JournalInvocation,
        lifecycle: ReceiptLifecycleState,
        outcome: Option<ReceiptOutcome>,
        response: Option<Digest>,
        error: Option<String>,
    ) -> Result<(), ProductDispatchError> {
        self.session
            .ensure_current()
            .map_err(|_| ProductDispatchError::PeerRefused)?;
        product_time_remaining(invocation.deadline)?;
        if self.failed
            || invocation.terminal.is_some()
            || !self
                .active
                .as_ref()
                .is_some_and(|active| Arc::ptr_eq(active, &invocation.nonce))
        {
            return Err(ProductDispatchError::RecoveryRequired);
        }
        let clock = self
            .logical_clock
            .checked_add(1)
            .ok_or(ProductDispatchError::StorageUnavailable)?;
        let wall = u64::try_from(
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .map_err(|_| ProductDispatchError::StorageUnavailable)?
                .as_millis(),
        )
        .map_err(|_| ProductDispatchError::StorageUnavailable)?;
        let mut event = invocation.event.clone();
        event.lifecycle = lifecycle;
        event.outcome = outcome;
        event.response_sha256 = response;
        event.error_code = error;
        event.monotonic_ms = clock;
        event.wall_clock_unix_ms = wall;
        // Arm storage failure before the syscall; acknowledgement alone does not clear it.
        self.failed = true;
        let committed = self
            .journal
            .append(event)
            .map_err(|_| ProductDispatchError::StorageUnavailable)?;
        self.logical_clock = clock;
        let fact = self
            .journal
            .receipt_fact(&invocation.request_id, invocation.request_sha256)
            .map_err(|_| ProductDispatchError::StorageUnavailable)?;
        if fact
            .lifecycle()
            .map_err(|_| ProductDispatchError::StorageUnavailable)?
            != lifecycle
            || fact
                .record_sha256()
                .map_err(|_| ProductDispatchError::StorageUnavailable)?
                != committed.record_sha256
        {
            return Err(ProductDispatchError::StorageUnavailable);
        }
        if lifecycle.is_terminal() {
            invocation.terminal = Some(lifecycle);
        }
        self.session
            .ensure_current()
            .map_err(|_| ProductDispatchError::PeerRefused)?;
        product_time_remaining(invocation.deadline)?;
        self.failed = false;
        Ok(())
    }

    fn seal(
        &mut self,
        invocation: &JournalInvocation,
    ) -> Result<ServiceTerminalSeal, ProductDispatchError> {
        self.session
            .ensure_current()
            .map_err(|_| ProductDispatchError::PeerRefused)?;
        product_time_remaining(invocation.deadline)?;
        if self.failed
            || !self
                .active
                .as_ref()
                .is_some_and(|active| Arc::ptr_eq(active, &invocation.nonce))
        {
            return Err(ProductDispatchError::StorageUnavailable);
        }
        // The additional whole-chain readback is part of the durable barrier;
        // any failure, including its Source/clock post, stays sticky.
        self.failed = true;
        let fact = self
            .journal
            .receipt_fact(&invocation.request_id, invocation.request_sha256)
            .map_err(|_| ProductDispatchError::StorageUnavailable)?;
        let lifecycle = fact
            .lifecycle()
            .map_err(|_| ProductDispatchError::StorageUnavailable)?;
        let request_id = fact
            .receipt_id()
            .map_err(|_| ProductDispatchError::StorageUnavailable)?;
        if !lifecycle.is_terminal()
            || Some(lifecycle) != invocation.terminal
            || request_id != invocation.request_id
            || fact
                .request_sha256()
                .map_err(|_| ProductDispatchError::StorageUnavailable)?
                != invocation.request_sha256
        {
            return Err(ProductDispatchError::StorageUnavailable);
        }
        let record_sha256 = fact
            .record_sha256()
            .map_err(|_| ProductDispatchError::StorageUnavailable)?;
        self.session
            .ensure_current()
            .map_err(|_| ProductDispatchError::PeerRefused)?;
        product_time_remaining(invocation.deadline)?;
        self.failed = false;
        Ok(ServiceTerminalSeal {
            nonce: invocation.nonce.clone(),
            writer: self.writer.clone(),
            deadline: invocation.deadline,
            request_sha256: invocation.request_sha256,
            record_sha256,
            lifecycle,
        })
    }
}

pub(super) fn validate_managed_history(
    journal: &mut ReceiptJournal,
) -> Result<(), ProductDispatchError> {
    if !journal.is_managed() {
        return Err(ProductDispatchError::InvalidConfiguration);
    }
    if journal
        .has_unresolved_receipts()
        .map_err(|_| ProductDispatchError::StorageUnavailable)?
        || !journal
            .execution_reconciliation_facts()
            .map_err(|_| ProductDispatchError::StorageUnavailable)?
            .is_empty()
    {
        return Err(ProductDispatchError::RecoveryRequired);
    }
    Ok(())
}

fn receipt_effect(effect: EffectClass) -> ReceiptEffectClass {
    match effect {
        EffectClass::Observation => ReceiptEffectClass::Observation,
        EffectClass::LocalInteraction => ReceiptEffectClass::LocalInteraction,
        EffectClass::PotentialExternalEffect => ReceiptEffectClass::PotentialExternalEffect,
    }
}

fn operation_name(operation: &BrowserOperation) -> &'static str {
    match operation {
        BrowserOperation::Health => "health",
        BrowserOperation::SessionCreate { .. } => "session_create",
        BrowserOperation::SessionSnapshot => "session_snapshot",
        BrowserOperation::SessionClose => "session_close",
        BrowserOperation::PageObserve { .. } => "page_observe",
        BrowserOperation::PageNavigate { .. } => "page_navigate",
        BrowserOperation::PageAct { .. } => "page_act",
        BrowserOperation::PageWait { .. } => "page_wait",
        BrowserOperation::PageExtract { .. } => "page_extract",
    }
}
