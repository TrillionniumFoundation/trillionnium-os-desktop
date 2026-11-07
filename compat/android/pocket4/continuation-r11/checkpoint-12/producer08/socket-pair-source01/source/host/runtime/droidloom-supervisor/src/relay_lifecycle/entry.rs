//! Single-threaded namespace-entry half of the real init barrier.
//!
//! All inherited capabilities are sealed before a helper can execute. Only
//! the constructor channel is deliberately inherited by the final init exec;
//! the constructor closes it before init can start any service.
use super::capability::{self, Artifact};
use super::domain::{self, Identity};
use super::init_peer;
use super::policy::{self, PressureRelaySpec};
use crate::CellSpec;
use sha2::{Digest, Sha256};
use std::ffi::{CString, OsString};
use std::fs::File;
use std::io::{self, Write};
use std::os::fd::{AsRawFd, FromRawFd, RawFd};
use std::os::unix::fs::{FileExt, MetadataExt};
use std::os::unix::process::CommandExt;
use std::path::Path;
use std::process::Command;

/// Exact pure-CLI pairing value required before private relay entry may spawn.
pub const ABI: &str = "droidloom-relay-entry-v2";
pub(crate) const ENTRY_ENV: [&str; 3] = [
    "DROIDLOOM_RELAY_ENTRY_ABI",
    "DROIDLOOM_RELAY_ENTRY_NONCE",
    "DROIDLOOM_RELAY_ENTRY_SPEC_SHA256",
];
const INIT_ENV: [&str; 5] = [
    "DROIDLOOM_INIT_RELAY_REQUIRED",
    "DROIDLOOM_INIT_RELAY_ABI",
    "DROIDLOOM_INIT_RELAY_FD",
    "DROIDLOOM_INIT_RELAY_NONCE",
    "DROIDLOOM_INIT_RELAY_TIMEOUT_MS",
];
const FIXED: [RawFd; 4] = [
    init_peer::CONTROL_FD,
    init_peer::DOMAIN_FD,
    init_peer::OWNER_FD,
    init_peer::ENTRY_FD,
];
const BOOTSTRAP: &str = "droidloom/lmkd-bootstrap";
const INIT_LINKER: &str = "/system/bin/bootstrap/linker64";
fn error(message: &'static str) -> io::Error {
    domain::error(message)
}

