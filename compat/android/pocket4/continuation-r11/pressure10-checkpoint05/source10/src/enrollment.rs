// Copyright 2026 Droidloom contributors; SPDX-License-Identifier: Apache-2.0
//! One bounded request, authenticated against existing lifecycle authority,
//! and one SCM_RIGHTS grant of packet recipients. Real PSI FDs stay in host.
//! A failed send retains the owner for explicit, verified retirement.
use super::*;
use std::mem::size_of_val;

const REQUEST_SIZE: usize = 144;
const GRANT_SIZE: usize = 176;
const MAX_MONITORS: usize = 2;
const BAD_POLL: libc::c_short = libc::POLLERR | libc::POLLHUP | libc::POLLRDHUP | libc::POLLNVAL;

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct EnrollmentRequest {
    pub nonce: [u8; 32],
    pub cgroup: FileId,
    pub budget: [u8; 32],
    pub configs: Vec<PressureConfig>,
}

fn number(bytes: &[u8], offset: usize, length: usize) -> u64 {
    let mut value = [0u8; 8];
    value[..length].copy_from_slice(&bytes[offset..offset + length]);
    u64::from_le_bytes(value)
}
fn put(bytes: &mut [u8], offset: usize, value: u64, length: usize) {
    bytes[offset..offset + length].copy_from_slice(&value.to_le_bytes()[..length]);
}
pub(super) fn valid_budget(budget: &[u8; 32]) -> bool {
    let maximum = number(budget, 0, 8);
    let high = number(budget, 8, 8);
    let swap = number(budget, 16, 8);
    let flags = number(budget, 24, 4);
    number(budget, 28, 4) == 1 && flags <= 3 && maximum > 0 && maximum <= i64::MAX as u64 &&
        swap <= i64::MAX as u64 &&
        (if flags & 1 != 0 { high == 0 } else { high > 0 && high <= maximum }) &&
        (flags & 2 == 0 || swap == 0)
}
impl EnrollmentRequest {
    pub fn validate(&self) -> Result<()> {
        if self.nonce == [0; 32] || self.cgroup.device == 0 || self.cgroup.inode == 0 ||
            !valid_budget(&self.budget) || self.configs.is_empty() || self.configs.len() > MAX_MONITORS {
            return Err(Error::Reject("invalid enrollment nonce/scope/monitor count"));
        }
        for config in &self.configs { config.exact_trigger()?; }
        if self.configs.len() == 2 && self.configs[0].level == self.configs[1].level {
            return Err(Error::Reject("duplicate enrollment monitor level"));
        }
        Ok(())
    }
    pub fn decode(wire: &[u8]) -> Result<Self> {
        if wire.len() != REQUEST_SIZE || &wire[..8] != b"P4ENR01!" || number(wire, 8, 4) != 1 {
            return Err(Error::Reject("enrollment wire size/magic/version"));
        }
        let count = number(wire, 12, 4) as usize;
        if !(1..=MAX_MONITORS).contains(&count) { return Err(Error::Reject("enrollment monitor count")); }
        let mut nonce = [0u8; 32]; nonce.copy_from_slice(&wire[16..48]);
        let cgroup = FileId { device: number(wire, 48, 8), inode: number(wire, 56, 8) };
        let mut budget = [0u8; 32]; budget.copy_from_slice(&wire[64..96]);
        let mut configs = Vec::with_capacity(count);
        for index in 0..MAX_MONITORS {
            let at = 96 + 24 * index;
            if index >= count {
                if wire[at..at + 24].iter().any(|b| *b != 0) { return Err(Error::Reject("nonzero unused monitor slot")); }
                continue;
            }
            if number(wire, at + 4, 4) != 0 { return Err(Error::Reject("nonzero enrollment reserved field")); }
            let level = match number(wire, at, 4) {
                1 => PressureLevel::Medium, 2 => PressureLevel::Critical,
                _ => return Err(Error::Reject("unknown enrollment monitor level")),
            };
            configs.push(PressureConfig { level, window_us: number(wire, at + 8, 8), stall_us: number(wire, at + 16, 8) });
        }
        let request = Self { nonce, cgroup, budget, configs };
        request.validate()?;
        Ok(request)
    }
    pub fn encode(&self) -> Result<[u8; REQUEST_SIZE]> {
        self.validate()?;
        let mut wire = [0u8; REQUEST_SIZE]; wire[..8].copy_from_slice(b"P4ENR01!");
        put(&mut wire, 8, 1, 4); put(&mut wire, 12, self.configs.len() as u64, 4);
        wire[16..48].copy_from_slice(&self.nonce);
        put(&mut wire, 48, self.cgroup.device, 8); put(&mut wire, 56, self.cgroup.inode, 8);
        wire[64..96].copy_from_slice(&self.budget);
        encode_configs(&mut wire, 96, &self.configs);
        Ok(wire)
    }
    fn matches_authority(&self, authority: &CellAuthority) -> Result<()> {
        self.validate()?;
        let scope = authority.scope_request();
        if self.cgroup != scope.cgroup || self.budget != scope.budget {
            return Err(Error::Reject("enrollment request is not the held cell scope/budget"));
        }
        Ok(())
    }
}
fn encode_configs(wire: &mut [u8], offset: usize, configs: &[PressureConfig]) {
    for (index, config) in configs.iter().enumerate() {
        let at = offset + 24 * index;
        put(wire, at, match config.level { PressureLevel::Medium => 1, PressureLevel::Critical => 2 }, 4);
        put(wire, at + 8, config.window_us, 8); put(wire, at + 16, config.stall_us, 8);
    }
}
fn encode_grant(request: &EnrollmentRequest, generation: &[u8; 32]) -> Result<[u8; GRANT_SIZE]> {
    request.validate()?;
    if generation == &[0; 32] { return Err(Error::Reject("retired grant generation")); }
    let mut wire = [0u8; GRANT_SIZE]; wire[..8].copy_from_slice(b"P4ENG01!");
    put(&mut wire, 8, 1, 4); put(&mut wire, 12, request.configs.len() as u64, 4);
    wire[16..48].copy_from_slice(&request.nonce); wire[48..80].copy_from_slice(generation);
    put(&mut wire, 80, request.cgroup.device, 8); put(&mut wire, 88, request.cgroup.inode, 8);
    wire[96..128].copy_from_slice(&request.budget);
    encode_configs(&mut wire, 128, &request.configs);
    Ok(wire)
}

