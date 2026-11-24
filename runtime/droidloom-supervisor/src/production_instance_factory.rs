//! Boot-born kernel-lineage factory. The fixed systemd launcher owns each
//! Android generation; its original broker may borrow the closed query path.
//! Both roles retain native original-peer custody and source-owned operations.
use super::*;
use std::io::{Read, Write};
use std::os::fd::AsRawFd;
use std::os::unix::fs::{FileTypeExt, PermissionsExt};

#[path = "production_instance_adoption.rs"]
mod adoption;
#[path = "production_instance_identity.rs"]
mod boot_identity;
pub use adoption::run_instance_adopter;
#[path = "production_instance_placement.rs"]
mod placement;
pub(crate) use placement::move_original_init_from_factory;
pub(crate) const FACTORY_CGROUP: &str = adoption::FACTORY_CGROUP;

const SOCKET: &str = "/run/droidloom-early/instance-factory.sock";
const START: &[u8; 8] = b"DLSTART1";
const BIRTH: &[u8; 8] = b"DLCELL01";
const DONE: &[u8; 8] = b"DLDONE01";
const FAILED: &[u8; 8] = b"DLFAIL01";
const FACTORY_SELINUX: &str = "u:r:kernel:s0";
const FACTORY_APPARMOR: &str = "droidloom-instance-factory (enforce)";
const CLIENT_SELINUX: &str = "u:r:droidloom_instance_launcher:s0";
const CLIENT_APPARMOR: &str = "droidloom-instance-launcher (enforce)";
unsafe extern "C" {
    fn droidloom_factory_context() -> libc::c_int;
    fn droidloom_factory_prepare() -> libc::c_int;
    fn droidloom_factory_device_directory() -> libc::c_int;
}

