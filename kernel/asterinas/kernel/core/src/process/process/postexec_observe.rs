// SPDX-License-Identifier: MPL-2.0

//! Internal, single-child observation handoff. There is deliberately no device
//! ioctl or default boot caller in this first slice. A future endpoint must use
//! its kernel caller and real pidfd/control-file objects, never userspace PIDs
//! or an asserted image key. This is not a management or history capability.

use super::{
    Process, ProcessImageKey, image::InitialObserveGrant, init_proc::SealedObserveLauncher,
};
use crate::{
    fs::cgroupfs::NativeCpuObserver,
    prelude::*,
    process::{PidFile, posix_thread::AsPosixThread, task_set::TaskSet},
    thread::AsThread,
    vm::vmar::Vmar,
};

/// An identity selector, not an authorization credential. The issuer can mint
/// only one launch for its globally non-reused, boot-local image nonce.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) struct ObserveLaunchNonce(u64);

/// A snapshot of the owner of an actual open HOS2 session. Capturing or passing
/// it does not authorize a read, and does not make that fd usable by its broker.
pub(crate) struct ControlSessionRecipient {
    process: Arc<Process>,
    key: ProcessImageKey,
}

impl ControlSessionRecipient {
    pub(crate) fn capture(process: Arc<Process>, key: ProcessImageKey) -> Result<Self> {
        process.check_hepta_capspace_session(key)?;
        Ok(Self { process, key })
    }
}

#[derive(Clone)]
pub(super) struct ObserveIssuer {
    process: Weak<Process>,
    key: ProcessImageKey,
}

impl ObserveIssuer {
    pub(super) fn same_issuer(&self, other: &Self) -> bool {
        self.key == other.key && Weak::ptr_eq(&self.process, &other.process)
    }

    pub(super) fn check(&self) -> Result<()> {
        let process = self
            .process
            .upgrade()
            .ok_or_else(|| Error::with_message(Errno::ESTALE, "observe launch issuer ended"))?;
        let result = process.hepta_image.lock().check_observe_launcher(self.key);
        result
    }
}

/// Non-Clone boot-plan authority for one observe-only child. Its only production
/// constructor consumes the explicit sealed-initial launcher token. Neither a
/// NativeCpuObserver pin nor a parent relationship can construct this authority.
pub(crate) struct ObserveLaunchAuthority {
    binding: LaunchBinding,
    observer: Arc<NativeCpuObserver>,
    issued_ns: u64,
    expires_ns: u64,
}

impl ObserveLaunchAuthority {
    pub(super) fn from_sealed_initial(
        sealed: SealedObserveLauncher,
        observer: Arc<NativeCpuObserver>,
        issued_ns: u64,
    ) -> Result<Self> {
        let expires_ns = issued_ns.checked_add(300_000_000_000).ok_or_else(|| {
            Error::with_message(Errno::EOVERFLOW, "observe launch lease overflow")
        })?;
        let (process, key) = sealed.into_parts();
        Ok(Self {
            binding: LaunchBinding::new(process, key),
            observer,
            issued_ns,
            expires_ns,
        })
    }

    /// Bind the one ticket to the Supervisor's actual child allocation and its
    /// current post-exec image. The caller is obtained from the kernel context.
    /// Consuming this value prevents rebinding a failed launch to another child.
    pub(crate) fn bind_child(
        self,
        caller: &Arc<Process>,
        pidfd: &PidFile,
    ) -> Result<BoundObserveLaunch> {
        let child = self.binding.bind_child(caller, pidfd)?;
        Ok(BoundObserveLaunch {
            binding: self.binding,
            child,
            observer: self.observer,
            issued_ns: self.issued_ns,
            expires_ns: self.expires_ns,
            installed: false,
        })
    }
}

struct LaunchBinding {
    supervisor: Arc<Process>,
    supervisor_key: ProcessImageKey,
    nonce: ObserveLaunchNonce,
}

