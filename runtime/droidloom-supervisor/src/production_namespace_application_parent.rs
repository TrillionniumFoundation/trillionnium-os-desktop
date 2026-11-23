//! Application authority borrowed only from the original live Ready owner.
//! Process numbers found here are observation data. They never select a
//! command namespace, a signal target, or an application execution root.
use super::*;
use crate::control::application_probe::RuntimeEpoch;
use crate::production_application::{
    ApplicationRead, ApplicationReadResult, ApplicationTaskControl, BrowserCommand,
    BrowserCommandResult, ContactsQuery, ContactsReadResult, LaunchCommand, LaunchCommandResult,
};
use crate::production_cgroup::ApplicationLeaf;

#[path = "production_namespace_task_control_parent.rs"]
mod task_control;
pub(crate) use task_control::{TaskControlEndpoint, TaskControlPeer};

#[path = "production_namespace_image_custody.rs"]
mod image_custody;

#[path = "production_namespace_input_threads.rs"]
mod input_threads;

pub(crate) struct ApplicationAuthority<'a> {
    tree: &'a IsolatedNamespaces,
    selection: &'a ProductionSelection,
    admission: &'a ExecutionAdmission,
}

pub(crate) struct FrameworkObservation {
    directory: File,
    node: Node,
    identity: ProcessIdentity,
    epoch: RuntimeEpoch,
    // No integer PID or Ready observation can re-issue either original owner.
    init_nonce: [u8; 16],
    init_identity: ProcessIdentity,
    init_node: Node,
    zygote_directory: File,
    zygote_node: Node,
    zygote_identity: ProcessIdentity,
}

