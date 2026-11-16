//! The normal daemon's production backend. This module uses only the shared
//! transport/validation helpers; it never calls the development lifecycle or
//! its numeric-PID Android command helpers.
use super::*;
use crate::production_cell::{CellPoll, ProductionCell};
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
    parent: fs::File,
    name: CString,
    node: Option<fs::File>,
    identity: Option<(u64, u64, u32, u32)>,
    retirement_attempted: bool,
}

impl OwnedListener {
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
        self.listener
            .as_ref()
            .ok_or_else(|| ControlError::Invalid("control listener retired".into()))
    }

    fn initialize(mut self) -> Result<Self, ControlError> {
        self.set_mode()?;
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
    // A stale or foreign entry remains an explicit recovery decision.
    OwnedListener::bind_at(parent, c"control.sock".to_owned())?.initialize()
}

struct ProductionDaemon {
    active: Option<ProductionCell>,
    state: CellState,
    last_result: String,
    progress: Reporter,
}

impl ProductionDaemon {
    fn new() -> Self {
        Self {
            active: None,
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
                self.active = None;
                self.state = CellState::Stopped;
            }
            Ok(CellPoll::FailedAfterRetirement { message, exit }) => {
                self.last_result =
                    format!("production cell failed: {message}; actual retirement: {exit:?}");
                self.active = None;
                self.state = CellState::Stopped;
            }
            Err(error) => {
                self.last_result = error.to_string();
                self.active = None;
                self.state = CellState::Quarantined;
            }
        }
    }

    fn start(&mut self, peer_uid: u32, spec: &Path) -> Result<ControlResponse, ControlError> {
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
        let selected = ProductionSelection::load(spec, peer_uid)
            .map_err(|error| ControlError::Invalid(error.to_string()))?;
        if let Some(active) = &self.active {
            authorize_uid(peer_uid, active.spec().host_uid)?;
            if !active.same_selection(&selected) {
                return Err(ControlError::Invalid(
                    "another exact production selection is already owned".into(),
                ));
            }
            return Ok(self.success("selected production cell is already owned"));
        }
        self.state = CellState::Starting;
        let progress = &self.progress;
        match ProductionCell::start(selected, |message| progress.report(message)) {
            Ok(cell) => {
                self.active = Some(cell);
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
                Ok(self.success(self.last_result.clone()))
            }
            Err(error) => {
                self.state = CellState::Quarantined;
                self.last_result = error.to_string();
                Err(ControlError::Invalid(self.last_result.clone()))
            }
        }
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

    fn handle(
        &mut self,
        peer_uid: u32,
        request: ControlRequest,
        file: Option<fs::File>,
        shutdown: &AtomicBool,
    ) -> ControlResponse {
        self.poll();
        let result = match request {
            ControlRequest::Start { spec } => self.start(peer_uid, &spec),
            ControlRequest::Stop => self.stop(peer_uid),
            ControlRequest::Restart { spec } => {
                // Validate the next exact selection before stopping any owner.
                ProductionSelection::load(&spec, peer_uid)
                    .map_err(|error| ControlError::Invalid(error.to_string()))
                    .and_then(|_| self.stop(peer_uid))
                    .and_then(|_| self.start(peer_uid, &spec))
            }
            ControlRequest::Status | ControlRequest::Readiness => self.status(peer_uid),
            ControlRequest::WaitReady => self.wait_ready(peer_uid, shutdown),
            _ => {
                // No fallback to development's find-by-PID, nsenter, shell,
                // APK helper or automatic Start. A future application bridge
                // must consume a ReadyTreeWitness from this exact owner.
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
            match listener.accept() {
                Ok((mut stream, _)) => {
                    let response = match receive_request(&mut stream) {
                        Ok((peer, request, file, streaming)) => {
                            daemon.progress = Reporter::new(&stream, streaming)?;
                            daemon.handle(peer, request, file, shutdown)
                        }
                        Err(error) => daemon.failure(error.to_string()),
                    };
                    if let Err(error) = send_response(&mut stream, &response) {
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
        daemon.state = CellState::Starting;
        assert_eq!(daemon.status(1000).unwrap().state, CellState::Starting);
        assert!(!daemon.wait_ready(1000, &stopped).is_ok());
    }
}
