//! The bootstrap owns the Android property service. PID 1 owns its private
//! shutdown channel and observes retirement of both persistent mountpoints.
use super::*;
use std::mem::{self, MaybeUninit};
use std::os::fd::{AsRawFd, FromRawFd, OwnedFd};
use std::os::unix::net::UnixDatagram;

pub(super) const REQUEST: &[u8] = b"DROIDLOOM_SHUTDOWN_V1";
const UNMOUNTED: &[u8] = b"DROIDLOOM_DATA_UNMOUNTED_V1";

pub(super) fn attach(command: &mut Command, endpoint: &UnixDatagram) {
    let source = endpoint.as_raw_fd();
    command.env("DROIDLOOM_INIT_CONTROL_FD", "3");
    // Only this endpoint crosses exec. The caller keeps the original socket live through spawn.
    unsafe {
        command.pre_exec(move || {
            if source != 3 && libc::dup2(source, 3) < 0 || libc::fcntl(3, libc::F_SETFD, 0) < 0 {
                return Err(io::Error::last_os_error());
            }
            Ok(())
        });
    }
}
pub(super) struct Channel {
    socket: UnixDatagram,
}
impl Channel {
    pub(super) fn pair() -> io::Result<(Self, UnixDatagram)> {
        let (owner, bootstrap) = UnixDatagram::pair()?;
        let yes: libc::c_int = 1;
        for socket in [&owner, &bootstrap] {
            let result = unsafe {
                libc::setsockopt(
                    socket.as_raw_fd(),
                    libc::SOL_SOCKET,
                    libc::SO_PASSCRED,
                    (&yes as *const libc::c_int).cast(),
                    mem::size_of_val(&yes) as libc::socklen_t,
                )
            };
            if result != 0 {
                return Err(io::Error::last_os_error());
            }
        }
        owner.set_nonblocking(true)?;
        Ok((Self { socket: owner }, bootstrap))
    }

    pub(super) fn request(&self) -> io::Result<()> {
        if self.socket.send(REQUEST)? != REQUEST.len() {
            return Err(error("incomplete Android shutdown request"));
        }
        Ok(())
    }

    pub(super) fn observe(&self, pid: u32) -> io::Result<bool> {
        let mut body = [0u8; 64];
        let mut control = [0usize; 32];
        let mut iov = libc::iovec {
            iov_base: body.as_mut_ptr().cast(),
            iov_len: body.len(),
        };
        let mut msg = unsafe { MaybeUninit::<libc::msghdr>::zeroed().assume_init() };
        msg.msg_iov = &mut iov;
        msg.msg_iovlen = 1;
        msg.msg_control = control.as_mut_ptr().cast();
        msg.msg_controllen = mem::size_of_val(&control);
        let n = unsafe {
            libc::recvmsg(
                self.socket.as_raw_fd(),
                &mut msg,
                libc::MSG_DONTWAIT | libc::MSG_CMSG_CLOEXEC,
            )
        };
        if n < 0 {
            let e = io::Error::last_os_error();
            if matches!(
                e.kind(),
                io::ErrorKind::WouldBlock | io::ErrorKind::Interrupted
            ) {
                return Ok(false);
            }
            return Err(e);
        }
        let mut source = None;
        let mut foreign = false;
        let mut item = unsafe { libc::CMSG_FIRSTHDR(&msg) };
        while !item.is_null() {
            let header = unsafe { &*item };
            let base = unsafe { libc::CMSG_LEN(0) } as usize;
            if header.cmsg_len < base {
                return Err(error("invalid shutdown ancillary message"));
            }
            let len = header.cmsg_len - base;
            let data = unsafe { libc::CMSG_DATA(item) };
            match (header.cmsg_level, header.cmsg_type) {
                (libc::SOL_SOCKET, libc::SCM_CREDENTIALS)
                    if len == mem::size_of::<libc::ucred>() && source.is_none() =>
                {
                    source =
                        Some(unsafe { std::ptr::read_unaligned(data.cast::<libc::ucred>()) }.pid);
                }
                (libc::SOL_SOCKET, libc::SCM_RIGHTS) => {
                    foreign = true;
                    for i in 0..len / mem::size_of::<libc::c_int>() {
                        let fd =
                            unsafe { std::ptr::read_unaligned(data.cast::<libc::c_int>().add(i)) };
                        if fd >= 0 {
                            drop(unsafe { OwnedFd::from_raw_fd(fd) });
                        }
                    }
                }
                _ => foreign = true,
            }
            item = unsafe { libc::CMSG_NXTHDR(&msg, item) };
        }
        if foreign
            || msg.msg_flags & (libc::MSG_CTRUNC | libc::MSG_TRUNC) != 0
            || source != Some(pid as i32)
            || body.get(..n as usize) != Some(UNMOUNTED)
        {
            return Err(error(
                "untrusted or incomplete Android shutdown acknowledgement",
            ));
        }
        Ok(true)
    }
}

