//! Readonly application queries bound to the root-selected early production
//! executable and the kernel's original socket peer pidfd.
use super::*;
use crate::production_selection::{PublishedServiceProgram, SharedKernelLauncher};
use std::ffi::CStr;
use std::os::fd::{FromRawFd, RawFd};
use std::os::unix::fs::OpenOptionsExt;

const PROGRAM: &str = "/usr/lib/droidloom/production/current/droidloomd";
const SO_PEERPIDFD: i32 = 77;

#[derive(Clone, Debug, Eq, PartialEq)]
struct Node {
    device: u64,
    inode: u64,
    mode: u32,
    uid: u32,
    gid: u32,
    links: u64,
    bytes: u64,
    modified: (i64, i64),
    changed: (i64, i64),
}
impl Node {
    fn of(file: &fs::File) -> io::Result<Self> {
        Ok(Self::from(&file.metadata()?))
    }
    fn from(m: &fs::Metadata) -> Self {
        Self {
            device: m.dev(),
            inode: m.ino(),
            mode: m.mode(),
            uid: m.uid(),
            gid: m.gid(),
            links: m.nlink(),
            bytes: m.len(),
            modified: (m.mtime(), m.mtime_nsec()),
            changed: (m.ctime(), m.ctime_nsec()),
        }
    }
}
fn open_at(parent: RawFd, name: &CStr, flags: i32) -> io::Result<fs::File> {
    // SAFETY: a live directory descriptor and a terminated fixed component;
    // ownership of a successful descriptor moves immediately into File.
    let raw = unsafe { libc::openat(parent, name.as_ptr(), flags | libc::O_CLOEXEC) };
    if raw < 0 {
        return Err(io::Error::last_os_error());
    }
    Ok(unsafe { fs::File::from_raw_fd(raw) })
}
fn invalid(message: &'static str) -> io::Error {
    io::Error::other(message)
}
fn live(pidfd: &fs::File) -> io::Result<()> {
    let mut poll = libc::pollfd {
        fd: pidfd.as_raw_fd(),
        events: libc::POLLIN,
        revents: 0,
    };
    // SAFETY: one initialized pollfd; no blocking wait and no signal is sent.
    let result = unsafe { libc::poll(&mut poll, 1, 0) };
    if result < 0 {
        return Err(io::Error::last_os_error());
    }
    if result != 0 || poll.revents != 0 {
        return Err(invalid("original control peer exited"));
    }
    Ok(())
}
fn peer_pidfd(stream: &UnixStream) -> io::Result<fs::File> {
    let mut raw = -1i32;
    let mut size = std::mem::size_of::<i32>() as libc::socklen_t;
    // SAFETY: kernel writes one descriptor into the initialized integer.
    let result = unsafe {
        libc::getsockopt(
            stream.as_raw_fd(),
            libc::SOL_SOCKET,
            SO_PEERPIDFD,
            (&mut raw as *mut i32).cast(),
            &mut size,
        )
    };
    if result < 0 {
        return Err(io::Error::last_os_error());
    }
    if raw < 0 {
        return Err(invalid("control peer has no kernel pidfd"));
    }
    let file = unsafe { fs::File::from_raw_fd(raw) };
    if size as usize != std::mem::size_of::<i32>() {
        return Err(invalid("invalid peer pidfd length"));
    }
    // SO_PEERPIDFD creates a received descriptor; explicitly preserve CLOEXEC.
    if unsafe { libc::fcntl(file.as_raw_fd(), libc::F_SETFD, libc::FD_CLOEXEC) } < 0 {
        return Err(io::Error::last_os_error());
    }
    live(&file)?;
    Ok(file)
}
fn read_small(mut file: fs::File, limit: u64) -> io::Result<Vec<u8>> {
    let mut bytes = Vec::new();
    Read::by_ref(&mut file)
        .take(limit + 1)
        .read_to_end(&mut bytes)?;
    if bytes.len() as u64 > limit {
        return Err(invalid("control peer proc field exceeded its bound"));
    }
    Ok(bytes)
}
fn root_credentials(bytes: &[u8]) -> io::Result<()> {
    let text = std::str::from_utf8(bytes).map_err(|_| invalid("nontext control peer status"))?;
    for field in ["Uid:", "Gid:"] {
        let rows: Vec<_> = text
            .lines()
            .filter(|line| line.starts_with(field))
            .collect();
        if rows.len() != 1
            || rows[0].split_whitespace().skip(1).collect::<Vec<_>>() != ["0", "0", "0", "0"]
        {
            return Err(invalid(
                "control peer no longer has the fixed root credentials",
            ));
        }
    }
    Ok(())
}
fn start_ticks(bytes: &[u8], pid: u32) -> io::Result<u64> {
    let text = std::str::from_utf8(bytes).map_err(|_| invalid("nontext control peer stat"))?;
    if text.split_whitespace().next() != Some(pid.to_string().as_str()) {
        return Err(invalid("control peer proc PID differs"));
    }
    let tail = text
        .rsplit_once(')')
        .ok_or_else(|| invalid("invalid control peer stat"))?
        .1;
    tail.split_whitespace()
        .nth(19)
        .ok_or_else(|| invalid("missing control peer start time"))?
        .parse()
        .map_err(|_| invalid("invalid control peer start time"))
}
fn peer_credentials_checked(stream: &UnixStream) -> Result<libc::ucred, ControlError> {
    let peer = peer_credentials(stream)?;
    if peer.pid <= 1 || peer.uid != 0 || peer.gid != 0 {
        return Err(ControlError::Invalid(
            "identity queries require the original root production peer".into(),
        ));
    }
    Ok(peer)
}

