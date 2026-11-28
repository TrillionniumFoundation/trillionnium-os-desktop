//! Protected boot identity for observation-only broker peers.
//! Only the boot kernel lineage can create or mutate this actual record type.
//! No broker read of a kernel task's proc entry is needed for this protocol.
use super::*;
use serde::{Deserialize, Serialize};

const RECORD: &str = "/run/droidloom-early/factory.json";
const PENDING: &std::ffi::CStr = c"factory.pending";
const FINAL: &std::ffi::CStr = c"factory.json";
const RECORD_LABEL: &[u8] = b"u:object_r:p4_linux_instance_record_t:s0";
const SCHEMA: &str = "droidloom-boot-factory-v1";

#[derive(Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct Record {
    schema: String,
    boot_id: String,
    pid: u32,
    pidfd_device: u64,
    pidfd_inode: u64,
    executable_device: u64,
    executable_inode: u64,
    executable_size: u64,
}

#[repr(C)]
#[derive(Default)]
struct PidInfo {
    mask: u64,
    cgroupid: u64,
    pid: u32,
    tgid: u32,
    ppid: u32,
    ruid: u32,
    rgid: u32,
    euid: u32,
    egid: u32,
    suid: u32,
    sgid: u32,
    fsuid: u32,
    fsgid: u32,
    exit_code: i32,
    coredump_mask: u32,
    coredump_signal: u32,
    supported_mask: u64,
}
const _: () = assert!(std::mem::size_of::<PidInfo>() == 80);

fn pid_info(file: &File) -> io::Result<PidInfo> {
    let mut value = PidInfo {
        mask: 3,
        ..PidInfo::default()
    };
    cv(unsafe { libc::ioctl(file.as_raw_fd(), 0xc050_ff0b_u64, &mut value) })?;
    if value.mask & 3 != 3 || value.pid <= 1 || value.pid != value.tgid {
        return Err(invalid("boot factory PIDFD identity is incomplete"));
    }
    Ok(value)
}

fn require_factory(info: &PidInfo, pid: u32) -> io::Result<()> {
    if info.pid != pid
        || info.ppid != 1
        || [
            info.ruid, info.rgid, info.euid, info.egid, info.suid, info.sgid, info.fsuid,
            info.fsgid,
        ]
        .iter()
        .any(|value| *value != 0)
    {
        return Err(invalid(
            "boot factory is no longer the original root child of Linux PID 1",
        ));
    }
    Ok(())
}

fn boot_id() -> io::Result<String> {
    let mut raw = String::new();
    File::open("/proc/sys/kernel/random/boot_id")?
        .take(64)
        .read_to_string(&mut raw)?;
    if raw.len() != 37 || !raw.ends_with('\n') {
        return Err(invalid(
            "boot factory requires the original canonical kernel boot ID",
        ));
    }
    let value = &raw[..36];
    for (index, byte) in value.bytes().enumerate() {
        let correct = if [8, 13, 18, 23].contains(&index) {
            byte == b'-'
        } else {
            byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte)
        };
        if !correct {
            return Err(invalid("boot factory kernel boot ID is malformed"));
        }
    }
    Ok(value.into())
}

#[derive(Debug)]
struct PublicationOperationError {
    operation: &'static str,
    source: io::Error,
}
impl std::fmt::Display for PublicationOperationError {
    fn fmt(&self, output: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(output, "{}: {}", self.operation, self.source)
    }
}
impl std::error::Error for PublicationOperationError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        Some(&self.source)
    }
}

/// Fixed source-owned operation names add diagnostics only. The original
/// failure and its error chain remain intact; no permission or success changes.
fn publication_operation<T>(operation: &'static str, result: io::Result<T>) -> io::Result<T> {
    result.map_err(|source| {
        io::Error::new(
            source.kind(),
            PublicationOperationError { operation, source },
        )
    })
}

fn own_published_executable() -> io::Result<File> {
    let selected = publication_operation("read published launcher", SharedKernelLauncher::read())?
        .ok_or_else(|| invalid("boot factory published selection is absent"))?;
    let program = publication_operation("read published manager ELF", selected.entry_program())?;
    if !publication_operation(
        "compare active manager ELF",
        program.matches_current_process(),
    )? {
        return Err(invalid(
            "boot factory identity does not execute the published manager",
        ));
    }
    publication_operation("open active manager ELF", File::open("/proc/self/exe"))
}