fn monotonic() -> Result<u64> {
    let mut t: libc::timespec = unsafe { zeroed() };
    if unsafe { libc::clock_gettime(libc::CLOCK_MONOTONIC, &mut t) } != 0 || t.tv_sec < 0 || !(0..1_000_000_000).contains(&t.tv_nsec) {
        return Err(Error::Reject("enrollment monotonic clock unavailable"));
    }
    (t.tv_sec as u64).checked_mul(1_000_000_000).and_then(|x| x.checked_add(t.tv_nsec as u64))
        .filter(|x| *x != 0).ok_or(Error::Reject("enrollment monotonic clock overflow"))
}
struct Deadline { start: u64, end: u64, last: u64 }
impl Deadline {
    fn new(timeout: Duration) -> Result<Self> {
        let duration = u64::try_from(timeout.as_nanos()).map_err(|_| Error::Reject("enrollment timeout overflow"))?;
        if !(1_000_000..=2_000_000_000).contains(&duration) { return Err(Error::Reject("enrollment handshake bound outside 1..2000 ms")); }
        let start = monotonic()?;
        let end = start.checked_add(duration).ok_or(Error::Reject("enrollment deadline overflow"))?;
        Ok(Self { start, end, last: start })
    }
    fn check(&mut self) -> Result<()> {
        let now = monotonic()?;
        if now < self.start || now < self.last || now >= self.end { return Err(Error::Reject("enrollment deadline/clock failed")); }
        self.last = now;
        Ok(())
    }
    fn wait(&mut self, fd: RawFd, wanted: libc::c_short) -> Result<()> {
        loop {
            self.check()?;
            let timeout = ((self.end - self.last).div_ceil(1_000_000).min(100)) as libc::c_int;
            let mut p = libc::pollfd { fd, events: wanted | libc::POLLRDHUP, revents: 0 };
            let rc = unsafe { libc::poll(&mut p, 1, timeout) };
            if rc < 0 && io::Error::last_os_error().kind() == io::ErrorKind::Interrupted { continue; }
            if rc < 0 { return Err(err("poll enrollment handshake")); }
            if p.revents & BAD_POLL != 0 { return Err(Error::Reject("enrollment control disconnected")); }
            self.check()?;
            if p.revents & wanted != 0 { return Ok(()); }
        }
    }
}

