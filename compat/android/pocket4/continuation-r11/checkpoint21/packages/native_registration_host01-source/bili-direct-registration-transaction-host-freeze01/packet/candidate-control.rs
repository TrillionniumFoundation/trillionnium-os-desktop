//! Privileged two-phase Android task lifecycle service.

use std::collections::{BTreeMap, BTreeSet};
use std::sync::{Arc, Condvar, Mutex, MutexGuard};
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use droidloom_composer::task_control::{TaskControlRegistry, TaskRegistration, TaskRegistrationPhase};
use droidloom_composer::{DisplayId, TaskId};
use droidloom_composer_aidl::denial::DenialPresentationSink;
use droidloom_composer_aidl::service::ComposerLifecycle;
use droidloom_denial_ipc::{SeqPacket, SeqPacketListener};
use droidloom_denial_protocol::TaskObjectId;
use droidloom_task_control::{
    decode_request, encode_response, ControlErrorCode, ControlRequest, ControlResponse,
    PROTOCOL_MAJOR, PROTOCOL_MINOR,
};

const AID_ROOT: u32 = 0;
const AID_SYSTEM: u32 = 1_000;
const CONFIGURE_TIMEOUT: Duration = Duration::from_secs(5);

type ControlFailure = (ControlErrorCode, String);

#[derive(Debug)]
struct State {
    registry: TaskControlRegistry,
    retired: BTreeSet<TaskObjectId>,
    input_scales: BTreeMap<TaskObjectId, (u32, u32)>,
    direct_tasks: BTreeMap<TaskId, TaskObjectId>,
    direct_android_displays: BTreeMap<TaskObjectId, u32>,
    removals: BTreeMap<TaskObjectId, RemovalProgress>,
    endpoint_calls: BTreeMap<TaskObjectId, EndpointCalls>,
}

/// Calls made for one never-reused object/display. Record each invocation
/// before crossing the backend boundary: Err cannot prove it had no effects.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct EndpointCalls {
    display: DisplayId,
    composer: bool,
    denial: bool,
}

/// Retirement completion for this exact object/display. An endpoint is
/// complete only if it was never invoked or its cleanup returned Ok.
/// An error never upgrades either fact.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct RemovalProgress {
    display: DisplayId,
    denial_complete: bool,
    composer_complete: bool,
}

struct DirectReservation {
    object: TaskObjectId,
    display: DisplayId,
    task: TaskId,
    android_display: u32,
    package: String,
}

impl DirectReservation {
    fn matches(&self, state: &State, registration: &TaskRegistration) -> bool {
        registration.object == self.object
            && registration.reservation.display == self.display
            && registration.reservation.package == self.package
            && state.direct_tasks.get(&self.task) == Some(&self.object)
            && state.direct_android_displays.get(&self.object) == Some(&self.android_display)
    }
}

/// Cloneable coordinator shared by the control listener and Denial event pump.
#[derive(Clone)]
pub struct TaskCoordinator {
    sink: DenialPresentationSink,
    lifecycle: ComposerLifecycle,
    state: Arc<(Mutex<State>, Condvar)>,
    operation_gate: Arc<Mutex<()>>,
    direct_registration_gate: Arc<Mutex<()>>,
}

impl TaskCoordinator {
    /// Create an empty coordinator for one Composer/Denial connection.
    pub fn new(sink: DenialPresentationSink, lifecycle: ComposerLifecycle) -> Self {
        let first_object = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .ok()
            .and_then(|elapsed| u64::try_from(elapsed.as_nanos()).ok())
            .filter(|object| *object <= i64::MAX as u64)
            .unwrap_or(1);
        Self {
            sink,
            lifecycle,
            state: Arc::new((
                Mutex::new(State {
                    registry: TaskControlRegistry::with_first_ids(1, first_object)
                        .expect("wall-clock object seed is a positive signed 64-bit value"),
                    retired: BTreeSet::new(),
                    input_scales: BTreeMap::new(),
                    direct_tasks: BTreeMap::new(),
                    direct_android_displays: BTreeMap::new(),
                    removals: BTreeMap::new(),
                    endpoint_calls: BTreeMap::new(),
                }),
                Condvar::new(),
            )),
            operation_gate: Arc::new(Mutex::new(())),
            direct_registration_gate: Arc::new(Mutex::new(())),
        }
    }

