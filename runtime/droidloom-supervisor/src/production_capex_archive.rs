//! Fixed CP3A CAPEX decoding into kernel-sealed, non-executable anonymous files.
//!
//! The compiled profile is the only source of accepted sizes and hashes. This
//! module proves bytes and output immutability, not AVB signature validity,
//! MAC permission, block ownership, apexd execution or Android readiness.
//! The runtime adapter must obtain the original container from the admitted
//! system mount; a caller's path or matching host copy grants no such authority.

use crate::production_execution_profile::apex_inputs::{
    archive::VerifiedArchive, original_compressed,
};
use flate2::{Decompress, FlushDecompress, Status};
use sha2::{Digest, Sha256};
use std::fs::{File, Metadata};
use std::io;
use std::os::fd::{AsRawFd, FromRawFd};
use std::os::unix::fs::{FileExt, MetadataExt};
use std::rc::Rc;
use std::time::Instant;

#[path = "production_capex_requested_source.rs"]
mod requested_source;
pub(crate) use requested_source::MatchedDecompressedCapex;

const MAX_CONTAINER: u64 = 32 * 1024 * 1024;
const MAX_ORIGINAL: u64 = 64 * 1024 * 1024;
const CHUNK: usize = 65_536;
const MFD_NOEXEC_SEAL: u32 = 0x0008;
const F_SEAL_EXEC: i32 = 0x0020;
const REQUIRED_SEALS: i32 =
    libc::F_SEAL_SEAL | libc::F_SEAL_SHRINK | libc::F_SEAL_GROW | libc::F_SEAL_WRITE | F_SEAL_EXEC;
const MEMBERS: [&[u8]; 5] = [
    b"AndroidManifest.xml",
    b"apex_build_info.pb",
    b"apex_manifest.pb",
    b"apex_pubkey",
    b"original_apex",
];

fn need(ok: bool, why: &'static str) -> io::Result<()> {
    if ok {
        Ok(())
    } else {
        Err(io::Error::new(io::ErrorKind::InvalidData, why))
    }
}
fn deadline(end: Instant) -> io::Result<()> {
    if Instant::now() < end {
        Ok(())
    } else {
        Err(io::Error::new(
            io::ErrorKind::TimedOut,
            "original CAPEX decoding deadline",
        ))
    }
}
fn part(bytes: &[u8], start: usize, count: usize) -> io::Result<&[u8]> {
    bytes
        .get(
            start
                ..start
                    .checked_add(count)
                    .ok_or_else(|| io::Error::other("CAPEX field overflow"))?,
        )
        .ok_or_else(|| io::Error::new(io::ErrorKind::UnexpectedEof, "truncated CAPEX field"))
}
fn le16(bytes: &[u8], at: usize) -> io::Result<u16> {
    Ok(u16::from_le_bytes(part(bytes, at, 2)?.try_into().unwrap()))
}
fn le32(bytes: &[u8], at: usize) -> io::Result<u32> {
    Ok(u32::from_le_bytes(part(bytes, at, 4)?.try_into().unwrap()))
}
fn le64(bytes: &[u8], at: usize) -> io::Result<u64> {
    Ok(u64::from_le_bytes(part(bytes, at, 8)?.try_into().unwrap()))
}
fn read(file: &File, at: u64, count: usize, total: u64) -> io::Result<Vec<u8>> {
    need(
        count <= CHUNK && at.checked_add(count as u64).is_some_and(|n| n <= total),
        "bounded CAPEX read within the original held inode",
    )?;
    let mut bytes = vec![0; count];
    file.read_exact_at(&mut bytes, at)?;
    Ok(bytes)
}
fn digest(file: &File, total: u64, end: Instant) -> io::Result<String> {
    let mut hash = Sha256::new();
    let mut buffer = [0; CHUNK];
    let mut at = 0;
    while at < total {
        deadline(end)?;
        let count = (total - at).min(CHUNK as u64) as usize;
        file.read_exact_at(&mut buffer[..count], at)?;
        hash.update(&buffer[..count]);
        at += count as u64;
    }
    deadline(end)?;
    Ok(format!("{:x}", hash.finalize()))
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct Identity {
    dev: u64,
    ino: u64,
    mode: u32,
    uid: u32,
    gid: u32,
    links: u64,
    bytes: u64,
    mtime: (i64, i64),
    ctime: (i64, i64),
}
impl Identity {
    fn of(meta: &Metadata) -> Self {
        Self {
            dev: meta.dev(),
            ino: meta.ino(),
            mode: meta.mode(),
            uid: meta.uid(),
            gid: meta.gid(),
            links: meta.nlink(),
            bytes: meta.len(),
            mtime: (meta.mtime(), meta.mtime_nsec()),
            ctime: (meta.ctime(), meta.ctime_nsec()),
        }
    }
}
fn container_identity(file: &File) -> io::Result<Identity> {
    let meta = file.metadata()?;
    let flags = unsafe { libc::fcntl(file.as_raw_fd(), libc::F_GETFL) };
    if flags < 0 {
        return Err(io::Error::last_os_error());
    }
    need(
        meta.is_file()
            && meta.len() > 0
            && meta.len() <= MAX_CONTAINER
            && flags & (libc::O_ACCMODE | libc::O_PATH) == libc::O_RDONLY,
        "CAPEX requires a bounded regular original readonly body descriptor",
    )?;
    Ok(Identity::of(&meta))
}

#[derive(Clone, Copy, Debug)]
struct Directory {
    offset: u64,
    bytes: usize,
}
fn directory(tail: &[u8], total: u64) -> io::Result<Directory> {
    need(
        total <= MAX_CONTAINER && tail.len() >= 22 && tail.len() as u64 <= total,
        "bounded complete CAPEX ZIP end",
    )?;
    let mut result = None;
    for at in 0..=tail.len() - 22 {
        if part(tail, at, 4)? != b"PK\x05\x06"
            || at + 22 + le16(tail, at + 20)? as usize != tail.len()
        {
            continue;
        }
        need(result.is_none(), "ambiguous CAPEX ZIP end record")?;
        let offset = u64::from(le32(tail, at + 16)?);
        let bytes = le32(tail, at + 12)? as usize;
        need(
            le16(tail, at + 4)? == 0
                && le16(tail, at + 6)? == 0
                && le16(tail, at + 8)? == 5
                && le16(tail, at + 10)? == 5
                && (5 * 46..=CHUNK).contains(&bytes)
                && offset.checked_add(bytes as u64) == Some(total - tail.len() as u64 + at as u64)
                && le16(tail, at + 20)? < 4096
                && tail[at + 22..].iter().all(|b| *b == 0)
                && total % 4096 == 0,
            "exact five-member, single-disk CP3A CAPEX directory and terminal padding",
        )?;
        result = Some(Directory { offset, bytes });
    }
    result.ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, "CAPEX ZIP end absent"))
}

