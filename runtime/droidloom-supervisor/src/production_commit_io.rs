//! Private held native tool execution for the production owner.
use super::*;
use crate::native_hardware_label as held;
use std::{
    collections::BTreeMap,
    ffi::CString,
    io::{Read, Write},
    os::{
        fd::{AsRawFd, FromRawFd},
        unix::{
            fs::{FileExt, MetadataExt, OpenOptionsExt},
            process::CommandExt,
        },
    },
    process::{Command, ExitStatus, Stdio},
    sync::atomic::{AtomicBool, Ordering},
};
static RETIREMENT_UNKNOWN: AtomicBool = AtomicBool::new(false);
pub(super) fn retired() -> io::Result<()> {
    if RETIREMENT_UNKNOWN.load(Ordering::Acquire) {
        return Err(error(
            "prior tool retirement unproven; no later mutation is allowed",
        ));
    }
    Ok(())
}
pub(super) struct Input {
    pub file: File,
    pub path: PathBuf,
    pub identity: [u64; 9],
    pub pin: c::BytesPin,
    parents: Vec<(PathBuf, File, [u64; 5])>,
    label: Vec<u8>,
}
fn parents(path: &Path) -> io::Result<Vec<(PathBuf, File, [u64; 5])>> {
    if !path.is_absolute()
        || path.components().any(|v| {
            !matches!(
                v,
                std::path::Component::RootDir | std::path::Component::Normal(_)
            )
        })
    {
        return Err(error("production input is not canonical"));
    }
    let mut out = Vec::new();
    for p in path
        .parent()
        .ok_or_else(|| error("parent absent"))?
        .ancestors()
    {
        let f = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_PATH | libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open(p)?;
        let id = f9(&f)?;
        if id[2] & 0o170000 != 0o040000 || id[3..5] != [0, 0] || id[2] & 0o022 != 0 {
            return Err(error("production ancestor is not root-controlled"));
        }
        out.push((p.into(), f, id[..5].try_into().unwrap()));
    }
    Ok(out)
}
pub(super) fn whole(f: &File, bytes: u64) -> io::Result<String> {
    let before = f9(f)?;
    let mut hash = Sha256::new();
    let mut offset = 0;
    let mut raw = [0u8; 32768];
    while offset < bytes {
        let n = f.read_at(&mut raw, offset)?;
        if n == 0 || offset + n as u64 > bytes {
            return Err(error("whole source size differs"));
        }
        hash.update(&raw[..n]);
        offset += n as u64;
    }
    if f.read_at(&mut raw[..1], offset)? != 0 || f9(f)? != before {
        return Err(error("whole source changed"));
    }
    Ok(format!("{:x}", hash.finalize()))
}
impl Input {
    pub(super) fn open(
        path: &Path,
        pin: &c::BytesPin,
        mode: u32,
        label: Option<&[u8]>,
    ) -> io::Result<Self> {
        if pin.bytes == 0 {
            if pin.sha256 != sha(b"") {
                return Err(error("empty source digest differs"));
            }
        } else {
            pin.validate(512 * 1024 * 1024)?;
        }
        let parents = parents(path)?;
        let file = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_NOFOLLOW | libc::O_NONBLOCK | libc::O_CLOEXEC)
            .open(path)?;
        let identity = f9(&file)?;
        let actual = held::label(&file)?;
        if identity[2] != u64::from(libc::S_IFREG | mode)
            || identity[3..6] != [0, 0, 1]
            || identity[6] != pin.bytes
            || label.is_some_and(|s| s != actual)
            || whole(&file, pin.bytes)? != pin.sha256
        {
            return Err(error("whole production source, metadata or label differs"));
        }
        let v = Self {
            file,
            path: path.into(),
            identity,
            pin: pin.clone(),
            parents,
            label: actual,
        };
        v.guard()?;
        Ok(v)
    }
    pub(super) fn guard(&self) -> io::Result<()> {
        for (p, f, old) in &self.parents {
            let named = OpenOptions::new()
                .read(true)
                .custom_flags(libc::O_PATH | libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
                .open(p)?;
            if f9(f)?[..5] != *old || f9(&named)?[..5] != *old {
                return Err(error("source parent replaced"));
            }
        }
        let named = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_NOFOLLOW | libc::O_NONBLOCK | libc::O_CLOEXEC)
            .open(&self.path)?;
        if f9(&named)? != self.identity
            || f9(&self.file)? != self.identity
            || held::label(&self.file)? != self.label
            || whole(&self.file, self.pin.bytes)? != self.pin.sha256
        {
            return Err(error("source lost its actual held/named custody"));
        }
        Ok(())
    }
    pub(super) fn bytes(&self, limit: u64) -> io::Result<Vec<u8>> {
        if self.pin.bytes > limit {
            return Err(error("production JSON exceeds bound"));
        }
        self.guard()?;
        let mut b = vec![0; self.pin.bytes as usize];
        self.file.read_exact_at(&mut b, 0)?;
        if sha(&b) != self.pin.sha256 {
            return Err(error("production JSON changed"));
        }
        self.guard()?;
        Ok(b)
    }
}
pub(super) struct CommandResult {
    pub status: ExitStatus,
    pub stdout: Vec<u8>,
    pub stderr: Vec<u8>,
    pub pid: u32,
}
impl CommandResult {
    pub(super) fn success(&self) -> io::Result<()> {
        if !self.status.success() || !self.stderr.is_empty() {
            return Err(error("normal production command failed"));
        }
        Ok(())
    }
    pub(super) fn observation(&self) -> Value {
        json!({"pid":self.pid,"exit_code":self.status.code(),"actual_child_reaped":true,
  "stdout_bytes":self.stdout.len(),"stdout_sha256":sha(&self.stdout),"stderr_bytes":self.stderr.len(),"stderr_sha256":sha(&self.stderr)})
    }
}
unsafe fn no_caps() -> bool {
    #[repr(C)]
    struct H {
        version: u32,
        pid: i32,
    }
    #[repr(C)]
    #[derive(Clone, Copy)]
    struct D {
        effective: u32,
        permitted: u32,
        inheritable: u32,
    }
    let h = H {
        version: 0x20080522,
        pid: 0,
    };
    let d = [D {
        effective: 0,
        permitted: 0,
        inheritable: 0,
    }; 2];
    unsafe {
        libc::syscall(libc::SYS_capset, &h, d.as_ptr()) == 0
            && libc::prctl(libc::PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) == 0
    }
}
pub(super) fn invoke(
    tool: &Input,
    args: &[&str],
    borrowed: Option<&File>,
    end: Instant,
    limit: usize,
) -> io::Result<CommandResult> {
    retired()?;
    tool.guard()?;
    if args.len() > 8 || Instant::now() + Duration::from_secs(2) >= end {
        return Err(error(
            "normal command cannot fit its fixed argv/retirement window",
        ));
    }
    let copy = |f: &File| -> io::Result<File> {
        let n = unsafe { libc::fcntl(f.as_raw_fd(), libc::F_DUPFD_CLOEXEC, 64) };
        if n < 0 {
            Err(io::Error::last_os_error())
        } else {
            Ok(unsafe { File::from_raw_fd(n) })
        }
    };
    let exe = copy(&tool.file)?;
    let borrowed = borrowed.map(copy).transpose()?;
    let mut argv =
        vec![CString::new(tool.path.as_os_str().as_encoded_bytes()).map_err(io::Error::other)?];
    argv.extend(
        args.iter()
            .map(|v| CString::new(*v).map_err(io::Error::other))
            .collect::<io::Result<Vec<_>>>()?,
    );
    let mut av = [0usize; 10];
    for (out, s) in av.iter_mut().zip(&argv) {
        *out = s.as_ptr() as usize;
    }
    let env = [
        c"PATH=/usr/sbin:/usr/bin:/sbin:/bin",
        c"LANG=C.UTF-8",
        c"SYSTEMD_PAGER=cat",
        c"SYSTEMD_COLORS=0",
    ];
    let parent = unsafe { libc::getpid() };
    let mut command = Command::new(&tool.path);
    command
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .env_clear();
    unsafe {
        command.pre_exec(move || {
            if libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGKILL, 0, 0, 0) != 0
                || libc::getppid() != parent
                || libc::dup3(exe.as_raw_fd(), 4, libc::O_CLOEXEC) < 0
            {
                return Err(io::Error::last_os_error());
            }
            if let Some(f) = &borrowed {
                if libc::dup3(f.as_raw_fd(), 3, 0) < 0 {
                    return Err(io::Error::last_os_error());
                }
            } else {
                libc::close(3);
            }
            if libc::syscall(libc::SYS_close_range, 5u32, u32::MAX, 4u32) != 0 || !no_caps() {
                return Err(io::Error::last_os_error());
            }
            // All allocations and pointer storage predate fork.
            let _keep = &argv;
            let ev = [
                env[0].as_ptr(),
                env[1].as_ptr(),
                env[2].as_ptr(),
                env[3].as_ptr(),
                std::ptr::null(),
            ];
            libc::syscall(
                libc::SYS_execveat,
                4,
                c"".as_ptr(),
                av.as_ptr(),
                ev.as_ptr(),
                libc::AT_EMPTY_PATH,
            );
            Err(io::Error::last_os_error())
        });
    }
    RETIREMENT_UNKNOWN.store(true, Ordering::Release);
    let mut child = match command.spawn() {
        Ok(v) => v,
        Err(e) => {
            // std's exec-error handshake has already waited its exact failed child.
            RETIREMENT_UNKNOWN.store(false, Ordering::Release);
            return Err(e);
        }
    };
    let pid = child.id();
    let pidfd = match crate::development::owned_process::open_pidfd(pid) {
        Ok(p) => p,
        Err(e) => {
            let _ = child.kill();
            return Err(e);
        }
    };
    let mut child = ChildOwner {
        child,
        pidfd,
        pid,
        reaped: None,
    };
    let mut stdout = child
        .child
        .stdout
        .take()
        .ok_or_else(|| error("normal stdout absent"))?;
    let mut stderr = child
        .child
        .stderr
        .take()
        .ok_or_else(|| error("normal stderr absent"))?;
    socket::nonblocking(stdout.as_raw_fd())?;
    socket::nonblocking(stderr.as_raw_fd())?;
    let mut out = Vec::new();
    let mut err = Vec::new();
    let mut out_end = false;
    let mut err_end = false;
    let work_end = end - Duration::from_secs(2);
    let drain = |r: &mut dyn Read, b: &mut Vec<u8>, eof: &mut bool| -> io::Result<()> {
        let mut raw = [0u8; 32768];
        loop {
            match r.read(&mut raw) {
                Ok(0) => {
                    *eof = true;
                    return Ok(());
                }
                Ok(n) => {
                    if b.len() + n > limit {
                        return Err(error("native output exceeded closed bound"));
                    }
                    b.extend_from_slice(&raw[..n]);
                }
                Err(e) if e.kind() == io::ErrorKind::WouldBlock => return Ok(()),
                Err(e) if e.kind() == io::ErrorKind::Interrupted => (),
                Err(e) => return Err(e),
            }
        }
    };
    let result = (|| {
        loop {
            drain(&mut stdout, &mut out, &mut out_end)?;
            drain(&mut stderr, &mut err, &mut err_end)?;
            if let Some(status) = child.try_wait()? {
                RETIREMENT_UNKNOWN.store(false, Ordering::Release);
                drain(&mut stdout, &mut out, &mut out_end)?;
                drain(&mut stderr, &mut err, &mut err_end)?;
                if !out_end || !err_end {
                    RETIREMENT_UNKNOWN.store(true, Ordering::Release);
                    return Err(error("native command left output writers"));
                }
                tool.guard()?;
                return Ok(CommandResult {
                    status,
                    stdout: std::mem::take(&mut out),
                    stderr: std::mem::take(&mut err),
                    pid,
                });
            }
            if Instant::now() >= work_end {
                return Err(error("normal command exceeded original deadline"));
            }
            std::thread::sleep(Duration::from_millis(5));
        }
    })();
    if result.is_err() {
        child.stop(end)?;
        let _ = drain(&mut stdout, &mut out, &mut out_end);
        let _ = drain(&mut stderr, &mut err, &mut err_end);
        if out_end && err_end {
            RETIREMENT_UNKNOWN.store(false, Ordering::Release);
        }
    }
    result
}
fn attrs(f: &File) -> io::Result<BTreeMap<Vec<u8>, Vec<u8>>> {
    let mut names = vec![0u8; 65536];
    let n = unsafe { libc::flistxattr(f.as_raw_fd(), names.as_mut_ptr().cast(), names.len()) };
    if n < 0 {
        return Err(io::Error::last_os_error());
    }
    names.truncate(n as usize);
    if !names.is_empty() && names.last() != Some(&0) {
        return Err(error("GRUB attribute list truncated"));
    }
    let mut out = BTreeMap::new();
    for name in names.split(|b| *b == 0).filter(|s| !s.is_empty()) {
        let key = CString::new(name).map_err(io::Error::other)?;
        let mut b = vec![0u8; 65536];
        let n =
            unsafe { libc::fgetxattr(f.as_raw_fd(), key.as_ptr(), b.as_mut_ptr().cast(), b.len()) };
        if n < 0 {
            return Err(io::Error::last_os_error());
        }
        b.truncate(n as usize);
        if out.insert(name.to_vec(), b).is_some() {
            return Err(error("duplicate actual attribute"));
        }
    }
    Ok(out)
}
fn generation(f: &File) -> io::Result<u32> {
    let mut n = 0i64;
    if unsafe { libc::ioctl(f.as_raw_fd(), 0x80087601u64, &mut n) } != 0 {
        return Err(io::Error::last_os_error());
    }
    Ok(n as u32)
}
pub(super) struct Environment {
    file: File,
    identity: [u64; 9],
    generation: u32,
    attributes: BTreeMap<Vec<u8>, Vec<u8>>,
    body: Vec<u8>,
}
impl Environment {
    pub(super) fn open() -> io::Result<Self> {
        retired()?;
        let _ = parents(Path::new(c::ENV))?;
        let file = OpenOptions::new()
            .read(true)
            .write(true)
            .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open(c::ENV)?;
        let identity = f9(&file)?;
        let mut fs = std::mem::MaybeUninit::<libc::statfs>::uninit();
        if identity[2] != 0o100644
            || identity[3..7] != [0, 0, 1, 1024]
            || unsafe { libc::fstatfs(file.as_raw_fd(), fs.as_mut_ptr()) } != 0
            || unsafe { fs.assume_init() }.f_type != 0xef53
        {
            return Err(error("GRUB environment is not one fixed ext4 inode"));
        }
        let generation = generation(&file)?;
        let attributes = attrs(&file)?;
        if held::label(&file)? != b"u:object_r:p4_linux_maintenance_grubenv_t:s0" {
            return Err(error("GRUB environment label differs"));
        }
        let mut body = vec![0; 1024];
        file.read_exact_at(&mut body, 0)?;
        c::fields(&body)?;
        let v = Self {
            file,
            identity,
            generation,
            attributes,
            body,
        };
        v.guard()?;
        Ok(v)
    }
    pub(super) fn guard(&self) -> io::Result<()> {
        retired()?;
        let named = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open(c::ENV)?;
        let mut body = vec![0; 1024];
        self.file.read_exact_at(&mut body, 0)?;
        if f9(&self.file)? != self.identity
            || f9(&named)? != self.identity
            || generation(&self.file)? != self.generation
            || attrs(&self.file)? != self.attributes
            || body != self.body
        {
            return Err(error("environment changed outside owned command"));
        }
        Ok(())
    }
    pub(super) fn select(
        &mut self,
        tool: &Input,
        candidate: &str,
        trial: bool,
        end: Instant,
    ) -> io::Result<Value> {
        self.guard()?;
        c::entry(candidate)?;
        let key = if trial { c::TRIAL } else { c::ACTIVE };
        let value = format!("{key}={candidate}");
        let before = self.body.clone();
        // Reject before mutation as well as at the actual readback.
        let mut expected = c::fields(&before)?;
        if expected.get(key).is_some_and(|s| !s.is_empty())
            || expected.get("next_entry").is_some_and(|s| !s.is_empty())
            || expected
                .get(if trial { c::ACTIVE } else { c::TRIAL })
                .is_some_and(|s| !s.is_empty())
        {
            return Err(error("foreign or prior production selection"));
        }
        expected.insert(key.into(), candidate.into());
        let outcome = invoke(
            tool,
            &["/proc/self/fd/3", "set", &value],
            Some(&self.file),
            end,
            65536,
        );
        retired()?; // Unknown retirement cannot authorize even a read/undo cycle.
        let mut after = vec![0; 1024];
        self.file.read_exact_at(&mut after, 0)?;
        let now = f9(&self.file)?;
        if now[..7] != self.identity[..7]
            || generation(&self.file)? != self.generation
            || attrs(&self.file)? != self.attributes
        {
            return Err(error(
                "normal GRUB command replaced held generation or attributes",
            ));
        }
        if before != after {
            c::selected_only(&before, &after, candidate, trial)?;
        }
        self.identity = now;
        self.body = after;
        self.guard()?;
        let actual = outcome?;
        actual.success()?;
        c::selected_only(&before, &self.body, candidate, trial)?;
        self.file.sync_all()?;
        if unsafe { libc::syncfs(self.file.as_raw_fd()) } != 0 {
            return Err(io::Error::last_os_error());
        }
        self.guard()?;
        Ok(
            json!({"normal_tool":actual.observation(),"before_sha256":sha(&before),"after_sha256":sha(&self.body),"generation":self.generation,"selected":value}),
        )
    }
}