    /// Create the configured default display SurfaceFlinger requires before
    /// Android's activity services are available. This display is deliberately
    /// left unbound: later application launches still reserve independent
    /// display/window identities through the task-control protocol.
    pub fn stage_bootstrap_display(
        &self,
        package: String,
    ) -> Result<(TaskObjectId, DisplayId), String> {
        match self.reserve(0, package).map_err(|(code, message)| {
            format!("bootstrap display reservation failed ({code:?}): {message}")
        })? {
            ControlResponse::Reserved {
                object, display, ..
            } => Ok((TaskObjectId(object), DisplayId(display))),
            _ => Err("bootstrap display reservation returned an unexpected response".to_owned()),
        }
    }

    /// Mark the first configured display as launchable and wake its pending
    /// reserve request. Later reconfigures leave the bound phase unchanged.
    pub fn display_connected(&self, object: TaskObjectId) -> Result<(), String> {
        let (state, changed) = &*self.state;
        let mut state = state
            .lock()
            .map_err(|_| "task-control state lock is poisoned".to_owned())?;
        let phase = state
            .registry
            .get(object)
            .map_err(|error| error.to_string())?
            .phase;
        if phase == TaskRegistrationPhase::Staged {
            state
                .registry
                .mark_connected(object)
                .map_err(|error| error.to_string())?;
            changed.notify_all();
        }
        Ok(())
    }

    /// Record the logical-to-buffer scale carried by the latest configure.
    pub fn set_input_scale(
        &self,
        object: TaskObjectId,
        numerator: u32,
        denominator: u32,
    ) -> Result<(), String> {
        if numerator == 0 || denominator == 0 {
            return Err(format!(
                "Droidloom object {} received an invalid input scale {numerator}/{denominator}",
                object.0
            ));
        }
        let mut state = self
            .state
            .0
            .lock()
            .map_err(|_| "task-control state lock is poisoned".to_owned())?;
        state
            .registry
            .get(object)
            .map_err(|error| error.to_string())?;
        state.input_scales.insert(object, (numerator, denominator));
        Ok(())
    }

    /// Return whether an object was intentionally removed, allowing the event
    /// pump to discard an already-queued final event without accepting random
    /// unknown object identities.
    pub fn is_retired(&self, object: TaskObjectId) -> bool {
        self.state
            .0
            .lock()
            .map(|state| state.retired.contains(&object))
            .unwrap_or(false)
    }

    /// Return whether this object is a SurfaceFlinger-owned task channel and
    /// therefore must never be advertised as an Android logical display.
    pub fn is_direct_task(&self, object: TaskObjectId) -> bool {
        self.state
            .0
            .lock()
            .map(|state| state.direct_android_displays.contains_key(&object))
            .unwrap_or(false)
    }

