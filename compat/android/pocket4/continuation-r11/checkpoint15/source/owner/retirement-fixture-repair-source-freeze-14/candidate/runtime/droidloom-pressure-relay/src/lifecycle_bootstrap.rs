// Copyright 2026 Droidloom contributors; SPDX-License-Identifier: Apache-2.0
//! Real daemon entry for a trusted supervisor's inherited socketpair.
//!
//! This is NOT the Android enrollment socket. Only the exact root parent may
//! supply the sixteen lifecycle-owned descriptors. No process/path lookup,
//! threshold override, shell command, or Android-supplied authority is accepted.
use super::*;
use std::io::Write;
use std::os::fd::BorrowedFd;

const BOOT_SIZE: usize = 128;
const STATUS_SIZE: usize = 160;
const RETIRE_SIZE: usize = 48;
const RIGHTS: usize = 16;
const NSFS_MAGIC: libc::c_long = 0x6e73_6673;
const NS_GET_NSTYPE: libc::c_ulong = 0xb703;
const BAD: libc::c_short = libc::POLLERR | libc::POLLHUP | libc::POLLRDHUP | libc::POLLNVAL;
const TMPFS_MAGIC: libc::c_long = 0x0102_1994;

// The layout is chosen only by the trusted lifecycle caller. The legacy
// owned fixture and the real ABI3 init barrier have different, explicit
// bootstrap layouts; neither endpoint guesses from a pathname or falls back.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum BootstrapLayout { ProjectedRootV1, HoldingLeafV3 }

fn number(bytes: &[u8], at: usize, width: usize) -> u64 {
    let mut value = [0; 8]; value[..width].copy_from_slice(&bytes[at..at + width]);
    u64::from_le_bytes(value)
}
fn put(bytes: &mut [u8], at: usize, value: u64, width: usize) {
    bytes[at..at + width].copy_from_slice(&value.to_le_bytes()[..width]);
}

/// Trusted image policy and a new per-invocation nonce. FD order is fixed:
/// cgroup root, owner pidfd, init pidfd, LMKD executable, init executable,
/// private endpoint directory, then pid/pid_for_children/mnt/cgroup/user/net/
/// ipc/uts/time/time_for_children namespace FDs. The parent must already hold
/// every descriptor and the corresponding LMKD startup barrier.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct BootstrapSpec {
    pub nonce: [u8; 32],
    pub uid: u32,
    pub gid: u32,
    pub lmkd_sha256: [u8; 32],
    pub init_sha256: [u8; 32],
}
impl BootstrapSpec {
    fn validate(&self) -> Result<()> {
        if self.nonce == [0; 32] || self.lmkd_sha256 == [0; 32] || self.init_sha256 == [0; 32] ||
            self.uid == 0 || self.uid == u32::MAX || self.gid == 0 || self.gid == u32::MAX {
            return Err(Error::Reject("invalid trusted bootstrap nonce/role/image policy"));
        }
        Ok(())
    }
    /// Legacy owned-fixture wire. Real ABI3 init uses the explicitly selected
    /// holding path below and never retries this version after rejection.
    pub fn encode(&self) -> Result<[u8; BOOT_SIZE]> {
        self.encode_with_layout(BootstrapLayout::ProjectedRootV1)
    }
    fn encode_with_layout(&self, layout: BootstrapLayout) -> Result<[u8; BOOT_SIZE]> {
        self.validate()?;
        let mut wire = [0; BOOT_SIZE]; wire[..8].copy_from_slice(b"P4BOOT1!");
        put(&mut wire, 8, 1, 4); put(&mut wire, 12, self.uid as u64, 4); put(&mut wire, 16, self.gid as u64, 4);
        if layout == BootstrapLayout::HoldingLeafV3 {
            wire[..8].copy_from_slice(b"P4BOOT2!");
            put(&mut wire, 8, 2, 4); put(&mut wire, 20, 3, 4);
        }
        wire[24..56].copy_from_slice(&self.nonce);
        wire[56..88].copy_from_slice(&self.lmkd_sha256); wire[88..120].copy_from_slice(&self.init_sha256);
        Ok(wire)
    }
    fn decode(wire: &[u8]) -> Result<Self> {
        let (spec, layout) = Self::decode_with_layout(wire)?;
        if layout != BootstrapLayout::ProjectedRootV1 {
            return Err(Error::Reject("owned fixture bootstrap layout differs from root projection"));
        }
        Ok(spec)
    }
    fn decode_with_layout(wire: &[u8]) -> Result<(Self, BootstrapLayout)> {
        if wire.len() != BOOT_SIZE || wire[120..].iter().any(|b| *b != 0) {
            return Err(Error::Reject("bootstrap size/magic/version/reserved field"));
        }
        let layout = if &wire[..8] == b"P4BOOT1!" && number(wire, 8, 4) == 1 && number(wire, 20, 4) == 0 {
            BootstrapLayout::ProjectedRootV1
        } else if &wire[..8] == b"P4BOOT2!" && number(wire, 8, 4) == 2 && number(wire, 20, 4) == 3 {
            BootstrapLayout::HoldingLeafV3
        } else {
            return Err(Error::Reject("bootstrap size/magic/version/reserved field"));
        };
        let mut nonce = [0; 32]; nonce.copy_from_slice(&wire[24..56]);
        let mut lmkd_sha256 = [0; 32]; lmkd_sha256.copy_from_slice(&wire[56..88]);
        let mut init_sha256 = [0; 32]; init_sha256.copy_from_slice(&wire[88..120]);
        let spec = Self { nonce, uid: number(wire, 12, 4) as u32, gid: number(wire, 16, 4) as u32,
            lmkd_sha256, init_sha256 };
        spec.validate()?; Ok((spec, layout))
    }
    /// Legacy owned-fixture datagram, exactly sixteen SCM_RIGHTS. Calling
    /// again is a protocol fault and retires the broker. This method never
    /// opens a PID or path and is not the real ABI3 producer's send path.
    pub fn send(&self, channel: BorrowedFd<'_>, descriptors: &[BorrowedFd<'_>; RIGHTS], timeout: Duration) -> Result<()> {
        self.send_with_layout(channel, descriptors, timeout, BootstrapLayout::ProjectedRootV1)
    }
    fn send_with_layout(&self, channel: BorrowedFd<'_>, descriptors: &[BorrowedFd<'_>; RIGHTS],
        timeout: Duration, layout: BootstrapLayout) -> Result<()> {
        let wire = self.encode_with_layout(layout)?;
        let raw: Vec<RawFd> = descriptors.iter().map(AsRawFd::as_raw_fd).collect();
        send_packet(channel.as_raw_fd(), &wire, &raw, &mut Deadline::new(timeout)?)
    }
    pub fn receive_status(&self, channel: BorrowedFd<'_>, timeout: Duration) -> Result<BootstrapStatus> {
        let (wire, rights) = receive_packet(channel.as_raw_fd(), STATUS_SIZE, &mut Deadline::new(timeout)?, true)?;
        if !rights.is_empty() { return Err(Error::Reject("bootstrap status carried authority FDs")); }
        let status = BootstrapStatus::decode(&wire)?;
        if status.nonce != self.nonce { return Err(Error::Reject("bootstrap status nonce mismatch")); }
        Ok(status)
    }
    /// Transport helper for a separately held exact lifecycle Child. The
    /// caller must own that child and the inherited channel; socketpair
    /// SO_PEERCRED identifies its creator, not a later child. This compares
    /// against the parent's PREEXISTING spec; the child's packet never defines
    /// image/nonce policy. The production broker independently verifies lineage.
    pub fn receive_from_owned_child(&self, channel: BorrowedFd<'_>, timeout: Duration) -> Result<[OwnedFd; RIGHTS]> {
        let (wire, rights) = receive_packet(channel.as_raw_fd(), BOOT_SIZE, &mut Deadline::new(timeout)?, false)?;
        if BootstrapSpec::decode(&wire)? != *self { return Err(Error::Reject("owned child bootstrap differs from parent pins")); }
        rights.try_into().map_err(|_| Error::Reject("owned child lifecycle descriptor count"))
    }
    pub fn request_retirement(&self, channel: BorrowedFd<'_>, timeout: Duration) -> Result<()> {
        let mut wire = [0; RETIRE_SIZE]; wire[..8].copy_from_slice(b"P4RET01!");
        put(&mut wire, 8, 1, 4); wire[16..48].copy_from_slice(&self.nonce);
        send_packet(channel.as_raw_fd(), &wire, &[], &mut Deadline::new(timeout)?)
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
#[repr(u32)]
pub enum BootstrapState { Ready = 1, Active = 2, Retired = 3 }
/// READY certifies host preparation only. ACTIVE certifies grant delivery, not
/// a PSI event. RETIRED certifies joined host cleanup, not cell process exit.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct BootstrapStatus {
    pub state: BootstrapState, pub nonce: [u8; 32], pub generation: [u8; 32],
    pub endpoint: FileId, pub cgroup: FileId, pub budget: [u8; 32],
    pub granted: bool, pub faulted: bool,
}
impl BootstrapStatus {
    /// Send an inode-bound projection permit to a held private namespace
    /// owner's inherited channel. That owner must compare the socket inode,
    /// project only it, and retain LMKD's barrier until the comparison passes.
    pub fn permit_projection(&self, channel: BorrowedFd<'_>, timeout: Duration) -> Result<()> {
        if self.state != BootstrapState::Ready { return Err(Error::Reject("projection requires initial READY")); }
        let mut wire = [0; 64]; wire[..8].copy_from_slice(b"P4PROJ1!"); wire[8..40].copy_from_slice(&self.nonce);
        put(&mut wire, 40, self.endpoint.device, 8); put(&mut wire, 48, self.endpoint.inode, 8); put(&mut wire, 56, 1, 4);
        send_packet(channel.as_raw_fd(), &wire, &[], &mut Deadline::new(timeout)?)
    }
    fn encode(&self) -> [u8; STATUS_SIZE] {
        let mut wire = [0; STATUS_SIZE]; wire[..8].copy_from_slice(b"P4BST01!");
        put(&mut wire, 8, 1, 4); put(&mut wire, 12, self.state as u64, 4);
        wire[16..48].copy_from_slice(&self.nonce); wire[48..80].copy_from_slice(&self.generation);
        put(&mut wire, 80, self.endpoint.device, 8); put(&mut wire, 88, self.endpoint.inode, 8);
        put(&mut wire, 96, self.cgroup.device, 8); put(&mut wire, 104, self.cgroup.inode, 8);
        wire[112..144].copy_from_slice(&self.budget);
        put(&mut wire, 144, u64::from(self.granted) | (u64::from(self.faulted) << 1), 4);
        wire
    }
    fn decode(wire: &[u8]) -> Result<Self> {
        if wire.len() != STATUS_SIZE || &wire[..8] != b"P4BST01!" || number(wire, 8, 4) != 1 ||
            wire[148..].iter().any(|b| *b != 0) || number(wire, 144, 4) > 3 {
            return Err(Error::Reject("bootstrap status framing"));
        }
        let state = match number(wire, 12, 4) { 1 => BootstrapState::Ready, 2 => BootstrapState::Active,
            3 => BootstrapState::Retired, _ => return Err(Error::Reject("unknown bootstrap state")) };
        let mut nonce = [0; 32]; nonce.copy_from_slice(&wire[16..48]);
        let mut generation = [0; 32]; generation.copy_from_slice(&wire[48..80]);
        let mut budget = [0; 32]; budget.copy_from_slice(&wire[112..144]);
        let endpoint = FileId { device: number(wire, 80, 8), inode: number(wire, 88, 8) };
        let cgroup = FileId { device: number(wire, 96, 8), inode: number(wire, 104, 8) };
        if nonce == [0; 32] || generation == [0; 32] || endpoint.device == 0 || endpoint.inode == 0 ||
            cgroup.device == 0 || cgroup.inode == 0 {
            return Err(Error::Reject("bootstrap status empty identity"));
        }
        let flags = number(wire, 144, 4);
        if !super::enrollment::valid_budget(&budget) ||
            (state == BootstrapState::Ready && flags != 0) ||
            (state == BootstrapState::Active && flags != 1) {
            return Err(Error::Reject("bootstrap status budget/state flags"));
        }
        Ok(Self { state, nonce, generation, endpoint, cgroup, budget, granted: flags & 1 != 0, faulted: flags & 2 != 0 })
    }
}

