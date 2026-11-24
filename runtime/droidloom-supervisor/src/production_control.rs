//! The normal daemon's production backend. This module uses only the shared
//! transport/validation helpers; it never calls the development lifecycle or
//! its numeric-PID Android command helpers.
use super::*;
use crate::production_cell::{CellPoll, ProductionCell};
use crate::production_configuration::ConfigurationReadGuard;
use crate::production_execution::PreparationAdmission;
use crate::production_mac::{
    BrokerAcceptedStream, BrokerSelectedListener, HostPeerIssuer, KernelFirstAcceptedStream,
    KernelFirstBrokerListener, MacError,
};
use crate::production_namespace::TreeExit;
use crate::production_readiness::BootProperty;
use crate::production_selection::ProductionSelection;
use std::ffi::CString;
use std::os::fd::{FromRawFd, RawFd};
use std::os::unix::ffi::OsStrExt;

fn trusted_directory(parent: RawFd, name: &std::ffi::CStr) -> Result<fs::File, ControlError> {
    let fd = unsafe {
        libc::openat(
            parent,
            name.as_ptr(),
            libc::O_PATH
                | libc::O_DIRECTORY
                | libc::O_NOFOLLOW
                | libc::O_CLOEXEC
                | libc::O_NONBLOCK,
        )
    };
    if fd < 0 {
        return Err(io_error(
            "open fixed production socket parent",
            io::Error::last_os_error(),
        ));
    }
    let file = unsafe { fs::File::from_raw_fd(fd) };
    let m = file
        .metadata()
        .map_err(|source| io_error("inspect held socket parent", source))?;
    if !m.is_dir() || m.uid() != 0 || m.gid() != 0 || m.mode() & 0o022 != 0 {
        return Err(ControlError::Invalid(
            "production socket parent is not root-owned and sealed".into(),
        ));
    }
    Ok(file)
}

// This owner exists immediately after bind, before chmod, metadata validation
// or nonblocking setup can fail. The node is an O_PATH reference to the actual
// filesystem socket; the listener's sockfs inode is not that identity.
struct OwnedListener {
    listener: Option<UnixListener>,
    selected: Option<BrokerSelectedListener>,
    early: Option<KernelFirstBrokerListener>,
    parent: fs::File,
    name: CString,
    node: Option<fs::File>,
    identity: Option<(u64, u64, u32, u32)>,
    retirement_attempted: bool,
}

fn selected_socket_io(error: MacError) -> io::Error {
    match error {
        MacError::Io(error) => error,
        other => io::Error::other(other.to_string()),
    }
}

fn selected_socket_control(error: MacError) -> ControlError {
    io_error(
        "observe original selected control socket",
        selected_socket_io(error),
    )
}

enum AcceptedConnection<'listener> {
    Ordinary(UnixStream),
    Selected(BrokerAcceptedStream<'listener>),
    Early(KernelFirstAcceptedStream<'listener>),
}

impl<'a> AcceptedConnection<'a> {
    fn into_package(self) -> Result<ProductionAcceptedStream<'a>, ControlError> {
        let value = match self {
            Self::Selected(stream) => ProductionConnection::Selected(stream),
            Self::Early(stream) => ProductionConnection::Early(stream),
            Self::Ordinary(_) => {
                return Err(ControlError::Invalid(
                    "package retirement requires the original production listener".into(),
                ));
            }
        };
        Ok(ProductionAcceptedStream(value))
    }
    fn stream(&self) -> io::Result<&UnixStream> {
        match self {
            Self::Ordinary(stream) => Ok(stream),
            Self::Selected(stream) => stream.stream().map_err(selected_socket_io),
            Self::Early(stream) => stream.stream().map_err(selected_socket_io),
        }
    }
    fn stream_mut(&mut self) -> io::Result<&mut UnixStream> {
        match self {
            Self::Ordinary(stream) => Ok(stream),
            Self::Selected(stream) => stream.stream_mut().map_err(selected_socket_io),
            Self::Early(stream) => stream.stream_mut().map_err(selected_socket_io),
        }
    }
}

// Only an accepted connection from either typed production owner can issue
// this transport. The development UnixStream variant is deliberately absent.
pub(crate) struct ProductionAcceptedStream<'a>(ProductionConnection<'a>);
enum ProductionConnection<'a> {
    Selected(BrokerAcceptedStream<'a>),
    Early(KernelFirstAcceptedStream<'a>),
}
impl ProductionAcceptedStream<'_> {
    pub(crate) fn stream(&self) -> io::Result<&UnixStream> {
        match &self.0 {
            ProductionConnection::Selected(stream) => stream.stream().map_err(selected_socket_io),
            ProductionConnection::Early(stream) => stream.stream().map_err(selected_socket_io),
        }
    }
    pub(crate) fn stream_mut(&mut self) -> io::Result<&mut UnixStream> {
        match &mut self.0 {
            ProductionConnection::Selected(stream) => {
                stream.stream_mut().map_err(selected_socket_io)
            }
            ProductionConnection::Early(stream) => stream.stream_mut().map_err(selected_socket_io),
        }
    }
}

impl OwnedListener {
    fn bind_early_at(
        parent: fs::File,
        owner: crate::production_execution::RuntimeMacOwner,
        deadline: std::time::Instant,
    ) -> Result<Self, ControlError> {
        let early = KernelFirstBrokerListener::prepare(owner, &parent, deadline)
            .map_err(selected_socket_control)?;
        let mut owned = Self {
            listener: None,
            selected: None,
            early: Some(early),
            parent,
            name: c"control.sock".to_owned(),
            node: None,
            identity: None,
            retirement_attempted: false,
        };
        let bound = owned.early.as_mut().unwrap().bind_and_listen();
        let held = owned
            .early
            .as_ref()
            .unwrap()
            .server_inode()
            .map_err(selected_socket_control)
            .and_then(|inode| {
                inode
                    .try_clone()
                    .map_err(|source| io_error("retain direct control socket inode", source))
            });
        match held {
            Ok(inode) => {
                owned.node = Some(inode);
                owned.observe_node()?;
            }
            Err(inode_error) => {
                return match bound {
                    Ok(()) => Err(inode_error),
                    Err(bind_error) => Err(ControlError::Invalid(format!(
                        "direct listener creation failed: {bind_error}; original inode unavailable: {inode_error}",
                    ))),
                };
            }
        }
        bound.map_err(selected_socket_control)?;
        Ok(owned)
    }

