//! Parent-side Android exec and readiness observation. Preparation does not
//! construct this type: the same owned child must pass the final admission,
//! authenticated ExecArmed, control CLOEXEC and actual executable checks.
use super::*;
use crate::production_execution::{ExecutionAdmission, PreparedExecution};
use crate::production_readiness::{BootProperty, ReadinessError, read_boot_complete};
use crate::production_selection::ProductionSelection;
use std::ffi::CStr;

const BOOT_PROPERTY: &CStr = c"u:object_r:boot_status_prop:s0";
const TMPFS_MAGIC: libc::c_long = 0x0102_1994;

#[path = "production_namespace_execution_identity.rs"]
mod identity;
pub(crate) use identity::{ExecutedDevObservation, ExecutedInitGeneration, ExecutedInitWitness};
#[path = "production_namespace_activation_peer.rs"]
mod activation_peer;
pub(crate) use activation_peer::OwnedActivationPeer;
#[path = "production_namespace_activation_broker.rs"]
mod activation_broker;
#[path = "production_namespace_activation_channel.rs"]
mod activation_channel;
#[path = "production_namespace_activation_owner.rs"]
mod activation_owner;
#[path = "production_namespace_init_bootstrap_bind.rs"]
mod init_bootstrap_bind;
#[path = "production_namespace_init_cleanup.rs"]
mod init_cleanup;
#[path = "production_namespace_init_mounts.rs"]
mod init_mounts;
#[path = "production_namespace_init_propagation.rs"]
mod init_propagation;
#[path = "production_namespace_init_storage_binds.rs"]
mod init_storage_binds;
#[path = "production_namespace_native_successor_parent.rs"]
mod native_successor;
#[path = "production_namespace_native_transition.rs"]
mod native_transition;

#[path = "production_namespace_application_parent.rs"]
mod application;
pub(crate) use application::{
    ApplicationAuthority, FrameworkObservation, TaskControlEndpoint, TaskControlPeer,
};

pub(crate) struct ExecutedNamespaces {
    tree: IsolatedNamespaces,
    linkerconfig: Option<activation_broker::CompletedLinkerconfig>,
    execution_profile: crate::production_runtime_assets::RuntimeExecProfile,
    early_cleanup: RefCell<init_cleanup::EarlyCleanup>,
    initial_mounts: RefCell<init_mounts::InitialMounts>,
    initial_propagation: RefCell<init_propagation::InitialPropagation>,
    initial_storage_binds: RefCell<init_storage_binds::InitialStorageBinds>,
}

/// A borrow of one actually executed, live and ready tree. No caller can
/// construct it from a PID, a property value, a digest or a test declaration.
pub(crate) struct ReadyTreeWitness<'a> {
    owner: &'a mut ExecutedNamespaces,
    selection: &'a ProductionSelection,
    admission: &'a ExecutionAdmission,
}

impl ReadyTreeWitness<'_> {
    pub(crate) fn host_uid(&self) -> Result<u32> {
        Ok(self.owner.tree.witness()?.identity_lease()?.host_uid())
    }
}

fn fixed_at(parent: &File, name: &CStr, directory: bool, body: bool) -> Result<File> {
    let flags = libc::O_CLOEXEC
        | libc::O_NOFOLLOW
        | libc::O_NONBLOCK
        | if body { libc::O_RDONLY } else { libc::O_PATH }
        | if directory { libc::O_DIRECTORY } else { 0 };
    let fd = unsafe { libc::openat(parent.as_raw_fd(), name.as_ptr(), flags) };
    if fd < 0 {
        return Err(io::Error::last_os_error().into());
    }
    let file = unsafe { File::from_raw_fd(fd) };
    if file.metadata()?.mode() & libc::S_IFMT == libc::S_IFLNK {
        return Err(NamespaceError::Rejected(
            "production property path is a symlink",
        ));
    }
    Ok(file)
}

