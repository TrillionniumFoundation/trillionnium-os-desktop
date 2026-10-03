//! Private original-creator custody. A numeric PID alone can collide in a
//! nested PID namespace; original kernel socket credentials cannot be minted
//! by the inheriting process. Namespace custody is an additional check.
use super::*;
use std::mem::{size_of, zeroed};

// linux/nsfs.h: _IO(0xb7, 0x3), queried on the actual held namespace file.
const NS_GET_NSTYPE: libc::c_ulong = 0xb703;

fn socket_value<T: Copy>(fd: libc::c_int, option: libc::c_int) -> Result<T, ApprovedPolicyError> {
    // SAFETY: getsockopt initializes this bounded output; it retains no pointer.
    let mut value: T = unsafe { zeroed() };
    let mut length = size_of::<T>() as libc::socklen_t;
    if unsafe {
        libc::getsockopt(
            fd,
            libc::SOL_SOCKET,
            option,
            std::ptr::addr_of_mut!(value).cast(),
            &mut length,
        )
    } != 0
        || length as usize != size_of::<T>()
    {
        return Err(ApprovedPolicyError::SourceRefused);
    }
    Ok(value)
}

struct CreatorEndpoint {
    stream: UnixStream,
    device: u64,
    inode: u64,
    cookie: u64,
    peer: PeerIdentity,
}
impl CreatorEndpoint {
    fn identity(stream: &UnixStream) -> Result<(u64, u64, u64), ApprovedPolicyError> {
        let fd = stream.as_raw_fd();
        // SAFETY: fcntl reads this owned descriptor without retaining it.
        let flags = unsafe { libc::fcntl(fd, libc::F_GETFD) };
        let kind: libc::c_int = socket_value(fd, libc::SO_TYPE)?;
        let cookie: u64 = socket_value(fd, libc::SO_COOKIE)?;
        // SAFETY: fstat writes this live stat buffer and retains no pointer.
        let mut metadata: libc::stat = unsafe { zeroed() };
        if unsafe { libc::fstat(fd, &mut metadata) } != 0 {
            return Err(ApprovedPolicyError::SourceRefused);
        }
        if flags < 0
            || flags & libc::FD_CLOEXEC == 0
            || kind != libc::SOCK_STREAM
            || metadata.st_mode & libc::S_IFMT != libc::S_IFSOCK
            || cookie == 0
        {
            return Err(ApprovedPolicyError::SourceRefused);
        }
        Ok((metadata.st_dev, metadata.st_ino, cookie))
    }
    fn capture(stream: UnixStream, pid: u32) -> Result<Self, ApprovedPolicyError> {
        let (device, inode, cookie) = Self::identity(&stream)?;
        let peer =
            PeerIdentity::from_stream(&stream).map_err(|_| ApprovedPolicyError::SourceRefused)?;
        if peer.pid != Some(pid) || pid == 0 {
            return Err(ApprovedPolicyError::ProcessChanged);
        }
        Ok(Self {
            stream,
            device,
            inode,
            cookie,
            peer,
        })
    }
    fn verify(&self) -> Result<(), ApprovedPolicyError> {
        if Self::identity(&self.stream)? != (self.device, self.inode, self.cookie) {
            return Err(ApprovedPolicyError::Changed);
        }
        let peer = PeerIdentity::from_stream(&self.stream)
            .map_err(|_| ApprovedPolicyError::ProcessChanged)?;
        if peer != self.peer || peer.pid.is_none() {
            return Err(ApprovedPolicyError::ProcessChanged);
        }
        Ok(())
    }
}

fn current_pid_namespace() -> Result<File, ApprovedPolicyError> {
    // This fixed procfs magic link must be followed intentionally. It is not a
    // root policy path and does not reuse the original nofollow policy walker.
    // SAFETY: fixed NUL-terminated path; successful FD is immediately owned.
    let fd = unsafe {
        libc::open(
            c"/proc/thread-self/ns/pid".as_ptr(),
            libc::O_RDONLY | libc::O_CLOEXEC,
        )
    };
    if fd < 0 {
        return Err(ApprovedPolicyError::SourceRefused);
    }
    Ok(File::from(unsafe { OwnedFd::from_raw_fd(fd) }))
}
fn namespace_identity(file: &File) -> Result<(u64, u64), ApprovedPolicyError> {
    // SAFETY: this no-argument nsfs ioctl reads the owned namespace descriptor.
    if unsafe { libc::ioctl(file.as_raw_fd(), NS_GET_NSTYPE) } != libc::CLONE_NEWPID {
        return Err(ApprovedPolicyError::SourceRefused);
    }
    let metadata = file
        .metadata()
        .map_err(|_| ApprovedPolicyError::SourceRefused)?;
    Ok((metadata.dev(), metadata.ino()))
}

pub(super) struct CreatorContext {
    pub(super) pid: u32,
    endpoints: [CreatorEndpoint; 2],
    pid_namespace: File,
    pid_namespace_identity: (u64, u64),
}
impl CreatorContext {
    pub(super) fn capture() -> Result<Self, ApprovedPolicyError> {
        let pid = std::process::id();
        let (first, second) = UnixStream::pair().map_err(|_| ApprovedPolicyError::SourceRefused)?;
        let endpoints = [
            CreatorEndpoint::capture(first, pid)?,
            CreatorEndpoint::capture(second, pid)?,
        ];
        let pid_namespace = current_pid_namespace()?;
        let pid_namespace_identity = namespace_identity(&pid_namespace)?;
        let value = Self {
            pid,
            endpoints,
            pid_namespace,
            pid_namespace_identity,
        };
        value.verify()?;
        Ok(value)
    }
    pub(super) fn verify(&self) -> Result<(), ApprovedPolicyError> {
        if self.pid != std::process::id() {
            return Err(ApprovedPolicyError::ProcessChanged);
        }
        // Numeric collision queries only private creator resources first.
        // In a nested child the original ancestor peer has no PID there.
        for endpoint in &self.endpoints {
            endpoint.verify()?;
        }
        if namespace_identity(&self.pid_namespace)? != self.pid_namespace_identity
            || namespace_identity(&current_pid_namespace()?)? != self.pid_namespace_identity
        {
            return Err(ApprovedPolicyError::ProcessChanged);
        }
        Ok(())
    }
}
