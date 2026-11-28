//! Original, parked user/net namespace holder for an early host connection.
//!
//! Preparation only reads the original issuer and creator identities. The
//! containing owner must retain this value before create() makes either a
//! private channel or a child. No imported namespace, numeric PID, matching
//! digest or caller-selected role can construct this owner.
use super::host_peer::{HostPeerAuthority, HostPeerIssuer, HostPeerPair, HostPeerRole};
use super::host_proc::HostProcView;
use super::netns_provider::{NamespaceIdentity, namespace};
use super::*;

const NS_GET_USERNS: libc::c_ulong = 0xb701;
const NS_GET_PARENT: libc::c_ulong = 0xb702;
const PIDFS_MAGIC: u64 = 0x5049_4446;
const CREATE_LIMIT: Duration = Duration::from_secs(10);
const RETIRE_LIMIT: Duration = Duration::from_secs(3);
const CHILD_FLAGS: u64 = (libc::CLONE_PIDFD | libc::CLONE_NEWUSER | libc::CLONE_NEWNET) as u64;
const MAGIC: u32 = 0x5048_4e31;
const READY: u32 = 1;
const PARKED: u32 = 2;
const RELEASE: u8 = 0x52;
const CHILD_CHANNEL: RawFd = 3;
const CHILD_CREATOR: RawFd = 4;

const NAMESPACES: [(&CStr, i32); 10] = [
    (c"user", libc::CLONE_NEWUSER),
    (c"net", libc::CLONE_NEWNET),
    (c"mnt", libc::CLONE_NEWNS),
    (c"pid", libc::CLONE_NEWPID),
    (c"pid_for_children", libc::CLONE_NEWPID),
    (c"ipc", libc::CLONE_NEWIPC),
    (c"uts", libc::CLONE_NEWUTS),
    (c"cgroup", libc::CLONE_NEWCGROUP),
    (c"time", 0x80),
    (c"time_for_children", 0x80),
];

fn file(rc: libc::c_long) -> Result<File> {
    if rc < 0 {
        return Err(io::Error::last_os_error().into());
    }
    let fd = i32::try_from(rc).map_err(|_| MacError::Rejected("host holder FD overflow"))?;
    Ok(unsafe { File::from_raw_fd(fd) })
}

fn zero(rc: libc::c_long) -> Result<()> {
    if rc == 0 {
        Ok(())
    } else {
        Err(io::Error::last_os_error().into())
    }
}

fn before(end: Instant) -> Result<()> {
    require(
        Instant::now() < end,
        "original host holder creation deadline",
    )
}

fn alive(fd: &File) -> Result<()> {
    let mut p = libc::pollfd {
        fd: fd.as_raw_fd(),
        events: libc::POLLIN,
        revents: 0,
    };
    let n = unsafe { libc::poll(&mut p, 1, 0) };
    if n < 0 {
        return Err(io::Error::last_os_error().into());
    }
    require(
        n == 0 && p.revents == 0,
        "original host holder PIDFD is not live",
    )
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct PidIdentity {
    pid: u32,
    tgid: u32,
    parent: u32,
    ids: [u32; 8],
}

fn pid_identity(fd: &File) -> Result<PidIdentity> {
    alive(fd)?;
    let original = descriptor_identity(fd.as_fd())?;
    require(
        kind(fd)? == PIDFS_MAGIC,
        "host holder requires an actual pidfs descriptor",
    )?;
    let mut info = crate::production_activation_protocol::PidfdInfo::request_exit();
    info.mask = 3;
    zero(unsafe {
        libc::ioctl(
            fd.as_raw_fd(),
            crate::production_activation_protocol::PIDFD_GET_INFO as libc::c_ulong,
            &mut info,
        )
    } as libc::c_long)?;
    require(
        info.mask & 3 == 3
            && info.mask & !7 == 0
            && info.pid > 1
            && info.tgid > 1
            && info.exit_code == 0
            && info.coredump_mask == 0
            && info.coredump_signal == 0
            && descriptor_identity(fd.as_fd())? == original,
        "complete live host holder PIDFD information",
    )?;
    alive(fd)?;
    Ok(PidIdentity {
        pid: info.pid,
        tgid: info.tgid,
        parent: info.ppid,
        ids: [
            info.ruid, info.euid, info.suid, info.fsuid, info.rgid, info.egid, info.sgid,
            info.fsgid,
        ],
    })
}

fn read_proc(directory: &File, name: &CStr) -> Result<Vec<u8>> {
    require(
        kind(directory)? == PROC_MAGIC,
        "original host holder procfs directory",
    )?;
    let opened = open_at(directory.as_raw_fd(), name, libc::O_RDONLY)?;
    require(
        kind(&opened)? == PROC_MAGIC && Node::of(&opened)?.mode & libc::S_IFMT == libc::S_IFREG,
        "actual fixed host holder procfs record",
    )?;
    bounded(&opened, 65536)
}

fn number(raw: &[u8]) -> Result<u64> {
    require(
        !raw.is_empty()
            && raw.len() <= 20
            && raw.iter().all(u8::is_ascii_digit)
            && (raw.len() == 1 || raw[0] != b'0'),
        "canonical host holder proc integer",
    )?;
    std::str::from_utf8(raw)
        .map_err(|_| MacError::Rejected("host holder proc encoding"))?
        .parse()
        .map_err(|_| MacError::Rejected("host holder proc integer overflow"))
}

fn status_field<'a>(raw: &'a [u8], key: &[u8]) -> Result<Vec<&'a [u8]>> {
    require(
        !raw.is_empty() && raw.len() <= 65536 && raw.ends_with(b"\n"),
        "complete host holder status",
    )?;
    let mut matches = raw
        .split(|b| *b == b'\n')
        .filter_map(|line| line.strip_prefix(key));
    let row = matches
        .next()
        .ok_or(MacError::Rejected("missing host holder status field"))?;
    require(
        matches.next().is_none(),
        "duplicate host holder status field",
    )?;
    Ok(row
        .split(|b| b.is_ascii_whitespace())
        .filter(|v| !v.is_empty())
        .collect())
}

