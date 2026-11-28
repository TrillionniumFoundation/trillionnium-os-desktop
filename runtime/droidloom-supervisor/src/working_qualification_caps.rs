//! Exact kernel capability states for the working owner and its fixed children.
//! All working actors retain only SETUID/SETGID for the fixed file worker
//! and SYS_PTRACE for existing read-only Main metadata. No DAC/CHOWN/SETPCAP
//! capability is granted. Children set NNP before their normal fixed entry.
use std::{
    fs::File,
    io::{self, Read},
    os::fd::AsRawFd,
};
pub(super) const BOUNDING: u64 = (1 << 6) | (1 << 7) | (1 << 19);
pub(super) const PARENT: u64 = BOUNDING;
pub(super) const CHILD: u64 = BOUNDING;
fn reject(s: &str) -> io::Error {
    io::Error::new(io::ErrorKind::PermissionDenied, s)
}
#[repr(C)]
struct Header {
    version: u32,
    pid: i32,
}
#[repr(C)]
#[derive(Clone, Copy, Default)]
struct Data {
    effective: u32,
    permitted: u32,
    inheritable: u32,
}
fn values() -> io::Result<[u64; 3]> {
    let mut h = Header {
        version: 0x2008_0522,
        pid: 0,
    };
    let mut d = [Data::default(); 2];
    if unsafe { libc::syscall(libc::SYS_capget, &mut h, d.as_mut_ptr()) } != 0 {
        return Err(io::Error::last_os_error());
    }
    Ok([
        u64::from(d[0].permitted) | (u64::from(d[1].permitted) << 32),
        u64::from(d[0].effective) | (u64::from(d[1].effective) << 32),
        u64::from(d[0].inheritable) | (u64::from(d[1].inheritable) << 32),
    ])
}
fn status() -> io::Result<String> {
    let mut raw = Vec::new();
    File::open("/proc/self/status")?
        .take(16385)
        .read_to_end(&mut raw)?;
    if raw.is_empty() || raw.len() > 16384 {
        return Err(reject("working self status exceeds source bound"));
    }
    String::from_utf8(raw).map_err(|_| reject("working self status is not UTF-8"))
}
fn one<'a>(raw: &'a str, key: &str) -> io::Result<&'a str> {
    let mut rows = raw.lines().filter_map(|l| l.strip_prefix(key));
    let value = rows
        .next()
        .ok_or_else(|| reject("working capability status field missing"))?
        .trim();
    if rows.next().is_some() {
        return Err(reject("working capability status field duplicated"));
    }
    Ok(value)
}
fn compare(raw: &str, actual: u64, one_thread: bool) -> io::Result<()> {
    for (key, mask) in [
        ("CapPrm:", actual),
        ("CapEff:", actual),
        ("CapInh:", 0),
        ("CapAmb:", 0),
        ("CapBnd:", BOUNDING),
    ] {
        let s = one(raw, key)?;
        if s.len() != 16
            || !s.bytes().all(|v| v.is_ascii_hexdigit())
            || u64::from_str_radix(s, 16).ok() != Some(mask)
        {
            return Err(reject("working exact kernel capability mask differs"));
        }
    }
    if one(raw, "TracerPid:")? != "0" || (one_thread && one(raw, "Threads:")? != "1") {
        return Err(reject(
            "working capability handoff requires an untraced sole initial thread",
        ));
    }
    Ok(())
}
fn ambient_empty() -> io::Result<()> {
    // PR_CAP_AMBIENT_CLEAR_ALL may only remove capabilities.
    if unsafe {
        libc::prctl(
            libc::PR_CAP_AMBIENT,
            libc::PR_CAP_AMBIENT_CLEAR_ALL,
            0,
            0,
            0,
        )
    } != 0
    {
        return Err(io::Error::last_os_error());
    }
    Ok(())
}
fn file_caps_absent(exe: &File) -> io::Result<()> {
    let rc = unsafe {
        libc::fgetxattr(
            exe.as_raw_fd(),
            c"security.capability".as_ptr(),
            std::ptr::null_mut(),
            0,
        )
    };
    if rc != -1 || io::Error::last_os_error().raw_os_error() != Some(libc::ENODATA) {
        return Err(reject(
            "working normal executable has file capabilities or unknown capability xattr state",
        ));
    }
    Ok(())
}
pub(super) fn seal(parent: bool, exe: &File) -> io::Result<()> {
    if unsafe {
        (
            libc::getuid(),
            libc::geteuid(),
            libc::getgid(),
            libc::getegid(),
        )
    } != (0, 0, 0, 0)
        || unsafe { libc::prctl(libc::PR_GET_SECUREBITS, 0, 0, 0, 0) } != 0
    {
        return Err(reject(
            "working capability handoff requires normal root semantics with no securebits",
        ));
    }
    file_caps_absent(exe)?;
    let want = if parent { PARENT } else { CHILD };
    let state = values()?;
    let nnp = unsafe { libc::prctl(libc::PR_GET_NO_NEW_PRIVS, 0, 0, 0, 0) };
    if state == [want, want, 0] && nnp == (if parent { 0 } else { 1 }) {
        compare(&status()?, want, true)?;
        return guard(parent);
    }
    // Normal root exec receives exactly the three unit-bounded capabilities.
    // Only the fixed child sets NNP; it can never acquire a larger set.
    if state != [BOUNDING, BOUNDING, 0] || nnp != 0 {
        return Err(reject(
            "working first capability state is not the normal fixed unit exec",
        ));
    }
    compare(&status()?, BOUNDING, true)?;
    ambient_empty()?;
    let h = Header {
        version: 0x2008_0522,
        pid: 0,
    };
    let mut d = [Data::default(); 2];
    d[0].permitted = want as u32;
    d[0].effective = want as u32;
    d[1].permitted = (want >> 32) as u32;
    d[1].effective = (want >> 32) as u32;
    if unsafe { libc::syscall(libc::SYS_capset, &h, d.as_ptr()) } != 0 {
        return Err(io::Error::last_os_error());
    }
    if !parent && unsafe { libc::prctl(libc::PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) } != 0 {
        return Err(io::Error::last_os_error());
    }
    guard(parent)
}
pub(super) fn guard(parent: bool) -> io::Result<()> {
    let want = if parent { PARENT } else { CHILD };
    // Compare the live syscall result, not a saved receipt.
    if values()? != [want, want, 0] {
        return Err(reject("working effective/permitted capabilities changed"));
    }
    let expected_nnp = if parent { 0 } else { 1 };
    if unsafe { libc::prctl(libc::PR_GET_NO_NEW_PRIVS, 0, 0, 0, 0) } != expected_nnp
        || unsafe { libc::prctl(libc::PR_GET_SECUREBITS, 0, 0, 0, 0) } != 0
    {
        return Err(reject(
            "working normal capability/NNP execution state changed",
        ));
    }
    compare(&status()?, want, false)
}
#[cfg(test)]
mod tests {
    use super::*;
    fn example(actual: u64) -> String {
        format!(
            "CapPrm:\t{actual:016x}\nCapEff:\t{actual:016x}\nCapInh:\t0000000000000000\nCapAmb:\t0000000000000000\nCapBnd:\t{BOUNDING:016x}\nTracerPid:\t0\nThreads:\t1\n"
        )
    }
    #[test]
    fn working_caps_reject_dac_chown_and_untrusted_exec_state() {
        compare(&example(PARENT), PARENT, true).unwrap();
        compare(&example(CHILD), CHILD, true).unwrap();
        assert_eq!(PARENT, CHILD);
        for forbidden in [1_u64 << 0, 1 << 1, 1 << 2, 1 << 8] {
            assert_eq!(BOUNDING & forbidden, 0);
            assert!(compare(&example(CHILD | forbidden), CHILD, true).is_err());
        }
        assert!(
            compare(
                &example(CHILD).replace("CapInh:\t0000000000000000", "CapInh:\t0000000000000004"),
                CHILD,
                true
            )
            .is_err()
        );
        assert!(
            compare(
                &example(CHILD).replace("CapAmb:\t0000000000000000", "CapAmb:\t0000000000000004"),
                CHILD,
                true
            )
            .is_err()
        );
        assert!(
            compare(
                &example(CHILD).replace("TracerPid:\t0", "TracerPid:\t123"),
                CHILD,
                true
            )
            .is_err()
        );
        assert!(
            compare(
                &example(CHILD).replace("Threads:\t1", "Threads:\t2"),
                CHILD,
                true
            )
            .is_err()
        );
        assert!(
            compare(
                &(example(CHILD) + "CapEff:\t0000000000080004\n"),
                CHILD,
                true
            )
            .is_err()
        );
        let extended = example(CHILD).replace(
            &format!("CapBnd:\t{BOUNDING:016x}"),
            &format!("CapBnd:\t{:016x}", BOUNDING | (1 << 8)),
        );
        assert!(compare(&extended, CHILD, true).is_err());
    }
}