    fn bind_selected_at(
        parent: fs::File,
        issuer: HostPeerIssuer,
        deadline: std::time::Instant,
    ) -> Result<Self, ControlError> {
        // prepare has no worker. Store the original issuer and parent before
        // creating the first selected namespace, helper or listening socket.
        let selected = BrokerSelectedListener::prepare(issuer, &parent, deadline)
            .map_err(selected_socket_control)?;
        let mut owned = Self {
            listener: None,
            selected: Some(selected),
            early: None,
            parent,
            name: c"control.sock".to_owned(),
            node: None,
            identity: None,
            retirement_attempted: false,
        };
        let bound = owned.selected.as_mut().unwrap().bind_and_listen();
        // A bind may have created the original inode before a later stage
        // fails. Retain that real inode before propagating the original
        // failure, so Drop can apply the same exact unlink checks. Possession
        // of this inode does not certify a listening or usable endpoint.
        let held = owned
            .selected
            .as_ref()
            .unwrap()
            .server_inode()
            .map_err(selected_socket_control)
            .and_then(|inode| {
                inode
                    .try_clone()
                    .map_err(|source| io_error("retain original selected socket inode", source))
            });
        match held {
            Ok(inode) => {
                owned.node = Some(inode);
                owned.observe_node()?;
            }
            Err(inode_error) => {
                return match bound {
                    Ok(()) => Err(inode_error),
                    Err(bind_error) => Err(ControlError::Invalid(format!(
                        "selected listener creation failed: {bind_error}; original inode unavailable: {inode_error}",
                    ))),
                };
            }
        }
        bound.map_err(selected_socket_control)?;
        Ok(owned)
    }

    fn bind_at(parent: fs::File, name: CString) -> Result<Self, ControlError> {
        if name.as_bytes().is_empty()
            || name.as_bytes().contains(&b'/')
            || matches!(name.as_bytes(), b"." | b"..")
        {
            return Err(ControlError::Invalid("socket leaf name is invalid".into()));
        }
        let mut st = std::mem::MaybeUninit::<libc::stat>::uninit();
        let rc = unsafe {
            libc::fstatat(
                parent.as_raw_fd(),
                name.as_ptr(),
                st.as_mut_ptr(),
                libc::AT_SYMLINK_NOFOLLOW,
            )
        };
        if rc == 0 || io::Error::last_os_error().kind() != io::ErrorKind::NotFound {
            return Err(ControlError::Invalid(
                "control socket path is already present or unobservable".into(),
            ));
        }
        let held_path = PathBuf::from(format!("/proc/self/fd/{}", parent.as_raw_fd()))
            .join(std::ffi::OsStr::from_bytes(name.as_bytes()));
        let listener = UnixListener::bind(&held_path)
            .map_err(|source| io_error("bind socket in held directory", source))?;
        let mut owned = Self {
            listener: Some(listener),
            selected: None,
            early: None,
            parent,
            name,
            node: None,
            identity: None,
            retirement_attempted: false,
        };
        let fd = unsafe {
            libc::openat(
                owned.parent.as_raw_fd(),
                owned.name.as_ptr(),
                libc::O_PATH | libc::O_NOFOLLOW | libc::O_CLOEXEC | libc::O_NONBLOCK,
            )
        };
        if fd < 0 {
            // There is no safe pathname-only fallback. The Drop path records
            // that this newly bound entry could not be identity-qualified.
            return Err(io_error(
                "hold new control socket identity",
                io::Error::last_os_error(),
            ));
        }
        owned.node = Some(unsafe { fs::File::from_raw_fd(fd) });
        owned.observe_node()?;
        Ok(owned)
    }

    fn observe_node(&mut self) -> Result<fs::Metadata, ControlError> {
        let node = self.node.as_ref().ok_or_else(|| {
            ControlError::Invalid("new socket identity is unavailable; path is retained".into())
        })?;
        let m = node
            .metadata()
            .map_err(|source| io_error("observe held control socket", source))?;
        if !m.file_type().is_socket() || m.nlink() != 1 {
            return Err(ControlError::Invalid(
                "held control socket type or links differ".into(),
            ));
        }
        let observed = (m.dev(), m.ino(), m.uid(), m.gid());
        if self.identity.is_some_and(|expected| expected != observed) {
            return Err(ControlError::Invalid(
                "held control socket ownership changed".into(),
            ));
        }
        self.identity = Some(observed);
        Ok(m)
    }

    fn set_mode(&mut self) -> Result<(), ControlError> {
        self.observe_node()?;
        let fd = self
            .node
            .as_ref()
            .expect("observed socket descriptor")
            .as_raw_fd();
        // Follow only our held O_PATH FD. A changed directory entry must not
        // redirect chmod to a replacement inode or a symlink target.
        let node_path = PathBuf::from(format!("/proc/self/fd/{fd}"));
        fs::set_permissions(node_path, fs::Permissions::from_mode(0o666))
            .map_err(|source| io_error("set held control socket mode", source))?;
        if self.observe_node()?.mode() & 0o7777 != 0o666 {
            return Err(ControlError::Invalid(
                "held control socket mode differs".into(),
            ));
        }
        Ok(())
    }

    fn listener(&self) -> Result<&UnixListener, ControlError> {
        if let Some(selected) = &self.selected {
            return selected.listener().map_err(selected_socket_control);
        }
        if let Some(early) = &self.early {
            return early.listener().map_err(selected_socket_control);
        }
        self.listener
            .as_ref()
            .ok_or_else(|| ControlError::Invalid("control listener retired".into()))
    }

