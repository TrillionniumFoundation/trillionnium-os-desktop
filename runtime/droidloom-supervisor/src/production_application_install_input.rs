//! Bounded immutable APK-segment observations and nonblocking pipe streaming.
//! Only bytes read from the original received descriptor are written. Android
//! receives the creator-origin read pipe; it never receives this APK descriptor.
use super::*;
use sha2::{Digest, Sha256};
use std::io::Write;
use std::os::fd::{AsRawFd, RawFd};
use std::os::unix::fs::FileExt;
use std::time::Instant;
#[derive(Clone, Copy, Eq, PartialEq, Debug)]
struct Node {
    values: [u64; 7],
    times: [i64; 4],
}
fn node(file: &File) -> Result<Node> {
    let m = file.metadata()?;
    Ok(Node {
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
    })
}
fn before(deadline: Instant) -> Result<()> {
    require(Instant::now() < deadline, "APK input absolute deadline")
}
fn digest(
    file: &File,
    offset: u64,
    length: u64,
    deadline: Instant,
    progress: &mut dyn FnMut() -> Result<()>,
) -> Result<[u8; 32]> {
    let mut hash = Sha256::new();
    let mut position = 0;
    let mut buffer = [0_u8; 64 * 1024];
    let mut progress_after = Instant::now();
    while position < length {
        before(deadline)?;
        if Instant::now() >= progress_after {
            progress()?;
            progress_after = Instant::now() + std::time::Duration::from_millis(20);
        }
        let count = (length - position).min(buffer.len() as u64) as usize;
        file.read_exact_at(&mut buffer[..count], offset + position)?;
        hash.update(&buffer[..count]);
        position += count as u64;
    }
    Ok(hash.finalize().into())
}
#[derive(Clone, Debug, Serialize)]
pub(crate) struct SegmentObservation {
    pub index: usize,
    pub bytes: u64,
    pub sha256: String,
}
struct Segment {
    offset: u64,
    length: u64,
    sha256: [u8; 32],
}
pub(super) struct Payload {
    file: File,
    original: Node,
    segments: Vec<Segment>,
    total: u64,
}
impl Payload {
    pub(super) fn prepare(
        file: File,
        lengths: &[u64],
        deadline: Instant,
        progress: &mut dyn FnMut() -> Result<()>,
    ) -> Result<Self> {
        before(deadline)?;
        require(
            (1..=32).contains(&lengths.len()),
            "installation needs one through 32 original APK segments",
        )?;
        let original = node(&file)?;
        require(
            original.values[2] as u32 & libc::S_IFMT == libc::S_IFREG,
            "installation input is not a regular file",
        )?;
        let mut total = 0_u64;
        for &length in lengths {
            require(length >= 4, "APK segment is smaller than its ZIP header")?;
            total = total
                .checked_add(length)
                .filter(|v| *v <= super::install_command::MAX_INSTALL_BYTES)
                .ok_or_else(|| reject("complete APK input exceeds 2 GiB"))?;
        }
        require(
            original.values[6] == total,
            "APK segment lengths differ from the original file",
        )?;
        let mut segments = Vec::with_capacity(lengths.len());
        let mut offset = 0_u64;
        for &length in lengths {
            let mut magic = [0_u8; 4];
            file.read_exact_at(&mut magic, offset)?;
            require(
                magic == *b"PK\x03\x04",
                "APK segment is not an original ZIP body",
            )?;
            let sha256 = digest(&file, offset, length, deadline, progress)?;
            require(
                node(&file)? == original,
                "original APK input changed during hashing",
            )?;
            segments.push(Segment {
                offset,
                length,
                sha256,
            });
            offset += length;
        }
        Ok(Self {
            file,
            original,
            segments,
            total,
        })
    }
    pub(super) fn total(&self) -> u64 {
        self.total
    }
    pub(super) fn observations(&self) -> Vec<SegmentObservation> {
        self.segments
            .iter()
            .enumerate()
            .map(|(index, s)| SegmentObservation {
                index,
                bytes: s.length,
                sha256: s.sha256.iter().map(|byte| format!("{byte:02x}")).collect(),
            })
            .collect()
    }
    pub(super) fn len(&self) -> usize {
        self.segments.len()
    }
    pub(super) fn segment(&self, index: usize) -> Result<SegmentInput> {
        require(
            node(&self.file)? == self.original,
            "original APK input changed before stream",
        )?;
        let s = self
            .segments
            .get(index)
            .ok_or_else(|| reject("APK segment index outside original input"))?;
        Ok(SegmentInput {
            file: self.file.try_clone()?,
            original: self.original,
            offset: s.offset,
            length: s.length,
            sha256: s.sha256,
        })
    }
    pub(super) fn revalidate(
        &self,
        deadline: Instant,
        progress: &mut dyn FnMut() -> Result<()>,
    ) -> Result<()> {
        require(
            node(&self.file)? == self.original,
            "original APK input changed before commit",
        )?;
        for s in &self.segments {
            require(
                digest(&self.file, s.offset, s.length, deadline, progress)? == s.sha256
                    && node(&self.file)? == self.original,
                "original APK bytes changed before commit",
            )?;
        }
        before(deadline)
    }
}
pub(super) struct SegmentInput {
    file: File,
    original: Node,
    offset: u64,
    length: u64,
    sha256: [u8; 32],
}
impl SegmentInput {
    pub(super) fn bytes(&self) -> u64 {
        self.length
    }
}
pub(super) struct InputPump {
    input: SegmentInput,
    writer: Option<File>,
    buffer: [u8; 64 * 1024],
    buffer_at: usize,
    buffer_end: usize,
    sent: u64,
    hash: Sha256,
}
impl InputPump {
    pub(super) fn new(input: SegmentInput, writer: File) -> Result<Self> {
        let m = writer.metadata()?;
        let flags = unsafe { libc::fcntl(writer.as_raw_fd(), libc::F_GETFL) };
        require(
            m.mode() & libc::S_IFMT == libc::S_IFIFO
                && flags >= 0
                && flags & (libc::O_ACCMODE | libc::O_NONBLOCK | libc::O_PATH)
                    == libc::O_WRONLY | libc::O_NONBLOCK,
            "APK writer is not the creator's nonblocking write pipe",
        )?;
        // Rust's process startup ignores SIGPIPE. Refuse a changed disposition
        // before writing; a closed Android reader must be an ordinary error.
        let mut action: libc::sigaction = unsafe { std::mem::zeroed() };
        require(
            unsafe { libc::sigaction(libc::SIGPIPE, std::ptr::null(), &mut action) } == 0
                && action.sa_sigaction == libc::SIG_IGN,
            "APK writer requires an ignored SIGPIPE",
        )?;
        Ok(Self {
            input,
            writer: Some(writer),
            buffer: [0; 64 * 1024],
            buffer_at: 0,
            buffer_end: 0,
            sent: 0,
            hash: Sha256::new(),
        })
    }
    pub(super) fn descriptor(&self) -> Option<RawFd> {
        self.writer.as_ref().map(AsRawFd::as_raw_fd)
    }
    pub(super) fn close(&mut self) {
        self.writer.take();
    }
    pub(super) fn advance(&mut self, deadline: Instant) -> Result<()> {
        for _ in 0..16 {
            before(deadline)?;
            require(
                node(&self.input.file)? == self.input.original,
                "original APK changed while streaming",
            )?;
            if self.sent == self.input.length {
                let actual: [u8; 32] = self.hash.clone().finalize().into();
                require(
                    actual == self.input.sha256,
                    "streamed APK digest differs from the reviewed original",
                )?;
                self.close();
                return Ok(());
            }
            let writer = self
                .writer
                .as_mut()
                .ok_or_else(|| reject("APK pipe closed before complete stream"))?;
            if self.buffer_at == self.buffer_end {
                self.buffer_end =
                    (self.input.length - self.sent).min(self.buffer.len() as u64) as usize;
                self.buffer_at = 0;
                self.input.file.read_exact_at(
                    &mut self.buffer[..self.buffer_end],
                    self.input.offset + self.sent,
                )?;
            }
            match writer.write(&self.buffer[self.buffer_at..self.buffer_end]) {
                Ok(0) => return Err(reject("APK pipe returned an empty write")),
                Ok(count) => {
                    self.hash
                        .update(&self.buffer[self.buffer_at..self.buffer_at + count]);
                    self.sent += count as u64;
                    self.buffer_at += count;
                }
                Err(error) if error.kind() == io::ErrorKind::WouldBlock => return Ok(()),
                Err(error) if error.kind() == io::ErrorKind::Interrupted => continue,
                Err(error) => return Err(error.into()),
            }
        }
        Ok(())
    }
    pub(super) fn finish(&self) -> Result<()> {
        require(
            self.sent == self.input.length
                && self.writer.is_none()
                && <[u8; 32]>::from(self.hash.clone().finalize()) == self.input.sha256
                && node(&self.input.file)? == self.input.original,
            "Android did not receive one complete unchanged APK segment",
        )
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Read;
    use std::os::fd::FromRawFd;
    fn pipe() -> (File, File) {
        let mut f = [-1; 2];
        assert_eq!(
            unsafe { libc::pipe2(f.as_mut_ptr(), libc::O_CLOEXEC | libc::O_NONBLOCK) },
            0
        );
        unsafe { (File::from_raw_fd(f[0]), File::from_raw_fd(f[1])) }
    }
    #[test]
    fn installation_input_streams_exact_original_segments_with_backpressure() {
        let mut file = tempfile::tempfile().unwrap();
        let mut data = vec![7; 256 * 1024];
        data[..4].copy_from_slice(b"PK\x03\x04");
        file.write_all(&data).unwrap();
        file.write_all(b"PK\x03\x04split").unwrap();
        let deadline = Instant::now() + std::time::Duration::from_secs(5);
        let payload =
            Payload::prepare(file, &[data.len() as u64, 9], deadline, &mut || Ok(())).unwrap();
        assert_eq!(payload.total(), data.len() as u64 + 9);
        let (mut read, write) = pipe();
        let mut pump = InputPump::new(payload.segment(0).unwrap(), write).unwrap();
        let mut actual = Vec::new();
        let mut block = [0; 8192];
        while pump.descriptor().is_some() {
            pump.advance(deadline).unwrap();
            loop {
                match read.read(&mut block) {
                    Ok(0) => break,
                    Ok(n) => actual.extend_from_slice(&block[..n]),
                    Err(e) if e.kind() == io::ErrorKind::WouldBlock => break,
                    Err(e) => panic!("{e}"),
                }
            }
        }
        read.read_to_end(&mut actual).unwrap();
        pump.finish().unwrap();
        assert_eq!(actual, data);
        payload.revalidate(deadline, &mut || Ok(())).unwrap();
        assert_eq!(payload.observations().len(), 2);
    }
    #[test]
    fn installation_input_rejects_mutation_and_incomplete_or_overflowed_sets() {
        let mut file = tempfile::tempfile().unwrap();
        file.write_all(b"PK\x03\x04abcdef").unwrap();
        let deadline = Instant::now() + std::time::Duration::from_secs(5);
        for sizes in [vec![], vec![9], vec![u64::MAX], vec![3, 7]] {
            assert!(
                Payload::prepare(file.try_clone().unwrap(), &sizes, deadline, &mut || Ok(()))
                    .is_err()
            );
        }
        let payload =
            Payload::prepare(file.try_clone().unwrap(), &[10], deadline, &mut || Ok(())).unwrap();
        let (_read, write) = pipe();
        let mut pump = InputPump::new(payload.segment(0).unwrap(), write).unwrap();
        file.write_at(b"x", 5).unwrap();
        assert!(pump.advance(deadline).is_err());
        assert!(payload.revalidate(deadline, &mut || Ok(())).is_err());
        assert!(pump.finish().is_err());
    }
}