    /// Register one launcher- or observer-verified WindowManager task for direct export.
    /// The channel reuses safe Composer window state but intentionally skips
    /// Composer hotplug: it is not an Android display. This explicit registry
    /// is also the allowlist that excludes HOME and system organizer tasks.
    pub fn register_direct_task(
        &self,
        task: TaskId,
        package: String,
        android_display: u32,
    ) -> Result<(TaskObjectId, DisplayId), String> {
        // Lock order is registration -> operation -> state. Do not hold the
        // operation/state guards while reserve waits for the configure event.
        let _registration = self.direct_registration_gate.lock()
            .map_err(|_| "direct registration lock is poisoned".to_owned())?;
        if task.0 == 0 || task.0 > i32::MAX as u64 {
            return Err(format!("invalid Android task identity {}", task.0));
        }
        {
            let _operation = self.operation_gate.lock()
                .map_err(|_| "task-control operation lock is poisoned".to_owned())?;
            let state = self.state.0.lock()
                .map_err(|_| "task-control state lock is poisoned".to_owned())?;
            if let Some(existing) = state.direct_tasks.get(&task).copied() {
                let registration = state.registry.get(existing)
                    .map_err(|error| error.to_string())?;
                if registration.reservation.package != package
                    || state.direct_android_displays.get(&existing) != Some(&android_display)
                {
                    return Err(format!(
                        "Android task {} is already registered with different ownership",
                        task.0
                    ));
                }
                // A Removing entry still carries its old task/display fields.
                // Those fields alone must never qualify it for reuse.
                if registration.phase != TaskRegistrationPhase::Bound
                    || registration.task != Some(task)
                    || registration.android_display != Some(android_display)
                    || state.removals.contains_key(&existing)
                    || state.endpoint_calls.get(&existing) != Some(&EndpointCalls {
                        display: registration.reservation.display,
                        composer: true,
                        denial: true,
                    })
                {
                    return Err(format!(
                        "Android task {} direct registration is not fully Bound ({:?})",
                        task.0, registration.phase
                    ));
                }
                return Ok((existing, registration.reservation.display));
            }
        }

        let response = self
            .reserve_with_kind(0, package.clone(), Some((task, android_display)))
            .map_err(|(code, message)| {
                format!("direct task reserve failed ({code:?}): {message}")
            })?;
        let ControlResponse::Reserved { object, display, .. } = response else {
            return Err("direct task reservation returned an unexpected response".to_owned());
        };
        let reservation = DirectReservation {
            object: TaskObjectId(object),
            display: DisplayId(display),
            task,
            android_display,
            package,
        };
        let operation = self.operation_gate.lock().map_err(|_| {
            format!("task-control operation lock is poisoned after reserving direct object {}; cleanup is unqualified",
                    reservation.object.0)
        })?;
        let binding: Result<(), String> = (|| {
            // A retire request may have run during the configure wait. Recheck
            // this exact reservation under the same gate as binding/teardown.
            let already_bound = {
                let state = self.state.0.lock()
                    .map_err(|_| "task-control state lock is poisoned".to_owned())?;
                let registration = state.registry.get(reservation.object)
                    .map_err(|error| error.to_string())?;
                if !reservation.matches(&state, registration)
                    || state.endpoint_calls.get(&reservation.object) != Some(&EndpointCalls {
                        display: reservation.display,
                        composer: true,
                        denial: true,
                    })
                {
                    return Err("direct reservation ownership or endpoint calls changed before binding".to_owned());
                }
                if registration.phase == TaskRegistrationPhase::Bound
                    && registration.task == Some(task)
                    && registration.android_display == Some(android_display)
                    && !state.removals.contains_key(&reservation.object)
                {
                    true
                } else if registration.phase == TaskRegistrationPhase::Connected
                    && registration.task.is_none()
                    && registration.android_display.is_none()
                    && !state.removals.contains_key(&reservation.object)
                {
                    false
                } else {
                    return Err(format!(
                        "direct object {} is not awaiting complete binding ({:?})",
                        reservation.object.0, registration.phase
                    ));
                }
            };
            if already_bound {
                return Ok(());
            }
            self.sink.bind_task(reservation.display, task)
                .map_err(|error| format!("bind direct Denial task identity: {error}"))?;
            self.lifecycle.bind_direct_task(reservation.display, task)
                .map_err(|error| format!("bind direct Composer task identity: {error:?}"))?;
            // Return an owned Result from this scope. Its state guard is gone
            // before a failure reaches rollback, which locks state itself.
            let result = {
                let mut state = self.state.0.lock()
                    .map_err(|_| "task-control state lock is poisoned".to_owned())?;
                let registration = state.registry.get(reservation.object)
                    .map_err(|error| error.to_string())?;
                if !reservation.matches(&state, registration) {
                    return Err("direct reservation ownership changed before registry commit".to_owned());
                }
                state.registry.bind_task(reservation.object, task, android_display)
                    .map(|_| ())
                    .map_err(|error| error.to_string())
            };
            result
        })();
        if let Err(primary) = binding {
            return match self.rollback_direct_locked(&reservation, &operation) {
                Ok(()) => Err(primary),
                Err((code, cleanup)) => Err(format!(
                    "{primary}; cleanup of direct object {} failed ({code:?}): {cleanup}",
                    reservation.object.0
                )),
            };
        }
        Ok((reservation.object, reservation.display))
    }

    fn rollback_direct_locked(
        &self,
        reservation: &DirectReservation,
        operation: &MutexGuard<'_, ()>,
    ) -> Result<(), ControlFailure> {
        {
            let state = self.state.0.lock()
                .map_err(|_| backend("task-control state lock is poisoned"))?;
            if !state.retired.contains(&reservation.object) {
                let registration = state.registry.get(reservation.object)
                    .map_err(control_error)?;
                if !reservation.matches(&state, registration) {
                    return Err((ControlErrorCode::Conflict,
                        "refusing cleanup of a changed direct reservation".to_owned()));
                }
                if registration.phase == TaskRegistrationPhase::Bound {
                    return Err((ControlErrorCode::Conflict,
                        "refusing rollback of a complete Bound direct registration".to_owned()));
                }
            }
        }
        // This gate is already held. Calling remove()/retire_direct_task()
        // here would recursively lock it; remove_internal_locked never does.
        self.remove_internal_locked(reservation.object, operation)
    }

