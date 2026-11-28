//! One owned, nonblocking task-control session. The connector's actual exit is
//! established before Hello; every reply carries a real kernel sender PIDFD.
//! No public FD/path/PID constructor, reconnect, background worker or fallback.
use super::*;
use crate::production_namespace::{TaskControlEndpoint, TaskControlPeer};
use crate::production_selection::early_generation::{
    EarlyApplicationAuthority, EarlyTaskControlEndpoint, EarlyTaskControlPeer,
};
use droidloom_task_control::{
    ControlRequest, ControlResponse, MAX_RECORD_BYTES, PROTOCOL_MAJOR, decode_response,
    encode_request,
};
use std::mem;
use std::os::fd::{AsRawFd, FromRawFd, IntoRawFd, OwnedFd};
use std::time::Instant;

const SO_PASSPIDFD: i32 = 76;
const SCM_PIDFD: i32 = 4;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum Phase {
    Hello,
    Register,
    Bound,
    Failed,
}

pub(crate) struct ApplicationTaskControl {
    socket: File,
    endpoint: Endpoint,
    composer: Option<Peer>,
    package: String,
    deadline: Instant,
    phase: Phase,
    receipt: BridgeReceipt,
}

fn socket_option(socket: &File, option: i32, expected: i32) -> Result<()> {
    let mut value = 0_i32;
    let mut size = mem::size_of::<i32>() as libc::socklen_t;
    if unsafe {
        libc::getsockopt(
            socket.as_raw_fd(),
            libc::SOL_SOCKET,
            option,
            (&mut value as *mut i32).cast(),
            &mut size,
        )
    } != 0
    {
        return Err(io::Error::last_os_error().into());
    }
    require(
        size as usize == mem::size_of::<i32>() && value == expected,
        "task-control socket contract differs",
    )
}

fn socket_shape(socket: &File) -> Result<()> {
    for (key, value) in [
        (libc::SO_TYPE, libc::SOCK_SEQPACKET),
        (libc::SO_DOMAIN, libc::AF_UNIX),
        (libc::SO_ACCEPTCONN, 0),
        (libc::SO_PASSCRED, 1),
        (SO_PASSPIDFD, 1),
    ] {
        socket_option(socket, key, value)?;
    }
    let flags = unsafe { libc::fcntl(socket.as_raw_fd(), libc::F_GETFL) };
    let fd_flags = unsafe { libc::fcntl(socket.as_raw_fd(), libc::F_GETFD) };
    require(
        flags >= 0
            && fd_flags >= 0
            && flags & libc::O_NONBLOCK != 0
            && fd_flags & libc::FD_CLOEXEC != 0,
        "task-control connection must be nonblocking and CLOEXEC",
    )?;
    let mut name: libc::sockaddr_un = unsafe { mem::zeroed() };
    let mut size = mem::size_of_val(&name) as libc::socklen_t;
    if unsafe {
        libc::getpeername(
            socket.as_raw_fd(),
            (&mut name as *mut libc::sockaddr_un).cast(),
            &mut size,
        )
    } != 0
    {
        return Err(io::Error::last_os_error().into());
    }
    let expected = b"/dev/socket/droidloom-task-control\0";
    let offset = mem::offset_of!(libc::sockaddr_un, sun_path);
    let actual_size = size as usize;
    require(
        name.sun_family == libc::AF_UNIX as libc::sa_family_t
            && (offset + expected.len()..=mem::size_of_val(&name)).contains(&actual_size)
            && name.sun_path[..expected.len()]
                .iter()
                .map(|v| *v as u8)
                .eq(expected.iter().copied())
            && name.sun_path[expected.len()..actual_size - offset]
                .iter()
                .all(|v| *v == 0),
        "task-control peer is not the fixed Android init endpoint",
    )
}