pub(super) fn request_reboot(tool: &Input, end: Instant) -> io::Result<CommandResult> {
    invoke(tool, &c::REBOOT_ARGUMENTS, None, end, 65536)
}
pub(super) fn observe_reboot(tool: &Input, end: Instant) -> io::Result<Value> {
    let start = Instant::now();
    let mut observations = Vec::new();
    for _ in 0..16 {
        let actual = invoke(
            tool,
            &[
                "show",
                "reboot.target",
                "--no-pager",
                "--property=ActiveState,SubState,Job",
            ],
            None,
            end,
            16384,
        )?;
        actual.success()?;
        let raw = std::str::from_utf8(&actual.stdout).map_err(io::Error::other)?;
        let mut fields = BTreeMap::new();
        for line in raw.lines() {
            let (k, v) = line
                .split_once('=')
                .ok_or_else(|| error("PID1 reboot observation has unnamed field"))?;
            if fields.insert(k, v).is_some() {
                return Err(error("PID1 reboot observation duplicated a field"));
            }
        }
        if fields.len() != 3
            || !["ActiveState", "SubState", "Job"]
                .iter()
                .all(|k| fields.contains_key(k))
        {
            return Err(error("PID1 reboot observation omitted actual properties"));
        }
        let active = fields["ActiveState"];
        let job = fields["Job"];
        if active == "failed" {
            return Err(error("actual PID1 reboot target failed"));
        }
        let accepted =
            ["active", "activating"].contains(&active) || (!job.is_empty() && job != "0");
        observations.push(json!({"actual_tool":actual.observation(),"properties":raw}));
        if accepted {
            return Ok(
                json!({"actual_reboot_job_observed":true,"normal_shutdown_observed":false,"observations":observations}),
            );
        }
        if active != "inactive" || !["dead", "inactive"].contains(&fields["SubState"]) {
            return Err(error("actual PID1 reboot state is unresolved"));
        }
        if Instant::now() + Duration::from_secs(3) >= end {
            break;
        }
        std::thread::sleep(Duration::from_secs(1));
    }
    Err(error(&format!(
        "normal PID1 reboot remained idle after {} ms and {} readonly observations; no request replay",
        start.elapsed().as_millis(),
        observations.len()
    )))
}
impl Environment {
    pub(super) fn is_active(&self, candidate: &str) -> io::Result<bool> {
        self.guard()?;
        c::entry(candidate)?;
        let values = c::fields(&self.body)?;
        if values.get("next_entry").is_some_and(|s| !s.is_empty())
            || values.get(c::TRIAL).is_some_and(|s| !s.is_empty())
        {
            return Err(error("normal boot left a once/trial selector unresolved"));
        }
        match values.get(c::ACTIVE).map(String::as_str) {
            None | Some("") => Ok(false),
            Some(v) if v == candidate => Ok(true),
            _ => Err(error("persistent selector belongs to another candidate")),
        }
    }
    pub(super) fn clear_owned(
        &mut self,
        tool: &Input,
        candidate: &str,
        end: Instant,
    ) -> io::Result<Value> {
        self.guard()?;
        c::entry(candidate)?;
        let before = self.body.clone();
        let mut expected = c::fields(&before)?;
        if expected.get("next_entry").is_some_and(|v| !v.is_empty())
            || [c::TRIAL, c::ACTIVE].iter().any(|k| {
                expected
                    .get(*k)
                    .is_some_and(|v| !v.is_empty() && v != candidate)
            })
        {
            return Err(error("normal fallback refuses another actual selection"));
        }
        if [c::TRIAL, c::ACTIVE]
            .iter()
            .all(|k| expected.get(*k).is_none_or(|v| v.is_empty()))
        {
            return Ok(json!({"readonly_already_unselected":true,"actual_sha256":sha(&before)}));
        }
        expected.remove(c::TRIAL);
        expected.remove(c::ACTIVE);
        let outcome = invoke(
            tool,
            &["/proc/self/fd/3", "unset", c::TRIAL, c::ACTIVE],
            Some(&self.file),
            end,
            65536,
        );
        retired()?;
        let mut after = vec![0; 1024];
        self.file.read_exact_at(&mut after, 0)?;
        let now = f9(&self.file)?;
        if now[..7] != self.identity[..7]
            || generation(&self.file)? != self.generation
            || attrs(&self.file)? != self.attributes
            || (before != after && c::fields(&after)? != expected)
        {
            return Err(error(
                "normal own-selector undo changed another environment field or inode",
            ));
        }
        self.identity = now;
        self.body = after;
        self.guard()?;
        let actual = outcome?;
        actual.success()?;
        if c::fields(&self.body)? != expected {
            return Err(error("normal own-selector undo did not take effect"));
        }
        self.file.sync_all()?;
        if unsafe { libc::syncfs(self.file.as_raw_fd()) } != 0 {
            return Err(io::Error::last_os_error());
        }
        self.guard()?;
        Ok(
            json!({"actual_tool":actual.observation(),"before_sha256":sha(&before),"after_sha256":sha(&self.body),"own_selection_removed":true}),
        )
    }
}
