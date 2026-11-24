//! One-time transfer of the original boot factory into its permanent service.
//! Only the fixed systemd executor opens the migration file for writing. The
//! adopter relays that same FileDescription; the factory writes its own "0".
use super::*;

const ADOPT: &[u8; 8] = b"DLADOPT1";
const PLACED: &[u8; 8] = b"DLPLACE1";
const ACKNOWLEDGED: &[u8; 8] = b"DLADACK1";
const ADOPTED: &[u8; 8] = b"DLADONE1";
pub(super) const FACTORY_CGROUP: &str = "/system.slice/droidloom-instance-factory.service";
const MEMBERSHIP: &str =
    "/sys/fs/cgroup/system.slice/droidloom-instance-factory.service/cgroup.procs";
const CGROUP2_MAGIC: libc::c_long = 0x63677270;

fn self_pidfd() -> io::Result<File> {
    let raw = unsafe { libc::syscall(libc::SYS_pidfd_open, libc::getpid(), 0) };
    if raw < 0 {
        return Err(io::Error::last_os_error());
    }
    let held = unsafe { File::from_raw_fd(raw as i32) };
    if ended(&held)? {
        return Err(invalid("factory adoption lost the original process"));
    }
    Ok(held)
}
fn membership_file(file: &File, access: i32) -> io::Result<()> {
    check_fs(file, CGROUP2_MAGIC)?;
    let node = file.metadata()?;
    let flags = unsafe { libc::fcntl(file.as_raw_fd(), libc::F_GETFL) };
    cv(flags)?;
    if !node.is_file()
        || node.uid() != 0
        || node.gid() != 0
        || node.nlink() != 1
        || node.mode() & 0o7777 != 0o644
        || flags & libc::O_ACCMODE != access
        || flags & (libc::O_APPEND | libc::O_PATH) != 0
    {
        return Err(invalid(
            "factory migration is not the original cgroup control file",
        ));
    }
    Ok(())
}
fn inherited_membership() -> io::Result<File> {
    let raw = unsafe { libc::fcntl(libc::STDOUT_FILENO, libc::F_DUPFD_CLOEXEC, 64) };
    if raw < 0 {
        return Err(io::Error::last_os_error());
    }
    let file = unsafe { File::from_raw_fd(raw) };
    membership_file(&file, libc::O_WRONLY)?;
    // No subsequent log or generic standard-output write can migrate a task.
    // StandardInput=null is part of the exact loaded source unit.
    cv(unsafe { libc::dup2(libc::STDIN_FILENO, libc::STDOUT_FILENO) })?;
    Ok(file)
}
fn original_factory_cgroup(expected: &str) -> io::Result<()> {
    let current = File::open("/proc/self/ns/cgroup")?;
    let original = File::open("/proc/1/ns/cgroup")?;
    if identity(&current)? != identity(&original)? {
        return Err(invalid(
            "factory no longer observes the initial cgroup namespace",
        ));
    }
    let mut body = String::new();
    File::open("/proc/self/cgroup")?
        .take(4097)
        .read_to_string(&mut body)?;
    if body != format!("0::{expected}\n") {
        return Err(invalid("original boot factory is outside its fixed cgroup"));
    }
    Ok(())
}
fn client_channel() -> io::Result<(File, Peer)> {
    let node = std::fs::symlink_metadata(SOCKET)?;
    if !node.file_type().is_socket()
        || node.uid() != 0
        || node.gid() != 0
        || node.nlink() != 1
        || node.mode() & 0o7777 != 0o600
    {
        return Err(invalid(
            "factory adoption endpoint is not the private boot socket",
        ));
    }
    let channel = socket()?;
    let (name, length) = address();
    cv(unsafe {
        libc::connect(
            channel.as_raw_fd(),
            (&name as *const libc::sockaddr_un).cast(),
            length,
        )
    })?;
    let peer = Peer::acquire(&channel, FACTORY_SELINUX, FACTORY_APPARMOR)?;
    Ok((channel, peer))
}
fn expect(channel: &File, expected: &[u8; 8], duration: Duration) -> io::Result<()> {
    let Some((tag, descriptors)) = receive(channel, duration)? else {
        return Err(invalid("original factory adoption timed out"));
    };
    if &tag != expected || !descriptors.is_empty() {
        return Err(invalid("original factory adoption phase differs"));
    }
    Ok(())
}

