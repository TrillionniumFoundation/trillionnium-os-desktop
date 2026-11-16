//! Owned host-only regressions for the real lifecycle dispatcher.
//!
//! These tests do not enter Android or contact the running service. One ordinary
//! test process stands in for the owned cell process. The running dispatch test
//! installs a thread-local seccomp filter before calling Daemon::handle, so an
//! attempted fork/clone cannot be hidden by a later wait or a fast child exit.

use super::*;
use std::process::{Child, ChildStdin, Command, Stdio};

const FIXTURE_ENV: &str = "DROIDLOOM_OWNED_STATUS_PROCESS_FIXTURE";
const FIXTURE_TEST: &str =
    "control::status_lifecycle_tests::owned_lifecycle_process_fixture";
const FIXTURE_READY: &[u8] = b"OWNED_STATUS_FIXTURE_READY\n";
const OWNER_UID: u32 = 2_000_000_000;

struct ChildGuard(Option<Child>);

impl Drop for ChildGuard {
    fn drop(&mut self) {
        if let Some(mut child) = self.0.take() {
            let _ = child.kill();
            let _ = child.wait();
        }
    }
}

struct RunningFixture {
    daemon: Daemon,
    input: Option<ChildStdin>,
    directory: tempfile::TempDir,
    owner_pid: u32,
}

impl RunningFixture {
    fn new() -> Self {
        let directory = tempfile::tempdir().unwrap();
        let root = directory.path();
        let spec = CellSpec {
            host_uid: OWNER_UID,
            subordinate_uids: crate::IdRange {
                start: 200_000,
                count: 100_000,
            },
            subordinate_gids: crate::IdRange {
                start: 300_000,
                count: 100_000,
            },
            image_dir: root.join("images"),
            image_layout: crate::AndroidImageLayout::default(),
            gapps_dir: None,
            vendor_image: root.join("vendor.img"),
            android_init: None,
            android_file_overrides: Vec::new(),
            android_runtime_directories: Vec::new(),
            shared_storage_directories: Vec::new(),
            data_dir: root.join("data"),
            runtime_dir: root.join("runtime"),
            render_node: "/dev/dri/renderD128".into(),
            graphics_backend: crate::GraphicsBackend::default(),
            denial_socket: root.join("denial.sock"),
        };
        spec.validate().unwrap();
        let spec_path = root.join("cell.json");
        fs::write(&spec_path, serde_json::to_vec(&spec).unwrap()).unwrap();

        let child = Command::new(std::env::current_exe().unwrap())
            .args(["--exact", FIXTURE_TEST, "--ignored", "--nocapture", "--test-threads=1"])
            .env(FIXTURE_ENV, "1")
            .stdin(Stdio::piped())
            .stdout(Stdio::null())
            .stderr(Stdio::piped())
            .spawn()
            .unwrap();
        let mut child = ChildGuard(Some(child));
        let process = child.0.as_mut().unwrap();
        let input = process.stdin.take().unwrap();
        let mut stderr = process.stderr.take().unwrap();
        let mut poll = libc::pollfd {
            fd: stderr.as_raw_fd(),
            events: libc::POLLIN,
            revents: 0,
        };
        // SAFETY: poll points to one live descriptor owned by this fixture.
        let count = unsafe { libc::poll(&mut poll, 1, 3000) };
        assert_eq!(count, 1, "owned fixture did not announce readiness");
        assert_ne!(poll.revents & libc::POLLIN, 0);
        let mut ready = vec![0_u8; FIXTURE_READY.len()];
        stderr.read_exact(&mut ready).unwrap();
        assert_eq!(ready, FIXTURE_READY);
        drop(stderr);
        assert!(process.try_wait().unwrap().is_none());
        let owner_pid = process.id();
        let cell = DevelopmentCell::owned_process_for_lifecycle_test(
            spec.clone(),
            child.0.take().unwrap(),
        );
        let mut daemon = Daemon::new(DaemonConfig {
            socket: root.join("unused.sock"),
            supervisor: root.join("unused-supervisor"),
            spec_directory: root.to_owned(),
        });
        daemon.active = Some(ActiveCell {
            spec_path,
            spec,
            cell,
        });
        Self {
            daemon,
            input: Some(input),
            directory,
            owner_pid,
        }
    }

