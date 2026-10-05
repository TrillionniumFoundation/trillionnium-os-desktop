//! Required privileged source corpus. Actual root/nobody path and live procfs
//! facts never claim an installed broker. Native completion remains synthetic.
#![deny(unsafe_op_in_unsafe_fn)]
use hepta_agent_transport::{
    AcceptedStreamCustody, ClientConnection, PeerIdentity, PeerPolicy, RemoteTerminalState,
    RootControlPathPolicy, RootOwnedControlListener, RootPathControlConnection,
};
use hepta_browser_actor::{ServoRuntimeError, TaskFlowPrincipal, servo_runtime_pair};
use hepta_browser_codec::{
    BrowserOperation, BrowserRequest, JsonObject, decode_response, encode_request,
};
use hepta_browserd::{
    ProductControlMonitorOutcome, ProductRequestCoordinator, RestartPolicy,
    RetainedProductConnection,
};
use hepta_peer_attestation::{
    AttestationError, ControlOwnerError, ControlOwnerPolicy, PeerRuntimePolicy, ProcfsPeerAttestor,
    RootPathAttestedHandoffReceiver, RootPathAttestedHandoffSender,
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
use std::sync::Arc;
use std::sync::atomic::{AtomicU32, Ordering};
use std::thread;
use std::time::{Duration, Instant};
const WAIT: Duration = Duration::from_secs(20);
const NOBODY: u32 = 65534;
static NEXT: AtomicU32 = AtomicU32::new(0);
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
    pin: String,
    runtime: PeerRuntimePolicy,
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
        // Explicit launcher provisioning happens before either peer launch.
        // The known owned test ELF is never approval learned from a peer.
        let selected = ProcfsPeerAttestor::default()
            .read_snapshot(std::process::id())
            .unwrap();
        let runtime = PeerRuntimePolicy::exact(&selected);
        let pin = selected.executable_sha256;
        let binary = root.join("fixture");
        let bytes = fs::read(std::env::current_exe().unwrap()).unwrap();
        fs::write(&binary, bytes).unwrap();
        fs::set_permissions(&binary, fs::Permissions::from_mode(0o555)).unwrap();
        let config = root.join("explicit-policy");
        fs::write(
            &config,
            format!(
                "{}\n{}\n{}\n{}\n",
                pin,
                runtime.expected_cgroup_v2_path,
                runtime.expected_systemd_unit.as_deref().unwrap_or(""),
                std::process::id()
            ),
        )
        .unwrap();
        fs::set_permissions(&config, fs::Permissions::from_mode(0o440)).unwrap();
        chown(&config, 0, NOBODY);
        Self {
            cp: root.join("control.sock"),
            op: root.join("agent.sock"),
            binary,
            config,
            root,
            pin,
            runtime,
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
    fn policy(&self, pid: u32, uid: u32, pin: &str) -> ControlOwnerPolicy {
        let mut runtime = self.runtime.clone();
        runtime.expected_uid = uid;
        runtime.expected_gid = if uid == 0 { 0 } else { NOBODY };
        ControlOwnerPolicy::new(
            kernel(uid, runtime.expected_gid, Some(pid)),
            runtime,
            pin.into(),
        )
        .unwrap()
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
            .arg(&f.config);
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
fn child_policy(config: &Path) -> (ControlOwnerPolicy, u32) {
    let text = fs::read_to_string(config).unwrap();
    let fields: Vec<_> = text.lines().collect();
    assert_eq!(fields.len(), 4);
    let parent = fields[3].parse().unwrap();
    let runtime = PeerRuntimePolicy {
        expected_uid: 0,
        expected_gid: 0,
        expected_cgroup_v2_path: fields[1].into(),
        expected_systemd_unit: (!fields[2].is_empty()).then(|| fields[2].into()),
    };
    (
        ControlOwnerPolicy::new(kernel(0, 0, Some(parent)), runtime, fields[0].into()).unwrap(),
        parent,
    )
}
fn custodian(cp: &Path, op: &Path, config: &Path, mode: &str) {
    let cross = mode == "cross";
    let original = UnixListener::bind(op).unwrap();
    let (policy, parent) = child_policy(config);
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
    let setup = RootPathAttestedHandoffSender::from_accepted(connection, accepted, policy);
    if cross {
        assert_eq!(setup.err(), Some(ControlOwnerError::PeerRefused));
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
    let stream = UnixStream::connect(op).unwrap();
    println!("CONNECTED");
    match input() {
        b'x' => return,
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
}
impl Trio {
    fn new(wait: Duration) -> Self {
        Self::new_mode(wait, "custodian")
    }
    fn new_mode(wait: Duration, mode: &str) -> Self {
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
        let receiver = RootPathAttestedHandoffReceiver::from_control(
            connection,
            fixture.policy(custodian.child.id(), 0, &fixture.pin),
            &fixture.op,
        )
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
        fs::set_permissions(&self.fixture.cp, fs::Permissions::from_mode(0o600)).unwrap();
    }
    fn restore(&self) {
        fs::set_permissions(&self.fixture.cp, fs::Permissions::from_mode(0o660)).unwrap();
    }
}
fn verify_entries() {
    for which in 0..5 {
        let mut trio = Trio::new(WAIT);
        let received = trio.receive();
        received
            .consume_before(|stream, deadline, custody, mut retained| {
                assert!(deadline <= trio.deadline);
                let identity = PeerIdentity::from_stream(&stream).unwrap();
                let attested = ProcfsPeerAttestor::default()
                    .attest(identity, &trio.fixture.runtime)
                    .unwrap();
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
            })
            .unwrap();
        trio.custodian.expect("REPORT_REFUSED");
        trio.finish();
    }
}
#[derive(Clone, Copy)]
enum Cut {
    Normal,
    Fork,
    NativePath,
    TerminalPath,
    CancelActive,
}
fn product(cut: Cut) {
    let mut trio = Trio::new(WAIT);
    let received = trio.receive();
    if matches!(cut, Cut::Fork) {
        let pid = unsafe { libc::fork() };
        assert!(pid >= 0);
        if pid == 0 {
            assert_eq!(
                received.deadline().err(),
                Some(ControlOwnerError::ProcessChanged)
            );
            drop(received);
            unsafe { libc::_exit(0) }
        }
        let mut status = 0;
        assert_eq!(unsafe { libc::waitpid(pid, &mut status, 0) }, pid);
        assert_eq!(status, 0);
    }
    let (connection, monitor) = RetainedProductConnection::from_control_retained_received(
        received,
        &trio.fixture.runtime,
        &trio.fixture.pin,
    )
    .unwrap();
    assert!(connection.deadline().unwrap() <= trio.deadline);
    let principal = TaskFlowPrincipal {
        principal_id: "explicit-root-path-source-fixture".into(),
        expected_uid: 0,
        expected_gid: 0,
        expected_systemd_unit: trio
            .fixture
            .runtime
            .expected_systemd_unit
            .clone()
            .expect("actual inherited host service unit, no synthetic unit"),
        expected_cgroup_v2_path: trio.fixture.runtime.expected_cgroup_v2_path.clone(),
        expected_executable_sha256: trio.fixture.pin.clone(),
    };
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
    let worker = thread::spawn(move || {
        let mut coordinator = ProductRequestCoordinator::from_retained_connection(
            principal,
            &connection,
            endpoint,
            journal,
            "source-root-path-fixture".into(),
            RestartPolicy::new(3).unwrap(),
        )
        .unwrap();
        coordinator.serve_retained_connection(connection)
    });
    trio.agent.command(b'h');
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
        calls, 1,
        "one actual queued source callback, no Servo claim"
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
    trio.agent.expect("REQUEST");
    let response = trio.agent.line();
    assert!(response == "RESPONSE" || response == "RESPONSE_REFUSED");
    let mut history =
        ReceiptJournal::open_managed(&path, JournalId([0x51; 16]), ManagedOpenPolicy::STRICT)
            .unwrap();
    let records = history.inspect().unwrap().records;
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
fn earlier_deadline() {
    let mut trio = Trio::new(Duration::from_secs(3));
    let received = trio.receive();
    let deadline = received.deadline().unwrap();
    assert_eq!(deadline, trio.deadline);
    received
        .consume_before(|stream, fixed, custody, mut retained| {
            assert_eq!(fixed, deadline);
            let verifier = custody.verifier().unwrap();
            assert_eq!(verifier.deadline().unwrap(), deadline);
            thread::sleep(
                deadline.saturating_duration_since(Instant::now()) + Duration::from_millis(10),
            );
            assert!(verifier.ensure_alive().is_err());
            assert!(retained.ensure_current().is_err());
            drop(stream);
        })
        .unwrap();
    trio.custodian.expect("REPORT_REFUSED");
    trio.finish();
}
fn earlier_accepted_deadline() {
    let mut trio = Trio::new_mode(WAIT, "early");
    let received = trio.receive();
    let deadline = received.deadline().unwrap();
    assert!(deadline < trio.deadline);
    received
        .consume_before(|stream, fixed, custody, mut retained| {
            assert_eq!(fixed, deadline);
            let verifier = custody.verifier().unwrap();
            assert_eq!(verifier.deadline().unwrap(), deadline);
            thread::sleep(
                deadline.saturating_duration_since(Instant::now()) + Duration::from_millis(10),
            );
            assert!(verifier.ensure_alive().is_err());
            assert!(retained.ensure_current().is_err());
            drop(stream);
        })
        .unwrap();
    trio.custodian.expect("REPORT_REFUSED");
    trio.finish();
}
fn expired_accepted_no_packet() {
    let f = Fixture::new();
    let mut listener = f.listener();
    let mut child = ChildOwner::spawn(&f, "expired", &f.op, false);
    child.expect("PATH_CURRENT");
    let mut original = UnixStream::connect(&f.op).unwrap();
    original.set_read_timeout(Some(WAIT)).unwrap();
    let fixed = Instant::now() + WAIT;
    let connection = listener
        .accept_before(kernel(0, 0, Some(child.child.id())), fixed)
        .unwrap();
    let mut receiver = RootPathAttestedHandoffReceiver::from_control(
        connection,
        f.policy(child.child.id(), 0, &f.pin),
        &f.op,
    )
    .unwrap();
    child.expect("ARMED");
    child.command(b's');
    assert_eq!(
        receiver.receive_retained_custodied().err(),
        Some(ControlOwnerError::HandoffRefused),
        "original expired custody closes without descriptor publication"
    );
    child.expect("EXPIRED_NO_PACKET");
    let mut byte = [0];
    assert_eq!(
        original.read(&mut byte).unwrap(),
        0,
        "original accepted stream retired on unsent expiry"
    );
    drop(original);
    child.finish();
}
fn cross_uid_refusal() {
    let f = Fixture::new();
    let mut listener = f.listener();
    let directory = f.root.join("nobody");
    fs::create_dir(&directory).unwrap();
    chown(&directory, NOBODY, NOBODY);
    fs::set_permissions(&directory, fs::Permissions::from_mode(0o700)).unwrap();
    let op = directory.join("agent.sock");
    let mut child = ChildOwner::spawn(&f, "cross", &op, true);
    child.expect("PATH_CURRENT");
    let original = UnixStream::connect(&op).unwrap();
    let connection = listener
        .accept_before(
            kernel(NOBODY, NOBODY, Some(child.child.id())),
            Instant::now() + WAIT,
        )
        .unwrap();
    connection.deadline().unwrap();
    let result = RootPathAttestedHandoffReceiver::from_control(
        connection,
        f.policy(child.child.id(), NOBODY, &f.pin),
        &op,
    );
    assert!(
        matches!(
            result.err(),
            Some(ControlOwnerError::PeerRefused | ControlOwnerError::HandoffRefused)
        ),
        "peer's actual cross-UID procfs refusal closes the original channel; the root endpoint may itself read its owned child, but cannot continue a closed handoff"
    );
    child.expect("LIVE_PEER_REFUSED");
    drop(original);
    child.finish();
}
fn wrong_pin() {
    let f = Fixture::new();
    let mut listener = f.listener();
    let mut child = ChildOwner::spawn(&f, "custodian", &f.op, false);
    child.expect("PATH_CURRENT");
    let original = UnixStream::connect(&f.op).unwrap();
    let deadline = Instant::now() + WAIT;
    let connection = listener
        .accept_before(kernel(0, 0, Some(child.child.id())), deadline)
        .unwrap();
    let wrong = "0".repeat(64);
    assert_ne!(wrong, f.pin);
    assert_eq!(
        RootPathAttestedHandoffReceiver::from_control(
            connection,
            f.policy(child.child.id(), 0, &wrong),
            &f.op
        )
        .err(),
        Some(ControlOwnerError::PeerRefused)
    );
    child.expect("SETUP_REFUSED");
    drop(original);
    child.finish();
}
fn root_main() {
    assert_eq!(
        unsafe { libc::geteuid() },
        0,
        "required explicit root profile; no skip"
    );
    for (name, run) in [
        ("five-verifier-entrypoints", verify_entries as fn()),
        ("durable-terminal", || product(Cut::Normal)),
        ("fork-original-owner", || product(Cut::Fork)),
        ("native-final-path-refusal", || product(Cut::NativePath)),
        ("terminal-path-refusal", || product(Cut::TerminalPath)),
        ("cancel-keeps-report-only-path", || {
            product(Cut::CancelActive)
        }),
        ("earlier-original-path-deadline", earlier_deadline),
        (
            "earlier-original-accepted-deadline",
            earlier_accepted_deadline,
        ),
        (
            "expired-original-accepted-no-packet",
            expired_accepted_no_packet,
        ),
        ("cross-uid-procfs-closed", cross_uid_refusal),
        ("explicit-wrong-pin", wrong_pin),
    ] {
        let before = inventory();
        run();
        assert_eq!(inventory(), before, "actual descriptor retirement");
        println!("PASS {name}; actual kernel/default procfs, source callback only");
    }
    println!(
        "11 actual privileged bridge groups; five individual verifier entrypoints; no installed/Servo qualification"
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
    if a.iter().any(|x| x == "--privileged-bridge-profile") {
        root_main();
        return;
    }
    let out = Command::new("/usr/bin/sudo")
        .args(["--non-interactive", "--"])
        .arg(std::env::current_exe().unwrap())
        .arg("--privileged-bridge-profile")
        .output()
        .expect("actual privileged source fixture required");
    std::io::stdout().write_all(&out.stdout).unwrap();
    std::io::stderr().write_all(&out.stderr).unwrap();
    assert!(out.status.success(), "no skip or fallback");
}
