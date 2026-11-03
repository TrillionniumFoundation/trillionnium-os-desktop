//! Actual owned Session/App processes and egui's output-driven idle timer.
//! This is a host component test, not a native compositor/window qualification.
use super::*;
use std::os::fd::{AsRawFd, FromRawFd, OwnedFd};
use std::process::{Child, Command, Stdio};
use std::time::Instant;
use trill_ui_core::calculator_lifetime::SessionLifetimeSource;

const ROLE: &str = "TRILL_TEST_CALCULATOR_LIFETIME_ROLE";
const PARENT: &str = "calculator_organ::lifetime_tests::owned_session_fixture";
const APP: &str = "calculator_organ::lifetime_tests::idle_app_fixture";
const READY: &[u8] = b"TRILL_TEST_CALCULATOR_IDLE_READY_V1";
const CLOSED: &[u8] = b"TRILL_TEST_CALCULATOR_IDLE_CLOSED_V1";
const FIXTURE: &[u8] = b"calculator-lifetime-fixture-v1";

fn target() -> CalculatorTargetIdentity {
    CalculatorTargetIdentity {
        session_instance: "7".repeat(32),
        task_id: 2,
        incarnation: "8".repeat(32),
    }
}
fn fixture(test: &str, role: &str) -> Command {
    let mut command = Command::new(std::env::current_exe().unwrap());
    command
        .args(["--exact", test, "--nocapture", "--test-threads=1"])
        .env(ROLE, role);
    command
}

#[test]
fn owned_session_fixture() {
    if std::env::var(ROLE).as_deref() != Ok("session") {
        return;
    }
    let inherited = unsafe { BorrowedFd::borrow_raw(0) }
        .try_clone_to_owned()
        .unwrap();
    let bootstrap = UnixDatagram::from(inherited);
    let (metadata, mut control, app_control) =
        trill_ui_core::notes_private_unix::receive_channels(&bootstrap, Duration::from_secs(8))
            .unwrap();
    assert_eq!(metadata, FIXTURE);
    // The spawning thread exits first; lifetime belongs to the Session process.
    let child = std::thread::spawn(move || {
        let mut command = fixture(APP, "app");
        command.stdin(Stdio::from(OwnedFd::from(app_control)));
        SessionLifetimeSource::capture_current(target())
            .unwrap()
            .inherit_into(&mut command)
            .unwrap();
        command.spawn().unwrap()
    })
    .join()
    .unwrap();
    control.write_all(&child.id().to_be_bytes()).unwrap();
    control
        .set_read_timeout(Some(Duration::from_secs(8)))
        .unwrap();
    let mut barrier = [0_u8];
    control.read_exact(&mut barrier).unwrap();
    // No wait/reap or child kill here. The real original Session now exits.
    drop(child);
}

#[test]
fn idle_app_fixture() {
    if std::env::var(ROLE).as_deref() != Ok("app") {
        return;
    }
    let lifetime = SessionLifetime::from_environment(&target())
        .unwrap()
        .unwrap();
    let ctx = egui::Context::default();
    let inherited = unsafe { BorrowedFd::borrow_raw(0) }
        .try_clone_to_owned()
        .unwrap();
    let notification = UnixDatagram::from(inherited);
    notification
        .set_write_timeout(Some(Duration::from_secs(1)))
        .unwrap();
    let (effect, _effect_owner) = UnixStream::pair().unwrap();
    let (recovery, _recovery_owner) = UnixDatagram::pair().unwrap();
    let channel = CalculatorAppChannel::from_channels(
        ctx.clone(),
        target(),
        effect,
        recovery,
        Some(lifetime),
    )
    .unwrap();
    let started = Instant::now();
    let mut frames = 0_u32;
    let mut ready = false;
    loop {
        assert!(
            started.elapsed() < Duration::from_secs(12),
            "bounded idle app fixture"
        );
        let mut closed = false;
        let input = egui::RawInput {
            time: Some(started.elapsed().as_secs_f64()),
            ..Default::default()
        };
        assert!(input.events.is_empty());
        let output = ctx.run(input, |ctx| {
            closed = channel.close_if_session_ended(ctx);
            if !closed {
                egui::CentralPanel::default().show(ctx, |ui| {
                    ui.label("Idle Calculator");
                });
            }
        });
        frames += 1;
        let viewport = &output.viewport_output[&egui::ViewportId::ROOT];
        if closed {
            assert!(ready);
            assert!(viewport.commands.contains(&egui::ViewportCommand::Close));
            assert!(!viewport
                .commands
                .contains(&egui::ViewportCommand::CancelClose));
            assert_eq!(channel.revision(), 0);
            assert!(!channel.receipt_pending());
            drop(channel);
            assert_eq!(notification.send(CLOSED).unwrap(), CLOSED.len());
            println!("CALCULATOR_IDLE_CLOSED frames={frames} input_events=0 effects=0");
            return;
        }
        let delay = viewport.repaint_delay;
        assert!(
            delay <= Duration::from_millis(100),
            "idle lifetime timer must remain bounded"
        );
        if !ready && frames >= 3 && !delay.is_zero() {
            ready = true;
            assert_eq!(notification.send(READY).unwrap(), READY.len());
            println!("CALCULATOR_IDLE_READY delay_us={}", delay.as_micros());
        }
        // The actual egui output schedules the next frame. No input, effect,
        // external repaint or out-of-band lifetime poll wakes this idle model.
        std::thread::sleep(delay.max(Duration::from_millis(1)));
    }
}

