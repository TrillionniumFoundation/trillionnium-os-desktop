//! Explicit privileged source/actual-PIN test fixture only. The launcher chooses
//! unit, UID and owned ELF pin BEFORE peer launch. No production self-approval.
#![allow(dead_code)]
#![deny(unsafe_op_in_unsafe_fn)]
use hepta_agent_transport::{
    AcceptedStreamCustody, ClientConnection, PeerIdentity, PeerPolicy, RemoteTerminalState,
    RootControlPathPolicy, RootOwnedControlListener, RootPathControlConnection,
};
use hepta_browser_codec::{BrowserOperation, BrowserRequest, decode_response, encode_request};
use hepta_peer_attestation::{
    ApprovedPolicyDocument, ApprovedPolicyError, AttestationError, ControlOwnerError,
    ProcfsPeerAttestor, RootPathAttestedHandoffReceiver,
};
use std::ffi::CString;
use std::fs;
use std::io::{Read, Write};
use std::mem::{size_of, zeroed};
use std::os::fd::{AsRawFd, FromRawFd, OwnedFd, RawFd};
use std::os::unix::fs::PermissionsExt;
use std::os::unix::net::{UnixListener, UnixStream};
use std::os::unix::process::CommandExt;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::OnceLock;
use std::sync::atomic::{AtomicU32, Ordering};
use std::thread;
use std::time::{Duration, Instant};
pub const WAIT: Duration = Duration::from_secs(20);
const NOBODY: u32 = 65534;
static NEXT: AtomicU32 = AtomicU32::new(0);
static UNIT: OnceLock<String> = OnceLock::new();
fn poll(fd: RawFd, stop: Instant) {
    let millis = stop
        .saturating_duration_since(Instant::now())
        .as_millis()
        .min(20000) as i32;
    assert!(millis > 0);
    let mut p = libc::pollfd {
        fd,
        events: libc::POLLIN,
        revents: 0,
    };
    assert!(
        unsafe { libc::poll(&mut p, 1, millis) } > 0,
        "owned fixture deadline"
    );
}
fn input() -> u8 {
    poll(0, Instant::now() + WAIT);
    let mut b = [0];
    std::io::stdin().read_exact(&mut b).unwrap();
    b[0]
}
fn kernel(uid: u32, gid: u32, pid: Option<u32>) -> PeerPolicy {
    PeerPolicy {
        expected_uid: uid,
        expected_gid: Some(gid),
        expected_pid: pid,
    }
}
fn request() -> BrowserRequest {
    BrowserRequest {
        request_id: "rooted-request".into(),
        session_id: None,
        session_generation: None,
        deadline_unix_ms: None,
        operation: BrowserOperation::Health,
    }
}
fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|value| format!("{value:02x}")).collect()
}
fn chown(path: &Path, uid: u32, gid: u32) {
    let p = CString::new(path.as_os_str().as_encoded_bytes()).unwrap();
    assert_eq!(unsafe { libc::chown(p.as_ptr(), uid, gid) }, 0);
}
pub fn inventory() -> Vec<(u32, PathBuf)> {
    let names: Vec<_> = fs::read_dir("/proc/self/fd")
        .unwrap()
        .map(|e| e.unwrap().file_name())
        .collect();
    let mut result: Vec<_> = names
        .into_iter()
        .filter_map(|n| {
            let fd = n.to_str().unwrap().parse().unwrap();
            fs::read_link(format!("/proc/self/fd/{fd}"))
                .ok()
                .map(|p| (fd, p))
        })
        .collect();
    result.sort();
    result
}
fn control_cookies() -> Vec<u64> {
    let mut cookies = Vec::new();
    for (fd, _) in inventory() {
        let mut cookie = 0_u64;
        let mut length = size_of::<u64>() as libc::socklen_t;
        if unsafe {
            libc::getsockopt(
                fd as i32,
                libc::SOL_SOCKET,
                libc::SO_COOKIE,
                std::ptr::addr_of_mut!(cookie).cast(),
                &mut length,
            )
        } == 0
        {
            cookies.push(cookie);
        }
    }
    cookies.sort();
    cookies
}
pub struct Fixture {
    pub root: PathBuf,
    cp: PathBuf,
    op: PathBuf,
    binary: PathBuf,
    pub config: PathBuf,
    owner_pid: u32,
}
impl Fixture {
    pub fn new() -> Self {
        let root = PathBuf::from(format!(
            "/var/lib/hepta-root-bridge-{}-{}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir(&root).unwrap();
        fs::set_permissions(&root, fs::Permissions::from_mode(0o750)).unwrap();
        chown(&root, 0, NOBODY);
        // Literal unit/cgroup selected by the fixture launcher BEFORE this
        // process and peers launch. No observed PID/snapshot generates policy.
        let unit = UNIT.get().unwrap().clone();
        let binary = root.join("fixture");
        phase_diagnostics::mark(
            phase_diagnostics::Phase::ReadBinary,
            phase_diagnostics::Edge::Begin,
        );
        let bytes = fs::read(std::env::current_exe().unwrap()).unwrap();
        phase_diagnostics::mark(
            phase_diagnostics::Phase::ReadBinary,
            phase_diagnostics::Edge::End,
        );
        phase_diagnostics::mark(
            phase_diagnostics::Phase::WriteBinary,
            phase_diagnostics::Edge::Begin,
        );
        fs::write(&binary, &bytes).unwrap();
        fs::set_permissions(&binary, fs::Permissions::from_mode(0o555)).unwrap();
        phase_diagnostics::mark(
            phase_diagnostics::Phase::WriteBinary,
            phase_diagnostics::Edge::End,
        );
        phase_diagnostics::mark(
            phase_diagnostics::Phase::VerifyCopy,
            phase_diagnostics::Edge::Begin,
        );
        assert_eq!(fs::read(&binary).unwrap(), bytes);
        phase_diagnostics::mark(
            phase_diagnostics::Phase::VerifyCopy,
            phase_diagnostics::Edge::End,
        );
        // Hash the known launcher-owned copied file before either peer exists.
        phase_diagnostics::mark(
            phase_diagnostics::Phase::HashBinary,
            phase_diagnostics::Edge::Begin,
        );
        let hash = Command::new("/usr/bin/sha256sum")
            .arg(&binary)
            .output()
            .unwrap();
        assert!(hash.status.success());
        let pin = String::from_utf8(hash.stdout).unwrap()[..64].to_owned();
        assert!(
            pin.bytes()
                .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
        );
        phase_diagnostics::mark(
            phase_diagnostics::Phase::HashBinary,
            phase_diagnostics::Edge::End,
        );
        let config = root.join("approved-policy");
        let text = format!(
            "schema=trillionnium.approved-mechanisms.v1\ncontrol.uid=0\ncontrol.gid=0\ncontrol.unit={unit}\ncontrol.cgroup=/system.slice/{unit}\ncontrol.elf_sha256={pin}\ncontrol.principal_id=source-control\nagent.uid=0\nagent.gid=0\nagent.unit={unit}\nagent.cgroup=/system.slice/{unit}\nagent.elf_sha256={pin}\nagent.principal_id=source-agent\n"
        );
        fs::write(&config, text).unwrap();
        fs::set_permissions(&config, fs::Permissions::from_mode(0o440)).unwrap();
        chown(&config, 0, NOBODY);
        Self {
            cp: root.join("control.sock"),
            op: root.join("agent.sock"),
            binary,
            config,
            root,
            owner_pid: std::process::id(),
        }
    }
    fn path_policy(&self) -> RootControlPathPolicy {
        RootControlPathPolicy::new(&self.cp, NOBODY, 0o750, NOBODY, 0o660).unwrap()
    }
    pub fn listener(&self) -> RootOwnedControlListener {
        let fd =
            unsafe { libc::socket(libc::AF_UNIX, libc::SOCK_SEQPACKET | libc::SOCK_CLOEXEC, 0) };
        assert!(fd >= 0);
        let owned = unsafe { OwnedFd::from_raw_fd(fd) };
        let mut a: libc::sockaddr_un = unsafe { zeroed() };
        a.sun_family = libc::AF_UNIX as _;
        let bytes = self.cp.as_os_str().as_encoded_bytes();
        for (to, from) in a.sun_path.iter_mut().zip(bytes) {
            *to = *from as _;
        }
        let len = (std::mem::offset_of!(libc::sockaddr_un, sun_path) + bytes.len() + 1)
            as libc::socklen_t;
        assert_eq!(
            unsafe { libc::bind(fd, std::ptr::addr_of!(a).cast(), len) },
            0
        );
        assert_eq!(unsafe { libc::listen(fd, 2) }, 0);
        chown(&self.cp, 0, NOBODY);
        fs::set_permissions(&self.cp, fs::Permissions::from_mode(0o660)).unwrap();
        RootOwnedControlListener::from_inherited(owned, &self.path_policy()).unwrap()
    }
    pub fn document(&self, deadline: Instant) -> ApprovedPolicyDocument {
        ApprovedPolicyDocument::open_root_owned_before(&self.config, deadline).unwrap()
    }
    pub fn agent_path(&self) -> &Path {
        &self.op
    }
    pub fn rewrite(&self, key: &str, value: &str) {
        let text = fs::read_to_string(&self.config).unwrap();
        let rewritten: String = text
            .lines()
            .map(|line| {
                if line.starts_with(&format!("{key}=")) {
                    format!("{key}={value}\n")
                } else {
                    format!("{line}\n")
                }
            })
            .collect();
        fs::write(&self.config, rewritten).unwrap();
    }
}
impl Drop for Fixture {
    fn drop(&mut self) {
        if self.owner_pid == std::process::id() {
            fs::remove_dir_all(&self.root).unwrap();
        }
    }
}
pub struct ChildOwner {
    pub child: Child,
    owner_pid: u32,
    done: bool,
}
impl ChildOwner {
    pub fn spawn(f: &Fixture, mode: &str, op: &Path, nobody: bool) -> Self {
        let mut command = Command::new(&f.binary);
        command
            .args(["--child", mode])
            .arg(&f.cp)
            .arg(op)
            .arg(if mode == "cross" {
                f.root.join("sender-approved-policy")
            } else {
                f.config.clone()
            });
        if nobody {
            command.uid(NOBODY).gid(NOBODY);
        }
        Self {
            child: command
                .stdin(Stdio::piped())
                .stdout(Stdio::piped())
                .stderr(Stdio::inherit())
                .spawn()
                .unwrap(),
            owner_pid: std::process::id(),
            done: false,
        }
    }
    pub fn line(&mut self) -> String {
        let mut out = Vec::new();
        let stop = Instant::now() + WAIT;
        let reader = self.child.stdout.as_mut().unwrap();
        loop {
            poll(reader.as_raw_fd(), stop);
            let mut b = [0];
            assert_eq!(reader.read(&mut b).unwrap(), 1);
            if b[0] == b'\n' {
                break;
            }
            out.push(b[0]);
            assert!(out.len() < 65536);
        }
        String::from_utf8(out).unwrap()
    }
    pub fn expect(&mut self, s: &str) {
        assert_eq!(self.line(), s);
    }
    pub fn command(&mut self, b: u8) {
        self.child.stdin.as_mut().unwrap().write_all(&[b]).unwrap();
    }
    pub fn finish(&mut self) {
        self.command(b'x');
        let stop = Instant::now() + WAIT;
        loop {
            if let Some(status) = self.child.try_wait().unwrap() {
                self.done = true;
                assert!(status.success());
                return;
            }
            assert!(Instant::now() < stop);
            thread::sleep(Duration::from_millis(2));
        }
    }
}
impl Drop for ChildOwner {
    fn drop(&mut self) {
        if self.owner_pid == std::process::id() && !self.done {
            let _ = self.child.kill();
            let _ = self.child.wait();
        }
    }
}
fn custodian(cp: &Path, op: &Path, config: &Path, mode: &str) {
    let cross = mode == "cross";
    let original = UnixListener::bind(op).unwrap();
    let parent = unsafe { libc::getppid() } as u32;
    let path = RootControlPathPolicy::new(cp, NOBODY, 0o750, NOBODY, 0o660).unwrap();
    let deadline = Instant::now() + WAIT;
    let connection =
        RootPathControlConnection::connect_before(&path, kernel(0, 0, Some(parent)), deadline)
            .unwrap();
    assert_eq!(connection.deadline().unwrap(), deadline);
    println!("PATH_CURRENT");
    poll(original.as_raw_fd(), Instant::now() + WAIT);
    let (accepted, _) = original.accept().unwrap();
    // First local custody at original accept, before live peer setup. The
    // bridge cannot rewrap or allocate another accepted budget.
    let accepted_deadline = Instant::now()
        + if mode == "early" || mode == "expired" {
            Duration::from_secs(3)
        } else {
            WAIT
        };
    let accepted = AcceptedStreamCustody::capture_before(accepted, op, accepted_deadline).unwrap();
    if cross {
        assert!(
            matches!(
                ProcfsPeerAttestor::default().read_snapshot(parent),
                Err(AttestationError::ReadProc { path, source })
                    if path.file_name().is_some_and(|name| name == "exe")
                        && source.raw_os_error() == Some(libc::EACCES)
            ),
            "actual cross-UID executable EACCES, no unrelated parse failure or static fallback"
        );
    }
    let before = control_cookies();
    let document = ApprovedPolicyDocument::open_root_owned_before(config, deadline).unwrap();
    let setup = document
        .select_control()
        .unwrap()
        .bind_sender(connection, accepted);
    if cross {
        assert_eq!(setup.err(), Some(ApprovedPolicyError::PeerRefused));
        println!("LIVE_PEER_REFUSED");
        assert_eq!(input(), b'x');
        return;
    }
    let mut sender = if let Ok(sender) = setup {
        sender
    } else {
        println!("SETUP_REFUSED");
        assert_eq!(input(), b'x');
        return;
    };
    assert_eq!(
        control_cookies(),
        before,
        "same original control socket cookies, no replacement socket"
    );
    assert_eq!(sender.ensure_control_current().unwrap(), deadline);
    println!("ARMED");
    if mode == "bootstrap-refusal" {
        // Additive configured-bootstrap refusal stimulus. No original native
        // or retained-handshake case changes or acquires a replacement budget.
        assert_eq!(input(), b'x');
        return;
    }
    assert_eq!(input(), b's');
    if mode == "expired" {
        thread::sleep(
            accepted_deadline.saturating_duration_since(Instant::now()) + Duration::from_millis(10),
        );
        assert_eq!(
            sender.send_retained().err(),
            Some(ControlOwnerError::DeadlineExceeded)
        );
        assert!(sender.send_retained().is_err());
        println!("EXPIRED_NO_PACKET");
        assert_eq!(input(), b'x');
        return;
    }
    let mut pending = sender.send_retained().unwrap();
    assert!(pending.ensure_current().unwrap() <= deadline.min(accepted_deadline));
    assert!(sender.send_retained().is_err());
    drop(sender);
    println!("SENT");
    loop {
        let mut fd = libc::pollfd {
            fd: 0,
            events: libc::POLLIN,
            revents: 0,
        };
        assert!(unsafe { libc::poll(&mut fd, 1, 0) } >= 0);
        if fd.revents != 0 {
            let command = input();
            if command == b'x' {
                return;
            }
            assert_eq!(command, b'c', "owned command");
            pending.request_cancel().unwrap();
            println!("CANCELLED");
        }
        let result = pending.poll_retirement();
        if result.is_err() {
            println!("REPORT_REFUSED");
            assert_eq!(input(), b'x');
            return;
        }
        if let Some(report) = result.unwrap() {
            assert!(matches!(
                report.state(),
                RemoteTerminalState::Completed | RemoteTerminalState::Indeterminate
            ));
            assert!(pending.poll_retirement().is_err());
            println!(
                "REPORT {:?} {} {}",
                report.state(),
                hex(&report.request_sha256()),
                hex(&report.record_sha256())
            );
            assert_eq!(input(), b'x');
            return;
        }
        thread::sleep(Duration::from_millis(2));
    }
}
// Fixed diagnostic tokens only: no error message, values, or payload output.
const AGENT_RECEIVE_ERRORS: [(&str, &str); 29] = [
    ("RXPLAT___", "unsupported-platform"),
    ("RXCRED___", "invalid-peer-credentials"),
    ("RXUNAUTH_", "unauthorized-peer"),
    ("RXMAGIC__", "invalid-magic"),
    ("RXVERS___", "unsupported-version"),
    ("RXKIND___", "unknown-frame-kind"),
    ("RXFLAGS__", "reserved-flags"),
    ("RXNINVAL_", "invalid-session-nonce"),
    ("RXSIZE___", "frame-too-large"),
    ("RXDIGEST_", "payload-digest-mismatch"),
    ("RXDEADLN_", "deadline-or-timeout"),
    ("RXEOF____", "unexpected-eof"),
    ("RXCHALL__", "invalid-challenge"),
    ("RXEXPECT_", "unexpected-frame-kind"),
    ("RXNONCE__", "session-nonce-mismatch"),
    ("RXSEQ____", "sequence-mismatch"),
    ("RXSEQEND_", "sequence-exhausted"),
    ("RXPANIC__", "self-check-thread-panicked"),
    ("RXRESET__", "io-connection-reset"),
    ("RXABORT__", "io-connection-aborted"),
    ("RXBROKEN_", "io-broken-pipe"),
    ("RXNOTCON_", "io-not-connected"),
    ("RXIOEOF__", "io-unexpected-eof"),
    ("RXIOTIME_", "io-timed-out"),
    ("RXIOBLCK_", "io-would-block"),
    ("RXINTR___", "io-interrupted"),
    ("RXINVAL__", "io-invalid-input"),
    ("RXDENIED_", "io-permission-denied"),
    ("RXIOOTHR_", "io-other"),
];
fn agent_receive_error_token(error: &hepta_agent_transport::TransportError) -> &'static str {
    use hepta_agent_transport::TransportError;
    let index = match error {
        TransportError::UnsupportedPlatform => 0,
        TransportError::InvalidPeerCredentials => 1,
        TransportError::UnauthorizedPeer => 2,
        TransportError::InvalidMagic => 3,
        TransportError::UnsupportedVersion(_) => 4,
        TransportError::UnknownFrameKind(_) => 5,
        TransportError::ReservedFlags(_) => 6,
        TransportError::InvalidSessionNonce => 7,
        TransportError::FrameTooLarge { .. } => 8,
        TransportError::PayloadDigestMismatch => 9,
        TransportError::DeadlineExceeded => 10,
        TransportError::UnexpectedEof => 11,
        TransportError::InvalidChallenge => 12,
        TransportError::UnexpectedFrameKind => 13,
        TransportError::SessionNonceMismatch => 14,
        TransportError::SequenceMismatch { .. } => 15,
        TransportError::SequenceExhausted => 16,
        TransportError::SelfCheckThreadPanicked => 17,
        TransportError::Io(error) => match error.kind() {
            std::io::ErrorKind::ConnectionReset => 18,
            std::io::ErrorKind::ConnectionAborted => 19,
            std::io::ErrorKind::BrokenPipe => 20,
            std::io::ErrorKind::NotConnected => 21,
            std::io::ErrorKind::UnexpectedEof => 22,
            std::io::ErrorKind::TimedOut => 23,
            std::io::ErrorKind::WouldBlock => 24,
            std::io::ErrorKind::Interrupted => 25,
            std::io::ErrorKind::InvalidInput => 26,
            std::io::ErrorKind::PermissionDenied => 27,
            _ => 28,
        },
    };
    AGENT_RECEIVE_ERRORS[index].0
}
pub fn agent_receive_error_label(token: &[u8]) -> Option<&'static str> {
    AGENT_RECEIVE_ERRORS
        .iter()
        .find(|(code, _)| code.as_bytes() == token)
        .map(|(_, label)| *label)
}
fn agent(op: &Path) {
    let mut stream = UnixStream::connect(op).unwrap();
    println!("CONNECTED");
    let command = input();
    if command == b'x' {
        return;
    }
    if command == b'e' {
        stream.set_read_timeout(Some(WAIT)).unwrap();
        let mut byte = [0];
        assert_eq!(stream.read(&mut byte).unwrap(), 0);
        println!("ORIGINAL_EOF_WITHOUT_HANDSHAKE");
        assert_eq!(input(), b'x');
        return;
    }
    assert_eq!(command, b'h', "owned Agent command");
    let peer = PeerIdentity::from_stream(&stream).unwrap();
    let mut client = ClientConnection::connect(stream, PeerPolicy::exact(peer), WAIT).unwrap();
    let mut size = [0; 4];
    std::io::stdin().read_exact(&mut size).unwrap();
    let size = u32::from_be_bytes(size) as usize;
    assert!(size > 0 && size <= 65536);
    let mut payload = vec![0; size];
    std::io::stdin().read_exact(&mut payload).unwrap();
    let sequence = client.send_request(payload, WAIT).unwrap();
    println!("REQUEST");
    let received = client.receive_response(sequence, WAIT);
    if let Ok(bytes) = received {
        decode_response(&bytes).unwrap();
        println!("RESPONSE {}", std::str::from_utf8(&bytes).unwrap());
    } else if let Err(error) = received {
        let token = agent_receive_error_token(&error);
        // Preserve the original error drop before the failure print.
        drop(error);
        println!("RESPONSE_REFUSED {token}");
    }
    assert_eq!(input(), b'x');
}
pub struct Trio {
    pub fixture: Fixture,
    pub custodian: ChildOwner,
    pub agent: ChildOwner,
    receiver: RootPathAttestedHandoffReceiver,
    pub deadline: Instant,
    pub document: ApprovedPolicyDocument,
}
impl Trio {
    pub fn new(wait: Duration) -> Self {
        Self::new_before(Instant::now() + wait)
    }
    pub fn new_before(ceiling: Instant) -> Self {
        Self::setup(ceiling, "custodian", ceiling)
    }
    pub fn new_mode(wait: Duration, mode: &str, policy_wait: Duration) -> Self {
        let now = Instant::now();
        Self::setup(now + wait, mode, now + policy_wait)
    }
    fn setup(ceiling: Instant, mode: &str, policy_ceiling: Instant) -> Self {
        phase_diagnostics::mark(
            phase_diagnostics::Phase::FixtureSetup,
            phase_diagnostics::Edge::Begin,
        );
        let fixture = Fixture::new();
        let mut listener = fixture.listener();
        let mut custodian = ChildOwner::spawn(&fixture, mode, &fixture.op, false);
        custodian.expect("PATH_CURRENT");
        let mut agent = ChildOwner::spawn(&fixture, "agent", &fixture.op, false);
        agent.expect("CONNECTED");
        let deadline = ceiling;
        let connection = listener
            .accept_before(kernel(0, 0, Some(custodian.child.id())), deadline)
            .unwrap();
        assert_eq!(connection.deadline().unwrap(), deadline);
        let before = control_cookies();
        let document = fixture.document(deadline.min(policy_ceiling));
        let receiver = document
            .select_control()
            .unwrap()
            .bind_receiver(connection, &fixture.op)
            .unwrap();
        assert_eq!(
            control_cookies(),
            before,
            "same root control descriptor cookie through live admission"
        );
        custodian.expect("ARMED");
        phase_diagnostics::mark(
            phase_diagnostics::Phase::FixtureSetup,
            phase_diagnostics::Edge::End,
        );
        Self {
            fixture,
            custodian,
            agent,
            receiver,
            deadline,
            document,
        }
    }
    pub fn request(&mut self, request: &BrowserRequest) {
        let bytes = encode_request(request).unwrap();
        self.agent.command(b'h');
        let input = self.agent.child.stdin.as_mut().unwrap();
        input
            .write_all(&(bytes.len() as u32).to_be_bytes())
            .unwrap();
        input.write_all(&bytes).unwrap();
    }
    pub fn receive(&mut self) -> hepta_peer_attestation::ControlRetainedAcceptedStream {
        self.custodian.command(b's');
        let received = self.receiver.receive_retained_custodied().unwrap();
        self.custodian.expect("SENT");
        assert!(received.deadline().unwrap() <= self.deadline);
        assert!(self.receiver.receive_retained_custodied().is_err());
        received
    }
    pub fn finish(&mut self) {
        self.agent.finish();
        self.custodian.finish();
    }
    pub fn drift(&self) {
        self.fixture.rewrite("agent.principal_id", "changed-agent");
    }
    pub fn restore(&self) {
        self.fixture.rewrite("agent.principal_id", "source-agent");
    }
}
pub fn child_entry() -> bool {
    let a: Vec<_> = std::env::args_os().collect();
    if a.get(1).is_none_or(|v| v != "--child") {
        return false;
    }
    assert_eq!(a.len(), 6);
    let mode = a[2].to_str().unwrap();
    if mode == "agent" {
        agent(Path::new(&a[4]));
    } else {
        custodian(Path::new(&a[3]), Path::new(&a[4]), Path::new(&a[5]), mode);
    }
    true
}
pub fn configure(unit: &str) {
    assert_eq!(
        unsafe { libc::geteuid() },
        0,
        "explicit privileged fixture required; no skip"
    );
    UNIT.set(unit.to_owned()).unwrap();
}
pub fn launch_host(run: fn()) {
    if child_entry() {
        return;
    }
    let a: Vec<_> = std::env::args().collect();
    if a.get(1)
        .is_some_and(|v| v == "--configured-systemd-profile")
    {
        assert_eq!(a.len(), 3);
        configure(&a[2]);
        run();
        return;
    }
    let unit = format!("hepta-approved-startup-{}.service", std::process::id());
    let out = Command::new("/usr/bin/sudo")
        .args([
            "--non-interactive",
            "--",
            "/usr/bin/systemd-run",
            "--quiet",
            "--wait",
            "--collect",
            "--pipe",
        ])
        .arg(format!("--unit={unit}"))
        .arg("--property=RuntimeMaxSec=180s")
        .arg(std::env::current_exe().unwrap())
        .args(["--configured-systemd-profile", &unit])
        .output()
        .unwrap();
    std::io::stdout().write_all(&out.stdout).unwrap();
    std::io::stderr().write_all(&out.stderr).unwrap();
    assert!(
        out.status.success(),
        "actual transient root fixture required, no skip"
    );
}

