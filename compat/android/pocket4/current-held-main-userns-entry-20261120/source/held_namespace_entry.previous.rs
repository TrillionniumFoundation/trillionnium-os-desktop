// SPDX-License-Identifier: Apache-2.0
// Execute one command through already-held namespace and root descriptors.
// No numeric target PID is used for namespace entry. This is not setuid.
#[cfg(not(all(target_os = "linux", target_arch = "x86_64")))]
compile_error!("This qualified helper is Linux x86_64 only.");

use std::collections::{BTreeMap, BTreeSet};
use std::ffi::CString;
use std::os::raw::{c_char, c_int, c_long, c_short, c_ulong};
use std::ptr;

#[repr(C)]
struct PollFd { fd: c_int, events: c_short, revents: c_short }
const _: () = assert!(std::mem::size_of::<PollFd>() == 8);
extern "C" {
    fn getpid() -> c_int;
    fn getppid() -> c_int;
    fn prctl(option: c_int, ...) -> c_int;
    fn fcntl(fd: c_int, command: c_int, ...) -> c_int;
    fn ioctl(fd: c_int, request: c_ulong, ...) -> c_int;
    fn setns(fd: c_int, namespace_type: c_int) -> c_int;
    fn fchdir(fd: c_int) -> c_int;
    fn chroot(path: *const c_char) -> c_int;
    fn chdir(path: *const c_char) -> c_int;
    fn fork() -> c_int;
    fn waitpid(pid: c_int, status: *mut c_int, options: c_int) -> c_int;
    fn poll(fds: *mut PollFd, count: c_ulong, timeout: c_int) -> c_int;
    fn syscall(number: c_long, ...) -> c_long;
    fn execve(path: *const c_char, argv: *const *const c_char,
              envp: *const *const c_char) -> c_int;
    fn close(fd: c_int) -> c_int;
    fn _exit(status: c_int) -> !;
    static mut environ: *mut *mut c_char;
}

fn fail(message: &str) -> ! {
    eprintln!("held-namespace-entry: {message}");
    std::process::exit(125);
}
fn checked(result: c_int, operation: &str) {
    if result < 0 {
        fail(&format!("{operation}: {}", std::io::Error::last_os_error()));
    }
}
fn cloexec(fd: c_int) {
    let flags = unsafe { fcntl(fd, 1) }; // F_GETFD
    checked(flags, "get FD flags");
    checked(unsafe { fcntl(fd, 2, flags | 1) }, "set FD_CLOEXEC");
}
fn main() {
    let arguments: Vec<String> = std::env::args().skip(1).collect();
    let separator = arguments.iter().position(|s| s == "--")
        .unwrap_or_else(|| fail("missing -- command separator"));
    if separator + 1 >= arguments.len() { fail("missing command"); }
    let mut values = BTreeMap::<String, c_int>::new();
    for arg in &arguments[..separator] {
        let (name, raw) = arg.split_once('=').unwrap_or_else(|| fail("expected --name=value"));
        if !["--parent-pid", "--root-fd", "--mnt-fd", "--pid-fd",
             "--uts-fd", "--ipc-fd", "--net-fd", "--cgroup-fd"].contains(&name) {
            fail("unknown option");
        }
        let value: c_int = raw.parse().unwrap_or_else(|_| fail("invalid integer"));
        if value <= 0 || (name != "--parent-pid" && value < 3) {
            fail("invalid PID or descriptor");
        }
        if values.insert(name.to_owned(), value).is_some() { fail("duplicate option"); }
    }
    let required = ["--parent-pid", "--root-fd", "--mnt-fd", "--pid-fd", "--uts-fd", "--ipc-fd"];
    for key in required { if !values.contains_key(key) { fail("missing required option"); } }
    let parent = values["--parent-pid"];
    if unsafe { getppid() } != parent { fail("unexpected launcher parent"); }
    checked(unsafe { prctl(1, 9 as c_ulong, 0 as c_ulong, 0 as c_ulong, 0 as c_ulong) },
            "set launcher parent-death signal");
    if unsafe { getppid() } != parent { fail("launcher parent exited during admission"); }

    let root = values["--root-fd"];
    let mut unique = BTreeSet::<c_int>::new();
    for (name, fd) in &values {
        if name == "--parent-pid" { continue; }
        if !unique.insert(*fd) { fail("descriptor aliases another authority"); }
        cloexec(*fd); // pass_fds cleared this flag; restore it before the final exec.
    }
    let entries = [
        ("--cgroup-fd", 0x02000000), ("--ipc-fd", 0x08000000),
        ("--uts-fd", 0x04000000), ("--net-fd", 0x40000000),
        ("--mnt-fd", 0x00020000), ("--pid-fd", 0x20000000),
    ];
    for (name, kind) in entries {
        if let Some(fd) = values.get(name) {
            let observed = unsafe { ioctl(*fd, 0xb703 as c_ulong) }; // NS_GET_NSTYPE
            checked(observed, "read namespace type");
            if observed != kind { fail("namespace descriptor has wrong type"); }
        }
    }
    let command: Vec<CString> = arguments[separator + 1..].iter()
        .map(|s| CString::new(s.as_bytes()).unwrap_or_else(|_| fail("NUL in command"))).collect();
    if !arguments[separator + 1].starts_with('/') { fail("command must be absolute"); }
    let mut argv: Vec<*const c_char> = command.iter().map(|s| s.as_ptr()).collect();
    argv.push(ptr::null());
    // A pidfd remains meaningful in the child's different PID namespace.
    // getppid() alone could become zero there and cannot close this race.
    let own_pidfd = unsafe { syscall(434, getpid() as c_long, 0 as c_long) }; // pidfd_open
    if own_pidfd < 0 || own_pidfd > c_int::MAX as c_long { fail("cannot pin entry parent"); }
    let own_pidfd = own_pidfd as c_int;
    cloexec(own_pidfd);
    for (name, kind) in entries {
        if let Some(fd) = values.get(name) {
            checked(unsafe { setns(*fd, kind) }, "enter held namespace");
        }
    }
    checked(unsafe { fchdir(root) }, "enter held root");
    checked(unsafe { chroot(b".\0".as_ptr().cast()) }, "set held root");
    checked(unsafe { chdir(b"/\0".as_ptr().cast()) }, "set root working directory");
    let child = unsafe { fork() };
    checked(child, "fork into held PID namespace");
    if child == 0 {
        checked(unsafe { prctl(1, 9 as c_ulong, 0 as c_ulong, 0 as c_ulong, 0 as c_ulong) },
                "set entry parent-death signal");
        let mut parent_poll = PollFd { fd: own_pidfd, events: 1, revents: 0 };
        let ready = unsafe { poll(&mut parent_poll, 1, 0) };
        if ready != 0 { fail("entry parent exited before command"); }
        // All namespace/root/pidfd authorities are CLOEXEC and cannot leak into
        // the Android command or its descendants.
        unsafe { execve(command[0].as_ptr(), argv.as_ptr(), environ.cast()) };
        fail(&format!("execute command: {}", std::io::Error::last_os_error()));
    }
    for fd in unique { unsafe { close(fd) }; }
    unsafe { close(own_pidfd) };
    let mut status = 0;
    loop {
        let result = unsafe { waitpid(child, &mut status, 0) };
        if result == child { break; }
        if result < 0 && std::io::Error::last_os_error().raw_os_error() == Some(4) { continue; }
        fail("cannot reap entry child");
    }
    let signal = status & 0x7f;
    let code = if signal == 0 { (status >> 8) & 0xff } else { 128 + signal };
    unsafe { _exit(code) };
}