#[derive(Default)]
struct Mounts {
    data: Option<u64>,
    metadata: Option<u64>,
    ids: Vec<u64>,
    any: bool,
}
pub(super) struct PersistentMounts {
    data: u64,
    metadata: u64,
}
impl PersistentMounts {
    fn from_view(view: Mounts) -> io::Result<Self> {
        match (view.data, view.metadata) {
            (Some(data), Some(metadata)) if data != metadata => Ok(Self { data, metadata }),
            _ => Err(error(
                "original data and metadata mounts must be present at handoff",
            )),
        }
    }
    pub(super) fn acquire() -> io::Result<Self> {
        Self::from_view(Mounts::current()?)
    }
    fn present(&self, v: &Mounts) -> bool {
        v.data == Some(self.data) && v.metadata == Some(self.metadata)
    }
    fn retired(&self, v: &Mounts) -> bool {
        !v.any && !v.ids.contains(&self.data) && !v.ids.contains(&self.metadata)
    }
    #[cfg(test)]
    pub(super) fn fixture() -> Self {
        Self {
            data: 998975433,
            metadata: 998975434,
        }
    }
}
impl Mounts {
    fn parse(text: &str) -> io::Result<Self> {
        let mut mounts = Self::default();
        let mut lines = 0;
        for line in text.lines() {
            let (first, _) = line
                .split_once(" - ")
                .ok_or_else(|| error("incomplete kernel mountinfo"))?;
            let mut fields = first.split_ascii_whitespace();
            let id = fields
                .next()
                .and_then(|s| s.parse::<u64>().ok())
                .ok_or_else(|| error("invalid mount ID"))?;
            let path = fields
                .nth(3)
                .ok_or_else(|| error("missing mountpoint in kernel mountinfo"))?;
            if path == "/data" && mounts.data.replace(id).is_some()
                || path == "/metadata" && mounts.metadata.replace(id).is_some()
            {
                return Err(error("ambiguous persistent Android mount"));
            }
            mounts.ids.push(id);
            mounts.any |= path == "/data"
                || path == "/metadata"
                || path.starts_with("/data/")
                || path.starts_with("/metadata/");
            lines += 1;
        }
        if lines == 0 {
            return Err(error("empty kernel mountinfo"));
        }
        Ok(mounts)
    }
    fn current() -> io::Result<Self> {
        let file = File::open("/proc/self/mountinfo")?;
        let mut stat = MaybeUninit::<libc::statfs>::uninit();
        if unsafe { libc::fstatfs(file.as_raw_fd(), stat.as_mut_ptr()) } != 0 {
            return Err(io::Error::last_os_error());
        }
        if unsafe { stat.assume_init().f_type } != libc::PROC_SUPER_MAGIC {
            return Err(error("mount retirement requires kernel procfs"));
        }
        let mut raw = String::new();
        file.take(4 * 1024 * 1024 + 1).read_to_string(&mut raw)?;
        if raw.len() > 4 * 1024 * 1024 {
            return Err(error("mountinfo exceeds its bounded size"));
        }
        Self::parse(&raw)
    }
}