fn executable(child: &TreeChild) -> Result<File> {
    child.verify()?;
    // The sole intentional proc magic-link follow. It is relative to the
    // original held proc directory, then compared to the already held init
    // inode. O_NOFOLLOW here would incorrectly inspect the proc symlink itself.
    let fd = unsafe {
        libc::openat(
            child.proc_dir.as_raw_fd(),
            c"exe".as_ptr(),
            libc::O_PATH | libc::O_CLOEXEC | libc::O_NONBLOCK,
        )
    };
    if fd < 0 {
        return Err(io::Error::last_os_error().into());
    }
    let file = unsafe { File::from_raw_fd(fd) };
    child.verify()?;
    Ok(file)
}

fn exec_failed_record(child: &TreeChild) -> Result<()> {
    let (packet, peer) = receive_packet(child.control.as_raw_fd())?;
    if !packet.matches(child.nonce, 1)
        || peer.pid != child.identity.pid as i32
        || peer.uid != child.uids.start
        || peer.gid != child.gids.start
    {
        return Err(NamespaceError::Rejected(
            "exec failure original nonce/SCM peer differs",
        ));
    }
    if packet.phase == Phase::Failed as u32 && packet.errno > 0 {
        return Err(io::Error::from_raw_os_error(packet.errno).into());
    }
    Err(NamespaceError::Rejected(
        "unexpected record after ExecArmed",
    ))
}

fn wait_exec_cloexec(child: &TreeChild) -> Result<()> {
    let deadline = Instant::now() + PROTOCOL_TIMEOUT;
    loop {
        if pidfd_exited(&child.pidfd)? {
            // A real EOF caused by process death is not evidence of exec.
            return Err(NamespaceError::Rejected(
                "owned init exited before exec observation",
            ));
        }
        let remaining = deadline.saturating_duration_since(Instant::now());
        if remaining.is_zero() {
            return Err(NamespaceError::Rejected("owned exec CLOEXEC deadline"));
        }
        let mut fds = [
            libc::pollfd {
                fd: child.control.as_raw_fd(),
                events: libc::POLLIN,
                revents: 0,
            },
            libc::pollfd {
                fd: child.pidfd.as_raw_fd(),
                events: libc::POLLIN,
                revents: 0,
            },
        ];
        let ms = remaining.as_millis().max(1).min(i32::MAX as u128) as i32;
        let rc = unsafe { libc::poll(fds.as_mut_ptr(), fds.len() as libc::nfds_t, ms) };
        if rc < 0 {
            let error = io::Error::last_os_error();
            if error.kind() == io::ErrorKind::Interrupted {
                continue;
            }
            return Err(error.into());
        }
        if rc == 0 {
            continue;
        }
        if fds.iter().any(|fd| fd.revents & libc::POLLNVAL != 0) {
            return Err(NamespaceError::Rejected(
                "owned exec descriptor became invalid",
            ));
        }
        if fds[0].revents & (libc::POLLIN | libc::POLLHUP | libc::POLLERR) != 0 {
            let mut byte = [0_u8; 1];
            let n = unsafe {
                libc::recv(
                    child.control.as_raw_fd(),
                    byte.as_mut_ptr().cast(),
                    1,
                    libc::MSG_PEEK | libc::MSG_DONTWAIT,
                )
            };
            if n == 0 {
                child.verify()?;
                return Ok(());
            }
            if n > 0 {
                return exec_failed_record(child);
            }
            let error = io::Error::last_os_error();
            if matches!(error.raw_os_error(), Some(libc::EINTR | libc::EAGAIN)) {
                continue;
            }
            return Err(error.into());
        }
    }
}

fn seccomp_filter_depth(status: &[u8]) -> Result<u32> {
    let value = status_field(status, "Seccomp_filters:")?.trim();
    if value.is_empty() || !value.bytes().all(|byte| byte.is_ascii_digit()) {
        return Err(NamespaceError::Rejected("invalid seccomp filter count"));
    }
    let count = value
        .parse::<u32>()
        .map_err(|_| NamespaceError::Rejected("invalid seccomp filter count"))?;
    match (status_field(status, "Seccomp:")?.trim(), count) {
        ("0", 0) | ("2", 1..) => Ok(count),
        _ => Err(NamespaceError::Rejected(
            "inconsistent seccomp mode and filter count",
        )),
    }
}

fn require_android_filter_installation(inherited: u32, installed: u32) -> Result<()> {
    // The raw child adds exactly one runtime filter and one APEX listener
    // filter between these two barriers. The count alone has no policy identity.
    if inherited.checked_add(2) != Some(installed) {
        return Err(NamespaceError::Rejected(
            "original init seccomp filter installation differed",
        ));
    }
    Ok(())
}

