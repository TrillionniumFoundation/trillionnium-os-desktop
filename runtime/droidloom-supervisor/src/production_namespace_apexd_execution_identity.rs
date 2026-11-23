//! Original apexd thread identity from the already received inherited request.
//! A caller PID is only a lookup candidate bracketed by the same listener ID.
//! This type grants no device, syscall response, mount, Ready or production
//! state. The request owner must retain the original mount-actor ledger borrow.
//! Its kernel-only checks never call the apexd MAC witness.
use super::*;
use sha2::{Digest, Sha256};
use std::os::fd::BorrowedFd;
use std::os::unix::fs::FileExt;
use std::rc::Rc;

const APEXD_BYTES: u64 = 1_281_752;
const APEXD_SHA256: [u8; 32] = [
    0xec, 0x9d, 0x36, 0xdb, 0x2c, 0xd8, 0xeb, 0x6c, 0x9b, 0xb9, 0xe5, 0x00, 0x5b, 0x3c, 0x4d, 0x81,
    0x20, 0x6e, 0x90, 0x1d, 0x13, 0xc1, 0x12, 0xac, 0xb1, 0xa9, 0xf5, 0x7f, 0x6d, 0xfb, 0x30, 0xa4,
];

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct ExecutableIdentity {
    node: Node,
    mount: u64,
    mode: u32,
    uid: u32,
    gid: u32,
    links: u64,
    bytes: u64,
    mtime: (i64, i64),
    ctime: (i64, i64),
}

fn mount_id(file: &File) -> Result<u64> {
    super::super::super::writable_proc::held_mount_id(file)
}

impl ExecutableIdentity {
    fn observe(file: &File) -> Result<Self> {
        let m = file.metadata()?;
        if !m.is_file() || m.mode() & 0o111 == 0 || m.mode() & 0o6000 != 0 {
            return Err(NamespaceError::Rejected(
                "apexd is not a regular nonsuid executable",
            ));
        }
        Ok(Self {
            node: Node::of(file)?,
            mount: mount_id(file)?,
            mode: m.mode(),
            uid: m.uid(),
            gid: m.gid(),
            links: m.nlink(),
            bytes: m.len(),
            mtime: (m.mtime(), m.mtime_nsec()),
            ctime: (m.ctime(), m.ctime_nsec()),
        })
    }
}

fn fixed_ioctl(notification: &wire::Notification) -> Result<()> {
    if notification.id == 0
        || notification.pid <= 1
        || notification.flags != 0
        || notification.data.arch != ARCH_X86_64
        || notification.data.nr != libc::SYS_ioctl as i32
        || notification.data.instruction_pointer == 0
        || notification.data.args[0] > i32::MAX as u64
        || notification.data.args[1] > u32::MAX as u64
        || !matches!(
            notification.operation(),
            Some(
                wire::Operation::LoopIoctl
                    | wire::Operation::DeviceMapperIoctl
                    | wire::Operation::BlockIoctl
            )
        )
    {
        return Err(NamespaceError::Rejected(
            "apexd request is outside original x86-64 device ioctl ABI",
        ));
    }
    Ok(())
}

fn original_executable(root: &File) -> Result<File> {
    #[repr(C)]
    struct OpenHow {
        flags: u64,
        mode: u64,
        resolve: u64,
    }
    let how = OpenHow {
        flags: (libc::O_RDONLY | libc::O_CLOEXEC | libc::O_NOFOLLOW) as u64,
        mode: 0,
        // BENEATH | NO_SYMLINKS | NO_MAGICLINKS. Cross a held approved mount
        // if present, but never follow an arbitrary executable symlink.
        resolve: 0x08 | 0x04 | 0x02,
    };
    let raw = unsafe {
        libc::syscall(
            libc::SYS_openat2,
            root.as_raw_fd(),
            c"system/bin/apexd".as_ptr(),
            &how,
            std::mem::size_of::<OpenHow>(),
        )
    };
    if raw < 0 {
        return Err(io::Error::last_os_error().into());
    }
    Ok(unsafe { File::from_raw_fd(raw as i32) })
}

fn original_member_at(directory: &File, name: &std::ffi::CStr, flags: i32) -> Result<File> {
    let raw = unsafe {
        libc::openat(
            directory.as_raw_fd(),
            name.as_ptr(),
            flags | libc::O_NOFOLLOW | libc::O_CLOEXEC | libc::O_NONBLOCK,
        )
    };
    if raw < 0 {
        return Err(io::Error::last_os_error().into());
    }
    Ok(unsafe { File::from_raw_fd(raw) })
}

