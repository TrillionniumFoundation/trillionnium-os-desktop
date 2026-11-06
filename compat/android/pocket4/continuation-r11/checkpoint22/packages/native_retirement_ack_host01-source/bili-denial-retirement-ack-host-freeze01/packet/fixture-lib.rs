//! Host-only provider fixtures for the unchanged production coordinator API.
//! This crate does not implement Android Binder or qualify installed Main.
extern crate self as droidloom_composer_aidl;

use std::collections::{BTreeMap, VecDeque};
use std::sync::{Arc, Mutex};
use droidloom_composer::{DisplayId, ReservedTaskWindowSpec, TaskId, TaskWindowSpec};
use droidloom_denial_protocol::TaskObjectId;

#[derive(Clone, Copy, Debug, Eq, PartialEq, Ord, PartialOrd)]
pub enum Point { Stage, Register, SinkBind, ComposerBind, Destroy, Remove, Activate }

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Moment { Before, After }

#[derive(Clone, Copy, Debug)]
pub enum Fault { Before(&'static str), After(&'static str) }

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct FixtureError(&'static str);
impl std::fmt::Display for FixtureError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result { f.write_str(self.0) }
}
impl std::error::Error for FixtureError {}

#[derive(Clone, Debug)]
struct Window { package: String, task: Option<TaskId> }
#[derive(Clone, Debug)]
struct Channel { object: TaskObjectId, task: Option<TaskId> }

#[derive(Default)]
struct Data {
    windows: BTreeMap<DisplayId, Window>,
    channels: BTreeMap<DisplayId, Channel>,
    calls: Vec<(Point, DisplayId)>,
    faults: BTreeMap<Point, VecDeque<Fault>>,
}
type Observer = Arc<dyn Fn(Point, Moment, DisplayId) + Send + Sync>;
type Configure = Arc<dyn Fn(TaskObjectId) + Send + Sync>;

#[derive(Clone, Default)]
pub struct Backend {
    data: Arc<Mutex<Data>>,
    observer: Arc<Mutex<Option<Observer>>>,
    configure: Arc<Mutex<Option<Configure>>>,
}
impl Backend {
    pub fn fail(&self, point: Point, fault: Fault) {
        self.data.lock().unwrap().faults.entry(point).or_default().push_back(fault);
    }
    pub fn observe(&self, observer: Observer) {
        *self.observer.lock().unwrap() = Some(observer);
    }
    pub fn configure_with(&self, configure: Option<Configure>) {
        *self.configure.lock().unwrap() = configure;
    }
    fn notify(&self, point: Point, moment: Moment, display: DisplayId) {
        let callback = self.observer.lock().unwrap().clone();
        if let Some(callback) = callback { callback(point, moment, display); }
    }
    fn perform<T>(
        &self,
        point: Point,
        display: DisplayId,
        change: impl FnOnce(&mut Data) -> Result<T, FixtureError>,
    ) -> Result<T, FixtureError> {
        self.notify(point, Moment::Before, display);
        let (result, effect_applied) = {
            let mut data = self.data.lock().unwrap();
            data.calls.push((point, display));
            let fault = data.faults.entry(point).or_default().pop_front();
            if let Some(Fault::Before(message)) = fault {
                (Err(FixtureError(message)), false)
            } else {
                match change(&mut data) {
                    Err(error) => (Err(error), false),
                    Ok(value) => (
                        match fault {
                            Some(Fault::After(message)) => Err(FixtureError(message)),
                            _ => Ok(value),
                        },
                        true,
                    ),
                }
            }
        };
        // No fixture mutex is held while production callbacks run.
        if effect_applied { self.notify(point, Moment::After, display); }
        result
    }
    pub fn calls(&self) -> Vec<(Point, DisplayId)> { self.data.lock().unwrap().calls.clone() }
    pub fn count(&self, point: Point) -> usize {
        self.data.lock().unwrap().calls.iter().filter(|(p, _)| *p == point).count()
    }
    pub fn endpoints_empty(&self) -> bool {
        let data = self.data.lock().unwrap();
        data.windows.is_empty() && data.channels.is_empty()
    }
    pub fn has_window(&self, display: DisplayId) -> bool {
        self.data.lock().unwrap().windows.contains_key(&display)
    }
    pub fn has_channel(&self, display: DisplayId) -> bool {
        self.data.lock().unwrap().channels.contains_key(&display)
    }
    pub fn bound_tasks(&self, display: DisplayId) -> (Option<TaskId>, Option<TaskId>) {
        let data = self.data.lock().unwrap();
        (data.channels.get(&display).and_then(|v| v.task),
         data.windows.get(&display).and_then(|v| v.task))
    }
}

