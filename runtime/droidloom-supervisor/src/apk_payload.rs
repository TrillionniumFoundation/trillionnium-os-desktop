//! Fixed, immutable original APK bytes for the public installer.
//! This is a transport container, never an APK rewrite. The selected client
//! creates one non-executable memfd; the broker receives only its sealed,
//! read-only description and never opens a caller's home or temporary path.
use super::{ControlError, apk, io_error};
use sha2::{Digest, Sha256};
use std::fs::{File, Metadata, OpenOptions};
use std::io::{self, Write};
use std::os::fd::{AsRawFd, FromRawFd};
use std::os::unix::fs::{FileExt, MetadataExt, OpenOptionsExt};
use std::path::PathBuf;
use std::time::{Duration, Instant};

const NAME: &std::ffi::CStr = c"droidloom-apk-payload";
const MAX_BYTES: u64 = 2 * 1024 * 1024 * 1024;
const PREPARE_LIMIT: Duration = Duration::from_secs(120);
// Stable Linux UAPI, also present in the final shared kernel's memfd.h.
const MFD_NOEXEC_SEAL: libc::c_uint = 0x0008;
const F_SEAL_EXEC: libc::c_int = 0x0020;
const REQUIRED_SEALS: libc::c_int =
    libc::F_SEAL_SEAL | libc::F_SEAL_SHRINK | libc::F_SEAL_GROW | libc::F_SEAL_WRITE;
const PAYLOAD_CONTEXT: &[u8] = b"u:object_r:droidloom_apk_payload:s0";

fn invalid(message: impl Into<String>) -> ControlError {
    ControlError::Invalid(message.into())
}
fn before(deadline: Instant) -> Result<(), ControlError> {
    if Instant::now() >= deadline {
        return Err(invalid("original APK capture deadline expired"));
    }
    super::physical_qualification_channel::working_runtime::progress()
        .map_err(invalid)
}
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct Node {
    values: [u64; 7],
    times: [i64; 4],
}
fn node(m: &Metadata) -> Node {
    Node {
        values: [
            m.dev(),
            m.ino(),
            m.mode() as u64,
            m.uid() as u64,
            m.gid() as u64,
            m.nlink(),
            m.len(),
        ],
        times: [m.mtime(), m.mtime_nsec(), m.ctime(), m.ctime_nsec()],
    }
}
fn observe(file: &File) -> Result<Node, ControlError> {
    file.metadata()
        .map(|m| node(&m))
        .map_err(|e| io_error("observe original APK", e))
}
fn hash(
    file: &File,
    offset: u64,
    length: u64,
    deadline: Instant,
) -> Result<[u8; 32], ControlError> {
    let mut h = Sha256::new();
    let mut buffer = [0_u8; 64 * 1024];
    let mut done = 0;
    while done < length {
        before(deadline)?;
        let count =
            usize::try_from((length - done).min(buffer.len() as u64)).expect("bounded chunk");
        file.read_exact_at(&mut buffer[..count], offset + done)
            .map_err(|e| io_error("read complete original APK", e))?;
        h.update(&buffer[..count]);
        done += count as u64;
    }
    Ok(h.finalize().into())
}
fn create() -> Result<File, ControlError> {
    // SAFETY: NAME is a source-owned, terminated literal; no pointer is retained.
    let fd = unsafe {
        libc::memfd_create(
            NAME.as_ptr(),
            libc::MFD_CLOEXEC | libc::MFD_ALLOW_SEALING | MFD_NOEXEC_SEAL,
        )
    };
    if fd < 0 {
        return Err(io_error(
            "create non-executable APK payload",
            io::Error::last_os_error(),
        ));
    }
    // SAFETY: the successful syscall transfers one new descriptor.
    Ok(unsafe { File::from_raw_fd(fd) })
}
fn seal(writer: File) -> Result<File, ControlError> {
    writer
        .sync_all()
        .map_err(|e| io_error("finish original APK payload", e))?;
    // SAFETY: F_ADD_SEALS accepts a scalar mask on this live owned descriptor.
    if unsafe { libc::fcntl(writer.as_raw_fd(), libc::F_ADD_SEALS, REQUIRED_SEALS) } != 0 {
        return Err(io_error(
            "seal original APK payload",
            io::Error::last_os_error(),
        ));
    }
    // A dup preserves O_RDWR, so open a new description of this held memfd.
    // Only our actual numeric descriptor is formatted, never a caller path.
    let readonly = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_CLOEXEC)
        .open(format!("/proc/self/fd/{}", writer.as_raw_fd()))
        .map_err(|e| io_error("reopen sealed APK payload read-only", e))?;
    if observe(&readonly)? != observe(&writer)? {
        return Err(invalid(
            "read-only APK description is not the original sealed inode",
        ));
    }
    drop(writer);
    Ok(readonly)
}

