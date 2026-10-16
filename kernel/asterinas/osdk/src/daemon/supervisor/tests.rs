// SPDX-License-Identifier: MPL-2.0

use std::{
    io::Read,
    net::{TcpListener, TcpStream},
    path::Path,
    thread,
    time::{Duration, Instant},
};

use tempfile::{TempDir, tempdir};

use super::{DaemonScheme, DaemonSupervisor, RunningDaemon, SignalGuard};
use crate::error::Errno;

const LEASE_TIMEOUT: Duration = Duration::from_secs(2);

fn shell_daemon(script: &str) -> DaemonScheme {
    DaemonScheme {
        path: "/bin/sh".into(),
        args: vec!["-c".into(), script.into()],
    }
}

enum LeaderAction {
    Wait,
    ExitSuccess,
    ExitFailure,
}

/// The native-host fixture requires Bash's /dev/tcp support. A descendant
/// holds a TCP writer open until it is killed or the test closes its peer.
/// Unlike /proc PID probes, EOF works across PID namespaces and identifies
/// this fixture's resource lifetime without confusing a reused numeric PID.
/// Closing the test's connection also makes the descendant's read finish,
/// so assertion failures do not leave the fixture alive indefinitely.
struct DescendantLease {
    listener: TcpListener,
    work_dir: TempDir,
}

impl DescendantLease {
    fn new() -> Self {
        assert!(
            Path::new("/bin/bash").is_file(),
            "native daemon lifecycle tests require /bin/bash with /dev/tcp support"
        );
        let listener = TcpListener::bind(("127.0.0.1", 0)).unwrap();
        listener.set_nonblocking(true).unwrap();
        Self {
            listener,
            work_dir: tempdir().unwrap(),
        }
    }

    fn daemon(&self, ignore_term: bool, action: LeaderAction) -> DaemonScheme {
        let port = self.listener.local_addr().unwrap().port();
        let disposition = if ignore_term {
            "trap '' TERM"
        } else {
            "trap - TERM"
        };
        let action = match action {
            LeaderAction::Wait => "wait",
            LeaderAction::ExitSuccess => "exit 0",
            LeaderAction::ExitFailure => "exit 1",
        };
        let script = format!(
            r#"
(
    {disposition}
    exec 3<>/dev/tcp/127.0.0.1/{port} || exit 98
    printf r >&3
    printf ready >child.ready
    IFS= read -r -u 3 cleanup || :
) &
for ((attempt = 0; attempt < 200; attempt++)); do
    [[ -s child.ready ]] && break
    sleep 0.005
done
[[ -s child.ready ]] || exit 99
{action}
"#
        );
        DaemonScheme {
            path: "/bin/bash".into(),
            // Disable job control so the background child inherits the
            // daemon leader's process group, which is the managed boundary.
            args: vec![
                "--noprofile".into(),
                "--norc".into(),
                "+m".into(),
                "-c".into(),
                script,
            ],
        }
    }

    fn accept_ready(&self) -> TcpStream {
        let deadline = Instant::now() + LEASE_TIMEOUT;
        let mut connection = loop {
            match self.listener.accept() {
                Ok((connection, _)) => break connection,
                Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                    assert!(Instant::now() < deadline, "descendant did not connect");
                    thread::sleep(Duration::from_millis(5));
                }
                Err(error) => panic!("failed to accept descendant lease: {error}"),
            }
        };
        connection.set_read_timeout(Some(LEASE_TIMEOUT)).unwrap();
        let mut ready = [0u8; 1];
        connection.read_exact(&mut ready).unwrap();
        assert_eq!(&ready, b"r", "invalid descendant readiness marker");
        connection
    }

    fn path(&self) -> &Path {
        self.work_dir.path()
    }
}

fn assert_lease_closed(mut connection: TcpStream) {
    let mut byte = [0u8; 1];
    assert_eq!(
        connection
            .read(&mut byte)
            .expect("descendant lease remained open"),
        0,
        "descendant sent unexpected bytes instead of closing its lease"
    );
}

#[test]
fn nonzero_daemon_exit_aborts_startup() {
    let signal_guard = SignalGuard::install().unwrap();
    let daemons = [shell_daemon("exit 1")];
    let result = DaemonSupervisor::start(&daemons, Path::new("."), &signal_guard);
    assert!(matches!(result, Err(Errno::ExecuteCommand)));
}

#[test]
fn successful_daemon_exit_is_reaped() {
    let signal_guard = SignalGuard::install().unwrap();
    let daemons = [shell_daemon("exit 0")];
    let supervisor = DaemonSupervisor::start(&daemons, Path::new("."), &signal_guard)
        .expect("successful daemon exit should not abort startup");
    assert!(supervisor.running_daemons.is_empty());
}

#[test]
fn stop_all_terminates_running_daemon() {
    let signal_guard = SignalGuard::install().unwrap();
    let daemons = [shell_daemon("sleep 30")];
    let mut supervisor = DaemonSupervisor::start(&daemons, Path::new("."), &signal_guard)
        .expect("running daemon should start successfully");
    assert!(!supervisor.running_daemons.is_empty());
    supervisor.stop_all();
    assert!(supervisor.running_daemons.is_empty());
}