    /// Resolve a previously authorized direct task without creating anything.
    /// SurfaceFlinger connections for HOME or other unsolicited tasks fail
    /// closed here and therefore never create a Denial window.
    pub fn direct_task_display(&self, task: TaskId) -> Result<DisplayId, String> {
        let state = self
            .state
            .0
            .lock()
            .map_err(|_| "task-control state lock is poisoned".to_owned())?;
        let object = state
            .direct_tasks
            .get(&task)
            .copied()
            .ok_or_else(|| format!("Android task {} is not authorized for export", task.0))?;
        let registration = state
            .registry
            .get(object)
            .map_err(|error| error.to_string())?;
        if registration.phase != TaskRegistrationPhase::Bound {
            return Err(format!("Android task {} export is not ready", task.0));
        }
        Ok(registration.reservation.display)
    }

    /// Remove exactly one direct task after SurfaceFlinger observes that
    /// WindowManager destroyed its layer subtree.
    pub fn retire_direct_task(&self, task: TaskId) -> Result<(), String> {
        let _operation = self
            .operation_gate
            .lock()
            .map_err(|_| "task-control operation lock is poisoned".to_owned())?;
        let object = self
            .state
            .0
            .lock()
            .map_err(|_| "task-control state lock is poisoned".to_owned())?
            .direct_tasks
            .get(&task)
            .copied()
            .ok_or_else(|| format!("Android task {} is not authorized for export", task.0))?;
        self.remove_internal_locked(object, &_operation)
            .map_err(|(code, message)| format!("retire direct task failed ({code:?}): {message}"))
    }

    /// Accept authenticated privileged clients forever. Each connection is
    /// independent so a configure wait cannot block teardown/status traffic.
    pub fn serve(&self, listener: SeqPacketListener) -> Result<(), String> {
        loop {
            let socket = listener
                .accept()
                .map_err(|error| format!("accept task-control client: {error}"))?;
            let credentials = socket
                .peer_credentials()
                .map_err(|error| format!("authenticate task-control client: {error}"))?;
            if credentials.uid != AID_ROOT && credentials.uid != AID_SYSTEM {
                eprintln!(
                    "Droidloom rejected task-control peer pid={} uid={} gid={}",
                    credentials.pid, credentials.uid, credentials.gid
                );
                continue;
            }
            let coordinator = self.clone();
            std::thread::Builder::new()
                .name("droidloom-task-client".to_owned())
                .spawn(move || {
                    if let Err(error) = coordinator.serve_connection(&socket) {
                        eprintln!("Droidloom task-control client closed: {error}");
                    }
                })
                .map_err(|error| format!("start task-control client thread: {error}"))?;
        }
    }

    fn serve_connection(&self, socket: &SeqPacket) -> Result<(), String> {
        let mut ready = false;
        loop {
            let record = socket
                .receive_record()
                .map_err(|error| format!("receive task-control record: {error}"))?;
            if !record.descriptors.is_empty() {
                return Err("task-control record carried forbidden descriptors".to_owned());
            }
            let request = decode_request(&record.bytes)
                .map_err(|error| format!("decode task-control record: {error}"))?;
            let response = match request {
                ControlRequest::Hello {
                    min_major,
                    max_major,
                } if !ready && min_major <= PROTOCOL_MAJOR && max_major >= PROTOCOL_MAJOR => {
                    ready = true;
                    ControlResponse::ServerHello {
                        major: PROTOCOL_MAJOR,
                        minor: PROTOCOL_MINOR,
                    }
                }
                ControlRequest::Hello { .. } => error_response(
                    0,
                    ControlErrorCode::Protocol,
                    "repeated or incompatible task-control hello".to_owned(),
                ),
                request if !ready => error_response(
                    request_id(&request),
                    ControlErrorCode::Protocol,
                    "task-control hello is required".to_owned(),
                ),
                request => {
                    let request_id = request_id(&request);
                    match self.handle(request) {
                        Ok(response) => response,
                        Err((code, message)) => error_response(request_id, code, message),
                    }
                }
            };
            let bytes = encode_response(&response)
                .map_err(|error| format!("encode task-control response: {error}"))?;
            socket
                .send_record(&bytes, &[])
                .map_err(|error| format!("send task-control response: {error}"))?;
        }
    }

