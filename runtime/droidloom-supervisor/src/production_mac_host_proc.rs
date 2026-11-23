//! Detached, read-only host procfs with an explicit SELinux context provider.
//! Creation stays in the original initial user/PID namespaces. Foreign reads
//! accept only original typed init/helper or manager/observer owners; no supplied
//! PID, path, prior receipt or caller-chosen role can issue a read. A loader
//! view is distinct from the original broker view and grants no broker role.
use super::*;

const NSFS_MAGIC: u64 = 0x6e73_6673;
const PIDFS_MAGIC: u64 = 0x5049_4446;
const NS_GET_NSTYPE: libc::c_ulong = 0xb703;
const NS_GET_ID: libc::c_ulong = 0x8008_b70d;
const PIDFD_GET_INFO: libc::c_ulong = 0xc048_ff0b;
const PIDFD_THREAD: u32 = 0x80;
const MOUNTINFO_MAX: usize = 16 * 1024 * 1024;

#[repr(C)]
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct PidfdInfo {
    mask: u64,
    cgroup: u64,
    pid: u32,
    tgid: u32,
    ppid: u32,
    ruid: u32,
    rgid: u32,
    euid: u32,
    egid: u32,
    suid: u32,
    sgid: u32,
    fsuid: u32,
    fsgid: u32,
    exit_code: i32,
    coredump: u32,
    spare: u32,
}
const _: () =
    assert!(std::mem::size_of::<PidfdInfo>() == 72 && std::mem::align_of::<PidfdInfo>() == 8);

fn file(rc: libc::c_long) -> Result<File> {
    if rc < 0 {
        return Err(io::Error::last_os_error().into());
    }
    let fd = i32::try_from(rc).map_err(|_| MacError::Rejected("host proc descriptor overflow"))?;
    Ok(unsafe { File::from_raw_fd(fd) })
}
fn success(rc: libc::c_long) -> Result<()> {
    if rc == 0 {
        Ok(())
    } else {
        Err(io::Error::last_os_error().into())
    }
}
fn alive(fd: BorrowedFd<'_>) -> Result<()> {
    let mut p = libc::pollfd {
        fd: fd.as_raw_fd(),
        events: libc::POLLIN,
        revents: 0,
    };
    let rc = unsafe { libc::poll(&mut p, 1, 0) };
    if rc < 0 {
        return Err(io::Error::last_os_error().into());
    }
    require(rc == 0 && p.revents == 0, "original PIDFD must remain live")
}
fn pidfd_info(fd: BorrowedFd<'_>) -> Result<PidfdInfo> {
    alive(fd)?;
    let before = descriptor_identity(fd)?;
    let mut fs: libc::statfs = unsafe { std::mem::zeroed() };
    success(unsafe { libc::fstatfs(fd.as_raw_fd(), &mut fs) } as libc::c_long)?;
    require(
        fs.f_type as u64 == PIDFS_MAGIC,
        "original kernel pidfs descriptor required",
    )?;
    let mut value: PidfdInfo = unsafe { std::mem::zeroed() };
    value.mask = 3;
    success(unsafe { libc::ioctl(fd.as_raw_fd(), PIDFD_GET_INFO, &mut value) } as libc::c_long)?;
    require(
        value.mask & 3 == 3
            && value.mask & !7 == 0
            && value.pid > 0
            && value.tgid > 0
            && value.exit_code == 0
            && value.coredump == 0
            && value.spare == 0,
        "complete live PIDFD info with no terminal state",
    )?;
    require(
        descriptor_identity(fd)? == before,
        "original PIDFD inode changed",
    )?;
    alive(fd)?;
    Ok(value)
}
fn canonical(bytes: &[u8], zero: bool) -> Result<u64> {
    require(
        !bytes.is_empty()
            && bytes.len() <= 20
            && bytes.iter().all(u8::is_ascii_digit)
            && (bytes.len() == 1 || bytes[0] != b'0'),
        "canonical bounded proc integer",
    )?;
    let value = std::str::from_utf8(bytes)
        .map_err(|_| MacError::Rejected("proc integer encoding"))?
        .parse::<u64>()
        .map_err(|_| MacError::Rejected("proc integer overflow"))?;
    require(zero || value > 0, "positive proc identity integer")?;
    Ok(value)
}
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct Process {
    pid: u32,
    tgid: u32,
    parent: u32,
    start: u64,
}

/// This is an equality record, not a constructor for an apexd task. Only the
/// typed thread observer below can issue it after actual cross-view reads.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(super) struct ApexdThreadBinding {
    original_proc: Node,
    pidfd: DescriptorIdentity,
    info: PidfdInfo,
    process: Process,
    namespaces: [ApexdNamespaceBinding; 7],
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct ApexdNamespaceBinding {
    kind: i32,
    node: Node,
    id: u64,
}

fn apexd_process_matches_pidfd(process: Process, info: PidfdInfo) -> Result<()> {
    require(
        process.pid > 0
            && process.tgid > 0
            && process.start > 0
            && (process.pid, process.tgid, process.parent) == (info.pid, info.tgid, info.ppid),
        "original apexd thread PIDFD must match its TID, TGID, PPID and live start time",
    )
}