fn record_metadata(file: &File) -> io::Result<std::fs::Metadata> {
    let metadata = file.metadata()?;
    if !metadata.is_file()
        || metadata.uid() != 0
        || metadata.gid() != 0
        || metadata.mode() & 0o7777 != 0o400
        || metadata.nlink() != 1
        || metadata.len() == 0
        || metadata.len() > 2048
    {
        return Err(invalid(
            "boot factory record is not the original root read-only inode",
        ));
    }
    check_fs(file, libc::TMPFS_MAGIC)?;
    let mut label = [0_u8; 128];
    let length = unsafe {
        libc::fgetxattr(
            file.as_raw_fd(),
            c"security.selinux".as_ptr(),
            label.as_mut_ptr().cast(),
            label.len(),
        )
    };
    if length < 0 {
        return Err(io::Error::last_os_error());
    }
    let actual = &label[..length as usize];
    if actual.strip_suffix(&[0]).unwrap_or(actual) != RECORD_LABEL {
        return Err(invalid(
            "boot factory record has a foreign actual SELinux object label",
        ));
    }
    Ok(metadata)
}

struct RecordFile {
    file: File,
    node: (u64, u64),
    body: Vec<u8>,
    data: Record,
}
impl RecordFile {
    fn read() -> io::Result<Self> {
        let directory =
            open_root_trusted_directory(Path::new(HANDOFF)).map_err(io::Error::other)?;
        let raw = unsafe {
            libc::openat(
                directory.as_raw_fd(),
                FINAL.as_ptr(),
                libc::O_RDONLY | libc::O_CLOEXEC | libc::O_NOFOLLOW | libc::O_NONBLOCK,
            )
        };
        cv(raw)?;
        let file = unsafe { File::from_raw_fd(raw) };
        let metadata = record_metadata(&file)?;
        let mut body = vec![0; metadata.len() as usize];
        file.read_exact_at(&mut body, 0)?;
        let data: Record = serde_json::from_slice(&body).map_err(io::Error::other)?;
        if data.schema != SCHEMA || data.boot_id != boot_id()? || data.pid <= 1 {
            return Err(invalid(
                "boot factory record is from another schema, boot or process",
            ));
        }
        let value = Self {
            file,
            node: (metadata.dev(), metadata.ino()),
            body,
            data,
        };
        value.revalidate()?;
        Ok(value)
    }
    fn revalidate(&self) -> io::Result<()> {
        let metadata = record_metadata(&self.file)?;
        if (metadata.dev(), metadata.ino()) != self.node
            || metadata.len() as usize != self.body.len()
            || named_identity(Path::new(RECORD))? != self.node
            || self.data.boot_id != boot_id()?
        {
            return Err(invalid("original boot factory record was replaced"));
        }
        let mut body = vec![0; self.body.len()];
        self.file.read_exact_at(&mut body, 0)?;
        if body != self.body {
            return Err(invalid("original boot factory record contents changed"));
        }
        Ok(())
    }
    fn verify_process(&self, pidfd: &File, executable: &File) -> io::Result<()> {
        self.revalidate()?;
        if ended(pidfd)? || identity(pidfd)? != (self.data.pidfd_device, self.data.pidfd_inode) {
            return Err(invalid(
                "peer is not the same live boot factory PIDFS object",
            ));
        }
        require_factory(&pid_info(pidfd)?, self.data.pid)?;
        let image = executable.metadata()?;
        if (image.dev(), image.ino(), image.len())
            != (
                self.data.executable_device,
                self.data.executable_inode,
                self.data.executable_size,
            )
        {
            return Err(invalid(
                "boot factory and current owner do not share the published ELF",
            ));
        }
        if ended(pidfd)? {
            return Err(invalid(
                "original boot factory exited during identity verification",
            ));
        }
        Ok(())
    }
}