pub mod denial {
    use super::*;
    #[derive(Clone)]
    pub struct DenialPresentationSink { backend: Backend }
    impl DenialPresentationSink {
        pub fn fixture(backend: Backend) -> Self { Self { backend } }
        pub fn register_task(
            &self, object: TaskObjectId, reservation: &ReservedTaskWindowSpec,
        ) -> Result<(), FixtureError> {
            self.backend.perform(Point::Register, reservation.display, |data| {
                if !data.windows.contains_key(&reservation.display) {
                    return Err(FixtureError("composer-not-staged"));
                }
                if data.channels.contains_key(&reservation.display)
                    || data.channels.values().any(|v| v.object == object)
                {
                    return Err(FixtureError("duplicate-channel"));
                }
                data.channels.insert(reservation.display, Channel { object, task: None });
                Ok(())
            })?;
            let configure = self.backend.configure.lock().unwrap().clone();
            if let Some(configure) = configure { configure(object); }
            Ok(())
        }
        pub fn bind_task(&self, display: DisplayId, task: TaskId) -> Result<(), FixtureError> {
            self.backend.perform(Point::SinkBind, display, |data| {
                if data.channels.iter().any(|(id, value)| *id != display && value.task == Some(task)) {
                    return Err(FixtureError("duplicate-channel-task"));
                }
                let channel = data.channels.get_mut(&display).ok_or(FixtureError("unknown-channel"))?;
                if channel.task.is_some_and(|value| value != task) {
                    return Err(FixtureError("channel-task-changed"));
                }
                channel.task = Some(task);
                Ok(())
            })
        }
        pub fn unregister_task(&self, display: DisplayId, expected: TaskObjectId) -> Result<(), FixtureError> {
            self.backend.perform(Point::Destroy, display, |data| {
                if data.channels.get(&display).ok_or(FixtureError("unknown-channel"))?.object != expected {
                    return Err(FixtureError("wrong-channel-owner"));
                }
                data.channels.remove(&display).ok_or(FixtureError("unknown-channel"))?;
                Ok(())
            })
        }
        pub fn request_activation(&self, display: DisplayId) -> Result<(), FixtureError> {
            self.backend.perform(Point::Activate, display, |data| {
                if !data.channels.contains_key(&display) {
                    return Err(FixtureError("unknown-channel"));
                }
                Ok(())
            })
        }
    }
}
pub mod service {
    use super::*;
    #[derive(Clone)]
    pub struct ComposerLifecycle { backend: Backend }
    impl ComposerLifecycle {
        pub fn fixture(backend: Backend) -> Self { Self { backend } }
        pub fn stage_task(&self, reservation: ReservedTaskWindowSpec) -> Result<(), FixtureError> {
            self.backend.perform(Point::Stage, reservation.display, |data| {
                if data.windows.contains_key(&reservation.display) {
                    return Err(FixtureError("duplicate-window"));
                }
                data.windows.insert(reservation.display, Window { package: reservation.package, task: None });
                Ok(())
            })
        }
        fn bind(&self, display: DisplayId, task: TaskId) -> Result<TaskWindowSpec, FixtureError> {
            self.backend.perform(Point::ComposerBind, display, |data| {
                if data.windows.iter().any(|(id, value)| *id != display && value.task == Some(task)) {
                    return Err(FixtureError("duplicate-window-task"));
                }
                let window = data.windows.get_mut(&display).ok_or(FixtureError("unknown-window"))?;
                if window.task.is_some_and(|value| value != task) {
                    return Err(FixtureError("window-task-changed"));
                }
                window.task = Some(task);
                Ok(TaskWindowSpec { task, display, package: window.package.clone() })
            })
        }
        pub fn bind_task(&self, display: DisplayId, task: TaskId) -> Result<TaskWindowSpec, FixtureError> {
            self.bind(display, task)
        }
        pub fn bind_direct_task(&self, display: DisplayId, task: TaskId) -> Result<TaskWindowSpec, FixtureError> {
            self.bind(display, task)
        }
        pub fn remove_display(&self, display: DisplayId) -> Result<Option<TaskWindowSpec>, FixtureError> {
            self.backend.perform(Point::Remove, display, |data| {
                let window = data.windows.remove(&display).ok_or(FixtureError("unknown-window"))?;
                Ok(window.task.map(|task| TaskWindowSpec { task, display, package: window.package }))
            })
        }
    }
}