fn same_apexd_namespaces(original: &File, selected: &File) -> Result<[ApexdNamespaceBinding; 7]> {
    let mut result = Vec::with_capacity(7);
    for (name, kind) in [
        (c"user", libc::CLONE_NEWUSER),
        (c"pid", libc::CLONE_NEWPID),
        (c"mnt", libc::CLONE_NEWNS),
        (c"net", libc::CLONE_NEWNET),
        (c"ipc", libc::CLONE_NEWIPC),
        (c"uts", libc::CLONE_NEWUTS),
        (c"cgroup", libc::CLONE_NEWCGROUP),
    ] {
        let (a, an, aid) = namespace(original, name, kind)?;
        let (b, bn, bid) = namespace(selected, name, kind)?;
        require(
            an == bn && aid == bid && Node::of(&a)? == an && Node::of(&b)? == bn,
            "selected apexd thread view must retain every original fixed namespace identity",
        )?;
        result.push(ApexdNamespaceBinding {
            kind,
            node: an,
            id: aid,
        });
    }
    result
        .try_into()
        .map_err(|_| MacError::Rejected("complete fixed apexd namespace identity set"))
}

fn stat_identity(raw: &[u8]) -> Result<(u32, u32, u64)> {
    require(
        !raw.is_empty()
            && raw.len() <= 65536
            && raw.ends_with(b"\n")
            && !raw[..raw.len() - 1].contains(&b'\n'),
        "complete bounded proc stat record",
    )?;
    let start = raw
        .windows(2)
        .position(|w| w == b" (")
        .ok_or(MacError::Rejected("proc stat command start"))?;
    let end = raw
        .iter()
        .rposition(|b| *b == b')')
        .ok_or(MacError::Rejected("proc stat command end"))?;
    require(
        end > start + 1 && raw.get(end + 1) == Some(&b' '),
        "complete proc stat command",
    )?;
    let pid = u32::try_from(canonical(&raw[..start], false)?)
        .map_err(|_| MacError::Rejected("proc PID overflow"))?;
    let tail = &raw[end + 2..raw.len() - 1];
    let parts: Vec<_> = tail
        .split(|b| b.is_ascii_whitespace())
        .filter(|p| !p.is_empty())
        .collect();
    require(
        (50..=64).contains(&parts.len())
            && parts[0].len() == 1
            && b"RSDTtWIP".contains(&parts[0][0]),
        "complete live proc stat fields",
    )?;
    let parent = u32::try_from(canonical(parts[1], true)?)
        .map_err(|_| MacError::Rejected("proc parent overflow"))?;
    Ok((pid, parent, canonical(parts[19], false)?))
}
fn status_number(raw: &[u8], key: &[u8]) -> Result<u32> {
    require(
        !raw.is_empty() && raw.len() <= 65536 && raw.ends_with(b"\n"),
        "complete bounded proc status",
    )?;
    let mut values = raw
        .split(|b| *b == b'\n')
        .filter_map(|line| line.strip_prefix(key));
    let value = values
        .next()
        .ok_or(MacError::Rejected("required proc status field absent"))?;
    require(
        values.next().is_none(),
        "duplicate proc status identity field",
    )?;
    let parts: Vec<_> = value
        .split(|b| b.is_ascii_whitespace())
        .filter(|p| !p.is_empty())
        .collect();
    require(parts.len() == 1, "one exact proc status identity integer")?;
    u32::try_from(canonical(parts[0], true)?)
        .map_err(|_| MacError::Rejected("proc status identity overflow"))
}
fn proc_read(directory: &File, name: &CStr) -> Result<Vec<u8>> {
    require(
        kind(directory)? == PROC_MAGIC,
        "actual held process procfs required",
    )?;
    let opened = open_at(directory.as_raw_fd(), name, libc::O_RDONLY)?;
    require(
        kind(&opened)? == PROC_MAGIC && Node::of(&opened)?.mode & libc::S_IFMT == libc::S_IFREG,
        "fixed actual proc regular file",
    )?;
    bounded(&opened, 65536)
}
fn process(directory: &File) -> Result<Process> {
    let before = Node::of(directory)?;
    require(
        before.mode & libc::S_IFMT == libc::S_IFDIR && kind(directory)? == PROC_MAGIC,
        "actual original proc directory",
    )?;
    let first = stat_identity(&proc_read(directory, c"stat")?)?;
    let status = proc_read(directory, c"status")?;
    let result = Process {
        pid: status_number(&status, b"Pid:")?,
        tgid: status_number(&status, b"Tgid:")?,
        parent: status_number(&status, b"PPid:")?,
        start: first.2,
    };
    require(
        (result.pid, result.parent, result.start) == first
            && stat_identity(&proc_read(directory, c"stat")?)? == first
            && Node::of(directory)? == before,
        "stable actual PID, parent, start time and original proc inode",
    )?;
    Ok(result)
}
fn namespace(directory: &File, name: &CStr, expected_kind: i32) -> Result<(File, Node, u64)> {
    let ns = open_at(
        directory.as_raw_fd(),
        c"ns",
        libc::O_PATH | libc::O_DIRECTORY,
    )?;
    require(
        kind(&ns)? == PROC_MAGIC,
        "actual fixed proc namespace directory",
    )?;
    // Only fixed kernel namespace magic links from the sealed call sites below
    // are intentionally followed; no caller-provided namespace name is accepted.
    let f = file(unsafe {
        libc::openat(
            ns.as_raw_fd(),
            name.as_ptr(),
            libc::O_RDONLY | libc::O_CLOEXEC,
        )
    } as libc::c_long)?;
    require(
        kind(&f)? == NSFS_MAGIC,
        "actual kernel namespace descriptor",
    )?;
    let node = Node::of(&f)?;
    let nstype = unsafe { libc::ioctl(f.as_raw_fd(), NS_GET_NSTYPE, 0 as libc::c_ulong) };
    if nstype < 0 {
        return Err(io::Error::last_os_error().into());
    }
    let mut id = 0_u64;
    success(unsafe { libc::ioctl(f.as_raw_fd(), NS_GET_ID, &mut id) } as libc::c_long)?;
    require(
        nstype == expected_kind && id != 0 && Node::of(&f)? == node,
        "fixed actual namespace type and identity",
    )?;
    Ok((f, node, id))
}
fn same_namespaces(original: &File, view: &File) -> Result<()> {
    for (name, kind) in [(c"user", libc::CLONE_NEWUSER), (c"pid", libc::CLONE_NEWPID)] {
        let (a, an, aid) = namespace(original, name, kind)?;
        let (b, bn, bid) = namespace(view, name, kind)?;
        require(
            an == bn && aid == bid && Node::of(&a)? == an && Node::of(&b)? == bn,
            "new proc view must name the same original user/PID namespaces",
        )?;
    }
    Ok(())
}
fn mount_id(f: &File) -> Result<u64> {
    let mut value: libc::statx = unsafe { std::mem::zeroed() };
    success(unsafe {
        libc::syscall(
            libc::SYS_statx,
            f.as_raw_fd(),
            c"".as_ptr(),
            libc::AT_EMPTY_PATH,
            0x1000_u32,
            &mut value,
        )
    })?;
    require(
        value.stx_mask & 0x1000 != 0 && value.stx_mnt_id != 0,
        "actual held proc mount ID",
    )?;
    Ok(value.stx_mnt_id)
}
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct Volume {
    dev: u64,
    ino: u64,
    mode: u32,
    uid: u32,
    gid: u32,
    mount: u64,
    fsid: [u8; 8],
}
fn volume(root: &File) -> Result<Volume> {
    let n = Node::of(root)?;
    let mut fs: libc::statfs = unsafe { std::mem::zeroed() };
    success(unsafe { libc::fstatfs(root.as_raw_fd(), &mut fs) } as libc::c_long)?;
    let mut v: libc::statvfs = unsafe { std::mem::zeroed() };
    success(unsafe { libc::fstatvfs(root.as_raw_fd(), &mut v) } as libc::c_long)?;
    require(
        fs.f_type as u64 == PROC_MAGIC
            && n.mode == libc::S_IFDIR | 0o555
            && n.uid == 0
            && n.gid == 0
            && v.f_flag & 15 == 15,
        "actual readonly nosuid nodev noexec root proc view",
    )?;
    const _: () = assert!(std::mem::size_of::<libc::fsid_t>() == 8);
    let fsid = unsafe { std::mem::transmute::<libc::fsid_t, [u8; 8]>(fs.f_fsid) };
    Ok(Volume {
        dev: n.dev,
        ino: n.ino,
        mode: n.mode,
        uid: n.uid,
        gid: n.gid,
        mount: mount_id(root)?,
        fsid,
    })
}
fn absent_mount(bytes: &[u8], mount: u64) -> Result<()> {
    require(
        !bytes.is_empty() && bytes.len() <= MOUNTINFO_MAX && bytes.ends_with(b"\n"),
        "complete bounded original host mount inventory",
    )?;
    let text = std::str::from_utf8(bytes)
        .map_err(|_| MacError::Rejected("host mount inventory encoding"))?;
    let mut seen = BTreeSet::new();
    for line in text.lines() {
        let fields: Vec<_> = line.split_ascii_whitespace().collect();
        require(
            fields.len() >= 10 && fields.iter().filter(|x| **x == "-").count() == 1,
            "complete host mount inventory row",
        )?;
        let id = canonical(fields[0].as_bytes(), false)?;
        require(
            id != mount && seen.insert(id),
            "host selected proc must stay detached; mount IDs must be unique",
        )?;
    }
    Ok(())
}
fn detached(loaded: &LoadedPolicyWitness, id: u64) -> Result<()> {
    let file = open_at(loaded.own_proc.as_raw_fd(), c"mountinfo", libc::O_RDONLY)?;
    require(
        kind(&file)? == PROC_MAGIC,
        "original caller mount inventory from procfs",
    )?;
    absent_mount(&bounded(&file, MOUNTINFO_MAX)?, id)
}
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum ViewRole {
    Broker,
    Loader,
    Helper,
}
impl ViewRole {
    fn context(self) -> &'static str {
        match self {
            Self::Broker => BROKER,
            Self::Loader => LOADER,
            Self::Helper => HOST,
        }
    }
    fn apparmor(self) -> &'static [u8] {
        match self {
            Self::Broker => AA_BROKER,
            Self::Loader => AA_LOADER,
            Self::Helper => b"unconfined\n",
        }
    }
}
fn fixed_view_identity(role: ViewRole, selinux: &[u8], apparmor: &[u8]) -> Result<()> {
    require(
        context_matches(selinux, role.context()) && apparmor == role.apparmor(),
        "selected proc creator must retain both exact role identities",
    )
}
fn actor(
    loaded: &LoadedPolicyWitness,
    selection: &ProductionSelection,
    role: ViewRole,
) -> Result<()> {
    loaded.revalidate(selection)?;
    fixed_view_identity(
        role,
        &self_attr::selinux_current()?,
        &proc_attr(&loaded.own_proc, true)?,
    )?;
    self_attr::require_no_fscreate()?;
    loaded.stable_epoch()
}
/// A privately created representation view. Its descriptors are never exported
/// to a guest or caller and it is never grafted onto a host/guest path.
pub(super) struct HostProcView {
    mount: File,
    root: File,
    own: File,
    own_pidfd: File,
    own_node: Node,
    own_process: Process,
    own_info: PidfdInfo,
    volume: Volume,
    provider: ProviderBinding,
    role: ViewRole,
    _same_thread: PhantomData<Rc<()>>,
}
impl HostProcView {
    pub(super) fn create(
        loaded: &LoadedPolicyWitness,
        selection: &ProductionSelection,
    ) -> Result<Self> {
        Self::create_role(loaded, selection, ViewRole::Broker)
    }
    /// Private fixed loader route; actual typed CURRENT and explicit AppArmor
    /// observations issue the role, never a caller-supplied context string.
    pub(super) fn create_loader(
        loaded: &LoadedPolicyWitness,
        selection: &ProductionSelection,
    ) -> Result<Self> {
        Self::create_role(loaded, selection, ViewRole::Loader)
    }
    /// Fixed original package-helper identity: host SELinux and unconfined AppArmor.
    /// This does not borrow the broker/loader view or accept a role string.
    pub(super) fn create_package_helper(
        loaded: &LoadedPolicyWitness,
        selection: &ProductionSelection,
    ) -> Result<Self> {
        Self::create_role(loaded, selection, ViewRole::Helper)
    }
    fn create_role(
        loaded: &LoadedPolicyWitness,
        selection: &ProductionSelection,
        role: ViewRole,
    ) -> Result<Self> {
        actor(loaded, selection, role)?;
        // Observe the actual creator's initial namespaces and effective
        // capability before creating a host-PID representation view. UID0
        // and a unit's AmbientCapabilities setting do not prove this.
        let original_proc = Node::of(&loaded.own_proc)?;
        let original_user = namespace(&loaded.own_proc, c"user", libc::CLONE_NEWUSER)?;
        let original_pid = namespace(&loaded.own_proc, c"pid", libc::CLONE_NEWPID)?;
        require(
            original_user.2 == 3
                && original_pid.2 == 4
                && unsafe { libc::syscall(libc::SYS_gettid) } == loaded.tid as libc::c_long,
            "selected host proc requires the original thread and initial user/PID namespaces",
        )?;
        let header = [0x2008_0522_u32, 0_u32];
        let mut capabilities = [0_u32; 6];
        success(unsafe {
            libc::syscall(libc::SYS_capget, header.as_ptr(), capabilities.as_mut_ptr())
        })?;
        const SYS_ADMIN: u32 = 1 << 21;
        require(
            capabilities[0] & SYS_ADMIN != 0 && capabilities[1] & SYS_ADMIN != 0,
            "selected host proc creator lacks actual effective/permitted SYS_ADMIN",
        )?;
        let current_user = namespace(&loaded.own_proc, c"user", libc::CLONE_NEWUSER)?;
        let current_pid = namespace(&loaded.own_proc, c"pid", libc::CLONE_NEWPID)?;
        require(
            Node::of(&loaded.own_proc)? == original_proc
                && (current_user.1, current_user.2) == (original_user.1, original_user.2)
                && (current_pid.1, current_pid.2) == (original_pid.1, original_pid.2)
                && Node::of(&original_user.0)? == original_user.1
                && Node::of(&original_pid.0)? == original_pid.1
                && unsafe { libc::syscall(libc::SYS_gettid) } == loaded.tid as libc::c_long,
            "original proc, thread or namespace changed across capability observation",
        )?;
        actor(loaded, selection, role)?;
        let own_pidfd =
            file(unsafe { libc::syscall(libc::SYS_pidfd_open, loaded.tid, PIDFD_THREAD) })?;
        let own_info = pidfd_info(own_pidfd.as_fd())?;
        require(
            own_info.pid == loaded.tid as u32,
            "PIDFD is the original actual broker thread",
        )?;
        let original = process(&loaded.own_proc)?;
        require(
            (original.pid, original.tgid, original.parent)
                == (own_info.pid, own_info.tgid, own_info.ppid),
            "original broker proc and PIDFD agree",
        )?;
        let mut sequence = Some(loaded.av_sequence);
        access(
            &loaded.root,
            role.context(),
            role.context(),
            "capability",
            &["sys_admin"],
            true,
            &mut sequence,
        )?;
        access(
            &loaded.root,
            role.context(),
            "u:object_r:proc:s0",
            "filesystem",
            &["mount", "getattr"],
            true,
            &mut sequence,
        )?;
        let context = file(unsafe { libc::syscall(libc::SYS_fsopen, c"proc".as_ptr(), 1_u32) })?;
        for (key, value) in [
            (c"hidepid", c"2"),
            (c"gid", c"0"),
            (c"subset", c"pid"),
            (c"lsm_context", c"selinux"),
        ] {
            success(unsafe {
                libc::syscall(
                    libc::SYS_fsconfig,
                    context.as_raw_fd(),
                    1_u32,
                    key.as_ptr(),
                    value.as_ptr(),
                    0,
                )
            })?;
        }
        actor(loaded, selection, role)?;
        success(unsafe {
            libc::syscall(
                libc::SYS_fsconfig,
                context.as_raw_fd(),
                6_u32,
                std::ptr::null::<libc::c_char>(),
                std::ptr::null::<libc::c_char>(),
                0,
            )
        })?;
        let mount =
            file(unsafe { libc::syscall(libc::SYS_fsmount, context.as_raw_fd(), 1_u32, 15_u32) })?;
        let root = open_at(mount.as_raw_fd(), c".", libc::O_RDONLY | libc::O_DIRECTORY)?;
        let snapshot = volume(&root)?;
        require(
            volume(&mount)? == snapshot,
            "original created mount/root custody",
        )?;
        detached(loaded, snapshot.mount)?;
        let name = CString::new(own_info.pid.to_string())
            .map_err(|_| MacError::Rejected("actual thread proc name"))?;
        let own = open_at(root.as_raw_fd(), &name, libc::O_RDONLY | libc::O_DIRECTORY)?;
        require(
            mount_id(&own)? == snapshot.mount && process(&own)? == original,
            "host view resolves the same actual broker thread",
        )?;
        same_namespaces(&loaded.own_proc, &own)?;
        let value = Self {
            mount,
            root,
            own_node: Node::of(&own)?,
            own,
            own_pidfd,
            own_process: original,
            own_info,
            volume: snapshot,
            provider: loaded.binding(),
            role,
            _same_thread: PhantomData,
        };
        value.revalidate(loaded, selection)?;
        Ok(value)
    }
    pub(super) fn revalidate(
        &self,
        loaded: &LoadedPolicyWitness,
        selection: &ProductionSelection,
    ) -> Result<()> {
        require(
            self.provider == loaded.binding(),
            "host proc belongs to another original provider or epoch",
        )?;
        actor(loaded, selection, self.role)?;
        require(
            volume(&self.mount)? == self.volume
                && volume(&self.root)? == self.volume
                && mount_id(&self.own)? == self.volume.mount
                && Node::of(&self.own)? == self.own_node,
            "original private readonly proc mount and broker inode",
        )?;
        detached(loaded, self.volume.mount)?;
        require(
            pidfd_info(self.own_pidfd.as_fd())? == self.own_info
                && process(&loaded.own_proc)? == self.own_process
                && process(&self.own)? == self.own_process,
            "original broker PIDFD and both held proc identities",
        )?;
        same_namespaces(&loaded.own_proc, &self.own)?;
        let selected = proc_attr(&self.own, false)?;
        let typed = self_attr::selinux_current()?;
        let apparmor = proc_attr(&self.own, true)?;
        fixed_view_identity(self.role, &selected, &apparmor)?;
        fixed_view_identity(self.role, &typed, &apparmor)?;
        require(
            context_matches(&selected, self.role.context())
                && context_matches(&typed, self.role.context()),
            "explicit proc SELinux provider must agree with actual typed CURRENT",
        )?;
        require(
            pidfd_info(self.own_pidfd.as_fd())? == self.own_info,
            "broker PIDFD changed during view revalidation",
        )?;
        loaded.stable_epoch()
    }
    fn observe(
        &self,
        loaded: &LoadedPolicyWitness,
        selection: &ProductionSelection,
        original: &File,
        pidfd: BorrowedFd<'_>,
        expected: &str,
        expected_apparmor: &[u8],
    ) -> Result<Vec<u8>> {
        self.revalidate(loaded, selection)?;
        let held = descriptor_identity(pidfd)?;
        let before = pidfd_info(pidfd)?;
        let original_node = Node::of(original)?;
        let original_process = process(original)?;
        require(
            (
                original_process.pid,
                original_process.tgid,
                original_process.parent,
            ) == (before.pid, before.tgid, before.ppid)
                && before.pid == before.tgid,
            "original live process PIDFD/proc identities",
        )?;
        let name = CString::new(before.pid.to_string())
            .map_err(|_| MacError::Rejected("actual PIDFD-derived proc name"))?;
        let viewed = open_at(
            self.root.as_raw_fd(),
            &name,
            libc::O_RDONLY | libc::O_DIRECTORY,
        )?;
        let node = Node::of(&viewed)?;
        require(
            mount_id(&viewed)? == self.volume.mount && process(&viewed)? == original_process,
            "selected view resolves only the same original process and start time",
        )?;
        same_namespaces(original, &viewed)?;
        let context = proc_attr(&viewed, false)?;
        require(
            context_matches(&context, expected),
            "actual original foreign SELinux role differs",
        )?;
        require(
            proc_attr(&viewed, true)? == expected_apparmor,
            "actual original foreign AppArmor role differs",
        )?;
        require(
            Node::of(&viewed)? == node
                && process(&viewed)? == original_process
                && Node::of(original)? == original_node
                && process(original)? == original_process
                && descriptor_identity(pidfd)? == held
                && pidfd_info(pidfd)? == before,
            "original foreign process changed across selected context read",
        )?;
        same_namespaces(original, &viewed)?;
        self.revalidate(loaded, selection)?;
        Ok(context)
    }
    /// Observe only the actual original apexd task's thread PIDFD. Unlike the
    /// existing leader-only observer, this path keeps TID and TGID distinct.
    /// No caller-selected PID, proc descriptor, label or namespace is accepted.
    pub(super) fn for_apexd(
        &self,
        loaded: &LoadedPolicyWitness,
        task: &crate::production_namespace::ActualApexdTask,
    ) -> Result<ApexdThreadBinding> {
        require(
            self.role == ViewRole::Broker,
            "original apexd view requires the original broker role",
        )?;
        original_owner(task.revalidate_kernel())?;
        let generation = original_owner(task.generation())?;
        let selection = original_owner(task.selection())?;
        self.revalidate(loaded, selection)?;

        let pidfd = task.pidfd();
        let held = descriptor_identity(pidfd)?;
        let before = pidfd_info(pidfd)?;
        let original = task.proc_directory();
        let original_node = Node::of(original)?;
        let original_process = process(original)?;
        apexd_process_matches_pidfd(original_process, before)?;

        // /<TID> is derived solely from the original kernel PIDFD, never from
        // the process leader or a supplied numeric task identifier.
        let name = CString::new(before.pid.to_string())
            .map_err(|_| MacError::Rejected("actual apexd PIDFD-derived thread name"))?;
        let viewed = open_at(
            self.root.as_raw_fd(),
            &name,
            libc::O_RDONLY | libc::O_DIRECTORY,
        )?;
        let node = Node::of(&viewed)?;
        require(
            mount_id(&viewed)? == self.volume.mount && process(&viewed)? == original_process,
            "selected view resolves the same original apexd TID/TGID/start time",
        )?;
        let namespaces = same_apexd_namespaces(original, &viewed)?;
        let context = proc_attr(&viewed, false)?;
        let apparmor = proc_attr(&viewed, true)?;
        super::apexd_task::fixed_apexd_identity(&context, &apparmor)?;
        require(
            proc_attr(original, true)? == AA_ANDROID,
            "original held apexd thread AppArmor role differs",
        )?;
        process_confinement_state(original)?;

        // The opaque task revalidation proves the approved full default mount
        // graph and original namespace pair. Matching the two proc views alone
        // is never treated as proof of that graph.
        original_owner(task.revalidate_kernel())?;
        require(
            original_owner(task.generation())? == generation,
            "original apexd task/default graph changed during selected context read",
        )?;
        require(
            Node::of(&viewed)? == node
                && process(&viewed)? == original_process
                && Node::of(original)? == original_node
                && process(original)? == original_process
                && descriptor_identity(pidfd)? == held
                && pidfd_info(pidfd)? == before,
            "original apexd thread changed across selected context read",
        )?;
        require(
            same_apexd_namespaces(original, &viewed)? == namespaces,
            "original apexd namespaces changed across selected context read",
        )?;
        super::apexd_task::fixed_apexd_identity(
            &proc_attr(&viewed, false)?,
            &proc_attr(&viewed, true)?,
        )?;
        self.revalidate(loaded, selection)?;
        original_owner(task.revalidate_kernel())?;
        require(
            original_owner(task.generation())? == generation
                && descriptor_identity(pidfd)? == held
                && pidfd_info(pidfd)? == before,
            "original apexd thread/epoch must remain live through final MAC bookend",
        )?;
        Ok(ApexdThreadBinding {
            original_proc: original_node,
            pidfd: held,
            info: before,
            process: original_process,
            namespaces,
        })
    }

