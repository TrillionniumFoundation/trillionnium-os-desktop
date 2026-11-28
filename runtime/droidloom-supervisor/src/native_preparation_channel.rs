//! One unnamed preparation-only channel for the three original diagnostics.
//! The command is a fixed ordinal; only the normal parent borrows Main/PM and
//! invokes the authenticated broker. No caller argv, UID, PID or path is read.
use crate::control::{NativeApplicationInspector, PreparationReadObservation};
use crate::native_leaf_baseline::NativeLeafBaselineObservation;
use crate::native_preparation_read::PreparationReadKind;
use std::fs::File;
use std::io::{self, Write};
use std::os::fd::{AsRawFd, FromRawFd, RawFd};
use std::os::unix::fs::MetadataExt;
use std::os::unix::net::UnixDatagram;
use std::process::{Child, Command};
use std::time::Instant;

pub(crate) const ENV: &str = "DROIDLOOM_NATIVE_PREPARATION_FD";
const KINDS: [PreparationReadKind; 3] = [
    PreparationReadKind::GuestUid,
    PreparationReadKind::GuestGid,
    PreparationReadKind::BootCompleted,
];
const TOKENS: [u8; 3] = [b'U', b'D', b'B'];
const SEALS: i32 = libc::F_SEAL_SEAL | libc::F_SEAL_SHRINK | libc::F_SEAL_GROW | libc::F_SEAL_WRITE;
fn invalid(why: &str) -> io::Error {
    io::Error::other(why)
}
fn live(file: &File) -> io::Result<()> {
    let mut p = libc::pollfd {
        fd: file.as_raw_fd(),
        events: libc::POLLIN,
        revents: 0,
    };
    match unsafe { libc::poll(&mut p, 1, 0) } {
        0 => Ok(()),
        -1 => Err(io::Error::last_os_error()),
        _ => Err(invalid("original preparation collector is no longer live")),
    }
}
fn sealed_reply(bytes: &[u8]) -> io::Result<File> {
    if bytes.is_empty() || bytes.len() > crate::native_preparation_read::MAX_RESPONSE_BYTES {
        return Err(invalid(
            "complete preparation reply exceeds its fixed bound",
        ));
    }
    let raw = unsafe {
        libc::memfd_create(
            c"droidloom-preparation-read".as_ptr(),
            libc::MFD_CLOEXEC | libc::MFD_ALLOW_SEALING,
        )
    };
    if raw < 0 {
        return Err(io::Error::last_os_error());
    }
    let mut writer = unsafe { File::from_raw_fd(raw) };
    writer.write_all(bytes)?;
    if unsafe { libc::fcntl(writer.as_raw_fd(), libc::F_ADD_SEALS, SEALS) } != 0 {
        return Err(io::Error::last_os_error());
    }
    let reader = File::open(format!("/proc/self/fd/{}", writer.as_raw_fd()))?;
    let a = reader.metadata()?;
    let b = writer.metadata()?;
    if a.dev() != b.dev()
        || a.ino() != b.ino()
        || a.nlink() != 0
        || a.len() != bytes.len() as u64
        || unsafe { libc::fcntl(reader.as_raw_fd(), libc::F_GET_SEALS) } != SEALS
        || unsafe { libc::fcntl(reader.as_raw_fd(), libc::F_GETFL) } & libc::O_ACCMODE
            != libc::O_RDONLY
    {
        return Err(invalid("preparation sealed reply identity changed"));
    }
    Ok(reader)
}
fn send_reply(socket: &UnixDatagram, file: &File) -> io::Result<()> {
    let mut byte = b'R';
    let mut io = libc::iovec {
        iov_base: (&mut byte as *mut u8).cast(),
        iov_len: 1,
    };
    let mut control = [0usize; 4];
    let mut msg: libc::msghdr = unsafe { std::mem::zeroed() };
    msg.msg_iov = &mut io;
    msg.msg_iovlen = 1;
    msg.msg_control = control.as_mut_ptr().cast();
    msg.msg_controllen = unsafe { libc::CMSG_SPACE(std::mem::size_of::<RawFd>() as u32) } as usize;
    unsafe {
        let header = libc::CMSG_FIRSTHDR(&msg);
        (*header).cmsg_level = libc::SOL_SOCKET;
        (*header).cmsg_type = libc::SCM_RIGHTS;
        (*header).cmsg_len = libc::CMSG_LEN(std::mem::size_of::<RawFd>() as u32) as usize;
        std::ptr::write_unaligned(libc::CMSG_DATA(header).cast::<RawFd>(), file.as_raw_fd());
    }
    let n = unsafe {
        libc::sendmsg(
            socket.as_raw_fd(),
            &msg,
            libc::MSG_DONTWAIT | libc::MSG_NOSIGNAL,
        )
    };
    if n != 1 {
        return Err(if n < 0 {
            io::Error::last_os_error()
        } else {
            invalid("short sealed preparation reply")
        });
    }
    Ok(())
}
fn receive(socket: &UnixDatagram, pid: u32) -> io::Result<Option<u8>> {
    let mut bytes = [0u8; 2];
    let mut io = libc::iovec {
        iov_base: bytes.as_mut_ptr().cast(),
        iov_len: bytes.len(),
    };
    let mut control = [0usize; 8];
    let mut msg: libc::msghdr = unsafe { std::mem::zeroed() };
    msg.msg_iov = &mut io;
    msg.msg_iovlen = 1;
    msg.msg_control = control.as_mut_ptr().cast();
    msg.msg_controllen = std::mem::size_of_val(&control);
    let n = unsafe {
        libc::recvmsg(
            socket.as_raw_fd(),
            &mut msg,
            libc::MSG_DONTWAIT | libc::MSG_CMSG_CLOEXEC,
        )
    };
    if n < 0 {
        let e = io::Error::last_os_error();
        return if e.kind() == io::ErrorKind::WouldBlock {
            Ok(None)
        } else {
            Err(e)
        };
    }
    let mut credentials = None;
    let mut malformed = false;
    unsafe {
        let mut header = libc::CMSG_FIRSTHDR(&msg);
        while !header.is_null() {
            let h = &*header;
            if h.cmsg_level == libc::SOL_SOCKET && h.cmsg_type == libc::SCM_RIGHTS {
                // A child has no input descriptors in this protocol. Close all
                // delivered FDs even on a rejected or truncated message.
                let base = libc::CMSG_LEN(0) as usize;
                if h.cmsg_len >= base {
                    let count = (h.cmsg_len - base) / std::mem::size_of::<RawFd>();
                    for i in 0..count {
                        let fd = std::ptr::read_unaligned(
                            libc::CMSG_DATA(header).cast::<RawFd>().add(i),
                        );
                        libc::close(fd);
                    }
                }
                malformed = true;
            } else if h.cmsg_level == libc::SOL_SOCKET
                && h.cmsg_type == libc::SCM_CREDENTIALS
                && h.cmsg_len == libc::CMSG_LEN(std::mem::size_of::<libc::ucred>() as u32) as usize
                && credentials.is_none()
            {
                credentials = Some(std::ptr::read_unaligned(
                    libc::CMSG_DATA(header).cast::<libc::ucred>(),
                ));
            } else {
                malformed = true;
            }
            header = libc::CMSG_NXTHDR(&msg, header);
        }
    }
    let c = credentials.ok_or_else(|| invalid("preparation request lacks kernel credentials"))?;
    if n != 1
        || msg.msg_flags & !libc::MSG_CMSG_CLOEXEC != 0
        || malformed
        || c.pid <= 1
        || c.pid as u32 != pid
        || c.uid != 0
        || c.gid != 0
    {
        return Err(invalid(
            "preparation request is not the same original collector and fixed byte",
        ));
    }
    Ok(Some(bytes[0]))
}
pub(crate) struct NativePreparationChannel {
    server: UnixDatagram,
    child: UnixDatagram,
    collector: Option<(u32, File)>,
    deadline: Instant,
    attempted: usize,
    failed: Option<String>,
    reads: Vec<PreparationReadObservation>,
}
impl NativePreparationChannel {
    pub(crate) fn new(deadline: Instant) -> Result<Self, String> {
        if Instant::now() >= deadline {
            return Err("preparation original work end expired".into());
        }
        let (server, child) = UnixDatagram::pair().map_err(|e| e.to_string())?;
        server.set_nonblocking(true).map_err(|e| e.to_string())?;
        let value: libc::c_int = 1;
        if unsafe {
            libc::setsockopt(
                server.as_raw_fd(),
                libc::SOL_SOCKET,
                libc::SO_PASSCRED,
                (&value as *const libc::c_int).cast(),
                std::mem::size_of_val(&value) as libc::socklen_t,
            )
        } != 0
        {
            return Err(io::Error::last_os_error().to_string());
        }
        Ok(Self {
            server,
            child,
            collector: None,
            deadline,
            attempted: 0,
            failed: None,
            reads: Vec::new(),
        })
    }
    pub(crate) fn prepare(&self, command: &mut Command) -> RawFd {
        command.env(ENV, self.child.as_raw_fd().to_string());
        self.child.as_raw_fd()
    }
    pub(crate) fn bind_child(&mut self, child: &Child) -> Result<(), String> {
        if self.collector.is_some() || Instant::now() >= self.deadline {
            return Err("preparation collector already bound or expired".into());
        }
        // This PID comes only from our own unreaped Child. It cannot be reused
        // while the normal Invocation retains that child and owns wait/reap.
        let pid = child.id();
        let raw = unsafe { libc::syscall(libc::SYS_pidfd_open, pid, 0) };
        if raw < 0 {
            return Err(io::Error::last_os_error().to_string());
        }
        let file = unsafe { File::from_raw_fd(raw as RawFd) };
        live(&file).map_err(|e| e.to_string())?;
        self.collector = Some((pid, file));
        Ok(())
    }
    pub(crate) fn serve(
        &mut self,
        baseline: &NativeLeafBaselineObservation<'_>,
        inspector: &NativeApplicationInspector,
    ) -> Result<(), String> {
        let (pid, pidfd) = self
            .collector
            .as_ref()
            .ok_or("preparation collector was never bound")?;
        let Some(token) = receive(&self.server, *pid).map_err(|e| e.to_string())? else {
            return Ok(());
        };
        if Instant::now() >= self.deadline {
            return Err("preparation request exceeded original collector end".into());
        }
        live(pidfd).map_err(|e| e.to_string())?;
        if self.failed.is_some() {
            self.server.send(b"1").map_err(|e| e.to_string())?;
            return Ok(());
        }
        if self.attempted >= KINDS.len() || token != TOKENS[self.attempted] {
            let _ = self.server.send(b"1");
            return Err("preparation command order, replay or payload differs".into());
        }
        let kind = KINDS[self.attempted];
        self.attempted += 1;
        let actual = (|| {
            baseline
                .verify_local(inspector, self.deadline)
                .map_err(|e| e.to_string())?;
            let observed = inspector
                .execute_preparation_read_until(
                    baseline.main(),
                    baseline.actual_application(),
                    kind,
                    self.deadline,
                )
                .map_err(|e| e.to_string())?;
            baseline
                .verify_local(inspector, self.deadline)
                .map_err(|e| e.to_string())?;
            live(pidfd).map_err(|e| e.to_string())?;
            if Instant::now() >= self.deadline {
                return Err("preparation reply exceeded original collector end".into());
            }
            let comparison = observed.comparison()?;
            let raw = serde_json::to_vec(&comparison).map_err(|e| e.to_string())?;
            let file = sealed_reply(&raw).map_err(|e| e.to_string())?;
            send_reply(&self.server, &file).map_err(|e| e.to_string())?;
            Ok(observed)
        })();
        match actual {
            Ok(value) => self.reads.push(value),
            Err(error) => {
                self.failed = Some(error);
                if Instant::now() >= self.deadline {
                    return Err("preparation failed after its original end".into());
                }
                // Keep G available for the collector's original finally path.
                // An attempted diagnostic is never repeated, even on unknown exit.
                self.server.send(b"1").map_err(|e| e.to_string())?;
            }
        }
        Ok(())
    }
    pub(crate) fn finish(
        self,
        baseline: &mut NativeLeafBaselineObservation<'_>,
        inspector: &NativeApplicationInspector,
    ) -> Result<(), String> {
        if let Some(error) = self.failed {
            return Err(format!("actual preparation diagnostic failed: {error}"));
        }
        if self.attempted != 3 || self.reads.len() != 3 || Instant::now() >= self.deadline {
            return Err("preparation diagnostics are incomplete or late".into());
        }
        baseline
            .record_preparation_reads(inspector, self.reads, self.deadline)
            .map_err(|e| e.to_string())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::{Read, Seek, SeekFrom};
    #[test]
    fn preparation_reply_fd_is_complete_readonly_sealed_and_cloexec() {
        let body = b"complete normal comparison";
        let source = sealed_reply(body).unwrap();
        let (tx, rx) = UnixDatagram::pair().unwrap();
        send_reply(&tx, &source).unwrap();
        let mut data = [0u8; 2];
        let mut iov = libc::iovec {
            iov_base: data.as_mut_ptr().cast(),
            iov_len: data.len(),
        };
        let mut control = [0usize; 4];
        let mut msg: libc::msghdr = unsafe { std::mem::zeroed() };
        msg.msg_iov = &mut iov;
        msg.msg_iovlen = 1;
        msg.msg_control = control.as_mut_ptr().cast();
        msg.msg_controllen = std::mem::size_of_val(&control);
        let n = unsafe { libc::recvmsg(rx.as_raw_fd(), &mut msg, libc::MSG_CMSG_CLOEXEC) };
        assert_eq!(n, 1);
        assert_eq!(data[0], b'R');
        assert_eq!(msg.msg_flags & !libc::MSG_CMSG_CLOEXEC, 0);
        let header = unsafe { libc::CMSG_FIRSTHDR(&msg) };
        assert!(!header.is_null());
        assert_eq!(unsafe { (*header).cmsg_level }, libc::SOL_SOCKET);
        assert_eq!(unsafe { (*header).cmsg_type }, libc::SCM_RIGHTS);
        assert_eq!(unsafe { (*header).cmsg_len }, unsafe {
            libc::CMSG_LEN(std::mem::size_of::<RawFd>() as u32)
        } as usize);
        assert!(unsafe { libc::CMSG_NXTHDR(&msg, header) }.is_null());
        let fd = unsafe { std::ptr::read_unaligned(libc::CMSG_DATA(header).cast::<RawFd>()) };
        let mut reader = unsafe { File::from_raw_fd(fd) };
        assert_eq!(
            (
                reader.metadata().unwrap().dev(),
                reader.metadata().unwrap().ino()
            ),
            (
                source.metadata().unwrap().dev(),
                source.metadata().unwrap().ino()
            )
        );
        assert_eq!(
            unsafe { libc::fcntl(fd, libc::F_GETFD) } & libc::FD_CLOEXEC,
            libc::FD_CLOEXEC
        );
        assert_eq!(
            unsafe { libc::fcntl(fd, libc::F_GETFL) } & libc::O_ACCMODE,
            libc::O_RDONLY
        );
        assert_eq!(unsafe { libc::fcntl(fd, libc::F_GET_SEALS) }, SEALS);
        let mut actual = Vec::new();
        reader.read_to_end(&mut actual).unwrap();
        assert_eq!(actual, body);
        assert!(reader.write_all(b"x").is_err());
        reader.seek(SeekFrom::Start(0)).unwrap();
        actual.clear();
        reader.read_to_end(&mut actual).unwrap();
        assert_eq!(actual, body);
        assert!(sealed_reply(&[]).is_err());
        assert!(
            sealed_reply(&vec![
                0;
                crate::native_preparation_read::MAX_RESPONSE_BYTES + 1
            ])
            .is_err()
        );
    }
    #[test]
    fn preparation_request_rejects_absent_or_wrong_credentials_and_input_rights() {
        let (tx, rx) = UnixDatagram::pair().unwrap();
        tx.send(b"U").unwrap();
        assert!(receive(&rx, std::process::id()).is_err()); // no SO_PASSCRED
        let value: libc::c_int = 1;
        assert_eq!(
            unsafe {
                libc::setsockopt(
                    rx.as_raw_fd(),
                    libc::SOL_SOCKET,
                    libc::SO_PASSCRED,
                    (&value as *const libc::c_int).cast(),
                    std::mem::size_of_val(&value) as libc::socklen_t,
                )
            },
            0
        );
        tx.send(b"U").unwrap();
        assert!(receive(&rx, std::process::id() + 1).is_err()); // actual kernel credential, wrong owned child
        let file = sealed_reply(b"unrequested input").unwrap();
        send_reply(&tx, &file).unwrap();
        assert!(receive(&rx, std::process::id()).is_err()); // any input descriptor is forbidden
        tx.send(b"UB").unwrap();
        assert!(receive(&rx, std::process::id()).is_err());
    }
}
