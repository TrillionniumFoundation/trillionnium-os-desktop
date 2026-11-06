//! Concrete Composer presentation sink for the Denial-native protocol.
//!
//! One [`TaskChannel`] exists per Android task/display. DMA-BUF descriptors
//! cross the socket only on first allocation registration; acquire and release
//! timeline descriptors cross only when the task is bound. A steady-state
//! submission sends one descriptor-free `Present` record.

use std::collections::BTreeMap;
use std::os::fd::AsFd;
use std::sync::{Arc, Condvar, Mutex, MutexGuard};
use std::time::{Duration, Instant};

use binder::ParcelFileDescriptor;
use droidloom_composer::denial::{
    AppliedDenialEvent, DenialBridgeError, DenialTaskBinding, PreparedPresent,
};
use droidloom_composer::{
    ClientTarget, ComposerError, DisplayId, ReservedTaskWindowSpec, TaskId, hwc3::ErrorCode,
    hwc3::Session,
};
use droidloom_denial_ipc::{AttachedDescriptor, IpcError, ProtocolSocket};
use droidloom_denial_protocol::{AndroidMessage, DenialMessage, DescriptorKind, RetirementNonce, TaskObjectId};
use droidloom_syncobj::{AndroidTaskTimelines, SyncobjDevice, SyncobjError};
use droidloom_syncobj::frame_trace;
use droidloom_transport::{AcceptedFrame, BufferId, BufferMetadata};
use thiserror::Error;

use crate::minigbm::{ImportedRenderTarget, PreparedLayer, PresentationSink};
use crate::{PresentationFailure, gles::LayerCompositor};

