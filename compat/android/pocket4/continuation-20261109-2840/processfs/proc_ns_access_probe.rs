//! Ordinary-UID regression for the exact proc namespace directory access mode.
//! Changes only this process's dumpability, restores it, and opens only self.
use std::ffi::CString;
use std::fs;
use std::os::fd::{AsRawFd, FromRawFd, OwnedFd};
use std::os::unix::fs::MetadataExt;

const O_RDONLY: i32 = 0;
const O_DIRECTORY: i32 = 0x1_0000;
const O_NOFOLLOW: i32 = 0x2_0000;
const O_CLOEXEC: i32 = 0x8_0000;
const O_PATH: i32 = 0x20_0000;
const PR_GET_DUMPABLE: i32 = 3;
const PR_SET_DUMPABLE: i32 = 4;
const NS_GET_NSTYPE: usize = 0xb703;
const CLONE_NEWPID: i32 = 0x2000_0000;

unsafe extern "C" {
    fn openat(dirfd: i32, path: *const i8, flags: i32, ...) -> i32;
    fn prctl(option: i32, ...) -> i32;
    fn ioctl(fd: i32, request: usize, ...) -> i32;
    fn geteuid() -> u32;
}

fn opened(parent: i32, name: &str, flags: i32) -> Result<OwnedFd, i32> {
    let name = CString::new(name).map_err(|_| 22)?;
    let fd = unsafe { openat(parent, name.as_ptr(), flags | O_CLOEXEC | O_NOFOLLOW, 0_u32) };
    if fd < 0 {
        Err(std::io::Error::last_os_error().raw_os_error().unwrap_or(5))
    } else {
        Ok(unsafe { OwnedFd::from_raw_fd(fd) })
    }
}

struct DumpableGuard(i32);
impl Drop for DumpableGuard {
    fn drop(&mut self) {
        unsafe { prctl(PR_SET_DUMPABLE, self.0 as usize, 0_usize, 0_usize, 0_usize) };
    }
}

fn run() -> Result<(), String> {
    let uid = unsafe { geteuid() };
    if uid == 0 {
        return Err("requires an ordinary UID".into());
    }
    let status = fs::read_to_string("/proc/self/status").map_err(|e| e.to_string())?;
    if !status.lines().any(|l| l == "CapEff:\t0000000000000000") {
        return Err("requires zero effective capabilities".into());
    }
    let initial = unsafe { prctl(PR_GET_DUMPABLE, 0_usize, 0_usize, 0_usize, 0_usize) };
    if initial != 1 {
        return Err(format!("unexpected initial dumpability {initial}"));
    }
    let root = fs::File::open("/proc").map_err(|e| e.to_string())?;
    let one = opened(root.as_raw_fd(), &std::process::id().to_string(), O_RDONLY | O_DIRECTORY)
        .map_err(|e| format!("open owned pid: {e}"))?;
    drop(opened(one.as_raw_fd(), "ns", O_RDONLY | O_DIRECTORY)
        .map_err(|e| format!("dumpable baseline: {e}"))?);

    let guard = DumpableGuard(initial);
    if unsafe { prctl(PR_SET_DUMPABLE, 0_usize, 0_usize, 0_usize, 0_usize) } != 0 {
        return Err("cannot set own dumpability to zero".into());
    }
    let ns_metadata = fs::metadata("/proc/self/ns").map_err(|e| e.to_string())?;
    if ns_metadata.mode() & 0o777 != 0o511 || ns_metadata.uid() == uid {
        return Err(format!("unexpected protected namespace directory mode/owner: {:o}/{}", ns_metadata.mode(), ns_metadata.uid()));
    }
    match opened(one.as_raw_fd(), "ns", O_RDONLY | O_DIRECTORY) {
        Err(13) => {}
        Err(e) => return Err(format!("old mode returned errno {e}, wanted EACCES")),
        Ok(_) => return Err("old mode unexpectedly obtained read authority".into()),
    }
    let ns = opened(one.as_raw_fd(), "ns", O_PATH | O_DIRECTORY)
        .map_err(|e| format!("path-only directory open: {e}"))?;
    let name = CString::new("pid").unwrap();
    let pid = unsafe { openat(ns.as_raw_fd(), name.as_ptr(), O_RDONLY | O_CLOEXEC, 0_u32) };
    if pid < 0 {
        return Err(format!("fixed self namespace link: {}", std::io::Error::last_os_error()));
    }
    let pid = unsafe { OwnedFd::from_raw_fd(pid) };
    if unsafe { ioctl(pid.as_raw_fd(), NS_GET_NSTYPE, 0_usize) } != CLONE_NEWPID {
        return Err("opened namespace is not a PID namespace".into());
    }
    let actual = fs::File::from(pid).metadata().map_err(|e| e.to_string())?;
    let expected = fs::metadata("/proc/self/ns/pid").map_err(|e| e.to_string())?;
    if (actual.dev(), actual.ino()) != (expected.dev(), expected.ino()) {
        return Err("opened namespace identity mismatch".into());
    }
    drop(guard);
    if unsafe { prctl(PR_GET_DUMPABLE, 0_usize, 0_usize, 0_usize, 0_usize) } != initial {
        return Err("own dumpability restoration failed".into());
    }
    drop(opened(one.as_raw_fd(), "ns", O_RDONLY | O_DIRECTORY)
        .map_err(|e| format!("restored baseline: {e}"))?);
    println!("{{\"passed\":true,\"euid\":{uid},\"effective_capabilities\":0,\"initial_dumpable\":{initial},\"nondumpable_ns_owner\":{},\"nondumpable_ns_mode\":\"0511\",\"old_open_errno\":13,\"path_only_open_passed\":true,\"pid_namespace_type_and_identity_matched\":true,\"dumpable_restored\":true,\"Android_starts\":0,\"private_namespace_controls\":0,\"production_ready\":false}}", ns_metadata.uid());
    Ok(())
}

fn main() {
    if let Err(e) = run() {
        eprintln!("proc namespace access regression failed: {e}");
        std::process::exit(1);
    }
}
