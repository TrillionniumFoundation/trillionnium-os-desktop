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
    observed_at: Instant,
}
impl MainCustodyObservation {
    /// Read-only comparison projection, not a capability or acceptance receipt.
    pub fn facts(&self) -> &crate::main_custody::RuntimeMainCustody {
        &self.facts
    }
    /// Actual fixed normal peer, rechecked at construction and by revalidate_main.
    pub fn peer(&self) -> &NativeInspectionPeer {
        &self.peer
    }
    pub(crate) fn observed_at(&self) -> Instant {
        self.observed_at
    }
}

/// Actual PM output minted only after a successful fixed request to the held
/// normal peer. Saved ApplicationInspection values cannot construct this token.
pub struct ActualApplicationObservation {
    facts: application_probe::ApplicationInspection,
    peer: NativeInspectionPeer,
    pidfd: fs::File,
    observed_at: Instant,
}
impl ActualApplicationObservation {
    /// Comparison data only; copying it cannot recreate an actual observation.
    pub fn facts(&self) -> &application_probe::ApplicationInspection {
        &self.facts
    }
    pub fn peer(&self) -> &NativeInspectionPeer {
        &self.peer
    }
    pub(crate) fn observed_at(&self) -> Instant {
        self.observed_at
    }
}

/// One actual complete user-0 inventory from this retained normal peer. The
/// serializable facts are comparisons; only the fixed request mints this token.
pub struct ActualUserZeroPackageInventoryObservation {
    facts: crate::package_inventory_observation::UserZeroPackageInventoryFacts,
    peer: NativeInspectionPeer,
    pidfd: fs::File,
    observed_at: Instant,
}
impl ActualUserZeroPackageInventoryObservation {
    pub fn facts(&self) -> &crate::package_inventory_observation::UserZeroPackageInventoryFacts {
        &self.facts
    }
    pub(crate) fn observed_at(&self) -> Instant { self.observed_at }
}


/// One actual complete selected-package exit-history sample. The wire body is
/// comparison only; this token retains the admitted peer and installed identity.
pub struct ActualApplicationExitObservation {
    facts: crate::application_exit_state::ApplicationExitStateFacts,
    application: application_probe::ApplicationInspection,
    peer: NativeInspectionPeer,
    pidfd: fs::File,
    observed_at: Instant,
}
impl ActualApplicationExitObservation {
    pub fn facts(&self) -> &crate::application_exit_state::ApplicationExitStateFacts { &self.facts }
    /// The actual local receipt time, never supplied by a caller or wire document.
    pub fn observed_at(&self) -> Instant { self.observed_at }
}

fn exit_state_response(
    response: ControlResponse,
    application: &application_probe::ApplicationInspection,
) -> Result<crate::application_exit_state::ApplicationExitStateFacts, ControlError> {
    if !response.ok || response.state != CellState::Running
        || response.host_pid != Some(application.epoch.cell_host_pid)
        || response.launch.is_some() || response.applications.is_some()
        || response.application_icon.is_some() || response.inspection.is_some()
        || response.image_custody.is_some() || response.runtime_vintf.is_some()
    {
        return Err(ControlError::Invalid("actual complete exit-state query did not complete".into()));
    }
    let raw=response.diagnostics.ok_or_else(||ControlError::Invalid(
        "actual complete exit-state query omitted its comparison body".into()))?;
    if raw.len()>crate::application_exit_state::MAX_WIRE_BYTES {
        return Err(ControlError::Invalid("actual exit-state body exceeded its fixed bound".into()));
    }
    let facts:crate::application_exit_state::ApplicationExitStateFacts=serde_json::from_str(&raw)?;
    facts.require_application(application).map_err(ControlError::Invalid)?;
    Ok(facts)
}

/// One actual complete selected-package PM-permission sample. The wire body is
/// comparison only; this token retains the admitted peer and installed identity.
pub struct ActualApplicationPermissionObservation {
    facts: crate::application_permission_state::ApplicationPermissionStateFacts,
    application: application_probe::ApplicationInspection,
    peer: NativeInspectionPeer,
    pidfd: fs::File,
    observed_at: Instant,
}
impl ActualApplicationPermissionObservation {
    pub fn facts(&self) -> &crate::application_permission_state::ApplicationPermissionStateFacts { &self.facts }
    /// The actual local receipt time, never supplied by a caller or wire document.
    pub fn observed_at(&self) -> Instant { self.observed_at }
}

fn permission_state_response(
    response: ControlResponse,
    application: &application_probe::ApplicationInspection,
) -> Result<crate::application_permission_state::ApplicationPermissionStateFacts, ControlError> {
    if !response.ok || response.state != CellState::Running
        || response.host_pid != Some(application.epoch.cell_host_pid)
        || response.launch.is_some() || response.applications.is_some()
        || response.application_icon.is_some() || response.inspection.is_some()
        || response.image_custody.is_some() || response.runtime_vintf.is_some()
    {
        return Err(ControlError::Invalid("actual complete PM-permission query did not complete".into()));
    }
    let raw=response.diagnostics.ok_or_else(||ControlError::Invalid(
        "actual complete PM-permission query omitted its comparison body".into()))?;
    if raw.len()>crate::application_permission_state::MAX_WIRE_BYTES {
        return Err(ControlError::Invalid("actual PM-permission body exceeded its fixed bound".into()));
    }
    let facts:crate::application_permission_state::ApplicationPermissionStateFacts=serde_json::from_str(&raw)?;
    facts.require_application(application).map_err(ControlError::Invalid)?;
    Ok(facts)
}

/// One actual complete selected-package AppOps sample. The wire body is
/// comparison only; this token retains the admitted peer and installed identity.
pub struct ActualApplicationAppOpsObservation {
    facts: crate::application_appops_state::ApplicationAppOpsStateFacts,
    application: application_probe::ApplicationInspection,
    peer: NativeInspectionPeer,
    pidfd: fs::File,
    observed_at: Instant,
}
impl ActualApplicationAppOpsObservation {
    pub fn facts(&self) -> &crate::application_appops_state::ApplicationAppOpsStateFacts { &self.facts }
    /// The actual local receipt time, never supplied by a caller or wire document.
    pub fn observed_at(&self) -> Instant { self.observed_at }
}

