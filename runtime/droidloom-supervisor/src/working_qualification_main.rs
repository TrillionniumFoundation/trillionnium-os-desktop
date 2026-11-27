//! Retained local kernel bookends for the one opaque bootstrap Main.
//! Full normal Main RPCs remain at their original business bookends. This
//! component neither reads an account file nor opens an original/returned image.
use super::*;
use crate::control::MainCustodyObservation;
use crate::control::application_custody::CustodyNamespace;
use crate::main_custody::{MainProcessCustody, RuntimeMainCustody};

const NAMESPACES: [(&str, &CStr); 7] = [
    ("cgroup", c"ns/cgroup"),
    ("ipc", c"ns/ipc"),
    ("mount", c"ns/mnt"),
    ("net", c"ns/net"),
    ("pid", c"ns/pid"),
    ("user", c"ns/user"),
    ("uts", c"ns/uts"),
];

fn parent(text: &str) -> io::Result<u32> {
    let (_, fields) = text
        .rsplit_once(") ")
        .ok_or_else(|| io::Error::other("working Main stat parent absent"))?;
    fields
        .split_ascii_whitespace()
        .nth(1)
        .ok_or_else(|| io::Error::other("working Main stat parent absent"))?
        .parse()
        .map_err(io::Error::other)
}

struct Process {
    proc_root: File,
    directory: File,
    directory_identity: MainNodeIdentity,
    pidfd: File,
    pid: u32,
    start: u64,
    parent: u32,
    root: File,
    root_identity: MainNodeIdentity,
    executable: File,
    executable_identity: MainNodeIdentity,
    namespaces: Vec<(File, MainNodeIdentity)>,
}
impl Process {
    // Private: production callers select these only from the actual opaque Main.
    fn capture(pid: u32, start: u64) -> io::Result<Self> {
        let pidfd = file(unsafe { libc::syscall(libc::SYS_pidfd_open, pid, 0_u32) })?;
        live(&pidfd)?;
        let proc_root = File::open("/proc")?;
        fs_kind(&proc_root, libc::PROC_SUPER_MAGIC)?;
        let name = CString::new(pid.to_string()).map_err(io::Error::other)?;
        let directory = open_at(
            &proc_root,
            &name,
            libc::O_PATH | libc::O_DIRECTORY | libc::O_NOFOLLOW,
        )?;
        let directory_identity = identity(&directory)?;
        let stat = small(&directory, c"stat")?;
        birth(&stat, pid, start)?;
        let parent = parent(&stat)?;
        let root = open_at(&directory, c"root", libc::O_PATH | libc::O_DIRECTORY)?;
        let root_identity = identity(&root)?;
        let executable = open_at(&directory, c"exe", libc::O_PATH)?;
        let executable_identity = identity(&executable)?;
        let mut namespaces = Vec::new();
        for (_, name) in NAMESPACES {
            let namespace = open_at(&directory, name, libc::O_RDONLY)?;
            fs_kind(&namespace, 0x6e736673)?;
            let id = identity(&namespace)?;
            namespaces.push((namespace, id));
        }
        let value = Self {
            proc_root,
            directory,
            directory_identity,
            pidfd,
            pid,
            start,
            parent,
            root,
            root_identity,
            executable,
            executable_identity,
            namespaces,
        };
        value.guard()?;
        Ok(value)
    }
    fn require_process(&self, expected: &MainProcessCustody) -> io::Result<()> {
        require(
            self.pid == expected.host_pid
                && self.start == expected.start_ticks
                && self.parent == expected.parent_host_pid
                && identity(&self.pidfd)? == expected.pidfd
                && self.root_identity == expected.root
                && self.executable_identity == expected.executable,
            "working Main actual process differs from its authenticated observation",
        )?;
        self.guard()
    }
    fn require_namespaces(&self, expected: &[CustodyNamespace]) -> io::Result<()> {
        require(
            expected.len() == NAMESPACES.len(),
            "working Main namespace count differs",
        )?;
        for (((_, actual), (name, _)), expected) in
            self.namespaces.iter().zip(NAMESPACES).zip(expected)
        {
            require(
                expected.name == name
                    && (expected.device, expected.inode) == (actual.device, actual.inode),
                "working Main held namespace differs from its authenticated observation",
            )?;
        }
        self.guard()
    }
    fn guard(&self) -> io::Result<()> {
        live(&self.pidfd)?;
        let name = CString::new(self.pid.to_string()).map_err(io::Error::other)?;
        require(
            identity(&self.directory)? == self.directory_identity
                && identity(&open_at(
                    &self.proc_root,
                    &name,
                    libc::O_PATH | libc::O_DIRECTORY | libc::O_NOFOLLOW,
                )?)? == self.directory_identity,
            "working Main retained process directory changed",
        )?;
        let stat = small(&self.directory, c"stat")?;
        birth(&stat, self.pid, self.start)?;
        require(
            parent(&stat)? == self.parent
                && identity(&self.root)? == self.root_identity
                && identity(&open_at(
                    &self.directory,
                    c"root",
                    libc::O_PATH | libc::O_DIRECTORY,
                )?)? == self.root_identity
                && identity(&self.executable)? == self.executable_identity
                && identity(&open_at(&self.directory, c"exe", libc::O_PATH)?)?
                    == self.executable_identity,
            "working Main actual parent, root or executable changed",
        )?;
        for ((held, expected), (_, name)) in self.namespaces.iter().zip(NAMESPACES) {
            let named = open_at(&self.directory, name, libc::O_RDONLY)?;
            fs_kind(held, 0x6e736673)?;
            fs_kind(&named, 0x6e736673)?;
            require(
                identity(held)? == *expected && identity(&named)? == *expected,
                "working Main actual namespace changed",
            )?;
        }
        birth(&small(&self.directory, c"stat")?, self.pid, self.start)?;
        live(&self.pidfd)
    }
}

