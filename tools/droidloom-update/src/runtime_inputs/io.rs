//! Held input descriptors and finite filesystem-tool children.
use crate::contract::{FileRef, absolute, digest};
use crate::{Result, require};
use serde::Serialize;
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::ffi::{CString, OsString};
use std::fs::{self, File, OpenOptions};
use std::io::{Read, Write};
use std::os::fd::{AsRawFd, FromRawFd, OwnedFd};
use std::os::unix::ffi::OsStrExt;
use std::os::unix::fs::{DirBuilderExt, FileExt, MetadataExt, OpenOptionsExt, PermissionsExt};
use std::os::unix::process::CommandExt;
use std::path::{Component, Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::time::{Duration, Instant};

pub(crate) fn hash(raw: &[u8]) -> String {
    format!("{:x}", Sha256::digest(raw))
}
pub(crate) fn f9(meta: &fs::Metadata) -> Result<[u64; 9]> {
    let nanos = |s: i64, ns: i64| -> Result<u64> {
        require(
            s >= 0 && (0..1_000_000_000).contains(&ns),
            "bounded positive file timestamp",
        )?;
        (s as u64)
            .checked_mul(1_000_000_000)
            .and_then(|n| n.checked_add(ns as u64))
            .ok_or_else(|| "file timestamp overflow".into())
    };
    Ok([
        meta.dev(),
        meta.ino(),
        meta.mode() as u64,
        meta.uid() as u64,
        meta.gid() as u64,
        meta.nlink(),
        meta.len(),
        nanos(meta.mtime(), meta.mtime_nsec())?,
        nanos(meta.ctime(), meta.ctime_nsec())?,
    ])
}

pub(crate) struct Deadline {
    end: Instant,
}
impl Deadline {
    pub fn new(seconds: u64) -> Self {
        Self {
            end: Instant::now() + Duration::from_secs(seconds),
        }
    }
    pub fn check(&self) -> Result<()> {
        require(
            Instant::now() < self.end,
            "same absolute production-input deadline expired",
        )
    }
    pub fn remaining(&self) -> Result<Duration> {
        self.check()?;
        Ok(self.end.saturating_duration_since(Instant::now()))
    }
}

/// Resolve every actual pathname component without following symlinks.
pub(crate) fn open_file(path: &Path) -> Result<File> {
    absolute(path)?;
    let mut parent = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_PATH | libc::O_DIRECTORY | libc::O_CLOEXEC)
        .open("/")?;
    let names: Vec<_> = path
        .components()
        .filter_map(|c| match c {
            Component::Normal(s) => Some(s),
            _ => None,
        })
        .collect();
    require(!names.is_empty(), "file cannot be filesystem root")?;
    for (i, name) in names.iter().enumerate() {
        let name = CString::new(name.as_bytes())?;
        let last = i + 1 == names.len();
        let flags = if last {
            libc::O_RDONLY | libc::O_NONBLOCK
        } else {
            libc::O_PATH | libc::O_DIRECTORY
        };
        let fd = unsafe {
            libc::openat(
                parent.as_raw_fd(),
                name.as_ptr(),
                flags | libc::O_NOFOLLOW | libc::O_CLOEXEC,
            )
        };
        if fd < 0 {
            return Err(std::io::Error::last_os_error().into());
        }
        let opened = unsafe { File::from_raw_fd(fd) };
        if last {
            return Ok(opened);
        }
        parent = opened;
    }
    Err("missing final input component".into())
}
pub(crate) fn read_small_unpinned(
    path: &Path,
    expected: &str,
    max: u64,
) -> Result<(Vec<u8>, FileRef)> {
    require(digest(expected), "complete expected plan digest")?;
    let file = open_file(path)?;
    let meta = file.metadata()?;
    let before = f9(&meta)?;
    require(
        meta.is_file()
            && meta.nlink() == 1
            && meta.mode() & 0o7022 == 0
            && meta.len() > 0
            && meta.len() <= max,
        "bounded sealed plan file",
    )?;
    let mut raw = Vec::with_capacity(meta.len() as usize);
    (&file).take(max + 1).read_to_end(&mut raw)?;
    require(
        raw.len() as u64 == meta.len()
            && hash(&raw) == expected
            && f9(&file.metadata()?)? == before
            && f9(&open_file(path)?.metadata()?)? == before,
        "actual plan bytes and inode",
    )?;
    Ok((
        raw,
        FileRef {
            path: path.to_owned(),
            bytes: meta.len(),
            sha256: expected.into(),
            f9: before,
        },
    ))
}