impl ReadyTreeWitness<'_> {
    pub(crate) fn run_application_read(
        &mut self,
        request: &ApplicationRead,
    ) -> Result<ApplicationReadResult> {
        self.revalidate_application()?;
        let result = {
            let authority = self.application_authority();
            crate::production_application::run(&authority, request)
                .map_err(|error| NamespaceError::RuntimeResource(error.to_string()))
        };
        // A result from a stopped, rebooted, or changed owned tree is unusable.
        // Cleanup has already completed (or quarantined) before this check.
        let after = self.revalidate_application();
        let value = result?;
        after?;
        Ok(value)
    }

    pub(crate) fn run_application_read_before(
        &mut self,
        request: &ApplicationRead,
        deadline: std::time::Instant,
    ) -> Result<ApplicationReadResult> {
        self.revalidate_application()?;
        let result = crate::production_application::run_read_before(
            &self.application_authority(),
            request,
            deadline,
        )
        .map_err(|error| NamespaceError::RuntimeResource(error.to_string()));
        let after = self.revalidate_application();
        let value = result?;
        after?;
        if std::time::Instant::now() >= deadline {
            return Err(NamespaceError::Rejected(
                "application read workflow deadline",
            ));
        }
        Ok(value)
    }

    pub(crate) fn run_application_browser(
        &mut self,
        request: &BrowserCommand,
        deadline: std::time::Instant,
    ) -> Result<BrowserCommandResult> {
        self.revalidate_application()?;
        let result = crate::production_application::run_browser_command(
            &self.application_authority(),
            request,
            deadline,
        )
        .map_err(|error| NamespaceError::RuntimeResource(error.to_string()));
        let after = self.revalidate_application();
        let value = result?;
        after?;
        if std::time::Instant::now() >= deadline {
            return Err(NamespaceError::Rejected("browser workflow deadline"));
        }
        Ok(value)
    }

    pub(crate) fn run_application_contacts_read(
        &mut self,
        request: &ContactsQuery,
        deadline: std::time::Instant,
    ) -> Result<ContactsReadResult> {
        self.revalidate_application()?;
        let result = crate::production_application::run_contacts_read(
            &self.application_authority(),
            request,
            deadline,
        )
        .map_err(|error| NamespaceError::RuntimeResource(error.to_string()));
        let after = self.revalidate_application();
        let value = result?;
        after?;
        if std::time::Instant::now() >= deadline {
            return Err(NamespaceError::Rejected("Contacts read workflow deadline"));
        }
        Ok(value)
    }

    pub(crate) fn run_application_launch(
        &mut self,
        request: &LaunchCommand,
        deadline: std::time::Instant,
    ) -> Result<LaunchCommandResult> {
        if std::time::Instant::now() >= deadline {
            return Err(NamespaceError::Rejected("launch absolute deadline"));
        }
        self.revalidate_application()?;
        let result = crate::production_application::run_launch_command(
            &self.application_authority(),
            request,
            deadline,
        )
        .map_err(|error| NamespaceError::RuntimeResource(error.to_string()));
        let after = self.revalidate_application();
        let value = result?;
        after?;
        if std::time::Instant::now() >= deadline {
            return Err(NamespaceError::Rejected("launch absolute deadline"));
        }
        Ok(value)
    }

    pub(crate) fn open_application_task_control(
        &mut self,
        package: &str,
        deadline: std::time::Instant,
    ) -> Result<ApplicationTaskControl> {
        self.revalidate_application()?;
        let result = crate::production_application::connect_task_control(
            &self.application_authority(),
            package,
            deadline,
        )
        .map_err(|error| NamespaceError::RuntimeResource(error.to_string()));
        let after = self.revalidate_application();
        let value = result?;
        after?;
        if std::time::Instant::now() >= deadline {
            return Err(NamespaceError::Rejected("task-control connection deadline"));
        }
        Ok(value)
    }

    pub(crate) fn revalidate_task_control(
        &mut self,
        connection: &ApplicationTaskControl,
        deadline: std::time::Instant,
    ) -> Result<()> {
        self.revalidate_application()?;
        connection
            .revalidate(&self.application_authority(), deadline)
            .map_err(|error| NamespaceError::RuntimeResource(error.to_string()))
    }

    pub(crate) fn exchange_task_control(
        &mut self,
        connection: &mut ApplicationTaskControl,
        request: &droidloom_task_control::ControlRequest,
        deadline: std::time::Instant,
    ) -> Result<droidloom_task_control::ControlResponse> {
        self.revalidate_application()?;
        let result = connection
            .exchange(&self.application_authority(), request, deadline)
            .map_err(|error| NamespaceError::RuntimeResource(error.to_string()));
        let after = self.revalidate_application();
        let response = result?;
        after?;
        if std::time::Instant::now() >= deadline {
            return Err(NamespaceError::Rejected("task-control exchange deadline"));
        }
        Ok(response)
    }

    pub(crate) fn revalidate_application(&mut self) -> Result<()> {
        if self.owner.readiness(self.selection, self.admission)? != BootProperty::Complete {
            return Err(NamespaceError::Rejected(
                "application read requires current actual readiness",
            ));
        }
        Ok(())
    }

    fn application_authority(&self) -> ApplicationAuthority<'_> {
        ApplicationAuthority {
            tree: &self.owner.tree,
            selection: self.selection,
            admission: self.admission,
        }
    }

    pub(crate) fn observe_application_framework(&mut self) -> Result<FrameworkObservation> {
        self.revalidate_application()?;
        let authority = self.application_authority();
        authority.observe_framework()
    }

    pub(crate) fn application_epoch(
        &mut self,
        held: &FrameworkObservation,
    ) -> Result<RuntimeEpoch> {
        self.revalidate_application()?;
        self.application_authority().verify_framework(held)?;
        Ok(held.epoch.clone())
    }
}

