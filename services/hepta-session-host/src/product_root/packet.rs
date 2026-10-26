//! Bounded same-parent datagrams with exact kernel credentials and owned rights.
use super::{Result, process};
use std::mem;
use std::os::fd::{AsRawFd, FromRawFd, OwnedFd};
use std::os::unix::net::UnixDatagram;
use std::time::{Duration, Instant};

pub(super) enum ReadMode {
    Peek,
    Consume,
}

#[cfg(test)]
#[path = "packet_tests.rs"]
mod tests;
pub(super) enum Rights {
    None,
    One,
}

pub(super) fn remaining(end: Instant) -> Result<Duration> {
    end.checked_duration_since(Instant::now())
        .filter(|d| !d.is_zero() && *d <= Duration::from_secs(30))
        .ok_or_else(|| "original startup episode expired or exceeds 30 seconds".into())
}

pub(super) fn passcred(socket: &UnixDatagram) -> Result<()> {
    let value: libc::c_int = 1;
    // SAFETY: exact live socket and one initialized integer option.
    if unsafe {
        libc::setsockopt(
            socket.as_raw_fd(),
            libc::SOL_SOCKET,
            libc::SO_PASSCRED,
            std::ptr::from_ref(&value).cast(),
            mem::size_of_val(&value) as libc::socklen_t,
        )
    } != 0
    {
        return Err(std::io::Error::last_os_error().into());
    }
    Ok(())
}

pub(super) fn metadata(
    socket: &UnixDatagram,
    expected: libc::ucred,
    mode: ReadMode,
    expected_rights: Rights,
    end: Instant,
) -> Result<(Vec<u8>, Vec<OwnedFd>)> {
    socket.set_read_timeout(Some(remaining(end)?))?;
    let mut bytes = [0u8; 16_385];
    let mut control = [0usize; 64];
    let mut vector = libc::iovec {
        iov_base: bytes.as_mut_ptr().cast(),
        iov_len: bytes.len(),
    };
    // SAFETY: zeroed msghdr is initialized below with exact bounded live buffers.
    let mut message: libc::msghdr = unsafe { mem::zeroed() };
    message.msg_iov = &mut vector;
    message.msg_iovlen = 1;
    message.msg_control = control.as_mut_ptr().cast();
    message.msg_controllen = mem::size_of_val(&control);
    let flags = libc::MSG_CMSG_CLOEXEC
        | match mode {
            ReadMode::Peek => libc::MSG_PEEK,
            ReadMode::Consume => 0,
        };
    // SAFETY: all pointers reference the above live initialized bounded buffers.
    let count = unsafe { libc::recvmsg(socket.as_raw_fd(), &mut message, flags) };
    if count < 0 {
        return Err(std::io::Error::last_os_error().into());
    }
    let mut rights = Vec::new();
    let mut credential = None;
    let mut valid = true;
    // Adopt all kernel-delivered rights before any refusal, including PEEK
    // duplicates, so malformed or unexpected packets cannot leak descriptors.
    unsafe {
        let mut header = libc::CMSG_FIRSTHDR(&message);
        while !header.is_null() {
            let length = (*header).cmsg_len;
            let prefix = libc::CMSG_LEN(0) as usize;
            if length < prefix || length > message.msg_controllen {
                valid = false;
                break;
            }
            if (*header).cmsg_level != libc::SOL_SOCKET {
                valid = false;
            } else if (*header).cmsg_type == libc::SCM_RIGHTS {
                let n = length - prefix;
                if n % mem::size_of::<i32>() != 0 {
                    valid = false;
                }
                for index in 0..n / mem::size_of::<i32>() {
                    let raw = libc::CMSG_DATA(header)
                        .cast::<i32>()
                        .add(index)
                        .read_unaligned();
                    if raw >= 0 {
                        rights.push(OwnedFd::from_raw_fd(raw));
                    } else {
                        valid = false;
                    }
                }
            } else if (*header).cmsg_type == libc::SCM_CREDENTIALS
                && length == libc::CMSG_LEN(mem::size_of::<libc::ucred>() as u32) as usize
                && credential.is_none()
            {
                credential = Some(
                    libc::CMSG_DATA(header)
                        .cast::<libc::ucred>()
                        .read_unaligned(),
                );
            } else {
                valid = false;
            }
            header = libc::CMSG_NXTHDR(&message, header);
        }
    }
    let wanted = match expected_rights {
        Rights::None => 0,
        Rights::One => 1,
    };
    if !valid
        || count <= 0
        || count as usize > 16_384
        || message.msg_flags & (libc::MSG_TRUNC | libc::MSG_CTRUNC) != 0
        || rights.len() != wanted
        || credential
            .is_none_or(|c| c.pid != expected.pid || c.uid != expected.uid || c.gid != expected.gid)
    {
        return Err("original parent datagram credentials, rights or bounds differ".into());
    }
    remaining(end)?;
    Ok((bytes[..count as usize].to_vec(), rights))
}

pub(super) fn pinned_metadata(pidfd: &OwnedFd, pid: u32) -> Result<String> {
    process::alive(pidfd)?;
    let info = std::fs::read_to_string(format!("/proc/self/fdinfo/{}", pidfd.as_raw_fd()))?;
    if !info.lines().any(|s| {
        s.strip_prefix("Pid:")
            .is_some_and(|v| v.trim() == pid.to_string())
    }) {
        return Err("held descriptor does not name the actual child".into());
    }
    let stat = std::fs::read_to_string(format!("/proc/{pid}/stat"))?;
    let ticks = stat
        .rsplit_once(") ")
        .and_then(|(_, s)| s.split_whitespace().nth(19))
        .filter(|v| v.parse::<u64>().is_ok_and(|n| n > 0))
        .ok_or("actual child birth is missing")?;
    Ok(format!(
        "{}:{pid}:{ticks}",
        std::fs::read_to_string("/proc/sys/kernel/random/boot_id")?.trim()
    ))
}