#[test]
fn stop_all_escalates_when_daemon_ignores_sigterm() {
    let signal_guard = SignalGuard::install().unwrap();
    let daemons = [shell_daemon("trap '' TERM; sleep 30")];
    let mut supervisor = DaemonSupervisor::start(&daemons, Path::new("."), &signal_guard)
        .expect("daemon should start successfully");
    supervisor.stop_all();
    assert!(supervisor.running_daemons.is_empty());
}

#[test]
fn stop_all_terminates_daemon_descendants() {
    let fixture = DescendantLease::new();
    let signal_guard = SignalGuard::install().unwrap();
    let daemons = [fixture.daemon(false, LeaderAction::Wait)];
    let mut supervisor = DaemonSupervisor::start(&daemons, fixture.path(), &signal_guard)
        .expect("daemon with descendant should start");
    let connection = fixture.accept_ready();
    supervisor.stop_all();
    assert_lease_closed(connection);
}

#[test]
fn stop_all_kills_term_ignoring_descendant_after_leader_exits() {
    let fixture = DescendantLease::new();
    let signal_guard = SignalGuard::install().unwrap();
    let daemons = [fixture.daemon(true, LeaderAction::Wait)];
    let mut supervisor = DaemonSupervisor::start(&daemons, fixture.path(), &signal_guard)
        .expect("daemon with TERM-ignoring descendant should start");
    let connection = fixture.accept_ready();
    supervisor.stop_all();
    assert!(supervisor.running_daemons.is_empty());
    // A second stop, followed by Drop, must not signal an already reaped PGID.
    supervisor.stop_all();
    assert_lease_closed(connection);
}

#[test]
fn successful_startup_exit_cleans_term_ignoring_descendant() {
    let fixture = DescendantLease::new();
    let signal_guard = SignalGuard::install().unwrap();
    let daemons = [fixture.daemon(true, LeaderAction::ExitSuccess)];
    let supervisor = DaemonSupervisor::start(&daemons, fixture.path(), &signal_guard)
        .expect("successful leader exit should not abort startup");
    let connection = fixture.accept_ready();
    assert!(supervisor.running_daemons.is_empty());
    assert_lease_closed(connection);
}

#[test]
fn failed_startup_exit_cleans_term_ignoring_descendant() {
    let fixture = DescendantLease::new();
    let signal_guard = SignalGuard::install().unwrap();
    let daemons = [fixture.daemon(true, LeaderAction::ExitFailure)];
    let result = DaemonSupervisor::start(&daemons, fixture.path(), &signal_guard);
    let connection = fixture.accept_ready();
    assert!(matches!(result, Err(Errno::ExecuteCommand)));
    assert_lease_closed(connection);
}

#[test]
fn drop_cleans_term_ignoring_descendant() {
    let fixture = DescendantLease::new();
    let signal_guard = SignalGuard::install().unwrap();
    let daemons = [fixture.daemon(true, LeaderAction::Wait)];
    let supervisor = DaemonSupervisor::start(&daemons, fixture.path(), &signal_guard)
        .expect("daemon should start");
    let connection = fixture.accept_ready();
    drop(supervisor);
    assert_lease_closed(connection);
}

#[test]
fn poll_exit_observes_status_repeatedly_before_reaping() {
    let daemon = shell_daemon("exit 7");
    let mut running = RunningDaemon::new(&daemon, Path::new(".")).unwrap();
    let deadline = Instant::now() + LEASE_TIMEOUT;
    let status = loop {
        if let Some(status) = running.poll_exit().unwrap() {
            break status;
        }
        assert!(Instant::now() < deadline, "daemon did not exit in time");
        thread::sleep(Duration::from_millis(5));
    };
    assert_eq!(status.exit_status(), Some(7));
    assert_eq!(running.poll_exit().unwrap().unwrap().exit_status(), Some(7));
    assert!(
        running.owns_child,
        "observing status must preserve the PID anchor"
    );
    running.kill_and_wait();
    assert!(!running.owns_child);
    assert_eq!(running.child.wait().unwrap().code(), Some(7));
}

#[test]
fn external_reap_disarms_later_group_signals() {
    let daemon = shell_daemon("exit 0");
    let mut running = RunningDaemon::new(&daemon, Path::new(".")).unwrap();
    assert_eq!(running.child.wait().unwrap().code(), Some(0));
    let error = running.poll_exit().unwrap_err();
    let expected: std::io::Error = rustix::io::Errno::CHILD.into();
    assert_eq!(error.raw_os_error(), expected.raw_os_error());
    assert!(!running.owns_child);
    // These operations and Drop must now be harmless: the numeric PID could
    // already have been reused, and is no longer an identity authority.
    running.terminate();
    running.kill();
    running.kill_and_wait();
    assert!(!running.owns_child);
}
