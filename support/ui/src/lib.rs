107cfbba18862eceb203051cd34d50c21b1c47c1
//! Boundary state for the host UI prototype.
//!
//! This crate is deliberately a small, pure Rust model.  It does not start a
//! process, own a Wayland socket, or grant an OS capability.  Its purpose is
//! to make the failure-domain contract executable and testable:
//!
//! * the shell is an independent client and can restart without touching an
//!   application's process;
//! * a compositor/session restart disconnects client surfaces and requires an
//!   explicit reattach; and
//! * a GPU reset has an explicit outcome and invalidates surfaces until they
//!   are recreated.
//!
//! The HOS2 portion below is an observation-only adapter over the shared
//! `hos2-os-abi` codec.  It intentionally exposes no budget, revoke, or device
//! operation and defines no second wire or permission protocol.

use std::collections::BTreeMap;

/// Pure state model for the initial full-display Android host contract.
///
/// This module is intentionally a consumer-side contract model.  It does not
/// open a SurfaceFlinger handle, import a dma-buf, create a native fence, or
/// define an Android wire protocol.  A08 owns those semantics; this model is
/// only used to make generation, buffer lifetime, synchronization, input and
/// lifecycle decisions explicit before a real implementation is connected.
pub mod android;

pub use hos2_os_abi::{
    DeliveryRequest, DeliveryState, Error as Hos2CodecError, Opcode, QueryAbiResponse,
    QueryDeliveryResponse, ReadUsageResponse, Request, RequestPayload, Response, ResponsePayload,
    Status,
};

/// A non-zero identifier for an application process tracked by the model.
#[derive(Clone, Copy, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
pub struct AppId(u64);

impl AppId {
    /// Construct an application id.  Zero is reserved and therefore rejected.
    pub const fn new(value: u64) -> Option<Self> {
        if value == 0 {
            None
        } else {
            Some(Self(value))
        }
    }

    pub const fn get(self) -> u64 {
        self.0
    }
}

/// A non-zero identifier for a UI session.  It is a label in this model, not
/// an authentication credential.
#[derive(Clone, Copy, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
pub struct SessionId(u128);

impl SessionId {
    pub const fn new(value: u128) -> Option<Self> {
        if value == 0 {
            None
        } else {
            Some(Self(value))
        }
    }