fn status_number(raw: &[u8], key: &[u8]) -> Result<u64> {
    let parts = status_field(raw, key)?;
    require(parts.len() == 1, "one host holder status number")?;
    number(parts[0])
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct ProcessIdentity {
    pid: u32,
    parent: u32,
    start: u64,
}

fn stat_identity(raw: &[u8]) -> Result<ProcessIdentity> {
    require(
        !raw.is_empty() && raw.len() <= 65536 && raw.ends_with(b"\n"),
        "complete host holder stat",
    )?;
    let begin = raw
        .windows(2)
        .position(|w| w == b" (")
        .ok_or(MacError::Rejected("host holder stat command start"))?;
    let end = raw
        .iter()
        .rposition(|b| *b == b')')
        .ok_or(MacError::Rejected("host holder stat command end"))?;
    require(
        end > begin + 1 && raw.get(end + 1) == Some(&b' '),
        "host holder stat command delimiters",
    )?;
    let parts: Vec<_> = raw[end + 2..raw.len() - 1]
        .split(|b| b.is_ascii_whitespace())
        .filter(|p| !p.is_empty())
        .collect();
    require(
        (50..=64).contains(&parts.len())
            && parts[0].len() == 1
            && b"RSDTtWIP".contains(&parts[0][0]),
        "complete live host holder stat fields",
    )?;
    Ok(ProcessIdentity {
        pid: u32::try_from(number(&raw[..begin])?).map_err(|_| MacError::Rejected("holder PID"))?,
        parent: u32::try_from(number(parts[1])?)
            .map_err(|_| MacError::Rejected("holder parent"))?,
        start: number(parts[19])?,
    })
}

fn parked_process(proc: &File, pidfd: &File, expected: PidIdentity) -> Result<ProcessIdentity> {
    let node = Node::of(proc)?;
    require(
        kind(proc)? == PROC_MAGIC && node.mode & libc::S_IFMT == libc::S_IFDIR,
        "actual held host holder proc directory",
    )?;
    require(
        pid_identity(pidfd)? == expected && expected.ids == [0; 8],
        "same original holder PIDFD and physical root credentials",
    )?;
    let first = stat_identity(&read_proc(proc, c"stat")?)?;
    let status = read_proc(proc, c"status")?;
    require(
        first.pid == expected.pid
            && first.parent == expected.parent
            && first.start > 0
            && status_number(&status, b"Pid:")? == expected.pid as u64
            && status_number(&status, b"Tgid:")? == expected.tgid as u64
            && status_number(&status, b"PPid:")? == expected.parent as u64
            && status_number(&status, b"Threads:")? == 1
            && status_number(&status, b"NoNewPrivs:")? == 1
            && status_number(&status, b"Seccomp:")? == 2,
        "original single parked thread with no-new-privileges and actual seccomp",
    )?;
    for key in [b"Uid:".as_slice(), b"Gid:"] {
        let ids = status_field(&status, key)?;
        require(
            ids.len() == 4 && ids.iter().all(|v| *v == b"0"),
            "original holder physical UID/GID changed",
        )?;
    }
    for key in [
        b"CapInh:".as_slice(),
        b"CapPrm:",
        b"CapEff:",
        b"CapBnd:",
        b"CapAmb:",
    ] {
        require(
            status_field(&status, key)? == vec![b"0000000000000000".as_slice()],
            "parked holder retains a capability",
        )?;
    }
    let task = open_at(proc.as_raw_fd(), c"task", libc::O_PATH | libc::O_DIRECTORY)?;
    let name =
        CString::new(expected.pid.to_string()).map_err(|_| MacError::Rejected("holder task"))?;
    let thread = open_at(task.as_raw_fd(), &name, libc::O_PATH | libc::O_DIRECTORY)?;
    require(
        read_proc(&thread, c"children")?.is_empty(),
        "parked holder has descendants",
    )?;
    require(
        Node::of(proc)? == node
            && stat_identity(&read_proc(proc, c"stat")?)? == first
            && pid_identity(pidfd)? == expected,
        "holder changed across actual proc observations",
    )?;
    Ok(first)
}

fn namespaces(proc: &File) -> Result<Vec<(File, NamespaceIdentity)>> {
    let directory = open_at(proc.as_raw_fd(), c"ns", libc::O_PATH | libc::O_DIRECTORY)?;
    require(
        kind(&directory)? == PROC_MAGIC,
        "held holder namespace directory is procfs",
    )?;
    let mut values = Vec::with_capacity(NAMESPACES.len());
    for (name, kind) in NAMESPACES {
        // The only follows are these ten fixed kernel namespace magic links,
        // relative to the original held process directory.
        let value = file(unsafe {
            libc::openat(
                directory.as_raw_fd(),
                name.as_ptr(),
                libc::O_RDONLY | libc::O_CLOEXEC,
            )
        } as libc::c_long)?;
        let identity = namespace(&value, kind)?;
        values.push((value, identity));
    }
    Ok(values)
}

fn namespace_owner(fd: &File, request: libc::c_ulong) -> Result<File> {
    let result =
        file(unsafe { libc::ioctl(fd.as_raw_fd(), request, 0 as libc::c_ulong) } as libc::c_long)?;
    let flags = unsafe { libc::fcntl(result.as_raw_fd(), libc::F_GETFD) };
    if flags < 0 {
        return Err(io::Error::last_os_error().into());
    }
    require(
        flags & libc::FD_CLOEXEC != 0,
        "held namespace parent/owner CLOEXEC",
    )?;
    Ok(result)
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(super) struct HostPeerNetworkBinding {
    provider: ProviderBinding,
    pair: HostPeerPair,
    holder_pidfd: DescriptorIdentity,
    holder_proc: Node,
    start: u64,
    user: NamespaceIdentity,
    network: NamespaceIdentity,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum Stage {
    Prepared,
    Creating,
    Live,
    Retiring,
    Retired,
}

pub(super) struct HostPeerNetworkOwner {
    original: Option<HostPeerIssuer>,
    provider: ProviderBinding,
    pair: HostPeerPair,
    holder: Holder,
    creator_namespaces: Vec<(File, NamespaceIdentity)>,
    proc_root: File,
    process: Option<File>,
    process_id: Option<ProcessIdentity>,
    held_namespaces: Vec<(File, NamespaceIdentity)>,
    identity: Option<HostPeerNetworkBinding>,
    view: Option<HostProcView>,
    stage: Stage,
    _same_thread: PhantomData<Rc<()>>,
}

impl HostPeerNetworkOwner {
    pub(super) fn prepare(authority: &HostPeerAuthority<'_>, end: Instant) -> Result<Self> {
        let now = Instant::now();
        require(
            end > now && end.duration_since(now) <= CREATE_LIMIT,
            "bounded original host namespace creation deadline",
        )?;
        authority.revalidate()?;
        let original = authority.retain_original()?;
        let creator_namespaces = namespaces(&authority.loaded().own_proc)?;
        require(
            creator_namespaces[0].1.id == 3,
            "host namespace creator must remain in the original initial user namespace",
        )?;
        let proc_root = open_absolute("/proc", libc::O_PATH | libc::O_DIRECTORY)?;
        require(
            kind(&proc_root)? == PROC_MAGIC,
            "actual original host procfs root",
        )?;
        let holder = Holder::prepare(end)?;
        require(
            holder.creator == authority.loaded().tid as i64,
            "host namespace creator is the original MAC thread",
        )?;
        let value = Self {
            original: Some(original),
            provider: authority.provider(),
            pair: authority.pair(),
            holder,
            creator_namespaces,
            proc_root,
            process: None,
            process_id: None,
            held_namespaces: Vec::new(),
            identity: None,
            view: None,
            stage: Stage::Prepared,
            _same_thread: PhantomData,
        };
        value.original(authority)?;
        before(end)?;
        Ok(value)
    }

    fn original(&self, authority: &HostPeerAuthority<'_>) -> Result<()> {
        authority.revalidate()?;
        let original = self
            .original
            .as_ref()
            .ok_or(MacError::Rejected("host issuer retired"))?
            .authority()?;
        require(
            original.pair() == self.pair
                && authority.pair() == self.pair
                && original.provider() == self.provider
                && authority.provider() == self.provider,
            "host namespace cannot substitute the original retained MAC pair",
        )?;
        self.holder.same_thread()?;
        let current = namespaces(&authority.loaded().own_proc)?;
        require(
            current
                .iter()
                .map(|v| v.1)
                .eq(self.creator_namespaces.iter().map(|v| v.1)),
            "host namespace creator left its original namespaces",
        )?;
        for ((held, expected), (_, ty)) in self.creator_namespaces.iter().zip(NAMESPACES) {
            require(
                namespace(held, ty)? == *expected,
                "original creator namespace changed",
            )?;
        }
        authority.revalidate()
    }

    pub(super) fn create(&mut self, authority: &HostPeerAuthority<'_>) -> Result<()> {
        require(
            self.stage == Stage::Prepared,
            "host namespace creation cannot be replayed",
        )?;
        self.original(authority)?;
        before(self.holder.deadline)?;
        self.stage = Stage::Creating;
        self.holder.spawn()?;
        self.holder.receive(READY)?;
        self.original(authority)?;
        let info = pid_identity(self.holder.pidfd()?)?;
        require(
            info.pid == self.holder.pid as u32
                && info.pid == info.tgid
                && info.parent == self.holder.parent as u32
                && info.ids == [0; 8],
            "new child identity must agree with the atomic clone PIDFD",
        )?;
        let name = CString::new(info.pid.to_string())
            .map_err(|_| MacError::Rejected("holder PID name"))?;
        self.process = Some(open_at(
            self.proc_root.as_raw_fd(),
            &name,
            libc::O_RDONLY | libc::O_DIRECTORY,
        )?);
        let proc = self.process.as_ref().unwrap();
        self.process_id = Some(parked_process(proc, self.holder.pidfd()?, info)?);
        self.held_namespaces = namespaces(proc)?;
        self.check_namespaces()?;
        self.identity = Some(HostPeerNetworkBinding {
            provider: self.provider,
            pair: self.pair,
            holder_pidfd: descriptor_identity(self.holder.pidfd()?.as_fd())?,
            holder_proc: Node::of(proc)?,
            start: self.process_id.unwrap().start,
            user: self.held_namespaces[0].1,
            network: self.held_namespaces[1].1,
        });
        self.view = Some(match authority.role() {
            HostPeerRole::Broker => {
                HostProcView::create(authority.loaded(), authority.selection())?
            }
            HostPeerRole::Loader => {
                HostProcView::create_loader(authority.loaded(), authority.selection())?
            }
            HostPeerRole::Helper => {
                HostProcView::create_package_helper(authority.loaded(), authority.selection())?
            }
        });
        self.view
            .as_ref()
            .unwrap()
            .for_host_peer_network(authority, &self.observation(authority)?)?;
        before(self.holder.deadline)?;
        self.holder.release()?;
        self.holder.receive(PARKED)?;
        self.storage(authority)?;
        self.view
            .as_ref()
            .unwrap()
            .for_host_peer_network(authority, &self.observation(authority)?)?;
        self.storage(authority)?;
        before(self.holder.deadline)?;
        self.stage = Stage::Live;
        Ok(())
    }

    fn check_namespaces(&self) -> Result<()> {
        require(
            self.held_namespaces.len() == NAMESPACES.len(),
            "complete holder namespace set",
        )?;
        let current = namespaces(
            self.process
                .as_ref()
                .ok_or(MacError::Rejected("holder proc absent"))?,
        )?;
        for (index, ((held, expected), (_, ty))) in
            self.held_namespaces.iter().zip(NAMESPACES).enumerate()
        {
            require(
                namespace(held, ty)? == *expected && current[index].1 == *expected,
                "holder left an original held namespace",
            )?;
            if index < 2 {
                require(
                    *expected != self.creator_namespaces[index].1,
                    "holder must create fresh user and network namespaces",
                )?;
            } else {
                require(
                    *expected == self.creator_namespaces[index].1,
                    "holder unexpectedly created or entered another namespace",
                )?;
            }
        }
        let user = &self.held_namespaces[0];
        let network = &self.held_namespaces[1];
        require(
            user.1.id != 3,
            "host peer network cannot use the initial user namespace",
        )?;
        let owner = namespace_owner(&network.0, NS_GET_USERNS)?;
        let parent = namespace_owner(&user.0, NS_GET_PARENT)?;
        require(
            namespace(&owner, libc::CLONE_NEWUSER)? == user.1
                && namespace(&parent, libc::CLONE_NEWUSER)? == self.creator_namespaces[0].1
                && self.creator_namespaces[0].1.id == 3,
            "fresh network owner and original initial user-namespace parent differ",
        )
    }

    fn storage(&self, authority: &HostPeerAuthority<'_>) -> Result<()> {
        require(
            matches!(self.stage, Stage::Creating | Stage::Live),
            "host holder is not live",
        )?;
        if self.stage == Stage::Creating {
            before(self.holder.deadline)?;
        }
        self.original(authority)?;
        let identity = self
            .identity
            .ok_or(MacError::Rejected("host holder identity not captured"))?;
        let proc = self
            .process
            .as_ref()
            .ok_or(MacError::Rejected("original holder proc retired"))?;
        let info = pid_identity(self.holder.pidfd()?)?;
        require(
            info.pid == self.holder.pid as u32
                && info.pid == info.tgid
                && info.parent == self.holder.parent as u32
                && descriptor_identity(self.holder.pidfd()?.as_fd())? == identity.holder_pidfd
                && Node::of(proc)? == identity.holder_proc
                && Some(parked_process(proc, self.holder.pidfd()?, info)?) == self.process_id,
            "original host holder process generation differs",
        )?;
        self.check_namespaces()?;
        require(
            self.held_namespaces[0].1 == identity.user
                && self.held_namespaces[1].1 == identity.network,
            "original host namespace binding differs",
        )?;
        self.original(authority)?;
        if self.stage == Stage::Creating {
            before(self.holder.deadline)?;
        }
        Ok(())
    }

    fn revalidate(&self, authority: &HostPeerAuthority<'_>) -> Result<()> {
        require(
            self.stage == Stage::Live && self.holder.released && self.holder.parked,
            "host namespace lacks its actual parked holder",
        )?;
        self.storage(authority)?;
        self.view
            .as_ref()
            .ok_or(MacError::Rejected("original holder label view absent"))?
            .for_host_peer_network(authority, &self.observation(authority)?)?;
        self.storage(authority)
    }

    fn observation(
        &self,
        authority: &HostPeerAuthority<'_>,
    ) -> Result<HostPeerNetworkObservation<'_>> {
        self.storage(authority)?;
        Ok(HostPeerNetworkObservation { owner: self })
    }

    pub(super) fn network(
        &self,
        authority: &HostPeerAuthority<'_>,
    ) -> Result<(&File, NamespaceIdentity)> {
        self.revalidate(authority)?;
        Ok((&self.held_namespaces[1].0, self.held_namespaces[1].1))
    }

    pub(super) fn binding(
        &self,
        authority: &HostPeerAuthority<'_>,
    ) -> Result<HostPeerNetworkBinding> {
        self.revalidate(authority)?;
        self.identity
            .ok_or(MacError::Rejected("original host namespace binding absent"))
    }

    /// Observe only the helper belonging to this same original holder.
    /// A matching MAC pair alone does not identify one of multiple namespaces.
    pub(super) fn verify_socket(
        &self,
        authority: &HostPeerAuthority<'_>,
        observation: &super::host_peer_socket::HostPeerSocketObservation<'_>,
    ) -> Result<()> {
        self.revalidate(authority)?;
        let network = self.binding(authority)?;
        require(
            observation.network_binding()? == network,
            "socket helper cannot borrow another original host network holder",
        )?;
        self.view
            .as_ref()
            .ok_or(MacError::Rejected("original holder label view absent"))?
            .for_host_peer_socket(authority, observation)?;
        self.storage(authority)?;
        require(
            observation.network_binding()? == network && self.binding(authority)? == network,
            "socket helper or original network holder changed during MAC observation",
        )
    }

    pub(super) fn retire(&mut self, authority: &HostPeerAuthority<'_>) -> Result<()> {
        require(
            authority.pair() == self.pair && authority.provider() == self.provider,
            "host namespace retirement cannot substitute its original owner",
        )?;
        self.retire_owned()
    }

    /// Already-owned cleanup remains possible when policy/role revalidation
    /// fails. This only kills and reaps the original atomic child PIDFD; it
    /// cannot create, adopt, label or issue a namespace/socket capability.
    pub(super) fn retire_owned(&mut self) -> Result<()> {
        self.holder.same_thread()?;
        if self.stage == Stage::Retired {
            return Ok(());
        }
        self.stage = Stage::Retiring;
        self.holder.retire()?;
        self.view.take();
        self.held_namespaces.clear();
        self.process.take();
        self.original.take();
        self.stage = Stage::Retired;
        Ok(())
    }
}

impl Drop for HostPeerNetworkOwner {
    fn drop(&mut self) {
        if self.holder.child.is_some() && self.holder.exit.is_none() {
            // Failure leaves the original child, namespaces and issuer in
            // custody. Drop never reports an unobserved retirement as success.
            if let Some(original) = self.original.take() {
                std::mem::forget(original);
            }
            if let Some(view) = self.view.take() {
                std::mem::forget(view);
            }
            if let Some(proc) = self.process.take() {
                std::mem::forget(proc);
            }
            for (fd, _) in self.held_namespaces.drain(..) {
                std::mem::forget(fd);
            }
        }
    }
}

pub(super) struct HostPeerNetworkObservation<'a> {
    owner: &'a HostPeerNetworkOwner,
}
impl HostPeerNetworkObservation<'_> {
    pub(super) fn revalidate(&self, authority: &HostPeerAuthority<'_>) -> Result<()> {
        self.owner.storage(authority)
    }
    pub(super) fn pidfd(&self) -> Result<BorrowedFd<'_>> {
        Ok(self.owner.holder.pidfd()?.as_fd())
    }
    pub(super) fn proc_directory(&self) -> Result<&File> {
        self.owner
            .process
            .as_ref()
            .ok_or(MacError::Rejected("original holder proc absent"))
    }
    pub(super) fn binding(&self) -> Result<HostPeerNetworkBinding> {
        self.owner
            .identity
            .ok_or(MacError::Rejected("original holder binding absent"))
    }
}