/// Both public CLI forms use this exact original-byte transport.
pub(crate) fn prepare(paths: &[PathBuf]) -> Result<(File, Vec<u64>), ControlError> {
    prepare_bound(SourceInputs::Paths(paths), Instant::now() + PREPARE_LIMIT)
}

/// Source-admitted whole-file comparisons, still using the original sealed
/// descriptor transport and the caller's one absolute preparation deadline.
pub(crate) fn prepare_pinned_until(
    files: &[&File],
    expected: &[(u64, [u8; 32])],
    deadline: Instant,
) -> Result<(File, Vec<u64>), ControlError> {
    if files.len() != expected.len() {
        return Err(invalid("complete APK paths and source pins differ"));
    }
    prepare_bound(SourceInputs::Pinned(files, expected), deadline)
}

enum SourceInputs<'a> {
    Paths(&'a [PathBuf]),
    Pinned(&'a [&'a File], &'a [(u64, [u8; 32])]),
}
fn prepare_bound(
    source: SourceInputs<'_>,
    caller_deadline: Instant,
) -> Result<(File, Vec<u64>), ControlError> {
    let count=match &source { SourceInputs::Paths(p)=>p.len(), SourceInputs::Pinned(f,_)=>f.len() };
    if !(1..=32).contains(&count) {
        return Err(invalid("supply one through 32 original APK files"));
    }
    let deadline = (Instant::now() + PREPARE_LIMIT).min(caller_deadline);
    let mut inputs = Vec::with_capacity(count);
    let mut lengths = Vec::with_capacity(count);
    let mut total = 0_u64;
    for index in 0..count {
        before(deadline)?;
        let file = match &source {
            SourceInputs::Paths(paths)=>OpenOptions::new().read(true)
                .custom_flags(libc::O_NONBLOCK | libc::O_CLOEXEC).open(&paths[index]),
            SourceInputs::Pinned(files,_)=>files[index].try_clone(),
        }.map_err(|e| io_error("open original APK with caller permissions", e))?;
        let original = observe(&file)?;
        let length = apk::validate(&file)?;
        total = total
            .checked_add(length)
            .filter(|n| *n <= MAX_BYTES)
            .ok_or_else(|| invalid("complete original APK set exceeds 2 GiB"))?;
        let digest = hash(&file, 0, length, deadline)?;
        if matches!(&source, SourceInputs::Pinned(_, pins) if pins[index] != (length, digest)) {
            return Err(invalid("original APK differs from the complete source-admitted bytes"));
        }
        if observe(&file)? != original {
            return Err(invalid("original APK changed during initial capture"));
        }
        inputs.push((file, original, digest));
        lengths.push(length);
    }
    let mut writer = create()?;
    let mut offset = 0;
    let mut buffer = [0_u8; 64 * 1024];
    for ((file, original, expected), length) in inputs.iter().zip(&lengths) {
        if observe(file)? != *original {
            return Err(invalid("original APK changed before payload copy"));
        }
        let mut copied = 0;
        let mut h = Sha256::new();
        while copied < *length {
            before(deadline)?;
            let count = usize::try_from((*length - copied).min(buffer.len() as u64))
                .expect("bounded chunk");
            file.read_exact_at(&mut buffer[..count], copied)
                .map_err(|e| io_error("read original APK for payload", e))?;
            writer
                .write_all(&buffer[..count])
                .map_err(|e| io_error("write original APK payload", e))?;
            h.update(&buffer[..count]);
            copied += count as u64;
        }
        if <[u8; 32]>::from(h.finalize()) != *expected
            || observe(file)? != *original
            || hash(file, 0, *length, deadline)? != *expected
            || observe(file)? != *original
        {
            return Err(invalid(
                "original APK bytes or metadata changed during payload copy",
            ));
        }
        // Independently read back the copied segment, not only the source.
        if hash(&writer, offset, *length, deadline)? != *expected {
            return Err(invalid(
                "copied APK payload differs from its original segment",
            ));
        }
        offset += *length;
    }
    if writer
        .metadata()
        .map_err(|e| io_error("measure APK payload", e))?
        .len()
        != total
    {
        return Err(invalid(
            "original APK payload is truncated or has trailing bytes",
        ));
    }
    let readonly = seal(writer)?;
    validate(&readonly, &lengths)?;
    for ((file, original, expected), length) in inputs.iter().zip(&lengths) {
        if observe(file)? != *original
            || hash(file, 0, *length, deadline)? != *expected
            || observe(file)? != *original
        {
            return Err(invalid(
                "original APK changed before sealed payload publication",
            ));
        }
    }
    before(deadline)?;
    Ok((readonly, lengths))
}

