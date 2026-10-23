// SPDX-License-Identifier: MPL-2.0

//! This module defines functions related to spawning the init process.

use ostd::{arch::cpu::context::UserContext, task::Task, user::UserContextApi};

use super::{Process, ProcessImageKey, Session, image::ProcessImageState};
use crate::{
    fs::{
        thread_info::ThreadFsInfo,
        vfs::path::{Path, PathResolver},
    },
    prelude::*,
    process::{
        Credentials, ProcessVm, ShebangScriptPath, UndetectedExecutable, UserNamespace, pid_table,
        posix_thread::{AsPosixThread, PosixThreadBuilder, allocate_posix_tid, derive_thread_name},
        rlimit::{ResourceLimits, new_resource_limits_for_init},
        signal::sig_disposition::SigDispositions,
    },
    sched::Nice,
    thread::{AsThread, Tid},
    vm::vmar::{Vmar, VmarHandle},
};

#[cfg(feature = "g1d-trusted-control")]
mod trusted_roles;

#[cfg(not(feature = "g1c-trusted-observe"))]
use crate::process::program_loader::ProgramToLoad;
#[cfg(feature = "g1c-trusted-observe")]
use crate::{
    fs::cgroupfs::{CgroupMembership, NativeCpuObserver},
    process::program_loader::elf::LoadedInitialImage,
};

/// One loaded initial process that has never been scheduled.
///
/// Only `create_init_process`, after the actual loader and task builder succeed,
/// constructs this value. It is deliberately not Clone. The VMAR pin identifies
/// the loaded allocation; alone it does not authenticate executable bytes.
/// The optional observe profile must additionally consume the private token
/// produced by final-byte verification and VMAR sealing before activation.
struct PreparedInitialProcess {
    process: Arc<Process>,
    vmar: Arc<Vmar>,
    task: Arc<Task>,
    key: ProcessImageKey,
    consumed: bool,
}

/// Consumed only by the internal post-exec observe authority constructor.
/// No userspace bytes, PID, uid, or ELF digest can construct this token.
#[cfg(feature = "g1c-trusted-observe")]
pub(super) struct SealedObserveLauncher {
    process: Arc<Process>,
    key: ProcessImageKey,
}

#[cfg(feature = "g1c-trusted-observe")]
impl SealedObserveLauncher {
    pub(super) fn into_parts(self) -> (Arc<Process>, ProcessImageKey) {
        (self.process, self.key)
    }
}

impl PreparedInitialProcess {
    /// Explicit boot-plan seam; existing G1-c/G1-d profiles never call it.
    /// The observer is the original workload owner's read-only pin. Attaching
    /// a recipient must never call NativeCpuObserver::prepare or reset policy.
    #[cfg(feature = "g1c-trusted-observe")]
    fn prepare_observe_launcher(
        &self,
        loaded: LoadedInitialImage,
        entry: Vaddr,
        observer: Arc<NativeCpuObserver>,
        issued_ns: u64,
    ) -> Result<super::ObserveLaunchAuthority> {
        loaded.consume(&self.vmar, entry)?;
        with_initial_image(&self.process, &self.vmar, &self.task, |image| {
            image.arm_initial_observe_launcher(self.key)
        })?;
        super::ObserveLaunchAuthority::from_sealed_initial(
            SealedObserveLauncher {
                process: self.process.clone(),
                key: self.key,
            },
            observer,
            issued_ns,
        )
    }

    #[cfg(feature = "g1d-trusted-control")]
    fn activate_control(
        &self,
        loaded: LoadedInitialImage,
        entry: Vaddr,
        slots: Arc<super::trusted_control::TrustedControlSlots>,
    ) -> Result<()> {
        loaded.consume(&self.vmar, entry)?;
        with_initial_image(&self.process, &self.vmar, &self.task, |image| {
            image.activate_initial_control(self.key, slots)
        })
    }

    #[cfg(feature = "g1c-trusted-observe")]
    fn activate_observation(&self, loaded: LoadedInitialImage, entry: Vaddr) -> Result<()> {
        loaded.consume(&self.vmar, entry)?;
        let (observer, issued) = NativeCpuObserver::prepare(&self.process, self.key.nonce())?;
        with_initial_image(&self.process, &self.vmar, &self.task, |image| {
            image.activate_initial_observer(self.key, observer, issued)
        })?;
        println!(
            "[hepta-g1c] initial observe activated: slot=1 generation=1 cap_ns=50000000 period_ns=100000000 lease_ns=300000000000"
        );
        Ok(())
    }

