//! Actual root-selected three-process default-proc corpus. Synthetic runtime
//! callbacks and direct remote transport reports do not qualify native effects.
#[path = "../../../experiments/servo-product-owner/src/approved_test_support.rs"]
mod support;
use hepta_agent_transport::{
    AcceptedStreamCustody, PeerPolicy, RootControlPathPolicy, RootPathControlConnection,
};
use hepta_agent_transport::{RemoteRetirementReport, RemoteTerminalState};
use hepta_browser_actor::{ServoRuntimeOwner, servo_runtime_pair};
use hepta_browser_codec::{BrowserOperation, BrowserRequest, JsonObject, decode_response};
use hepta_browserd::{ApprovedRetainedAdmission, ProductControlMonitorOutcome, RuntimeState};
use hepta_peer_attestation::{
    ApprovedAgentRequestBinding, ApprovedPolicyDocument, AttestedRetainedReceiver,
    ControlOwnerError, ControlRequestCustody,
};
use hepta_session_core::{JournalId, ReceiptJournal};
use std::io::Read;
use std::os::fd::AsRawFd;
use std::os::unix::net::UnixListener;
use std::os::unix::process::CommandExt;
use std::path::Path;
use std::process::Command;
use std::sync::{Arc, mpsc};
use std::thread;
use std::time::{Duration, Instant};

fn fixture_input() -> u8 {
    let mut poll = libc::pollfd {
        fd: 0,
        events: libc::POLLIN,
        revents: 0,
    };
    assert!(unsafe { libc::poll(&mut poll, 1, 20000) } > 0);
    let mut byte = [0];
    std::io::stdin().read_exact(&mut byte).unwrap();
    byte[0]
}
fn exec_custodian(cp: &Path, op: &Path, config: &Path, cancel: bool) {
    let original = UnixListener::bind(op).unwrap();
    let deadline = Instant::now() + support::WAIT;
    let path = RootControlPathPolicy::new(cp, 65534, 0o750, 65534, 0o660).unwrap();
    let connection = RootPathControlConnection::connect_before(
        &path,
        PeerPolicy {
            expected_uid: 0,
            expected_gid: Some(0),
            expected_pid: Some(unsafe { libc::getppid() } as u32),
        },
        deadline,
    )
    .unwrap();
    println!("PATH_CURRENT");
    let mut readable = libc::pollfd {
        fd: original.as_raw_fd(),
        events: libc::POLLIN,
        revents: 0,
    };
    assert!(unsafe { libc::poll(&mut readable, 1, 20000) } > 0);
    let (accepted, _) = original.accept().unwrap();
    let accepted =
        AcceptedStreamCustody::capture_before(accepted, op, Instant::now() + support::WAIT)
            .unwrap();
    let document = ApprovedPolicyDocument::open_root_owned_before(config, deadline).unwrap();
    let mut sender = document
        .select_control()
        .unwrap()
        .bind_sender(connection, accepted)
        .unwrap();
    println!("ARMED");
    assert_eq!(fixture_input(), b's');
    let mut pending = sender.send_retained().unwrap();
    println!("SENT");
    assert_eq!(fixture_input(), b'q');
    if cancel {
        pending.request_cancel().unwrap();
    }
    // Test-only exec stimulus: retain this actual original Control socket over
    // exec, allowing the new idle contract and true full boundary to be tested.
    let mut changed = 0;
    let mut original_object = None;
    for entry in std::fs::read_dir("/proc/self/fd").unwrap() {
        let fd: i32 = entry
            .unwrap()
            .file_name()
            .to_str()
            .unwrap()
            .parse()
            .unwrap();
        let mut kind = 0i32;
        let mut size = std::mem::size_of::<i32>() as libc::socklen_t;
        if unsafe {
            libc::getsockopt(
                fd,
                libc::SOL_SOCKET,
                libc::SO_TYPE,
                std::ptr::addr_of_mut!(kind).cast(),
                &mut size,
            )
        } == 0
            && kind == libc::SOCK_SEQPACKET
        {
            let mut stat = std::mem::MaybeUninit::<libc::stat>::uninit();
            assert_eq!(unsafe { libc::fstat(fd, stat.as_mut_ptr()) }, 0);
            let stat = unsafe { stat.assume_init() };
            let mut cookie = 0u64;
            let mut cookie_size = std::mem::size_of::<u64>() as libc::socklen_t;
            assert_eq!(
                unsafe {
                    libc::getsockopt(
                        fd,
                        libc::SOL_SOCKET,
                        libc::SO_COOKIE,
                        std::ptr::addr_of_mut!(cookie).cast(),
                        &mut cookie_size,
                    )
                },
                0
            );
            assert_eq!(cookie_size as usize, std::mem::size_of::<u64>());
            let identity = (stat.st_dev, stat.st_ino, cookie);
            if let Some(original) = original_object {
                assert_eq!(identity, original);
            } else {
                original_object = Some(identity);
            }
            let flags = unsafe { libc::fcntl(fd, libc::F_GETFD) };
            assert!(flags >= 0);
            assert_eq!(
                unsafe { libc::fcntl(fd, libc::F_SETFD, flags & !libc::FD_CLOEXEC) },
                0
            );
            changed += 1;
        }
    }
    // RootPathControlConnection retains one duplicate of this same original
    // endpoint for pathname custody; both real FDs must refer to one object.
    assert_eq!(changed, 2);
    println!("EXECING");
    panic!(
        "exec failed: {}",
        Command::new("/usr/bin/sleep").arg("10").exec()
    );
}
fn actual_exec_boundary(cancel: bool) {
    let mode = if cancel {
        "readiness-exec-cancel"
    } else {
        "readiness-exec-idle"
    };
    let mut trio = support::Trio::new_mode(support::WAIT, mode, support::WAIT);
    let (mut retained, _custody, _binding) = retained(&mut trio);
    assert!(!retained.poll_cancel_when_readable().unwrap());
    trio.custodian.command(b'q');
    trio.custodian.expect("EXECING");
    let stop = Instant::now() + Duration::from_secs(2);
    let executable = format!("/proc/{}/exe", trio.custodian.child.id());
    while std::fs::read_link(&executable)
        .unwrap()
        .file_name()
        .unwrap()
        != "sleep"
    {
        assert!(Instant::now() < stop);
        thread::sleep(Duration::from_millis(1));
    }
    if cancel {
        assert_eq!(
            retained.poll_cancel_when_readable(),
            Err(ControlOwnerError::PeerRefused)
        );
    } else {
        assert!(
            !retained.poll_cancel_when_readable().unwrap(),
            "idle is no full identity assertion"
        );
        assert_eq!(
            retained.send_remote_report(report()),
            Err(ControlOwnerError::PeerRefused)
        );
    }
    trio.custodian.child.kill().unwrap();
    trio.custodian.child.wait().unwrap();
    trio.agent.finish();
}
fn exec_ready_full_refuses() {
    actual_exec_boundary(true);
}
fn exec_idle_terminal_full_refuses() {
    actual_exec_boundary(false);
}