#[repr(C)]
#[derive(Clone, Copy)]
struct Reply {
    magic: u32,
    phase: u32,
    errno: i32,
    reserved: u32,
}

struct Holder {
    creator: i64,
    parent: i32,
    creator_pidfd: File,
    deadline: Instant,
    child: Option<File>,
    channel: Option<File>,
    pid: i32,
    spawned: bool,
    ready: bool,
    released: bool,
    parked: bool,
    exit: Option<(i32, i32)>,
    waited_pid: Option<i32>,
    terminal_verified: bool,
    retirement_end: Option<Instant>,
    _same_thread: PhantomData<Rc<()>>,
}

impl Holder {
    fn prepare(deadline: Instant) -> Result<Self> {
        before(deadline)?;
        let creator = unsafe { libc::syscall(libc::SYS_gettid) };
        let parent = unsafe { libc::getpid() };
        require(
            creator > 1 && parent > 1,
            "host holder cannot originate in PID1",
        )?;
        let creator_pidfd =
            file(unsafe { libc::syscall(libc::SYS_pidfd_open, creator, 0x80_u32) })?;
        let info = pid_identity(&creator_pidfd)?;
        require(
            info.pid as i64 == creator && info.tgid == parent as u32,
            "host holder creator thread PIDFD identity",
        )?;
        Ok(Self {
            creator,
            parent,
            creator_pidfd,
            deadline,
            child: None,
            channel: None,
            pid: 0,
            spawned: false,
            ready: false,
            released: false,
            parked: false,
            exit: None,
            waited_pid: None,
            terminal_verified: false,
            retirement_end: None,
            _same_thread: PhantomData,
        })
    }