fn appops_state_response(
    response: ControlResponse,
    application: &application_probe::ApplicationInspection,
) -> Result<crate::application_appops_state::ApplicationAppOpsStateFacts, ControlError> {
    if !response.ok || response.state != CellState::Running
        || response.host_pid != Some(application.epoch.cell_host_pid)
        || response.launch.is_some() || response.applications.is_some()
        || response.application_icon.is_some() || response.inspection.is_some()
        || response.image_custody.is_some() || response.runtime_vintf.is_some()
    {
        return Err(ControlError::Invalid("actual complete AppOps query did not complete".into()));
    }
    let raw=response.diagnostics.ok_or_else(||ControlError::Invalid(
        "actual complete AppOps query omitted its comparison body".into()))?;
    if raw.len()>crate::application_appops_state::MAX_WIRE_BYTES {
        return Err(ControlError::Invalid("actual AppOps body exceeded its fixed bound".into()));
    }
    let facts:crate::application_appops_state::ApplicationAppOpsStateFacts=serde_json::from_str(&raw)?;
    facts.require_application(application).map_err(ControlError::Invalid)?;
    Ok(facts)
}


/// One actual anonymous registered-account sample from the same live broker key. The wire body is
/// comparison only; this token retains the admitted peer and installed identity.
pub struct ActualApplicationAccountObservation {
    facts: crate::application_account_state::ApplicationAccountStateFacts,
    application: application_probe::ApplicationInspection,
    peer: NativeInspectionPeer,
    pidfd: fs::File,
    observed_at: Instant,
    original_end: Instant,
    main: crate::main_custody::RuntimeMainCustody,
}
impl ActualApplicationAccountObservation {
    pub fn facts(&self) -> &crate::application_account_state::ApplicationAccountStateFacts { &self.facts }
    /// The actual local receipt time, never supplied by a caller or wire document.
    pub fn observed_at(&self) -> Instant { self.observed_at }
}

fn account_state_response(
    response: ControlResponse,
    application: &application_probe::ApplicationInspection,
) -> Result<crate::application_account_state::ApplicationAccountStateFacts, ControlError> {
    if !response.ok || response.state != CellState::Running
        || response.host_pid != Some(application.epoch.cell_host_pid)
        || response.launch.is_some() || response.applications.is_some()
        || response.application_icon.is_some() || response.inspection.is_some()
        || response.image_custody.is_some() || response.runtime_vintf.is_some()
    {
        return Err(ControlError::Invalid("actual complete Account query did not complete".into()));
    }
    let raw=response.diagnostics.ok_or_else(||ControlError::Invalid(
        "actual complete Account query omitted its comparison body".into()))?;
    if raw.len()>crate::application_account_state::MAX_WIRE_BYTES {
        return Err(ControlError::Invalid("actual Account body exceeded its fixed bound".into()));
    }
    let facts:crate::application_account_state::ApplicationAccountStateFacts=serde_json::from_str(&raw)
        .map_err(|_|ControlError::Invalid("anonymous account response schema differs".into()))?;
    facts.require_application(application).map_err(ControlError::Invalid)?;
    Ok(facts)
}


fn inventory_response(
    response: ControlResponse,
    application: &application_probe::ApplicationInspection,
) -> Result<crate::package_inventory_observation::UserZeroPackageInventoryFacts, ControlError> {
    if !response.ok || response.state != CellState::Running
        || response.host_pid != Some(application.epoch.cell_host_pid)
        || response.launch.is_some() || response.applications.is_some()
        || response.application_icon.is_some() || response.inspection.is_some()
        || response.image_custody.is_some() || response.runtime_vintf.is_some()
        || application.user != 0
    {
        return Err(ControlError::Invalid("actual complete user-0 inventory did not complete".into()));
    }
    let raw = response.diagnostics.ok_or_else(|| ControlError::Invalid(
        "actual complete user-0 inventory omitted its comparison body".into()))?;
    if raw.len() > crate::package_inventory_observation::MAX_WIRE_BYTES {
        return Err(ControlError::Invalid("actual complete inventory exceeded its bound".into()));
    }
    let facts: crate::package_inventory_observation::UserZeroPackageInventoryFacts =
        serde_json::from_str(&raw)?;
    facts.validate(&application.epoch).map_err(ControlError::Invalid)?;
    if facts.records().get(application.package.as_str()) != Some(&application.uid) {
        return Err(ControlError::Invalid("complete inventory differs from the actual target UID".into()));
    }
    Ok(facts)
}

fn application_response(
    response: ControlResponse,
    package: &str,
    user: u32,
) -> Result<application_probe::ApplicationInspection, ControlError> {
    if !response.ok
        || response.state != CellState::Running
        || response.launch.is_some()
        || response.applications.is_some()
        || response.application_icon.is_some()
        || response.image_custody.is_some()
        || response.runtime_vintf.is_some()
    {
        return Err(ControlError::Invalid(
            "actual normal application observation did not complete".into(),
        ));
    }
    let facts = response.inspection.ok_or_else(|| {
        ControlError::Invalid("actual normal application response omitted the package".into())
    })?;
    if facts.package != package
        || facts.user != user
        || facts.uid == 0
        || facts.uid / 100_000 != user
        || facts.version_code == 0
        || facts.apks.is_empty()
        || response.host_pid != Some(facts.epoch.cell_host_pid)
        || facts.epoch.cell_host_pid <= 1
        || facts.epoch.framework_host_pid <= 1
        || facts.epoch.framework_start_ticks == 0
    {
        return Err(ControlError::Invalid(
            "actual normal application identity differs".into(),
        ));
    }
    let mut names = std::collections::BTreeSet::new();
    let mut paths = std::collections::BTreeSet::new();
    if facts.apks.len() > 64
        || facts.apks.iter().filter(|a| a.name == "base.apk").count() != 1
        || facts.apks.iter().any(|apk| {
            !names.insert(&apk.name)
                || !paths.insert(&apk.path)
                || apk.bytes < 4
                || !Path::new(&apk.path).is_absolute()
                || apk.sha256.len() != 64
                || !apk
                    .sha256
                    .bytes()
                    .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
        })
    {
        return Err(ControlError::Invalid(
            "actual installed APK base/split identity is incomplete".into(),
        ));
    }
    Ok(facts)
}