    fn new(process: Arc<Process>, vmar: Arc<Vmar>, task: Arc<Task>) -> Result<Self> {
        let key = with_initial_image(&process, &vmar, &task, |image| image.prepare_initial())?;
        Ok(Self {
            process,
            vmar,
            task,
            key,
            consumed: false,
        })
    }

    /// Claims the original Process first-run state without scheduling. Kept
    /// separate so kernel regressions can validate real, unstarted objects
    /// without executing their intentionally empty fixture user contexts.
    fn claim_resume(&mut self) -> Result<()> {
        with_initial_image(&self.process, &self.vmar, &self.task, |image| {
            image.consume_initial(self.key)
        })?;
        self.consumed = true;
        Ok(())
    }

    fn resume(mut self) -> Result<Arc<Process>> {
        self.claim_resume()?;

        // No fallible preparation remains after registration. All Process
        // locks were released before the PID table or scheduler is entered.
        set_bootstrap_session_and_group(&self.process);
        let process = self.process.clone();
        self.task.as_thread().unwrap().run();
        Ok(process)
    }
}

impl Drop for PreparedInitialProcess {
    fn drop(&mut self) {
        if !self.consumed {
            // Cancel only this still-prepared image. A stale token cannot
            // close a different image or re-enable a consumed first run.
            self.process.hepta_image.lock().cancel_initial(self.key);
            #[cfg(feature = "g1d-trusted-control")]
            self.process.revoke_closing_hepta_control();
            // This task never ran. Remove its failed bootstrap membership only
            // after releasing the image mutex; retained accounting owners keep
            // the original cgroup alive until the task/RCU references retire.
            #[cfg(feature = "g1c-trusted-observe")]
            CgroupMembership::write_lock().move_process_to_root(&self.process);
        }
        // Strong Process/Task/VMAR pins are dropped after the image lock.
    }
}

/// Check and claim under the established VMAR -> TaskSet -> image order.
/// `/proc/[pid]/mem` and `maps` already take VMAR before looking up main_thread.
/// Never acquire VMAR after TaskSet or acquire an outer lock from image state.
fn with_initial_image<R>(
    process: &Arc<Process>,
    vmar: &Arc<Vmar>,
    task: &Arc<Task>,
    action: impl FnOnce(&mut ProcessImageState) -> Result<R>,
) -> Result<R> {
    let current_vmar = process.vmar.lock();
    let tasks = process.tasks().lock();
    if !current_vmar
        .as_ref()
        .is_some_and(|current| Arc::ptr_eq(current, vmar))
        || tasks.as_slice().len() != 1
        || !Arc::ptr_eq(tasks.main(), task)
        || tasks.has_exited_group()
        || tasks.has_exited_main()
        || tasks.in_execve()
        || process.status().is_zombie()
    {
        return_errno_with_message!(Errno::ESTALE, "initial process binding changed");
    }
    let Some(posix_thread) = task.as_posix_thread() else {
        return_errno_with_message!(Errno::ESTALE, "initial task is not a POSIX task");
    };
    if !posix_thread
        .weak_process()
        .upgrade()
        .is_some_and(|owner| Arc::ptr_eq(&owner, process))
        || task.as_thread().unwrap().is_exited()
    {
        return_errno_with_message!(
            Errno::ESTALE,
            "initial task belongs to an ended or foreign process"
        );
    }
    action(&mut process.hepta_image.lock())
}

/// Creates and schedules the init process to run.
pub(crate) fn spawn_init_process(
    path_resolver: PathResolver,
    executable_path: Path,
    argv: Vec<CString>,
    envp: Vec<CString>,
) -> Result<Arc<Process>> {
    // Boot arguments are already kernel-owned. Check them before either the
    // ordinary initial load or the trusted profile's three role copies.
    crate::process::program_loader::ArgBudget::for_args(
        crate::process::process_vm::INIT_STACK_SIZE as u64,
        &argv,
        &envp,
    )?;
    #[cfg(feature = "g1d-trusted-control")]
    return trusted_roles::spawn(path_resolver, executable_path, argv, envp);
    #[cfg(not(feature = "g1d-trusted-control"))]
    create_init_process(path_resolver, executable_path, argv, envp)?.resume()
}