#[derive(Clone, Debug)]
struct Entry {
    local: u64,
    data: u64,
    compressed: u64,
    expanded: u64,
    crc: u32,
    extra: Vec<u8>,
}
fn entries(bytes: &[u8], expected_original: u64) -> io::Result<Vec<Entry>> {
    need(
        bytes.len() <= CHUNK && expected_original > 0 && expected_original <= MAX_ORIGINAL,
        "bounded fixed CAPEX directory and output",
    )?;
    let mut cursor = 0;
    let mut entries = Vec::with_capacity(5);
    for (index, name) in MEMBERS.iter().enumerate() {
        let head = part(bytes, cursor, 46)?;
        let name_bytes = le16(head, 28)? as usize;
        let extra_bytes = le16(head, 30)? as usize;
        let comment_bytes = le16(head, 32)? as usize;
        need(
            part(head, 0, 4)? == b"PK\x01\x02"
                && name_bytes == name.len()
                && extra_bytes <= 256
                && comment_bytes == 0
                && le16(head, 34)? == 0
                && le16(head, 36)? == 0,
            "complete fixed CAPEX central entry",
        )?;
        let body = part(bytes, cursor + 46, name_bytes + extra_bytes)?;
        need(
            part(body, 0, name_bytes)? == *name,
            "exact complete CAPEX member order",
        )?;
        let compressed = u64::from(le32(head, 20)?);
        let expanded = u64::from(le32(head, 24)?);
        let is_original = index == 4;
        need(
            if is_original {
                le16(head, 4)? == 20
                    && le16(head, 6)? == 20
                    && le16(head, 8)? == 0x808
                    && le16(head, 10)? == 8
                    && le32(head, 38)? == 0
                    && extra_bytes == 0
                    && compressed > 0
                    && compressed < MAX_CONTAINER
                    && expanded == expected_original
            } else {
                le16(head, 4)? == 0x030a
                    && le16(head, 6)? == 10
                    && le16(head, 8)? == 0x800
                    && le16(head, 10)? == 0
                    && le32(head, 38)? == 0x81a4_0000
                    && compressed == expanded
                    && (1..=CHUNK as u64).contains(&expanded)
            },
            "fixed stored metadata or original_apex raw-DEFLATE encoding",
        )?;
        entries.push(Entry {
            local: u64::from(le32(head, 42)?),
            data: 0,
            compressed,
            expanded,
            crc: le32(head, 16)?,
            extra: part(body, name_bytes, extra_bytes)?.to_vec(),
        });
        cursor += 46 + body.len();
    }
    need(
        cursor == bytes.len(),
        "whole CAPEX central directory consumed exactly once",
    )?;
    Ok(entries)
}

