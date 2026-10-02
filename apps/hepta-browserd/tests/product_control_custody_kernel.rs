//! Three actual Linux processes and fixed live procfs measurements. Explicit
//! same-UID host policies are not installed service or native Servo evidence.
#![cfg(target_os = "linux")]
#![deny(unsafe_op_in_unsafe_fn)]
use hepta_agent_transport::{PeerIdentity, PeerPolicy};
use hepta_browserd::{AcceptedProductConnection, ProductDispatchError, product_connection_queue};
use hepta_peer_attestation::{
    AttestedHandoffReceiver, AttestedHandoffSender, ControlOwnerError, ControlOwnerPolicy,
    ControlReceivedAcceptedStream, PeerRuntimePolicy, ProcfsPeerAttestor,
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
    sender.send().unwrap();
    println!("SENT");
    match input() {
        b'x' => (),
        b'e' => {
            let error = Command::new("/usr/bin/sleep").arg("30").exec();
            panic!("exec failed: {error}");
        }
        _ => panic!("unexpected custodian command"),
    }
}
fn agent(op: &Path) {
    let mut stream = UnixStream::connect(op).unwrap();
    println!("CONNECTED");
    let stop = Instant::now() + Duration::from_secs(30);
    let mut live_socket = true;
    loop {
        let mut p = [
            libc::pollfd {
                fd: 0,
                events: libc::POLLIN,
                revents: 0,
            },
            libc::pollfd {
                fd: if live_socket { stream.as_raw_fd() } else { -1 },
                events: libc::POLLIN,
                revents: 0,
            },
        ];
        let millis = stop
            .saturating_duration_since(Instant::now())
            .as_millis()
            .min(10000) as i32;
        assert!(millis > 0);
        let result = unsafe { libc::poll(p.as_mut_ptr(), 2, millis) };
        assert!(result >= 0);
        if p[0].revents != 0 {
            let mut c = [0];
            std::io::stdin().read_exact(&mut c).unwrap();
            match c[0] {
                b'x' => break,
                b'o' => stream.write_all(b"original-agent").unwrap(),
                b'e' => {
                    let error = Command::new("/usr/bin/sleep").arg("30").exec();
                    panic!("exec failed: {error}");
                }
                _ => panic!("unexpected Agent command"),
            }
        }
        if live_socket && p[1].revents != 0 {
            let mut bytes = [0; 7];
            let n = stream.read(&mut bytes).unwrap();
            if n == 0 {
                live_socket = false;
                println!("EOF");
            } else {
                assert_eq!(&bytes[..n], b"checked");
                println!("CHECKED");
            }
        }
    }
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
struct Trio {
    _directory: Directory,
    custodian: ChildOwner,
    agent: ChildOwner,
    receiver: AttestedHandoffReceiver,
    agent_policy: PeerRuntimePolicy,
    agent_pin: String,
}
impl Trio {
    fn new() -> Self {
        Self::new_budget(WAIT)
    }
    fn new_budget(budget: Duration) -> Self {
        let p = std::env::temp_dir().join(format!(
            "g2dual-{}-{}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        fs::DirBuilder::new().mode(0o700).create(&p).unwrap();
        let directory = Directory(p.clone(), std::process::id());
        let cp = p.join("control.sock");
        let path = p.join("agent.sock");
        let listener = seqpacket(&cp, true);
        let budget_arg = PathBuf::from(budget.as_millis().to_string());
        let mut custodian = ChildOwner::spawn("custodian", &[&cp, &path, &budget_arg]);
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
        let mut agent = ChildOwner::spawn("agent", &[&path]);
        agent.line("CONNECTED");
        assert_ne!(custodian.child.id(), agent.child.id());
        assert_ne!(agent.child.id(), std::process::id());
        assert_ne!(custodian.child.id(), std::process::id());
        let allowed = policy(control.as_raw_fd());
        let receiver =
            AttestedHandoffReceiver::from_control(control, allowed, &path, WAIT).unwrap();
        custodian.line("ARMED");
        let actual = ProcfsPeerAttestor::default()
            .read_snapshot(agent.child.id())
            .unwrap();
        let agent_policy = PeerRuntimePolicy::exact(&actual);
        let agent_pin = actual.executable_sha256;
        Self {
            _directory: directory,
            custodian,
            agent,
            receiver,
            agent_policy,
            agent_pin,
        }
    }
    fn received(&mut self) -> ControlReceivedAcceptedStream {
        self.custodian.command(b's');
        let result = self.receiver.receive_custodied().unwrap();
        self.custodian.line("SENT");
        assert_eq!(
            self.receiver.receive_custodied().err(),
            Some(ControlOwnerError::ChannelRetired)
        );
        result
    }
    fn connection(
        &mut self,
    ) -> (
        AcceptedProductConnection,
        hepta_peer_attestation::ControlRequestVerifier,
    ) {
        let result = self.received();
        let verifier = result.control_verifier().unwrap();
        let c = AcceptedProductConnection::from_control_received(
            result,
            &self.agent_policy,
            &self.agent_pin,
        )
        .unwrap();
        (c, verifier)
    }
    fn finish(&mut self) {
        self.custodian.finish();
        self.agent.finish();
    }
}
fn inventory() -> Vec<u32> {
    let mut result: Vec<_> = fs::read_dir("/proc/self/fd")
        .unwrap()
        .map(|value| {
            value
                .unwrap()
                .file_name()
                .to_str()
                .unwrap()
                .parse()
                .unwrap()
        })
        .collect();
    result.sort_unstable();
    result
}
fn descriptor_snapshot() -> Vec<(u32, PathBuf)> {
    let numbers = inventory();
    numbers
        .into_iter()
        .filter_map(|fd| {
            fs::read_link(format!("/proc/self/fd/{fd}"))
                .ok()
                .map(|path| (fd, path))
        })
        .collect()
}
fn original_and_scope() {
    let mut trio = Trio::new();
    let received = trio.received();
    let deadline = received.deadline().unwrap();
    let verifier = received.control_verifier().unwrap();
    assert_eq!(deadline, verifier.deadline().unwrap());
    trio.agent.command(b'o');
    received
        .consume_before(|mut stream, original, custody| {
            assert_eq!(original, deadline);
            assert_eq!(
                PeerIdentity::from_stream(&stream).unwrap().pid,
                Some(trio.agent.child.id())
            );
            let mut bytes = [0; 14];
            stream.read_exact(&mut bytes).unwrap();
            assert_eq!(&bytes, b"original-agent");
            custody.verifier().unwrap().verify_current().unwrap();
            stream.write_all(b"checked").unwrap();
        })
        .unwrap();
    trio.agent.line("CHECKED");
    trio.agent.line("EOF");
    assert_eq!(
        verifier.verify_current(),
        Err(ControlOwnerError::PeerRefused)
    );
    trio.finish();
}
fn connection_drop_and_cancel() {
    for cancel in [false, true] {
        let mut trio = Trio::new();
        let (connection, verifier) = trio.connection();
        verifier.verify_current().unwrap();
        let cancellation = connection.cancellation();
        if cancel {
            cancellation.cancel();
            assert_eq!(
                connection.deadline().err(),
                Some(ProductDispatchError::Cancelled)
            );
        }
        drop(connection);
        trio.agent.line("EOF");
        assert!(verifier.verify_current().is_err());
        drop(cancellation);
        trio.finish();
    }
}
fn explicit_revoke() {
    let mut trio = Trio::new();
    let received = trio.received();
    let verifier = received.control_verifier().unwrap();
    received
        .consume_before(|stream, _, custody| {
            custody.revoke().unwrap();
            assert_eq!(
                verifier.verify_current(),
                Err(ControlOwnerError::PeerRefused)
            );
            assert_eq!(
                custody.verifier().err(),
                Some(ControlOwnerError::PeerRefused)
            );
            drop(stream);
        })
        .unwrap();
    assert!(verifier.ensure_alive().is_err());
    trio.agent.line("EOF");
    trio.finish();
}
fn custodian_loss() {
    for queued in [false, true] {
        for changed_image in [false, true] {
            let mut trio = Trio::new();
            let (connection, verifier) = trio.connection();
            let mut connection = Some(connection);
            let (ingress, queue) = product_connection_queue(1).unwrap();
            if queued {
                ingress.try_submit(connection.take().unwrap()).unwrap();
            }
            if changed_image {
                trio.custodian.changed_image();
            } else {
                trio.custodian.finish();
            }
            assert!(verifier.verify_current().is_err());
            if queued {
                assert_eq!(
                    queue.try_next().err(),
                    Some(ProductDispatchError::PeerRefused)
                );
            } else {
                assert_eq!(
                    ingress.try_submit(connection.take().unwrap()).err(),
                    Some(ProductDispatchError::PeerRefused)
                );
            }
            trio.agent.line("EOF");
            if changed_image { /* bounded owner Drop retires exec child */ }
            trio.agent.finish();
        }
    }
}
fn opaque_custodian_loss() {
    for exec in [false, true] {
        let mut trio = Trio::new();
        let received = trio.received();
        let verifier = received.control_verifier().unwrap();
        if exec {
            trio.custodian.changed_image();
        } else {
            trio.custodian.finish();
        }
        assert!(verifier.verify_current().is_err());
        assert_eq!(
            AcceptedProductConnection::from_control_received(
                received,
                &trio.agent_policy,
                &trio.agent_pin
            )
            .err(),
            Some(ProductDispatchError::PeerRefused)
        );
        trio.agent.line("EOF");
        trio.agent.finish();
    }
}
fn wrong_agent_and_agent_loss() {
    for mode in ["policy", "death", "exec"] {
        let mut trio = Trio::new();
        let received = trio.received();
        let verifier = received.control_verifier().unwrap();
        if mode == "policy" {
            trio.agent_policy.expected_cgroup_v2_path = "/wrong".into();
        } else if mode == "death" {
            trio.agent.finish();
        } else {
            trio.agent.changed_image();
        }
        assert_eq!(
            AcceptedProductConnection::from_control_received(
                received,
                &trio.agent_policy,
                &trio.agent_pin
            )
            .err(),
            Some(ProductDispatchError::PeerRefused)
        );
        assert!(
            verifier.verify_current().is_err(),
            "construction failure must revoke control scope too"
        );
        trio.custodian.finish();
        if mode == "policy" {
            trio.agent.line("EOF");
            trio.agent.finish();
        }
    }
}
fn approved_agent_pin_cannot_be_asserted() {
    for pin in [
        "0".repeat(64),
        "A".repeat(64),
        "g".repeat(64),
        "1".repeat(63),
        String::new(),
    ] {
        let mut trio = Trio::new();
        let controlled = trio.received();
        let verifier = controlled.control_verifier().unwrap();
        let expected = if pin == "0".repeat(64) {
            ProductDispatchError::PeerRefused
        } else {
            ProductDispatchError::InvalidConfiguration
        };
        assert_eq!(
            AcceptedProductConnection::from_control_received(controlled, &trio.agent_policy, &pin)
                .err(),
            Some(expected)
        );
        assert!(verifier.verify_current().is_err());
        trio.agent.line("EOF");
        trio.finish();
    }
}
fn queue_full_closes_owned_scope() {
    let mut first = Trio::new();
    let (one, first_verifier) = first.connection();
    let (ingress, queue) = product_connection_queue(1).unwrap();
    ingress.try_submit(one).unwrap();
    let mut second = Trio::new();
    let (two, second_verifier) = second.connection();
    assert_eq!(
        ingress.try_submit(two).err(),
        Some(ProductDispatchError::QueueFull)
    );
    assert!(second_verifier.verify_current().is_err());
    second.agent.line("EOF");
    second.finish();
    first_verifier.verify_current().unwrap();
    drop(queue.try_next().unwrap().unwrap());
    first.agent.line("EOF");
    first.finish();
}
fn queued_agent_loss() {
    for exec in [false, true] {
        let mut trio = Trio::new();
        let (connection, verifier) = trio.connection();
        let (ingress, queue) = product_connection_queue(1).unwrap();
        ingress.try_submit(connection).unwrap();
        if exec {
            trio.agent.changed_image();
        } else {
            trio.agent.finish();
        }
        assert_eq!(
            queue.try_next().err(),
            Some(ProductDispatchError::PeerRefused)
        );
        assert!(
            verifier.verify_current().is_err(),
            "observed Agent loss permanently retires paired control lease"
        );
        trio.custodian.finish();
    }
}
fn expires_without_renewal() {
    let mut trio = Trio::new_budget(Duration::from_secs(10));
    let received = trio.received();
    let original = received.deadline().unwrap();
    let verifier = received.control_verifier().unwrap();
    thread::sleep(Duration::from_millis(100));
    let connection = AcceptedProductConnection::from_control_received(
        received,
        &trio.agent_policy,
        &trio.agent_pin,
    )
    .unwrap();
    assert_eq!(connection.deadline().unwrap(), original);
    let (ingress, queue) = product_connection_queue(1).unwrap();
    ingress.try_submit(connection).unwrap();
    thread::sleep(original.saturating_duration_since(Instant::now()) + Duration::from_millis(10));
    assert_eq!(
        queue.try_next().err(),
        Some(ProductDispatchError::DeadlineExceeded)
    );
    assert!(verifier.verify_current().is_err());
    trio.agent.line("EOF");
    trio.finish();
}
fn opaque_drop_closes_original() {
    let mut trio = Trio::new();
    let received = trio.received();
    let verifier = received.control_verifier().unwrap();
    drop(received);
    assert!(verifier.verify_current().is_err());
    trio.agent.line("EOF");
    trio.finish();
}
fn fork_copy_has_no_authority() {
    let mut trio = Trio::new();
    let received = trio.received();
    let verifier = received.control_verifier().unwrap();
    let original = received.deadline().unwrap();
    let parent_descriptors = descriptor_snapshot();
    let pid = unsafe { libc::fork() };
    assert!(pid >= 0);
    if pid == 0 {
        let child_descriptors = descriptor_snapshot();
        assert_eq!(
            verifier.ensure_alive(),
            Err(ControlOwnerError::ProcessChanged)
        );
        assert_eq!(
            verifier.verify_current(),
            Err(ControlOwnerError::ProcessChanged)
        );
        assert_eq!(
            received.deadline().err(),
            Some(ControlOwnerError::ProcessChanged)
        );
        assert_eq!(
            received
                .consume_before(|_, _, _| panic!("fork callback forbidden"))
                .err(),
            Some(ControlOwnerError::ProcessChanged)
        );
        drop(verifier);
        let after = descriptor_snapshot();
        assert_eq!(
            child_descriptors.len() - after.len(),
            3,
            "only owned original socket/time namespace/control pidfd copies close"
        );
        assert!(
            after.iter().all(|entry| child_descriptors.contains(entry)),
            "foreign inherited descriptors survive"
        );
        unsafe { libc::_exit(0) }
    }
    let stop = Instant::now() + WAIT;
    let mut status = 0;
    loop {
        let done = unsafe { libc::waitpid(pid, &mut status, libc::WNOHANG) };
        if done == pid {
            break;
        }
        assert_eq!(done, 0);
        if Instant::now() >= stop {
            unsafe {
                libc::kill(pid, libc::SIGKILL);
                libc::waitpid(pid, &mut status, 0);
            }
            panic!("owned fork child timeout");
        }
        thread::sleep(Duration::from_millis(5));
    }
    assert_eq!(status, 0);
    assert_eq!(descriptor_snapshot(), parent_descriptors);
    verifier.verify_current().unwrap();
    assert_eq!(received.deadline().unwrap(), original);
    drop(received);
    trio.agent.line("EOF");
    trio.finish();
}
fn controlled_connection_fork_drop_preserves_parent() {
    let mut trio = Trio::new();
    let (connection, verifier) = trio.connection();
    let cancellation = connection.cancellation();
    let deadline = connection.deadline().unwrap();
    let (ingress, _queue) = product_connection_queue(1).unwrap();
    let parent_descriptors = descriptor_snapshot();
    let pid = unsafe { libc::fork() };
    assert!(pid >= 0);
    if pid == 0 {
        let child_descriptors = descriptor_snapshot();
        assert_eq!(
            connection.deadline().err(),
            Some(ProductDispatchError::PeerRefused)
        );
        cancellation.cancel();
        assert_eq!(
            ingress.try_submit(connection).err(),
            Some(ProductDispatchError::PeerRefused)
        );
        drop(cancellation);
        drop(verifier);
        let after = descriptor_snapshot();
        assert_eq!(
            child_descriptors.len() - after.len(),
            4,
            "owned original/interrupt/Agent pidfd/control pidfd copies close"
        );
        assert!(after.iter().all(|entry| child_descriptors.contains(entry)));
        unsafe { libc::_exit(0) }
    }
    let stop = Instant::now() + WAIT;
    let mut status = 0;
    loop {
        let done = unsafe { libc::waitpid(pid, &mut status, libc::WNOHANG) };
        if done == pid {
            break;
        }
        assert_eq!(done, 0);
        if Instant::now() >= stop {
            unsafe {
                libc::kill(pid, libc::SIGKILL);
                libc::waitpid(pid, &mut status, 0);
            }
            panic!("owned controlled fork child timeout");
        }
        thread::sleep(Duration::from_millis(5));
    }
    assert_eq!(status, 0);
    assert_eq!(descriptor_snapshot(), parent_descriptors);
    assert_eq!(connection.deadline().unwrap(), deadline);
    verifier.verify_current().unwrap();
    cancellation.cancel();
    trio.agent.line("EOF");
    drop(connection);
    trio.finish();
}
// The original-Agent files below are explicitly synthetic, solely to make the
// callback facade corpus independent of host systemd unit availability. Control
// custody still comes from the real default-live three-process path. This is
// source ordering evidence, never default product admission or Servo execution.
fn source_completion_two_peer_checks() {
    use hepta_agent_port::{AgentPortError, DispatchContext, HandlerOutcome};
    use hepta_browser_actor::{
        ServoBrowserActor, ServoRuntimeError, TaskFlowPrincipal, servo_runtime_pair,
    };
    use hepta_browser_codec::{
        BrowserErrorCode, BrowserOperation, BrowserRequest, EffectClass, JsonObject,
    };
    use std::sync::Arc;
    for cut in [
        "normal",
        "control-death",
        "control-revoke",
        "agent-files",
        "preflight-revoke",
        "prepared-revoke",
        "prepared-expired",
        "prepared-preflight-refusal",
        "prepared-fork",
    ] {
        let mut trio = Trio::new();
        let controlled = trio.received();
        let control = controlled.control_verifier().unwrap();
        let (original, deadline, custody) = controlled
            .consume_before(|stream, deadline, custody| (stream, deadline, custody))
            .unwrap();
        let peer = PeerIdentity::from_stream(&original).unwrap();
        assert_eq!(peer.pid, Some(trio.agent.child.id()));
        let fake = trio._directory.0.join("explicit-source-agent-proc");
        let process = fake.join(peer.pid.unwrap().to_string());
        fs::DirBuilder::new().mode(0o700).create(&fake).unwrap();
        fs::DirBuilder::new().mode(0o700).create(&process).unwrap();
        fs::write(
            process.join("status"),
            format!(
                "Uid:\t{0}\t{0}\t{0}\t{0}\nGid:\t{1}\t{1}\t{1}\t{1}\n",
                peer.uid, peer.gid
            ),
        )
        .unwrap();
        let mut fields = vec!["S"; 20];
        fields[19] = "987654";
        fs::write(
            process.join("stat"),
            format!(
                "{} (source-fixture) {}\n",
                peer.pid.unwrap(),
                fields.join(" ")
            ),
        )
        .unwrap();
        fs::write(
            process.join("cgroup"),
            "0::/system.slice/source-fixture.service\n",
        )
        .unwrap();
        fs::write(process.join("exe"), b"explicit-source-fixture-image").unwrap();
        let attestor = ProcfsPeerAttestor::new(&fake);
        let snapshot = attestor.read_snapshot(peer.pid.unwrap()).unwrap();
        let attested = attestor
            .attest(peer, &PeerRuntimePolicy::exact(&snapshot))
            .unwrap();
        let principal = TaskFlowPrincipal {
            principal_id: "source-only-dual".into(),
            expected_uid: peer.uid,
            expected_gid: peer.gid,
            expected_systemd_unit: snapshot.systemd_unit.clone().unwrap(),
            expected_cgroup_v2_path: snapshot.cgroup_v2_path,
            expected_executable_sha256: snapshot.executable_sha256,
        };
        let (endpoint, mut owner) = servo_runtime_pair(Arc::new(|| {}));
        if cut == "preflight-revoke" {
            custody.revoke().unwrap();
        }
        let worker_control = control.clone();
        let preflight_only = cut == "preflight-revoke";
        let prepared = cut.starts_with("prepared-");
        let (prepared_tx, prepared_rx) = std::sync::mpsc::channel();
        let (retired_tx, retired_rx) = std::sync::mpsc::channel();
        let worker = thread::spawn(move || {
            let mut actor =
                ServoBrowserActor::from_attested(principal, peer, &attestor, &attested, endpoint)
                    .unwrap();
            let request = BrowserRequest {
                request_id: "source-dual-health".into(),
                session_id: None,
                session_generation: None,
                deadline_unix_ms: None,
                operation: BrowserOperation::Health,
            };
            let context = DispatchContext {
                peer,
                transport_sequence: 1,
                canonical_request_sha256: "1".repeat(64),
                effect_class: EffectClass::Observation,
                accepted_at: Instant::now(),
                // A shorter source-fixture deadline never extends the actual
                // accepted custody. The original kernel expiry corpus remains.
                effective_deadline: if cut == "prepared-expired" {
                    deadline.min(Instant::now() + Duration::from_secs(1))
                } else {
                    deadline
                },
            };
            let refusal = actor
                .preflight_attested_controlled(
                    &context,
                    &request,
                    &attestor,
                    &attested,
                    &worker_control,
                )
                .unwrap();
            if preflight_only {
                return Ok(HandlerOutcome::Failure(refusal.unwrap()));
            }
            assert!(refusal.is_none());
            if prepared {
                let cancellation = actor.cancellation_token(request.request_id.clone());
                assert!(
                    actor
                        .active_cancellation_token(&request.request_id)
                        .is_some()
                );
                assert!(!cancellation.is_cancelled());
                prepared_tx.send(()).unwrap();
                retired_rx.recv_timeout(WAIT).unwrap();
                if cut == "prepared-expired" {
                    if let Some(remaining) = context
                        .effective_deadline
                        .checked_duration_since(Instant::now())
                    {
                        thread::sleep(remaining);
                    }
                    assert!(context.remaining().is_err());
                }
                let outcome = if cut == "prepared-fork" {
                    let parent_descriptors = descriptor_snapshot();
                    let child = unsafe { libc::fork() };
                    assert!(child >= 0);
                    if child == 0 {
                        let refused = actor.retire_prepared_request(&request.request_id).is_err();
                        let kept = actor
                            .active_cancellation_token(&request.request_id)
                            .is_some();
                        let untouched = !cancellation.is_cancelled();
                        unsafe { libc::_exit(if refused && kept && untouched { 0 } else { 83 }) };
                    }
                    let mut status = 0;
                    let stop = Instant::now() + WAIT;
                    loop {
                        let waited = unsafe { libc::waitpid(child, &mut status, libc::WNOHANG) };
                        assert!(waited >= 0);
                        if waited == child {
                            break;
                        }
                        if Instant::now() >= stop {
                            // This exact child remains unreaped, so its PID
                            // cannot have been reused for another process.
                            unsafe {
                                libc::kill(child, libc::SIGKILL);
                                libc::waitpid(child, &mut status, 0);
                            }
                            panic!("inherited preparation refusal exceeded fixture deadline");
                        }
                        thread::sleep(Duration::from_millis(1));
                    }
                    assert!(libc::WIFEXITED(status));
                    assert_eq!(libc::WEXITSTATUS(status), 0);
                    assert_eq!(descriptor_snapshot(), parent_descriptors);
                    assert!(!cancellation.is_cancelled());
                    assert!(
                        actor
                            .active_cancellation_token(&request.request_id)
                            .is_some()
                    );
                    worker_control.verify_current().unwrap();
                    actor.retire_prepared_request(&request.request_id).unwrap();
                    actor.retire_prepared_request(&request.request_id).unwrap();
                    Ok(HandlerOutcome::Success(JsonObject::new()))
                } else if cut == "prepared-preflight-refusal" {
                    let refusal = actor
                        .preflight_attested_controlled(
                            &context,
                            &request,
                            &attestor,
                            &attested,
                            &worker_control,
                        )
                        .unwrap();
                    Ok(HandlerOutcome::Failure(refusal.unwrap()))
                } else {
                    actor.handle_attested_controlled(
                        &context,
                        &request,
                        &attestor,
                        &attested,
                        &worker_control,
                    )
                };
                assert!(
                    actor
                        .active_cancellation_token(&request.request_id)
                        .is_none(),
                    "every prepared refusal must remove the request token"
                );
                assert!(
                    cancellation.is_cancelled(),
                    "retained token must be revoked"
                );
                assert!(actor.page_owner().is_none());
                return outcome;
            }
            actor.handle_attested_controlled(
                &context,
                &request,
                &attestor,
                &attested,
                &worker_control,
            )
        });
        if prepared {
            prepared_rx.recv_timeout(WAIT).unwrap();
            if cut != "prepared-expired" && cut != "prepared-fork" {
                custody.revoke().unwrap();
            }
            retired_tx.send(()).unwrap();
            match worker.join().unwrap() {
                Err(AgentPortError::DeadlineExceeded) => assert_eq!(cut, "prepared-expired"),
                Ok(HandlerOutcome::Failure(error)) => {
                    assert_ne!(cut, "prepared-expired");
                    assert_eq!(error.code, BrowserErrorCode::PolicyDenied);
                }
                Ok(HandlerOutcome::Success(_)) => assert_eq!(cut, "prepared-fork"),
                _ => panic!("unexpected prepared request outcome"),
            }
            owner.pump_one();
            assert!(
                owner.take_command().is_none(),
                "refusal cannot enqueue runtime work"
            );
        } else if preflight_only {
            match worker.join().unwrap().unwrap() {
                HandlerOutcome::Failure(error) => {
                    assert_eq!(error.code, BrowserErrorCode::PolicyDenied)
                }
                _ => panic!("revoked preflight cannot succeed"),
            }
            assert!(owner.take_command().is_none());
        } else {
            let stop = Instant::now() + WAIT;
            let command = loop {
                owner.pump_one();
                if let Some(command) = owner.take_command() {
                    break command;
                }
                assert!(Instant::now() < stop);
                thread::sleep(Duration::from_millis(1));
            };
            let (_, _, completion) = command.into_parts();
            completion.ensure_current_peer().unwrap();
            match cut {
                "control-death" => trio.custodian.finish(),
                "control-revoke" => custody.revoke().unwrap(),
                "agent-files" => {
                    fs::write(process.join("exe"), b"changed source-fixture image").unwrap();
                }
                "normal" => (),
                _ => unreachable!(),
            }
            if cut == "normal" {
                completion.ensure_current_peer().unwrap();
                completion.complete_success(JsonObject::new(), None);
            } else {
                assert!(
                    matches!(
                        completion.ensure_current_peer(),
                        Err(ServoRuntimeError::PeerIdentityRevoked
                            | ServoRuntimeError::BrowserCrashed)
                    ),
                    "revoked peer or already retired callback must deny"
                );
                if cut == "agent-files" {
                    fs::write(process.join("exe"), b"explicit-source-fixture-image").unwrap();
                    assert_eq!(
                        control.verify_current(),
                        Err(ControlOwnerError::PeerRefused),
                        "observed Agent failure latches paired control refusal after bytes restore"
                    );
                    assert!(
                        matches!(
                            completion.ensure_current_peer(),
                            Err(ServoRuntimeError::PeerIdentityRevoked
                                | ServoRuntimeError::BrowserCrashed)
                        ),
                        "revoked peer or already retired callback must deny"
                    );
                }
                completion.complete_error(ServoRuntimeError::PeerIdentityRevoked);
            }
            while !worker.is_finished() {
                owner.pump_one();
                assert!(Instant::now() < stop);
                thread::sleep(Duration::from_millis(1));
            }
            match worker.join().unwrap().unwrap() {
                HandlerOutcome::Success(_) => assert_eq!(cut, "normal"),
                HandlerOutcome::Failure(error) => {
                    assert_ne!(cut, "normal");
                    assert_eq!(error.code, BrowserErrorCode::Indeterminate);
                }
            }
        }
        drop(custody);
        assert!(control.verify_current().is_err());
        drop(original);
        trio.agent.line("EOF");
        if cut != "control-death" {
            trio.custodian.finish();
        }
        trio.agent.finish();
        println!("PASS SOURCE controlled completion cut {cut}; synthetic Agent facts, no Servo");
    }
}
fn main() {
    let args: Vec<_> = std::env::args().collect();
    if args.get(1).map(String::as_str) == Some("--child") {
        if args[2] == "custodian" {
            custodian(
                Path::new(&args[3]),
                Path::new(&args[4]),
                Duration::from_millis(args[5].parse().unwrap()),
            );
        } else {
            agent(Path::new(&args[3]));
        }
        return;
    }
    let cases: [(&str, fn()); 13] = [
        (
            "three actual PIDs/original SO_PEERCRED/deadline/bytes",
            original_and_scope,
        ),
        (
            "connection Drop and cancellation revoke retained scope",
            connection_drop_and_cancel,
        ),
        ("explicit owner revoke never restores", explicit_revoke),
        (
            "queued custodian death and exec retire original",
            custodian_loss,
        ),
        (
            "opaque custodian death and exec deny Agent admission",
            opaque_custodian_loss,
        ),
        (
            "Agent policy/death/exec failure jointly retires control scope",
            wrong_agent_and_agent_loss,
        ),
        (
            "approved Agent pin is canonical and compared to actual bytes",
            approved_agent_pin_cannot_be_asserted,
        ),
        (
            "queue overflow drops only rejected owner",
            queue_full_closes_owned_scope,
        ),
        (
            "queued Agent death or exec revokes paired scope",
            queued_agent_loss,
        ),
        (
            "original expiry never becomes new queue deadline",
            expires_without_renewal,
        ),
        (
            "opaque result Drop closes original socket",
            opaque_drop_closes_original,
        ),
        (
            "actual inherited fork denies before state/parent preserved",
            fork_copy_has_no_authority,
        ),
        (
            "controlled connection fork Drop closes only child owned FDs",
            controlled_connection_fork_drop_preserves_parent,
        ),
    ];
    for (name, test) in cases {
        let before = inventory();
        test();
        assert_eq!(inventory(), before);
        println!("PASS {name}");
    }
    let before = inventory();
    source_completion_two_peer_checks();
    assert_eq!(inventory(), before);
    println!(
        "PASS SOURCE: nine controlled completion cuts; synthetic Agent facts and actual control pidfd only, no Servo execution"
    );
    println!("13 actual three-process dual-owner case groups passed; source host only");
}
