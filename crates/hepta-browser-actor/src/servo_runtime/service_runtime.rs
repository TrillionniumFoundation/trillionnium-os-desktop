//! Thin typed mapping of the closed simulation service mechanism. No legacy
//! endpoint/completion extraction, Source constructor, actor or activation.
mod service_actor;
pub use service_actor::ServiceServoBrowserActor;

use super::*;
use simulation::engine_dispatch::event_loop::{
    ServiceEngineBridge, ServiceEngineCommand, ServiceEngineCompletion, ServiceEngineEndpoint,
    closed_immutable_service_engine_pair,
};

/// Only the future opaque service actor can consume this private typed endpoint.
///
/// ```compile_fail,E0616
/// use hepta_browser_actor::ServiceServoRuntimeEndpoint;
/// fn raw(e: ServiceServoRuntimeEndpoint) { let _ = e.inner; }
/// ```
pub struct ServiceServoRuntimeEndpoint {
    inner: Option<ServiceEngineEndpoint>,
}

impl Drop for ServiceServoRuntimeEndpoint {
    fn drop(&mut self) {
        self.inner.take();
    }
}

/// Same captured service command, with a closed Servo operation mapping.
pub struct ServiceServoRuntimeCommand {
    inner: ServiceEngineCommand,
}

impl ServiceServoRuntimeCommand {
    pub fn into_parts(
        self,
    ) -> (
        Option<PageOwnerSnapshot>,
        ServoRuntimeOperation,
        ServiceServoRuntimeCompletion,
    ) {
        let (owner, message, completion) = self.inner.into_parts();
        let operation = match message {
            BrowserActorMessage::Health => ServoRuntimeOperation::Health,
            BrowserActorMessage::CreateSession {
                session_id,
                profile,
            } => ServoRuntimeOperation::CreateSession {
                session_id,
                profile,
            },
            BrowserActorMessage::Snapshot => ServoRuntimeOperation::Snapshot,
            BrowserActorMessage::Close => ServoRuntimeOperation::Close,
            BrowserActorMessage::Observe { fields } => ServoRuntimeOperation::Observe { fields },
            // The underlying opaque closed bridge never emits these values.
            // Refuse rather than choosing another native operation on drift.
            BrowserActorMessage::Navigate { .. }
            | BrowserActorMessage::Wait { .. }
            | BrowserActorMessage::Extract { .. }
            | BrowserActorMessage::Act { .. } => {
                let _ = completion.complete(Err(RuntimeFailure::PolicyDenied(
                    "closed service mapping refused",
                )));
                panic!("closed service bridge emitted an excluded operation");
            }
        };
        (
            owner,
            operation,
            ServiceServoRuntimeCompletion { inner: completion },
        )
    }
}

/// Single-use service completion; readonly proof is retained through both
/// mapping and the underlying service final-forward pipeline.
///
/// ```compile_fail,E0616
/// use hepta_browser_actor::ServiceServoRuntimeCompletion;
/// fn raw(c: ServiceServoRuntimeCompletion) { let _ = c.inner; }
/// ```
pub struct ServiceServoRuntimeCompletion {
    inner: ServiceEngineCompletion,
}

impl ServiceServoRuntimeCompletion {
    pub fn request_id(&self) -> &str {
        self.inner.request_id()
    }

    pub fn deadline(&self) -> Instant {
        self.inner.deadline()
    }

    pub fn ensure_current_request(&self) -> Result<(), ServoRuntimeError> {
        self.inner
            .ensure_current_request()
            .map_err(map_runtime_error)
    }

    pub fn complete_success(
        self,
        result: JsonObject,
        current_url: Option<String>,
    ) -> ServoCompletionDelivery {
        self.inner
            .complete(Ok(RuntimeReply {
                result,
                current_url,
            }))
            .into()
    }

    pub fn complete_error(self, error: ServoRuntimeError) -> ServoCompletionDelivery {
        self.inner.complete(Err(error.into())).into()
    }
}

/// Creator-thread typed bridge. This is not an installed Servo owner or native
/// health observation. It takes no caller callback/backend/capability value.
pub struct ServiceServoRuntimeBridge {
    inner: ServiceEngineBridge,
}

impl ServiceServoRuntimeBridge {
    pub fn pump_one(&mut self) -> ServoPumpResult {
        match self.inner.pump_one() {
            CallbackPumpResult::Idle => ServoPumpResult::Idle,
            CallbackPumpResult::Pending => ServoPumpResult::Pending,
            CallbackPumpResult::Replied => ServoPumpResult::Replied,
            CallbackPumpResult::Retired => ServoPumpResult::Retired,
        }
    }

    pub fn take_command(&mut self) -> Option<ServiceServoRuntimeCommand> {
        self.inner
            .take_command()
            .map(|inner| ServiceServoRuntimeCommand { inner })
    }

    pub fn next_wake_deadline(&self) -> Option<Instant> {
        self.inner.next_wake_deadline()
    }

    pub fn retire(&mut self) {
        self.inner.retire();
    }
}

/// Create a fixed closed typed mechanism, without Source approval or a future
/// Instant. An unbound endpoint cannot produce an approved service command.
pub fn closed_immutable_service_runtime_pair(
    waker: Arc<dyn ServoEventLoopWaker>,
) -> (ServiceServoRuntimeEndpoint, ServiceServoRuntimeBridge) {
    let (endpoint, bridge) =
        closed_immutable_service_engine_pair(Arc::new(ServoWakerAdapter(waker)));
    (
        ServiceServoRuntimeEndpoint {
            inner: Some(endpoint),
        },
        ServiceServoRuntimeBridge { inner: bridge },
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn thin_unbound_pair_has_no_service_command_or_native_health() {
        let (_endpoint, mut bridge) = closed_immutable_service_runtime_pair(Arc::new(|| {}));
        assert_eq!(bridge.pump_one(), ServoPumpResult::Idle);
        assert!(bridge.take_command().is_none());
        assert!(bridge.next_wake_deadline().is_none());
    }

    #[test]
    fn thin_endpoint_drop_does_not_reopen_or_replay() {
        let (endpoint, mut bridge) = closed_immutable_service_runtime_pair(Arc::new(|| {}));
        drop(endpoint);
        assert_eq!(bridge.pump_one(), ServoPumpResult::Retired);
        assert!(bridge.take_command().is_none());
    }
}