fn task_executable(proc: &File) -> Result<File> {
    // This exact proc magic link is intentionally followed from the already
    // held original thread proc inode, never from an external process path.
    let raw = unsafe {
        libc::openat(
            proc.as_raw_fd(),
            c"exe".as_ptr(),
            libc::O_RDONLY | libc::O_CLOEXEC,
        )
    };
    if raw < 0 {
        return Err(io::Error::last_os_error().into());
    }
    Ok(unsafe { File::from_raw_fd(raw) })
}

fn read_at_before(file: &File, buffer: &mut [u8], offset: u64, deadline: Instant) -> Result<usize> {
    loop {
        if Instant::now() >= deadline {
            return Err(NamespaceError::Rejected(
                "apexd read exceeded original request deadline",
            ));
        }
        match file.read_at(buffer, offset) {
            Ok(count) => {
                if Instant::now() >= deadline {
                    return Err(NamespaceError::Rejected(
                        "apexd read finished after original deadline",
                    ));
                }
                return Ok(count);
            }
            Err(error) if error.kind() == io::ErrorKind::Interrupted => continue,
            Err(error) => return Err(error.into()),
        }
    }
}

// The original CP3A /system/etc/init/apexd.rc (1334 B, SHA256
// 4baae395daa83df7a35debff152cd8cdedb3bf7b9d87abb5c4ebb9fdde6fabe6)
// declares normal apexd as user root, group system. AID_SYSTEM is 1000.
fn service_credentials(info: &PidfdInfo, uids: (u32, u32), gids: (u32, u32)) -> Result<()> {
    let uid = uids.0;
    let gid = gids
        .0
        .checked_add(1000)
        .filter(|x| inside(*x, gids))
        .ok_or(NamespaceError::Rejected(
            "apexd system group is outside original mapping",
        ))?;
    if !inside(uid, uids) {
        return Err(NamespaceError::Rejected(
            "apexd root is outside original mapping",
        ));
    }
    require_pidfd_creds(info, uid, gid)
        .map_err(|_| NamespaceError::Rejected("original apexd root/system credentials differ"))
}

fn normal_service_command(raw: &[u8]) -> Result<()> {
    if raw != b"/system/bin/apexd\0" {
        return Err(NamespaceError::Rejected(
            "apexd default actor is not the original normal service command",
        ));
    }
    Ok(())
}

fn executable_bytes(file: &File, expected: ExecutableIdentity, deadline: Instant) -> Result<()> {
    if expected.bytes != APEXD_BYTES || ExecutableIdentity::observe(file)? != expected {
        return Err(NamespaceError::Rejected(
            "original CP3A apexd size or identity differs",
        ));
    }
    let mut fs: libc::statvfs = unsafe { std::mem::zeroed() };
    if unsafe { libc::fstatvfs(file.as_raw_fd(), &mut fs) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    if fs.f_flag & libc::ST_RDONLY == 0 {
        return Err(NamespaceError::Rejected(
            "original apexd executable mount is writable",
        ));
    }
    let mut hash = Sha256::new();
    let mut offset = 0_u64;
    let mut buffer = [0_u8; 16 * 1024];
    while offset < APEXD_BYTES {
        if Instant::now() >= deadline {
            return Err(NamespaceError::Rejected(
                "apexd executable original request deadline",
            ));
        }
        let want = ((APEXD_BYTES - offset) as usize).min(buffer.len());
        let count = read_at_before(file, &mut buffer[..want], offset, deadline)?;
        if count == 0 {
            return Err(NamespaceError::Rejected("original apexd short executable"));
        }
        hash.update(&buffer[..count]);
        offset += count as u64;
    }
    let mut tail = [0_u8; 1];
    let digest: [u8; 32] = hash.finalize().into();
    if read_at_before(file, &mut tail, APEXD_BYTES, deadline)? != 0
        || digest != APEXD_SHA256
        || ExecutableIdentity::observe(file)? != expected
        || Instant::now() >= deadline
    {
        return Err(NamespaceError::Rejected(
            "actual original CP3A apexd executable bytes changed",
        ));
    }
    Ok(())
}

/// Stable equality dimensions for one exact apexd thread and approved epoch.
/// This private value owns no handles and cannot recreate or extend live authority.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct ActualApexdActorEpoch {
    original: Binding,
    identity: ProcessIdentity,
    tgid: u32,
    proc: Node,
    pidfd: Node,
    executable: ExecutableIdentity,
    default: DefaultMountBinding,
}