/// Actual descriptor admission, shared by sender and early receiver.
pub(crate) fn validate(file: &File, lengths: &[u64]) -> Result<(), ControlError> {
    if !(1..=32).contains(&lengths.len()) {
        return Err(invalid("sealed APK payload has an invalid segment count"));
    }
    let total = lengths.iter().try_fold(0_u64, |total, length| {
        if *length < 4 {
            return Err(invalid("APK segment is shorter than its ZIP header"));
        }
        total
            .checked_add(*length)
            .filter(|n| *n <= MAX_BYTES)
            .ok_or_else(|| invalid("sealed APK payload exceeds 2 GiB"))
    })?;
    let m = file
        .metadata()
        .map_err(|e| io_error("inspect sealed APK payload", e))?;
    if !m.is_file() || m.nlink() != 0 || m.mode() & 0o111 != 0 || m.len() != total {
        return Err(invalid(
            "APK input is not one complete non-executable anonymous payload",
        ));
    }
    // SAFETY: both fcntl commands return scalar properties of this live FD.
    let flags = unsafe { libc::fcntl(file.as_raw_fd(), libc::F_GETFL) };
    let seals = unsafe { libc::fcntl(file.as_raw_fd(), libc::F_GET_SEALS) };
    if flags < 0
        || flags & (libc::O_ACCMODE | libc::O_PATH) != libc::O_RDONLY
        || seals < 0
        || seals & REQUIRED_SEALS != REQUIRED_SEALS
        || seals & F_SEAL_EXEC != F_SEAL_EXEC
    {
        return Err(invalid(
            "APK payload must be read-only with every immutable and no-exec seal",
        ));
    }
    // SAFETY: statfs is initialized and writable for exactly this syscall.
    let mut fs: libc::statfs = unsafe { std::mem::zeroed() };
    if unsafe { libc::fstatfs(file.as_raw_fd(), &mut fs) } != 0 {
        return Err(io_error(
            "inspect APK payload filesystem",
            io::Error::last_os_error(),
        ));
    }
    if fs.f_type != libc::TMPFS_MAGIC {
        return Err(invalid("APK payload is not the fixed shmem transport"));
    }
    // AppArmor on the selected 6.18 kernel maps an internal IS_ROOT memfd
    // dentry to the disconnected root. It does not retain the memfd name.
    // Check the actual kernel-rendered name separately, through our own held
    // descriptor; no client-supplied pathname or descriptor number is accepted.
    let name = std::fs::read_link(format!("/proc/self/fd/{}", file.as_raw_fd()))
        .map_err(|e| io_error("read held APK payload name", e))?;
    if name != PathBuf::from("/memfd:droidloom-apk-payload (deleted)") {
        return Err(invalid("APK input has a different anonymous payload name"));
    }
    let mut offset = 0;
    for length in lengths {
        let mut magic = [0_u8; 4];
        file.read_exact_at(&mut magic, offset)
            .map_err(|e| io_error("read original APK segment header", e))?;
        if magic != *b"PK\x03\x04" {
            return Err(invalid("sealed APK segment is not an original ZIP body"));
        }
        offset += *length;
    }
    // Name, source inode and description observations are one held-FD bookend.
    // Another description can never make missing seals or a writable alias pass.
    if observe(file)? != node(&m)
        || unsafe { libc::fcntl(file.as_raw_fd(), libc::F_GETFL) } != flags
        || unsafe { libc::fcntl(file.as_raw_fd(), libc::F_GET_SEALS) } != seals
    {
        return Err(invalid(
            "sealed APK input identity or descriptor flags changed",
        ));
    }
    Ok(())
}

/// Production additionally requires the real fixed SELinux object context.
/// A host unit test without the joint policy cannot qualify this check.
pub(crate) fn validate_production_context(file: &File) -> Result<(), ControlError> {
    validate_context(file,PAYLOAD_CONTEXT)
}
pub(crate) fn validate_working_context(
    file:&File,
    peer:&super::working_install_peer::WorkingInstallPeer,
)->Result<(),ControlError>{
    peer.guard()?;
    validate_context(file,b"u:object_r:p4_linux_working_comparison_t:s0")?;
    peer.guard()
}
fn validate_context(file:&File,expected:&[u8])->Result<(),ControlError>{
    let mut bytes = [0_u8; 256];
    // SAFETY: a source-owned key and bounded writable buffer stay live.
    let n = unsafe {
        libc::fgetxattr(
            file.as_raw_fd(),
            c"security.selinux".as_ptr(),
            bytes.as_mut_ptr().cast(),
            bytes.len(),
        )
    };
    if n < 0 {
        return Err(io_error(
            "read original APK payload SELinux context",
            io::Error::last_os_error(),
        ));
    }
    let got = &bytes[..usize::try_from(n).map_err(|_| invalid("invalid APK context length"))?];
    let got = got.strip_suffix(&[0]).unwrap_or(got);
    if got != expected {
        return Err(invalid("APK payload has a different SELinux source type"));
    }
    Ok(())
}

#[cfg(test)]
pub(crate) fn test_payload(bytes: &[u8]) -> File {
    let mut file = create().unwrap();
    file.write_all(bytes).unwrap();
    seal(file).unwrap()
}

#[cfg(test)]
#[path = "apk_payload_tests.rs"]
mod tests;