fn retained(
    trio: &mut support::Trio,
) -> (
    AttestedRetainedReceiver,
    ControlRequestCustody,
    ApprovedAgentRequestBinding,
) {
    let received = trio.receive();
    trio.document
        .select_agent()
        .unwrap()
        .admit_retained(received)
        .unwrap()
        .consume_with_request_binding(
            |stream, _deadline, custody, retained, _attested, _principal, binding| {
                drop(stream);
                (retained, custody, binding)
            },
        )
        .unwrap()
}
fn report() -> RemoteRetirementReport {
    RemoteRetirementReport::new(RemoteTerminalState::Completed, [4; 32], [5; 32]).unwrap()
}
fn idle_and_revoked_action_reporting() {
    let mut trio = support::Trio::new(support::WAIT);
    let (mut retained, custody, _binding) = retained(&mut trio);
    let old_action = custody.verifier().unwrap();
    let original = retained.ensure_current().unwrap();
    for _ in 0..25 {
        assert!(!retained.poll_cancel_when_readable().unwrap());
    }
    assert_eq!(retained.ensure_current().unwrap(), original);
    custody.revoke().unwrap();
    assert!(old_action.verify_current().is_err());
    assert!(!retained.poll_cancel_when_readable().unwrap());
    retained.send_remote_report(report()).unwrap();
    assert!(trio.custodian.line().starts_with("REPORT Completed "));
    assert!(old_action.verify_current().is_err());
    assert!(retained.send_remote_report(report()).is_err());
    trio.finish();
}
fn actual_cancel_retires_action_reporting_owner_survives() {
    let mut trio = support::Trio::new(support::WAIT);
    let (mut retained, custody, _binding) = retained(&mut trio);
    let action = custody.verifier().unwrap();
    assert!(!retained.poll_cancel_when_readable().unwrap());
    trio.custodian.command(b'c');
    trio.custodian.expect("CANCELLED");
    let stop = retained.ensure_current().unwrap();
    loop {
        if retained.poll_cancel_when_readable().unwrap() {
            break;
        }
        assert!(Instant::now() < stop);
        thread::sleep(Duration::from_millis(1));
    }
    assert!(action.verify_current().is_err());
    retained.send_remote_report(report()).unwrap();
    assert!(trio.custodian.line().starts_with("REPORT Completed "));
    trio.finish();
}
fn root_drift_sticky_refusal() {
    let mut trio = support::Trio::new(support::WAIT);
    let (mut retained, custody, _binding) = retained(&mut trio);
    let action = custody.verifier().unwrap();
    assert!(!retained.poll_cancel_when_readable().unwrap());
    trio.drift();
    assert_eq!(
        retained.poll_cancel_when_readable(),
        Err(ControlOwnerError::PeerRefused)
    );
    trio.restore();
    assert!(retained.poll_cancel_when_readable().is_err());
    assert!(action.verify_current().is_err());
    assert!(retained.send_remote_report(report()).is_err());
    trio.finish();
}
fn actual_control_death_refuses() {
    let mut trio = support::Trio::new(support::WAIT);
    let (mut retained, custody, _binding) = retained(&mut trio);
    let action = custody.verifier().unwrap();
    assert!(!retained.poll_cancel_when_readable().unwrap());
    trio.custodian.child.kill().unwrap();
    trio.custodian.child.wait().unwrap();
    assert_eq!(
        retained.poll_cancel_when_readable(),
        Err(ControlOwnerError::PeerRefused)
    );
    assert!(action.verify_current().is_err());
    assert!(retained.send_remote_report(report()).is_err());
    trio.agent.finish();
}
fn actual_fork_parent_report_survives() {
    let mut trio = support::Trio::new(support::WAIT);
    let (mut retained, _custody, _binding) = retained(&mut trio);
    let child = unsafe { libc::fork() };
    assert!(child >= 0);
    if child == 0 {
        let denied = retained.poll_cancel_when_readable() == Err(ControlOwnerError::ProcessChanged);
        drop(retained);
        unsafe { libc::_exit(if denied { 0 } else { 7 }) }
    }
    let mut status = 0;
    assert_eq!(unsafe { libc::waitpid(child, &mut status, 0) }, child);
    assert_eq!(status, 0);
    assert!(!retained.poll_cancel_when_readable().unwrap());
    retained.send_remote_report(report()).unwrap();
    assert!(trio.custodian.line().starts_with("REPORT Completed "));
    trio.finish();
}
fn original_expiry_no_renewal() {
    let mut trio = support::Trio::new(support::WAIT);
    let (mut retained, custody, _binding) = retained(&mut trio);
    let action = custody.verifier().unwrap();
    let original = retained.ensure_current().unwrap();
    assert!(original <= trio.deadline);
    assert!(!retained.poll_cancel_when_readable().unwrap());
    thread::sleep(original.saturating_duration_since(Instant::now()) + Duration::from_millis(2));
    assert_eq!(
        retained.poll_cancel_when_readable(),
        Err(ControlOwnerError::DeadlineExceeded)
    );
    assert!(action.verify_current().is_err());
    assert!(retained.send_remote_report(report()).is_err());
    trio.finish();
}
fn collect(
    owner: &mut ServoRuntimeOwner,
    receiver: &mpsc::Receiver<hepta_browserd::ApprovedRetainedObservation>,
    ceiling: Instant,
) -> hepta_browserd::ApprovedRetainedObservation {
    loop {
        if let Ok(value) = receiver.try_recv() {
            return value;
        }
        owner.pump_one();
        if let Some(command) = owner.take_command() {
            let (_, _, completion) = command.into_parts();
            completion.ensure_current_peer().unwrap();
            completion.complete_success(JsonObject::new(), None);
        }
        assert!(
            Instant::now() < ceiling,
            "original accepted ceiling, no renewal"
        );
        thread::sleep(Duration::from_millis(1));
    }
}
fn actual_product_journal_terminal_on_idle_control() {
    let mut trio = support::Trio::new(support::WAIT);
    let received = trio.receive();
    let admission =
        ApprovedRetainedAdmission::from_received(received, trio.document.select_agent().unwrap())
            .unwrap();
    let ceiling = admission.deadline().unwrap();
    let journal = ReceiptJournal::create_managed(
        trio.fixture.root.join("readiness-receipts"),
        JournalId([0x71; 16]),
        1,
    )
    .unwrap();
    let (endpoint, mut owner) = servo_runtime_pair(Arc::new(|| {}));
    let (sender, receiver) = mpsc::sync_channel(1);
    let worker = thread::spawn(move || {
        let mut coordinator = admission
            .coordinator(endpoint, journal, "readiness-host-source".into())
            .unwrap();
        sender
            .send(admission.serve(&mut coordinator).unwrap())
            .unwrap();
    });
    trio.request(&BrowserRequest {
        request_id: "readiness-health".into(),
        session_id: None,
        session_generation: None,
        deadline_unix_ms: None,
        operation: BrowserOperation::Health,
    });
    let observation = collect(&mut owner, &receiver, ceiling);
    assert!(observation.service().as_ref().unwrap().response_committed);
    assert_eq!(
        observation.report(),
        &Ok(ProductControlMonitorOutcome::ReportEnqueued)
    );
    assert_eq!(observation.runtime_state(), RuntimeState::Ready);
    trio.agent.expect("REQUEST");
    let wire = trio.agent.line();
    assert!(
        decode_response(wire.strip_prefix("RESPONSE ").unwrap().as_bytes())
            .unwrap()
            .value
            .outcome
            .is_ok()
    );
    assert!(trio.custodian.line().starts_with("REPORT Completed "));
    worker.join().unwrap();
    trio.finish();
}
// Sender-oriented cases use a real opposite Control receiver, not the old
// receiver-oriented custodian process. Each case starts in a fresh exec.
fn sender_require_single_thread() {
    let mut tasks = 0;
    for task in std::fs::read_dir("/proc/self/task").unwrap() {
        task.unwrap();
        tasks += 1;
    }
    assert_eq!(tasks, 1, "fresh sender case must have one task before fork");
}