    pub(super) fn for_init(
        &self,
        loaded: &LoadedPolicyWitness,
        init: &ExecutedInitWitness<'_>,
    ) -> Result<Vec<u8>> {
        require(
            self.role == ViewRole::Broker,
            "init view requires original broker role",
        )?;
        original_owner(init.revalidate())?;
        let generation = original_owner(init.generation())?;
        require(
            pidfd_info(init.pidfd())?.pid == init.host_pid(),
            "selected init is the original host PIDFD",
        )?;
        let observed = self.observe(
            loaded,
            init.selection(),
            init.proc_directory(),
            init.pidfd(),
            INIT,
            AA_ANDROID,
        )?;
        original_owner(init.revalidate())?;
        require(
            original_owner(init.generation())? == generation,
            "original init generation changed across host view read",
        )?;
        Ok(observed)
    }
    pub(super) fn for_helper(
        &self,
        loaded: &LoadedPolicyWitness,
        init: &ExecutedInitWitness<'_>,
        peer: &OwnedActivationPeer<'_>,
    ) -> Result<Vec<u8>> {
        require(
            self.role == ViewRole::Broker,
            "activation helper view requires original broker role",
        )?;
        original_owner(init.revalidate())?;
        original_owner(peer.revalidate())?;
        let generation = original_owner(init.generation())?;
        require(
            peer.generation() == generation && pidfd_info(peer.pidfd())?.ppid == init.host_pid(),
            "fixed helper is this original init's descendant",
        )?;
        let observed = self.observe(
            loaded,
            init.selection(),
            peer.proc_directory(),
            peer.pidfd(),
            LINKERCONFIG,
            AA_ANDROID,
        )?;
        original_owner(peer.revalidate())?;
        original_owner(init.revalidate())?;
        require(
            peer.generation() == generation && original_owner(init.generation())? == generation,
            "original helper/init generation changed across host view read",
        )?;
        Ok(observed)
    }