struct RunningSession(Child);
impl Drop for RunningSession {
    fn drop(&mut self) {
        let _ = self.0.kill();
        let _ = self.0.wait();
    }
}
struct HeldApp(OwnedFd);
impl Drop for HeldApp {
    fn drop(&mut self) {
        // Only the held descriptor of this fixture's real unreaped child is
        // used for cleanup; a numeric PID is never signalled after reaping.
        unsafe {
            libc::syscall(
                libc::SYS_pidfd_send_signal,
                self.0.as_raw_fd(),
                libc::SIGKILL,
                std::ptr::null::<libc::siginfo_t>(),
                0,
            );
        }
    }
}
fn notification(channel: &UnixDatagram, expected: &[u8]) {
    let mut raw = [0_u8; 64];
    let length = channel
        .recv(&mut raw)
        .expect("bounded owned fixture progress");
    assert_eq!(&raw[..length], expected);
}

#[test]
fn idle_egui_observes_original_session_exit_without_input_or_effect() {
    for killed in [false, true] {
        let (bootstrap, inherited) = UnixDatagram::pair().unwrap();
        let (mut control, session_control) = UnixStream::pair().unwrap();
        let (events, app_control) = UnixDatagram::pair().unwrap();
        control
            .set_read_timeout(Some(Duration::from_secs(8)))
            .unwrap();
        control
            .set_write_timeout(Some(Duration::from_secs(1)))
            .unwrap();
        events
            .set_read_timeout(Some(Duration::from_secs(8)))
            .unwrap();
        // Test control transports only. These carry no original owner grant,
        // app mutation or receipt and never parse human libtest stdout.
        trill_ui_core::notes_private_unix::send_channels(
            &bootstrap,
            FIXTURE,
            &session_control,
            &app_control,
            Duration::from_secs(1),
        )
        .unwrap();
        drop((session_control, app_control));
        let child = fixture(PARENT, "session")
            .stdin(Stdio::from(OwnedFd::from(inherited)))
            .stdout(Stdio::inherit())
            .spawn()
            .unwrap();
        let mut session = RunningSession(child);
        let mut pid = [0_u8; 4];
        control.read_exact(&mut pid).unwrap();
        let app_pid = u32::from_be_bytes(pid);
        notification(&events, READY);
        // Session still holds its Child and never reaps it, so this actual
        // descendant cannot have its PID recycled before opening the pidfd.
        let raw = unsafe { libc::syscall(libc::SYS_pidfd_open, app_pid, 0) };
        assert!(raw >= 0);
        let app = HeldApp(unsafe { OwnedFd::from_raw_fd(raw as i32) });
        let mut poll = libc::pollfd {
            fd: app.0.as_raw_fd(),
            events: libc::POLLIN,
            revents: 0,
        };
        assert_eq!(
            unsafe { libc::poll(&mut poll, 1, 0) },
            0,
            "idle App remains live after spawning thread exits"
        );
        if killed {
            session.0.kill().unwrap();
        } else {
            control.write_all(&[1]).unwrap();
        }
        assert_eq!(session.0.wait().unwrap().success(), !killed);
        notification(&events, CLOSED);
        assert_eq!(
            unsafe { libc::poll(&mut poll, 1, 3000) },
            1,
            "actual idle App fixture exits"
        );
    }
}
