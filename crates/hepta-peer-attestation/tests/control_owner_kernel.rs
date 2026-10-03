//! Required real Linux host corpus, single-thread entrypoint. Same-UID explicit
//! test policies and local sockets are not installed service/approval evidence.
#![cfg(target_os = "linux")]
#![deny(unsafe_op_in_unsafe_fn)]
use hepta_agent_transport::{
    AcceptedStreamCustody, HandoffError, HandoffReceiver, HandoffSender, PeerIdentity, PeerPolicy,
};
use hepta_peer_attestation::{
    AttestedHandoffReceiver, AttestedHandoffSender, ControlOwnerError, ControlOwnerPolicy,
    PeerRuntimePolicy, ProcfsPeerAttestor,
};
use std::fs;
use std::io::{Read, Write};
use std::mem::{size_of, zeroed};
use std::os::fd::{AsRawFd, FromRawFd, OwnedFd, RawFd};
use std::os::unix::fs::DirBuilderExt;
use std::os::unix::net::{UnixListener, UnixStream};
use std::os::unix::process::CommandExt;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicU64, Ordering};
use std::thread;
use std::time::{Duration, Instant};
const WAIT: Duration = Duration::from_secs(5);
static NEXT: AtomicU64 = AtomicU64::new(0);
struct Directory(PathBuf);
impl Directory {
    fn new() -> Self {
        let p = std::env::temp_dir().join(format!(
            "g2owner-{}-{}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        fs::DirBuilder::new().mode(0o700).create(&p).unwrap();
        Self(p)
    }
}
impl Drop for Directory {
    fn drop(&mut self) {
        fs::remove_dir_all(&self.0).unwrap();
    }
}
fn wait_fd(fd: RawFd, events: i16) {
    let mut p = libc::pollfd {
        fd,
        events,
        revents: 0,
    };
    assert!(
        unsafe { libc::poll(&mut p, 1, 5000) } > 0,
        "owned fixture endpoint deadline"
    );
}
fn address(path: &Path) -> libc::sockaddr_un {
    let mut a: libc::sockaddr_un = unsafe { zeroed() };
    a.sun_family = libc::AF_UNIX as _;
    let b = path.as_os_str().as_encoded_bytes();
    assert!(b.len() < a.sun_path.len());
    for (i, v) in b.iter().enumerate() {
        a.sun_path[i] = *v as _;
    }
    a
}
fn control(path: &Path, listen: bool) -> OwnedFd {
    let fd = unsafe { libc::socket(libc::AF_UNIX, libc::SOCK_SEQPACKET | libc::SOCK_CLOEXEC, 0) };
    assert!(fd >= 0);
    let owned = unsafe { OwnedFd::from_raw_fd(fd) };
    let a = address(path);
    let result = unsafe {
        if listen {
            libc::bind(
                fd,
                std::ptr::addr_of!(a).cast(),
                size_of::<libc::sockaddr_un>() as _,
            )
        } else {
            libc::connect(
                fd,
                std::ptr::addr_of!(a).cast(),
                size_of::<libc::sockaddr_un>() as _,
            )
        }
    };
    assert_eq!(result, 0);
    if listen {
        assert_eq!(unsafe { libc::listen(fd, 2) }, 0);
    }
    owned
}
fn actual_policy(fd: RawFd) -> ControlOwnerPolicy {
    let borrowed = unsafe { libc::fcntl(fd, libc::F_DUPFD_CLOEXEC, 3) };
    assert!(borrowed >= 0);
    let stream = unsafe { UnixStream::from_raw_fd(borrowed) };
    let p = PeerIdentity::from_stream(&stream).unwrap();
    let s = ProcfsPeerAttestor::default()
        .read_snapshot(p.pid.unwrap())
        .unwrap();
    ControlOwnerPolicy::new(
        PeerPolicy::exact(p),
        PeerRuntimePolicy::exact(&s),
        s.executable_sha256,
    )
    .unwrap()
}
fn input() -> u8 {
    let mut p = libc::pollfd {
        fd: 0,
        events: libc::POLLIN,
        revents: 0,
    };
    assert!(unsafe { libc::poll(&mut p, 1, 15000) } > 0);
    let mut b = [0];
    std::io::stdin().read_exact(&mut b).unwrap();
    b[0]
}
fn helper(mode: &str, cp: &Path, op: &Path) {
    let listener = UnixListener::bind(op).unwrap();
    let fd = control(cp, false);
    println!("READY");
    wait_fd(listener.as_raw_fd(), libc::POLLIN);
    let (accepted, _) = listener.accept().unwrap();
    if mode == "hold" {
        println!("ARMED");
        match input() {
            b'e' => {
                let e = Command::new("/usr/bin/sleep").arg("5").exec();
                panic!("actual exec failed: {e}");
            }
            b'x' => return,
            _ => panic!("unexpected fixture command"),
        };
    } else if mode == "malformed" {
        let mut stream = UnixStream::from(fd);
        let mut challenge = [0; 40];
        stream.read_exact(&mut challenge).unwrap();
        println!("ARMED");
        assert_eq!(input(), b's');
        stream.write_all(b"bad").unwrap();
        println!("SENT");
        assert_eq!(input(), b'x');
    } else {
        let policy = actual_policy(fd.as_raw_fd());
        let mut sender =
            AttestedHandoffSender::from_accepted(fd, accepted, op, policy, WAIT).unwrap();
        println!("ARMED");
        match input() {
            b's' => {
                sender.send().unwrap();
                assert_eq!(sender.send(), Err(ControlOwnerError::ChannelRetired));
                println!("SENT");
            }
            b'c' => {
                sender.cancel().unwrap();
                assert_eq!(sender.send(), Err(ControlOwnerError::Cancelled));
                println!("CANCELLED");
            }
            b'd' => {
                assert_eq!(sender.send(), Err(ControlOwnerError::DeadlineExceeded));
                assert_eq!(sender.send(), Err(ControlOwnerError::ChannelRetired));
                println!("EXPIRED");
            }
            _ => panic!("unexpected fixture command"),
        };
        assert_eq!(input(), b'x');
    }
}
struct Session {
    _directory: Directory,
    path: PathBuf,
    child: Child,
    control: Option<OwnedFd>,
    client: UnixStream,
    finished: bool,
    owner_pid: u32,
}
impl Session {
    fn new(mode: &str) -> Self {
        let d = Directory::new();
        let cp = d.0.join("control.sock");
        let path = d.0.join("original.sock");
        let listener = control(&cp, true);
        let child = Command::new(std::env::current_exe().unwrap())
            .args(["--child", mode])
            .arg(&cp)
            .arg(&path)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::inherit())
            .spawn()
            .unwrap();
        wait_fd(listener.as_raw_fd(), libc::POLLIN);
        let fd = unsafe {
            libc::accept4(
                listener.as_raw_fd(),
                std::ptr::null_mut(),
                std::ptr::null_mut(),
                libc::SOCK_CLOEXEC,
            )
        };
        assert!(fd >= 0);
        let mut s = Self {
            _directory: d,
            path,
            child,
            control: Some(unsafe { OwnedFd::from_raw_fd(fd) }),
            client: UnixStream::pair().unwrap().0,
            finished: false,
            owner_pid: std::process::id(),
        };
        s.line("READY");
        s.client = UnixStream::connect(&s.path).unwrap();
        s.client.set_read_timeout(Some(WAIT)).unwrap();
        s
    }
    fn line(&mut self, expected: &str) {
        let reader = self.child.stdout.as_mut().unwrap();
        let mut line = Vec::new();
        loop {
            wait_fd(reader.as_raw_fd(), libc::POLLIN);
            let mut b = [0];
            assert_eq!(reader.read(&mut b).unwrap(), 1);
            if b[0] == b'\n' {
                break;
            }
            line.push(b[0]);
            assert!(line.len() <= 128);
        }
        assert_eq!(std::str::from_utf8(&line).unwrap(), expected);
    }
    fn command(&mut self, value: u8) {
        self.child
            .stdin
            .as_mut()
            .unwrap()
            .write_all(&[value])
            .unwrap();
    }
    fn receiver(&mut self, budget: Duration) -> AttestedHandoffReceiver {
        let fd = self.control.take().unwrap();
        let policy = actual_policy(fd.as_raw_fd());
        AttestedHandoffReceiver::from_control(fd, policy, &self.path, budget).unwrap()
    }
    fn finish(&mut self) {
        self.command(b'x');
        let stop = Instant::now() + WAIT;
        loop {
            if let Some(status) = self.child.try_wait().unwrap() {
                self.finished = true;
                assert!(status.success());
                break;
            }
            assert!(Instant::now() < stop);
            thread::sleep(Duration::from_millis(5));
        }
    }
    fn eof(&mut self) {
        let mut b = [0];
        assert_eq!(self.client.read(&mut b).unwrap(), 0);
    }
}
impl Drop for Session {
    fn drop(&mut self) {
        if self.owner_pid == std::process::id() && !self.finished {
            let _ = self.child.kill();
            let _ = self.child.wait();
        }
    }
}
fn inventory() -> Vec<u32> {
    let mut f: Vec<_> = fs::read_dir("/proc/self/fd")
        .unwrap()
        .map(|v| {
            v.unwrap()
                .file_name()
                .to_str()
                .unwrap()
                .parse::<u32>()
                .unwrap()
        })
        .collect();
    f.sort_unstable();
    f
}
fn closed(fd: RawFd) {
    assert_eq!(unsafe { libc::fcntl(fd, libc::F_GETFD) }, -1);
    assert_eq!(
        std::io::Error::last_os_error().raw_os_error(),
        Some(libc::EBADF)
    );
}
fn positive() {
    let before = inventory();
    {
        let mut s = Session::new("send");
        let mut r = s.receiver(WAIT);
        s.line("ARMED");
        s.command(b's');
        let received = r.receive().unwrap();
        let deadline = received.deadline().unwrap();
        assert!(deadline <= Instant::now() + WAIT);
        received
            .consume_before(|mut original, d| {
                assert_eq!(d, deadline);
                assert_eq!(
                    PeerIdentity::from_stream(&original).unwrap().pid,
                    Some(std::process::id())
                );
                original.write_all(b"original").unwrap();
            })
            .unwrap();
        let mut b = [0; 8];
        s.client.read_exact(&mut b).unwrap();
        assert_eq!(&b, b"original");
        s.line("SENT");
        assert_eq!(r.receive().err(), Some(ControlOwnerError::ChannelRetired));
        s.finish();
    }
    assert_eq!(inventory(), before);
}
fn wrong_policy() {
    for case in ["exe", "uid", "gid", "pid", "cgroup", "unit"] {
        let before = inventory();
        {
            let mut s = Session::new("hold");
            let fd = s.control.take().unwrap();
            let raw = fd.as_raw_fd();
            let dup = unsafe { libc::fcntl(raw, libc::F_DUPFD_CLOEXEC, 3) };
            let stream = unsafe { UnixStream::from_raw_fd(dup) };
            let p = PeerIdentity::from_stream(&stream).unwrap();
            drop(stream);
            let actual = ProcfsPeerAttestor::default()
                .read_snapshot(s.child.id())
                .unwrap();
            let mut kernel = PeerPolicy::exact(p);
            let mut runtime = PeerRuntimePolicy::exact(&actual);
            let mut pin = actual.executable_sha256;
            match case {
                "exe" => pin = "0".repeat(64),
                "uid" => {
                    kernel.expected_uid ^= 1;
                    runtime.expected_uid = kernel.expected_uid;
                }
                "gid" => {
                    runtime.expected_gid ^= 1;
                    kernel.expected_gid = Some(runtime.expected_gid);
                }
                "pid" => kernel.expected_pid = Some(std::process::id()),
                "cgroup" => runtime.expected_cgroup_v2_path = "/wrong".into(),
                "unit" => runtime.expected_systemd_unit = Some("wrong.service".into()),
                _ => unreachable!(),
            };
            let policy = ControlOwnerPolicy::new(kernel, runtime, pin).unwrap();
            assert_eq!(
                AttestedHandoffReceiver::from_control(fd, policy, &s.path, WAIT).err(),
                Some(ControlOwnerError::PeerRefused)
            );
            closed(raw);
            s.line("ARMED");
            s.finish();
            s.eof();
        }
        assert_eq!(inventory(), before);
    }
}
fn death_or_exec() {
    for mode in ["death", "exec"] {
        let before = inventory();
        {
            let mut s = Session::new("hold");
            let raw = s.control.as_ref().unwrap().as_raw_fd();
            let mut r = s.receiver(WAIT);
            s.line("ARMED");
            if mode == "death" {
                s.finish();
            } else {
                s.command(b'e');
                let initial = std::env::current_exe().unwrap();
                let stop = Instant::now() + WAIT;
                while fs::read_link(format!("/proc/{}/exe", s.child.id())).unwrap() == initial {
                    assert!(Instant::now() < stop);
                    thread::sleep(Duration::from_millis(5));
                }
            }
            assert_eq!(
                r.ensure_current().err(),
                Some(ControlOwnerError::PeerRefused)
            );
            closed(raw);
            assert_eq!(r.receive().err(), Some(ControlOwnerError::ChannelRetired));
        }
        assert_eq!(inventory(), before);
    }
}
fn receiver_cancel() {
    let before = inventory();
    {
        let mut s = Session::new("hold");
        let raw = s.control.as_ref().unwrap().as_raw_fd();
        let mut r = s.receiver(WAIT);
        s.line("ARMED");
        r.cancel().unwrap();
        closed(raw);
        assert_eq!(r.receive().err(), Some(ControlOwnerError::Cancelled));
        s.finish();
    }
    assert_eq!(inventory(), before);
}
fn sender_cancel() {
    let before = inventory();
    {
        let mut s = Session::new("send");
        let mut r = s.receiver(WAIT);
        s.line("ARMED");
        s.command(b'c');
        s.line("CANCELLED");
        assert_eq!(r.receive().err(), Some(ControlOwnerError::HandoffRefused));
        s.eof();
        s.finish();
    }
    assert_eq!(inventory(), before);
}
fn receiver_deadline() {
    let before = inventory();
    {
        let mut s = Session::new("hold");
        let raw = s.control.as_ref().unwrap().as_raw_fd();
        let mut r = s.receiver(WAIT);
        s.line("ARMED");
        let original = r.ensure_current().unwrap();
        thread::sleep(
            original.saturating_duration_since(Instant::now()) + Duration::from_millis(5),
        );
        assert_eq!(r.receive().err(), Some(ControlOwnerError::DeadlineExceeded));
        closed(raw);
        assert_eq!(r.receive().err(), Some(ControlOwnerError::ChannelRetired));
        s.finish();
    }
    assert_eq!(inventory(), before);
}

fn sender_delay_expires_original() {
    let before = inventory();
    {
        let mut s = Session::new("send");
        let mut r = s.receiver(Duration::from_secs(20));
        s.line("ARMED");
        // The original sender ceiling started before actual procfs/handshake.
        // Waiting after constructor completion cannot create a fresh budget.
        thread::sleep(WAIT + Duration::from_millis(20));
        s.command(b'd');
        s.line("EXPIRED");
        assert_eq!(r.receive().err(), Some(ControlOwnerError::HandoffRefused));
        s.eof();
        s.finish();
    }
    assert_eq!(inventory(), before);
}

fn expired_constructor_closes_control() {
    let before = inventory();
    {
        let mut s = Session::new("hold");
        let fd = s.control.take().unwrap();
        let raw = fd.as_raw_fd();
        let policy = actual_policy(raw);
        assert_eq!(
            AttestedHandoffReceiver::from_control(fd, policy, &s.path, Duration::from_nanos(1))
                .err(),
            Some(ControlOwnerError::DeadlineExceeded)
        );
        closed(raw);
        s.line("ARMED");
        s.finish();
        s.eof();
    }
    assert_eq!(inventory(), before);
}
fn malformed() {
    let before = inventory();
    {
        let mut s = Session::new("malformed");
        let raw = s.control.as_ref().unwrap().as_raw_fd();
        let mut r = s.receiver(WAIT);
        s.line("ARMED");
        s.command(b's');
        s.line("SENT");
        assert_eq!(r.receive().err(), Some(ControlOwnerError::HandoffRefused));
        closed(raw);
        assert_eq!(r.receive().err(), Some(ControlOwnerError::ChannelRetired));
        s.finish();
    }
    assert_eq!(inventory(), before);
}
fn fork_refusal() {
    let before = inventory();
    {
        let mut s = Session::new("hold");
        let raw = s.control.as_ref().unwrap().as_raw_fd();
        let mut r = s.receiver(WAIT);
        s.line("ARMED");
        let pid = unsafe { libc::fork() };
        assert!(pid >= 0);
        if pid == 0 {
            assert_eq!(r.cancel(), Err(ControlOwnerError::ProcessChanged));
            assert_eq!(r.receive().err(), Some(ControlOwnerError::ProcessChanged));
            assert_eq!(
                r.ensure_current().err(),
                Some(ControlOwnerError::ProcessChanged)
            );
            drop(r);
            closed(raw);
            unsafe { libc::_exit(0) }
        }
        let mut status = 0;
        let stop = Instant::now() + WAIT;
        loop {
            let reaped = unsafe { libc::waitpid(pid, &mut status, libc::WNOHANG) };
            if reaped == pid {
                break;
            }
            assert_eq!(reaped, 0);
            if Instant::now() >= stop {
                unsafe {
                    libc::kill(pid, libc::SIGKILL);
                    libc::waitpid(pid, &mut status, 0)
                };
                panic!("owned fork child deadline");
            }
            thread::sleep(Duration::from_millis(5));
        }
        assert_eq!(status, 0);
        assert!(unsafe { libc::fcntl(raw, libc::F_GETFD) } >= 0);
        assert!(r.ensure_current().is_ok());
        r.cancel().unwrap();
        s.finish();
    }
    assert_eq!(inventory(), before);
}
fn controls() -> (OwnedFd, OwnedFd) {
    let mut f = [-1; 2];
    assert_eq!(
        unsafe {
            libc::socketpair(
                libc::AF_UNIX,
                libc::SOCK_SEQPACKET | libc::SOCK_CLOEXEC,
                0,
                f.as_mut_ptr(),
            )
        },
        0
    );
    unsafe { (OwnedFd::from_raw_fd(f[0]), OwnedFd::from_raw_fd(f[1])) }
}
fn captured_before() {
    let before = inventory();
    {
        let d = Directory::new();
        let path = d.0.join("original.sock");
        let listener = UnixListener::bind(&path).unwrap();
        let _client = UnixStream::connect(&path).unwrap();
        let (accepted, _) = listener.accept().unwrap();
        let raw = accepted.as_raw_fd();
        let p = PeerPolicy::exact(PeerIdentity::from_stream(&accepted).unwrap());
        let (a, b) = controls();
        let mut r = HandoffReceiver::from_control(b, p, &path).unwrap();
        let mut s = HandoffSender::from_control(a, p, WAIT).unwrap();
        let entry = Instant::now() + Duration::from_millis(500);
        thread::sleep(Duration::from_millis(100));
        let c = AcceptedStreamCustody::capture_before(accepted, &path, entry).unwrap();
        thread::sleep(Duration::from_millis(20));
        s.send(c).unwrap();
        closed(raw);
        let original = r.receive(WAIT).unwrap();
        assert!(
            original.deadline().unwrap() <= entry,
            "original absolute Instant was renewed"
        );
        assert!(
            original
                .deadline()
                .unwrap()
                .saturating_duration_since(Instant::now())
                < Duration::from_millis(400)
        );
    }
    assert_eq!(inventory(), before);
}
fn expired_or_excess_capture() {
    for duration in [None, Some(Duration::from_secs(21))] {
        let before = inventory();
        {
            let d = Directory::new();
            let p = d.0.join("original.sock");
            let listener = UnixListener::bind(&p).unwrap();
            let mut client = UnixStream::connect(&p).unwrap();
            client.set_read_timeout(Some(WAIT)).unwrap();
            let (accepted, _) = listener.accept().unwrap();
            let deadline = duration
                .map(|v| Instant::now() + v)
                .unwrap_or(Instant::now() - Duration::from_millis(1));
            let expected = if duration.is_none() {
                HandoffError::DeadlineExceeded
            } else {
                HandoffError::InvalidConfiguration
            };
            assert_eq!(
                AcceptedStreamCustody::capture_before(accepted, &p, deadline).err(),
                Some(expected)
            );
            let mut b = [0];
            assert_eq!(client.read(&mut b).unwrap(), 0);
        }
        assert_eq!(inventory(), before);
    }
}
fn invalid_configuration() {
    let before = inventory();
    {
        let d = Directory::new();
        let p = d.0.join("original.sock");
        let listener = UnixListener::bind(&p).unwrap();
        let mut client = UnixStream::connect(&p).unwrap();
        client.set_read_timeout(Some(WAIT)).unwrap();
        let (accepted, _) = listener.accept().unwrap();
        let (a, _b) = controls();
        let raw = a.as_raw_fd();
        let policy = actual_policy(raw);
        assert_eq!(
            AttestedHandoffSender::from_accepted(a, accepted, &p, policy, Duration::MAX).err(),
            Some(ControlOwnerError::InvalidConfiguration)
        );
        closed(raw);
        let mut bytes = [0];
        assert_eq!(client.read(&mut bytes).unwrap(), 0);
        assert!(Instant::now().checked_add(Duration::MAX).is_none());
    }
    assert_eq!(inventory(), before);
}
fn main() {
    let a: Vec<_> = std::env::args().collect();
    if a.get(1).map(String::as_str) == Some("--child") {
        helper(&a[2], Path::new(&a[3]), Path::new(&a[4]));
        return;
    }
    let cases: [(&str, fn()); 13] = [
        ("real two-process live/exact original", positive),
        ("approved pin/kernel/cgroup/unit mismatch", wrong_policy),
        ("original pidfd death and actual exec drift", death_or_exec),
        ("exclusive receiver cancel", receiver_cancel),
        ("single-use sender cancel/EOF", sender_cancel),
        ("fixed control wait deadline", receiver_deadline),
        (
            "ordinary delay never renews sender ingress",
            sender_delay_expires_original,
        ),
        (
            "expired constructor closes original control",
            expired_constructor_closes_control,
        ),
        ("malformed actual packet fail-stop", malformed),
        ("actual fork owns no copied authority", fork_refusal),
        (
            "absolute capture remains conservative after delay",
            captured_before,
        ),
        (
            "past and over20 absolute ceilings",
            expired_or_excess_capture,
        ),
        (
            "overflow duration consumes original FDs",
            invalid_configuration,
        ),
    ];
    for (name, test) in cases {
        test();
        println!("PASS {name}");
    }
    println!("13 actual Linux control-owner case groups passed");
}