// Fixed, opt-in parent-fixture diagnostics. Other support consumers leave this
// disabled. The complete lifecycle emits at most 90 samples; 128 allows a
// bounded margin. No per-drive sample, authority object, path or payload enters.
pub mod phase_diagnostics {
    use std::cell::{Cell, RefCell};
    use std::io::{self, Write};
    use std::panic::{AssertUnwindSafe, catch_unwind, resume_unwind};
    use std::time::{Duration, Instant};
    const CAPACITY: usize = 128;
    #[derive(Clone, Copy, Debug)]
    pub enum Phase {
        ReadBinary,
        WriteBinary,
        VerifyCopy,
        HashBinary,
        FixtureSetup,
        Admission,
        Enqueue,
        Response,
        Report,
        ChildrenFinish,
        ServoReady,
        PeersReady,
        AdmissionReady,
        StartupReady,
        RequestSend,
        RequestObserved,
    }
    #[derive(Clone, Copy, Debug)]
    pub enum Edge {
        Begin,
        End,
        Sample,
    }
    #[derive(Clone, Copy, Debug)]
    pub enum Request {
        Health,
        Create,
        Observe,
        Snapshot,
        Unknown,
    }
    #[derive(Clone, Copy, Debug)]
    pub enum Drive {
        None,
        Idle,
        Pending,
        Queued,
        RetiredCompletion,
        ReceiverGone,
        WakeFailed,
        Retired,
    }
    #[derive(Clone, Copy, Debug)]
    pub enum Data {
        Boundary,
        Stage {
            elapsed_ms: u128,
        },
        Startup {
            elapsed_ms: u128,
            remaining_ms: u128,
        },
        Send {
            request: Request,
            remaining_ms: u128,
        },
        Observation {
            request: Request,
            elapsed_ms: u128,
            drives: u64,
            drive_ms: u128,
            last_drive: Drive,
        },
    }
    #[derive(Clone, Copy, Debug)]
    struct Sample {
        phase: Phase,
        edge: Edge,
        since_start: Duration,
        data: Data,
    }
    struct Trace {
        origin: Instant,
        samples: [Option<Sample>; CAPACITY],
        len: usize,
    }
    thread_local! {
        static TRACE: RefCell<Option<Trace>> = const { RefCell::new(None) };
        static LOST: Cell<bool> = const { Cell::new(false) };
    }
    pub fn record(phase: Phase, edge: Edge, data: Data) {
        // The hot path contains only an owner-thread borrow, clock read and
        // fixed-array assignment. It cannot format, allocate, perform I/O,
        // wait on a mutex or affect any request result. Clock cost is nonzero.
        let _ = TRACE.try_with(|slot| {
            let Ok(mut slot) = slot.try_borrow_mut() else {
                LOST.set(true);
                return;
            };
            let Some(trace) = slot.as_mut() else { return };
            if trace.len == CAPACITY {
                LOST.set(true);
                return;
            }
            if matches!(
                data,
                Data::Send {
                    request: Request::Unknown,
                    ..
                } | Data::Observation {
                    request: Request::Unknown,
                    ..
                }
            ) {
                LOST.set(true);
            }
            trace.samples[trace.len] = Some(Sample {
                phase,
                edge,
                since_start: trace.origin.elapsed(),
                data,
            });
            trace.len += 1;
        });
    }
    pub fn mark(phase: Phase, edge: Edge) {
        record(phase, edge, Data::Boundary);
    }
    pub fn request(value: &str) -> Request {
        match value {
            "health" => Request::Health,
            "create" => Request::Create,
            "observe" => Request::Observe,
            "snapshot" => Request::Snapshot,
            _ => Request::Unknown,
        }
    }
    fn start() {
        TRACE.with(|slot| {
            assert!(slot.borrow().is_none(), "one diagnostic case per process");
            *slot.borrow_mut() = Some(Trace {
                origin: Instant::now(),
                samples: [None; CAPACITY],
                len: 0,
            });
        });
        LOST.set(false);
    }
    fn flush(sink: &mut impl Write, succeeded: bool) -> io::Result<()> {
        let trace = TRACE
            .with(|slot| slot.borrow_mut().take())
            .ok_or_else(|| io::Error::other("diagnostic trace absent"))?;
        // Formatting/I/O occurs only after the case returned or finished
        // unwinding. No I/O or fallible diagnostic work runs from a Drop.
        for sample in trace.samples[..trace.len].iter().flatten() {
            writeln!(
                sink,
                "APPROVED_NATIVE_PHASE phase={:?} edge={:?} ns={} data={:?}",
                sample.phase,
                sample.edge,
                sample.since_start.as_nanos(),
                sample.data
            )?;
        }
        let lost = LOST.get();
        writeln!(
            sink,
            "APPROVED_NATIVE_PHASE_END count={} lost={} case_succeeded={}",
            trace.len, lost, succeeded
        )?;
        sink.flush()?;
        if lost {
            return Err(io::Error::other("diagnostic trace incomplete"));
        }
        Ok(())
    }
    pub fn run_case(case: impl FnOnce()) {
        start();
        let result = catch_unwind(AssertUnwindSafe(case));
        // Diagnostic I/O failure never changes the original case result.
        // Missing/partial output or lost=true is separate, incomplete evidence.
        let _diagnostic_result = flush(&mut io::stderr().lock(), result.is_ok());
        if let Err(original) = result {
            resume_unwind(original);
        }
    }
}
