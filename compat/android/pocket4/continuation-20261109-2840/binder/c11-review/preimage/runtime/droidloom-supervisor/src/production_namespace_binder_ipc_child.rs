//! Test-only real IPC within the three already-created private Binder contexts.
//! No host Binder paths, policy changes, external FDs, exec, or numeric-PID kill.
//! The production build does not compile or invoke this module.
#![cfg(test)]

use super::private_binder::{protocol_failure, syscall_failure};
use super::{CHILD_FD, finish};
use std::ffi::CStr;
use std::os::fd::RawFd;

const MAP_BYTES: usize = 1024 * 1024;
const BINDER_WRITE_READ: libc::c_ulong = 0xc030_6201;
const BINDER_SET_CONTEXT_MGR_EXT: libc::c_ulong = 0x4018_620d;
const BINDER_GET_EXTENDED_ERROR: libc::c_ulong = 0xc00c_6211;
const BC_TRANSACTION: u32 = 0x4040_6300;
const BC_REPLY: u32 = 0x4040_6301;
const BC_FREE_BUFFER: u32 = 0x4008_6303;
const BC_ENTER_LOOPER: u32 = 0x0000_630c;
const BR_TRANSACTION_SEC_CTX: u32 = 0x8048_7202;
const BR_REPLY: u32 = 0x8040_7203;
const BR_NOOP: u32 = 0x0000_720c;
const BR_TRANSACTION_COMPLETE: u32 = 0x0000_7206;
const BR_FAILED_REPLY: u32 = 0x0000_7211;
const TEST_CODE: u32 = 1599098439;
const TEST_UID: u32 = 10001;
const REPLY_VALUE: u32 = 0x5034_4352;

#[repr(C)]
#[derive(Clone, Copy)]
struct Transaction {
    target: u64,
    cookie: u64,
    code: u32,
    flags: u32,
    sender_pid: i32,
    sender_euid: u32,
    data_size: u64,
    offsets_size: u64,
    buffer: u64,
    offsets: u64,
}
#[repr(C)]
struct SecctxTransaction {
    transaction: Transaction,
    secctx: u64,
}
#[repr(C)]
struct WriteRead {
    write_size: u64,
    write_consumed: u64,
    write_buffer: u64,
    read_size: u64,
    read_consumed: u64,
    read_buffer: u64,
}
#[repr(C)]
struct FlatObject {
    kind: u32,
    flags: u32,
    binder: u64,
    cookie: u64,
}
#[repr(C)]
struct ExtendedError {
    id: u32,
    command: u32,
    param: i32,
}
#[repr(C)]
struct CloneArgs {
    flags: u64,
    pidfd: u64,
    child_tid: u64,
    parent_tid: u64,
    exit_signal: u64,
    stack: u64,
    stack_size: u64,
    tls: u64,
    set_tid: u64,
    set_tid_size: u64,
    cgroup: u64,
}
#[repr(C)]
#[derive(Clone, Copy)]
struct ClientReport {
    passed: u32,
    uid: u32,
    system_errno: i32,
    failed_command: u32,
    extended_errno: i32,
}
const _: [(); 64] = [(); std::mem::size_of::<Transaction>()];
const _: [(); 72] = [(); std::mem::size_of::<SecctxTransaction>()];
const _: [(); 48] = [(); std::mem::size_of::<WriteRead>()];
const _: [(); 24] = [(); std::mem::size_of::<FlatObject>()];
const _: [(); 12] = [(); std::mem::size_of::<ExtendedError>()];
const _: [(); 88] = [(); std::mem::size_of::<CloneArgs>()];
const _: [(); 20] = [(); std::mem::size_of::<ClientReport>()];

fn now_ns() -> i64 {
    let mut time: libc::timespec = unsafe { std::mem::zeroed() };
    if unsafe { libc::syscall(libc::SYS_clock_gettime, libc::CLOCK_MONOTONIC, &mut time) } != 0 {
        return -1;
    }
    time.tv_sec
        .saturating_mul(1_000_000_000)
        .saturating_add(time.tv_nsec)
}

fn within(mapping: *mut libc::c_void, pointer: u64, bytes: usize) -> bool {
    let begin = mapping as usize;
    let p = pointer as usize;
    p >= begin && p - begin <= MAP_BYTES && bytes <= MAP_BYTES - (p - begin)
}