struct Held {
    file: File,
    reference: FileRef,
}
pub(crate) struct Inputs {
    held: BTreeMap<PathBuf, Held>,
}
impl Inputs {
    pub fn new() -> Self {
        Self {
            held: BTreeMap::new(),
        }
    }
    pub fn add(&mut self, reference: &FileRef, deadline: &Deadline) -> Result<()> {
        deadline.check()?;
        reference.validate(crate::contract::MAX_INPUT)?;
        if let Some(prior) = self.held.get(&reference.path) {
            return require(
                prior.reference == *reference,
                "same path has contradictory input identities",
            );
        }
        require(
            self.held.len() < 1024,
            "bounded actual input descriptor closure",
        )?;
        let file = open_file(&reference.path)?;
        require(
            file.metadata()?.is_file() && f9(&file.metadata()?)? == reference.f9,
            format!("original full F9 mismatch: {}", reference.path.display()),
        )?;
        verify(&file, reference, deadline)?;
        self.held.insert(
            reference.path.clone(),
            Held {
                file,
                reference: reference.clone(),
            },
        );
        Ok(())
    }
    pub fn file(&self, reference: &FileRef) -> Result<&File> {
        let held = self
            .held
            .get(&reference.path)
            .ok_or("input was not actually verified")?;
        require(held.reference == *reference, "held input reference differs")?;
        Ok(&held.file)
    }
    pub fn descriptor_path(&self, reference: &FileRef) -> Result<PathBuf> {
        Ok(PathBuf::from(format!(
            "/proc/{}/fd/{}",
            std::process::id(),
            self.file(reference)?.as_raw_fd()
        )))
    }
    pub fn bytes(
        &mut self,
        reference: &FileRef,
        maximum: u64,
        deadline: &Deadline,
    ) -> Result<Vec<u8>> {
        require(reference.bytes <= maximum, "bounded small input")?;
        self.add(reference, deadline)?;
        let file = self.file(reference)?;
        let mut raw = vec![0; reference.bytes as usize];
        let mut offset = 0;
        while offset < raw.len() {
            deadline.check()?;
            let n = file.read_at(&mut raw[offset..], offset as u64)?;
            require(n != 0, "short held input")?;
            offset += n;
        }
        require(
            hash(&raw) == reference.sha256 && f9(&file.metadata()?)? == reference.f9,
            "held input bytes changed",
        )?;
        deadline.check()?;
        Ok(raw)
    }
    pub fn copy_new(
        &mut self,
        reference: &FileRef,
        path: &Path,
        mode: u32,
        deadline: &Deadline,
    ) -> Result<FileRef> {
        self.add(reference, deadline)?;
        let source = self.file(reference)?;
        let mut out = create_file(path, 0o600)?;
        let mut h = Sha256::new();
        let mut total = 0;
        let mut buf = vec![0_u8; 65536];
        while total < reference.bytes {
            deadline.check()?;
            let limit = buf.len().min((reference.bytes - total) as usize);
            let n = source.read_at(&mut buf[..limit], total)?;
            require(n > 0, "short held input copy")?;
            out.write_all(&buf[..n])?;
            h.update(&buf[..n]);
            total += n as u64;
        }
        require(
            format!("{:x}", h.finalize()) == reference.sha256
                && f9(&source.metadata()?)? == reference.f9,
            "copied input SHA and original inode",
        )?;
        out.set_permissions(fs::Permissions::from_mode(mode))?;
        out.sync_all()?;
        let r = actual_ref(path, deadline)?;
        require(
            r.bytes == reference.bytes && r.sha256 == reference.sha256,
            "whole copied input readback",
        )?;
        Ok(r)
    }
    pub fn revalidate_all(&self, deadline: &Deadline) -> Result<Vec<FileRef>> {
        let mut rows = Vec::new();
        for held in self.held.values() {
            verify(&held.file, &held.reference, deadline)?;
            rows.push(held.reference.clone());
        }
        deadline.check()?;
        Ok(rows)
    }
}
fn verify(file: &File, reference: &FileRef, deadline: &Deadline) -> Result<()> {
    require(
        f9(&file.metadata()?)? == reference.f9
            && f9(&open_file(&reference.path)?.metadata()?)? == reference.f9,
        "actual input identity before read",
    )?;
    let mut h = Sha256::new();
    let mut pos = 0;
    let mut buf = vec![0_u8; 65536];
    loop {
        deadline.check()?;
        let n = file.read_at(&mut buf, pos)?;
        if n == 0 {
            break;
        }
        pos += n as u64;
        require(pos <= reference.bytes, "input grew beyond exact bound")?;
        h.update(&buf[..n]);
    }
    require(
        pos == reference.bytes
            && format!("{:x}", h.finalize()) == reference.sha256
            && f9(&file.metadata()?)? == reference.f9
            && f9(&open_file(&reference.path)?.metadata()?)? == reference.f9,
        "whole input SHA/F9 after read",
    )?;
    deadline.check()
}