/// Task lifecycle, socket, or explicit-synchronization failure.
#[derive(Debug, Error)]
pub enum DenialSinkError {
    /// Another live task already owns the display.
    #[error("Denial task display {0:?} is already registered")]
    DuplicateDisplay(DisplayId),
    /// Another live task already owns the protocol object.
    #[error("Denial task object {0:?} is already registered")]
    DuplicateObject(TaskObjectId),
    /// No live task owns the requested display.
    #[error("Denial task display {0:?} is not registered")]
    UnknownDisplay(DisplayId),
    /// Cleanup named a display currently owned by a different protocol object.
    #[error("Denial display {display:?} is owned by {actual:?}, not {expected:?}")]
    OwnershipMismatch {
        /// Display whose ownership was checked while holding the task map.
        display: DisplayId,
        /// Object that the caller is authorized to retire.
        expected: TaskObjectId,
        /// Live object that must remain untouched.
        actual: TaskObjectId,
    },
    /// A task cannot be registered without a qualified retirement protocol.
    #[error("Denial retirement receipts were not negotiated")]
    RetirementUnsupported,
    /// A partially registered channel may only be retired.
    #[error("Denial display {0:?} registration did not complete")]
    RegistrationIncomplete(DisplayId),
    /// No new submission or binding is allowed after retirement begins.
    #[error("Denial display {0:?} is retiring")]
    TaskRetiring(DisplayId),
    /// The exact remote receipt or local reservations are still outstanding.
    #[error("Denial retirement pending for {object:?}, nonce {nonce:?}")]
    RetirementPending {
        /// Object still owned locally.
        object: TaskObjectId,
        /// Original nonce; a later caller must not send a new request.
        nonce: RetirementNonce,
    },
    /// A receipt did not match the single pending object/request.
    #[error("Denial retirement receipt mismatch for {object:?}, nonce {nonce:?}")]
    RetirementMismatch {
        /// Object named by the receipt.
        object: TaskObjectId,
        /// Nonce named by the receipt.
        nonce: RetirementNonce,
    },
    /// A receipt came through another socket instance.
    #[error("Denial retirement receipt belongs to another peer connection")]
    RetirementForeignPeer,
    /// No receipt can qualify once this peer has disconnected.
    #[error("Denial peer disconnected before local retirement completed")]
    PeerDisconnected,
    /// Request identities cannot wrap or be reused.
    #[error("Denial retirement nonce space exhausted")]
    RetirementNonceExhausted,
    /// A remote receipt contradicted locally outstanding accepted frames.
    #[error("Denial retirement receipt arrived before accepted frames released for {0:?}")]
    RetirementFramesOutstanding(TaskObjectId),
    /// A task-scoped host event named no live task object.
    #[error("Denial task object {0:?} is not registered")]
    UnknownObject(TaskObjectId),
    /// A connection-scoped message reached task dispatch.
    #[error("connection-scoped Denial message cannot be applied to a task")]
    ConnectionMessage,
    /// A cached buffer ID was reused with different immutable metadata.
    #[error("buffer {0:?} was reused with different immutable metadata")]
    BufferMetadataMismatch(BufferId),
    /// Native plane descriptors do not match the validated plane table.
    #[error("DMA-BUF plane descriptor count does not match metadata")]
    PlaneDescriptorMismatch,
    /// Denial repeated a live render-target ID.
    #[error("Denial repeated render target {0:?}")]
    DuplicateRenderTarget(BufferId),
    /// Denial revoked a render target that was not registered.
    #[error("Denial revoked unknown render target {0:?}")]
    UnknownRenderTarget(BufferId),
    /// No target in the newest configured pool is currently reusable.
    #[error("Denial display {0:?} has no idle render target")]
    NoRenderTarget(DisplayId),
    /// Task state was poisoned by a panic and cannot be trusted.
    #[error("Denial task presentation state lock is poisoned")]
    Poisoned,
    /// Typed task/Composer bridge rejected an ordering transition.
    #[error(transparent)]
    Bridge(#[from] DenialBridgeError),
    /// Typed sequenced-packet transport failed.
    #[error(transparent)]
    Ipc(#[from] IpcError),
    /// Linux DRM syncobj operation failed.
    #[error(transparent)]
    Syncobj(#[from] SyncobjError),
    /// EGL/GLES layer composition failed.
    #[error("Droidloom layer composition failed: {0}")]
    Graphics(String),
    /// The safe Composer state rejected a direct SurfaceFlinger frame.
    #[error(transparent)]
    Composer(#[from] ComposerError),
}

impl DenialSinkError {
    fn error_code(&self) -> ErrorCode {
        match self {
            Self::UnknownDisplay(_) => ErrorCode::BadDisplay,
            Self::BufferMetadataMismatch(_)
            | Self::PlaneDescriptorMismatch
            | Self::DuplicateRenderTarget(_)
            | Self::UnknownRenderTarget(_)
            | Self::Bridge(_) => ErrorCode::BadParameter,
            Self::RetirementUnsupported
            | Self::RegistrationIncomplete(_)
            | Self::TaskRetiring(_)
            | Self::RetirementPending { .. }
            | Self::RetirementMismatch { .. }
            | Self::RetirementForeignPeer
            | Self::PeerDisconnected
            | Self::RetirementNonceExhausted
            | Self::RetirementFramesOutstanding(_)
            | Self::OwnershipMismatch { .. }
            | Self::DuplicateDisplay(_)
            | Self::DuplicateObject(_)
            | Self::UnknownObject(_)
            | Self::ConnectionMessage
            | Self::NoRenderTarget(_)
            | Self::Poisoned
            | Self::Ipc(_)
            | Self::Syncobj(_)
            | Self::Graphics(_)
            | Self::Composer(_) => ErrorCode::NoResources,
        }
    }
}

/// Cloneable concrete sink shared by the Binder adapter and lifecycle/event
/// pump. The socket is full-duplex; only one event-pump thread may receive.
#[derive(Clone, Debug)]
pub struct DenialPresentationSink {
    socket: Arc<ProtocolSocket>,
    device: SyncobjDevice,
    tasks: Arc<Mutex<TaskTable>>,
    retirement_changed: Arc<Condvar>,
    retirement_receipts: bool,
    compositor: Arc<Mutex<Option<LayerCompositor>>>,
    activation_requests: bool,
}

impl DenialPresentationSink {
    /// Create an empty sink after the connection-level hello has succeeded.
    pub fn new(socket: ProtocolSocket, device: SyncobjDevice) -> Self {
        Self {
            socket: Arc::new(socket),
            device,
            tasks: Arc::new(Mutex::new(TaskTable::default())),
            retirement_changed: Arc::new(Condvar::new()),
            retirement_receipts: false,
            compositor: Arc::new(Mutex::new(None)),
            activation_requests: false,
        }
    }

    /// Record the activation capability negotiated with this host.
    #[must_use]
    pub fn with_activation_requests(mut self, enabled: bool) -> Self {
        self.activation_requests = enabled;
        self
    }

    /// Record the capability only after a minor-5 ServerHello was qualified.
    #[must_use]
    pub fn with_retirement_receipts(mut self, enabled: bool) -> Self {
        self.retirement_receipts = enabled;
        self
    }

    /// Request host activation of an already bound task when supported.
    ///
    /// # Errors
    /// Returns unknown-display or transport errors; older hosts remain usable.
    pub fn request_activation(&self, display: DisplayId) -> Result<(), DenialSinkError> {
        if self.activation_requests {
            let tasks = self.lock_tasks()?;
            let channel = tasks.get(&display).ok_or(DenialSinkError::UnknownDisplay(display))?;
            require_live(channel, display)?;
            self.socket.send_android(&AndroidMessage::RequestActivation {
                object: channel.binding.object(),
            }, &[])?;
        }
        Ok(())
    }

    /// Borrow the connected socket for a single-owner protocol event pump.
    pub fn socket(&self) -> &ProtocolSocket {
        &self.socket
    }

    /// Create and bind one native Denial task object and its two timelines.
    ///
    /// The caller must first create the matching [`Session`] task window. This
    /// method holds the task map lock through both sends so a concurrent event
    /// receiver cannot observe a configure before local insertion completes.
    ///
    /// # Errors
    ///
    /// Rejects duplicate display/object ownership and propagates timeline or
    /// transport failures. Partial registration retains its exact local owner
    /// and primary failure until the separate confirmed retirement completes.
    pub fn register_task(
        &self,
        object: TaskObjectId,
        reservation: &ReservedTaskWindowSpec,
    ) -> Result<(), DenialSinkError> {
        if !self.retirement_receipts {
            return Err(DenialSinkError::RetirementUnsupported);
        }
        let mut tasks = self.lock_tasks()?;
        if tasks.peer_disconnected {
            return Err(DenialSinkError::PeerDisconnected);
        }
        if tasks.contains_key(&reservation.display)
            || tasks.preparations.contains_key(&reservation.display)
        {
            return Err(DenialSinkError::DuplicateDisplay(reservation.display));
        }
        if tasks.values().any(|task| task.binding.object() == object)
            || tasks.preparations.values().any(|entry| entry.object == object)
        {
            return Err(DenialSinkError::DuplicateObject(object));
        }
        // Claim before fallible local preparation. No remote call can precede
        // this record; preparation-only cleanup therefore has explicit proof.
        tasks.preparations.insert(reservation.display, PreparingTask {
            object, primary_error: None,
        });
        let prepared = (|| -> Result<_, DenialSinkError> {
            let binding = DenialTaskBinding::new(object, reservation)?;
            let timelines = AndroidTaskTimelines::create(&self.device)?;
            let descriptors = timelines.export_descriptors()?;
            Ok((binding, timelines, descriptors))
        })();
        let (binding, timelines, descriptors) = match prepared {
            Ok(value) => value,
            Err(error) => {
                tasks.preparations.get_mut(&reservation.display)
                    .expect("preparation was inserted").primary_error = Some(error.to_string());
                return Err(error);
            }
        };
        tasks.insert(reservation.display, TaskChannel {
            binding, timelines,
            render_targets: BTreeMap::new(),
            frame_targets: BTreeMap::new(),
            trace_fences: BTreeMap::new(),
            content_opaque: None,
            surfaceflinger_present_fence: None,
            android_display_extent: None,
            registration_complete: false,
            create_attempted: false,
            create_sent: false,
            timelines_attempted: false,
            primary_registration_error: None,
            retirement: None,
        });
        tasks.preparations.remove(&reservation.display);
        let channel = tasks.get_mut(&reservation.display).expect("channel was inserted");
        channel.create_attempted = true;
        if let Err(error) = self.socket.send_android(&channel.binding.create_task_message(), &[]) {
            channel.primary_registration_error = Some(error.to_string());
            return Err(error.into());
        }
        channel.create_sent = true;
        channel.timelines_attempted = true;
        let timeline_fds = [descriptors.acquire.as_fd(), descriptors.release.as_fd()];
        if let Err(error) = self.socket.send_android(&channel.binding.bind_timelines_message(), &timeline_fds) {
            channel.primary_registration_error = Some(error.to_string());
            return Err(error.into());
        }
        channel.registration_complete = true;
        Ok(())
    }

    /// Publish the real Android task identity after launch on the connected
    /// display. Local state is committed only after the record is sent.
    ///
    /// # Errors
    ///
    /// Rejects unknown displays, repeated/zero bindings, and transport errors.
    pub fn bind_task(&self, display: DisplayId, task: TaskId) -> Result<(), DenialSinkError> {
        let mut tasks = self.lock_tasks()?;
        if tasks.iter().any(|(owned_display, channel)| {
            *owned_display != display && channel.binding.task() == Some(task)
        }) {
            return Err(DenialSinkError::Bridge(
                DenialBridgeError::UnexpectedMessage,
            ));
        }
        let channel = tasks
            .get_mut(&display)
            .ok_or(DenialSinkError::UnknownDisplay(display))?;
        require_live(channel, display)?;
        if channel.binding.task() == Some(task) {
            return Ok(());
        }
        let message = channel.binding.bind_task_message(task)?;
        self.socket.send_android(&message, &[])?;
        channel.binding.mark_task_bound(task)?;
        Ok(())
    }

    /// Retire only the exact owned object and wait for its confirmed receipt.
    ///
    /// No tasks/session mutex is held while waiting. A timeout retains the
    /// original request and resources; a later call observes that same request
    /// without sending it again. Preparation before any send is locally proven.
    ///
    /// # Errors
    /// Rejects foreign ownership, unsupported/disconnected peers, an unconfirmed
    /// receipt, or outstanding local target reservations. Errors preserve state.
    pub fn unregister_task(
        &self,
        display: DisplayId,
        expected_object: TaskObjectId,
    ) -> Result<(), DenialSinkError> {
        let deadline = Instant::now().checked_add(Duration::from_secs(2))
            .ok_or(DenialSinkError::RetirementNonceExhausted)?;
        let mut tasks = self.lock_tasks()?;
        if tasks.peer_disconnected { return Err(DenialSinkError::PeerDisconnected); }
        if let Some(preparing) = tasks.preparations.get(&display) {
            if preparing.object != expected_object {
                return Err(DenialSinkError::OwnershipMismatch {
                    display, expected: expected_object, actual: preparing.object,
                });
            }
            // This exact record can exist only before the first remote send.
            tasks.preparations.remove(&display);
            return Ok(());
        }
        let channel = tasks.get(&display).ok_or(DenialSinkError::UnknownDisplay(display))?;
        let actual = channel.binding.object();
        if actual != expected_object {
            return Err(DenialSinkError::OwnershipMismatch {
                display, expected: expected_object, actual,
            });
        }
        if !channel.create_attempted {
            let local = tasks.remove(&display);
            drop(tasks);
            drop(local);
            return Ok(());
        }
        if !self.retirement_receipts { return Err(DenialSinkError::RetirementUnsupported); }
        let existing = channel.retirement.as_ref().map(|entry| entry.nonce);
        let nonce = match existing {
            Some(nonce) => nonce,
            None => {
                let next = tasks.next_nonce.checked_add(1)
                    .ok_or(DenialSinkError::RetirementNonceExhausted)?;
                tasks.next_nonce = next;
                let nonce = RetirementNonce(next);
                let channel = tasks.get_mut(&display).expect("exact owner checked");
                channel.retirement = Some(PendingRetirement {
                    nonce, send_attempted: true, send_error: None, receipt_received: false,
                });
                // The record precedes the send. A send error may still be
                // followed by a matching receipt, but never triggers a resend.
                if let Err(error) = self.socket.send_android(
                    &AndroidMessage::RetireTask { object: expected_object, nonce }, &[],
                ) {
                    channel.retirement.as_mut().expect("request was recorded")
                        .send_error = Some(error.to_string());
                    return Err(error.into());
                }
                nonce
            }
        };
        loop {
            if tasks.peer_disconnected { return Err(DenialSinkError::PeerDisconnected); }
            let channel = tasks.get(&display).ok_or(DenialSinkError::UnknownDisplay(display))?;
            if channel.binding.object() != expected_object {
                return Err(DenialSinkError::OwnershipMismatch {
                    display, expected: expected_object, actual: channel.binding.object(),
                });
            }
            let request = channel.retirement.as_ref()
                .ok_or(DenialSinkError::RetirementMismatch { object: expected_object, nonce })?;
            if request.nonce != nonce {
                return Err(DenialSinkError::RetirementMismatch { object: expected_object, nonce });
            }
            if request.receipt_received
                && channel.frame_targets.is_empty()
                && channel.render_targets.values().all(|target| !target.busy && !target.reserved)
            {
                let retired = tasks.remove(&display);
                drop(tasks);
                drop(retired);
                return Ok(());
            }
            let remaining = deadline.saturating_duration_since(Instant::now());
            if remaining.is_zero() {
                return Err(DenialSinkError::RetirementPending { object: expected_object, nonce });
            }
            let (next, _) = self.retirement_changed.wait_timeout(tasks, remaining)
                .map_err(|_| DenialSinkError::Poisoned)?;
            tasks = next;
        }
    }

    /// Apply a receipt read from this exact socket by its single event receiver.
    /// This path never takes the Composer Session or coordinator operation lock.
    pub fn accept_retirement_receipt(
        &self,
        receiver: &ProtocolSocket,
        object: TaskObjectId,
        nonce: RetirementNonce,
    ) -> Result<(), DenialSinkError> {
        if !std::ptr::eq(receiver, self.socket.as_ref()) {
            return Err(DenialSinkError::RetirementForeignPeer);
        }
        let mut tasks = self.lock_tasks()?;
        if tasks.peer_disconnected { return Err(DenialSinkError::PeerDisconnected); }
        let channel = tasks.values_mut().find(|channel| channel.binding.object() == object)
            .ok_or(DenialSinkError::UnknownObject(object))?;
        let request = channel.retirement.as_mut()
            .ok_or(DenialSinkError::RetirementMismatch { object, nonce })?;
        if request.nonce != nonce || !request.send_attempted || request.receipt_received {
            return Err(DenialSinkError::RetirementMismatch { object, nonce });
        }
        if !channel.frame_targets.is_empty() || channel.render_targets.values().any(|target| target.busy) {
            return Err(DenialSinkError::RetirementFramesOutstanding(object));
        }
        request.receipt_received = true;
        self.retirement_changed.notify_all();
        Ok(())
    }

    /// Wake waiters when the single receiver ends. EOF is never a receipt.
    pub fn peer_disconnected(&self) -> Result<(), DenialSinkError> {
        let mut tasks = self.lock_tasks()?;
        tasks.peer_disconnected = true;
        self.retirement_changed.notify_all();
        Ok(())
    }

    /// Metadata for a partial or retiring task cannot publish new app state.
    /// BufferReleased is handled separately so already accepted frames drain.
    pub fn suppress_task_metadata(&self, object: TaskObjectId) -> Result<bool, DenialSinkError> {
        let tasks = self.lock_tasks()?;
        let channel = tasks.values().find(|channel| channel.binding.object() == object)
            .ok_or(DenialSinkError::UnknownObject(object))?;
        Ok(!channel.registration_complete || channel.retirement.is_some())
    }

    /// Acknowledge a host configure in both Composer and the protocol stream.
    ///
    /// # Errors
    ///
    /// Rejects an unknown display or stale serial and propagates send failure.
    pub fn acknowledge_configure(
        &self,
        session: &mut Session,
        display: DisplayId,
        serial: u32,
    ) -> Result<(), DenialSinkError> {
        let mut tasks = self.lock_tasks()?;
        let task = tasks
            .get_mut(&display)
            .ok_or(DenialSinkError::UnknownDisplay(display))?;
        // Retirement has already ordered its request on this socket. A late
        // configure must not create work after that request.
        if !task.registration_complete || task.retirement.is_some() { return Ok(()); }
        let message = task.binding.acknowledge_configure(session, serial)?;
        self.socket.send_android(&message, &[])?;
        Ok(())
    }

    /// Apply one already-decoded task-scoped host event to its exact Composer
    /// display and protocol binding.
    ///
    /// # Errors
    ///
    /// Rejects connection messages, unknown objects, wrong ordering, or a
    /// poisoned task map.
    pub fn apply_task_event(
        &self,
        session: &mut Session,
        message: &DenialMessage,
    ) -> Result<AppliedDenialEvent, DenialSinkError> {
        let received = if frame_trace::enabled() { frame_trace::now_ns() } else { 0 };
        let object = task_object(message).ok_or(DenialSinkError::ConnectionMessage)?;
        let mut tasks = self.lock_tasks()?;
        let task = tasks
            .values_mut()
            .find(|task| task.binding.object() == object)
            .ok_or(DenialSinkError::UnknownObject(object))?;
        if !matches!(message, DenialMessage::BufferReleased { .. }) {
            require_live(task, task.binding.display())?;
        }
        let event = task.binding.apply_event(session, message)?;
        if let AppliedDenialEvent::Configure { width, height, .. } = &event {
            pin_android_display_extent(&mut task.android_display_extent, *width, *height)?;
        }
        if let DenialMessage::BufferReleased { frame, buffer, .. } = message {
            let tracked = task
                .frame_targets
                .remove(frame)
                .ok_or(DenialSinkError::UnknownRenderTarget(*buffer))?;
            if tracked != *buffer {
                return Err(DenialSinkError::BufferMetadataMismatch(*buffer));
            }
            let remove = {
                let target = task
                    .render_targets
                    .get_mut(buffer)
                    .ok_or(DenialSinkError::UnknownRenderTarget(*buffer))?;
                target.busy = false;
                target.revoked
            };
            if remove {
                task.render_targets.remove(buffer);
            }
            self.retirement_changed.notify_all();
            if frame_trace::sampled(frame.0) {
                frame_trace::event("android_reusable", object.0, frame.0, buffer.0,
                    &[("receive_ns", received), ("reusable_ns", frame_trace::now_ns())]);
                if let Some(fence) = task.trace_fences.remove(frame) {
                    match frame_trace::fence_signal_ns(fence.as_fd()) {
                        Ok(Some(signal)) => frame_trace::event("android_gpu_complete", object.0,
                            frame.0, buffer.0, &[("signal_ns", signal)]),
                        _ => frame_trace::event("android_gpu_timestamp_unavailable", object.0,
                            frame.0, buffer.0, &[]),
                    }
                }
            }
        }
        Ok(event)
    }

    /// Cache one Denial-owned render target and its received DMA-BUF planes.
    pub fn register_render_target(
        &self,
        object: TaskObjectId,
        configure_serial: u32,
        buffer: BufferMetadata,
        descriptors: Vec<AttachedDescriptor>,
    ) -> Result<(), DenialSinkError> {
        let planes = descriptors
            .into_iter()
            .map(|descriptor| {
                if descriptor.kind == DescriptorKind::DmabufPlane {
                    Ok(descriptor.fd)
                } else {
                    Err(DenialSinkError::PlaneDescriptorMismatch)
                }
            })
            .collect::<Result<Vec<_>, _>>()?;
        if planes.len() != buffer.planes.len() {
            return Err(DenialSinkError::PlaneDescriptorMismatch);
        }
        let mut tasks = self.lock_tasks()?;
        let task = tasks
            .values_mut()
            .find(|task| task.binding.object() == object)
            .ok_or(DenialSinkError::UnknownObject(object))?;
        // The descriptors above remain local and are dropped on this return.
        // Late metadata cannot add imports to a partial/retiring owner.
        if !task.registration_complete || task.retirement.is_some() { return Ok(()); }
        if task.render_targets.contains_key(&buffer.id) {
            return Err(DenialSinkError::DuplicateRenderTarget(buffer.id));
        }
        task.render_targets.insert(
            buffer.id,
            HostRenderTarget {
                configure_serial,
                metadata: buffer,
                plane_fds: planes,
                reserved: false,
                busy: false,
                revoked: false,
            },
        );
        Ok(())
    }

    /// Drop one Denial-owned render target after the host revokes it.
    pub fn unregister_render_target(
        &self,
        object: TaskObjectId,
        buffer: BufferId,
    ) -> Result<(), DenialSinkError> {
        let mut tasks = self.lock_tasks()?;
        let task = tasks
            .values_mut()
            .find(|task| task.binding.object() == object)
            .ok_or(DenialSinkError::UnknownObject(object))?;
        // Keep accepted-frame/reservation bookkeeping until its own release.
        if !task.registration_complete || task.retirement.is_some() { return Ok(()); }
        let target = task
            .render_targets
            .get_mut(&buffer)
            .ok_or(DenialSinkError::UnknownRenderTarget(buffer))?;
        if target.reserved || target.busy {
            // A resize retires the previous target generation immediately,
            // but Denial can race a revoke against a target SurfaceFlinger is
            // rendering or whose frame is still displayed. Stop selecting it
            // now and drop the cached import after cancellation/release.
            target.revoked = true;
            return Ok(());
        }
        task.render_targets.remove(&buffer);
        Ok(())
    }

    /// Reserve an idle Denial-owned target for SurfaceFlinger's RenderEngine.
    ///
    /// # Errors
    ///
    /// Rejects an unknown display or a pool with no currently idle target.
    pub fn acquire_surfaceflinger_target(
        &self,
        display: DisplayId,
    ) -> Result<ImportedRenderTarget, DenialSinkError> {
        let mut tasks = self.lock_tasks()?;
        let task = tasks
            .get_mut(&display)
            .ok_or(DenialSinkError::UnknownDisplay(display))?;
        require_live(task, display)?;
        let newest_serial = task
            .render_targets
            .values()
            .filter(|target| !target.revoked)
            .map(|target| target.configure_serial)
            .max()
            .ok_or(DenialSinkError::NoRenderTarget(display))?;
        let target = task
            .render_targets
            .values_mut()
            .find(|target| {
                target.configure_serial == newest_serial
                    && !target.reserved
                    && !target.busy
                    && !target.revoked
            })
            .ok_or(DenialSinkError::NoRenderTarget(display))?;
        let plane_fds = target
            .plane_fds
            .iter()
            .map(|fd| {
                fd.try_clone().map_err(|error| {
                    DenialSinkError::Graphics(format!(
                        "duplicate SurfaceFlinger target plane: {error}"
                    ))
                })
            })
            .collect::<Result<Vec<_>, _>>()?;
        target.reserved = true;
        Ok(ImportedRenderTarget {
            metadata: target.metadata.clone(),
            configure_serial: target.configure_serial,
            plane_fds,
        })
    }

    /// Return a target reservation that SurfaceFlinger did not submit.
    pub fn cancel_surfaceflinger_target(&self, display: DisplayId, target: ImportedRenderTarget) {
        self.cancel_reserved_target(display, target.metadata.id);
    }

    /// Import SurfaceFlinger's ready fence and present its already-composed
    /// display target to Denial without another graphics pass.
    ///
    /// # Errors
    ///
    /// Preserves the configure, target ownership, timeline, and release
    /// invariants used by the original HWC composition path.
    pub fn submit_surfaceflinger_target(
        &self,
        session: &mut Session,
        display: DisplayId,
        target: ImportedRenderTarget,
        acquire_fence: Option<std::os::fd::OwnedFd>,
        opaque: bool,
        damage: Option<droidloom_transport::Damage>,
    ) -> Result<droidloom_transport::FrameId, DenialSinkError> {
        // Legacy or unknown damage remains full. The transport validates
        // bounds before accepting the target; empty damage remains empty.
        let damage = damage.unwrap_or(droidloom_transport::Damage {
            x: 0,
            y: 0,
            width: target.metadata.width,
            height: target.metadata.height,
        });
        let damage = if damage.width == 0 && damage.height == 0 {
            Vec::new()
        } else {
            vec![damage]
        };
        let frame = match session
            .windows_mut()
            .composer_for_display_mut(display)
            .map_err(|error| DenialSinkError::Graphics(error.to_string()))?
            .submit_rendered_target(
                display,
                ClientTarget {
                    buffer: target.metadata.clone(),
                    damage,
                    has_acquire_fence: true,
                },
            ) {
            Ok(frame) => frame,
            Err(error) => {
                self.cancel_reserved_target(display, target.metadata.id);
                return Err(error.into());
            }
        };

        if let Err(error) = self.send_surfaceflinger_frame(display, &frame, &target, acquire_fence, opaque)
        {
            if let Ok(composer) = session.windows_mut().composer_for_display_mut(display) {
                let _ = composer.cancel_unsubmitted_target(frame.frame_id);
            }
            self.cancel_reserved_target(display, target.metadata.id);
            return Err(error);
        }
        Ok(frame.frame_id)
    }

    /// Delegate an authenticated pair of sockets to the task's presenter.
    pub fn bind_layer_stream(&self, display: DisplayId, sockets: &[std::os::fd::BorrowedFd<'_>]) -> Result<(), DenialSinkError> {
        let tasks = self.lock_tasks()?;
        let task = tasks.get(&display).ok_or(DenialSinkError::UnknownDisplay(display))?;
        require_live(task, display)?;
        self.socket.send_android(&AndroidMessage::BindLayerStream { object: task.binding.object() }, sockets)?;
        Ok(())
    }

    /// Resolve a protocol task object to its dedicated Composer display.
    ///
    /// # Errors
    ///
    /// Rejects an unknown object or poisoned task map.
    pub fn display_for_object(&self, object: TaskObjectId) -> Result<DisplayId, DenialSinkError> {
        let tasks = self.lock_tasks()?;
        tasks
            .iter()
            .find_map(|(display, task)| (task.binding.object() == object).then_some(*display))
            .ok_or(DenialSinkError::UnknownObject(object))
    }

    fn submit_frame(
        &self,
        display: DisplayId,
        frame: AcceptedFrame,
        target: ImportedRenderTarget,
        mut layers: Vec<PreparedLayer>,
    ) -> Result<ParcelFileDescriptor, PresentationFailure> {
        if target.metadata != frame.buffer {
            self.cancel_reserved_target(display, target.metadata.id);
            return Err(PresentationFailure::unsubmitted(ErrorCode::BadParameter));
        }
        let display_extent = match self.android_display_extent(display) {
            Ok(extent) => extent,
            Err(error) => {
                self.cancel_reserved_target(display, target.metadata.id);
                return Err(PresentationFailure::unsubmitted(error.error_code()));
            }
        };
        let acquire_fence = match self.compose(&target, &mut layers, display_extent) {
            Ok(fence) => fence,
            Err(error) => {
                eprintln!("droidloom-composer: composition failed: {error}");
                self.cancel_reserved_target(display, target.metadata.id);
                return Err(PresentationFailure::unsubmitted(error.error_code()));
            }
        };
        // SurfaceFlinger's present fence protects the Android layer buffers
        // read by Droidloom's composition pass. Denial's independent release
        // event protects the composed, Denial-owned target from reuse; waiting
        // for that event here would deadlock Android presentation on the host
        // UI's next raster frame.
        let present_fence = acquire_fence.as_fd().try_clone_to_owned().map_err(|_| {
            self.cancel_reserved_target(display, target.metadata.id);
            PresentationFailure::unsubmitted(ErrorCode::NoResources)
        })?;
        let mut tasks = self
            .lock_tasks()
            .map_err(|error| PresentationFailure::unsubmitted(error.error_code()))?;
        let task = tasks
            .get_mut(&display)
            .ok_or_else(|| PresentationFailure::unsubmitted(ErrorCode::BadDisplay))?;
        if let Err(error) = require_live(task, display) {
            if let Some(target) = task.render_targets.get_mut(&frame.buffer.id) {
                if !target.busy { target.reserved = false; }
            }
            self.retirement_changed.notify_all();
            return Err(PresentationFailure::unsubmitted(error.error_code()));
        }
        let Some(host_target) = task.render_targets.get(&frame.buffer.id) else {
            return Err(PresentationFailure::unsubmitted(ErrorCode::BadParameter));
        };
        if !host_target.reserved
            || host_target.busy
            || host_target.revoked
            || host_target.metadata != frame.buffer
        {
            return Err(PresentationFailure::unsubmitted(ErrorCode::BadParameter));
        }

        let prepared = task
            .binding
            .prepare_present(display, &frame)
            .map_err(|error| {
                PresentationFailure::unsubmitted(DenialSinkError::from(error).error_code())
            })?;
        if let Err(error) = task
            .timelines
            .import_acquire_fence(prepared.acquire_point, acquire_fence.as_fd())
        {
            cancel_prepared(&mut task.binding, &frame, &prepared);
            if let Some(target) = task.render_targets.get_mut(&frame.buffer.id) {
                target.reserved = false;
            }
            return Err(PresentationFailure::unsubmitted(
                DenialSinkError::from(error).error_code(),
            ));
        }
        if let Err(error) = self.socket.send_android(&prepared.message, &[]) {
            cancel_prepared(&mut task.binding, &frame, &prepared);
            if let Some(target) = task.render_targets.get_mut(&frame.buffer.id) {
                target.reserved = false;
            }
            return Err(PresentationFailure::unsubmitted(
                DenialSinkError::from(error).error_code(),
            ));
        }

        let host_target = task
            .render_targets
            .get_mut(&frame.buffer.id)
            .expect("target was validated before present send");
        host_target.reserved = false;
        host_target.busy = true;
        task.frame_targets.insert(frame.frame_id, frame.buffer.id);

        Ok(ParcelFileDescriptor::new(present_fence))
    }

    fn send_surfaceflinger_frame(
        &self,
        display: DisplayId,
        frame: &AcceptedFrame,
        target: &ImportedRenderTarget,
        acquire_fence: Option<std::os::fd::OwnedFd>,
        opaque: bool,
    ) -> Result<(), DenialSinkError> {
        let tracing = frame_trace::sampled(frame.frame_id.0);
        let begin = if tracing { frame_trace::now_ns() } else { 0 };
        if target.metadata != frame.buffer || !frame.requires_acquire_fence {
            return Err(DenialSinkError::BufferMetadataMismatch(target.metadata.id));
        }
        let mut tasks = self.lock_tasks()?;
        let task = tasks
            .get_mut(&display)
            .ok_or(DenialSinkError::UnknownDisplay(display))?;
        require_live(task, display)?;
        let host_target = task
            .render_targets
            .get(&frame.buffer.id)
            .ok_or(DenialSinkError::UnknownRenderTarget(frame.buffer.id))?;
        if !host_target.reserved
            || host_target.busy
            || host_target.revoked
            || host_target.metadata != frame.buffer
        {
            return Err(DenialSinkError::BufferMetadataMismatch(frame.buffer.id));
        }

        // Send metadata before this exact frame on the ordered transport. A
        // transparent successor must clear a preceding frame's opaque proof.
        if task.content_opaque != Some(opaque) {
            self.socket.send_android(&AndroidMessage::SetContentState {
                object: task.binding.object(),
                flags: if opaque { droidloom_denial_protocol::content_state::OPAQUE } else { 0 },
            }, &[])?;
            task.content_opaque = Some(opaque);
        }
        let prepared = task.binding.prepare_present(display, frame)?;
        let import_begin = if tracing { frame_trace::now_ns() } else { 0 };
        let import_result = if let Some(acquire_fence) = acquire_fence.as_ref() {
            task.timelines
                .import_acquire_fence(prepared.acquire_point, acquire_fence.as_fd())
        } else {
            task.timelines.signal_acquire(prepared.acquire_point)
        };
        if let Err(error) = import_result {
            cancel_prepared(&mut task.binding, frame, &prepared);
            return Err(error.into());
        }
        let present_fence = match task.timelines.export_acquire_fence(prepared.acquire_point) {
            Ok(fence) => fence,
            Err(error) => {
                cancel_prepared(&mut task.binding, frame, &prepared);
                return Err(error.into());
            }
        };
        let send_begin = if tracing { frame_trace::now_ns() } else { 0 };
        if let Err(error) = self.socket.send_android(&prepared.message, &[]) {
            cancel_prepared(&mut task.binding, frame, &prepared);
            return Err(error.into());
        }

        let host_target = task
            .render_targets
            .get_mut(&frame.buffer.id)
            .expect("target was validated before direct present");
        host_target.reserved = false;
        host_target.busy = true;
        task.frame_targets.insert(frame.frame_id, frame.buffer.id);
        task.surfaceflinger_present_fence = Some(present_fence);
        if tracing {
            // Keep the original render fence: exporting an already completed DRM
            // point may replace it with a timestamp-less/global placeholder.
            if let Some(fence) = acquire_fence.as_ref().and_then(|fd| fd.try_clone().ok()) {
                task.trace_fences.insert(frame.frame_id, fence);
            }
            frame_trace::event("android_submit", task.binding.object().0, frame.frame_id.0,
                frame.buffer.id.0, &[("display", display.0), ("begin_ns", begin),
                    ("import_begin_ns", import_begin), ("send_begin_ns", send_begin),
                    ("send_done_ns", frame_trace::now_ns()), ("acquire_point", prepared.acquire_point)]);
        }
        Ok(())
    }

    fn compose(
        &self,
        target: &ImportedRenderTarget,
        layers: &mut [PreparedLayer],
        display_extent: (u32, u32),
    ) -> Result<std::os::fd::OwnedFd, DenialSinkError> {
        let mut compositor = self
            .compositor
            .lock()
            .map_err(|_| DenialSinkError::Poisoned)?;
        if compositor.is_none() {
            *compositor = Some(
                LayerCompositor::new(self.device.as_fd())
                    .map_err(|error| DenialSinkError::Graphics(error.to_string()))?,
            );
        }
        compositor
            .as_mut()
            .expect("initialized above")
            .compose(target, layers, display_extent)
            .map_err(|error| DenialSinkError::Graphics(error.to_string()))
    }

    fn android_display_extent(&self, display: DisplayId) -> Result<(u32, u32), DenialSinkError> {
        let tasks = self.lock_tasks()?;
        let task = tasks
            .get(&display)
            .ok_or(DenialSinkError::UnknownDisplay(display))?;
        require_live(task, display)?;
        task.android_display_extent.ok_or_else(|| {
            DenialSinkError::Graphics("Android display extent is not configured".to_owned())
        })
    }

    fn cancel_reserved_target(&self, display: DisplayId, buffer: BufferId) {
        if let Ok(mut tasks) = self.tasks.lock() {
            if let Some(task) = tasks.get_mut(&display) {
                let remove = if let Some(target) = task.render_targets.get_mut(&buffer) {
                    if !target.busy {
                        target.reserved = false;
                    }
                    !target.busy && !target.reserved && target.revoked
                } else {
                    false
                };
                if remove {
                    task.render_targets.remove(&buffer);
                }
                self.retirement_changed.notify_all();
            }
        }
    }

    fn lock_tasks(
        &self,
    ) -> Result<MutexGuard<'_, TaskTable>, DenialSinkError> {
        self.tasks.lock().map_err(|_| DenialSinkError::Poisoned)
    }
}

impl PresentationSink for DenialPresentationSink {
    fn acquire_target(&mut self, display: DisplayId) -> Result<ImportedRenderTarget, ErrorCode> {
        let mut tasks = self.lock_tasks().map_err(|error| error.error_code())?;
        let task = tasks.get_mut(&display).ok_or(ErrorCode::BadDisplay)?;
        require_live(task, display).map_err(|error| error.error_code())?;
        let newest_serial = task
            .render_targets
            .values()
            .filter(|target| !target.revoked)
            .map(|target| target.configure_serial)
            .max()
            .ok_or(ErrorCode::NoResources)?;
        let target = task
            .render_targets
            .values_mut()
            .find(|target| {
                target.configure_serial == newest_serial
                    && !target.reserved
                    && !target.busy
                    && !target.revoked
            })
            .ok_or(ErrorCode::NoResources)?;
        let plane_fds = target
            .plane_fds
            .iter()
            .map(|fd| fd.try_clone().map_err(|_| ErrorCode::NoResources))
            .collect::<Result<Vec<_>, _>>()?;
        target.reserved = true;
        Ok(ImportedRenderTarget {
            metadata: target.metadata.clone(),
            configure_serial: target.configure_serial,
            plane_fds,
        })
    }

    fn cancel_target(&mut self, display: DisplayId, target: ImportedRenderTarget) {
        self.cancel_reserved_target(display, target.metadata.id);
    }

    fn take_direct_present_fence(
        &mut self,
        display: DisplayId,
    ) -> Result<ParcelFileDescriptor, ErrorCode> {
        let mut tasks = self.lock_tasks().map_err(|error| error.error_code())?;
        let task = tasks.get_mut(&display).ok_or(ErrorCode::BadDisplay)?;
        task.surfaceflinger_present_fence
            .take()
            .map(ParcelFileDescriptor::new)
            .ok_or(ErrorCode::NoResources)
    }

    fn submit(
        &mut self,
        display: DisplayId,
        frame: AcceptedFrame,
        target: ImportedRenderTarget,
        layers: Vec<PreparedLayer>,
    ) -> Result<ParcelFileDescriptor, PresentationFailure> {
        self.submit_frame(display, frame, target, layers)
    }
}

#[derive(Debug, Default)]
struct TaskTable {
    channels: BTreeMap<DisplayId, TaskChannel>,
    preparations: BTreeMap<DisplayId, PreparingTask>,
    next_nonce: u64,
    peer_disconnected: bool,
}
impl std::ops::Deref for TaskTable {
    type Target = BTreeMap<DisplayId, TaskChannel>;
    fn deref(&self) -> &Self::Target { &self.channels }
}
impl std::ops::DerefMut for TaskTable {
    fn deref_mut(&mut self) -> &mut Self::Target { &mut self.channels }
}

#[derive(Debug)]
struct PreparingTask {
    object: TaskObjectId,
    primary_error: Option<String>,
}

#[derive(Debug)]
struct PendingRetirement {
    nonce: RetirementNonce,
    send_attempted: bool,
    send_error: Option<String>,
    receipt_received: bool,
}

fn require_live(task: &TaskChannel, display: DisplayId) -> Result<(), DenialSinkError> {
    if !task.registration_complete {
        Err(DenialSinkError::RegistrationIncomplete(display))
    } else if task.retirement.is_some() {
        Err(DenialSinkError::TaskRetiring(display))
    } else {
        Ok(())
    }
}

#[derive(Debug)]
struct TaskChannel {
    binding: DenialTaskBinding,
    timelines: AndroidTaskTimelines,
    registration_complete: bool,
    create_attempted: bool,
    create_sent: bool,
    timelines_attempted: bool,
    primary_registration_error: Option<String>,
    retirement: Option<PendingRetirement>,
    render_targets: BTreeMap<BufferId, HostRenderTarget>,
    frame_targets: BTreeMap<droidloom_transport::FrameId, BufferId>,
    /// Sampled original render fences, bounded by the existing in-flight pool.
    trace_fences: BTreeMap<droidloom_transport::FrameId, std::os::fd::OwnedFd>,
    /// Last opaque-coverage proof sent to the host for this task.
    content_opaque: Option<bool>,
    /// SurfaceFlinger's GPU completion fence awaiting Composer3 present reply.
    surfaceflinger_present_fence: Option<std::os::fd::OwnedFd>,
    /// SurfaceFlinger display space pinned by the first hotplug configure.
    /// Denial may resize or scale the target independently, while Android
    /// layer frames remain in this stable coordinate space.
    android_display_extent: Option<(u32, u32)>,
}

#[derive(Debug)]
struct HostRenderTarget {
    configure_serial: u32,
    metadata: BufferMetadata,
    plane_fds: Vec<std::os::fd::OwnedFd>,
    reserved: bool,
    busy: bool,
    /// Denial retired this generation while a render or displayed frame still
    /// owned it. The cache entry is removed at the corresponding safe point.
    revoked: bool,
}

fn cancel_prepared(
    binding: &mut DenialTaskBinding,
    frame: &AcceptedFrame,
    prepared: &PreparedPresent,
) {
    let _ = binding.cancel_unsubmitted_present(frame.frame_id, prepared.release_point);
}

fn task_object(message: &DenialMessage) -> Option<TaskObjectId> {
    match message {
        DenialMessage::FormatFeedback { object, .. }
        | DenialMessage::RegisterRenderTarget { object, .. }
        | DenialMessage::UnregisterRenderTarget { object, .. }
        | DenialMessage::Configure { object, .. }
        | DenialMessage::Insets { object, .. }
        | DenialMessage::Visibility { object, .. }
        | DenialMessage::Close { object }
        | DenialMessage::BufferReleased { object, .. }
        | DenialMessage::Presented { object, .. }
        | DenialMessage::Input { object, .. } => Some(*object),
        DenialMessage::TaskRetired { .. } => None,
        DenialMessage::Error { object, .. } => *object,
        DenialMessage::ServerHello { .. } | DenialMessage::Ping { .. } => None,
    }
}

fn pin_android_display_extent(
    extent: &mut Option<(u32, u32)>,
    width: u32,
    height: u32,
) -> Result<(), DenialSinkError> {
    if width == 0 || height == 0 {
        return Err(DenialSinkError::Graphics(
            "invalid Android display extent".to_owned(),
        ));
    }
    extent.get_or_insert((width, height));
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::pin_android_display_extent;


    #[test]
    fn android_display_extent_remains_the_hotplug_size() {
        let mut extent = None;
        pin_android_display_extent(&mut extent, 480, 800).expect("initial configure");
        pin_android_display_extent(&mut extent, 1264, 2684).expect("host-scale configure");
        assert_eq!(extent, Some((480, 800)));
    }

    #[test]
    fn android_display_extent_rejects_empty_configures() {
        let mut extent = None;
        assert!(pin_android_display_extent(&mut extent, 0, 800).is_err());
        assert_eq!(extent, None);
    }
}