unsafe fn exchange(fd: RawFd, write: &[u8], read: &mut [u8], deadline: i64) -> Result<usize, i32> {
    let mut data = WriteRead {
        write_size: write.len() as u64,
        write_consumed: 0,
        write_buffer: write.as_ptr() as u64,
        read_size: read.len() as u64,
        read_consumed: 0,
        read_buffer: read.as_mut_ptr() as u64,
    };
    loop {
        if now_ns() < 0 || now_ns() >= deadline {
            return Err(libc::ETIMEDOUT);
        }
        let result = unsafe { libc::syscall(libc::SYS_ioctl, fd, BINDER_WRITE_READ, &mut data) };
        if result == 0 {
            if data.write_consumed != write.len() as u64 || data.read_consumed > read.len() as u64 {
                return Err(libc::EPROTO);
            }
            return Ok(data.read_consumed as usize);
        }
        let errno = unsafe { *libc::__errno_location() };
        if errno != libc::EINTR {
            return Err(errno);
        }
    }
}

unsafe fn transaction(
    fd: RawFd,
    command: u32,
    value: &Transaction,
    deadline: i64,
) -> Result<(), i32> {
    let mut bytes = [0_u8; 68];
    bytes[..4].copy_from_slice(&command.to_ne_bytes());
    unsafe {
        std::ptr::copy_nonoverlapping(
            (value as *const Transaction).cast::<u8>(),
            bytes.as_mut_ptr().add(4),
            64,
        );
    }
    unsafe { exchange(fd, &bytes, &mut [], deadline) }.map(|_| ())
}

unsafe fn free_buffer(fd: RawFd, pointer: u64, deadline: i64) -> Result<(), i32> {
    let mut bytes = [0_u8; 12];
    bytes[..4].copy_from_slice(&BC_FREE_BUFFER.to_ne_bytes());
    bytes[4..].copy_from_slice(&pointer.to_ne_bytes());
    unsafe { exchange(fd, &bytes, &mut [], deadline) }.map(|_| ())
}

unsafe fn open_device(path: &CStr) -> Result<RawFd, i32> {
    let raw = unsafe {
        libc::syscall(
            libc::SYS_openat,
            libc::AT_FDCWD,
            path.as_ptr(),
            libc::O_RDWR | libc::O_NONBLOCK | libc::O_CLOEXEC | libc::O_NOFOLLOW,
            0,
        )
    };
    if raw < 0 || raw > i32::MAX as libc::c_long {
        return Err(unsafe { *libc::__errno_location() });
    }
    Ok(raw as RawFd)
}

unsafe fn mapping(fd: RawFd) -> Result<*mut libc::c_void, i32> {
    let value = unsafe {
        libc::syscall(
            libc::SYS_mmap,
            0_usize,
            MAP_BYTES,
            libc::PROT_READ,
            libc::MAP_PRIVATE,
            fd,
            0_usize,
        )
    };
    if value == -1 {
        return Err(unsafe { *libc::__errno_location() });
    }
    Ok(value as *mut libc::c_void)
}

unsafe fn unconfined_label() -> Result<(), i32> {
    let raw = unsafe {
        libc::syscall(
            libc::SYS_openat,
            libc::AT_FDCWD,
            c"/proc/self/attr/current".as_ptr(),
            libc::O_RDONLY | libc::O_NONBLOCK | libc::O_CLOEXEC | libc::O_NOFOLLOW,
            0,
        )
    };
    if raw < 0 || raw > i32::MAX as libc::c_long {
        return Err(unsafe { *libc::__errno_location() });
    }
    let fd = raw as RawFd;
    let mut text = [0_u8; 32];
    let n = unsafe { libc::syscall(libc::SYS_read, fd, text.as_mut_ptr(), text.len()) };
    let mut extra = [0_u8; 1];
    let tail = unsafe { libc::syscall(libc::SYS_read, fd, extra.as_mut_ptr(), 1_usize) };
    unsafe {
        libc::syscall(libc::SYS_close, fd);
    }
    // This private host regression control is deliberately bound to the actual
    // unconfined label. A different LSM/profile must get its own reviewed test.
    if !((n == 10 && &text[..10] == b"unconfined") || (n == 11 && &text[..11] == b"unconfined\n"))
        || tail != 0
    {
        return Err(libc::EPROTO);
    }
    Ok(())
}

