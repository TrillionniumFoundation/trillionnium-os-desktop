//! Real Linux controls for owned-child custody. These are not Android tests.

use super::*;
use crate::production_identity::tests::broker_fixture;
use std::fs;

fn task_children() -> String {
    // SAFETY: read-only identity query.
    let tid = unsafe { libc::syscall(libc::SYS_gettid) };
    fs::read_to_string(format!("/proc/self/task/{tid}/children")).unwrap()
}

fn fixture_lock(root: &std::path::Path) -> File {
    OpenOptions::new()
        .read(true)
        .write(true)
        .open(root.join("registry/u1000.lease"))
        .unwrap()
}

fn exclusive_available(file: &File) -> bool {
    // SAFETY: separate test FD to its owned synthetic reservation.
    let rc = unsafe { libc::flock(file.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) };
    if rc == 0 {
        unsafe {
            libc::flock(file.as_raw_fd(), libc::LOCK_UN);
        }
        true
    } else {
        assert_eq!(io::Error::last_os_error().kind(), io::ErrorKind::WouldBlock);
        false
    }
}

#[test]
fn public_entry_requires_complete_admission_without_spawning() {
    let children = task_children();
    let (root, lease) = broker_fixture();
    let record = fs::read(root.path().join("registry/u1000.json")).unwrap();
    assert!(matches!(
        prepare_user_namespace(lease),
        Err(NamespaceError::HostAdmissionRequired)
    ));
    assert_eq!(task_children(), children);
    assert_eq!(
        fs::read(root.path().join("registry/u1000.json")).unwrap(),
        record
    );
    assert!(exclusive_available(&fixture_lock(root.path())));
}

#[test]
fn actual_clone_pidfd_proc_binding_fd_scrub_and_lease_lifetime() {
    let children = task_children();
    let sentinel = tempfile::tempfile().unwrap();
    let (root, lease) = broker_fixture();
    let lock = fixture_lock(root.path());
    let mut owner = Owner::spawn(Some(lease), child::Mode::ParkOnly).unwrap();
    assert!(!exclusive_available(&lock));
    let r = owner.held().unwrap();
    assert_eq!(r.identity.unwrap().pid, r.pid);
    assert_eq!(r.identity.unwrap().parent, std::process::id());
    let descriptors: Vec<_> = fs::read_dir(format!("/proc/{}/fd", r.pid))
        .unwrap()
        .map(|p| p.unwrap().file_name())
        .collect();
    assert_eq!(descriptors, [std::ffi::OsString::from("3")]);
    assert!(sentinel.metadata().is_ok());
    owner.send(Phase::Enter).unwrap();
    owner
        .receive(Phase::Parked, None, PROTOCOL_TIMEOUT)
        .unwrap();
    owner.verify_owned().unwrap();
    assert!(owner.install_maps().is_err()); // a parked host child is never a new mapped namespace
    let pid = owner.held().unwrap().pid;
    let result = owner.retire().unwrap();
    assert_eq!(
        result,
        ChildExit {
            pid,
            reason: libc::CLD_EXITED,
            status: 0
        }
    );
    assert!(exclusive_available(&lock));
    assert_eq!(task_children(), children);
    assert!(root.path().join("registry/u1000.json").exists());
}

#[test]
fn rejected_foreign_pid_never_receives_map_writes_or_signal() {
    let mut foreign = std::process::Command::new("/usr/bin/sleep")
        .arg("20")
        .spawn()
        .unwrap();
    let foreign_pid = foreign.id();
    let foreign_map = fs::read(format!("/proc/{foreign_pid}/uid_map")).unwrap();
    let (_root, lease) = broker_fixture();
    let mut owner = Owner::spawn(Some(lease), child::Mode::ParkOnly).unwrap();
    let actual = owner.held().unwrap().pid;
    owner.held_mut().unwrap().pid = foreign_pid; // corrupt only diagnostic PID
    assert!(owner.write_owned("uid_map", b"0 200000 100000\n").is_err());
    // Even failure cleanup targets only the atomic own pidfd. Restoring the
    // expected diagnostic identity allows an exact waitid evidence assertion.
    owner.held_mut().unwrap().pid = actual;
    owner.retire().unwrap();
    assert!(foreign.try_wait().unwrap().is_none());
    assert_eq!(
        fs::read(format!("/proc/{foreign_pid}/uid_map")).unwrap(),
        foreign_map
    );
    foreign.kill().unwrap(); // std::Child created and retained by this test only
    assert!(!foreign.wait().unwrap().success());
}

