//! Fixed original-init placement owned by its actual kernel-lineage parent.
//! No caller chooses a process ID, unit, path, command, namespace or cgroup.
use super::*;
use std::fmt;

const MOVE: &[u8; 8] = b"DLMOVE01";
const MOVED: &[u8; 8] = b"DLMOVED1";
const REQUEST_BYTES: usize = 72;
const RESPONSE_BYTES: usize = 104;
const PAYLOAD: &str = "/sys/fs/cgroup/system.slice/droidloom-production.service/cell-u1000/payload";
const FACTORY_MEMBERS: &str =
    "/sys/fs/cgroup/system.slice/droidloom-instance-factory.service/cgroup.procs";
const CGROUP2_MAGIC: libc::c_long = 0x63677270;

#[repr(C)]
struct NativePlacement {
    pid: i32,
    pidfd: i32,
    restored: i32,
}
unsafe extern "C" {
    fn droidloom_factory_place_init(
        pid_namespace: i32,
        target: i32,
        result: *mut NativePlacement,
    ) -> i32;
}
pub(super) enum Failure {
    Rejected(io::Error),
    AuthorityLost(io::Error),
    RetirementUnproven,
}
impl From<io::Error> for Failure {
    fn from(value: io::Error) -> Self {
        Self::Rejected(value)
    }
}
impl fmt::Display for Failure {
    fn fmt(&self, out: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Rejected(error) => write!(out, "original init placement rejected: {error}"),
            Self::AuthorityLost(error) => {
                write!(out, "original factory context was not restored: {error}")
            }
            Self::RetirementUnproven => {
                write!(out, "original init placement helper retirement is unproven")
            }
        }
    }
}
impl Failure {
    pub(super) fn fatal(&self) -> bool {
        matches!(self, Self::AuthorityLost(_) | Self::RetirementUnproven)
    }
}
#[derive(Clone, Copy)]
struct Exit {
    pid: u32,
    code: i32,
    status: i32,
}
struct Helper {
    pid: i32,
    pidfd: File,
    reaped: bool,
}
impl Helper {
    fn finish(&mut self, deadline: Instant) -> io::Result<Exit> {
        if self.reaped {
            return Err(invalid("placement helper was already reaped"));
        }
        if !wait(
            &self.pidfd,
            libc::POLLIN,
            deadline.saturating_duration_since(Instant::now()),
        )? {
            return Err(invalid("original placement helper exceeded its deadline"));
        }
        let mut original = unsafe { std::mem::zeroed::<libc::siginfo_t>() };
        loop {
            let value = unsafe {
                libc::waitid(
                    libc::P_PIDFD,
                    self.pidfd.as_raw_fd() as libc::id_t,
                    &mut original,
                    libc::WEXITED | libc::WNOWAIT,
                )
            };
            if value < 0 && io::Error::last_os_error().kind() == io::ErrorKind::Interrupted {
                continue;
            }
            cv(value)?;
            break;
        }
        let mut consumed = unsafe { std::mem::zeroed::<libc::siginfo_t>() };
        loop {
            let value = unsafe {
                libc::waitid(
                    libc::P_PIDFD,
                    self.pidfd.as_raw_fd() as libc::id_t,
                    &mut consumed,
                    libc::WEXITED,
                )
            };
            if value < 0 && io::Error::last_os_error().kind() == io::ErrorKind::Interrupted {
                continue;
            }
            cv(value)?;
            break;
        }
        self.reaped = true;
        if unsafe { original.si_pid() } != self.pid
            || unsafe { consumed.si_pid() } != self.pid
            || original.si_code != consumed.si_code
            || unsafe { original.si_status() } != unsafe { consumed.si_status() }
            || !matches!(
                original.si_code,
                libc::CLD_EXITED | libc::CLD_KILLED | libc::CLD_DUMPED
            )
        {
            return Err(invalid("original helper terminal event differs"));
        }
        Ok(Exit {
            pid: unsafe { original.si_pid() } as u32,
            code: original.si_code,
            status: unsafe { original.si_status() },
        })
    }
    fn retire_failed(&mut self) -> std::result::Result<(), Failure> {
        if self.reaped {
            return Ok(());
        }
        if !ended(&self.pidfd).map_err(|_| Failure::RetirementUnproven)? {
            let result = unsafe {
                libc::syscall(
                    libc::SYS_pidfd_send_signal,
                    self.pidfd.as_raw_fd(),
                    libc::SIGKILL,
                    std::ptr::null::<libc::siginfo_t>(),
                    0,
                )
            };
            if result < 0 && io::Error::last_os_error().raw_os_error() != Some(libc::ESRCH) {
                return Err(Failure::RetirementUnproven);
            }
        }
        self.finish(Instant::now() + Duration::from_secs(3))
            .map_err(|_| Failure::RetirementUnproven)?;
        Ok(())
    }
}
impl Drop for Helper {
    fn drop(&mut self) {
        if !self.reaped {
            // Last-resort failure cleanup never becomes a positive receipt.
            let _ = self.retire_failed();
        }
    }
}
fn put_node(packet: &mut [u8], offset: usize, node: (u64, u64)) {
    packet[offset..offset + 8].copy_from_slice(&node.0.to_le_bytes());
    packet[offset + 8..offset + 16].copy_from_slice(&node.1.to_le_bytes());
}
fn node(packet: &[u8], offset: usize) -> (u64, u64) {
    (
        u64::from_le_bytes(packet[offset..offset + 8].try_into().unwrap()),
        u64::from_le_bytes(packet[offset + 8..offset + 16].try_into().unwrap()),
    )
}
fn nonce() -> io::Result<[u8; 32]> {
    let mut value = [0u8; 32];
    let mut filled = 0usize;
    while filled < value.len() {
        let count = unsafe {
            libc::getrandom(value[filled..].as_mut_ptr().cast(), value.len() - filled, 0)
        };
        if count < 0 && io::Error::last_os_error().kind() == io::ErrorKind::Interrupted {
            continue;
        }
        if count <= 0 {
            return Err(io::Error::last_os_error());
        }
        filled += count as usize;
    }
    if value == [0; 32] {
        return Err(invalid("native placement nonce is empty"));
    }
    Ok(value)
}
fn original_namespace(file: &File) -> io::Result<()> {
    check_fs(file, 0x6e736673)?;
    if unsafe { libc::ioctl(file.as_raw_fd(), 0xb703u64) } != libc::CLONE_NEWPID {
        return Err(invalid("original init PID namespace required"));
    }
    Ok(())
}
fn target_directory(file: &File) -> io::Result<()> {
    check_fs(file, CGROUP2_MAGIC)?;
    let value = file.metadata()?;
    let flags = unsafe { libc::fcntl(file.as_raw_fd(), libc::F_GETFL) };
    cv(flags)?;
    if !value.is_dir()
        || value.uid() != 0
        || value.gid() != 0
        || value.mode() & 0o7777 != 0o755
        || flags & libc::O_ACCMODE != libc::O_RDONLY
        || flags & libc::O_PATH != 0
    {
        return Err(invalid("fresh original payload cgroup directory required"));
    }
    Ok(())
}
fn control(directory: &File, access: i32) -> io::Result<File> {
    let raw = unsafe {
        libc::openat(
            directory.as_raw_fd(),
            c"cgroup.procs".as_ptr(),
            access | libc::O_CLOEXEC | libc::O_NOFOLLOW,
        )
    };
    cv(raw)?;
    let file = unsafe { File::from_raw_fd(raw) };
    check_fs(&file, CGROUP2_MAGIC)?;
    let value = file.metadata()?;
    if !value.is_file() || value.uid() != 0 || value.gid() != 0 || value.mode() & 0o7777 != 0o644 {
        return Err(invalid("original payload membership file differs"));
    }
    Ok(file)
}
fn members(mut file: File) -> io::Result<Vec<u32>> {
    check_fs(&file, CGROUP2_MAGIC)?;
    let mut body = String::new();
    (&mut file).take(16 * 1024 + 1).read_to_string(&mut body)?;
    if body.len() > 16 * 1024 || (!body.is_empty() && !body.ends_with('\n')) {
        return Err(invalid("original cgroup member readback is incomplete"));
    }
    let mut result = Vec::new();
    for line in body.lines() {
        let value: u32 = line.parse().map_err(io::Error::other)?;
        if value <= 1 || line != value.to_string() || result.contains(&value) {
            return Err(invalid("original cgroup member identity is invalid"));
        }
        result.push(value);
    }
    Ok(result)
}
pub(super) fn requested(channel: &File) -> io::Result<bool> {
    if !wait(channel, libc::POLLIN, Duration::from_secs(5))? {
        return Err(invalid(
            "original owner did not submit a fixed factory operation",
        ));
    }
    let mut tag = [0u8; 8];
    let size = unsafe {
        libc::recv(
            channel.as_raw_fd(),
            tag.as_mut_ptr().cast(),
            tag.len(),
            libc::MSG_PEEK | libc::MSG_DONTWAIT,
        )
    };
    if size < 0 {
        return Err(io::Error::last_os_error());
    }
    Ok(size == 8 && &tag == MOVE)
}
fn original_members() -> io::Result<Vec<u32>> {
    members(
        std::fs::OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_CLOEXEC | libc::O_NOFOLLOW)
            .open(FACTORY_MEMBERS)?,
    )
}
pub(super) fn serve(
    channel: &File,
    child: &Child,
    validate: &dyn Fn() -> io::Result<()>,
) -> std::result::Result<(), Failure> {
    validate()?;
    let Some((request, mut descriptors)) =
        receive_bytes::<REQUEST_BYTES>(channel, Duration::from_secs(5))?
    else {
        return Err(invalid("original placement request timed out").into());
    };
    if &request[..8] != MOVE
        || request[8..40] == [0u8; 32]
        || descriptors.len() != 1
        || node(&request, 40) != identity(&child.pidfd)?
        || node(&request, 56) != identity(&child.pins[0].object)?
        || ended(&child.pidfd)?
    {
        return Err(invalid("placement request belongs to another original init").into());
    }
    original_namespace(&child.pins[0].object)?;
    let requested = descriptors.remove(0);
    target_directory(&requested)?;
    let target = std::fs::OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
        .open(PAYLOAD)?;
    target_directory(&target)?;
    let target_node = identity(&target)?;
    if target_node != identity(&requested)?
        || !members(control(&target, libc::O_RDONLY)?)?.is_empty()
        || !original_members()?.contains(&(child.pid as u32))
    {
        return Err(invalid("original init or its empty payload cgroup changed").into());
    }
    drop(requested);
    let output = control(&target, libc::O_WRONLY)?;
    validate()?;
    if ended(&child.pidfd)? {
        return Err(invalid("original init retired before cgroup placement").into());
    }
    let mut raw = NativePlacement {
        pid: -1,
        pidfd: -1,
        restored: 0,
    };
    let result = unsafe {
        droidloom_factory_place_init(
            child.pins[0].object.as_raw_fd(),
            output.as_raw_fd(),
            &mut raw,
        )
    };
    let error = if result < 0 {
        Some(io::Error::last_os_error())
    } else {
        None
    };
    let mut helper = if raw.pidfd >= 0 {
        Some(Helper {
            pid: raw.pid,
            pidfd: unsafe { File::from_raw_fd(raw.pidfd) },
            reaped: false,
        })
    } else {
        None
    };
    if raw.restored != 1 {
        if let Some(value) = &mut helper {
            value.retire_failed()?;
        }
        return Err(Failure::AuthorityLost(error.unwrap_or_else(|| {
            invalid("native placement did not restore the factory's original context")
        })));
    }
    if let Some(error) = error {
        if let Some(value) = &mut helper {
            value.retire_failed()?;
        }
        return Err(error.into());
    }
    let Some(mut helper) = helper else {
        return Err(Failure::RetirementUnproven);
    };
    if raw.pid <= 1 {
        helper.retire_failed()?;
        return Err(invalid("native placement did not retain its direct child").into());
    }
    let exit = match helper.finish(Instant::now() + Duration::from_secs(5)) {
        Ok(exit) => exit,
        Err(error) => {
            helper.retire_failed()?;
            return Err(error.into());
        }
    };
    if exit.code != libc::CLD_EXITED || exit.status != 0 {
        return Err(invalid("original init migration helper did not exit normally zero").into());
    }
    validate()?;
    if ended(&child.pidfd)?
        || identity(&target)? != target_node
        || named_identity(Path::new(PAYLOAD))? != target_node
        || members(control(&target, libc::O_RDONLY)?)? != [child.pid as u32]
        || original_members()?.contains(&(child.pid as u32))
    {
        return Err(invalid("original init cgroup placement readback differs").into());
    }
    let mut response = [0u8; RESPONSE_BYTES];
    response[..8].copy_from_slice(MOVED);
    response[8..40].copy_from_slice(&request[8..40]);
    put_node(&mut response, 40, identity(&child.pidfd)?);
    put_node(&mut response, 56, identity(&child.pins[0].object)?);
    put_node(&mut response, 72, target_node);
    response[88..92].copy_from_slice(&exit.pid.to_le_bytes());
    response[92..96].copy_from_slice(&exit.code.to_le_bytes());
    response[96..100].copy_from_slice(&exit.status.to_le_bytes());
    send_bytes(channel, &response, &[])?;
    Ok(())
}
pub(crate) fn move_original_init_from_factory(
    init: &File,
    namespace: &File,
    target: &File,
) -> io::Result<()> {
    if ended(init)? {
        return Err(invalid("original init already retired before placement"));
    }
    original_namespace(namespace)?;
    target_directory(target)?;
    let original_init = identity(init)?;
    let original_namespace = identity(namespace)?;
    let original_target = identity(target)?;
    let endpoint = QueryEndpoint::connect()?;
    endpoint.revalidate()?;
    let mut request = [0u8; REQUEST_BYTES];
    request[..8].copy_from_slice(MOVE);
    request[8..40].copy_from_slice(&nonce()?);
    put_node(&mut request, 40, original_init);
    put_node(&mut request, 56, original_namespace);
    send_bytes(endpoint.channel(), &request, &[target])?;
    let Some((response, descriptors)) =
        receive_bytes::<RESPONSE_BYTES>(endpoint.channel(), Duration::from_secs(20))?
    else {
        return Err(invalid("original factory did not complete init placement"));
    };
    endpoint.revalidate()?;
    let helper = u32::from_le_bytes(response[88..92].try_into().unwrap());
    let code = i32::from_le_bytes(response[92..96].try_into().unwrap());
    let status = i32::from_le_bytes(response[96..100].try_into().unwrap());
    if !descriptors.is_empty()
        || &response[..8] != MOVED
        || response[8..40] != request[8..40]
        || node(&response, 40) != original_init
        || node(&response, 56) != original_namespace
        || node(&response, 72) != original_target
        || helper <= 1
        || helper == endpoint.pid()
        || code != libc::CLD_EXITED
        || status != 0
        || response[100..] != [0u8; 4]
        || ended(init)?
        || identity(init)? != original_init
        || identity(namespace)? != original_namespace
        || identity(target)? != original_target
    {
        return Err(invalid(
            "factory init placement is not the original normal outcome",
        ));
    }
    // The original resource owner independently reads metadata and both cgroup
    // member lists before continuing its delegated payload namespace setup.
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn placement_helper_reports_and_reaps_the_actual_nonzero_terminal_event() {
        let mut fd = -1i32;
        let mut args = [0u64; 11];
        args[0] = libc::CLONE_PIDFD as u64;
        args[1] = (&mut fd as *mut i32) as u64;
        args[4] = libc::SIGCHLD as u64;
        let pid = unsafe {
            libc::syscall(
                libc::SYS_clone3,
                args.as_ptr(),
                std::mem::size_of_val(&args),
            )
        };
        if pid == 0 {
            unsafe { libc::_exit(17) };
        }
        assert!(pid > 1 && fd >= 0, "{}", io::Error::last_os_error());
        let mut child = Helper {
            pid: pid as i32,
            pidfd: unsafe { File::from_raw_fd(fd) },
            reaped: false,
        };
        let exit = child
            .finish(Instant::now() + Duration::from_secs(2))
            .unwrap();
        assert_eq!(exit.pid, pid as u32);
        assert_eq!(exit.code, libc::CLD_EXITED);
        assert_eq!(exit.status, 17);
        assert!(child.reaped);
        let mut actual = unsafe { std::mem::zeroed::<libc::siginfo_t>() };
        assert_eq!(
            unsafe {
                libc::waitid(
                    libc::P_PIDFD,
                    fd as libc::id_t,
                    &mut actual,
                    libc::WEXITED | libc::WNOHANG,
                )
            },
            -1
        );
        assert_eq!(
            io::Error::last_os_error().raw_os_error(),
            Some(libc::ECHILD)
        );
    }
}
