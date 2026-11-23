//! Release-bound re-opening of the birth pidfd and PID namespace. Each Linux
//! descriptor is opened in the current service domain after switch_root.
use super::*;
use std::fs;
use std::os::fd::{AsFd, BorrowedFd, OwnedFd};

const GENERATION: &str = "/run/droidloom-early/generation.json";
const NAMESPACE: &str = "/run/droidloom-early/pidns";
const NS_GET_NSTYPE: libc::c_ulong = 0xb703;
const NS_GET_TGID_IN_PIDNS: libc::c_ulong = 0x8004b709;
const PIDFD_GET_INFO_V0: libc::c_ulong = 0xc040ff0b;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Birth {
    schema: String,
    selection_sha256: String,
    boot_id: String,
    host_pid: i32,
    pidfs_dev: u64,
    pidfs_ino: u64,
    pidns_dev: u64,
    pidns_ino: u64,
}

#[repr(C)]
#[derive(Default)]
struct PidInfo {
    mask: u64,
    cgroup: u64,
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
}

fn invalid(detail: &str) -> io::Error {
    io::Error::other(detail)
}
fn cv(result: i32) -> io::Result<i32> {
    if result < 0 {
        Err(io::Error::last_os_error())
    } else {
        Ok(result)
    }
}
fn pidfd(pid: i32) -> io::Result<File> {
    let raw = cv(unsafe { libc::syscall(libc::SYS_pidfd_open, pid, 0) as i32 })?;
    Ok(unsafe { File::from_raw_fd(raw) })
}
fn live(fd: BorrowedFd<'_>) -> io::Result<()> {
    let mut status = libc::pollfd {
        fd: fd.as_raw_fd(),
        events: libc::POLLIN,
        revents: 0,
    };
    match cv(unsafe { libc::poll(&mut status, 1, 0) })? {
        0 => Ok(()),
        _ => Err(invalid(
            "kernel reports that the selected process has exited",
        )),
    }
}
fn info(fd: BorrowedFd<'_>, creds: bool) -> io::Result<PidInfo> {
    let mask = if creds { 3 } else { 1 };
    let mut record = PidInfo {
        mask,
        ..Default::default()
    };
    cv(unsafe { libc::ioctl(fd.as_raw_fd(), PIDFD_GET_INFO_V0, &mut record) })?;
    if record.mask & mask != mask {
        return Err(invalid("kernel omitted required PIDFD_GET_INFO fields"));
    }
    Ok(record)
}
fn translated(ns: &File, id: i32) -> io::Result<i32> {
    cv(unsafe { libc::ioctl(ns.as_raw_fd(), NS_GET_TGID_IN_PIDNS, id as libc::c_ulong) })
}
fn local_ids(fd: BorrowedFd<'_>) -> io::Result<Vec<i32>> {
    let data = fs::read_to_string(format!("/proc/self/fdinfo/{}", fd.as_raw_fd()))?;
    let row = data
        .lines()
        .find_map(|l| l.strip_prefix("NSpid:"))
        .ok_or_else(|| invalid("missing kernel NSpid for held pidfd"))?;
    let ids: Vec<i32> = row
        .split_ascii_whitespace()
        .map(|n| n.parse().map_err(io::Error::other))
        .collect::<io::Result<_>>()?;
    if ids.is_empty() || ids.len() > 32 || ids.iter().any(|n| *n < 1) {
        return Err(invalid("invalid or exited pid namespace membership"));
    }
    Ok(ids)
}
fn identity(f: &File) -> io::Result<(u64, u64)> {
    let meta = f.metadata()?;
    Ok((meta.dev(), meta.ino()))
}

pub(super) fn verify_birth_before_switch(selected: &str) -> io::Result<()> {
    let (held, bytes) = SealedFile::read(Path::new(GENERATION), 4096).map_err(io::Error::other)?;
    let birth: Birth = serde_json::from_slice(&bytes)?;
    if held.node.mode & 0o7777 != 0o400
        || birth.schema != "droidloom-early-child-v1"
        || birth.host_pid <= 1
        || birth.selection_sha256 != selected
        || birth.boot_id != fs::read_to_string("/proc/sys/kernel/random/boot_id")?.trim()
    {
        return Err(invalid(
            "the original Android generation belongs to a different Ubuntu boot or private release",
        ));
    }
    let init = pidfd(birth.host_pid)?;
    let ns = open_root_trusted(Path::new(NAMESPACE)).map_err(io::Error::other)?;
    if identity(&init)? != (birth.pidfs_dev, birth.pidfs_ino)
        || identity(&ns)? != (birth.pidns_dev, birth.pidns_ino)
        || cv(unsafe { libc::ioctl(ns.as_raw_fd(), NS_GET_NSTYPE) })? != libc::CLONE_NEWPID
        || translated(&ns, birth.host_pid)? != 1
        || info(init.as_fd(), false)?.tgid != birth.host_pid as u32
    {
        return Err(invalid(
            "the original pidfd and pinned namespace do not identify this Android PID 1",
        ));
    }
    live(init.as_fd())?;
    held.revalidate().map_err(io::Error::other)
}