    fn finish(&mut self) {
        drop(self.input.take());
        let mut active = self.daemon.active.take().unwrap();
        active.cell.stop().unwrap();
        assert!(active.cell.try_wait().unwrap().is_some());
    }
}

impl Drop for RunningFixture {
    fn drop(&mut self) {
        drop(self.input.take());
        if let Some(mut active) = self.daemon.active.take() {
            // The fallback owns only this fixture child. Successful tests also
            // call finish(), which checks stop and joined exit explicitly.
            let _ = active.cell.stop();
        }
    }
}

#[test]
#[ignore = "private subprocess entry used only by RunningFixture"]
fn owned_lifecycle_process_fixture() {
    if std::env::var(FIXTURE_ENV).as_deref() != Ok("1") {
        return;
    }
    std::io::stderr().write_all(FIXTURE_READY).unwrap();
    let mut byte = [0_u8; 1];
    let error = std::io::stdin().read_exact(&mut byte).unwrap_err();
    assert_eq!(error.kind(), io::ErrorKind::UnexpectedEof);
}

fn current_thread_children() -> Vec<u32> {
    // SAFETY: gettid has no pointer arguments or side effects.
    let tid = unsafe { libc::syscall(libc::SYS_gettid) };
    assert!(tid > 0);
    let path = format!("/proc/self/task/{tid}/children");
    let mut text = String::new();
    fs::File::open(path)
        .unwrap()
        .take(8193)
        .read_to_string(&mut text)
        .unwrap();
    assert!(text.len() <= 8192);
    let mut children: Vec<u32> = text
        .split_whitespace()
        .map(|part| {
            assert!(part.bytes().all(|b| b.is_ascii_digit()));
            let pid: u32 = part.parse().unwrap();
            assert!(pid > 0);
            pid
        })
        .collect();
    children.sort_unstable();
    assert!(!children.windows(2).any(|pair| pair[0] == pair[1]));
    children
}

fn forbid_process_creation_on_this_test_thread() {
    const LD_W_ABS: u16 = 0x20;
    const ALU_AND_K: u16 = 0x54;
    const JMP_JEQ_K: u16 = 0x15;
    const RET_K: u16 = 0x06;
    const AUDIT_ARCH_X86_64: u32 = 0xc000_003e;
    const SECCOMP_RET_KILL_PROCESS: u32 = 0x8000_0000;
    const SECCOMP_RET_ERRNO: u32 = 0x0005_0000;
    const SECCOMP_RET_ALLOW: u32 = 0x7fff_0000;

    let stmt = |code, k| libc::sock_filter { code, jt: 0, jf: 0, k };
    let jump = |k, jt, jf| libc::sock_filter { code: JMP_JEQ_K, jt, jf, k };
    let mut filter = vec![
        stmt(LD_W_ABS, 4), // seccomp_data.arch
        jump(AUDIT_ARCH_X86_64, 1, 0),
        stmt(RET_K, SECCOMP_RET_KILL_PROCESS),
        stmt(LD_W_ABS, 0), // seccomp_data.nr
        stmt(ALU_AND_K, !(1_u32 << 30)), // reject x32 aliases too
    ];
    for syscall in [libc::SYS_fork, libc::SYS_vfork, libc::SYS_clone, libc::SYS_clone3] {
        filter.push(jump(syscall as u32, 0, 1));
        filter.push(stmt(RET_K, SECCOMP_RET_ERRNO | libc::EPERM as u32));
    }
    filter.push(stmt(RET_K, SECCOMP_RET_ALLOW));
    let program = libc::sock_fprog {
        len: u16::try_from(filter.len()).unwrap(),
        filter: filter.as_mut_ptr(),
    };
    // SAFETY: these prctl operations only restrict this test thread. program
    // and its filter remain valid during the syscall; the kernel copies them.
    assert_eq!(
        unsafe { libc::prctl(libc::PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) },
        0,
        "{}",
        io::Error::last_os_error()
    );
    assert_eq!(
        unsafe { libc::prctl(libc::PR_SET_SECCOMP, 2, &program as *const libc::sock_fprog) },
        0,
        "{}",
        io::Error::last_os_error()
    );
}