/// Keeps the original self PIDFD alive for the whole boot factory lifetime.
/// This is an identity record only: it contains no wait or readiness success.
pub(super) struct Publication {
    record: RecordFile,
    pidfd: File,
    executable: File,
}
impl Publication {
    pub(super) fn publish() -> io::Result<Self> {
        let mut operation = "validate factory MAC context";
        let result = (|| {
            cv(unsafe { droidloom_factory_context() })?;
            operation = "resolve published factory executable";
            let executable = own_published_executable()?;
            let pid = unsafe { libc::getpid() } as u32;
            operation = "open original factory PIDFD";
            let pidfd = original_process_handle(pid)?;
            operation = "validate original factory PIDFD lineage";
            require_factory(&pid_info(&pidfd)?, pid)?;
            operation = "stat original factory executable";
            let image = executable.metadata()?;
            operation = "stat original factory PIDFD";
            let node = identity(&pidfd)?;
            operation = "read original kernel boot ID";
            let data = Record {
                schema: SCHEMA.into(),
                boot_id: boot_id()?,
                pid,
                pidfd_device: node.0,
                pidfd_inode: node.1,
                executable_device: image.dev(),
                executable_inode: image.ino(),
                executable_size: image.len(),
            };
            operation = "serialize factory identity record";
            let mut body = serde_json::to_vec(&data).map_err(io::Error::other)?;
            body.push(b'\n');
            operation = "walk trusted factory handoff directory";
            let trusted =
                open_root_trusted_directory(Path::new(HANDOFF)).map_err(io::Error::other)?;
            operation = "open factory handoff directory for sync";
            let directory = std::fs::OpenOptions::new()
                .read(true)
                .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
                .open(HANDOFF)?;
            operation = "compare original factory handoff directory";
            if identity(&trusted)? != identity(&directory)? {
                return Err(invalid("boot factory publication directory changed"));
            }
            operation = "create pending factory identity record";
            let raw = unsafe {
                libc::openat(
                    directory.as_raw_fd(),
                    PENDING.as_ptr(),
                    libc::O_RDWR
                        | libc::O_CREAT
                        | libc::O_EXCL
                        | libc::O_CLOEXEC
                        | libc::O_NOFOLLOW,
                    0o600,
                )
            };
            cv(raw)?;
            let mut pending = unsafe { File::from_raw_fd(raw) };
            operation = "write pending factory identity record";
            pending.write_all(&body)?;
            operation = "sync pending factory identity contents";
            pending.sync_all()?;
            operation = "seal pending factory identity mode";
            cv(unsafe { libc::fchmod(pending.as_raw_fd(), 0o400) })?;
            operation = "sync sealed factory identity metadata";
            pending.sync_all()?;
            operation = "validate pending factory identity label";
            record_metadata(&pending)?;
            operation = "revalidate factory MAC context";
            cv(unsafe { droidloom_factory_context() })?;
            operation = "revalidate original factory PIDFD lineage";
            require_factory(&pid_info(&pidfd)?, pid)?;
            operation = "publish original factory identity name";
            let result = unsafe {
                libc::syscall(
                    libc::SYS_renameat2,
                    directory.as_raw_fd(),
                    PENDING.as_ptr(),
                    directory.as_raw_fd(),
                    FINAL.as_ptr(),
                    libc::RENAME_NOREPLACE,
                )
            };
            if result != 0 {
                return Err(io::Error::last_os_error());
            }
            operation = "sync published factory identity directory";
            directory.sync_all()?;
            drop(pending); // Keep no writable record description after publication.
            operation = "read back published factory identity";
            let record = RecordFile::read()?;
            if record.data != data || record.body != body {
                return Err(invalid(
                    "atomic boot factory publication differs from its source facts",
                ));
            }
            let value = Self {
                record,
                pidfd,
                executable,
            };
            operation = "revalidate published factory identity";
            value.revalidate()?;
            Ok(value)
        })();
        publication_operation(operation, result)
    }
    pub(super) fn revalidate(&self) -> io::Result<()> {
        cv(unsafe { droidloom_factory_context() })?;
        self.record.verify_process(&self.pidfd, &self.executable)
    }
}

fn original_process_handle(pid: u32) -> io::Result<File> {
    let raw = unsafe { libc::syscall(libc::SYS_pidfd_open, pid, 0_u32) };
    if raw < 0 {
        return Err(io::Error::last_os_error());
    }
    let file = unsafe { File::from_raw_fd(raw as i32) };
    if ended(&file)? {
        return Err(invalid("boot factory self PIDFD is already retired"));
    }
    Ok(file)
}