/// Output only: the caller cannot deserialize this into an inspector or authority.
#[derive(Debug, Eq, PartialEq, Serialize)]
pub struct NativeInspectionPeer {
    pub pid: u32,
    pub start_ticks: u64,
    pub boot_id: String,
    pub executable_bytes: u64,
    pub executable_sha256: String,
    pub public_selector_sha256: String,
    pub systemd_invocation_checked: bool,
}

/// An in-process observation created only by the authenticated normal inspector.
/// It retains the actual peer PIDFD. It is neither Clone nor Deserialize and has
/// no public constructor. Its comparison-only receipt cannot recreate this fact.
/// This proves resource custody; account contents and business acceptance are
/// separate factories and are not granted by this type.
pub struct MainCustodyObservation {
    facts: crate::main_custody::RuntimeMainCustody,
    peer: NativeInspectionPeer,
    pidfd: fs::File,
}
impl MainCustodyObservation {
    /// Read-only comparison projection, not a capability or acceptance receipt.
    pub fn facts(&self) -> &crate::main_custody::RuntimeMainCustody { &self.facts }
    /// Actual fixed normal peer, rechecked at construction and by revalidate_main.
    pub fn peer(&self) -> &NativeInspectionPeer { &self.peer }
}

fn main_response(
    response: ControlResponse, expected: &application_probe::RuntimeEpoch,
) -> Result<crate::main_custody::RuntimeMainCustody, ControlError> {
    if !response.ok || response.state != CellState::Running
        || response.host_pid != Some(expected.cell_host_pid)
        || response.launch.is_some() || response.applications.is_some()
        || response.application_icon.is_some() || response.inspection.is_some()
        || response.image_custody.is_some() || response.runtime_vintf.is_some()
    {
        return Err(ControlError::Invalid("normal Main resource observation did not complete".into()));
    }
    let body = response.diagnostics.ok_or_else(|| ControlError::Invalid(
        "normal Main resource observation omitted its fixed body".into()))?;
    if body.len() > 32768 {
        return Err(ControlError::Invalid("normal Main resource observation exceeded its bound".into()));
    }
    let facts: crate::main_custody::RuntimeMainCustody = serde_json::from_str(&body)?;
    facts.validate(expected).map_err(ControlError::Invalid)?;
    Ok(facts)
}