    fn handle(&self, request: ControlRequest) -> Result<ControlResponse, ControlFailure> {
        match request {
            ControlRequest::Reserve {
                request_id,
                package,
            } => self.reserve(request_id, package),
            ControlRequest::Bind {
                request_id,
                object,
                task,
                android_display,
            } => self.bind(
                request_id,
                TaskObjectId(object),
                TaskId(task),
                android_display,
            ),
            ControlRequest::RegisterDirect {
                request_id,
                package,
                task,
                android_display,
            } => self.register_direct(request_id, package, TaskId(task), android_display),
            ControlRequest::Remove { request_id, object } => {
                self.remove(request_id, TaskObjectId(object))
            }
            ControlRequest::Hello { .. } => Err((
                ControlErrorCode::Protocol,
                "unexpected hello dispatch".to_owned(),
            )),
        }
    }

    fn reserve(&self, request_id: u64, package: String) -> Result<ControlResponse, ControlFailure> {
        self.reserve_with_kind(request_id, package, None)
    }

    fn register_direct(
        &self,
        request_id: u64,
        package: String,
        task: TaskId,
        android_display: u32,
    ) -> Result<ControlResponse, ControlFailure> {
        if android_display > i32::MAX as u32 {
            return Err((
                ControlErrorCode::InvalidRequest,
                format!("Android display ID {android_display} exceeds the framework range"),
            ));
        }
        let (object, display) = self
            .register_direct_task(task, package, android_display)
            .map_err(backend)?;
        self.sink.request_activation(display).map_err(|error| backend(error.to_string()))?;
        Ok(ControlResponse::Bound {
            request_id,
            object: object.0,
            task: task.0,
            display: display.0,
            android_display,
        })
    }

    fn reserve_with_kind(
        &self,
        request_id: u64,
        package: String,
        direct_task: Option<(TaskId, u32)>,
    ) -> Result<ControlResponse, ControlFailure> {
        let registration = {
            let operation = self.operation_gate.lock()
                .map_err(|_| backend("task-control operation lock is poisoned"))?;
            let registration = {
                let mut state = self.state.0.lock()
                    .map_err(|_| backend("task-control state lock is poisoned"))?;
                if let Some((task, _)) = direct_task {
                    if state.direct_tasks.contains_key(&task) {
                        return Err((ControlErrorCode::Conflict,
                            format!("Android task {} already has a direct channel", task.0)));
                    }
                }
                let registration = state.registry.reserve(package).map_err(control_error)?;
                state.endpoint_calls.insert(registration.object, EndpointCalls {
                    display: registration.reservation.display,
                    composer: false,
                    denial: false,
                });
                if let Some((task, android_display)) = direct_task {
                    state.direct_tasks.insert(task, registration.object);
                    state.direct_android_displays.insert(registration.object, android_display);
                }
                registration
            };

            // Every failure after reserve leaves this closure before cleanup.
            // No state guard crosses a backend call or recursive state lock.
            let staging: Result<(), ControlFailure> = (|| {
                self.record_endpoint_call_locked(
                    registration.object, registration.reservation.display, false, &operation,
                )?;
                self.lifecycle.stage_task(registration.reservation.clone())
                    .map_err(|error| backend(format!("stage Composer display: {error:?}")))?;
                {
                    let mut state = self.state.0.lock()
                        .map_err(|_| backend("task-control state lock is poisoned"))?;
                    state.registry.mark_staged(registration.object).map_err(control_error)?;
                }
                self.record_endpoint_call_locked(
                    registration.object, registration.reservation.display, true, &operation,
                )?;
                self.sink.register_task(registration.object, &registration.reservation)
                    .map_err(|error| backend(format!("stage Denial task: {error}")))?;
                Ok(())
            })();
            if let Err((code, primary)) = staging {
                let message = match self.remove_internal_locked(registration.object, &operation) {
                    Ok(()) => primary,
                    Err((cleanup_code, cleanup)) => format!(
                        "{primary}; reservation cleanup failed ({cleanup_code:?}): {cleanup}"
                    ),
                };
                return Err((code, message));
            }
            registration
        };

        let (state, changed) = &*self.state;
        let state = state
            .lock()
            .map_err(|_| backend("task-control state lock is poisoned"))?;
        let (state, _wait) = changed
            .wait_timeout_while(state, CONFIGURE_TIMEOUT, |state| {
                state
                    .registry
                    .get(registration.object)
                    .is_ok_and(|current| current.phase == TaskRegistrationPhase::Staged)
            })
            .map_err(|_| backend("task-control state lock is poisoned"))?;
        let connected = state
            .registry
            .get(registration.object)
            .is_ok_and(|current| {
                matches!(
                    current.phase,
                    TaskRegistrationPhase::Connected | TaskRegistrationPhase::Bound
                )
            });
        drop(state);
        if !connected {
            let primary = format!(
                "request {request_id}: Denial did not configure object {} within {} ms",
                registration.object.0,
                CONFIGURE_TIMEOUT.as_millis()
            );
            let message = match self.remove_internal(registration.object) {
                Ok(()) => primary,
                Err((code, cleanup)) => format!(
                    "{primary}; reservation cleanup failed ({code:?}): {cleanup}"
                ),
            };
            return Err((ControlErrorCode::ConfigureTimeout, message));
        }
        Ok(ControlResponse::Reserved {
            request_id,
            object: registration.object.0,
            display: registration.reservation.display.0,
        })
    }