struct SenderControlProcess {
    pid: libc::pid_t,
    owner_pid: u32,
    channel: std::os::unix::net::UnixStream,
    reaped: bool,
}
impl SenderControlProcess {
    fn assert_running(&mut self) {
        assert_eq!(self.owner_pid, std::process::id());
        assert!(!self.reaped);
        let mut status = 0;
        let result = unsafe { libc::waitpid(self.pid, &mut status, libc::WNOHANG) };
        if result == self.pid
            || (result < 0 && std::io::Error::last_os_error().raw_os_error() == Some(libc::ECHILD))
        {
            // Consume a reaped/lost identity before failing; never signal a
            // now-reusable numeric PID from Drop.
            self.reaped = true;
        }
        assert_eq!(result, 0, "original Control peer exited before liveness proof");
    }
    fn expect(&mut self, expected: u8) {
        let mut byte = [0];
        self.channel.read_exact(&mut byte).unwrap();
        assert_eq!(byte[0], expected);
    }
    fn command(&mut self, command: u8, expected: u8) {
        use std::io::Write;
        self.channel.write_all(&[command]).unwrap();
        self.expect(expected);
    }
    fn wait(&mut self, success: bool) {
        assert_eq!(self.owner_pid, std::process::id());
        assert!(!self.reaped);
        let stop = Instant::now() + support::WAIT;
        loop {
            let mut status = 0;
            let result = unsafe { libc::waitpid(self.pid, &mut status, libc::WNOHANG) };
            assert!(result >= 0);
            if result == self.pid {
                self.reaped = true;
                if success { assert_eq!(status, 0); }
                return;
            }
            assert!(Instant::now() < stop, "owned Control receiver did not exit");
            thread::sleep(Duration::from_millis(1));
        }
    }
    fn kill_owned(&mut self) {
        assert_eq!(self.owner_pid, std::process::id());
        assert!(!self.reaped, "never signal a reused numeric PID");
        assert_eq!(unsafe { libc::kill(self.pid, libc::SIGKILL) }, 0);
        self.wait(false);
    }
    fn finish(&mut self) {
        self.command(b'x', b'X');
        self.wait(true);
    }
}
impl Drop for SenderControlProcess {
    fn drop(&mut self) {
        if self.owner_pid == std::process::id() && !self.reaped {
            self.kill_owned();
        }
    }
}

