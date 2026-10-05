//! Independent original report. Owning custody drops before private done.
use super::*;

enum ReportMessage {
    Terminal(ServiceTerminalSeal),
    NoTerminal,
}
struct ReportOwnersDone {
    nonce: Arc<InvocationNonce>,
    result: Result<ServiceReportObservation, ProductDispatchError>,
}

pub(super) struct ReportOriginalOwners {
    pub(super) reporter: ApprovedServiceRetainedReporter,
    pub(super) custody: ControlRequestCustody,
    pub(super) wake: OriginalConnectedDenial,
    pub(super) session: ApprovedServiceSessionVerifier,
    pub(super) nonce: Arc<InvocationNonce>,
    pub(super) writer: Arc<WriterNonce>,
    pub(super) deadline: Instant,
    pub(super) cancellation: Arc<ServiceCancellationLatch>,
}

pub(super) struct ServiceReportWorker {
    session: ApprovedServiceSessionVerifier,
    nonce: Arc<InvocationNonce>,
    deadline: Instant,
    cancellation: Arc<ServiceCancellationLatch>,
    terminal: Option<mpsc::SyncSender<ReportMessage>>,
    done: Option<mpsc::Receiver<ReportOwnersDone>>,
    thread: Option<JoinHandle<()>>,
    finished: bool,
}

impl ServiceReportWorker {
    pub(super) fn spawn(
        mut owners: ReportOriginalOwners,
        session: ApprovedServiceSessionVerifier,
    ) -> Result<Self, ProductDispatchError> {
        session
            .ensure_current()
            .map_err(|_| ProductDispatchError::PeerRefused)?;
        let deadline = owners.deadline;
        if owners
            .reporter
            .original_deadline()
            .map_err(|_| ProductDispatchError::PeerRefused)?
            != deadline
        {
            return Err(ProductDispatchError::PeerRefused);
        }
        product_time_remaining(deadline)?;
        let (terminal, receive) = mpsc::sync_channel(1);
        let (notify, done) = mpsc::sync_channel(1);
        let nonce = owners.nonce.clone();
        let cancellation = owners.cancellation.clone();
        let thread = std::thread::Builder::new()
            .name("original-service-report".to_owned())
            .spawn(move || run_original_report(owners, receive, notify))
            .map_err(|_| ProductDispatchError::Closed)?;
        let worker = Self {
            session,
            nonce,
            deadline,
            cancellation,
            terminal: Some(terminal),
            done: Some(done),
            thread: Some(thread),
            finished: false,
        };
        // Construct the guarded owner before the post sample. A creator failure
        // must not destruct an inherited channel packet or join a thread.
        worker.current()?;
        Ok(worker)
    }

    pub(super) fn finish(
        &mut self,
        seal: Option<ServiceTerminalSeal>,
    ) -> Result<ServiceReportObservation, ProductDispatchError> {
        self.current()?;
        let message = seal
            .map(ReportMessage::Terminal)
            .unwrap_or(ReportMessage::NoTerminal);
        self.terminal
            .take()
            .ok_or(ProductDispatchError::Closed)?
            .try_send(message)
            .map_err(|_| ProductDispatchError::Closed)?;
        self.current()?;
        loop {
            self.current()?;
            let wait = product_time_remaining(self.deadline)?.min(Duration::from_millis(5));
            let done = match self
                .done
                .as_ref()
                .ok_or(ProductDispatchError::Closed)?
                .recv_timeout(wait)
            {
                Ok(done) => done,
                Err(mpsc::RecvTimeoutError::Timeout) => continue,
                Err(mpsc::RecvTimeoutError::Disconnected) => {
                    return Err(ProductDispatchError::Closed);
                }
            };
            if !Arc::ptr_eq(&done.nonce, &self.nonce) {
                return Err(ProductDispatchError::PeerRefused);
            }
            // Done proves explicit custody release, not thread termination by itself.
            while !self
                .thread
                .as_ref()
                .ok_or(ProductDispatchError::Closed)?
                .is_finished()
            {
                self.current()?;
                std::thread::yield_now();
            }
            self.current()?;
            self.finished = true;
            self.done.take();
            self.thread.take(); // Drop detaches an observed terminal thread; never join.
            return done.result;
        }
    }

    fn current(&self) -> Result<(), ProductDispatchError> {
        self.session
            .ensure_current()
            .map_err(|_| ProductDispatchError::PeerRefused)?;
        product_time_remaining(self.deadline)?;
        Ok(())
    }
}

impl Drop for ServiceReportWorker {
    fn drop(&mut self) {
        if self.session.ensure_current().is_err() {
            // No copied std channel/thread packet destructor after creator refusal.
            std::mem::forget(self.terminal.take());
            std::mem::forget(self.done.take());
            std::mem::forget(self.thread.take());
        } else if !self.finished {
            self.cancellation.deny_token();
        }
    }
}

