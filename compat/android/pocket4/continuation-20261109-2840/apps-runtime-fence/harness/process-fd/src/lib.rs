//! Visibility adapters for the same production PIDFD functions.
//! Built as a dependency so unrelated DevelopmentCell test fixtures are not loaded.
#![deny(unsafe_op_in_unsafe_fn)]

#[allow(dead_code)]
#[path = "../../../source/runtime/droidloom-supervisor/src/development_process.rs"]
mod owned_process;

pub fn open_pidfd(pid: u32) -> std::io::Result<std::os::fd::OwnedFd> {
    owned_process::open_pidfd(pid)
}

pub fn pidfd_exited(fd: &std::os::fd::OwnedFd) -> std::io::Result<bool> {
    owned_process::pidfd_exited(fd)
}