pub(super) fn retire(
    owner: &mut Bootstrap,
    mounts: &PersistentMounts,
    limit: Duration,
) -> io::Result<()> {
    let result = (|| {
        let before = Mounts::current()?;
        if owner.poll()?.is_some() {
            return Err(error("Android bootstrap exited before orderly shutdown"));
        }
        owner.control.request()?;
        let end = Instant::now() + limit;
        let mut acknowledged = false;
        loop {
            if !acknowledged {
                acknowledged = owner.control.observe(owner.child.id())?;
            }
            if let Some(exit) = owner.poll()? {
                // The datagram may have arrived between the first read and waitpid.
                if !acknowledged {
                    acknowledged = owner.control.observe(owner.child.id())?;
                }
                if exit.success()
                    && acknowledged
                    && mounts.present(&before)
                    && mounts.retired(&Mounts::current()?)
                {
                    return Ok(());
                }
                return Err(error(
                    "Android bootstrap exited without verified release of persistent mounts",
                ));
            }
            if Instant::now() >= end {
                return Err(error(
                    "Android orderly shutdown timed out before data retirement",
                ));
            }
            thread::sleep(Duration::from_millis(30));
        }
    })();
    if result.is_err() && owner.poll()?.is_none() {
        owner.child.kill()?;
        owner.exit = Some(owner.child.wait()?);
    }
    result
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn root_mounts_and_descendants_must_be_absent_after_shutdown() {
        let text = "24 19 0:1 / / rw - tmpfs tmpfs rw\n25 24 7:1 / /data rw - ext4 d rw\n26 24 7:2 / /metadata rw - ext4 m rw\n";
        let mounted = Mounts::parse(text).unwrap();
        assert!(mounted.data == Some(25) && mounted.metadata == Some(26) && mounted.any);
        let witness = PersistentMounts::from_view(mounted).unwrap();
        let nested = Mounts::parse("25 24 7:1 / /data/local rw - ext4 d rw\n").unwrap();
        assert!(nested.data.is_none() && nested.any);
        let moved = Mounts::parse("25 24 7:1 / /old rw - ext4 d rw\n").unwrap();
        assert!(!witness.retired(&moved));
        assert!(
            !Mounts::parse("24 19 0:1 / / rw - tmpfs tmpfs rw\n")
                .unwrap()
                .any
        );
    }
    #[test]
    fn the_shutdown_endpoint_survives_exec_and_proves_both_real_processes() {
        let (control, peer) = Channel::pair().unwrap();
        let script = r#"import os,socket,struct
s=socket.socket(fileno=int(os.environ["DROIDLOOM_INIT_CONTROL_FD"]))
os.set_inheritable(s.fileno(),False)
message,control,flags,_=s.recvmsg(128,128)
assert not flags and message==b"DROIDLOOM_SHUTDOWN_V1"
creds=[struct.unpack("iii",v) for l,t,v in control if (l,t)==(socket.SOL_SOCKET,socket.SCM_CREDENTIALS)]
assert len(creds)==1 and creds[0][0]==os.getppid()
s.send(b"DROIDLOOM_DATA_UNMOUNTED_V1")"#;
        let mut command = Command::new("/usr/bin/python3");
        command.args(["-c", script]);
        attach(&mut command, &peer);
        let mut child = command.spawn().unwrap();
        drop(peer);
        control.request().unwrap();
        assert!(child.wait().unwrap().success());
        assert!(control.observe(child.id()).unwrap());
    }
    #[test]
    fn only_a_datagram_from_the_actual_bootstrap_process_counts() {
        let (owner, peer) = Channel::pair().unwrap();
        peer.send(UNMOUNTED).unwrap();
        assert!(owner.observe(std::process::id()).unwrap());
        peer.send(UNMOUNTED).unwrap();
        assert!(owner.observe(std::process::id() + 1).is_err());
        peer.send(b"ready").unwrap();
        assert!(owner.observe(std::process::id()).is_err());
    }
}
