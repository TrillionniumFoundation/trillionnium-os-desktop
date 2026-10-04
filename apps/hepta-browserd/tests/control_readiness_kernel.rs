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
}
fn main() {
    let args: Vec<_> = std::env::args_os().collect();
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