    fn accept(&self) -> io::Result<AcceptedConnection<'_>> {
        if let Some(selected) = &self.selected {
            return selected
                .accept()
                .map(AcceptedConnection::Selected)
                .map_err(selected_socket_io);
        }
        if let Some(early) = &self.early {
            return early
                .accept()
                .map(AcceptedConnection::Early)
                .map_err(selected_socket_io);
        }
        self.listener
            .as_ref()
            .ok_or_else(|| io::Error::other("ordinary control listener retired"))?
            .accept()
            .map(|(stream, _)| AcceptedConnection::Ordinary(stream))
    }

    fn initialize(mut self) -> Result<Self, ControlError> {
        if self.selected.is_some() || self.early.is_some() {
            // The selected owner set the fixed mode before sealing its inode.
            // A redundant chmod would change that original seal's ctime.
            if self.observe_node()?.mode() & 0o7777 != 0o666 {
                return Err(ControlError::Invalid(
                    "selected control socket mode differs".into(),
                ));
            }
        } else {
            self.set_mode()?;
        }
        self.observe_node()?;
        self.listener()?
            .set_nonblocking(true)
            .map_err(|source| io_error("make production listener nonblocking", source))?;
        Ok(self)
    }

    fn cleanup(&mut self) -> Result<(), ControlError> {
        if self.retirement_attempted {
            return Ok(());
        }
        if let Some(selected) = &mut self.selected {
            // Accepted streams borrow this owner, so they must have closed
            // before mutable retirement. This closes all socket duplicates
            // before the original namespace and issuer; pathname unlink stays
            // exclusively with the held-inode checks below.
            selected.retire().map_err(selected_socket_control)?;
        }
        if let Some(early) = &mut self.early {
            early.retire().map_err(selected_socket_control)?;
        }
        self.retirement_attempted = true;
        // Close the listening endpoint even if the path is foreign or cannot
        // be observed. Never keep serving after an initialization error.
        self.listener.take();
        let node = self.node.as_ref().ok_or_else(|| {
            ControlError::Invalid("new socket has no held inode proof; path was not removed".into())
        })?;
        let held = node
            .metadata()
            .map_err(|source| io_error("recheck held control socket", source))?;
        if !held.file_type().is_socket()
            || self
                .identity
                .is_some_and(|id| id != (held.dev(), held.ino(), held.uid(), held.gid()))
        {
            return Err(ControlError::Invalid(
                "held socket identity changed; path was not removed".into(),
            ));
        }
        let mut st = std::mem::MaybeUninit::<libc::stat>::uninit();
        let rc = unsafe {
            libc::fstatat(
                self.parent.as_raw_fd(),
                self.name.as_ptr(),
                st.as_mut_ptr(),
                libc::AT_SYMLINK_NOFOLLOW,
            )
        };
        if rc < 0 {
            let source = io::Error::last_os_error();
            if source.kind() == io::ErrorKind::NotFound && held.nlink() == 0 {
                return Ok(());
            }
            return Err(io_error("recheck owned socket entry", source));
        }
        let now = unsafe { st.assume_init() };
        if now.st_mode & libc::S_IFMT != libc::S_IFSOCK
            || held.nlink() != 1
            || now.st_nlink != 1
            || (now.st_dev, now.st_ino, now.st_uid, now.st_gid)
                != (held.dev(), held.ino(), held.uid(), held.gid())
        {
            return Err(ControlError::Invalid(
                "control socket entry was replaced; it was not removed".into(),
            ));
        }
        if unsafe { libc::unlinkat(self.parent.as_raw_fd(), self.name.as_ptr(), 0) } != 0 {
            return Err(io_error(
                "unlink held owned socket entry",
                io::Error::last_os_error(),
            ));
        }
        let after = node
            .metadata()
            .map_err(|source| io_error("verify socket unlink", source))?;
        if (after.dev(), after.ino(), after.uid(), after.gid())
            != (held.dev(), held.ino(), held.uid(), held.gid())
            || !after.file_type().is_socket()
            || after.nlink() != 0
        {
            return Err(ControlError::Invalid(
                "owned socket unlink did not retire the held inode".into(),
            ));
        }
        Ok(())
    }

    fn retire(mut self) -> Result<(), ControlError> {
        self.cleanup()
    }
}

impl Drop for OwnedListener {
    fn drop(&mut self) {
        if let Err(error) = self.cleanup() {
            eprintln!("control socket retirement could not be proven: {error}");
        }
    }
}

fn ordinary_socket_parent(socket: &Path) -> Result<(fs::File, CString), ControlError> {
    let parent = socket
        .parent()
        .ok_or_else(|| ControlError::Invalid("socket parent is missing".into()))?;
    let name = socket
        .file_name()
        .ok_or_else(|| ControlError::Invalid("socket leaf is missing".into()))?;
    let parent_name = CString::new(parent.as_os_str().as_bytes())
        .map_err(|_| ControlError::Invalid("socket parent contains NUL".into()))?;
    let name = CString::new(name.as_bytes())
        .map_err(|_| ControlError::Invalid("socket name contains NUL".into()))?;
    let fd = unsafe {
        libc::open(
            parent_name.as_ptr(),
            libc::O_PATH
                | libc::O_DIRECTORY
                | libc::O_NOFOLLOW
                | libc::O_CLOEXEC
                | libc::O_NONBLOCK,
        )
    };
    if fd < 0 {
        return Err(io_error(
            "open ordinary socket parent",
            io::Error::last_os_error(),
        ));
    }
    let parent = unsafe { fs::File::from_raw_fd(fd) };
    let m = parent
        .metadata()
        .map_err(|source| io_error("observe ordinary socket parent", source))?;
    if !m.is_dir() || m.uid() != unsafe { libc::geteuid() } || m.mode() & 0o022 != 0 {
        return Err(ControlError::Invalid(
            "ordinary socket parent is not caller-owned and sealed".into(),
        ));
    }
    Ok((parent, name))
}

fn bind_production_listener(socket: &Path) -> Result<OwnedListener, ControlError> {
    if unsafe { libc::geteuid() } != 0 {
        // Ordinary transport controls may use a caller-owned temporary socket.
        // Production Start still independently requires real/effective root.
        let (parent, name) = ordinary_socket_parent(socket)?;
        return OwnedListener::bind_at(parent, name)?.initialize();
    }
    if socket != Path::new(DEFAULT_CONTROL_SOCKET) {
        return Err(ControlError::Invalid(
            "root production broker uses its fixed lifecycle socket".into(),
        ));
    }
    let root = trusted_directory(libc::AT_FDCWD, c"/")?;
    let run = trusted_directory(root.as_raw_fd(), c"run")?;
    let parent = trusted_directory(run.as_raw_fd(), c"droidloom")?;
    // Acquire the actual startup selection and MAC pair before any listener
    // resource. The shared configuration guard is released only after bind;
    // the original sealed descriptors remain in the listener's issuer.
    let deadline = std::time::Instant::now() + std::time::Duration::from_secs(10);
    let guard = ConfigurationReadGuard::acquire()
        .map_err(|error| ControlError::Invalid(error.to_string()))?;
    let selection = ProductionSelection::load(&guard, Path::new("/etc/droidloom/cell.json"), 0)
        .map_err(|error| ControlError::Invalid(error.to_string()))?;
    let preparation = PreparationAdmission::acquire(selection)
        .map_err(|error| ControlError::Invalid(error.to_string()))?;
    let context = preparation.owner();
    preparation
        .revalidate(context.selection())
        .map_err(|error| ControlError::Invalid(error.to_string()))?;
    let issuer = HostPeerIssuer::broker(context.clone()).map_err(selected_socket_control)?;
    let owned =
        OwnedListener::bind_selected_at(parent, issuer, deadline.min(preparation.deadline()))?
            .initialize()?;
    guard
        .revalidate()
        .map_err(|error| ControlError::Invalid(error.to_string()))?;
    preparation
        .revalidate(context.selection())
        .map_err(|error| ControlError::Invalid(error.to_string()))?;
    if std::time::Instant::now() >= deadline {
        return Err(io_error(
            "selected control listener setup deadline",
            io::Error::from_raw_os_error(libc::ETIMEDOUT),
        ));
    }
    // This is startup socket custody only. No Android Start, identity lease,
    // active tree, readiness result or package retirement is issued here.
    Ok(owned)
}