fn local_window(file: &File, entry: &mut Entry, index: usize, total: u64) -> io::Result<()> {
    let head = read(file, entry.local, 30, total)?;
    let name = MEMBERS[index];
    let original = index == 4;
    need(
        part(&head, 0, 4)? == b"PK\x03\x04"
            && le16(&head, 4)? == if original { 20 } else { 10 }
            && le16(&head, 6)? == if original { 0x808 } else { 0x800 }
            && le16(&head, 8)? == if original { 8 } else { 0 }
            && le16(&head, 26)? as usize == name.len()
            && le16(&head, 28)? as usize == entry.extra.len()
            && le32(&head, 14)? == if original { 0 } else { entry.crc }
            && u64::from(le32(&head, 18)?) == if original { 0 } else { entry.compressed }
            && u64::from(le32(&head, 22)?) == if original { 0 } else { entry.expanded },
        "CAPEX local and central fields agree including original data descriptor",
    )?;
    let body = read(
        file,
        entry.local + 30,
        name.len() + entry.extra.len(),
        total,
    )?;
    need(
        part(&body, 0, name.len())? == name
            && part(&body, name.len(), entry.extra.len())? == entry.extra,
        "CAPEX local member name and extras match the central record",
    )?;
    entry.data = entry.local + 30 + body.len() as u64;
    need(
        entry
            .data
            .checked_add(entry.compressed)
            .is_some_and(|n| n < total),
        "CAPEX member data remains inside the actual original inode",
    )
}

fn compressed_window(
    file: &File,
    total: u64,
    expected_original: u64,
    end: Instant,
) -> io::Result<Entry> {
    deadline(end)?;
    // CP3A's terminal comment is at most 4095 bytes. A 64 KiB tail contains
    // that complete end record without allocating from an untrusted length.
    let count = total.min(CHUNK as u64) as usize;
    let tail = read(file, total - count as u64, count, total)?;
    let directory = directory(&tail, total)?;
    let raw = read(file, directory.offset, directory.bytes, total)?;
    let mut entries = entries(&raw, expected_original)?;
    let mut next = 0;
    for (index, entry) in entries.iter_mut().enumerate() {
        deadline(end)?;
        need(
            entry.local == next,
            "CAPEX local records cannot overlap or conceal an extra member",
        )?;
        local_window(file, entry, index, total)?;
        next = entry.data + entry.compressed;
        if index < 4 {
            let data = read(file, entry.data, entry.compressed as usize, total)?;
            need(
                crc32fast::hash(&data) == entry.crc,
                "actual stored CAPEX metadata CRC",
            )?;
        }
    }
    let original = entries.pop().unwrap();
    let descriptor = read(file, next, 16, total)?;
    need(
        part(&descriptor, 0, 4)? == b"PK\x07\x08"
            && le32(&descriptor, 4)? == original.crc
            && u64::from(le32(&descriptor, 8)?) == original.compressed
            && u64::from(le32(&descriptor, 12)?) == original.expanded,
        "original CAPEX data descriptor equals its unique central record",
    )?;
    next += 16;
    need(
        directory.offset >= 32,
        "CAPEX signing footer precedes the directory",
    )?;
    let footer = read(file, directory.offset - 24, 24, total)?;
    need(
        part(&footer, 8, 16)? == b"APK Sig Block 42",
        "original CAPEX signing-block footer shape",
    )?;
    let size = le64(&footer, 0)?;
    let block_bytes = size
        .checked_add(8)
        .ok_or_else(|| io::Error::other("CAPEX signing-block overflow"))?;
    need(
        (4096..=CHUNK as u64).contains(&block_bytes)
            && block_bytes % 4096 == 0
            && block_bytes <= directory.offset,
        "bounded original CAPEX signing block",
    )?;
    let block = directory.offset - block_bytes;
    need(
        block % 4096 == 0 && next <= block && block - next < 4096,
        "exact zero padding between original DEFLATE descriptor and signing block",
    )?;
    let padding = read(file, next, (block - next) as usize, total)?;
    need(
        padding.iter().all(|b| *b == 0) && le64(&read(file, block, 8, total)?, 0)? == size,
        "original signing-block size bookends and zero alignment padding",
    )?;
    deadline(end)?;
    Ok(original)
}