impl ApplicationAuthority<'_> {
    /// Progress only from the same already-issued Ready application authority.
    /// This is called after the short-lived namespace join worker is reaped;
    /// it does not exempt that worker from the original live admission scan.
    pub(crate) fn progress_inherited_native(&self, deadline: Instant) -> Result<()> {
        self.revalidate()?;
        if Instant::now() >= deadline {
            return Err(NamespaceError::Rejected(
                "application native progress deadline",
            ));
        }
        let end = deadline.min(Instant::now() + Duration::from_secs(10));
        match self.tree.progress_inherited_native(end)? {
            InheritedNativePoll::Idle | InheritedNativePoll::Completed(_) => {}
            InheritedNativePoll::PendingOther(_) => {
                // Never leave an unsupported operation parked indefinitely or
                // reinterpret it as a native-namespace success.
                let child = self.child()?;
                if !pidfd_exited(&child.pidfd)? {
                    signal_owned(&child.pidfd, libc::SIGKILL)?;
                }
                return Err(NamespaceError::Rejected(
                    "application inherited operation needs its fixed non-native dispatcher",
                ));
            }
        }
        self.revalidate()?;
        if Instant::now() >= deadline {
            return Err(NamespaceError::Rejected(
                "application native progress exceeded deadline",
            ));
        }
        Ok(())
    }

    fn child(&self) -> Result<&TreeChild> {
        self.tree
            .init
            .as_ref()
            .ok_or(NamespaceError::RetirementUnproven)
    }

    pub(crate) fn revalidate(&self) -> Result<()> {
        self.admission
            .revalidate_tree(self.selection, &self.tree.witness()?)
            .map_err(|error| NamespaceError::RuntimeResource(error.to_string()))?;
        self.tree.verify_live_admission()?;
        self.tree.require_cgroup_hierarchy_ready()?;
        let child = self.child()?;
        child.verify()?;
        let target = executable(child)?;
        self.tree
            .runtime_observation
            .as_ref()
            .ok_or(NamespaceError::Rejected("original runtime custody absent"))?
            .verify_executable_target(&target)
    }

    pub(crate) fn leaf(&self) -> Result<ApplicationLeaf<'_>> {
        self.revalidate()?;
        let r = self
            .tree
            .keeper
            .as_ref()
            .ok_or(NamespaceError::RetirementUnproven)?
            .owner
            .held()?;
        match &r.authority {
            HeldAuthority::Budgeted(group) => group
                .application_leaf(&CgroupTreeReadyWitness { tree: self.tree })
                .map_err(|error| NamespaceError::CgroupResource(error.to_string())),
            #[cfg(test)]
            _ => Err(NamespaceError::HostAdmissionRequired),
        }
    }

    /// Borrow the actual resource owner retained by the Ready issuer. This
    /// exposes no constructor, mount transfer or independent execution power.
    pub(crate) fn runtime_owner(
        &self,
    ) -> Result<&crate::production_runtime_assets::PreparedRuntime> {
        self.revalidate()?;
        self.tree.runtime.as_ref().ok_or(NamespaceError::Rejected(
            "original query runtime custody absent",
        ))
    }

    pub(crate) fn query_runtime_binding(
        &self,
    ) -> Result<(&str, &str, u32, (u64, u64), (u32, u32))> {
        self.revalidate()?;
        let child = self.child()?;
        let userns = child.namespaces.userns.metadata()?;
        Ok((
            self.selection.base_cohort(),
            self.selection.runtime_manifest(),
            self.selection.spec().host_uid,
            (userns.dev(), userns.ino()),
            (child.uids.start, child.gids.start),
        ))
    }

    pub(crate) fn descriptors(&self, binary: &CStr) -> Result<Vec<File>> {
        self.revalidate()?;
        if binary != c"cmd" && binary != c"toybox" && binary != c"app_process64" {
            return Err(NamespaceError::Rejected(
                "application binary is not a fixed read tool",
            ));
        }
        let child = self.child()?;
        let root = held_child_root(child)?;
        let system = fixed_at(&root, c"system", true, false)?;
        let bin = fixed_at(&system, c"bin", true, false)?;
        let original = fixed_at(&bin, binary, false, true)?;
        let metadata = original.metadata()?;
        if !metadata.is_file()
            || metadata.mode() & 0o6000 != 0
            || metadata.mode() & 0o111 == 0
            || metadata.mode() & 0o022 != 0
            || metadata.uid() != child.uids.start
            || metadata.len() == 0
            || metadata.len() > 128 * 1024 * 1024
        {
            return Err(NamespaceError::Rejected(
                "fixed Android read tool metadata differs",
            ));
        }
        let runtime = self.runtime_owner()?;
        let role: crate::production_runtime_assets::RuntimeQueryExecutable<'_> = runtime
            .query_executable(self, binary)
            .map_err(|error| NamespaceError::RuntimeResource(error.to_string()))?;
        role.verify_original(&original, child.uids.start, child.gids.start)
            .map_err(|error| NamespaceError::RuntimeResource(error.to_string()))?;
        let private = fixed_at(&root, c".droidloom-query", true, false)?;
        let executable = fixed_at(&private, binary, false, true)?;
        role.verify_projection(&executable)
            .map_err(|error| NamespaceError::RuntimeResource(error.to_string()))?;
        // The public original is retained only for the fresh worker's second
        // complete-byte/label check. Only the private role can be executed.
        if (role.file().metadata()?.dev(), role.file().metadata()?.ino())
            != (executable.metadata()?.dev(), executable.metadata()?.ino())
        {
            return Err(NamespaceError::Rejected(
                "query target differs from the held private role",
            ));
        }
        let parent_fd = unsafe { libc::syscall(libc::SYS_pidfd_open, libc::getpid(), 0_u32) };
        if parent_fd < 0 {
            return Err(io::Error::last_os_error().into());
        }
        // The only numeric pidfd_open here is this very process. Target
        // authority always comes from the already held original init pidfd.
        let parent = unsafe { File::from_raw_fd(parent_fd as i32) };
        let init = File::from(child.pidfd.try_clone()?);
        let user = child.namespaces.userns.try_clone()?;
        let mut files = vec![init, parent, root, user];
        for kind in [
            libc::CLONE_NEWNS,
            libc::CLONE_NEWPID,
            libc::CLONE_NEWIPC,
            libc::CLONE_NEWUTS,
            libc::CLONE_NEWNET,
            libc::CLONE_NEWCGROUP,
        ] {
            let namespace = child
                .namespaces
                .held
                .iter()
                .find(|row| row.1 == kind)
                .ok_or(NamespaceError::Rejected(
                    "original application namespace absent",
                ))?;
            files.push(namespace.3.try_clone()?);
        }
        files.push(executable);
        files.push(original);
        role.revalidate(self)
            .map_err(|error| NamespaceError::RuntimeResource(error.to_string()))?;
        self.revalidate()?;
        Ok(files)
    }

    /// Additional descriptors are only this same owner's fixed readonly
    /// content.jar copy and its actual selected system counterpart.
    pub(crate) fn contacts_content_descriptors(&self) -> Result<[File; 2]> {
        self.revalidate()?;
        let child = self.child()?;
        let root = held_child_root(child)?;
        let system = fixed_at(&root, c"system", true, false)?;
        let framework = fixed_at(&system, c"framework", true, false)?;
        let original = fixed_at(&framework, c"content.jar", false, true)?;
        let runtime = self.runtime_owner()?;
        let role: crate::production_runtime_assets::RuntimeQueryData<'_> = runtime
            .contacts_content_jar(self)
            .map_err(|error| NamespaceError::RuntimeResource(error.to_string()))?;
        role.verify_original(&original, child.uids.start, child.gids.start)
            .map_err(|error| NamespaceError::RuntimeResource(error.to_string()))?;
        let private = fixed_at(&root, c".droidloom-query", true, false)?;
        let copy = fixed_at(&private, c"content.jar", false, true)?;
        role.verify_projection(&copy)
            .map_err(|error| NamespaceError::RuntimeResource(error.to_string()))?;
        if (copy.metadata()?.dev(), copy.metadata()?.ino())
            != (role.file().metadata()?.dev(), role.file().metadata()?.ino())
        {
            return Err(NamespaceError::Rejected(
                "Contacts classpath differs from held runtime role",
            ));
        }
        role.revalidate(self)
            .map_err(|error| NamespaceError::RuntimeResource(error.to_string()))?;
        self.revalidate()?;
        Ok([copy, original])
    }

    pub(crate) fn bind_created_process(&self, pidfd: &OwnedFd, query: bool) -> Result<(File, u32)> {
        self.revalidate()?;
        let child = self.child()?;
        if pidfd_exited(pidfd)? {
            return Err(NamespaceError::Rejected(
                "created application child exited before binding",
            ));
        }
        let info = pidfd_info(pidfd.as_raw_fd())?;
        if info.pid != info.tgid || info.ppid != child.parent_pid || info.pid == child.identity.pid
        {
            return Err(NamespaceError::Rejected(
                "application pidfd is not an owned direct broker child",
            ));
        }
        if query {
            require_pidfd_creds(&info, child.uids.start, child.gids.start)?;
            child.namespaces.verify(pidfd)?;
        } else {
            require_pidfd_creds(&info, 0, 0)?;
        }
        // Lookup only binds the process already acquired atomically by clone3.
        let directory = open_proc_at(
            &child.proc_root,
            &info.pid.to_string(),
            libc::O_RDONLY | libc::O_DIRECTORY,
        )?;
        let identity = read_identity(&directory, info.pid)?;
        if identity.parent != child.parent_pid || pidfd_exited(pidfd)? {
            return Err(NamespaceError::Rejected(
                "application process generation changed while binding",
            ));
        }
        Ok((directory, info.pid))
    }

    pub(crate) fn mapped_root(&self) -> Result<(u32, u32)> {
        let child = self.child()?;
        Ok((child.uids.start, child.gids.start))
    }

    fn observe_framework(&self) -> Result<FrameworkObservation> {
        self.revalidate()?;
        let held = observe_framework_for_child(self.child()?)?;
        self.verify_framework(&held)?;
        Ok(held)
    }

    fn verify_framework(&self, held: &FrameworkObservation) -> Result<()> {
        self.revalidate()?;
        verify_framework_for_child(self.child()?, held)?;
        self.revalidate()
    }
}

