//! Byte matching for the original apexd loop backing request.
//!
//! This is a data witness only. The dispatcher must separately hold the actual
//! executed apexd, original PIDFD/thread, request, default mount epoch and MAC
//! owner. A File or this witness cannot issue any of those authorities.
//!
//! The requested /data inode is retained for change detection, but is never
//! passed as loop backing. Only the separately copied, fully hashed and
//! kernel-sealed output may enter the existing compressed private-loop path.
use super::*;
use std::os::fd::AsRawFd;

const DIRECT_ALIGNMENT: usize = 4096;
// Final Linux 6.18 UAPI: F_LINUX_SPECIFIC_BASE (1024) + 3. This query
// compares two descriptors already held by this process; no kcmp privilege.
const F_DUPFD_QUERY: i32 = 1027;
#[repr(align(4096))]
struct AlignedBlock([u8; CHUNK]);

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct RequestedIdentity {
    inode: Identity,
    flags: i32,
}
fn requested_identity(file: &File, expected_bytes: u64) -> io::Result<RequestedIdentity> {
    let metadata = file.metadata()?;
    let flags = unsafe { libc::fcntl(file.as_raw_fd(), libc::F_GETFL) };
    let descriptor = unsafe { libc::fcntl(file.as_raw_fd(), libc::F_GETFD) };
    if flags < 0 || descriptor < 0 {
        return Err(io::Error::last_os_error());
    }
    need(
        metadata.is_file()
            && metadata.len() == expected_bytes
            && expected_bytes > 0
            && expected_bytes <= MAX_ORIGINAL
            && flags & (libc::O_ACCMODE | libc::O_PATH) == libc::O_RDONLY
            && descriptor & libc::FD_CLOEXEC != 0,
        "the actual requested backing descriptor must be a complete readonly regular original APEX",
    )?;
    Ok(RequestedIdentity {
        inode: Identity::of(&metadata),
        flags,
    })
}
fn require_original_description(
    original: &File,
    observed: &File,
    expected: RequestedIdentity,
    bytes: u64,
) -> io::Result<()> {
    need(
        requested_identity(original, bytes)? == expected
            && requested_identity(observed, bytes)? == expected,
        "original requested inode, complete flags and full identity differ",
    )?;
    let same = unsafe { libc::fcntl(original.as_raw_fd(), F_DUPFD_QUERY, observed.as_raw_fd()) };
    if same < 0 {
        return Err(io::Error::last_os_error());
    }
    need(
        same == 1,
        "request must retain the same original open file description",
    )?;
    need(
        requested_identity(original, bytes)? == expected
            && requested_identity(observed, bytes)? == expected,
        "original requested description changed across its identity query",
    )
}
fn aligned_pread(
    file: &File,
    buffer: &mut AlignedBlock,
    count: usize,
    offset: u64,
    end: Instant,
) -> io::Result<usize> {
    need(
        count > 0
            && count <= CHUNK
            && count % DIRECT_ALIGNMENT == 0
            && offset <= MAX_ORIGINAL
            && offset % DIRECT_ALIGNMENT as u64 == 0
            && (buffer.0.as_ptr() as usize) % DIRECT_ALIGNMENT == 0,
        "bounded aligned read without changing the original open-file-description flags",
    )?;
    loop {
        deadline(end)?;
        let result = unsafe {
            libc::pread(
                file.as_raw_fd(),
                buffer.0.as_mut_ptr().cast(),
                count,
                offset as libc::off_t,
            )
        };
        if result >= 0 {
            deadline(end)?;
            return Ok(result as usize);
        }
        let error = io::Error::last_os_error();
        if error.kind() != io::ErrorKind::Interrupted {
            return Err(error);
        }
    }
}
#[derive(Debug)]
struct ReadEvidence {
    bytes: u64,
    sha256: String,
    crc32: u32,
    reads: usize,
    last_requested: usize,
    last_returned: usize,
    eof_offset: u64,
    eof_returned: usize,
}
fn match_or_copy(
    input: &File,
    output: Option<&File>,
    bytes: u64,
    end: Instant,
) -> io::Result<ReadEvidence> {
    need(
        bytes > 0 && bytes <= MAX_ORIGINAL,
        "bounded complete original requested archive",
    )?;
    let mut buffer = Box::new(AlignedBlock([0; CHUNK]));
    let mut sha = Sha256::new();
    let mut crc = crc32fast::Hasher::new();
    let mut at = 0;
    let mut reads = 0;
    let mut last_requested = 0;
    let mut last_returned = 0;
    while at < bytes {
        deadline(end)?;
        let expected = (bytes - at).min(CHUNK as u64) as usize;
        // The last request remains aligned even when the real EOF is not.
        // Hash/copy only the kernel's actual returned bytes. A rounded request
        // size must never become invented output padding or a hash shortcut.
        let requested = expected.div_ceil(DIRECT_ALIGNMENT) * DIRECT_ALIGNMENT;
        let returned = aligned_pread(input, &mut buffer, requested, at, end)?;
        need(
            returned == expected,
            "actual requested archive had an incomplete read or grew beyond its pinned EOF",
        )?;
        sha.update(&buffer.0[..returned]);
        crc.update(&buffer.0[..returned]);
        if let Some(output) = output {
            output.write_all_at(&buffer.0[..returned], at)?;
        }
        at += returned as u64;
        reads += 1;
        last_requested = requested;
        last_returned = returned;
    }
    deadline(end)?;
    let eof_offset = bytes.div_ceil(DIRECT_ALIGNMENT as u64) * DIRECT_ALIGNMENT as u64;
    let eof_returned = aligned_pread(input, &mut buffer, DIRECT_ALIGNMENT, eof_offset, end)?;
    need(
        eof_returned == 0,
        "actual requested archive has bytes beyond the aligned EOF",
    )?;
    deadline(end)?;
    Ok(ReadEvidence {
        bytes: at,
        sha256: format!("{:x}", sha.finalize()),
        crc32: crc.finalize(),
        reads,
        last_requested,
        last_returned,
        eof_offset,
        eof_returned,
    })
}

