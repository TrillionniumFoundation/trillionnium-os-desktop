//! Immutable, non-executable APK transport created by the calling client.
//!
//! The broker receives only a read-only description of this sealed anonymous
//! inode. It never receives the user's source file or opens a caller pathname.
use super::{ControlError, apk, io_error};
use std::fs::{File, Metadata, OpenOptions};
use std::io::{self, Write};
use std::os::fd::{AsRawFd, FromRawFd};
use std::os::unix::fs::{FileExt, MetadataExt, OpenOptionsExt};
use std::path::PathBuf;
use std::time::{Duration, Instant};

const MAX_BYTES: u64 = 2 * 1024 * 1024 * 1024;
const MFD_NOEXEC_SEAL: libc::c_uint = 0x0008;
const F_SEAL_EXEC: libc::c_int = 0x0020;
const SEALS: libc::c_int =
    libc::F_SEAL_SEAL | libc::F_SEAL_SHRINK | libc::F_SEAL_GROW | libc::F_SEAL_WRITE | F_SEAL_EXEC;

#[derive(Eq, PartialEq)]
struct Identity {
    values: [u64; 7],
    times: [i64; 4],
}
impl Identity {
    fn read(m: &Metadata) -> Self {
        Self {
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
}
fn need(ok: bool, message: &str) -> Result<(), ControlError> {
    if ok {
        Ok(())
    } else {
        Err(ControlError::Invalid(message.into()))
    }
}
fn before(deadline: Instant) -> Result<(), ControlError> {
    need(
        Instant::now() < deadline,
        "APK payload preparation exceeded its fixed deadline",
    )
}

fn fresh() -> Result<File, ControlError> {
    // The selected shared kernel supports MFD_NOEXEC_SEAL. An older kernel
    // fails explicitly; no writable disk file or executable-memfd fallback.
    let raw = unsafe {
        libc::memfd_create(
            c"droidloom-apk-payload".as_ptr(),
            libc::MFD_CLOEXEC | libc::MFD_ALLOW_SEALING | MFD_NOEXEC_SEAL,
        )
    };
    if raw < 0 {
        return Err(io_error(
            "create non-executable APK payload",
            io::Error::last_os_error(),
        ));
    }
    let file = unsafe { File::from_raw_fd(raw) };
    if unsafe { libc::fchmod(file.as_raw_fd(), 0o400) } != 0 {
        return Err(io_error(
            "protect APK payload mode",
            io::Error::last_os_error(),
        ));
    }
    let seals = unsafe { libc::fcntl(file.as_raw_fd(), libc::F_GET_SEALS) };
    need(
        seals == F_SEAL_EXEC,
        "fresh APK payload lacks the kernel's non-executable seal",
    )?;
    Ok(file)
}

fn read_only(file: &File) -> Result<File, ControlError> {
    // A dup/SCM_RIGHTS copy retains O_RDWR and would require broker write access
    // even after sealing. Reopen this original held inode read-only first.
    let identity = Identity::read(
        &file
            .metadata()
            .map_err(|e| io_error("inspect sealed APK payload", e))?,
    );
    let result = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_CLOEXEC)
        .open(format!("/proc/self/fd/{}", file.as_raw_fd()))
        .map_err(|e| io_error("open original sealed APK payload read-only", e))?;
    need(
        identity
            == Identity::read(
                &result
                    .metadata()
                    .map_err(|e| io_error("inspect read-only APK payload", e))?,
            ),
        "read-only APK description is not the original sealed inode",
    )?;
    Ok(result)
}

/// Same check at the public early-owner boundary and before client transfer.
/// It grants no application acceptance or signer claim; Android still verifies
/// the complete original APKs and enforces installed signer continuity.
pub(super) fn validate(file: &File, expected_bytes: u64) -> Result<(), ControlError> {
    let metadata = file
        .metadata()
        .map_err(|e| io_error("inspect anonymous APK payload", e))?;
    let seals = unsafe { libc::fcntl(file.as_raw_fd(), libc::F_GET_SEALS) };
    let flags = unsafe { libc::fcntl(file.as_raw_fd(), libc::F_GETFL) };
    let descriptor = unsafe { libc::fcntl(file.as_raw_fd(), libc::F_GETFD) };
    let mut filesystem: libc::statfs = unsafe { std::mem::zeroed() };
    if unsafe { libc::fstatfs(file.as_raw_fd(), &mut filesystem) } != 0 {
        return Err(io_error(
            "inspect original APK payload filesystem",
            io::Error::last_os_error(),
        ));
    }
    need(
        (4..=MAX_BYTES).contains(&expected_bytes)
            && metadata.is_file()
            && metadata.mode() == libc::S_IFREG | 0o400
            && metadata.nlink() == 0
            && metadata.len() == expected_bytes
            && seals == SEALS
            && flags >= 0
            && descriptor >= 0
            && flags & (libc::O_ACCMODE | libc::O_PATH) == libc::O_RDONLY
            && descriptor & libc::FD_CLOEXEC != 0
            && filesystem.f_type == libc::TMPFS_MAGIC,
        "APK transport must be the complete read-only, non-executable sealed anonymous inode",
    )
}

pub(super) fn prepare(paths: &[PathBuf]) -> Result<(File, Vec<u64>), ControlError> {
    need(
        (1..=32).contains(&paths.len()),
        "supply one through 32 original APK files",
    )?;
    let deadline = Instant::now() + Duration::from_secs(110);
    let mut inputs = Vec::with_capacity(paths.len());
    let mut lengths = Vec::with_capacity(paths.len());
    let mut total = 0_u64;
    for path in paths {
        before(deadline)?;
        let file = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_NONBLOCK | libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open(path)
            .map_err(|e| io_error("open original APK with caller permissions", e))?;
        let length = apk::validate(&file)?;
        let identity = Identity::read(
            &file
                .metadata()
                .map_err(|e| io_error("capture original APK inode", e))?,
        );
        total = total
            .checked_add(length)
            .filter(|v| *v <= MAX_BYTES)
            .ok_or_else(|| ControlError::Invalid("complete APK payload exceeds 2 GiB".into()))?;
        inputs.push((file, identity));
        lengths.push(length);
    }
    let mut payload = fresh()?;
    let mut buffer = [0u8; 64 * 1024];
    for ((file, identity), length) in inputs.iter().zip(&lengths) {
        let mut offset = 0;
        while offset < *length {
            before(deadline)?;
            need(
                *identity
                    == Identity::read(
                        &file
                            .metadata()
                            .map_err(|e| io_error("recheck original APK", e))?,
                    ),
                "original APK changed during immutable transport preparation",
            )?;
            let count = usize::try_from((*length - offset).min(buffer.len() as u64))
                .expect("bounded copy block");
            file.read_exact_at(&mut buffer[..count], offset)
                .map_err(|e| io_error("read original APK bytes", e))?;
            payload
                .write_all(&buffer[..count])
                .map_err(|e| io_error("copy original APK bytes into anonymous payload", e))?;
            offset += count as u64;
        }
    }
    for (file, identity) in &inputs {
        need(
            *identity
                == Identity::read(
                    &file
                        .metadata()
                        .map_err(|e| io_error("recheck complete original APK input", e))?,
                ),
            "original APK changed before immutable transport was sealed",
        )?;
    }
    before(deadline)?;
    if unsafe { libc::fcntl(payload.as_raw_fd(), libc::F_ADD_SEALS, SEALS) } != 0 {
        return Err(io_error(
            "seal complete original APK payload",
            io::Error::last_os_error(),
        ));
    }
    let output = read_only(&payload)?;
    drop(payload);
    validate(&output, total)?;
    before(deadline)?;
    Ok((output, lengths))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Read;
    use std::os::unix::net::UnixStream;

    #[test]
    fn split_bytes_survive_transfer_only_as_read_only_sealed_nonexecutable_payload() {
        let directory = tempfile::tempdir().unwrap();
        let paths = [
            directory.path().join("base.apk"),
            directory.path().join("split.apk"),
        ];
        std::fs::write(&paths[0], b"PK\x03\x04base").unwrap();
        std::fs::write(&paths[1], b"PK\x03\x04split").unwrap();
        let (file, lengths) = prepare(&paths).unwrap();
        assert_eq!(lengths, [8, 9]);
        let (sender, receiver) = UnixStream::pair().unwrap();
        apk::send_file(&sender, b'{', &file).unwrap();
        drop(file);
        let (_, transferred) = apk::receive_file(&receiver).unwrap();
        let mut transferred = transferred.unwrap();
        validate(&transferred, 17).unwrap();
        let mut actual = Vec::new();
        transferred.read_to_end(&mut actual).unwrap();
        assert_eq!(actual, b"PK\x03\x04basePK\x03\x04split");
        assert_eq!(
            transferred.write_at(b"x", 4).unwrap_err().raw_os_error(),
            Some(libc::EBADF)
        );
        assert_eq!(unsafe { libc::fchmod(transferred.as_raw_fd(), 0o500) }, -1);
        assert_eq!(io::Error::last_os_error().raw_os_error(), Some(libc::EPERM));
    }

    #[test]
    fn missing_seals_and_writable_descriptions_are_rejected() {
        let mut file = fresh().unwrap();
        file.write_all(b"PK\x03\x04test").unwrap();
        assert!(validate(&read_only(&file).unwrap(), 8).is_err());
        assert_eq!(
            unsafe { libc::fcntl(file.as_raw_fd(), libc::F_ADD_SEALS, SEALS) },
            0
        );
        assert!(validate(&file, 8).is_err());
        assert_eq!(
            file.write_at(b"x", 4).unwrap_err().raw_os_error(),
            Some(libc::EPERM)
        );
        assert!(file.set_len(9).is_err());
        let read = read_only(&file).unwrap();
        validate(&read, 8).unwrap();
        assert!(validate(&read, 7).is_err());
    }

    #[test]
    fn arbitrary_disk_descriptions_are_not_production_apk_transport() {
        let mut input = tempfile::tempfile().unwrap();
        input.write_all(b"PK\x03\x04test").unwrap();
        assert!(validate(&input, 8).is_err());
    }

    #[test]
    fn invalid_originals_are_rejected_without_creating_a_session() {
        assert!(prepare(&[]).is_err());
        assert!(prepare(&vec![PathBuf::from("/absent.apk"); 33]).is_err());
        let directory = tempfile::tempdir().unwrap();
        let path = directory.path().join("input.apk");
        std::fs::write(&path, b"not-apk").unwrap();
        assert!(prepare(std::slice::from_ref(&path)).is_err());
        std::fs::write(&path, b"PK\x03\x04base").unwrap();
        let alias = directory.path().join("alias.apk");
        std::os::unix::fs::symlink(&path, &alias).unwrap();
        assert!(prepare(&[alias]).is_err());
        let (file, lengths) = prepare(&[path]).unwrap();
        assert_eq!(lengths, [8]);
        validate(&file, 8).unwrap();
    }
}
