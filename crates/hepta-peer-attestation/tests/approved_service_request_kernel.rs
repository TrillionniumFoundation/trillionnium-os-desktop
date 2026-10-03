//! Explicit root-selected source test, not an installed service or native health.
//! Real default /proc, root files and three actual PIDs. Single-thread harness.
//! Last two groups inject unsafe same-process descriptor replacement at the
//! transport mechanism layer; they do not claim safe arbitrary concurrent dup2.
use hepta_agent_transport::{
    AcceptedStreamCustody, HandoffReceiver, HandoffSender, PeerPolicy, RemoteRetirementReport,
    RemoteTerminalState, RootControlPathCustody, RootControlPathPolicy, RootControlPathVerifier, RootOwnedControlListener,
    RootPathControlConnection,
};
use hepta_peer_attestation::{
    ApprovedPolicyError, ApprovedServicePolicyDocument, ApprovedServiceReceivedRequest,
    ApprovedServiceRequestBinding, ApprovedServiceRequests, ApprovedServiceRetainedReporter,
    ControlRequestCustody,
};
use sha2::{Digest, Sha256};
use std::{
    fs::{self, OpenOptions},
    io::{Read, Write},
    mem::{size_of, zeroed},
    os::{
        fd::{AsRawFd, FromRawFd, OwnedFd, RawFd},
        unix::{
            fs::{MetadataExt, OpenOptionsExt, PermissionsExt},
            net::{UnixListener, UnixStream},
        },
    },
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::{Arc, atomic::{AtomicBool, Ordering}},
    time::{Duration, Instant},
};

const GROUPS: usize = 19;
const WAIT: Duration = Duration::from_secs(20);
const AFTER_FIRST: Duration = Duration::from_secs(21);
const SIDEBAND_BYTES: usize = 192;