pub(crate) fn spec_digest(spec: &CellSpec) -> io::Result<[u8; 32]> {
    let bytes = serde_json::to_vec(spec).map_err(io::Error::other)?;
    Ok(Sha256::digest(bytes).into())
}
pub(crate) fn clean_command_environment(command: &mut Command) {
    for key in ENTRY_ENV.into_iter().chain(INIT_ENV) {
        command.env_remove(key);
    }
}
fn close_on_exec(fd: RawFd, enabled: bool) -> io::Result<()> {
    let flags = unsafe { libc::fcntl(fd, libc::F_GETFD) };
    if flags < 0 {
        return Err(io::Error::last_os_error());
    }
    let flags = if enabled {
        flags | libc::FD_CLOEXEC
    } else {
        flags & !libc::FD_CLOEXEC
    };
    if unsafe { libc::fcntl(fd, libc::F_SETFD, flags) } < 0 {
        return Err(io::Error::last_os_error());
    }
    Ok(())
}
fn pidfd_alive(fd: &File) -> io::Result<()> {
    let path = format!("/proc/self/fdinfo/{}", fd.as_raw_fd());
    let text = std::fs::read_to_string(path)?;
    // The parent's PID is deliberately 0 in this child PID namespace. A Pid
    // field plus the kernel pidfd poll semantics establishes descriptor type;
    // no positive numeric PID is used to open, signal, or authenticate a peer.
    let mut fields = text.lines().filter_map(|line| line.strip_prefix("Pid:\t"));
    let pid: i64 = fields
        .next()
        .ok_or_else(|| error("entry owner FD is not a pidfd"))?
        .trim()
        .parse()
        .map_err(|_| error("entry owner pidfd identity malformed"))?;
    if pid < 0 || fields.next().is_some() {
        return Err(error("entry owner pidfd retired"));
    }
    let mut poll = libc::pollfd {
        fd: fd.as_raw_fd(),
        events: libc::POLLIN,
        revents: 0,
    };
    let count = unsafe { libc::poll(&mut poll, 1, 0) };
    if count < 0 {
        return Err(io::Error::last_os_error());
    }
    if count != 0 || poll.revents != 0 {
        return Err(error("entry owner is no longer alive"));
    }
    Ok(())
}
fn require_control(fd: &File) -> io::Result<()> {
    let mut kind: libc::c_int = 0;
    let mut length = std::mem::size_of_val(&kind) as libc::socklen_t;
    if unsafe {
        libc::getsockopt(
            fd.as_raw_fd(),
            libc::SOL_SOCKET,
            libc::SO_TYPE,
            (&mut kind as *mut libc::c_int).cast(),
            &mut length,
        )
    } < 0
    {
        return Err(io::Error::last_os_error());
    }
    if kind != libc::SOCK_SEQPACKET || length as usize != std::mem::size_of_val(&kind) {
        return Err(error("entry control is not a seqpacket channel"));
    }
    let flags = unsafe { libc::fcntl(fd.as_raw_fd(), libc::F_GETFL) };
    if flags < 0 || flags & libc::O_NONBLOCK == 0 {
        return Err(error("entry control is not nonblocking"));
    }
    let mut peer: libc::ucred = unsafe { std::mem::zeroed() };
    let mut size = std::mem::size_of_val(&peer) as libc::socklen_t;
    if unsafe {
        libc::getsockopt(
            fd.as_raw_fd(),
            libc::SOL_SOCKET,
            libc::SO_PEERCRED,
            (&mut peer as *mut libc::ucred).cast(),
            &mut size,
        )
    } < 0
    {
        return Err(io::Error::last_os_error());
    }
    if peer.uid != 0
        || peer.gid != 0
        || peer.pid < 0
        || size as usize != std::mem::size_of_val(&peer)
    {
        return Err(error("entry channel peer is not the root lifecycle owner"));
    }
    Ok(())
}