/// Only an actual Main token can mint this retained local resource observation.
/// No public constructor, Deserialize, caller path or reconstructed pass flag.
pub(crate) struct HeldWorkingMain {
    original_peer_pidfd: File,
    peer: Process,
    processes: [Process; 3],
    mounts: [File; 2],
    mount_roots: [MainMountRoot; 2],
    uid_map: Vec<IdMapRange>,
    gid_map: Vec<IdMapRange>,
    facts: RuntimeMainCustody,
}
impl HeldWorkingMain {
    pub(crate) fn capture(main: &MainCustodyObservation) -> io::Result<Self> {
        let facts = main.facts();
        facts.validate(&facts.epoch).map_err(io::Error::other)?;
        let original_peer_pidfd = main.retain_working_peer_pidfd().map_err(io::Error::other)?;
        let peer = Process::capture(main.peer().pid, main.peer().start_ticks)?;
        require(
            identity(&peer.pidfd)? == identity(&original_peer_pidfd)?,
            "working Main peer PIDFD differs from the actual original observation",
        )?;
        let manager = File::open(crate::normal_host_release::MANAGER)?;
        require(
            identity(&manager)? == peer.executable_identity,
            "working Main actual peer no longer uses the selected normal manager inode",
        )?;
        let init = Process::capture(facts.init.host_pid, facts.init.start_ticks)?;
        init.require_process(&facts.init)?;
        init.require_namespaces(&facts.owner.namespaces)?;
        let zygote = Process::capture(facts.zygote.host_pid, facts.zygote.start_ticks)?;
        zygote.require_process(&facts.zygote)?;
        let framework = Process::capture(facts.framework.host_pid, facts.framework.start_ticks)?;
        framework.require_process(&facts.framework)?;
        framework.require_namespaces(&facts.framework_namespaces)?;
        let mounts = [
            rooted_kind(&framework.root, "data", false)?,
            rooted_kind(&framework.root, "metadata", false)?,
        ];
        let mount_roots = [
            facts.persistent_data.backings[0].framework_root,
            facts.persistent_data.backings[1].framework_root,
        ];
        let uid_map = id_map(&small(&framework.directory, c"uid_map")?)?;
        let gid_map = id_map(&small(&framework.directory, c"gid_map")?)?;
        let value = Self {
            original_peer_pidfd,
            peer,
            processes: [init, zygote, framework],
            mounts,
            mount_roots,
            uid_map,
            gid_map,
            facts: facts.clone(),
        };
        value.guard()?;
        Ok(value)
    }
    pub(crate) fn guard(&self) -> io::Result<()> {
        live(&self.original_peer_pidfd)?;
        self.peer.guard()?;
        require(
            identity(&self.peer.pidfd)? == identity(&self.original_peer_pidfd)?,
            "working Main original normal peer changed",
        )?;
        for process in &self.processes {
            process.guard()?;
        }
        let framework = &self.processes[2];
        for ((held, expected), name) in self
            .mounts
            .iter()
            .zip(&self.mount_roots)
            .zip(["data", "metadata"])
        {
            root_matches(&directory(held, name)?, expected)?;
            let named = rooted_kind(&framework.root, name, false)?;
            root_matches(&directory(&named, name)?, expected)?;
        }
        require(
            id_map(&small(&framework.directory, c"uid_map")?)? == self.uid_map
                && id_map(&small(&framework.directory, c"gid_map")?)? == self.gid_map,
            "working Main actual namespace mappings changed",
        )?;
        framework.guard()?;
        self.peer.guard()?;
        live(&self.original_peer_pidfd)
    }
    pub(crate) fn facts(&self) -> &RuntimeMainCustody {
        &self.facts
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn working_main_local_process_guard_keeps_actual_pidfd_and_rejects_exit() {
        let mut child = std::process::Command::new("/bin/sleep")
            .arg("30")
            .spawn()
            .unwrap();
        let pid = child.id();
        let stat = std::fs::read_to_string(format!("/proc/{pid}/stat")).unwrap();
        let fields = stat
            .rsplit_once(") ")
            .unwrap()
            .1
            .split_ascii_whitespace()
            .collect::<Vec<_>>();
        let start = fields[19].parse().unwrap();
        let actual = Process::capture(pid, start).unwrap();
        actual.guard().unwrap();
        assert!(Process::capture(pid, start + 1).is_err());
        child.kill().unwrap();
        child.wait().unwrap();
        assert!(actual.guard().is_err());
        // This exercises real local process custody, not a forged Main token.
    }
    #[test]
    fn working_main_parent_parser_checks_the_actual_stat_field() {
        assert_eq!(parent("17 (name ) with spaces) S 3 0 0").unwrap(), 3);
        assert!(parent("17 (name) S nope 0").is_err());
    }
}
