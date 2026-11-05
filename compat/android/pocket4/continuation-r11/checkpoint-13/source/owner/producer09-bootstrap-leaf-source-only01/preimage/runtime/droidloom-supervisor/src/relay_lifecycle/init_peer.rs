//! Private supervisor-to-real-init handshake. A HELLO is a claim to verify;
//! all kernel identity, role, filesystem and budget evidence is held and checked.
use super::capability::{Artifact, Process};
use super::domain::{self, Domain, Identity};
use super::policy::{self, PressureRelaySpec, digest};
use droidloom_pressure_relay::{BootstrapState, BootstrapStatus, Budget};
use std::fs::File;
use std::io;
use std::mem::{size_of, zeroed};
use std::os::fd::{AsRawFd, FromRawFd, RawFd};
use std::os::unix::fs::{FileTypeExt, MetadataExt};
use std::time::{Duration, Instant};

pub(crate) const CONTROL_FD: i32 = 198;
pub(crate) const DOMAIN_FD: i32 = 199;
pub(crate) const OWNER_FD: i32 = 200;
pub(crate) const ENTRY_FD: i32 = 201;
pub(crate) const LIBRARY: &str = "/droidloom/lmkd-bootstrap/libdroidloom_init_relay.so";
pub(crate) const LMKD: &str = "/droidloom/lmkd-bootstrap/lmkd";
pub(crate) const ENDPOINT: &str = "droidloom-lmkd-psi";
// ABI 2 PROJECT owns one detached mount cloned by the current source-namespace
// owner. A raw foreign O_PATH descriptor is no longer a projection capability.
pub(crate) const INIT_ABI_TEXT: &str = "2";
const INIT_ABI: u32 = 2;
#[cfg(target_arch = "x86_64")]
pub(crate) const COMPAT: &str = "/system/lib64/libclang_rt.asan-x86_64-android.so";
#[cfg(target_arch = "aarch64")]
pub(crate) const COMPAT: &str = "/system/lib64/bootstrap/libclang_rt.hwasan-aarch64-android.so";
const WIRE: usize = 128;
const HELLO: u32 = 1;
const PROJECT: u32 = 2;
const PROJECTED: u32 = 3;
const COMMIT: u32 = 4;
const DONE: u32 = 5;
fn error(message: &'static str) -> io::Error {
    domain::error(message)
}
pub(crate) fn preload() -> String {
    format!("{LIBRARY}:{COMPAT}")
}
fn number(wire: &[u8; WIRE], offset: usize, width: usize) -> u64 {
    let mut bytes = [0; 8];
    bytes[..width].copy_from_slice(&wire[offset..offset + width]);
    u64::from_le_bytes(bytes)
}
fn put(wire: &mut [u8; WIRE], offset: usize, value: u64, width: usize) {
    wire[offset..offset + width].copy_from_slice(&value.to_le_bytes()[..width]);
}
fn frame(kind: u32, nonce: &[u8; 32]) -> [u8; WIRE] {
    let mut wire = [0; WIRE];
    wire[..8].copy_from_slice(b"P4IBV2!!");
    put(&mut wire, 8, INIT_ABI as u64, 4);
    put(&mut wire, 12, kind as u64, 4);
    wire[16..48].copy_from_slice(nonce);
    wire
}
fn require_frame(wire: &[u8; WIRE], kind: u32, nonce: &[u8; 32]) -> io::Result<()> {
    if nonce == &[0; 32] || wire[..48] != frame(kind, nonce)[..48] {
        return Err(error("init protocol ABI/kind/nonce differs"));
    }
    Ok(())
}
fn detached_endpoint(endpoint: &File) -> io::Result<File> {
    let original = endpoint.metadata()?;
    let flags = unsafe { libc::fcntl(endpoint.as_raw_fd(), libc::F_GETFL) };
    let descriptor = unsafe { libc::fcntl(endpoint.as_raw_fd(), libc::F_GETFD) };
    if !original.file_type().is_socket()
        || flags < 0 || flags & libc::O_PATH == 0
        || descriptor < 0 || descriptor & libc::FD_CLOEXEC == 0
    {
        return Err(error("source endpoint is not a sealed O_PATH socket"));
    }
    // The caller has just validated the original HostContext and READY. The
    // endpoint was opened in that same namespace, not received from init.
    // OPEN_TREE_CLONE creates an owned anonymous mount; closing the last FD
    // after any failure releases it. No path reopen or foreign-FD fallback.
    const OPEN_TREE_CLONE: libc::c_uint = 1;
    let raw = unsafe {
        libc::syscall(
            libc::SYS_open_tree,
            endpoint.as_raw_fd(),
            c"".as_ptr(),
            OPEN_TREE_CLONE | libc::AT_EMPTY_PATH as libc::c_uint
                | libc::O_CLOEXEC as libc::c_uint,
        )
    };
    if raw < 0 { return Err(io::Error::last_os_error()); }
    // SAFETY: open_tree returned a new owned descriptor.
    let detached = unsafe { File::from_raw_fd(raw as RawFd) };
    let cloned = detached.metadata()?;
    let flags = unsafe { libc::fcntl(detached.as_raw_fd(), libc::F_GETFL) };
    let descriptor = unsafe { libc::fcntl(detached.as_raw_fd(), libc::F_GETFD) };
    if !cloned.file_type().is_socket()
        || cloned.dev() != original.dev() || cloned.ino() != original.ino()
        || cloned.uid() != original.uid() || cloned.gid() != original.gid()
        || cloned.mode() != original.mode()
        || flags < 0 || flags & libc::O_PATH == 0
        || descriptor < 0 || descriptor & libc::FD_CLOEXEC == 0
    {
        return Err(error("detached endpoint identity or sealing differs"));
    }
    Ok(detached)
}
pub(crate) fn pair() -> io::Result<(File, File)> {
    let mut fds = [-1; 2];
    if unsafe {
        libc::socketpair(
            libc::AF_UNIX,
            libc::SOCK_SEQPACKET | libc::SOCK_CLOEXEC | libc::SOCK_NONBLOCK,
            0,
            fds.as_mut_ptr(),
        )
    } != 0
    {
        return Err(io::Error::last_os_error());
    }
    // SAFETY: socketpair returned two distinct owned descriptors.
    let host = unsafe { File::from_raw_fd(fds[0]) };
    let child = unsafe { File::from_raw_fd(fds[1]) };
    let on: libc::c_int = 1;
    if unsafe {
        libc::setsockopt(
            host.as_raw_fd(),
            libc::SOL_SOCKET,
            libc::SO_PASSCRED,
            (&on as *const libc::c_int).cast(),
            size_of::<libc::c_int>() as libc::socklen_t,
        )
    } != 0
    {
        return Err(io::Error::last_os_error());
    }
    Ok((host, child))
}
#[repr(C, align(16))]
struct Ancillary([u8; 512]);
struct Packet {
    wire: [u8; WIRE],
    rights: Vec<File>,
    credential: libc::ucred,
}
fn receive_packet(fd: RawFd) -> io::Result<Packet> {
    let mut wire = [0; WIRE];
    let mut control = Ancillary([0; 512]);
    let mut vector = libc::iovec {
        iov_base: wire.as_mut_ptr().cast(),
        iov_len: WIRE,
    };
    let mut message: libc::msghdr = unsafe { zeroed() };
    message.msg_iov = &mut vector;
    message.msg_iovlen = 1;
    message.msg_control = control.0.as_mut_ptr().cast();
    message.msg_controllen = control.0.len();
    let count = unsafe {
        libc::recvmsg(
            fd,
            &mut message,
            libc::MSG_DONTWAIT | libc::MSG_CMSG_CLOEXEC | libc::MSG_TRUNC,
        )
    };
    if count < 0 {
        return Err(io::Error::last_os_error());
    }
    let mut rights = Vec::new();
    let mut credentials = Vec::new();
    let mut malformed = false;
    // Every delivered descriptor becomes owned before any framing error can
    // return. MSG_CTRUNC is rejected after the delivered subset is adopted.
    let mut header = unsafe { libc::CMSG_FIRSTHDR(&message) };
    while !header.is_null() {
        let minimum = unsafe { libc::CMSG_LEN(0) } as usize;
        let h = unsafe { &*header };
        if h.cmsg_len < minimum {
            malformed = true;
            break;
        }
        let bytes = h.cmsg_len - minimum;
        let data = unsafe { libc::CMSG_DATA(header) };
        if (data as usize)
            .checked_add(bytes)
            .is_none_or(|end| end > control.0.as_ptr() as usize + message.msg_controllen)
        {
            malformed = true;
            break;
        }
        if h.cmsg_level == libc::SOL_SOCKET && h.cmsg_type == libc::SCM_RIGHTS {
            if bytes == 0 || bytes % size_of::<RawFd>() != 0 {
                malformed = true;
            }
            for index in 0..bytes / size_of::<RawFd>() {
                let raw = unsafe {
                    std::ptr::read_unaligned(data.add(index * size_of::<RawFd>()).cast::<RawFd>())
                };
                if raw < 0 {
                    malformed = true;
                    continue;
                }
                // SAFETY: each kernel-delivered SCM_RIGHTS number is fresh.
                rights.push(unsafe { File::from_raw_fd(raw) });
            }
        } else if h.cmsg_level == libc::SOL_SOCKET
            && h.cmsg_type == libc::SCM_CREDENTIALS
            && bytes == size_of::<libc::ucred>()
        {
            credentials.push(unsafe { std::ptr::read_unaligned(data.cast::<libc::ucred>()) });
        } else {
            malformed = true;
        }
        header = unsafe { libc::CMSG_NXTHDR(&message, header) };
    }
    if count != WIRE as isize
        || message.msg_flags & (libc::MSG_TRUNC | libc::MSG_CTRUNC) != 0
        || malformed
        || rights.len() > 16
        || credentials.len() != 1
    {
        return Err(error(
            "init message size/ancillary credentials/rights differ",
        ));
    }
    for fd in &rights {
        let flags = unsafe { libc::fcntl(fd.as_raw_fd(), libc::F_GETFD) };
        if flags < 0 || flags & libc::FD_CLOEXEC == 0 {
            return Err(error("received init capability is not CLOEXEC"));
        }
    }
    Ok(Packet {
        wire,
        rights,
        credential: credentials.remove(0),
    })
}
fn send_packet(fd: RawFd, wire: &[u8; WIRE], right: Option<&File>) -> io::Result<()> {
    let mut control = Ancillary([0; 512]);
    let mut vector = libc::iovec {
        iov_base: wire.as_ptr() as *mut libc::c_void,
        iov_len: WIRE,
    };
    let mut message: libc::msghdr = unsafe { zeroed() };
    message.msg_iov = &mut vector;
    message.msg_iovlen = 1;
    if let Some(file) = right {
        message.msg_control = control.0.as_mut_ptr().cast();
        message.msg_controllen = unsafe { libc::CMSG_SPACE(size_of::<RawFd>() as u32) } as usize;
        let header = unsafe { libc::CMSG_FIRSTHDR(&message) };
        unsafe {
            (*header).cmsg_level = libc::SOL_SOCKET;
            (*header).cmsg_type = libc::SCM_RIGHTS;
            (*header).cmsg_len = libc::CMSG_LEN(size_of::<RawFd>() as u32) as usize;
            std::ptr::write_unaligned(libc::CMSG_DATA(header).cast::<RawFd>(), file.as_raw_fd());
        }
    }
    let sent = unsafe { libc::sendmsg(fd, &message, libc::MSG_NOSIGNAL | libc::MSG_DONTWAIT) };
    if sent < 0 {
        return Err(io::Error::last_os_error());
    }
    if sent != WIRE as isize {
        return Err(error("short init seqpacket send"));
    }
    Ok(())
}
struct Wait<'a> {
    socket: RawFd,
    owner: &'a Process,
    init: Option<&'a Process>,
    cancel: &'a File,
    deadline: Instant,
}
impl Wait<'_> {
    fn ready(&self, events: i16, terminal: bool) -> io::Result<()> {
        loop {
            self.owner.live()?;
            if let Some(init) = self.init {
                init.live()?;
            }
            let now = Instant::now();
            if now >= self.deadline {
                return Err(error("init barrier deadline expired"));
            }
            let mut polls = [
                libc::pollfd {
                    fd: self.socket,
                    events,
                    revents: 0,
                },
                libc::pollfd {
                    fd: self.owner.fd().as_raw_fd(),
                    events: libc::POLLIN,
                    revents: 0,
                },
                libc::pollfd {
                    fd: self.init.map_or(-1, |p| p.fd().as_raw_fd()),
                    events: libc::POLLIN,
                    revents: 0,
                },
                libc::pollfd {
                    fd: self.cancel.as_raw_fd(),
                    events: libc::POLLIN,
                    revents: 0,
                },
            ];
            let timeout = i32::try_from(
                self.deadline
                    .saturating_duration_since(now)
                    .as_millis()
                    .max(1),
            )
            .unwrap_or(i32::MAX);
            let count =
                unsafe { libc::poll(polls.as_mut_ptr(), polls.len() as libc::nfds_t, timeout) };
            if count < 0 {
                let e = io::Error::last_os_error();
                if e.kind() == io::ErrorKind::Interrupted {
                    continue;
                }
                return Err(e);
            }
            // Retirement wins a batch even if a valid init packet is waiting.
            if polls[1..].iter().any(|p| p.revents != 0) {
                return Err(error("init barrier owner/init/cancellation changed"));
            }
            let flags = polls[0].revents;
            if flags & (libc::POLLERR | libc::POLLNVAL) != 0 {
                return Err(error("init barrier channel fault"));
            }
            let hup = flags & (libc::POLLHUP | libc::POLLRDHUP) != 0;
            if hup && !(terminal && flags & libc::POLLIN != 0) {
                return Err(error("init barrier closed before complete DONE"));
            }
            if flags & events != 0 {
                return Ok(());
            }
        }
    }
    fn receive(&self, terminal: bool) -> io::Result<Packet> {
        loop {
            self.ready(libc::POLLIN | libc::POLLRDHUP, terminal)?;
            match receive_packet(self.socket) {
                Err(e)
                    if e.kind() == io::ErrorKind::WouldBlock
                        || e.kind() == io::ErrorKind::Interrupted =>
                {
                    continue;
                }
                result => return result,
            }
        }
    }
    fn send(
        &self,
        wire: &[u8; WIRE],
        right: Option<&File>,
        before_send: &mut dyn FnMut() -> io::Result<()>,
    ) -> io::Result<()> {
        loop {
            self.ready(libc::POLLOUT | libc::POLLRDHUP, false)?;
            before_send()?;
            match send_packet(self.socket, wire, right) {
                Err(e)
                    if e.kind() == io::ErrorKind::WouldBlock
                        || e.kind() == io::ErrorKind::Interrupted =>
                {
                    continue;
                }
                result => return result,
            }
        }
    }
}
#[derive(Clone, Copy, Eq, PartialEq)]
enum Phase {
    Fresh,
    Hello,
    Done,
    Poisoned,
}
pub(crate) struct InitPeer {
    socket: Option<File>,
    nonce: [u8; 32],
    phase: Phase,
    entry_deadline: Instant,
    handshake: Duration,
}
pub(crate) struct Hello {
    pub process: Process,
    pub namespaces: Vec<File>,
    pub executable: Artifact,
    pub root: File,
    pub guest_domain: File,
    pub compat: Artifact,
    pub linker: Artifact,
}
impl Hello {
    pub(crate) fn validate(
        &self,
        owner: &Process,
        domain: &Domain,
        barrier: &Artifact,
    ) -> io::Result<()> {
        self.process.validate_init_child(owner)?;
        self.process.validate_namespaces(&self.namespaces)?;
        domain.validate()?;
        let root = self.process.root()?;
        if Identity::of(&root)? != Identity::of(&self.root)? {
            return Err(error("init root changed"));
        }
        let projection =
            domain::beneath(&root, "sys/fs/cgroup", libc::O_RDONLY | libc::O_DIRECTORY)?;
        domain::filesystem(&projection, 0x6367_7270)?;
        if Identity::of(&projection)? != domain.identity()
            || Identity::of(&self.guest_domain)? != domain.identity()
        {
            return Err(error("init cgroup projection changed"));
        }
        self.executable.validate(false)?;
        self.compat.validate(false)?;
        self.linker.validate(false)?;
        barrier.validate(false)?;
        self.process.require_preload(&preload())?;
        self.process.live()
    }
}
impl InitPeer {
    pub(crate) fn new(
        socket: File,
        nonce: [u8; 32],
        policy: &PressureRelaySpec,
    ) -> io::Result<Self> {
        if nonce == [0; 32] {
            return Err(error("zero init barrier nonce"));
        }
        Ok(Self {
            socket: Some(socket),
            nonce,
            phase: Phase::Fresh,
            entry_deadline: Instant::now() + Duration::from_millis(policy.entry_timeout_ms as u64),
            handshake: Duration::from_millis(policy.bootstrap_timeout_ms as u64),
        })
    }
    pub(crate) fn close(&mut self) {
        self.socket = None;
        if self.phase != Phase::Done {
            self.phase = Phase::Poisoned;
        }
    }
    pub(crate) fn accept(
        &mut self,
        owner: &Process,
        domain: &Domain,
        policy: &PressureRelaySpec,
        barrier: &Artifact,
        cancel: &File,
        audit: &super::audit::Audit,
    ) -> io::Result<Hello> {
        if self.phase != Phase::Fresh {
            return Err(error("init HELLO is a single attempt"));
        }
        self.phase = Phase::Poisoned;
        let socket = self
            .socket
            .as_ref()
            .ok_or_else(|| error("init channel missing"))?
            .as_raw_fd();
        let packet = Wait {
            socket,
            owner,
            init: None,
            cancel,
            deadline: self.entry_deadline,
        }
        .receive(false)?;
        require_frame(&packet.wire, HELLO, &self.nonce)?;
        if packet.rights.len() != 12
            || number(&packet.wire, 88, 4) != 12
            || packet.wire[92..].iter().any(|v| *v != 0)
            || packet.credential.uid != 0
            || packet.credential.gid != 0
            || packet.credential.pid <= 0
        {
            return Err(error("init HELLO role/rights/reserved bytes differ"));
        }
        let mut rights = packet.rights.into_iter();
        let guest_domain = rights.next().expect("length checked");
        let process = Process::from_received_pidfd(rights.next().expect("length checked"))?;
        if process.pid() != packet.credential.pid {
            return Err(error("init HELLO sender differs from received pidfd"));
        }
        process.validate_init_child(owner)?;
        let namespaces: Vec<File> = rights.collect();
        process.validate_namespaces(&namespaces)?;
        domain.validate()?;
        domain::filesystem(&guest_domain, 0x6367_7270)?;
        let identity = Identity::of(&guest_domain)?;
        if identity != domain.identity()
            || number(&packet.wire, 48, 8) != identity.device
            || number(&packet.wire, 56, 8) != identity.inode
            || number(&packet.wire, 64, 8) != policy.memory_max_bytes
            || number(&packet.wire, 72, 8) != policy.memory_high_bytes
            || number(&packet.wire, 80, 8) != policy.memory_swap_max_bytes
        {
            return Err(error("init HELLO domain or explicit budget differs"));
        }
        // The broker receives our original host domain descriptor. The guest
        // copy is evidence of the projection, never the source of authority.
        let root = process.root()?;
        let projection =
            domain::beneath(&root, "sys/fs/cgroup", libc::O_RDONLY | libc::O_DIRECTORY)?;
        if Identity::of(&projection)? != domain.identity() {
            return Err(error("actual init root exposes a different cgroup"));
        }
        let executable = Artifact::from_file(
            process.executable()?,
            digest(&policy.init_sha256).map_err(error)?,
            true,
        )?;
        let compat = Artifact::from_file(
            domain::beneath(&root, COMPAT.trim_start_matches('/'), libc::O_RDONLY)?,
            digest(&policy.compat_preload_sha256).map_err(error)?,
            false,
        )?;
        let linker = Artifact::from_file(
            domain::beneath(&root, "system/bin/bootstrap/linker64", libc::O_RDONLY)?,
            digest(&policy.init_linker_sha256).map_err(error)?,
            true,
        )?;
        process.require_preload(&preload())?;
        executable.validate_mapped(&process)?;
        compat.validate_mapped(&process)?;
        linker.validate_mapped(&process)?;
        barrier.validate_mapped(&process)?;
        let hello = Hello {
            process,
            namespaces,
            executable,
            root,
            guest_domain,
            compat,
            linker,
        };
        hello.validate(owner, domain, barrier)?;
        self.entry_deadline = Instant::now() + self.handshake;
        self.phase = Phase::Hello;
        audit.record(super::audit::InitRecord::capture(&hello, &packet.wire)
            .map(|init| super::audit::Event::InitHello { init }));
        Ok(hello)
    }
    pub(crate) fn commit(
        &mut self,
        hello: &Hello,
        owner: &Process,
        domain: &Domain,
        policy: &PressureRelaySpec,
        barrier: &Artifact,
        ready: &BootstrapStatus,
        endpoint: &File,
        cancel: &File,
        broker_gate: &mut dyn FnMut() -> io::Result<()>,
        audit: &super::audit::Audit,
    ) -> io::Result<()> {
        if self.phase != Phase::Hello {
            return Err(error("init projection/COMMIT is a single attempt"));
        }
        self.phase = Phase::Poisoned;
        let expected_budget = Budget {
            maximum: policy.memory_max_bytes,
            high: Some(policy.memory_high_bytes),
            swap_maximum: Some(policy.memory_swap_max_bytes),
        }
        .canonical();
        if ready.state != BootstrapState::Ready
            || ready.nonce != self.nonce
            || ready.faulted
            || ready.granted
            || ready.cgroup.device != domain.identity().device
            || ready.cgroup.inode != domain.identity().inode
            || ready.budget != expected_budget
        {
            return Err(error(
                "broker READY does not bind this exact init/domain/budget",
            ));
        }
        let metadata = endpoint.metadata()?;
        let identity = Identity::of(endpoint)?;
        let flags = unsafe { libc::fcntl(endpoint.as_raw_fd(), libc::F_GETFL) };
        if flags < 0
            || flags & libc::O_PATH == 0
            || !metadata.file_type().is_socket()
            || metadata.uid() != policy.lmkd_uid
            || metadata.gid() != policy.lmkd_gid
            || metadata.mode() & 0o7777 != 0o600
            || ready.endpoint.device != identity.device
            || ready.endpoint.inode != identity.inode
        {
            return Err(error("broker socket capability differs from READY"));
        }
        let mut wire = frame(PROJECT, &self.nonce);
        put(&mut wire, 48, identity.device, 8);
        put(&mut wire, 56, identity.inode, 8);
        put(&mut wire, 64, policy.lmkd_uid as u64, 4);
        put(&mut wire, 68, policy.lmkd_gid as u64, 4);
        put(&mut wire, 72, 0o600, 4);
        let socket = self
            .socket
            .as_ref()
            .ok_or_else(|| error("init channel missing"))?
            .as_raw_fd();
        let wait = Wait {
            socket,
            owner,
            init: Some(&hello.process),
            cancel,
            deadline: self.entry_deadline,
        };
        hello.validate(owner, domain, barrier)?;
        // This gate revalidates the captured process-leader and current worker
        // namespaces before cloning. Wait::send repeats it at actual transfer.
        broker_gate()?;
        let detached = detached_endpoint(endpoint)?;
        wait.send(&wire, Some(&detached), broker_gate)?;
        drop(detached);
        audit.record(Ok(super::audit::Event::InitProjectSent { wire_hex: policy::hex(&wire) }));
        let projected = wait.receive(false)?;
        put(&mut wire, 12, PROJECTED as u64, 4);
        require_exact_peer_packet(&projected, &wire, hello.process.pid())?;
        let mounted = domain::beneath(&hello.root, "dev/socket/droidloom-lmkd-psi", libc::O_PATH)?;
        let mounted_meta = mounted.metadata()?;
        if Identity::of(&mounted)? != identity
            || !mounted_meta.file_type().is_socket()
            || mounted_meta.uid() != policy.lmkd_uid
            || mounted_meta.gid() != policy.lmkd_gid
            || mounted_meta.mode() & 0o7777 != 0o600
        {
            return Err(error(
                "actual init socket projection differs from the permitted inode",
            ));
        }
        hello.validate(owner, domain, barrier)?;
        audit.record(Ok(super::audit::Event::InitProjectedAccepted { wire_hex: policy::hex(&projected.wire) }));
        put(&mut wire, 12, COMMIT as u64, 4);
        wait.send(&wire, None, broker_gate)?;
        audit.record(Ok(super::audit::Event::InitCommitSent { wire_hex: policy::hex(&wire) }));
        let done = wait.receive(true)?;
        put(&mut wire, 12, DONE as u64, 4);
        require_exact_peer_packet(&done, &wire, hello.process.pid())?;
        // DONE may share a poll batch with HUP. It is valid only with exact
        // identity and both real process generations still alive.
        owner.live()?;
        hello.process.live()?;
        domain.validate()?;
        self.phase = Phase::Done;
        self.socket = None;
        audit.record(Ok(super::audit::Event::InitDoneAccepted { wire_hex: policy::hex(&done.wire) }));
        Ok(())
    }
}
fn require_exact_peer_packet(packet: &Packet, expected: &[u8; WIRE], pid: i32) -> io::Result<()> {
    if packet.wire != *expected
        || !packet.rights.is_empty()
        || packet.credential.pid != pid
        || packet.credential.uid != 0
        || packet.credential.gid != 0
    {
        return Err(error(
            "init phase echo/credentials/unexpected rights differ",
        ));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    fn packet_pair() -> (File, File) {
        pair().unwrap()
    }
    #[test]
    fn actual_scm_rights_are_closed_on_invalid_ancillary_or_phase() {
        let (receive, send) = packet_pair();
        let mut pipes = [-1; 2];
        assert_eq!(
            unsafe { libc::pipe2(pipes.as_mut_ptr(), libc::O_CLOEXEC | libc::O_NONBLOCK) },
            0
        );
        let reader = unsafe { File::from_raw_fd(pipes[0]) };
        let writer = unsafe { File::from_raw_fd(pipes[1]) };
        let nonce = [7; 32];
        let mut wire = frame(DONE, &nonce);
        wire[0] = 0;
        send_packet(send.as_raw_fd(), &wire, Some(&writer)).unwrap();
        drop(writer);
        let packet = receive_packet(receive.as_raw_fd()).unwrap();
        assert_eq!(packet.rights.len(), 1);
        assert!(require_frame(&packet.wire, DONE, &nonce).is_err());
        drop(packet);
        let mut item = libc::pollfd {
            fd: reader.as_raw_fd(),
            events: libc::POLLIN,
            revents: 0,
        };
        assert_eq!(unsafe { libc::poll(&mut item, 1, 0) }, 1);
        assert_ne!(item.revents & libc::POLLHUP, 0);
    }
    #[test]
    fn kernel_credentials_are_required_and_terminal_packet_survives_hup() {
        let (receive, send) = packet_pair();
        let wire = frame(DONE, &[9; 32]);
        send_packet(send.as_raw_fd(), &wire, None).unwrap();
        drop(send);
        let packet = receive_packet(receive.as_raw_fd()).unwrap();
        assert_eq!(packet.wire, wire);
        assert_eq!(packet.credential.pid, unsafe { libc::getpid() });
        assert_eq!(packet.credential.uid, unsafe { libc::geteuid() });
        assert!(packet.rights.is_empty());
    }
    #[test]
    fn exact_wire_rejects_old_abi_nonce_and_phase() {
        let nonce = [3; 32];
        let wire = frame(HELLO, &nonce);
        require_frame(&wire, HELLO, &nonce).unwrap();
        assert!(require_frame(&wire, DONE, &nonce).is_err());
        assert!(require_frame(&wire, HELLO, &[4; 32]).is_err());
        for abi in [0, 1] {
            let mut old = wire;
            put(&mut old, 8, abi, 4);
            assert!(require_frame(&old, HELLO, &nonce).is_err());
        }
        let mut old = wire;
        old[..8].copy_from_slice(b"P4IBV1!!");
        assert!(require_frame(&old, HELLO, &nonce).is_err());
        assert_eq!(INIT_ABI_TEXT.parse::<u32>().unwrap(), INIT_ABI);
        assert!(require_frame(&frame(HELLO, &[0; 32]), HELLO, &[0; 32]).is_err());
    }
    #[test]
    fn detached_projection_rejects_non_path_capabilities_before_mount_creation() {
        let file = tempfile::tempfile().unwrap();
        assert_eq!(detached_endpoint(&file).unwrap_err().kind(), io::ErrorKind::Other);
        let (socket, _peer) = std::os::unix::net::UnixStream::pair().unwrap();
        let socket = File::from(std::os::fd::OwnedFd::from(socket));
        assert_eq!(detached_endpoint(&socket).unwrap_err().kind(), io::ErrorKind::Other);
    }
}