fn sender_control_fd() -> i32 {
    let mut selected = None;
    let mut identity = None;
    for (fd, _) in support::inventory() {
        let fd = fd as i32;
        let mut kind = 0i32;
        let mut length = std::mem::size_of::<i32>() as libc::socklen_t;
        if unsafe {
            libc::getsockopt(fd, libc::SOL_SOCKET, libc::SO_TYPE,
                std::ptr::addr_of_mut!(kind).cast(), &mut length)
        } != 0 || kind != libc::SOCK_SEQPACKET {
            continue;
        }
        let mut address = std::mem::MaybeUninit::<libc::sockaddr_un>::uninit();
        let mut address_length = std::mem::size_of::<libc::sockaddr_un>() as libc::socklen_t;
        if unsafe { libc::getpeername(fd, address.as_mut_ptr().cast(), &mut address_length) } != 0 {
            continue;
        }
        let mut cookie = 0u64;
        let mut cookie_length = std::mem::size_of::<u64>() as libc::socklen_t;
        assert_eq!(unsafe {
            libc::getsockopt(fd, libc::SOL_SOCKET, libc::SO_COOKIE,
                std::ptr::addr_of_mut!(cookie).cast(), &mut cookie_length)
        }, 0);
        assert_eq!(cookie_length as usize, std::mem::size_of::<u64>());
        let mut metadata = std::mem::MaybeUninit::<libc::stat>::uninit();
        assert_eq!(unsafe { libc::fstat(fd, metadata.as_mut_ptr()) }, 0);
        let metadata = unsafe { metadata.assume_init() };
        let current = (metadata.st_dev, metadata.st_ino, cookie);
        if let Some(original) = identity {
            assert_eq!(current, original, "one original connected Control object");
        } else {
            identity = Some(current);
            selected = Some(fd);
        }
    }
    selected.unwrap()
}