    fn bind(
        &self,
        request_id: u64,
        object: TaskObjectId,
        task: TaskId,
        android_display: u32,
    ) -> Result<ControlResponse, ControlFailure> {
        if android_display > i32::MAX as u32 {
            return Err((
                ControlErrorCode::InvalidRequest,
                format!("Android display ID {android_display} exceeds the framework range"),
            ));
        }
        let _operation = self
            .operation_gate
            .lock()
            .map_err(|_| backend("task-control operation lock is poisoned"))?;
        let registration = {
            let state = self
                .state
                .0
                .lock()
                .map_err(|_| backend("task-control state lock is poisoned"))?;
            let registration = state.registry.get(object).map_err(control_error)?.clone();
            if registration.phase == TaskRegistrationPhase::Bound
                && registration.task == Some(task)
                && registration.android_display == Some(android_display)
            {
                return Ok(ControlResponse::Bound {
                    request_id,
                    object: object.0,
                    task: task.0,
                    display: registration.reservation.display.0,
                    android_display,
                });
            }
            if registration.phase != TaskRegistrationPhase::Connected {
                return Err((
                    ControlErrorCode::Conflict,
                    format!("object {} is not awaiting task binding", object.0),
                ));
            }
            registration
        };
        self.sink
            .bind_task(registration.reservation.display, task)
            .map_err(|error| backend(format!("bind Denial task identity: {error}")))?;
        self.lifecycle
            .bind_task(registration.reservation.display, task)
            .map_err(|error| backend(format!("bind Composer task identity: {error:?}")))?;
        let spec = self
            .state
            .0
            .lock()
            .map_err(|_| backend("task-control state lock is poisoned"))?
            .registry
            .bind_task(object, task, android_display)
            .map_err(control_error)?;
        Ok(ControlResponse::Bound {
            request_id,
            object: object.0,
            task: task.0,
            display: spec.display.0,
            android_display,
        })
    }

    /// Resolve the Android task, display, and logical-to-buffer scale for a live object.
    pub fn input_route_for_object(
        &self,
        object: TaskObjectId,
    ) -> Result<(TaskId, u32, u32, u32), String> {
        let state = self
            .state
            .0
            .lock()
            .map_err(|_| "task-control state lock is poisoned".to_owned())?;
        let registration = state
            .registry
            .get(object)
            .map_err(|error| error.to_string())?;
        let android_display = registration.android_display.ok_or_else(|| {
            format!(
                "Droidloom object {} has not been bound to an Android logical display",
                object.0
            )
        })?;
        let task = registration.task.ok_or_else(|| {
            format!(
                "Droidloom object {} has not been bound to an Android task",
                object.0
            )
        })?;
        let (numerator, denominator) =
            state.input_scales.get(&object).copied().ok_or_else(|| {
                format!(
                    "Droidloom object {} has not received a configured input scale",
                    object.0
                )
            })?;
        Ok((task, android_display, numerator, denominator))
    }

