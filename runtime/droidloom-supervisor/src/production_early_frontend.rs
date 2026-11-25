//! The existing early MainPID owns presentation. It authenticates Composer
//! before graphical protocol bytes exist on the Linux side, without borrowing
//! ReadyTree (Composer cannot publish Binder until that handshake completes).
use super::{EarlyBoardResources, invalid};
use crate::production_execution::RuntimeMacOwner;
#[path = "production_frontend_observation.rs"]
mod observation;
pub(crate) use observation::{QueryObservation, observe_query};
#[path = "production_frontend_camera.rs"]
mod camera;
#[path = "production_frontend_protocol.rs"]
mod wire;
use std::ffi::{CStr, CString};
use std::fs::{self, File};
use std::io::{self, Read};
use std::os::fd::{AsRawFd, FromRawFd, OwnedFd};
use std::os::unix::fs::{MetadataExt, PermissionsExt};
use std::time::{Duration, Instant};
use wire::{Node, Role, check, cv};

const COMPOSER: &CStr = c"android.hardware.graphics.composer3-service.droidloom";

#[derive(Clone, PartialEq, Eq)]
struct Seal {
    node: Node,
    integers: [u64; 5],
    times: [i64; 4],
}
impl Seal {
    fn of(file: &File) -> io::Result<Self> {
        let m = file.metadata()?;
        Ok(Self {
            node: Node(m.dev(), m.ino()),
            integers: [
                u64::from(m.mode()),
                u64::from(m.uid()),
                u64::from(m.gid()),
                m.nlink(),
                m.len(),
            ],
            times: [m.mtime(), m.mtime_nsec(), m.ctime(), m.ctime_nsec()],
        })
    }
}
fn procfs(file: &File) -> io::Result<()> {
    let mut value: libc::statfs = unsafe { std::mem::zeroed() };
    cv(unsafe { libc::fstatfs(file.as_raw_fd(), &mut value) })?;
    check(
        value.f_type == libc::PROC_SUPER_MAGIC,
        "frontend process evidence is not procfs",
    )
}
fn read_at(parent: &File, name: &CStr) -> io::Result<Vec<u8>> {
    let file = wire::openat(parent, name, libc::O_RDONLY)?;
    procfs(&file)?;
    let mut out = Vec::new();
    file.take(8193).read_to_end(&mut out)?;
    check(
        out.len() <= 8192,
        "frontend process evidence exceeded bound",
    )?;
    Ok(out)
}
fn namespace(directory: &File, name: &str) -> io::Result<File> {
    let ns = wire::openat(directory, c"ns", libc::O_PATH | libc::O_DIRECTORY)?;
    let name = CString::new(name).map_err(|_| invalid("invalid fixed namespace name"))?;
    let raw = cv(unsafe {
        libc::openat(
            ns.as_raw_fd(),
            name.as_ptr(),
            libc::O_RDONLY | libc::O_CLOEXEC,
        )
    })?;
    Ok(unsafe { File::from_raw_fd(raw) })
}
fn namespace_owner(namespace: &File) -> io::Result<File> {
    let raw = cv(unsafe { libc::ioctl(namespace.as_raw_fd(), 0xb701 as libc::c_ulong) })?;
    Ok(unsafe { File::from_raw_fd(raw) })
}
fn start_ticks(directory: &File, pid: u32) -> io::Result<u64> {
    let bytes = read_at(directory, c"stat")?;
    let text = std::str::from_utf8(&bytes).map_err(io::Error::other)?;
    let (head, tail) = text
        .split_once(" (")
        .ok_or_else(|| invalid("process stat lacks comm"))?;
    let (_, fields) = tail
        .rsplit_once(") ")
        .ok_or_else(|| invalid("process stat lacks fields"))?;
    check(
        head.parse::<u32>().ok() == Some(pid),
        "process stat is from another PID",
    )?;
    fields
        .split_ascii_whitespace()
        .nth(19)
        .and_then(|v| v.parse().ok())
        .filter(|n| *n > 0)
        .ok_or_else(|| invalid("process stat has no original start time"))
}
struct ProgramPeer {
    peer: wire::Peer,
    directory: File,
    directory_node: Node,
    start: u64,
    executable: File,
    root: File,
    expected: Seal,
    context: Vec<u8>,
    namespaces: Vec<(&'static str, File, Node)>,
    observer: std::rc::Rc<std::cell::RefCell<observation::Observer>>,
    userns: Option<File>,
    reader_uid: u32,
    reader_gid: u32,
    input: bool,
}
impl ProgramPeer {
    fn acquire(
        socket: &OwnedFd,
        program: &File,
        context: &[u8],
        kind: i32,
        observer: &std::rc::Rc<std::cell::RefCell<observation::Observer>>,
        scope: Option<(&File, u32)>,
    ) -> io::Result<Self> {
        let peer = wire::Peer::acquire_as(socket, context, kind)?;
        let info = wire::pid_info(&peer.pidfd)?;
        wire::exact_ids(&info, peer.uid, peer.gid)?;
        let proc = wire::trusted_directory("/proc")?;
        procfs(&proc)?;
        let name = CString::new(peer.pid.to_string()).unwrap();
        let directory = wire::openat(&proc, &name, libc::O_PATH | libc::O_DIRECTORY)?;
        procfs(&directory)?;
        let userns = scope.map(|(ns, _)| ns.try_clone()).transpose()?;
        let reader_uid = scope.map_or(peer.uid, |(_, id)| id);
        let reader_gid = scope.map_or(peer.gid, |(_, id)| id);
        let input = scope.is_some_and(|(_, id)| id == 0);
        let first = observer.borrow_mut().sample(
            &directory,
            &peer.pidfd,
            userns.as_ref(),
            reader_uid,
            reader_gid,
            input,
        )?;
        let expected = Seal::of(program)?;
        check(
            first.context == context && Seal::of(&first.executable)? == expected,
            "frontend peer initial program or actual role differs",
        )?;
        let mut namespaces = Vec::new();
        for (name, fd) in ["user", "pid", "mnt"].into_iter().zip(first.namespaces) {
            let node = Node::of(&fd)?;
            namespaces.push((name, fd, node));
        }
        let value = Self {
            directory_node: Node::of(&directory)?,
            start: start_ticks(&directory, peer.pid)?,
            executable: first.executable,
            root: first.root,
            context: context.to_vec(),
            expected,
            peer,
            directory,
            namespaces,
            observer: std::rc::Rc::clone(observer),
            userns,
            reader_uid,
            reader_gid,
            input,
        };
        value.revalidate(socket, program)?;
        Ok(value)
    }
    fn revalidate(&self, socket: &OwnedFd, program: &File) -> io::Result<observation::Observation> {
        self.peer.revalidate(socket)?;
        let actual = self.observer.borrow_mut().sample(
            &self.directory,
            &self.peer.pidfd,
            self.userns.as_ref(),
            self.reader_uid,
            self.reader_gid,
            self.input,
        )?;
        check(
            Node::of(&self.directory)? == self.directory_node
                && start_ticks(&self.directory, self.peer.pid)? == self.start
                && Seal::of(&self.executable)? == self.expected
                && Seal::of(program)? == self.expected
                && Seal::of(&actual.executable)? == self.expected
                && Node::of(&actual.root)? == Node::of(&self.root)?
                && actual.context == self.context,
            "registered peer changed its executable, generation, root or actual domain",
        )?;
        for ((_, held, node), now) in self.namespaces.iter().zip(&actual.namespaces) {
            check(
                Node::of(held)? == *node && Node::of(now)? == *node,
                "registered peer namespace changed",
            )?;
        }
        self.peer.revalidate(socket)?;
        Ok(actual)
    }
    fn android(
        &self,
        board: &EarlyBoardResources,
        root: &File,
        role: Role,
        actual: &observation::Observation,
    ) -> io::Result<()> {
        let spec = board.selection().spec();
        let uid = spec
            .subordinate_uids
            .start
            .checked_add(role.android_id())
            .ok_or_else(|| invalid("Composer uid overflow"))?;
        let gid = spec
            .subordinate_gids
            .start
            .checked_add(role.android_id())
            .ok_or_else(|| invalid("Composer gid overflow"))?;
        let info = wire::pid_info(&self.peer.pidfd)?;
        wire::exact_ids(&info, uid, gid)?;
        check(
            info.ppid == board.host_pid() as u32 && self.peer.uid == uid && self.peer.gid == gid,
            "Composer is not the original Android init's system service",
        )?;
        check(
            Node::of(&actual.namespaces[0])? == Node::of(board.user_namespace())?
                && Node::of(&actual.namespaces[1])? == Node::of(board.pid_namespace())?,
            "Composer is outside the original Android namespaces",
        )?;
        check(
            Node::of(&namespace_owner(&actual.namespaces[2])?)?
                == Node::of(board.user_namespace())?,
            "Composer mount namespace belongs to a foreign user namespace",
        )?;
        check(
            Node::of(&actual.root)? == Node::of(root)?,
            "Composer does not use the selected original Android root",
        )?;
        board.revalidate()
    }
    fn presenter(
        &self,
        board: &EarlyBoardResources,
        actual: &observation::Observation,
    ) -> io::Result<()> {
        let info = wire::pid_info(&self.peer.pidfd)?;
        check(
            info.euid == board.selection().spec().host_uid
                && info.euid != 0
                && self.peer.uid == info.euid
                && self.peer.gid == info.egid,
            "presenter uid differs from the original selected desktop user",
        )?;
        wire::exact_ids(&info, self.peer.uid, self.peer.gid)?;
        let own = File::open("/proc/self")?;
        for (index, name) in ["user", "pid"].into_iter().enumerate() {
            check(
                Node::of(&actual.namespaces[index])? == Node::of(&namespace(&own, name)?)?,
                "presenter is not in the original Linux user and PID namespaces",
            )?;
        }
        Ok(())
    }
}

struct Listener {
    fd: OwnedFd,
    parent: File,
    parent_node: Node,
    name: CString,
    node: Option<File>,
    seal: Option<Seal>,
    gid: u32,
    mode: u32,
    socket_type: i32,
}
impl Listener {
    fn bind(parent: File, name: &CStr, gid: u32, mode: u32, socket_type: i32) -> io::Result<Self> {
        let parent_node = Node::of(&parent)?;
        let fd = wire::socket_as(socket_type)?;
        let mut value = Self {
            fd,
            parent,
            parent_node,
            name: name.to_owned(),
            node: None,
            seal: None,
            gid,
            mode,
            socket_type,
        };
        let path = format!(
            "/proc/self/fd/{}/{}",
            value.parent.as_raw_fd(),
            name.to_str().unwrap()
        );
        let (address, length) = wire::address(&path)?;
        cv(unsafe {
            libc::bind(
                value.fd.as_raw_fd(),
                (&address as *const libc::sockaddr_un).cast(),
                length,
            )
        })?;
        value.node = Some(wire::openat(&value.parent, name, libc::O_PATH)?);
        let node = value.node.as_ref().unwrap();
        cv(unsafe { libc::fchownat(node.as_raw_fd(), c"".as_ptr(), 0, gid, libc::AT_EMPTY_PATH) })?;
        fs::set_permissions(
            format!("/proc/self/fd/{}", node.as_raw_fd()),
            fs::Permissions::from_mode(mode),
        )?;
        value.seal = Some(Seal::of(node)?);
        value.revalidate()?;
        cv(unsafe { libc::listen(value.fd.as_raw_fd(), 8) })?;
        wire::socket_shape_as(&value.fd, socket_type, true)?;
        Ok(value)
    }
    fn revalidate(&self) -> io::Result<()> {
        let node = self
            .node
            .as_ref()
            .ok_or_else(|| invalid("frontend listener has no original inode"))?;
        let m = node.metadata()?;
        let current = wire::socket_node(&self.parent, &self.name, 0, self.gid, self.mode)?;
        check(
            Node::of(&self.parent)? == self.parent_node
                && Node::of(&current)? == Node::of(node)?
                && m.nlink() == 1
                && self
                    .seal
                    .as_ref()
                    .is_none_or(|s| Seal::of(node).is_ok_and(|v| v == *s)),
            "original frontend listener inode changed",
        )
    }
    fn accept(&self) -> io::Result<Option<OwnedFd>> {
        self.revalidate()?;
        let raw = unsafe {
            libc::accept4(
                self.fd.as_raw_fd(),
                std::ptr::null_mut(),
                std::ptr::null_mut(),
                libc::SOCK_CLOEXEC | libc::SOCK_NONBLOCK,
            )
        };
        if raw < 0 {
            let e = io::Error::last_os_error();
            return if matches!(
                e.kind(),
                io::ErrorKind::WouldBlock | io::ErrorKind::Interrupted
            ) {
                Ok(None)
            } else {
                Err(e)
            };
        }
        let fd = unsafe { OwnedFd::from_raw_fd(raw) };
        wire::socket_shape_as(&fd, self.socket_type, false)?;
        self.revalidate()?;
        Ok(Some(fd))
    }
    fn unlink(&mut self) -> io::Result<()> {
        if self.node.is_none() {
            return Ok(());
        }
        self.revalidate()?;
        cv(unsafe { libc::unlinkat(self.parent.as_raw_fd(), self.name.as_ptr(), 0) })?;
        check(
            self.node.as_ref().unwrap().metadata()?.nlink() == 0,
            "frontend listener unlink did not retire its actual inode",
        )?;
        self.node.take();
        Ok(())
    }
}
impl Drop for Listener {
    fn drop(&mut self) {
        wire::shutdown(&self.fd);
        if let Err(e) = self.unlink() {
            eprintln!("original frontend socket retirement failed: {e}");
        }
    }
}

struct RuntimeDirectory {
    parent: File,
    directory: File,
    node: Node,
    name: CString,
    mode: u32,
    retired: bool,
}
impl RuntimeDirectory {
    fn create(parent: File, name: &CStr) -> io::Result<Self> {
        cv(unsafe { libc::mkdirat(parent.as_raw_fd(), name.as_ptr(), 0o700) })?;
        let directory = wire::openat(&parent, name, libc::O_RDONLY | libc::O_DIRECTORY)?;
        let mut value = Self {
            node: Node::of(&directory)?,
            parent,
            directory,
            name: name.to_owned(),
            mode: 0o700,
            retired: false,
        };
        cv(unsafe { libc::fchmod(value.directory.as_raw_fd(), 0o711) })?;
        value.mode = 0o711;
        value.revalidate()?;
        Ok(value)
    }
    fn revalidate(&self) -> io::Result<()> {
        let m = self.directory.metadata()?;
        check(
            !self.retired
                && m.uid() == 0
                && m.gid() == 0
                && m.mode() == libc::S_IFDIR | self.mode
                && Node::of(&self.directory)? == self.node
                && Node::of(&wire::openat(
                    &self.parent,
                    &self.name,
                    libc::O_PATH | libc::O_DIRECTORY,
                )?)? == self.node,
            "frontend runtime directory was replaced or changed",
        )
    }
    fn retire(&mut self) -> io::Result<()> {
        if self.retired {
            return Ok(());
        }
        self.revalidate()?;
        cv(unsafe {
            libc::unlinkat(
                self.parent.as_raw_fd(),
                self.name.as_ptr(),
                libc::AT_REMOVEDIR,
            )
        })?;
        check(
            self.directory.metadata()?.nlink() == 0,
            "frontend directory inode remains linked",
        )?;
        self.retired = true;
        Ok(())
    }
}
impl Drop for RuntimeDirectory {
    fn drop(&mut self) {
        if let Err(e) = self.retire() {
            eprintln!("frontend directory retirement failed: {e}");
        }
    }
}

struct Connection {
    socket: OwnedFd,
    peer: ProgramPeer,
}
struct Presenter {
    connection: Connection,
    nonce: Option<[u8; 16]>,
    grant_sent: bool,
    bound: bool,
    deadline: Instant,
}
struct Lane {
    role: Role,
    control: Listener,
    endpoint: Listener,
    presenter: Option<Presenter>,
    android: Option<Connection>,
}
struct Programs {
    root: File,
    presenter: File,
    composer: File,
    input: File,
    jar: File,
    jar_seal: Seal,
    observer: std::rc::Rc<std::cell::RefCell<observation::Observer>>,
}
fn image_file(root: &File, parts: &[&CStr], executable: bool) -> io::Result<File> {
    let mut directory = root.try_clone()?;
    for part in &parts[..parts.len() - 1] {
        directory = wire::openat(&directory, part, libc::O_PATH | libc::O_DIRECTORY)?;
    }
    let file = wire::openat(&directory, parts[parts.len() - 1], libc::O_PATH)?;
    let m = file.metadata()?;
    let mut v: libc::statvfs = unsafe { std::mem::zeroed() };
    cv(unsafe { libc::fstatvfs(file.as_raw_fd(), &mut v) })?;
    check(
        m.is_file()
            && m.nlink() == 1
            && m.mode() & 0o6022 == 0
            && (64..=128 * 1024 * 1024).contains(&m.len())
            && v.f_flag & libc::ST_RDONLY != 0,
        "selected Android frontend input is not sealed on its readonly image",
    )?;
    if executable {
        check(
            m.mode() & 0o111 != 0,
            "selected frontend program is not executable",
        )?;
    }
    Ok(file)
}
impl Programs {
    fn android(&self, role: Role) -> &File {
        if role == Role::Composer {
            &self.composer
        } else {
            &self.input
        }
    }
    fn android_peer(
        &self,
        c: &Connection,
        board: &EarlyBoardResources,
        role: Role,
    ) -> io::Result<()> {
        let actual = c.peer.revalidate(&c.socket, self.android(role))?;
        c.peer.android(board, &self.root, role, &actual)?;
        if role != Role::Composer {
            check(
                Seal::of(&self.jar)? == self.jar_seal,
                "the selected input bridge JAR changed",
            )?;
            let argv = &actual.command;
            let fields: Vec<_> = argv.split(|b| *b == 0).filter(|s| !s.is_empty()).collect();
            check(
                fields.len() == 3
                    && [
                        b"app_process".as_slice(),
                        b"/system/bin/app_process",
                        b"/system/bin/app_process64",
                    ]
                    .contains(&fields[0])
                    && fields[1] == b"/system/bin"
                    && fields[2] == b"com.android.droidloom.input.InputBridge",
                "input service is not the fixed production class entrypoint",
            )?;
            let environment = &actual.environment;
            let values: Vec<_> = environment.split(|b| *b == 0).collect();
            check(
                values
                    .iter()
                    .filter(|v| v.starts_with(b"CLASSPATH="))
                    .copied()
                    .eq(
                        [
                            b"CLASSPATH=/system_ext/framework/droidloom-input-bridge.jar"
                                .as_slice(),
                        ],
                    )
                    && !values
                        .iter()
                        .any(|v| v.starts_with(b"LD_PRELOAD=") || v.starts_with(b"LD_AUDIT=")),
                "input service classpath or injected loader environment differs",
            )?;
        }
        c.peer.revalidate(&c.socket, self.android(role)).map(|_| ())
    }
}
impl Lane {
    fn revoke(&mut self) {
        if let Some(c) = self.android.take() {
            wire::shutdown(&c.socket);
        }
        if let Some(p) = self.presenter.take() {
            wire::shutdown(&p.connection.socket);
        }
    }
    fn validate(
        &self,
        board: &EarlyBoardResources,
        programs: &Programs,
        original: Option<Node>,
    ) -> io::Result<()> {
        self.control.revalidate()?;
        self.endpoint.revalidate()?;
        if let Some(c) = &self.android {
            programs.android_peer(c, board, self.role)?;
        }
        if let Some(p) = &self.presenter {
            let actual = p
                .connection
                .peer
                .revalidate(&p.connection.socket, &programs.presenter)?;
            p.connection.peer.presenter(board, &actual)?;
            if let Some(original) = original {
                check(
                    Node::of(&p.connection.peer.peer.pidfd)? == original,
                    "companion registration is not the same original presenter",
                )?;
            }
            if p.bound {
                wire::control_live(&p.connection.socket)?;
            }
        }
        Ok(())
    }
    fn progress(
        &mut self,
        board: &EarlyBoardResources,
        programs: &Programs,
        original: Option<Node>,
    ) -> io::Result<()> {
        if let Err(e) = self.validate(board, programs, original) {
            self.revoke();
            board.revalidate()?;
            self.control.revalidate()?;
            self.endpoint.revalidate()?;
            eprintln!("frontend {:?} registration revoked: {e}", self.role);
        }
        if let Some(socket) = self.control.accept()? {
            let accepted = (|| {
                check(
                    self.presenter.is_none(),
                    "an original presenter connection is already active",
                )?;
                let peer = ProgramPeer::acquire(
                    &socket,
                    &programs.presenter,
                    wire::PRESENTER_CONTEXT,
                    libc::SOCK_SEQPACKET,
                    &programs.observer,
                    None,
                )?;
                let actual = peer.revalidate(&socket, &programs.presenter)?;
                peer.presenter(board, &actual)?;
                if let Some(original) = original {
                    check(
                        Node::of(&peer.peer.pidfd)? == original,
                        "companion presenter differs from Composer owner",
                    )?;
                }
                Ok::<_, io::Error>(Presenter {
                    connection: Connection { socket, peer },
                    nonce: None,
                    grant_sent: false,
                    bound: false,
                    deadline: Instant::now() + Duration::from_secs(5),
                })
            })();
            match accepted {
                Ok(p) => self.presenter = Some(p),
                Err(e) => eprintln!("frontend {:?} presenter rejected: {e}", self.role),
            }
        }
        if let Some(socket) = self.endpoint.accept()? {
            let accepted = (|| {
                check(
                    self.android.is_none(),
                    "an original Android endpoint is already active",
                )?;
                let peer = ProgramPeer::acquire(
                    &socket,
                    programs.android(self.role),
                    self.role.context(),
                    self.role.socket_type(),
                    &programs.observer,
                    Some((board.user_namespace(), self.role.android_id())),
                )?;
                let connection = Connection { socket, peer };
                programs.android_peer(&connection, board, self.role)?;
                Ok::<_, io::Error>(connection)
            })();
            match accepted {
                Ok(p) => self.android = Some(p),
                Err(e) => eprintln!("frontend {:?} Android peer rejected: {e}", self.role),
            }
        }
        if let Err(e) = self.exchange(board, programs, original) {
            self.revoke();
            eprintln!("frontend {:?} handshake rejected: {e}", self.role);
        }
        Ok(())
    }
    fn exchange(
        &mut self,
        board: &EarlyBoardResources,
        programs: &Programs,
        original: Option<Node>,
    ) -> io::Result<()> {
        self.validate(board, programs, original)?;
        let Some(p) = self.presenter.as_mut() else {
            return Ok(());
        };
        if !p.bound {
            if (p.nonce.is_none() || p.grant_sent) && Instant::now() >= p.deadline {
                return Err(invalid("frontend handshake deadline expired"));
            }
            if let Some(record) = wire::receive(&p.connection.socket)? {
                if let Some(nonce) = p.nonce {
                    check(p.grant_sent, "acknowledgement before a real grant")?;
                    wire::reply(&record, wire::ACK, nonce)?;
                    p.bound = true;
                } else {
                    check(
                        record.kind == wire::HELLO,
                        "frontend registration must start with Hello",
                    )?;
                    p.nonce = Some(record.nonce);
                }
            }
        }
        if let (Some(nonce), Some(android)) = (p.nonce, self.android.as_ref()) {
            if !p.grant_sent {
                let actual = p
                    .connection
                    .peer
                    .revalidate(&p.connection.socket, &programs.presenter)?;
                p.connection.peer.presenter(board, &actual)?;
                programs.android_peer(android, board, self.role)?;
                let record = wire::Record {
                    kind: wire::GRANT,
                    nonce,
                    pid: android.peer.peer.pid,
                    uid: android.peer.peer.uid,
                    gid: android.peer.peer.gid,
                    fds: vec![
                        android.socket.try_clone()?,
                        android.peer.peer.pidfd.try_clone()?,
                    ],
                };
                match wire::send(&p.connection.socket, &record) {
                    Ok(()) => {
                        p.grant_sent = true;
                        p.deadline = Instant::now() + Duration::from_secs(5);
                        programs.android_peer(android, board, self.role)?;
                        board.revalidate()?;
                    }
                    Err(e)
                        if matches!(
                            e.kind(),
                            io::ErrorKind::WouldBlock | io::ErrorKind::Interrupted
                        ) =>
                    {
                        ()
                    }
                    Err(e) => return Err(e),
                }
            }
        }
        Ok(())
    }
    fn retire(&mut self) -> io::Result<()> {
        self.revoke();
        self.control.unlink()?;
        self.endpoint.unlink()
    }
}
impl Drop for Lane {
    fn drop(&mut self) {
        self.revoke();
    }
}

pub(super) struct Frontend<'a> {
    board: &'a EarlyBoardResources,
    owner: &'a RuntimeMacOwner,
    programs: Programs,
    lanes: Vec<Lane>,
    camera: Option<camera::CameraLane>,
    control_parent: RuntimeDirectory,
    android_parent: RuntimeDirectory,
    retired: bool,
}
pub(super) struct FrontendRetirement {
    _original_endpoints_retired: (),
}
impl<'a> Frontend<'a> {
    pub(super) fn prepare(
        board: &'a EarlyBoardResources,
        owner: &'a RuntimeMacOwner,
        root: &File,
    ) -> io::Result<Self> {
        board.revalidate()?;
        owner.objects().map_err(io::Error::other)?;
        let presenter = wire::openat(
            &wire::trusted_directory("/usr/bin")?,
            c"droidloom-wayland",
            libc::O_RDONLY,
        )?;
        let p = presenter.metadata()?;
        check(
            p.is_file()
                && p.uid() == 0
                && p.gid() == 0
                && p.nlink() == 1
                && p.mode() == libc::S_IFREG | 0o755,
            "installed presenter is not its root-owned normal executable",
        )?;
        let composer = image_file(root, &[c"vendor", c"bin", c"hw", COMPOSER], true)?;
        let input = image_file(root, &[c"system", c"bin", c"app_process64"], true)?;
        let jar = image_file(
            root,
            &[
                c"system",
                c"system_ext",
                c"framework",
                c"droidloom-input-bridge.jar",
            ],
            false,
        )?;
        let programs = Programs {
            root: root.try_clone()?,
            presenter,
            composer,
            input,
            jar_seal: Seal::of(&jar)?,
            jar,
            observer: std::rc::Rc::new(std::cell::RefCell::new(observation::Observer::default())),
        };
        let directory =
            RuntimeDirectory::create(wire::trusted_directory("/run")?, c"droidloom-frontend")?;
        let android = RuntimeDirectory::create(directory.directory.try_clone()?, c"android")?;
        let groups = board.selection().spec().subordinate_gids;
        let mut lanes = Vec::new();
        for role in Role::ALL {
            let control = Listener::bind(
                directory.directory.try_clone()?,
                role.control(),
                0,
                0o666,
                libc::SOCK_SEQPACKET,
            )?;
            let gid = groups
                .start
                .checked_add(role.android_id())
                .ok_or_else(|| invalid("frontend gid overflow"))?;
            let endpoint = Listener::bind(
                android.directory.try_clone()?,
                role.endpoint(),
                gid,
                0o620,
                role.socket_type(),
            )?;
            lanes.push(Lane {
                role,
                control,
                endpoint,
                presenter: None,
                android: None,
            });
        }
        let camera = camera::CameraLane::prepare(board, owner, root, &android.directory)?;
        let value = Self {
            board,
            owner,
            programs,
            lanes,
            camera,
            control_parent: directory,
            android_parent: android,
            retired: false,
        };
        value.board.revalidate()?;
        Ok(value)
    }
    /// Borrow the actual owner directory before its readonly clone is attached.
    /// This descriptor is never reconstructed from a receipt or caller path.
    pub(super) fn projection(&self) -> io::Result<&File> {
        self.programs.observer.borrow().clean()?;
        self.board.revalidate()?;
        self.owner.objects().map_err(io::Error::other)?;
        self.control_parent.revalidate()?;
        self.android_parent.revalidate()?;
        for lane in &self.lanes {
            lane.control.revalidate()?;
            lane.endpoint.revalidate()?;
        }
        if let Some(camera) = &self.camera {
            camera.revalidate(self.board)?;
        }
        let mut names = fs::read_dir(format!(
            "/proc/self/fd/{}",
            self.android_parent.directory.as_raw_fd()
        ))?
        .map(|e| e.map(|e| e.file_name()))
        .collect::<io::Result<Vec<_>>>()?;
        names.sort();
        let mut expected = Role::ALL
            .map(|role| std::ffi::OsString::from(role.endpoint().to_str().unwrap()))
            .to_vec();
        if self.camera.is_some() {
            expected.push(std::ffi::OsString::from("camera"));
        }
        expected.sort();
        check(
            names == expected,
            "frontend projection has an extra or missing object",
        )?;
        Ok(&self.android_parent.directory)
    }
    pub(super) fn progress(&mut self) -> io::Result<()> {
        self.projection()?;
        if let Some(camera) = &mut self.camera {
            camera.progress(self.board)?;
        }
        let original_before = self.lanes[0]
            .presenter
            .as_ref()
            .map(|p| Node::of(&p.connection.peer.peer.pidfd))
            .transpose()?;
        self.lanes[0].progress(self.board, &self.programs, None)?;
        let original = self.lanes[0]
            .presenter
            .as_ref()
            .filter(|p| p.bound)
            .map(|p| Node::of(&p.connection.peer.peer.pidfd))
            .transpose()?;
        if original_before != original || original.is_none() {
            for lane in &mut self.lanes[1..] {
                lane.revoke();
            }
        }
        if let Some(original) = original {
            for lane in &mut self.lanes[1..] {
                lane.progress(self.board, &self.programs, Some(original))?;
            }
        }
        self.programs.observer.borrow().clean()?;
        self.board.revalidate()
    }
    pub(super) fn retire(&mut self) -> io::Result<()> {
        if self.retired {
            return Ok(());
        }
        if let Some(camera) = &mut self.camera {
            camera.retire()?;
        }
        for lane in &mut self.lanes {
            lane.revoke();
        }
        self.programs.observer.borrow_mut().retire()?;
        for lane in &mut self.lanes {
            lane.retire()?;
        }
        self.android_parent.retire()?;
        self.control_parent.retire()?;
        self.retired = true;
        Ok(())
    }
    pub(super) fn retire_with_proof(&mut self) -> io::Result<FrontendRetirement> {
        check(!self.retired, "original frontend retirement was already consumed")?;
        self.retire()?;
        Ok(FrontendRetirement { _original_endpoints_retired: () })
    }
}
impl Drop for Frontend<'_> {
    fn drop(&mut self) {
        if let Err(e) = self.retire() {
            eprintln!("frontend retirement failed: {e}");
        }
    }
}
