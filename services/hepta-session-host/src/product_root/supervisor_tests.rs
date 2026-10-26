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