    pub const fn get(self) -> u128 {
        self.0
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ProcessState {
    Stopped,
    Running,
    Restarting,
    Failed,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum LinkState {
    Down,
    Connecting,
    Up,
    Reconnecting,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum GpuState {
    /// No reset is in progress.  The generation identifies the last known
    /// renderer/device instance, not a hardware handle.
    Ready {
        generation: u64,
    },
    Resetting {
        from_generation: u64,
    },
    /// Reset finished, but the renderer could not be trusted to recover.
    Failed {
        generation: u64,
    },
}

impl GpuState {
    pub const fn generation(self) -> u64 {
        match self {
            Self::Ready { generation }
            | Self::Resetting {
                from_generation: generation,
            }
            | Self::Failed { generation } => generation,
        }
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum AppProcessState {
    Running,
    Exited { code: Option<i32> },
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum DetachReason {
    NotConnected,
    CompositorRestart,
    SessionRestart,
    GpuReset,
    ExplicitDisconnect,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum AppConnectionState {
    /// The process exists but has no client connection to the compositor.
    Detached {
        reason: DetachReason,
    },
    Attached,
    Closed,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum SurfaceState {
    None,
    Attached { gpu_generation: u64 },
    NeedsRecreate { gpu_generation: u64 },
    Lost,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct ShellSnapshot {
    pub process: ProcessState,
    pub generation: u64,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct SessionSnapshot {
    pub id: SessionId,
    pub process: ProcessState,
    pub generation: u64,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct CompositorSnapshot {
    pub process: ProcessState,
    pub session_link: LinkState,
    pub generation: u64,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct AppSnapshot {
    pub id: AppId,
    pub process: AppProcessState,
    pub connection: AppConnectionState,
    pub surface: SurfaceState,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct DesktopSnapshot {
    pub shell: ShellSnapshot,
    pub session: SessionSnapshot,
    pub compositor: CompositorSnapshot,
    pub gpu: GpuState,
    pub apps: Vec<AppSnapshot>,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Component {
    Shell,
    Session,
    Compositor,
    Gpu,
    App(AppId),
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum TransitionError {
    InvalidTransition {
        component: Component,
        process: ProcessState,
    },
    SessionUnavailable,
    CompositorUnavailable,
    AppAlreadyExists,
    AppNotFound,
    AppExited,
    AppAlreadyAttached,
    AppNotAttached,
    SurfaceNotRecreatable,
    GpuResetInProgress,
    GpuNotResetting,
    GpuUnavailable,
    GenerationExhausted,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct AppRegistration {
    pub id: AppId,
    pub process: AppProcessState,
    pub connection: AppConnectionState,
    pub surface: SurfaceState,
}

#[derive(Clone, Debug)]
struct AppRecord {
    process: AppProcessState,
    connection: AppConnectionState,
    surface: SurfaceState,
}

/// An in-memory model of the shell/session/compositor process boundary.
///
/// The model is intentionally conservative.  A process can survive a failed
/// compositor or session link, but a client surface is only reported attached
/// after an explicit `reattach_app` call.  No method infers reattachment from
/// a PID, a shell restart, or a model-generated message.
#[derive(Clone, Debug)]
pub struct DesktopRuntime {
    shell: ShellSnapshot,
    session: SessionSnapshot,
    compositor: CompositorSnapshot,
    gpu: GpuState,
    apps: BTreeMap<AppId, AppRecord>,
}

impl DesktopRuntime {
    pub fn new(session_id: SessionId) -> Self {
        Self {
            shell: ShellSnapshot {
                process: ProcessState::Stopped,
                generation: 0,
            },
            session: SessionSnapshot {
                id: session_id,
                process: ProcessState::Stopped,
                generation: 0,
            },
            compositor: CompositorSnapshot {
                process: ProcessState::Stopped,
                session_link: LinkState::Down,
                generation: 0,
            },
            gpu: GpuState::Ready { generation: 0 },
            apps: BTreeMap::new(),
        }
    }

    pub const fn shell(&self) -> ShellSnapshot {
        self.shell
    }

    pub const fn session(&self) -> SessionSnapshot {
        self.session
    }

    pub const fn compositor(&self) -> CompositorSnapshot {
        self.compositor
    }

    pub const fn gpu(&self) -> GpuState {
        self.gpu
    }

    pub fn snapshot(&self) -> DesktopSnapshot {
        DesktopSnapshot {
            shell: self.shell,
            session: self.session,
            compositor: self.compositor,
            gpu: self.gpu,
            apps: self
                .apps
                .iter()
                .map(|(&id, record)| AppSnapshot {
                    id,
                    process: record.process,
                    connection: record.connection,
                    surface: record.surface,
                })
                .collect(),
        }
    }

    pub fn app(&self, id: AppId) -> Option<AppSnapshot> {
        self.apps.get(&id).map(|record| AppSnapshot {
            id,
            process: record.process,
            connection: record.connection,
            surface: record.surface,
        })
    }

    pub fn start_session(&mut self) -> Result<SessionSnapshot, TransitionError> {
        match self.session.process {
            ProcessState::Stopped | ProcessState::Failed => {
                let generation = next(self.session.generation)?;
                self.session.process = ProcessState::Running;
                self.session.generation = generation;
                Ok(self.session)
            }
            process => Err(TransitionError::InvalidTransition {
                component: Component::Session,
                process,
            }),
        }
    }

    /// Restart the session process while preserving the compositor process
    /// record.  Existing client processes survive, but their surfaces are
    /// detached and the compositor link must be reconnected explicitly.
    pub fn restart_session(&mut self) -> Result<SessionSnapshot, TransitionError> {
        if self.session.process != ProcessState::Running {
            return Err(TransitionError::InvalidTransition {
                component: Component::Session,
                process: self.session.process,
            });
        }
        let generation = next(self.session.generation)?;
        self.session.process = ProcessState::Restarting;
        self.session.generation = generation;
        self.detach_apps(DetachReason::SessionRestart);
        self.session.process = ProcessState::Running;
        self.compositor.session_link = if self.compositor.process == ProcessState::Running {
            LinkState::Reconnecting
        } else {
            LinkState::Down
        };
        Ok(self.session)
    }

    /// Reconnect an already-running compositor to a restarted session.  A
    /// compositor process restart itself is handled by
    /// [`Self::reconnect_compositor`].
    pub fn reconnect_session(&mut self) -> Result<(), TransitionError> {
        if self.session.process != ProcessState::Running {
            return Err(TransitionError::SessionUnavailable);
        }
        if self.compositor.process != ProcessState::Running {
            return Err(TransitionError::CompositorUnavailable);
        }
        if !matches!(
            self.compositor.session_link,
            LinkState::Down | LinkState::Connecting | LinkState::Reconnecting
        ) {
            return Err(TransitionError::InvalidTransition {
                component: Component::Session,
                process: self.session.process,
            });
        }
        self.compositor.session_link = LinkState::Up;
        Ok(())
    }

    pub fn stop_session(&mut self) -> Result<(), TransitionError> {
        if self.session.process == ProcessState::Stopped {
            return Err(TransitionError::InvalidTransition {
                component: Component::Session,
                process: self.session.process,
            });
        }
        let generation = next(self.session.generation)?;
        self.session.process = ProcessState::Stopped;
        self.session.generation = generation;
        self.compositor.session_link = LinkState::Down;
        self.detach_apps(DetachReason::SessionRestart);
        Ok(())
    }

    pub fn crash_session(&mut self) -> Result<(), TransitionError> {
        if self.session.process == ProcessState::Stopped {
            return Err(TransitionError::InvalidTransition {
                component: Component::Session,
                process: self.session.process,
            });
        }
        let generation = next(self.session.generation)?;
        self.session.process = ProcessState::Failed;
        self.session.generation = generation;
        self.compositor.session_link = LinkState::Down;
        self.detach_apps(DetachReason::SessionRestart);
        Ok(())
    }

    pub fn start_compositor(&mut self) -> Result<CompositorSnapshot, TransitionError> {
        if self.session.process != ProcessState::Running {
            return Err(TransitionError::SessionUnavailable);
        }
        match self.compositor.process {
            ProcessState::Stopped | ProcessState::Failed => {
                let generation = next(self.compositor.generation)?;
                self.compositor.process = ProcessState::Running;
                self.compositor.generation = generation;
                self.compositor.session_link = LinkState::Up;
                Ok(self.compositor)
            }
            process => Err(TransitionError::InvalidTransition {
                component: Component::Compositor,
                process,
            }),
        }
    }

    /// Begin a compositor restart.  Applications remain running, but all
    /// compositor client links and surfaces become detached/lost until the
    /// explicit reconnect and reattach operations succeed.
    pub fn restart_compositor(&mut self) -> Result<(), TransitionError> {
        if self.compositor.process != ProcessState::Running {
            return Err(TransitionError::InvalidTransition {
                component: Component::Compositor,
                process: self.compositor.process,
            });
        }
        let generation = next(self.compositor.generation)?;
        self.compositor.process = ProcessState::Restarting;
        self.compositor.session_link = LinkState::Reconnecting;
        self.compositor.generation = generation;
        self.detach_apps(DetachReason::CompositorRestart);
        Ok(())
    }

    pub fn crash_compositor(&mut self) -> Result<(), TransitionError> {
        if self.compositor.process == ProcessState::Stopped {
            return Err(TransitionError::InvalidTransition {
                component: Component::Compositor,
                process: self.compositor.process,
            });
        }
        let generation = next(self.compositor.generation)?;
        self.compositor.process = ProcessState::Failed;
        self.compositor.session_link = LinkState::Down;
        self.compositor.generation = generation;
        self.detach_apps(DetachReason::CompositorRestart);
        Ok(())
    }

    /// Finish a compositor restart after the session link has been observed.
    /// This does not reattach any application automatically.
    pub fn reconnect_compositor(&mut self) -> Result<(), TransitionError> {
        if self.session.process != ProcessState::Running {
            return Err(TransitionError::SessionUnavailable);
        }
        if !matches!(
            self.compositor.process,
            ProcessState::Restarting | ProcessState::Failed
        ) {
            return Err(TransitionError::InvalidTransition {
                component: Component::Compositor,
                process: self.compositor.process,
            });
        }
        self.compositor.process = ProcessState::Running;
        self.compositor.session_link = LinkState::Up;
        Ok(())
    }

    pub fn start_shell(&mut self) -> Result<ShellSnapshot, TransitionError> {
        match self.shell.process {
            ProcessState::Stopped | ProcessState::Failed => {
                let generation = next(self.shell.generation)?;
                self.shell.process = ProcessState::Running;
                self.shell.generation = generation;
                Ok(self.shell)
            }
            process => Err(TransitionError::InvalidTransition {
                component: Component::Shell,
                process,
            }),
        }
    }

    /// Restart only the shell process.  The session, compositor, client
    /// process records, and surfaces are intentionally untouched.
    pub fn restart_shell(&mut self) -> Result<ShellSnapshot, TransitionError> {
        if self.shell.process != ProcessState::Running {
            return Err(TransitionError::InvalidTransition {
                component: Component::Shell,
                process: self.shell.process,
            });
        }
        let generation = next(self.shell.generation)?;
        self.shell.process = ProcessState::Restarting;
        self.shell.generation = generation;
        self.shell.process = ProcessState::Running;
        Ok(self.shell)
    }

    pub fn crash_shell(&mut self) -> Result<(), TransitionError> {
        if self.shell.process == ProcessState::Stopped {
            return Err(TransitionError::InvalidTransition {
                component: Component::Shell,
                process: self.shell.process,
            });
        }
        let generation = next(self.shell.generation)?;
        self.shell.process = ProcessState::Failed;
        self.shell.generation = generation;
        Ok(())
    }

    pub fn register_app(&mut self, registration: AppRegistration) -> Result<(), TransitionError> {
        if self.apps.contains_key(&registration.id) {
            return Err(TransitionError::AppAlreadyExists);
        }
        self.apps.insert(
            registration.id,
            AppRecord {
                process: registration.process,
                connection: registration.connection,
                surface: registration.surface,
            },
        );
        Ok(())
    }

    pub fn launch_app(&mut self, id: AppId) -> Result<(), TransitionError> {
        if self.apps.contains_key(&id) {
            return Err(TransitionError::AppAlreadyExists);
        }
        self.apps.insert(
            id,
            AppRecord {
                process: AppProcessState::Running,
                connection: AppConnectionState::Detached {
                    reason: DetachReason::NotConnected,
                },
                surface: SurfaceState::None,
            },
        );
        Ok(())
    }

    /// Attach a running application after the compositor and session have
    /// independently reported a usable connection.
    pub fn reattach_app(&mut self, id: AppId) -> Result<(), TransitionError> {
        if self.session.process != ProcessState::Running {
            return Err(TransitionError::SessionUnavailable);
        }
        if self.compositor.process != ProcessState::Running
            || self.compositor.session_link != LinkState::Up
        {
            return Err(TransitionError::CompositorUnavailable);
        }
        if !matches!(self.gpu, GpuState::Ready { .. }) {
            return Err(TransitionError::GpuUnavailable);
        }
        let Some(app) = self.apps.get_mut(&id) else {
            return Err(TransitionError::AppNotFound);
        };
        if app.process != AppProcessState::Running {
            return Err(TransitionError::AppExited);
        }
        if app.connection == AppConnectionState::Attached {
            return Err(TransitionError::AppAlreadyAttached);
        }
        app.connection = AppConnectionState::Attached;
        app.surface = SurfaceState::Attached {
            gpu_generation: self.gpu.generation(),
        };
        Ok(())
    }

    pub fn disconnect_app(&mut self, id: AppId) -> Result<(), TransitionError> {
        let Some(app) = self.apps.get_mut(&id) else {
            return Err(TransitionError::AppNotFound);
        };
        if app.process != AppProcessState::Running {
            return Err(TransitionError::AppExited);
        }
        app.connection = AppConnectionState::Detached {
            reason: DetachReason::ExplicitDisconnect,
        };
        app.surface = SurfaceState::None;
        Ok(())
    }

    /// Recreate only the surface after a recovered GPU reset.  The app's
    /// process and compositor client remain distinct lifecycle objects.
    pub fn recreate_app_surface(&mut self, id: AppId) -> Result<(), TransitionError> {
        if self.gpu.generation() == 0 || !matches!(self.gpu, GpuState::Ready { .. }) {
            return Err(TransitionError::GpuUnavailable);
        }
        if self.session.process != ProcessState::Running {
            return Err(TransitionError::SessionUnavailable);
        }
        if self.compositor.process != ProcessState::Running
            || self.compositor.session_link != LinkState::Up
        {
            return Err(TransitionError::CompositorUnavailable);
        }
        let Some(app) = self.apps.get_mut(&id) else {
            return Err(TransitionError::AppNotFound);
        };
        if app.process != AppProcessState::Running {
            return Err(TransitionError::AppExited);
        }
        if app.connection != AppConnectionState::Attached {
            return Err(TransitionError::AppNotAttached);
        }
        if !matches!(app.surface, SurfaceState::NeedsRecreate { .. }) {
            return Err(TransitionError::SurfaceNotRecreatable);
        }
        app.surface = SurfaceState::Attached {
            gpu_generation: self.gpu.generation(),
        };
        Ok(())
    }

    pub fn exit_app(&mut self, id: AppId, code: Option<i32>) -> Result<(), TransitionError> {
        let Some(app) = self.apps.get_mut(&id) else {
            return Err(TransitionError::AppNotFound);
        };
        app.process = AppProcessState::Exited { code };
        app.connection = AppConnectionState::Closed;
        app.surface = SurfaceState::Lost;
        Ok(())
    }

    pub fn begin_gpu_reset(&mut self) -> Result<(), TransitionError> {
        let generation = self.gpu.generation();
        if matches!(self.gpu, GpuState::Resetting { .. }) {
            return Err(TransitionError::GpuResetInProgress);
        }
        self.gpu = GpuState::Resetting {
            from_generation: generation,
        };
        for app in self.apps.values_mut() {
            if app.process == AppProcessState::Running
                && app.connection == AppConnectionState::Attached
            {
                app.surface = SurfaceState::NeedsRecreate {
                    gpu_generation: generation,
                };
            }
        }
        Ok(())
    }

    pub fn finish_gpu_reset(&mut self, recovered: bool) -> Result<(), TransitionError> {
        let GpuState::Resetting { from_generation } = self.gpu else {
            return Err(TransitionError::GpuNotResetting);
        };
        let generation = next(from_generation)?;
        self.gpu = if recovered {
            GpuState::Ready { generation }
        } else {
            GpuState::Failed { generation }
        };
        for app in self.apps.values_mut() {
            if app.process == AppProcessState::Running {
                app.surface = if recovered {
                    if app.connection == AppConnectionState::Attached {
                        SurfaceState::NeedsRecreate {
                            gpu_generation: generation,
                        }
                    } else {
                        SurfaceState::Lost
                    }
                } else {
                    app.connection = AppConnectionState::Detached {
                        reason: DetachReason::GpuReset,
                    };
                    SurfaceState::Lost
                };
            }
        }
        Ok(())
    }

    fn detach_apps(&mut self, reason: DetachReason) {
        for app in self.apps.values_mut() {
            if app.process == AppProcessState::Running {
                app.connection = AppConnectionState::Detached { reason };
                app.surface = SurfaceState::Lost;
            }
        }
    }
}

fn next(value: u64) -> Result<u64, TransitionError> {
    value
        .checked_add(1)
        .ok_or(TransitionError::GenerationExhausted)
}

/// Read-only access to the already-defined HOS2 observation operations.
///
/// Implementors are expected to be A02/A05 owned transport consumers.  The
/// UI model does not construct wire frames, choose credentials, or issue
/// mutation opcodes.  A source may reject a call with the shared codec error
/// or with `ReadOnlyError::Unavailable`; neither result is interpreted as a
/// successful operation.
pub trait Hos2ReadOnlySource {
    type Error;

    fn query_abi(&self, request_id: [u8; 16]) -> Result<QueryAbiResponse, Self::Error>;
    fn read_usage(
        &self,
        request_id: [u8; 16],
        target_slot: u64,
        target_generation: u64,
    ) -> Result<ReadUsageResponse, Self::Error>;
    fn query_delivery(
        &self,
        request_id: [u8; 16],
        target_slot: u64,
        target_generation: u64,
        request: DeliveryRequest,
    ) -> Result<QueryDeliveryResponse, Self::Error>;
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ReadOnlyError<E> {
    Unavailable,
    Transport(E),
    Rejected(Status),
    MutationNotAllowed,
    MalformedResponse,
}

/// A typed adapter for a transport that accepts existing HOS2 requests and
/// returns existing HOS2 responses.  It forwards only QueryAbi, ReadUsage and
/// QueryDelivery, rejecting all mutation opcodes before transport use.
pub struct Hos2ReadOnlyAdapter<T> {
    transport: T,
}

impl<T> Hos2ReadOnlyAdapter<T> {
    pub const fn new(transport: T) -> Self {
        Self { transport }
    }

    pub fn into_inner(self) -> T {
        self.transport
    }
}

pub trait Hos2ReadTransport {
    type Error;

    fn exchange(&self, request: Request) -> Result<Response, Self::Error>;
}

impl<T> Hos2ReadOnlyAdapter<T>
where
    T: Hos2ReadTransport,
{
    /// Forward an existing HOS2 request only when its opcode is one of the
    /// observation operations.  The adapter never forwards InstallBudget or
    /// RetireThrough, and it does not manufacture an authorization decision.
    pub fn exchange_read_only(
        &self,
        request: Request,
    ) -> Result<Response, ReadOnlyError<T::Error>> {
        if !matches!(
            request.opcode,
            Opcode::QueryAbi | Opcode::ReadUsage | Opcode::QueryDelivery
        ) {
            return Err(ReadOnlyError::MutationNotAllowed);
        }
        self.transport
            .exchange(request)
            .map_err(ReadOnlyError::Transport)
    }
}

impl<T> Hos2ReadOnlySource for Hos2ReadOnlyAdapter<T>
where
    T: Hos2ReadTransport,
{
    type Error = ReadOnlyError<T::Error>;

    fn query_abi(&self, request_id: [u8; 16]) -> Result<QueryAbiResponse, Self::Error> {
        let response = self
            .transport
            .exchange(Request {
                opcode: Opcode::QueryAbi,
                request_id,
                target_slot: 0,
                target_generation: 0,
                payload: RequestPayload::QueryAbi,
            })
            .map_err(ReadOnlyError::Transport)?;
        match response {
            Response {
                opcode: Opcode::QueryAbi,
                status: Status::Ok,
                payload: ResponsePayload::QueryAbi(payload),
                ..
            } => Ok(payload),
            Response {
                opcode: Opcode::QueryAbi,
                status: Status::Ok,
                ..
            } => Err(ReadOnlyError::MalformedResponse),
            Response {
                opcode: Opcode::QueryAbi,
                status,
                ..
            } => Err(ReadOnlyError::Rejected(status)),
            Response { .. } => Err(ReadOnlyError::MalformedResponse),
        }
    }

    fn read_usage(
        &self,
        request_id: [u8; 16],
        target_slot: u64,
        target_generation: u64,
    ) -> Result<ReadUsageResponse, Self::Error> {
        let response = self
            .transport
            .exchange(Request {
                opcode: Opcode::ReadUsage,
                request_id,
                target_slot,
                target_generation,
                payload: RequestPayload::ReadUsage,
            })
            .map_err(ReadOnlyError::Transport)?;
        match response {
            Response {
                opcode: Opcode::ReadUsage,
                status: Status::Ok,
                payload: ResponsePayload::ReadUsage(payload),
                ..
            } => Ok(payload),
            Response {
                opcode: Opcode::ReadUsage,
                status: Status::Ok,
                ..
            } => Err(ReadOnlyError::MalformedResponse),
            Response {
                opcode: Opcode::ReadUsage,
                status,
                ..
            } => Err(ReadOnlyError::Rejected(status)),
            Response { .. } => Err(ReadOnlyError::MalformedResponse),
        }
    }

    fn query_delivery(
        &self,
        request_id: [u8; 16],
        target_slot: u64,
        target_generation: u64,
        request: DeliveryRequest,
    ) -> Result<QueryDeliveryResponse, Self::Error> {
        let response = self
            .transport
            .exchange(Request {
                opcode: Opcode::QueryDelivery,
                request_id,
                target_slot,
                target_generation,
                payload: RequestPayload::QueryDelivery(request),
            })
            .map_err(ReadOnlyError::Transport)?;
        match response {
            Response {
                opcode: Opcode::QueryDelivery,
                status: Status::Ok,
                payload: ResponsePayload::QueryDelivery(payload),
                ..
            } => Ok(payload),
            Response {
                opcode: Opcode::QueryDelivery,
                status: Status::Ok,
                ..
            } => Err(ReadOnlyError::MalformedResponse),
            Response {
                opcode: Opcode::QueryDelivery,
                status,
                ..
            } => Err(ReadOnlyError::Rejected(status)),
            Response { .. } => Err(ReadOnlyError::MalformedResponse),
        }
    }
}

/// An adapter result used by callers that want to distinguish a transport
/// failure from an actual HOS2 status without introducing another status enum.
pub fn classify_response(response: &Response) -> Result<&ResponsePayload, Status> {
    if response.status == Status::Ok {
        Ok(&response.payload)
    } else {
        Err(response.status)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn id(value: u64) -> AppId {
        AppId::new(value).expect("non-zero app id")
    }

    fn runtime() -> DesktopRuntime {
        DesktopRuntime::new(SessionId::new(1).expect("non-zero session id"))
    }

    fn ready_runtime() -> DesktopRuntime {
        let mut runtime = runtime();
        runtime.start_session().unwrap();
        runtime.start_compositor().unwrap();
        runtime.start_shell().unwrap();
        runtime.launch_app(id(7)).unwrap();
        runtime.reattach_app(id(7)).unwrap();
        runtime
    }

    #[test]
    fn shell_restart_preserves_session_compositor_and_app_process() {
        let mut runtime = ready_runtime();
        let before = runtime.snapshot();
        runtime.restart_shell().unwrap();
        let after = runtime.snapshot();
        assert_eq!(after.session, before.session);
        assert_eq!(after.compositor, before.compositor);
        assert_eq!(after.gpu, before.gpu);
        assert_eq!(after.apps[0].process, AppProcessState::Running);
        assert_eq!(after.apps[0].connection, AppConnectionState::Attached);
        assert_ne!(after.shell.generation, before.shell.generation);
    }

    #[test]
    fn compositor_restart_detaches_without_claiming_reattach() {
        let mut runtime = ready_runtime();
        runtime.restart_compositor().unwrap();
        let detached = runtime.app(id(7)).unwrap();
        assert_eq!(detached.process, AppProcessState::Running);
        assert_eq!(
            detached.connection,
            AppConnectionState::Detached {
                reason: DetachReason::CompositorRestart
            }
        );
        assert_eq!(detached.surface, SurfaceState::Lost);
        runtime.reconnect_compositor().unwrap();
        assert_eq!(
            runtime.app(id(7)).unwrap().connection,
            AppConnectionState::Detached {
                reason: DetachReason::CompositorRestart
            }
        );
        runtime.reattach_app(id(7)).unwrap();
        assert_eq!(
            runtime.app(id(7)).unwrap().connection,
            AppConnectionState::Attached
        );
    }

    #[test]
    fn session_failure_is_separate_from_shell_and_app_process() {
        let mut runtime = ready_runtime();
        runtime.crash_session().unwrap();
        assert_eq!(runtime.shell().process, ProcessState::Running);
        assert_eq!(runtime.compositor().session_link, LinkState::Down);
        let app = runtime.app(id(7)).unwrap();
        assert_eq!(app.process, AppProcessState::Running);
        assert_eq!(
            app.connection,
            AppConnectionState::Detached {
                reason: DetachReason::SessionRestart
            }
        );
    }

    #[test]
    fn session_restart_requires_link_reconnect_before_reattach() {
        let mut runtime = ready_runtime();
        let old_generation = runtime.session().generation;
        runtime.restart_session().unwrap();
        assert!(runtime.session().generation > old_generation);
        assert_eq!(runtime.compositor().session_link, LinkState::Reconnecting);
        assert_eq!(
            runtime.reattach_app(id(7)),
            Err(TransitionError::CompositorUnavailable)
        );
        runtime.reconnect_session().unwrap();
        runtime.reattach_app(id(7)).unwrap();
        assert_eq!(
            runtime.app(id(7)).unwrap().connection,
            AppConnectionState::Attached
        );
    }

    #[test]
    fn generation_exhaustion_does_not_leave_lifecycle_in_a_transient_state() {
        let mut runtime = ready_runtime();

        runtime.session.generation = u64::MAX;
        let before_session = runtime.snapshot();
        assert_eq!(
            runtime.restart_session(),
            Err(TransitionError::GenerationExhausted)
        );
        assert_eq!(runtime.snapshot(), before_session);

        runtime.session.generation = 1;
        runtime.compositor.generation = u64::MAX;
        let before_compositor = runtime.snapshot();
        assert_eq!(
            runtime.restart_compositor(),
            Err(TransitionError::GenerationExhausted)
        );
        assert_eq!(runtime.snapshot(), before_compositor);

        runtime.compositor.generation = 1;
        runtime.shell.generation = u64::MAX;
        let before_shell = runtime.snapshot();
        assert_eq!(
            runtime.restart_shell(),
            Err(TransitionError::GenerationExhausted)
        );
        assert_eq!(runtime.snapshot(), before_shell);
    }

    #[test]
    fn gpu_reset_requires_explicit_recreation_and_reports_failure() {
        let mut runtime = ready_runtime();
        let old_generation = runtime.gpu().generation();
        runtime.begin_gpu_reset().unwrap();
        assert!(matches!(runtime.gpu(), GpuState::Resetting { .. }));
        assert!(matches!(
            runtime.app(id(7)).unwrap().surface,
            SurfaceState::NeedsRecreate { .. }
        ));
        runtime.finish_gpu_reset(true).unwrap();
        assert!(
            matches!(runtime.gpu(), GpuState::Ready { generation } if generation > old_generation)
        );
        assert!(matches!(
            runtime.app(id(7)).unwrap().surface,
            SurfaceState::NeedsRecreate { .. }
        ));
        runtime.recreate_app_surface(id(7)).unwrap();
        runtime.begin_gpu_reset().unwrap();
        runtime.finish_gpu_reset(false).unwrap();
        assert!(matches!(runtime.gpu(), GpuState::Failed { .. }));
        assert_eq!(runtime.app(id(7)).unwrap().surface, SurfaceState::Lost);
    }

    #[test]
    fn exited_app_cannot_be_reattached() {
        let mut runtime = ready_runtime();
        runtime.exit_app(id(7), Some(0)).unwrap();
        assert_eq!(runtime.reattach_app(id(7)), Err(TransitionError::AppExited));
        assert_eq!(
            runtime.app(id(7)).unwrap().connection,
            AppConnectionState::Closed
        );
    }

    struct FakeTransport {
        response: Response,
    }

    impl Hos2ReadTransport for FakeTransport {
        type Error = &'static str;

        fn exchange(&self, request: Request) -> Result<Response, Self::Error> {
            assert!(matches!(
                request.opcode,
                Opcode::QueryAbi | Opcode::ReadUsage | Opcode::QueryDelivery
            ));
            Ok(self.response)
        }
    }

    fn response(opcode: Opcode, payload: ResponsePayload) -> Response {
        Response {
            opcode,
            status: Status::Ok,
            request_id: [9; 16],
            boot_id: [8; 16],
            revision: if matches!(opcode, Opcode::ReadUsage) {
                1
            } else {
                0
            },
            payload,
        }
    }

    #[test]
    fn read_only_adapter_forwards_only_observation_calls() {
        let payload = QueryAbiResponse {
            space_id: [1; 16],
            page_size: 4096,
            max_request_payload: 64,
            max_response_payload: 64,
            supported_ops: 0b11_1110,
            features: 0,
        };
        let source = Hos2ReadOnlyAdapter::new(FakeTransport {
            response: response(Opcode::QueryAbi, ResponsePayload::QueryAbi(payload)),
        });
        assert_eq!(source.query_abi([1; 16]).unwrap(), payload);
    }

    #[test]
    fn non_ok_hos2_status_stays_an_observation_error() {
        let source = Hos2ReadOnlyAdapter::new(FakeTransport {
            response: Response {
                opcode: Opcode::QueryAbi,
                status: Status::PermissionDenied,
                request_id: [9; 16],
                boot_id: [8; 16],
                revision: 0,
                payload: ResponsePayload::Empty,
            },
        });
        assert_eq!(
            source.query_abi([1; 16]),
            Err(ReadOnlyError::Rejected(Status::PermissionDenied))
        );
    }

    #[test]
    fn read_only_adapter_rejects_mutating_opcode_before_transport() {
        let source = Hos2ReadOnlyAdapter::new(FakeTransport {
            response: response(
                Opcode::QueryAbi,
                ResponsePayload::QueryAbi(QueryAbiResponse {
                    space_id: [1; 16],
                    page_size: 4096,
                    max_request_payload: 64,
                    max_response_payload: 64,
                    supported_ops: 0,
                    features: 0,
                }),
            ),
        });
        let request = Request {
            opcode: Opcode::InstallBudget,
            request_id: [1; 16],
            target_slot: 1,
            target_generation: 1,
            payload: RequestPayload::InstallBudget(hos2_os_abi::InstallBudgetRequest {
                expected_revision: 1,
                period_ns: hos2_os_abi::CPU_PERIOD_NS,
                cap_ns: 1,
                reserved: 0,
            }),
        };
        assert_eq!(
            source.exchange_read_only(request),
            Err(ReadOnlyError::MutationNotAllowed)
        );
    }
}