fn create_init_process(
    path_resolver: PathResolver,
    executable_path: Path,
    argv: Vec<CString>,
    envp: Vec<CString>,
) -> Result<PreparedInitialProcess> {
    let fs = ThreadFsInfo::new(path_resolver);

    let (init_proc, vmar) =
        allocate_initial_process(&executable_path, new_resource_limits_for_init());
    let pid = init_proc.pid();

    let loaded_vmar = vmar.clone_arc();
    let loaded = create_init_task(pid, &init_proc, fs, vmar, executable_path, argv, envp)?;
    init_proc
        .tasks()
        .lock()
        .insert(loaded.task.clone())
        .unwrap();

    let prepared = PreparedInitialProcess::new(init_proc, loaded_vmar, loaded.task)?;
    #[cfg(feature = "g1c-trusted-observe")]
    prepared.activate_observation(loaded.image, loaded.entry)?;
    Ok(prepared)
}

fn allocate_initial_process(
    executable_path: &Path,
    resource_limits: ResourceLimits,
) -> (Arc<Process>, VmarHandle) {
    let pid = allocate_posix_tid();
    let vmar = VmarHandle::new(ProcessVm::new(executable_path.clone()));
    let nice = Nice::default();
    let oom_score_adj = 0;
    let sig_dispositions = Arc::new(Mutex::new(SigDispositions::default()));
    let user_ns = UserNamespace::get_init_singleton().clone();

    let init_proc = Process::new(
        pid,
        vmar.clone_arc(),
        resource_limits,
        nice,
        oom_score_adj,
        sig_dispositions,
        user_ns,
    );

    (init_proc, vmar)
}

fn set_bootstrap_session_and_group(process: &Arc<Process>) {
    // Linux starts init without a process group or session. Asterinas requires
    // both, so the bootstrap pair has PGID/SID zero until userspace setsid().
    // Locking order: PID table -> process group
    let mut pid_table = pid_table::pid_table_mut();

    // Add the process to the bootstrap process group and session
    let (session, process_group) = Session::new_bootstrap_pair(process);
    pid_table.insert_session(session.sid(), &session);
    pid_table.insert_process_group(process_group.pgid(), &process_group);
    *process.process_group.lock() = Some(process_group);

    // Add the new process to the global table
    pid_table.insert_process(process.pid(), process);
}

/// Creates the init task from the given executable path.
struct LoadedInitialTask {
    task: Arc<Task>,
    #[cfg(feature = "g1c-trusted-observe")]
    image: LoadedInitialImage,
    #[cfg(feature = "g1c-trusted-observe")]
    entry: Vaddr,
}

fn create_init_task(
    tid: Tid,
    process: &Arc<Process>,
    fs: ThreadFsInfo,
    vmar: VmarHandle,
    executable_path: Path,
    argv: Vec<CString>,
    envp: Vec<CString>,
) -> Result<LoadedInitialTask> {
    let credentials = Credentials::new_root();

    #[cfg(feature = "g1c-trusted-observe")]
    let image;
    let (elf_load_info, executable_abs_path) = {
        let path_resolver = fs.resolver().read();
        let executable_abs_path = path_resolver.make_abs_path(&executable_path).into_string();
        let shebang_script_path =
            ShebangScriptPath::Accessible(CString::new(executable_abs_path.clone()).unwrap());

        let executable = UndetectedExecutable::open(executable_path.clone(), shebang_script_path)?;
        #[cfg(not(feature = "g1c-trusted-observe"))]
        let elf_load_info = {
            let stack_limit_bytes = process
                .resource_limits()
                .get_rlimit(crate::process::ResourceType::RLIMIT_STACK)
                .get_cur();
            let program_to_load = ProgramToLoad::from_executable(
                executable,
                &path_resolver,
                argv,
                envp,
                stack_limit_bytes,
            )?;
            let vmar = process.lock_vmar();
            program_to_load.load_to_vmar(vmar.unwrap(), &path_resolver)?
        };
        #[cfg(feature = "g1c-trusted-observe")]
        let elf_load_info = {
            let (info, loaded) = executable.load_trusted_initial(vmar.clone_arc(), argv, envp)?;
            image = loaded;
            info
        };

        (elf_load_info, executable_abs_path)
    };

    let mut user_ctx = UserContext::default();
    user_ctx.set_instruction_pointer(elf_load_info.entry_point as _);
    user_ctx.set_stack_pointer(elf_load_info.user_stack_top as _);

    let thread_name = derive_thread_name(&executable_abs_path);

    let thread_builder =
        PosixThreadBuilder::new(tid, thread_name, Box::new(user_ctx), credentials, vmar)
            .process(Arc::downgrade(process))
            .fs(Arc::new(fs));
    Ok(LoadedInitialTask {
        task: thread_builder.build(),
        #[cfg(feature = "g1c-trusted-observe")]
        image,
        #[cfg(feature = "g1c-trusted-observe")]
        entry: elf_load_info.entry_point,
    })
}