// This sum type has only the two actual source-owned capabilities. A caller
// cannot supply a path, PID or serialized endpoint, and kinds cannot be mixed.
#[derive(Clone, Copy)]
enum Authority<'borrow, 'owner> {
    Legacy(&'borrow ApplicationAuthority<'owner>),
    Early(&'borrow EarlyApplicationAuthority<'owner>),
}
impl<'borrow, 'owner> Authority<'borrow, 'owner> {
    fn worker(self) -> &'borrow dyn ApplicationWorkerAuthority {
        match self {
            Self::Legacy(a) => a,
            Self::Early(a) => a,
        }
    }
    fn task_control_endpoint(self, deadline: Instant) -> Result<Endpoint> {
        match self {
            Self::Legacy(a) => a
                .task_control_endpoint(deadline)
                .map(Endpoint::Legacy)
                .map_err(external),
            Self::Early(a) => a
                .task_control_endpoint(deadline)
                .map(Endpoint::Early)
                .map_err(external),
        }
    }
    fn progress_inherited_native(self, deadline: Instant) -> Result<()> {
        self.worker()
            .progress_inherited_native(deadline)
            .map_err(external)
    }
}
enum Endpoint {
    Legacy(TaskControlEndpoint),
    Early(EarlyTaskControlEndpoint),
}
enum Peer {
    Legacy(TaskControlPeer),
    Early(EarlyTaskControlPeer),
}
impl Endpoint {
    fn socket_inode(&self) -> &File {
        match self {
            Self::Legacy(e) => e.socket_inode(),
            Self::Early(e) => e.socket_inode(),
        }
    }
    fn composer_sha256(&self) -> &str {
        match self {
            Self::Legacy(e) => e.composer_sha256(),
            Self::Early(e) => e.composer_sha256(),
        }
    }
    fn bind_listener(
        &mut self,
        a: Authority<'_, '_>,
        socket: &File,
        deadline: Instant,
    ) -> Result<()> {
        match (self, a) {
            (Self::Legacy(e), Authority::Legacy(a)) => {
                e.bind_listener(a, socket, deadline).map_err(external)
            }
            (Self::Early(e), Authority::Early(a)) => {
                e.bind_listener(a, socket, deadline).map_err(external)
            }
            _ => Err(reject(
                "task-control endpoint belongs to another owner kind",
            )),
        }
    }
    fn revalidate_connection(
        &self,
        a: Authority<'_, '_>,
        socket: &File,
        deadline: Instant,
    ) -> Result<()> {
        match (self, a) {
            (Self::Legacy(e), Authority::Legacy(a)) => e
                .revalidate_connection(a, socket, deadline)
                .map_err(external),
            (Self::Early(e), Authority::Early(a)) => e
                .revalidate_connection(a, socket, deadline)
                .map_err(external),
            _ => Err(reject(
                "task-control endpoint belongs to another owner kind",
            )),
        }
    }
    fn bind_sender(
        &self,
        a: Authority<'_, '_>,
        pidfd: OwnedFd,
        credentials: libc::ucred,
        deadline: Instant,
    ) -> Result<Peer> {
        match (self, a) {
            (Self::Legacy(e), Authority::Legacy(a)) => e
                .bind_sender(a, pidfd, credentials, deadline)
                .map(Peer::Legacy)
                .map_err(external),
            (Self::Early(e), Authority::Early(a)) => e
                .bind_sender(a, pidfd, credentials, deadline)
                .map(Peer::Early)
                .map_err(external),
            _ => Err(reject("task-control sender belongs to another owner kind")),
        }
    }
}
impl Peer {
    fn revalidate(
        &self,
        a: Authority<'_, '_>,
        endpoint: &Endpoint,
        deadline: Instant,
    ) -> Result<()> {
        match (self, a, endpoint) {
            (Self::Legacy(p), Authority::Legacy(a), Endpoint::Legacy(e)) => {
                p.revalidate(a, e, deadline).map_err(external)
            }
            (Self::Early(p), Authority::Early(a), Endpoint::Early(e)) => {
                p.revalidate(a, e, deadline).map_err(external)
            }
            _ => Err(reject("task-control sender belongs to another owner kind")),
        }
    }
    fn same_generation(&self, other: &Self) -> bool {
        match (self, other) {
            (Self::Legacy(a), Self::Legacy(b)) => a.same_generation(b),
            (Self::Early(a), Self::Early(b)) => a.same_generation(b),
            _ => false,
        }
    }
}

