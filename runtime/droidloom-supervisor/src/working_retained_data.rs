//! Fixed normal read-only retained-original helper. It has no PM operation,
//! public APK reader, account-data writer, namespace entry or arbitrary path.
use crate::control::working_retained_peer as peer;
use crate::control::{
    DEFAULT_CONTROL_SOCKET, NativeApplicationInspector, working_install_peer::WorkingInstallPeer,
};
use crate::native_leaf_baseline_data::working_main::HeldWorkingMain;
use crate::native_working_contract::retained_data as c;
use crate::physical_qualification_channel::working_runtime::boot::BootOwner;
use crate::working_retained_originals::RetainedOriginalLease;
use crate::working_retained_wire::{self as wire, Frame};
use std::{
    io,
    os::{fd::FromRawFd, unix::net::UnixStream},
    path::Path,
    time::{Duration, Instant},
};
fn reject(why: impl Into<String>) -> io::Error {
    io::Error::new(io::ErrorKind::PermissionDenied, why.into())
}
#[repr(C)]
struct CapHeader {
    version: u32,
    pid: i32,
}
#[repr(C)]
#[derive(Default, Clone, Copy)]
struct CapData {
    effective: u32,
    permitted: u32,
    inheritable: u32,
}
fn reduce_capabilities() -> io::Result<()> {
    let header = CapHeader {
        version: 0x2008_0522,
        pid: 0,
    };
    let mut caps = [CapData::default(); 2];
    if unsafe { libc::syscall(libc::SYS_capget, &header, caps.as_mut_ptr()) } != 0 {
        return Err(io::Error::last_os_error());
    }
    // proc magic-link read checks can require the existing host observer's
    // CAP_SYS_PTRACE. No new capability is gained; all filesystem/uid/mount/
    // administration capabilities are dropped. MAC still forbids ptrace attach.
    caps[0].permitted &= 1 << 19;
    caps[0].effective = caps[0].permitted;
    caps[0].inheritable = 0;
    caps[1] = CapData::default();
    if unsafe { libc::syscall(libc::SYS_capset, &header, caps.as_ptr()) } != 0
        || unsafe {
            libc::prctl(
                libc::PR_CAP_AMBIENT,
                libc::PR_CAP_AMBIENT_CLEAR_ALL,
                0,
                0,
                0,
            )
        } != 0
        || unsafe { libc::prctl(libc::PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) } != 0
    {
        return Err(io::Error::last_os_error());
    }
    check_capabilities()
}
fn check_capabilities() -> io::Result<()> {
    let header = CapHeader {
        version: 0x2008_0522,
        pid: 0,
    };
    let mut caps = [CapData::default(); 2];
    if unsafe { libc::syscall(libc::SYS_capget, &header, caps.as_mut_ptr()) } != 0 {
        return Err(io::Error::last_os_error());
    }
    if caps[0].effective & !(1 << 19) != 0
        || caps[0].permitted & !(1 << 19) != 0
        || caps[0].inheritable != 0
        || caps[1].effective | caps[1].permitted | caps[1].inheritable != 0
        || unsafe { libc::prctl(libc::PR_GET_NO_NEW_PRIVS, 0, 0, 0, 0) } != 1
    {
        return Err(reject("retained helper capability boundary changed"));
    }
    Ok(())
}
fn execute() -> io::Result<()> {
    let args = std::env::args_os().collect::<Vec<_>>();
    if args.len() != 2 || args[0] != c::HELPER_PATH || args[1] != peer::ARG {
        return Err(reject(
            "retained helper requires its single fixed normal entry",
        ));
    }
    if crate::native_hardware_label::current(101)? != peer::ROLE
        || crate::native_hardware_label::current(104)? != peer::PROFILE
    {
        return Err(reject(
            "retained helper lacks its actual normal MAC transition",
        ));
    }
    reduce_capabilities()?;
    let socket = unsafe { UnixStream::from_raw_fd(3) };
    wire::prepare(&socket)?;
    let initial = Instant::now() + Duration::from_secs(10);
    let parent =
        WorkingInstallPeer::capture(&socket, initial).map_err(|e| reject(e.to_string()))?;
    let parent_pid = unsafe { libc::getppid() } as u32;
    if unsafe { libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGKILL, 0, 0, 0) } != 0 {
        return Err(io::Error::last_os_error());
    }
    if unsafe { libc::getppid() } as u32 != parent_pid {
        return Err(reject("retained actual parent died during post-exec setup"));
    }
    if parent.pid() != parent_pid {
        return Err(reject("retained private creator is not the actual parent"));
    }
    let first = wire::receive(&socket, parent_pid, initial, &mut || {
        parent.guard().map_err(|e| reject(e.to_string()))
    })?;
    let Frame::Begin {
        schema,
        candidate_id,
        preparation_end_ns,
        helper_end_ns,
        main: expected,
    } = first
    else {
        return Err(reject("retained helper requires Begin"));
    };
    let now = wire::clock()?;
    if schema != wire::SCHEMA
        || !c::digest(&candidate_id)
        || helper_end_ns > preparation_end_ns
        || helper_end_ns <= now
        || helper_end_ns - now > c::RETAINED_HELPER_SECONDS * 1_000_000_000
    {
        return Err(reject(
            "retained helper original absolute window/schema differs",
        ));
    }
    let end = wire::until(helper_end_ns)?;
    let boot = BootOwner::for_retained_data()?;
    if boot.config().candidate_id != candidate_id {
        return Err(reject(
            "retained helper belongs to another actual working boot",
        ));
    }
    let mut inspector =
        NativeApplicationInspector::acquire_until(Path::new(DEFAULT_CONTROL_SOCKET), end)
            .map_err(|e| reject(e.to_string()))?;
    let main = inspector
        .observe_current_main_until(end)
        .map_err(|e| reject(e.to_string()))?;
    if main.facts() != &expected {
        return Err(reject(
            "retained helper independently observed another complete actual Main",
        ));
    }
    boot.compare_main(&main)?;
    let held = HeldWorkingMain::capture(&main)?;
    let spec = boot.retained_spec()?;
    let originals = RetainedOriginalLease::capture(spec, &main, end)?;
    let mut guard = || {
        check_capabilities()?;
        parent.guard().map_err(|e| reject(e.to_string()))?;
        boot.compare_main(&main)?;
        held.guard()?;
        originals.guard(&main, end)
    };
    guard()?;
    wire::send(
        &socket,
        &Frame::Ready {
            schema: wire::SCHEMA.into(),
            main: main.facts().clone(),
        },
        end,
        &mut guard,
    )?;
    if !matches!(
        wire::receive(&socket, parent_pid, end, &mut guard)?,
        Frame::Finish {}
    ) {
        return Err(reject("retained helper expected fixed Finish"));
    }
    guard()?;
    drop(guard);
    let after = inspector
        .refresh_main_until(&main, end)
        .map_err(|e| reject(e.to_string()))?;
    if after.facts() != main.facts() {
        return Err(reject("retained final actual Main differs"));
    }
    boot.compare_main(&after)?;
    held.guard()?;
    originals.hash_pair(end)?;
    originals.guard(&after, end)?;
    let mut guard = || {
        check_capabilities()?;
        parent.guard().map_err(|e| reject(e.to_string()))?;
        boot.compare_main(&after)?;
        held.guard()?;
        originals.guard(&after, end)
    };
    wire::send(
        &socket,
        &Frame::Finished {
            schema: wire::SCHEMA.into(),
            main: after.facts().clone(),
        },
        end,
        &mut guard,
    )?;
    if !matches!(
        wire::receive(&socket, parent_pid, end, &mut guard)?,
        Frame::Retire {}
    ) {
        return Err(reject("retained helper expected fixed Retire"));
    }
    guard()?;
    Ok(())
}
/// The separate installed ELF invokes exactly this source entry.
pub fn run() -> i32 {
    match execute() {
        Ok(()) => 0,
        Err(error) => {
            eprintln!("droidloom retained original helper rejected: {error}");
            1
        }
    }
}