pub(crate) fn create_directory(path: &Path) -> Result<()> {
    absolute(path)?;
    fs::DirBuilder::new().mode(0o700).create(path)?;
    let meta = fs::symlink_metadata(path)?;
    require(
        meta.is_dir() && meta.uid() == unsafe { libc::geteuid() } && meta.mode() & 0o7777 == 0o700,
        "new private output directory",
    )?;
    Ok(())
}
pub(crate) fn create_file(path: &Path, mode: u32) -> Result<File> {
    Ok(OpenOptions::new()
        .read(true)
        .write(true)
        .create_new(true)
        .mode(mode)
        .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
        .open(path)?)
}
pub(crate) fn write_new(
    path: &Path,
    raw: &[u8],
    mode: u32,
    deadline: &Deadline,
) -> Result<FileRef> {
    deadline.check()?;
    let mut file = create_file(path, 0o600)?;
    file.write_all(raw)?;
    file.set_permissions(fs::Permissions::from_mode(mode))?;
    file.sync_all()?;
    deadline.check()?;
    let result = actual_ref(path, deadline)?;
    require(
        result.bytes == raw.len() as u64 && result.sha256 == hash(raw),
        "complete new-file readback",
    )?;
    Ok(result)
}
pub(crate) fn actual_ref(path: &Path, deadline: &Deadline) -> Result<FileRef> {
    let file = open_file(path)?;
    let before = f9(&file.metadata()?)?;
    require(
        before[2] & 0o170000 == 0o100000
            && before[5] == 1
            && before[6] <= crate::contract::MAX_INPUT,
        "bounded regular output",
    )?;
    let mut h = Sha256::new();
    let mut total = 0;
    let mut buf = vec![0_u8; 65536];
    loop {
        deadline.check()?;
        let n = file.read_at(&mut buf, total)?;
        if n == 0 {
            break;
        }
        total += n as u64;
        require(total <= before[6], "output grew during readback")?;
        h.update(&buf[..n]);
    }
    require(
        total == before[6]
            && f9(&file.metadata()?)? == before
            && f9(&open_file(path)?.metadata()?)? == before,
        "complete stable output",
    )?;
    deadline.check()?;
    Ok(FileRef {
        path: path.to_owned(),
        bytes: total,
        sha256: format!("{:x}", h.finalize()),
        f9: before,
    })
}
pub(crate) fn json_new<T: Serialize>(
    path: &Path,
    value: &T,
    deadline: &Deadline,
) -> Result<FileRef> {
    let mut raw = serde_json::to_vec_pretty(value)?;
    raw.push(b'\n');
    write_new(path, &raw, 0o400, deadline)
}