fn main_response(
    response: ControlResponse,
    expected: &application_probe::RuntimeEpoch,
) -> Result<crate::main_custody::RuntimeMainCustody, ControlError> {
    if !response.ok
        || response.state != CellState::Running
        || response.host_pid != Some(expected.cell_host_pid)
        || response.launch.is_some()
        || response.applications.is_some()
        || response.application_icon.is_some()
        || response.inspection.is_some()
        || response.image_custody.is_some()
        || response.runtime_vintf.is_some()
    {
        return Err(ControlError::Invalid(
            "normal Main resource observation did not complete".into(),
        ));
    }
    let body = response.diagnostics.ok_or_else(|| {
        ControlError::Invalid("normal Main resource observation omitted its fixed body".into())
    })?;
    if body.len() > 32768 {
        return Err(ControlError::Invalid(
            "normal Main resource observation exceeded its bound".into(),
        ));
    }
    let facts: crate::main_custody::RuntimeMainCustody = serde_json::from_str(&body)?;
    facts.validate(expected).map_err(ControlError::Invalid)?;
    Ok(facts)
}

// Comparison of an already authenticated response. This helper returns only
// data; the private client below must retain its actual normal peer PIDFD.
fn current_main_response(
    response: ControlResponse,
    actual_boot_id: &str,
) -> Result<crate::main_custody::RuntimeMainCustody, ControlError> {
    let body = response.diagnostics.as_deref().ok_or_else(|| {
        ControlError::Invalid("current Main observation omitted its body".into())
    })?;
    if body.len() > 32768 {
        return Err(ControlError::Invalid("current Main observation exceeds bound".into()));
    }
    let observed: crate::main_custody::RuntimeMainCustody = serde_json::from_str(body)?;
    if observed.epoch.boot_id != actual_boot_id {
        return Err(ControlError::Invalid("current Main response belongs to another actual host boot".into()));
    }
    main_response(response, &observed.epoch)
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
fn check_deadline(value: Option<Instant>) -> Result<(), ControlError> {
    if value.is_some_and(|end| Instant::now() >= end) {
        Err(ControlError::Invalid(
            "original native leaf deadline expired".into(),
        ))
    } else {
        Ok(())
    }
}

impl NativeApplicationInspector {
    /// Acquire the same fixed listener within one already-started caller budget.
    pub fn acquire_until(socket: &Path, deadline: Instant) -> Result<Self, ControlError> {
        check_deadline(Some(deadline))?;
        let result = Self::acquire(socket)?;
        check_deadline(Some(deadline))?;
        Ok(result)
    }

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
        self.request_fixed_until(request, None)
    }
    pub(crate) fn request_fixed_until(
        &mut self,
        request: &ControlRequest,
        deadline: Option<Instant>,
    ) -> Result<ControlResponse, ControlError> {
        check_deadline(deadline)?;
        self.revalidate()?;
        check_deadline(deadline)?;
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
        check_deadline(deadline)?;
        let result = if let Some(end) = deadline {
            progress::request_on_until(stream, request, end)
        } else {
            progress::request_on(stream, Instant::now(), request, None, None)
        };
        live(&current_pidfd).map_err(|e| io_error("recheck current control peer", e))?;
        self.revalidate()?;
        check_deadline(deadline)?;
        result
    }

    /// Run only the existing fixed inspection operation on the authenticated
    /// connection, retaining the original peer and normal source bookends.
    pub fn inspect(&mut self, package: &str, user: u32) -> Result<ControlResponse, ControlError> {
        validate_android_user(user)?;
        let result = self.request_fixed(&ControlRequest::InspectApplication {
            package: package.into(),
            user,
        })?;
        if result
            .inspection
            .as_ref()
            .is_some_and(|value| value.epoch.boot_id != self.boot_id)
        {
            return Err(ControlError::Invalid(
                "inspection belongs to a different host boot".into(),
            ));
        }
        Ok(result)
    }

    /// The same fixed actual inspection, consuming the original caller budget.
    pub fn inspect_until(
        &mut self,
        package: &str,
        user: u32,
        deadline: Instant,
    ) -> Result<ControlResponse, ControlError> {
        validate_android_user(user)?;
        let result = self.request_fixed_until(
            &ControlRequest::InspectApplication {
                package: package.into(),
                user,
            },
            Some(deadline),
        )?;
        if result
            .inspection
            .as_ref()
            .is_some_and(|value| value.epoch.boot_id != self.boot_id)
        {
            return Err(ControlError::Invalid(
                "inspection belongs to a different host boot".into(),
            ));
        }
        Ok(result)
    }

    /// One actual PM request within the caller's original deadline, retaining
    /// its normal peer. This is the only production constructor for the token.
    pub fn inspect_observed_until(
        &mut self,
        package: &str,
        user: u32,
        deadline: Instant,
    ) -> Result<ActualApplicationObservation, ControlError> {
        let facts =
            application_response(self.inspect_until(package, user, deadline)?, package, user)?;
        let peer = self.observation()?;
        let pidfd = self
            .pidfd
            .try_clone()
            .map_err(|e| io_error("retain actual PM peer", e))?;
        live(&pidfd).map_err(|e| io_error("check actual PM peer", e))?;
        check_deadline(Some(deadline))?;
        Ok(ActualApplicationObservation {
            facts,
            peer,
            pidfd,
            observed_at: Instant::now(),
        })
    }

    /// Local custody only: held peer/process/source and both original opaque
    /// observations. This deliberately performs no PM or full Main RPC.
    pub(crate) fn require_observations_local(
        &self,
        main: &MainCustodyObservation,
        application: &ActualApplicationObservation,
        deadline: Instant,
    ) -> Result<(), ControlError> {
        check_deadline(Some(deadline))?;
        let actual = self.observation()?;
        let current = self
            .pidfd
            .metadata()
            .map_err(|e| io_error("stat live normal peer", e))?;
        for (fd, peer) in [
            (&main.pidfd, &main.peer),
            (&application.pidfd, &application.peer),
        ] {
            live(fd).map_err(|e| io_error("check original observed peer", e))?;
            let held = fd
                .metadata()
                .map_err(|e| io_error("stat original observed peer", e))?;
            if (held.dev(), held.ino()) != (current.dev(), current.ino()) || peer != &actual {
                return Err(ControlError::Invalid(
                    "native observations belong to another actual peer".into(),
                ));
            }
        }
        if main.facts.epoch != application.facts.epoch {
            return Err(ControlError::Invalid(
                "actual PM and Main epochs differ".into(),
            ));
        }
        check_deadline(Some(deadline))
    }

    /// Obtain the first actual Main epoch from the same fixed authenticated
    /// Ready owner. This reads no APK, accepts no epoch/selector, and uses the
    /// existing 70-second transport inside the caller's original absolute end.
    pub fn observe_current_main_until(
        &mut self,
        deadline: Instant,
    ) -> Result<MainCustodyObservation, ControlError> {
        check_deadline(Some(deadline))?;
        self.revalidate()?;
        let request = ControlRequest::ObserveCurrentRuntimeMain {};
        if deadline.saturating_duration_since(Instant::now()) < progress::response_timeout(&request) {
            return Err(ControlError::Invalid("original source/capture window cannot fit current Main observation".into()));
        }
        let response = self.request_fixed_until(&request, Some(deadline))?;
        let facts = current_main_response(response, &self.boot_id)?;
        let peer = self.observation()?;
        let pidfd = self.pidfd.try_clone()
            .map_err(|e| io_error("retain actual current Main peer", e))?;
        live(&pidfd).map_err(|e| io_error("check actual current Main peer", e))?;
        self.revalidate()?;
        check_deadline(Some(deadline))?;
        Ok(MainCustodyObservation { facts, peer, pidfd, observed_at: Instant::now() })
    }

    /// Observe only the original normal owner's current process, namespace,
    /// writable backing and retained mount resources. Expected PIDs compare a
    /// live epoch; they never select a process or authorize a saved receipt.
    pub fn observe_main(
        &mut self,
        expected: &application_probe::RuntimeEpoch,
    ) -> Result<MainCustodyObservation, ControlError> {
        self.observe_main_deadline(expected, None)
    }
    /// The normal Main observation within the original caller's absolute budget.
    pub fn observe_main_until(
        &mut self,
        expected: &application_probe::RuntimeEpoch,
        deadline: Instant,
    ) -> Result<MainCustodyObservation, ControlError> {
        self.observe_main_deadline(expected, Some(deadline))
    }
    fn observe_main_deadline(
        &mut self,
        expected: &application_probe::RuntimeEpoch,
        deadline: Option<Instant>,
    ) -> Result<MainCustodyObservation, ControlError> {
        check_deadline(deadline)?;
        self.revalidate()?;
        if expected.boot_id != self.boot_id {
            return Err(ControlError::Invalid(
                "Main epoch belongs to another host boot".into(),
            ));
        }
        let response = self.request_fixed_until(
            &ControlRequest::ObserveRuntimeMain {
                expected_epoch: expected.clone(),
            },
            deadline,
        )?;
        let facts = main_response(response, expected)?;
        let peer = self.observation()?;
        let pidfd = self
            .pidfd
            .try_clone()
            .map_err(|e| io_error("retain actual Main control peer", e))?;
        live(&pidfd).map_err(|e| io_error("check actual Main control peer", e))?;
        self.revalidate()?;
        check_deadline(deadline)?;
        Ok(MainCustodyObservation {
            facts,
            peer,
            pidfd,
            observed_at: Instant::now(),
        })
    }

    /// Re-observe the same fixed resources through the same actual source-bound
    /// peer. This method consumes no external FilePin, pathname or success bit.
    pub fn revalidate_main(&mut self, prior: &MainCustodyObservation) -> Result<(), ControlError> {
        self.revalidate_main_deadline(prior, None)
    }
    /// Revalidate the same actual owner without renewing an outer lease.
    pub fn revalidate_main_until(
        &mut self,
        prior: &MainCustodyObservation,
        deadline: Instant,
    ) -> Result<(), ControlError> {
        self.revalidate_main_deadline(prior, Some(deadline))
    }
    /// Reuses the one normal revalidation RPC and returns the new actual token,
    /// so downstream bookends need not repeat that operation.
    pub fn refresh_main_until(
        &mut self,
        prior: &MainCustodyObservation,
        deadline: Instant,
    ) -> Result<MainCustodyObservation, ControlError> {
        self.refresh_main_deadline(prior, Some(deadline))
    }
    fn revalidate_main_deadline(
        &mut self,
        prior: &MainCustodyObservation,
        deadline: Option<Instant>,
    ) -> Result<(), ControlError> {
        self.refresh_main_deadline(prior, deadline).map(|_| ())
    }
    fn refresh_main_deadline(
        &mut self,
        prior: &MainCustodyObservation,
        deadline: Option<Instant>,
    ) -> Result<MainCustodyObservation, ControlError> {
        check_deadline(deadline)?;
        live(&prior.pidfd).map_err(|e| io_error("recheck retained Main peer", e))?;
        let old = prior
            .pidfd
            .metadata()
            .map_err(|e| io_error("stat retained Main peer", e))?;
        let current = self
            .pidfd
            .metadata()
            .map_err(|e| io_error("stat current Main peer", e))?;
        if (old.dev(), old.ino()) != (current.dev(), current.ino())
            || prior.peer != self.observation()?
        {
            return Err(ControlError::Invalid(
                "Main observation belongs to another actual control peer".into(),
            ));
        }
        let after = self.observe_main_deadline(&prior.facts.epoch, deadline)?;
        if after.peer != prior.peer || after.facts != prior.facts {
            return Err(ControlError::Invalid(
                "Main process, selection, namespace or persistent resource changed".into(),
            ));
        }
        live(&prior.pidfd).map_err(|e| io_error("finish retained Main peer check", e))?;
        self.revalidate()?;
        check_deadline(deadline)?;
        Ok(after)
    }

    /// One fixed complete user-0 query. This borrows the existing actual Main
    /// and PM tokens and never adds a Main/PM request or renews the outer lease.
    pub fn observe_user_zero_package_inventory_until(
        &mut self,
        main: &MainCustodyObservation,
        application: &ActualApplicationObservation,
        deadline: Instant,
    ) -> Result<ActualUserZeroPackageInventoryObservation, ControlError> {
        self.require_observations_local(main, application, deadline)?;
        if application.facts.user != 0 {
            return Err(ControlError::Invalid("complete inventory is fixed to Android user zero".into()));
        }
        let request = ControlRequest::ObserveUserZeroPackageInventory {
            expected_epoch: main.facts.epoch.clone(),
        };
        // Do not launch a fresh fixed-budget server request late in an outer
        // invocation. The server retains its original 48s work/12s retirement
        // budget and the complete 70s transport must fit in this original end.
        if deadline.saturating_duration_since(Instant::now()) < progress::response_timeout(&request) {
            return Err(ControlError::Invalid("original leaf budget cannot fit complete inventory request".into()));
        }
        let facts = inventory_response(
            self.request_fixed_until(&request, Some(deadline))?,
            &application.facts,
        )?;
        self.require_observations_local(main, application, deadline)?;
        let peer = self.observation()?;
        let pidfd = self.pidfd.try_clone()
            .map_err(|e| io_error("retain actual complete inventory peer", e))?;
        live(&pidfd).map_err(|e| io_error("check actual complete inventory peer", e))?;
        check_deadline(Some(deadline))?;
        Ok(ActualUserZeroPackageInventoryObservation {
            facts, peer, pidfd, observed_at: Instant::now(),
        })
    }
    pub(crate) fn require_inventory_local(
        &self,
        main: &MainCustodyObservation,
        application: &ActualApplicationObservation,
        inventory: &ActualUserZeroPackageInventoryObservation,
        deadline: Instant,
    ) -> Result<(), ControlError> {
        self.require_observations_local(main, application, deadline)?;
        live(&inventory.pidfd).map_err(|e| io_error("recheck actual inventory peer", e))?;
        let held = inventory.pidfd.metadata().map_err(|e| io_error("stat inventory peer", e))?;
        let current = self.pidfd.metadata().map_err(|e| io_error("stat current inventory peer", e))?;
        if (held.dev(), held.ino()) != (current.dev(), current.ino())
            || inventory.peer != self.observation()?
            || inventory.facts.epoch != main.facts.epoch
            || inventory.facts.records().get(application.facts.package.as_str()) != Some(&application.facts.uid)
        {
            return Err(ControlError::Invalid("complete inventory belongs to another actual owner or target".into()));
        }
        check_deadline(Some(deadline))
    }


    /// One actual fixed exit-history query; borrows the original Main/PM owner
    /// and the caller's original end. No fresh Main or PM request is added.
    pub fn observe_application_exit_state_until(
        &mut self,
        main: &MainCustodyObservation,
        application: &ActualApplicationObservation,
        deadline: Instant,
    ) -> Result<ActualApplicationExitObservation, ControlError> {
        self.require_observations_local(main,application,deadline)?;
        if application.facts.user!=0 || !crate::engine_custody::selected_package(&application.facts.package) {
            return Err(ControlError::Invalid("exit-state requires a selected actual user-zero application".into()));
        }
        let request=ControlRequest::ObserveApplicationExitState{
            package:application.facts.package.clone(), expected_epoch:main.facts.epoch.clone(),
        };
        if deadline.saturating_duration_since(Instant::now())<progress::response_timeout(&request) {
            return Err(ControlError::Invalid("original observation budget cannot fit the fixed exit-state request".into()));
        }
        let facts=exit_state_response(self.request_fixed_until(&request,Some(deadline))?,&application.facts)?;
        self.require_observations_local(main,application,deadline)?;
        let peer=self.observation()?;
        let pidfd=self.pidfd.try_clone().map_err(|e|io_error("retain actual exit-state peer",e))?;
        live(&pidfd).map_err(|e|io_error("check actual exit-state peer",e))?;
        check_deadline(Some(deadline))?;
        Ok(ActualApplicationExitObservation{
            facts, application:application.facts.clone(), peer, pidfd, observed_at:Instant::now(),
        })
    }
    /// Recheck an actual sample's owner and complete installed identity. This
    /// does not refresh its observation time or turn comparison JSON into a fact.
    pub fn require_exit_state_local(
        &self,
        main: &MainCustodyObservation,
        application: &ActualApplicationObservation,
        observation: &ActualApplicationExitObservation,
        deadline: Instant,
    ) -> Result<(), ControlError> {
        self.require_observations_local(main,application,deadline)?;
        live(&observation.pidfd).map_err(|e|io_error("recheck actual exit-state peer",e))?;
        let held=observation.pidfd.metadata().map_err(|e|io_error("stat exit-state peer",e))?;
        let current=self.pidfd.metadata().map_err(|e|io_error("stat current exit-state peer",e))?;
        if (held.dev(),held.ino())!=(current.dev(),current.ino())
            || observation.peer!=self.observation()? || observation.application!=application.facts
            || observation.facts.epoch()!=&main.facts.epoch
        {
            return Err(ControlError::Invalid("exit-state observation belongs to another original owner or application".into()));
        }
        observation.facts.require_application(&application.facts).map_err(ControlError::Invalid)?;
        check_deadline(Some(deadline))
    }

    /// One actual fixed PM-permission query; borrows the original Main/PM owner
    /// and the caller's original end. No fresh Main or PM request is added.
    pub fn observe_application_permission_state_until(
        &mut self,
        main: &MainCustodyObservation,
        application: &ActualApplicationObservation,
        deadline: Instant,
    ) -> Result<ActualApplicationPermissionObservation, ControlError> {
        self.require_observations_local(main,application,deadline)?;
        if application.facts.user!=0 || !crate::engine_custody::selected_package(&application.facts.package) {
            return Err(ControlError::Invalid("PM-permission requires a selected actual user-zero application".into()));
        }
        let request=ControlRequest::ObserveApplicationPermissionState{
            package:application.facts.package.clone(), expected_epoch:main.facts.epoch.clone(),
        };
        if deadline.saturating_duration_since(Instant::now())<progress::response_timeout(&request) {
            return Err(ControlError::Invalid("original observation budget cannot fit the fixed PM-permission request".into()));
        }
        let facts=permission_state_response(self.request_fixed_until(&request,Some(deadline))?,&application.facts)?;
        self.require_observations_local(main,application,deadline)?;
        let peer=self.observation()?;
        let pidfd=self.pidfd.try_clone().map_err(|e|io_error("retain actual PM-permission peer",e))?;
        live(&pidfd).map_err(|e|io_error("check actual PM-permission peer",e))?;
        check_deadline(Some(deadline))?;
        Ok(ActualApplicationPermissionObservation{
            facts, application:application.facts.clone(), peer, pidfd, observed_at:Instant::now(),
        })
    }
    /// Recheck an actual sample's owner and complete installed identity. This
    /// does not refresh its observation time or turn comparison JSON into a fact.
    pub fn require_permission_state_local(
        &self,
        main: &MainCustodyObservation,
        application: &ActualApplicationObservation,
        observation: &ActualApplicationPermissionObservation,
        deadline: Instant,
    ) -> Result<(), ControlError> {
        self.require_observations_local(main,application,deadline)?;
        live(&observation.pidfd).map_err(|e|io_error("recheck actual PM-permission peer",e))?;
        let held=observation.pidfd.metadata().map_err(|e|io_error("stat PM-permission peer",e))?;
        let current=self.pidfd.metadata().map_err(|e|io_error("stat current PM-permission peer",e))?;
        if (held.dev(),held.ino())!=(current.dev(),current.ino())
            || observation.peer!=self.observation()? || observation.application!=application.facts
            || observation.facts.epoch()!=&main.facts.epoch
        {
            return Err(ControlError::Invalid("PM-permission observation belongs to another original owner or application".into()));
        }
        observation.facts.require_application(&application.facts).map_err(ControlError::Invalid)?;
        check_deadline(Some(deadline))
    }

    /// One actual fixed AppOps query; borrows the original Main/PM owner
    /// and the caller's original end. No fresh Main or PM request is added.
    pub fn observe_application_appops_state_until(
        &mut self,
        main: &MainCustodyObservation,
        application: &ActualApplicationObservation,
        deadline: Instant,
    ) -> Result<ActualApplicationAppOpsObservation, ControlError> {
        self.require_observations_local(main,application,deadline)?;
        if application.facts.user!=0 || !crate::engine_custody::selected_package(&application.facts.package) {
            return Err(ControlError::Invalid("AppOps requires a selected actual user-zero application".into()));
        }
        let request=ControlRequest::ObserveApplicationAppOpsState{
            package:application.facts.package.clone(), expected_epoch:main.facts.epoch.clone(),
        };
        if deadline.saturating_duration_since(Instant::now())<progress::response_timeout(&request) {
            return Err(ControlError::Invalid("original observation budget cannot fit the fixed AppOps request".into()));
        }
        let facts=appops_state_response(self.request_fixed_until(&request,Some(deadline))?,&application.facts)?;
        self.require_observations_local(main,application,deadline)?;
        let peer=self.observation()?;
        let pidfd=self.pidfd.try_clone().map_err(|e|io_error("retain actual AppOps peer",e))?;
        live(&pidfd).map_err(|e|io_error("check actual AppOps peer",e))?;
        check_deadline(Some(deadline))?;
        Ok(ActualApplicationAppOpsObservation{
            facts, application:application.facts.clone(), peer, pidfd, observed_at:Instant::now(),
        })
    }
    /// Recheck an actual sample's owner and complete installed identity. This
    /// does not refresh its observation time or turn comparison JSON into a fact.
    pub fn require_appops_state_local(
        &self,
        main: &MainCustodyObservation,
        application: &ActualApplicationObservation,
        observation: &ActualApplicationAppOpsObservation,
        deadline: Instant,
    ) -> Result<(), ControlError> {
        self.require_observations_local(main,application,deadline)?;
        live(&observation.pidfd).map_err(|e|io_error("recheck actual AppOps peer",e))?;
        let held=observation.pidfd.metadata().map_err(|e|io_error("stat AppOps peer",e))?;
        let current=self.pidfd.metadata().map_err(|e|io_error("stat current AppOps peer",e))?;
        if (held.dev(),held.ino())!=(current.dev(),current.ino())
            || observation.peer!=self.observation()? || observation.application!=application.facts
            || observation.facts.epoch()!=&main.facts.epoch
        {
            return Err(ControlError::Invalid("AppOps observation belongs to another original owner or application".into()));
        }
        observation.facts.require_application(&application.facts).map_err(ControlError::Invalid)?;
        check_deadline(Some(deadline))
    }


    /// One actual fixed Account query; borrows the original Main/PM owner
    /// and the caller's original end. No fresh Main or PM request is added.
    pub fn observe_application_account_state_until(
        &mut self,
        main: &MainCustodyObservation,
        application: &ActualApplicationObservation,
        deadline: Instant,
    ) -> Result<ActualApplicationAccountObservation, ControlError> {
        self.require_observations_local(main,application,deadline)?;
        if application.facts.user!=0 || !crate::engine_custody::selected_package(&application.facts.package) {
            return Err(ControlError::Invalid("Account requires a selected actual user-zero application".into()));
        }
        let request=ControlRequest::ObserveApplicationAccountState{
            package:application.facts.package.clone(), expected_epoch:main.facts.epoch.clone(),
        };
        if deadline.saturating_duration_since(Instant::now())<progress::response_timeout(&request) {
            return Err(ControlError::Invalid("original observation budget cannot fit the fixed Account request".into()));
        }
        let facts=account_state_response(self.request_fixed_until(&request,Some(deadline))?,&application.facts)?;
        self.require_observations_local(main,application,deadline)?;
        let peer=self.observation()?;
        let pidfd=self.pidfd.try_clone().map_err(|e|io_error("retain actual Account peer",e))?;
        live(&pidfd).map_err(|e|io_error("check actual Account peer",e))?;
        check_deadline(Some(deadline))?;
        Ok(ActualApplicationAccountObservation{
            facts, application:application.facts.clone(), peer, pidfd, observed_at:Instant::now(),
            original_end:deadline,main:main.facts.clone(),
        })
    }
    /// Recheck an actual sample's owner and complete installed identity. This
    /// does not refresh its observation time or turn comparison JSON into a fact.
    pub fn require_account_state_local(
        &self,
        main: &MainCustodyObservation,
        application: &ActualApplicationObservation,
        observation: &ActualApplicationAccountObservation,
        deadline: Instant,
    ) -> Result<(), ControlError> {
        self.require_observations_local(main,application,deadline)?;
        live(&observation.pidfd).map_err(|e|io_error("recheck actual Account peer",e))?;
        let held=observation.pidfd.metadata().map_err(|e|io_error("stat Account peer",e))?;
        let current=self.pidfd.metadata().map_err(|e|io_error("stat current Account peer",e))?;
        if (held.dev(),held.ino())!=(current.dev(),current.ino())
            || observation.peer!=self.observation()? || observation.application!=application.facts
            || observation.facts.epoch()!=&main.facts.epoch
            || observation.main!=main.facts || deadline>observation.original_end
            || observation.observed_at>=observation.original_end
        {
            return Err(ControlError::Invalid("Account observation belongs to another original owner or application".into()));
        }
        observation.facts.require_application(&application.facts).map_err(ControlError::Invalid)?;
        check_deadline(Some(deadline))
    }


    /// Partial preservation only: both non-reconstructible samples must belong
    /// to the same live peer, complete Main/PM identity and original work end.
    pub fn require_account_state_pair_local(
        &self,
        main: &MainCustodyObservation,
        application: &ActualApplicationObservation,
        before: &ActualApplicationAccountObservation,
        after: &ActualApplicationAccountObservation,
        deadline: Instant,
    ) -> Result<(), ControlError> {
        self.require_account_state_local(main,application,before,deadline)?;
        self.require_account_state_local(main,application,after,deadline)?;
        if before.original_end!=after.original_end || after.observed_at<=before.observed_at {
            return Err(ControlError::Invalid("account samples do not share the original ordered window".into()));
        }
        before.facts.same_registered_accounts(&after.facts).map_err(ControlError::Invalid)
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

/// An authenticated historical observation of one actual running process.
/// APK byte identity comes from the borrowed normal PM token. The server itself
/// reads PM/AMS metadata, Main, selected runtime bytes and the actual maps.
pub struct EngineMappingObservation {
    facts: crate::engine_custody::RuntimeEngineObservation,
    application: application_probe::ApplicationInspection,
    peer: NativeInspectionPeer,
    pidfd: fs::File,
    observed_at: Instant,
}
impl EngineMappingObservation {
    pub fn facts(&self) -> &crate::engine_custody::RuntimeEngineObservation {
        &self.facts
    }
    /// Separately observed full APK identity, not an engine-request byte read.
    pub fn application(&self) -> &application_probe::ApplicationInspection {
        &self.application
    }
    pub fn peer(&self) -> &NativeInspectionPeer {
        &self.peer
    }
    pub(crate) fn observed_at(&self) -> Instant {
        self.observed_at
    }
}
fn engine_response(
    response: ControlResponse,
    main: &crate::main_custody::RuntimeMainCustody,
    expected: &application_probe::ApplicationInspection,
) -> Result<crate::engine_custody::RuntimeEngineObservation, ControlError> {
    if !response.ok
        || response.state != CellState::Running
        || response.host_pid != Some(expected.epoch.cell_host_pid)
        || response.launch.is_some()
        || response.applications.is_some()
        || response.application_icon.is_some()
        || response.inspection.is_some()
        || response.image_custody.is_some()
        || response.runtime_vintf.is_some()
    {
        return Err(ControlError::Invalid(
            "normal running engine observation did not complete".into(),
        ));
    }
    let body = response.diagnostics.ok_or_else(|| {
        ControlError::Invalid("normal running engine observation omitted its fixed body".into())
    })?;
    if body.len() > crate::engine_custody::MAX_WIRE_BYTES {
        return Err(ControlError::Invalid(
            "engine observation exceeded its fixed bound".into(),
        ));
    }
    let facts: crate::engine_custody::RuntimeEngineObservation = serde_json::from_str(&body)?;
    if !facts.application.matches_inspection(expected) {
        return Err(ControlError::Invalid(
            "actual engine PM metadata differs from the normal full-APK observation".into(),
        ));
    }
    facts
        .validate(main, &facts.application)
        .map_err(ControlError::Invalid)?;
    Ok(facts)
}
impl NativeApplicationInspector {
    /// Observe a package that is already running, joining only actual opaque
    /// Main and PM tokens from this same normal peer. Absence is never native PASS.
    pub fn observe_running_engine(
        &mut self,
        main: &MainCustodyObservation,
        application: &ActualApplicationObservation,
    ) -> Result<EngineMappingObservation, ControlError> {
        self.observe_running_engine_until(
            main,
            application,
            Instant::now() + Duration::from_secs(70),
        )
    }

    /// One request within the caller's original absolute budget. There are no
    /// hidden Main or full-APK requests before or after the engine operation.
    pub fn observe_running_engine_until(
        &mut self,
        main: &MainCustodyObservation,
        application: &ActualApplicationObservation,
        deadline: Instant,
    ) -> Result<EngineMappingObservation, ControlError> {
        self.require_observations_local(main, application, deadline)?;
        let expected = &application.facts;
        if expected.user != 0
            || !crate::engine_custody::selected_package(&expected.package)
            || expected.epoch.boot_id != self.boot_id
        {
            return Err(ControlError::Invalid(
                "engine query differs from the selected actual application".into(),
            ));
        }
        let response = self.request_fixed_until(
            &ControlRequest::ObserveApplicationEngine {
                package: expected.package.clone(),
                user: expected.user,
                expected_epoch: expected.epoch.clone(),
            },
            Some(deadline),
        )?;
        let facts = engine_response(response, &main.facts, expected)?;
        self.require_observations_local(main, application, deadline)?;
        let peer = self.observation()?;
        let pidfd = self
            .pidfd
            .try_clone()
            .map_err(|e| io_error("retain actual engine observer peer", e))?;
        live(&pidfd).map_err(|e| io_error("check retained engine peer", e))?;
        check_deadline(Some(deadline))?;
        Ok(EngineMappingObservation {
            facts,
            application: expected.clone(),
            peer,
            pidfd,
            observed_at: Instant::now(),
        })
    }

    /// A second actual running observation, still under the original caller
    /// budget. A closed process fails; a saved result never substitutes for it.
    pub fn revalidate_engine_until(
        &mut self,
        main: &MainCustodyObservation,
        application: &ActualApplicationObservation,
        prior: &EngineMappingObservation,
        deadline: Instant,
    ) -> Result<(), ControlError> {
        check_deadline(Some(deadline))?;
        live(&prior.pidfd).map_err(|e| io_error("recheck engine peer", e))?;
        let before = prior
            .pidfd
            .metadata()
            .map_err(|e| io_error("stat retained engine peer", e))?;
        let current = self
            .pidfd
            .metadata()
            .map_err(|e| io_error("stat current engine peer", e))?;
        if (before.dev(), before.ino()) != (current.dev(), current.ino())
            || prior.peer != self.observation()?
            || application.facts != prior.application
        {
            return Err(ControlError::Invalid(
                "engine observation belongs to another peer or installed application".into(),
            ));
        }
        let after = self.observe_running_engine_until(main, application, deadline)?;
        if after.peer != prior.peer
            || after.facts.main != prior.facts.main
            || after.facts.process != prior.facts.process
            || after.facts.source != prior.facts.source
            || after.facts.actual_engine != prior.facts.actual_engine
            || after.facts.mappings != prior.facts.mappings
            || after.facts.native_executable != prior.facts.native_executable
            || !after.facts.runtime_abi.same_process(&prior.facts.runtime_abi)
            || after.observed_at <= prior.observed_at
        {
            return Err(ControlError::Invalid(
                "original App process, engine inode or mappings changed".into(),
            ));
        }
        live(&prior.pidfd).map_err(|e| io_error("finish retained engine peer check", e))?;
        check_deadline(Some(deadline))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn native_leaf_pm_token_parser_rejects_foreign_or_incomplete_actual_response() {
        let epoch = crate::main_custody::tests::sample().epoch;
        let app:application_probe::ApplicationInspection=serde_json::from_value(serde_json::json!({
            "package":"com.example.fixture","user":0,"uid":10123,"version_code":1,"epoch":epoch,
            "apks":[{"name":"base.apk","path":"/data/app/fixture/base.apk","bytes":4,"sha256":"a".repeat(64)}]
        })).unwrap();
        let response = ControlResponse {
            ok: true,
            state: CellState::Running,
            message: String::new(),
            host_pid: Some(app.epoch.cell_host_pid),
            launch: None,
            applications: None,
            application_icon: None,
            diagnostics: None,
            inspection: Some(app.clone()),
            image_custody: None,
            runtime_vintf: None,
        };
        assert_eq!(
            application_response(response.clone(), &app.package, 0).unwrap(),
            app
        );
        for case in 0..10 {
            let mut changed = response.clone();
            match case {
                0 => changed.ok = false,
                1 => changed.state = CellState::Quarantined,
                2 => changed.host_pid = Some(999),
                3 => changed.inspection = None,
                4 => changed.inspection.as_mut().unwrap().package = "com.other".into(),
                5 => changed.inspection.as_mut().unwrap().uid = 100123,
                6 => changed.inspection.as_mut().unwrap().apks.clear(),
                7 => changed
                    .inspection
                    .as_mut()
                    .unwrap()
                    .apks
                    .push(app.apks[0].clone()),
                8 => changed.inspection.as_mut().unwrap().apks[0].name = "split.apk".into(),
                _ => changed.inspection.as_mut().unwrap().apks[0].sha256 = "caller".into(),
            }
            assert!(application_response(changed, &app.package, 0).is_err());
        }
        // Parsed JSON never creates ActualApplicationObservation here.
    }

    #[test]
    fn main_observation_requires_the_fixed_successful_response_and_exact_body() {
        let facts = crate::main_custody::tests::sample();
        let response = ControlResponse {
            ok: true,
            state: CellState::Running,
            message: String::new(),
            host_pid: Some(facts.epoch.cell_host_pid),
            launch: None,
            applications: None,
            application_icon: None,
            diagnostics: Some(serde_json::to_string(&facts).unwrap()),
            inspection: None,
            image_custody: None,
            runtime_vintf: None,
        };
        assert_eq!(
            main_response(response.clone(), &facts.epoch).unwrap(),
            facts
        );
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
    fn current_main_request_accepts_no_caller_epoch_pid_or_qualification() {
        let value = serde_json::json!({"command":"observe_current_runtime_main"});
        let request: ControlRequest = serde_json::from_value(value.clone()).unwrap();
        assert!(matches!(request, ControlRequest::ObserveCurrentRuntimeMain {}));
        assert_eq!(progress::response_timeout(&request), Duration::from_secs(70));
        for (key, extra) in [("expected_epoch", serde_json::json!({})),
            ("pid", serde_json::json!(1234)), ("path", serde_json::json!("/proc/1")),
            ("runtime_qualified", serde_json::json!(true))] {
            let mut bad = value.clone();
            bad[key] = extra;
            assert!(serde_json::from_value::<ControlRequest>(bad).is_err());
        }
    }

    #[test]
    fn current_main_response_requires_actual_boot_and_full_normal_response() {
        let facts = crate::main_custody::tests::sample();
        let response = ControlResponse {
            ok: true, state: CellState::Running, message: String::new(),
            host_pid: Some(facts.epoch.cell_host_pid), launch: None,
            applications: None, application_icon: None,
            diagnostics: Some(serde_json::to_string(&facts).unwrap()),
            inspection: None, image_custody: None, runtime_vintf: None,
        };
        assert_eq!(current_main_response(response.clone(), &facts.epoch.boot_id).unwrap(), facts);
        assert!(current_main_response(response.clone(), "other-boot").is_err());
        for case in 0..6 {
            let mut bad = response.clone();
            match case {
                0 => bad.ok = false,
                1 => bad.state = CellState::Starting,
                2 => bad.host_pid = Some(999),
                3 => bad.launch = Some("unrelated".into()),
                4 => bad.diagnostics = None,
                _ => bad.diagnostics = Some("true".into()),
            }
            assert!(current_main_response(bad, &facts.epoch.boot_id).is_err());
        }
        // These are comparison-parser tests, never an opaque Main factory.
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