unsafe fn client(path: &CStr, output: RawFd, deadline: i64) -> ! {
    let mut result = ClientReport {
        passed: 0,
        uid: 0,
        system_errno: 0,
        failed_command: 0,
        extended_errno: 0,
    };
    let mut fd = -1;
    let mut map = std::ptr::null_mut();
    let attempt = (|| -> Result<(), i32> {
        if unsafe {
            libc::syscall(
                libc::SYS_prctl,
                libc::PR_SET_PDEATHSIG,
                libc::SIGKILL,
                0,
                0,
                0,
            )
        } != 0
            || unsafe { libc::syscall(libc::SYS_getppid) } != 1
            || unsafe { libc::syscall(libc::SYS_setgroups, 0_usize, std::ptr::null::<u32>()) } != 0
            || unsafe { libc::syscall(libc::SYS_setresgid, TEST_UID, TEST_UID, TEST_UID) } != 0
            || unsafe { libc::syscall(libc::SYS_setresuid, TEST_UID, TEST_UID, TEST_UID) } != 0
            || unsafe { libc::syscall(libc::SYS_getuid) } != TEST_UID as libc::c_long
            || unsafe { libc::syscall(libc::SYS_geteuid) } != TEST_UID as libc::c_long
            || unsafe { libc::syscall(libc::SYS_getgid) } != TEST_UID as libc::c_long
            || unsafe { libc::syscall(libc::SYS_getegid) } != TEST_UID as libc::c_long
            || unsafe { libc::syscall(libc::SYS_getgroups, 0_usize, std::ptr::null_mut::<u32>()) }
                != 0
        {
            return Err(libc::EPERM);
        }
        // setresgid/setresuid clear PDEATHSIG. Re-arm only after the final
        // credential change, then close the race against this exact PID 1.
        if unsafe {
            libc::syscall(
                libc::SYS_prctl,
                libc::PR_SET_PDEATHSIG,
                libc::SIGKILL,
                0,
                0,
                0,
            )
        } != 0
            || unsafe { libc::syscall(libc::SYS_getppid) } != 1
        {
            return Err(libc::EPERM);
        }
        result.uid = TEST_UID;
        unsafe {
            unconfined_label()?;
        }
        fd = unsafe { open_device(path)? };
        map = unsafe { mapping(fd)? };
        let mut request: Transaction = unsafe { std::mem::zeroed() };
        request.code = TEST_CODE;
        unsafe {
            transaction(fd, BC_TRANSACTION, &request, deadline)?;
        }
        loop {
            if now_ns() < 0 || now_ns() >= deadline {
                return Err(libc::ETIMEDOUT);
            }
            let mut bytes = [0_u8; 4096];
            let count = match unsafe { exchange(fd, &[], &mut bytes, deadline) } {
                Ok(value) => value,
                Err(libc::EAGAIN) => {
                    let mut poll = libc::pollfd {
                        fd,
                        events: libc::POLLIN,
                        revents: 0,
                    };
                    let rc = unsafe { libc::syscall(libc::SYS_poll, &mut poll, 1_usize, 5_i32) };
                    if rc < 0 && unsafe { *libc::__errno_location() } != libc::EINTR {
                        return Err(libc::EIO);
                    }
                    continue;
                }
                Err(error) => return Err(error),
            };
            let mut offset = 0;
            while offset < count {
                if count - offset < 4 {
                    return Err(libc::EPROTO);
                }
                let command = u32::from_ne_bytes(
                    bytes[offset..offset + 4]
                        .try_into()
                        .map_err(|_| libc::EPROTO)?,
                );
                offset += 4;
                let size = ((command >> 16) & 0x3fff) as usize;
                if size > count - offset {
                    return Err(libc::EPROTO);
                }
                match command {
                    BR_FAILED_REPLY => {
                        let mut error: ExtendedError = unsafe { std::mem::zeroed() };
                        if unsafe {
                            libc::syscall(
                                libc::SYS_ioctl,
                                fd,
                                BINDER_GET_EXTENDED_ERROR,
                                &mut error,
                            )
                        } != 0
                        {
                            return Err(unsafe { *libc::__errno_location() });
                        }
                        result.failed_command = error.command;
                        result.extended_errno = error.param;
                        return Err(libc::EPROTO);
                    }
                    BR_REPLY => {
                        let reply = unsafe {
                            std::ptr::read_unaligned(
                                bytes.as_ptr().add(offset).cast::<Transaction>(),
                            )
                        };
                        if reply.data_size != 4
                            || reply.offsets_size != 0
                            || !within(map, reply.buffer, 4)
                        {
                            return Err(libc::EPROTO);
                        }
                        let value = unsafe { std::ptr::read_unaligned(reply.buffer as *const u32) };
                        unsafe {
                            free_buffer(fd, reply.buffer, deadline)?;
                        }
                        if value != REPLY_VALUE {
                            return Err(libc::EPROTO);
                        }
                        result.passed = 1;
                        return Ok(());
                    }
                    BR_NOOP | BR_TRANSACTION_COMPLETE => {}
                    _ => return Err(libc::EPROTO),
                }
                offset += size;
            }
        }
    })();
    if let Err(error) = attempt {
        result.system_errno = error;
    }
    if !map.is_null() {
        unsafe {
            libc::syscall(libc::SYS_munmap, map, MAP_BYTES);
        }
    }
    if fd >= 0 {
        unsafe {
            libc::syscall(libc::SYS_close, fd);
        }
    }
    let n = unsafe {
        libc::syscall(
            libc::SYS_write,
            output,
            &result,
            std::mem::size_of::<ClientReport>(),
        )
    };
    unsafe {
        libc::syscall(libc::SYS_close, output);
        finish(
            if result.passed == 1 && n == std::mem::size_of::<ClientReport>() as libc::c_long {
                0
            } else {
                127
            },
        )
    }
}