#[test]
fn early_exit_and_wrong_nonce_are_reaped_without_external_adoption() {
    for mode in [child::Mode::ExitBeforeCreated, child::Mode::WrongNonce] {
        let before = task_children();
        let (_root, lease) = broker_fixture();
        assert!(Owner::spawn(Some(lease), mode).is_err());
        assert_eq!(task_children(), before);
    }
}

#[test]
fn missing_ready_has_deadline_and_pidfd_only_forced_cleanup() {
    let before = task_children();
    let (_root, lease) = broker_fixture();
    let mut owner = Owner::spawn(Some(lease), child::Mode::WithholdReady).unwrap();
    owner.send(Phase::Enter).unwrap();
    let error = owner
        .receive(Phase::Ready, None, Duration::from_millis(40))
        .err()
        .unwrap();
    assert!(matches!(error, NamespaceError::Io(ref e) if e.kind() == io::ErrorKind::TimedOut));
    let result = owner.retire().unwrap();
    assert_eq!(result.reason, libc::CLD_KILLED);
    assert_eq!(result.status, libc::SIGKILL);
    assert_eq!(task_children(), before);
}

#[test]
fn stale_reservation_rejected_before_map_and_owned_child_retires() {
    let (root, lease) = broker_fixture();
    let mut owner = Owner::spawn(Some(lease), child::Mode::ParkOnly).unwrap();
    fs::write(root.path().join("subgid"), "997:300000:100000\n").unwrap();
    assert!(matches!(
        owner.verify_owned(),
        Err(NamespaceError::Identity(_))
    ));
    let result = owner.retire().unwrap(); // teardown does not need stale map authority
    assert_eq!(result.reason, libc::CLD_EXITED);
}

#[test]
fn complete_map_readback_rejects_extra_ranges_signs_and_truncation() {
    let range = IdRange {
        start: 200000,
        count: 100000,
    };
    verify_map(b"         0     200000     100000\n", range).unwrap();
    for value in [
        &b"0 200000 100000"[..],
        &b"0 200000 100000\n0 400000 100000\n"[..],
        &b"0 +200000 100000\n"[..],
        &b"0 200000 65536\n"[..],
        &b"1 200000 100000\n"[..],
        &b"0 200001 100000\n"[..],
        &b"0 4294967296 100000\n"[..],
    ] {
        assert!(verify_map(value, range).is_err());
    }
    assert!(require_empty_groups(b"Groups:\t1000\n").is_err());
    assert!(require_empty_groups(b"Groups:\t\nGroups:\t\n").is_err());
    assert!(require_ids(b"Uid:\t200000 0 200000 200000\n", "Uid:", 200000).is_err());
}

