//! Explicit privileged source fixture. No installed unit or capability graph
//! is changed. Missing sudo/root/kernel facts fail; there are no skip paths.
use hepta_agent_transport::{
    PeerPolicy, RootControlPathError as Error, RootControlPathPolicy as Policy,
    RootOwnedControlListener as Listener, RootPathControlConnection as Connection,
};
use std::ffi::CString;
use std::fs::{self, File};
use std::io::{Read, Write};
use std::mem::zeroed;
use std::os::fd::{AsRawFd, FromRawFd, OwnedFd};
use std::os::unix::ffi::OsStrExt;
use std::os::unix::fs::PermissionsExt;
use std::os::unix::net::UnixStream;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::atomic::{AtomicU32, Ordering};
use std::time::{Duration, Instant};

// Independently selected test-profile roles, never peer-derived approval.
const TEST_CLIENT_UID: u32 = 65534;
const TEST_CLIENT_GID: u32 = 65534;
static NEXT: AtomicU32 = AtomicU32::new(0);
struct Fixture {
    root: PathBuf,
    path: PathBuf,
}
impl Fixture {
    fn new() -> Self {
        let root = PathBuf::from(format!(
            "/run/hepta-g2-rootpath-{}-{}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir(&root).unwrap();
        fs::set_permissions(&root, fs::Permissions::from_mode(0o750)).unwrap();
        chown(&root, 0, TEST_CLIENT_GID);
        let path = root.join("control.sock");
        Self { root, path }
    }
    fn policy(&self) -> Policy {
        Policy::new(&self.path, TEST_CLIENT_GID, 0o750, TEST_CLIENT_GID, 0o660).unwrap()
    }
    fn socket(&self, kind: i32, listen: bool) -> OwnedFd {
        let fd = unsafe { libc::socket(libc::AF_UNIX, kind | libc::SOCK_CLOEXEC, 0) };
        assert!(fd >= 0);
        let fd = unsafe { OwnedFd::from_raw_fd(fd) };
        let mut addr: libc::sockaddr_un = unsafe { zeroed() };
        addr.sun_family = libc::AF_UNIX as libc::sa_family_t;
        let name = self.path.as_os_str().as_bytes();
        for (to, from) in addr.sun_path.iter_mut().zip(name) {
            *to = *from as libc::c_char;
        }
        let len =
            (std::mem::offset_of!(libc::sockaddr_un, sun_path) + name.len() + 1) as libc::socklen_t;
        assert_eq!(
            unsafe { libc::bind(fd.as_raw_fd(), std::ptr::addr_of!(addr).cast(), len) },
            0
        );
        chown(&self.path, 0, TEST_CLIENT_GID);
        fs::set_permissions(&self.path, fs::Permissions::from_mode(0o660)).unwrap();
        if listen {
            assert_eq!(unsafe { libc::listen(fd.as_raw_fd(), 2) }, 0);
        }
        fd
    }
    fn listener(&self) -> Listener {
        Listener::from_inherited(self.socket(libc::SOCK_SEQPACKET, true), &self.policy()).unwrap()
    }
}
impl Drop for Fixture {
    fn drop(&mut self) {
        fs::remove_dir_all(&self.root).unwrap();
    }
}
fn chown(path: &Path, uid: u32, gid: u32) {
    let name = CString::new(path.as_os_str().as_bytes()).unwrap();
    assert_eq!(unsafe { libc::chown(name.as_ptr(), uid, gid) }, 0);
}
fn policy(uid: u32, gid: u32, pid: Option<u32>) -> PeerPolicy {
    PeerPolicy {
        expected_uid: uid,
        expected_gid: Some(gid),
        expected_pid: pid,
    }
}
fn ceiling() -> Instant {
    Instant::now() + Duration::from_secs(3)
}
fn child(body: impl FnOnce()) -> u32 {
    let parent = std::process::id();
    let pid = unsafe { libc::fork() };
    assert!(pid >= 0);
    if pid == 0 {
        assert_eq!(
            unsafe { libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGKILL) },
            0
        );
        assert_eq!(unsafe { libc::getppid() } as u32, parent);
        unsafe { libc::alarm(8) };
        let result = std::panic::catch_unwind(std::panic::AssertUnwindSafe(body));
        unsafe { libc::_exit(if result.is_ok() { 0 } else { 101 }) };
    }
    pid as u32
}
fn unprivileged() {
    let parent = unsafe { libc::getppid() };
    assert_eq!(unsafe { libc::setgroups(0, std::ptr::null()) }, 0);
    assert_eq!(
        unsafe { libc::setresgid(TEST_CLIENT_GID, TEST_CLIENT_GID, TEST_CLIENT_GID) },
        0
    );
    assert_eq!(
        unsafe { libc::setresuid(TEST_CLIENT_UID, TEST_CLIENT_UID, TEST_CLIENT_UID) },
        0
    );
    // setuid clears PDEATHSIG; arm it again without claiming a production unit.
    assert_eq!(
        unsafe { libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGKILL) },
        0
    );
    assert_eq!(unsafe { libc::getppid() }, parent);
}
fn reap(pid: u32) {
    let until = Instant::now() + Duration::from_secs(4);
    loop {
        let mut status = 0;
        let result = unsafe { libc::waitpid(pid as i32, &mut status, libc::WNOHANG) };
        assert!(result >= 0);
        if result != 0 {
            assert_eq!(status, 0, "actual owned child exit");
            return;
        }
        if Instant::now() >= until {
            // This unreaped original child PID cannot have been reused.
            unsafe {
                libc::kill(pid as i32, libc::SIGKILL);
                libc::waitpid(pid as i32, &mut status, 0);
            }
            panic!("bounded owned child retirement");
        }
        std::thread::sleep(Duration::from_millis(2));
    }
}
fn stream(fd: OwnedFd) -> UnixStream {
    let value = UnixStream::from(fd);
    value.set_nonblocking(false).unwrap();
    value
        .set_read_timeout(Some(Duration::from_secs(2)))
        .unwrap();
    value
        .set_write_timeout(Some(Duration::from_secs(2)))
        .unwrap();
    value
}
fn inventory() -> Vec<(u32, PathBuf)> {
    let names: Vec<_> = fs::read_dir("/proc/self/fd")
        .unwrap()
        .map(|e| e.unwrap().file_name())
        .collect();
    let mut entries: Vec<_> = names
        .into_iter()
        .filter_map(|n| {
            let fd: u32 = n.to_str().unwrap().parse().unwrap();
            fs::read_link(format!("/proc/self/fd/{fd}"))
                .ok()
                .map(|p| (fd, p))
        })
        .collect();
    entries.sort();
    entries
}
fn invalid_configuration() {
    for name in [
        "relative",
        "/run/a/../b",
        "/run/a/./b",
        "/run//b",
        "/run/a/",
        "/run/a\0b",
        "/run/a\nb",
        "/run/%61/b",
        "/run/é/b",
        "/",
        "/leaf",
    ] {
        assert!(matches!(
            Policy::new(Path::new(name), 0, 0o750, 0, 0o660),
            Err(Error::InvalidConfiguration)
        ));
    }
    let long = format!("/run/{}", "a".repeat(104));
    assert!(Policy::new(Path::new(&long), 0, 0o750, 0, 0o660).is_err());
    for (d, s) in [
        (0o770, 0o660),
        (0o755, 0o660),
        (0o750, 0o666),
        (0o750, 0o4600),
    ] {
        assert!(Policy::new(Path::new("/run/a/b"), 0, d, 0, s).is_err());
    }
}
fn descriptor_and_creator() {
    for (kind, listen) in [(libc::SOCK_STREAM, true), (libc::SOCK_SEQPACKET, false)] {
        let f = Fixture::new();
        assert!(matches!(
            Listener::from_inherited(f.socket(kind, listen), &f.policy()),
            Err(Error::WrongDescriptor)
        ));
    }
    let f = Fixture::new();
    assert!(matches!(
        Listener::from_inherited(File::open("/dev/null").unwrap().into(), &f.policy()),
        Err(Error::WrongDescriptor)
    ));
    let fd = f.socket(libc::SOCK_SEQPACKET, true);
    let inherited = duplicate(fd.as_raw_fd());
    let pid = child(|| {
        assert!(matches!(
            Listener::from_inherited(inherited, &f.policy()),
            Err(Error::ListenerCreatorMismatch)
        ));
    });
    reap(pid);
    // The parent's real original listening descriptor is still live.
    let pid = child(|| {
        unprivileged();
        assert!(matches!(
            Listener::from_inherited(duplicate(fd.as_raw_fd()), &f.policy()),
            Err(Error::PrivilegedProfileRequired)
        ));
    });
    reap(pid);
    drop(Listener::from_inherited(fd, &f.policy()).unwrap());
}
fn duplicate(fd: i32) -> OwnedFd {
    let result = unsafe { libc::fcntl(fd, libc::F_DUPFD_CLOEXEC, 3) };
    assert!(result >= 0);
    unsafe { OwnedFd::from_raw_fd(result) }
}
fn bad_paths() {
    for cut in 0..5 {
        let f = Fixture::new();
        let fd = f.socket(libc::SOCK_SEQPACKET, true);
        match cut {
            0 => fs::set_permissions(&f.root, fs::Permissions::from_mode(0o770)).unwrap(),
            1 => fs::set_permissions(&f.path, fs::Permissions::from_mode(0o666)).unwrap(),
            2 => chown(&f.path, TEST_CLIENT_UID, TEST_CLIENT_GID),
            3 => fs::hard_link(&f.path, f.root.join("alias.sock")).unwrap(),
            4 => {
                let old = f.root.join("original.sock");
                fs::rename(&f.path, &old).unwrap();
                std::os::unix::fs::symlink(&old, &f.path).unwrap();
            }
            _ => unreachable!(),
        }
        assert!(matches!(
            Listener::from_inherited(fd, &f.policy()),
            Err(Error::PathRefused)
        ));
    }
    let f = Fixture::new();
    let fd = f.socket(libc::SOCK_SEQPACKET, true);
    let old = f.root.with_extension("old");
    fs::rename(&f.root, &old).unwrap();
    std::os::unix::fs::symlink(&old, &f.root).unwrap();
    assert!(matches!(
        Listener::from_inherited(fd, &f.policy()),
        Err(Error::PathRefused)
    ));
    fs::remove_file(&f.root).unwrap();
    fs::rename(&old, &f.root).unwrap();
}
fn actual_bound_inode_and_replacement() {
    let f = Fixture::new();
    let old = f.socket(libc::SOCK_SEQPACKET, true);
    let before = fs::metadata(&f.path).unwrap();
    use std::os::unix::fs::MetadataExt;
    let socket_stat = unsafe {
        let mut s: libc::stat = zeroed();
        assert_eq!(libc::fstat(old.as_raw_fd(), &mut s), 0);
        s
    };
    assert_ne!(
        socket_stat.st_ino,
        before.ino(),
        "fd inode is not pathname inode"
    );
    fs::remove_file(&f.path).unwrap();
    let replacement = f.socket(libc::SOCK_SEQPACKET, true);
    assert!(
        matches!(
            Listener::from_inherited(old, &f.policy()),
            Err(Error::PathRefused)
        ),
        "actual kernel old bound dentry is unlinked"
    );
    drop(replacement);
    fs::remove_file(&f.path).unwrap();
    let mut listener = f.listener();
    fs::remove_file(&f.path).unwrap();
    let replacement = f.socket(libc::SOCK_SEQPACKET, true);
    assert!(matches!(
        listener.accept_before(policy(0, 0, None), ceiling()),
        Err(Error::PathRefused)
    ));
    assert!(matches!(
        listener.accept_before(policy(0, 0, None), ceiling()),
        Err(Error::Retired)
    ));
    drop(replacement);
}
fn exchange(cut: u8) {
    let f = Fixture::new();
    let mut listener = f.listener();
    let deadline = ceiling();
    let owner = std::process::id();
    let pid = child(|| {
        unprivileged();
        let original = deadline;
        let connection =
            Connection::connect_before(&f.policy(), policy(0, 0, Some(owner)), original).unwrap();
        assert_eq!(connection.deadline().unwrap(), original);
        connection
            .consume_before(|fd, received, custody| {
                assert_eq!(received, original);
                let verifier = custody.verifier().unwrap();
                let mut socket = stream(fd);
                socket.write_all(b"X").unwrap();
                let mut reply = [0];
                socket.read_exact(&mut reply).unwrap();
                assert_eq!(&reply, b"Y");
                verifier.verify_current().unwrap();
                drop(custody);
                assert!(matches!(verifier.verify_current(), Err(Error::Retired)));
            })
            .unwrap();
    });
    let connection = listener
        .accept_before(
            policy(TEST_CLIENT_UID, TEST_CLIENT_GID, Some(pid)),
            deadline,
        )
        .unwrap();
    assert_eq!(connection.deadline().unwrap(), deadline);
    let (mut socket, custody, verifier) = connection
        .consume_before(|fd, received, custody| {
            assert_eq!(received, deadline);
            let verifier = custody.verifier().unwrap();
            (stream(fd), custody, verifier)
        })
        .unwrap();
    let mut byte = [0];
    socket.read_exact(&mut byte).unwrap();
    assert_eq!(&byte, b"X");
    verifier.verify_current().unwrap();
    if cut == 1 {
        // Do not move parent custody into a closure subsequently dropped by
        // the parent. Only the actual fork child's copies are retired here.
        let fork = unsafe { libc::fork() };
        assert!(fork >= 0);
        if fork == 0 {
            unsafe { libc::alarm(4) };
            let result = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
                assert!(matches!(
                    verifier.verify_current(),
                    Err(Error::ProcessChanged)
                ));
                drop(custody);
                drop(socket);
            }));
            unsafe { libc::_exit(if result.is_ok() { 0 } else { 101 }) };
        }
        reap(fork as u32);
        verifier.verify_current().unwrap();
    }
    socket.write_all(b"Y").unwrap();
    reap(pid);
    assert!(
        matches!(verifier.verify_current(), Err(Error::PeerRefused)),
        "same original kernel pidfd observes real exit"
    );
    assert!(matches!(verifier.verify_current(), Err(Error::Retired)));
    drop(custody);
}
fn path_scope_latching() {
    let f = Fixture::new();
    let mut listener = f.listener();
    let deadline = ceiling();
    let owner = std::process::id();
    let pid = child(|| {
        let connection =
            Connection::connect_before(&f.policy(), policy(0, 0, Some(owner)), deadline).unwrap();
        connection
            .consume_before(|fd, _, custody| {
                let mut socket = stream(fd);
                socket.write_all(b"X").unwrap();
                let mut out = [0];
                socket.read_exact(&mut out).unwrap();
                drop(custody);
            })
            .unwrap();
    });
    let connection = listener
        .accept_before(policy(0, 0, Some(pid)), deadline)
        .unwrap();
    connection
        .consume_before(|fd, _, custody| {
            let mut socket = stream(fd);
            let mut input = [0];
            socket.read_exact(&mut input).unwrap();
            let v = custody.verifier().unwrap();
            fs::set_permissions(&f.path, fs::Permissions::from_mode(0o666)).unwrap();
            assert!(matches!(v.verify_current(), Err(Error::PathRefused)));
            fs::set_permissions(&f.path, fs::Permissions::from_mode(0o660)).unwrap();
            assert!(matches!(v.verify_current(), Err(Error::Retired)));
            socket.write_all(b"Y").unwrap();
        })
        .unwrap();
    reap(pid);
}
fn peer_configuration_and_budget() {
    for wrong in [
        policy(TEST_CLIENT_UID, TEST_CLIENT_GID, None),
        policy(0, TEST_CLIENT_GID, None),
        policy(0, 0, Some(std::process::id() + 1)),
    ] {
        let f = Fixture::new();
        let listener = f.listener();
        assert!(matches!(
            Connection::connect_before(&f.policy(), wrong, ceiling()),
            Err(Error::PeerRefused)
        ));
        drop(listener);
    }
    let f = Fixture::new();
    let mut listener = f.listener();
    assert!(matches!(
        Connection::connect_before(
            &f.policy(),
            policy(0, 0, None),
            Instant::now() - Duration::from_nanos(1)
        ),
        Err(Error::DeadlineExceeded)
    ));
    assert!(matches!(
        Connection::connect_before(
            &f.policy(),
            policy(0, 0, None),
            Instant::now() + Duration::from_secs(21)
        ),
        Err(Error::InvalidConfiguration)
    ));
    drop(listener);
    fs::remove_file(&f.path).unwrap();
    listener = f.listener();
    let deadline = Instant::now() + Duration::from_millis(15);
    let start = Instant::now();
    assert!(matches!(
        listener.accept_before(policy(0, 0, None), deadline),
        Err(Error::DeadlineExceeded)
    ));
    assert!(start.elapsed() < Duration::from_secs(1));
    assert!(matches!(
        listener.accept_before(policy(0, 0, None), ceiling()),
        Err(Error::Retired)
    ));
}
fn missing_actual_capability() {
    let f = Fixture::new();
    let pid = child(|| {
        // Actual effective capability removal. The listener still has valid
        // root ownership, shape, creation identity and pathname metadata.
        #[repr(C)]
        struct Header {
            version: u32,
            pid: i32,
        }
        #[repr(C)]
        #[derive(Clone, Copy)]
        struct Data {
            effective: u32,
            permitted: u32,
            inheritable: u32,
        }
        let mut header = Header {
            version: 0x20080522,
            pid: 0,
        };
        let mut data = [Data {
            effective: 0,
            permitted: 0,
            inheritable: 0,
        }; 2];
        assert_eq!(
            unsafe { libc::syscall(libc::SYS_capget, &mut header, &mut data) },
            0
        );
        data[0].effective &= !(1 << 12);
        assert_eq!(
            unsafe { libc::syscall(libc::SYS_capset, &header, &data) },
            0
        );
        assert!(matches!(
            Listener::from_inherited(f.socket(libc::SOCK_SEQPACKET, true), &f.policy()),
            Err(Error::PrivilegedProfileRequired)
        ));
    });
    reap(pid);
}
fn consumed_deadline_and_late_refusal() {
    let f = Fixture::new();
    let mut listener = f.listener();
    let original = Instant::now() + Duration::from_millis(150);
    let client = Connection::connect_before(
        &f.policy(),
        policy(0, 0, Some(std::process::id())),
        original,
    )
    .unwrap();
    let server = listener
        .accept_before(policy(0, 0, Some(std::process::id())), original)
        .unwrap();
    let (fd, custody, verifier) = server
        .consume_before(|fd, returned, custody| {
            assert_eq!(returned, original, "unchanged opaque accepted ceiling");
            let verifier = custody.verifier().unwrap();
            (fd, custody, verifier)
        })
        .unwrap();
    std::thread::sleep(Duration::from_millis(160));
    assert!(matches!(
        verifier.verify_current(),
        Err(Error::DeadlineExceeded)
    ));
    assert!(matches!(verifier.verify_current(), Err(Error::Retired)));
    assert!(matches!(
        client.consume_before(|_, _, _| panic!("late callback forbidden")),
        Err(Error::DeadlineExceeded)
    ));
    drop(fd);
    drop(custody);
    drop(verifier);
}
fn live_foreign_relisten_cannot_restore_listener() {
    let f = Fixture::new();
    let fd = f.socket(libc::SOCK_SEQPACKET, true);
    let alias = duplicate(fd.as_raw_fd());
    let mut listener = Listener::from_inherited(fd, &f.policy()).unwrap();
    let (mut ready, mut child_signal) = UnixStream::pair().unwrap();
    let child_pid = child(|| {
        assert_eq!(unsafe { libc::listen(alias.as_raw_fd(), 2) }, 0);
        child_signal.write_all(b"R").unwrap();
        let mut end = [0];
        child_signal.read_exact(&mut end).unwrap();
        let mut listening: libc::c_int = 0;
        let mut size = std::mem::size_of_val(&listening) as libc::socklen_t;
        assert_eq!(
            unsafe {
                libc::getsockopt(
                    alias.as_raw_fd(),
                    libc::SOL_SOCKET,
                    libc::SO_ACCEPTCONN,
                    std::ptr::addr_of_mut!(listening).cast(),
                    &mut size,
                )
            },
            0
        );
        assert_eq!(
            listening, 1,
            "foreign alias remains a listener; no shutdown"
        );
    });
    drop(child_signal);
    let mut start = [0];
    ready.read_exact(&mut start).unwrap();
    let observed = hepta_agent_transport::PeerIdentity::from_stream(&UnixStream::from(duplicate(
        alias.as_raw_fd(),
    )))
    .unwrap();
    assert_eq!(
        observed.pid,
        Some(child_pid),
        "actual foreign listen incarnation"
    );
    let client =
        Connection::connect_before(&f.policy(), policy(0, 0, Some(child_pid)), ceiling()).unwrap();
    assert!(matches!(
        listener.accept_before(policy(0, 0, Some(std::process::id())), ceiling()),
        Err(Error::ListenerCreatorMismatch)
    ));
    // Restore the kernel credentials through our own still-held raw test alias.
    // Restoring facts cannot revive the retired typed listener or shared scope.
    assert_eq!(unsafe { libc::listen(alias.as_raw_fd(), 2) }, 0);
    let restored = hepta_agent_transport::PeerIdentity::from_stream(&UnixStream::from(duplicate(
        alias.as_raw_fd(),
    )))
    .unwrap();
    assert_eq!(restored.pid, Some(std::process::id()));
    assert!(matches!(
        listener.accept_before(policy(0, 0, Some(std::process::id())), ceiling()),
        Err(Error::Retired)
    ));
    ready.write_all(b"E").unwrap();
    reap(child_pid);
    drop(client);
}
fn observed_blocking_alias_cannot_restore_listener() {
    let f = Fixture::new();
    let fd = f.socket(libc::SOCK_SEQPACKET, true);
    let alias = duplicate(fd.as_raw_fd());
    let mut listener = Listener::from_inherited(fd, &f.policy()).unwrap();
    let flags = unsafe { libc::fcntl(alias.as_raw_fd(), libc::F_GETFL) };
    assert!(flags >= 0);
    assert_ne!(flags & libc::O_NONBLOCK, 0);
    assert_eq!(
        unsafe { libc::fcntl(alias.as_raw_fd(), libc::F_SETFL, flags & !libc::O_NONBLOCK) },
        0
    );
    // No incoming client: attempting native accept on the now-blocking
    // listener would hang rather than honor this original bounded ceiling.
    assert!(matches!(
        listener.accept_before(policy(0, 0, None), ceiling()),
        Err(Error::WrongDescriptor)
    ));
    assert_eq!(
        unsafe { libc::fcntl(alias.as_raw_fd(), libc::F_SETFL, flags) },
        0
    );
    assert!(matches!(
        listener.accept_before(policy(0, 0, None), ceiling()),
        Err(Error::Retired)
    ));
    assert!(
        unsafe { libc::fcntl(alias.as_raw_fd(), libc::F_GETFL) } >= 0,
        "only our listener copy retired; raw test alias remains owned"
    );
}
fn root_main() {
    assert_eq!(unsafe { libc::geteuid() }, 0);
    unsafe { libc::alarm(60) };
    for (name, body) in [
        (
            "closed externally configured canonical path",
            invalid_configuration as fn(),
        ),
        (
            "descriptor shape and original listener creator",
            descriptor_and_creator,
        ),
        (
            "nofollow root ancestors and exact socket metadata",
            bad_paths,
        ),
        (
            "actual bound inode and unlink-rebind refusal",
            actual_bound_inode_and_replacement,
        ),
        ("actual root-nobody control and original peer pidfd", || {
            exchange(0)
        }),
        ("actual fork child refusal and parent preserved", || {
            exchange(1)
        }),
        (
            "same custody path drift permanently latched",
            path_scope_latching,
        ),
        (
            "independent peer policy and fixed original ceilings",
            peer_configuration_and_budget,
        ),
        (
            "real missing SIOC privilege has no fallback",
            missing_actual_capability,
        ),
        (
            "consumed exact deadline and ordinary late callback refusal",
            consumed_deadline_and_late_refusal,
        ),
        (
            "actual foreign alias relisten and irreversible creator retirement",
            live_foreign_relisten_cannot_restore_listener,
        ),
        (
            "actual blocking alias flag drift and irreversible retirement",
            observed_blocking_alias_cannot_restore_listener,
        ),
    ] {
        let before = inventory();
        body();
        assert_eq!(inventory(), before, "owned root kernel descriptors retired");
        println!("PASS root-path kernel {name}");
    }
    println!(
        "PASS 12 privileged kernel source groups; no installed broker/executable/unit/principal/native authority"
    );
}
fn main() {
    if std::env::args().any(|a| a == "--privileged-kernel-profile") {
        root_main();
        return;
    }
    let output = Command::new("/usr/bin/sudo")
        .args(["--non-interactive", "--"])
        .arg(std::env::current_exe().unwrap())
        .arg("--privileged-kernel-profile")
        .output()
        .expect("explicit privileged test helper required");
    std::io::stdout().write_all(&output.stdout).unwrap();
    std::io::stderr().write_all(&output.stderr).unwrap();
    assert!(
        output.status.success(),
        "required actual privileged profile must pass; no skip"
    );
}