/// Full original-request equality, including the exact notification.
/// No public fields or constructor recreate a live task.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) struct ActualApexdGeneration {
    actor: ActualApexdActorEpoch,
    notification: wire::Notification,
}

impl ActualApexdGeneration {
    /// Structural comparison only: neither value proves a pending request,
    /// a current deadline or a retained kernel lease. In particular, a
    /// completed probe cannot be reused as authority for a later configure.
    pub(crate) fn same_actor_epoch(&self, other: &Self) -> bool {
        self.actor == other.actor
    }
}

/// A read-only identity issued by the same inherited pending-request owner.
/// This may be a nonleader apexd worker; it is never the original PID 1.
pub(crate) struct ActualApexdTask {
    scope: Rc<Scope>,
    notification: wire::Notification,
    listener: File,
    deadline: Instant,
    pidfd: OwnedFd,
    proc: File,
    identity: ProcessIdentity,
    tgid: u32,
    pidfd_node: Node,
    proc_node: Node,
    credentials: [u32; 8],
    cgroup: Vec<u8>,
    mount_namespace: File,
    mount_node: Node,
    root: File,
    root_node: Node,
    graph: mount_epoch::SuccessorGraph,
    executable: File,
    executable_identity: ExecutableIdentity,
    default_binding: DefaultMountBinding,
}

impl ActualApexdTask {
    pub(super) fn capture(
        scope: Rc<Scope>,
        listener: &File,
        notification: wire::Notification,
        deadline: Instant,
    ) -> Result<Self> {
        fixed_ioctl(&notification)?;
        let now = Instant::now();
        if now >= deadline
            || deadline.duration_since(now) > REQUEST_BUDGET
            || notification.pid == scope.binding.identity.pid
        {
            return Err(NamespaceError::Rejected(
                "apexd request is not a bounded actual descendant",
            ));
        }
        scope.check()?;
        scope.pending(listener, &notification)?;
        // No attach/seize or numeric-PID signal is performed. A fatal exit of
        // this candidate invalidates the same ID before any witness is issued.
        let raw = unsafe { libc::syscall(libc::SYS_pidfd_open, notification.pid, PIDFD_THREAD) };
        if raw < 0 {
            return Err(io::Error::last_os_error().into());
        }
        let pidfd = unsafe { OwnedFd::from_raw_fd(raw as i32) };
        if filesystem_kind_fd(pidfd.as_raw_fd())? != PIDFS_MAGIC {
            return Err(NamespaceError::Rejected(
                "apexd candidate is not an original thread PIDFD",
            ));
        }
        let info = pidfd_info(pidfd.as_raw_fd())?;
        if info.pid != notification.pid
            || info.tgid <= 1
            || info.tgid == scope.binding.identity.pid
            || info.ppid != scope.binding.identity.pid
        {
            return Err(NamespaceError::Rejected(
                "actual apexd thread is not an original mapped init child",
            ));
        }
        service_credentials(&info, scope.uids, scope.gids)?;
        let proc = open_proc_at(
            &scope.proc_root,
            &info.pid.to_string(),
            libc::O_RDONLY | libc::O_DIRECTORY,
        )?;
        let identity = read_identity(&proc, info.pid)?;
        if identity.parent != info.ppid {
            return Err(NamespaceError::Rejected("apexd PIDFD/proc parent differs"));
        }
        native_thread_status(&proc, identity, info.tgid, 0)?;
        normal_service_command(&read_proc(&proc, "cmdline")?)?;
        let cgroup = read_proc(&proc, "cgroup")?;
        payload_member(&cgroup, &scope.payload)?;
        let mount_namespace = from_pidfd(&pidfd, 0xff03, libc::CLONE_NEWNS)?;
        require_namespace_owner(&mount_namespace, scope.binding.user)?;
        let mount_node = Node::of(&mount_namespace)?;
        let root = namespace_root(&proc)?;
        let root_node = Node::of(&root)?;
        if mount_node != Node::of(&scope.default)? || root_node != Node::of(&scope.default_root)? {
            return Err(NamespaceError::Rejected(
                "apexd did not execute in the original default namespace/root",
            ));
        }
        let graph = mount_epoch::SuccessorGraph::observe(&proc, &root)?;
        let default_binding = scope.defaults.apexd_binding(mount_node, &graph)?;
        let executable = original_executable(&root)?;
        let executable_identity = ExecutableIdentity::observe(&executable)?;
        executable_bytes(&executable, executable_identity, deadline)?;
        if ExecutableIdentity::observe(&task_executable(&proc)?)? != executable_identity {
            return Err(NamespaceError::Rejected(
                "actual thread did not execute original CP3A apexd",
            ));
        }
        scope.pending(listener, &notification)?;
        let value = Self {
            scope,
            notification,
            listener: listener.try_clone()?,
            deadline,
            pidfd_node: fd_node(pidfd.as_raw_fd())?,
            pidfd,
            proc_node: Node::of(&proc)?,
            proc,
            identity,
            tgid: info.tgid,
            credentials: credentials(&info),
            cgroup,
            mount_namespace,
            mount_node,
            root,
            root_node,
            graph,
            executable,
            executable_identity,
            default_binding,
        };
        value.revalidate_kernel()?;
        Ok(value)
    }