    fn same_thread(&self) -> Result<()> {
        require(
            unsafe { libc::syscall(libc::SYS_gettid) } == self.creator,
            "host holder custody moved from its original creator thread",
        )?;
        alive(&self.creator_pidfd)
    }

    fn pidfd(&self) -> Result<&File> {
        self.child
            .as_ref()
            .ok_or(MacError::Rejected("atomic host holder PIDFD absent"))
    }

    fn spawn(&mut self) -> Result<()> {
        self.spawn_inner(CHILD_FLAGS, true, false)
    }

    fn spawn_inner(&mut self, flags: u64, reduce: bool, forbidden_probe: bool) -> Result<()> {
        self.same_thread()?;
        before(self.deadline)?;
        require(
            !self.spawned && self.child.is_none() && self.channel.is_none(),
            "host holder clone cannot be replayed",
        )?;
        // All callers outside this private module use the fixed production
        // flags above. Ordinary tests exercise the same barrier/park/reaper
        // without issuing a MAC or namespace authority.
        self.spawned = true;
        let mut action: libc::sigaction = unsafe { std::mem::zeroed() };
        zero(
            unsafe { libc::sigaction(libc::SIGCHLD, std::ptr::null(), &mut action) }
                as libc::c_long,
        )?;
        require(
            action.sa_sigaction == libc::SIG_DFL && action.sa_flags & libc::SA_NOCLDWAIT == 0,
            "host holder requires original-parent waitid reaping",
        )?;
        let mut pair = [-1_i32; 2];
        zero(unsafe {
            libc::socketpair(
                libc::AF_UNIX,
                libc::SOCK_SEQPACKET | libc::SOCK_CLOEXEC | libc::SOCK_NONBLOCK,
                0,
                pair.as_mut_ptr(),
            )
        } as libc::c_long)?;
        self.channel = Some(unsafe { File::from_raw_fd(pair[0]) });
        let child_channel = unsafe { File::from_raw_fd(pair[1]) };
        let mut now: libc::timespec = unsafe { std::mem::zeroed() };
        zero(unsafe { libc::clock_gettime(libc::CLOCK_MONOTONIC, &mut now) } as libc::c_long)?;
        let left = self
            .deadline
            .checked_duration_since(Instant::now())
            .ok_or(MacError::Rejected("host holder clone deadline"))?;
        let child_end = u64::try_from(now.tv_sec)
            .ok()
            .and_then(|v| v.checked_mul(1_000_000_000))
            .and_then(|v| v.checked_add(u64::try_from(now.tv_nsec).ok()?))
            .and_then(|v| v.checked_add(u64::try_from(left.as_nanos()).ok()?))
            .ok_or(MacError::Rejected(
                "host holder monotonic deadline overflow",
            ))?;
        let mut full: libc::sigset_t = unsafe { std::mem::zeroed() };
        let mut old: libc::sigset_t = unsafe { std::mem::zeroed() };
        zero(unsafe { libc::sigfillset(&mut full) } as libc::c_long)?;
        let rc = unsafe { libc::pthread_sigmask(libc::SIG_SETMASK, &full, &mut old) };
        if rc != 0 {
            return Err(io::Error::from_raw_os_error(rc).into());
        }
        let mut pidfd = -1_i32;
        let mut args = [0_u64; 11];
        args[0] = flags;
        args[1] = (&mut pidfd as *mut i32) as u64;
        args[4] = libc::SIGCHLD as u64;
        let pid = unsafe {
            libc::syscall(
                libc::SYS_clone3,
                args.as_ptr(),
                std::mem::size_of_val(&args),
            )
        };
        if pid == 0 {
            unsafe {
                child_main(
                    child_channel.as_raw_fd(),
                    self.creator_pidfd.as_raw_fd(),
                    self.parent,
                    child_end,
                    reduce,
                    forbidden_probe,
                )
            }
        }
        let error = if pid < 0 {
            Some(io::Error::last_os_error())
        } else {
            None
        };
        // clone3 with CLONE_PIDFD atomically returns this descriptor. Store it
        // in the already retained owner before restoration or any other check.
        if pid > 0 {
            if pidfd < 0 || pid > i32::MAX as i64 {
                std::process::abort();
            }
            self.child = Some(unsafe { File::from_raw_fd(pidfd) });
            self.pid = pid as i32;
        }
        let restored =
            unsafe { libc::pthread_sigmask(libc::SIG_SETMASK, &old, std::ptr::null_mut()) };
        drop(child_channel);
        if let Some(error) = error {
            return Err(error.into());
        }
        if restored != 0 {
            return Err(io::Error::from_raw_os_error(restored).into());
        }
        before(self.deadline)
    }