pub(super) fn connect(
    authority: &ApplicationAuthority<'_>,
    package: &str,
    deadline: Instant,
) -> Result<ApplicationTaskControl> {
    connect_owned(Authority::Legacy(authority), package, deadline)
}
pub(super) fn connect_early(
    authority: &EarlyApplicationAuthority<'_>,
    package: &str,
    deadline: Instant,
) -> Result<ApplicationTaskControl> {
    connect_owned(Authority::Early(authority), package, deadline)
}
impl ApplicationTaskControl {
    pub(crate) fn revalidate(
        &self,
        authority: &ApplicationAuthority<'_>,
        deadline: Instant,
    ) -> Result<()> {
        self.revalidate_owned(Authority::Legacy(authority), deadline)
    }
    pub(super) fn revalidate_early(
        &self,
        authority: &EarlyApplicationAuthority<'_>,
        deadline: Instant,
    ) -> Result<()> {
        self.revalidate_owned(Authority::Early(authority), deadline)
    }
    pub(crate) fn exchange(
        &mut self,
        authority: &ApplicationAuthority<'_>,
        request: &ControlRequest,
        deadline: Instant,
    ) -> Result<ControlResponse> {
        self.exchange_owned(Authority::Legacy(authority), request, deadline)
    }
    pub(super) fn exchange_early(
        &mut self,
        authority: &EarlyApplicationAuthority<'_>,
        request: &ControlRequest,
        deadline: Instant,
    ) -> Result<ControlResponse> {
        self.exchange_owned(Authority::Early(authority), request, deadline)
    }
}

fn connect_owned(
    authority: Authority<'_, '_>,
    package: &str,
    deadline: Instant,
) -> Result<ApplicationTaskControl> {
    require(
        package_valid(package) && package.len() <= droidloom_task_control::MAX_PACKAGE_BYTES,
        "invalid bound task-control package",
    )?;
    let mut endpoint = authority
        .task_control_endpoint(deadline)
        .map_err(external)?;
    let connection =
        process::connect_bridge(authority.worker(), endpoint.socket_inode(), deadline)?;
    require(
        connection.receipt.cgroup_removed
            && connection.receipt.worker_waitid_code == libc::CLD_EXITED
            && connection.receipt.worker_waitid_status == 0,
        "bridge connector retirement incomplete",
    )?;
    socket_shape(&connection.socket)?;
    endpoint
        .bind_listener(authority, &connection.socket, deadline)
        .map_err(external)?;
    let value = ApplicationTaskControl {
        socket: connection.socket,
        endpoint,
        composer: None,
        package: package.into(),
        deadline,
        phase: Phase::Hello,
        receipt: connection.receipt,
    };
    value.revalidate_owned(authority, deadline)?;
    Ok(value)
}

impl ApplicationTaskControl {
    fn revalidate_owned(&self, authority: Authority<'_, '_>, deadline: Instant) -> Result<()> {
        require(
            deadline == self.deadline && Instant::now() < deadline,
            "task-control fixed deadline changed or expired",
        )?;
        self.endpoint
            .revalidate_connection(authority, &self.socket, deadline)
            .map_err(external)?;
        if let Some(peer) = &self.composer {
            peer.revalidate(authority, &self.endpoint, deadline)
                .map_err(external)?;
        }
        socket_shape(&self.socket)?;
        require(
            Instant::now() < deadline,
            "task-control validation exceeded deadline",
        )
    }

    fn wait(&self, authority: Authority<'_, '_>, event: i16, deadline: Instant) -> Result<()> {
        self.revalidate_owned(authority, deadline)?;
        authority
            .progress_inherited_native(deadline)
            .map_err(external)?;
        self.revalidate_owned(authority, deadline)?;
        let mut poll = libc::pollfd {
            fd: self.socket.as_raw_fd(),
            events: event,
            revents: 0,
        };
        let count = unsafe {
            libc::poll(
                &mut poll,
                1,
                deadline
                    .saturating_duration_since(Instant::now())
                    .as_millis()
                    .clamp(1, 20) as i32,
            )
        };
        if count < 0 && io::Error::last_os_error().kind() != io::ErrorKind::Interrupted {
            return Err(io::Error::last_os_error().into());
        }
        require(
            poll.revents & (libc::POLLNVAL | libc::POLLERR | libc::POLLHUP) == 0,
            "task-control connection failed",
        )?;
        self.revalidate_owned(authority, deadline)
    }