fn inflate_into(
    source: &File,
    entry: &Entry,
    output: &File,
    expected_sha256: &str,
    end: Instant,
) -> io::Result<()> {
    need(
        entry.compressed > 0
            && entry.compressed < MAX_CONTAINER
            && entry.expanded > 0
            && entry.expanded <= MAX_ORIGINAL,
        "compiled finite CAPEX stream dimensions",
    )?;
    let mut decoder = Decompress::new(false);
    let mut input = [0; CHUNK];
    let mut decoded = [0; CHUNK];
    let (mut loaded, mut start, mut available, mut written) = (0_u64, 0_usize, 0_usize, 0_u64);
    let mut crc = crc32fast::Hasher::new();
    let mut sha = Sha256::new();
    loop {
        deadline(end)?;
        if start == available && loaded < entry.compressed {
            available = (entry.compressed - loaded).min(CHUNK as u64) as usize;
            source.read_exact_at(&mut input[..available], entry.data + loaded)?;
            loaded += available as u64;
            start = 0;
        }
        let before_in = decoder.total_in();
        let before_out = decoder.total_out();
        let status = decoder
            .decompress(
                &input[start..available],
                &mut decoded,
                FlushDecompress::None,
            )
            .map_err(|_| {
                io::Error::new(
                    io::ErrorKind::InvalidData,
                    "invalid original CAPEX DEFLATE stream",
                )
            })?;
        let consumed = decoder
            .total_in()
            .checked_sub(before_in)
            .ok_or_else(|| io::Error::other("CAPEX decoder input counter regressed"))?;
        let produced = decoder
            .total_out()
            .checked_sub(before_out)
            .ok_or_else(|| io::Error::other("CAPEX decoder output counter regressed"))?;
        need(
            consumed <= (available - start) as u64
                && produced <= CHUNK as u64
                && decoder.total_in() <= entry.compressed
                && written
                    .checked_add(produced)
                    .is_some_and(|n| n <= entry.expanded),
            "CAPEX decoder cannot exceed fixed input or output extent",
        )?;
        start += consumed as usize;
        if produced != 0 {
            let bytes = &decoded[..produced as usize];
            output.write_all_at(bytes, written)?;
            crc.update(bytes);
            sha.update(bytes);
            written += produced;
        }
        need(
            decoder.total_out() == written,
            "actual CAPEX output counter",
        )?;
        if status == Status::StreamEnd {
            need(
                decoder.total_in() == entry.compressed
                    && loaded == entry.compressed
                    && start == available
                    && written == entry.expanded,
                "one complete original DEFLATE stream with no trailing bytes",
            )?;
            break;
        }
        need(
            consumed != 0 || produced != 0,
            "truncated or stalled original CAPEX DEFLATE stream",
        )?;
    }
    need(
        crc.finalize() == entry.crc && format!("{:x}", sha.finalize()) == expected_sha256,
        "complete decoded original APEX CRC and compiled whole SHA256",
    )?;
    deadline(end)
}

fn fresh_output() -> io::Result<File> {
    let fd = unsafe {
        libc::memfd_create(
            c"droidloom-original-capex".as_ptr(),
            libc::MFD_CLOEXEC | libc::MFD_ALLOW_SEALING | MFD_NOEXEC_SEAL,
        )
    };
    if fd < 0 {
        return Err(io::Error::last_os_error());
    }
    let file = unsafe { File::from_raw_fd(fd) };
    if unsafe { libc::fchmod(file.as_raw_fd(), 0o400) } != 0 {
        return Err(io::Error::last_os_error());
    }
    let initial = unsafe { libc::fcntl(file.as_raw_fd(), libc::F_GET_SEALS) };
    if initial < 0 {
        return Err(io::Error::last_os_error());
    }
    need(
        initial == F_SEAL_EXEC
            && file.metadata()?.mode() == libc::S_IFREG | 0o400
            && file.metadata()?.nlink() == 0,
        "fresh anonymous output must already prohibit execute-bit changes",
    )?;
    Ok(file)
}