fn unavailable(reason: &str) -> ! {
    eprintln!("UNAVAILABLE {reason}; original request kernel NOT PASSED");
    std::process::exit(77)
}
fn descriptors() -> Vec<(u32, PathBuf)> {
    let names: Vec<_> = fs::read_dir("/proc/self/fd")
        .unwrap()
        .map(|entry| entry.unwrap().file_name())
        .collect();
    let mut result: Vec<_> = names
        .into_iter()
        .filter_map(|name| {
            let fd = name.to_str()?.parse().ok()?;
            Some((fd, fs::read_link(format!("/proc/self/fd/{fd}")).ok()?))
        })
        .collect();
    result.sort();
    result
}
fn poll(fd: RawFd, deadline: Instant) {
    let millis = deadline
        .saturating_duration_since(Instant::now())
        .as_millis()
        .min(20000) as i32;
    assert!(millis > 0, "owned fixture original wait");
    let mut item = libc::pollfd {
        fd,
        events: libc::POLLIN,
        revents: 0,
    };
    assert!(unsafe { libc::poll(&mut item, 1, millis) } > 0);
}
fn input() -> u8 {
    poll(0, Instant::now() + WAIT);
    let mut byte = [0];
    std::io::stdin().read_exact(&mut byte).unwrap();
    byte[0]
}
fn line(text: &str) {
    println!("{text}");
    std::io::stdout().flush().unwrap();
}
fn kernel(pid: u32) -> PeerPolicy {
    PeerPolicy {
        expected_uid: 0,
        expected_gid: Some(0),
        expected_pid: Some(pid),
    }
}
fn report() -> RemoteRetirementReport {
    RemoteRetirementReport::new(RemoteTerminalState::Completed, [1; 32], [2; 32]).unwrap()
}
fn metadata(path: &Path) -> (u64, u64, u32, u64, i64, i64, i64, i64) {
    let m = fs::metadata(path).unwrap();
    (
        m.dev(),
        m.ino(),
        m.mode(),
        m.size(),
        m.mtime(),
        m.mtime_nsec(),
        m.ctime(),
        m.ctime_nsec(),
    )
}
struct ChildOwner {
    child: Child,
    creator: u32,
    done: bool,
}
impl ChildOwner {
    fn spawn(f: &Fixture, role: &str, budget: Duration) -> Self {
        let child = Command::new(&f.binary)
            .arg("--child")
            .arg(role)
            .arg(&f.control_path)
            .arg(&f.agent_path)
            .arg(budget.as_millis().to_string())
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::inherit())
            .spawn()
            .unwrap();
        Self {
            child,
            creator: std::process::id(),
            done: false,
        }
    }
    fn expect(&mut self, expected: &str) {
        let deadline = Instant::now() + WAIT;
        let reader = self.child.stdout.as_mut().unwrap();
        let mut bytes = Vec::new();
        loop {
            poll(reader.as_raw_fd(), deadline);
            let mut byte = [0];
            assert_eq!(reader.read(&mut byte).unwrap(), 1);
            if byte[0] == b'\n' {
                break;
            }
            bytes.push(byte[0]);
            assert!(bytes.len() <= 1024);
        }
        assert_eq!(String::from_utf8(bytes).unwrap(), expected);
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
        let deadline = Instant::now() + WAIT;
        loop {
            if let Some(status) = self.child.try_wait().unwrap() {
                self.done = true;
                assert!(status.success());
                return;
            }
            assert!(Instant::now() < deadline);
            std::thread::sleep(Duration::from_millis(2));
        }
    }
}
impl Drop for ChildOwner {
    fn drop(&mut self) {
        if self.creator == std::process::id() && !self.done {
            let _ = self.child.kill();
            let _ = self.child.wait();
        }
    }
}
struct Fixture {
    root: PathBuf,
    binary: PathBuf,
    policy: PathBuf,
    control_path: PathBuf,
    agent_path: PathBuf,
    creator: u32,
}
impl Fixture {
    fn new(policy: &Path, index: usize) -> Self {
        let parent = policy.parent().unwrap();
        let root = parent.join(format!("case-{index}"));
        fs::create_dir(&root).unwrap();
        fs::set_permissions(&root, fs::Permissions::from_mode(0o700)).unwrap();
        let copy = root.join("policy");
        let mut file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .mode(0o600)
            .open(&copy)
            .unwrap();
        file.write_all(&fs::read(policy).unwrap()).unwrap();
        file.sync_all().unwrap();
        Self {
            binary: parent.join("request-kernel"),
            policy: copy,
            control_path: root.join("control.sock"),
            agent_path: root.join("agent.sock"),
            root,
            creator: std::process::id(),
        }
    }
    fn path_policy(&self) -> RootControlPathPolicy {
        RootControlPathPolicy::new(&self.control_path, 0, 0o700, 0, 0o600).unwrap()
    }
    fn listener(&self) -> RootOwnedControlListener {
        let fd =
            unsafe { libc::socket(libc::AF_UNIX, libc::SOCK_SEQPACKET | libc::SOCK_CLOEXEC, 0) };
        assert!(fd >= 0);
        let owned = unsafe { OwnedFd::from_raw_fd(fd) };
        let mut address: libc::sockaddr_un = unsafe { zeroed() };
        address.sun_family = libc::AF_UNIX as _;
        let bytes = self.control_path.as_os_str().as_encoded_bytes();
        assert!(bytes.len() < address.sun_path.len());
        for (out, byte) in address.sun_path.iter_mut().zip(bytes) {
            *out = *byte as _;
        }
        let length = (std::mem::offset_of!(libc::sockaddr_un, sun_path) + bytes.len() + 1)
            as libc::socklen_t;
        assert_eq!(
            unsafe { libc::bind(fd, std::ptr::addr_of!(address).cast(), length) },
            0
        );
        assert_eq!(unsafe { libc::listen(fd, 2) }, 0);
        fs::set_permissions(&self.control_path, fs::Permissions::from_mode(0o600)).unwrap();
        RootOwnedControlListener::from_inherited(owned, &self.path_policy()).unwrap()
    }
    fn source(&self) -> ApprovedServicePolicyDocument {
        ApprovedServicePolicyDocument::open_root_owned(&self.policy).unwrap()
    }
    fn requests(&self) -> ApprovedServiceRequests {
        ApprovedServiceRequests::from_owner(self.source().select_current_owner().unwrap()).unwrap()
    }
    fn change_static_role(&self, role: &str) {
        // Explicit negative root fixture, selected BEFORE any Control/Agent exists.
        // No observation is substituted into a policy or successful admission.
        let bytes = fs::read_to_string(&self.policy).unwrap();
        let changed: String = bytes
            .lines()
            .map(|v| {
                if v.starts_with(&format!("{role}.unit=")) {
                    format!("{role}.unit=unapproved-role.service\n")
                } else {
                    format!("{v}\n")
                }
            })
            .collect();
        fs::write(&self.policy, changed).unwrap();
    }
}
impl Drop for Fixture {
    fn drop(&mut self) {
        if self.creator == std::process::id() {
            fs::remove_dir_all(&self.root).unwrap();
        }
    }
}
struct Trio {
    control: ChildOwner,
    agent: ChildOwner,
    listener: RootOwnedControlListener,
    connection: Option<RootPathControlConnection>,
    first: Instant,
}
impl Trio {
    fn early(f: &Fixture) -> Self {
        let mut listener = f.listener();
        let first = Instant::now();
        let mut control = ChildOwner::spawn(f, "early", WAIT);
        control.expect("PATH_CURRENT");
        let connection = listener.accept_before(kernel(control.child.id()), first + WAIT).unwrap();
        let mut agent = ChildOwner::spawn(f, "agent", WAIT);
        agent.expect("CONNECTED"); control.expect("EARLY_READY");
        assert_ne!(control.child.id(), agent.child.id());
        assert_ne!(control.child.id(), std::process::id());
        assert_ne!(agent.child.id(), std::process::id());
        Self { control, agent, listener, connection: Some(connection), first }
    }
    fn new(f: &Fixture, budget: Duration) -> Self {
        assert!(!budget.is_zero() && budget <= WAIT);
        let mut listener = f.listener();
        let first = Instant::now();
        let mut control = ChildOwner::spawn(f, "control", budget);
        control.expect("PATH_CURRENT");
        let connection = listener
            .accept_before(kernel(control.child.id()), first + budget)
            .unwrap();
        let mut agent = ChildOwner::spawn(f, "agent", budget);
        agent.expect("CONNECTED");
        assert_ne!(control.child.id(), agent.child.id());
        assert_ne!(control.child.id(), std::process::id());
        assert_ne!(agent.child.id(), std::process::id());
        println!(
            "ACTUAL_TRIO owner={} control={} agent={}",
            std::process::id(),
            control.child.id(),
            agent.child.id()
        );
        Self {
            control,
            agent,
            listener,
            connection: Some(connection),
            first,
        }
    }
    fn receive(
        &mut self,
        f: &Fixture,
        requests: &mut ApprovedServiceRequests,
    ) -> Result<ApprovedServiceReceivedRequest, ApprovedPolicyError> {
        let receiver = requests.bind_control(self.connection.take().unwrap(), &f.agent_path)?;
        self.control.expect("ARMED");
        self.control.command(b's');
        let result = receiver.receive_request();
        self.control.expect("SENT");
        result
    }
    fn finish(&mut self) {
        self.control.finish();
        self.agent.finish();
    }
    fn replace_control(&mut self, target: RawFd) -> RootControlPathCustody {
        self.control.command(b'r');
        self.control.expect("SECOND_PATH");
        let connection = self
            .listener
            .accept_before(kernel(self.control.child.id()), Instant::now() + WAIT)
            .unwrap();
        connection
            .consume_before(|fd, _, custody| {
                assert_ne!(fd.as_raw_fd(), target);
                // This single-thread fault is bounded to this separately owned case.
                assert_eq!(unsafe { libc::dup2(fd.as_raw_fd(), target) }, target);
                assert_eq!(
                    unsafe { libc::fcntl(target, libc::F_SETFD, libc::FD_CLOEXEC) },
                    0
                );
                custody
            })
            .unwrap()
    }
}
struct PostFailureDropProbe {
    verifier: RootControlPathVerifier,
    dropped: Arc<AtomicBool>,
}
impl Drop for PostFailureDropProbe {
    fn drop(&mut self) {
        assert!(self.verifier.verify_current().is_err(), "post-failure T drop sees retired original scope");
        self.dropped.store(true, Ordering::SeqCst);
    }
}
struct Request {
    _stream: UnixStream,
    _custody: ControlRequestCustody,
    reporter: ApprovedServiceRetainedReporter,
    binding: ApprovedServiceRequestBinding,
    deadline: Instant,
}
fn unpack(received: ApprovedServiceReceivedRequest) -> Request {
    received
        .consume_with_request_binding(
            |stream, deadline, custody, reporter, _, principal, binding| {
                assert_eq!(principal, "fixture-agent");
                Request {
                    _stream: stream,
                    deadline,
                    _custody: custody,
                    reporter,
                    binding,
                }
            },
        )
        .unwrap()
}
fn terminal(request: &mut Request, trio: &mut Trio) {
    request.reporter.send_remote_report(report()).unwrap();
    assert!(request.reporter.send_remote_report(report()).is_err());
    trio.control.command(b'w');
    trio.control.expect("REPORT Completed");
}
fn seqpacket_to(pid: u32) -> RawFd {
    for (fd, _) in descriptors() {
        let fd = fd as RawFd;
        let mut kind = 0;
        let mut size = size_of::<i32>() as libc::socklen_t;
        if unsafe {
            libc::getsockopt(
                fd,
                libc::SOL_SOCKET,
                libc::SO_TYPE,
                std::ptr::addr_of_mut!(kind).cast(),
                &mut size,
            )
        } != 0
            || kind != libc::SOCK_SEQPACKET
        {
            continue;
        }
        let mut cred: libc::ucred = unsafe { zeroed() };
        let mut size = size_of::<libc::ucred>() as libc::socklen_t;
        if unsafe {
            libc::getsockopt(
                fd,
                libc::SOL_SOCKET,
                libc::SO_PEERCRED,
                std::ptr::addr_of_mut!(cred).cast(),
                &mut size,
            )
        } == 0
            && cred.pid == pid as i32
        {
            return fd;
        }
    }
    panic!("actual Control endpoint not found")
}