#[path = "production_early_application_control.rs"]
mod early_application;
pub(crate) use early_application::EarlyApplicationControl;

struct ProductionDaemon {
    active: Option<ProductionCell>,
    // Kept only by this original daemon. Neither ControlResponse nor an on-disk
    // status record can reconstruct or grant authority from these return values.
    last_retirement: Option<TreeExit>,
    // Actual duplicate descriptors from the same selection passed to this
    // daemon's successful Start; retained with its terminal owner result.
    owned_selection: Option<ProductionSelection>,
    state: CellState,
    last_result: String,
    progress: Reporter,
}

impl ProductionDaemon {
    fn new() -> Self {
        Self {
            active: None,
            last_retirement: None,
            owned_selection: None,
            state: CellState::Stopped,
            last_result: "production cell is stopped".into(),
            progress: Reporter::default(),
        }
    }

    fn success(&self, message: impl Into<String>) -> ControlResponse {
        ControlResponse {
            ok: true,
            state: self.state,
            message: message.into(),
            host_pid: self.active.as_ref().and_then(ProductionCell::host_pid),
            launch: None,
            applications: None,
            application_icon: None,
            diagnostics: None,
            inspection: None,
            window: None,
            window_image: None,
            image_custody: None,
        }
    }

    fn failure(&self, message: impl Into<String>) -> ControlResponse {
        let mut response = self.success(message);
        response.ok = false;
        response
    }

    fn authorize_active(&self, peer_uid: u32) -> Result<(), ControlError> {
        let active = self
            .active
            .as_ref()
            .ok_or_else(|| ControlError::Invalid("production cell is not running".into()))?;
        authorize_uid(peer_uid, active.spec().host_uid)
    }

    fn poll(&mut self) {
        if self.state == CellState::Quarantined {
            return;
        }
        let Some(active) = self.active.as_mut() else {
            return;
        };
        match active.poll() {
            Ok(CellPoll::Live(BootProperty::Complete)) => self.state = CellState::Running,
            Ok(CellPoll::Live(_)) => self.state = CellState::Starting,
            Ok(CellPoll::Exited(exit)) => {
                self.last_result = format!("owned production cell exited and retired: {exit:?}");
                self.last_retirement = Some(exit);
                self.active = None;
                self.state = CellState::Stopped;
            }
            Ok(CellPoll::FailedAfterRetirement { message, exit }) => {
                self.last_result =
                    format!("production cell failed: {message}; actual retirement: {exit:?}");
                self.last_retirement = Some(exit);
                self.active = None;
                self.state = CellState::Stopped;
            }
            Err(error) => {
                self.last_result = error.to_string();
                self.last_retirement = None;
                self.owned_selection = None;
                self.active = None;
                self.state = CellState::Quarantined;
            }
        }
    }

    fn start(&mut self, peer_uid: u32, spec: &Path) -> Result<ControlResponse, ControlError> {
        let guard = ConfigurationReadGuard::acquire()
            .map_err(|error| ControlError::Invalid(error.to_string()))?;
        self.start_under_guard(peer_uid, spec, &guard)
    }

    fn start_under_guard(
        &mut self,
        peer_uid: u32,
        spec: &Path,
        guard: &ConfigurationReadGuard,
    ) -> Result<ControlResponse, ControlError> {
        if self.state == CellState::Quarantined {
            return Err(ControlError::Invalid(
                "previous production ownership is quarantined; independent retirement is required"
                    .into(),
            ));
        }
        // The user identity comes from SO_PEERCRED; the privileged execution
        // process must itself be the real/effective root broker. A user-owned
        // diagnostic daemon cannot acquire authority by reading a selection.
        if unsafe { libc::getuid() } != 0 || unsafe { libc::geteuid() } != 0 {
            return Err(ControlError::Invalid(
                "production Start requires the root broker".into(),
            ));
        }
        let selected = ProductionSelection::load(guard, spec, peer_uid)
            .map_err(|error| ControlError::Invalid(error.to_string()))?;
        if selected
            .host_managed_launcher()
            .map_err(|error| ControlError::Invalid(error.to_string()))?
            .is_some()
        {
            return Err(ControlError::Invalid(
                "the selected host-managed container must start through its system service".into(),
            ));
        }
        if let Some(active) = &self.active {
            authorize_uid(peer_uid, active.spec().host_uid)?;
            if !active.same_selection(&selected) {
                return Err(ControlError::Invalid(
                    "another exact production selection is already owned".into(),
                ));
            }
            return Ok(self.success("selected production cell is already owned"));
        }
        // Only a validated new Start reaches this boundary. A previous owner's
        // terminal evidence cannot stand for any resources this attempt creates,
        // even if preparation subsequently fails or quarantines.
        guard
            .revalidate()
            .map_err(|error| ControlError::Invalid(error.to_string()))?;
        let retained_selection = selected
            .retain_for_retirement()
            .map_err(|error| ControlError::Invalid(error.to_string()))?;
        self.last_retirement = None;
        self.owned_selection = None;
        self.state = CellState::Starting;
        let progress = &self.progress;
        match ProductionCell::start(selected, |message| progress.report(message)) {
            Ok(cell) => {
                self.active = Some(cell);
                self.owned_selection = Some(retained_selection);
                if let Err(error) = guard.revalidate() {
                    // A changed configuration chain must not leave a newly
                    // created owner running after Start reports failure.
                    self.stop(0)?;
                    return Err(ControlError::Invalid(error.to_string()));
                }
                self.last_result =
                    "original init executed; waiting for genuine Android readiness".into();
                // Never call a parked/prepared child Running. A later poll
                // needs actual exec identity plus the real property ABI.
                Ok(self.success(self.last_result.clone()))
            }
            Err(failure) => {
                self.state = if failure.retirement_requires_review {
                    CellState::Quarantined
                } else {
                    CellState::Stopped
                };
                self.last_result = failure.error.to_string();
                Err(ControlError::Invalid(self.last_result.clone()))
            }
        }
    }

    fn restart(&mut self, peer_uid: u32, spec: &Path) -> Result<ControlResponse, ControlError> {
        let guard = ConfigurationReadGuard::acquire()
            .map_err(|error| ControlError::Invalid(error.to_string()))?;
        // One shared lock spans prevalidation, original-owner retirement and
        // the next Start. An exclusive package writer cannot enter the gap.
        ProductionSelection::load(&guard, spec, peer_uid)
            .map_err(|error| ControlError::Invalid(error.to_string()))?;
        self.stop(peer_uid)?;
        self.start_under_guard(peer_uid, spec, &guard)
    }