    fn exchange_owned(
        &mut self,
        authority: Authority<'_, '_>,
        request: &ControlRequest,
        deadline: Instant,
    ) -> Result<ControlResponse> {
        self.revalidate_owned(authority, deadline)?;
        let expected = requested_phase(self.phase, request, &self.package)?;
        let bytes = encode_request(request).map_err(external)?;
        require(
            !bytes.is_empty() && bytes.len() <= MAX_RECORD_BYTES,
            "task-control request bound",
        )?;
        // Even a partial/ambiguous failure consumes this session. No repeated
        // Hello, re-registration or new connection can hide a side effect.
        self.phase = Phase::Failed;
        loop {
            self.revalidate_owned(authority, deadline)?;
            let sent = unsafe {
                libc::send(
                    self.socket.as_raw_fd(),
                    bytes.as_ptr().cast(),
                    bytes.len(),
                    libc::MSG_NOSIGNAL | libc::MSG_DONTWAIT,
                )
            };
            if sent >= 0 {
                require(
                    sent as usize == bytes.len(),
                    "partial task-control seqpacket send",
                )?;
                break;
            }
            let error = io::Error::last_os_error();
            if error.kind() == io::ErrorKind::Interrupted {
                continue;
            }
            if error.kind() != io::ErrorKind::WouldBlock {
                return Err(error.into());
            }
            self.wait(authority, libc::POLLOUT, deadline)?;
        }
        let received = loop {
            self.revalidate_owned(authority, deadline)?;
            match receive_record(&self.socket)? {
                Some(value) => break value,
                None => self.wait(authority, libc::POLLIN, deadline)?,
            }
        };
        let peer = self
            .endpoint
            .bind_sender(authority, received.pidfd, received.credentials, deadline)
            .map_err(external)?;
        if let Some(original) = &self.composer {
            require(
                original.same_generation(&peer),
                "task-control reply changed Composer generation",
            )?;
        } else {
            self.composer = Some(peer);
        }
        let response = decode_response(&received.body).map_err(external)?;
        if let ControlResponse::Error {
            request_id,
            code,
            message,
        } = &response
        {
            let expected_id = match request {
                ControlRequest::Hello { .. } => 0,
                ControlRequest::RegisterDirect { request_id, .. } => *request_id,
                _ => return Err(reject("task-control error for a forbidden operation")),
            };
            require(
                *request_id == expected_id,
                "task-control error correlation differs",
            )?;
            self.revalidate_owned(authority, deadline)?;
            return Err(reject(format!(
                "task-control server error {code:?}: {message}"
            )));
        }
        require(
            matching_response(request, &response),
            "task-control response correlation differs",
        )?;
        self.revalidate_owned(authority, deadline)?;
        self.phase = expected;
        Ok(response)
    }

    pub(crate) fn complete(&self) -> Result<()> {
        require(
            self.phase == Phase::Bound
                && self.composer.is_some()
                && self.receipt.cgroup_removed
                && self.endpoint.composer_sha256().len() == 64,
            "task-control session did not complete its authenticated binding",
        )
    }

    pub(super) fn commands_allowed(&self) -> bool {
        self.phase == Phase::Register && self.composer.is_some()
    }

    pub(super) fn close(self) -> Result<BridgeReceipt> {
        let raw = self.socket.into_raw_fd();
        let shut = unsafe { libc::shutdown(raw, libc::SHUT_RDWR) };
        let shutdown_error = if shut == 0 {
            None
        } else {
            Some(io::Error::last_os_error())
        };
        // Never retry close on a potentially reused numeric descriptor.
        let closed = unsafe { libc::close(raw) };
        let close_error = if closed == 0 {
            None
        } else {
            Some(io::Error::last_os_error())
        };
        if let Some(error) = close_error.or(shutdown_error) {
            return Err(error.into());
        }
        Ok(self.receipt)
    }
}

fn requested_phase(phase: Phase, request: &ControlRequest, package: &str) -> Result<Phase> {
    match (phase, request) {
        (
            Phase::Hello,
            ControlRequest::Hello {
                min_major,
                max_major,
            },
        ) if *min_major == PROTOCOL_MAJOR && *max_major == PROTOCOL_MAJOR => Ok(Phase::Register),
        (
            Phase::Register,
            ControlRequest::RegisterDirect {
                request_id,
                package: actual,
                task,
                android_display,
            },
        ) if *request_id == 1 && actual == package && *task > 0 && *android_display == 0 => {
            Ok(Phase::Bound)
        }
        _ => Err(reject(
            "task-control request is outside this one bound launch",
        )),
    }
}
fn matching_response(request: &ControlRequest, response: &ControlResponse) -> bool {
    match (request, response) {
        (ControlRequest::Hello { .. }, ControlResponse::ServerHello { major, .. }) => {
            *major == PROTOCOL_MAJOR
        }
        (
            ControlRequest::RegisterDirect {
                request_id,
                task,
                android_display,
                ..
            },
            ControlResponse::Bound {
                request_id: actual,
                task: actual_task,
                android_display: actual_display,
                object,
                display,
            },
        ) => {
            request_id == actual
                && task == actual_task
                && android_display == actual_display
                && *object > 0
                && *display > 0
        }
        _ => false,
    }
}