    /// Observe only the original holder issued by the same early host-peer
    /// authority. The opaque observation retains its own PIDFD, proc and
    /// namespace custody; no PID, pathname or context string is accepted here.
    pub(super) fn for_host_peer_network(
        &self,
        authority: &super::host_peer::HostPeerAuthority<'_>,
        observation: &super::host_peer_namespace::HostPeerNetworkObservation<'_>,
    ) -> Result<()> {
        authority.revalidate()?;
        observation.revalidate(authority)?;
        let role = match authority.role() {
            super::host_peer::HostPeerRole::Broker => ViewRole::Broker,
            super::host_peer::HostPeerRole::Loader => ViewRole::Loader,
            super::host_peer::HostPeerRole::Helper => ViewRole::Helper,
        };
        require(
            self.role == role,
            "host peer holder must use the same original proc-view role",
        )?;
        let pair = authority.pair();
        let binding = observation.binding()?;
        self.observe(
            authority.loaded(),
            authority.selection(),
            observation.proc_directory()?,
            observation.pidfd()?,
            authority.context(),
            authority.role().apparmor(),
        )?;
        observation.revalidate(authority)?;
        require(
            observation.binding()? == binding,
            "original host peer holder custody changed across selected proc read",
        )?;
        authority.revalidate()?;
        require(
            authority.pair() == pair,
            "host peer original inputs or role changed across selected proc read",
        )
    }