unsafe fn peek(pidfd: RawFd) -> Result<Option<libc::siginfo_t>, i32> {
    let mut info: libc::siginfo_t = unsafe { std::mem::zeroed() };
    let rc = unsafe {
        libc::syscall(
            libc::SYS_waitid,
            libc::P_PIDFD,
            pidfd,
            &mut info,
            libc::WEXITED | libc::WNOHANG | libc::WNOWAIT,
            std::ptr::null_mut::<libc::rusage>(),
        )
    };
    if rc != 0 {
        return Err(unsafe { *libc::__errno_location() });
    }
    if unsafe { info.si_pid() } == 0 {
        Ok(None)
    } else {
        Ok(Some(info))
    }
}

unsafe fn retire(
    pidfd: RawFd,
    child: i32,
    kill: bool,
    deadline: i64,
) -> Result<libc::siginfo_t, i32> {
    if kill && unsafe { peek(pidfd)? }.is_none() {
        if unsafe {
            libc::syscall(
                libc::SYS_pidfd_send_signal,
                pidfd,
                libc::SIGKILL,
                std::ptr::null::<libc::siginfo_t>(),
                0_u32,
            )
        } != 0
            && unsafe { *libc::__errno_location() } != libc::ESRCH
        {
            return Err(unsafe { *libc::__errno_location() });
        }
    }
    loop {
        if let Some(observed) = unsafe { peek(pidfd)? } {
            if unsafe { observed.si_pid() } != child {
                return Err(libc::EPROTO);
            }
            let mut reaped: libc::siginfo_t = unsafe { std::mem::zeroed() };
            if unsafe {
                libc::syscall(
                    libc::SYS_waitid,
                    libc::P_PIDFD,
                    pidfd,
                    &mut reaped,
                    libc::WEXITED,
                    std::ptr::null_mut::<libc::rusage>(),
                )
            } != 0
                || unsafe { reaped.si_pid() } != child
                || reaped.si_code != observed.si_code
                || unsafe { reaped.si_status() } != unsafe { observed.si_status() }
            {
                return Err(libc::ECHILD);
            }
            return Ok(reaped);
        }
        if now_ns() < 0 || now_ns() >= deadline {
            return Err(libc::ETIMEDOUT);
        }
        let mut poll = libc::pollfd {
            fd: pidfd,
            events: libc::POLLIN,
            revents: 0,
        };
        let rc = unsafe { libc::syscall(libc::SYS_poll, &mut poll, 1_usize, 5_i32) };
        if rc < 0 && unsafe { *libc::__errno_location() } != libc::EINTR {
            return Err(libc::EIO);
        }
    }
}