impl IsolatedNamespaces {
    pub(crate) fn execute_runtime(
        mut self,
        selection: &ProductionSelection,
        admission: &PreparedExecution,
    ) -> Result<ExecutedNamespaces> {
        admission
            .revalidate_tree(selection, &self.witness()?)
            .map_err(|error| NamespaceError::RuntimeResource(error.to_string()))?;
        self.verify_live_admission()?;
        self.require_cgroup_hierarchy_ready()?;
        let execution_profile = self
            .runtime
            .as_ref()
            .ok_or(NamespaceError::Rejected("same-cohort runtime owner absent"))?
            .execution_profile(&self.witness()?)
            .map_err(|error| NamespaceError::RuntimeResource(error.to_string()))?;
        let context = admission
            .runtime_mac_owner(selection, &self.witness()?)
            .map_err(|error| NamespaceError::RuntimeResource(error.to_string()))?;
        let child = self
            .init
            .as_ref()
            .ok_or(NamespaceError::RetirementUnproven)?;
        if self.original_trace.is_some() {
            return Err(NamespaceError::Rejected(
                "original init trace owner already held",
            ));
        }
        self.original_trace = Some(std::rc::Rc::new(RefCell::new(
            original_ptrace::OriginalPtrace::prepare(child, context, admission.deadline())?,
        )));
        self.runtime_observation
            .as_mut()
            .ok_or(NamespaceError::Rejected("no prepared same-cohort runtime"))?
            .verify(child)?;
        // RuntimeReady holds the original single-threaded child at its command
        // barrier. Host-inherited filters are part of this starting depth.
        let inherited_depth = seccomp_filter_depth(&read_proc(&child.proc_dir, "status")?)?;
        send_packet(
            child.control.as_raw_fd(),
            &Packet::new(child.nonce, Phase::ExecInitCp3aScoped, 0, child.parent_pid),
        )?;
        if self.apex_notifications.is_some() {
            return Err(NamespaceError::Rejected(
                "original init notification listener already held",
            ));
        }
        self.apex_notifications =
            Some(apex_notifications::InheritedNotifications::receive_from_child(child)?);
        // The original listener is now held and authenticated, and the child
        // cannot proceed to exec until ApexNotifyAccepted. Later Android
        // code may install more filters after this bounded interval.
        let installed_depth = seccomp_filter_depth(&read_proc(&child.proc_dir, "status")?)?;
        require_android_filter_installation(inherited_depth, installed_depth)?;
        self.apex_notifications
            .as_ref()
            .unwrap()
            .bind_original_trace(child, self.original_trace.as_ref().unwrap().clone())?;
        self.original_trace
            .as_ref()
            .unwrap()
            .try_borrow_mut()
            .map_err(|_| NamespaceError::Rejected("original trace already borrowed"))?
            .mark_start_requested()?;
        send_packet(
            child.control.as_raw_fd(),
            &Packet::new(child.nonce, Phase::ApexNotifyAccepted, 0, child.parent_pid),
        )?;
        self.original_trace
            .as_ref()
            .unwrap()
            .try_borrow_mut()
            .map_err(|_| NamespaceError::Rejected("original trace already borrowed"))?
            .confirm_traceme_record(child)?;
        loop {
            if self
                .original_trace
                .as_ref()
                .unwrap()
                .try_borrow_mut()
                .map_err(|_| NamespaceError::Rejected("original trace already borrowed"))?
                .accept_traceme()?
            {
                break;
            }
            std::thread::sleep(Duration::from_millis(1));
        }
        child.receive_phase(Phase::ExecArmed)?;
        loop {
            if self
                .original_trace
                .as_ref()
                .unwrap()
                .try_borrow_mut()
                .map_err(|_| NamespaceError::Rejected("original trace already borrowed"))?
                .accept_exec_stop()?
            {
                break;
            }
            std::thread::sleep(Duration::from_millis(1));
        }
        wait_exec_cloexec(child)?;
        let target = executable(child)?;
        self.runtime_observation
            .as_ref()
            .unwrap()
            .verify_executable_target(&target)?;
        drop(target);
        admission
            .revalidate_tree(selection, &self.witness()?)
            .map_err(|error| NamespaceError::RuntimeResource(error.to_string()))?;
        self.original_trace
            .as_ref()
            .unwrap()
            .try_borrow_mut()
            .map_err(|_| NamespaceError::Rejected("original trace already borrowed"))?
            .start_syscalls(self.runtime_observation.as_ref().unwrap())?;
        // The listener and finite tracer remain in the same tree's retirement
        // machinery; no listener descriptor survives in executed Android.
        Ok(ExecutedNamespaces {
            tree: self,
            linkerconfig: None,
            execution_profile,
            early_cleanup: RefCell::new(init_cleanup::EarlyCleanup::default()),
            initial_mounts: RefCell::new(init_mounts::InitialMounts::default()),
            initial_propagation: RefCell::new(init_propagation::InitialPropagation::default()),
            initial_storage_binds: RefCell::new(init_storage_binds::InitialStorageBinds::default()),
        })
    }
}