fn credentials(channel: &File) -> io::Result<libc::ucred> {
    let mut value: libc::ucred = unsafe { std::mem::zeroed() };
    let mut size = std::mem::size_of_val(&value) as libc::socklen_t;
    cv(unsafe {
        libc::getsockopt(
            channel.as_raw_fd(),
            libc::SOL_SOCKET,
            libc::SO_PEERCRED,
            (&mut value as *mut libc::ucred).cast(),
            &mut size,
        )
    })?;
    if size as usize != std::mem::size_of_val(&value)
        || value.pid <= 1
        || value.uid != 0
        || value.gid != 0
    {
        return Err(invalid("boot factory native peer credentials differ"));
    }
    Ok(value)
}
fn peer_security(channel: &File) -> io::Result<()> {
    let mut bytes = [0_u8; 256];
    let mut size = bytes.len() as libc::socklen_t;
    cv(unsafe {
        libc::getsockopt(
            channel.as_raw_fd(),
            libc::SOL_SOCKET,
            libc::SO_PEERSEC,
            bytes.as_mut_ptr().cast(),
            &mut size,
        )
    })?;
    if size == 0 || size as usize > bytes.len() {
        return Err(invalid("boot factory native peer security length differs"));
    }
    let actual = &bytes[..size as usize];
    if actual.strip_suffix(&[0]).unwrap_or(actual) != FACTORY_SELINUX.as_bytes() {
        return Err(invalid(
            "boot factory native peer is outside its original kernel lineage",
        ));
    }
    Ok(())
}

/// A broker-origin observation handle bound to the protected original record.
/// It grants no signal, exec-stop, namespace or wait ownership.
pub(super) struct Observation {
    pub(super) pid: u32,
    pub(super) pidfd: File,
    record: RecordFile,
    executable: File,
}
impl Observation {
    pub(super) fn acquire(channel: &File) -> io::Result<Self> {
        let executable = own_published_executable()?;
        let record = RecordFile::read()?;
        let peer = credentials(channel)?;
        peer_security(channel)?;
        let mut raw = -1;
        let mut size = std::mem::size_of::<i32>() as libc::socklen_t;
        cv(unsafe {
            libc::getsockopt(
                channel.as_raw_fd(),
                libc::SOL_SOCKET,
                77,
                (&mut raw as *mut i32).cast(),
                &mut size,
            )
        })?;
        if raw < 0 {
            return Err(invalid(
                "boot factory native peer did not provide its original PIDFD",
            ));
        }
        let pidfd = unsafe { File::from_raw_fd(raw) };
        if size as usize != std::mem::size_of::<i32>() || peer.pid as u32 != record.data.pid {
            return Err(invalid(
                "boot factory peer PID differs from the protected original",
            ));
        }
        let value = Self {
            pid: peer.pid as u32,
            pidfd,
            record,
            executable,
        };
        value.revalidate(channel)?;
        Ok(value)
    }
    pub(super) fn revalidate(&self, channel: &File) -> io::Result<()> {
        let peer = credentials(channel)?;
        if peer.pid as u32 != self.pid {
            return Err(invalid("boot factory peer credentials changed"));
        }
        peer_security(channel)?;
        self.record.verify_process(&self.pidfd, &self.executable)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn publication_operation_retains_original_error_and_fixed_operation() {
        use std::error::Error as _;
        let error = publication_operation::<()>(
            "create pending factory identity record",
            Err(io::Error::from_raw_os_error(libc::EACCES)),
        )
        .unwrap_err();
        assert_eq!(error.kind(), io::ErrorKind::PermissionDenied);
        assert!(
            error
                .to_string()
                .starts_with("create pending factory identity record: ")
        );
        let detail = error
            .get_ref()
            .unwrap()
            .downcast_ref::<PublicationOperationError>()
            .unwrap();
        assert_eq!(
            detail
                .source()
                .unwrap()
                .downcast_ref::<io::Error>()
                .unwrap()
                .raw_os_error(),
            Some(libc::EACCES)
        );
    }

    #[test]
    fn boot_identity_schema_cannot_import_roles_or_wait_success() {
        let data = Record {
            schema: SCHEMA.into(),
            boot_id: boot_id().unwrap(),
            pid: std::process::id(),
            pidfd_device: 1,
            pidfd_inode: 2,
            executable_device: 3,
            executable_inode: 4,
            executable_size: 5,
        };
        let mut value = serde_json::to_value(&data).unwrap();
        value["waitid_status"] = serde_json::json!(0);
        assert!(serde_json::from_value::<Record>(value).is_err());
    }
    #[test]
    fn ordinary_host_cannot_publish_a_boot_factory_record() {
        assert!(Publication::publish().is_err());
    }
}