unsafe fn one_case(path: &CStr, nonce: [u8; 16], deadline: i64) {
    let fd = match unsafe { open_device(path) } {
        Ok(value) => value,
        Err(_) => unsafe { syscall_failure(nonce, line!()) },
    };
    let map = match unsafe { mapping(fd) } {
        Ok(value) => value,
        Err(_) => unsafe { syscall_failure(nonce, line!()) },
    };
    let mut object = FlatObject {
        kind: 0x7362_2a85,
        flags: 0x1000,
        binder: 0,
        cookie: 0,
    };
    // No FD-acceptance flag: this test sends no objects or passed descriptors.
    if unsafe { libc::syscall(libc::SYS_ioctl, fd, BINDER_SET_CONTEXT_MGR_EXT, &mut object) } != 0 {
        unsafe { syscall_failure(nonce, line!()) }
    }
    if unsafe { exchange(fd, &BC_ENTER_LOOPER.to_ne_bytes(), &mut [], deadline) }.is_err() {
        unsafe { protocol_failure(nonce) }
    }
    let mut pipes = [-1_i32; 2];
    if unsafe {
        libc::syscall(
            libc::SYS_pipe2,
            pipes.as_mut_ptr(),
            libc::O_CLOEXEC | libc::O_NONBLOCK,
        )
    } != 0
    {
        unsafe { syscall_failure(nonce, line!()) }
    }
    let mut pidfd = -1_i32;
    let mut args: CloneArgs = unsafe { std::mem::zeroed() };
    args.flags = 0x1000; // CLONE_PIDFD, atomic custody of this exact child.
    args.pidfd = (&mut pidfd as *mut i32) as u64;
    args.exit_signal = libc::SIGCHLD as u64;
    let child = unsafe { libc::syscall(libc::SYS_clone3, &args, std::mem::size_of::<CloneArgs>()) };
    if child < 0 || child > i32::MAX as libc::c_long {
        unsafe { syscall_failure(nonce, line!()) }
    }
    if child == 0 {
        unsafe {
            libc::syscall(libc::SYS_close, CHILD_FD);
            libc::syscall(libc::SYS_close, pipes[0]);
            libc::syscall(libc::SYS_munmap, map, MAP_BYTES);
            libc::syscall(libc::SYS_close, fd);
            client(path, pipes[1], deadline);
        }
    }
    if pidfd < 0 {
        unsafe { protocol_failure(nonce) }
    }
    unsafe {
        libc::syscall(libc::SYS_close, pipes[1]);
    }
    let mut received = 0_u32;
    let mut failed = None;
    let result = (|| -> Result<(), i32> {
        loop {
            if unsafe { peek(pidfd)? }.is_some() {
                break;
            }
            if now_ns() < 0 || now_ns() >= deadline {
                return Err(libc::ETIMEDOUT);
            }
            let mut bytes = [0_u8; 4096];
            let count = match unsafe { exchange(fd, &[], &mut bytes, deadline) } {
                Ok(value) => value,
                Err(libc::EAGAIN) => {
                    let mut poll = libc::pollfd {
                        fd,
                        events: libc::POLLIN,
                        revents: 0,
                    };
                    unsafe {
                        libc::syscall(libc::SYS_poll, &mut poll, 1_usize, 5_i32);
                    }
                    continue;
                }
                Err(error) => return Err(error),
            };
            let mut offset = 0;
            while offset < count {
                if count - offset < 4 {
                    return Err(libc::EPROTO);
                }
                let command = u32::from_ne_bytes(
                    bytes[offset..offset + 4]
                        .try_into()
                        .map_err(|_| libc::EPROTO)?,
                );
                offset += 4;
                let size = ((command >> 16) & 0x3fff) as usize;
                if size > count - offset {
                    return Err(libc::EPROTO);
                }
                match command {
                    BR_TRANSACTION_SEC_CTX => {
                        let got = unsafe {
                            std::ptr::read_unaligned(
                                bytes.as_ptr().add(offset).cast::<SecctxTransaction>(),
                            )
                        };
                        received += 1;
                        if received != 1
                            || got.transaction.code != TEST_CODE
                            || got.transaction.flags != 0
                            || got.transaction.sender_pid != child as i32
                            || got.transaction.sender_euid != TEST_UID
                            || got.transaction.data_size != 0
                            || got.transaction.offsets_size != 0
                            || !within(map, got.transaction.buffer, 0)
                            || !within(map, got.secctx, 11)
                            || unsafe { std::slice::from_raw_parts(got.secctx as *const u8, 11) }
                                != b"unconfined\0"
                        {
                            return Err(libc::EPROTO);
                        }
                        let value = REPLY_VALUE;
                        let mut reply: Transaction = unsafe { std::mem::zeroed() };
                        reply.data_size = 4;
                        reply.buffer = (&value as *const u32) as u64;
                        unsafe {
                            transaction(fd, BC_REPLY, &reply, deadline)?;
                            free_buffer(fd, got.transaction.buffer, deadline)?;
                        }
                    }
                    BR_NOOP | BR_TRANSACTION_COMPLETE => {}
                    _ => return Err(libc::EPROTO),
                }
                offset += size;
            }
        }
        Ok(())
    })();
    if let Err(error) = result {
        failed = Some(error);
    }
    let cleanup_deadline = now_ns().saturating_add(250_000_000);
    let reaped = match unsafe { retire(pidfd, child as i32, failed.is_some(), cleanup_deadline) } {
        Ok(value) => value,
        Err(_) => unsafe { protocol_failure(nonce) },
    };
    let mut report: ClientReport = unsafe { std::mem::zeroed() };
    let n = unsafe {
        libc::syscall(
            libc::SYS_read,
            pipes[0],
            &mut report,
            std::mem::size_of::<ClientReport>(),
        )
    };
    let mut extra = [0_u8; 1];
    let end = unsafe { libc::syscall(libc::SYS_read, pipes[0], extra.as_mut_ptr(), 1_usize) };
    unsafe {
        libc::syscall(libc::SYS_close, pipes[0]);
        libc::syscall(libc::SYS_close, pidfd);
        libc::syscall(libc::SYS_munmap, map, MAP_BYTES);
        libc::syscall(libc::SYS_close, fd);
    }
    if failed.is_some()
        || reaped.si_code != libc::CLD_EXITED
        || unsafe { reaped.si_status() } != 0
        || received != 1
        || n != std::mem::size_of::<ClientReport>() as libc::c_long
        || end != 0
        || report.passed != 1
        || report.uid != TEST_UID
        || report.system_errno != 0
        || report.failed_command != 0
        || report.extended_errno != 0
    {
        unsafe { protocol_failure(nonce) }
    }
}

