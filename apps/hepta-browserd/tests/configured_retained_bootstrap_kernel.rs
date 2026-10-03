//! Actual root pathname, procfs and three independent processes. No native
//! engine, installed service or action/effect qualification is asserted here.
#[path = "../../../experiments/servo-product-owner/src/approved_test_support.rs"]
mod support;
use hepta_agent_transport::PeerPolicy;
use hepta_browserd::{ConfiguredRetainedBootstrap, ProductDispatchError};
use std::time::{Duration, Instant};
use support::{ChildOwner, Fixture, WAIT};

fn exercise(drift: bool, shorter: bool, fork: bool) {
    let fixture = Fixture::new();
    let mut listener = fixture.listener();
    let mode = if drift || shorter {
        "bootstrap-refusal"
    } else {
        "custodian"
    };
    let mut control = ChildOwner::spawn(&fixture, mode, fixture.agent_path(), false);
    control.expect("PATH_CURRENT");
    let mut agent = ChildOwner::spawn(&fixture, "agent", fixture.agent_path(), false);
    agent.expect("CONNECTED");
    let original = Instant::now() + WAIT;
    let connection = listener
        .accept_before(
            PeerPolicy {
                expected_uid: 0,
                expected_gid: Some(0),
                expected_pid: Some(control.child.id()),
            },
            original,
        )
        .unwrap();
    let ceiling = if shorter {
        Instant::now() + Duration::from_millis(100)
    } else {
        original
    };
    let document = fixture.document(ceiling);
    let mut bootstrap =
        ConfiguredRetainedBootstrap::from_root_document(connection, fixture.agent_path(), document)
            .unwrap();
    assert_eq!(bootstrap.original_deadline().unwrap(), original);
    control.expect("ARMED");
    if fork {
        let pid = unsafe { libc::fork() };
        assert!(pid >= 0);
        if pid == 0 {
            assert_eq!(
                bootstrap.original_deadline(),
                Err(ProductDispatchError::PeerRefused)
            );
            drop(bootstrap);
            unsafe { libc::_exit(0) }
        }
        let mut status = 0;
        assert_eq!(unsafe { libc::waitpid(pid, &mut status, 0) }, pid);
        assert_eq!(status, 0);
        assert_eq!(bootstrap.original_deadline().unwrap(), original);
    }
    if drift {
        fixture.rewrite("agent.principal_id", "changed-agent");
        assert_eq!(
            bootstrap.into_admission().err(),
            Some(ProductDispatchError::PeerRefused)
        );
    } else if shorter {
        std::thread::sleep(
            ceiling.saturating_duration_since(Instant::now()) + Duration::from_millis(5),
        );
        assert_eq!(
            bootstrap.into_admission().err(),
            Some(ProductDispatchError::DeadlineExceeded)
        );
    } else {
        control.command(b's');
        let admission = bootstrap.into_admission().unwrap();
        control.expect("SENT");
        assert!(admission.deadline().unwrap() <= original);
        drop(admission);
    }
    if drift || shorter {
        // No SCM_RIGHTS packet was sent. The remote custodian still owns its
        // original accepted stream until its explicitly commanded retirement.
        // Local control refusal does not claim that remote cleanup completed.
        control.finish();
    }
    agent.command(b'e');
    agent.expect("ORIGINAL_EOF_WITHOUT_HANDSHAKE");
    agent.finish();
    if !drift && !shorter {
        control.finish();
    }
}

fn main() {
    support::launch_host(|| {
        for (name, drift, shorter, fork) in [
            ("same-root-document-original-pair", false, false, false),
            ("policy-drift-before-receive", true, false, false),
            ("shorter-source-ceiling-no-renewal", false, true, false),
            (
                "foreign-process-refusal-parent-retained",
                false,
                false,
                true,
            ),
        ] {
            let before = support::inventory();
            exercise(drift, shorter, fork);
            assert_eq!(support::inventory(), before);
            println!("PASS {name}; real configured retained ingress, no native or installed claim");
        }
    });
}
