//! Required actual transient-systemd/default-procfs configured-policy corpus.
//! Explicit unit, cgroup and owned ELF pin are fixed BEFORE peer launch.
//! Actual root/nobody files/processes; native completion is synthetic, not Servo.
#![deny(unsafe_op_in_unsafe_fn)]
use hepta_agent_transport::{
    AcceptedStreamCustody, ClientConnection, PeerIdentity, PeerPolicy, RemoteTerminalState,
    RootControlPathPolicy, RootOwnedControlListener, RootPathControlConnection,
};
use hepta_browser_actor::{ServoRuntimeError, servo_runtime_pair};
use hepta_browser_codec::{
    BrowserOperation, BrowserRequest, JsonObject, decode_response, encode_request,
};
use hepta_browserd::{
    ApprovedRetainedProductConnection, ProductControlMonitorOutcome, ProductRequestCoordinator,
    RestartPolicy,
};
use hepta_peer_attestation::{
    ApprovedPolicyDocument, ApprovedPolicyError, AttestationError, ControlOwnerError,
    ProcfsPeerAttestor, RootPathAttestedHandoffReceiver,
};
use hepta_session_core::{JournalId, ManagedOpenPolicy, ReceiptJournal, ReceiptLifecycleState};
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
use std::sync::atomic::{AtomicU32, Ordering};
use std::sync::{Arc, OnceLock};
use std::thread;
use std::time::{Duration, Instant};
const WAIT: Duration = Duration::from_secs(20);
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
fn inventory() -> Vec<(u32, PathBuf)> {
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
struct Fixture {
    root: PathBuf,
    cp: PathBuf,
    op: PathBuf,
    binary: PathBuf,
    config: PathBuf,
    owner_pid: u32,
}
impl Fixture {
    fn new() -> Self {
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
        let bytes = fs::read(std::env::current_exe().unwrap()).unwrap();
        fs::write(&binary, &bytes).unwrap();
        fs::set_permissions(&binary, fs::Permissions::from_mode(0o555)).unwrap();
        assert_eq!(fs::read(&binary).unwrap(), bytes);
        // Hash the known launcher-owned copied file before either peer exists.
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
    fn listener(&self) -> RootOwnedControlListener {
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
    fn document(&self, deadline: Instant) -> ApprovedPolicyDocument {
        ApprovedPolicyDocument::open_root_owned_before(&self.config, deadline).unwrap()
    }
    fn rewrite(&self, key: &str, value: &str) {
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
struct ChildOwner {
    child: Child,
    owner_pid: u32,
    done: bool,
}
impl ChildOwner {
    fn spawn(f: &Fixture, mode: &str, op: &Path, nobody: bool) -> Self {
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
    fn line(&mut self) -> String {
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
            assert!(out.len() < 256);
        }
        String::from_utf8(out).unwrap()
    }
    fn expect(&mut self, s: &str) {
        assert_eq!(self.line(), s);
    }
    fn command(&mut self, b: u8) {
        self.child.stdin.as_mut().unwrap().write_all(&[b]).unwrap();
    }
    fn finish(&mut self) {
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
    let mut sender = match setup {
        Ok(s) => s,
        Err(_) => {
            println!("SETUP_REFUSED");
            assert_eq!(input(), b'x');
            return;
        }
    };
    assert_eq!(
        control_cookies(),
        before,
        "same original control socket cookies, no replacement socket"
    );
    assert_eq!(sender.ensure_control_current().unwrap(), deadline);
    println!("ARMED");
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
            match input() {
                b'x' => return,
                b'c' => {
                    pending.request_cancel().unwrap();
                    println!("CANCELLED");
                }
                _ => panic!("owned command"),
            }
        }
        match pending.poll_retirement() {
            Ok(None) => (),
            Ok(Some(report)) => {
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
            Err(_) => {
                println!("REPORT_REFUSED");
                assert_eq!(input(), b'x');
                return;
            }
        }
        thread::sleep(Duration::from_millis(2));
    }
}
fn agent(op: &Path) {
    let mut stream = UnixStream::connect(op).unwrap();
    println!("CONNECTED");
    match input() {
        b'x' => return,
        b'e' => {
            stream.set_read_timeout(Some(WAIT)).unwrap();
            let mut byte = [0];
            assert_eq!(stream.read(&mut byte).unwrap(), 0);
            println!("ORIGINAL_EOF_WITHOUT_HANDSHAKE");
            assert_eq!(input(), b'x');
            return;
        }
        b'h' => (),
        _ => panic!("owned Agent command"),
    };
    let peer = PeerIdentity::from_stream(&stream).unwrap();
    let mut client = ClientConnection::connect(stream, PeerPolicy::exact(peer), WAIT).unwrap();
    let sequence = client
        .send_request(encode_request(&request()).unwrap(), WAIT)
        .unwrap();
    println!("REQUEST");
    if let Ok(bytes) = client.receive_response(sequence, WAIT) {
        decode_response(&bytes).unwrap();
        println!("RESPONSE");
    } else {
        println!("RESPONSE_REFUSED");
    }
    assert_eq!(input(), b'x');
}
struct Trio {
    fixture: Fixture,
    custodian: ChildOwner,
    agent: ChildOwner,
    receiver: RootPathAttestedHandoffReceiver,
    deadline: Instant,
    document: ApprovedPolicyDocument,
}
impl Trio {
    fn new(wait: Duration) -> Self {
        Self::new_mode(wait, "custodian", wait)
    }
    fn new_mode(wait: Duration, mode: &str, policy_wait: Duration) -> Self {
        let fixture = Fixture::new();
        let mut listener = fixture.listener();
        let mut custodian = ChildOwner::spawn(&fixture, mode, &fixture.op, false);
        custodian.expect("PATH_CURRENT");
        let mut agent = ChildOwner::spawn(&fixture, "agent", &fixture.op, false);
        agent.expect("CONNECTED");
        let deadline = Instant::now() + wait;
        let connection = listener
            .accept_before(kernel(0, 0, Some(custodian.child.id())), deadline)
            .unwrap();
        assert_eq!(connection.deadline().unwrap(), deadline);
        let before = control_cookies();
        let document = fixture.document(deadline.min(Instant::now() + policy_wait));
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
        Self {
            fixture,
            custodian,
            agent,
            receiver,
            deadline,
            document,
        }
    }
    fn receive(&mut self) -> hepta_peer_attestation::ControlRetainedAcceptedStream {
        self.custodian.command(b's');
        let received = self.receiver.receive_retained_custodied().unwrap();
        self.custodian.expect("SENT");
        assert!(received.deadline().unwrap() <= self.deadline);
        assert!(self.receiver.receive_retained_custodied().is_err());
        received
    }
    fn finish(&mut self) {
        self.agent.finish();
        self.custodian.finish();
    }
    fn drift(&self) {
        self.fixture.rewrite("agent.principal_id", "changed-agent");
    }
    fn restore(&self) {
        self.fixture.rewrite("agent.principal_id", "source-agent");
    }
}
fn verify_entries() {
    for which in 0..5 {
        let mut trio = Trio::new(WAIT);
        let received = trio.receive();
        let admitted = trio
            .document
            .select_agent()
            .unwrap()
            .admit_retained(received)
            .unwrap();
        admitted
            .consume_before(
                |stream, deadline, custody, mut retained, attested, principal| {
                    assert_eq!(principal, "source-agent");
                    assert!(deadline <= trio.deadline);
                    let identity = PeerIdentity::from_stream(&stream).unwrap();
                    assert_eq!(identity.pid, Some(attested.snapshot().pid));
                    assert_eq!(identity.uid, attested.snapshot().uid);
                    assert_eq!(identity.gid, attested.snapshot().gid);
                    let agent_custody = attested.request_custody().unwrap();
                    let agent = agent_custody.verifier();
                    let verifier = custody.verifier().unwrap();
                    let verify = || match which {
                        0 => verifier.ensure_alive(),
                        1 => verifier.ensure_pair_alive(&agent),
                        2 => verifier.verify_current(),
                        3 => verifier.verify_pair_current(&agent),
                        _ => verifier.deadline().map(|_| ()),
                    };
                    verify().unwrap();
                    trio.drift();
                    assert!(verify().is_err());
                    trio.restore();
                    assert!(
                        verify().is_err(),
                        "observed path failure cannot revive after restore"
                    );
                    assert!(retained.ensure_current().is_err());
                    drop(custody);
                    drop(stream);
                },
            )
            .unwrap_err();
        trio.custodian.expect("REPORT_REFUSED");
        trio.finish();
    }
}
#[derive(Clone, Copy)]
enum Cut {
    Normal,
    BeforeServe,
    Fork,
    NativePath,
    TerminalPath,
    CancelActive,
}
fn product(cut: Cut) {
    let mut trio = Trio::new(WAIT);
    let received = trio.receive();
    let (connection, monitor) = ApprovedRetainedProductConnection::from_received(
        received,
        trio.document.select_agent().unwrap(),
    )
    .unwrap();
    assert!(connection.deadline().unwrap() <= trio.deadline);
    if matches!(cut, Cut::Fork) {
        let pid = unsafe { libc::fork() };
        assert!(pid >= 0);
        if pid == 0 {
            assert_eq!(
                trio.document.ensure_current(),
                Err(ApprovedPolicyError::ProcessChanged)
            );
            assert!(trio.document.select_control().is_err());
            assert!(trio.document.select_agent().is_err());
            assert!(connection.deadline().is_err());
            assert!(connection.cancellation().is_err());
            drop(connection);
            drop(monitor);
            unsafe { libc::_exit(0) }
        }
        let mut status = 0;
        assert_eq!(unsafe { libc::waitpid(pid, &mut status, 0) }, pid);
        assert_eq!(status, 0);
        connection.deadline().unwrap();
    }
    let path = trio.fixture.root.join("receipts");
    let journal = ReceiptJournal::create_managed(&path, JournalId([0x51; 16]), 1).unwrap();
    let (endpoint, mut owner) = servo_runtime_pair(Arc::new(|| {}));
    let mut monitor = Some(monitor);
    let monitor_worker = if matches!(cut, Cut::CancelActive) {
        let monitor = monitor.take().unwrap();
        Some(thread::spawn(move || monitor.run()))
    } else {
        None
    };
    let (ready_tx, ready_rx) = std::sync::mpsc::sync_channel(1);
    let (go_tx, go_rx) = std::sync::mpsc::sync_channel(1);
    let worker = thread::spawn(move || {
        let mut coordinator = ProductRequestCoordinator::from_approved_retained_connection(
            &connection,
            endpoint,
            journal,
            "source-root-path-fixture".into(),
            RestartPolicy::new(3).unwrap(),
        )
        .unwrap();
        if matches!(cut, Cut::BeforeServe) {
            ready_tx.send(()).unwrap();
            go_rx.recv_timeout(WAIT).unwrap();
        }
        coordinator.serve_approved_retained_connection(connection)
    });
    if matches!(cut, Cut::BeforeServe) {
        ready_rx.recv_timeout(WAIT).unwrap();
        trio.drift();
        go_tx.send(()).unwrap();
        trio.agent.command(b'e');
    } else {
        trio.agent.command(b'h');
    }
    let stop = Instant::now() + WAIT;
    let mut calls = 0;
    while !worker.is_finished() {
        owner.pump_one();
        if let Some(command) = owner.take_command() {
            calls += 1;
            let (_, _, completion) = command.into_parts();
            if matches!(cut, Cut::CancelActive) {
                trio.custodian.command(b'c');
                trio.custodian.expect("CANCELLED");
                while completion.ensure_active().is_ok() {
                    assert!(Instant::now() < stop, "original cancel budget");
                    thread::sleep(Duration::from_millis(1));
                }
                assert!(completion.ensure_current_peer().is_err());
                completion.complete_error(ServoRuntimeError::Cancelled);
            } else if matches!(cut, Cut::NativePath) {
                trio.drift();
                assert!(completion.ensure_active().is_err());
                assert!(completion.ensure_current_peer().is_err());
                completion.complete_error(ServoRuntimeError::Cancelled);
            } else {
                completion.ensure_current_peer().unwrap();
                completion.complete_success(JsonObject::new(), None);
            }
        }
        assert!(Instant::now() < stop);
        thread::sleep(Duration::from_millis(1));
    }
    let served = worker.join().unwrap();
    assert_eq!(
        calls,
        if matches!(cut, Cut::BeforeServe) {
            0
        } else {
            1
        },
        "bounded actual source callback count, no Servo claim"
    );
    if matches!(cut, Cut::TerminalPath) {
        assert!(served.is_ok());
        trio.drift();
    }
    let observed = if let Some(worker) = monitor_worker {
        worker.join().unwrap()
    } else {
        monitor.take().unwrap().run()
    };
    let packet = if matches!(cut, Cut::Normal | Cut::Fork | Cut::CancelActive) {
        if !matches!(cut, Cut::CancelActive) {
            assert!(served.is_ok());
        }
        assert_eq!(observed, Ok(ProductControlMonitorOutcome::ReportEnqueued));
        Some(trio.custodian.line())
    } else {
        assert!(observed.is_err());
        trio.custodian.expect("REPORT_REFUSED");
        None
    };
    if matches!(cut, Cut::BeforeServe) {
        trio.agent.expect("ORIGINAL_EOF_WITHOUT_HANDSHAKE");
    } else {
        trio.agent.expect("REQUEST");
        let response = trio.agent.line();
        assert!(response == "RESPONSE" || response == "RESPONSE_REFUSED");
    }
    let mut history =
        ReceiptJournal::open_managed(&path, JournalId([0x51; 16]), ManagedOpenPolicy::STRICT)
            .unwrap();
    let records = history.inspect().unwrap().records;
    if matches!(cut, Cut::BeforeServe) {
        assert!(served.is_err());
        assert!(
            records.is_empty(),
            "no Requested or Dispatched facts before source refusal"
        );
        drop(history);
        trio.finish();
        return;
    }
    assert_eq!(records.len(), 3);
    if matches!(cut, Cut::NativePath | Cut::CancelActive) {
        assert_eq!(
            records.last().unwrap().event.lifecycle,
            ReceiptLifecycleState::Indeterminate
        );
    } else {
        assert_eq!(
            records.last().unwrap().event.lifecycle,
            ReceiptLifecycleState::Completed
        );
    }
    if let Some(packet) = packet {
        let last = records.last().unwrap();
        let state = if matches!(cut, Cut::CancelActive) {
            RemoteTerminalState::Indeterminate
        } else {
            RemoteTerminalState::Completed
        };
        assert_eq!(
            packet,
            format!(
                "REPORT {:?} {} {}",
                state,
                hex(&last.event.request_sha256),
                hex(&last.record_sha256)
            ),
            "actual private coordinator seal binds this own complete journal"
        );
    }
    drop(history);
    trio.finish();
}
fn wrong_control_pin() {
    let f = Fixture::new();
    f.rewrite("control.elf_sha256", &"0".repeat(64));
    let mut listener = f.listener();
    let mut child = ChildOwner::spawn(&f, "custodian", &f.op, false);
    child.expect("PATH_CURRENT");
    let original = UnixStream::connect(&f.op).unwrap();
    let deadline = Instant::now() + WAIT;
    let connection = listener
        .accept_before(kernel(0, 0, Some(child.child.id())), deadline)
        .unwrap();
    assert_eq!(
        f.document(deadline)
            .select_control()
            .unwrap()
            .bind_receiver(connection, &f.op)
            .err(),
        Some(ApprovedPolicyError::PeerRefused)
    );
    child.expect("SETUP_REFUSED");
    drop(original);
    child.finish();
}
fn wrong_agent_policy() {
    for (key, value) in [
        ("agent.elf_sha256", "0".repeat(64)),
        ("agent.uid", "65534".into()),
        ("agent.gid", "65534".into()),
        (
            "agent.cgroup",
            format!("/unapproved.slice/{}", UNIT.get().unwrap()),
        ),
        ("agent.unit", "unapproved.service".into()),
    ] {
        let f = Fixture::new();
        f.rewrite(key, &value);
        if key == "agent.unit" {
            f.rewrite("agent.cgroup", "/system.slice/unapproved.service");
        }
        let mut listener = f.listener();
        let mut child = ChildOwner::spawn(&f, "custodian", &f.op, false);
        child.expect("PATH_CURRENT");
        let mut agent = ChildOwner::spawn(&f, "agent", &f.op, false);
        agent.expect("CONNECTED");
        let deadline = Instant::now() + WAIT;
        let document = f.document(deadline);
        let connection = listener
            .accept_before(kernel(0, 0, Some(child.child.id())), deadline)
            .unwrap();
        let mut receiver = document
            .select_control()
            .unwrap()
            .bind_receiver(connection, &f.op)
            .unwrap();
        child.expect("ARMED");
        child.command(b's');
        let received = receiver.receive_retained_custodied().unwrap();
        child.expect("SENT");
        assert_eq!(
            document
                .select_agent()
                .unwrap()
                .admit_retained(received)
                .err(),
            Some(ApprovedPolicyError::PeerRefused)
        );
        child.expect("REPORT_REFUSED");
        agent.finish();
        child.finish();
    }
}
fn new_document_is_not_original_source() {
    let mut trio = Trio::new(WAIT);
    let other = trio.fixture.document(trio.deadline);
    let received = trio.receive();
    assert_eq!(
        other.select_agent().unwrap().admit_retained(received).err(),
        Some(ApprovedPolicyError::PeerRefused)
    );
    trio.custodian.expect("REPORT_REFUSED");
    trio.finish();
}
fn cross_uid_refusal() {
    let f = Fixture::new();
    // Source explicitly configured the child, yet kernel procfs executable
    // access is denied. No static configured pin substitutes for live custody.
    // Sender and receiver have explicit different counterparty policies.
    // Sender still expects the root broker, so its NEW approved admission
    // actually attempts and refuses inaccessible live root /proc/exe.
    let sender_config = f.root.join("sender-approved-policy");
    fs::copy(&f.config, &sender_config).unwrap();
    chown(&sender_config, 0, NOBODY);
    fs::set_permissions(&sender_config, fs::Permissions::from_mode(0o440)).unwrap();
    f.rewrite("control.uid", "65534");
    f.rewrite("control.gid", "65534");
    let mut listener = f.listener();
    let directory = f.root.join("nobody");
    fs::create_dir(&directory).unwrap();
    chown(&directory, NOBODY, NOBODY);
    fs::set_permissions(&directory, fs::Permissions::from_mode(0o700)).unwrap();
    let op = directory.join("agent.sock");
    let mut child = ChildOwner::spawn(&f, "cross", &op, true);
    child.expect("PATH_CURRENT");
    let original = UnixStream::connect(&op).unwrap();
    let deadline = Instant::now() + WAIT;
    let connection = listener
        .accept_before(kernel(NOBODY, NOBODY, Some(child.child.id())), deadline)
        .unwrap();
    assert!(
        f.document(deadline)
            .select_control()
            .unwrap()
            .bind_receiver(connection, &op)
            .is_err()
    );
    child.expect("LIVE_PEER_REFUSED");
    drop(original);
    child.finish();
}
fn earlier_policy_deadline() {
    let mut trio = Trio::new_mode(WAIT, "custodian", Duration::from_secs(3));
    let received = trio.receive();
    let fixed = received.deadline().unwrap();
    assert!(fixed < trio.deadline);
    let approved = trio
        .document
        .select_agent()
        .unwrap()
        .admit_retained(received)
        .unwrap();
    assert_eq!(
        approved.consume_before(|stream, deadline, custody, mut retained, _, _| {
            assert_eq!(fixed, deadline);
            let verifier = custody.verifier().unwrap();
            assert_eq!(verifier.deadline().unwrap(), fixed);
            thread::sleep(
                fixed.saturating_duration_since(Instant::now()) + Duration::from_millis(10),
            );
            assert!(verifier.ensure_alive().is_err());
            assert!(retained.ensure_current().is_err());
            drop(stream);
        }),
        Err(ApprovedPolicyError::DeadlineExceeded)
    );
    trio.custodian.expect("REPORT_REFUSED");
    trio.finish();
}
fn root_main() {
    assert_eq!(
        unsafe { libc::geteuid() },
        0,
        "required explicit root profile; no skip"
    );
    for (name, run) in [
        ("five-policy-verifier-entrypoints", verify_entries as fn()),
        ("configured-durable-terminal", || product(Cut::Normal)),
        ("policy-drift-before-serve-zero-facts", || {
            product(Cut::BeforeServe)
        }),
        ("fork-original-owner", || product(Cut::Fork)),
        ("native-final-policy-refusal", || product(Cut::NativePath)),
        ("terminal-policy-refusal", || product(Cut::TerminalPath)),
        ("cancel-keeps-report-only-policy", || {
            product(Cut::CancelActive)
        }),
        ("explicit-wrong-control-pin", wrong_control_pin),
        ("five-explicit-wrong-agent-fields", wrong_agent_policy),
        (
            "new-document-not-original-source",
            new_document_is_not_original_source,
        ),
        ("cross-uid-procfs-closed", cross_uid_refusal),
        ("earlier-original-policy-deadline", earlier_policy_deadline),
    ] {
        let before = inventory();
        run();
        assert_eq!(inventory(), before, "actual descriptor retirement");
        println!("PASS {name}; actual kernel/default procfs, source callback only");
    }
    println!(
        "12 actual configured-policy groups; five verifier entrypoints; no installed/Servo qualification"
    );
}
fn main() {
    let a: Vec<_> = std::env::args_os().collect();
    if a.get(1).is_some_and(|x| x == "--child") {
        let mode = a[2].to_str().unwrap();
        let cp = Path::new(&a[3]);
        let op = Path::new(&a[4]);
        let config = Path::new(&a[5]);
        if mode == "agent" {
            agent(op)
        } else {
            custodian(cp, op, config, mode)
        }
        return;
    }
    if a.get(1)
        .is_some_and(|x| x == "--configured-systemd-profile")
    {
        UNIT.set(a[2].to_str().unwrap().to_owned()).unwrap();
        root_main();
        return;
    }
    let unit = format!("hepta-approved-policy-{}.service", std::process::id());
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
        .expect("actual transient systemd source fixture required");
    std::io::stdout().write_all(&out.stdout).unwrap();
    std::io::stderr().write_all(&out.stderr).unwrap();
    assert!(out.status.success(), "no skip/fallback");
}