impl ExecutedNamespaces {
    pub(crate) fn host_pid(&self) -> u32 {
        // Display only. This value is never fed back to a constructor, signal,
        // map write, namespace entry or Android command implementation.
        self.tree
            .init
            .as_ref()
            .expect("executed owner holds init")
            .identity
            .pid
    }

    pub(crate) fn termination_observed(&self) -> Result<bool> {
        let keeper = self
            .tree
            .keeper
            .as_ref()
            .ok_or(NamespaceError::RetirementUnproven)?;
        let resources = keeper.owner.held()?;
        if unsafe { libc::syscall(libc::SYS_gettid) } != libc::c_long::from(resources.creator_tid) {
            return Err(NamespaceError::Rejected("executed owner moved threads"));
        }
        let init = self
            .tree
            .init
            .as_ref()
            .ok_or(NamespaceError::RetirementUnproven)?;
        Ok(pidfd_exited(&init.pidfd)? || pidfd_exited(&resources.pidfd)?)
    }

    fn verify_original_exec(&mut self) -> Result<()> {
        self.tree.verify_live_admission()?;
        self.tree.require_cgroup_hierarchy_ready()?;
        let child = self
            .tree
            .init
            .as_ref()
            .ok_or(NamespaceError::RetirementUnproven)?;
        child.verify()?;
        let target = executable(child)?;
        let runtime = self
            .tree
            .runtime_observation
            .as_mut()
            .ok_or(NamespaceError::Rejected("executed runtime custody absent"))?;
        runtime.verify_executable_target(&target)?;
        drop(target);
        if let Some(epoch) = child.default_mounts.get() {
            // The issuer copied only the completed original graph. Later
            // original setns selects it only after actual EXIT and DETACH;
            // publication commits must remain exact typed graph deltas.
            return epoch.verify_current_layout(child);
        }
        // The initial view stays strict. Only the separately owned, complete
        // three-call phase can select the exact new view; no numeric namespace
        // or unexpected init-created mount is adopted.
        let mounts = self
            .initial_mounts
            .try_borrow()
            .map_err(|_| NamespaceError::Rejected("original tmpfs phase already borrowed"))?;
        let propagation = self
            .initial_propagation
            .try_borrow()
            .map_err(|_| NamespaceError::Rejected("original propagation phase already borrowed"))?;
        let storage_binds = self.initial_storage_binds.try_borrow().map_err(|_| {
            NamespaceError::Rejected("original storage bind phase already borrowed")
        })?;
        if storage_binds.verify_after(&propagation, &mounts, runtime, child)?
            || propagation.verify_after(&mounts, runtime, child)?
            || mounts.verify_after(runtime, child)?
        {
            Ok(())
        } else {
            runtime.verify(child)
        }
    }

    fn verify_prepared_exec(
        &mut self,
        selection: &ProductionSelection,
        admission: &PreparedExecution,
    ) -> Result<()> {
        admission
            .revalidate_tree(selection, &self.tree.witness()?)
            .map_err(|error| NamespaceError::RuntimeResource(error.to_string()))?;
        self.verify_original_exec()?;
        admission
            .revalidate_tree(selection, &self.tree.witness()?)
            .map_err(|error| NamespaceError::RuntimeResource(error.to_string()))
    }