#[cfg(ktest)]
mod tests {
    use ostd::prelude::ktest;

    use super::*;
    use crate::process::test_util;

    // Actual Process/VMAR/Task allocations, without a loaded executable or
    // scheduling. Only the ordinary boot exercises loader -> prepare -> resume.
    fn prepare_fixture() -> PreparedInitialProcess {
        let (process, task) = test_util::new_unstarted_process();
        let vmar = process.vmar.lock().as_ref().unwrap().clone();
        PreparedInitialProcess::new(process, vmar, task).unwrap()
    }

    #[track_caller]
    fn assert_stale<T: Debug>(result: Result<T>) {
        assert_eq!(result.unwrap_err().error(), Errno::ESTALE);
    }

    #[ktest]
    fn initial_resume_claim_is_consumed_exactly_once() {
        let mut prepared = prepare_fixture();
        let key = prepared.key;
        prepared.claim_resume().unwrap();
        assert_stale(prepared.claim_resume());
        assert_eq!(prepared.process.hepta_capspace_session().unwrap(), key);
        assert_stale(prepared.process.hepta_image.lock().claim_unprepared_run());
    }

    #[ktest]
    fn prepared_initial_process_cannot_use_the_ordinary_first_run() {
        let prepared = prepare_fixture();
        assert_stale(prepared.process.hepta_image.lock().claim_unprepared_run());
        assert!(
            PreparedInitialProcess::new(
                prepared.process.clone(),
                prepared.vmar.clone(),
                prepared.task.clone()
            )
            .is_err()
        );
    }

    #[ktest]
    fn dropping_unconsumed_preparation_closes_only_its_image() {
        let prepared = prepare_fixture();
        let process = prepared.process.clone();
        let key = prepared.key;
        drop(prepared);
        assert_stale(process.hepta_capspace_session());
        assert_stale(process.check_hepta_capspace_session(key));
    }

    #[ktest]
    fn preparation_rejects_a_foreign_process_allocation() {
        let prepared = prepare_fixture();
        let (foreign, _foreign_task) = test_util::new_unstarted_process();
        let foreign_key = foreign.hepta_capspace_session().unwrap();
        assert!(
            PreparedInitialProcess::new(
                foreign.clone(),
                prepared.vmar.clone(),
                prepared.task.clone()
            )
            .is_err()
        );
        assert_eq!(foreign.hepta_capspace_session().unwrap(), foreign_key);
    }

    #[ktest]
    fn preparation_rejects_a_foreign_main_task() {
        let (process, _task) = test_util::new_unstarted_process();
        let (_foreign, foreign_task) = test_util::new_unstarted_process();
        let vmar = process.vmar.lock().as_ref().unwrap().clone();
        assert!(PreparedInitialProcess::new(process, vmar, foreign_task).is_err());
    }

    #[ktest]
    fn resume_rejects_replaced_vmar_and_cancels_the_prepared_image() {
        let mut prepared = prepare_fixture();
        let process = prepared.process.clone();
        let replacement = VmarHandle::new(ProcessVm::new(
            prepared.vmar.process_vm().executable_path().clone(),
        ));
        let old_vmar = process.lock_vmar().set_vmar(Some(replacement.clone_arc()));
        assert_stale(prepared.claim_resume());
        drop(prepared);
        assert_stale(process.hepta_capspace_session());
        let displaced = process.lock_vmar().set_vmar(old_vmar);
        drop(displaced);
    }

    #[ktest]
    fn resume_rejects_a_foreign_task_pin() {
        let mut prepared = prepare_fixture();
        let (_foreign, foreign_task) = test_util::new_unstarted_process();
        prepared.task = foreign_task;
        assert_stale(prepared.claim_resume());
    }

    #[ktest]
    fn prepared_old_epoch_cannot_resume_or_close_a_replacement_image() {
        let mut prepared = prepare_fixture();
        let process = prepared.process.clone();
        let old_key = prepared.key;
        process.begin_hepta_image_close();
        process.commit_hepta_exec_image().unwrap();
        let new_key = process.hepta_capspace_session().unwrap();
        assert_ne!(old_key, new_key);
        assert_stale(prepared.claim_resume());
        drop(prepared);
        assert_eq!(process.hepta_capspace_session().unwrap(), new_key);
    }

    #[ktest]
    fn prepared_exit_group_state_cannot_resume() {
        let mut prepared = prepare_fixture();
        {
            let mut tasks = prepared.process.tasks().lock();
            tasks.set_exited_group();
            prepared.process.begin_hepta_image_close();
        }
        assert_stale(prepared.claim_resume());
    }
}