fn root_corpus(policy: &Path) {
    assert_eq!(unsafe { libc::geteuid() }, 0);
    let original = metadata(policy);
    let golden = fs::read(policy).unwrap();
    assert_eq!(golden.split(|byte| *byte == b'\n').count() - 1, 19);
    let mut groups = 0;
    macro_rules! case {
        ($name:expr, $f:ident, $body:block) => {{
            let before = descriptors();
            let $f = Fixture::new(policy, groups);
            $body
            drop($f);
            assert_eq!(descriptors(), before, "exact FD inventory after {}", $name);
            groups += 1;
            println!("PASS {} original request kernel group; NativeHealth=false", $name);
        }};
    }
    case!(
        "same-source-new-actual-request-after-first-twenty-seconds",
        f,
        {
            let mut requests = f.requests();
            let session = requests.session_verifier().unwrap();
            let mut first = Trio::new(&f, WAIT);
            let mut request = unpack(first.receive(&f, &mut requests).unwrap());
            request.binding.verify_for_service(&session).unwrap();
            let old = request.binding.verifier_for_service(&session).unwrap();
            let accepted_at = first.first;
            let ceiling = request.deadline;
            assert!(ceiling <= first.first + WAIT);
            terminal(&mut request, &mut first);
            drop(request);
            first.finish();
            drop(first);
            // New pathname endpoints belong to the same original Source/session.
            fs::remove_file(&f.control_path).unwrap();
            fs::remove_file(&f.agent_path).unwrap();
            std::thread::sleep(
                (ceiling + Duration::from_secs(1)).saturating_duration_since(Instant::now()),
            );
            assert!(Instant::now() >= ceiling + Duration::from_secs(1));
            assert!(accepted_at.elapsed() >= AFTER_FIRST);
            assert!(old.verify_for_service(&session).is_err());
            requests.ensure_current().unwrap();
            session.ensure_current().unwrap();
            let mut second = Trio::new(&f, WAIT);
            let mut request = unpack(second.receive(&f, &mut requests).unwrap());
            request.binding.verify_for_service(&session).unwrap();
            assert!(request.deadline > ceiling);
            assert!(request.deadline <= second.first + WAIT);
            terminal(&mut request, &mut second);
            drop(request);
            second.finish();
            println!(
                "SOURCE_CONTINUITY_AFTER_FIRST elapsed_min_seconds={} NativeHealth=false",
                AFTER_FIRST.as_secs()
            );
        }
    );
    case!(
        "persistent-owning-custody-drop-denies-readonly-session",
        f,
        {
            let requests = f.requests();
            let session = requests.session_verifier().unwrap();
            drop(requests);
            assert!(session.ensure_current().is_err());
        }
    );
    case!("actual-agent-wrong-static-root-role-refuses", f, {
        f.change_static_role("agent");
        let mut requests = f.requests();
        let mut trio = Trio::new(&f, WAIT);
        assert!(trio.receive(&f, &mut requests).is_err());
        requests.ensure_current().unwrap();
    });
    case!(
        "actual-control-wrong-static-root-role-refuses-before-challenge",
        f,
        {
            f.change_static_role("control");
            let mut requests = f.requests();
            let mut trio = Trio::new(&f, WAIT);
            assert!(
                requests
                    .bind_control(trio.connection.take().unwrap(), &f.agent_path)
                    .is_err()
            );
            trio.control.expect("REFUSED");
            requests.ensure_current().unwrap();
            trio.finish();
        }
    );
    case!("same-policy-bytes-different-source-session-refuses", f, {
        let mut requests = f.requests();
        let session = requests.session_verifier().unwrap();
        let foreign_requests = f.requests();
        let foreign = foreign_requests.session_verifier().unwrap();
        foreign.ensure_current().unwrap();
        let mut trio = Trio::new(&f, WAIT);
        let mut request = unpack(trio.receive(&f, &mut requests).unwrap());
        let proof = request.binding.verifier_for_service(&session).unwrap();
        assert!(proof.verify_for_service(&foreign).is_err());
        foreign.ensure_current().unwrap();
        proof.verify_for_service(&session).unwrap();
        terminal(&mut request, &mut trio);
        drop(request);
        trio.finish();
    });
    case!("actual-agent-exit-retires-only-original-request", f, {
        let mut requests = f.requests();
        let session = requests.session_verifier().unwrap();
        let mut trio = Trio::new(&f, WAIT);
        let request = unpack(trio.receive(&f, &mut requests).unwrap());
        trio.agent.finish();
        assert!(request.binding.verify_for_service(&session).is_err());
        requests.ensure_current().unwrap();
        session.ensure_current().unwrap();
    });
    case!("actual-control-eof-retires-only-original-request", f, {
        let mut requests = f.requests();
        let session = requests.session_verifier().unwrap();
        let mut trio = Trio::new(&f, WAIT);
        let mut request = unpack(trio.receive(&f, &mut requests).unwrap());
        trio.control.finish();
        assert!(request.reporter.poll_cancel().is_err());
        assert!(request.binding.verify_for_service(&session).is_err());
        requests.ensure_current().unwrap();
    });
    case!("original-request-expiry-cannot-mint-new-ceiling", f, {
        let mut requests = f.requests();
        let session = requests.session_verifier().unwrap();
        let mut trio = Trio::new(&f, Duration::from_secs(6));
        let mut request = unpack(trio.receive(&f, &mut requests).unwrap());
        std::thread::sleep(
            (request.deadline + Duration::from_millis(10))
                .saturating_duration_since(Instant::now()),
        );
        assert!(request.binding.verify_for_service(&session).is_err());
        assert!(request.reporter.send_remote_report(report()).is_err());
        requests.ensure_current().unwrap();
    });
    case!(
        "actual-cancel-revokes-action-independent-terminal-report-remains-legal",
        f,
        {
            let mut requests = f.requests();
            let session = requests.session_verifier().unwrap();
            let mut trio = Trio::new(&f, WAIT);
            let mut request = unpack(trio.receive(&f, &mut requests).unwrap());
            trio.control.command(b'c');
            trio.control.expect("CANCELLED");
            assert!(request.reporter.poll_cancel().unwrap());
            assert!(request.binding.verify_for_service(&session).is_err());
            terminal(&mut request, &mut trio);
            drop(request);
            requests.ensure_current().unwrap();
            trio.finish();
        }
    );
    case!(
        "actual-same-cancel-packet-replay-refuses-without-source-retirement",
        f,
        {
            let mut requests = f.requests();
            let mut trio = Trio::new(&f, WAIT);
            let mut request = unpack(trio.receive(&f, &mut requests).unwrap());
            trio.control.command(b'c');
            trio.control.expect("CANCELLED");
            let fd = seqpacket_to(trio.control.child.id());
            poll(fd, Instant::now() + WAIT);
            let mut packet = [0; SIDEBAND_BYTES];
            assert_eq!(
                unsafe { libc::recv(fd, packet.as_mut_ptr().cast(), packet.len(), libc::MSG_PEEK) },
                packet.len() as isize
            );
            assert!(request.reporter.poll_cancel().unwrap());
            // Protocol fault only: replay the actual authenticated packet over its
            // original live Control peer. No fabricated nonce is used as authority.
            trio.control.command(b'd');
            trio.control
                .child
                .stdin
                .as_mut()
                .unwrap()
                .write_all(&packet)
                .unwrap();
            trio.control.expect("DUPLICATE_CANCEL");
            assert!(request.reporter.poll_cancel().is_err());
            requests.ensure_current().unwrap();
        }
    );
    case!("source-path-drift-and-restoration-remain-sticky", f, {
        let requests = f.requests();
        let session = requests.session_verifier().unwrap();
        fs::set_permissions(&f.policy, fs::Permissions::from_mode(0o666)).unwrap();
        assert!(requests.ensure_current().is_err());
        fs::set_permissions(&f.policy, fs::Permissions::from_mode(0o600)).unwrap();
        assert!(requests.ensure_current().is_err());
        assert!(session.ensure_current().is_err());
    });
    case!(
        "actual-exec-unapproved-owner-elf-refuses-new-owner-admission",
        f,
        {
            // Exec destroys the old Rust proof address space. This group instead
            // proves admission denial of an actual different executed ELF.
            let path = f.root.join("unapproved-owner");
            let mut bytes = fs::read(&f.binary).unwrap();
            bytes.push(1);
            fs::write(&path, bytes).unwrap();
            fs::set_permissions(&path, fs::Permissions::from_mode(0o500)).unwrap();
            let status = Command::new(&path)
                .arg("--wrong-owner")
                .arg(&f.policy)
                .status()
                .unwrap();
            assert!(status.success());
            f.requests().ensure_current().unwrap();
        }
    );
    case!(
        "single-thread-fork-creator-first-parent-stays-current",
        f,
        {
            let mut requests = f.requests();
            let session = requests.session_verifier().unwrap();
            let mut trio = Trio::new(&f, WAIT);
            let mut request = unpack(trio.receive(&f, &mut requests).unwrap());
            let pid = unsafe { libc::fork() };
            assert!(pid >= 0);
            if pid == 0 {
                assert_eq!(
                    requests.ensure_current(),
                    Err(ApprovedPolicyError::ProcessChanged)
                );
                assert_eq!(
                    session.ensure_current(),
                    Err(ApprovedPolicyError::ProcessChanged)
                );
                assert_eq!(
                    request.binding.verify_for_service(&session).err(),
                    Some(ApprovedPolicyError::ProcessChanged)
                );
                assert_eq!(
                    request.reporter.poll_cancel(),
                    Err(ApprovedPolicyError::ProcessChanged)
                );
                unsafe { libc::_exit(0) }
            }
            let mut status = 0;
            assert_eq!(unsafe { libc::waitpid(pid, &mut status, 0) }, pid);
            assert_eq!(status, 0);
            request.binding.verify_for_service(&session).unwrap();
            terminal(&mut request, &mut trio);
            drop(request);
            trio.finish();
        }
    );
    case!(
        "isolated-same-credential-control-fd-replacement-before-scm-refuses",
        f,
        {
            let mut trio = Trio::new(&f, WAIT);
            let (receiver, target, custody) = trio
                .connection
                .take()
                .unwrap()
                .consume_before(|fd, _, custody| {
                    let target = fd.as_raw_fd();
                    (
                        HandoffReceiver::from_control(
                            fd,
                            kernel(trio.control.child.id()),
                            &f.agent_path,
                        )
                        .unwrap(),
                        target,
                        custody,
                    )
                })
                .unwrap();
            trio.control.expect("ARMED");
            let replacement = trio.replace_control(target);
            assert!(receiver.receive_retained_service_control(WAIT).is_err());
            drop(replacement);
            drop(custody);
            // New legacy Drop may close substituted FD; no cleanup immunity claim.
        }
    );
    case!(
        "isolated-same-credential-control-fd-replacement-before-report-refuses",
        f,
        {
            let mut trio = Trio::new(&f, WAIT);
            let (receiver, target, custody) = trio
                .connection
                .take()
                .unwrap()
                .consume_before(|fd, _, custody| {
                    let target = fd.as_raw_fd();
                    (
                        HandoffReceiver::from_control(
                            fd,
                            kernel(trio.control.child.id()),
                            &f.agent_path,
                        )
                        .unwrap(),
                        target,
                        custody,
                    )
                })
                .unwrap();
            trio.control.expect("ARMED");
            trio.control.command(b's');
            let (received, mut pending) = receiver
                .receive_retained_service_control(WAIT)
                .unwrap()
                .into_parts()
                .unwrap();
            trio.control.expect("SENT");
            let replacement = trio.replace_control(target);
            assert!(pending.send_report(report()).is_err());
            assert!(pending.send_report(report()).is_err());
            drop(received);
            drop(replacement);
            drop(custody);
        }
    );
    case!("early-actual-root-fd-replacement-refuses-while-old-clone-still-current", f, {
        let requests = f.requests();
        let mut trio = Trio::early(&f);
        let connection = trio.connection.take().unwrap();
        // Single-thread accept/admit creates the socket before its held clone.
        // Requiring the old deadline after replacement to remain current proves
        // this stimulus did not replace only the retained scope clone.
        let target = seqpacket_to(trio.control.child.id());
        let replacement = trio.replace_control(target);
        connection.deadline().unwrap();
        let mut callback_ran = false;
        let result = connection.consume_service_control_before(|_, _, _| { callback_ran = true; });
        assert!(result.is_err()); assert!(!callback_ran);
        requests.ensure_current().unwrap(); drop(replacement); trio.finish();
    });
    case!("post-transfer-mismatch-revokes-escaped-original-custody", f, {
        let requests = f.requests();
        let mut trio = Trio::early(&f);
        let connection = trio.connection.take().unwrap();
        let mut escaped = None;
        let observed_drop = Arc::new(AtomicBool::new(false));
        let result = connection.consume_service_control_before(|fd, deadline, custody| {
            let verifier = custody.verifier().unwrap();
            let destructor_verifier = custody.verifier().unwrap();
            let replacement = trio.replace_control(fd.as_raw_fd());
            escaped = Some((fd, deadline, custody, verifier, replacement));
            PostFailureDropProbe { verifier: destructor_verifier, dropped: Arc::clone(&observed_drop) }
        });
        assert!(result.is_err()); assert!(observed_drop.load(Ordering::SeqCst)); assert!(escaped.as_ref().unwrap().3.verify_current().is_err());
        // No shared pathname or persistent Source is retired by this FD fault.
        trio.control.command(b'r'); trio.control.expect("SECOND_PATH");
        let next = trio.listener.accept_before(kernel(trio.control.child.id()), Instant::now() + WAIT).unwrap();
        next.deadline().unwrap(); requests.ensure_current().unwrap();
        drop(next); drop(escaped); trio.finish();
    });
    case!("consumer-unwind-revokes-even-escaped-original-proof", f, {
        let requests = f.requests();
        let mut trio = Trio::early(&f); let connection = trio.connection.take().unwrap();
        let mut escaped = None;
        let result = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
            let _: Result<(), _> = connection.consume_service_control_before(|fd, deadline, custody| {
                let verifier = custody.verifier().unwrap();
                escaped = Some((fd, deadline, custody, verifier));
                panic!("specific consumer-unwind stimulus");
            });
        }));
        assert!(result.is_err()); assert!(escaped.as_ref().unwrap().3.verify_current().is_err());
        requests.ensure_current().unwrap(); drop(escaped); trio.finish();
    });
    case!("completed-original-fd-transfer-keeps-same-scope-and-instant", f, {
        let requests = f.requests();
        let mut trio = Trio::early(&f); let connection = trio.connection.take().unwrap();
        let original = connection.deadline().unwrap();
        let (fd, deadline, custody, verifier) = connection.consume_service_control_before(|fd, deadline, custody| {
            let verifier = custody.verifier().unwrap(); (fd, deadline, custody, verifier)
        }).unwrap();
        assert_eq!(deadline, original); verifier.verify_current().unwrap();
        requests.ensure_current().unwrap(); drop(fd); drop(custody);
        assert!(verifier.verify_current().is_err()); drop(verifier); trio.finish();
    });
    assert_eq!(groups, GROUPS);
    assert_eq!(metadata(policy), original);
    assert_eq!(fs::read(policy).unwrap(), golden);
    println!(
        "19 actual original-request kernel groups; NativeHealth=false installed=false production_ready=false"
    );
}