    pub(super) fn for_host_peer_socket(
        &self,
        authority: &super::host_peer::HostPeerAuthority<'_>,
        observation: &super::host_peer_socket::HostPeerSocketObservation<'_>,
    ) -> Result<()> {
        authority.revalidate()?;
        observation.revalidate(authority)?;
        let role = match authority.role() {
            super::host_peer::HostPeerRole::Broker => ViewRole::Broker,
            super::host_peer::HostPeerRole::Loader => ViewRole::Loader,
            super::host_peer::HostPeerRole::Helper => ViewRole::Helper,
        };
        require(
            self.role == role,
            "host peer socket helper must use the same original proc-view role",
        )?;
        let pair = authority.pair();
        let binding = observation.binding()?;
        self.observe(
            authority.loaded(),
            authority.selection(),
            observation.proc_directory()?,
            observation.pidfd()?,
            authority.context(),
            authority.role().apparmor(),
        )?;
        observation.revalidate(authority)?;
        require(
            observation.binding()? == binding,
            "original host peer socket helper custody changed across selected proc read",
        )?;
        authority.revalidate()?;
        require(
            authority.pair() == pair,
            "host peer original inputs or role changed across selected proc read",
        )
    }

    fn original_package_view(&self, owner: &super::package::PackageMacOwner) -> Result<()> {
        owner.revalidate()?;
        let role = match owner.role() {
            super::package::PackageMacRole::Helper => ViewRole::Helper,
            super::package::PackageMacRole::Broker => ViewRole::Broker,
        };
        require(
            self.role == role,
            "package proc view must retain the original fixed local role",
        )?;
        let original = owner.host_proc().ok_or(MacError::Rejected(
            "scoped package lacks its original selected proc view",
        ))?;
        require(
            std::ptr::eq(self, original),
            "package cannot substitute its original proc view",
        )?;
        let (loaded, selection) = owner.objects()?;
        self.revalidate(loaded, selection)
    }

