//! Fixed application commands borrowed from the actual early Android owner.
//! Numeric process names only bind already-held pidfds or observe framework
//! lineage; no request may supply a namespace, executable, root or command.
use super::{EarlyBaseAdmission, identity, info, live, pidfd};
use crate::control::application_probe::RuntimeEpoch;
use crate::production_application::{ApplicationWorkerAuthority, QueryProjection};
use crate::production_cgroup::{ApplicationLeaf, PreparedCgroup};
use crate::production_execution::RuntimeMacOwner;
use crate::production_namespace::NamespaceError;
use crate::production_readiness::{BootProperty, read_boot_complete};
use crate::production_runtime_assets::EarlyQueryResources;
use std::ffi::{CStr, CString};
use std::fs::File;
use std::io::{self, Read};
use std::os::fd::{AsFd, AsRawFd, FromRawFd, OwnedFd};
use std::os::unix::fs::MetadataExt;
use std::time::Instant;

type Result<T> = std::result::Result<T, NamespaceError>;
fn external(e: impl std::fmt::Display) -> NamespaceError {
    NamespaceError::RuntimeResource(e.to_string())
}
fn require(value: bool, why: &'static str) -> Result<()> {
    if value {
        Ok(())
    } else {
        Err(NamespaceError::Rejected(why))
    }
}
fn open(parent: &File, name: &CStr, directory: bool) -> io::Result<File> {
    let raw = unsafe {
        libc::openat(
            parent.as_raw_fd(),
            name.as_ptr(),
            libc::O_RDONLY
                | libc::O_NOFOLLOW
                | libc::O_CLOEXEC
                | libc::O_NONBLOCK
                | if directory { libc::O_DIRECTORY } else { 0 },
        )
    };
    if raw < 0 {
        Err(io::Error::last_os_error())
    } else {
        Ok(unsafe { File::from_raw_fd(raw) })
    }
}
fn proc_link(parent: &File, name: &CStr) -> io::Result<File> {
    let raw = unsafe {
        libc::openat(
            parent.as_raw_fd(),
            name.as_ptr(),
            libc::O_RDONLY | libc::O_CLOEXEC,
        )
    };
    if raw < 0 {
        Err(io::Error::last_os_error())
    } else {
        Ok(unsafe { File::from_raw_fd(raw) })
    }
}
fn fs_kind(file: &File, expected: libc::c_long) -> Result<()> {
    let mut st: libc::statfs = unsafe { std::mem::zeroed() };
    if unsafe { libc::fstatfs(file.as_raw_fd(), &mut st) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    require(
        st.f_type == expected,
        "early application descriptor filesystem differs",
    )
}
fn proc_bytes(parent: &File, name: &CStr) -> Result<Vec<u8>> {
    let file = open(parent, name, false)?;
    fs_kind(&file, libc::PROC_SUPER_MAGIC)?;
    let mut bytes = Vec::new();
    file.take(16385).read_to_end(&mut bytes)?;
    require(
        bytes.len() <= 16384,
        "early application proc evidence exceeded bound",
    )?;
    Ok(bytes)
}
fn proc_text(parent: &File, name: &CStr) -> Result<String> {
    String::from_utf8(proc_bytes(parent, name)?).map_err(external)
}
const NS_NAMES: [(&CStr, i32); 6] = [
    (c"ns/mnt", libc::CLONE_NEWNS),
    (c"ns/pid", libc::CLONE_NEWPID),
    (c"ns/ipc", libc::CLONE_NEWIPC),
    (c"ns/uts", libc::CLONE_NEWUTS),
    (c"ns/net", libc::CLONE_NEWNET),
    (c"ns/cgroup", libc::CLONE_NEWCGROUP),
];
fn ns_type(file: &File, kind: i32) -> Result<()> {
    fs_kind(file, 0x6e736673)?;
    let actual = unsafe { libc::ioctl(file.as_raw_fd(), 0xb703 as libc::c_ulong) };
    require(actual == kind, "early application namespace type differs")
}
fn ns_owner(file: &File, userns: &File) -> Result<()> {
    let raw = unsafe { libc::ioctl(file.as_raw_fd(), 0xb701 as libc::c_ulong) };
    if raw < 0 {
        return Err(io::Error::last_os_error().into());
    }
    let owner = unsafe { File::from_raw_fd(raw) };
    require(
        identity(&owner)? == identity(userns)?,
        "early application namespace has another owner",
    )
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
struct Process {
    pid: u32,
    parent: u32,
    start: u64,
}
fn parse_process(text: &str, pid: u32) -> Result<Process> {
    let (number, rest) = text
        .split_once(" (")
        .ok_or(NamespaceError::Rejected("process stat lacks PID"))?;
    let (_, tail) = rest
        .rsplit_once(") ")
        .ok_or(NamespaceError::Rejected("process stat lacks fields"))?;
    let fields: Vec<_> = tail.split_ascii_whitespace().collect();
    require(
        number.parse::<u32>().ok() == Some(pid) && fields.len() >= 20,
        "process stat identity or length differs",
    )?;
    require(
        !matches!(fields[0], "Z" | "X" | "x"),
        "process has exited and is awaiting reaping",
    )?;
    let parent = fields[1].parse::<u32>().map_err(external)?;
    let start = fields[19].parse::<u64>().map_err(external)?;
    require(pid > 0 && start > 0, "process stat lacks a live birth time")?;
    Ok(Process { pid, parent, start })
}
fn process(parent: &File, pid: u32) -> Result<Process> {
    parse_process(&proc_text(parent, c"stat")?, pid)
}
fn credentials(directory: &File, uid: u32, gid: u32) -> Result<()> {
    let text = proc_text(directory, c"status")?;
    for (prefix, expected) in [("Uid:", uid), ("Gid:", gid)] {
        let rows: Vec<_> = text
            .lines()
            .filter_map(|line| line.strip_prefix(prefix))
            .collect();
        require(
            rows.len() == 1,
            "process credential field missing or duplicated",
        )?;
        let values = rows[0]
            .split_ascii_whitespace()
            .map(str::parse::<u32>)
            .collect::<std::result::Result<Vec<_>, _>>()
            .map_err(external)?;
        require(
            values == [expected; 4],
            "process credentials differ from the original mapped role",
        )?;
    }
    Ok(())
}
fn valid_chain(init: Process, zygote: Process, framework: Process) -> bool {
    init.pid != zygote.pid
        && zygote.pid != framework.pid
        && init.pid != framework.pid
        && zygote.parent == init.pid
        && framework.parent == zygote.pid
        && init.start < zygote.start
        && zygote.start < framework.start
}
fn payload_member(directory: &File) -> Result<()> {
    let group = proc_text(directory, c"cgroup")?;
    let prefix = "0::/system.slice/droidloom-production.service/cell-u1000/payload/";
    require(
        group.starts_with(prefix)
            && group.lines().count() == 1
            && !group
                .trim_end_matches('\n')
                .split('/')
                .skip(1)
                .any(|part| part.is_empty() || part == "." || part == ".."),
        "framework process left the original Android payload",
    )
}

/// This owner can only borrow the existing reservation, budget, exact root and
/// private immutable query roles; it cannot manufacture a new Android lifetime.
pub(crate) struct EarlyApplicationAuthority<'a> {
    base: &'a EarlyBaseAdmission<'a>,
    group: &'a PreparedCgroup,
    owner: &'a RuntimeMacOwner,
    root: &'a File,
    query: &'a EarlyQueryResources,
    proc_root: File,
    namespaces: Vec<File>,
    init: Process,
    init_program: File,
    device: File,
    progress: &'a dyn Fn() -> io::Result<()>,
}
pub(crate) struct EarlyFrameworkObservation {
    directory: File,
    node: (u64, u64),
    framework: Process,
    framework_pidfd: File,
    zygote_directory: File,
    zygote_node: (u64, u64),
    zygote: Process,
    zygote_pidfd: File,
    init: Process,
    init_pidfd: (u64, u64),
    epoch: RuntimeEpoch,
}
impl<'a> EarlyApplicationAuthority<'a> {
    pub(crate) fn acquire(
        base: &'a EarlyBaseAdmission<'a>,
        group: &'a PreparedCgroup,
        owner: &'a RuntimeMacOwner,
        root: &'a File,
        query: &'a EarlyQueryResources,
        progress: &'a dyn Fn() -> io::Result<()>,
    ) -> Result<Self> {
        base.revalidate()?;
        group
            .revalidate_early_member(base, owner)
            .map_err(external)?;
        let proc_root = File::open("/proc")?;
        fs_kind(&proc_root, libc::PROC_SUPER_MAGIC)?;
        let mut namespaces = Vec::new();
        for (name, kind) in NS_NAMES {
            let held = proc_link(base.proc_directory(), name)?;
            ns_type(&held, kind)?;
            ns_owner(&held, base.user_namespace())?;
            namespaces.push(held);
        }
        require(
            identity(&namespaces[0])? == identity(base.board().mount_namespace())?
                && identity(&namespaces[1])? == identity(base.board().pid_namespace())?,
            "application namespaces differ from the original early pins",
        )?;
        let system = open(root, c"system", true)?;
        let bin = open(&system, c"bin", true)?;
        let init_program = open(&bin, c"init", false)?;
        let device = open(root, c"dev", true)?;
        fs_kind(&device, libc::TMPFS_MAGIC)?;
        let init = process(base.proc_directory(), base.board().host_pid() as u32)?;
        let this = Self {
            base,
            group,
            owner,
            root,
            query,
            proc_root,
            namespaces,
            init,
            init_program,
            device,
            progress,
        };
        // Original init may still be crossing exec. Construction binds the
        // selected image; an actual command additionally requires current exec
        // identity, boot property and original framework lineage below.
        this.revalidate()?;
        Ok(this)
    }
    pub(crate) fn revalidate(&self) -> Result<()> {
        self.base.revalidate()?;
        self.group
            .revalidate_early_member(self.base, self.owner)
            .map_err(external)?;
        self.query.revalidate(self.base).map_err(external)?;
        require(
            process(self.base.proc_directory(), self.init.pid)? == self.init,
            "early application original init birth changed",
        )?;
        for ((name, kind), held) in NS_NAMES.into_iter().zip(&self.namespaces) {
            let actual = proc_link(self.base.proc_directory(), name)?;
            ns_type(held, kind)?;
            require(
                identity(&actual)? == identity(held)?,
                "original application namespace changed",
            )?;
        }
        require(
            identity(&self.device)? == identity(&open(self.root, c"dev", true)?)?,
            "early application private device mount changed",
        )?;
        self.base.board().revalidate()?;
        Ok(())
    }
    pub(crate) fn host_pid(&self) -> u32 {
        self.init.pid
    }
    pub(crate) fn host_uid(&self) -> u32 {
        self.base.board().selection().spec().host_uid
    }
    fn executed(&self) -> Result<()> {
        self.revalidate()?;
        let actual = proc_link(self.base.proc_directory(), c"exe")?;
        let root = proc_link(self.base.proc_directory(), c"root")?;
        require(
            identity(&actual)? == identity(&self.init_program)?
                && identity(&root)? == identity(self.root)?,
            "early application requires the actual original init executable and root",
        )?;
        self.revalidate()
    }
    pub(crate) fn ready(&self) -> Result<()> {
        self.executed()?;
        let property_dir = open(&self.device, c"__properties__", true)?;
        fs_kind(&property_dir, libc::TMPFS_MAGIC)?;
        let (uid, gid) = self.mapped_root()?;
        let m = property_dir.metadata()?;
        require(
            m.uid() == uid && m.gid() == gid && m.mode() & 0o6022 == 0,
            "early private property directory custody differs",
        )?;
        let file = open(&property_dir, c"u:object_r:boot_status_prop:s0", false)?;
        fs_kind(&file, libc::TMPFS_MAGIC)?;
        require(
            read_boot_complete(&file, uid, gid).map_err(external)? == BootProperty::Complete,
            "early application operation requires current Android boot completion",
        )?;
        self.executed()
    }
    fn same_guest(&self, directory: &File) -> Result<bool> {
        for (name, held) in [
            (c"ns/user", self.base.user_namespace()),
            (c"ns/pid", self.base.board().pid_namespace()),
        ] {
            let actual = proc_link(directory, name)?;
            fs_kind(&actual, 0x6e736673)?;
            if identity(&actual)? != identity(held)? {
                return Ok(false);
            }
        }
        Ok(true)
    }
    fn process_dir(&self, pid: u32) -> Result<File> {
        let name = CString::new(pid.to_string()).map_err(external)?;
        let directory = open(&self.proc_root, &name, true)?;
        fs_kind(&directory, libc::PROC_SUPER_MAGIC)?;
        Ok(directory)
    }
    fn verify_framework_processes(&self, held: &EarlyFrameworkObservation) -> Result<()> {
        live(held.framework_pidfd.as_fd())?;
        live(held.zygote_pidfd.as_fd())?;
        self.ready()?;
        for (descriptor, expected) in [
            (&held.framework_pidfd, held.framework),
            (&held.zygote_pidfd, held.zygote),
        ] {
            let actual = info(descriptor.as_fd(), false)?;
            require(
                actual.pid == expected.pid
                    && actual.tgid == expected.pid
                    && actual.ppid == expected.parent,
                "held framework pidfd no longer identifies the original observed task",
            )?;
        }
        let (uid, gid) = self.mapped_root()?;
        require(
            held.init == self.init
                && held.init_pidfd == identity(self.base.board().pidfd())?
                && valid_chain(self.init, held.zygote, held.framework)
                && identity(&held.directory)? == held.node
                && identity(&held.zygote_directory)? == held.zygote_node
                && process(&held.directory, held.framework.pid)? == held.framework
                && process(&held.zygote_directory, held.zygote.pid)? == held.zygote
                && proc_bytes(&held.directory, c"comm")? == b"system_server\n"
                && matches!(
                    proc_bytes(&held.zygote_directory, c"comm")?.as_slice(),
                    b"zygote\n" | b"zygote64\n"
                )
                && self.same_guest(&held.directory)?
                && self.same_guest(&held.zygote_directory)?,
            "original early init/zygote/system_server lineage changed",
        )?;
        credentials(
            &held.directory,
            uid.checked_add(1000)
                .ok_or(NamespaceError::Rejected("framework UID overflow"))?,
            gid.checked_add(1000)
                .ok_or(NamespaceError::Rejected("framework GID overflow"))?,
        )?;
        credentials(&held.zygote_directory, uid, gid)?;
        payload_member(&held.directory)?;
        for (pid, node) in [
            (held.framework.pid, held.node),
            (held.zygote.pid, held.zygote_node),
        ] {
            require(
                identity(&self.process_dir(pid)?)? == node,
                "framework proc name was replaced",
            )?;
        }
        require(
            held.epoch.boot_id == self.base.board().generation.birth.boot_id
                && held.epoch.cell_host_pid == self.init.pid
                && held.epoch.framework_host_pid == held.framework.pid
                && held.epoch.framework_start_ticks == held.framework.start,
            "framework epoch differs from the original early generation",
        )?;
        self.ready()?;
        live(held.framework_pidfd.as_fd())?;
        live(held.zygote_pidfd.as_fd())?;
        Ok(())
    }
    pub(crate) fn observe_framework(&self) -> Result<EarlyFrameworkObservation> {
        self.ready()?;
        let mut found = None;
        let mut count = 0usize;
        for entry in std::fs::read_dir(format!("/proc/self/fd/{}", self.proc_root.as_raw_fd()))? {
            let entry = entry?;
            let Some(name) = entry.file_name().to_str().map(str::to_owned) else {
                continue;
            };
            if name.is_empty() || !name.bytes().all(|v| v.is_ascii_digit()) {
                continue;
            }
            count += 1;
            require(count <= 131072, "bounded host process inventory exceeded")?;
            let pid = name.parse::<u32>().map_err(external)?;
            let observed = (|| -> Result<Option<EarlyFrameworkObservation>> {
                let directory = self.process_dir(pid)?;
                if proc_bytes(&directory, c"comm")? != b"system_server\n"
                    || !self.same_guest(&directory)?
                {
                    return Ok(None);
                }
                let framework = process(&directory, pid)?;
                let zygote_directory = self.process_dir(framework.parent)?;
                let zygote = process(&zygote_directory, framework.parent)?;
                require(
                    valid_chain(self.init, zygote, framework)
                        && self.same_guest(&zygote_directory)?,
                    "framework observation is outside the original early lineage",
                )?;
                // These are liveness observations of the lineage already bound
                // above. They never become signal or execution capabilities.
                let framework_pidfd = pidfd(framework.pid as i32)?;
                let zygote_pidfd = pidfd(zygote.pid as i32)?;
                let held = EarlyFrameworkObservation {
                    node: identity(&directory)?,
                    directory,
                    framework,
                    framework_pidfd,
                    zygote_node: identity(&zygote_directory)?,
                    zygote_directory,
                    zygote,
                    zygote_pidfd,
                    init: self.init,
                    init_pidfd: identity(self.base.board().pidfd())?,
                    epoch: RuntimeEpoch {
                        boot_id: self.base.board().generation.birth.boot_id.clone(),
                        cell_host_pid: self.init.pid,
                        framework_host_pid: pid,
                        framework_start_ticks: framework.start,
                    },
                };
                self.verify_framework_processes(&held)?;
                Ok(Some(held))
            })();
            match observed {
                Ok(Some(held)) => {
                    require(
                        found.is_none(),
                        "multiple original early system_server processes",
                    )?;
                    found = Some(held);
                }
                Ok(None) => {}
                Err(NamespaceError::Io(e))
                    if matches!(e.raw_os_error(), Some(libc::ENOENT | libc::ESRCH)) => {}
                Err(e) => return Err(e),
            }
        }
        let held = found.ok_or(NamespaceError::Rejected(
            "original early Android system_server is absent",
        ))?;
        self.verify_framework_processes(&held)?;
        Ok(held)
    }
    pub(crate) fn epoch(&self, held: &EarlyFrameworkObservation) -> Result<RuntimeEpoch> {
        self.verify_framework_processes(held)?;
        Ok(held.epoch.clone())
    }
}
impl ApplicationWorkerAuthority for EarlyApplicationAuthority<'_> {
    fn query_projection(&self) -> QueryProjection {
        QueryProjection::EarlyDev
    }
    fn revalidate(&self) -> Result<()> {
        self.revalidate()
    }
    fn descriptors(&self, binary: &CStr) -> Result<Vec<File>> {
        self.ready()?;
        let [copy, original] = self
            .query
            .descriptors(self.base, self.root, binary)
            .map_err(external)?;
        let raw = unsafe { libc::syscall(libc::SYS_pidfd_open, libc::getpid(), 0u32) };
        if raw < 0 {
            return Err(io::Error::last_os_error().into());
        }
        let parent = unsafe { File::from_raw_fd(raw as i32) };
        let mut files = vec![
            self.base.board().pidfd().try_clone()?,
            parent,
            self.root.try_clone()?,
            self.base.user_namespace().try_clone()?,
        ];
        for namespace in &self.namespaces {
            files.push(namespace.try_clone()?);
        }
        files.extend([copy, original]);
        self.ready()?;
        Ok(files)
    }
    fn contacts_content_descriptors(&self) -> Result<[File; 2]> {
        self.ready()?;
        let out = self.query.content(self.base, self.root).map_err(external)?;
        self.ready()?;
        Ok(out)
    }
    fn mapped_root(&self) -> Result<(u32, u32)> {
        let (uid, gid) = self.base.identity_lease().broker_ranges();
        Ok((uid.start, gid.start))
    }
    fn leaf(&self) -> Result<ApplicationLeaf<'_>> {
        self.ready()?;
        self.group
            .early_application_leaf(self.base, self.owner)
            .map_err(external)
    }
    fn bind_created_process(&self, pidfd: &OwnedFd, query: bool) -> Result<(File, u32)> {
        self.revalidate()?;
        live(pidfd.as_fd())?;
        let observed = info(pidfd.as_fd(), true)?;
        require(
            observed.pid == observed.tgid
                && observed.ppid == std::process::id()
                && observed.pid != self.init.pid,
            "application pidfd is not this broker's direct child",
        )?;
        // The query is parked before USER setns and credential changes. Only
        // its PID namespace is already the selected Android namespace.
        let (uid, gid) = (0, 0);
        require(
            [observed.ruid, observed.euid, observed.suid, observed.fsuid] == [uid; 4]
                && [observed.rgid, observed.egid, observed.sgid, observed.fsgid] == [gid; 4],
            "created application process credentials differ",
        )?;
        let directory = self.process_dir(observed.pid)?;
        require(
            process(&directory, observed.pid)?.parent == std::process::id(),
            "created application child parent changed",
        )?;
        if query {
            let own = self.process_dir(std::process::id())?;
            require(
                identity(&proc_link(&directory, c"ns/user")?)?
                    == identity(&proc_link(&own, c"ns/user")?)?,
                "parked query changed its original host user namespace",
            )?;
            for ((name, _), held) in NS_NAMES.into_iter().zip(&self.namespaces) {
                let expected = if name == c"ns/pid" {
                    held.try_clone()?
                } else {
                    proc_link(&own, name)?
                };
                require(
                    identity(&proc_link(&directory, name)?)? == identity(&expected)?,
                    "parked query has changed namespace before its original trace owner",
                )?;
            }
        }
        live(pidfd.as_fd())?;
        self.revalidate()?;
        Ok((directory, observed.pid))
    }
    fn progress_inherited_native(&self, deadline: Instant) -> Result<()> {
        // Kernel-first Android has no inherited legacy seccomp-notify channel.
        // The callback services the same original frontend while commands run.
        require(
            Instant::now() < deadline,
            "early application progress deadline",
        )?;
        self.revalidate()?;
        (self.progress)()?;
        self.revalidate()?;
        require(
            Instant::now() < deadline,
            "early application progress exceeded deadline",
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn early_framework_stat_retains_kernel_birth_despite_parentheses_in_name() {
        let text = format!("31 (odd ) process) S 17 {} 12345 0\n", ["0"; 17].join(" "));
        assert_eq!(
            parse_process(&text, 31).unwrap(),
            Process {
                pid: 31,
                parent: 17,
                start: 12345
            }
        );
        assert!(parse_process(&text, 32).is_err());
        assert!(parse_process("31 (short) S 17", 31).is_err());
    }
    #[test]
    fn early_framework_chain_rejects_reparenting_and_birth_reuse() {
        let init = Process {
            pid: 31,
            parent: 1,
            start: 10,
        };
        let zygote = Process {
            pid: 32,
            parent: 31,
            start: 20,
        };
        let framework = Process {
            pid: 33,
            parent: 32,
            start: 30,
        };
        assert!(valid_chain(init, zygote, framework));
        assert!(!valid_chain(
            init,
            Process {
                parent: 1,
                ..zygote
            },
            framework
        ));
        assert!(!valid_chain(
            init,
            zygote,
            Process {
                parent: 31,
                ..framework
            }
        ));
        assert!(!valid_chain(
            init,
            Process {
                start: 30,
                ..zygote
            },
            framework
        ));
    }
    #[test]
    fn early_framework_zombie_cannot_pass_live_or_process_observation() {
        let mut child = std::process::Command::new("/bin/sleep")
            .arg("10")
            .spawn()
            .unwrap();
        let held = File::open(format!("/proc/{}", child.id())).unwrap();
        let original = pidfd(child.id() as i32).unwrap();
        live(original.as_fd()).unwrap();
        process(&held, child.id()).unwrap();
        child.kill().unwrap();
        let mut event = libc::pollfd {
            fd: original.as_raw_fd(),
            events: libc::POLLIN,
            revents: 0,
        };
        assert_eq!(unsafe { libc::poll(&mut event, 1, 2000) }, 1);
        assert!(live(original.as_fd()).is_err());
        assert!(process(&held, child.id()).is_err());
        child.wait().unwrap();
    }
    #[test]
    fn early_application_proc_helpers_observe_real_child_and_reject_regular_files() {
        let mut child = std::process::Command::new("/bin/sleep")
            .arg("10")
            .spawn()
            .unwrap();
        let held = File::open(format!("/proc/{}", child.id())).unwrap();
        let observed = process(&held, child.id()).unwrap();
        assert_eq!(observed.parent, std::process::id());
        credentials(&held, unsafe { libc::getuid() }, unsafe { libc::getgid() }).unwrap();
        let ordinary = tempfile::tempfile().unwrap();
        assert!(fs_kind(&ordinary, libc::PROC_SUPER_MAGIC).is_err());
        assert!(ns_type(&ordinary, libc::CLONE_NEWPID).is_err());
        child.kill().unwrap();
        child.wait().unwrap();
    }
}