/// Private fields make a partial inherited contract unusable by later phases.
pub(crate) struct Entry {
    channel: File,
    domain: File,
    owner: File,
    executable: Artifact,
    policy: PressureRelaySpec,
    nonce: [u8; 32],
    domain_identity: Identity,
    barrier: Artifact,
    lmkd: Artifact,
    prepared: bool,
    sealed: bool,
}
impl Entry {
    /// This is the first operation in development-enter, before validation
    /// helpers or any process spawn. Failure always terminates that entry.
    pub(crate) fn receive(spec: &CellSpec) -> io::Result<Option<Self>> {
        let env: Vec<Option<OsString>> = ENTRY_ENV.iter().map(std::env::var_os).collect();
        let leaked_init = INIT_ENV.iter().any(|key| std::env::var_os(key).is_some());
        let Some(policy) = spec.pressure_relay.as_ref() else {
            if env.iter().any(Option::is_some) || leaked_init {
                return Err(error("relay capability environment without relay policy"));
            }
            return Ok(None);
        };
        // Seal every known descriptor even if the textual contract is bad.
        // Do not construct owners until sealing has succeeded for all four.
        for fd in FIXED {
            close_on_exec(fd, true)?;
        }
        if leaked_init || env[0].as_deref() != Some(std::ffi::OsStr::new(ABI)) {
            return Err(error("entry ABI or inherited init environment differs"));
        }
        let nonce = policy::digest(
            env[1]
                .as_ref()
                .and_then(|s| s.to_str())
                .ok_or_else(|| error("entry nonce missing"))?,
        )
        .map_err(error)?;
        let declared = policy::digest(
            env[2]
                .as_ref()
                .and_then(|s| s.to_str())
                .ok_or_else(|| error("entry specification pin missing"))?,
        )
        .map_err(error)?;
        if declared != spec_digest(spec)? {
            return Err(error("entry specification changed after host admission"));
        }
        if unsafe { libc::getuid() } != 0
            || unsafe { libc::geteuid() } != 0
            || unsafe { libc::getgid() } != 0
            || unsafe { libc::getegid() } != 0
            || unsafe { libc::getpid() } != 1
            || unsafe { libc::getppid() } != 0
        {
            return Err(error(
                "relay entry is not private root PID 1 with an outer owner",
            ));
        }
        // SAFETY: the private ABI transfers these four distinct inherited FDs
        // exactly once; they have all just been sealed CLOEXEC.
        let [channel, domain_fd, owner, executable] =
            FIXED.map(|fd| unsafe { File::from_raw_fd(fd) });
        if unsafe { libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGKILL) } < 0 {
            return Err(io::Error::last_os_error());
        }
        // The pidfd closes the race where the outside parent died before
        // PR_SET_PDEATHSIG could be armed in this new PID namespace.
        pidfd_alive(&owner)?;
        require_control(&channel)?;
        let executable = Artifact::from_file(
            executable,
            policy::digest(&policy.entry_supervisor.sha256).map_err(error)?,
            true,
        )?;
        let actual = File::open("/proc/self/exe")?;
        if Identity::of(&actual)? != executable.identity()
            || capability::hash(&actual)? != executable.digest()
        {
            return Err(error(
                "actual entry executable differs from inherited package pin",
            ));
        }
        let barrier = Artifact::open(&policy.init_barrier, false)?;
        let lmkd = Artifact::open(&policy.lmkd, true)?;
        let domain_identity = Identity::of(&domain_fd)?;
        domain::enter_self(&domain_fd, policy)?;
        pidfd_alive(&owner)?;
        Ok(Some(Self {
            channel,
            domain: domain_fd,
            owner,
            executable,
            policy: policy.clone(),
            nonce,
            domain_identity,
            barrier,
            lmkd,
            prepared: false,
            sealed: false,
        }))
    }

    /// Runs after the normal image overlays, but before pivot_root or init.
    pub(crate) fn prepare_image(&mut self, root_path: &Path) -> io::Result<()> {
        if self.prepared || self.sealed {
            return Err(error("relay image preparation is a single attempt"));
        }
        self.sealed = true; // Any partial mount failure permanently closes this entry.
        pidfd_alive(&self.owner)?;
        self.executable.validate(true)?;
        self.barrier.validate(true)?;
        self.lmkd.validate(true)?;
        let root = domain::directory(root_path)?;
        let init = Artifact::from_file(
            domain::beneath(&root, "system/bin/init", libc::O_RDONLY)?,
            policy::digest(&self.policy.init_sha256).map_err(error)?,
            true,
        )?;
        require_init_alias(&root, init.identity())?;
        require_interpreter(init.file(), INIT_LINKER)?;
        let linker = Artifact::from_file(
            domain::beneath(&root, INIT_LINKER.trim_start_matches('/'), libc::O_RDONLY)?,
            policy::digest(&self.policy.init_linker_sha256).map_err(error)?,
            true,
        )?;
        let compat = Artifact::from_file(
            domain::beneath(
                &root,
                init_peer::COMPAT.trim_start_matches('/'),
                libc::O_RDONLY,
            )?,
            policy::digest(&self.policy.compat_preload_sha256).map_err(error)?,
            false,
        )?;
        let old_rc = Artifact::from_file(
            domain::beneath(&root, "system/etc/init/lmkd.rc", libc::O_RDONLY)?,
            policy::digest(&self.policy.lmkd_rc_sha256).map_err(error)?,
            false,
        )?;
        let droidloom = make_parent(&root, "droidloom")?;
        if unsafe { libc::mkdirat(droidloom.as_raw_fd(), c"lmkd-bootstrap".as_ptr(), 0o755) } != 0 {
            return Err(io::Error::last_os_error());
        }
        let directory = domain::named(
            &droidloom,
            "lmkd-bootstrap",
            libc::O_RDONLY | libc::O_DIRECTORY,
        )?;
        for (name, mode) in [("libdroidloom_init_relay.so", 0o644), ("lmkd", 0o755)] {
            drop(domain::at(
                directory.as_raw_fd(),
                &CString::new(name).expect("fixed name"),
                libc::O_WRONLY | libc::O_CREAT | libc::O_EXCL,
                mode,
            )?);
        }
        bind_readonly(
            &root,
            &format!("{BOOTSTRAP}/libdroidloom_init_relay.so"),
            self.barrier.file(),
        )?;
        bind_readonly(&root, &format!("{BOOTSTRAP}/lmkd"), self.lmkd.file())?;
        let mut generated = domain::at(
            directory.as_raw_fd(),
            c"lmkd.rc",
            libc::O_RDWR | libc::O_CREAT | libc::O_EXCL,
            0o644,
        )?;
        generated.write_all(lmkd_rc(self.policy.lmkd_uid, self.policy.lmkd_gid).as_bytes())?;
        generated.sync_all()?;
        old_rc.validate(true)?;
        bind_readonly(&root, "system/etc/init/lmkd.rc", &generated)?;
        // Preserve the pre-existing loader/preload pair and a non-set-ID init
        // on an explicit nosuid read-only bind before relying on PDEATHSIG.
        bind_readonly(&root, "system/bin/init", init.file())?;
        init.validate(true)?;
        linker.validate(true)?;
        compat.validate(true)?;
        self.barrier.validate(true)?;
        self.lmkd.validate(true)?;
        self.prepared = true;
        self.sealed = false;
        pidfd_alive(&self.owner)
    }

    /// cpu_placement::prepare has sealed CLONE_NEWCGROUP immediately before
    /// this call. Its v2 namespace root must be the exact inherited domain.
    pub(crate) fn project_cgroup(&self, root: &Path) -> io::Result<()> {
        if !self.prepared || self.sealed {
            return Err(error("relay image is not prepared"));
        }
        pidfd_alive(&self.owner)?;
        if Identity::of(&self.domain)? != self.domain_identity {
            return Err(error("held domain identity changed"));
        }
        domain::mount_private_view(root, self.domain_identity)
    }

    /// Attach only to the final /init second_stage command. No ordinary
    /// helper may inherit these capabilities or the private opt-in variables.
    pub(crate) fn configure_init(&mut self, command: &mut Command) -> io::Result<()> {
        if !self.prepared || self.sealed {
            return Err(error("init release preparation reused or incomplete"));
        }
        self.sealed = true;
        require_init_command(command)?;
        pidfd_alive(&self.owner)?;
        self.barrier.validate(false)?;
        self.lmkd.validate(false)?;
        clean_command_environment(command);
        command
            .env("LD_PRELOAD", init_peer::preload())
            .env(INIT_ENV[0], "1")
            .env(INIT_ENV[1], init_peer::INIT_ABI_TEXT)
            .env(INIT_ENV[2], init_peer::CONTROL_FD.to_string())
            .env(INIT_ENV[3], policy::hex(&self.nonce))
            .env(INIT_ENV[4], self.policy.bootstrap_timeout_ms.to_string());
        let control = self.channel.as_raw_fd();
        let owner = self.owner.as_raw_fd();
        // SAFETY: the entry is single-threaded. This pre-exec closure performs
        // only async-signal-safe syscalls and changes no shared parent state.
        unsafe {
            command.pre_exec(move || {
                // This is the final pre-exec callback, after any CPU placement
                // callbacks. Keep the inherited parent-death link explicit at
                // the exact direct, nonprivileged init exec boundary.
                if libc::getuid() != 0
                    || libc::geteuid() != 0
                    || libc::getgid() != 0
                    || libc::getegid() != 0
                    || libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGKILL) < 0
                {
                    return Err(io::Error::other(
                        "init credentials or parent-death contract changed before exec",
                    ));
                }
                let mut poll = libc::pollfd {
                    fd: owner,
                    events: libc::POLLIN,
                    revents: 0,
                };
                if libc::poll(&mut poll, 1, 0) != 0 || poll.revents != 0 {
                    return Err(io::Error::other(
                        "entry owner died immediately before init exec",
                    ));
                }
                close_on_exec(control, false)
            });
        }
        Ok(())
    }
}

