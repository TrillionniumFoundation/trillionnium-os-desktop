//! One original owning service, actual wire and complete managed receipt chain.
//! Default installed startup remains disabled; this constructs no native owner.
mod coordinator;
mod lifecycle;
mod report;
#[cfg(test)]
mod tests;
mod wire;

pub use coordinator::{ApprovedServiceProductCoordinator, ServiceRetainedObservation};

use super::{ProductDispatchError, ServiceEvidence, product_time_remaining};
use hepta_agent_port::{AgentPortError, DispatchContext, HandlerOutcome};
use hepta_agent_transport::{
    OriginalConnectedDenial, PeerIdentity, PeerPolicy, RemoteRetirementReport, RemoteTerminalState,
    RootPathControlConnection, ServerConnection,
};
use hepta_browser_actor::{
    CancellationToken, PageOwnerSnapshot, ServiceServoBrowserActor, ServiceServoRuntimeEndpoint,
    executable_sha256,
};
use hepta_browser_codec::{
    BrowserErrorCode, BrowserOperation, BrowserRequest, BrowserResponse, BrowserWireError,
    EffectClass, JsonObject, JsonValue, decode_request, encode_response,
};
use hepta_peer_attestation::{
    ApprovedServiceOwnerBinding, ApprovedServiceRequestBinding, ApprovedServiceRequestVerifier,
    ApprovedServiceRequests, ApprovedServiceRetainedReporter, ApprovedServiceSessionVerifier,
    ControlRequestCustody,
};
use hepta_session_core::{
    Digest, PrivacyClass, ReceiptEffectClass, ReceiptEvent, ReceiptJournal, ReceiptLifecycleState,
    ReceiptOutcome, ReceiptSource,
};
use std::os::unix::net::UnixStream;
use std::path::Path;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, OnceLock, mpsc};
use std::thread::JoinHandle;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use lifecycle::{JournalInvocation, ServiceManagedLifecycle, ServiceTerminalSeal};
use report::ServiceReportWorker;
use wire::{DecodedOriginal, OriginalServiceWire, PreparedResponse};

/// Diagnostic product phase. It is not action, recovery or replay permission.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ServiceProductPhase {
    Idle,
    Active,
    Quarantined,
    Closed,
}

/// Original report observation, without a public journal seal or delivery claim.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ServiceReportObservation {
    ReportEnqueued,
    NoTerminal,
}

struct InvocationNonce;
struct WriterNonce;

struct ServiceCancellationLatch {
    cancelled: AtomicBool,
    token: OnceLock<CancellationToken>,
}

impl ServiceCancellationLatch {
    fn new() -> Self {
        Self {
            cancelled: AtomicBool::new(false),
            token: OnceLock::new(),
        }
    }

    fn cancel(&self) {
        self.cancelled.store(true, Ordering::SeqCst);
        self.deny_token();
    }

    fn deny_token(&self) {
        if let Some(token) = self.token.get() {
            token.cancel();
        }
    }

    fn install(&self, token: CancellationToken) -> Result<(), ProductDispatchError> {
        self.token
            .set(token)
            .map_err(|_| ProductDispatchError::PeerRefused)?;
        if self.cancelled.load(Ordering::SeqCst) {
            if let Some(token) = self.token.get() {
                token.cancel();
            }
            return Err(ProductDispatchError::Cancelled);
        }
        Ok(())
    }

    fn current(&self) -> Result<(), ProductDispatchError> {
        // Successful legacy retirement normally cancels the saved token. Only
        // real remote cancellation/scope failure sets this separate sticky bit.
        if self.cancelled.load(Ordering::SeqCst) {
            Err(ProductDispatchError::Cancelled)
        } else {
            Ok(())
        }
    }
}

struct InvocationUnwind {
    quarantine: Arc<AtomicBool>,
    cancellation: Arc<ServiceCancellationLatch>,
    armed: bool,
}

impl Drop for InvocationUnwind {
    fn drop(&mut self) {
        if self.armed {
            self.quarantine.store(true, Ordering::SeqCst);
            self.cancellation.deny_token();
        }
    }
}

fn original_current(
    verifier: &ApprovedServiceRequestVerifier,
    session: &ApprovedServiceSessionVerifier,
    deadline: Instant,
) -> Result<(), ProductDispatchError> {
    session
        .ensure_current()
        .map_err(|_| ProductDispatchError::PeerRefused)?;
    product_time_remaining(deadline)?;
    verifier
        .verify_for_service(session)
        .map_err(|_| ProductDispatchError::PeerRefused)?;
    product_time_remaining(deadline)?;
    session
        .ensure_current()
        .map_err(|_| ProductDispatchError::PeerRefused)
}

fn port_error(error: AgentPortError) -> ProductDispatchError {
    match error {
        AgentPortError::DeadlineExceeded => ProductDispatchError::DeadlineExceeded,
        _ => ProductDispatchError::DispatchFailed,
    }
}

fn parse_digest(value: &str) -> Result<Digest, ProductDispatchError> {
    if value.len() != 64 {
        return Err(ProductDispatchError::StorageUnavailable);
    }
    let mut result = [0; 32];
    for (index, pair) in value.as_bytes().chunks_exact(2).enumerate() {
        let digit = |byte| match byte {
            b'0'..=b'9' => Ok(byte - b'0'),
            b'a'..=b'f' => Ok(byte - b'a' + 10),
            _ => Err(ProductDispatchError::StorageUnavailable),
        };
        result[index] = (digit(pair[0])? << 4) | digit(pair[1])?;
    }
    if result == [0; 32] {
        return Err(ProductDispatchError::StorageUnavailable);
    }
    Ok(result)
}