/// A process-local read-only client. It never accepts an executable hash, PID,
/// invocation or socket pathname selected by a material/acceptance document.
pub struct NativeApplicationInspector {
    selector: SharedKernelLauncher,
    program: PublishedServiceProgram,
    peer_pid: u32,
    pidfd: fs::File,
    proc: fs::File,
    proc_node: Node,
    exe: fs::File,
    start: u64,
    boot_id: String,
    parents: Vec<(PathBuf, fs::File, Node)>,
    socket_node: fs::File,
    socket_identity: Node,
    first: Option<UnixStream>,
}
impl NativeApplicationInspector {
    /// Acquire the fixed early production listener. Absence or a different
    /// layout is unsupported; it never falls back to an ordinary user socket.
    pub fn acquire(socket: &Path) -> Result<Self, ControlError> {
        let io = |e| io_error("bind actual production application peer", e);
        if socket != Path::new(DEFAULT_CONTROL_SOCKET) {
            return Err(ControlError::Invalid(
                "material identity only uses the fixed production socket".into(),
            ));
        }
        let selector = SharedKernelLauncher::read().map_err(io)?.ok_or_else(|| {
            ControlError::Invalid("normal shared-kernel launcher is not published".into())
        })?;
        if !selector.early_kernel_boot() {
            return Err(ControlError::Invalid(
                "material identity currently supports the selected early shared-kernel owner"
                    .into(),
            ));
        }
        let program = selector.entry_program().map_err(io)?;
        let mut parents = Vec::new();
        let mut parent = libc::AT_FDCWD;
        for (path, name) in [
            ("/", c"/"),
            ("/run", c"run"),
            ("/run/droidloom", c"droidloom"),
        ] {
            let file = open_at(
                parent,
                name,
                libc::O_PATH | libc::O_DIRECTORY | libc::O_NOFOLLOW,
            )
            .map_err(io)?;
            let node = Node::of(&file).map_err(io)?;
            if node.uid != 0 || node.gid != 0 || node.mode & 0o022 != 0 {
                return Err(ControlError::Invalid(
                    "production socket parent is not protected by root".into(),
                ));
            }
            parent = file.as_raw_fd();
            parents.push((PathBuf::from(path), file, node));
        }
        let socket_node =
            open_at(parent, c"control.sock", libc::O_PATH | libc::O_NOFOLLOW).map_err(io)?;
        let socket_identity = Node::of(&socket_node).map_err(io)?;
        if socket_identity.mode & libc::S_IFMT != libc::S_IFSOCK
            || socket_identity.uid != 0
            || socket_identity.gid != 0
            || socket_identity.links != 1
        {
            return Err(ControlError::Invalid(
                "fixed production socket has a different type or owner".into(),
            ));
        }
        let stream = progress::connect(socket).map_err(io)?;
        let peer = peer_credentials_checked(&stream)?;
        let pidfd = peer_pidfd(&stream).map_err(io)?;
        let peer_pid = peer.pid as u32;
        let proc_path = PathBuf::from(format!("/proc/{peer_pid}"));
        let proc = fs::OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_PATH | libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open(proc_path)
            .map_err(io)?;
        let proc_node = Node::of(&proc).map_err(io)?;
        // Deliberate proc magic-link open: compare its actual held executable
        // inode with the root-published normal ELF, not readlink/argv[0].
        let exe = open_at(proc.as_raw_fd(), c"exe", libc::O_RDONLY).map_err(io)?;
        let start = start_ticks(
            &read_small(
                open_at(proc.as_raw_fd(), c"stat", libc::O_RDONLY | libc::O_NOFOLLOW)
                    .map_err(io)?,
                4096,
            )
            .map_err(io)?,
            peer_pid,
        )
        .map_err(io)?;
        let boot_id = fs::read_to_string("/proc/sys/kernel/random/boot_id")
            .map_err(io)?
            .trim()
            .to_owned();
        if boot_id.len() != 36 {
            return Err(ControlError::Invalid("invalid current host boot ID".into()));
        }
        let result = Self {
            selector,
            program,
            peer_pid,
            pidfd,
            proc,
            proc_node,
            exe,
            start,
            boot_id,
            parents,
            socket_node,
            socket_identity,
            first: Some(stream),
        };
        result.revalidate()?;
        Ok(result)
    }
    /// Recheck original descriptors and names. This neither runs a service nor
    /// turns the public selector into Main or application qualification.
    pub fn revalidate(&self) -> Result<(), ControlError> {
        let io = |e| io_error("revalidate actual application peer", e);
        live(&self.pidfd).map_err(io)?;
        self.selector.revalidate().map_err(io)?;
        self.program.revalidate().map_err(io)?;
        for (path, file, held) in &self.parents {
            let actual = Node::of(file).map_err(io)?;
            let named = Node::from(&fs::symlink_metadata(path).map_err(io)?);
            for value in [&actual, &named] {
                if (value.device, value.inode, value.mode, value.uid, value.gid)
                    != (held.device, held.inode, held.mode, held.uid, held.gid)
                {
                    return Err(ControlError::Invalid(
                        "root socket parent identity changed".into(),
                    ));
                }
            }
        }
        if Node::of(&self.socket_node).map_err(io)? != self.socket_identity
            || Node::from(&fs::symlink_metadata(DEFAULT_CONTROL_SOCKET).map_err(io)?)
                != self.socket_identity
            || Node::of(&self.proc).map_err(io)? != self.proc_node
        {
            return Err(ControlError::Invalid(
                "control socket or held process changed".into(),
            ));
        }
        let info = fs::read_to_string(format!("/proc/self/fdinfo/{}", self.pidfd.as_raw_fd()))
            .map_err(io)?;
        if info
            .lines()
            .filter(|line| line.starts_with("Pid:"))
            .collect::<Vec<_>>()
            != [format!("Pid:\t{}", self.peer_pid).as_str()]
        {
            return Err(ControlError::Invalid(
                "kernel pidfd does not identify the original control peer".into(),
            ));
        }
        let read = |name: &CStr, limit| {
            read_small(
                open_at(
                    self.proc.as_raw_fd(),
                    name,
                    libc::O_RDONLY | libc::O_NOFOLLOW,
                )?,
                limit,
            )
        };
        root_credentials(&read(c"status", 16384).map_err(io)?).map_err(io)?;
        if start_ticks(&read(c"stat", 4096).map_err(io)?, self.peer_pid).map_err(io)? != self.start
        {
            return Err(ControlError::Invalid(
                "control peer start time changed".into(),
            ));
        }
        let argv = read(c"cmdline", 4096).map_err(io)?;
        let expected = format!("{PROGRAM}\0--socket\0{DEFAULT_CONTROL_SOCKET}\0");
        if argv != expected.as_bytes() {
            return Err(ControlError::Invalid(
                "control peer is not the fixed normal production command".into(),
            ));
        }
        let active = open_at(self.proc.as_raw_fd(), c"exe", libc::O_RDONLY).map_err(io)?;
        if !self.program.matches_executable(&self.exe).map_err(io)?
            || !self.program.matches_executable(&active).map_err(io)?
            || fs::read_to_string("/proc/sys/kernel/random/boot_id")
                .map_err(io)?
                .trim()
                != self.boot_id
        {
            return Err(ControlError::Invalid(
                "actual control executable or host boot changed".into(),
            ));
        }
        live(&self.pidfd).map_err(io)
    }
    fn request_fixed(&mut self, request: &ControlRequest) -> Result<ControlResponse, ControlError> {
        self.revalidate()?;
        let stream = match self.first.take() {
            Some(stream) => stream,
            None => progress::connect(Path::new(DEFAULT_CONTROL_SOCKET))
                .map_err(|e| io_error("connect fixed application peer", e))?,
        };
        let peer = peer_credentials_checked(&stream)?;
        let current_pidfd =
            peer_pidfd(&stream).map_err(|e| io_error("capture current control peer", e))?;
        if peer.pid as u32 != self.peer_pid {
            return Err(ControlError::Invalid(
                "fixed socket was replaced by another daemon".into(),
            ));
        }
        let result = progress::request_on(stream, Instant::now(), request, None, None);
        live(&current_pidfd).map_err(|e| io_error("recheck current control peer", e))?;
        self.revalidate()?;
        result
    }