pub struct EarlyAndroidGeneration {
    configuration: ConfigurationReadGuard,
    public: SharedKernelLauncher,
    program: super::launcher::PublishedServiceProgram,
    selected: ProductionSelection,
    record: SealedFile,
    base_manifest: SealedFile,
    carrier: SealedFile,
    init: File,
    ns: File,
    birth: Birth,
    depth: usize,
}

impl EarlyAndroidGeneration {
    /// Acquire the exact kernel-born generation bound by a private root selection.
    pub fn acquire() -> io::Result<Self> {
        let configuration = ConfigurationReadGuard::acquire()?;
        let selected = ProductionSelection::load(&configuration, Path::new(SPECIFICATION), 0)
            .map_err(io::Error::other)?;
        if !selected.early_boot {
            return Err(invalid("kernel first-stage Android was not selected"));
        }
        let public = SharedKernelLauncher::read()?
            .ok_or_else(|| invalid("public early Android release is missing"))?;
        if !public.matches_private_early(&selected.selected.sha256) {
            return Err(invalid("public and private early Android releases differ"));
        }
        let program = public.entry_program()?;
        if !program.matches_current_process()? {
            return Err(invalid(
                "the running early owner differs from the installed release executable",
            ));
        }
        let (record, bytes) =
            SealedFile::read(Path::new(GENERATION), 4096).map_err(io::Error::other)?;
        let birth: Birth = serde_json::from_slice(&bytes)?;
        if birth.schema != "droidloom-early-child-v1"
            || record.node.mode & 0o7777 != 0o400
            || birth.host_pid <= 1
            || birth.selection_sha256 != selected.selected.sha256
            || birth.boot_id != fs::read_to_string("/proc/sys/kernel/random/boot_id")?.trim()
        {
            return Err(invalid(
                "sealed early child does not belong to this boot and release",
            ));
        }
        let base = selected.base_cohort();
        let (base_manifest, bytes) = SealedFile::read(
            &Path::new("/etc/droidloom/cohorts").join(format!("{base}.json")),
            16 * 1024,
        )
        .map_err(io::Error::other)?;
        if base_manifest.sha256 != base {
            return Err(invalid(
                "early Android base manifest differs from the sealed private choice",
            ));
        }
        let declaration =
            crate::production_mounts::selected_early_observer(&bytes).map_err(io::Error::other)?;
        let image = Path::new("/var/lib/droidloom/cohorts")
            .join(base)
            .join("images")
            .join(droidloom_contracts::system_ext::READINESS_FILE);
        let (carrier, _bytes) =
            SealedFile::read(&image, 16 * 1024 * 1024).map_err(io::Error::other)?;
        if carrier.sha256 != declaration.sha256 || carrier.node.bytes != declaration.bytes {
            return Err(invalid(
                "early readiness carrier does not match the selected release",
            ));
        }
        let init = pidfd(birth.host_pid)?;
        let ns = open_root_trusted(Path::new(NAMESPACE)).map_err(io::Error::other)?;
        let levels = local_ids(init.as_fd())?;
        if levels.len() < 2 || levels.first() != Some(&birth.host_pid) || levels.last() != Some(&1)
        {
            return Err(invalid("selected task is not the nested namespace init"));
        }
        let this = Self {
            configuration,
            public,
            program,
            selected,
            record,
            base_manifest,
            carrier,
            init,
            ns,
            birth,
            depth: levels.len(),
        };
        this.revalidate()?;
        Ok(this)
    }
    /// Host group authorized to connect to the fixed per-cell socket.
    pub fn observer_group(&self) -> io::Result<u32> {
        let range = &self.selected.spec().subordinate_gids;
        if range.count <= 9999 {
            return Err(invalid("cell range lacks Android nobody"));
        }
        range
            .start
            .checked_add(9999)
            .ok_or_else(|| invalid("invalid observer group"))
    }

    /// Poll the actual Android namespace init without rehashing its release.
    pub fn check_liveness(&self) -> io::Result<()> {
        live(self.init.as_fd())
    }