    fn receive(&mut self, expected: u32) -> Result<()> {
        require(
            (expected == READY && !self.ready && !self.released)
                || (expected == PARKED && self.ready && self.released && !self.parked),
            "host holder reply phase cannot replay",
        )?;
        loop {
            self.same_thread()?;
            before(self.deadline)?;
            alive(self.pidfd()?)?;
            let channel = self
                .channel
                .as_ref()
                .ok_or(MacError::Rejected("holder channel absent"))?;
            let mut reply: Reply = unsafe { std::mem::zeroed() };
            let count = unsafe {
                libc::recv(
                    channel.as_raw_fd(),
                    (&mut reply as *mut Reply).cast(),
                    std::mem::size_of::<Reply>(),
                    libc::MSG_DONTWAIT | libc::MSG_TRUNC,
                )
            };
            if count >= 0 {
                require(
                    count as usize == std::mem::size_of::<Reply>()
                        && reply.magic == MAGIC
                        && reply.phase == expected
                        && reply.errno == 0
                        && reply.reserved == 0,
                    "actual host holder reply differs from its finite phase",
                )?;
                self.same_thread()?;
                alive(self.pidfd()?)?;
                before(self.deadline)?;
                if expected == READY {
                    self.ready = true;
                } else {
                    self.parked = true;
                }
                return Ok(());
            }
            let error = io::Error::last_os_error();
            if error.raw_os_error() != Some(libc::EAGAIN)
                && error.raw_os_error() != Some(libc::EINTR)
            {
                return Err(error.into());
            }
            let mut p = libc::pollfd {
                fd: channel.as_raw_fd(),
                events: libc::POLLIN,
                revents: 0,
            };
            let rc = unsafe { libc::poll(&mut p, 1, 20) };
            if rc < 0 && io::Error::last_os_error().raw_os_error() != Some(libc::EINTR) {
                return Err(io::Error::last_os_error().into());
            }
        }
    }

    fn release(&mut self) -> Result<()> {
        self.same_thread()?;
        before(self.deadline)?;
        require(
            self.ready && !self.released,
            "post-PDEATHSIG READY must precede release",
        )?;
        alive(self.pidfd()?)?;
        let fd = self
            .channel
            .as_ref()
            .ok_or(MacError::Rejected("holder channel absent"))?
            .as_raw_fd();
        let rc = unsafe {
            libc::send(
                fd,
                (&RELEASE as *const u8).cast(),
                1,
                libc::MSG_NOSIGNAL | libc::MSG_DONTWAIT,
            )
        };
        // Never retry an uncertain successful release with another budget.
        self.released = rc == 1;
        if rc < 0 {
            return Err(io::Error::last_os_error().into());
        }
        require(rc == 1, "exact one-byte host holder release")?;
        self.same_thread()?;
        before(self.deadline)
    }