// A pre-Ready read-only issuer. This does not require ExecutionAdmission,
// ReadyTreeWitness, or a sys.boot_completed property. Its live original-init
// borrow is the only way to obtain or recheck this observation. It cannot
// authorize task-profile writes, an app command, or a final exec.
impl ExecutedInitWitness<'_> {
    pub(crate) fn observe_pre_ready_framework(&self) -> Result<FrameworkObservation> {
        self.revalidate()?;
        let held = observe_framework_for_child(self.init())?;
        self.revalidate_pre_ready_framework(&held)?;
        Ok(held)
    }

    /// Observe the current input workers without issuing a Ready or task-control authority.
    pub(crate) fn observe_pre_ready_input_threads(
        &self,
        deadline: std::time::Instant,
    ) -> Result<()> {
        let framework = self.observe_pre_ready_framework()?;
        input_threads::observe(self, &framework, deadline)
    }

    pub(crate) fn revalidate_pre_ready_framework(&self, held: &FrameworkObservation) -> Result<()> {
        self.revalidate()?;
        verify_framework_for_child(self.init(), held)?;
        self.revalidate()
    }
}

fn same_guest_namespaces(directory: &File, child: &TreeChild) -> Result<bool> {
    // Proc magic links are followed only to read and compare NSFS inodes.
    // These descriptors never become a setns target or process authority.
    for (name, expected) in [
        (c"ns/pid", child.pid_namespace()),
        (c"ns/user", &child.namespaces.userns),
    ] {
        let raw = unsafe {
            libc::openat(
                directory.as_raw_fd(),
                name.as_ptr(),
                libc::O_RDONLY | libc::O_CLOEXEC,
            )
        };
        if raw < 0 {
            return Err(io::Error::last_os_error().into());
        }
        let namespace = unsafe { File::from_raw_fd(raw) };
        check_fs(namespace.as_raw_fd(), NSFS_MAGIC)?;
        if Node::of(&namespace)? != Node::of(expected)? {
            return Ok(false);
        }
    }
    Ok(true)
}