    /// Resolve the real Android task behind an explicitly authorized direct object.
    pub fn direct_task_route_for_object(
        &self,
        object: TaskObjectId,
    ) -> Result<(TaskId, u32), String> {
        let state = self
            .state
            .0
            .lock()
            .map_err(|_| "task-control state lock is poisoned".to_owned())?;
        let android_display = state
            .direct_android_displays
            .get(&object)
            .copied()
            .ok_or_else(|| format!("Droidloom object {} is not a direct task", object.0))?;
        let task = state
            .direct_tasks
            .iter()
            .find_map(|(task, owned_object)| (*owned_object == object).then_some(*task))
            .ok_or_else(|| format!("Droidloom object {} has no Android task", object.0))?;
        Ok((task, android_display))
    }

    fn remove(
        &self,
        request_id: u64,
        object: TaskObjectId,
    ) -> Result<ControlResponse, ControlFailure> {
        let operation = self.operation_gate.lock()
            .map_err(|_| backend("task-control operation lock is poisoned"))?;
        self.remove_internal_locked(object, &operation)?;
        Ok(ControlResponse::Removed {
            request_id,
            object: object.0,
        })
    }

    fn remove_internal(&self, object: TaskObjectId) -> Result<(), ControlFailure> {
        let operation = self.operation_gate.lock()
            .map_err(|_| backend("task-control operation lock is poisoned"))?;
        self.remove_internal_locked(object, &operation)
    }

    fn forget_direct_object(state: &mut State, object: TaskObjectId) {
        state.direct_android_displays.remove(&object);
        state.direct_tasks.retain(|_, owned_object| *owned_object != object);
    }

    fn record_endpoint_call_locked(
        &self,
        object: TaskObjectId,
        display: DisplayId,
        denial: bool,
        _operation: &MutexGuard<'_, ()>,
    ) -> Result<(), ControlFailure> {
        let mut state = self.state.0.lock()
            .map_err(|_| backend("task-control state lock is poisoned"))?;
        let registration = state.registry.get(object).map_err(control_error)?;
        let expected_phase = if denial {
            TaskRegistrationPhase::Staged
        } else {
            TaskRegistrationPhase::Reserved
        };
        if registration.phase != expected_phase
            || registration.reservation.display != display
            || state.removals.contains_key(&object)
        {
            return Err((ControlErrorCode::Conflict,
                "endpoint invocation is not for this pending reservation".to_owned()));
        }
        let calls = state.endpoint_calls.get_mut(&object).ok_or_else(|| {
            backend("reservation endpoint-call record is missing")
        })?;
        if calls.display != display || calls.denial || (calls.composer != denial) {
            return Err((ControlErrorCode::Conflict,
                "reservation endpoint invocation order changed".to_owned()));
        }
        if denial {
            calls.denial = true;
        } else {
            calls.composer = true;
        }
        Ok(())
    }

    fn record_removal_locked(
        &self,
        object: TaskObjectId,
        progress: RemovalProgress,
        _operation: &MutexGuard<'_, ()>,
    ) -> Result<(), ControlFailure> {
        let mut state = self.state.0.lock()
            .map_err(|_| backend("task-control state lock is poisoned"))?;
        let registration = state.registry.get(object).map_err(control_error)?;
        let previous = state.removals.get(&object).copied().ok_or_else(|| {
            backend("task retirement progress is missing")
        })?;
        if !matches!(registration.phase,
                TaskRegistrationPhase::Reserved | TaskRegistrationPhase::Removing)
            || registration.reservation.display != progress.display
            || previous.display != progress.display
            || (previous.denial_complete && !progress.denial_complete)
            || (previous.composer_complete && !progress.composer_complete)
            || (progress.composer_complete && !progress.denial_complete)
        {
            return Err((ControlErrorCode::Conflict,
                "task retirement identity or progress changed".to_owned()));
        }
        state.removals.insert(object, progress);
        Ok(())
    }