    fn reap(&mut self) -> Result<bool> {
        if self.exit.is_some() {
            return self.verify_terminal();
        }
        let Some(child) = self.child.as_ref() else {
            return Ok(true);
        };
        let mut info: libc::siginfo_t = unsafe { std::mem::zeroed() };
        zero(unsafe {
            libc::waitid(
                libc::P_PIDFD,
                child.as_raw_fd() as u32,
                &mut info,
                libc::WEXITED | libc::WNOHANG,
            )
        } as libc::c_long)?;
        let pid = unsafe { info.si_pid() };
        if pid == 0 {
            return Ok(false);
        }
        // Journal the actual wait before any fallible terminal validation.
        self.exit = Some((info.si_code, unsafe { info.si_status() }));
        self.waited_pid = Some(pid);
        self.verify_terminal()
    }

    fn verify_terminal(&mut self) -> Result<bool> {
        if self.terminal_verified {
            return Ok(true);
        }
        let (code, status) = self
            .exit
            .ok_or(MacError::Rejected("holder waitid event absent"))?;
        require(
            self.waited_pid == Some(self.pid),
            "original host holder waitid identity",
        )?;
        let raw = crate::production_activation_protocol::raw_wait_status(code, status)
            .ok_or(MacError::Rejected("original holder native wait status"))?;
        let mut info = crate::production_activation_protocol::PidfdInfo::request_exit();
        zero(unsafe {
            libc::ioctl(
                self.pidfd()?.as_raw_fd(),
                crate::production_activation_protocol::PIDFD_GET_INFO as libc::c_ulong,
                &mut info,
            )
        } as libc::c_long)?;
        require(
            info.mask & crate::production_activation_protocol::PIDFD_INFO_EXIT != 0
                && info.exit_code == raw,
            "original reaped holder PIDFD exit information differs",
        )?;
        self.terminal_verified = true;
        Ok(true)
    }

    fn retire(&mut self) -> Result<()> {
        self.same_thread()?;
        if self.child.is_none() || self.reap()? {
            self.channel.take();
            return Ok(());
        }
        let end = *self
            .retirement_end
            .get_or_insert_with(|| Instant::now() + RETIRE_LIMIT);
        let rc = unsafe {
            libc::syscall(
                libc::SYS_pidfd_send_signal,
                self.pidfd()?.as_raw_fd(),
                libc::SIGKILL,
                std::ptr::null::<libc::siginfo_t>(),
                0_u32,
            )
        };
        if rc != 0 && io::Error::last_os_error().raw_os_error() != Some(libc::ESRCH) {
            return Err(io::Error::last_os_error().into());
        }
        loop {
            if self.reap()? {
                self.channel.take();
                return Ok(());
            }
            require(
                Instant::now() < end,
                "original host holder retirement deadline",
            )?;
            let mut p = libc::pollfd {
                fd: self.pidfd()?.as_raw_fd(),
                events: libc::POLLIN,
                revents: 0,
            };
            let rc = unsafe { libc::poll(&mut p, 1, 20) };
            if rc < 0 && io::Error::last_os_error().raw_os_error() != Some(libc::EINTR) {
                return Err(io::Error::last_os_error().into());
            }
        }
    }
}

impl Drop for Holder {
    fn drop(&mut self) {
        if self.child.is_some() && self.exit.is_none() {
            if let Some(child) = self.child.take() {
                std::mem::forget(child);
            }
            if let Some(channel) = self.channel.take() {
                std::mem::forget(channel);
            }
        }
    }
}

const fn ins(code: u16, k: u32) -> libc::sock_filter {
    libc::sock_filter {
        code,
        jt: 0,
        jf: 0,
        k,
    }
}
const fn jump(k: u32, jt: u8, jf: u8) -> libc::sock_filter {
    libc::sock_filter {
        code: 0x15,
        jt,
        jf,
        k,
    }
}
const PARK_FILTER: [libc::sock_filter; 18] = [
    ins(0x20, 4),
    jump(0xc000_003e, 1, 0),
    ins(0x06, 0x8000_0000),
    ins(0x20, 0),
    jump(libc::SYS_poll as u32, 0, 1),
    ins(0x06, 0x7fff_0000),
    jump(libc::SYS_clock_gettime as u32, 0, 1),
    ins(0x06, 0x7fff_0000),
    jump(libc::SYS_exit_group as u32, 0, 1),
    ins(0x06, 0x7fff_0000),
    jump(libc::SYS_recvfrom as u32, 1, 0),
    jump(libc::SYS_sendto as u32, 0, 5),
    ins(0x20, 20),
    jump(0, 0, 3),
    ins(0x20, 16),
    jump(CHILD_CHANNEL as u32, 0, 1),
    ins(0x06, 0x7fff_0000),
    ins(0x06, 0x8000_0000),
];

unsafe fn child_exit(code: i32) -> ! {
    unsafe {
        libc::syscall(libc::SYS_exit_group, code);
    }
    // exit_group cannot return on the supported kernel. Do not unwind or run
    // inherited Rust destructors in the post-clone child.
    loop {
        std::hint::spin_loop();
    }
}

unsafe fn child_live(end: Option<u64>) -> bool {
    unsafe {
        let mut p = libc::pollfd {
            fd: CHILD_CREATOR,
            events: libc::POLLIN,
            revents: 0,
        };
        if libc::syscall(libc::SYS_poll, &mut p, 1, 0) != 0 || p.revents != 0 {
            return false;
        }
        if let Some(end) = end {
            let mut now: libc::timespec = std::mem::zeroed();
            if libc::syscall(libc::SYS_clock_gettime, libc::CLOCK_MONOTONIC, &mut now) != 0 {
                return false;
            }
            let Some(n) = u64::try_from(now.tv_sec)
                .ok()
                .and_then(|v| v.checked_mul(1_000_000_000))
                .and_then(|v| v.checked_add(u64::try_from(now.tv_nsec).ok()?))
            else {
                return false;
            };
            if n >= end {
                return false;
            }
        }
        true
    }
}