fn require_process_credentials(
    directory: &File,
    uid: u32,
    gid: u32,
    role: &'static str,
) -> Result<()> {
    let status = read_proc(directory, "status")?;
    for (field, expected) in [("Uid:", uid), ("Gid:", gid)] {
        let observed = status_field(&status, field)?
            .split_ascii_whitespace()
            .map(str::parse::<u32>)
            .collect::<std::result::Result<Vec<_>, _>>()
            .map_err(|_| NamespaceError::Rejected("malformed Android process credentials"))?;
        if observed != [expected; 4] {
            return Err(NamespaceError::Rejected(role));
        }
    }
    Ok(())
}

fn zygote_name(directory: &File) -> Result<bool> {
    Ok(matches!(
        read_proc(directory, "comm")?.as_slice(),
        b"zygote\n" | b"zygote64\n"
    ))
}

fn valid_original_chain(
    init: ProcessIdentity,
    zygote: ProcessIdentity,
    system_server: ProcessIdentity,
) -> bool {
    init.pid != zygote.pid
        && zygote.pid != system_server.pid
        && init.pid != system_server.pid
        && zygote.parent == init.pid
        && system_server.parent == zygote.pid
        && init.start_ticks < zygote.start_ticks
        && zygote.start_ticks < system_server.start_ticks
}

