//! Frozen Binder extension for the core/vendor frontend boundary.
//! The existing record codecs run only on descriptors created by this service
//! after the kernel-authenticated caller role passes the entry check.

#[path = "frontend_authority.rs"]
mod authority;

use std::fs::File;
use std::os::fd::AsFd;
use std::sync::Arc;
use std::sync::atomic::{AtomicUsize, Ordering};

use binder::{
    BinderFeatures, ExceptionCode, Interface, ParcelFileDescriptor, Status, Strong, ThreadState,
};
use droidloom_denial_ipc::{SeqPacket, kernel_caller::KernelCaller};
use org_droidloom_frontend::aidl::org::droidloom::frontend::IFrontendChannels::{
    BnFrontendChannels, IFrontendChannels,
};

use crate::control::TaskCoordinator;
use crate::input::InputBridge;

const MAX_TASK_CHANNELS: usize = 16;

pub(super) struct FrontendChannels {
    input: Arc<InputBridge>,
    coordinator: TaskCoordinator,
    active_tasks: Arc<AtomicUsize>,
}

impl FrontendChannels {
    pub(super) fn new(input: Arc<InputBridge>, coordinator: TaskCoordinator) -> Self {
        Self {
            input,
            coordinator,
            active_tasks: Arc::new(AtomicUsize::new(0)),
        }
    }

    pub(super) fn into_binder(self) -> Strong<dyn IFrontendChannels> {
        BnFrontendChannels::new_binder(
            self,
            BinderFeatures {
                ..BinderFeatures::default()
            },
        )
    }
}

impl Interface for FrontendChannels {}

fn authorize(
    endpoint: authority::Endpoint,
    caller: &ParcelFileDescriptor,
) -> binder::Result<KernelCaller> {
    let uid = ThreadState::get_calling_uid();
    let context = match endpoint {
        authority::Endpoint::Input => b"u:r:droidloom_input_bridge:s0".as_slice(),
        authority::Endpoint::TaskControl => b"u:r:droidloom_task_launcher:s0".as_slice(),
    };
    if !authority::permitted(ThreadState::is_handling_transaction(), uid) {
        return Err(Status::new_exception(ExceptionCode::SECURITY, None));
    }
    // Public vendor Binder APIs supply PID/UID. Kernel socket metadata and the
    // retained peer PIDFD bind the proof to that actual synchronous caller.
    let descriptor = caller.as_fd().try_clone_to_owned().map_err(failure)?;
    KernelCaller::acquire(descriptor, ThreadState::get_calling_pid(), uid, 0, context)
        .map_err(|_| Status::new_exception(ExceptionCode::SECURITY, None))
}

fn failure(_: impl std::fmt::Display) -> Status {
    Status::new_service_specific_error(1, None)
}

fn descriptor(socket: &SeqPacket) -> binder::Result<ParcelFileDescriptor> {
    let fd = socket.as_fd().try_clone_to_owned().map_err(failure)?;
    Ok(ParcelFileDescriptor::new(File::from(fd)))
}

struct TaskLease(Arc<AtomicUsize>);
impl Drop for TaskLease {
    fn drop(&mut self) {
        self.0.fetch_sub(1, Ordering::AcqRel);
    }
}

impl IFrontendChannels for FrontendChannels {
    fn openInputChannel(
        &self,
        proof: &ParcelFileDescriptor,
    ) -> binder::Result<ParcelFileDescriptor> {
        let caller = authorize(authority::Endpoint::Input, proof)?;
        let (sender, receiver) = SeqPacket::pair().map_err(failure)?;
        let result = descriptor(&receiver)?;
        self.input.install(sender, caller).map_err(failure)?;
        Ok(result)
    }

    fn openTaskControlChannel(
        &self,
        proof: &ParcelFileDescriptor,
    ) -> binder::Result<ParcelFileDescriptor> {
        let caller = authorize(authority::Endpoint::TaskControl, proof)?;
        self.active_tasks
            .fetch_update(Ordering::AcqRel, Ordering::Acquire, |value| {
                (value < MAX_TASK_CHANNELS).then_some(value + 1)
            })
            .map_err(|_| Status::new_service_specific_error(2, None))?;
        let lease = TaskLease(Arc::clone(&self.active_tasks));
        let (server, client) = SeqPacket::pair().map_err(failure)?;
        let result = descriptor(&client)?;
        let coordinator = self.coordinator.clone();
        std::thread::Builder::new()
            .name("droidloom-binder-task".into())
            .spawn(move || {
                let _lease = lease;
                if let Err(error) = coordinator.serve_authenticated_channel(&server, &caller) {
                    eprintln!("Droidloom authenticated task channel closed: {error}");
                }
            })
            .map_err(failure)?;
        Ok(result)
    }
}