#[derive(Debug)]
struct SealedOutput {
    file: File,
    identity: Identity,
}
impl SealedOutput {
    fn seal(file: File, bytes: u64) -> io::Result<Self> {
        need(
            bytes > 0 && bytes <= MAX_ORIGINAL && file.metadata()?.len() == bytes,
            "seal only the complete bounded original APEX",
        )?;
        if unsafe { libc::fcntl(file.as_raw_fd(), libc::F_ADD_SEALS, REQUIRED_SEALS) } != 0 {
            return Err(io::Error::last_os_error());
        }
        let identity = Identity::of(&file.metadata()?);
        let result = Self { file, identity };
        result.revalidate()?;
        Ok(result)
    }
    fn revalidate(&self) -> io::Result<()> {
        let seals = unsafe { libc::fcntl(self.file.as_raw_fd(), libc::F_GET_SEALS) };
        let flags = unsafe { libc::fcntl(self.file.as_raw_fd(), libc::F_GETFL) };
        let descriptor = unsafe { libc::fcntl(self.file.as_raw_fd(), libc::F_GETFD) };
        if seals < 0 || flags < 0 || descriptor < 0 {
            return Err(io::Error::last_os_error());
        }
        let mut fs: libc::statfs = unsafe { std::mem::zeroed() };
        if unsafe { libc::fstatfs(self.file.as_raw_fd(), &mut fs) } != 0 {
            return Err(io::Error::last_os_error());
        }
        need(
            seals == REQUIRED_SEALS
                && flags & (libc::O_ACCMODE | libc::O_PATH) == libc::O_RDWR
                && descriptor & libc::FD_CLOEXEC != 0
                && fs.f_type as u64 == 0x0102_1994
                && self.identity.mode == libc::S_IFREG | 0o400
                && self.identity.links == 0
                && self.identity.bytes > 0
                && self.identity.bytes <= MAX_ORIGINAL
                && Identity::of(&self.file.metadata()?) == self.identity,
            "same non-executable anonymous inode with irreversible write, grow, shrink and seal locks",
        )
    }
}