    fn remove_internal_locked(
        &self,
        object: TaskObjectId,
        operation: &MutexGuard<'_, ()>,
    ) -> Result<(), ControlFailure> {
        let (registration, mut progress) = {
            let mut state = self.state.0.lock()
                .map_err(|_| backend("task-control state lock is poisoned"))?;
            if state.retired.contains(&object) {
                if state.registry.get(object).is_ok()
                    || state.direct_android_displays.contains_key(&object)
                    || state.direct_tasks.values().any(|owned| *owned == object)
                    || state.input_scales.contains_key(&object)
                    || state.removals.contains_key(&object)
                    || state.endpoint_calls.contains_key(&object)
                {
                    return Err((ControlErrorCode::Conflict,
                        "retired object still has live coordinator state".to_owned()));
                }
                return Ok(());
            }
            let registration = state.registry.get(object).map_err(control_error)?.clone();
            let calls = state.endpoint_calls.get(&object).copied().ok_or_else(|| {
                backend("reservation endpoint-call record is missing")
            })?;
            if calls.display != registration.reservation.display
                || (calls.denial && !calls.composer)
            {
                return Err((ControlErrorCode::Conflict,
                    "reservation endpoint calls are not for this display".to_owned()));
            }
            if registration.phase != TaskRegistrationPhase::Reserved
                && registration.phase != TaskRegistrationPhase::Removing
            {
                state.registry.begin_removal(object).map_err(control_error)?;
            }
            let progress = *state.removals.entry(object).or_insert(RemovalProgress {
                display: registration.reservation.display,
                denial_complete: !calls.denial,
                composer_complete: !calls.composer,
            });
            if progress.display != registration.reservation.display
                || (!calls.denial && !progress.denial_complete)
                || (!calls.composer && !progress.composer_complete)
                || (progress.composer_complete && !progress.denial_complete)
            {
                return Err((ControlErrorCode::Conflict,
                    "task retirement progress is not for this display".to_owned()));
            }
            (registration, progress)
        };

        // A Reserved entry can already have an attempted Composer call. It
        // must not be cancelled until every invoked endpoint is qualified.
        // Denial register Err may leave no local channel: UnknownDisplay then
        // remains an unresolved cleanup error, never evidence of remote absence.
        // Preserve ordering and each completed step. If Composer fails after
        // Denial succeeds, a later explicit retirement skips Denial; it must
        // not get stuck on the now-absent Denial channel. UnknownDisplay and
        // BadDisplay are never treated as successful cleanup.
        if !progress.denial_complete {
            self.sink.unregister_task(registration.reservation.display)
                .map_err(|error| backend(format!("destroy Denial task: {error}")))?;
            progress.denial_complete = true;
            self.record_removal_locked(object, progress, operation)?;
        }
        if !progress.composer_complete {
            self.lifecycle.remove_display(registration.reservation.display)
                .map_err(|error| backend(format!("remove Composer display: {error:?}")))?;
            progress.composer_complete = true;
            self.record_removal_locked(object, progress, operation)?;
        }
        let mut state = self.state.0.lock()
            .map_err(|_| backend("task-control state lock is poisoned"))?;
        if state.removals.get(&object) != Some(&progress)
            || !progress.denial_complete || !progress.composer_complete
        {
            return Err((ControlErrorCode::Conflict,
                "both backend retirement successes were not retained".to_owned()));
        }
        let phase = state.registry.get(object).map_err(control_error)?.phase;
        if phase == TaskRegistrationPhase::Reserved {
            state.registry.cancel_reservation(object).map_err(control_error)?;
        } else {
            state.registry.finish_removal(object).map_err(control_error)?;
        }
        state.input_scales.remove(&object);
        Self::forget_direct_object(&mut state, object);
        state.removals.remove(&object);
        state.endpoint_calls.remove(&object);
        state.retired.insert(object);
        self.state.1.notify_all();
        Ok(())
    }
}

fn request_id(request: &ControlRequest) -> u64 {
    match request {
        ControlRequest::Hello { .. } => 0,
        ControlRequest::Reserve { request_id, .. }
        | ControlRequest::Bind { request_id, .. }
        | ControlRequest::RegisterDirect { request_id, .. }
        | ControlRequest::Remove { request_id, .. } => *request_id,
    }
}

fn control_error(error: impl std::fmt::Display) -> ControlFailure {
    let message = error.to_string();
    let code = if message.contains("no registration") || message.contains("no native") {
        ControlErrorCode::NotFound
    } else if message.contains("already") || message.contains("cannot move") {
        ControlErrorCode::Conflict
    } else {
        ControlErrorCode::InvalidRequest
    };
    (code, message)
}

fn backend(message: impl Into<String>) -> ControlFailure {
    (ControlErrorCode::Backend, message.into())
}

fn error_response(request_id: u64, code: ControlErrorCode, message: String) -> ControlResponse {
    let mut bounded = String::with_capacity(message.len().min(1_024));
    for character in message.chars() {
        if bounded.len() + character.len_utf8() > 1_024 {
            break;
        }
        bounded.push(character);
    }
    if bounded.is_empty() {
        bounded.push_str("unspecified task-control failure");
    }
    ControlResponse::Error {
        request_id,
        code,
        message: bounded,
    }
}