    fn stop(&mut self, peer_uid: u32) -> Result<ControlResponse, ControlError> {
        if self.state == CellState::Quarantined {
            return Err(ControlError::Invalid(self.last_result.clone()));
        }
        let Some(active) = self.active.as_ref() else {
            return Ok(self.success("production cell is already stopped"));
        };
        authorize_uid(peer_uid, active.spec().host_uid)?;
        let mut active = self.active.take().expect("authorized owned cell");
        match active.stop() {
            Ok(exit) => {
                self.state = CellState::Stopped;
                self.last_result = format!("owned production cell retired: {exit:?}");
                self.last_retirement = Some(exit);
                Ok(self.success(self.last_result.clone()))
            }
            Err(error) => {
                self.state = CellState::Quarantined;
                self.last_result = error.to_string();
                self.last_retirement = None;
                self.owned_selection = None;
                Err(ControlError::Invalid(self.last_result.clone()))
            }
        }
    }

    fn original_package_selection(&self) -> Result<&ProductionSelection, ControlError> {
        if self.state == CellState::Quarantined
            || (self.active.is_none() && self.last_retirement.is_none())
        {
            return Err(ControlError::Invalid(
                "no complete original package resource owner is retained".into(),
            ));
        }
        self.owned_selection.as_ref().ok_or_else(|| {
            ControlError::Invalid("original owner has no retained sealed selection".into())
        })
    }

    fn package_retirement(
        &mut self,
        transaction: &mut super::package::ServerTransaction<'_>,
    ) -> Result<(), ControlError> {
        let invalid = |error: &dyn std::fmt::Display| ControlError::Invalid(error.to_string());
        // Authenticate and preflight before creating a deny fence or stopping
        // anything. A fresh daemon or ordinary already-stopped reply cannot pass.
        transaction.revalidate().map_err(|e| invalid(&e))?;
        let selected = self.original_package_selection()?;
        selected.revalidate().map_err(|e| invalid(&e))?;
        if selected.package_binding() != transaction.selection().package_binding() {
            return Err(ControlError::Invalid(
                "package request differs from this actual owner's selection".into(),
            ));
        }
        if self.active.is_none() {
            self.last_retirement
                .as_ref()
                .expect("retained original owner checked")
                .verify_package_retirement()
                .map_err(|e| invalid(&e))?;
        }
        transaction
            .fence_before_retirement()
            .map_err(|e| invalid(&e))?;
        self.original_package_selection()?
            .revalidate()
            .map_err(|e| invalid(&e))?;
        transaction.revalidate().map_err(|e| invalid(&e))?;
        self.stop(0)?;
        let selected = self.original_package_selection()?;
        selected.revalidate().map_err(|e| invalid(&e))?;
        if selected.package_binding() != transaction.selection().package_binding() {
            return Err(ControlError::Invalid(
                "original selected inputs changed during retirement".into(),
            ));
        }
        let exit = self.last_retirement.as_ref().ok_or_else(|| {
            ControlError::Invalid(
                "original owner did not produce actual resource retirement".into(),
            )
        })?;
        // TreeExit and every resource proof remain retained by this original
        // daemon even if the final reply is lost. No new peer is auto-adopted.
        transaction.complete(exit).map_err(|e| invalid(&e))
    }

    fn status(&self, peer_uid: u32) -> Result<ControlResponse, ControlError> {
        if self.active.is_some() {
            self.authorize_active(peer_uid)?;
        }
        let message = match self.state {
            CellState::Stopped | CellState::Quarantined => self.last_result.clone(),
            CellState::Starting => {
                "original init is owned; Android readiness has not completed".into()
            }
            CellState::Running => {
                "same owned original init is live and Android boot readiness is complete".into()
            }
        };
        Ok(self.success(message))
    }

    fn wait_ready(
        &mut self,
        peer_uid: u32,
        shutdown: &AtomicBool,
    ) -> Result<ControlResponse, ControlError> {
        self.authorize_active(peer_uid)?;
        let deadline = Instant::now() + ANDROID_READY_TIMEOUT;
        self.progress
            .report("Waiting for the owned Android init and its real boot property...");
        loop {
            self.poll();
            match self.state {
                CellState::Running => return self.status(peer_uid),
                CellState::Stopped | CellState::Quarantined => {
                    return Err(ControlError::Invalid(self.last_result.clone()));
                }
                CellState::Starting => {}
            }
            if shutdown.load(Ordering::Relaxed) {
                return Err(ControlError::Invalid(
                    "broker shutdown was requested".into(),
                ));
            }
            if Instant::now() >= deadline {
                return Err(ControlError::Invalid(
                    "owned Android readiness deadline expired".into(),
                ));
            }
            thread::sleep(ANDROID_SERVICE_RETRY_INTERVAL);
        }
    }

    fn launch(
        &mut self,
        peer_uid: u32,
        spec: &Path,
        package: &str,
        component: Option<&str>,
        resolution: Option<&str>,
        user: u32,
    ) -> Result<ControlResponse, ControlError> {
        // The public request owns one deadline, including selection, initial
        // readiness, all adapter effects, and the final owner checks.
        let deadline = std::time::Instant::now()
            .checked_add(droidloom_task_launcher::effects::LAUNCH_LIMIT)
            .ok_or_else(|| ControlError::Invalid("production launch deadline overflow".into()))?;
        let before = || {
            if std::time::Instant::now() < deadline {
                Ok(())
            } else {
                Err(ControlError::Invalid(
                    "production launch deadline expired".into(),
                ))
            }
        };
        before()?;
        validate_package(package)?;
        validate_android_user(user)?;
        if let Some(component) = component {
            validate_component(component)?;
            if component
                .split_once('/')
                .is_none_or(|(owner, _)| owner != package)
            {
                return Err(ControlError::Invalid(format!(
                    "launcher component {component} does not belong to package {package}"
                )));
            }
        }
        let resolution = resolution
            .map(|value| -> Result<(u32, u32), ControlError> {
                let checked = parse_launch_resolution(value)?;
                let (width, height) = checked.split_once('x').ok_or_else(|| {
                    ControlError::Invalid("validated launch extent is incomplete".into())
                })?;
                let dimension = |value: &str| {
                    value.parse::<u32>().map_err(|_| {
                        ControlError::Invalid("validated launch dimension is invalid".into())
                    })
                };
                Ok((dimension(width)?, dimension(height)?))
            })
            .transpose()?;
        self.authorize_active(peer_uid)?;
        if self.state != CellState::Running {
            return Err(ControlError::Invalid(
                "production launch requires current Android readiness".into(),
            ));
        }
        before()?;
        // One original configuration read lease spans selection, the entire
        // owned launch, and the final readiness/identity checks. Launch never
        // creates or starts a cell to satisfy a request.
        let guard = ConfigurationReadGuard::acquire()
            .map_err(|error| ControlError::Invalid(error.to_string()))?;
        before()?;
        let selected = ProductionSelection::load(&guard, spec, peer_uid)
            .map_err(|error| ControlError::Invalid(error.to_string()))?;
        before()?;
        let active = self.active.as_mut().expect("authorized active owner");
        if !active.same_selection(&selected) {
            return Err(ControlError::Invalid(
                "launch specification differs from the owned production selection".into(),
            ));
        }
        guard
            .revalidate()
            .map_err(|error| ControlError::Invalid(error.to_string()))?;
        let request = droidloom_task_launcher::LaunchRequest {
            package: package.into(),
            component: component.map(str::to_owned),
            resolution,
            user,
        };
        self.progress.report("Launching the application...");
        before()?;
        let launched = active
            .launch_application(&request, deadline)
            .map_err(|error| ControlError::Invalid(error.to_string()));
        // Revalidate the original owner even when the operation failed. Keep
        // its original operation/retirement error if this poll also fences it.
        self.poll();
        let observed = launched?;
        before()?;
        guard
            .revalidate()
            .map_err(|error| ControlError::Invalid(error.to_string()))?;
        selected
            .revalidate()
            .map_err(|error| ControlError::Invalid(error.to_string()))?;
        if self.state != CellState::Running
            || self
                .active
                .as_ref()
                .is_none_or(|active| !active.same_selection(&selected))
        {
            return Err(ControlError::Invalid(
                "production tree or selection changed after application launch".into(),
            ));
        }
        let binding = observed.binding;
        let mut response = self.success(format!("launched {package}"));
        response.launch = Some(format!(
            "object={} composer_display={} android_display={} task={}",
            binding.object, binding.composer_display, binding.android_display, binding.task
        ));
        response.inspection = Some(observed.application.clone());
        before()?;
        Ok(response)
    }