/// This long-lived state is independent of any Android-generation service.
/// It is never reconstructed from a JSON claim or a new numeric process ID.
pub(super) struct Adoption {
    manager: manager::Manager,
    invocation: [u8; 16],
    pid: u32,
    pidfd: File,
}
impl Adoption {
    pub(super) fn request(tag: &[u8; 8]) -> bool {
        tag == ADOPT
    }
    pub(super) fn accept(channel: &File, peer: &Peer, membership: File) -> io::Result<Self> {
        cv(unsafe { droidloom_factory_context() })?;
        original_factory_cgroup("/")?;
        peer.revalidate()?;
        let manager = manager::Manager::acquire_factory()?;
        let invocation = manager.verify_factory_adopter(peer.pid)?;
        membership_file(&membership, libc::O_WRONLY)?;
        // This read-only open is factory-origin. Only the received write-open
        // FileDescription retains the original service executor's f_cred.
        let named = std::fs::OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_CLOEXEC | libc::O_NOFOLLOW)
            .open(MEMBERSHIP)?;
        membership_file(&named, libc::O_RDONLY)?;
        if identity(&named)? != identity(&membership)? {
            return Err(invalid(
                "adopter relayed a different cgroup membership inode",
            ));
        }
        peer.revalidate()?;
        if manager.verify_factory_adopter(peer.pid)? != invocation {
            return Err(invalid(
                "factory adopter invocation changed before self placement",
            ));
        }
        let pidfd = self_pidfd()?;
        cv(unsafe { droidloom_factory_context() })?;
        original_factory_cgroup("/")?;
        let mut transferred = &membership;
        transferred.write_all(b"0")?;
        drop(membership);
        original_factory_cgroup(FACTORY_CGROUP)?;
        cv(unsafe { droidloom_factory_context() })?;
        send(channel, PLACED, &[])?;
        expect(channel, ACKNOWLEDGED, Duration::from_secs(35))?;
        peer.revalidate()?;
        let state = Self {
            manager,
            invocation,
            pid: unsafe { libc::getpid() } as u32,
            pidfd,
        };
        state.revalidate()?;
        send(channel, ADOPTED, &[])?;
        Ok(state)
    }
    pub(super) fn revalidate(&self) -> io::Result<()> {
        cv(unsafe { droidloom_factory_context() })?;
        if ended(&self.pidfd)? || self.pid != unsafe { libc::getpid() } as u32 {
            return Err(invalid("original adopted factory process changed"));
        }
        original_factory_cgroup(FACTORY_CGROUP)?;
        self.manager.verify_factory_main(self.pid, &self.invocation)
    }
}

/// The configured service starts this bounded adopter, not a replacement
/// kernel-domain process. READY and MAINPIDFD are one authenticated notification.
pub fn run_instance_adopter() -> io::Result<()> {
    cv(unsafe { droidloom_instance_context() })?;
    let selected = SharedKernelLauncher::read()?
        .ok_or_else(|| invalid("public selected release is absent"))?;
    if !selected.entry_program()?.matches_current_process()? {
        return Err(invalid(
            "factory adopter does not execute the published manager",
        ));
    }
    let pid = unsafe { libc::getpid() } as u32;
    let original = self_pidfd()?;
    let manager = manager::Manager::acquire_factory()?;
    let invocation = manager.verify_factory_adopter(pid)?;
    manager.verify_factory_membership(&original, &invocation)?;
    let membership = inherited_membership()?;
    let (channel, peer) = client_channel()?;
    peer.revalidate()?;
    send(&channel, ADOPT, &[&membership])?;
    drop(membership);
    expect(&channel, PLACED, Duration::from_secs(20))?;
    peer.revalidate()?;
    manager.verify_factory_membership(&peer.pidfd, &invocation)?;
    manager.notify_factory_main(pid, &peer.pidfd, &invocation)?;
    let deadline = Instant::now() + Duration::from_secs(25);
    loop {
        peer.revalidate()?;
        let state = manager.factory_state()?;
        if state.invocation != invocation
            || !matches!(state.main_pid, value if value == pid || value == peer.pid)
            || !matches!(state.state.as_str(), "activating" | "active")
        {
            return Err(invalid(
                "factory service changed while adopting its original MainPID",
            ));
        }
        if state.state == "active" {
            manager.verify_factory_main(peer.pid, &invocation)?;
            manager.verify_factory_membership(&peer.pidfd, &invocation)?;
            peer.revalidate()?;
            break;
        }
        if Instant::now() >= deadline {
            return Err(invalid("systemd did not adopt the original factory PIDFD"));
        }
        std::thread::sleep(Duration::from_millis(50));
    }
    send(&channel, ACKNOWLEDGED, &[])?;
    expect(&channel, ADOPTED, Duration::from_secs(10))?;
    manager.verify_factory_main(peer.pid, &invocation)?;
    manager.verify_factory_membership(&peer.pidfd, &invocation)?;
    peer.revalidate()?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn adoption_rejects_an_ordinary_file_even_with_correct_access_flags() {
        let file = tempfile::tempfile().unwrap();
        assert!(membership_file(&file, libc::O_RDWR).is_err());
    }
}