    pub(super) fn for_package_process(
        &self,
        owner: &super::package::PackageMacOwner,
        process: &crate::control::package::PackageProcess,
    ) -> Result<()> {
        self.original_package_view(owner)?;
        process
            .revalidate()
            .map_err(|e| MacError::Owner(e.to_string()))?;
        let binding = process.binding();
        let (loaded, selection) = owner.objects()?;
        let (context, apparmor) = if process.is_broker() {
            (BROKER, AA_BROKER)
        } else {
            (HOST, b"unconfined\n".as_slice())
        };
        self.observe(
            loaded,
            selection,
            process.proc(),
            process.pidfd(),
            context,
            apparmor,
        )?;
        process
            .revalidate()
            .map_err(|e| MacError::Owner(e.to_string()))?;
        require(
            process.binding() == binding,
            "original package process changed across selected proc read",
        )?;
        self.original_package_view(owner)
    }

    pub(super) fn for_package_unit(
        &self,
        owner: &super::package::PackageMacOwner,
        unit: &crate::production_cgroup::PackageBrokerUnit,
        broker: &crate::control::package::PackageProcess,
        deadline: Instant,
    ) -> Result<()> {
        require(
            Instant::now() < deadline,
            "original package manager observation deadline",
        )?;
        self.original_package_view(owner)?;
        unit.require_original_owner(owner)
            .map_err(|e| MacError::Owner(e.to_string()))?;
        broker
            .revalidate()
            .map_err(|e| MacError::Owner(e.to_string()))?;
        require(
            broker.is_broker(),
            "package unit requires the original fixed broker process",
        )?;
        let broker_binding = broker.binding();
        let generation = unit
            .generation(broker, deadline)
            .map_err(|e| MacError::Owner(e.to_string()))?;
        let (loaded, selection) = owner.objects()?;
        self.observe(
            loaded,
            selection,
            unit.manager_proc(),
            unit.manager_pidfd(),
            HOST,
            b"unconfined\n",
        )?;
        self.observe(
            loaded,
            selection,
            broker.proc(),
            broker.pidfd(),
            BROKER,
            AA_BROKER,
        )?;
        broker
            .revalidate()
            .map_err(|e| MacError::Owner(e.to_string()))?;
        require(
            broker.binding() == broker_binding,
            "package unit original broker changed across selected proc reads",
        )?;
        unit.require_original_owner(owner)
            .map_err(|e| MacError::Owner(e.to_string()))?;
        require(
            unit.generation(broker, deadline)
                .map_err(|e| MacError::Owner(e.to_string()))?
                == generation,
            "package manager generation changed across selected proc reads",
        )?;
        self.original_package_view(owner)?;
        require(
            Instant::now() < deadline,
            "original package manager observation deadline",
        )
    }