// The build controller writes this file as exact production bytes followed by
// transaction_tests.rs. No coordinator function or Core registry is substituted.
#[path = "control_under_test.rs"]
mod control;

// Explicit host seams for the real Denial provider source below.
// Real socket records, Core bindings, ownership/state methods and Condvar waits run.
// Binder objects, DRM ioctls and GLES are not executed or qualified by this fixture.
use std::os::fd::AsFd;
extern crate self as binder;
extern crate self as droidloom_syncobj;

#[derive(Debug)]
pub struct ParcelFileDescriptor(pub std::os::fd::OwnedFd);
impl ParcelFileDescriptor {
    pub fn new(fd: std::os::fd::OwnedFd) -> Self { Self(fd) }
}

#[derive(Debug)]
pub struct PresentationFailure { pub code: droidloom_composer::hwc3::ErrorCode }
impl PresentationFailure {
    pub fn unsubmitted(code: droidloom_composer::hwc3::ErrorCode) -> Self { Self { code } }
}

#[derive(Debug)]
pub struct SyncobjError(&'static str);
impl std::fmt::Display for SyncobjError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result { f.write_str(self.0) }
}
impl std::error::Error for SyncobjError {}

#[derive(Debug, Default)]
pub struct TimelineSeam {
    pub creates: std::sync::atomic::AtomicUsize,
    pub exports: std::sync::atomic::AtomicUsize,
    pub fail_create: std::sync::atomic::AtomicBool,
    pub fail_export: std::sync::atomic::AtomicBool,
    pub close_peer_on_descriptor_borrow: Mutex<Option<droidloom_denial_ipc::ProtocolSocket>>,
}
#[derive(Clone, Debug)]
pub struct SyncobjDevice {
    file: Arc<std::fs::File>,
    pub seam: Arc<TimelineSeam>,
}
impl SyncobjDevice {
    pub fn fixture() -> Self {
        Self { file: Arc::new(std::fs::File::open("/dev/null").unwrap()),
               seam: Arc::new(TimelineSeam::default()) }
    }
}
impl std::os::fd::AsFd for SyncobjDevice {
    fn as_fd(&self) -> std::os::fd::BorrowedFd<'_> { self.file.as_fd() }
}
#[derive(Debug)]
pub struct AndroidTaskTimelines { device: SyncobjDevice }
#[derive(Debug)]
pub struct FixtureDescriptor {
    fd: std::os::fd::OwnedFd,
    seam: Arc<TimelineSeam>,
}
impl std::os::fd::AsFd for FixtureDescriptor {
    fn as_fd(&self) -> std::os::fd::BorrowedFd<'_> {
        // A deterministic, explicitly named descriptor seam can close the peer
        // after the real CreateTask send, before the real BindTimelines send.
        drop(self.seam.close_peer_on_descriptor_borrow.lock().unwrap().take());
        self.fd.as_fd()
    }
}
pub struct FixtureDescriptors { pub acquire: FixtureDescriptor, pub release: FixtureDescriptor }
impl AndroidTaskTimelines {
    pub fn create(device: &SyncobjDevice) -> Result<Self, SyncobjError> {
        use std::sync::atomic::Ordering::SeqCst;
        device.seam.creates.fetch_add(1, SeqCst);
        if device.seam.fail_create.load(SeqCst) { return Err(SyncobjError("fixture-create-failure")); }
        Ok(Self { device: device.clone() })
    }
    pub fn export_descriptors(&self) -> Result<FixtureDescriptors, SyncobjError> {
        use std::sync::atomic::Ordering::SeqCst;
        self.device.seam.exports.fetch_add(1, SeqCst);
        if self.device.seam.fail_export.load(SeqCst) { return Err(SyncobjError("fixture-export-failure")); }
        let descriptor = || -> Result<FixtureDescriptor, SyncobjError> {
            Ok(FixtureDescriptor {
                fd: self.device.file.as_fd().try_clone_to_owned().map_err(|_| SyncobjError("fixture-dup-failure"))?,
                seam: Arc::clone(&self.device.seam),
            })
        };
        Ok(FixtureDescriptors { acquire: descriptor()?, release: descriptor()? })
    }
    pub fn import_acquire_fence(&self, _point: u64, _fd: std::os::fd::BorrowedFd<'_>) -> Result<(), SyncobjError> {
        Err(SyncobjError("DRM import is outside host fixture"))
    }
    pub fn signal_acquire(&self, _point: u64) -> Result<(), SyncobjError> {
        Err(SyncobjError("DRM signal is outside host fixture"))
    }
    pub fn export_acquire_fence(&self, _point: u64) -> Result<std::os::fd::OwnedFd, SyncobjError> {
        Err(SyncobjError("DRM fence is outside host fixture"))
    }
}
pub mod frame_trace {
    pub fn enabled() -> bool { false }
    pub fn now_ns() -> u64 { panic!("frame clock is not used by this host fixture") }
    pub fn sampled(_frame: u64) -> bool { false }
    pub fn event(_name: &str, _object: u64, _frame: u64, _buffer: u64, _fields: &[(&str, u64)]) {
        panic!("frame trace is not used by this host fixture")
    }
    pub fn fence_signal_ns(_fd: std::os::fd::BorrowedFd<'_>) -> std::io::Result<Option<u64>> {
        Err(std::io::Error::other("GPU signal is outside host fixture"))
    }
}
pub mod minigbm {
    use super::*;
    use droidloom_transport::{AcceptedFrame, BufferMetadata};
    #[derive(Debug)]
    pub struct ImportedRenderTarget {
        pub metadata: BufferMetadata,
        pub configure_serial: u32,
        pub plane_fds: Vec<std::os::fd::OwnedFd>,
    }
    pub struct PreparedLayer;
    pub trait PresentationSink {
        fn acquire_target(&mut self, display: DisplayId) -> Result<ImportedRenderTarget, droidloom_composer::hwc3::ErrorCode>;
        fn cancel_target(&mut self, display: DisplayId, target: ImportedRenderTarget);
        fn take_direct_present_fence(&mut self, display: DisplayId) -> Result<ParcelFileDescriptor, droidloom_composer::hwc3::ErrorCode>;
        fn submit(&mut self, display: DisplayId, frame: AcceptedFrame, target: ImportedRenderTarget,
                  layers: Vec<PreparedLayer>) -> Result<ParcelFileDescriptor, PresentationFailure>;
    }
}
pub mod gles {
    use super::*;
    #[derive(Debug)]
    pub struct LayerCompositor;
    impl LayerCompositor {
        pub fn new(_fd: std::os::fd::BorrowedFd<'_>) -> Result<Self, &'static str> {
            Err("GLES is outside host fixture")
        }
        pub fn compose(&mut self, _target: &minigbm::ImportedRenderTarget,
                       _layers: &mut [minigbm::PreparedLayer], _extent: (u32,u32))
                       -> Result<std::os::fd::OwnedFd, &'static str> {
            Err("GLES is outside host fixture")
        }
    }
}
#[path = "provider_under_test.rs"]
mod real_provider;
#[path = "engine_retirement.rs"]
mod engine_retirement;
#[path = "handshake_under_test.rs"]
mod handshake_under_test;
