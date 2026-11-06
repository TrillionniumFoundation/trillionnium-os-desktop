//! A bounded, generation-private diagnostic sink, never lifecycle authority.
//!
//! The paired constructor primes the actual loaded KernelLogger with a nonce
//! marker, then removes its temporary environment and seals the writer across
//! exec. The host checks the bytes after the real HELLO identity admission.
//! A fixed-size shmem file has no reader dependency and cannot grow on overflow.
//! This captures a prefix, not a promise that every logger write succeeded.
use super::domain::{self, Identity};
use super::policy;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::fs::{File, OpenOptions};
use std::io;
use std::os::fd::{AsRawFd, FromRawFd, IntoRawFd, RawFd};
use std::os::unix::fs::{FileExt, MetadataExt, OpenOptionsExt};
use std::sync::{Arc, Mutex};

pub(crate) const FD: RawFd = 202;
pub(crate) const CAPACITY: usize = 256 * 1024;
pub(crate) const ENTRY_ENV: &str = "DROIDLOOM_RELAY_ENTRY_INIT_LOG";
pub(crate) const ABI_ENV: &str = "DROIDLOOM_INIT_LOG_ABI";
pub(crate) const FD_ENV: &str = "DROIDLOOM_INIT_LOG_FD";
pub(crate) const LOGGER_ENV: &str = "ANDROID_FILE__dev_kmsg";
pub(crate) const ABI: &str = "1";
const SEALS: i32 = libc::F_SEAL_GROW | libc::F_SEAL_SHRINK | libc::F_SEAL_SEAL;

