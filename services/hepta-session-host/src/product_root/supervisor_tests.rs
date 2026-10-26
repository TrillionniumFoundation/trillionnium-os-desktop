//! Actual FD lifecycle fixtures; no child, authority, Registry or Root is made.
use super::*;
use std::os::fd::AsFd;
use std::os::unix::net::UnixDatagram;

fn flags(fd: i32) -> i32 {
    // SAFETY: each caller holds the live descriptor for this observation.
    unsafe { libc::fcntl(fd, libc::F_GETFD) }
}

#[test]
fn partial_inheritance_failure_restores_the_first_original_cloexec_bit() {
    let (first, second) = UnixDatagram::pair().unwrap();
    let before = flags(first.as_raw_fd());
    let original_second = flags(second.as_raw_fd());
    assert_ne!(before & libc::FD_CLOEXEC, 0);
    // SAFETY: mutate only this freshly created test-owned second descriptor.
    assert_eq!(
        unsafe {
            libc::fcntl(
                second.as_raw_fd(),
                libc::F_SETFD,
                original_second & !libc::FD_CLOEXEC,
            )
        },
        0
    );
    assert!(InheritOnce::new(&[first.as_fd(), second.as_fd()]).is_err());
    assert_eq!(flags(first.as_raw_fd()), before);
}

#[test]
fn duplicate_inherited_slot_is_rejected_without_leaving_a_transferable_alias() {
    let (first, _peer) = UnixDatagram::pair().unwrap();
    let before = flags(first.as_raw_fd());
    assert!(InheritOnce::new(&[first.as_fd(), first.as_fd()]).is_err());
    assert_eq!(flags(first.as_raw_fd()), before);
}

fn spawn_spec(command: AgentCommand) -> SpawnSpec {
    let agent = AgentId::parse("a77c44fb-0e69-41f1-8eb8-4d4b9ef6d8b1").unwrap();
    let root = std::path::PathBuf::from("/unused-original-spawn-guard");
    SpawnSpec {
        agent_id: agent,
        generation: 1,
        fleet_root: root.clone(),
        workspace: root.clone(),
        home_root: root.clone(),
        run_root: root.clone(),
        control_socket: root.join("control.sock"),
        logs_root: root.join("logs"),
        command,
    }
}

#[test]
fn historical_recovery_cannot_spawn_or_reuse_a_new_descriptor_episode() {
    let command = AgentCommand::new("/definitely-absent-original-program", Vec::new()).unwrap();
    let armed = std::sync::Arc::new(std::sync::atomic::AtomicBool::new(false));
    let mut driver = OneOriginalSpawn {
        driver: UnixProcessDriver::new(256).unwrap(),
        consumed: false,
        armed: armed.clone(),
        command: command.clone(),
    };
    assert!(driver.spawn(&spawn_spec(command.clone())).is_err());
    assert!(
        !driver.consumed,
        "historical recovery never entered the original process driver"
    );
    armed.store(true, std::sync::atomic::Ordering::Release);
    assert!(driver.spawn(&spawn_spec(command.clone())).is_err());
    assert!(
        driver.consumed,
        "even failed original spawn consumes the episode"
    );
    armed.store(true, std::sync::atomic::Ordering::Release);
    assert!(driver.spawn(&spawn_spec(command)).is_err());
}

#[test]
fn changed_original_command_consumes_the_arm_before_any_child_can_start() {
    let command = AgentCommand::new("/definitely-absent-original-program", Vec::new()).unwrap();
    let armed = std::sync::Arc::new(std::sync::atomic::AtomicBool::new(true));
    let mut driver = OneOriginalSpawn {
        driver: UnixProcessDriver::new(256).unwrap(),
        consumed: false,
        armed: armed.clone(),
        command: command.clone(),
    };
    let different = AgentCommand::new("/bin/true", Vec::new()).unwrap();
    assert!(driver.spawn(&spawn_spec(different)).is_err());
    assert!(!armed.load(std::sync::atomic::Ordering::Acquire));
    assert!(
        !driver.consumed,
        "the original driver was never entered with changed input"
    );
    assert!(driver.spawn(&spawn_spec(command)).is_err());
}