/// Largest supported wait for one lifecycle request/response transaction.
/// Callers must share this bound; a longer argument is rejected before I/O.
pub const MAX_LIFECYCLE_IO_TIMEOUT: Duration = Duration::from_secs(2);

struct Deadline(Instant);
impl Deadline {
    fn new(timeout: Duration) -> Result<Self> {
        if timeout < Duration::from_millis(1) || timeout > MAX_LIFECYCLE_IO_TIMEOUT {
            return Err(Error::Reject("bootstrap I/O bound outside 1..2000 ms"));
        }
        Ok(Self(Instant::now().checked_add(timeout).ok_or(Error::Reject("bootstrap deadline overflow"))?))
    }
    fn check(&self) -> Result<()> {
        if Instant::now() >= self.0 { return Err(Error::Reject("bootstrap deadline expired")); }
        Ok(())
    }
    fn wait(&mut self, fd: RawFd, event: libc::c_short) -> Result<()> {
        self.wait_packet(fd, event, false)
    }
    fn wait_packet(&mut self, fd: RawFd, event: libc::c_short, drain_final: bool) -> Result<()> {
        loop {
            self.check()?;
            let mut p = libc::pollfd { fd, events: event | libc::POLLRDHUP, revents: 0 };
            let ms = self.0.saturating_duration_since(Instant::now()).as_millis().clamp(1, 100) as libc::c_int;
            if unsafe { libc::poll(&mut p, 1, ms) } < 0 {
                if io::Error::last_os_error().kind() == io::ErrorKind::Interrupted { continue; }
                return Err(err("poll lifecycle bootstrap"));
            }
            let final_packet = drain_final && event == libc::POLLIN && p.revents & libc::POLLIN != 0 &&
                p.revents & (libc::POLLERR | libc::POLLNVAL) == 0;
            if p.revents & BAD != 0 && !final_packet { return Err(Error::Reject("lifecycle bootstrap disconnected")); }
            self.check()?;
            if p.revents & event != 0 { return Ok(()); }
        }
    }
}

fn send_packet(fd: RawFd, wire: &[u8], rights: &[RawFd], deadline: &mut Deadline) -> Result<()> {
    if rights.len() > RIGHTS { return Err(Error::Reject("too many outgoing lifecycle handles")); }
    loop {
        deadline.wait(fd, libc::POLLOUT)?;
        let mut iov = libc::iovec { iov_base: wire.as_ptr().cast_mut().cast(), iov_len: wire.len() };
        let mut control = [0 as libc::c_long; 32];
        let mut message: libc::msghdr = unsafe { zeroed() };
        message.msg_iov = &mut iov; message.msg_iovlen = 1;
        if !rights.is_empty() {
            message.msg_control = control.as_mut_ptr().cast();
            message.msg_controllen = unsafe { libc::CMSG_SPACE(std::mem::size_of_val(rights) as u32) } as usize;
            let header = unsafe { libc::CMSG_FIRSTHDR(&message) };
            unsafe {
                (*header).cmsg_level = libc::SOL_SOCKET; (*header).cmsg_type = libc::SCM_RIGHTS;
                (*header).cmsg_len = libc::CMSG_LEN(std::mem::size_of_val(rights) as u32) as usize;
                std::ptr::copy_nonoverlapping(rights.as_ptr().cast::<u8>(), libc::CMSG_DATA(header), std::mem::size_of_val(rights));
            }
        }
        let sent = unsafe { libc::sendmsg(fd, &message, libc::MSG_DONTWAIT | libc::MSG_NOSIGNAL) };
        if sent < 0 && io::Error::last_os_error().kind() == io::ErrorKind::WouldBlock { continue; }
        if sent < 0 { return Err(err("send lifecycle packet")); }
        if sent as usize != wire.len() { return Err(Error::Reject("partial lifecycle packet")); }
        deadline.check()?; return Ok(());
    }
}
fn receive_packet(fd: RawFd, length: usize, deadline: &mut Deadline, drain_final: bool) -> Result<(Vec<u8>, Vec<OwnedFd>)> {
    let (wire, rights) = receive_up_to(fd, length, deadline, drain_final)?;
    if wire.len() != length { return Err(Error::Reject("lifecycle packet exact size")); }
    Ok((wire, rights))
}
fn receive_up_to(fd: RawFd, length: usize, deadline: &mut Deadline, drain_final: bool) -> Result<(Vec<u8>, Vec<OwnedFd>)> {
    loop {
        deadline.wait_packet(fd, libc::POLLIN, drain_final)?;
        let mut wire = vec![0; length];
        let mut iov = libc::iovec { iov_base: wire.as_mut_ptr().cast(), iov_len: wire.len() };
        let mut control = [0 as libc::c_long; 64];
        let mut message: libc::msghdr = unsafe { zeroed() };
        message.msg_iov = &mut iov; message.msg_iovlen = 1;
        message.msg_control = control.as_mut_ptr().cast(); message.msg_controllen = std::mem::size_of_val(&control);
        let got = unsafe { libc::recvmsg(fd, &mut message, libc::MSG_CMSG_CLOEXEC | libc::MSG_DONTWAIT | libc::MSG_TRUNC) };
        if got < 0 && io::Error::last_os_error().kind() == io::ErrorKind::WouldBlock { continue; }
        if got < 0 { return Err(err("receive lifecycle packet")); }
        let mut rights = Vec::new(); let mut malformed = false;
        let mut header = unsafe { libc::CMSG_FIRSTHDR(&message) };
        while !header.is_null() {
            let h = unsafe { &*header };
            let base = unsafe { libc::CMSG_LEN(0) } as usize;
            if h.cmsg_level == libc::SOL_SOCKET && h.cmsg_type == libc::SCM_RIGHTS && h.cmsg_len >= base {
                let payload = h.cmsg_len - base;
                if payload % size_of::<RawFd>() != 0 { malformed = true; }
                for i in 0..payload / size_of::<RawFd>() {
                    let raw = unsafe { std::ptr::read_unaligned(libc::CMSG_DATA(header).add(i * size_of::<RawFd>()).cast::<RawFd>()) };
                    rights.push(unsafe { OwnedFd::from_raw_fd(raw) });
                }
            } else { malformed = true; }
            header = unsafe { libc::CMSG_NXTHDR(&message, header) };
        }
        // Own all delivered FDs before any error. Linux closes undisclosed FDs
        // on ancillary truncation; RAII closes all visible ones here.
        if malformed || message.msg_flags & (libc::MSG_TRUNC | libc::MSG_CTRUNC) != 0 || got <= 0 || got as usize > length {
            return Err(Error::Reject("lifecycle packet framing/ancillary data"));
        }
        wire.truncate(got as usize);
        deadline.check()?; return Ok((wire, rights));
    }
}

enum ProgressFrame { Audit(PressureAudit), Status(BootstrapStatus) }
fn receive_progress_frame(fd: RawFd, deadline: &mut Deadline) -> Result<ProgressFrame> {
    let (wire, rights) = receive_up_to(fd, super::pressure_audit::PRESSURE_AUDIT_SIZE, deadline, true)?;
    if !rights.is_empty() { return Err(Error::Reject("lifecycle progress carried authority FDs")); }
    if wire.starts_with(b"P4AUD01!") {
        Ok(ProgressFrame::Audit(PressureAudit::decode(&wire)?))
    } else {
        Ok(ProgressFrame::Status(BootstrapStatus::decode(&wire)?))
    }
}

fn status_scalar(text: &str, key: &str) -> Result<u64> {
    let mut lines = text.lines().filter_map(|line| line.strip_prefix(key));
    let value = lines.next().ok_or(Error::Reject("missing lifecycle process scalar"))?;
    if lines.next().is_some() { return Err(Error::Reject("duplicate lifecycle process scalar")); }
    numeric(value.trim())
}
fn pidfd_number(host: &HostContext, fd: RawFd) -> Result<libc::pid_t> {
    // Signal 0 only verifies the kernel descriptor kind/liveness; it sends no
    // signal. A regular file with forged fdinfo-looking contents cannot pass.
    if unsafe { libc::syscall(libc::SYS_pidfd_send_signal, fd, 0, std::ptr::null::<libc::siginfo_t>(), 0) } != 0 {
        return Err(err("validate inherited lifecycle pidfd"));
    }
    let value = status_scalar(&read_at(&host.self_proc, &format!("fdinfo/{fd}"), MAX_PROC_BYTES)?, "Pid:")?;
    libc::pid_t::try_from(value).ok().filter(|pid| *pid > 0).ok_or(Error::Reject("inherited pidfd has no live host PID"))
}
fn adopt_pidfd(host: &HostContext, fd: OwnedFd) -> Result<ProcessPin> {
    let pid = pidfd_number(host, fd.as_raw_fd())?;
    let pin = host.pin(pid, fd)?;
    let status = read_at(&pin.proc_dir, "status", MAX_PROC_BYTES)?;
    if status_scalar(&status, "Tgid:")? != pid as u64 || status_scalar(&status, "Pid:")? != pid as u64 ||
        pidfd_number(host, pin.pidfd.as_raw_fd())? != pid {
        return Err(Error::Reject("inherited lifecycle pidfd is not a stable process leader"));
    }
    pin.live()?; Ok(pin)
}
fn trusted_parent(host: &HostContext, channel: RawFd) -> Result<ProcessPin> {
    if unsafe { libc::geteuid() } != 0 || unsafe { libc::getegid() } != 0 ||
        socket_integer(channel, libc::SO_TYPE)? != libc::SOCK_SEQPACKET ||
        socket_integer(channel, libc::SO_DOMAIN)? != libc::AF_UNIX ||
        socket_integer(channel, libc::SO_ACCEPTCONN)? != 0 {
        return Err(Error::Reject("bootstrap requires root connected Unix seqpacket"));
    }
    let flags = unsafe { libc::fcntl(channel, libc::F_GETFL) };
    if flags < 0 || flags & libc::O_NONBLOCK == 0 { return Err(Error::Reject("bootstrap channel must be nonblocking")); }
    if unsafe { libc::fcntl(channel, libc::F_SETFD, libc::FD_CLOEXEC) } < 0 { return Err(err("seal inherited channel")); }
    let peer = credentials(channel)?;
    if peer.uid != 0 || peer.gid != 0 || peer.pid != unsafe { libc::getppid() } {
        return Err(Error::Reject("bootstrap peer is not the exact root lifecycle parent"));
    }
    let raw = socket_integer(channel, SO_PEERPIDFD)?;
    if raw < 0 { return Err(Error::Reject("bootstrap parent pidfd unavailable")); }
    let parent = adopt_pidfd(host, unsafe { OwnedFd::from_raw_fd(raw) })?;
    if parent.pid != peer.pid { return Err(Error::Reject("bootstrap parent pidfd/credential mismatch")); }
    if unsafe { libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGKILL) } < 0 || unsafe { libc::getppid() } != parent.pid {
        return Err(Error::Reject("bootstrap parent-death contract failed"));
    }
    parent.live()?; Ok(parent)
}