fn observe_zygote(
    child: &TreeChild,
    system_server: &ProcessIdentity,
) -> Result<(File, Node, ProcessIdentity)> {
    if system_server.parent == child.identity.pid || system_server.parent == 0 {
        return Err(NamespaceError::Rejected(
            "system_server is not a child of the original zygote",
        ));
    }
    let directory = open_proc_at(
        &child.proc_root,
        &system_server.parent.to_string(),
        libc::O_RDONLY | libc::O_DIRECTORY,
    )?;
    let identity = read_identity(&directory, system_server.parent)?;
    if !valid_original_chain(child.identity, identity, *system_server)
        || !zygote_name(&directory)?
        || !same_guest_namespaces(&directory, child)?
    {
        return Err(NamespaceError::Rejected(
            "zygote parent is not in the original init generation",
        ));
    }
    require_process_credentials(
        &directory,
        child.uids.start,
        child.gids.start,
        "zygote is not mapped guest root",
    )?;
    let node = Node::of(&directory)?;
    Ok((directory, node, identity))
}

fn observe_framework_for_child(child: &TreeChild) -> Result<FrameworkObservation> {
    child.verify()?;
    let boot = read_boot_uuid(&child.proc_root)?;
    let mut found = None;
    for name in proc_names(&child.proc_root)? {
        let pid: u32 = name
            .parse()
            .map_err(|_| NamespaceError::Rejected("malformed proc observation name"))?;
        let directory =
            match open_proc_at(&child.proc_root, &name, libc::O_RDONLY | libc::O_DIRECTORY) {
                Ok(value) => value,
                Err(NamespaceError::Io(error))
                    if matches!(error.raw_os_error(), Some(libc::ENOENT | libc::ESRCH)) =>
                {
                    continue;
                }
                Err(error) => return Err(error),
            };
        let comm = match read_proc(&directory, "comm") {
            Ok(value) => value,
            Err(NamespaceError::Io(error))
                if matches!(error.raw_os_error(), Some(libc::ENOENT | libc::ESRCH)) =>
            {
                continue;
            }
            Err(error) => return Err(error),
        };
        if comm != b"system_server\n" || !framework_namespace(&directory, child)? {
            continue;
        }
        let identity = read_identity(&directory, pid)?;
        let (zygote_directory, zygote_node, zygote_identity) = observe_zygote(child, &identity)?;
        let held = FrameworkObservation {
            node: Node::of(&directory)?,
            directory,
            identity,
            epoch: RuntimeEpoch {
                boot_id: boot.clone(),
                cell_host_pid: child.identity.pid,
                framework_host_pid: pid,
                framework_start_ticks: identity.start_ticks,
            },
            init_nonce: child.nonce,
            init_identity: child.identity,
            init_node: child.proc_node,
            zygote_directory,
            zygote_node,
            zygote_identity,
        };
        verify_framework_for_child(child, &held)?;
        if found.replace(held).is_some() {
            return Err(NamespaceError::Rejected(
                "more than one owned system_server",
            ));
        }
    }
    child.verify()?;
    found.ok_or(NamespaceError::Rejected(
        "actual system_server not found in original namespace",
    ))
}