#[derive(Debug, Serialize)]
pub(crate) struct CommandRecord {
    pub argv: Vec<String>,
    pub tool: FileRef,
    pub pid: u32,
    pub starttime: u64,
    pub returncode: Option<i32>,
    pub signal: Option<i32>,
    pub reaped: bool,
    pub pidfd_events: i16,
    pub stdout: FileRef,
    pub stderr: FileRef,
    pub failure: Option<String>,
    pub cleanup_error: Option<String>,
}
pub(crate) struct Runner<'a> {
    pub root: &'a Path,
    pub deadline: &'a Deadline,
    pub epoch: u32,
    pub commands: Vec<CommandRecord>,
}
impl<'a> Runner<'a> {
    pub fn run(
        &mut self,
        inputs: &Inputs,
        tool: &FileRef,
        args: &[OsString],
    ) -> Result<(Vec<u8>, Vec<u8>)> {
        use std::os::unix::process::ExitStatusExt;
        self.deadline.check()?;
        require(
            self.commands.len() < 512,
            "bounded fixed tool command count",
        )?;
        let held = inputs.file(tool)?;
        verify(held, tool, self.deadline)?;
        let index = self.commands.len() + 1;
        let prefix = self.root.join(format!("{index:04}"));
        let stdout_path = prefix.with_extension("stdout");
        let stderr_path = prefix.with_extension("stderr");
        let out = create_file(&stdout_path, 0o600)?;
        let err = create_file(&stderr_path, 0o600)?;
        let parent = unsafe { libc::getpid() };
        let mut command = Command::new(format!("/proc/self/fd/{}", held.as_raw_fd()));
        command
            .arg0(&tool.path)
            .args(args)
            .env_clear()
            .env("PATH", "/usr/sbin:/usr/bin:/bin")
            .env("LC_ALL", "C")
            .env("TZ", "UTC")
            .env("E2FSPROGS_FAKE_TIME", self.epoch.to_string())
            .stdin(Stdio::null())
            .stdout(Stdio::from(out.try_clone()?))
            .stderr(Stdio::from(err.try_clone()?));
        unsafe {
            command.pre_exec(move || {
                if libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGKILL) != 0
                    || libc::getppid() != parent
                    || libc::prctl(libc::PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0
                {
                    return Err(std::io::Error::last_os_error());
                }
                for (which, value) in [
                    (libc::RLIMIT_AS, 512_u64 * 1024 * 1024),
                    (libc::RLIMIT_FSIZE, crate::contract::IMAGE_BYTES_MAX),
                    (libc::RLIMIT_CPU, 60),
                ] {
                    let limit = libc::rlimit {
                        rlim_cur: value,
                        rlim_max: value,
                    };
                    if libc::setrlimit(which, &limit) != 0 {
                        return Err(std::io::Error::last_os_error());
                    }
                }
                Ok(())
            });
        }
        let command_end = Instant::now() + self.deadline.remaining()?.min(Duration::from_secs(60));
        let mut child = command.spawn()?;
        let raw_pidfd = unsafe { libc::syscall(libc::SYS_pidfd_open, child.id(), 0) };
        if raw_pidfd < 0 {
            let original = std::io::Error::last_os_error();
            // The unreaped Child is still our direct child; its PID cannot be reused.
            let kill = child.kill();
            let reap = child.wait();
            return Err(format!(
                "atomic ownership unavailable: {original}; kill={kill:?}; reap={reap:?}"
            )
            .into());
        }
        let pidfd = unsafe { OwnedFd::from_raw_fd(raw_pidfd as i32) };
        let starttime = match proc_start(child.id()) {
            Ok(v) => v,
            Err(error) => {
                let cleanup = retire_child(&mut child, &pidfd);
                return Err(format!("original child stat: {error}; cleanup={cleanup:?}").into());
            }
        };
        let started = serde_json::json!({
            "pid":child.id(),"starttime":starttime,"tool":tool,
            "args":args.iter().map(|a| a.to_string_lossy()).collect::<Vec<_>>(),
            "maximum_seconds":60,"same_absolute_deadline":true
        });
        if let Err(error) = json_new(
            &prefix.with_extension("started.json"),
            &started,
            self.deadline,
        ) {
            let cleanup = retire_child(&mut child, &pidfd);
            return Err(format!("child start receipt: {error}; cleanup={cleanup:?}").into());
        }
        let waited: Result<_> = (|| {
            loop {
                self.deadline.check()?;
                require(
                    Instant::now() < command_end,
                    "fixed tool command deadline expired",
                )?;
                if let Some(status) = child.try_wait()? {
                    self.deadline.check()?;
                    require(
                        Instant::now() < command_end,
                        "tool exited after original command deadline",
                    )?;
                    return Ok(status);
                }
                require(
                    out.metadata()?.len() <= 4 * 1024 * 1024
                        && err.metadata()?.len() <= 4 * 1024 * 1024,
                    "bounded tool diagnostics",
                )?;
                let mut poll = libc::pollfd {
                    fd: pidfd.as_raw_fd(),
                    events: libc::POLLIN,
                    revents: 0,
                };
                let left = command_end
                    .saturating_duration_since(Instant::now())
                    .as_millis()
                    .min(50) as i32;
                let rc = unsafe { libc::poll(&mut poll, 1, left) };
                if rc < 0 && std::io::Error::last_os_error().raw_os_error() != Some(libc::EINTR) {
                    return Err(std::io::Error::last_os_error().into());
                }
            }
        })();
        let failure = waited.as_ref().err().map(ToString::to_string);
        let mut cleanup_error = None;
        let status = match waited {
            Ok(s) => Some(s),
            Err(_) => match retire_child(&mut child, &pidfd) {
                Ok(s) => Some(s),
                Err(e) => {
                    cleanup_error = Some(e.to_string());
                    None
                }
            },
        };
        out.set_permissions(fs::Permissions::from_mode(0o400))?;
        out.sync_all()?;
        err.set_permissions(fs::Permissions::from_mode(0o400))?;
        err.sync_all()?;
        // Failure records use a separate finite observation allowance and never
        // turn an expired work deadline into successful production publication.
        let evidence = Deadline::new(10);
        let events = pidfd_events(&pidfd)?;
        let record = CommandRecord {
            argv: std::iter::once(tool.path.to_string_lossy().into_owned())
                .chain(args.iter().map(|a| a.to_string_lossy().into_owned()))
                .collect(),
            tool: tool.clone(),
            pid: child.id(),
            starttime,
            returncode: status.as_ref().and_then(|s| s.code()),
            signal: status.as_ref().and_then(|s| s.signal()),
            reaped: status.is_some() && events & libc::POLLHUP != 0,
            pidfd_events: events,
            stdout: actual_ref(&stdout_path, &evidence)?,
            stderr: actual_ref(&stderr_path, &evidence)?,
            failure,
            cleanup_error,
        };
        json_new(&prefix.with_extension("result.json"), &record, &evidence)?;
        let ok = record.failure.is_none()
            && record.cleanup_error.is_none()
            && record.returncode == Some(0)
            && record.signal.is_none()
            && record.reaped
            && events & (libc::POLLERR | libc::POLLNVAL) == 0;
        self.commands.push(record);
        require(
            ok,
            "fixed tool did not exit zero and retire within its original deadline",
        )?;
        self.deadline.check()?;
        verify(held, tool, self.deadline)?;
        let stdout = fs::read(&stdout_path)?;
        let stderr = fs::read(&stderr_path)?;
        require(
            stdout.len() <= 4 * 1024 * 1024 && stderr.len() <= 4 * 1024 * 1024,
            "final tool output bound",
        )?;
        self.deadline.check()?;
        Ok((stdout, stderr))
    }
}
fn proc_start(pid: u32) -> Result<u64> {
    let raw = fs::read_to_string(format!("/proc/{pid}/stat"))?;
    require(raw.len() <= 16384, "bounded original child stat")?;
    let end = raw.rfind(')').ok_or("original child stat delimiter")?;
    Ok(raw[end + 1..]
        .split_whitespace()
        .nth(19)
        .ok_or("original child starttime")?
        .parse()?)
}
fn pidfd_events(pidfd: &OwnedFd) -> Result<i16> {
    let mut p = libc::pollfd {
        fd: pidfd.as_raw_fd(),
        events: libc::POLLIN | libc::POLLHUP,
        revents: 0,
    };
    let rc = unsafe { libc::poll(&mut p, 1, 0) };
    if rc < 0 {
        return Err(std::io::Error::last_os_error().into());
    }
    Ok(p.revents)
}
fn retire_child(child: &mut Child, pidfd: &OwnedFd) -> Result<std::process::ExitStatus> {
    if let Some(status) = child.try_wait()? {
        return Ok(status);
    }
    let rc = unsafe {
        libc::syscall(
            libc::SYS_pidfd_send_signal,
            pidfd.as_raw_fd(),
            libc::SIGKILL,
            std::ptr::null::<libc::siginfo_t>(),
            0,
        )
    };
    if rc != 0 && std::io::Error::last_os_error().raw_os_error() != Some(libc::ESRCH) {
        return Err(std::io::Error::last_os_error().into());
    }
    let end = Instant::now() + Duration::from_secs(5);
    loop {
        if let Some(status) = child.try_wait()? {
            require(
                pidfd_events(pidfd)? & libc::POLLHUP != 0,
                "killed original child was not reaped",
            )?;
            return Ok(status);
        }
        require(Instant::now() < end, "original child cleanup deadline")?;
        let mut p = libc::pollfd {
            fd: pidfd.as_raw_fd(),
            events: libc::POLLIN,
            revents: 0,
        };
        unsafe {
            libc::poll(&mut p, 1, 10);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn held_source_rejects_same_path_replacement_and_parent_symlink() {
        let t = tempfile::tempdir().unwrap();
        let p = t.path().join("original");
        fs::write(&p, b"original bytes").unwrap();
        fs::set_permissions(&p, fs::Permissions::from_mode(0o400)).unwrap();
        let d = Deadline::new(10);
        let r = actual_ref(&p, &d).unwrap();
        let mut inputs = Inputs::new();
        inputs.add(&r, &d).unwrap();
        fs::rename(&p, t.path().join("old")).unwrap();
        fs::write(&p, b"original bytes").unwrap();
        fs::set_permissions(&p, fs::Permissions::from_mode(0o400)).unwrap();
        assert!(inputs.revalidate_all(&d).is_err());
        let link = t.path().join("linked");
        std::os::unix::fs::symlink(t.path(), &link).unwrap();
        assert!(open_file(&link.join("original")).is_err());
    }
    #[test]
    fn actual_tool_failure_and_expired_deadline_do_not_publish_success() {
        let t = tempfile::Builder::new()
            .prefix("runtime-command-ordinary-")
            .tempdir()
            .unwrap()
            .keep();
        println!("RUNTIME_COMMAND_FIXTURE_ROOT:{}", t.display());
        let d = Deadline::new(15);
        let reference = actual_ref(Path::new("/usr/sbin/e2fsck"), &d).unwrap();
        let mut inputs = Inputs::new();
        inputs.add(&reference, &d).unwrap();
        let logs = t.join("commands");
        create_directory(&logs).unwrap();
        let mut runner = Runner {
            root: &logs,
            deadline: &d,
            epoch: 1_230_768_000,
            commands: Vec::new(),
        };
        assert!(
            runner
                .run(&inputs, &reference, &["--droidloom-invalid-option".into()])
                .is_err()
        );
        assert_eq!(runner.commands.len(), 1);
        let actual = &runner.commands[0];
        assert!(actual.returncode.is_some_and(|code| code != 0));
        assert!(actual.reaped && actual.pidfd_events & libc::POLLHUP != 0);
        assert!(actual.cleanup_error.is_none());
        inputs.revalidate_all(&d).unwrap();

        let expired = Deadline::new(0);
        let mut refused = Runner {
            root: &logs,
            deadline: &expired,
            epoch: 1_230_768_000,
            commands: Vec::new(),
        };
        assert!(refused.run(&inputs, &reference, &["-V".into()]).is_err());
        assert!(refused.commands.is_empty());
    }
}