fn role_namespaces(files: Vec<File>, init: &ProcessPin) -> Result<NamespacePins> {
    if files.len() != NS_NAMES.len() { return Err(Error::Reject("lifecycle namespace handle count")); }
    let kinds = [libc::CLONE_NEWPID, libc::CLONE_NEWPID, libc::CLONE_NEWNS, libc::CLONE_NEWCGROUP,
        libc::CLONE_NEWUSER, libc::CLONE_NEWNET, libc::CLONE_NEWIPC, libc::CLONE_NEWUTS, 0x80, 0x80];
    let init_pins = init.namespace_pins()?;
    let mut ids = Vec::with_capacity(NS_NAMES.len());
    for (index, file) in files.iter().enumerate() {
        require_fs(file, NSFS_MAGIC)?;
        if unsafe { libc::ioctl(file.as_raw_fd(), NS_GET_NSTYPE) } != kinds[index] {
            return Err(Error::Reject("lifecycle namespace descriptor type/order"));
        }
        let id = FileId::of(file)?;
        // LMKD may run in init's explicitly supplied default APEX mount
        // namespace. All other namespaces must be the stable private init's.
        if NS_NAMES[index] != "mnt" && id != init_pins.ids[index] {
            return Err(Error::Reject("role namespace is outside the lifecycle cell"));
        }
        ids.push(id);
    }
    Ok(NamespacePins { files, ids })
}
fn claim_directory(directory: &File, spec: &BootstrapSpec, authority: &CellAuthority) -> Result<()> {
    let m = directory.metadata().map_err(|e| io_err("stat lifecycle endpoint directory", e))?;
    if !m.is_dir() || m.uid() != 0 || m.gid() != 0 || m.mode() & 0o077 != 0 {
        return Err(Error::Reject("bootstrap endpoint directory is not private root-owned"));
    }
    // Persistent, exclusive marker. Broker exit/crash never makes this same
    // lifecycle directory reusable. Only the trusted supervisor may provision
    // a NEW cell directory after old retirement AND both exact old PIDs exit.
    let name = CString::new("droidloom-lmkd-psi.claim").expect("literal");
    let raw = unsafe { libc::openat(directory.as_raw_fd(), name.as_ptr(), libc::O_WRONLY | libc::O_CREAT |
        libc::O_EXCL | libc::O_NOFOLLOW | libc::O_CLOEXEC, 0o600) };
    if raw < 0 { return Err(err("claim one-shot lifecycle endpoint directory")); }
    let mut marker = unsafe { File::from_raw_fd(raw) };
    let mut data = [0; 104]; data[..8].copy_from_slice(b"P4SLOT1!");
    data[8..40].copy_from_slice(&spec.nonce); data[40..72].copy_from_slice(&authority.generation);
    put(&mut data, 72, authority.root_id.device, 8); put(&mut data, 80, authority.root_id.inode, 8);
    put(&mut data, 88, authority.owner.start, 8); put(&mut data, 96, authority.init.start, 8);
    marker.write_all(&data).map_err(|e| io_err("record lifecycle one-shot claim", e))?;
    marker.sync_all().map_err(|e| io_err("persist lifecycle one-shot claim", e))
}

fn owned_bootstrap_directory(file: &File, filesystem: libc::c_long) -> Result<()> {
    require_fs(file, filesystem)?;
    let m = file.metadata().map_err(|e| io_err("stat bootstrap layout directory", e))?;
    if !m.is_dir() || m.nlink() == 0 || m.uid() != 0 || m.gid() != 0 || m.mode() & 0o022 != 0 {
        return Err(Error::Reject("bootstrap layout directory owner/type/mode differs"));
    }
    Ok(())
}
fn exact_holding_membership(root_procs: &str, leaf_procs: &str, init_pid: libc::pid_t) -> Result<()> {
    if init_pid <= 0 || !root_procs.is_empty() || leaf_procs != format!("{init_pid}\n") {
        return Err(Error::Reject("bootstrap holding layout requires empty root and exact init leaf"));
    }
    Ok(())
}
// Retain the actual directories and both host-mount ancestry proofs until
// bootstrap is complete. A second capture must match these same generations;
// a replacement pathname, sibling, ancestor, or different mount cannot pass.
struct BootstrapLayoutPins {
    layout: BootstrapLayout,
    files: Vec<File>,
    ids: Vec<FileId>,
    ancestry: Vec<ancestry::CgroupAncestry>,
}
impl BootstrapLayoutPins {
    fn capture(layout: BootstrapLayout, host: &HostContext, root: &File, init: &ProcessPin) -> Result<Self> {
        init.live()?;
        let root_id = FileId::of(root)?;
        let init_root = open_at(&init.proc_dir, "root", libc::O_PATH | libc::O_DIRECTORY)?;
        let member = host.membership(&init.proc_dir)?;
        let mut ancestry = Vec::new();
        let files = match layout {
            BootstrapLayout::ProjectedRootV1 => {
                let projection = beneath_dir(&init_root, "sys/fs/cgroup")?;
                require_fs(&projection, CGROUP2_MAGIC)?;
                if FileId::of(&member)? != root_id || FileId::of(&projection)? != root_id {
                    return Err(Error::Reject("bootstrap init membership/projection differs from held root"));
                }
                vec![init_root, member, projection]
            }
            BootstrapLayout::HoldingLeafV3 => {
                owned_bootstrap_directory(root, CGROUP2_MAGIC)?;
                let holding = beneath_dir(&init_root, "dev/.droidloom-cgroups")?;
                let projection = beneath_dir(&init_root, "dev/.droidloom-cgroups/relay-v2")?;
                let sys = beneath_dir(&init_root, "sys")?;
                let target = beneath_dir(&init_root, "sys/fs/cgroup")?;
                owned_bootstrap_directory(&holding, TMPFS_MAGIC)?;
                owned_bootstrap_directory(&projection, CGROUP2_MAGIC)?;
                owned_bootstrap_directory(&sys, TMPFS_MAGIC)?;
                owned_bootstrap_directory(&target, TMPFS_MAGIC)?;
                if FileId::of(&projection)? != root_id || FileId::of(&sys)?.device != FileId::of(&target)?.device {
                    return Err(Error::Reject("bootstrap holding projection or native target differs from held layout"));
                }
                let leaf = beneath_dir(root, "init-bootstrap")?;
                owned_bootstrap_directory(&leaf, CGROUP2_MAGIC)?;
                let parent = open_at(&leaf, "..", libc::O_RDONLY | libc::O_DIRECTORY | libc::O_NOFOLLOW)?;
                if FileId::of(&leaf)? == root_id || FileId::of(&member)? != FileId::of(&leaf)? ||
                    FileId::of(&parent)? != root_id || read_at(root, "cgroup.type", 64)? != "domain\n" ||
                    read_at(&leaf, "cgroup.type", 64)? != "domain\n" ||
                    !read_at(&leaf, "cgroup.subtree_control", 256)?.trim().is_empty() {
                    return Err(Error::Reject("bootstrap init is outside the exact controller-free leaf"));
                }
                ancestry.push(ancestry::CgroupAncestry::capture(root, &member)?);
                ancestry.push(ancestry::CgroupAncestry::capture(root, &leaf)?);
                exact_holding_membership(&read_at(root, "cgroup.procs", 64)?,
                    &read_at(&leaf, "cgroup.procs", 64)?, init.pid)?;
                vec![init_root, member, projection, holding, sys, target, leaf, parent]
            }
        };
        let ids = files.iter().map(FileId::of).collect::<Result<Vec<_>>>()?;
        init.live()?;
        Ok(Self { layout, files, ids, ancestry })
    }
    fn validate(&self, host: &HostContext, root: &File, init: &ProcessPin) -> Result<()> {
        let current = Self::capture(self.layout, host, root, init)?;
        if self.files.len() != self.ids.len() || current.ids != self.ids || current.ancestry.len() != self.ancestry.len() {
            return Err(Error::Reject("bootstrap layout changed during authority construction"));
        }
        for (file, expected) in self.files.iter().zip(&self.ids) {
            if FileId::of(file)? != *expected { return Err(Error::Reject("held bootstrap layout generation changed")); }
        }
        for (held, observed) in self.ancestry.iter().zip(&current.ancestry) {
            held.validate()?;
            if !held.same_as(observed) { return Err(Error::Reject("bootstrap leaf ancestor chain changed")); }
        }
        Ok(())
    }
}

fn bootstrap(host: &HostContext, parent: &ProcessPin, channel: RawFd) -> Result<(BootstrapSpec, Arc<CellAuthority>, File)> {
    let mut deadline = Deadline::new(Duration::from_secs(2))?;
    let (wire, rights) = receive_packet(channel, BOOT_SIZE, &mut deadline, false)?;
    if rights.len() != RIGHTS { return Err(Error::Reject("bootstrap requires exactly sixteen owned descriptors")); }
    let (spec, layout) = BootstrapSpec::decode_with_layout(&wire)?;
    let mut rights = rights.into_iter();
    let root = File::from(rights.next().expect("fixed rights count"));
    let owner = adopt_pidfd(host, rights.next().expect("fixed rights count"))?;
    let init = adopt_pidfd(host, rights.next().expect("fixed rights count"))?;
    let lmkd = ExecutablePin::from_lifecycle(File::from(rights.next().expect("fixed rights count")), spec.lmkd_sha256)?;
    let expected_init = ExecutablePin::from_lifecycle(File::from(rights.next().expect("fixed rights count")), spec.init_sha256)?;
    let directory = File::from(rights.next().expect("fixed rights count"));
    let owner_status = read_at(&owner.proc_dir, "status", MAX_PROC_BYTES)?;
    let init_status = read_at(&init.proc_dir, "status", MAX_PROC_BYTES)?;
    if owner.pid != parent.pid && status_scalar(&owner_status, "PPid:")? != parent.pid as u64 {
        return Err(Error::Reject("namespace owner is not held by bootstrap parent"));
    }
    let identity = parse_status(&init_status, init.pid)?;
    if init.pid == owner.pid || status_scalar(&init_status, "PPid:")? != owner.pid as u64 ||
        identity.namespace_pids.len() < 2 || identity.namespace_pids.last() != Some(&1) ||
        identity.uids != [0; 4] || identity.gids != [0; 4] {
        return Err(Error::Reject("init is not the exact private root child of namespace owner"));
    }
    let init_executable = open_at(&init.proc_dir, "exe", libc::O_RDONLY)?;
    expected_init.matches(&init_executable, true)?;
    let layout_pins = BootstrapLayoutPins::capture(layout, host, &root, &init)?;
    let namespaces = role_namespaces(rights.map(File::from).collect(), &init)?;
    if namespaces.identity("pid") == host.host_namespaces.identity("pid") {
        return Err(Error::Reject("bootstrap init must be in a private PID namespace"));
    }
    let role = RolePolicy { uid: spec.uid, gid: spec.gid, namespaces, executable: lmkd };
    let authority = Arc::new(CellAuthority::from_lifecycle(root, owner, init, role)?);
    parent.live()?; host.validate_host_view()?; no_unexpected_peer_data(channel)?; deadline.check()?;
    layout_pins.validate(host, &authority.root, &authority.init)?;
    claim_directory(&directory, &spec, &authority)?;
    layout_pins.validate(host, &authority.root, &authority.init)?;
    deadline.check()?;
    Ok((spec, authority, directory))
}