fn sender_receiver_child(
    fixture: &support::Fixture,
    mut commands: std::os::unix::net::UnixStream,
    sender_pid: u32,
    deadline: Instant,
) {
    use std::io::Write;
    use std::os::fd::{FromRawFd, OwnedFd};
    let mut listener = fixture.listener();
    commands.write_all(b'L').unwrap();
    let connection = listener.accept_before(PeerPolicy {
        expected_uid: 0, expected_gid: Some(0), expected_pid: Some(sender_pid),
    }, deadline).unwrap();
    drop(listener);
    let document = fixture.document(deadline);
    let mut receiver = document.select_control().unwrap()
        .bind_receiver(connection, fixture.agent_path()).unwrap();
    commands.write_all(b'B').unwrap();
    let mut start = [0];
    commands.read_exact(&mut start).unwrap();
    if start[0] == b'x' {
        commands.write_all(b'X').unwrap();
        return;
    }
    assert_eq!(start[0], b's');
    let received = receiver.receive_retained_custodied().unwrap();
    drop(receiver);
    let (retained, custody) = document.select_agent().unwrap().admit_retained(received).unwrap()
        .consume_with_request_binding(|stream, _deadline, custody, retained, _peer, _principal, _binding| {
            drop(stream);
            (retained, custody)
        }).unwrap();
    let mut action = Some(custody.verifier().unwrap());
    assert!(action.as_ref().unwrap().verify_current().is_ok());
    let mut custody = Some(custody);
    let mut retained = Some(retained);
    commands.write_all(b'A').unwrap();
    loop {
        let mut command = [0];
        commands.read_exact(&mut command).unwrap();
        match command[0] {
            b'x' => { commands.write_all(b'X').unwrap(); return; },
            b'r' => {
                retained.as_mut().unwrap().send_remote_report(report()).unwrap();
                commands.write_all(b'R').unwrap();
            },
            b'c' => {
                assert!(action.as_ref().unwrap().verify_current().is_ok());
                while !retained.as_mut().unwrap().poll_cancel_when_readable().unwrap() {
                    assert!(Instant::now() < deadline);
                    thread::sleep(Duration::from_millis(1));
                }
                assert!(action.as_ref().unwrap().verify_current().is_err());
                retained.as_mut().unwrap().send_remote_report(report()).unwrap();
                commands.write_all(b'C').unwrap();
            },
            b'm' => {
                let bytes = [0x7fu8];
                assert_eq!(unsafe {
                    libc::send(sender_control_fd(), bytes.as_ptr().cast(), bytes.len(), libc::MSG_NOSIGNAL)
                }, bytes.len() as isize);
                commands.write_all(b'M').unwrap();
            },
            b'h' => {
                drop(retained.take());
                drop(custody.take());
                drop(action.take());
                commands.write_all(b'H').unwrap();
            },
            b'e' | b'q' => {
                // Only a same-object duplicate survives exec; do not alter
                // the original retained owner's CLOEXEC flags.
                let fd = unsafe { libc::fcntl(sender_control_fd(), libc::F_DUPFD_CLOEXEC, 3) };
                assert!(fd >= 0);
                let held = unsafe { OwnedFd::from_raw_fd(fd) };
                let flags = unsafe { libc::fcntl(held.as_raw_fd(), libc::F_GETFD) };
                assert!(flags >= 0);
                assert_eq!(unsafe { libc::fcntl(held.as_raw_fd(), libc::F_SETFD, flags & !libc::FD_CLOEXEC) }, 0);
                if command[0] == b'q' {
                    retained.as_mut().unwrap().send_remote_report(report()).unwrap();
                }
                commands.write_all(b'E').unwrap();
                panic!("owned Control exec failed: {}", Command::new("/usr/bin/sleep").arg("10").exec());
            },
            _ => panic!("unknown owned receiver command"),
        }
    }
}