    /// Run only the existing fixed inspection operation on the authenticated
    /// connection, retaining the original peer and normal source bookends.
    pub fn inspect(&mut self, package: &str, user: u32) -> Result<ControlResponse, ControlError> {
        validate_android_user(user)?;
        let result = self.request_fixed(&ControlRequest::InspectApplication {
            package: package.into(), user,
        })?;
        if result.inspection.as_ref().is_some_and(|value| value.epoch.boot_id != self.boot_id) {
            return Err(ControlError::Invalid("inspection belongs to a different host boot".into()));
        }
        Ok(result)
    }

    /// Observe only the original normal owner's current process, namespace,
    /// writable backing and retained mount resources. Expected PIDs compare a
    /// live epoch; they never select a process or authorize a saved receipt.
    pub fn observe_main(
        &mut self, expected: &application_probe::RuntimeEpoch,
    ) -> Result<MainCustodyObservation, ControlError> {
        self.revalidate()?;
        if expected.boot_id != self.boot_id {
            return Err(ControlError::Invalid("Main epoch belongs to another host boot".into()));
        }
        let response = self.request_fixed(&ControlRequest::ObserveRuntimeMain {
            expected_epoch: expected.clone(),
        })?;
        let facts = main_response(response, expected)?;
        let peer = self.observation()?;
        let pidfd = self.pidfd.try_clone()
            .map_err(|e| io_error("retain actual Main control peer", e))?;
        live(&pidfd).map_err(|e| io_error("check actual Main control peer", e))?;
        self.revalidate()?;
        Ok(MainCustodyObservation { facts, peer, pidfd })
    }