fn valid_retirement(wire: &[u8], spec: &BootstrapSpec) -> bool {
    wire.len() == RETIRE_SIZE && &wire[..8] == b"P4RET01!" && number(wire, 8, 4) == 1 &&
        number(wire, 12, 4) == 0 && wire[16..48] == spec.nonce
}

// Diagnostics only: borrow both original causes before the joined receipt is
// consumed by PressureAudit. UTF-8 hex keeps one parseable line without losing
// newlines or non-ASCII bytes. A stderr failure must not replace either cause,
// change the retirement outcome, or acquire any lifecycle authority.
fn report_retirement_cause(output: &mut impl Write, status: &BootstrapStatus,
    relay_reason: Option<&str>, lifecycle_error: Option<&Error>) {
    if relay_reason.is_none() && lifecycle_error.is_none() { return; }
    let hex = |bytes: &[u8]| -> String {
        const DIGITS: &[u8; 16] = b"0123456789abcdef";
        let mut text = String::with_capacity(bytes.len() * 2);
        for &byte in bytes {
            text.push(DIGITS[(byte >> 4) as usize] as char);
            text.push(DIGITS[(byte & 15) as usize] as char);
        }
        text
    };
    let optional_hex = |text: Option<&str>| -> String {
        match text {
            Some(value) => format!("\"{}\"", hex(value.as_bytes())),
            None => "null".to_owned(),
        }
    };
    let lifecycle_message = lifecycle_error.map(|error| error.to_string());
    let _ = writeln!(output,
        "droidloom-psi-owner: retirement-cause-v1 {{\"schema\":1,\"nonce\":\"{}\",\"authority_generation\":\"{}\",\"cgroup_device\":{},\"cgroup_inode\":{},\"granted\":{},\"faulted\":{},\"relay_reason_utf8_hex\":{},\"lifecycle_error_utf8_hex\":{}}}",
        hex(&status.nonce), hex(&status.generation), status.cgroup.device, status.cgroup.inode,
        status.granted, status.faulted, optional_hex(relay_reason), optional_hex(lifecycle_message.as_deref()));
}

/// Production executable entry. Call once in a freshly exec'd, host-namespace
/// process leader with one inherited nonblocking seqpacket at fd 3. The exact
/// parent owns startup, endpoint projection, timeout policy and cell teardown.
/// No endpoint is opened until its sixteen trusted handles pass validation.
pub fn run_inherited_lifecycle(channel: OwnedFd) -> Result<()> {
    let host = Arc::new(HostContext::open()?);
    let parent = trusted_parent(&host, channel.as_raw_fd())?;
    let (spec, authority, directory) = bootstrap(&host, &parent, channel.as_raw_fd())?;
    let prepared = PreparedRelay::bind_at(directory, spec.uid, spec.gid)?;
    let scope = authority.scope_request();
    let mut status = BootstrapStatus { state: BootstrapState::Ready, nonce: spec.nonce,
        generation: authority.generation, endpoint: prepared.endpoint_identity(), cgroup: scope.cgroup,
        budget: scope.budget, granted: false, faulted: false };
    let mut relay = prepared.activate(Arc::clone(&host), authority)?;
    let outcome = (|| -> Result<()> {
        send_packet(channel.as_raw_fd(), &status.encode(), &[], &mut Deadline::new(Duration::from_secs(1))?)?;
        loop {
            parent.live()?; host.validate_host_view()?;
            match relay.phase() {
                RelayPhase::Active if !status.granted => {
                    status.state = BootstrapState::Active; status.granted = true;
                    send_packet(channel.as_raw_fd(), &status.encode(), &[], &mut Deadline::new(Duration::from_secs(1))?)?;
                }
                RelayPhase::Retiring | RelayPhase::Retired | RelayPhase::Poisoned =>
                    return Err(Error::Reject("relay service retired; exact old cell requires lifecycle recovery")),
                _ => {}
            }
            let mut p = libc::pollfd { fd: channel.as_raw_fd(), events: libc::POLLIN | libc::POLLRDHUP, revents: 0 };
            if unsafe { libc::poll(&mut p, 1, 100) } < 0 {
                if io::Error::last_os_error().kind() == io::ErrorKind::Interrupted { continue; }
                return Err(err("wait lifecycle retirement command"));
            }
            if p.revents & BAD != 0 { return Err(Error::Reject("lifecycle parent control lost")); }
            if p.revents & libc::POLLIN != 0 {
                let (wire, rights) = receive_packet(channel.as_raw_fd(), RETIRE_SIZE, &mut Deadline::new(Duration::from_secs(1))?, false)?;
                if !rights.is_empty() || !valid_retirement(&wire, &spec) {
                    return Err(Error::Reject("unexpected lifecycle command or replay"));
                }
                return Ok(());
            }
        }
    })();
    // Every path after activation goes through verified retirement. A failed
    // or timed-out join retains the owner and cannot emit RETIRED or exit as a
    // success. The lifecycle parent must retain its own cell ownership too.
    relay.request_retirement();
    loop {
        match relay.finish_retirement(Duration::from_millis(250)) {
            Ok(Some(receipt)) => {
                status.state = BootstrapState::Retired;
                status.granted = receipt.was_granted();
                status.faulted = outcome.is_err() || receipt.reason().is_some();
                report_retirement_cause(&mut io::stderr().lock(), &status, receipt.reason(), outcome.as_ref().err());
                let audit = PressureAudit::from_retirement(&status, receipt, super::psi::now_ns()?);
                // Joined-worker observations use this exact trusted parent
                // channel. They supply no authority and do not substitute for
                // the following terminal status and exact process reap.
                send_packet(channel.as_raw_fd(), &audit.encode()?, &[], &mut Deadline::new(Duration::from_secs(1))?)?;
                send_packet(channel.as_raw_fd(), &status.encode(), &[], &mut Deadline::new(Duration::from_secs(1))?)?;
                if status.faulted && outcome.is_ok() {
                    return Err(Error::Reject("PSI worker faulted while lifecycle retirement completed"));
                }
                return outcome;
            }
            Ok(None) => {}
            Err(_) => thread::sleep(Duration::from_millis(100)), // permanently unproven, never fabricate a receipt
        }
    }
}

/// Read-only kernel identities from an existing authenticated broker pin.
/// This serializable-by-the-caller data is never accepted as authority.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct LifecycleProcessObservation {
    pub pid: i32,
    pub birth: u64,
    pub pidfd: FileId,
    pub proc_dir: FileId,
}