    pub(super) fn for_systemd_owner(
        &self,
        loaded: &LoadedPolicyWitness,
        owner: &crate::production_cgroup::SystemdOwnerWitness<'_>,
    ) -> Result<()> {
        require(
            self.role == ViewRole::Broker,
            "prepared manager requires original broker view",
        )?;
        owner
            .revalidate()
            .map_err(|e| MacError::Owner(e.to_string()))?;
        let generation = owner
            .generation()
            .map_err(|e| MacError::Owner(e.to_string()))?;
        self.observe(
            loaded,
            owner.selection(),
            owner.manager_proc(),
            owner.manager_pidfd(),
            HOST,
            b"unconfined\n",
        )?;
        self.observe(
            loaded,
            owner.selection(),
            owner.broker_proc(),
            owner.broker_pidfd(),
            BROKER,
            AA_BROKER,
        )?;
        owner
            .revalidate()
            .map_err(|e| MacError::Owner(e.to_string()))?;
        require(
            owner
                .generation()
                .map_err(|e| MacError::Owner(e.to_string()))?
                == generation,
            "original systemd owner generation changed across selected proc observations",
        )
    }
    pub(super) fn for_manager_label(
        &self,
        loaded: &LoadedPolicyWitness,
        selection: &ProductionSelection,
        endpoint: &crate::production_cgroup::ManagerLabelObservation<'_>,
        deadline: Instant,
    ) -> Result<()> {
        require(
            self.role == ViewRole::Loader,
            "manager label requires original loader view",
        )?;
        endpoint
            .revalidate_until(deadline)
            .map_err(|e| MacError::Owner(e.to_string()))?;
        let generation = endpoint
            .generation()
            .map_err(|e| MacError::Owner(e.to_string()))?;
        self.observe(
            loaded,
            selection,
            endpoint.manager_proc(),
            endpoint.manager_pidfd(),
            HOST,
            b"unconfined\n",
        )?;
        self.observe(
            loaded,
            selection,
            endpoint.observer_proc(),
            endpoint.observer_pidfd(),
            LOADER,
            AA_LOADER,
        )?;
        endpoint
            .revalidate_until(deadline)
            .map_err(|e| MacError::Owner(e.to_string()))?;
        require(
            endpoint
                .generation()
                .map_err(|e| MacError::Owner(e.to_string()))?
                == generation,
            "original manager label endpoint generation changed across selected proc observations",
        )
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn selected_proc_roles_reject_crossed_lsms_and_other_domains() {
        for role in [ViewRole::Broker, ViewRole::Loader, ViewRole::Helper] {
            assert!(fixed_view_identity(role, role.context().as_bytes(), role.apparmor()).is_ok());
            for selinux in [BROKER, LOADER, HOST, INIT] {
                for apparmor in [AA_BROKER, AA_LOADER, AA_ANDROID, b"unconfined\n".as_slice()] {
                    if selinux == role.context() && apparmor == role.apparmor() {
                        continue;
                    }
                    assert!(matches!(
                        fixed_view_identity(role, selinux.as_bytes(), apparmor),
                        Err(MacError::Rejected(
                            "selected proc creator must retain both exact role identities"
                        ))
                    ));
                }
            }
            assert!(
                fixed_view_identity(
                    role,
                    format!("{}\0extra", role.context()).as_bytes(),
                    role.apparmor()
                )
                .is_err()
            );
        }
    }
    #[test]
    fn original_process_pidfd_and_proc_agree_without_issuing_a_mac_view() {
        let proc = File::open("/proc/self").unwrap();
        let observed = process(&proc).unwrap();
        let fd =
            file(unsafe { libc::syscall(libc::SYS_pidfd_open, libc::getpid(), 0_u32) }).unwrap();
        let pid = pidfd_info(fd.as_fd()).unwrap();
        assert_eq!(
            (observed.pid, observed.tgid, observed.parent),
            (pid.pid, pid.tgid, pid.ppid)
        );
        assert!(observed.start > 0);
    }
    #[test]
    fn ordinary_files_cannot_supply_pidfd_or_proc_mount_authority() {
        let regular = tempfile::tempfile().unwrap();
        assert!(pidfd_info(regular.as_fd()).is_err());
        assert!(process(&regular).is_err());
        assert!(volume(&regular).is_err());
    }
    #[test]
    fn stat_parser_rejects_incomplete_dead_and_ambiguous_identity_records() {
        let proc = File::open("/proc/self").unwrap();
        let raw = proc_read(&proc, c"stat").unwrap();
        assert!(stat_identity(&raw).is_ok());
        assert!(stat_identity(&raw[..raw.len() - 1]).is_err());
        let end = raw.iter().rposition(|b| *b == b')').unwrap();
        let mut dead = raw.clone();
        dead[end + 2] = b'Z';
        assert!(stat_identity(&dead).is_err());
        let mut extra = raw.clone();
        extra.extend_from_slice(b"\n");
        assert!(stat_identity(&extra).is_err());
        assert!(status_number(b"Pid:\t1\nPid:\t1\n", b"Pid:").is_err());
        assert!(status_number(b"Pid:\t01\n", b"Pid:").is_err());
    }
    #[test]
    fn detached_view_inventory_rejects_attached_reused_and_truncated_mount_ids() {
        let row = b"41 1 0:42 / / ro - proc proc ro\n";
        assert!(absent_mount(row, 42).is_ok());
        assert!(absent_mount(row, 41).is_err());
        assert!(absent_mount(&row[..row.len() - 1], 42).is_err());
        assert!(absent_mount(&[row.as_slice(), row.as_slice()].concat(), 42).is_err());
    }

    #[test]
    fn apexd_thread_identity_rejects_leader_surrogate_and_crossed_process_fields() {
        let original = Process {
            pid: 23,
            tgid: 17,
            parent: 1,
            start: 12345,
        };
        let mut info: PidfdInfo = unsafe { std::mem::zeroed() };
        info.mask = 3;
        info.pid = 23;
        info.tgid = 17;
        info.ppid = 1;
        apexd_process_matches_pidfd(original, info).unwrap();
        for crossed in [
            PidfdInfo { pid: 17, ..info },
            PidfdInfo { tgid: 23, ..info },
            PidfdInfo { ppid: 2, ..info },
        ] {
            assert!(apexd_process_matches_pidfd(original, crossed).is_err());
        }
        assert!(
            apexd_process_matches_pidfd(
                Process {
                    start: 0,
                    ..original
                },
                info
            )
            .is_err()
        );
    }
}
