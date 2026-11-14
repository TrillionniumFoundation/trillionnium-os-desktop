//! Test-only fixed executable handoff. The production runtime uses the same
//! final-capability and execveat functions, with an unqualified profile gate.
use super::empty_root::KernelStatfs;
use super::{CHILD_FD, Packet, Phase, finish, send};
use std::os::fd::RawFd;

pub(super) fn decode_private_failure(value: i32) -> Option<(u32, u32, i32)> {
    let v = value as u32;
    let stage = (v >> 24) & 15;
    let line = (v >> 12) & 4095;
    let errno = (v & 4095) as i32;
    (v >> 28 == 5 && (1..=8).contains(&stage) && line != 0 && errno != 0)
        .then_some((stage, line, errno))
}
unsafe fn failed(nonce: [u8; 16], line: u32) -> ! {
    unsafe {
        let e = *libc::__errno_location();
        let e = if (1..4096).contains(&e) {
            e as u32
        } else {
            libc::EIO as u32
        };
        send(
            nonce,
            Phase::Failed,
            (0x5800_0000 | line << 12 | e) as i32,
            1,
        );
        finish(127)
    }
}
unsafe fn rejected(nonce: [u8; 16]) -> ! {
    unsafe {
        *libc::__errno_location() = libc::EPROTO;
        failed(nonce, line!())
    }
}
unsafe fn metadata(fd: RawFd, nonce: [u8; 16]) -> libc::stat {
    let mut out = unsafe { std::mem::zeroed() };
    if unsafe { libc::syscall(libc::SYS_fstat, fd, &mut out) } != 0 {
        unsafe { failed(nonce, line!()) }
    }
    out
}
fn same(a: &libc::stat, b: &libc::stat) -> bool {
    (
        a.st_dev,
        a.st_ino,
        a.st_mode,
        a.st_uid,
        a.st_gid,
        a.st_nlink,
        a.st_size,
        a.st_mtime,
        a.st_mtime_nsec,
        a.st_ctime,
        a.st_ctime_nsec,
    ) == (
        b.st_dev,
        b.st_ino,
        b.st_mode,
        b.st_uid,
        b.st_gid,
        b.st_nlink,
        b.st_size,
        b.st_mtime,
        b.st_mtime_nsec,
        b.st_ctime,
        b.st_ctime_nsec,
    )
}
unsafe fn received(nonce: [u8; 16], parent_pid: u32) -> RawFd {
    let mut packet = Packet::zeroed();
    let mut v = libc::iovec {
        iov_base: (&mut packet as *mut Packet).cast(),
        iov_len: std::mem::size_of::<Packet>(),
    };
    let mut ancillary = [0_usize; 16];
    let mut m: libc::msghdr = unsafe { std::mem::zeroed() };
    m.msg_iov = &mut v;
    m.msg_iovlen = 1;
    m.msg_control = ancillary.as_mut_ptr().cast();
    m.msg_controllen = std::mem::size_of_val(&ancillary);
    let n = unsafe { libc::syscall(libc::SYS_recvmsg, CHILD_FD, &mut m, libc::MSG_CMSG_CLOEXEC) };
    if n == 0 {
        unsafe { finish(0) }
    }
    if n != std::mem::size_of::<Packet>() as libc::c_long
        || m.msg_flags & (libc::MSG_TRUNC | libc::MSG_CTRUNC) != 0
        || !packet.matches(nonce, parent_pid)
        || packet.errno != 0
    {
        unsafe { rejected(nonce) }
    }
    let h = unsafe { libc::CMSG_FIRSTHDR(&m) };
    if packet.phase == Phase::Stop as u32 && h.is_null() {
        unsafe { finish(0) }
    }
    if packet.phase != Phase::PreparePostExecProbe as u32 || h.is_null() {
        unsafe { rejected(nonce) }
    }
    if unsafe { (*h).cmsg_level } != libc::SOL_SOCKET
        || unsafe { (*h).cmsg_type } != libc::SCM_RIGHTS
        || unsafe { (*h).cmsg_len } != unsafe { libc::CMSG_LEN(4) } as usize
        || !unsafe { libc::CMSG_NXTHDR(&m, h) }.is_null()
    {
        unsafe { rejected(nonce) }
    }
    let fd = unsafe { std::ptr::read_unaligned(libc::CMSG_DATA(h).cast::<i32>()) };
    if fd < 0 || fd == CHILD_FD {
        unsafe { rejected(nonce) }
    }
    if fd != 4 && unsafe { libc::syscall(libc::SYS_dup3, fd, 4, libc::O_CLOEXEC) } != 4 {
        unsafe { failed(nonce, line!()) }
    }
    if fd != 4 {
        unsafe {
            libc::syscall(libc::SYS_close, fd);
        }
    }
    if unsafe { libc::syscall(libc::SYS_close_range, 5_u32, u32::MAX, 0) } != 0 {
        unsafe { failed(nonce, line!()) }
    }
    4
}
unsafe fn executable(fd: RawFd, nonce: [u8; 16]) -> libc::stat {
    let st = unsafe { metadata(fd, nonce) };
    // The initial-root owner and exact full-body hash are checked by the
    // opaque test input before transmission. In the guest this host UID is
    // deliberately unmapped; no fake idmap or ownership rewrite is applied.
    if st.st_mode != libc::S_IFREG | 0o555
        || st.st_nlink != 1
        || !(64..=1_048_576).contains(&st.st_size)
    {
        unsafe { rejected(nonce) }
    }
    let mut fs: KernelStatfs = unsafe { std::mem::zeroed() };
    if unsafe { libc::syscall(libc::SYS_fstatfs, fd, &mut fs) } != 0 {
        unsafe { failed(nonce, line!()) }
    }
    if fs.f_flags as u64 & 8 != 0 {
        unsafe { rejected(nonce) }
    }
    let mut h = [0_u8; 64];
    if unsafe { libc::syscall(libc::SYS_pread64, fd, h.as_mut_ptr(), h.len(), 0) } != 64 {
        unsafe { failed(nonce, line!()) }
    }
    if &h[..7] != b"\x7fELF\x02\x01\x01"
        || u16::from_le_bytes([h[16], h[17]]) != 2
        || u16::from_le_bytes([h[18], h[19]]) != 62
    {
        unsafe { rejected(nonce) }
    }
    let x = unsafe {
        libc::syscall(
            libc::SYS_fgetxattr,
            fd,
            c"security.capability".as_ptr(),
            std::ptr::null::<u8>(),
            0,
        )
    };
    if x != -1 || ![libc::ENODATA, libc::EOPNOTSUPP].contains(&unsafe { *libc::__errno_location() })
    {
        unsafe { rejected(nonce) }
    }
    st
}
unsafe fn stdio(nonce: [u8; 16]) {
    for fd in 0..3 {
        unsafe {
            libc::syscall(libc::SYS_close, fd);
        }
    }
    let raw = unsafe {
        libc::syscall(
            libc::SYS_openat,
            libc::AT_FDCWD,
            c"/dev/null".as_ptr(),
            libc::O_RDWR | libc::O_CLOEXEC | libc::O_NOFOLLOW,
            0,
        )
    };
    if raw != 0 {
        unsafe { failed(nonce, line!()) }
    }
    let st = unsafe { metadata(0, nonce) };
    if st.st_mode & libc::S_IFMT != libc::S_IFCHR || st.st_rdev != libc::makedev(1, 3) {
        unsafe { rejected(nonce) }
    }
    for fd in 0..3 {
        if fd != 0 && unsafe { libc::syscall(libc::SYS_dup3, 0, fd, 0) } != fd as libc::c_long {
            unsafe { failed(nonce, line!()) }
        }
        if unsafe { libc::syscall(libc::SYS_fcntl, fd, libc::F_SETFD, 0) } != 0
            || unsafe { libc::syscall(libc::SYS_fcntl, fd, libc::F_GETFD) } != 0
        {
            unsafe { failed(nonce, line!()) }
        }
    }
}