    fn verify_exec(
        &mut self,
        selection: &ProductionSelection,
        admission: &ExecutionAdmission,
    ) -> Result<()> {
        admission
            .revalidate_tree(selection, &self.tree.witness()?)
            .map_err(|error| NamespaceError::RuntimeResource(error.to_string()))?;
        self.verify_original_exec()?;
        let init = self.original_init_witness(selection)?;
        admission
            .revalidate_init(&init)
            .map_err(|error| NamespaceError::RuntimeResource(error.to_string()))
    }

    pub(crate) fn readiness(
        &mut self,
        selection: &ProductionSelection,
        admission: &ExecutionAdmission,
    ) -> Result<BootProperty> {
        match self.service_inherited_native(
            selection,
            admission,
            Instant::now() + Duration::from_secs(10),
        )? {
            InheritedNativePoll::Idle | InheritedNativePoll::Completed(_) => {}
            InheritedNativePoll::PendingOther(_) => {
                // No property value can qualify a tree whose original pending
                // operation has no completed fixed handler. The controller's
                // existing error path retires the same owned tree.
                return Err(NamespaceError::Rejected(
                    "original inherited non-native operation requires its fixed dispatcher",
                ));
            }
        }
        self.verify_exec(selection, admission)?;
        let child = self
            .tree
            .init
            .as_ref()
            .ok_or(NamespaceError::RetirementUnproven)?;
        let value = (|| -> Result<BootProperty> {
            let root = held_child_root(child)?;
            let dev = fixed_at(&root, c"dev", true, false)?;
            if Some(Node::of(&dev)?) != self.tree.device_node
                || filesystem_kind(&dev)? != TMPFS_MAGIC
            {
                return Err(NamespaceError::Rejected(
                    "property DEV differs from owned private mount",
                ));
            }
            let property_dir = fixed_at(&dev, c"__properties__", true, false)?;
            let metadata = property_dir.metadata()?;
            if metadata.uid() != child.uids.start
                || metadata.gid() != child.gids.start
                || metadata.mode() & 0o6022 != 0
                || filesystem_kind(&property_dir)? != TMPFS_MAGIC
            {
                return Err(NamespaceError::Rejected(
                    "private property directory custody",
                ));
            }
            let file = fixed_at(&property_dir, BOOT_PROPERTY, false, true)?;
            if filesystem_kind(&file)? != TMPFS_MAGIC {
                return Err(NamespaceError::Rejected("property area filesystem differs"));
            }
            match read_boot_complete(&file, child.uids.start, child.gids.start) {
                Ok(value) => Ok(value),
                Err(ReadinessError::Changed) => Ok(BootProperty::Updating),
                Err(error) => Err(NamespaceError::RuntimeResource(error.to_string())),
            }
        })();
        let value = match value {
            Err(NamespaceError::Io(error)) if error.kind() == io::ErrorKind::NotFound => {
                BootProperty::Absent
            }
            other => other?,
        };
        self.verify_exec(selection, admission)?;
        Ok(value)
    }