fn require_init_command(command: &Command) -> io::Result<()> {
    let mut args = command.get_args();
    if command.get_program() != std::ffi::OsStr::new("/init")
        || args.next() != Some(std::ffi::OsStr::new("second_stage"))
        || args.next().is_some()
    {
        return Err(error(
            "relay barrier requires a direct exact /init second_stage exec",
        ));
    }
    Ok(())
}

fn make_parent(root: &File, name: &str) -> io::Result<File> {
    let name = CString::new(name).map_err(|_| error("invalid fixed parent"))?;
    if unsafe { libc::mkdirat(root.as_raw_fd(), name.as_ptr(), 0o755) } != 0 {
        let e = io::Error::last_os_error();
        if e.kind() != io::ErrorKind::AlreadyExists {
            return Err(e);
        }
    }
    let file = domain::at(
        root.as_raw_fd(),
        &name,
        libc::O_RDONLY | libc::O_DIRECTORY,
        0,
    )?;
    let m = file.metadata()?;
    if m.uid() != 0 || m.mode() & 0o022 != 0 {
        return Err(error("bootstrap parent is writable by another role"));
    }
    Ok(file)
}
fn bind_readonly(root: &File, relative: &str, source: &File) -> io::Result<()> {
    let target = domain::beneath(root, relative, libc::O_PATH)?;
    if !target.metadata()?.is_file() || !source.metadata()?.is_file() {
        return Err(error("readonly overlay is not a regular file"));
    }
    let source_path =
        CString::new(format!("/proc/self/fd/{}", source.as_raw_fd())).expect("descriptor path");
    let target_path =
        CString::new(format!("/proc/self/fd/{}", target.as_raw_fd())).expect("descriptor path");
    if unsafe {
        libc::mount(
            source_path.as_ptr(),
            target_path.as_ptr(),
            std::ptr::null(),
            libc::MS_BIND,
            std::ptr::null(),
        )
    } != 0
    {
        return Err(io::Error::last_os_error());
    }
    // Reopen through the held root after binding: the old target FD still
    // names the covered mount and cannot identify the newly attached mount.
    let mounted = domain::beneath(root, relative, libc::O_PATH)?;
    if Identity::of(&mounted)? != Identity::of(source)? {
        return Err(error("readonly overlay identity mismatch"));
    }
    let target_path =
        CString::new(format!("/proc/self/fd/{}", mounted.as_raw_fd())).expect("descriptor path");
    if unsafe {
        libc::mount(
            std::ptr::null(),
            target_path.as_ptr(),
            std::ptr::null(),
            libc::MS_BIND | libc::MS_REMOUNT | libc::MS_RDONLY | libc::MS_NOSUID | libc::MS_NODEV,
            std::ptr::null(),
        )
    } != 0
    {
        return Err(io::Error::last_os_error());
    }
    Ok(())
}
fn require_init_alias(root: &File, expected: Identity) -> io::Result<()> {
    let alias = domain::named(root, "init", libc::O_PATH)?;
    if alias.metadata()?.file_type().is_symlink() {
        let mut buffer = [0u8; 256];
        let count = unsafe {
            libc::readlinkat(
                root.as_raw_fd(),
                c"init".as_ptr(),
                buffer.as_mut_ptr().cast(),
                buffer.len(),
            )
        };
        if count < 0 {
            return Err(io::Error::last_os_error());
        }
        let value = &buffer[..count as usize];
        if value != b"system/bin/init" && value != b"/system/bin/init" {
            return Err(error("/init alias is not the paired executable"));
        }
    } else if !alias.metadata()?.is_file() || Identity::of(&alias)? != expected {
        return Err(error("/init is not the paired executable inode"));
    }
    Ok(())
}
fn read_exact(file: &File, buffer: &mut [u8], offset: u64) -> io::Result<()> {
    let mut filled = 0;
    while filled != buffer.len() {
        let count = file.read_at(&mut buffer[filled..], offset + filled as u64)?;
        if count == 0 {
            return Err(error("ELF input truncated"));
        }
        filled += count;
    }
    Ok(())
}
fn require_interpreter(file: &File, expected: &str) -> io::Result<()> {
    let mut header = [0u8; 64];
    read_exact(file, &mut header, 0)?;
    let u16_at = |at| u16::from_le_bytes(header[at..at + 2].try_into().expect("header width"));
    let u64_at = |at| u64::from_le_bytes(header[at..at + 8].try_into().expect("header width"));
    #[cfg(target_arch = "x86_64")]
    let machine = 62;
    #[cfg(target_arch = "aarch64")]
    let machine = 183;
    if &header[..7] != b"\x7fELF\x02\x01\x01"
        || !matches!(u16_at(16), 2 | 3)
        || u16_at(18) != machine
        || u16_at(52) != 64
        || u16_at(54) != 56
        || u16_at(56) == 0
        || u16_at(56) > 1024
    {
        return Err(error("init is not a bounded native ELF64 executable"));
    }
    let bytes = file.metadata()?.size();
    let start = u64_at(32);
    let end = start
        .checked_add(u64::from(u16_at(56)) * 56)
        .ok_or_else(|| error("ELF headers overflow"))?;
    if end > bytes {
        return Err(error("ELF program headers exceed file"));
    }
    let mut found = false;
    for index in 0..u16_at(56) {
        let mut ph = [0u8; 56];
        read_exact(file, &mut ph, start + u64::from(index) * 56)?;
        if u32::from_le_bytes(ph[..4].try_into().expect("program type")) != 3 {
            continue;
        }
        let offset = u64::from_le_bytes(ph[8..16].try_into().expect("program offset"));
        let size = u64::from_le_bytes(ph[32..40].try_into().expect("program size"));
        if found
            || size != expected.len() as u64 + 1
            || offset.checked_add(size).is_none_or(|n| n > bytes)
        {
            return Err(error(
                "init PT_INTERP duplicate or outside paired loader contract",
            ));
        }
        let mut interpreter = vec![0; size as usize];
        read_exact(file, &mut interpreter, offset)?;
        if interpreter.last() != Some(&0)
            || &interpreter[..interpreter.len() - 1] != expected.as_bytes()
        {
            return Err(error(
                "init dynamic loader differs from paired bootstrap linker",
            ));
        }
        found = true;
    }
    if !found {
        return Err(error(
            "init has no PT_INTERP; constructor cannot be guaranteed",
        ));
    }
    Ok(())
}
fn lmkd_rc(uid: u32, gid: u32) -> String {
    // Do not use escaped physical newlines: Rust strips their leading
    // whitespace and would remove the service-option indentation.
    format!(
        concat!(
            "# Package-owned native relay LMKD; init constructor owns the startup barrier.\n",
            "service lmkd {}\n",
            "    class core\n",
            "    user {}\n",
            "    group {} system readproc\n",
            "    capabilities DAC_OVERRIDE KILL IPC_LOCK SYS_NICE SYS_RESOURCE\n",
            "    socket lmkd seqpacket+passcred 0660 system system\n",
            "    task_profiles ServiceCapacityLow\n",
            "    stdio_to_kmsg\n",
            "    setenv DROIDLOOM_CELL 1\n",
            "    setenv DROIDLOOM_LMKD_CGROUP /sys/fs/cgroup\n",
            "    setenv DROIDLOOM_LMKD_PRESSURE relay-required\n",
        ),
        init_peer::LMKD,
        uid,
        gid
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::symlink;
    #[test]
    fn final_init_exec_contract_rejects_wrappers_and_other_stage() {
        let mut command = Command::new("/init");
        command.arg("second_stage");
        require_init_command(&command).unwrap();
        command.arg("unexpected");
        assert!(require_init_command(&command).is_err());
        let mut wrong = Command::new("/init");
        wrong.arg("first_stage");
        assert!(require_init_command(&wrong).is_err());
        let mut wrapper = Command::new("taskset");
        wrapper.args(["/init", "second_stage"]);
        assert!(require_init_command(&wrapper).is_err());
    }
    #[test]
    fn generated_native_lmkd_options_remain_inside_one_service_block() {
        let text = lmkd_rc(1069, 1069);
        let mut lines = text
            .lines()
            .filter(|line| !line.is_empty() && !line.starts_with('#'));
        assert_eq!(
            lines.next(),
            Some("service lmkd /droidloom/lmkd-bootstrap/lmkd")
        );
        let options: Vec<_> = lines.collect();
        assert_eq!(options.len(), 10);
        assert!(
            options
                .iter()
                .all(|line| line.starts_with("    ") && !line.starts_with("     "))
        );
        assert!(options.contains(&"    user 1069"));
        assert!(options.contains(&"    group 1069 system readproc"));
        assert!(options.contains(&"    setenv DROIDLOOM_LMKD_PRESSURE relay-required"));
    }
    #[test]
    fn init_alias_cannot_escape_the_private_image() {
        let temp = tempfile::tempdir().unwrap();
        let root = domain::directory(temp.path()).unwrap();
        symlink("../../host/init", temp.path().join("init")).unwrap();
        assert!(
            require_init_alias(
                &root,
                Identity {
                    device: 1,
                    inode: 1
                }
            )
            .is_err()
        );
        std::fs::remove_file(temp.path().join("init")).unwrap();
        symlink("/system/bin/init", temp.path().join("init")).unwrap();
        require_init_alias(
            &root,
            Identity {
                device: 1,
                inode: 1,
            },
        )
        .unwrap();
    }
    #[test]
    fn wrong_or_missing_dynamic_loader_cannot_open_init_barrier() {
        let mut file = tempfile::tempfile().unwrap();
        let mut bytes = vec![0u8; 256];
        bytes[..7].copy_from_slice(b"\x7fELF\x02\x01\x01");
        bytes[16..18].copy_from_slice(&3u16.to_le_bytes());
        #[cfg(target_arch = "x86_64")]
        bytes[18..20].copy_from_slice(&62u16.to_le_bytes());
        #[cfg(target_arch = "aarch64")]
        bytes[18..20].copy_from_slice(&183u16.to_le_bytes());
        bytes[32..40].copy_from_slice(&64u64.to_le_bytes());
        bytes[52..54].copy_from_slice(&64u16.to_le_bytes());
        bytes[54..56].copy_from_slice(&56u16.to_le_bytes());
        bytes[56..58].copy_from_slice(&1u16.to_le_bytes());
        bytes[64..68].copy_from_slice(&3u32.to_le_bytes());
        bytes[72..80].copy_from_slice(&128u64.to_le_bytes());
        bytes[96..104].copy_from_slice(&(INIT_LINKER.len() as u64 + 1).to_le_bytes());
        bytes[128..128 + INIT_LINKER.len()].copy_from_slice(INIT_LINKER.as_bytes());
        file.write_all(&bytes).unwrap();
        require_interpreter(&file, INIT_LINKER).unwrap();
        file.write_at(b"x", 128).unwrap();
        assert!(require_interpreter(&file, INIT_LINKER).is_err());
        file.write_at(&0u32.to_le_bytes(), 64).unwrap();
        assert!(require_interpreter(&file, INIT_LINKER).is_err());
        file.set_len(63).unwrap();
        assert!(require_interpreter(&file, INIT_LINKER).is_err());
    }
    #[test]
    fn ordinary_file_does_not_substitute_for_entry_owner_pidfd() {
        let file = tempfile::tempfile().unwrap();
        assert!(pidfd_alive(&file).is_err());
        let raw = unsafe { libc::syscall(libc::SYS_pidfd_open, libc::getpid(), 0) };
        assert!(raw >= 0);
        let pidfd = unsafe { File::from_raw_fd(raw as i32) };
        pidfd_alive(&pidfd).unwrap();
    }
    #[test]
    fn sealed_fixed_capabilities_do_not_reach_an_ordinary_exec() {
        let source = tempfile::tempfile().unwrap();
        let high = unsafe { libc::fcntl(source.as_raw_fd(), libc::F_DUPFD_CLOEXEC, 256) };
        assert!(high >= 256);
        let source = unsafe { File::from_raw_fd(high) };
        for sealed in [false, true] {
            let raw = source.as_raw_fd();
            let mut command = Command::new("/bin/sh");
            command.args([
                "-c",
                "for n in 198 199 200 201; do if [ -e /proc/self/fd/$n ]; then exit 9; fi; done",
            ]);
            unsafe {
                command.pre_exec(move || {
                    for target in FIXED {
                        if libc::dup2(raw, target) < 0 {
                            return Err(io::Error::last_os_error());
                        }
                        close_on_exec(target, sealed)?;
                    }
                    Ok(())
                });
            }
            let status = command.status().unwrap();
            assert_eq!(status.code(), Some(if sealed { 0 } else { 9 }));
        }
    }
}