fn error(message: &'static str) -> io::Error { domain::error(message) }

pub(crate) fn marker(nonce: &[u8; 32]) -> Vec<u8> {
    format!("<6>droidloom-init-log: P4_INIT_LOG_V1 nonce={}\n<6>droidloom-init-log: P4_INIT_LOG_CACHED_V1 nonce={}\n",
        policy::hex(nonce), policy::hex(nonce)).into_bytes()
}

/// Validate only the explicitly inherited diagnostic writer. A pipe, socket,
/// ordinary file, arbitrary size, append position or writable growth is denied.
pub(crate) fn validate_writer(file: &File) -> io::Result<Identity> {
    let m = file.metadata()?;
    let flags = unsafe { libc::fcntl(file.as_raw_fd(), libc::F_GETFL) };
    if flags < 0 { return Err(io::Error::last_os_error()); }
    let seals = unsafe { libc::fcntl(file.as_raw_fd(), libc::F_GET_SEALS) };
    if seals < 0 { return Err(io::Error::last_os_error()); }
    let mut fs: libc::statfs = unsafe { std::mem::zeroed() };
    if unsafe { libc::fstatfs(file.as_raw_fd(), &mut fs) } < 0 {
        return Err(io::Error::last_os_error());
    }
    if !m.is_file() || m.uid() != unsafe { libc::geteuid() }
        || m.gid() != unsafe { libc::getegid() } || m.nlink() != 0
        || m.mode() & 0o7777 != 0o600 || m.size() != CAPACITY as u64
        || flags & libc::O_ACCMODE != libc::O_WRONLY || flags & libc::O_NONBLOCK == 0
        || flags & (libc::O_APPEND | libc::O_PATH) != 0 || seals != SEALS
        || fs.f_type as u64 != 0x0102_1994
    {
        return Err(error("init diagnostic writer identity/type/flags/seals differ"));
    }
    Identity::of(file)
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
pub(crate) struct Observation {
    pub schema: u32,
    pub nonce: String,
    pub device: u64,
    pub inode: u64,
    pub capacity_bytes: usize,
    pub marker_verified_after_held_init_hello: bool,
    pub retirement_proven_before_capture: bool,
    pub observed_writer_offset: Option<u64>,
    pub captured_bytes: usize,
    pub captured_sha256: String,
    pub captured_hex: String,
    pub capacity_reached: bool,
    pub stream_completeness_claimed: bool,
    pub exact_writer_per_line_proven: bool,
    pub source_scope: String,
    pub first_error: Option<String>,
    pub secondary_errors: Vec<String>,
    pub held_fds_closed: bool,
}
impl Observation {
    fn remember(&mut self, message: String) {
        let mut end = message.len().min(512);
        while !message.is_char_boundary(end) { end -= 1; }
        let message = message[..end].to_owned();
        if self.first_error.is_none() { self.first_error = Some(message); }
        else if self.secondary_errors.len() < 4 { self.secondary_errors.push(message); }
    }
}

pub(crate) struct Capture {
    read: Option<File>,
    write: Option<File>,
    identity: Identity,
    nonce: [u8; 32],
    admission_attempted: bool,
    primed: bool,
}

/// Owner retains the same sink through every fallible attach/start step. A
/// partially constructed Session or failed worker spawn cannot silently drop
/// the only copy. Capture/close is still a single take of the actual two FDs.
#[derive(Clone)]
pub(crate) struct SharedCapture(Arc<Mutex<Option<Capture>>>);
impl SharedCapture {
    pub(crate) fn new(nonce: [u8; 32]) -> io::Result<Self> {
        Ok(Self(Arc::new(Mutex::new(Some(Capture::new(nonce)?)))))
    }
    pub(crate) fn duplicate_writer(&self) -> io::Result<File> {
        let held = self.0.lock().map_err(|_| error("init log owner lock poisoned"))?;
        held.as_ref().ok_or_else(|| error("init log capture already finalized"))?.writer()?.try_clone()
    }
    pub(crate) fn require_marker(&self) -> io::Result<()> {
        let mut held = self.0.lock().map_err(|_| error("init log owner lock poisoned"))?;
        held.as_mut().ok_or_else(|| error("init log capture already finalized"))?.require_marker()
    }
    pub(crate) fn finish(&self, retired: bool) -> Option<Observation> {
        let (capture, poisoned) = match self.0.lock() {
            Ok(mut held) => (held.take(), false),
            Err(poison) => (poison.into_inner().take(), true),
        };
        let mut result = capture?.finish(retired && !poisoned);
        if poisoned { result.remember("init log owner lock poisoned".into()); }
        Some(result)
    }
}
impl Capture {
    pub(crate) fn new(nonce: [u8; 32]) -> io::Result<Self> {
        let fd = unsafe {
            libc::memfd_create(c"droidloom-init-log".as_ptr(), libc::MFD_CLOEXEC | libc::MFD_ALLOW_SEALING)
        };
        if fd < 0 { return Err(io::Error::last_os_error()); }
        let read = unsafe { File::from_raw_fd(fd) };
        if unsafe { libc::fchmod(fd, 0o600) } < 0
            || unsafe { libc::ftruncate(fd, CAPACITY as libc::off_t) } < 0
        {
            return Err(io::Error::last_os_error());
        }
        if unsafe { libc::fcntl(fd, libc::F_ADD_SEALS, SEALS) } < 0 {
            return Err(io::Error::last_os_error());
        }
        // Reopening our own anonymous object creates a write-only OFD. The
        // parent retains this OFD solely to observe its final offset; pread on
        // the other OFD never changes the logger's position.
        let write = OpenOptions::new().write(true)
            .custom_flags(libc::O_NONBLOCK | libc::O_CLOEXEC)
            .open(format!("/proc/self/fd/{fd}"))?;
        let identity = validate_writer(&write)?;
        if Identity::of(&read)? != identity { return Err(error("init log reopen changed inode")); }
        let result = Self { read: Some(read), write: Some(write), identity, nonce,
            admission_attempted: false, primed: false };
        if result.position()? != 0 { return Err(error("new init log writer offset is not zero")); }
        Ok(result)
    }

    pub(crate) fn writer(&self) -> io::Result<&File> {
        self.write.as_ref().ok_or_else(|| error("init log writer was already consumed"))
    }
    fn reader(&self) -> io::Result<&File> {
        self.read.as_ref().ok_or_else(|| error("init log reader was already consumed"))
    }
    fn position(&self) -> io::Result<u64> {
        let value = unsafe { libc::lseek(self.writer()?.as_raw_fd(), 0, libc::SEEK_CUR) };
        if value < 0 { return Err(io::Error::last_os_error()); }
        if value as u64 > CAPACITY as u64 { return Err(error("init log offset exceeds fixed capacity")); }
        Ok(value as u64)
    }
    fn validate(&self) -> io::Result<()> {
        if validate_writer(self.writer()?)? != self.identity
            || Identity::of(self.reader()?)? != self.identity
        {
            return Err(error("held init log identity changed"));
        }
        Ok(())
    }
    /// Called only after InitPeer::accept has retained the real init process,
    /// executable and namespace proof, and before creating the relay broker.
    pub(crate) fn require_marker(&mut self) -> io::Result<()> {
        if self.admission_attempted { return Err(error("init logger marker admission is one attempt")); }
        self.admission_attempted = true;
        self.validate()?;
        let expected = marker(&self.nonce);
        if self.position()? < expected.len() as u64 {
            return Err(error("actual init KernelLogger did not write its generation marker"));
        }
        let mut actual = vec![0; expected.len()];
        self.reader()?.read_exact_at(&mut actual, 0)?;
        if actual != expected { return Err(error("actual init logger marker differs")); }
        self.validate()?;
        self.primed = true;
        Ok(())
    }
    /// Capture a stable prefix after retirement where possible. A failed
    /// retirement is explicitly labelled; its diagnostic read cannot certify
    /// that init stopped, that writes are complete, or that every line came
    /// from PID1 (pre-exec fork children may share the cached descriptor).
    pub(crate) fn finish(mut self, retired: bool) -> Observation {
        let mut out = Observation {
            schema: 1, nonce: policy::hex(&self.nonce), device: self.identity.device,
            inode: self.identity.inode, capacity_bytes: CAPACITY,
            marker_verified_after_held_init_hello: self.primed,
            retirement_proven_before_capture: retired, observed_writer_offset: None,
            captured_bytes: 0, captured_sha256: policy::hex(&Sha256::digest(b"")),
            captured_hex: String::new(), capacity_reached: false,
            stream_completeness_claimed: false, exact_writer_per_line_proven: false,
            source_scope: "generation-private cached init logger; fork-before-exec writers not individually attributed".into(),
            first_error: None, secondary_errors: Vec::new(), held_fds_closed: false,
        };
        let captured = (|| -> io::Result<()> {
            self.validate()?;
            let before = self.position()?;
            out.observed_writer_offset = Some(before);
            out.capacity_reached = before == CAPACITY as u64;
            let mut raw = vec![0; before as usize];
            self.reader()?.read_exact_at(&mut raw, 0)?;
            out.captured_bytes = raw.len();
            out.captured_sha256 = policy::hex(&Sha256::digest(&raw));
            out.captured_hex = policy::hex(&raw);
            self.validate()?;
            if self.position()? != before {
                return Err(error("init diagnostic writer moved during final capture"));
            }
            Ok(())
        })();
        if let Err(error) = captured { out.remember(error.to_string()); }
        // Explicit one-attempt close evidence; never retry a possibly reused
        // integer. The original capture error remains primary.
        let mut all_closed = true;
        for file in [self.write.take(), self.read.take()].into_iter().flatten() {
            if unsafe { libc::close(file.into_raw_fd()) } < 0 {
                all_closed = false;
                out.remember(format!("close init diagnostic FD: {}", io::Error::last_os_error()));
            }
        }
        out.held_fds_closed = all_closed;
        out
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;
    use std::os::unix::process::CommandExt;
    use std::process::Command;

    #[test]
    fn real_memfd_is_bounded_and_preserves_the_observed_prefix() {
        let mut capture = Capture::new([7; 32]).unwrap();
        // Explicit synthetic logger bytes; this is not Android ABI evidence.
        let head = marker(&[7; 32]);
        (&*capture.writer().unwrap()).write_all(&head).unwrap();
        capture.require_marker().unwrap();
        let tail = vec![b'x'; CAPACITY - head.len()];
        (&*capture.writer().unwrap()).write_all(&tail).unwrap();
        let overflow = (&*capture.writer().unwrap()).write(b"overflow").unwrap_err();
        assert_eq!(overflow.raw_os_error(), Some(libc::EPERM));
        let record = capture.finish(true);
        assert!(record.marker_verified_after_held_init_hello && record.capacity_reached);
        assert_eq!(record.captured_bytes, CAPACITY);
        assert!(record.captured_hex.starts_with(&policy::hex(&head)));
        assert!(record.held_fds_closed && record.first_error.is_none());
        assert!(!record.stream_completeness_claimed && !record.exact_writer_per_line_proven);
    }

    #[test]
    fn missing_or_foreign_marker_never_admits_a_generation() {
        let mut capture = Capture::new([8; 32]).unwrap();
        assert!(capture.require_marker().is_err());
        (&*capture.writer().unwrap()).write_all(&marker(&[8; 32])).unwrap();
        assert!(capture.require_marker().is_err());
        let record = capture.finish(false);
        assert!(!record.marker_verified_after_held_init_hello);
        assert!(!record.retirement_proven_before_capture);
        assert!(record.held_fds_closed);
        let mut wrong = Capture::new([8; 32]).unwrap();
        (&*wrong.writer().unwrap()).write_all(&marker(&[9; 32])).unwrap();
        assert!(wrong.require_marker().is_err());
        assert!(wrong.finish(false).held_fds_closed);
    }

    #[test]
    fn ordinary_file_and_read_write_descriptor_are_not_log_writers() {
        let capture = Capture::new([10; 32]).unwrap();
        assert!(validate_writer(capture.reader().unwrap()).is_err());
        assert!(validate_writer(&File::open("/dev/null").unwrap()).is_err());
        assert!(capture.finish(false).held_fds_closed);
    }

    #[test]
    fn attach_and_worker_start_error_seams_retain_the_owners_only_sink() {
        for phase in ["later attach field", "worker start"] {
            let owner = SharedCapture::new([12; 32]).unwrap();
            let mut writer = owner.duplicate_writer().unwrap();
            writer.write_all(&marker(&[12; 32])).unwrap();
            drop(writer);
            // Explicit failure seam around the actual shared type: later
            // field construction or thread creation returns Err and drops
            // the temporary Session copy. No HostContext/Android is invented.
            let failed = (|| -> io::Result<()> {
                let _partial_session = owner.clone();
                Err(error(phase))
            })().unwrap_err();
            assert_eq!(failed.to_string(), phase);
            let record = owner.finish(false).unwrap();
            assert_eq!(record.captured_hex, policy::hex(&marker(&[12; 32])));
            assert!(record.held_fds_closed);
            assert!(!record.marker_verified_after_held_init_hello);
            assert!(!record.retirement_proven_before_capture);
            assert!(owner.finish(false).is_none());
        }
    }

    #[test]
    fn poisoned_capture_keeps_data_and_closes_without_claiming_retirement() {
        let owner = SharedCapture::new([13; 32]).unwrap();
        let thread_copy = owner.clone();
        assert!(std::thread::spawn(move || {
            let _guard = thread_copy.0.lock().unwrap();
            panic!("owned diagnostic lock poison control");
        }).join().is_err());
        let record = owner.finish(true).unwrap();
        assert!(!record.retirement_proven_before_capture);
        assert!(record.held_fds_closed && record.first_error.unwrap().contains("poisoned"));
        assert!(owner.finish(false).is_none());
    }

    #[test]
    fn real_child_exec_does_not_receive_the_cloexec_writer() {
        let capture = Capture::new([11; 32]).unwrap();
        let raw = capture.writer().unwrap().as_raw_fd();
        let mut command = Command::new("/bin/sh");
        command.args(["-c", "test ! -e /proc/self/fd/202"]);
        unsafe {
            command.pre_exec(move || {
                if libc::dup3(raw, FD, libc::O_CLOEXEC) < 0 {
                    return Err(io::Error::last_os_error());
                }
                Ok(())
            });
        }
        assert!(command.status().unwrap().success());
        assert!(capture.finish(false).held_fds_closed);
    }
}