fn wait(file: &File, events: i16, timeout: Duration) -> io::Result<bool> {
    let end = Instant::now() + timeout;
    let mut p = libc::pollfd {
        fd: file.as_raw_fd(),
        events,
        revents: 0,
    };
    loop {
        let remaining = end.saturating_duration_since(Instant::now());
        if remaining.is_zero() {
            return Ok(false);
        }
        let n = unsafe {
            libc::poll(
                &mut p,
                1,
                remaining.as_millis().max(1).min(i32::MAX as u128) as i32,
            )
        };
        if n < 0 && io::Error::last_os_error().kind() == io::ErrorKind::Interrupted {
            continue;
        }
        cv(n)?;
        if p.revents & (libc::POLLERR | libc::POLLNVAL) != 0 {
            return Err(invalid("instance factory endpoint failed"));
        }
        return Ok(n == 1 && p.revents & (events | libc::POLLHUP) != 0);
    }
}
fn address() -> (libc::sockaddr_un, libc::socklen_t) {
    let mut address = unsafe { std::mem::zeroed::<libc::sockaddr_un>() };
    address.sun_family = libc::AF_UNIX as libc::sa_family_t;
    for (slot, byte) in address.sun_path.iter_mut().zip(SOCKET.bytes()) {
        *slot = byte as libc::c_char;
    }
    (
        address,
        (std::mem::size_of::<libc::sa_family_t>() + SOCKET.len() + 1) as libc::socklen_t,
    )
}
fn socket() -> io::Result<File> {
    let fd = unsafe { libc::socket(libc::AF_UNIX, libc::SOCK_SEQPACKET | libc::SOCK_CLOEXEC, 0) };
    cv(fd)?;
    Ok(unsafe { File::from_raw_fd(fd) })
}
fn send(socket: &File, tag: &[u8; 8], descriptors: &[&File]) -> io::Result<()> {
    send_bytes(socket, tag, descriptors)
}
fn send_bytes(socket: &File, tag: &[u8], descriptors: &[&File]) -> io::Result<()> {
    if tag.len() < 8 || tag.len() > 256 {
        return Err(invalid("fixed factory packet size differs"));
    }
    if descriptors.len() > 1 {
        return Err(invalid(
            "one original descriptor is the entire fixed protocol",
        ));
    }
    let mut io = libc::iovec {
        iov_base: tag.as_ptr().cast_mut().cast(),
        iov_len: tag.len(),
    };
    let mut control = [0usize; 8];
    let mut msg = unsafe { std::mem::zeroed::<libc::msghdr>() };
    msg.msg_iov = &mut io;
    msg.msg_iovlen = 1;
    if let Some(fd) = descriptors.first() {
        msg.msg_control = control.as_mut_ptr().cast();
        msg.msg_controllen =
            unsafe { libc::CMSG_SPACE(std::mem::size_of::<i32>() as u32) } as usize;
        let header = unsafe { libc::CMSG_FIRSTHDR(&msg) };
        if header.is_null() {
            return Err(invalid("invalid native descriptor packet"));
        }
        unsafe {
            (*header).cmsg_level = libc::SOL_SOCKET;
            (*header).cmsg_type = libc::SCM_RIGHTS;
            (*header).cmsg_len = libc::CMSG_LEN(std::mem::size_of::<i32>() as u32) as usize;
            std::ptr::write_unaligned(libc::CMSG_DATA(header).cast::<i32>(), fd.as_raw_fd());
        }
    }
    if !wait(socket, libc::POLLOUT, Duration::from_secs(5))? {
        return Err(invalid("instance factory response timed out"));
    }
    let n = unsafe {
        libc::sendmsg(
            socket.as_raw_fd(),
            &msg,
            libc::MSG_NOSIGNAL | libc::MSG_DONTWAIT,
        )
    };
    if n < 0 {
        return Err(io::Error::last_os_error());
    }
    if n as usize != tag.len() {
        return Err(invalid("instance factory packet was incomplete"));
    }
    Ok(())
}
fn receive(socket: &File, timeout: Duration) -> io::Result<Option<([u8; 8], Vec<File>)>> {
    receive_bytes::<8>(socket, timeout)
}
fn receive_bytes<const N: usize>(
    socket: &File,
    timeout: Duration,
) -> io::Result<Option<([u8; N], Vec<File>)>> {
    if !(8..=256).contains(&N) {
        return Err(invalid("fixed factory packet size differs"));
    }
    if !wait(socket, libc::POLLIN, timeout)? {
        return Ok(None);
    }
    let mut data = [0; N];
    let mut io = libc::iovec {
        iov_base: data.as_mut_ptr().cast(),
        iov_len: data.len(),
    };
    let mut control = [0usize; 16];
    let mut msg = unsafe { std::mem::zeroed::<libc::msghdr>() };
    msg.msg_iov = &mut io;
    msg.msg_iovlen = 1;
    msg.msg_control = control.as_mut_ptr().cast();
    msg.msg_controllen = std::mem::size_of_val(&control);
    let n = unsafe {
        libc::recvmsg(
            socket.as_raw_fd(),
            &mut msg,
            libc::MSG_CMSG_CLOEXEC | libc::MSG_DONTWAIT,
        )
    };
    if n < 0 {
        return Err(io::Error::last_os_error());
    }
    let mut descriptors = Vec::new();
    let mut header = unsafe { libc::CMSG_FIRSTHDR(&msg) };
    let mut malformed = false;
    while !header.is_null() {
        unsafe {
            if (*header).cmsg_level != libc::SOL_SOCKET
                || (*header).cmsg_type != libc::SCM_RIGHTS
                || (*header).cmsg_len < (libc::CMSG_LEN(0) as usize)
            {
                malformed = true;
            } else {
                let bytes = (*header).cmsg_len - libc::CMSG_LEN(0) as usize;
                if bytes % std::mem::size_of::<i32>() != 0 {
                    malformed = true;
                }
                for i in 0..bytes / std::mem::size_of::<i32>() {
                    let fd = std::ptr::read_unaligned(libc::CMSG_DATA(header).cast::<i32>().add(i));
                    if fd < 0 {
                        malformed = true;
                    } else {
                        descriptors.push(File::from_raw_fd(fd));
                    }
                }
            }
            header = libc::CMSG_NXTHDR(&msg, header);
        }
    }
    if n != N as isize
        || msg.msg_flags & (libc::MSG_TRUNC | libc::MSG_CTRUNC) != 0
        || malformed
        || descriptors.len() > 1
    {
        return Err(invalid("invalid or truncated instance factory packet"));
    }
    Ok(Some((data, descriptors)))
}
struct Peer {
    pid: u32,
    pidfd: File,
    selinux: &'static str,
    apparmor: &'static str,
}
impl Peer {
    fn acquire(socket: &File, selinux: &'static str, apparmor: &'static str) -> io::Result<Self> {
        let mut credentials = unsafe { std::mem::zeroed::<libc::ucred>() };
        let mut length = std::mem::size_of_val(&credentials) as libc::socklen_t;
        cv(unsafe {
            libc::getsockopt(
                socket.as_raw_fd(),
                libc::SOL_SOCKET,
                libc::SO_PEERCRED,
                (&mut credentials as *mut libc::ucred).cast(),
                &mut length,
            )
        })?;
        if length as usize != std::mem::size_of_val(&credentials)
            || credentials.pid <= 1
            || credentials.uid != 0
            || credentials.gid != 0
        {
            return Err(invalid(
                "instance factory peer is not an original privileged process",
            ));
        }
        let mut raw = -1;
        let mut length = std::mem::size_of::<i32>() as libc::socklen_t;
        const SO_PEERPIDFD: i32 = 77;
        cv(unsafe {
            libc::getsockopt(
                socket.as_raw_fd(),
                libc::SOL_SOCKET,
                SO_PEERPIDFD,
                (&mut raw as *mut i32).cast(),
                &mut length,
            )
        })?;
        if raw < 0 {
            return Err(invalid("kernel did not return the original peer PIDFD"));
        }
        let pidfd = unsafe { File::from_raw_fd(raw) };
        if length as usize != std::mem::size_of::<i32>() {
            return Err(invalid("invalid native peer PIDFD size"));
        }
        let result = Self {
            pid: credentials.pid as u32,
            pidfd,
            selinux,
            apparmor,
        };
        result.revalidate()?;
        Ok(result)
    }
    fn revalidate(&self) -> io::Result<()> {
        if ended(&self.pidfd)? {
            return Err(invalid("the original instance-factory peer exited"));
        }
        let mut info = String::new();
        File::open(format!("/proc/self/fdinfo/{}", self.pidfd.as_raw_fd()))?
            .take(4096)
            .read_to_string(&mut info)?;
        if !info
            .lines()
            .any(|line| line == format!("Pid:\t{}", self.pid))
        {
            return Err(invalid(
                "native peer PIDFD no longer identifies the authenticated process",
            ));
        }
        if self.selinux == FACTORY_SELINUX {
            // This boot-born process executed before policy activation and has
            // never changed its initial-userns credentials or executed again.
            let own = File::open("/proc/self/exe")?;
            let actual = File::open(format!("/proc/{}/exe", self.pid))?;
            if identity(&own)? != identity(&actual)? {
                return Err(invalid(
                    "factory peer does not execute the published manager",
                ));
            }
        }
        // The ordinary launcher may be nondumpable after its MAC transition.
        // The factory also requires its native systemd MainPID/invocation and
        // exact fixed ExecStart before creating a generation.
        for (lsm, expected) in [("selinux", self.selinux), ("apparmor", self.apparmor)] {
            if std::fs::read_to_string(format!("/proc/{}/attr/{lsm}/current", self.pid))?
                .trim_end_matches(['\n', '\0'])
                != expected
            {
                return Err(invalid(
                    "instance-factory peer has a different enforced MAC role",
                ));
            }
        }
        if ended(&self.pidfd)? {
            return Err(invalid("original peer exited during revalidation"));
        }
        Ok(())
    }
}
pub(super) struct RemoteChild {
    pub pidfd: File,
    socket: File,
    peer: Peer,
}
impl RemoteChild {
    pub fn connect() -> io::Result<Self> {
        let node = std::fs::symlink_metadata(SOCKET)?;
        if !node.file_type().is_socket()
            || node.uid() != 0
            || node.gid() != 0
            || node.mode() & 0o7777 != 0o600
        {
            return Err(invalid(
                "boot instance-factory socket is not its root-owned private endpoint",
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
        send(&channel, START, &[])?;
        let Some((tag, mut fds)) = receive(&channel, Duration::from_secs(230))? else {
            return Err(invalid(
                "boot instance factory did not create the original namespace tree",
            ));
        };
        if &tag != BIRTH || fds.len() != 1 {
            return Err(invalid("factory did not return one original birth PIDFD"));
        }
        let pidfd = fds.remove(0);
        if ended(&pidfd)? || identity(&pidfd)? != named_identity(&Path::new(HANDOFF).join("pidfd"))?
        {
            return Err(invalid(
                "received birth PIDFD is not the live published original child",
            ));
        }
        let value = Self {
            pidfd,
            socket: channel,
            peer,
        };
        value.revalidate()?;
        Ok(value)
    }
    pub fn revalidate(&self) -> io::Result<()> {
        check_fs(&self.pidfd, 0x50494446)?;
        self.peer.revalidate()
    }
    pub fn retire(self) -> io::Result<()> {
        if !ended(&self.pidfd)? {
            return Err(invalid(
                "factory completion requires original Android PIDFD death",
            ));
        }
        let end = Instant::now() + Duration::from_secs(25);
        loop {
            self.revalidate()?;
            if let Some((tag, fds)) = receive(&self.socket, Duration::from_millis(100))? {
                if &tag != DONE || !fds.is_empty() {
                    return Err(invalid("original factory could not retire this generation"));
                }
                for name in [
                    "generation.json",
                    "resources.json",
                    "pidfd",
                    "pidns",
                    "mntns",
                    "userns",
                    "cgroupns-creation",
                    "release",
                ] {
                    match std::fs::symlink_metadata(Path::new(HANDOFF).join(name)) {
                        Err(e) if e.kind() == io::ErrorKind::NotFound => {}
                        Err(e) => return Err(e),
                        Ok(_) => {
                            return Err(invalid(
                                "factory left an original generation handoff object",
                            ));
                        }
                    }
                }
                return Ok(());
            }
            if Instant::now() >= end {
                return Err(invalid("original factory retirement exceeded its deadline"));
            }
        }
    }
}
/// Observation-only client channel to the original boot factory. SO_PEERPIDFD
/// is created in the caller's context, not received as a kernel-origin file.
pub(crate) struct QueryEndpoint {
    channel: File,
    peer: boot_identity::Observation,
}
impl QueryEndpoint {
    pub(crate) fn connect() -> io::Result<Self> {
        let node = std::fs::symlink_metadata(SOCKET)?;
        if !node.file_type().is_socket()
            || node.uid() != 0
            || node.gid() != 0
            || node.mode() & 0o7777 != 0o600
        {
            return Err(invalid(
                "query factory endpoint is not the private boot socket",
            ));
        }
        for (lsm, expected) in [
            ("selinux", "u:r:droidloom_broker:s0"),
            ("apparmor", "droidloom-production-broker (enforce)"),
        ] {
            if std::fs::read_to_string(format!("/proc/self/attr/{lsm}/current"))?
                .trim_end_matches(['\n', '\0'])
                != expected
            {
                return Err(invalid("query factory client is not the original broker"));
            }
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
        let peer = boot_identity::Observation::acquire(&channel)?;
        Ok(Self { channel, peer })
    }
    pub(crate) fn channel(&self) -> &File {
        &self.channel
    }
    pub(crate) fn pidfd(&self) -> &File {
        &self.peer.pidfd
    }
    pub(crate) fn pid(&self) -> u32 {
        self.peer.pid
    }
    pub(crate) fn revalidate(&self) -> io::Result<()> {
        self.peer.revalidate(&self.channel)
    }
}

struct Listener {
    socket: File,
    node: (u64, u64),
}
impl Drop for Listener {
    fn drop(&mut self) {
        if named_identity(Path::new(SOCKET)).ok() == Some(self.node) {
            let _ = std::fs::remove_file(SOCKET);
        }
    }
}
impl Listener {
    fn bind() -> io::Result<Self> {
        unsafe {
            libc::umask(0o077);
        }
        let socket = socket()?;
        let (name, length) = address();
        cv(unsafe {
            libc::bind(
                socket.as_raw_fd(),
                (&name as *const libc::sockaddr_un).cast(),
                length,
            )
        })?;
        let original = named_identity(Path::new(SOCKET))?;
        std::fs::set_permissions(SOCKET, std::fs::Permissions::from_mode(0o600))?;
        let metadata = std::fs::symlink_metadata(SOCKET)?;
        if !metadata.file_type().is_socket()
            || metadata.uid() != 0
            || metadata.gid() != 0
            || metadata.nlink() != 1
            || metadata.mode() & 0o7777 != 0o600
            || named_identity(Path::new(SOCKET))? != original
        {
            return Err(invalid(
                "factory endpoint changed while setting its private mode",
            ));
        }
        cv(unsafe { libc::listen(socket.as_raw_fd(), 4) })?;
        Ok(Self {
            node: named_identity(Path::new(SOCKET))?,
            socket,
        })
    }
    fn accept(&self) -> io::Result<Option<File>> {
        if !wait(&self.socket, libc::POLLIN, Duration::from_millis(100))? {
            return Ok(None);
        }
        let fd = unsafe {
            libc::accept4(
                self.socket.as_raw_fd(),
                std::ptr::null_mut(),
                std::ptr::null_mut(),
                libc::SOCK_CLOEXEC | libc::SOCK_NONBLOCK,
            )
        };
        cv(fd)?;
        Ok(Some(unsafe { File::from_raw_fd(fd) }))
    }
}
fn serve_generation(
    channel: &File,
    peer: Peer,
    listener: &Listener,
    adoption: &adoption::Adoption,
) -> io::Result<()> {
    adoption.revalidate()?;
    cv(unsafe { droidloom_factory_context() })?;
    let configuration = ConfigurationReadGuard::acquire()?;
    let Some((choice, cell, base)) =
        intake(UbuntuRoot::AfterSwitchRoot).map_err(io::Error::other)?
    else {
        return Err(invalid(
            "boot factory requires the selected immutable shared-kernel release",
        ));
    };
    let plan = Plan {
        selection_sha256: digest(&choice.sha256)?,
        base_cohort_sha256: digest(&base)?,
        host_uid: cell.host_uid,
        uid_start: cell.subordinate_uids.start,
        uid_count: cell.subordinate_uids.count,
        gid_start: cell.subordinate_gids.start,
        gid_count: cell.subordinate_gids.count,
    };
    let manager = manager::Manager::acquire()?;
    let launcher = manager.verify_launcher_pid(peer.pid)?;
    peer.revalidate()?;
    adoption.revalidate()?;
    let child = Child::spawn(&plan)?;
    send(channel, BIRTH, &[&child.pidfd])?;
    let begin = Instant::now();
    let mut owner: Option<([u8; 16], u32, File)> = None;
    let mut original_init_placed = false;
    loop {
        cv(unsafe { droidloom_factory_context() })?;
        configuration.revalidate()?;
        choice.revalidate().map_err(io::Error::other)?;
        child.revalidate()?;
        let state = manager.owner()?;
        if let Some((id, pid, process)) = &owner {
            if state.clean_exit(id, *pid)? {
                if !ended(process)? {
                    return Err(invalid(
                        "original resource owner remains live after its reported exit",
                    ));
                }
                let observer = manager.observer()?;
                if observer.state == "inactive" && observer.main_pid == 0 {
                    if observer.exec_pid > 1
                        && (observer.code != 1
                            || observer.status != 0
                            || observer.result != "success")
                    {
                        return Err(invalid("original observer did not stop normally"));
                    }
                    child.retire()?;
                    // Retirement is complete even if its original client died.
                    // A lost response never creates a successful client result.
                    let _ = send(channel, DONE, &[]);
                    return Ok(());
                }
                if observer.state == "failed" {
                    return Err(invalid("original observer failed to retire"));
                }
            }
        } else if state.live() {
            peer.revalidate()?;
            if manager.verify_launcher_pid(peer.pid)? != launcher {
                return Err(invalid(
                    "authorized launcher invocation changed before resource ownership",
                ));
            }
            let process = original_process(state.main_pid)?;
            let again = manager.owner()?;
            if state.invocation != again.invocation || state.main_pid != again.main_pid {
                return Err(invalid(
                    "original resource owner changed during factory admission",
                ));
            }
            owner = Some((state.invocation, state.main_pid, process));
        } else if begin.elapsed() > Duration::from_secs(240) || state.state == "failed" {
            return Err(invalid(
                "authorized instance never acquired its original resource owner",
            ));
        }
        if let Some((owner_id, owner_pid, owner_process)) = &owner {
            if let Some(query_channel) = listener.accept()? {
                let Ok(query_peer) = Peer::acquire(
                    &query_channel,
                    "u:r:droidloom_broker:s0",
                    "droidloom-production-broker (enforce)",
                ) else {
                    continue;
                };
                if query_peer.pid != *owner_pid
                    || identity(&query_peer.pidfd)? != identity(owner_process)?
                {
                    continue;
                }
                let validate = || -> io::Result<()> {
                    adoption.revalidate()?;
                    cv(unsafe { droidloom_factory_context() })?;
                    query_peer.revalidate()?;
                    child.revalidate()?;
                    let current = manager.owner()?;
                    if !current.live()
                        || current.invocation != *owner_id
                        || current.main_pid != *owner_pid
                    {
                        return Err(invalid("original query resource owner changed"));
                    }
                    let mut stop = [0u8; 1];
                    child.stop.read_exact_at(&mut stop, 0)?;
                    if stop != [b'0'] {
                        return Err(invalid("original Android shutdown has begun"));
                    }
                    Ok(())
                };
                let placement_request = match placement::requested(&query_channel) {
                    Ok(value) => value,
                    Err(error) => {
                        eprintln!("fixed factory operation rejected before birth: {error}");
                        continue;
                    }
                };
                if placement_request {
                    if original_init_placed {
                        let _ = send(&query_channel, FAILED, &[]);
                        continue;
                    }
                    match placement::serve(&query_channel, &child, &validate) {
                        Ok(()) => original_init_placed = true,
                        Err(error) if error.fatal() => {
                            return Err(io::Error::other(error.to_string()));
                        }
                        Err(error) => eprintln!("{error}"),
                    }
                    continue;
                }
                if !original_init_placed {
                    let _ = send(&query_channel, FAILED, &[]);
                    continue;
                }
                let authority = crate::production_application::factory_query::FactoryAuthority {
                    init: &child.pidfd,
                    owner: owner_process,
                    pid_namespace: &child.pins[0].object,
                    mount_namespace: &child.pins[1].object,
                    user_namespace: &child.pins[2].object,
                    root_uid: plan.uid_start,
                    root_gid: plan.gid_start,
                    validate: &validate,
                };
                match crate::production_application::factory_query::serve(&query_channel, authority)
                {
                    Err(crate::production_application::ApplicationError::RetirementUnproven) => {
                        return Err(invalid("original factory query retirement is unproven"));
                    }
                    // No-child rejection, cancellation and actual reaped failures
                    // cannot kill the boot factory during an orderly Android stop.
                    Err(error) => eprintln!("fixed factory query rejected: {error}"),
                    Ok(()) => {}
                }
            }
        } else {
            std::thread::sleep(Duration::from_millis(100));
        }
    }
}
/// Serve fresh original namespace generations from the boot's kernel lineage.
/// Only board PID 1 can create this role; ordinary service units cannot enter it.
pub fn run_instance_factory(shutdown: &AtomicBool) -> io::Result<()> {
    let selected = SharedKernelLauncher::read()?
        .ok_or_else(|| invalid("public selected release is absent"))?;
    if !selected.entry_program()?.matches_current_process()? {
        return Err(invalid(
            "boot factory does not execute the published original manager",
        ));
    }
    cv(unsafe { droidloom_factory_prepare() })?;
    cv(unsafe { droidloom_factory_device_directory() })?;
    let publication = boot_identity::Publication::publish()?;
    let listener = Listener::bind()?;
    // The one byte goes only to the original board PID 1's inherited pipe.
    std::io::stdout().write_all(b"F")?;
    // Keep all three standard descriptor numbers occupied before native clone.
    // Reopening a birth handle as fd 1 would otherwise collide with init's close.
    let sink = std::fs::OpenOptions::new()
        .write(true)
        .custom_flags(libc::O_CLOEXEC | libc::O_NOFOLLOW)
        .open("/dev/null")?;
    let metadata = sink.metadata()?;
    if !metadata.file_type().is_char_device() || metadata.rdev() != libc::makedev(1, 3) {
        return Err(invalid(
            "factory standard output is not the original null device",
        ));
    }
    cv(unsafe { libc::dup2(sink.as_raw_fd(), libc::STDOUT_FILENO) })?;
    drop(sink);
    let mut adoption = None;
    while !shutdown.load(Ordering::Relaxed) {
        publication.revalidate()?;
        let Some(channel) = listener.accept()? else {
            continue;
        };
        let peer = match Peer::acquire(&channel, CLIENT_SELINUX, CLIENT_APPARMOR) {
            Ok(peer) => peer,
            Err(_) => continue,
        };
        let Ok(Some((tag, fds))) = receive(&channel, Duration::from_secs(5)) else {
            continue;
        };
        if adoption::Adoption::request(&tag) {
            if adoption.is_some() || fds.len() != 1 {
                let _ = send(&channel, FAILED, &[]);
                continue;
            }
            let descriptor = fds.into_iter().next().unwrap();
            adoption = Some(adoption::Adoption::accept(&channel, &peer, descriptor)?);
            continue;
        }
        if &tag != START || !fds.is_empty() {
            continue;
        }
        let Some(adopted) = &adoption else {
            let _ = send(&channel, FAILED, &[]);
            continue;
        };
        if let Err(error) = serve_generation(&channel, peer, &listener, adopted) {
            let _ = send(&channel, FAILED, &[]);
            // Published original pins remain a closed slot on failure; a failed
            // generation is never silently replaced with a new one.
            return Err(error);
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    fn pair() -> (File, File) {
        let mut fds = [-1; 2];
        cv(unsafe {
            libc::socketpair(
                libc::AF_UNIX,
                libc::SOCK_SEQPACKET | libc::SOCK_CLOEXEC,
                0,
                fds.as_mut_ptr(),
            )
        })
        .unwrap();
        (unsafe { File::from_raw_fd(fds[0]) }, unsafe {
            File::from_raw_fd(fds[1])
        })
    }
    fn self_pidfd() -> File {
        let fd = unsafe { libc::syscall(libc::SYS_pidfd_open, libc::getpid(), 0) };
        assert!(fd >= 0, "{}", io::Error::last_os_error());
        unsafe { File::from_raw_fd(fd as i32) }
    }
    #[test]
    fn native_birth_packet_preserves_original_pidfd_and_cloexec() {
        let (a, b) = pair();
        let original = self_pidfd();
        send(&a, BIRTH, &[&original]).unwrap();
        let (tag, received) = receive(&b, Duration::from_secs(1)).unwrap().unwrap();
        assert_eq!(&tag, BIRTH);
        assert_eq!(received.len(), 1);
        assert_eq!(
            identity(&received[0]).unwrap(),
            identity(&original).unwrap()
        );
        assert!(!ended(&received[0]).unwrap());
        assert_ne!(
            unsafe { libc::fcntl(received[0].as_raw_fd(), libc::F_GETFD) } & libc::FD_CLOEXEC,
            0
        );
    }
    #[test]
    fn native_peer_pidfd_identifies_the_original_socket_creator() {
        let (a, _b) = pair();
        let mut raw = -1i32;
        let mut length = std::mem::size_of::<i32>() as libc::socklen_t;
        cv(unsafe {
            libc::getsockopt(
                a.as_raw_fd(),
                libc::SOL_SOCKET,
                77,
                (&mut raw as *mut i32).cast(),
                &mut length,
            )
        })
        .unwrap();
        assert_eq!(length as usize, std::mem::size_of::<i32>());
        assert!(raw >= 0);
        let held = unsafe { File::from_raw_fd(raw) };
        assert_eq!(identity(&held).unwrap(), identity(&self_pidfd()).unwrap());
        assert!(!ended(&held).unwrap());
        assert!(
            Peer::acquire(&a, CLIENT_SELINUX, CLIENT_APPARMOR).is_err(),
            "an ordinary host test process cannot impersonate the production launcher"
        );
    }
    #[test]
    fn closed_or_truncated_native_packets_do_not_complete_a_generation() {
        let (a, b) = pair();
        assert_eq!(
            unsafe {
                libc::send(
                    a.as_raw_fd(),
                    b"DLDONE01!".as_ptr().cast(),
                    9,
                    libc::MSG_NOSIGNAL,
                )
            },
            9
        );
        assert!(receive(&b, Duration::from_secs(1)).is_err());
        drop(a);
        assert!(receive(&b, Duration::from_secs(1)).is_err());
    }
    #[test]
    fn extra_native_rights_are_rejected_and_closed() {
        // A private table makes the leak check independent of parallel tests.
        cv(unsafe { libc::unshare(libc::CLONE_FILES) }).unwrap();
        let (a, b) = pair();
        let first = self_pidfd();
        let second = self_pidfd();
        let before = std::fs::read_dir("/proc/thread-self/fd").unwrap().count();
        let fds = [first.as_raw_fd(), second.as_raw_fd()];
        let mut io = libc::iovec {
            iov_base: BIRTH.as_ptr().cast_mut().cast(),
            iov_len: 8,
        };
        let mut control = [0usize; 16];
        let mut packet = unsafe { std::mem::zeroed::<libc::msghdr>() };
        packet.msg_iov = &mut io;
        packet.msg_iovlen = 1;
        packet.msg_control = control.as_mut_ptr().cast();
        packet.msg_controllen =
            unsafe { libc::CMSG_SPACE(std::mem::size_of_val(&fds) as u32) } as usize;
        unsafe {
            let header = libc::CMSG_FIRSTHDR(&packet);
            (*header).cmsg_level = libc::SOL_SOCKET;
            (*header).cmsg_type = libc::SCM_RIGHTS;
            (*header).cmsg_len = libc::CMSG_LEN(std::mem::size_of_val(&fds) as u32) as usize;
            std::ptr::copy_nonoverlapping(
                fds.as_ptr().cast::<u8>(),
                libc::CMSG_DATA(header),
                std::mem::size_of_val(&fds),
            );
            assert_eq!(libc::sendmsg(a.as_raw_fd(), &packet, libc::MSG_NOSIGNAL), 8);
        }
        assert!(receive(&b, Duration::from_secs(1)).is_err());
        assert_eq!(
            std::fs::read_dir("/proc/thread-self/fd").unwrap().count(),
            before
        );
    }
}