// Request packets never carry authority FDs. Close every received SCM_RIGHTS
// descriptor, including visible descriptors in a truncated ancillary buffer.
fn close_unexpected_rights(message: &libc::msghdr) -> bool {
    let mut any = false;
    let mut header = unsafe { libc::CMSG_FIRSTHDR(message) };
    while !header.is_null() {
        any = true;
        let h = unsafe { &*header };
        let base = unsafe { libc::CMSG_LEN(0) } as usize;
        if h.cmsg_level == libc::SOL_SOCKET && h.cmsg_type == libc::SCM_RIGHTS && h.cmsg_len >= base {
            let count = (h.cmsg_len - base) / size_of::<RawFd>();
            let data = unsafe { libc::CMSG_DATA(header) };
            for i in 0..count {
                let fd = unsafe { std::ptr::read_unaligned(data.add(i * size_of::<RawFd>()).cast::<RawFd>()) };
                unsafe { libc::close(fd) };
            }
        }
        header = unsafe { libc::CMSG_NXTHDR(message, header) };
    }
    any
}
fn receive_request(connection: &AcceptedConnection, deadline: &mut Deadline) -> Result<EnrollmentRequest> {
    loop {
        deadline.wait(connection.socket.as_raw_fd(), libc::POLLIN)?;
        let mut wire = [0u8; REQUEST_SIZE];
        let mut control = [0 as libc::c_long; 16];
        let mut payload = libc::iovec { iov_base: wire.as_mut_ptr().cast(), iov_len: wire.len() };
        let mut message: libc::msghdr = unsafe { zeroed() };
        message.msg_iov = &mut payload; message.msg_iovlen = 1;
        message.msg_control = control.as_mut_ptr().cast(); message.msg_controllen = size_of_val(&control);
        let count = unsafe { libc::recvmsg(connection.socket.as_raw_fd(), &mut message, libc::MSG_DONTWAIT | libc::MSG_CMSG_CLOEXEC | libc::MSG_TRUNC) };
        if count < 0 && io::Error::last_os_error().kind() == io::ErrorKind::WouldBlock { continue; }
        if count < 0 { return Err(err("receive enrollment request")); }
        let unexpected = close_unexpected_rights(&message);
        if unexpected || message.msg_flags & libc::MSG_CTRUNC != 0 { return Err(Error::Reject("enrollment request carried ancillary authority")); }
        if count as usize != REQUEST_SIZE || message.msg_flags & libc::MSG_TRUNC != 0 { return Err(Error::Reject("enrollment request size")); }
        let request = EnrollmentRequest::decode(&wire)?;
        deadline.check()?;
        return Ok(request);
    }
}

/// The original authenticator still requires a quiet control connection. Read
/// exactly the finite request first, then authenticate its kernel connection;
/// extra queued messages are rejected by the unchanged no-extra-data guard.
impl HostContext {
    pub fn admit_enrollment(self: &Arc<Self>, connection: AcceptedConnection,
        authority: Arc<CellAuthority>, timeout: Duration) -> Result<PendingGrant> {
        let mut deadline = Deadline::new(timeout)?;
        let request = receive_request(&connection, &mut deadline)?;
        request.matches_authority(&authority)?;
        let peer = self.authenticate(connection, &authority)?;
        deadline.check()?;
        // A validated process gets one enrollment attempt per lifecycle
        // authority, including failed PSI registration or grant delivery.
        // Arc clones and concurrent listeners share the same terminal latch.
        authority.enrollment_attempted.claim()?;
        let registered = LeaseOwner::register(peer, Arc::clone(self), Arc::clone(&authority),
            authority.scope_request(), &request.configs)?;
        Ok(PendingGrant { registered, request, deadline, attempted: false, delivered: false })
    }
}