/// Original requested source plus a distinct immutable backing inode. The
/// source descriptor is intentionally retained and never relabelled, reopened
/// by pathname, promoted to writable, or made to impersonate the new output.
#[derive(Debug)]
pub(crate) struct MatchedDecompressedCapex {
    requested: File,
    requested_identity: RequestedIdentity,
    output: Rc<ImmutableCapex>,
}
impl MatchedDecompressedCapex {
    pub(crate) fn copy_requested(
        original_container: File,
        requested: File,
        index: usize,
        end: Instant,
    ) -> io::Result<Self> {
        deadline(end)?;
        let fixed = original_compressed(index).map_err(io::Error::other)?;
        let container_before = container_identity(&original_container)?;
        need(
            container_before.bytes == fixed.input.container_bytes
                && digest(&original_container, container_before.bytes, end)?
                    == fixed.input.container_sha256
                && container_identity(&original_container)? == container_before,
            "actual fixed-role original CAPEX input and full container identity",
        )?;
        // The existing strict parser still validates the complete original
        // central/local/descriptor/signature-window shape. Bytes copied from
        // the caller must match both that member CRC and the compiled hash.
        let window = compressed_window(
            &original_container,
            container_before.bytes,
            fixed.input.original_apex_bytes,
            end,
        )?;
        let source_before = requested_identity(&requested, fixed.input.original_apex_bytes)?;
        let output = fresh_output()?;
        let copied = match_or_copy(
            &requested,
            Some(&output),
            fixed.input.original_apex_bytes,
            end,
        )?;
        need(
            copied.bytes == fixed.input.original_apex_bytes
                && copied.sha256 == fixed.input.original_apex_sha256
                && copied.crc32 == window.crc
                && requested_identity(&requested, fixed.input.original_apex_bytes)?
                    == source_before,
            "whole actual requested source differs from the original compressed role or changed during copying",
        )?;
        let output = SealedOutput::seal(output, fixed.input.original_apex_bytes)?;
        let archive = Rc::new(VerifiedArchive::inspect(&output.file, index, end)?);
        need(
            (source_before.inode.dev, source_before.inode.ino)
                != (output.identity.dev, output.identity.ino),
            "the copied sealed backing must not alias the writable-path source inode",
        )?;
        // Read the original request again with its original O_DIRECT state.
        // No F_SETFL, pathname reopening or fabricated read-completion credit.
        let after = match_or_copy(&requested, None, fixed.input.original_apex_bytes, end)?;
        need(
            after.sha256 == copied.sha256
                && after.crc32 == copied.crc32
                && requested_identity(&requested, fixed.input.original_apex_bytes)?
                    == source_before
                && digest(&original_container, container_before.bytes, end)?
                    == fixed.input.container_sha256
                && container_identity(&original_container)? == container_before,
            "actual request and original CAPEX changed across sealed byte verification",
        )?;
        let output = Rc::new(ImmutableCapex {
            container: original_container,
            container_identity: container_before,
            output,
            archive,
        });
        let value = Self {
            requested,
            requested_identity: source_before,
            output,
        };
        value.revalidate()?;
        deadline(end)?;
        Ok(value)
    }
    pub(crate) fn revalidate(&self) -> io::Result<()> {
        self.output.revalidate()?;
        let fixed = original_compressed(self.output.archive.index()).map_err(io::Error::other)?;
        need(
            requested_identity(&self.requested, fixed.input.original_apex_bytes)?
                == self.requested_identity,
            "actual original apexd request inode or open-file-description flags changed",
        )
    }
    /// The request issuer supplies its own original transaction deadline at
    /// each use. This method does not create, extend or reset any deadline.
    pub(crate) fn attest_current_bytes(&self, end: Instant) -> io::Result<()> {
        self.revalidate()?;
        let fixed = original_compressed(self.output.archive.index()).map_err(io::Error::other)?;
        let bytes = match_or_copy(&self.requested, None, fixed.input.original_apex_bytes, end)?;
        need(
            bytes.sha256 == fixed.input.original_apex_sha256,
            "original requested decompressed bytes changed before use",
        )?;
        self.revalidate()?;
        deadline(end)
    }
    pub(crate) fn requested_file(&self) -> io::Result<&File> {
        self.revalidate()?;
        Ok(&self.requested)
    }
    // Borrow only: callers cannot detach an Rc<ImmutableCapex> from this
    // requested-source custody. The actual loop adapter must store the whole
    // Rc<MatchedDecompressedCapex> and call its revalidate at every use/retire.
    pub(crate) fn sealed_backing(&self) -> io::Result<&ImmutableCapex> {
        self.revalidate()?;
        Ok(&self.output)
    }
    /// Read-only role from the already matched, fixed original CAPEX profile.
    pub(crate) fn index(&self) -> usize {
        self.role_index()
    }
    /// Bind only the original request's already held descriptor. Equal bytes,
    /// inode and flags on a separately reopened description are insufficient.
    /// Unsupported F_DUPFD_QUERY is an error, never a metadata-only fallback.
    pub(crate) fn require_requested(&self, observed: &File) -> io::Result<()> {
        self.revalidate()?;
        let fixed = original_compressed(self.index()).map_err(io::Error::other)?;
        require_original_description(
            &self.requested,
            observed,
            self.requested_identity,
            fixed.input.original_apex_bytes,
        )?;
        self.revalidate()
    }
    pub(crate) fn role_index(&self) -> usize {
        self.output.archive.index()
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    use std::fs::OpenOptions;
    use std::io::Write;
    use std::os::unix::fs::OpenOptionsExt;
    use std::time::Duration;

    fn until() -> Instant {
        Instant::now() + Duration::from_secs(10)
    }

    #[test]
    fn requested_copy_reads_real_unaligned_eof_without_changing_direct_flags() {
        let directory = tempfile::tempdir().unwrap();
        let path = directory.path().join("original");
        let bytes: Vec<u8> = (0..CHUNK + 37).map(|n| (n % 251) as u8).collect();
        std::fs::write(&path, &bytes).unwrap();
        let input = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_DIRECT | libc::O_CLOEXEC)
            .open(&path)
            .unwrap();
        let identity = requested_identity(&input, bytes.len() as u64).unwrap();
        assert_ne!(identity.flags & libc::O_DIRECT, 0);
        let output = fresh_output().unwrap();
        let evidence = match_or_copy(&input, Some(&output), bytes.len() as u64, until()).unwrap();
        assert_eq!(evidence.bytes, bytes.len() as u64);
        assert_eq!(evidence.reads, 2);
        assert_eq!(evidence.last_requested, 4096);
        assert_eq!(evidence.last_returned, 37);
        assert_eq!(evidence.eof_offset, (CHUNK + 4096) as u64);
        assert_eq!(evidence.eof_returned, 0);
        assert_eq!(evidence.sha256, format!("{:x}", Sha256::digest(&bytes)));
        assert_eq!(evidence.crc32, crc32fast::hash(&bytes));
        let mut copied = vec![0; bytes.len()];
        output.read_exact_at(&mut copied, 0).unwrap();
        assert_eq!(copied, bytes);
        assert_eq!(
            requested_identity(&input, bytes.len() as u64).unwrap(),
            identity
        );
    }
    #[test]
    fn requested_description_requires_actual_dup_and_rejects_reopen_and_flags_change() {
        let directory = tempfile::tempdir().unwrap();
        let path = directory.path().join("original");
        std::fs::write(&path, [0x62; 4096]).unwrap();
        let original = File::open(&path).unwrap();
        let duplicate = original.try_clone().unwrap();
        let reopened = File::open(&path).unwrap();
        let before = requested_identity(&original, 4096).unwrap();
        // This is exactly the case that inode and flag comparisons cannot
        // distinguish. The kernel compares the two real struct file objects.
        assert_eq!(requested_identity(&reopened, 4096).unwrap(), before);
        require_original_description(&original, &duplicate, before, 4096).unwrap();
        assert!(require_original_description(&original, &reopened, before, 4096).is_err());
        assert_eq!(
            unsafe {
                libc::fcntl(
                    duplicate.as_raw_fd(),
                    libc::F_SETFL,
                    before.flags | libc::O_NONBLOCK,
                )
            },
            0,
        );
        assert!(require_original_description(&original, &duplicate, before, 4096).is_err());
        assert_eq!(
            unsafe { libc::fcntl(original.as_raw_fd(), libc::F_GETFL) },
            before.flags | libc::O_NONBLOCK,
        );
    }
    #[test]
    fn requested_gate_rejects_writable_description_without_changing_it() {
        let mut file = tempfile::tempfile().unwrap();
        file.write_all(&[0x35; 4096]).unwrap();
        let flags = unsafe { libc::fcntl(file.as_raw_fd(), libc::F_GETFL) };
        assert!(requested_identity(&file, 4096).is_err());
        assert_eq!(
            unsafe { libc::fcntl(file.as_raw_fd(), libc::F_GETFL) },
            flags
        );
    }
    #[test]
    fn requested_copy_rejects_truncation_growth_and_original_expired_deadline() {
        let directory = tempfile::tempdir().unwrap();
        let path = directory.path().join("original");
        std::fs::write(&path, vec![0x61; 4097]).unwrap();
        let input = OpenOptions::new().read(true).open(&path).unwrap();
        assert!(match_or_copy(&input, None, 4096, until()).is_err());
        assert!(match_or_copy(&input, None, 8192, until()).is_err());
        assert!(match_or_copy(&input, None, 4097, Instant::now()).is_err());
    }
}