    /// Actual kernel/owner/executable/complete approved graph checks only.
    /// Never call MacApexdTaskWitness from here; that observer calls this method.
    pub(crate) fn revalidate_kernel(&self) -> Result<()> {
        if Instant::now() >= self.deadline {
            return Err(NamespaceError::Rejected(
                "original apexd request deadline expired",
            ));
        }
        self.scope.check()?;
        self.scope.pending(&self.listener, &self.notification)?;
        if fd_node(self.pidfd.as_raw_fd())? != self.pidfd_node
            || filesystem_kind_fd(self.pidfd.as_raw_fd())? != PIDFS_MAGIC
            || Node::of(&self.proc)? != self.proc_node
            || read_identity(&self.proc, self.identity.pid)? != self.identity
            || pidfd_exited(&self.pidfd)?
        {
            return Err(NamespaceError::Rejected(
                "original apexd thread generation changed",
            ));
        }
        let info = pidfd_info(self.pidfd.as_raw_fd())?;
        service_credentials(&info, self.scope.uids, self.scope.gids)?;
        if info.pid != self.identity.pid
            || info.tgid != self.tgid
            || info.ppid != self.identity.parent
            || info.ppid != self.scope.binding.identity.pid
            || credentials(&info) != self.credentials
            || read_proc(&self.proc, "cgroup")? != self.cgroup
            || read_proc(&self.proc, "uid_map")? != self.scope.uid_map
            || read_proc(&self.proc, "gid_map")? != self.scope.gid_map
        {
            return Err(NamespaceError::Rejected(
                "apexd actual credentials, parent or payload changed",
            ));
        }
        native_thread_status(&self.proc, self.identity, self.tgid, 0)?;
        normal_service_command(&read_proc(&self.proc, "cmdline")?)?;
        payload_member(&self.cgroup, &self.scope.payload)?;
        if Node::of(&from_pidfd(&self.pidfd, 0xff09, libc::CLONE_NEWUSER)?)?
            != self.scope.binding.user
        {
            return Err(NamespaceError::Rejected(
                "apexd left original user namespace",
            ));
        }
        for (kind, command, _, original) in &self.scope.namespaces {
            let observed = from_pidfd(&self.pidfd, *command, *kind)?;
            require_namespace_owner(&observed, self.scope.binding.user)?;
            let expected = if *kind == libc::CLONE_NEWNS {
                self.mount_node
            } else {
                *original
            };
            if Node::of(&observed)? != expected {
                return Err(NamespaceError::Rejected(
                    "apexd current namespace is outside original owner",
                ));
            }
        }
        if Node::of(&self.mount_namespace)? != self.mount_node
            || Node::of(&self.root)? != self.root_node
        {
            return Err(NamespaceError::Rejected(
                "apexd held namespace/root changed",
            ));
        }
        let root = namespace_root(&self.proc)?;
        if Node::of(&root)? != self.root_node {
            return Err(NamespaceError::Rejected("apexd current root changed"));
        }
        let graph = mount_epoch::SuccessorGraph::observe(&self.proc, &root)?;
        self.graph.same_observation(&graph)?;
        if self.scope.defaults.apexd_binding(self.mount_node, &graph)? != self.default_binding {
            return Err(NamespaceError::Rejected(
                "apexd full default graph or issued epoch changed",
            ));
        }
        let named = original_executable(&root)?;
        let executed = task_executable(&self.proc)?;
        if ExecutableIdentity::observe(&named)? != self.executable_identity
            || ExecutableIdentity::observe(&executed)? != self.executable_identity
        {
            return Err(NamespaceError::Rejected(
                "actual apexd executable or original named source changed",
            ));
        }
        executable_bytes(&self.executable, self.executable_identity, self.deadline)?;
        self.graph.matches(&self.proc, &root)?;
        self.scope.pending(&self.listener, &self.notification)?;
        if pidfd_info(self.pidfd.as_raw_fd())?.pid != self.identity.pid
            || Instant::now() >= self.deadline
        {
            return Err(NamespaceError::Rejected(
                "apexd final original task/deadline changed",
            ));
        }
        Ok(())
    }