pub struct PendingGrant {
    registered: RegisteredLease,
    request: EnrollmentRequest,
    deadline: Deadline,
    attempted: bool,
    delivered: bool,
}
impl PendingGrant {
    pub fn registration_audit(&self) -> RegistrationAudit { self.registered.audit }
    pub fn owner(&mut self) -> &mut LeaseOwner { &mut self.registered.owner }
    pub fn request(&self) -> &EnrollmentRequest { &self.request }
    pub fn delivered(&self) -> bool { self.delivered }
    // A send failure/uncertain late result invalidates the lease and keeps the
    // owning handle here. The lifecycle caller MUST finish_retirement and
    // require actual completion before replacing this owner or cell generation.
    pub fn send_once(&mut self, host: &HostContext, authority: &CellAuthority) -> Result<()> {
        if self.attempted {
            self.registered.owner.retire();
            return Err(Error::Reject("enrollment grant is one attempt only"));
        }
        self.attempted = true;
        let result = (|| {
            self.deadline.check()?;
            self.request.matches_authority(authority)?;
            self.registered.owner.refresh(host, authority)?;
            let fd = self.registered.owner.peer.as_ref().ok_or(Error::Reject("grant peer disappeared"))?.connection.socket.as_raw_fd();
            let wire = encode_grant(&self.request, &self.registered.owner.generation())?;
            if self.registered.recipients.len() != self.request.configs.len() { return Err(Error::Reject("registered recipient count differs")); }
            loop {
                self.deadline.wait(fd, libc::POLLOUT)?;
                self.registered.owner.refresh(host, authority)?;
                self.deadline.check()?;
                match send_rights(fd, &wire, &self.registered.recipients) {
                    Ok(()) => break,
                    Err(Error::Io(_, ref error)) if error.kind() == io::ErrorKind::WouldBlock => continue,
                    Err(error) => return Err(error),
                }
            }
            self.registered.owner.refresh(host, authority)?;
            self.deadline.check()?;
            Ok(())
        })();
        // The host never keeps a temporary duplicate of the recipient after
        // the single send. Only its sender/PSI ownership remains in the worker.
        self.registered.recipients.clear();
        if result.is_err() { self.registered.owner.retire(); }
        else { self.delivered = true; }
        result
    }
}
fn send_rights(fd: RawFd, wire: &[u8; GRANT_SIZE], recipients: &[OwnedFd]) -> Result<()> {
    if recipients.is_empty() || recipients.len() > MAX_MONITORS { return Err(Error::Reject("grant recipient bound")); }
    let mut control = [0 as libc::c_long; 8];
    let mut payload = libc::iovec { iov_base: wire.as_ptr() as *mut libc::c_void, iov_len: wire.len() };
    let mut message: libc::msghdr = unsafe { zeroed() };
    message.msg_iov = &mut payload; message.msg_iovlen = 1;
    message.msg_control = control.as_mut_ptr().cast();
    message.msg_controllen = unsafe { libc::CMSG_SPACE((recipients.len() * size_of::<RawFd>()) as libc::c_uint) } as usize;
    let header = unsafe { libc::CMSG_FIRSTHDR(&message) };
    if header.is_null() || message.msg_controllen > size_of_val(&control) { return Err(Error::Reject("grant ancillary bound")); }
    unsafe {
        (*header).cmsg_level = libc::SOL_SOCKET; (*header).cmsg_type = libc::SCM_RIGHTS;
        (*header).cmsg_len = libc::CMSG_LEN((recipients.len() * size_of::<RawFd>()) as libc::c_uint) as usize;
        let data = libc::CMSG_DATA(header);
        for (index, recipient) in recipients.iter().enumerate() {
            std::ptr::write_unaligned(data.add(index * size_of::<RawFd>()).cast::<RawFd>(), recipient.as_raw_fd());
        }
    }
    let sent = unsafe { libc::sendmsg(fd, &message, libc::MSG_DONTWAIT | libc::MSG_NOSIGNAL) };
    if sent < 0 { return Err(err("send enrollment SCM_RIGHTS grant")); }
    if sent as usize != wire.len() { return Err(Error::Reject("short enrollment grant")); }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    fn golden(hex: &str) -> Vec<u8> {
        let text = hex.trim();
        assert_eq!(text.len() % 2, 0);
        (0..text.len()).step_by(2).map(|i| u8::from_str_radix(&text[i..i + 2], 16).unwrap()).collect()
    }
    fn request() -> EnrollmentRequest {
        EnrollmentRequest { nonce: [0x31; 32], cgroup: FileId { device: 13, inode: 17 },
            budget: Budget { maximum: 64 * 1024 * 1024, high: Some(24 * 1024 * 1024), swap_maximum: Some(0) }.canonical(),
            configs: vec![PressureConfig { level: PressureLevel::Medium, window_us: 1_000_000, stall_us: 70_000 },
                          PressureConfig { level: PressureLevel::Critical, window_us: 1_000_000, stall_us: 70_000 }] }
    }
    #[test]
    fn cross_language_wire_vectors_and_exact_contract() {
        let r = request(); let encoded = r.encode().unwrap();
        assert_eq!(encoded.as_slice(), golden(include_str!("../tests/data/request.hex")));
        assert_eq!(encode_grant(&r, &[0x51; 32]).unwrap().as_slice(), golden(include_str!("../tests/data/grant.hex")));
        assert_eq!(EnrollmentRequest::decode(&encoded).unwrap(), r);
        for offset in [0usize, 8, 100, 124] {
            let mut bad = encoded; bad[offset] ^= 1;
            assert!(EnrollmentRequest::decode(&bad).is_err(), "offset {offset}");
        }
        let mut one = r.clone(); one.configs.truncate(1);
        let mut unused = one.encode().unwrap(); unused[120] = 2;
        assert!(EnrollmentRequest::decode(&unused).is_err());
        let mut duplicate = r.clone(); duplicate.configs[1] = duplicate.configs[0]; assert!(duplicate.validate().is_err());
        for bad in [0u64, 499_999, 10_000_001] { let mut changed = r.clone(); changed.configs[0].window_us = bad; assert!(changed.validate().is_err()); }
        let mut zero = r.clone(); zero.nonce.fill(0); assert!(zero.validate().is_err());
        assert!(EnrollmentRequest::decode(&encoded[..143]).is_err());
        assert!(encode_grant(&r, &[0; 32]).is_err());
    }
    #[test]
    fn request_rights_are_closed_before_admission() {
        let mut control = [-1; 2]; let mut transferred = [-1; 2];
        assert_eq!(unsafe { libc::socketpair(libc::AF_UNIX, libc::SOCK_SEQPACKET | libc::SOCK_NONBLOCK | libc::SOCK_CLOEXEC, 0, control.as_mut_ptr()) }, 0);
        assert_eq!(unsafe { libc::pipe2(transferred.as_mut_ptr(), libc::O_CLOEXEC | libc::O_NONBLOCK) }, 0);
        let sender = unsafe { OwnedFd::from_raw_fd(control[0]) };
        let receiver = AcceptedConnection { socket: unsafe { OwnedFd::from_raw_fd(control[1]) } };
        let read_end = unsafe { OwnedFd::from_raw_fd(transferred[0]) };
        let write_end = unsafe { OwnedFd::from_raw_fd(transferred[1]) };
        // Use real kernel SCM_RIGHTS delivery; the request carries a descriptor
        // even though its 144-byte body is otherwise valid.
        let wire = request().encode().unwrap(); let raw_fd = write_end.as_raw_fd();
        let mut bytes = [0 as libc::c_long; 8];
        let mut io = libc::iovec { iov_base: wire.as_ptr() as *mut libc::c_void, iov_len: wire.len() };
        let mut message: libc::msghdr = unsafe { zeroed() };
        message.msg_iov = &mut io; message.msg_iovlen = 1; message.msg_control = bytes.as_mut_ptr().cast();
        message.msg_controllen = unsafe { libc::CMSG_SPACE(size_of::<RawFd>() as libc::c_uint) } as usize;
        unsafe {
            let h = libc::CMSG_FIRSTHDR(&message); (*h).cmsg_level = libc::SOL_SOCKET; (*h).cmsg_type = libc::SCM_RIGHTS;
            (*h).cmsg_len = libc::CMSG_LEN(size_of::<RawFd>() as libc::c_uint) as usize;
            std::ptr::write_unaligned(libc::CMSG_DATA(h).cast::<RawFd>(), raw_fd);
        }
        assert_eq!(unsafe { libc::sendmsg(sender.as_raw_fd(), &message, libc::MSG_NOSIGNAL) }, REQUEST_SIZE as isize);
        drop(write_end);
        let mut deadline = Deadline::new(Duration::from_millis(100)).unwrap();
        assert!(receive_request(&receiver, &mut deadline).is_err());
        let mut byte = 0u8;
        assert_eq!(unsafe { libc::read(read_end.as_raw_fd(), (&mut byte as *mut u8).cast(), 1) }, 0, "rejected authority FD leaked");
    }
}