    fn inspect_application(
        &mut self,
        peer_uid: u32,
        package: &str,
        user: u32,
    ) -> Result<ControlResponse, ControlError> {
        self.authorize_active(peer_uid)?;
        if self.state != CellState::Running {
            return Err(ControlError::Invalid(
                "production inspection requires current Android readiness".into(),
            ));
        }
        let observed = self
            .active
            .as_mut()
            .expect("authorized active owner")
            .inspect_application(package, user)
            .map_err(|error| ControlError::Invalid(error.to_string()));
        // Any unproven command retirement fences the same original owner.
        self.poll();
        let observed = observed?;
        if self.state != CellState::Running {
            return Err(ControlError::Invalid(
                "production tree changed after application inspection".into(),
            ));
        }
        let mut response = self.success("Installed package metadata and APK bytes observed in the owned production tree; application acceptance remains pending");
        response.inspection = Some(observed.application);
        response.image_custody = observed.image_custody;
        Ok(response)
    }

    fn open_browser(
        &mut self,
        peer_uid: u32,
        expected: &application_probe::ApplicationInspection,
        url: &str,
    ) -> Result<ControlResponse, ControlError> {
        validate_android_user(expected.user)?;
        application_probe::validate_https_url(url).map_err(ControlError::Invalid)?;
        self.authorize_active(peer_uid)?;
        if self.state != CellState::Running {
            return Err(ControlError::Invalid(
                "production browser requires current Android readiness".into(),
            ));
        }
        let opened = self
            .active
            .as_mut()
            .expect("authorized active owner")
            .open_browser(expected, url)
            .map_err(|error| ControlError::Invalid(error.to_string()));
        self.poll();
        let (inspection, output) = opened?;
        if self.state != CellState::Running {
            return Err(ControlError::Invalid(
                "production tree changed after browser operation".into(),
            ));
        }
        let mut response = self.success("Implicit Firefox HTTPS activity opened in the owned production tree; rendered content, media and whole-app acceptance remain pending");
        response.inspection = Some(inspection);
        response.launch = Some(output);
        Ok(response)
    }

    fn inspect_contacts_fixture(
        &mut self,
        peer_uid: u32,
        contacts: &application_probe::ApplicationInspection,
        provider: &application_probe::ApplicationInspection,
    ) -> Result<ControlResponse, ControlError> {
        self.authorize_active(peer_uid)?;
        if self.state != CellState::Running {
            return Err(ControlError::Invalid(
                "Contacts provider reads require current Android readiness".into(),
            ));
        }
        let result = self
            .active
            .as_mut()
            .expect("authorized active owner")
            .inspect_contacts_baseline(contacts, provider)
            .map_err(|error| ControlError::Invalid(error.to_string()));
        self.poll();
        let observed = result?;
        if self.state != CellState::Running {
            return Err(ControlError::Invalid(
                "production tree changed during Contacts provider reads".into(),
            ));
        }
        let mut response = self.success(
            "Contacts provider baseline observed in the original owned tree; account topology and create/edit/search/delete acceptance remain pending",
        );
        response.inspection = Some(contacts.clone());
        response.diagnostics = Some(serde_json::to_string(&observed)?);
        Ok(response)
    }

    fn handle(
        &mut self,
        peer_uid: u32,
        request: ControlRequest,
        file: Option<fs::File>,
        shutdown: &AtomicBool,
    ) -> ControlResponse {
        self.poll();
        let result = match request {
            ControlRequest::LaunchOwned { .. } | ControlRequest::Window { .. } =>
                Err(ControlError::Invalid("owned window operations require the original early production frontend".into())),
            ControlRequest::Start { spec } => self.start(peer_uid, &spec),
            ControlRequest::Stop => self.stop(peer_uid),
            ControlRequest::Restart { spec } => self.restart(peer_uid, &spec),
            ControlRequest::Status | ControlRequest::Readiness => self.status(peer_uid),
            ControlRequest::WaitReady => self.wait_ready(peer_uid, shutdown),
            ControlRequest::Launch {
                spec,
                package,
                component,
                resolution,
                user,
            } => {
                if file.is_some() {
                    Err(ControlError::Invalid(
                        "production launch does not accept a descriptor".into(),
                    ))
                } else if shutdown.load(Ordering::Relaxed) {
                    Err(ControlError::Invalid(
                        "broker shutdown was requested".into(),
                    ))
                } else {
                    self.launch(
                        peer_uid,
                        &spec,
                        &package,
                        component.as_deref(),
                        resolution.as_deref(),
                        user,
                    )
                }
            }
            ControlRequest::InspectApplication { package, user } => {
                self.inspect_application(peer_uid, &package, user)
            }
            ControlRequest::OpenBrowser { expected, url } => {
                self.open_browser(peer_uid, &expected, &url)
            }
            ControlRequest::InspectContactsFixture { contacts, provider } => {
                self.inspect_contacts_fixture(peer_uid, &contacts, &provider)
            }
            _ => {
                // Additional app/business actions need dedicated owned-tree
                // adapters. The fixed inspection bridge does not authorize
                // development PID lookup, nsenter, shell, or automatic Start.
                self.authorize_active(peer_uid).and_then(|_| {
                    Err(ControlError::Invalid(
                        "production application bridge has no qualified owned-tree capability"
                            .into(),
                    ))
                })
            }
        };
        drop(file); // An unaccepted SCM file is never opened by pathname/read.
        result.unwrap_or_else(|error| self.failure(error.to_string()))
    }