    pub(crate) fn pidfd(&self) -> BorrowedFd<'_> {
        self.pidfd.as_fd()
    }
    pub(crate) fn proc_directory(&self) -> &File {
        &self.proc
    }
    pub(crate) fn selection(&self) -> Result<&ProductionSelection> {
        self.scope
            .context
            .objects()
            .map(|(_, selection)| selection)
            .map_err(|e| NamespaceError::RuntimeResource(e.to_string()))
    }
    pub(crate) fn require_owner(&self, owner: &RuntimeMacOwner) -> Result<()> {
        let (mac, selection) = owner
            .objects()
            .map_err(|e| NamespaceError::RuntimeResource(e.to_string()))?;
        self.scope
            .context
            .require_pair(mac, selection)
            .map_err(|e| NamespaceError::RuntimeResource(e.to_string()))?;
        self.scope.check_custody()
    }
    pub(crate) fn generation(&self) -> Result<ActualApexdGeneration> {
        self.revalidate_kernel()?;
        Ok(ActualApexdGeneration {
            actor: ActualApexdActorEpoch {
                original: self.scope.binding,
                identity: self.identity,
                tgid: self.tgid,
                proc: self.proc_node,
                pidfd: self.pidfd_node,
                executable: self.executable_identity,
                default: self.default_binding,
            },
            notification: self.notification,
        })
    }

    /// Read-only source custody from the same admitted system, not permission
    /// to execute as init or to configure/export a block device.
    pub(in super::super::super) fn original_compressed_apex(
        &self,
        bases: &crate::production_mounts::PreparedMounts,
        witness: &super::super::super::OwnedNamespaceWitness<'_>,
        index: usize,
    ) -> Result<File> {
        self.revalidate_kernel()?;
        witness.revalidate()?;
        if Node::of(witness.user_namespace())? != self.scope.binding.user {
            return Err(NamespaceError::Rejected(
                "original apexd system input belongs to another namespace owner",
            ));
        }
        let fixed = crate::production_execution_profile::apex_inputs::original_compressed(index)
            .map_err(NamespaceError::Rejected)?;
        let original = bases
            .original_compressed_apex(witness, index)
            .map_err(|e| NamespaceError::MountResource(e.to_string()))?;
        let system = original_member_at(&self.root, c"system", libc::O_RDONLY | libc::O_DIRECTORY)?;
        let apex = original_member_at(&system, c"apex", libc::O_RDONLY | libc::O_DIRECTORY)?;
        let name = std::ffi::CString::new(fixed.input.container_file)
            .map_err(|_| NamespaceError::Rejected("compiled original CAPEX basename"))?;
        let probe = original_member_at(&apex, &name, libc::O_PATH)?;
        witness
            .identity_lease()?
            .broker_reject_backing_body(&probe)?;
        if !probe.metadata()?.is_file() || Node::of(&probe)? != Node::of(&original)? {
            return Err(NamespaceError::Rejected(
                "actual apexd system input differs from the admitted original inode",
            ));
        }
        let source = original_member_at(&apex, &name, libc::O_RDONLY)?;
        witness
            .identity_lease()?
            .broker_reject_backing_body(&source)?;
        let mut fs: libc::statvfs = unsafe { std::mem::zeroed() };
        if unsafe { libc::fstatvfs(source.as_raw_fd(), &mut fs) } != 0 {
            return Err(io::Error::last_os_error().into());
        }
        if Node::of(&source)? != Node::of(&original)?
            || mount_id(&source)? != mount_id(&system)?
            || mount_id(&apex)? != mount_id(&system)?
            || fs.f_flag & libc::ST_RDONLY == 0
            || source.metadata()?.len() != fixed.input.container_bytes
        {
            return Err(NamespaceError::Rejected(
                "actual apexd CAPEX system mount or member changed",
            ));
        }
        witness.revalidate()?;
        self.revalidate_kernel()?;
        Ok(source)
    }

    pub(in super::super::super) fn original_context(&self) -> Result<RuntimeMacOwner> {
        self.revalidate_kernel()?;
        Ok(self.scope.context.clone())
    }
    pub(in super::super::super) fn default_binding(&self) -> Result<DefaultMountBinding> {
        self.revalidate_kernel()?;
        Ok(self.default_binding)
    }
    pub(in super::super::super) fn require_request(
        &self,
        n: &wire::Notification,
        deadline: Instant,
    ) -> Result<()> {
        if n != &self.notification || deadline != self.deadline {
            return Err(NamespaceError::Rejected(
                "apexd task belongs to a different original request",
            ));
        }
        self.revalidate_kernel()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn actor_epoch_node(inode: u64) -> Node {
        Node { device: 7, inode }
    }

    // Values for equality tests only. No live task, descriptor, request owner,
    // kernel lease or target issuer can be created from these private values.
    fn actor_epoch_generation() -> ActualApexdGeneration {
        let original = Binding {
            identity: ProcessIdentity {
                pid: 17,
                parent: 1,
                start_ticks: 100,
            },
            proc: actor_epoch_node(1),
            pidfd: actor_epoch_node(2),
            user: actor_epoch_node(3),
            pid_namespace: actor_epoch_node(4),
            creator_tid: 23,
            nonce: [0x19; 16],
        };
        ActualApexdGeneration {
            actor: ActualApexdActorEpoch {
                original,
                identity: ProcessIdentity {
                    pid: 42,
                    parent: 17,
                    start_ticks: 200,
                },
                tgid: 40,
                proc: actor_epoch_node(7),
                pidfd: actor_epoch_node(8),
                executable: ExecutableIdentity {
                    node: actor_epoch_node(9),
                    mount: 2,
                    mode: 0o100755,
                    uid: 200000,
                    gid: 301000,
                    links: 1,
                    bytes: APEXD_BYTES,
                    mtime: (10, 20),
                    ctime: (10, 30),
                },
                default: DefaultMountBinding::from_test_parts(
                    original,
                    actor_epoch_node(10),
                    7,
                    11,
                ),
            },
            notification: wire::Notification {
                id: 19,
                pid: 42,
                flags: 0,
                data: wire::Data {
                    nr: libc::SYS_ioctl as i32,
                    arch: ARCH_X86_64,
                    instruction_pointer: 0x1000,
                    args: [7, 0x4c0a, 0x2000, 0, 0, 0],
                },
            },
        }
    }

    #[test]
    fn actual_apexd_actor_epoch_distinguishes_structural_actor_from_exact_request() {
        let probe = actor_epoch_generation();
        let mut next = probe;
        next.notification.id += 1;
        next.notification.data.args[2] = 0x3000;
        fixed_ioctl(&probe.notification).unwrap();
        fixed_ioctl(&next.notification).unwrap();
        assert!(probe.same_actor_epoch(&next));
        assert!(next.same_actor_epoch(&probe));
        assert_ne!(probe, next);
        assert_eq!(probe, probe);

        let changes: [fn(&mut wire::Notification); 12] = [
            |n| n.id += 1,
            |n| n.pid += 1,
            |n| n.flags = 1,
            |n| n.data.nr = libc::SYS_mount as i32,
            |n| n.data.arch ^= 1,
            |n| n.data.instruction_pointer += 1,
            |n| n.data.args[0] += 1,
            |n| n.data.args[1] += 1,
            |n| n.data.args[2] += 1,
            |n| n.data.args[3] += 1,
            |n| n.data.args[4] += 1,
            |n| n.data.args[5] += 1,
        ];
        for change in changes {
            let mut changed = probe;
            change(&mut changed.notification);
            assert!(probe.same_actor_epoch(&changed));
            assert_ne!(probe, changed, "full request equality lost a wire field");
        }
    }

    #[test]
    fn actual_apexd_actor_epoch_keeps_all_original_owner_and_task_dimensions() {
        let original = actor_epoch_generation();
        let changes: [fn(&mut ActualApexdActorEpoch); 28] = [
            |a| a.original.identity.pid += 1,
            |a| a.original.identity.parent += 1,
            |a| a.original.identity.start_ticks += 1,
            |a| a.original.proc.inode += 1,
            |a| a.original.pidfd.inode += 1,
            |a| a.original.user.inode += 1,
            |a| a.original.pid_namespace.inode += 1,
            |a| a.original.creator_tid += 1,
            |a| a.original.nonce[0] ^= 1,
            |a| a.identity.pid += 1,
            |a| a.identity.parent += 1,
            |a| a.identity.start_ticks += 1,
            |a| a.tgid += 1,
            |a| a.proc.inode += 1,
            |a| a.proc.device += 1,
            |a| a.pidfd.inode += 1,
            |a| a.pidfd.device += 1,
            |a| a.executable.node.inode += 1,
            |a| a.executable.node.device += 1,
            |a| a.executable.mount += 1,
            |a| a.executable.mode ^= 1,
            |a| a.executable.uid += 1,
            |a| a.executable.gid += 1,
            |a| a.executable.links += 1,
            |a| a.executable.bytes += 1,
            |a| a.executable.mtime.0 += 1,
            |a| a.executable.mtime.1 += 1,
            |a| a.executable.ctime.1 += 1,
        ];
        for change in changes {
            let mut changed = original;
            change(&mut changed.actor);
            assert_eq!(original.notification, changed.notification);
            assert!(!original.same_actor_epoch(&changed));
            assert_ne!(original, changed);
        }
    }

    #[test]
    fn actual_apexd_actor_epoch_keeps_default_owner_graph_and_epoch() {
        let original = actor_epoch_generation();
        let owner = original.actor.original;
        let mut other_owner = owner;
        other_owner.nonce[0] ^= 1;
        for default in [
            DefaultMountBinding::from_test_parts(other_owner, actor_epoch_node(10), 7, 11),
            DefaultMountBinding::from_test_parts(owner, actor_epoch_node(12), 7, 11),
            DefaultMountBinding::from_test_parts(owner, actor_epoch_node(10), 8, 11),
            DefaultMountBinding::from_test_parts(owner, actor_epoch_node(10), 7, 12),
        ] {
            let mut changed = original;
            changed.actor.default = default;
            assert_eq!(original.notification, changed.notification);
            assert!(!original.same_actor_epoch(&changed));
            assert_ne!(original, changed);
        }
    }

    #[test]
    fn actual_apexd_actor_epoch_does_not_merge_threads_or_validate_stale_requests() {
        let original = actor_epoch_generation();
        let mut other_thread = original;
        other_thread.actor.identity.pid += 1;
        other_thread.actor.identity.start_ticks += 1;
        other_thread.actor.proc.inode += 1;
        other_thread.actor.pidfd.inode += 1;
        assert_eq!(original.actor.tgid, other_thread.actor.tgid);
        assert!(!original.same_actor_epoch(&other_thread));

        // Equality of historical values says nothing about pending liveness.
        // These invalid notifications still fail the unchanged ABI validator;
        // the actual task also retains its pending-ID and deadline checks.
        for invalid in [0_u64, 1] {
            let mut request = original;
            if invalid == 0 {
                request.notification.id = 0;
            } else {
                request.notification.flags = 1;
            }
            assert!(original.same_actor_epoch(&request));
            assert_ne!(original, request);
            assert!(fixed_ioctl(&request.notification).is_err());
        }
    }

    #[test]
    fn actual_apexd_identity_requires_exact_device_ioctl_notification_abi() {
        let n = wire::Notification {
            id: 19,
            pid: 42,
            flags: 0,
            data: wire::Data {
                nr: libc::SYS_ioctl as i32,
                arch: ARCH_X86_64,
                instruction_pointer: 0x1000,
                args: [7, 0x4c0a, 0x2000, 0, 0, 0],
            },
        };
        fixed_ioctl(&n).unwrap();
        for bad in [0, 1] {
            let mut x = n;
            x.pid = bad;
            assert!(fixed_ioctl(&x).is_err());
        }
        let mut x = n;
        x.id = 0;
        assert!(fixed_ioctl(&x).is_err());
        let mut x = n;
        x.data.nr = libc::SYS_mount as i32;
        assert!(fixed_ioctl(&x).is_err());
        let mut x = n;
        x.data.args[0] = u64::MAX;
        assert!(fixed_ioctl(&x).is_err());
        let mut x = n;
        x.data.args[1] |= 1 << 32;
        assert!(fixed_ioctl(&x).is_err());
        let mut x = n;
        x.data.arch = 0x40000003;
        assert!(fixed_ioctl(&x).is_err());
        let mut x = n;
        x.flags = 1;
        assert!(fixed_ioctl(&x).is_err());
    }
    #[test]
    fn actual_apexd_executable_rejects_regular_mutation_and_non_cp3a_bytes() {
        use std::io::Write;
        use std::os::unix::fs::PermissionsExt;
        let mut file = tempfile::tempfile().unwrap();
        file.write_all(b"not original CP3A apexd").unwrap();
        file.set_permissions(std::fs::Permissions::from_mode(0o755))
            .unwrap();
        let before = ExecutableIdentity::observe(&file).unwrap();
        assert!(executable_bytes(&file, before, Instant::now() + Duration::from_secs(1)).is_err());
        file.write_all(b"changed").unwrap();
        assert_ne!(ExecutableIdentity::observe(&file).unwrap(), before);
        assert!(executable_bytes(&file, before, Instant::now() + Duration::from_secs(1)).is_err());
        file.set_permissions(std::fs::Permissions::from_mode(0o6755))
            .unwrap();
        assert!(ExecutableIdentity::observe(&file).is_err());
    }
    #[test]
    fn actual_apexd_service_rejects_other_valid_subordinate_uid_and_gid_slots() {
        let uid = 200000;
        let gid = 301000;
        let original = || PidfdInfo {
            ruid: uid,
            euid: uid,
            suid: uid,
            fsuid: uid,
            rgid: gid,
            egid: gid,
            sgid: gid,
            fsgid: gid,
            ..PidfdInfo::default()
        };
        let mut info = original();
        service_credentials(&info, (200000, 265536), (300000, 365536)).unwrap();
        for index in 0..8 {
            let mut bad = original();
            match index {
                0 => bad.ruid += 1,
                1 => bad.euid += 1,
                2 => bad.suid += 1,
                3 => bad.fsuid += 1,
                4 => bad.rgid += 1,
                5 => bad.egid += 1,
                6 => bad.sgid += 1,
                _ => bad.fsgid += 1,
            }
            assert!(service_credentials(&bad, (200000, 265536), (300000, 365536)).is_err());
        }
        info.ruid = 201000;
        info.euid = 201000;
        info.suid = 201000;
        info.fsuid = 201000;
        assert!(service_credentials(&info, (200000, 265536), (300000, 365536)).is_err());
        info = original();
        info.rgid = 300000;
        info.egid = 300000;
        info.sgid = 300000;
        info.fsgid = 300000;
        assert!(service_credentials(&info, (200000, 265536), (300000, 365536)).is_err());
        assert!(service_credentials(&info, (200000, 200000), (300000, 365536)).is_err());
        assert!(service_credentials(&info, (200000, 265536), (300000, 301000)).is_err());
        assert!(service_credentials(&info, (200000, 265536), (u32::MAX - 999, u32::MAX)).is_err());
    }

    #[test]
    fn actual_apexd_default_command_rejects_bootstrap_snapshot_and_extra_arguments() {
        normal_service_command(b"/system/bin/apexd\0").unwrap();
        for bad in [
            b"/system/bin/apexd\0--bootstrap\0".as_slice(),
            b"/system/bin/apexd\0--snapshotde\0",
            b"/system/bin/apexd\0\0",
            b"/system/bin/apexd",
            b"apexd\0",
            b"/system/bin/apexd-copy\0",
        ] {
            assert!(normal_service_command(bad).is_err());
        }
    }

    #[test]
    fn actual_apexd_bounded_read_keeps_original_fd_eof_and_expired_deadline() {
        let file = tempfile::tempfile().unwrap();
        file.write_all_at(b"actual", 0).unwrap();
        let mut bytes = [0_u8; 6];
        assert_eq!(
            read_at_before(
                &file,
                &mut bytes,
                0,
                Instant::now() + Duration::from_secs(1)
            )
            .unwrap(),
            6
        );
        assert_eq!(&bytes, b"actual");
        assert_eq!(
            read_at_before(
                &file,
                &mut bytes,
                6,
                Instant::now() + Duration::from_secs(1)
            )
            .unwrap(),
            0
        );
        assert!(read_at_before(&file, &mut bytes, 0, Instant::now()).is_err());
    }
}