fn verify_framework_for_child(child: &TreeChild, held: &FrameworkObservation) -> Result<()> {
    child.verify()?;
    if child.nonce != held.init_nonce
        || child.identity != held.init_identity
        || child.proc_node != held.init_node
        || Node::of(&held.directory)? != held.node
        || read_identity(&held.directory, held.identity.pid)? != held.identity
        || read_proc(&held.directory, "comm")? != b"system_server\n"
        || !framework_namespace(&held.directory, child)?
        || read_boot_uuid(&child.proc_root)? != held.epoch.boot_id
        || held.epoch.cell_host_pid != child.identity.pid
        || held.epoch.framework_host_pid != held.identity.pid
        || held.epoch.framework_start_ticks != held.identity.start_ticks
        || held.identity.parent != held.zygote_identity.pid
        || Node::of(&held.zygote_directory)? != held.zygote_node
        || read_identity(&held.zygote_directory, held.zygote_identity.pid)? != held.zygote_identity
        || !valid_original_chain(child.identity, held.zygote_identity, held.identity)
        || !zygote_name(&held.zygote_directory)?
        || !same_guest_namespaces(&held.zygote_directory, child)?
    {
        return Err(NamespaceError::Rejected(
            "held original init/zygote/system_server generation changed",
        ));
    }
    require_process_credentials(
        &held.zygote_directory,
        child.uids.start,
        child.gids.start,
        "zygote credentials changed",
    )?;
    for (name, node) in [
        (held.identity.pid, held.node),
        (held.zygote_identity.pid, held.zygote_node),
    ] {
        let named = open_proc_at(
            &child.proc_root,
            &name.to_string(),
            libc::O_RDONLY | libc::O_DIRECTORY,
        )?;
        if Node::of(&named)? != node {
            return Err(NamespaceError::Rejected(
                "original Android process proc name was replaced",
            ));
        }
    }
    child.verify()
}

fn read_boot_uuid(proc_root: &File) -> Result<String> {
    let mut file = proc_root.try_clone()?;
    for name in [c"sys", c"kernel", c"random"] {
        file = fixed_at(&file, name, true, false)?;
    }
    let leaf = fixed_at(&file, c"boot_id", false, true)?;
    let mut value = String::new();
    leaf.take(64).read_to_string(&mut value)?;
    let value = value.trim_end_matches('\n');
    if value.len() != 36
        || value.bytes().enumerate().any(|(index, byte)| {
            if [8, 13, 18, 23].contains(&index) {
                byte != b'-'
            } else {
                !byte.is_ascii_hexdigit() || byte.is_ascii_uppercase()
            }
        })
    {
        return Err(NamespaceError::Rejected("host boot UUID is malformed"));
    }
    Ok(value.to_owned())
}

const FRAMEWORK_PAYLOAD_PREFIX: &str =
    "0::/system.slice/droidloom-production.service/cell-u1000/payload/";