    fn shutdown(&mut self) -> Result<(), ControlError> {
        if self.state == CellState::Quarantined {
            return Err(ControlError::Invalid(self.last_result.clone()));
        }
        self.stop(0).map(|_| ())
    }
}

pub(super) fn serve(config: &DaemonConfig, shutdown: &AtomicBool) -> Result<(), ControlError> {
    let owned = bind_production_listener(&config.socket)?;
    let listener = owned.listener()?;
    let mut daemon = ProductionDaemon::new();
    let result = (|| {
        loop {
            if shutdown.load(Ordering::Relaxed) {
                return Ok(());
            }
            daemon.poll();
            match owned.accept() {
                Ok(mut accepted) => {
                    match super::package::is_package(
                        accepted
                            .stream()
                            .map_err(|source| io_error("observe accepted stream", source))?,
                    ) {
                        Ok(true) => {
                            let result = accepted.into_package().and_then(|stream| {
                                super::package::ServerTransaction::receive(stream)
                                    .map_err(|e| ControlError::Invalid(e.to_string()))
                                    .and_then(|mut transaction| {
                                        daemon.package_retirement(&mut transaction)
                                    })
                            });
                            if let Err(error) = result {
                                eprintln!("fixed package transaction refused: {error}");
                            }
                            daemon.progress = Reporter::default();
                            continue;
                        }
                        Ok(false) => {}
                        Err(error) => {
                            eprintln!("could not classify bounded production request: {error}");
                            continue;
                        }
                    }
                    let stream = accepted
                        .stream_mut()
                        .map_err(|source| io_error("observe original accepted stream", source))?;
                    let response = match receive_request(stream) {
                        Ok((peer, request, file, streaming)) => {
                            daemon.progress = Reporter::new(stream, streaming)?;
                            daemon.handle(peer, request, file, shutdown)
                        }
                        Err(error) => daemon.failure(error.to_string()),
                    };
                    if let Err(error) = send_response(stream, &response) {
                        eprintln!("could not deliver production response: {error}");
                    }
                    daemon.progress = Reporter::default();
                }
                Err(error) if error.kind() == io::ErrorKind::WouldBlock => {
                    wait_for_client(&listener)?
                }
                Err(source) => return Err(io_error("accept production client", source)),
            }
        }
    })();
    let retired = daemon.shutdown();
    let socket_result = owned.retire();
    result.and(retired).and(socket_result)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn production_stopped_response_does_not_create_resource_retirement() {
        let mut daemon = ProductionDaemon::new();
        // These calls have no cell and therefore make no native Stop or other
        // host operation. Their existing idempotent response is not a proof.
        for _ in 0..2 {
            assert!(daemon.stop(0).unwrap().ok);
            assert_eq!(daemon.state, CellState::Stopped);
            assert!(daemon.active.is_none());
            assert!(daemon.last_retirement.is_none());
        }
        daemon.state = CellState::Quarantined;
        assert!(daemon.stop(0).is_err());
        assert!(daemon.last_retirement.is_none());
    }

    #[test]
    fn package_retirement_requires_the_original_resource_owner_before_any_fence_or_stop() {
        let mut daemon = ProductionDaemon::new();
        assert!(daemon.original_package_selection().is_err());
        assert!(daemon.stop(0).unwrap().ok);
        assert!(daemon.original_package_selection().is_err());
        daemon.state = CellState::Quarantined;
        assert!(daemon.original_package_selection().is_err());
        assert!(daemon.owned_selection.is_none());
        assert!(daemon.last_retirement.is_none());
    }

    #[test]
    fn ordinary_connection_cannot_issue_package_transport() {
        let (stream, _peer) = UnixStream::pair().unwrap();
        assert!(AcceptedConnection::Ordinary(stream).into_package().is_err());
    }

    fn socket_owner(socket: &Path) -> OwnedListener {
        let (parent, name) = ordinary_socket_parent(socket).unwrap();
        OwnedListener::bind_at(parent, name).unwrap()
    }

    fn descriptors_closed(fds: &[RawFd]) {
        for &fd in fds {
            assert_eq!(unsafe { libc::fcntl(fd, libc::F_GETFD) }, -1);
            assert_eq!(io::Error::last_os_error().raw_os_error(), Some(libc::EBADF));
        }
    }

    #[test]
    fn production_socket_guard_cleans_each_initialization_error_and_closes_descriptors() {
        // These are injected, real EBADF/ENOENT failures at the three setup
        // boundaries, not a claim that normal chmod or fcntl failed on host.
        // Every case actually binds a Unix socket and verifies its retirement.
        for stage in 0..3 {
            let directory = tempfile::tempdir().unwrap();
            let socket = directory.path().join("control.sock");
            let mut fds = Vec::new();
            let mut held_observer = None;
            let result = (|| -> Result<(), ControlError> {
                let mut owned = socket_owner(&socket);
                fds = vec![
                    owned.listener().unwrap().as_raw_fd(),
                    owned.parent.as_raw_fd(),
                    owned.node.as_ref().unwrap().as_raw_fd(),
                ];
                held_observer = Some(owned.node.as_ref().unwrap().try_clone().unwrap());
                if stage == 0 {
                    assert_eq!(unsafe { libc::fchmod(-1, 0o666) }, -1);
                    return Err(io_error(
                        "injected chmod failure",
                        io::Error::last_os_error(),
                    ));
                }
                owned.set_mode()?;
                if stage == 1 {
                    fs::symlink_metadata(directory.path().join("absent-injected-metadata-target"))
                        .map_err(|source| io_error("injected metadata failure", source))?;
                }
                owned.observe_node()?;
                assert_eq!(
                    unsafe { libc::fcntl(-1, libc::F_SETFL, libc::O_NONBLOCK) },
                    -1
                );
                Err(io_error(
                    "injected nonblocking failure",
                    io::Error::last_os_error(),
                ))
            })();
            assert!(result.is_err());
            descriptors_closed(&fds);
            assert_eq!(
                held_observer.as_ref().unwrap().metadata().unwrap().nlink(),
                0
            );
            assert_eq!(
                fs::symlink_metadata(&socket).unwrap_err().kind(),
                io::ErrorKind::NotFound
            );
        }
    }

    #[test]
    fn production_socket_guard_preserves_replaced_entry_and_symlink_target() {
        for replace_with_link in [false, true] {
            let directory = tempfile::tempdir().unwrap();
            let socket = directory.path().join("control.sock");
            let sentinel = directory.path().join("sentinel");
            fs::write(&sentinel, b"foreign sentinel").unwrap();
            let owned = socket_owner(&socket).initialize().unwrap();
            let listener_fd = owned.listener().unwrap().as_raw_fd();
            let held = owned.node.as_ref().unwrap().try_clone().unwrap();
            fs::remove_file(&socket).unwrap();
            if replace_with_link {
                std::os::unix::fs::symlink(&sentinel, &socket).unwrap();
            } else {
                fs::write(&socket, b"replacement").unwrap();
            }
            let before = fs::symlink_metadata(&socket).unwrap();
            assert!(owned.retire().is_err());
            descriptors_closed(&[listener_fd]);
            let after = fs::symlink_metadata(&socket).unwrap();
            assert_eq!(
                (
                    before.dev(),
                    before.ino(),
                    before.mode(),
                    before.uid(),
                    before.gid(),
                    before.nlink()
                ),
                (
                    after.dev(),
                    after.ino(),
                    after.mode(),
                    after.uid(),
                    after.gid(),
                    after.nlink()
                )
            );
            assert_eq!(fs::read(&sentinel).unwrap(), b"foreign sentinel");
            assert_eq!(held.metadata().unwrap().nlink(), 0);
            let (parent, name) = ordinary_socket_parent(&socket).unwrap();
            assert!(OwnedListener::bind_at(parent, name).is_err());
            assert_eq!(fs::symlink_metadata(&socket).unwrap().ino(), before.ino());
        }
    }

    #[test]
    fn production_socket_guard_uses_held_parent_and_inode_after_directory_rename() {
        let directory = tempfile::tempdir().unwrap();
        let original = directory.path().join("original");
        let moved = directory.path().join("moved");
        fs::create_dir(&original).unwrap();
        let mut owned = socket_owner(&original.join("control.sock"));
        let held = owned.node.as_ref().unwrap().try_clone().unwrap();
        fs::rename(&original, &moved).unwrap();
        fs::create_dir(&original).unwrap();
        let foreign = original.join("control.sock");
        fs::write(&foreign, b"foreign path").unwrap();
        fs::set_permissions(&foreign, fs::Permissions::from_mode(0o400)).unwrap();
        let foreign_before = fs::metadata(&foreign).unwrap();
        owned.set_mode().unwrap();
        assert_eq!(
            fs::metadata(moved.join("control.sock")).unwrap().mode() & 0o7777,
            0o666
        );
        owned.retire().unwrap();
        assert_eq!(held.metadata().unwrap().nlink(), 0);
        assert!(!moved.join("control.sock").exists());
        let foreign_after = fs::metadata(&foreign).unwrap();
        assert_eq!(
            (
                foreign_before.dev(),
                foreign_before.ino(),
                foreign_before.mode()
            ),
            (
                foreign_after.dev(),
                foreign_after.ino(),
                foreign_after.mode()
            )
        );
        assert_eq!(fs::read(foreign).unwrap(), b"foreign path");
    }

    #[test]
    fn production_socket_guard_without_inode_proof_retains_entry_and_closes_listener() {
        let directory = tempfile::tempdir().unwrap();
        let socket = directory.path().join("control.sock");
        let (parent, name) = ordinary_socket_parent(&socket).unwrap();
        let listener = UnixListener::bind(&socket).unwrap();
        let listener_fd = listener.as_raw_fd();
        // The immediate post-bind state, before O_PATH capture succeeds.
        // Deliberately do not invent an inode identity to authorize cleanup.
        let owned = OwnedListener {
            listener: Some(listener),
            selected: None,
            early: None,
            parent,
            name,
            node: None,
            identity: None,
            retirement_attempted: false,
        };
        assert!(owned.retire().is_err());
        descriptors_closed(&[listener_fd]);
        assert!(
            fs::symlink_metadata(&socket)
                .unwrap()
                .file_type()
                .is_socket()
        );
        fs::remove_file(socket).unwrap(); // owned test fixture, no daemon cleanup credit
    }

    #[test]
    fn production_controller_quarantine_refuses_restart_and_stop_without_releasing_it() {
        let mut daemon = ProductionDaemon::new();
        daemon.state = CellState::Quarantined;
        daemon.last_result = "actual owner exit unproven".into();
        assert!(daemon.start(0, Path::new(DEFAULT_CELL_SPEC)).is_err());
        assert!(daemon.stop(0).is_err());
        assert!(daemon.shutdown().is_err());
        assert_eq!(daemon.state, CellState::Quarantined);
    }

    #[test]
    fn production_controller_preparation_is_not_readiness_and_app_requests_do_not_start() {
        let mut daemon = ProductionDaemon::new();
        let stopped = AtomicBool::new(false);
        let response = daemon.handle(
            1000,
            ControlRequest::Launch {
                spec: PathBuf::from(DEFAULT_CELL_SPEC),
                package: "org.example.app".into(),
                component: None,
                resolution: None,
                user: 0,
            },
            None,
            &stopped,
        );
        assert!(!response.ok);
        assert_eq!(response.state, CellState::Stopped);
        assert!(daemon.active.is_none());
        let inspected = daemon.handle(
            1000,
            ControlRequest::InspectApplication {
                package: "org.example.app".into(),
                user: 0,
            },
            None,
            &stopped,
        );
        assert!(!inspected.ok && inspected.inspection.is_none());
        assert_eq!(inspected.state, CellState::Stopped);
        assert!(daemon.active.is_none());
        daemon.state = CellState::Starting;
        assert_eq!(daemon.status(1000).unwrap().state, CellState::Starting);
        assert!(!daemon.wait_ready(1000, &stopped).is_ok());
    }

    #[test]
    fn production_launch_closes_unaccepted_descriptor_and_honors_shutdown_before_execution() {
        let request = || ControlRequest::Launch {
            spec: PathBuf::from(DEFAULT_CELL_SPEC),
            package: "org.example.app".into(),
            component: None,
            resolution: None,
            user: 0,
        };
        let mut daemon = ProductionDaemon::new();
        let shutdown = AtomicBool::new(false);
        let file = tempfile::tempfile().unwrap();
        let fd = file.as_raw_fd();
        let rejected = daemon.handle(1000, request(), Some(file), &shutdown);
        assert!(!rejected.ok);
        assert!(rejected.message.contains("does not accept a descriptor"));
        assert!(rejected.launch.is_none() && rejected.inspection.is_none());
        descriptors_closed(&[fd]);
        shutdown.store(true, Ordering::Relaxed);
        let rejected = daemon.handle(1000, request(), None, &shutdown);
        assert!(!rejected.ok && rejected.message.contains("shutdown was requested"));
        assert!(rejected.launch.is_none() && rejected.inspection.is_none());
        assert_eq!(daemon.state, CellState::Stopped);
        assert!(daemon.active.is_none());
        assert!(daemon.owned_selection.is_none());
        assert!(daemon.last_retirement.is_none());
    }
}