#[test]
fn status_and_readiness_are_distinct_explicit_wire_requests() {
    for (request, expected) in [
        (ControlRequest::Status, r#"{"command":"status"}"#),
        (ControlRequest::Readiness, r#"{"command":"readiness"}"#),
        (ControlRequest::WaitReady, r#"{"command":"wait_ready"}"#),
    ] {
        let wire = serde_json::to_string(&request).unwrap();
        assert_eq!(wire, expected);
        assert_eq!(serde_json::from_str::<ControlRequest>(&wire).unwrap(), request);
    }
}

#[test]
fn stopped_dispatch_does_not_claim_android_ready() {
    let root = tempfile::tempdir().unwrap();
    let mut daemon = Daemon::new(DaemonConfig {
        socket: root.path().join("unused.sock"),
        supervisor: root.path().join("unused-supervisor"),
        spec_directory: root.path().to_owned(),
    });
    for request in [ControlRequest::Status, ControlRequest::Readiness] {
        let response = daemon.handle(0, request, None);
        assert!(response.ok);
        assert_eq!(response.state, CellState::Stopped);
        assert_eq!(response.host_pid, None);
        assert!(!response.message.contains("Android is ready"));
    }
    let wait = daemon.handle(0, ControlRequest::WaitReady, None);
    assert!(!wait.ok);
    assert_eq!(wait.state, CellState::Stopped);
    assert!(wait.message.contains("not running"));
}

#[test]
fn running_status_dispatch_creates_no_child_and_cannot_replace_fresh_readiness() {
    let mut fixture = RunningFixture::new();
    let children = current_thread_children();
    assert_eq!(children, vec![fixture.owner_pid]);
    forbid_process_creation_on_this_test_thread();

    // Verify that the kernel boundary is active before testing the dispatcher.
    // A mistakenly permissive filter is a failure, not an untested green case.
    match Command::new(std::env::current_exe().unwrap()).arg("--help").spawn() {
        Err(error) => assert_eq!(error.raw_os_error(), Some(libc::EPERM)),
        Ok(child) => {
            drop(ChildGuard(Some(child)));
            panic!("process-creation filter did not reject spawn");
        }
    }

    for uid in [OWNER_UID, 0] {
        let status = fixture.daemon.handle(uid, ControlRequest::Status, None);
        assert!(status.ok, "{}", status.message);
        assert_eq!(status.state, CellState::Running);
        assert_eq!(status.host_pid, Some(fixture.owner_pid));
        assert!(status.message.contains("Android readiness has not been checked"));
        assert!(!status.message.contains("Android is ready"));
        assert_eq!(current_thread_children(), children);
    }
    let denied = fixture.daemon.handle(OWNER_UID + 1, ControlRequest::Status, None);
    assert!(!denied.ok);
    assert!(denied.message.contains("not authorized"));

    let spec_path = fixture.directory.path().join("cell.json");
    for request in [
        ControlRequest::Readiness,
        ControlRequest::WaitReady,
        ControlRequest::ListApplications { user: 0 },
        ControlRequest::ApplicationIcon {
            component: "org.example.statusfixture/.Main".into(),
            user: 0,
            size: 128,
        },
        ControlRequest::Launch {
            spec: spec_path,
            package: "org.example.statusfixture".into(),
            component: Some("org.example.statusfixture/.Main".into()),
            resolution: None,
            user: 0,
        },
    ] {
        let response = fixture.daemon.handle(0, request, None);
        assert!(!response.ok, "a lifecycle observation bypassed fresh readiness");
        assert_eq!(response.state, CellState::Running);
        assert!(
            response.message.contains("list exact cell namespace processes"),
            "request failed before the original fresh probe: {}",
            response.message
        );
        assert!(response.launch.is_none());
        assert!(response.applications.is_none());
        assert!(response.application_icon.is_none());
        assert_eq!(current_thread_children(), children);
    }

    let again = fixture.daemon.handle(0, ControlRequest::Status, None);
    assert!(again.ok);
    assert!(!again.message.contains("Android is ready"));
    fixture.finish();
    assert!(current_thread_children().is_empty());
}