    pub(crate) fn ready_witness<'a>(
        &'a mut self,
        selection: &'a ProductionSelection,
        admission: &'a ExecutionAdmission,
    ) -> Result<Option<ReadyTreeWitness<'a>>> {
        if self.readiness(selection, admission)? == BootProperty::Complete {
            Ok(Some(ReadyTreeWitness {
                owner: self,
                selection,
                admission,
            }))
        } else {
            Ok(None)
        }
    }

    pub(crate) fn retire(mut self) -> Result<TreeExit> {
        let storage_binds_retired = self.initial_storage_binds.get_mut().retire_views();
        let propagation_retired = self.initial_propagation.get_mut().retire_views();
        let cleanup_retired = self.early_cleanup.get_mut().retire();
        let mount_views_retired = self.initial_mounts.get_mut().retire_views();
        if storage_binds_retired.is_err()
            || propagation_retired.is_err()
            || cleanup_retired.is_err()
            || mount_views_retired.is_err()
        {
            self.tree.quarantine();
            // The original namespace/lease was quarantined before dropping
            // helper guards that retain any unproven worker and descriptors.
            return Err(NamespaceError::RetirementUnproven);
        }
        let Self {
            tree,
            linkerconfig,
            execution_profile: _,
            early_cleanup,
            initial_mounts,
            initial_propagation,
            initial_storage_binds,
        } = self;
        drop(initial_storage_binds);
        drop(initial_propagation);
        drop(early_cleanup);
        drop(initial_mounts);
        // The command was already reaped; close its observation descriptors
        // before the original tree releases its mount and lease resources.
        drop(linkerconfig);
        tree.retire()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn original_init_filter_depth_requires_consistent_kernel_fields_and_an_exact_delta() {
        assert_eq!(
            seccomp_filter_depth(b"Seccomp:\t0\nSeccomp_filters:\t0\n").unwrap(),
            0
        );
        assert_eq!(
            seccomp_filter_depth(b"Seccomp:\t2\nSeccomp_filters:\t3\n").unwrap(),
            3
        );
        for status in [
            "Seccomp:\t2\n",
            "Seccomp_filters:\t2\n",
            "Seccomp:\t2\nSeccomp_filters:\t2\nSeccomp_filters:\t3\n",
            "Seccomp:\t1\nSeccomp_filters:\t2\n",
            "Seccomp:\t0\nSeccomp_filters:\t1\n",
            "Seccomp:\t2\nSeccomp_filters:\t0\n",
            "Seccomp:\t2\nSeccomp_filters:\t+2\n",
            "Seccomp:\t2\nSeccomp_filters:\t4294967296\n",
        ] {
            assert!(seccomp_filter_depth(status.as_bytes()).is_err());
        }
        require_android_filter_installation(0, 2).unwrap();
        require_android_filter_installation(3, 5).unwrap();
        for (before, after) in [(3, 2), (3, 3), (3, 4), (3, 6), (u32::MAX, 1)] {
            assert!(require_android_filter_installation(before, after).is_err());
        }
    }

    #[test]
    fn original_init_filter_depth_observes_two_new_layers_on_a_held_kernel_task() {
        // A private ordinary test thread only appends these allow-all filters.
        // Its inherited restriction stack stays in force and dies with the thread.
        std::thread::spawn(|| {
            let task = File::open("/proc/thread-self").unwrap();
            let depth = || seccomp_filter_depth(&read_proc(&task, "status").unwrap()).unwrap();
            let initial = depth();
            let mut instruction = libc::sock_filter {
                code: (libc::BPF_RET | libc::BPF_K) as u16,
                jt: 0,
                jf: 0,
                k: libc::SECCOMP_RET_ALLOW,
            };
            let program = libc::sock_fprog {
                len: 1,
                filter: &mut instruction,
            };
            assert_eq!(
                unsafe { libc::prctl(libc::PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) },
                0
            );
            let append = || {
                assert_eq!(
                    unsafe {
                        libc::syscall(
                            libc::SYS_seccomp,
                            libc::SECCOMP_SET_MODE_FILTER,
                            0,
                            &program,
                        )
                    },
                    0
                )
            };
            append();
            let inherited = depth();
            assert_eq!(inherited, initial + 1);
            append();
            assert!(require_android_filter_installation(inherited, depth()).is_err());
            append();
            require_android_filter_installation(inherited, depth()).unwrap();
        })
        .join()
        .unwrap();
    }

    #[test]
    fn production_exec_property_walk_rejects_actual_directory_and_leaf_symlinks() {
        let temp = tempfile::tempdir().unwrap();
        std::fs::create_dir(temp.path().join("real")).unwrap();
        std::fs::write(temp.path().join("real/value"), b"property").unwrap();
        std::os::unix::fs::symlink("real", temp.path().join("alias")).unwrap();
        std::os::unix::fs::symlink("value", temp.path().join("real/alias")).unwrap();
        let root = File::open(temp.path()).unwrap();
        assert!(fixed_at(&root, c"alias", true, false).is_err());
        let real = fixed_at(&root, c"real", true, false).unwrap();
        assert!(fixed_at(&real, c"alias", false, true).is_err());
        assert_eq!(
            fixed_at(&real, c"value", false, true)
                .unwrap()
                .metadata()
                .unwrap()
                .len(),
            8
        );
    }
}