unsafe fn child_send(phase: u32, end: u64) {
    unsafe {
        let packet = Reply {
            magic: MAGIC,
            phase,
            errno: 0,
            reserved: 0,
        };
        loop {
            if !child_live(Some(end)) {
                child_exit(125);
            }
            let n = libc::syscall(
                libc::SYS_sendto,
                CHILD_CHANNEL,
                &packet,
                std::mem::size_of::<Reply>(),
                libc::MSG_NOSIGNAL | libc::MSG_DONTWAIT,
                std::ptr::null::<libc::sockaddr>(),
                0,
            );
            if n == std::mem::size_of::<Reply>() as i64 {
                return;
            }
            if n >= 0
                || (*libc::__errno_location() != libc::EAGAIN
                    && *libc::__errno_location() != libc::EINTR)
            {
                child_exit(125);
            }
            let mut p = libc::pollfd {
                fd: CHILD_CHANNEL,
                events: libc::POLLOUT,
                revents: 0,
            };
            libc::syscall(libc::SYS_poll, &mut p, 1, 20);
        }
    }
}

unsafe fn child_main(
    channel: RawFd,
    creator: RawFd,
    parent: i32,
    end: u64,
    reduce: bool,
    forbidden_probe: bool,
) -> ! {
    unsafe {
        let a = libc::syscall(libc::SYS_fcntl, channel, libc::F_DUPFD_CLOEXEC, 10);
        let b = libc::syscall(libc::SYS_fcntl, creator, libc::F_DUPFD_CLOEXEC, 10);
        if a < 0
            || b < 0
            || libc::syscall(libc::SYS_dup3, a, CHILD_CHANNEL, libc::O_CLOEXEC) < 0
            || libc::syscall(libc::SYS_dup3, b, CHILD_CREATOR, libc::O_CLOEXEC) < 0
            || libc::syscall(libc::SYS_close_range, 0_u32, 2_u32, 0_u32) != 0
            || libc::syscall(libc::SYS_close_range, 5_u32, u32::MAX, 0_u32) != 0
        {
            child_exit(125);
        }
        if reduce {
            // No mapping is installed and the child never changes UID/GID.
            // Its new-userns capabilities only permit dropping every set.
            if libc::syscall(libc::SYS_prctl, 47, 4, 0, 0, 0) != 0 {
                child_exit(125);
            }
            for cap in 0..64_i32 {
                if libc::syscall(libc::SYS_prctl, libc::PR_CAPBSET_DROP, cap, 0, 0, 0) != 0 {
                    if *libc::__errno_location() == libc::EINVAL {
                        break;
                    }
                    child_exit(125);
                }
            }
            let header = [0x2008_0522_u32, 0];
            let data = [0_u32; 6];
            if libc::syscall(libc::SYS_capset, header.as_ptr(), data.as_ptr()) != 0 {
                child_exit(125);
            }
        }
        if libc::syscall(libc::SYS_prctl, libc::PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0
            || libc::syscall(
                libc::SYS_prctl,
                libc::PR_SET_PDEATHSIG,
                libc::SIGKILL,
                0,
                0,
                0,
            ) != 0
            || libc::syscall(libc::SYS_getppid) != parent as i64
            || !child_live(Some(end))
        {
            child_exit(125);
        }
        // The forbidden-syscall ordinary fixture must not create a core file.
        if forbidden_probe && libc::syscall(libc::SYS_prctl, libc::PR_SET_DUMPABLE, 0, 0, 0, 0) != 0
        {
            child_exit(125);
        }
        let mut program = libc::sock_fprog {
            len: PARK_FILTER.len() as u16,
            filter: PARK_FILTER.as_ptr() as *mut libc::sock_filter,
        };
        if libc::syscall(libc::SYS_seccomp, 1_u32, 0_u32, &mut program) != 0 {
            child_exit(125);
        }
        if forbidden_probe {
            libc::syscall(libc::SYS_getpid);
            child_exit(126);
        }
        child_send(READY, end);
        loop {
            if !child_live(Some(end)) {
                child_exit(125);
            }
            let mut packet = [0_u8; 2];
            let n = libc::syscall(
                libc::SYS_recvfrom,
                CHILD_CHANNEL,
                packet.as_mut_ptr(),
                packet.len(),
                libc::MSG_DONTWAIT | libc::MSG_TRUNC,
                std::ptr::null::<libc::sockaddr>(),
                std::ptr::null::<libc::socklen_t>(),
            );
            if n == 1 && packet[0] == RELEASE {
                break;
            }
            if n >= 0
                || (*libc::__errno_location() != libc::EAGAIN
                    && *libc::__errno_location() != libc::EINTR)
            {
                child_exit(125);
            }
            let mut p = libc::pollfd {
                fd: CHILD_CHANNEL,
                events: libc::POLLIN,
                revents: 0,
            };
            libc::syscall(libc::SYS_poll, &mut p, 1, 20);
        }
        child_send(PARKED, end);
        // Successful creation ends the setup timer, not the connection's
        // lifetime. This holder only parks until its original owner retires.
        loop {
            if !child_live(None) {
                child_exit(125);
            }
            let mut p = libc::pollfd {
                fd: CHILD_CHANNEL,
                events: libc::POLLIN,
                revents: 0,
            };
            let n = libc::syscall(libc::SYS_poll, &mut p, 1, 100);
            if n < 0 && *libc::__errno_location() != libc::EINTR {
                child_exit(125);
            }
            if n > 0 {
                child_exit(125);
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::mpsc;

    // The ordinary fixtures create no namespace or MAC authority. They use
    // the same raw child barrier/filter/park/reaper with CLONE_PIDFD only.
    struct Child(Holder);
    impl Child {
        fn new(duration: Duration) -> Self {
            Self(Holder::prepare(Instant::now() + duration).unwrap())
        }
    }
    impl Drop for Child {
        fn drop(&mut self) {
            if self.0.retire().is_err() {
                // An uncertain live child cannot be silently detached by a
                // failing test. The process supervisor observes this failure.
                std::process::abort();
            }
        }
    }
    fn readable(fd: &File, end: Instant) {
        loop {
            let mut item = libc::pollfd {
                fd: fd.as_raw_fd(),
                events: libc::POLLIN,
                revents: 0,
            };
            let rc = unsafe { libc::poll(&mut item, 1, 10) };
            assert!(rc >= 0 || io::Error::last_os_error().raw_os_error() == Some(libc::EINTR));
            if rc > 0 {
                assert_ne!(item.revents & libc::POLLIN, 0);
                assert_eq!(item.revents & !(libc::POLLIN | libc::POLLHUP), 0);
                return;
            }
            assert!(
                Instant::now() < end,
                "original PIDFD did not become readable"
            );
        }
    }
    fn no_waitable_child(fd: &File) {
        let mut info: libc::siginfo_t = unsafe { std::mem::zeroed() };
        let rc = unsafe {
            libc::waitid(
                libc::P_PIDFD,
                fd.as_raw_fd() as u32,
                &mut info,
                libc::WEXITED | libc::WNOHANG,
            )
        };
        assert_eq!(rc, -1);
        assert_eq!(
            io::Error::last_os_error().raw_os_error(),
            Some(libc::ECHILD)
        );
    }
    #[test]
    fn original_host_holder_park_outlives_setup_deadline_and_retires_its_pidfd() {
        let mut child = Child::new(Duration::from_secs(3));
        child
            .0
            .spawn_inner(libc::CLONE_PIDFD as u64, false, false)
            .unwrap();
        child.0.receive(READY).unwrap();
        child.0.release().unwrap();
        child.0.receive(PARKED).unwrap();
        let end = child.0.deadline + Duration::from_millis(25);
        if let Some(left) = end.checked_duration_since(Instant::now()) {
            std::thread::sleep(left);
        }
        alive(child.0.pidfd().unwrap()).unwrap();
        child.0.retire().unwrap();
        assert!(child.0.terminal_verified);
        assert_eq!(child.0.exit, Some((libc::CLD_KILLED, libc::SIGKILL)));
        no_waitable_child(child.0.pidfd().unwrap());
    }
    #[test]
    fn original_unreleased_host_holder_expires_and_is_actually_reaped() {
        let mut child = Child::new(Duration::from_secs(3));
        child
            .0
            .spawn_inner(libc::CLONE_PIDFD as u64, false, false)
            .unwrap();
        child.0.receive(READY).unwrap();
        readable(child.0.pidfd().unwrap(), child.0.deadline + RETIRE_LIMIT);
        child.0.retire().unwrap();
        assert!(child.0.terminal_verified);
        assert_eq!(child.0.exit, Some((libc::CLD_EXITED, 125)));
        no_waitable_child(child.0.pidfd().unwrap());
    }
    #[test]
    fn actual_host_holder_filter_kills_an_unlisted_syscall() {
        let mut child = Child::new(Duration::from_secs(3));
        child
            .0
            .spawn_inner(libc::CLONE_PIDFD as u64, false, true)
            .unwrap();
        readable(child.0.pidfd().unwrap(), child.0.deadline);
        child.0.retire().unwrap();
        assert!(child.0.terminal_verified);
        assert!(matches!(
            child.0.exit,
            Some((libc::CLD_KILLED | libc::CLD_DUMPED, libc::SIGSYS))
        ));
        no_waitable_child(child.0.pidfd().unwrap());
    }

    // Only a test transfers the raw child handles across threads to observe
    // the original creator's death. No HostPeerNetworkOwner/issuer is moved.
    struct Transferred {
        child: Option<File>,
        creator: File,
        channel: Option<File>,
        pid: i32,
        creator_tid: i64,
        group: i32,
        exit: Option<(i32, i32)>,
    }
    impl Transferred {
        fn reap(&mut self, kill: bool) {
            if self.exit.is_some() {
                return;
            }
            let child = self.child.as_ref().unwrap();
            if kill {
                let rc = unsafe {
                    libc::syscall(
                        libc::SYS_pidfd_send_signal,
                        child.as_raw_fd(),
                        libc::SIGKILL,
                        std::ptr::null::<libc::siginfo_t>(),
                        0_u32,
                    )
                };
                assert!(rc == 0 || io::Error::last_os_error().raw_os_error() == Some(libc::ESRCH));
            }
            readable(child, Instant::now() + RETIRE_LIMIT);
            let mut info: libc::siginfo_t = unsafe { std::mem::zeroed() };
            assert_eq!(
                unsafe {
                    libc::waitid(
                        libc::P_PIDFD,
                        child.as_raw_fd() as u32,
                        &mut info,
                        libc::WEXITED | libc::WNOHANG,
                    )
                },
                0
            );
            let pid = unsafe { info.si_pid() };
            let observed = (info.si_code, unsafe { info.si_status() });
            self.exit = Some(observed);
            assert_eq!(pid, self.pid);
            let raw =
                crate::production_activation_protocol::raw_wait_status(observed.0, observed.1)
                    .unwrap();
            let mut final_info = crate::production_activation_protocol::PidfdInfo::request_exit();
            assert_eq!(
                unsafe {
                    libc::ioctl(
                        child.as_raw_fd(),
                        crate::production_activation_protocol::PIDFD_GET_INFO as libc::c_ulong,
                        &mut final_info,
                    )
                },
                0
            );
            assert_ne!(
                final_info.mask & crate::production_activation_protocol::PIDFD_INFO_EXIT,
                0
            );
            assert_eq!(final_info.exit_code, raw);
            no_waitable_child(child);
            self.channel.take();
        }
    }
    impl Drop for Transferred {
        fn drop(&mut self) {
            if self.exit.is_none() {
                // The assertion body always runs after the original handles
                // are stored here, so a failure still kills/reaps this child.
                self.reap(true);
            }
        }
    }
    #[test]
    fn original_nonleader_creator_death_kills_host_holder_while_group_lives() {
        let (send, receive) = mpsc::sync_channel(0);
        let (release, wait_release) = mpsc::sync_channel(0);
        let thread = std::thread::spawn(move || {
            let mut child = Child::new(Duration::from_secs(3));
            child
                .0
                .spawn_inner(libc::CLONE_PIDFD as u64, false, false)
                .unwrap();
            child.0.receive(READY).unwrap();
            let original = Transferred {
                child: child.0.child.take(),
                creator: child.0.creator_pidfd.try_clone().unwrap(),
                channel: child.0.channel.take(),
                pid: child.0.pid,
                creator_tid: child.0.creator,
                group: child.0.parent,
                exit: None,
            };
            send.send(original).unwrap();
            wait_release.recv().unwrap();
            // The child is still at its original post-PDEATHSIG READY
            // barrier. Exiting this actual nonleader task must kill it.
        });
        let mut original = receive.recv_timeout(Duration::from_secs(3)).unwrap();
        assert_eq!(original.group, unsafe { libc::getpid() });
        assert_ne!(original.creator_tid, unsafe {
            libc::syscall(libc::SYS_gettid)
        });
        assert_ne!(original.creator_tid, original.group as i64);
        alive(&original.creator).unwrap();
        alive(original.child.as_ref().unwrap()).unwrap();
        release.send(()).unwrap();
        thread.join().unwrap();
        // clear_child_tid/join precedes the creator's final PIDFD event on
        // Linux; observe that actual event within the original fixed bound.
        readable(&original.creator, Instant::now() + RETIRE_LIMIT);
        original.reap(false);
        assert_eq!(original.exit, Some((libc::CLD_KILLED, libc::SIGKILL)));
        assert_eq!(original.group, unsafe { libc::getpid() });
    }
}