fn run_original_report(
    owners: ReportOriginalOwners,
    receive: mpsc::Receiver<ReportMessage>,
    notify: mpsc::SyncSender<ReportOwnersDone>,
) {
    let ReportOriginalOwners {
        reporter,
        custody,
        wake,
        session,
        nonce,
        writer,
        deadline,
        cancellation,
    } = owners;
    let mut reporter = Some(reporter);
    let mut custody = Some(custody);
    let mut wake = Some(wake);
    let mut receive = Some(receive);
    let mut notify = Some(notify);
    let result = (|| {
        loop {
            session.ensure_current().map_err(|_| {
                cancellation.cancel();
                ProductDispatchError::PeerRefused
            })?;
            product_time_remaining(deadline)?;
            let report = reporter.as_mut().ok_or(ProductDispatchError::Closed)?;
            if report
                .original_deadline()
                .map_err(|_| ProductDispatchError::PeerRefused)?
                != deadline
            {
                return Err(ProductDispatchError::PeerRefused);
            }
            if report
                .poll_cancel()
                .map_err(|_| ProductDispatchError::PeerRefused)?
            {
                // A real Cancel already revokes action. Denial wake therefore uses
                // independent original Session/Reporter, never the revoked action.
                cancellation.cancel();
                custody
                    .as_ref()
                    .ok_or(ProductDispatchError::Closed)?
                    .revoke()
                    .map_err(|_| ProductDispatchError::PeerRefused)?;
                session
                    .ensure_current()
                    .map_err(|_| ProductDispatchError::PeerRefused)?;
                if report
                    .original_deadline()
                    .map_err(|_| ProductDispatchError::PeerRefused)?
                    != deadline
                {
                    return Err(ProductDispatchError::PeerRefused);
                }
                product_time_remaining(deadline)?;
                wake.take()
                    .ok_or(ProductDispatchError::Closed)?
                    .shutdown_original()
                    .map_err(|_| ProductDispatchError::PeerRefused)?;
                session
                    .ensure_current()
                    .map_err(|_| ProductDispatchError::PeerRefused)?;
                if report
                    .original_deadline()
                    .map_err(|_| ProductDispatchError::PeerRefused)?
                    != deadline
                {
                    return Err(ProductDispatchError::PeerRefused);
                }
                product_time_remaining(deadline)?;
            }
            session
                .ensure_current()
                .map_err(|_| ProductDispatchError::PeerRefused)?;
            let wait = product_time_remaining(deadline)?.min(Duration::from_millis(5));
            let message = match receive
                .as_ref()
                .ok_or(ProductDispatchError::Closed)?
                .recv_timeout(wait)
            {
                Ok(message) => message,
                Err(mpsc::RecvTimeoutError::Timeout) => continue,
                Err(mpsc::RecvTimeoutError::Disconnected) => {
                    return Err(ProductDispatchError::Closed);
                }
            };
            session
                .ensure_current()
                .map_err(|_| ProductDispatchError::PeerRefused)?;
            product_time_remaining(deadline)?;
            return match message {
                ReportMessage::NoTerminal => Ok(ServiceReportObservation::NoTerminal),
                ReportMessage::Terminal(seal) => {
                    let remote = seal.consume_report(&nonce, &writer, deadline)?;
                    report
                        .send_remote_report(remote)
                        .map_err(|_| ProductDispatchError::PeerRefused)?;
                    session
                        .ensure_current()
                        .map_err(|_| ProductDispatchError::PeerRefused)?;
                    product_time_remaining(deadline)?;
                    Ok(ServiceReportObservation::ReportEnqueued)
                }
            };
        }
    })();
    if result.is_err() {
        cancellation.deny_token();
    }
    // The slot Arc is in Reporter even after send_remote_report. Both owning
    // protocol objects end before the private completion is published.
    drop(reporter.take());
    drop(custody.take());
    drop(wake.take());
    if session.ensure_current().is_err() {
        cancellation.cancel();
        std::mem::forget(receive.take());
        std::mem::forget(notify.take());
        return;
    }
    drop(receive.take());
    if product_time_remaining(deadline).is_err() {
        return;
    }
    if let Some(notify) = notify.take() {
        if session.ensure_current().is_err() {
            cancellation.cancel();
            std::mem::forget(notify);
            return;
        }
        if product_time_remaining(deadline).is_err() {
            return;
        }
        let _ = notify.try_send(ReportOwnersDone { nonce, result });
        if session.ensure_current().is_err() {
            cancellation.cancel();
            std::mem::forget(notify);
            return;
        }
        // The controller independently repeats this same ceiling after
        // observing terminal thread state; done is never a renewed budget.
        if product_time_remaining(deadline).is_err() {
            cancellation.deny_token();
        }
    }
}
