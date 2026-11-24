//! Opt-in self-measurement for qualification; it creates no control endpoint.
use serde::Serialize;
use sha2::{Digest, Sha256};
use std::fs::{self, File, Metadata, OpenOptions};
use std::io::{self, Read, Write};
use std::os::unix::fs::{MetadataExt, OpenOptionsExt};
use std::time::{Duration, Instant};

const MAX_ELF_BYTES: u64 = 32 * 1024 * 1024;

#[derive(Debug, Eq, PartialEq, Serialize)]
struct FileIdentity {
    dev: u64,
    ino: u64,
    mode: u32,
    uid: u32,
    gid: u32,
    nlink: u64,
    size: u64,
    mtime_ns: i64,
    ctime_ns: i64,
}

fn invalid(message: &'static str) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidData, message)
}

fn timestamp(seconds: i64, nanos: i64) -> io::Result<i64> {
    if !(0..1_000_000_000).contains(&nanos) {
        return Err(invalid("self executable has an invalid timestamp"));
    }
    seconds.checked_mul(1_000_000_000).and_then(|n| n.checked_add(nanos))
        .ok_or_else(|| invalid("self executable timestamp overflow"))
}

fn identity(m: &Metadata) -> io::Result<FileIdentity> {
    Ok(FileIdentity {
        dev: m.dev(), ino: m.ino(), mode: m.mode(), uid: m.uid(), gid: m.gid(),
        nlink: m.nlink(), size: m.len(),
        mtime_ns: timestamp(m.mtime(), m.mtime_nsec())?,
        ctime_ns: timestamp(m.ctime(), m.ctime_nsec())?,
    })
}

fn small(path: &'static str, limit: u64) -> io::Result<Vec<u8>> {
    let mut bytes = Vec::new();
    File::open(path)?.take(limit + 1).read_to_end(&mut bytes)?;
    if bytes.len() as u64 > limit {
        return Err(invalid("self identity metadata exceeds its fixed bound"));
    }
    Ok(bytes)
}

fn start_ticks() -> io::Result<u64> {
    let bytes = small("/proc/self/stat", 8192)?;
    let value = std::str::from_utf8(&bytes)
        .map_err(|_| invalid("self stat is not UTF-8"))?;
    let pid = value.split_once(' ').ok_or_else(|| invalid("self stat PID missing"))?.0
        .parse::<u32>().map_err(|_| invalid("invalid self stat PID"))?;
    if pid != std::process::id() {
        return Err(invalid("self stat belongs to another process"));
    }
    let (_, rest) = value.rsplit_once(") ").ok_or_else(|| invalid("self stat command missing"))?;
    let start = rest.split_whitespace().nth(19)
        .ok_or_else(|| invalid("self start ticks missing"))?
        .parse::<u64>().map_err(|_| invalid("invalid self start ticks"))?;
    if start == 0 {
        return Err(invalid("self start ticks are zero"));
    }
    Ok(start)
}

fn context(path: &'static str) -> io::Result<String> {
    let bytes = small(path, 4096)?;
    let text = std::str::from_utf8(&bytes)
        .map_err(|_| invalid("self MAC context is not UTF-8"))?
        .trim_end_matches(['\0', '\n']);
    if text.is_empty() || text.len() > 1024 || !text.bytes().all(|b| (0x20..=0x7e).contains(&b)) {
        return Err(invalid("self MAC context is not bounded printable text"));
    }
    Ok(text.to_owned())
}

#[derive(Serialize)]
struct Observation {
    schema: &'static str,
    pid: u32,
    uid: u32,
    gid: u32,
    start_ticks: u64,
    clk_tck: i64,
    observed_ns: u64,
    invocation_id: String,
    elf_sha256: String,
    executable: FileIdentity,
    selinux: String,
    apparmor: String,
}

/// The existing trace toggle returns before any file, hash, MAC or clock work
/// when disabled. All inputs below are this process's fixed self descriptors.
pub(super) fn emit_if_enabled() -> Result<(), super::PresenterError> {
    if !*super::KEY_TRACE.get_or_init(|| {
        std::env::var_os("DROIDLOOM_INPUT_TRACE").as_deref()
            == Some(std::ffi::OsStr::new("1"))
    }) {
        return Ok(());
    }
    let started = start_ticks()?;
    let selinux = context("/proc/self/attr/current")?;
    let apparmor = context("/proc/self/attr/apparmor/current")?;
    let mut elf = OpenOptions::new().read(true).custom_flags(libc::O_CLOEXEC)
        .open("/proc/self/exe")?;
    let metadata = elf.metadata()?;
    if !metadata.is_file() || metadata.nlink() != 1 || !(4..=MAX_ELF_BYTES).contains(&metadata.len()) {
        return Err(invalid("self executable is not one bounded ordinary inode").into());
    }
    let original = identity(&metadata)?;
    let deadline = Instant::now() + Duration::from_secs(5);
    let mut sha = Sha256::new();
    let mut buffer = [0_u8; 64 * 1024];
    let mut total = 0_u64;
    loop {
        if Instant::now() >= deadline {
            return Err(invalid("self executable measurement deadline").into());
        }
        let count = elf.read(&mut buffer)?;
        if count == 0 { break; }
        if total == 0 && (count < 4 || buffer[..4] != *b"\x7fELF") {
            return Err(invalid("self executable is not ELF").into());
        }
        total = total.checked_add(count as u64)
            .filter(|n| *n <= original.size)
            .ok_or_else(|| invalid("self executable grew during measurement"))?;
        sha.update(&buffer[..count]);
    }
    if total != original.size || identity(&elf.metadata()?)? != original
        || identity(&fs::metadata("/proc/self/exe")?)? != original
        || start_ticks()? != started
        || context("/proc/self/attr/current")? != selinux
        || context("/proc/self/attr/apparmor/current")? != apparmor
    {
        return Err(invalid("self executable, process or MAC changed during measurement").into());
    }
    // SAFETY: these scalar self queries require no pointer or borrowed lifetime.
    let (uid, gid, clk_tck) = unsafe {
        (libc::geteuid(), libc::getegid(), libc::sysconf(libc::_SC_CLK_TCK))
    };
    if clk_tck <= 0 {
        return Err(invalid("self clock tick frequency is unavailable").into());
    }
    let observed = Observation {
        schema: "p4-presenter-self-identity-v1", pid: std::process::id(), uid, gid,
        start_ticks: started, clk_tck,
        observed_ns: super::monotonic_timestamp_nanos()?,
        invocation_id: std::env::var("INVOCATION_ID").unwrap_or_default(),
        elf_sha256: format!("{:x}", sha.finalize()), executable: original, selinux, apparmor,
    };
    let body = serde_json::to_string(&observed).map_err(io::Error::other)?;
    if body.len() > 4096 {
        return Err(invalid("self identity trace exceeds its fixed bound").into());
    }
    // A single bounded line in the existing unit-owned stderr stream.
    let mut stderr = io::stderr().lock();
    writeln!(stderr, "Droidloom identity trace: {body}")?;
    stderr.flush()?;
    Ok(())
}