struct SenderHostFixture {
    pending: hepta_peer_attestation::AttestedPendingHandoff,
    control: SenderControlProcess,
    agent: support::ChildOwner,
    fixture: support::Fixture,
    deadline: Instant,
}
impl SenderHostFixture {
    fn new(outer_wait: Duration, accepted_wait: Duration) -> Self {
        Self::setup(outer_wait, accepted_wait, false).unwrap()
    }
    fn setup(outer_wait: Duration, accepted_wait: Duration, unapproved: bool) -> Option<Self> {
        use std::io::Write;
        use std::os::unix::net::UnixStream;
        assert!(outer_wait <= support::WAIT && accepted_wait <= support::WAIT);
        let started = Instant::now();
        let control_deadline = started + support::WAIT;
        let outer_deadline = started + outer_wait;
        let accepted_deadline = started + accepted_wait;
        let fixture = support::Fixture::new();
        let original = UnixListener::bind(fixture.agent_path()).unwrap();
        let (commands, child_commands) = UnixStream::pair().unwrap();
        for channel in [&commands, &child_commands] {
            channel.set_read_timeout(Some(support::WAIT)).unwrap();
            channel.set_write_timeout(Some(support::WAIT)).unwrap();
        }
        let creator = std::process::id();
        sender_require_single_thread();
        let pid = unsafe { libc::fork() };
        assert!(pid >= 0);
        if pid == 0 {
            drop(commands);
            drop(original);
            let result = std::panic::catch_unwind(|| {
                sender_receiver_child(&fixture, child_commands, creator, control_deadline);
            });
            unsafe { libc::_exit(if result.is_ok() { 0 } else { 9 }) }
        }
        drop(child_commands);
        let mut control = SenderControlProcess { pid, owner_pid: creator, channel: commands, reaped: false };
        control.expect(b'L');
        let path = RootControlPathPolicy::new(&fixture.root.join("control.sock"), 65534, 0o750, 65534, 0o660).unwrap();
        let connection = RootPathControlConnection::connect_before(&path, PeerPolicy {
            expected_uid: 0, expected_gid: Some(0), expected_pid: Some(pid as u32),
        }, control_deadline).unwrap();
        let mut agent = support::ChildOwner::spawn(&fixture, "agent", fixture.agent_path(), false);
        agent.expect("CONNECTED");
        let mut poll = libc::pollfd { fd: original.as_raw_fd(), events: libc::POLLIN, revents: 0 };
        let remaining = accepted_deadline.saturating_duration_since(Instant::now()).as_millis();
        assert!(remaining > 0 && remaining <= 20000);
        assert!(unsafe { libc::poll(&mut poll, 1, remaining as i32) } > 0);
        let (accepted, _) = original.accept().unwrap();
        drop(original);
        let accepted = AcceptedStreamCustody::capture_before(accepted, fixture.agent_path(), accepted_deadline).unwrap();
        let document = if unapproved {
            let path = fixture.root.join("sender-denied-policy");
            std::fs::copy(&fixture.config, &path).unwrap();
            let text = std::fs::read_to_string(&path).unwrap();
            let changed: String = text.lines().map(|line| {
                if line.starts_with("control.elf_sha256=") {
                    format!("control.elf_sha256={}\n", "0".repeat(64))
                } else { format!("{line}\n") }
            }).collect();
            std::fs::write(&path, changed).unwrap();
            ApprovedPolicyDocument::open_root_owned_before(&path, outer_deadline).unwrap()
        } else { fixture.document(outer_deadline) };
        control.expect(b'B');
        let sender = document.select_control().unwrap().bind_sender(connection, accepted);
        if unapproved {
            assert_eq!(sender.err(), Some(hepta_peer_attestation::ApprovedPolicyError::PeerRefused));
            control.finish();
            agent.finish();
            return None;
        }
        let mut sender = sender.unwrap();
        control.channel.write_all(b"s").unwrap();
        let mut pending = sender.send_retained().unwrap();
        assert!(sender.send_retained().is_err());
        drop(sender);
        control.expect(b'A');
        let deadline = pending.ensure_current().unwrap();
        assert!(deadline <= outer_deadline.min(accepted_deadline));
        assert!(deadline > Instant::now());
        assert!(pending.poll_retirement_when_readable().unwrap().is_none());
        Some(Self { pending, control, agent, fixture, deadline })
    }
    fn ready_report_once(&mut self) {
        let value = self.pending.poll_retirement_when_readable().unwrap().unwrap();
        assert_eq!(value.state(), RemoteTerminalState::Completed);
        assert_eq!(value.request_sha256(), [4; 32]);
        assert_eq!(value.record_sha256(), [5; 32]);
        assert_eq!(self.pending.poll_retirement_when_readable().err(), Some(ControlOwnerError::ChannelRetired));
        assert!(self.pending.request_cancel().is_err());
    }
    fn finish(&mut self) {
        if !self.control.reaped { self.control.finish(); }
        self.agent.finish();
    }
}

