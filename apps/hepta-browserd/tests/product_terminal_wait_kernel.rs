//! Three actual Linux processes and fixed live procfs measurements. Explicit
//! same-UID host policies are not installed service or native Servo evidence.
#![cfg(target_os = "linux")]
#![deny(unsafe_op_in_unsafe_fn)]
use hepta_agent_transport::{ClientConnection, PeerIdentity, PeerPolicy, RemoteTerminalState};
use hepta_browser_actor::{TaskFlowPrincipal, servo_runtime_pair};
use hepta_browser_codec::{
    BrowserOperation, BrowserRequest, JsonObject, decode_response, encode_request,
};
use hepta_browserd::{
    ProductControlMonitor, ProductControlMonitorOutcome, ProductDispatchError,
    ProductRequestCoordinator, RestartPolicy, RetainedProductConnection, RuntimeState,
};
use hepta_peer_attestation::{
    AttestedHandoffReceiver, AttestedHandoffSender, ControlOwnerError, ControlOwnerPolicy,
    PeerRuntimePolicy, ProcfsPeerAttestor,
};
use hepta_session_core::{
    JournalId, ManagedOpenPolicy, PrivacyClass, ReceiptEffectClass, ReceiptEvent, ReceiptJournal,
    ReceiptLifecycleState, ReceiptOutcome, ReceiptSource,
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
use std::sync::Arc;
use std::sync::atomic::{AtomicU64, Ordering};
use std::thread;
use std::time::{Duration, Instant};
const WAIT: Duration = Duration::from_secs(20);
static NEXT: AtomicU64 = AtomicU64::new(0);
fn poll(fd: RawFd, events: i16, stop: Instant) {
    loop {
        let millis = stop
            .saturating_duration_since(Instant::now())
            .as_millis()
            .min(10000) as i32;
        assert!(millis > 0, "owned fixture deadline");
        let mut p = libc::pollfd {
            fd,
            events,
            revents: 0,
        };
        let ready = unsafe { libc::poll(&mut p, 1, millis) };
        if ready > 0 {
            return;
        }
        assert!(
            ready >= 0 || std::io::Error::last_os_error().kind() == std::io::ErrorKind::Interrupted
        );
    }
}
fn seqpacket(path: &Path, listening: bool) -> OwnedFd {
    let fd = unsafe { libc::socket(libc::AF_UNIX, libc::SOCK_SEQPACKET | libc::SOCK_CLOEXEC, 0) };
    assert!(fd >= 0);
    let fd = unsafe { OwnedFd::from_raw_fd(fd) };
    let mut address: libc::sockaddr_un = unsafe { zeroed() };
    address.sun_family = libc::AF_UNIX as _;
    let bytes = path.as_os_str().as_encoded_bytes();
    assert!(bytes.len() < address.sun_path.len());
    for (i, value) in bytes.iter().enumerate() {
        address.sun_path[i] = *value as _;
    }
    let result = unsafe {
        if listening {
            libc::bind(
                fd.as_raw_fd(),
                std::ptr::addr_of!(address).cast(),
                size_of::<libc::sockaddr_un>() as _,
            )
        } else {
            libc::connect(
                fd.as_raw_fd(),
                std::ptr::addr_of!(address).cast(),
                size_of::<libc::sockaddr_un>() as _,
            )
        }
    };
    assert_eq!(result, 0);
    if listening {
        assert_eq!(unsafe { libc::listen(fd.as_raw_fd(), 2) }, 0);
    }
    fd
}
fn policy(fd: RawFd) -> ControlOwnerPolicy {
    let duplicate = unsafe { libc::fcntl(fd, libc::F_DUPFD_CLOEXEC, 3) };
    assert!(duplicate >= 0);
    let stream = unsafe { UnixStream::from_raw_fd(duplicate) };
    let peer = PeerIdentity::from_stream(&stream).unwrap();
    let actual = ProcfsPeerAttestor::default()
        .read_snapshot(peer.pid.unwrap())
        .unwrap();
    ControlOwnerPolicy::new(
        PeerPolicy::exact(peer),
        PeerRuntimePolicy::exact(&actual),
        actual.executable_sha256,
    )
    .unwrap()
}
fn input() -> u8 {
    poll(0, libc::POLLIN, Instant::now() + Duration::from_secs(30));
    let mut value = [0];
    std::io::stdin().read_exact(&mut value).unwrap();
    value[0]
}
struct ChildOwner {
    child: Child,
    owner_pid: u32,
    done: bool,
}
impl ChildOwner {
    fn spawn(mode: &str, paths: &[&Path]) -> Self {
        let mut command = Command::new(std::env::current_exe().unwrap());
        command.args(["--child", mode]);
        for p in paths {
            command.arg(p);
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
    fn line(&mut self, expected: &str) {
        let stop = Instant::now() + WAIT;
        let reader = self.child.stdout.as_mut().unwrap();
        let mut bytes = Vec::new();
        loop {
            poll(reader.as_raw_fd(), libc::POLLIN, stop);
            let mut byte = [0];
            assert_eq!(reader.read(&mut byte).unwrap(), 1);
            if byte[0] == b'\n' {
                break;
            }
            bytes.push(byte[0]);
            assert!(bytes.len() <= 128);
        }
        assert_eq!(std::str::from_utf8(&bytes).unwrap(), expected);
    }
    fn command(&mut self, value: u8) {
        self.child
            .stdin
            .as_mut()
            .unwrap()
            .write_all(&[value])
            .unwrap();
    }
    fn finish(&mut self) {
        self.command(b'x');
        let stop = Instant::now() + WAIT;
        loop {
            if let Some(status) = self.child.try_wait().unwrap() {
                self.done = true;
                assert!(status.success());
                break;
            }
            assert!(Instant::now() < stop);
            thread::sleep(Duration::from_millis(5));
        }
    }
    fn changed_image(&mut self) {
        self.command(b'e');
        let original = std::env::current_exe().unwrap();
        let stop = Instant::now() + WAIT;
        while fs::read_link(format!("/proc/{}/exe", self.child.id())).unwrap() == original {
            assert!(Instant::now() < stop);
            thread::sleep(Duration::from_millis(5));
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
struct Directory(PathBuf, u32);
impl Drop for Directory {
    fn drop(&mut self) {
        if self.1 == std::process::id() {
            let _ = fs::remove_dir_all(&self.0);
        }
    }
}

fn request() -> BrowserRequest {
    BrowserRequest {
        request_id: "terminal-request".into(),
        session_id: None,
        session_generation: None,
        deadline_unix_ms: None,
        operation: BrowserOperation::Health,
    }
}
fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}
fn custodian(cp: &Path, op: &Path, budget: Duration) {
    let original = UnixListener::bind(op).unwrap();
    let control = seqpacket(cp, false);
    println!("READY");
    poll(original.as_raw_fd(), libc::POLLIN, Instant::now() + WAIT);
    let (stream, _) = original.accept().unwrap();
    let allowed = policy(control.as_raw_fd());
    let mut sender =
        AttestedHandoffSender::from_accepted(control, stream, op, allowed, budget).unwrap();
    println!("ARMED");
    assert_eq!(input(), b's');
    let mut pending = Some(sender.send_retained().unwrap());
    assert_eq!(sender.send().err(), Some(ControlOwnerError::ChannelRetired));
    drop(sender);
    println!("SENT");
    let stop = Instant::now() + WAIT;
    let mut quiet = false;
    loop {
        assert!(Instant::now() < stop);
        let mut p = libc::pollfd {
            fd: 0,
            events: libc::POLLIN,
            revents: 0,
        };
        assert!(unsafe { libc::poll(&mut p, 1, 0) } >= 0);
        if p.revents != 0 {
            match input() {
                b'x' => return,
                b'c' => {
                    pending.as_mut().unwrap().request_cancel().unwrap();
                    println!("CANCEL");
                }
                b'd' => {
                    drop(pending.take());
                    println!("DROPPED");
                }
                b'z' => {
                    quiet = true;
                    println!("QUIET");
                }
                b'e' => {
                    let e = Command::new("/usr/bin/sleep").arg("30").exec();
                    panic!("exec: {e}");
                }
                _ => panic!("custodian command"),
            }
        }
        if let Some(owner) = pending.as_mut().filter(|_| !quiet) {
            match owner.poll_retirement() {
                Ok(None) => (),
                Ok(Some(report)) => {
                    println!(
                        "REPORT {:?} {} {}",
                        report.state(),
                        hex(&report.request_sha256()),
                        hex(&report.record_sha256())
                    );
                    assert!(owner.poll_retirement().is_err());
                    assert!(owner.request_cancel().is_err());
                    pending.take();
                }
                Err(_) => {
                    println!("REFUSED");
                    pending.take();
                }
            }
        }
        thread::sleep(Duration::from_millis(2));
    }
}
fn agent(op: &Path) {
    let mut original = Some(UnixStream::connect(op).unwrap());
    let mut connections = Vec::new();
    println!("CONNECTED");
    loop {
        match input() {
            b'x' => return,
            b'e' => {
                let e = Command::new("/usr/bin/sleep").arg("30").exec();
                panic!("exec: {e}");
            }
            kind @ (b'h' | b'l' | b'r') => {
                let stream = original.take().unwrap();
                let interrupt = stream.try_clone().unwrap();
                let peer = PeerIdentity::from_stream(&stream).unwrap();
                let mut client =
                    ClientConnection::connect(stream, PeerPolicy::exact(peer), WAIT).unwrap();
                let mut current = request();
                if kind == b'r' {
                    current.request_id = "refused-current".into();
                    current.session_id = Some("missing-session".into());
                    current.session_generation = Some(1);
                    current.operation = BrowserOperation::SessionSnapshot;
                }
                let sequence = client
                    .send_request(encode_request(&current).unwrap(), WAIT)
                    .unwrap();
                println!("REQUEST");
                if kind == b'l' {
                    interrupt.shutdown(std::net::Shutdown::Both).unwrap();
                    println!("LOST");
                } else {
                    match client.receive_response(sequence, WAIT) {
                        Ok(frame) => {
                            decode_response(&frame).unwrap();
                            println!("RESPONSE");
                        }
                        Err(_) => println!("NO_RESPONSE"),
                    }
                }
                connections.push(client);
            }
            _ => panic!("Agent command"),
        }
        std::hint::black_box(&connections);
    }
}
impl ChildOwner {
    fn report(&mut self) -> String {
        let stop = Instant::now() + WAIT;
        let reader = self.child.stdout.as_mut().unwrap();
        let mut bytes = Vec::new();
        loop {
            poll(reader.as_raw_fd(), libc::POLLIN, stop);
            let mut one = [0];
            assert_eq!(reader.read(&mut one).unwrap(), 1);
            if one[0] == b'\n' {
                break;
            }
            bytes.push(one[0]);
            assert!(bytes.len() < 256);
        }
        String::from_utf8(bytes).unwrap()
    }
}
struct Trio {
    directory: Directory,
    custodian: ChildOwner,
    agent: ChildOwner,
    receiver: AttestedHandoffReceiver,
    agent_policy: PeerRuntimePolicy,
    principal: TaskFlowPrincipal,
    pin: String,
}
impl Trio {
    fn new(budget: Duration) -> Self {
        Self::new_wait(budget, budget)
    }
    fn new_wait(budget: Duration, control_wait: Duration) -> Self {
        let root = std::env::temp_dir().join(format!(
            "g2wait-{}-{}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        fs::DirBuilder::new().mode(0o700).create(&root).unwrap();
        let directory = Directory(root.clone(), std::process::id());
        let cp = root.join("control.sock");
        let op = root.join("agent.sock");
        let listener = seqpacket(&cp, true);
        let millis = PathBuf::from(budget.as_millis().to_string());
        let mut custodian = ChildOwner::spawn("custodian", &[&cp, &op, &millis]);
        custodian.line("READY");
        poll(listener.as_raw_fd(), libc::POLLIN, Instant::now() + WAIT);
        let raw = unsafe {
            libc::accept4(
                listener.as_raw_fd(),
                std::ptr::null_mut(),
                std::ptr::null_mut(),
                libc::SOCK_CLOEXEC,
            )
        };
        assert!(raw >= 0);
        let control = unsafe { OwnedFd::from_raw_fd(raw) };
        let mut agent = ChildOwner::spawn("agent", &[&op]);
        agent.line("CONNECTED");
        assert_ne!(agent.child.id(), custodian.child.id());
        assert_ne!(agent.child.id(), std::process::id());
        assert_ne!(custodian.child.id(), std::process::id());
        let receiver =
            AttestedHandoffReceiver::from_control(control, policy(raw), &op, control_wait).unwrap();
        custodian.line("ARMED");
        let snapshot = ProcfsPeerAttestor::default()
            .read_snapshot(agent.child.id())
            .unwrap();
        // This test controller selects its own known test ELF. A peer's newly
        // observed image never supplies an automatic production approval.
        let pin = ProcfsPeerAttestor::default()
            .read_snapshot(std::process::id())
            .unwrap()
            .executable_sha256;
        assert_eq!(snapshot.executable_sha256, pin);
        let principal = TaskFlowPrincipal {
            principal_id: "kernel-terminal-fixture".into(),
            expected_uid: snapshot.uid,
            expected_gid: snapshot.gid,
            expected_systemd_unit: snapshot
                .systemd_unit
                .clone()
                .expect("actual host service fixture required, never synthetic unit"),
            expected_cgroup_v2_path: snapshot.cgroup_v2_path.clone(),
            expected_executable_sha256: pin.clone(),
        };
        Self {
            directory,
            custodian,
            agent,
            receiver,
            agent_policy: PeerRuntimePolicy::exact(&snapshot),
            principal,
            pin,
        }
    }
    fn accepted(&mut self) -> (RetainedProductConnection, ProductControlMonitor) {
        self.custodian.command(b's');
        let received = self.receiver.receive_retained_custodied().unwrap();
        self.custodian.line("SENT");
        assert!(self.receiver.receive_retained_custodied().is_err());
        RetainedProductConnection::from_control_retained_received(
            received,
            &self.agent_policy,
            &self.pin,
        )
        .unwrap()
    }
    fn finish(&mut self) {
        self.agent.finish();
        self.custodian.finish();
    }
}
#[derive(Clone, Copy, PartialEq, Eq)]
enum Fault {
    None,
    LostResponse,
    LostReport,
    TerminalStorage,
    CancelActive,
    CancelRead,
    MissingOwner,
    ExecOwner,
    Fork,
    RefusedCurrent,
}
fn seed_unrelated(journal: &mut ReceiptJournal) {
    for (index, lifecycle) in [
        ReceiptLifecycleState::Requested,
        ReceiptLifecycleState::Dispatched,
        ReceiptLifecycleState::Completed,
    ]
    .into_iter()
    .enumerate()
    {
        journal
            .append(ReceiptEvent {
                receipt_id: "unrelated-history".into(),
                plan_revision: "2026-08-29-d6".into(),
                image_id: "kernel-source-only".into(),
                servo_commit: "670ae8a70801b162e186f81cbb5bdd2d59c39108".into(),
                browserd_version: "source-fixture".into(),
                session_id: "prior-session".into(),
                session_generation: 1,
                document_generation: 1,
                semantic_snapshot_revision: 0,
                mutation_epoch: 0,
                source: ReceiptSource::Agent,
                operation: "health".into(),
                lifecycle,
                outcome: (lifecycle == ReceiptLifecycleState::Completed)
                    .then_some(ReceiptOutcome::Succeeded),
                effect_class: ReceiptEffectClass::Observation,
                privacy_class: PrivacyClass::Internal,
                request_sha256: [0x21; 32],
                response_sha256: (lifecycle == ReceiptLifecycleState::Completed)
                    .then_some([0x22; 32]),
                error_code: None,
                detail: None,
                monotonic_ms: index as u64 + 1,
                wall_clock_unix_ms: 100 + index as u64,
            })
            .unwrap();
    }
}
fn run(fault: Fault) {
    let mut trio = Trio::new(WAIT);
    let (connection, monitor) = trio.accepted();
    if fault == Fault::LostReport {
        trio.custodian.command(b'z');
        trio.custodian.line("QUIET");
    }
    let accepted_deadline = connection.deadline().unwrap();
    let (endpoint, mut owner) = servo_runtime_pair(Arc::new(|| {}));
    let path = trio.directory.0.join("receipts");
    let mut journal = ReceiptJournal::create_managed(&path, JournalId([0x77; 16]), 1).unwrap();
    if fault == Fault::RefusedCurrent {
        seed_unrelated(&mut journal);
    }
    if fault == Fault::Fork {
        let pid = unsafe { libc::fork() };
        assert!(pid >= 0);
        if pid == 0 {
            assert_eq!(
                connection.deadline().err(),
                Some(ProductDispatchError::PeerRefused)
            );
            assert_eq!(monitor.run().err(), Some(ProductDispatchError::PeerRefused));
            drop(connection);
            drop(journal);
            unsafe { libc::_exit(0) }
        }
        let mut status = 0;
        assert_eq!(unsafe { libc::waitpid(pid, &mut status, 0) }, pid);
        assert_eq!(status, 0);
        assert_eq!(connection.deadline().unwrap(), accepted_deadline);
    }
    let principal = trio.principal.clone();
    let monitor_worker = thread::spawn(move || monitor.run());
    let (ready_tx, ready_rx) = std::sync::mpsc::sync_channel(0);
    let worker = thread::spawn(move || {
        let mut coordinator = ProductRequestCoordinator::from_retained_connection(
            principal,
            &connection,
            endpoint,
            journal,
            "kernel-source-only".into(),
            RestartPolicy::new(3).unwrap(),
        )
        .unwrap();
        ready_tx.send(()).unwrap();
        let result = coordinator.serve_retained_connection(connection);
        (result, coordinator.state())
    });
    ready_rx.recv_timeout(WAIT).unwrap();
    if fault == Fault::CancelRead {
        trio.custodian.command(b'c');
        trio.custodian.line("CANCEL");
    } else if fault == Fault::MissingOwner {
        trio.custodian.command(b'd');
        trio.custodian.line("DROPPED");
    } else if fault == Fault::ExecOwner {
        trio.custodian.changed_image();
    } else {
        trio.agent.command(if fault == Fault::LostResponse {
            b'l'
        } else if fault == Fault::RefusedCurrent {
            b'r'
        } else {
            b'h'
        });
        trio.agent.line("REQUEST");
    }
    let stop = Instant::now() + WAIT;
    let mut commands = 0;
    while !worker.is_finished() {
        owner.pump_one();
        if let Some(command) = owner.take_command() {
            commands += 1;
            let (_, _, completion) = command.into_parts();
            if fault == Fault::TerminalStorage {
                let segment = path.join("segment-0000000000000001.journal");
                fs::rename(&segment, path.join("original-preserved.journal")).unwrap();
                fs::write(segment, b"foreign terminal path").unwrap();
            }
            if fault == Fault::CancelActive {
                trio.custodian.command(b'c');
                trio.custodian.line("CANCEL");
                let until = Instant::now() + Duration::from_secs(2);
                while completion.ensure_active().is_ok() {
                    assert!(Instant::now() < until);
                    thread::sleep(Duration::from_millis(1));
                }
                assert!(completion.ensure_current_peer().is_err());
                completion.complete_error(hepta_browser_actor::ServoRuntimeError::Cancelled);
            } else {
                completion.ensure_current_peer().unwrap();
                completion.complete_success(JsonObject::new(), None);
            }
        }
        assert!(Instant::now() < stop, "bounded new callback source corpus");
        thread::sleep(Duration::from_millis(1));
    }
    let (served, state) = worker.join().unwrap();
    let monitor_result = monitor_worker.join().unwrap();
    if matches!(
        fault,
        Fault::None | Fault::LostResponse | Fault::LostReport | Fault::Fork | Fault::CancelActive
    ) {
        let packet = if fault == Fault::LostReport {
            None
        } else {
            Some(trio.custodian.report())
        };
        assert_eq!(
            monitor_result,
            Ok(ProductControlMonitorOutcome::ReportEnqueued)
        );
        let mut reopened =
            ReceiptJournal::open_managed(&path, JournalId([0x77; 16]), ManagedOpenPolicy::STRICT)
                .unwrap();
        let report = reopened.inspect().unwrap();
        assert_eq!(report.records.len(), 3);
        let terminal = report.records.last().unwrap();
        assert!(terminal.event.lifecycle.is_terminal());
        let expected = if fault == Fault::CancelActive {
            RemoteTerminalState::Indeterminate
        } else {
            RemoteTerminalState::Completed
        };
        if let Some(packet) = packet {
            assert_eq!(
                packet,
                format!(
                    "REPORT {:?} {} {}",
                    expected,
                    hex(&terminal.event.request_sha256),
                    hex(&terminal.record_sha256)
                )
            );
        } else {
            let before = reopened.inspect().unwrap();
            trio.custodian.command(b'd');
            trio.custodian.line("DROPPED");
            trio.custodian.finish();
            let after = reopened.inspect().unwrap();
            assert_eq!(
                before.records, after.records,
                "lost report/peer exit never rewrites sealed terminal"
            );
        }
        assert_eq!(terminal.event.receipt_id, "terminal-request");
        assert_eq!(commands, 1);
        if fault == Fault::LostResponse {
            assert!(served.is_err());
            trio.agent.line("LOST");
        } else if fault == Fault::CancelActive {
            assert!(served.is_err());
            assert_eq!(state, RuntimeState::ReplayReconciliationRequired);
            trio.agent.line("NO_RESPONSE");
        } else {
            assert!(served.is_ok());
            assert_eq!(state, RuntimeState::Ready);
            trio.agent.line("RESPONSE");
        }
        drop(reopened);
    } else {
        if fault == Fault::RefusedCurrent {
            assert!(served.is_ok());
            assert_eq!(monitor_result, Ok(ProductControlMonitorOutcome::NoTerminal));
            trio.agent.line("RESPONSE");
            let mut existing = ReceiptJournal::open_managed(
                &path,
                JournalId([0x77; 16]),
                ManagedOpenPolicy::STRICT,
            )
            .unwrap();
            let records = existing.inspect().unwrap().records;
            assert_eq!(records.len(), 3);
            assert!(
                records
                    .iter()
                    .all(|r| r.event.receipt_id == "unrelated-history")
            );
        } else {
            assert!(served.is_err());
        }
        assert!(
            monitor_result.is_err()
                || monitor_result == Ok(ProductControlMonitorOutcome::NoTerminal)
        );
        if !matches!(fault, Fault::ExecOwner | Fault::MissingOwner) {
            trio.custodian.line("REFUSED");
        }
        if fault == Fault::TerminalStorage {
            assert_eq!(commands, 1);
            trio.agent.line("NO_RESPONSE");
        } else {
            assert_eq!(commands, 0);
        }
    }
    if matches!(fault, Fault::ExecOwner | Fault::LostReport) {
        trio.agent.finish();
    } else {
        trio.finish();
    }
}
fn inventory() -> Vec<(u32, String)> {
    let mut names: Vec<_> = fs::read_dir("/proc/self/fd")
        .unwrap()
        .map(|entry| {
            entry
                .unwrap()
                .file_name()
                .to_str()
                .unwrap()
                .parse::<u32>()
                .unwrap()
        })
        .collect();
    names.sort_unstable();
    names
        .into_iter()
        .filter_map(|fd| {
            fs::read_link(format!("/proc/self/fd/{fd}"))
                .ok()
                .map(|p| (fd, p.to_string_lossy().into_owned()))
        })
        .collect()
}
fn original_deadlines_never_renew() {
    for short_control in [false, true] {
        let mut trio = if short_control {
            Trio::new_wait(WAIT, Duration::from_secs(2))
        } else {
            Trio::new(Duration::from_secs(2))
        };
        let (connection, monitor) = trio.accepted();
        let original = connection.deadline().unwrap();
        let monitor_worker = thread::spawn(move || monitor.run());
        let start = Instant::now();
        while !monitor_worker.is_finished() {
            assert!(start.elapsed() < Duration::from_secs(3));
            thread::sleep(Duration::from_millis(1));
        }
        assert!(monitor_worker.join().unwrap().is_err());
        assert!(connection.deadline().is_err());
        if short_control {
            assert!(
                original > Instant::now(),
                "control wait cannot renew itself from longer accepted ceiling"
            );
        }
        drop(connection);
        trio.custodian.line("REFUSED");
        trio.finish();
    }
}
fn main() {
    let args: Vec<_> = std::env::args_os().collect();
    if args.get(1).is_some_and(|v| v == "--child") {
        match args[2].to_str().unwrap() {
            "custodian" => custodian(
                Path::new(&args[3]),
                Path::new(&args[4]),
                Duration::from_millis(args[5].to_str().unwrap().parse().unwrap()),
            ),
            "agent" => agent(Path::new(&args[3])),
            _ => panic!("child mode"),
        }
        return;
    }
    for (name, fault) in [
        ("durable-complete", Fault::None),
        ("lost-agent-response-known-terminal", Fault::LostResponse),
        (
            "lost-report-and-owner-exit-preserve-terminal",
            Fault::LostReport,
        ),
        ("terminal-storage-no-report", Fault::TerminalStorage),
        ("cancel-active", Fault::CancelActive),
        ("cancel-blocking-read", Fault::CancelRead),
        ("missing-owner", Fault::MissingOwner),
        ("exec-owner", Fault::ExecOwner),
        ("fork-before-channel-mutex", Fault::Fork),
        (
            "unrelated-terminal-cannot-ack-refused-current",
            Fault::RefusedCurrent,
        ),
    ] {
        let before = inventory();
        run(fault);
        assert_eq!(inventory(), before, "all true FD owners retire");
        println!("PASS kernel terminal source {name}");
    }
    let before = inventory();
    original_deadlines_never_renew();
    assert_eq!(inventory(), before);
    println!("PASS kernel terminal source original-accepted-and-control-deadlines");
    println!(
        "PASS 11 actual three-process terminal groups; controlled completion only, no Servo or installed claim"
    );
}
