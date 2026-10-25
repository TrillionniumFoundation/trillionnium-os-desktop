// SPDX-License-Identifier: MPL-2.0

#[cfg(not(target_arch = "loongarch64"))]
use ostd::arch::cpu::context::CpuException;
#[cfg(target_arch = "loongarch64")]
use ostd::arch::cpu::context::CpuExceptionInfo as CpuException;
use ostd::{arch::cpu::context::UserContext, task::Task};

use crate::{
    prelude::*,
    process::signal::{
        constants::{SEGV_ACCERR, SIGSEGV},
        signals::{OwnedSignal, fault::FaultSignal},
    },
    thread::kernel_thread::AsKernelThread,
    vm::vmar::{PageFaultError, PageFaultInfo, Vmar},
};

pub(super) fn handle_exception(ctx: &Context, user_ctx: &UserContext, exception: CpuException) {
    debug!("handle exception: {:#x?}", exception);

    let permission_signal = if let Ok(page_fault_info) = PageFaultInfo::try_from(&exception) {
        let user_space = ctx.user_space();
        match handle_page_fault_from_vmar(user_space.vmar(), &page_fault_info) {
            Ok(()) => return,
            Err(error) => permission_fault_signal(&error, &page_fault_info),
        }
    } else {
        None
    };
    // Release the original user-space/VMAR guards before taking signal locks.
    if let Some(signal) = permission_signal {
        ctx.posix_thread
            .enqueue_owned_signal(OwnedSignal::new(signal));
        return;
    }

    // We cannot handle most exceptions. Send a fault signal to the current thread before returning
    // to user space.
    generate_fault_signal(exception, ctx, user_ctx);
}

/// A denied VMA permission is an access error even when demand paging has not
/// installed a PTE yet. Hardware "present" bits alone cannot classify that case.
/// Other VMAR failures retain the existing architecture-specific signal policy.
fn permission_fault_signal(error: &PageFaultError, info: &PageFaultInfo) -> Option<FaultSignal> {
    matches!(error, PageFaultError::PermissionDenied(_))
        .then(|| FaultSignal::new(SIGSEGV, SEGV_ACCERR, Some(info.address() as u64)))
}

/// Handles the page fault occurs in the VMAR.
fn handle_page_fault_from_vmar(
    vmar: &Vmar,
    page_fault_info: &PageFaultInfo,
) -> Result<(), PageFaultError> {
    if let Err(failure) = vmar.handle_page_fault_with_reason(page_fault_info) {
        let e = failure.error();
        // The handler has released its VMAR, page-table and VMO locks. This
        // diagnostic is evidence of the exact admission cause, not an OOM kill.
        if e.is_user_frame_limit()
            && let Some(owner) = vmar.user_memory_owner()
            && owner.report_denial()
        {
            if e.is_cgroup_frame_limit() {
                // Do not mislabel a hierarchical denial as a family cap, or
                // report a later (possibly migrated) domain snapshot as its cause.
                println!(
                    "[hepta-cgroup-memory] denied pid={} address={}",
                    crate::process::Process::current().map_or(0, |process| process.pid()),
                    page_fault_info.address(),
                );
            } else {
                println!(
                    "[hepta-user-memory] denied pid={} address={} current_pages={} limit_pages={}",
                    crate::process::Process::current().map_or(0, |process| process.pid()),
                    page_fault_info.address(),
                    owner.current_pages(),
                    owner.limit_pages()
                );
            }
        }
        warn!(
            "page fault handler failed: info: {:#x?}, err: {:?}",
            page_fault_info, e
        );
        return Err(failure);
    }
    Ok(())
}

/// A trait that converts CPU exceptions into fault signals.
///
/// This trait should be implemented by architecture-specific code for [`CpuException`].
pub(crate) trait ToFaultSignal {
    /// Converts a CPU exception into a fault signal.
    ///
    /// Returns `None` if the exception must be handled earlier and cannot be delivered as a signal.
    ///
    /// POSIX [requires] `SIGILL` and `SIGFPE` to report the address of the faulting instruction,
    /// and `SIGSEGV` and `SIGBUS` to report the address of the faulting memory reference. Linux
    /// behavior, however, is highly architecture-specific and does not always follow POSIX: for
    /// some exceptions, it reports neither the expected code nor the expected address. Linux may
    /// also attach an instruction address to `SIGTRAP`, but this behavior is not consistent across
    /// architectures.
    ///
    /// [requires]: https://pubs.opengroup.org/onlinepubs/009695399/basedefs/signal.h.html
    fn to_fault_signal(&self, user_ctx: &UserContext) -> Option<FaultSignal>;
}