struct ChildImage {
    process: Arc<Process>,
    key: ProcessImageKey,
}

impl LaunchBinding {
    fn new(supervisor: Arc<Process>, supervisor_key: ProcessImageKey) -> Self {
        Self {
            supervisor,
            supervisor_key,
            nonce: ObserveLaunchNonce(supervisor_key.nonce()),
        }
    }

    fn bind_child(&self, caller: &Arc<Process>, pidfd: &PidFile) -> Result<ChildImage> {
        if !Arc::ptr_eq(caller, &self.supervisor) {
            return_errno_with_message!(Errno::EPERM, "observe launcher belongs to another process");
        }
        let child = pidfd
            .process_opt()
            .ok_or_else(|| Error::with_message(Errno::ESTALE, "observe launch child ended"))?;
        let key = self.with_child_relationship(&child, || {
            let issuer_image = self.supervisor.hepta_image.lock();
            issuer_image.check_observe_launcher(self.supervisor_key)?;
            child.hepta_image.lock().postexec_observe_session()
        })?;
        Ok(ChildImage {
            process: child,
            key,
        })
    }

    /// Preserve the existing parent.children -> child.parent hierarchy while
    /// inspecting the actual allocation; PID reuse or reparenting cannot swap
    /// the recipient. Callers acquire VMAR/TaskSet before either image mutex.
    fn with_child_relationship<T>(
        &self,
        child: &Arc<Process>,
        action: impl FnOnce() -> Result<T>,
    ) -> Result<T> {
        if Arc::ptr_eq(child, &self.supervisor) {
            return_errno_with_message!(Errno::EPERM, "observe launch cannot target its issuer");
        }
        let children = self.supervisor.children.lock();
        if !children
            .as_ref()
            .and_then(|children| children.get(&child.pid()))
            .is_some_and(|registered| Arc::ptr_eq(registered, child))
        {
            return_errno_with_message!(
                Errno::EPERM,
                "observe recipient is not the registered child"
            );
        }
        let parent = child.parent.lock();
        if !parent
            .process()
            .upgrade()
            .is_some_and(|parent| Arc::ptr_eq(&parent, &self.supervisor))
        {
            return_errno_with_message!(Errno::EPERM, "observe launch parent changed");
        }
        action()
    }

    fn with_recipient<T>(
        &self,
        child: &ChildImage,
        nonce: ObserveLaunchNonce,
        recipient: &ControlSessionRecipient,
        action: impl FnOnce(&mut super::image::ProcessImageState, &Vmar, &TaskSet) -> Result<T>,
    ) -> Result<T> {
        self.check_recipient(child, nonce, recipient)?;
        self.with_child_relationship(&child.process, || {
            // Existing VMAR -> TaskSet -> image lifecycle order. In particular,
            // never hold an image mutex while waiting for a VMAR or task set.
            let current_vmar = child.process.vmar.lock();
            let vmar = current_vmar.as_ref().ok_or_else(|| {
                Error::with_message(Errno::ESTALE, "observe recipient VMAR ended")
            })?;
            let tasks = child.process.tasks().lock();
            if tasks.as_slice().is_empty()
                || tasks.has_exited_main()
                || tasks.has_exited_group()
                || tasks.in_execve()
                || child.process.status().is_zombie()
            {
                return_errno_with_message!(Errno::ESTALE, "observe recipient lifecycle changed");
            }
            for task in tasks.as_slice() {
                let Some(thread) = task.as_posix_thread() else {
                    return_errno_with_message!(
                        Errno::ESTALE,
                        "observe recipient has a foreign task"
                    );
                };
                if task.as_thread().unwrap().is_exited()
                    || !thread
                        .weak_process()
                        .upgrade()
                        .is_some_and(|owner| Arc::ptr_eq(&owner, &child.process))
                {
                    return_errno_with_message!(
                        Errno::ESTALE,
                        "observe recipient task ended or changed owner"
                    );
                }
            }
            let issuer_image = self.supervisor.hepta_image.lock();
            issuer_image.check_observe_launcher(self.supervisor_key)?;
            let mut image = child.process.hepta_image.lock();
            image.check_postexec_observe_recipient(child.key)?;
            action(&mut image, vmar, &tasks)
        })
    }