    /// Re-observe the same fixed resources through the same actual source-bound
    /// peer. This method consumes no external FilePin, pathname or success bit.
    pub fn revalidate_main(&mut self, prior: &MainCustodyObservation) -> Result<(), ControlError> {
        live(&prior.pidfd).map_err(|e| io_error("recheck retained Main peer", e))?;
        let old = prior.pidfd.metadata().map_err(|e| io_error("stat retained Main peer", e))?;
        let current = self.pidfd.metadata().map_err(|e| io_error("stat current Main peer", e))?;
        if (old.dev(), old.ino()) != (current.dev(), current.ino())
            || prior.peer != self.observation()?
        {
            return Err(ControlError::Invalid("Main observation belongs to another actual control peer".into()));
        }
        let after = self.observe_main(&prior.facts.epoch)?;
        if after.peer != prior.peer || after.facts != prior.facts {
            return Err(ControlError::Invalid("Main process, selection, namespace or persistent resource changed".into()));
        }
        live(&prior.pidfd).map_err(|e| io_error("finish retained Main peer check", e))?;
        self.revalidate()
    }
    /// Return factual provenance only; the struct is not an authority input.
    pub fn observation(&self) -> Result<NativeInspectionPeer, ControlError> {
        self.revalidate()?;
        let (executable_bytes, executable_sha256) = self.program.content_identity();
        Ok(NativeInspectionPeer {
            pid: self.peer_pid,
            start_ticks: self.start,
            boot_id: self.boot_id.clone(),
            executable_bytes,
            executable_sha256,
            public_selector_sha256: self.selector.public_selector_sha256().into(),
            systemd_invocation_checked: false,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn main_observation_requires_the_fixed_successful_response_and_exact_body() {
        let facts = crate::main_custody::tests::sample();
        let response = ControlResponse {
            ok: true, state: CellState::Running, message: String::new(),
            host_pid: Some(facts.epoch.cell_host_pid),
            launch: None, applications: None, application_icon: None,
            diagnostics: Some(serde_json::to_string(&facts).unwrap()),
            inspection: None, image_custody: None, runtime_vintf: None,
        };
        assert_eq!(main_response(response.clone(), &facts.epoch).unwrap(), facts);
        for case in 0..6 {
            let mut changed = response.clone();
            match case {
                0 => changed.ok = false,
                1 => changed.state = CellState::Quarantined,
                2 => changed.host_pid = Some(999),
                3 => changed.launch = Some("unrelated operation".into()),
                4 => changed.diagnostics = None,
                _ => changed.diagnostics = Some("true".into()),
            }
            assert!(main_response(changed, &facts.epoch).is_err());
        }
        // A parsed body remains comparison data. This test never constructs
        // MainCustodyObservation, whose only production constructor needs the
        // selected program, root socket and an actual original peer PIDFD.
    }

    #[test]
    fn native_socket_pidfd_binds_the_actual_original_process() {
        let (left, _right) = UnixStream::pair().unwrap();
        let peer = peer_credentials(&left).unwrap();
        assert_eq!(peer.pid as u32, std::process::id());
        let held = peer_pidfd(&left).unwrap();
        live(&held).unwrap();
        let info = fs::read_to_string(format!("/proc/self/fdinfo/{}", held.as_raw_fd())).unwrap();
        assert!(
            info.lines()
                .any(|line| line == format!("Pid:\t{}", std::process::id()))
        );
    }
    #[test]
    fn an_ordinary_same_user_socket_is_not_a_root_material_observer() {
        if unsafe { libc::geteuid() } == 0 {
            return;
        }
        let (left, _right) = UnixStream::pair().unwrap();
        assert!(peer_credentials_checked(&left).is_err());
    }
    #[test]
    fn daemon_credential_drop_and_malformed_stat_are_not_accepted() {
        root_credentials(b"Uid:\t0\t0\t0\t0\nGid:\t0\t0\t0\t0\n").unwrap();
        assert!(root_credentials(b"Uid:\t0\t1000\t0\t0\nGid:\t0\t0\t0\t0\n").is_err());
        assert!(root_credentials(b"Uid:\t0\t0\t0\t0\n").is_err());
        assert!(start_ticks(b"1 (daemon) R 0", 1).is_err());
    }
}
