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
        pub fn unregister_task(&self, display: DisplayId) -> Result<(), FixtureError> {
            self.backend.perform(Point::Destroy, display, |data| {
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