    fn check_recipient(
        &self,
        child: &ChildImage,
        nonce: ObserveLaunchNonce,
        recipient: &ControlSessionRecipient,
    ) -> Result<()> {
        if nonce != self.nonce || !Arc::ptr_eq(&child.process, &recipient.process) {
            return_errno_with_message!(
                Errno::EPERM,
                "observe launch nonce or child does not match"
            );
        }
        if child.key != recipient.key {
            return_errno_with_message!(Errno::ESTALE, "observe launch recipient image changed");
        }
        Ok(())
    }
}

/// One in-memory capability transaction, retained for exact reply-loss retry.
/// It has no durable journal, D namespace, mutable CPU policy, manage or ACK
/// right. Capacity is one child for the entire sealed issuer image lifetime.
pub(crate) struct BoundObserveLaunch {
    binding: LaunchBinding,
    child: ChildImage,
    observer: Arc<NativeCpuObserver>,
    issued_ns: u64,
    expires_ns: u64,
    installed: bool,
}

impl BoundObserveLaunch {
    pub(crate) fn nonce(&self) -> ObserveLaunchNonce {
        self.binding.nonce
    }

    /// Only an exact repeat can succeed after installation. Every call checks
    /// both live images and the original parent/child relation; a stale ticket
    /// cannot install into a second exec image, even if the PID is unchanged.
    pub(crate) fn install(
        &mut self,
        caller: &Arc<Process>,
        nonce: ObserveLaunchNonce,
        recipient: &ControlSessionRecipient,
    ) -> Result<()> {
        if !Arc::ptr_eq(caller, &self.binding.supervisor) {
            return_errno_with_message!(Errno::EPERM, "observe launcher belongs to another process");
        }
        let grant = InitialObserveGrant::for_launch(
            self.observer.clone(),
            self.issued_ns,
            self.expires_ns,
            ObserveIssuer {
                process: Arc::downgrade(&self.binding.supervisor),
                key: self.binding.supervisor_key,
            },
        );
        self.binding
            .with_recipient(&self.child, nonce, recipient, |image, vmar, tasks| {
                // All caller/child/image/slot checks precede irreversible changes.
                // The borrowed reservation makes final slot installation infallible.
                let slot =
                    image.prepare_postexec_observer(self.child.key, grant, self.installed)?;
                commit_external_fences(&self.child.process, vmar, tasks)?;
                slot.commit();
                Ok(())
            })?;
        self.installed = true;
        Ok(())
    }
}

/// Called only with the recipient VMAR, TaskSet and both live images locked.
/// Admission counters cover existing ptrace references and alien-copy/clone
/// work; no gate mutex is held by that work while it faults or copies memory.
/// Rejecting any preparation leaves both fences and the image slot unchanged.
fn commit_external_fences(process: &Process, vmar: &Vmar, tasks: &TaskSet) -> Result<()> {
    // Check before inspecting tracer state: an in-flight ptrace read/write may
    // already hold that state while waiting for our outer VMAR lock.
    let process_fence = process.external_control_fence().prepare_fence()?;
    let vmar_fence = vmar.prepare_external_write_fence()?;
    if tasks
        .as_slice()
        .iter()
        .any(|task| task.as_posix_thread().unwrap().tracer().is_some())
    {
        return_errno_with_message!(Errno::EPERM, "observe recipient has an existing tracer");
    }
    // Process protection deliberately lasts until Process destruction, including
    // later execs. The VMAR fence lasts for this VMAR. The observation grant
    // itself remains image-local and is revoked by exec/exit as before.
    process_fence.commit();
    vmar_fence.commit();
    Ok(())
}

#[cfg(ktest)]
#[path = "postexec_observe_tests.rs"]
mod tests;