struct Received {
    body: Vec<u8>,
    credentials: libc::ucred,
    pidfd: OwnedFd,
}

fn receive_record(socket: &File) -> Result<Option<Received>> {
    let mut bytes = [0_u8; MAX_RECORD_BYTES];
    let mut iov = libc::iovec {
        iov_base: bytes.as_mut_ptr().cast(),
        iov_len: bytes.len(),
    };
    // Room for all kernel-permitted SCM_RIGHTS (which are forbidden here), as
    // well as credentials/PIDFD. Adopt every delivered FD before rejecting.
    let mut control = [0_usize; 256];
    let mut header: libc::msghdr = unsafe { mem::zeroed() };
    header.msg_iov = &mut iov;
    header.msg_iovlen = 1;
    header.msg_control = control.as_mut_ptr().cast();
    header.msg_controllen = mem::size_of_val(&control);
    let count = unsafe {
        libc::recvmsg(
            socket.as_raw_fd(),
            &mut header,
            libc::MSG_DONTWAIT | libc::MSG_CMSG_CLOEXEC,
        )
    };
    if count < 0 {
        let error = io::Error::last_os_error();
        if matches!(
            error.kind(),
            io::ErrorKind::Interrupted | io::ErrorKind::WouldBlock
        ) {
            return Ok(None);
        }
        return Err(error.into());
    }
    let mut credentials = None;
    let mut pidfds = Vec::new();
    let mut rights = Vec::new();
    let mut malformed = false;
    let mut cmsg = unsafe { libc::CMSG_FIRSTHDR(&header) };
    while !cmsg.is_null() {
        let fixed = unsafe { libc::CMSG_LEN(0) } as usize;
        let length = unsafe { (*cmsg).cmsg_len };
        let start = cmsg as usize;
        let end = (header.msg_control as usize).checked_add(header.msg_controllen);
        if length < fixed
            || end.is_none()
            || start.checked_add(length).is_none_or(|n| n > end.unwrap())
        {
            malformed = true;
            break;
        }
        let payload = length - fixed;
        let level = unsafe { (*cmsg).cmsg_level };
        let kind = unsafe { (*cmsg).cmsg_type };
        if level == libc::SOL_SOCKET && (kind == libc::SCM_RIGHTS || kind == SCM_PIDFD) {
            if payload % mem::size_of::<i32>() != 0
                || (kind == SCM_PIDFD && payload != mem::size_of::<i32>())
            {
                malformed = true;
            }
            for index in 0..payload / mem::size_of::<i32>() {
                let raw = unsafe {
                    std::ptr::read_unaligned(
                        libc::CMSG_DATA(cmsg)
                            .add(index * mem::size_of::<i32>())
                            .cast::<i32>(),
                    )
                };
                if raw < 0 {
                    malformed = true;
                } else {
                    let fd = unsafe { OwnedFd::from_raw_fd(raw) };
                    if kind == SCM_PIDFD {
                        pidfds.push(fd);
                    } else {
                        rights.push(fd);
                    }
                }
            }
        } else if level == libc::SOL_SOCKET
            && kind == libc::SCM_CREDENTIALS
            && payload == mem::size_of::<libc::ucred>()
        {
            let value =
                unsafe { std::ptr::read_unaligned(libc::CMSG_DATA(cmsg).cast::<libc::ucred>()) };
            if credentials.replace(value).is_some() {
                malformed = true;
            }
        } else {
            malformed = true;
        }
        cmsg = unsafe { libc::CMSG_NXTHDR(&header, cmsg) };
    }
    require(
        count > 0
            && count as usize <= bytes.len()
            && !malformed
            && rights.is_empty()
            && pidfds.len() == 1
            && header.msg_flags & (libc::MSG_TRUNC | libc::MSG_CTRUNC) == 0,
        "task-control record is truncated or contains forbidden/missing capabilities",
    )?;
    let credentials =
        credentials.ok_or_else(|| reject("task-control record credentials absent"))?;
    let pidfd = pidfds.pop().unwrap();
    let flags = unsafe { libc::fcntl(pidfd.as_raw_fd(), libc::F_GETFD) };
    require(
        flags >= 0 && flags & libc::FD_CLOEXEC != 0,
        "task-control message PIDFD is not CLOEXEC",
    )?;
    Ok(Some(Received {
        body: bytes[..count as usize].to_vec(),
        credentials,
        pidfd,
    }))
}

#[cfg(test)]
#[path = "production_application_task_control_tests.rs"]
mod tests;