fn sender_default_proc_idle_report_once() {
    let mut f = SenderHostFixture::new(support::WAIT, support::WAIT);
    for _ in 0..25 { assert!(f.pending.poll_retirement_when_readable().unwrap().is_none()); }
    assert_eq!(f.pending.ensure_current().unwrap(), f.deadline);
    f.control.command(b'r', b'R');
    f.ready_report_once();
    f.finish();
}
fn sender_unapproved_construction_has_no_pending_owner() {
    assert!(SenderHostFixture::setup(support::WAIT, support::WAIT, true).is_none());
}
fn sender_root_path_restore_stays_retired() {
    let mut f = SenderHostFixture::new(support::WAIT, support::WAIT);
    let original = f.fixture.root.join("control.sock");
    let held = f.fixture.root.join("held-control.sock");
    std::fs::rename(&original, &held).unwrap();
    assert_eq!(f.pending.poll_retirement_when_readable().err(), Some(ControlOwnerError::PeerRefused));
    std::fs::rename(&held, &original).unwrap();
    assert_eq!(f.pending.poll_retirement_when_readable().err(), Some(ControlOwnerError::ChannelRetired));
    f.finish();
}
fn sender_whole_policy_restore_stays_retired() {
    let mut f = SenderHostFixture::new(support::WAIT, support::WAIT);
    f.fixture.rewrite("agent.principal_id", "changed-agent");
    assert_eq!(f.pending.poll_retirement_when_readable().err(), Some(ControlOwnerError::PeerRefused));
    f.fixture.rewrite("agent.principal_id", "source-agent");
    assert_eq!(f.pending.poll_retirement_when_readable().err(), Some(ControlOwnerError::ChannelRetired));
    f.finish();
}
fn sender_actual_control_pidfd_death_refuses() {
    let mut f = SenderHostFixture::new(support::WAIT, support::WAIT);
    f.control.kill_owned();
    assert_eq!(f.pending.poll_retirement_when_readable().err(), Some(ControlOwnerError::PeerRefused));
    assert_eq!(f.pending.poll_retirement_when_readable().err(), Some(ControlOwnerError::ChannelRetired));
    f.finish();
}
fn sender_actual_control_exec_boundary(ready: bool) {
    let mut f = SenderHostFixture::new(support::WAIT, support::WAIT);
    f.control.command(if ready { b'q' } else { b'e' }, b'E');
    let stop = Instant::now() + Duration::from_secs(2);
    let executable = format!("/proc/{}/exe", f.control.pid);
    while std::fs::read_link(&executable).unwrap().file_name().unwrap() != "sleep" {
        assert!(Instant::now() < stop);
        thread::sleep(Duration::from_millis(1));
    }
    if ready {
        assert_eq!(f.pending.poll_retirement_when_readable().err(), Some(ControlOwnerError::PeerRefused));
    } else {
        assert!(f.pending.poll_retirement_when_readable().unwrap().is_none(), "idle is not executable attestation");
        assert_eq!(f.pending.poll_retirement().err(), Some(ControlOwnerError::PeerRefused));
    }
    f.control.assert_running();
    assert_eq!(std::fs::read_link(&executable).unwrap().file_name().unwrap(), "sleep");
    assert_eq!(f.pending.poll_retirement_when_readable().err(), Some(ControlOwnerError::ChannelRetired));
    f.control.kill_owned();
    f.finish();
}
fn sender_actual_control_exec_idle_full_refuses() { sender_actual_control_exec_boundary(false); }
fn sender_actual_control_exec_ready_full_refuses() { sender_actual_control_exec_boundary(true); }
fn sender_actual_fork_parent_report_survives() {
    let mut f = SenderHostFixture::new(support::WAIT, support::WAIT);
    sender_require_single_thread();
    let pid = unsafe { libc::fork() };
    assert!(pid >= 0);
    if pid == 0 {
        let denied = f.pending.poll_retirement_when_readable().err() == Some(ControlOwnerError::ProcessChanged);
        drop(f.pending);
        unsafe { libc::_exit(if denied { 0 } else { 7 }) }
    }
    let mut status = 0;
    assert_eq!(unsafe { libc::waitpid(pid, &mut status, 0) }, pid);
    assert_eq!(status, 0);
    assert!(f.pending.poll_retirement_when_readable().unwrap().is_none());
    f.control.command(b'r', b'R');
    f.ready_report_once();
    f.finish();
}
fn sender_original_ceiling(outer_first: bool) {
    let shorter = support::WAIT / 2;
    let mut f = SenderHostFixture::new(if outer_first { shorter } else { support::WAIT },
        if outer_first { support::WAIT } else { shorter });
    thread::sleep(f.deadline.saturating_duration_since(Instant::now()) + Duration::from_millis(2));
    assert_eq!(f.pending.poll_retirement_when_readable().err(), Some(ControlOwnerError::DeadlineExceeded));
    assert!(f.pending.ensure_current().is_err());
    assert!(f.pending.request_cancel().is_err());
    f.finish();
}
fn sender_outer_ceiling_never_renews() { sender_original_ceiling(true); }
fn sender_accepted_ceiling_never_renews() { sender_original_ceiling(false); }
fn sender_cancel_keeps_original_report_once() {
    let mut f = SenderHostFixture::new(support::WAIT, support::WAIT);
    f.pending.request_cancel().unwrap();
    f.control.command(b'c', b'C');
    f.ready_report_once();
    f.finish();
}
fn sender_malformed_ready_is_sticky() {
    let mut f = SenderHostFixture::new(support::WAIT, support::WAIT);
    f.control.command(b'm', b'M');
    assert_eq!(f.pending.poll_retirement_when_readable().err(), Some(ControlOwnerError::HandoffRefused));
    assert_eq!(f.pending.poll_retirement_when_readable().err(), Some(ControlOwnerError::ChannelRetired));
    f.finish();
}
fn sender_hup_with_live_peer_is_sticky() {
    let mut f = SenderHostFixture::new(support::WAIT, support::WAIT);
    f.control.command(b'h', b'H');
    assert_eq!(unsafe { libc::kill(f.control.pid, 0) }, 0);
    assert_eq!(f.pending.poll_retirement_when_readable().err(), Some(ControlOwnerError::HandoffRefused));
    assert_eq!(f.pending.poll_retirement_when_readable().err(), Some(ControlOwnerError::ChannelRetired));
    f.finish();
}