#[test]
fn unexpected_received_fd_is_rejected_and_closed() {
    let mut raw = [-1_i32; 2];
    assert_eq!(
        unsafe {
            libc::socketpair(
                libc::AF_UNIX,
                libc::SOCK_SEQPACKET | libc::SOCK_CLOEXEC,
                0,
                raw.as_mut_ptr(),
            )
        },
        0
    );
    let receiver = unsafe { OwnedFd::from_raw_fd(raw[0]) };
    let sender = unsafe { OwnedFd::from_raw_fd(raw[1]) };
    let value = 1_i32;
    assert_eq!(
        unsafe {
            libc::setsockopt(
                receiver.as_raw_fd(),
                libc::SOL_SOCKET,
                libc::SO_PASSCRED,
                (&value as *const i32).cast(),
                std::mem::size_of::<i32>() as libc::socklen_t,
            )
        },
        0
    );
    let sentinel = tempfile::tempfile().unwrap();
    let count = || fs::read_dir("/proc/self/fd").unwrap().count();
    let before = count();
    let packet = Packet::new([9; 16], Phase::Created, 0, std::process::id());
    let mut iov = libc::iovec {
        iov_base: (&packet as *const Packet).cast_mut().cast(),
        iov_len: std::mem::size_of::<Packet>(),
    };
    let mut data = [0_usize; 8];
    let mut msg: libc::msghdr = unsafe { std::mem::zeroed() };
    msg.msg_iov = &mut iov;
    msg.msg_iovlen = 1;
    msg.msg_control = data.as_mut_ptr().cast();
    msg.msg_controllen = unsafe { libc::CMSG_SPACE(std::mem::size_of::<i32>() as u32) } as usize;
    let header = unsafe { libc::CMSG_FIRSTHDR(&msg) };
    unsafe {
        (*header).cmsg_level = libc::SOL_SOCKET;
        (*header).cmsg_type = libc::SCM_RIGHTS;
        (*header).cmsg_len = libc::CMSG_LEN(std::mem::size_of::<i32>() as u32) as usize;
        std::ptr::write_unaligned(libc::CMSG_DATA(header).cast::<i32>(), sentinel.as_raw_fd());
        assert_eq!(
            libc::sendmsg(sender.as_raw_fd(), &msg, libc::MSG_NOSIGNAL),
            std::mem::size_of::<Packet>() as isize
        );
    }
    assert!(receive_packet(receiver.as_raw_fd()).is_err());
    assert_eq!(count(), before);
    assert!(sentinel.metadata().is_ok());
}

