//! Finite read-only original-image hashing primitive shared by cold and runtime.
//! Linux 6.18 fs.h defines RWF_DONTCACHE=0x80; ext4_file_operations advertises
//! FOP_DONTCACHE. Refuse unsupported filesystems/kernels instead of silently
//! buffering 32 GiB into the qualification cgroup's unchanged memory limit.
use rustix::fs::{OFlags, fcntl_getfl};
use rustix::io::{ReadWriteFlags, preadv2};
use std::{fs::File, io, time::Instant};
pub(crate) const MAX_READ: usize = 1024 * 1024;
const RWF_DONTCACHE: u32 = 0x80;
fn invalid(why: &str) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidInput, why)
}
fn deadline(end: Instant) -> io::Result<()> {
    if Instant::now() >= end {
        Err(io::Error::new(
            io::ErrorKind::TimedOut,
            "original image no-cache read exhausted its unchanged pair end",
        ))
    } else {
        Ok(())
    }
}
/// Read exactly one bounded chunk from the same actual read-only OFD. Preserve
/// offset and the caller's original end across partial reads and EINTR. Every
/// syscall is enclosed by the caller's real custody guard. No fallback, cache
/// writeback, global drop_caches, descriptor write or renewed time is allowed.
pub(crate) fn read_exact_at(
    file: &File,
    mut output: &mut [u8],
    mut offset: u64,
    end: Instant,
    guard: &mut dyn FnMut() -> io::Result<()>,
) -> io::Result<()> {
    if output.is_empty()
        || output.len() > MAX_READ
        || offset
            .checked_add(output.len() as u64)
            .is_none_or(|v| v > i64::MAX as u64)
    {
        return Err(invalid(
            "original image read length/offset exceeds the fixed chunk",
        ));
    }
    let flags = fcntl_getfl(file)?;
    if flags & OFlags::ACCMODE != OFlags::RDONLY {
        return Err(invalid(
            "original image hash requires an actual read-only OFD",
        ));
    }
    while !output.is_empty() {
        deadline(end)?;
        guard()?;
        deadline(end)?;
        let mut iov = [io::IoSliceMut::new(output)];
        let result = preadv2(
            file,
            &mut iov,
            offset,
            ReadWriteFlags::from_bits_retain(RWF_DONTCACHE),
        )
        .map_err(io::Error::from);
        guard()?;
        deadline(end)?;
        let n = match result {
            Err(e) if e.kind() == io::ErrorKind::Interrupted => continue,
            Err(e) => return Err(e),
            Ok(0) => {
                return Err(io::Error::new(
                    io::ErrorKind::UnexpectedEof,
                    "original image no-cache read was truncated",
                ));
            }
            Ok(n) => n,
        };
        if n > output.len() {
            return Err(invalid("kernel original-image read exceeded its iovec"));
        }
        offset += n as u64;
        output = &mut output[n..];
    }
    Ok(())
}
#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;
    fn fixture() -> (tempfile::NamedTempFile, File) {
        let directory = std::env::var_os("CARGO_TARGET_DIR")
            .map(std::path::PathBuf::from)
            .unwrap_or_else(|| std::env::current_dir().unwrap());
        let mut original = tempfile::NamedTempFile::new_in(directory).unwrap();
        original.write_all(b"original user data").unwrap();
        original.as_file().sync_all().unwrap();
        let reader = File::open(original.path()).unwrap();
        (original, reader)
    }
    #[test]
    fn actual_no_cache_read_preserves_offset_bytes_read_only_flags_and_custody_bookends() {
        use std::os::unix::fs::MetadataExt;
        let (_original, reader) = fixture();
        let before = reader.metadata().unwrap();
        let mut out = [0u8; 9];
        let mut boundaries = 0;
        read_exact_at(
            &reader,
            &mut out,
            9,
            Instant::now() + std::time::Duration::from_secs(5),
            &mut || {
                boundaries += 1;
                Ok(())
            },
        )
        .unwrap();
        assert_eq!(&out, b"user data");
        assert!(boundaries >= 2);
        let after = reader.metadata().unwrap();
        assert_eq!(
            (
                before.dev(),
                before.ino(),
                before.mode(),
                before.len(),
                before.mtime(),
                before.mtime_nsec(),
                before.ctime(),
                before.ctime_nsec()
            ),
            (
                after.dev(),
                after.ino(),
                after.mode(),
                after.len(),
                after.mtime(),
                after.mtime_nsec(),
                after.ctime(),
                after.ctime_nsec()
            )
        );
        assert_eq!(
            fcntl_getfl(&reader).unwrap() & OFlags::ACCMODE,
            OFlags::RDONLY
        );
    }
    #[test]
    fn original_no_cache_read_rejects_writable_fds_expired_windows_truncation_and_foreign_custody()
    {
        let (original, reader) = fixture();
        let end = Instant::now() + std::time::Duration::from_secs(5);
        assert!(read_exact_at(original.as_file(), &mut [0; 8], 0, end, &mut || Ok(())).is_err());
        assert!(read_exact_at(&reader, &mut [0; 8], 0, Instant::now(), &mut || Ok(())).is_err());
        assert!(read_exact_at(&reader, &mut [0; 8], 16, end, &mut || Ok(())).is_err());
        assert!(
            read_exact_at(&reader, &mut [0; 8], 0, end, &mut || Err(invalid(
                "actual generation changed"
            )))
            .is_err()
        );
        assert!(read_exact_at(&reader, &mut [0; 8], u64::MAX, end, &mut || Ok(())).is_err());
    }
}