/// Generates a fault signal for the current thread.
fn generate_fault_signal(exception: CpuException, ctx: &Context, user_ctx: &UserContext) {
    let Some(signal) = exception.to_fault_signal(user_ctx) else {
        panic!("`{:?}` cannot be handled via signals", exception);
    };
    ctx.posix_thread
        .enqueue_owned_signal(OwnedSignal::new(signal));
}

pub(super) fn page_fault_handler(info: &CpuException) -> Result<(), ()> {
    let task = Task::current().unwrap();
    let page_fault_info = info.try_into().unwrap();

    if let Some(thread_local) = task.as_thread_local() {
        if thread_local.is_page_fault_disabled() {
            // Do nothing if the page fault handler is disabled. This will typically cause the
            // fallible memory operation to report EFAULT errors immediately.
            return Err(());
        }

        let user_space = CurrentUserSpace::new(thread_local);
        handle_page_fault_from_vmar(user_space.vmar(), &page_fault_info).map_err(|_| ())
    } else {
        let vmar = task
            .as_kernel_thread()
            .and_then(|kernel_thread| kernel_thread.vmar())
            .ok_or(())?;
        handle_page_fault_from_vmar(vmar, &page_fault_info).map_err(|_| ())
    }
}

#[cfg(ktest)]
mod tests {
    use ostd::prelude::ktest;

    use super::*;
    use crate::{
        fs::pseudofs::SockFs,
        process::{ProcessVm, signal::signals::Signal},
        vm::{
            perms::VmPerms,
            user_memory::UserMemoryAccount,
            vmar::{VmarHandle, VmarMapOffset},
        },
    };

    #[ktest]
    fn actual_vmar_permission_denial_reports_access_error_without_reclassifying_other_failures() {
        crate::time::clocks::init_for_ktest();
        crate::util::random::init();
        // The genuine quota-denial path emits through the original console.
        // Standalone aster-core tests do not run component bootstrap.
        aster_console::init_for_ktest();
        let account = UserMemoryAccount::new(0);
        let vmar =
            VmarHandle::new_with_owner(ProcessVm::new(SockFs::new_path()), Some(account.clone()));
        let address = 0x4000_0000;
        vmar.new_map(PAGE_SIZE, VmPerms::empty())
            .offset(VmarMapOffset::FixedNoReplace(address))
            .build()
            .unwrap();
        let info = PageFaultInfo::new(address, VmPerms::WRITE);
        let error = handle_page_fault_from_vmar(&vmar, &info).unwrap_err();
        assert_eq!(error.error().error(), Errno::EACCES);
        assert!(matches!(error, PageFaultError::PermissionDenied(_)));
        let signal = permission_fault_signal(&error, &info).unwrap();
        assert_eq!(signal.num(), SIGSEGV);
        assert_eq!(signal.to_info().si_code, SEGV_ACCERR);
        assert_eq!(signal.to_info().si_addr(), address);

        let absent = PageFaultInfo::new(address + PAGE_SIZE, VmPerms::WRITE);
        let error = handle_page_fault_from_vmar(&vmar, &absent).unwrap_err();
        assert!(matches!(error, PageFaultError::Unmapped(_)));
        assert_eq!(error.error().error(), Errno::EACCES); // Original errno is preserved.
        assert!(permission_fault_signal(&error, &absent).is_none());
        vmar.new_map(PAGE_SIZE, VmPerms::READ | VmPerms::WRITE)
            .offset(VmarMapOffset::FixedNoReplace(address + PAGE_SIZE))
            .build()
            .unwrap();
        let error = handle_page_fault_from_vmar(&vmar, &absent).unwrap_err();
        assert!(matches!(error, PageFaultError::Other(_)));
        assert!(error.error().is_user_frame_limit());
        assert!(permission_fault_signal(&error, &absent).is_none());
        assert_eq!(account.current_pages(), 0);
    }
}