pub(super) unsafe fn run(nonce: [u8; 16], parent_pid: u32) -> ! {
    unsafe {
        let fd = received(nonce, parent_pid);
        let initial = executable(fd, nonce);
        stdio(nonce);
        if libc::syscall(libc::SYS_fcntl, CHILD_FD, libc::F_GETFD)
            != libc::FD_CLOEXEC as libc::c_long
            || libc::syscall(libc::SYS_fcntl, fd, libc::F_GETFD) != libc::FD_CLOEXEC as libc::c_long
        {
            rejected(nonce)
        }
        // Only this fixed test image retains the inherited authenticated
        // endpoint across exec. The Android runtime endpoint remains CLOEXEC.
        if libc::syscall(libc::SYS_fcntl, CHILD_FD, libc::F_SETFD, 0) != 0 {
            failed(nonce, line!())
        }
        let error =
            super::final_exec::prepare(super::final_exec::FinalCapabilityProfile::PrivateZero);
        if error != 0 {
            *libc::__errno_location() = error;
            failed(nonce, line!())
        }
        let error = crate::production_runtime_seccomp::install();
        if error != 0 {
            *libc::__errno_location() = error;
            failed(nonce, line!())
        }
        if !same(&initial, &metadata(fd, nonce)) {
            rejected(nonce)
        }
        let mut hex = [0_u8; 33];
        let alphabet = b"0123456789abcdef";
        for i in 0..16 {
            hex[2 * i] = alphabet[(nonce[i] >> 4) as usize];
            hex[2 * i + 1] = alphabet[(nonce[i] & 15) as usize];
        }
        let mut parent = [0_u8; 11];
        let mut pos = 10;
        let mut value = parent_pid;
        if value <= 1 || value > i32::MAX as u32 {
            rejected(nonce)
        }
        while value != 0 {
            pos -= 1;
            parent[pos] = b'0' + (value % 10) as u8;
            value /= 10;
        }
        let argv = [
            c"droidloom-private-proc-postexec-v1".as_ptr(),
            hex.as_ptr().cast(),
            parent.as_ptr().add(pos).cast(),
            std::ptr::null(),
        ];
        let env = [std::ptr::null::<libc::c_char>()];
        *libc::__errno_location() = super::final_exec::exec_held(fd, argv.as_ptr(), env.as_ptr());
        failed(nonce, line!())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn production_postexec_failure_encoding_does_not_overlap_runtime_or_xattr_errno() {
        assert_eq!(
            decode_private_failure((0x5800_0000u32 | (120 << 12) | libc::EACCES as u32) as i32),
            Some((8, 120, 13))
        );
        for v in [0, 1, 4095, -1, 0x45001001, 0x59001001, 0x58000001] {
            assert_eq!(decode_private_failure(v), None);
        }
    }
}