pub(super) unsafe fn run(nonce: [u8; 16]) {
    if unsafe { unconfined_label() }.is_err() {
        unsafe { protocol_failure(nonce) }
    }
    let start = now_ns();
    if start < 0 {
        unsafe { protocol_failure(nonce) }
    }
    // The caller's existing protocol bound is three seconds. The complete
    // three-context test shares a two-second deadline plus bounded reap.
    let deadline = start + 2_000_000_000;
    for path in [
        c"/dev/binderfs/binder",
        c"/dev/binderfs/hwbinder",
        c"/dev/binderfs/vndbinder",
    ] {
        unsafe {
            one_case(path, nonce, deadline);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn transaction_layout_matches_exact_x86_64_binder_uapi() {
        assert_eq!(std::mem::offset_of!(Transaction, sender_pid), 24);
        assert_eq!(std::mem::offset_of!(Transaction, data_size), 32);
        assert_eq!(std::mem::offset_of!(Transaction, buffer), 48);
        assert_eq!(std::mem::offset_of!(SecctxTransaction, secctx), 64);
        assert_eq!(
            BINDER_WRITE_READ,
            (3 << 30) | (48 << 16) | (b'b' as u64) << 8 | 1
        );
        assert_eq!(
            BINDER_SET_CONTEXT_MGR_EXT,
            (1 << 30) | (24 << 16) | (b'b' as u64) << 8 | 13
        );
    }
    #[test]
    fn kernel_data_pointer_must_stay_wholly_in_held_mapping() {
        let base = 0x1000_usize as *mut libc::c_void;
        assert!(within(base, 0x1000, MAP_BYTES));
        assert!(within(base, 0x1000 + MAP_BYTES as u64, 0));
        assert!(!within(base, 0xfff, 1));
        assert!(!within(base, 0x1000 + MAP_BYTES as u64, 1));
        assert!(!within(base, u64::MAX, 1));
        assert!(!within(base, 0x1000, MAP_BYTES + 1));
    }
}