// This must be run separately, only after the actual source and private
// namespace scope have been approved. It does not construct a HostAdmission
// token, call the production entry point, write host grants or run Android.
#[test]
#[ignore = "requires separately approved root private-userns syscall controls"]
fn privileged_private_userns_mapping_controls() {
    assert_eq!(unsafe { libc::geteuid() }, 0);
    let original_uidmap = fs::read("/proc/self/uid_map").unwrap();
    let original_gidmap = fs::read("/proc/self/gid_map").unwrap();
    let original_groups = status_field(&fs::read("/proc/self/status").unwrap(), "Groups:")
        .unwrap()
        .to_owned();
    let before = task_children();
    let (root, lease) = broker_fixture();
    let lock = fixture_lock(root.path());
    let mut owner = Owner::spawn(Some(lease), child::Mode::GroupControl).unwrap();
    owner.enter_userns().unwrap();
    {
        let witness = owner.witness().unwrap();
        witness.revalidate().unwrap();
        assert_eq!(witness.host_pid(), owner.held().unwrap().pid);
        assert_eq!(
            witness.start_ticks(),
            owner.held().unwrap().identity.unwrap().start_ticks
        );
        assert_eq!(
            witness.pidfd().as_raw_fd(),
            owner.held().unwrap().pidfd.as_raw_fd()
        );
        assert!(
            read_proc(witness.proc_directory(), "uid_map")
                .unwrap()
                .is_empty()
        );
        assert_eq!(
            Node::of(witness.user_namespace()).unwrap(),
            Node::of(owner.held().unwrap().userns.as_ref().unwrap()).unwrap()
        );
    }
    assert!(owner.write_owned("setgroups", b"deny\n").is_err());
    assert!(owner.write_owned("uid_map", b"0 300000 100000\n").is_err());
    assert!(owner.write_owned("gid_map", b"0 200000 100000\n").is_err());
    let held = owner.held().unwrap();
    assert!(
        read_proc(held.proc_dir.as_ref().unwrap(), "uid_map")
            .unwrap()
            .is_empty()
    );
    assert!(
        read_proc(held.proc_dir.as_ref().unwrap(), "gid_map")
            .unwrap()
            .is_empty()
    );
    let (uids, gids) = owner.install_maps().unwrap();
    assert!(owner.install_maps().is_err()); // cannot map twice
    owner.mapped_go(uids, gids).unwrap();
    owner.send(Phase::ProbeGroups).unwrap();
    owner
        .receive(
            Phase::GroupsSet,
            Some((uids.start, gids.start)),
            PROTOCOL_TIMEOUT,
        )
        .unwrap();
    let held = owner.held().unwrap();
    let status = read_proc(held.proc_dir.as_ref().unwrap(), "status").unwrap();
    let groups: Vec<u32> = status_field(&status, "Groups:")
        .unwrap()
        .split_ascii_whitespace()
        .map(|s| s.parse().unwrap())
        .collect();
    assert_eq!(groups, [gids.start + 1, gids.start + 99999]);
    assert_eq!(
        read_proc(held.proc_dir.as_ref().unwrap(), "setgroups").unwrap(),
        b"allow\n"
    );
    owner.send(Phase::ClearGroups).unwrap();
    owner
        .receive(
            Phase::GroupsCleared,
            Some((uids.start, gids.start)),
            PROTOCOL_TIMEOUT,
        )
        .unwrap();
    require_empty_groups(
        &read_proc(owner.held().unwrap().proc_dir.as_ref().unwrap(), "status").unwrap(),
    )
    .unwrap();
    // The actual child's namespace must not satisfy the parent's initial-root gate.
    assert!(require_initial_userns(owner.held().unwrap().userns.as_ref().unwrap()).is_err());
    let r = owner.held().unwrap();
    let pid = r.pid;
    let inode = Node::of(r.userns.as_ref().unwrap()).unwrap().inode;
    let start = r.identity.unwrap().start_ticks;
    assert!(!exclusive_available(&lock));
    let fd_names: Vec<_> = fs::read_dir(format!("/proc/{pid}/fd"))
        .unwrap()
        .map(|p| p.unwrap().file_name())
        .collect();
    assert_eq!(fd_names, [std::ffi::OsString::from("3")]);
    let report = owner.retire().unwrap();
    assert_eq!(
        report,
        ChildExit {
            pid,
            status: 0,
            reason: libc::CLD_EXITED
        }
    );
    assert!(exclusive_available(&lock));
    assert_eq!(task_children(), before);
    assert_eq!(fs::read("/proc/self/uid_map").unwrap(), original_uidmap);
    assert_eq!(fs::read("/proc/self/gid_map").unwrap(), original_gidmap);
    assert_eq!(
        status_field(&fs::read("/proc/self/status").unwrap(), "Groups:").unwrap(),
        original_groups
    );
    assert!(root.path().join("registry/u1000.json").exists());
    println!(
        "private syscall control: pid={pid} start_ticks={start} userns_inode={inode}; held lease, exact maps and allow read back; mapped supplementary groups set/read/cleared; wrong map/order and repeat rejected; exit reaped; host maps/groups unchanged; production admission=false Android=0"
    );

    // A changed authority after the child exists must block maps, then retire
    // that same child without using the stale authority for teardown.
    let (root2, lease2) = broker_fixture();
    let mut rejected = Owner::spawn(Some(lease2), child::Mode::UserNamespace).unwrap();
    rejected.enter_userns().unwrap();
    fs::write(
        root2.path().join("subuid"),
        "droidloom-cell-u1000:300000:100000\n",
    )
    .unwrap();
    assert!(matches!(
        rejected.install_maps(),
        Err(NamespaceError::Identity(_))
    ));
    assert_eq!(rejected.retire().unwrap().reason, libc::CLD_EXITED);
    assert_eq!(task_children(), before);
    // Confirm an ordinary public call remains blocked, including under root.
    let (_root3, lease3) = broker_fixture();
    assert!(matches!(
        prepare_user_namespace(lease3),
        Err(NamespaceError::HostAdmissionRequired)
    ));
    println!(
        "changed selected authority rejected with no map; fixed owned child retired; root public entry remains blocked"
    );
}