fn framework_namespace(directory: &File, child: &TreeChild) -> Result<bool> {
    if !same_guest_namespaces(directory, child)? {
        return Ok(false);
    }
    let uid = child
        .uids
        .start
        .checked_add(1000)
        .ok_or(NamespaceError::Rejected("framework UID overflow"))?;
    let gid = child
        .gids
        .start
        .checked_add(1000)
        .ok_or(NamespaceError::Rejected("framework GID overflow"))?;
    require_process_credentials(directory, uid, gid, "framework credentials differ")?;
    let cgroup = read_proc(directory, "cgroup")?;
    let cgroup = std::str::from_utf8(&cgroup)
        .map_err(|_| NamespaceError::Rejected("non-text framework cgroup"))?;
    if !cgroup.starts_with(FRAMEWORK_PAYLOAD_PREFIX)
        || cgroup.lines().count() != 1
        || cgroup
            .trim_end_matches('\n')
            .split('/')
            .skip(1)
            .any(|part| part.is_empty() || part == "." || part == "..")
    {
        return Err(NamespaceError::Rejected(
            "framework left the original payload budget",
        ));
    }
    Ok(true)
}

fn proc_names(root: &File) -> Result<Vec<String>> {
    let file = fixed_at(root, c".", true, true)?;
    check_fs(file.as_raw_fd(), PROC_MAGIC)?;
    let mut names = Vec::new();
    let mut buffer = [0_u8; 16384];
    loop {
        let count = unsafe {
            libc::syscall(
                libc::SYS_getdents64,
                file.as_raw_fd(),
                buffer.as_mut_ptr(),
                buffer.len(),
            )
        };
        if count < 0 {
            return Err(io::Error::last_os_error().into());
        }
        if count == 0 {
            break;
        }
        let mut offset = 0;
        while offset < count as usize {
            if offset + 20 > count as usize {
                return Err(NamespaceError::Rejected("short proc directory record"));
            }
            let size = u16::from_ne_bytes([buffer[offset + 16], buffer[offset + 17]]) as usize;
            if size < 20 || offset + size > count as usize {
                return Err(NamespaceError::Rejected("invalid proc directory record"));
            }
            let bytes = &buffer[offset + 19..offset + size];
            let end = bytes
                .iter()
                .position(|byte| *byte == 0)
                .ok_or(NamespaceError::Rejected("unterminated proc name"))?;
            let bytes = &bytes[..end];
            if buffer[offset + 18] == libc::DT_DIR
                && !bytes.is_empty()
                && bytes.iter().all(u8::is_ascii_digit)
            {
                names.push(
                    String::from_utf8(bytes.to_vec())
                        .map_err(|_| NamespaceError::Rejected("non-text proc name"))?,
                );
                if names.len() > 131072 {
                    return Err(NamespaceError::Rejected("proc observation bound"));
                }
            }
            offset += size;
        }
    }
    Ok(names)
}

#[cfg(test)]
mod pre_ready_identity_tests {
    use super::*;

    #[test]
    fn original_init_zygote_system_server_lineage_rejects_reparenting_and_reuse() {
        let init = ProcessIdentity {
            pid: 200,
            parent: 1,
            start_ticks: 10,
        };
        let zygote = ProcessIdentity {
            pid: 201,
            parent: 200,
            start_ticks: 20,
        };
        let system_server = ProcessIdentity {
            pid: 202,
            parent: 201,
            start_ticks: 30,
        };
        assert!(valid_original_chain(init, zygote, system_server));
        assert!(!valid_original_chain(
            init,
            ProcessIdentity {
                parent: 1,
                ..zygote
            },
            system_server,
        ));
        assert!(!valid_original_chain(
            init,
            zygote,
            ProcessIdentity {
                parent: 200,
                ..system_server
            },
        ));
        assert!(!valid_original_chain(
            init,
            ProcessIdentity {
                start_ticks: 31,
                ..zygote
            },
            system_server,
        ));
        assert!(!valid_original_chain(
            init,
            ProcessIdentity {
                start_ticks: 9,
                ..zygote
            },
            system_server,
        ));
        assert!(!valid_original_chain(
            init,
            zygote,
            ProcessIdentity {
                pid: 201,
                ..system_server
            },
        ));
        assert!(!valid_original_chain(
            init,
            zygote,
            ProcessIdentity {
                start_ticks: 20,
                ..system_server
            },
        ));
    }
}