/// Non-serializable custody of the original container and its actual sealed
/// output. The archive witness is made only after every output seal is present.
#[derive(Debug)]
pub(crate) struct ImmutableCapex {
    container: File,
    container_identity: Identity,
    output: SealedOutput,
    archive: Rc<VerifiedArchive>,
}
impl ImmutableCapex {
    pub(crate) fn decode(container: File, index: usize, end: Instant) -> io::Result<Self> {
        deadline(end)?;
        let fixed = original_compressed(index).map_err(io::Error::other)?;
        let identity = container_identity(&container)?;
        need(
            identity.bytes == fixed.input.container_bytes
                && fixed.input.original_apex_bytes <= MAX_ORIGINAL,
            "same compiled original CAPEX role and complete container length",
        )?;
        need(
            digest(&container, identity.bytes, end)? == fixed.input.container_sha256
                && container_identity(&container)? == identity,
            "complete compiled CAPEX input hash and original full inode identity",
        )?;
        let entry = compressed_window(
            &container,
            identity.bytes,
            fixed.input.original_apex_bytes,
            end,
        )?;
        let output = fresh_output()?;
        inflate_into(
            &container,
            &entry,
            &output,
            &fixed.input.original_apex_sha256,
            end,
        )?;
        let output = SealedOutput::seal(output, fixed.input.original_apex_bytes)?;
        let archive = Rc::new(VerifiedArchive::inspect(&output.file, index, end)?);
        need(
            digest(&container, identity.bytes, end)? == fixed.input.container_sha256
                && container_identity(&container)? == identity,
            "original CAPEX remains byte-identical after actual output verification",
        )?;
        let result = Self {
            container,
            container_identity: identity,
            output,
            archive,
        };
        result.revalidate()?;
        deadline(end)?;
        Ok(result)
    }
    pub(crate) fn revalidate(&self) -> io::Result<()> {
        need(
            container_identity(&self.container)? == self.container_identity,
            "held original compressed container changed",
        )?;
        original_compressed(self.archive.index()).map_err(io::Error::other)?;
        self.output.revalidate()?;
        self.archive.matches(&self.output.file)
    }
    pub(crate) fn file(&self) -> io::Result<&File> {
        self.revalidate()?;
        Ok(&self.output.file)
    }
    pub(crate) fn archive(&self) -> io::Result<Rc<VerifiedArchive>> {
        self.revalidate()?;
        Ok(Rc::clone(&self.archive))
    }
    pub(crate) fn matches(&self, file: &File, archive: &VerifiedArchive) -> io::Result<()> {
        self.revalidate()?;
        need(
            Identity::of(&file.metadata()?) == self.output.identity
                && archive.index() == self.archive.index(),
            "CAPEX loop requires this exact sealed output and fixed role",
        )?;
        archive.matches(file)
    }
    pub(crate) fn container(&self) -> io::Result<&File> {
        self.revalidate()?;
        Ok(&self.container)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use flate2::{Compression, write::DeflateEncoder};
    use std::io::{Read, Write};
    use std::time::Duration;

    fn until() -> Instant {
        Instant::now() + Duration::from_secs(10)
    }
    fn compressed(bytes: &[u8]) -> Vec<u8> {
        let mut encoder = DeflateEncoder::new(Vec::new(), Compression::best());
        encoder.write_all(bytes).unwrap();
        encoder.finish().unwrap()
    }
    fn stream(bytes: &[u8], encoded: &[u8]) -> (File, Entry, String) {
        let mut file = tempfile::tempfile().unwrap();
        file.write_all(&[0x44; 37]).unwrap();
        file.write_all(encoded).unwrap();
        let entry = Entry {
            local: 0,
            data: 37,
            compressed: encoded.len() as u64,
            expanded: bytes.len() as u64,
            crc: crc32fast::hash(bytes),
            extra: Vec::new(),
        };
        (file, entry, format!("{:x}", Sha256::digest(bytes)))
    }

    #[test]
    fn capex_stream_consumes_exact_input_and_output_across_multiple_buffers() {
        let mut state = 0x5319_ab27_u32;
        let noise: Vec<_> = (0..CHUNK * 3 + 17)
            .map(|_| {
                state ^= state << 13;
                state ^= state >> 17;
                state ^= state << 5;
                state as u8
            })
            .collect();
        for bytes in [noise, vec![b'a'; CHUNK * 3 + 17]] {
            let encoded = compressed(&bytes);
            let (source, entry, hash) = stream(&bytes, &encoded);
            let mut output = tempfile::tempfile().unwrap();
            inflate_into(&source, &entry, &output, &hash, until()).unwrap();
            let mut read = Vec::new();
            output.read_to_end(&mut read).unwrap();
            assert_eq!(read, bytes);
        }
    }

    #[test]
    fn capex_stream_rejects_truncation_trailing_streams_crc_hash_and_output_overrun() {
        let bytes = vec![0x5a; CHUNK + 19];
        let encoded = compressed(&bytes);
        for change in 0..8 {
            let mut data = encoded.clone();
            match change {
                0 => {
                    data.pop();
                }
                1 => data.push(0),
                2 => data.extend_from_slice(&encoded),
                3 => data[0] ^= 0xff,
                _ => {}
            }
            let (source, mut entry, mut hash) = stream(&bytes, &data);
            match change {
                4 => entry.crc ^= 1,
                5 => hash = "0".repeat(64),
                6 => entry.expanded -= 1,
                7 => entry.expanded += 1,
                _ => {}
            }
            let output = tempfile::tempfile().unwrap();
            assert!(
                inflate_into(&source, &entry, &output, &hash, until()).is_err(),
                "mutation {change}"
            );
            assert!(output.metadata().unwrap().len() <= entry.expanded);
        }
        let (source, entry, hash) = stream(&bytes, &encoded);
        let output = tempfile::tempfile().unwrap();
        assert!(inflate_into(&source, &entry, &output, &hash, Instant::now()).is_err());
        assert_eq!(output.metadata().unwrap().len(), 0);
    }

    #[test]
    fn capex_seals_actually_reject_write_resize_shared_mapping_and_execute_bit() {
        fn check_rejected_operation(output: &SealedOutput) {
            let observed = Identity::of(&output.file.metadata().unwrap());
            // Linux may update write timestamps before rejecting a sealed
            // pwrite. The bytes, inode, owner, mode and extent must remain
            // immutable; any actual full-identity change revokes this witness.
            let mut expected = output.identity;
            expected.mtime = observed.mtime;
            expected.ctime = observed.ctime;
            assert_eq!(observed, expected);
            assert_eq!(
                unsafe { libc::fcntl(output.file.as_raw_fd(), libc::F_GET_SEALS) },
                REQUIRED_SEALS
            );
            if observed == output.identity {
                output.revalidate().unwrap();
            } else {
                assert_eq!(
                    output.revalidate().unwrap_err().kind(),
                    io::ErrorKind::InvalidData
                );
            }
        }
        let output = fresh_output().unwrap();
        output.write_all_at(&[0x31; 4096], 0).unwrap();
        let output = SealedOutput::seal(output, 4096).unwrap();
        output.revalidate().unwrap();
        assert_eq!(
            output.file.write_at(b"x", 0).unwrap_err().raw_os_error(),
            Some(libc::EPERM)
        );
        check_rejected_operation(&output);
        for bytes in [0, 4095, 4097, 8192] {
            assert_eq!(
                unsafe { libc::ftruncate(output.file.as_raw_fd(), bytes) },
                -1
            );
            assert_eq!(io::Error::last_os_error().raw_os_error(), Some(libc::EPERM));
            check_rejected_operation(&output);
        }
        let mapped = unsafe {
            libc::mmap(
                std::ptr::null_mut(),
                4096,
                libc::PROT_READ | libc::PROT_WRITE,
                libc::MAP_SHARED,
                output.file.as_raw_fd(),
                0,
            )
        };
        assert_eq!(mapped, libc::MAP_FAILED);
        assert_eq!(io::Error::last_os_error().raw_os_error(), Some(libc::EPERM));
        check_rejected_operation(&output);
        assert_eq!(unsafe { libc::fchmod(output.file.as_raw_fd(), 0o500) }, -1);
        assert_eq!(io::Error::last_os_error().raw_os_error(), Some(libc::EPERM));
        check_rejected_operation(&output);
        let mut bytes = [0; 4096];
        output.file.read_exact_at(&mut bytes, 0).unwrap();
        assert_eq!(bytes, [0x31; 4096]);
    }

    #[test]
    fn capex_cannot_seal_while_a_real_writable_mapping_survives() {
        let file = fresh_output().unwrap();
        file.write_all_at(&[0x55; 4096], 0).unwrap();
        let mapped = unsafe {
            libc::mmap(
                std::ptr::null_mut(),
                4096,
                libc::PROT_READ | libc::PROT_WRITE,
                libc::MAP_SHARED,
                file.as_raw_fd(),
                0,
            )
        };
        assert_ne!(mapped, libc::MAP_FAILED);
        struct Mapping(*mut libc::c_void);
        impl Drop for Mapping {
            fn drop(&mut self) {
                assert_eq!(unsafe { libc::munmap(self.0, 4096) }, 0);
            }
        }
        let _mapping = Mapping(mapped);
        let error = SealedOutput::seal(file, 4096).unwrap_err();
        assert_eq!(error.raw_os_error(), Some(libc::EBUSY));
    }

    fn syntax_fixture() -> (Vec<u8>, u64, usize, usize) {
        let payload = vec![0x32; 4096];
        let deflated = compressed(&payload);
        let mut bytes = Vec::new();
        let mut central = Vec::new();
        let mut descriptor = 0;
        for (index, name) in MEMBERS.iter().enumerate() {
            let original = index == 4;
            let body = if original {
                deflated.as_slice()
            } else {
                b"data".as_slice()
            };
            let expanded = if original { payload.len() } else { body.len() };
            let crc = if original {
                crc32fast::hash(&payload)
            } else {
                crc32fast::hash(body)
            };
            let offset = bytes.len();
            let mut local = vec![0; 30];
            local[..4].copy_from_slice(b"PK\x03\x04");
            local[4..6].copy_from_slice(&(if original { 20_u16 } else { 10 }).to_le_bytes());
            local[6..8].copy_from_slice(&(if original { 0x808_u16 } else { 0x800 }).to_le_bytes());
            local[8..10].copy_from_slice(&(if original { 8_u16 } else { 0 }).to_le_bytes());
            local[26..28].copy_from_slice(&(name.len() as u16).to_le_bytes());
            if !original {
                local[14..18].copy_from_slice(&crc.to_le_bytes());
                local[18..22].copy_from_slice(&(body.len() as u32).to_le_bytes());
                local[22..26].copy_from_slice(&(expanded as u32).to_le_bytes());
            }
            bytes.extend_from_slice(&local);
            bytes.extend_from_slice(name);
            bytes.extend_from_slice(body);
            let mut row = vec![0; 46];
            row[..4].copy_from_slice(b"PK\x01\x02");
            row[4..6].copy_from_slice(&(if original { 20_u16 } else { 0x030a }).to_le_bytes());
            row[6..8].copy_from_slice(&local[4..6]);
            row[8..10].copy_from_slice(&local[6..8]);
            row[10..12].copy_from_slice(&local[8..10]);
            row[16..20].copy_from_slice(&crc.to_le_bytes());
            row[20..24].copy_from_slice(&(body.len() as u32).to_le_bytes());
            row[24..28].copy_from_slice(&(expanded as u32).to_le_bytes());
            row[28..30].copy_from_slice(&(name.len() as u16).to_le_bytes());
            row[38..42]
                .copy_from_slice(&(if original { 0_u32 } else { 0x81a4_0000 }).to_le_bytes());
            row[42..46].copy_from_slice(&(offset as u32).to_le_bytes());
            central.extend_from_slice(&row);
            central.extend_from_slice(name);
            if original {
                descriptor = bytes.len();
                bytes.extend_from_slice(b"PK\x07\x08");
                bytes.extend_from_slice(&crc.to_le_bytes());
                bytes.extend_from_slice(&(body.len() as u32).to_le_bytes());
                bytes.extend_from_slice(&(expanded as u32).to_le_bytes());
            }
        }
        bytes.resize(bytes.len().div_ceil(4096) * 4096, 0);
        let block = bytes.len();
        bytes.resize(block + 8192, 0);
        bytes[block..block + 8].copy_from_slice(&8184_u64.to_le_bytes());
        bytes[block + 8168..block + 8176].copy_from_slice(&8184_u64.to_le_bytes());
        bytes[block + 8176..block + 8192].copy_from_slice(b"APK Sig Block 42");
        let central_at = bytes.len();
        bytes.extend_from_slice(&central);
        let end = bytes.len();
        bytes.resize(end + 22, 0);
        bytes[end..end + 4].copy_from_slice(b"PK\x05\x06");
        bytes[end + 8..end + 10].copy_from_slice(&5_u16.to_le_bytes());
        bytes[end + 10..end + 12].copy_from_slice(&5_u16.to_le_bytes());
        bytes[end + 12..end + 16].copy_from_slice(&(central.len() as u32).to_le_bytes());
        bytes[end + 16..end + 20].copy_from_slice(&(central_at as u32).to_le_bytes());
        let comment = bytes.len().div_ceil(4096) * 4096 - bytes.len();
        bytes[end + 20..end + 22].copy_from_slice(&(comment as u16).to_le_bytes());
        bytes.resize(bytes.len() + comment, 0);
        (bytes, payload.len() as u64, descriptor, central_at)
    }
    fn syntax(bytes: &[u8], expanded: u64) -> io::Result<Entry> {
        let mut file = tempfile::tempfile().unwrap();
        file.write_all(bytes)?;
        compressed_window(&file, bytes.len() as u64, expanded, until())
    }

    #[test]
    fn capex_zip_rejects_overlaps_wrong_local_records_descriptor_and_terminal_aliases() {
        // A structural fixture is not a signed CAPEX. It never passes the
        // public constructor's compiled whole-container hash.
        let (bytes, expanded, descriptor, central) = syntax_fixture();
        syntax(&bytes, expanded).unwrap();
        let eocd = central + entries_bytes(&bytes, central);
        for at in [
            0,
            4,
            6,
            8,
            14,
            18,
            22,
            26,
            28,
            30,
            descriptor,
            descriptor + 4,
            descriptor + 8,
            descriptor + 12,
            descriptor + 16,
            central - 24,
            central - 16,
            central,
            central + 4,
            central + 6,
            central + 8,
            central + 10,
            central + 16,
            central + 20,
            central + 24,
            central + 28,
            central + 30,
            central + 32,
            central + 34,
            central + 36,
            central + 38,
            central + 42,
            central + 46,
            eocd + 4,
            eocd + 6,
            eocd + 8,
            eocd + 10,
            eocd + 12,
            eocd + 16,
            eocd + 20,
            eocd + 22,
        ] {
            let mut changed = bytes.clone();
            changed[at] ^= 1;
            assert!(syntax(&changed, expanded).is_err(), "offset {at}");
        }
        assert!(syntax(&bytes[..bytes.len() - 1], expanded).is_err());
        assert!(syntax(&bytes, expanded + 1).is_err());
        let mut extra = bytes.clone();
        extra.extend_from_slice(&[0; 4096]);
        assert!(syntax(&extra, expanded).is_err());
    }
    fn entries_bytes(bytes: &[u8], central: usize) -> usize {
        let mut at = central;
        for _ in 0..5 {
            at += 46
                + le16(bytes, at + 28).unwrap() as usize
                + le16(bytes, at + 30).unwrap() as usize;
        }
        at - central
    }

    #[test]
    fn capex_constructor_does_not_promote_a_host_copy_shape_or_unknown_role() {
        let (bytes, _, _, _) = syntax_fixture();
        let directory = tempfile::tempdir().unwrap();
        let path = directory.path().join("capex");
        std::fs::write(&path, &bytes).unwrap();
        let rows = crate::production_execution_profile::apex_inputs::original_inputs().unwrap();
        for index in [0, 38, usize::MAX] {
            assert!(ImmutableCapex::decode(File::open(&path).unwrap(), index, until()).is_err());
        }
        let index = rows
            .iter()
            .position(|r| r.input.container_file == "com.android.resolv.capex")
            .unwrap();
        assert!(ImmutableCapex::decode(File::open(&path).unwrap(), index, until()).is_err());
        assert!(ImmutableCapex::decode(File::open(&path).unwrap(), index, Instant::now()).is_err());
        let writer = std::fs::OpenOptions::new()
            .read(true)
            .write(true)
            .open(&path)
            .unwrap();
        assert!(container_identity(&writer).is_err());
        assert!(container_identity(&File::open("/dev/null").unwrap()).is_err());
        let temporary = tempfile::tempfile().unwrap();
        temporary.write_all_at(&[0x31; 4096], 0).unwrap();
        assert!(SealedOutput::seal(temporary, 4096).is_err());
    }
}