fn controller(cp: &Path, ap: &Path, budget: Duration) {
    let listener = UnixListener::bind(ap).unwrap();
    let parent = unsafe { libc::getppid() } as u32;
    let path = RootControlPathPolicy::new(cp, 0, 0o700, 0, 0o600).unwrap();
    let original = Instant::now() + budget;
    let connection =
        RootPathControlConnection::connect_before(&path, kernel(parent), original).unwrap();
    line("PATH_CURRENT");
    poll(listener.as_raw_fd(), original);
    let (stream, _) = listener.accept().unwrap();
    let custody =
        AcceptedStreamCustody::capture_before(stream, ap, Instant::now() + budget).unwrap();
    let (sender, raw_fd, path_custody) = connection
        .consume_before(|fd, deadline, custody| {
            let raw = fd.as_raw_fd();
            (
                HandoffSender::from_control(
                    fd,
                    kernel(parent),
                    deadline.saturating_duration_since(Instant::now()),
                ),
                raw,
                custody,
            )
        })
        .unwrap();
    let sender = if let Ok(sender) = sender {
        sender
    } else {
        line("REFUSED");
        assert_eq!(input(), b'x');
        return;
    };
    line("ARMED");
    let command = input();
    if command == b'r' {
        let second =
            RootPathControlConnection::connect_before(&path, kernel(parent), Instant::now() + WAIT)
                .unwrap();
        line("SECOND_PATH");
        assert_eq!(input(), b'x');
        drop(second);
        drop(path_custody);
        return;
    }
    assert_eq!(command, b's');
    let mut pending = sender.send_retained_service_control(custody).unwrap();
    line("SENT");
    let mut second = None;
    loop {
        match input() {
            b'x' => break,
            b'c' => {
                pending.request_cancel().unwrap();
                line("CANCELLED");
            }
            b'd' => {
                let mut packet = [0; SIDEBAND_BYTES];
                std::io::stdin().read_exact(&mut packet).unwrap();
                assert_eq!(
                    unsafe {
                        libc::send(
                            raw_fd,
                            packet.as_ptr().cast(),
                            packet.len(),
                            libc::MSG_NOSIGNAL,
                        )
                    },
                    packet.len() as isize
                );
                line("DUPLICATE_CANCEL");
            }
            b'r' => {
                assert!(second.is_none());
                second = Some(
                    RootPathControlConnection::connect_before(
                        &path,
                        kernel(parent),
                        Instant::now() + WAIT,
                    )
                    .unwrap(),
                );
                line("SECOND_PATH");
            }
            b'w' => {
                let received = pending.wait_report().unwrap();
                assert_eq!(received, report());
                line("REPORT Completed");
            }
            other => panic!("unexpected owned command {other}"),
        }
    }
    drop(second);
    drop(path_custody);
}
fn agent(path: &Path) {
    let stream = UnixStream::connect(path).unwrap();
    line("CONNECTED");
    assert_eq!(input(), b'x');
    drop(stream);
}
fn early_control(cp: &Path, ap: &Path) {
    let listener = UnixListener::bind(ap).unwrap();
    let parent = unsafe { libc::getppid() } as u32;
    let path = RootControlPathPolicy::new(cp, 0, 0o700, 0, 0o600).unwrap();
    let original = Instant::now() + WAIT;
    let first = RootPathControlConnection::connect_before(&path, kernel(parent), original).unwrap();
    line("PATH_CURRENT"); poll(listener.as_raw_fd(), original);
    let (stream, _) = listener.accept().unwrap();
    let accepted = AcceptedStreamCustody::capture_before(stream, ap, Instant::now() + WAIT).unwrap();
    line("EARLY_READY"); let mut extras = Vec::new();
    loop {
        match input() {
            b'x' => break,
            b'r' => {
                extras.push(RootPathControlConnection::connect_before(&path, kernel(parent), Instant::now() + WAIT).unwrap());
                line("SECOND_PATH");
            }
            other => panic!("unexpected early owned command {other}"),
        }
    }
    drop(extras); drop(accepted); drop(first);
}
fn prepare() -> i32 {
    assert_eq!(unsafe { libc::geteuid() }, 0);
    let before = descriptors();
    let source = std::env::current_exe().unwrap();
    let identity = metadata(&source);
    let mut input = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
        .open(&source)
        .unwrap();
    let mut bytes = Vec::new();
    Read::by_ref(&mut input)
        .take(256 * 1024 * 1024 + 1)
        .read_to_end(&mut bytes)
        .unwrap();
    assert!(!bytes.is_empty() && bytes.len() <= 256 * 1024 * 1024);
    assert_eq!(metadata(&source), identity);
    let digest = format!("{:x}", Sha256::digest(&bytes));
    let root = PathBuf::from(format!(
        "/var/lib/hepta-service-request-v2-kernel-{}",
        std::process::id()
    ));
    fs::create_dir(&root).unwrap();
    fs::set_permissions(&root, fs::Permissions::from_mode(0o700)).unwrap();
    let binary = root.join("request-kernel");
    let mut output = OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o500)
        .open(&binary)
        .unwrap();
    output.write_all(&bytes).unwrap();
    output.sync_all().unwrap();
    drop(output);
    assert_eq!(fs::read(&binary).unwrap(), bytes);
    let selected = metadata(&binary);
    assert_eq!(fs::metadata(&binary).unwrap().uid(), 0);
    assert_eq!(fs::metadata(&binary).unwrap().nlink(), 1);
    let unit = format!(
        "hepta-service-request-v2-kernel-{}.service",
        std::process::id()
    );
    let mut policy = String::from("schema=trillionnium.approved-mechanisms.v2\n");
    for role in ["control", "agent", "owner"] {
        policy.push_str(&format!("{role}.uid=0\n{role}.gid=0\n{role}.unit={unit}\n{role}.cgroup=/system.slice/{unit}\n{role}.elf_sha256={digest}\n{role}.principal_id=fixture-{role}\n"));
    }
    let policy_path = root.join("policy");
    let mut output = OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o600)
        .open(&policy_path)
        .unwrap();
    output.write_all(policy.as_bytes()).unwrap();
    output.sync_all().unwrap();
    drop(output);
    println!(
        "ROOT_STATIC_REQUEST_PROFILE unit={unit} binary_sha256={digest} observedIdentityUsed=false"
    );
    let result = Command::new("/usr/bin/systemd-run")
        .args([
            "--quiet",
            "--wait",
            "--pipe",
            "--property=Type=oneshot",
            "--property=User=0",
            "--property=Group=0",
            "--property=RuntimeMaxSec=120",
            "--property=TimeoutStartSec=120",
        ])
        .arg(format!("--unit={unit}"))
        .arg(&binary)
        .arg("--policy")
        .arg(&policy_path)
        .output()
        .unwrap();
    std::io::stdout().write_all(&result.stdout).unwrap();
    std::io::stderr().write_all(&result.stderr).unwrap();
    assert_eq!(fs::read(&binary).unwrap(), bytes);
    assert_eq!(metadata(&binary), selected);
    assert_eq!(fs::read(&policy_path).unwrap(), policy.as_bytes());
    drop(input);
    fs::remove_dir_all(&root).unwrap();
    assert!(!root.exists());
    assert_eq!(descriptors(), before);
    result.status.code().unwrap_or(1)
}
fn main() {
    let arguments: Vec<_> = std::env::args_os().collect();
    if arguments.len() == 3 && arguments[1] == "--policy" {
        root_corpus(Path::new(&arguments[2]));
    } else if arguments.len() == 3 && arguments[1] == "--wrong-owner" {
        let source =
            ApprovedServicePolicyDocument::open_root_owned(Path::new(&arguments[2])).unwrap();
        assert!(matches!(
            source.select_current_owner(),
            Err(ApprovedPolicyError::PeerRefused)
        ));
    } else if arguments.len() == 6 && arguments[1] == "--child" {
        let millis: u64 = arguments[5].to_str().unwrap().parse().unwrap();
        let budget = Duration::from_millis(millis);
        assert!(!budget.is_zero() && budget <= WAIT);
        if arguments[2] == "control" {
            controller(Path::new(&arguments[3]), Path::new(&arguments[4]), budget);
        } else if arguments[2] == "agent" {
            agent(Path::new(&arguments[4]));
        } else if arguments[2] == "early" {
            early_control(Path::new(&arguments[3]), Path::new(&arguments[4]));
        } else {
            std::process::exit(2);
        }
    } else if arguments.len() == 2 && arguments[1] == "--prepare" {
        std::process::exit(prepare());
    } else if arguments.len() == 1 {
        if !Path::new("/usr/bin/sudo").is_file() || !Path::new("/run/systemd/system").is_dir() {
            unavailable("root systemd prerequisite");
        }
        let result = Command::new("/usr/bin/sudo")
            .args(["--non-interactive", "--"])
            .arg(std::env::current_exe().unwrap())
            .arg("--prepare")
            .output()
            .unwrap();
        std::io::stdout().write_all(&result.stdout).unwrap();
        std::io::stderr().write_all(&result.stderr).unwrap();
        std::process::exit(result.status.code().unwrap_or(1));
    } else {
        eprintln!("INVALID original request kernel arguments");
        std::process::exit(2);
    }
}