fn sender_host_cases() -> [(&'static str, fn()); 13] {
    [
        ("sender-default-proc-idle-report-once", sender_default_proc_idle_report_once),
        ("sender-unapproved-construction-no-pending-owner", sender_unapproved_construction_has_no_pending_owner),
        ("sender-root-path-restore-still-retired", sender_root_path_restore_stays_retired),
        ("sender-whole-policy-restore-still-retired", sender_whole_policy_restore_stays_retired),
        ("sender-actual-control-pidfd-death", sender_actual_control_pidfd_death_refuses),
        ("sender-actual-control-exec-idle-full-refusal", sender_actual_control_exec_idle_full_refuses),
        ("sender-actual-control-exec-ready-full-refusal", sender_actual_control_exec_ready_full_refuses),
        ("sender-real-fork-parent-report-survives", sender_actual_fork_parent_report_survives),
        ("sender-original-outer-ceiling-no-renewal", sender_outer_ceiling_never_renews),
        ("sender-original-accepted-ceiling-no-renewal", sender_accepted_ceiling_never_renews),
        ("sender-cancel-keeps-original-report-once", sender_cancel_keeps_original_report_once),
        ("sender-malformed-ready-sticky-refusal", sender_malformed_ready_is_sticky),
        ("sender-live-peer-hup-sticky-refusal", sender_hup_with_live_peer_is_sticky),
    ]
}

struct FreshSenderCase {
    child: std::process::Child,
    owner_pid: u32,
    reaped: bool,
}
impl Drop for FreshSenderCase {
    fn drop(&mut self) {
        if self.owner_pid == std::process::id() && !self.reaped {
            let _ = self.child.kill();
            let _ = self.child.wait();
            self.reaped = true;
        }
    }
}
fn sender_host_corpus() {
    let arguments: Vec<_> = std::env::args().collect();
    assert_eq!(arguments.len(), 3);
    assert_eq!(arguments[1], "--configured-systemd-profile");
    for index in 0..sender_host_cases().len() {
        let before = support::inventory();
        let child = Command::new(std::env::current_exe().unwrap())
            .args(["--upper-sender-case", &arguments[2], &index.to_string()])
            .stdin(std::process::Stdio::null())
            .stdout(std::process::Stdio::inherit())
            .stderr(std::process::Stdio::inherit())
            .spawn().unwrap();
        let mut owned = FreshSenderCase { child, owner_pid: std::process::id(), reaped: false };
        let stop = Instant::now() + support::WAIT;
        loop {
            if let Some(status) = owned.child.try_wait().unwrap() {
                owned.reaped = true;
                assert!(status.success(), "fresh sender case failed: {index}");
                break;
            }
            assert!(Instant::now() < stop, "fresh sender case exceeded the existing fixture wait");
            thread::sleep(Duration::from_millis(2));
        }
        drop(owned);
        assert_eq!(support::inventory(), before);
    }
}
fn sender_host_case(index: usize) {
    let (name, case) = sender_host_cases()[index];
    sender_require_single_thread();
    let before = support::inventory();
    case();
    assert_eq!(support::inventory(), before);
    println!("PASS {name}; actual default proc/kernel/root fixture; no native/installed qualification");
}

fn corpus() {
    for (name, case) in [
        (
            "idle-and-independent-report-after-action-revoke",
            idle_and_revoked_action_reporting as fn(),
        ),
        (
            "actual-cancel-revokes-action-keeps-report",
            actual_cancel_retires_action_reporting_owner_survives,
        ),
        (
            "whole-root-policy-drift-sticky-refusal",
            root_drift_sticky_refusal,
        ),
        (
            "actual-control-pidfd-death-refusal",
            actual_control_death_refuses,
        ),
        (
            "fork-refusal-parent-original-report",
            actual_fork_parent_report_survives,
        ),
        (
            "original-twenty-second-expiry-no-renewal",
            original_expiry_no_renewal,
        ),
        (
            "actual-journal-terminal-with-idle-control",
            actual_product_journal_terminal_on_idle_control,
        ),
        (
            "actual-control-exec-ready-full-boundary",
            exec_ready_full_refuses,
        ),
        (
            "actual-control-exec-idle-no-authority-terminal-full-refusal",
            exec_idle_terminal_full_refuses,
        ),
    ] {
        let before = support::inventory();
        case();
        assert_eq!(support::inventory(), before);
        println!(
            "PASS {name}; actual default proc/kernel/root fixture; no native/installed qualification"
        );
    }
    sender_host_corpus();
}
fn main() {
    let args: Vec<_> = std::env::args_os().collect();
    if args.get(1).is_some_and(|value| value == "--upper-sender-case") {
        assert_eq!(args.len(), 4);
        support::configure(args[2].to_str().unwrap());
        sender_host_case(args[3].to_str().unwrap().parse().unwrap());
        return;
    }
    if args.get(1).is_some_and(|value| value == "--child")
        && args
            .get(2)
            .is_some_and(|value| value == "readiness-exec-cancel" || value == "readiness-exec-idle")
    {
        assert_eq!(args.len(), 6);
        exec_custodian(
            Path::new(&args[3]),
            Path::new(&args[4]),
            Path::new(&args[5]),
            args[2] == "readiness-exec-cancel",
        );
        return;
    }
    support::launch_host(corpus);
}