    /// Check both the sealed selection and the original process in the pinned PID namespace.
    pub fn revalidate(&self) -> io::Result<()> {
        self.configuration.revalidate()?;
        self.public.revalidate()?;
        self.program.revalidate()?;
        self.selected.revalidate().map_err(io::Error::other)?;
        self.record.revalidate().map_err(io::Error::other)?;
        self.base_manifest
            .revalidate_path()
            .map_err(io::Error::other)?;
        self.carrier.revalidate_path().map_err(io::Error::other)?;
        let named = open_root_trusted(Path::new(NAMESPACE)).map_err(io::Error::other)?;
        let namespace = (self.birth.pidns_dev, self.birth.pidns_ino);
        if identity(&named)? != namespace
            || identity(&self.ns)? != namespace
            || identity(&self.init)? != (self.birth.pidfs_dev, self.birth.pidfs_ino)
            || cv(unsafe { libc::ioctl(self.ns.as_raw_fd(), NS_GET_NSTYPE) })? != libc::CLONE_NEWPID
            || translated(&self.ns, self.birth.host_pid)? != 1
            || info(self.init.as_fd(), false)?.tgid != self.birth.host_pid as u32
        {
            return Err(invalid("early namespace or its unique PID 1 changed"));
        }
        live(self.init.as_fd())
    }
    /// Obtain a real socket peer pidfd and admit only the declared, mapped AID_NOBODY
    /// service directly launched by the selected stock init.
    pub fn verify_observer(&self, channel: BorrowedFd<'_>) -> io::Result<OwnedFd> {
        self.revalidate()?;
        let mut context = [0u8; 256];
        let mut len = context.len() as libc::socklen_t;
        cv(unsafe {
            libc::getsockopt(
                channel.as_raw_fd(),
                libc::SOL_SOCKET,
                libc::SO_PEERSEC,
                context.as_mut_ptr().cast(),
                &mut len,
            )
        })?;
        let context = &context[..len as usize];
        if context.strip_suffix(&[0]).unwrap_or(context) != b"u:r:droidloom_readiness:s0" {
            return Err(invalid(
                "early readiness socket peer is not the Android observer domain",
            ));
        }
        let mut cred: libc::ucred = unsafe { std::mem::zeroed() };
        len = std::mem::size_of_val(&cred) as _;
        cv(unsafe {
            libc::getsockopt(
                channel.as_raw_fd(),
                libc::SOL_SOCKET,
                libc::SO_PEERCRED,
                (&mut cred as *mut libc::ucred).cast(),
                &mut len,
            )
        })?;
        if len as usize != std::mem::size_of_val(&cred) {
            return Err(invalid("incomplete kernel peer credentials"));
        }
        let mut raw = -1i32;
        len = std::mem::size_of_val(&raw) as _;
        cv(unsafe {
            libc::getsockopt(
                channel.as_raw_fd(),
                libc::SOL_SOCKET,
                77,
                (&mut raw as *mut i32).cast(),
                &mut len,
            )
        })?;
        let peer = unsafe { OwnedFd::from_raw_fd(cv(raw)?) };
        if len as usize != std::mem::size_of_val(&raw) {
            return Err(invalid("incomplete peer pidfd"));
        }
        let observed = info(peer.as_fd(), true)?;
        let spec = self.selected.spec();
        let mapped = |range: &crate::IdRange| -> io::Result<u32> {
            if range.count <= 9999 {
                return Err(invalid("cell range does not include Android nobody"));
            }
            range
                .start
                .checked_add(9999)
                .ok_or_else(|| invalid("cell ID map overflow"))
        };
        let uid = mapped(&spec.subordinate_uids)?;
        let gid = mapped(&spec.subordinate_gids)?;
        let ids = local_ids(peer.as_fd())?;
        let relative = translated(&self.ns, cred.pid)?;
        if cred.pid <= 1
            || observed.ppid != self.birth.host_pid as u32
            || observed.pid != cred.pid as u32
            || observed.tgid != cred.pid as u32
            || cred.uid != uid
            || cred.gid != gid
            || [observed.ruid, observed.euid, observed.suid, observed.fsuid] != [uid; 4]
            || [observed.rgid, observed.egid, observed.sgid, observed.fsgid] != [gid; 4]
            || relative <= 1
            || ids.len() != self.depth
            || ids.last() != Some(&relative)
        {
            return Err(invalid(
                "observer identity does not belong to the selected early Android init",
            ));
        }
        live(peer.as_fd())?;
        self.revalidate()?;
        Ok(peer)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn original_pidfd_reports_direct_child_and_becomes_readable_after_exit() {
        use std::process::Command;
        let mut child = Command::new("/bin/sleep").arg("20").spawn().unwrap();
        let held = pidfd(child.id() as i32).unwrap();
        let original = info(held.as_fd(), true).unwrap();
        assert_eq!(original.tgid, child.id());
        assert_eq!(original.ppid, std::process::id());
        assert_eq!(
            *local_ids(held.as_fd()).unwrap().last().unwrap(),
            child.id() as i32
        );
        live(held.as_fd()).unwrap();
        child.kill().unwrap();
        child.wait().unwrap();
        assert!(live(held.as_fd()).is_err());
    }
    #[test]
    fn ordinary_file_cannot_translate_a_namespace_pid_or_return_process_info() {
        let file = tempfile::tempfile().unwrap();
        assert!(info(file.as_fd(), false).is_err());
        assert!(translated(&file, 1).is_err());
    }
}