/// Supervisor-side ownership adapter. It executes the exact verified broker
/// inode through a held FD, keeps the exact Child and a private inherited
/// socketpair, and uses the SAME process-wide lifecycle slot as PreparedRelay.
///
/// Spawn returns the owner before any bootstrap I/O. initialize/retire errors
/// leave it in the caller's hands. Never remove this value from ActiveCell on
/// error, and never open LMKD's startup barrier before initialize returns READY.
pub struct LifecycleBroker {
    child: std::process::Child,
    running: Option<ProcessPin>,
    channel: OwnedFd,
    executable: ExecutablePin,
    host: HostContext,
    spec: BootstrapSpec,
    layout: BootstrapLayout,
    inputs: Option<Vec<OwnedFd>>,
    attempted: bool,
    ready: Option<BootstrapStatus>,
    latest: Option<BootstrapStatus>,
    audit: Option<PressureAudit>,
    retirement_requested: bool,
    retirement_seen: bool,
    retirement_poisoned: bool,
    joined: bool,
    retired: Arc<AtomicBool>,
}
impl LifecycleBroker {
    pub fn spawn(executable: ExecutablePin, spec: BootstrapSpec, handles: &[BorrowedFd<'_>; RIGHTS]) -> Result<Self> {
        Self::spawn_in_context(HostContext::open()?, executable, spec, handles)
    }
    /// Legacy owned-fixture entry with an already projected domain root.
    /// Accepts only a HostContext originally opened by the process leader.
    /// Its fields are private; forked processes and workers which change any
    /// namespace fail validation before they can spawn or send authority.
    pub fn spawn_in_context(host: HostContext, executable: ExecutablePin, spec: BootstrapSpec,
        handles: &[BorrowedFd<'_>; RIGHTS]) -> Result<Self> {
        Self::spawn_with_layout(host, executable, spec, handles, BootstrapLayout::ProjectedRootV1)
    }
    /// Paired only with the real ABI3 init barrier: the finite domain is at
    /// its verified holding view and init occupies the exact bootstrap leaf.
    /// This sends a version-2/layout-3 packet; an old broker rejects it. There
    /// is no fallback to the legacy fixture's already-projected root layout.
    pub fn spawn_holding_in_context(host: HostContext, executable: ExecutablePin, spec: BootstrapSpec,
        handles: &[BorrowedFd<'_>; RIGHTS]) -> Result<Self> {
        Self::spawn_with_layout(host, executable, spec, handles, BootstrapLayout::HoldingLeafV3)
    }
    fn spawn_with_layout(host: HostContext, executable: ExecutablePin, spec: BootstrapSpec,
        handles: &[BorrowedFd<'_>; RIGHTS], layout: BootstrapLayout) -> Result<Self> {
        use std::os::unix::process::CommandExt;
        spec.validate()?;
        if unsafe { libc::geteuid() } != 0 || unsafe { libc::getegid() } != 0 {
            return Err(Error::Reject("lifecycle broker caller must be root"));
        }
        executable.matches(&executable.file, true)?;
        host.validate_current_thread()?;
        let owner = adopt_pidfd(&host, duplicate(handles[1].as_raw_fd())?)?;
        let init = adopt_pidfd(&host, duplicate(handles[2].as_raw_fd())?)?;
        let inputs = handles.iter().map(|fd| duplicate(fd.as_raw_fd())).collect::<Result<Vec<_>>>()?;
        let mut pair = [-1; 2];
        if unsafe { libc::socketpair(libc::AF_UNIX, libc::SOCK_SEQPACKET | libc::SOCK_CLOEXEC | libc::SOCK_NONBLOCK,
            0, pair.as_mut_ptr()) } < 0 { return Err(err("create private lifecycle bootstrap socketpair")); }
        let channel = unsafe { OwnedFd::from_raw_fd(pair[0]) };
        let child_socket = unsafe { OwnedFd::from_raw_fd(pair[1]) };
        // The child bootstrap channel is exactly fd 3. Pin the executable at a
        // different high descriptor before pre_exec can replace that number.
        let binary_raw = unsafe { libc::fcntl(executable.file.as_raw_fd(), libc::F_DUPFD_CLOEXEC, 64) };
        if binary_raw < 0 { return Err(err("pin exact broker exec descriptor")); }
        let binary = unsafe { OwnedFd::from_raw_fd(binary_raw) };
        let source = child_socket.as_raw_fd();
        let parent_pid = unsafe { libc::getpid() };
        let mut command = std::process::Command::new(format!("/proc/self/fd/{}", binary.as_raw_fd()));
        command.args(["--lifecycle-fd", "3"]).stdin(std::process::Stdio::null());
        unsafe {
            command.pre_exec(move || {
                if source != 3 && libc::dup2(source, 3) < 0 { return Err(io::Error::last_os_error()); }
                if libc::fcntl(3, libc::F_SETFD, 0) < 0 || libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGKILL) < 0 {
                    return Err(io::Error::last_os_error());
                }
                if libc::getppid() != parent_pid { return Err(io::Error::other("lifecycle parent changed before exec")); }
                Ok(())
            });
        }
        let retired = super::lifecycle_relay::reserve_lifecycle_process_slot(owner.pidfd.as_raw_fd(), init.pidfd.as_raw_fd())?;
        let child = match command.spawn() {
            Ok(child) => child,
            Err(error) => {
                // Command::spawn has reaped a pre-exec failure. No trusted
                // bootstrap was sent, so no PSI owner can have been created.
                retired.store(true, Ordering::Release);
                return Err(io_err("execute exact lifecycle broker", error));
            }
        };
        // No fallible operation between spawn and returning retained ownership.
        Ok(Self { child, running: None, channel, executable, host, spec, layout, inputs: Some(inputs), attempted: false,
            ready: None, latest: None, audit: None, retirement_requested: false, retirement_seen: false,
            retirement_poisoned: false, joined: false, retired })
    }
    pub fn pid(&self) -> u32 { self.child.id() }
    pub fn latest_status(&self) -> Option<&BootstrapStatus> { self.latest.as_ref() }
    pub fn retirement_complete(&self) -> bool { self.joined }
    /// Data-only identity of the existing authenticated, live broker pin.
    /// No API accepts this value as authority. The origin/worker validation is
    /// unchanged, and neither a numeric PID nor a new process lookup is used.
    pub fn process_observation(&self) -> Result<LifecycleProcessObservation> {
        self.host.validate_current_thread()?;
        let process = self.running.as_ref().ok_or(Error::Reject("broker process not authenticated"))?;
        process.live()?;
        let mut stat: libc::stat = unsafe { std::mem::zeroed() };
        if unsafe { libc::fstat(process.pidfd.as_raw_fd(), &mut stat) } < 0 {
            return Err(err("observe held broker pidfd"));
        }
        let result = LifecycleProcessObservation {
            pid: process.pid, birth: process.start,
            pidfd: FileId { device: stat.st_dev as u64, inode: stat.st_ino as u64 },
            proc_dir: FileId::of(&process.proc_dir)?,
        };
        process.live()?;
        Ok(result)
    }
    /// Close only this exact owned broker's authority channel after an
    /// unproven retirement failure. This is revocation, never a joined receipt
    /// or permission to release a generation. Keep this value retained.
    pub fn revoke_unproven_control(&mut self) -> Result<()> {
        if self.joined { return Err(Error::Reject("joined broker no longer needs unproven revocation")); }
        if unsafe { libc::shutdown(self.channel.as_raw_fd(), libc::SHUT_RDWR) } < 0 {
            return Err(err("revoke unproven lifecycle control"));
        }
        Ok(())
    }
    /// Audit becomes available only after terminal status and exact child reap.
    pub fn pressure_audit(&self) -> Option<&PressureAudit> { if self.joined { self.audit.as_ref() } else { None } }
    /// Returns the kernel listener identity that the caller must compare with
    /// its socket projection before releasing the owned LMKD startup barrier.
    /// READY alone is neither enrollment nor a PSI event acceptance receipt.
    pub fn initialize(&mut self) -> Result<&BootstrapStatus> {
        if self.attempted || self.joined { return Err(Error::Reject("lifecycle broker bootstrap is one attempt")); }
        self.attempted = true;
        self.host.validate_host_view()?;
        let broker = self.host.pin_owned_child(&mut self.child)?;
        let running = open_at(&broker.proc_dir, "exe", libc::O_RDONLY)?;
        self.executable.matches(&running, true)?;
        self.running = Some(broker);
        let inputs = self.inputs.take().ok_or(Error::Reject("bootstrap inputs already consumed"))?;
        let borrowed: [BorrowedFd<'_>; RIGHTS] = std::array::from_fn(|index| unsafe {
            BorrowedFd::borrow_raw(inputs[index].as_raw_fd())
        });
        self.spec.send_with_layout(unsafe { BorrowedFd::borrow_raw(self.channel.as_raw_fd()) }, &borrowed,
            Duration::from_secs(2), self.layout)?;
        drop(inputs);
        let status = self.spec.receive_status(unsafe { BorrowedFd::borrow_raw(self.channel.as_raw_fd()) }, Duration::from_secs(2))?;
        if status.state != BootstrapState::Ready { return Err(Error::Reject("lifecycle broker did not return initial READY")); }
        self.latest = Some(status.clone()); self.ready = Some(status);
        // Keep a valid READY even if the child just failed, so the caller can
        // still consume its terminal receipt and reap it without opening LMKD.
        self.running.as_ref().expect("retained broker process pin").live()?; self.host.validate_host_view()?;
        Ok(self.ready.as_ref().expect("stored READY"))
    }
    /// Final gate used immediately before releasing real Android init.
    /// Pending progress is rejected here: enrollment cannot legitimately start
    /// while init is still held in its constructor.
    pub fn ready_for_init_commit(&self) -> Result<()> {
        self.host.validate_current_thread()?;
        if !self.attempted || self.joined || self.retirement_requested || self.retirement_seen || self.retirement_poisoned ||
            self.latest.as_ref().is_none_or(|s| s.state != BootstrapState::Ready || s.faulted || s.granted) {
            return Err(Error::Reject("broker no longer holds its initial READY"));
        }
        self.running.as_ref().ok_or(Error::Reject("broker process pin missing"))?.live()?;
        let mut p = libc::pollfd { fd: self.channel.as_raw_fd(), events: libc::POLLIN | libc::POLLRDHUP, revents: 0 };
        if unsafe { libc::poll(&mut p, 1, 0) } != 0 || p.revents != 0 {
            return Err(Error::Reject("broker changed before init COMMIT"));
        }
        Ok(())
    }
    /// Pure readiness query. Terminal packets may be drained with HUP, but a
    /// bare dead/closed broker is never treated as successful retirement.
    pub fn progress_available(&self) -> Result<bool> {
        self.host.validate_current_thread()?;
        let mut p = libc::pollfd { fd: self.channel.as_raw_fd(), events: libc::POLLIN | libc::POLLRDHUP, revents: 0 };
        if unsafe { libc::poll(&mut p, 1, 0) } < 0 { return Err(err("poll owned broker progress")); }
        if p.revents & (libc::POLLERR | libc::POLLNVAL) != 0 { return Err(Error::Reject("broker progress fault")); }
        if p.revents & libc::POLLIN != 0 { return Ok(true); }
        if p.revents & (libc::POLLHUP | libc::POLLRDHUP) != 0 { return Err(Error::Reject("broker closed without drained retirement")); }
        self.running.as_ref().ok_or(Error::Reject("broker process pin missing"))?.live()?;
        Ok(false)
    }
    fn accept_status(&mut self, status: BootstrapStatus) -> Result<()> {
        let ready = self.ready.as_ref().ok_or(Error::Reject("no completed lifecycle bootstrap"))?;
        if status.generation != ready.generation || status.endpoint != ready.endpoint || status.cgroup != ready.cgroup ||
            status.budget != ready.budget || status.state == BootstrapState::Ready || self.retirement_seen {
            return Err(Error::Reject("lifecycle status changed scope/replayed terminal generation"));
        }
        if status.state == BootstrapState::Active && self.latest.as_ref().is_some_and(|s| s.state == BootstrapState::Active) {
            return Err(Error::Reject("repeated lifecycle ACTIVE status"));
        }
        if status.state == BootstrapState::Retired {
            let audit = self.audit.as_ref().ok_or(Error::Reject("retirement lacks joined pressure audit"))?;
            if audit.granted != status.granted || audit.faulted != status.faulted {
                return Err(Error::Reject("pressure audit and retirement flags differ"));
            }
        } else if self.audit.is_some() {
            return Err(Error::Reject("nonterminal lifecycle status after terminal audit"));
        }
        self.retirement_seen = status.state == BootstrapState::Retired;
        self.latest = Some(status); Ok(())
    }
    /// Receives real grant/fault/retirement progress. A faulted RETIRED status
    /// is the recovery hook: keep ActiveCell owned, finish this broker, then
    /// stop and reap the exact old owner AND init before another generation.
    pub fn receive_progress(&mut self, timeout: Duration) -> Result<&BootstrapStatus> {
        let mut deadline = Deadline::new(timeout)?;
        loop {
            match receive_progress_frame(self.channel.as_raw_fd(), &mut deadline)? {
                ProgressFrame::Audit(audit) => {
                    let ready = self.ready.as_ref().ok_or(Error::Reject("pressure audit before READY"))?;
                    if self.audit.is_some() || self.retirement_seen || audit.nonce != self.spec.nonce ||
                        audit.authority_generation != ready.generation || audit.cgroup != ready.cgroup || audit.budget != ready.budget {
                        return Err(Error::Reject("terminal pressure audit replay/scope mismatch"));
                    }
                    self.audit = Some(audit);
                }
                ProgressFrame::Status(status) => {
                    if status.nonce != self.spec.nonce { return Err(Error::Reject("lifecycle progress nonce mismatch")); }
                    self.accept_status(status)?;
                    return Ok(self.latest.as_ref().expect("stored progress"));
                }
            }
        }
    }
    /// A timeout/error retains the Child/control/slot. Successful return needs
    /// both a valid joined-worker RETIRED packet AND reaping the exact broker.
    /// This still does not certify that the old Android owner/init have died.
    pub fn retire(&mut self, timeout: Duration) -> Result<bool> {
        if self.retirement_poisoned { return Err(Error::Reject("broker retirement is poisoned; retain exact generation")); }
        if self.joined { return Ok(true); }
        if !self.attempted || self.ready.is_none() { return Err(Error::Reject("bootstrap incomplete; retain failed owner")); }
        let deadline = Deadline::new(timeout)?;
        let attempt = (|| -> Result<bool> {
            let mut request_error = None;
            if !self.retirement_seen && !self.retirement_requested {
                // A broker can retire on its own error and close after writing its
                // AUDIT/RETIRED pair. Drain actual input before trying to write to
                // that closed peer; bare EOF still fails the unchanged receiver.
                while !self.retirement_seen {
                    if deadline.0.saturating_duration_since(Instant::now()) < Duration::from_millis(1) {
                        return Ok(false);
                    }
                    let mut p = libc::pollfd { fd: self.channel.as_raw_fd(),
                        events: libc::POLLIN | libc::POLLRDHUP, revents: 0 };
                    if unsafe { libc::poll(&mut p, 1, 0) } < 0 {
                        if io::Error::last_os_error().kind() == io::ErrorKind::Interrupted { continue; }
                        return Err(err("poll retirement input"));
                    }
                    if p.revents & (libc::POLLIN | BAD) == 0 { break; }
                    let remaining = deadline.0.saturating_duration_since(Instant::now());
                    if remaining < Duration::from_millis(1) { return Ok(false); }
                    // The existing terminal receiver decides whether data may
                    // be drained with HUP/ERR; this poll supplies no evidence.
                    self.receive_progress(remaining)?;
                }
                if !self.retirement_seen {
                    let remaining = deadline.0.saturating_duration_since(Instant::now());
                    if remaining < Duration::from_millis(1) { return Ok(false); }
                    self.retirement_requested = true; // never replay the command
                    request_error = self.spec.request_retirement(
                        unsafe { BorrowedFd::borrow_raw(self.channel.as_raw_fd()) }, remaining).err();
                }
            }
            let terminal = (|| -> Result<bool> {
                // Close can also race the readiness check above. A failed send is
                // not retirement evidence: only the same full receiver plus exact
                // Child reap can discharge it. Otherwise keep that first error.
                while !self.retirement_seen {
                    let remaining = deadline.0.saturating_duration_since(Instant::now());
                    if remaining < Duration::from_millis(1) { return Ok(false); }
                    self.receive_progress(remaining)?;
                }
                loop {
                    if let Some(exit) = self.child.try_wait().map_err(|e| io_err("reap exact lifecycle broker", e))? {
                        let faulted = self.latest.as_ref().expect("retirement status").faulted;
                        if exit.code() != Some(if faulted { 1 } else { 0 }) {
                            return Err(Error::Reject("broker exit disagrees with retirement receipt"));
                        }
                        self.joined = true; self.retired.store(true, Ordering::Release); return Ok(true);
                    }
                    if Instant::now() >= deadline.0 { return Ok(false); }
                    thread::sleep(Duration::from_millis(1));
                }
            })();
            match (terminal, request_error) {
                (Ok(true), _) => Ok(true),
                (_, Some(error)) => Err(error),
                (result, None) => result,
            }
        })();
        // A malformed/failed retirement cannot be retried into a clean
        // certificate by consuming a valid tail left after the first error.
        // Ok(false) retains an unfinished wait and remains resumable.
        if attempt.is_err() { self.retirement_poisoned = true; }
        attempt
    }
    /// Only before ANY bootstrap send, stopping/reaping this exact child proves
    /// there was no authority or PSI owner. After initialize starts, failures
    /// must retain the handle and cannot use this shortcut.
    pub fn abort_before_initialize(&mut self) -> Result<()> {
        if self.attempted || self.joined { return Err(Error::Reject("bootstrap attempt already consumed")); }
        if self.child.try_wait().map_err(|e| io_err("poll unbootstrapped broker", e))?.is_none() {
            self.child.kill().map_err(|e| io_err("stop exact unbootstrapped broker", e))?;
        }
        self.child.wait().map_err(|e| io_err("reap unbootstrapped broker", e))?;
        self.inputs = None; self.joined = true; self.retired.store(true, Ordering::Release); Ok(())
    }
}
impl Drop for LifecycleBroker {
    fn drop(&mut self) {
        // Closing the inherited control requests broker retirement. Do NOT
        // fabricate a joined receipt, reset the shared slot, kill a cell, or
        // silently authorize a replacement from a best-effort destructor.
        if !self.joined { unsafe { libc::shutdown(self.channel.as_raw_fd(), libc::SHUT_RDWR) }; }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn spec() -> BootstrapSpec { BootstrapSpec { nonce: [7; 32], uid: 1069, gid: 1069,
        lmkd_sha256: [8; 32], init_sha256: [9; 32] } }
    fn sockets() -> (OwnedFd, OwnedFd) {
        let mut fds = [-1; 2];
        assert_eq!(unsafe { libc::socketpair(libc::AF_UNIX, libc::SOCK_SEQPACKET | libc::SOCK_CLOEXEC |
            libc::SOCK_NONBLOCK, 0, fds.as_mut_ptr()) }, 0);
        unsafe { (OwnedFd::from_raw_fd(fds[0]), OwnedFd::from_raw_fd(fds[1])) }
    }
    fn empty_audit_and_status() -> (PressureAudit, BootstrapStatus) {
        let s = spec(); let mut budget = [0; 32]; put(&mut budget, 0, 512 * 1024 * 1024, 8);
        put(&mut budget, 24, 1, 4); put(&mut budget, 28, 1, 4);
        let status = BootstrapStatus { state: BootstrapState::Retired, nonce: s.nonce, generation: [6; 32],
            endpoint: FileId { device: 1, inode: 2 }, cgroup: FileId { device: 3, inode: 4 }, budget,
            granted: false, faulted: false };
        let audit = PressureAudit { nonce: s.nonce, authority_generation: status.generation, cgroup: status.cgroup,
            budget, granted: false, faulted: false, incomplete: false, registrations: RegistrationAudit::default(),
            observations: 0, packets_queued: 0, stop_reason: 0, events: EventAuditTrail::default(), retired_monotonic_ns: 10 };
        (audit, status)
    }
    // This is a post-READY transport/reap fixture, not bootstrap authority.
    // Only this test module seeds READY. Production constructors, their
    // leader-origin requirement and all sixteen-handle checks are unchanged.
    // Python merely sends Rust-encoded frames on the inherited owned socket;
    // it implements no alternate protocol decoder or qualification logic.
    const RETIREMENT_PEER: &str = r#"
import socket, sys
raw = sys.stdin.buffer.read(32769)
assert len(raw) <= 32768
lines = raw.splitlines()
assert len(lines) >= 3
code = int(lines[0]); assert code in (0, 1)
request = bytes.fromhex(lines[1].decode())
hold = lines[2] == b'1'
frames = [bytes.fromhex(line.decode()) for line in lines[3:]]
assert len(sys.argv) == 3
channel = socket.socket(fileno=int(sys.argv[1]))
control = socket.socket(fileno=int(sys.argv[2]))
assert channel.type == control.type == socket.SOCK_SEQPACKET
channel.settimeout(2)
control.settimeout(2)
assert control.send(b'R') == 1
assert control.recv(2) == b'G'
if request:
    assert channel.recv(len(request) + 1) == request
for frame in frames:
    assert channel.send(frame) == len(frame)
if hold:
    assert control.recv(2) == b'X'
channel.close(); control.close()
sys.exit(code)
"#;
    struct RetirementOwnedChild(Option<std::process::Child>);
    impl Drop for RetirementOwnedChild {
        fn drop(&mut self) {
            if let Some(child) = self.0.as_mut() {
                if child.try_wait().ok().flatten().is_none() { let _ = child.kill(); }
                let _ = child.wait();
            }
        }
    }
    struct RetirementFixture { broker: LifecycleBroker, control: OwnedFd }
    impl Drop for RetirementFixture {
        fn drop(&mut self) {
            if self.broker.child.try_wait().ok().flatten().is_none() { let _ = self.broker.child.kill(); }
            let _ = self.broker.child.wait();
        }
    }
    impl RetirementFixture {
        fn wait_exact_exit_without_reaping(&self) {
            let pin = self.broker.running.as_ref().unwrap();
            let deadline = Instant::now() + Duration::from_secs(2);
            loop {
                let mut p = libc::pollfd { fd: pin.pidfd.as_raw_fd(), events: libc::POLLIN, revents: 0 };
                let count = unsafe { libc::poll(&mut p, 1, 10) };
                assert!(count >= 0);
                if p.revents & libc::POLLIN != 0 { return; }
                assert_eq!(p.revents, 0);
                assert!(Instant::now() < deadline, "owned retirement peer failed to exit");
            }
        }
        fn release_exit(&self) {
            send_packet(self.control.as_raw_fd(), b"X", &[],
                &mut Deadline::new(Duration::from_secs(1)).unwrap()).unwrap();
        }
    }
    fn retirement_fixture(frames: Vec<Vec<u8>>, code: i32, wait_request: bool, hold: bool) -> RetirementFixture {
        use std::io::{Seek, SeekFrom};
        use std::os::unix::process::CommandExt;
        use std::process::{Command, Stdio};
        fn high(fd: RawFd) -> OwnedFd {
            let value = unsafe { libc::fcntl(fd, libc::F_DUPFD_CLOEXEC, 64) };
            assert!(value >= 0);
            unsafe { OwnedFd::from_raw_fd(value) }
        }
        fn hex(data: &[u8]) -> String { data.iter().map(|v| format!("{v:02x}")).collect() }
        let request = if wait_request {
            let mut wire = [0; RETIRE_SIZE]; wire[..8].copy_from_slice(b"P4RET01!");
            put(&mut wire, 8, 1, 4); wire[16..].copy_from_slice(&spec().nonce); hex(&wire)
        } else { String::new() };
        let mut input = format!("{code}\n{request}\n{}\n", u8::from(hold));
        for frame in frames { input.push_str(&hex(&frame)); input.push('\n'); }
        assert!(input.len() <= 32768);
        let raw = unsafe { libc::memfd_create(c"owned-retirement-input".as_ptr(), libc::MFD_CLOEXEC | libc::MFD_ALLOW_SEALING) };
        assert!(raw >= 0);
        let mut input_file = unsafe { File::from_raw_fd(raw) };
        input_file.write_all(input.as_bytes()).unwrap();
        input_file.seek(SeekFrom::Start(0)).unwrap();
        assert_eq!(unsafe { libc::fcntl(input_file.as_raw_fd(), libc::F_ADD_SEALS,
            libc::F_SEAL_WRITE | libc::F_SEAL_GROW | libc::F_SEAL_SHRINK | libc::F_SEAL_SEAL) }, 0);
        let (channel, peer) = sockets();
        let (control, peer_control) = sockets();
        let peer_high = high(peer.as_raw_fd()); let control_high = high(peer_control.as_raw_fd());
        let image = File::open("/usr/bin/python3").unwrap();
        let digest = executable_digest(&image).unwrap();
        let executable = ExecutablePin::from_lifecycle(image, digest).unwrap();
        let image_high = high(executable.file.as_raw_fd());
        let source = peer_high.as_raw_fd(); let ctl = control_high.as_raw_fd();
        let parent_pid = unsafe { libc::getpid() };
        let mut command = Command::new(format!("/proc/self/fd/{}", image_high.as_raw_fd()));
        command.args(["-I", "-B", "-c", RETIREMENT_PEER])
            .arg(source.to_string()).arg(ctl.to_string()).stdin(Stdio::from(input_file))
            .stdout(Stdio::null()).stderr(Stdio::null());
        unsafe {
            command.pre_exec(move || {
                if libc::fcntl(source, libc::F_SETFD, 0) < 0 || libc::fcntl(ctl, libc::F_SETFD, 0) < 0 ||
                    libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGKILL) < 0 {
                    return Err(io::Error::last_os_error());
                }
                if libc::getppid() != parent_pid { return Err(io::Error::other("owned fixture parent changed")); }
                Ok(())
            });
        }
        let mut child = RetirementOwnedChild(Some(command.spawn().unwrap()));
        drop(peer); drop(peer_control); drop(peer_high); drop(control_high); drop(image_high);
        let (ready, rights) = receive_packet(control.as_raw_fd(), 1,
            &mut Deadline::new(Duration::from_secs(2)).unwrap(), false).unwrap();
        assert_eq!(ready, b"R"); assert!(rights.is_empty());
        // Capture real host/proc/thread identities for the test object. This
        // test-only assembly does not exercise/claim public leader-origin or
        // successful bootstrap admission; retire never opens that barrier.
        let proc_root = open_dir(Path::new("/proc")).unwrap();
        let self_pid = unsafe { libc::getpid() };
        let self_proc = open_at(&proc_root, &self_pid.to_string(), libc::O_RDONLY | libc::O_DIRECTORY | libc::O_NOFOLLOW).unwrap();
        let self_birth = process_birth(&read_at(&self_proc, "stat", MAX_PROC_BYTES).unwrap(), self_pid).unwrap();
        let host_namespaces = NamespacePins::capture(&self_proc).unwrap();
        let host = HostContext { proc_root, cgroup_mount: open_dir(Path::new("/sys/fs/cgroup")).unwrap(),
            self_proc, self_pid, self_birth, host_namespaces };
        host.validate_current_thread().unwrap();
        let running = host.pin_owned_child(child.0.as_mut().unwrap()).unwrap();
        executable.matches(&open_at(&running.proc_dir, "exe", libc::O_RDONLY).unwrap(), true).unwrap();
        let (_, mut ready) = empty_audit_and_status(); ready.state = BootstrapState::Ready;
        let broker = LifecycleBroker { child: child.0.take().unwrap(), running: Some(running), channel,
            executable, host, spec: spec(), layout: BootstrapLayout::HoldingLeafV3, inputs: None,
            attempted: true, latest: Some(ready.clone()), ready: Some(ready), audit: None,
            retirement_requested: false, retirement_seen: false, retirement_poisoned: false, joined: false,
            retired: Arc::new(AtomicBool::new(false)) };
        let fixture = RetirementFixture { broker, control };
        send_packet(fixture.control.as_raw_fd(), b"G", &[],
            &mut Deadline::new(Duration::from_secs(1)).unwrap()).unwrap();
        fixture
    }
    #[test]
    fn retirement_drains_owned_terminal_before_closed_peer_request() {
        for faulted in [false, true] {
            let (mut audit, mut status) = empty_audit_and_status();
            audit.faulted = faulted; status.faulted = faulted;
            if faulted {
                // Keep the codec rejection that exposed the original invalid
                // fixture. Real faulted receipts are always incomplete.
                assert!(matches!(audit.encode(), Err(Error::Reject("pressure retirement audit bounds/state"))));
                audit.incomplete = true;
            }
            let mut owned = retirement_fixture(vec![audit.encode().unwrap().to_vec(), status.encode().to_vec()],
                if faulted { 1 } else { 0 }, false, false);
            owned.wait_exact_exit_without_reaping();
            // Preserve the real old send-first failure without changing the
            // state of the broker: no RETIRE can be delivered to this peer.
            assert!(owned.broker.spec.request_retirement(
                unsafe { BorrowedFd::borrow_raw(owned.broker.channel.as_raw_fd()) }, MAX_LIFECYCLE_IO_TIMEOUT).is_err());
            assert!(owned.broker.retire(MAX_LIFECYCLE_IO_TIMEOUT).unwrap());
            assert!(!owned.broker.retirement_requested);
            assert_eq!(owned.broker.latest_status(), Some(&status));
            assert_eq!(owned.broker.pressure_audit(), Some(&audit));
            assert!(owned.broker.retired.load(Ordering::Acquire));
            assert!(owned.broker.retire(MAX_LIFECYCLE_IO_TIMEOUT).unwrap());
        }
    }
    #[test]
    fn retirement_live_owned_peer_receives_one_exact_request() {
        let (audit, status) = empty_audit_and_status();
        let mut owned = retirement_fixture(vec![audit.encode().unwrap().to_vec(), status.encode().to_vec()], 0, true, false);
        assert!(owned.broker.retire(MAX_LIFECYCLE_IO_TIMEOUT).unwrap());
        assert!(owned.broker.retirement_requested);
        assert_eq!(owned.broker.pressure_audit(), Some(&audit));
        assert_eq!(owned.broker.child.try_wait().unwrap().unwrap().code(), Some(0));
    }
    #[test]
    fn retirement_does_not_promote_dead_unbound_or_incomplete_peer() {
        let (audit, status) = empty_audit_and_status();
        let audit_wire = audit.encode().unwrap().to_vec(); let status_wire = status.encode().to_vec();
        let mut nonce = status.clone(); nonce.nonce[0] ^= 1;
        let mut generation = audit.clone(); generation.authority_generation[0] ^= 1;
        let mut scope = status.clone(); scope.cgroup.inode += 1;
        let mut flags = status.clone(); flags.faulted = true;
        let mut active = status.clone(); active.state = BootstrapState::Active; active.granted = true;
        let cases = [
            ("bare EOF and exact death", vec![], 0),
            ("status without joined audit", vec![status_wire.clone()], 0),
            ("audit without terminal", vec![audit_wire.clone()], 0),
            ("wrong nonce", vec![audit_wire.clone(), nonce.encode().to_vec()], 0),
            ("wrong generation", vec![generation.encode().unwrap().to_vec(), status_wire.clone()], 0),
            ("wrong scope", vec![audit_wire.clone(), scope.encode().to_vec()], 0),
            ("inconsistent flags", vec![audit_wire.clone(), flags.encode().to_vec()], 1),
            ("replayed audit", vec![audit_wire.clone(), audit_wire.clone(), status_wire.clone()], 0),
            ("ACTIVE only then death", vec![active.encode().to_vec()], 0),
            ("exit disagrees with terminal", vec![audit_wire, status_wire], 1),
        ];
        for (label, frames, code) in cases {
            let mut owned = retirement_fixture(frames, code, false, false);
            owned.wait_exact_exit_without_reaping();
            assert!(owned.broker.retire(MAX_LIFECYCLE_IO_TIMEOUT).is_err(), "{label}");
            assert!(!owned.broker.retirement_complete(), "{label}");
            assert!(owned.broker.pressure_audit().is_none(), "{label}");
            assert!(!owned.broker.retired.load(Ordering::Acquire), "{label}");
            assert!(owned.broker.retire(MAX_LIFECYCLE_IO_TIMEOUT).is_err(), "{label}: retry");
            assert!(!owned.broker.retirement_complete(), "{label}: retry");
        }
    }
    #[test]
    fn retirement_terminal_alone_cannot_replace_exact_child_exit() {
        let (audit, status) = empty_audit_and_status();
        let mut owned = retirement_fixture(vec![audit.encode().unwrap().to_vec(), status.encode().to_vec()], 0, false, true);
        assert_eq!(owned.broker.receive_progress(MAX_LIFECYCLE_IO_TIMEOUT).unwrap(), &status);
        assert!(!owned.broker.retire(Duration::from_millis(100)).unwrap());
        assert!(owned.broker.retirement_seen);
        assert!(!owned.broker.retirement_complete());
        assert!(owned.broker.pressure_audit().is_none());
        assert!(!owned.broker.retired.load(Ordering::Acquire));
        owned.release_exit();
        assert!(owned.broker.retire(MAX_LIFECYCLE_IO_TIMEOUT).unwrap());
        assert_eq!(owned.broker.pressure_audit(), Some(&audit));
    }
    #[test]
    fn retirement_cause_diagnostic_preserves_specific_and_lifecycle_reasons() {
        let (_, mut status) = empty_audit_and_status(); status.faulted = true;
        let before = status.clone();
        let reason = "specific rejection".to_owned();
        let outcome: Result<()> = Err(Error::Reject("outer"));
        let mut output = Vec::new();
        report_retirement_cause(&mut output, &status, Some(&reason), outcome.as_ref().err());
        let expected = format!(
            "droidloom-psi-owner: retirement-cause-v1 {{\"schema\":1,\"nonce\":\"{}\",\"authority_generation\":\"{}\",\"cgroup_device\":3,\"cgroup_inode\":4,\"granted\":false,\"faulted\":true,\"relay_reason_utf8_hex\":\"73706563696669632072656a656374696f6e\",\"lifecycle_error_utf8_hex\":\"72656a65637465643a206f75746572\"}}\n",
            "07".repeat(32), "06".repeat(32));
        assert_eq!(String::from_utf8(output).unwrap(), expected);
        assert_eq!(status, before); assert_eq!(reason, "specific rejection");
        assert!(matches!(outcome, Err(Error::Reject("outer"))));
    }
    #[test]
    fn retirement_cause_diagnostic_healthy_is_silent() {
        struct NoWrite;
        impl Write for NoWrite {
            fn write(&mut self, _: &[u8]) -> io::Result<usize> { panic!("healthy diagnostic wrote"); }
            fn flush(&mut self) -> io::Result<()> { panic!("healthy diagnostic flushed"); }
        }
        let (_, status) = empty_audit_and_status();
        report_retirement_cause(&mut NoWrite, &status, None, None);
    }
    #[test]
    fn retirement_cause_diagnostic_encodes_raw_utf8_once() {
        let (_, mut status) = empty_audit_and_status(); status.faulted = true;
        let reason = "line\n原因\t\"";
        let mut output = Vec::new();
        report_retirement_cause(&mut output, &status, Some(reason), None);
        let text = String::from_utf8(output).unwrap();
        assert_eq!(text.bytes().filter(|byte| *byte == b'\n').count(), 1);
        assert!(text.contains("\"relay_reason_utf8_hex\":\"6c696e650ae58e9fe59ba00922\""));
        assert!(text.contains("\"lifecycle_error_utf8_hex\":null"));
        assert!(!text.contains(reason));
    }
    #[test]
    fn retirement_cause_diagnostic_broken_owned_socket_preserves_outcome() {
        let (mut writer, peer) = std::os::unix::net::UnixStream::pair().unwrap();
        drop(peer);
        assert_eq!(writer.write(b"probe").unwrap_err().kind(), io::ErrorKind::BrokenPipe);
        let (_, mut status) = empty_audit_and_status(); status.faulted = true;
        let before = status.clone();
        let reason = "original admission reason".to_owned();
        let outcome: Result<()> = Err(Error::Reject("original lifecycle result"));
        report_retirement_cause(&mut writer, &status, Some(&reason), outcome.as_ref().err());
        assert_eq!(status, before); assert_eq!(reason, "original admission reason");
        assert!(matches!(outcome, Err(Error::Reject("original lifecycle result"))));
    }
    #[test]
    fn producer05_three_second_retirement_is_rejected_before_transport() {
        let (caller, peer) = sockets();
        // Producer05 passed this exact argument to LifecycleBroker::retire.
        // Its first Deadline::new rejects it; the public request path shares
        // that same bound. Preserve the old failure rather than relaxing it.
        let result = spec().request_retirement(
            unsafe { BorrowedFd::borrow_raw(caller.as_raw_fd()) },
            Duration::from_secs(3),
        );
        assert!(matches!(result, Err(Error::Reject("bootstrap I/O bound outside 1..2000 ms"))));
        let mut byte = 0u8;
        assert_eq!(unsafe { libc::recv(peer.as_raw_fd(), (&mut byte as *mut u8).cast(), 1,
            libc::MSG_DONTWAIT) }, -1);
        assert_eq!(io::Error::last_os_error().kind(), io::ErrorKind::WouldBlock);
    }
    #[test]
    fn shared_retirement_bound_sends_exact_request_and_receives_terminal_ack() {
        let (caller, peer) = sockets();
        let request = spec();
        let peer_request = request.clone();
        let (_, expected_ack) = empty_audit_and_status();
        let peer_ack = expected_ack.clone();
        let server = std::thread::spawn(move || {
            let (wire, rights) = receive_packet(peer.as_raw_fd(), RETIRE_SIZE,
                &mut Deadline::new(MAX_LIFECYCLE_IO_TIMEOUT)?, false)?;
            let mut expected = [0; RETIRE_SIZE];
            expected[..8].copy_from_slice(b"P4RET01!");
            put(&mut expected, 8, 1, 4);
            expected[16..48].copy_from_slice(&peer_request.nonce);
            if wire != expected || !rights.is_empty() {
                return Err(Error::Reject("ordinary retirement control received a different request"));
            }
            send_packet(peer.as_raw_fd(), &peer_ack.encode(), &[],
                &mut Deadline::new(MAX_LIFECYCLE_IO_TIMEOUT)?)
            // Closing peer after the real send also covers terminal POLLIN+HUP.
        });
        let actual = request.request_retirement(
            unsafe { BorrowedFd::borrow_raw(caller.as_raw_fd()) }, MAX_LIFECYCLE_IO_TIMEOUT,
        ).and_then(|()| request.receive_status(
            unsafe { BorrowedFd::borrow_raw(caller.as_raw_fd()) }, MAX_LIFECYCLE_IO_TIMEOUT,
        ));
        // Join the bounded real peer even when the caller path fails.
        let peer_result = server.join();
        peer_result.unwrap().unwrap();
        assert_eq!(actual.unwrap(), expected_ack);
    }
    #[test]
    fn audit_and_terminal_packet_survive_peer_close_with_exact_framing() {
        let (send, receive) = sockets(); let (audit, status) = empty_audit_and_status();
        send_packet(send.as_raw_fd(), &audit.encode().unwrap(), &[], &mut Deadline::new(Duration::from_secs(1)).unwrap()).unwrap();
        send_packet(send.as_raw_fd(), &status.encode(), &[], &mut Deadline::new(Duration::from_secs(1)).unwrap()).unwrap();
        drop(send);
        match receive_progress_frame(receive.as_raw_fd(), &mut Deadline::new(Duration::from_secs(1)).unwrap()).unwrap() {
            ProgressFrame::Audit(actual) => assert_eq!(actual, audit),
            ProgressFrame::Status(_) => panic!("audit packet was confused with terminal status"),
        }
        match receive_progress_frame(receive.as_raw_fd(), &mut Deadline::new(Duration::from_secs(1)).unwrap()).unwrap() {
            ProgressFrame::Status(actual) => assert_eq!(actual, status),
            ProgressFrame::Audit(_) => panic!("terminal status was confused with audit"),
        }
        assert!(receive_progress_frame(receive.as_raw_fd(), &mut Deadline::new(Duration::from_secs(1)).unwrap()).is_err());
    }
    #[test]
    fn progress_audit_rejects_and_closes_unexpected_rights() {
        let (send, receive) = sockets(); let (audit, _) = empty_audit_and_status();
        let mut pipe = [-1; 2]; assert_eq!(unsafe { libc::pipe2(pipe.as_mut_ptr(), libc::O_CLOEXEC | libc::O_NONBLOCK) }, 0);
        let (reader, writer) = unsafe { (OwnedFd::from_raw_fd(pipe[0]), OwnedFd::from_raw_fd(pipe[1])) };
        send_packet(send.as_raw_fd(), &audit.encode().unwrap(), &[writer.as_raw_fd(); RIGHTS],
            &mut Deadline::new(Duration::from_secs(1)).unwrap()).unwrap();
        drop(writer);
        assert!(receive_progress_frame(receive.as_raw_fd(), &mut Deadline::new(Duration::from_secs(1)).unwrap()).is_err());
        let mut byte = 0u8;
        assert_eq!(unsafe { libc::read(reader.as_raw_fd(), (&mut byte as *mut u8).cast(), 1) }, 0);
    }
    #[test]
    fn bootstrap_codec_is_fixed_and_rejects_reserved_policy() {
        let s = spec(); let wire = s.encode().unwrap(); assert_eq!(BootstrapSpec::decode(&wire).unwrap(), s);
        for at in [0, 8, 20, 23, 120, 127] {
            let mut malformed = wire; malformed[at] ^= 1; assert!(BootstrapSpec::decode(&malformed).is_err());
        }
        assert!(BootstrapSpec::decode(&wire[..127]).is_err());
        let mut s = s; s.uid = 0; assert!(s.encode().is_err());
    }
    #[test]
    fn holding_bootstrap_version_is_explicit_and_never_falls_back() {
        let s = spec();
        let legacy = s.encode().unwrap();
        let holding = s.encode_with_layout(BootstrapLayout::HoldingLeafV3).unwrap();
        assert_eq!(&legacy[..8], b"P4BOOT1!");
        assert_eq!(number(&legacy, 8, 4), 1);
        assert_eq!(number(&legacy, 20, 4), 0);
        assert_eq!(&holding[..8], b"P4BOOT2!");
        assert_eq!(number(&holding, 8, 4), 2);
        assert_eq!(number(&holding, 20, 4), 3);
        assert_eq!(BootstrapSpec::decode_with_layout(&holding).unwrap(), (s.clone(), BootstrapLayout::HoldingLeafV3));
        assert_eq!(BootstrapSpec::decode_with_layout(&legacy).unwrap(), (s, BootstrapLayout::ProjectedRootV1));
        // The old owned-child reader cannot silently reinterpret ABI3 input.
        assert!(BootstrapSpec::decode(&holding).is_err());
        for (version, layout) in [(1, 3), (2, 0), (2, 1), (2, 2), (3, 3), (2, u32::MAX)] {
            let mut wrong = holding;
            put(&mut wrong, 8, version as u64, 4); put(&mut wrong, 20, layout as u64, 4);
            assert!(BootstrapSpec::decode_with_layout(&wrong).is_err());
        }
        let mut wrong = legacy; put(&mut wrong, 20, 3, 4);
        assert!(BootstrapSpec::decode_with_layout(&wrong).is_err());
        for at in [0, 120, 127] {
            let mut wrong = holding; wrong[at] ^= 1;
            assert!(BootstrapSpec::decode_with_layout(&wrong).is_err());
        }
        assert!(BootstrapSpec::decode_with_layout(&holding[..127]).is_err());
    }
    #[test]
    fn holding_bootstrap_membership_requires_the_exact_init_slot() {
        exact_holding_membership("", "17\n", 17).unwrap();
        for (root, leaf, pid) in [("17\n", "17\n", 17), ("\n", "17\n", 17),
            ("", "", 17), ("", "18\n", 17), ("", "17\n18\n", 17),
            ("", "17\n17\n", 17), ("", "017\n", 17), ("", "17", 17),
            ("", "17\n", 0), ("", "17\n", -1)] {
            assert!(exact_holding_membership(root, leaf, pid).is_err());
        }
    }
    #[test]
    fn holding_packet_rejects_legacy_owned_child_receiver_and_closes_rights() {
        let (send, receive) = sockets();
        let mut pipe = [-1; 2];
        assert_eq!(unsafe { libc::pipe2(pipe.as_mut_ptr(), libc::O_CLOEXEC | libc::O_NONBLOCK) }, 0);
        let (reader, writer) = unsafe { (OwnedFd::from_raw_fd(pipe[0]), OwnedFd::from_raw_fd(pipe[1])) };
        let handles: [BorrowedFd<'_>; RIGHTS] = std::array::from_fn(|_| unsafe { BorrowedFd::borrow_raw(writer.as_raw_fd()) });
        spec().send_with_layout(unsafe { BorrowedFd::borrow_raw(send.as_raw_fd()) }, &handles,
            Duration::from_secs(1), BootstrapLayout::HoldingLeafV3).unwrap();
        drop(writer);
        assert!(spec().receive_from_owned_child(unsafe { BorrowedFd::borrow_raw(receive.as_raw_fd()) },
            Duration::from_secs(1)).is_err());
        let mut byte = 0u8;
        assert_eq!(unsafe { libc::read(reader.as_raw_fd(), (&mut byte as *mut u8).cast(), 1) }, 0);
    }
    #[test]
    fn inherited_rights_are_cloexec_and_owned_on_reject() {
        let (send, receive) = sockets();
        let mut pipe = [-1; 2]; assert_eq!(unsafe { libc::pipe2(pipe.as_mut_ptr(), libc::O_CLOEXEC | libc::O_NONBLOCK) }, 0);
        let (reader, writer) = unsafe { (OwnedFd::from_raw_fd(pipe[0]), OwnedFd::from_raw_fd(pipe[1])) };
        send_packet(send.as_raw_fd(), &spec().encode().unwrap(), &[writer.as_raw_fd(); RIGHTS],
            &mut Deadline::new(Duration::from_secs(1)).unwrap()).unwrap();
        let (_, rights) = receive_packet(receive.as_raw_fd(), BOOT_SIZE,
            &mut Deadline::new(Duration::from_secs(1)).unwrap(), false).unwrap();
        assert_eq!(rights.len(), RIGHTS);
        let numbers: Vec<_> = rights.iter().map(AsRawFd::as_raw_fd).collect();
        for fd in &numbers { assert_ne!(unsafe { libc::fcntl(*fd, libc::F_GETFD) } & libc::FD_CLOEXEC, 0); }
        drop(writer); drop(rights);
        let mut byte = 0u8;
        // EOF proves every transferred writer is closed, without racing
        // unrelated parallel tests that may reuse numeric FD slots.
        assert_eq!(unsafe { libc::read(reader.as_raw_fd(), (&mut byte as *mut u8).cast(), 1) }, 0);
    }
    #[test]
    fn bootstrap_parent_channel_rejects_extra_rights_and_old_nonce_commands() {
        let s = spec();
        let mut wire = [0; RETIRE_SIZE]; wire[..8].copy_from_slice(b"P4RET01!"); put(&mut wire, 8, 1, 4);
        wire[16..].copy_from_slice(&s.nonce); assert!(valid_retirement(&wire, &s));
        wire[16] ^= 1; assert!(!valid_retirement(&wire, &s));
        let (send, receive) = sockets();
        send_packet(send.as_raw_fd(), &[0; STATUS_SIZE], &[send.as_raw_fd()],
            &mut Deadline::new(Duration::from_secs(1)).unwrap()).unwrap();
        assert!(s.receive_status(unsafe { BorrowedFd::borrow_raw(receive.as_raw_fd()) }, Duration::from_secs(1)).is_err());
    }
    #[test]
    fn malformed_packet_closes_all_transferred_rights() {
        let (send, receive) = sockets();
        let mut pipe = [-1; 2]; assert_eq!(unsafe { libc::pipe2(pipe.as_mut_ptr(), libc::O_CLOEXEC | libc::O_NONBLOCK) }, 0);
        let (reader, writer) = unsafe { (OwnedFd::from_raw_fd(pipe[0]), OwnedFd::from_raw_fd(pipe[1])) };
        send_packet(send.as_raw_fd(), &[0; BOOT_SIZE + 1], &[writer.as_raw_fd(); RIGHTS],
            &mut Deadline::new(Duration::from_secs(1)).unwrap()).unwrap();
        drop(writer);
        assert!(receive_packet(receive.as_raw_fd(), BOOT_SIZE,
            &mut Deadline::new(Duration::from_secs(1)).unwrap(), false).is_err());
        let mut byte = 0u8;
        assert_eq!(unsafe { libc::read(reader.as_raw_fd(), (&mut byte as *mut u8).cast(), 1) }, 0);
    }
    #[test]
    fn terminal_status_survives_peer_close_but_never_certifies_pressure() {
        let (send, receive) = sockets();
        let s = spec(); let mut budget = [0; 32]; put(&mut budget, 0, 512 * 1024 * 1024, 8);
        put(&mut budget, 24, 1, 4); put(&mut budget, 28, 1, 4);
        let status = BootstrapStatus { state: BootstrapState::Retired, nonce: s.nonce, generation: [6; 32],
            endpoint: FileId { device: 1, inode: 2 }, cgroup: FileId { device: 3, inode: 4 }, budget,
            granted: false, faulted: true };
        send_packet(send.as_raw_fd(), &status.encode(), &[], &mut Deadline::new(Duration::from_secs(1)).unwrap()).unwrap();
        drop(send);
        assert_eq!(s.receive_status(unsafe { BorrowedFd::borrow_raw(receive.as_raw_fd()) }, Duration::from_secs(1)).unwrap(), status);
        assert!(s.receive_status(unsafe { BorrowedFd::borrow_raw(receive.as_raw_fd()) }, Duration::from_secs(1)).is_err());
    }
}
