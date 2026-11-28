//! Fixed original linkerconfig boundary. Freestanding x86-64 Linux ELF;
//! no libc, dynamic linker, allocator, command interpreter or path arguments.
//! Its actual broker/MAC/namespace integration remains a production gate.
#![no_std]
#![no_main]
#![deny(unsafe_op_in_unsafe_fn)]
#[path = "production_activation_protocol.rs"]
mod protocol;
use core::arch::{asm, global_asm};
use core::panic::PanicInfo;
use protocol::*;
#[cfg(not(target_arch = "x86_64"))]
compile_error!("fixed linkerconfig trampoline requires x86-64 Linux");
global_asm!(
    ".section .text._start,\"ax\",@progbits",
    ".global _start",
    ".type _start,@function",
    "_start:",
    "xor ebp, ebp",
    "mov rdi, rsp",
    "and rsp, -16",
    "call linkerconfig_entry",
    "ud2",
);
const READ: i64 = 0;
const WRITE: i64 = 1;
const CLOSE: i64 = 3;
const FSTAT: i64 = 5;
const POLL: i64 = 7;
const IOCTL: i64 = 16;
const RT_SIGACTION: i64 = 13;
const RT_SIGPROCMASK: i64 = 14;
const PREAD64: i64 = 17;
const GETPID: i64 = 39;
const SOCKET: i64 = 41;
const CONNECT: i64 = 42;
const SENDMSG: i64 = 46;
const RECVMSG: i64 = 47;
const GETSOCKOPT: i64 = 55;
const CLONE: i64 = 56;
const FCNTL: i64 = 72;
const GETUID: i64 = 102;
const GETGID: i64 = 104;
const GETEUID: i64 = 107;
const GETEGID: i64 = 108;
const GETPPID: i64 = 110;
const FSTATFS: i64 = 138;
const PRCTL: i64 = 157;
const GETTID: i64 = 186;
const FGETXATTR: i64 = 193;
const CLOCK_GETTIME: i64 = 228;
const EXIT_GROUP: i64 = 231;
const TGKILL: i64 = 234;
const WAITID: i64 = 247;
const OPENAT: i64 = 257;
const DUP3: i64 = 292;
const PIPE2: i64 = 293;
const EXECVEAT: i64 = 322;
const PIDFD_SEND_SIGNAL: i64 = 424;
const CLONE3: i64 = 435;
const CLOSE_RANGE: i64 = 436;
const EIO: i32 = 5;
const EAGAIN: i64 = -11;
const EINTR: i64 = -4;
const EPROTO: i32 = 71;
const ETIMEDOUT: i32 = 110;
const EFBIG: i32 = 27;
const SIGKILL: i32 = 9;
const SIGCHLD: i32 = 17;
const POLLIN: i16 = 1;
const POLLOUT: i16 = 4;
const POLLERR: i16 = 8;
const POLLHUP: i16 = 16;
const POLLNVAL: i16 = 32;
const O_CLOEXEC: i32 = 0x80000;
const O_NONBLOCK: i32 = 0x800;
const MSG_DONTWAIT: i32 = 0x40;
const MSG_NOSIGNAL: i32 = 0x4000;
const MSG_CMSG_CLOEXEC: i32 = 0x40000000;
const CLD_EXITED: i32 = 1;
const CLD_KILLED: i32 = 2;
const CLD_DUMPED: i32 = 3;
type Result<T> = core::result::Result<T, i32>;
#[inline(always)]
unsafe fn syscall(n: i64, a: i64, b: i64, c: i64, d: i64, e: i64, f: i64) -> i64 {
    let result: i64;
    unsafe {
        asm!("syscall",inlateout("rax") n=>result,in("rdi") a,in("rsi") b,
        in("rdx") c,in("r10") d,in("r8") e,in("r9") f,
        lateout("rcx") _,lateout("r11") _,options(nostack));
    }
    result
}
#[inline(always)]
fn c(n: i64, a: i64, b: i64, d: i64) -> i64 {
    unsafe { syscall(n, a, b, d, 0, 0, 0) }
}
fn checked(value: i64) -> Result<i64> {
    if (-4095..0).contains(&value) {
        Err((-value) as i32)
    } else if value < 0 {
        Err(EPROTO)
    } else {
        Ok(value)
    }
}
fn finish(code: i32) -> ! {
    c(EXIT_GROUP, i64::from(code), 0, 0);
    unsafe {
        asm!("ud2", options(noreturn));
    }
}
#[panic_handler]
fn panic(_: &PanicInfo<'_>) -> ! {
    finish(127)
}

// The pinned prebuilt core archive retains this personality relocation even
// with panic=abort. An unexpected unwind terminates; it can never succeed.
#[unsafe(no_mangle)]
extern "C" fn rust_eh_personality() -> ! {
    finish(127)
}
// Volatile loops keep compiler-emitted aggregate intrinsics libc-independent.
#[unsafe(no_mangle)]
unsafe extern "C" fn memcpy(dst: *mut u8, src: *const u8, n: usize) -> *mut u8 {
    for i in 0..n {
        unsafe {
            dst.add(i).write_volatile(src.add(i).read_volatile());
        }
    }
    dst
}
#[unsafe(no_mangle)]
unsafe extern "C" fn memset(dst: *mut u8, v: i32, n: usize) -> *mut u8 {
    for i in 0..n {
        unsafe {
            dst.add(i).write_volatile(v as u8);
        }
    }
    dst
}
#[unsafe(no_mangle)]
unsafe extern "C" fn memcmp(a: *const u8, b: *const u8, n: usize) -> i32 {
    for i in 0..n {
        let x = unsafe { a.add(i).read_volatile() };
        let y = unsafe { b.add(i).read_volatile() };
        if x != y {
            return i32::from(x) - i32::from(y);
        }
    }
    0
}
#[unsafe(no_mangle)]
unsafe extern "C" fn bcmp(a: *const u8, b: *const u8, n: usize) -> i32 {
    unsafe { memcmp(a, b, n) }
}
#[repr(C)]
struct Time {
    seconds: i64,
    nanos: i64,
}
#[repr(C)]
struct PollFd {
    fd: i32,
    events: i16,
    revents: i16,
}
#[repr(C)]
struct IoVec {
    base: *mut u8,
    length: usize,
}
#[repr(C)]
struct Message {
    name: *mut u8,
    name_length: u32,
    pad0: u32,
    iov: *mut IoVec,
    iov_length: usize,
    control: *mut u8,
    control_length: usize,
    flags: i32,
    pad1: i32,
}
#[repr(C)]
struct Stat {
    dev: u64,
    ino: u64,
    links: u64,
    mode: u32,
    uid: u32,
    gid: u32,
    pad: u32,
    rdev: u64,
    size: i64,
    block_size: i64,
    blocks: i64,
    atime: i64,
    atime_ns: i64,
    mtime: i64,
    mtime_ns: i64,
    ctime: i64,
    ctime_ns: i64,
    unused: [i64; 3],
}
#[repr(C)]
struct StatFs {
    kind: i64,
    block_size: i64,
    blocks: u64,
    free: u64,
    available: u64,
    files: u64,
    free_files: u64,
    fsid: [i32; 2],
    name_length: i64,
    fragment_size: i64,
    flags: i64,
    spare: [i64; 4],
}
const _: () = assert!(core::mem::size_of::<Time>() == 16);
const _: () = assert!(core::mem::size_of::<PollFd>() == 8);
const _: () = assert!(core::mem::size_of::<Message>() == 56);
const _: () = assert!(core::mem::size_of::<IoVec>() == 16);
const _: () = assert!(core::mem::size_of::<Stat>() == 144);
const _: () = assert!(core::mem::size_of::<StatFs>() == 120);
fn now() -> Result<u64> {
    let mut t = Time {
        seconds: 0,
        nanos: 0,
    };
    checked(c(CLOCK_GETTIME, 1, (&mut t as *mut Time) as i64, 0))?;
    if t.seconds < 0 || !(0..1_000_000_000).contains(&t.nanos) {
        return Err(EPROTO);
    }
    (t.seconds as u64)
        .checked_mul(1_000_000_000)
        .and_then(|v| v.checked_add(t.nanos as u64))
        .ok_or(EPROTO)
}
fn before(deadline: u64) -> Result<()> {
    if now()? >= deadline {
        Err(ETIMEDOUT)
    } else {
        Ok(())
    }
}
fn wait_event(fd: i32, events: i16, deadline: u64) -> Result<i16> {
    loop {
        before(deadline)?;
        let remaining = deadline.checked_sub(now()?).ok_or(ETIMEDOUT)?;
        let millis = remaining.div_ceil(1_000_000).min(i32::MAX as u64) as i32;
        let mut event = PollFd {
            fd,
            events,
            revents: 0,
        };
        let r = c(
            POLL,
            (&mut event as *mut PollFd) as i64,
            1,
            i64::from(millis),
        );
        before(deadline)?;
        if r == EINTR {
            continue;
        }
        checked(r)?;
        if r == 0 {
            return Err(ETIMEDOUT);
        }
        if r != 1 || event.revents & (POLLERR | POLLNVAL) != 0 {
            return Err(EPROTO);
        }
        return Ok(event.revents);
    }
}
fn close(fd: i32) {
    if fd >= 0 {
        c(CLOSE, i64::from(fd), 0, 0);
    }
}
fn above_stdio(fd: i32) -> Result<i32> {
    if fd >= 3 {
        return Ok(fd);
    }
    let copied = checked(c(FCNTL, i64::from(fd), 1030, 3))? as i32;
    close(fd);
    Ok(copied)
}
fn metadata(fd: i32) -> Result<Stat> {
    let mut s: Stat = unsafe { core::mem::zeroed() };
    checked(c(FSTAT, i64::from(fd), (&mut s as *mut Stat) as i64, 0))?;
    Ok(s)
}
fn same_file(a: &Stat, b: &Stat) -> bool {
    a.dev == b.dev
        && a.ino == b.ino
        && a.links == b.links
        && a.mode == b.mode
        && a.uid == b.uid
        && a.gid == b.gid
        && a.size == b.size
        && a.mtime == b.mtime
        && a.mtime_ns == b.mtime_ns
        && a.ctime == b.ctime
        && a.ctime_ns == b.ctime_ns
}
fn original_input(fd: i32) -> Result<Stat> {
    let stat = metadata(fd)?;
    if stat.mode & 0o170000 != 0o100000
        || stat.uid != 0
        || stat.gid != 0
        || stat.links != 1
        || stat.mode & 0o6022 != 0
        || stat.mode & 0o111 == 0
        || !(64..=32 * 1024 * 1024).contains(&stat.size)
    {
        return Err(EPROTO);
    }
    let mut fs: StatFs = unsafe { core::mem::zeroed() };
    checked(c(
        FSTATFS,
        i64::from(fd),
        (&mut fs as *mut StatFs) as i64,
        0,
    ))?;
    if fs.flags & 7 != 7 || fs.flags & 8 != 0 {
        return Err(EPROTO);
    }
    if checked(c(FCNTL, i64::from(fd), 1, 0))? & 1 != 1
        || checked(c(FCNTL, i64::from(fd), 3, 0))? & (3 | 0x200000) != 0
    {
        return Err(EPROTO);
    }
    if unsafe {
        syscall(
            FGETXATTR,
            i64::from(fd),
            b"security.capability\0".as_ptr() as i64,
            0,
            0,
            0,
            0,
        )
    } != -61
    {
        return Err(EPROTO);
    }
    let mut elf = [0_u8; 64];
    if unsafe { syscall(PREAD64, i64::from(fd), elf.as_mut_ptr() as i64, 64, 0, 0, 0) } != 64
        || &elf[..7] != b"\x7fELF\x02\x01\x01"
        || ![2, 3].contains(&u16::from_le_bytes([elf[16], elf[17]]))
        || u16::from_le_bytes([elf[18], elf[19]]) != 62
        || !same_file(&stat, &metadata(fd)?)
    {
        return Err(EPROTO);
    }
    Ok(stat)
}
fn send_packet(fd: i32, p: &Packet, passed_fd: i32, data: &[u8], deadline: u64) -> Result<()> {
    if data.len() != p.data_length as usize || data.len() > DIAGNOSTIC_CHUNK {
        return Err(EPROTO);
    }
    let mut ancillary = [20_u64, 1_u64 | (1_u64 << 32), passed_fd as u32 as u64];
    let mut iov = [
        IoVec {
            base: (p as *const Packet).cast_mut().cast(),
            length: PACKET_BYTES,
        },
        IoVec {
            base: data.as_ptr().cast_mut(),
            length: data.len(),
        },
    ];
    let message = Message {
        name: core::ptr::null_mut(),
        name_length: 0,
        pad0: 0,
        iov: iov.as_mut_ptr(),
        iov_length: if data.is_empty() { 1 } else { 2 },
        control: if passed_fd >= 0 {
            ancillary.as_mut_ptr().cast()
        } else {
            core::ptr::null_mut()
        },
        control_length: if passed_fd >= 0 { 24 } else { 0 },
        flags: 0,
        pad1: 0,
    };
    loop {
        before(deadline)?;
        let r = c(
            SENDMSG,
            i64::from(fd),
            (&message as *const Message) as i64,
            i64::from(MSG_DONTWAIT | MSG_NOSIGNAL),
        );
        if r == EINTR {
            continue;
        }
        if r == EAGAIN {
            if wait_event(fd, POLLOUT, deadline)? & (POLLHUP | POLLOUT) != POLLOUT {
                return Err(EPROTO);
            }
            continue;
        }
        checked(r)?;
        before(deadline)?;
        return if r == (PACKET_BYTES + data.len()) as i64 {
            Ok(())
        } else {
            Err(EIO)
        };
    }
}
fn receive_packet(fd: i32, with_fd: bool, deadline: u64) -> Result<(Packet, i32)> {
    loop {
        before(deadline)?;
        if wait_event(fd, POLLIN, deadline)? & (POLLIN | POLLHUP) != POLLIN {
            return Err(EPROTO);
        }
        let mut p = Packet::empty(0);
        let mut ancillary = [0_u64; 8];
        let mut iov = IoVec {
            base: (&mut p as *mut Packet).cast(),
            length: PACKET_BYTES,
        };
        let mut message = Message {
            name: core::ptr::null_mut(),
            name_length: 0,
            pad0: 0,
            iov: &mut iov,
            iov_length: 1,
            control: ancillary.as_mut_ptr().cast(),
            control_length: core::mem::size_of_val(&ancillary),
            flags: 0,
            pad1: 0,
        };
        let r = c(
            RECVMSG,
            i64::from(fd),
            (&mut message as *mut Message) as i64,
            i64::from(MSG_DONTWAIT | MSG_CMSG_CLOEXEC),
        );
        if r == EINTR || r == EAGAIN {
            continue;
        }
        checked(r)?;
        before(deadline)?;
        if r != PACKET_BYTES as i64
            || message.flags & (0x20 | 0x8) != 0
            || !p.header_is_fixed()
            || p.data_length != 0
            || p.detail != 0
        {
            return Err(EPROTO);
        }
        let passed = if with_fd {
            if message.control_length != 24
                || ancillary[0] != 20
                || ancillary[1] != (1_u64 | (1_u64 << 32))
                || ancillary[2] >> 32 != 0
            {
                return Err(EPROTO);
            }
            above_stdio(ancillary[2] as i32)?
        } else {
            if message.control_length != 0 {
                return Err(EPROTO);
            }
            -1
        };
        return Ok((p, passed));
    }
}
fn connected_socket() -> Result<i32> {
    let fd = above_stdio(checked(c(SOCKET, 1, i64::from(5 | O_CLOEXEC | O_NONBLOCK), 0))? as i32)?;
    let mut address = [0_u8; 110];
    address[0] = 1;
    address[2..2 + SOCKET_PATH.len()].copy_from_slice(SOCKET_PATH);
    checked(c(
        CONNECT,
        i64::from(fd),
        address.as_ptr() as i64,
        (2 + SOCKET_PATH.len()) as i64,
    ))?;
    let mut peer = [0_u32; 3];
    let mut bytes = 12_u32;
    checked(unsafe {
        syscall(
            GETSOCKOPT,
            i64::from(fd),
            1,
            17,
            peer.as_mut_ptr() as i64,
            (&mut bytes as *mut u32) as i64,
            0,
        )
    })?;
    // The broker lives outside this PID namespace. This comparison confers no
    // authority: the broker must authenticate this actual peer PIDFD and MAC.
    if bytes != 12 || peer[0] != 0 {
        return Err(EPROTO);
    }
    Ok(fd)
}
fn new_pipe(blocking_writer: bool) -> Result<[i32; 2]> {
    let mut fds = [-1_i32; 2];
    checked(c(
        PIPE2,
        fds.as_mut_ptr() as i64,
        i64::from(O_CLOEXEC | O_NONBLOCK),
        0,
    ))?;
    fds[0] = above_stdio(fds[0])?;
    fds[1] = above_stdio(fds[1])?;
    if blocking_writer {
        let flags = checked(c(FCNTL, i64::from(fds[1]), 3, 0))?;
        checked(c(
            FCNTL,
            i64::from(fds[1]),
            4,
            flags & !i64::from(O_NONBLOCK),
        ))?;
    }
    Ok(fds)
}
struct State {
    socket: i32,
    original: i32,
    pidfd: i32,
    child_pid: i32,
    wrapper_pid: i32,
    session: Packet,
    stage: u32,
    reaped: bool,
    terminal_code: i32,
    terminal_status: i32,
    output: [u8; OUTPUT_LIMIT],
    output_length: usize,
}
impl State {
    fn new() -> Self {
        Self {
            socket: -1,
            original: -1,
            pidfd: -1,
            child_pid: 0,
            wrapper_pid: c(GETPID, 0, 0, 0) as i32,
            session: Packet::empty(HELLO),
            stage: HELLO,
            reaped: false,
            terminal_code: 0,
            terminal_status: 0,
            output: [0; OUTPUT_LIMIT],
            output_length: 0,
        }
    }
    fn record(&self, phase: u32) -> Packet {
        let mut p = self.session;
        p.phase = phase;
        p.child_pid = self.child_pid;
        p.exit_code = self.terminal_code;
        p.exit_status = self.terminal_status;
        p.error = 0;
        p.output_bytes = self.output_length as u64;
        p.data_length = 0;
        p.detail = 0;
        p.reserved = 0;
        p
    }
    fn expected(&self, phase: u32, terminal: bool) -> Result<()> {
        let (p, _) = receive_packet(self.socket, false, self.session.deadline_ns)?;
        if p.phase != phase
            || !p.session_matches(&self.session)
            || p.error != 0
            || p.output_bytes
                != if terminal {
                    self.output_length as u64
                } else {
                    0
                }
            || p.exit_code != if terminal { self.terminal_code } else { 0 }
            || p.exit_status != if terminal { self.terminal_status } else { 0 }
            || c(GETPPID, 0, 0, 0) != 1
        {
            return Err(EPROTO);
        }
        Ok(())
    }
    fn waitid(&mut self, keep: bool, deadline: u64) -> Result<()> {
        let mut info = [0_u64; 16];
        let flags = 4 | 1 | if keep { 0x01000000 } else { 0 };
        loop {
            before(deadline)?;
            let r = unsafe {
                syscall(
                    WAITID,
                    3,
                    i64::from(self.pidfd),
                    info.as_mut_ptr() as i64,
                    flags,
                    0,
                    0,
                )
            };
            if r == EINTR {
                continue;
            }
            checked(r)?;
            break;
        }
        let values = unsafe { core::slice::from_raw_parts(info.as_ptr().cast::<i32>(), 32) };
        let code = values[2];
        let status = values[6];
        if values[0] != SIGCHLD
            || values[4] != self.child_pid
            || values[5] != 0
            || ![CLD_EXITED, CLD_KILLED, CLD_DUMPED].contains(&code)
            || (code == CLD_EXITED && !(0..=255).contains(&status))
            || (code != CLD_EXITED && !(1..=64).contains(&status))
        {
            return Err(EPROTO);
        }
        if self.terminal_code != 0 && (self.terminal_code != code || self.terminal_status != status)
        {
            return Err(EPROTO);
        }
        self.terminal_code = code;
        self.terminal_status = status;
        if !keep {
            let mut event = PollFd {
                fd: self.pidfd,
                events: 0,
                revents: 0,
            };
            if c(POLL, (&mut event as *mut PollFd) as i64, 1, 0) != 1
                || event.revents & POLLHUP == 0
                || event.revents & (POLLERR | POLLNVAL) != 0
            {
                return Err(EPROTO);
            }
            self.reaped = true;
            let mut final_info = PidfdInfo::request_exit();
            checked(c(
                IOCTL,
                i64::from(self.pidfd),
                PIDFD_GET_INFO as i64,
                (&mut final_info as *mut PidfdInfo) as i64,
            ))?;
            if final_info.mask & PIDFD_INFO_EXIT == 0
                || raw_wait_status(code, status) != Some(final_info.exit_code)
            {
                return Err(EPROTO);
            }
        }
        before(deadline)
    }
    fn retire(&mut self) -> Result<()> {
        if self.reaped || self.child_pid == 0 {
            return Ok(());
        }
        if self.pidfd < 0 {
            return Err(EPROTO);
        }
        let r = unsafe {
            syscall(
                PIDFD_SEND_SIGNAL,
                i64::from(self.pidfd),
                i64::from(SIGKILL),
                0,
                0,
                0,
                0,
            )
        };
        if r != -3 {
            checked(r)?;
        }
        let deadline = now()?.checked_add(RETIREMENT_NS).ok_or(EPROTO)?;
        if wait_event(self.pidfd, POLLIN, deadline)? & POLLIN == 0 {
            return Err(EPROTO);
        }
        self.waitid(false, deadline)
    }
    fn fail(&mut self, error: i32) -> ! {
        let retired = self.retire().is_ok();
        if self.socket >= 0 {
            let mut p = self.record(FAILED);
            p.error = if (1..4096).contains(&error) {
                error
            } else {
                EPROTO
            };
            p.detail = self.stage | if retired { 0 } else { 0x80000000 };
            if let Ok(current) = now() {
                let _ = send_packet(
                    self.socket,
                    &p,
                    -1,
                    &[],
                    current.saturating_add(100_000_000),
                );
            }
        }
        finish(127)
    }
    fn drain_output(&mut self, fd: i32) -> Result<bool> {
        let mut chunk = [0_u8; 4096];
        loop {
            before(self.session.deadline_ns)?;
            let r = c(
                READ,
                i64::from(fd),
                chunk.as_mut_ptr() as i64,
                chunk.len() as i64,
            );
            if r == EINTR {
                continue;
            }
            if r == EAGAIN {
                return Ok(false);
            }
            checked(r)?;
            if r == 0 {
                return Ok(true);
            }
            let n = r as usize;
            let end = self.output_length.checked_add(n).ok_or(EFBIG)?;
            if end > OUTPUT_LIMIT {
                return Err(EFBIG);
            }
            self.output[self.output_length..end].copy_from_slice(&chunk[..n]);
            self.output_length = end;
        }
    }
    fn observe_exit(&mut self, errors: i32, output: i32) -> Result<()> {
        let mut exec_bytes = [0_u8; 4];
        let mut exec_length = 0;
        let mut exec_closed = false;
        loop {
            before(self.session.deadline_ns)?;
            if !exec_closed {
                let mut extra = [0_u8; 8];
                let r = c(
                    READ,
                    i64::from(errors),
                    extra.as_mut_ptr() as i64,
                    extra.len() as i64,
                );
                if r == 0 {
                    exec_closed = true;
                } else if r > 0 {
                    let end = exec_length + r as usize;
                    if end > 4 {
                        return Err(EPROTO);
                    }
                    exec_bytes[exec_length..end].copy_from_slice(&extra[..r as usize]);
                    exec_length = end;
                } else if r != EINTR && r != EAGAIN {
                    checked(r)?;
                }
            }
            if exec_length == 4 {
                let errno = i32::from_ne_bytes(exec_bytes);
                return Err(if (1..4096).contains(&errno) {
                    errno
                } else {
                    EPROTO
                });
            }
            if exec_closed && exec_length != 0 {
                return Err(EPROTO);
            }
            let output_closed = self.drain_output(output)?;
            let mut fds = [
                PollFd {
                    fd: self.pidfd,
                    events: POLLIN,
                    revents: 0,
                },
                PollFd {
                    fd: self.socket,
                    events: POLLIN,
                    revents: 0,
                },
                PollFd {
                    fd: if exec_closed { -1 } else { errors },
                    events: POLLIN,
                    revents: 0,
                },
                PollFd {
                    fd: if output_closed { -1 } else { output },
                    events: POLLIN,
                    revents: 0,
                },
            ];
            let remaining = self
                .session
                .deadline_ns
                .checked_sub(now()?)
                .ok_or(ETIMEDOUT)?;
            let r = c(
                POLL,
                fds.as_mut_ptr() as i64,
                fds.len() as i64,
                remaining.div_ceil(1_000_000).min(i32::MAX as u64) as i64,
            );
            before(self.session.deadline_ns)?;
            if r == EINTR {
                continue;
            }
            checked(r)?;
            if r == 0 {
                return Err(ETIMEDOUT);
            }
            if fds.iter().any(|fd| fd.revents & (POLLERR | POLLNVAL) != 0)
                || fds[1].revents & POLLHUP != 0
            {
                return Err(EPROTO);
            }
            if fds[1].revents & POLLIN != 0 {
                let (p, _) = receive_packet(self.socket, false, self.session.deadline_ns)?;
                if p.phase == CANCEL && p.session_matches(&self.session) {
                    return Err(125);
                }
                return Err(EPROTO);
            }
            if fds[0].revents & POLLIN != 0 {
                self.waitid(true, self.session.deadline_ns)?;
                // Recheck EOF after the same PIDFD exit. A surviving inherited
                // writer is not converted into a successful short helper.
                if !exec_closed {
                    let r = c(READ, i64::from(errors), exec_bytes.as_mut_ptr() as i64, 4);
                    if r != 0 {
                        return Err(if r == 4 {
                            let e = i32::from_ne_bytes(exec_bytes);
                            if (1..4096).contains(&e) { e } else { EPROTO }
                        } else {
                            EPROTO
                        });
                    }
                }
                if !self.drain_output(output)? {
                    return Err(EPROTO);
                }
                return before(self.session.deadline_ns);
            }
        }
    }
    fn perform(&mut self) -> Result<()> {
        self.socket = connected_socket()?;
        let handshake = now()?.checked_add(HANDSHAKE_NS).ok_or(EPROTO)?;
        let mut hello = Packet::empty(HELLO);
        hello.child_pid = self.wrapper_pid;
        send_packet(self.socket, &hello, -1, &[], handshake)?;
        self.stage = AUTH;
        let (auth, original) = receive_packet(self.socket, true, handshake)?;
        let current = now()?;
        if auth.phase != AUTH
            || !auth.nonempty_session()
            || auth.child_pid != 0
            || auth.error != 0
            || auth.exit_code != 0
            || auth.exit_status != 0
            || auth.output_bytes != 0
            || auth.deadline_ns <= current
            || auth.deadline_ns - current > MAX_COMMAND_NS
        {
            return Err(EPROTO);
        }
        self.session = auth;
        self.original = original;
        let original_identity = original_input(original)?;
        let gate = new_pipe(false)?;
        let errors = new_pipe(false)?;
        let output = new_pipe(true)?;
        let input = above_stdio(checked(unsafe {
            syscall(
                OPENAT,
                -100,
                b"/dev/null\0".as_ptr() as i64,
                i64::from(O_CLOEXEC | O_NONBLOCK),
                0,
                0,
                0,
            )
        })? as i32)?;
        before(self.session.deadline_ns)?;
        self.stage = CHILD;
        let mut pidfd = -1_i32;
        let args = [
            4096_u64,
            (&mut pidfd as *mut i32) as u64,
            0,
            0,
            SIGCHLD as u64,
            0,
            0,
            0,
        ];
        let mut pid = c(CLONE3, args.as_ptr() as i64, 64, 0);
        if pid == -38 {
            // The installed runtime filter returns ENOSYS for clone3. The
            // fallback still receives the original PIDFD atomically.
            pid = unsafe {
                syscall(
                    CLONE,
                    4096 | i64::from(SIGCHLD),
                    0,
                    (&mut pidfd as *mut i32) as i64,
                    0,
                    0,
                    0,
                )
            };
        }
        checked(pid)?;
        if pid == 0 {
            child(
                original,
                self.socket,
                self.wrapper_pid,
                gate,
                errors,
                output,
                input,
                self.session.deadline_ns,
            );
        }
        self.child_pid = pid as i32;
        self.pidfd = pidfd;
        if pidfd < 0 || pid > i64::from(i32::MAX) {
            close(gate[1]);
            return Err(EPROTO);
        }
        self.session.child_pid = self.child_pid;
        close(gate[0]);
        close(errors[1]);
        close(output[1]);
        close(input);
        send_packet(
            self.socket,
            &self.record(CHILD),
            self.pidfd,
            &[],
            self.session.deadline_ns,
        )?;
        self.stage = GO;
        self.expected(GO, false)?;
        if !same_file(&original_identity, &metadata(original)?) {
            return Err(EPROTO);
        }
        let go = [0x47_u8];
        if c(WRITE, i64::from(gate[1]), go.as_ptr() as i64, 1) != 1 {
            return Err(EIO);
        }
        close(gate[1]);
        self.stage = EXITED;
        self.observe_exit(errors[0], output[0])?;
        send_packet(
            self.socket,
            &self.record(EXITED),
            -1,
            &[],
            self.session.deadline_ns,
        )?;
        self.stage = REAP;
        self.expected(REAP, true)?;
        self.waitid(false, self.session.deadline_ns)?;
        if !same_file(&original_identity, &metadata(original)?) {
            return Err(EPROTO);
        }
        self.stage = REAPED;
        send_packet(
            self.socket,
            &self.record(REAPED),
            -1,
            &[],
            self.session.deadline_ns,
        )?;
        self.stage = DIAGNOSTIC;
        let mut offset = 0;
        while offset < self.output_length {
            let end = (offset + DIAGNOSTIC_CHUNK).min(self.output_length);
            let mut p = self.record(DIAGNOSTIC);
            p.output_bytes = offset as u64;
            p.data_length = (end - offset) as u32;
            send_packet(
                self.socket,
                &p,
                -1,
                &self.output[offset..end],
                self.session.deadline_ns,
            )?;
            offset = end;
        }
        self.stage = ACK;
        self.expected(ACK, true)?;
        before(self.session.deadline_ns)
    }
}
fn child(
    original: i32,
    control: i32,
    parent: i32,
    gate: [i32; 2],
    errors: [i32; 2],
    output: [i32; 2],
    input: i32,
    deadline: u64,
) -> ! {
    close(control);
    close(gate[1]);
    close(errors[0]);
    close(output[0]);
    let run = || -> Result<()> {
        checked(unsafe { syscall(PRCTL, 1, i64::from(SIGKILL), 0, 0, 0, 0) })?;
        if c(GETPPID, 0, 0, 0) != i64::from(parent) {
            return Err(EPROTO);
        }
        if wait_event(gate[0], POLLIN, deadline)? & POLLIN == 0 {
            return Err(EPROTO);
        }
        let mut go = [0_u8; 2];
        if c(READ, i64::from(gate[0]), go.as_mut_ptr() as i64, 2) != 1 || go[0] != 0x47 {
            return Err(EPROTO);
        }
        close(gate[0]);
        for (from, to) in [(input, 0_i32), (output[1], 1), (output[1], 2)] {
            checked(c(DUP3, i64::from(from), i64::from(to), 0))?;
        }
        checked(c(CLOSE_RANGE, 3, i64::from(u32::MAX), 4))?;
        before(deadline)?;
        let argv = [
            b"/system/bin/linkerconfig\0".as_ptr(),
            b"--target\0".as_ptr(),
            b"/linkerconfig\0".as_ptr(),
            core::ptr::null(),
        ];
        let env = [
            b"PATH=/system/bin\0".as_ptr(),
            b"ANDROID_ROOT=/system\0".as_ptr(),
            b"ANDROID_DATA=/data\0".as_ptr(),
            core::ptr::null(),
        ];
        checked(unsafe {
            syscall(
                EXECVEAT,
                i64::from(original),
                b"\0".as_ptr() as i64,
                argv.as_ptr() as i64,
                env.as_ptr() as i64,
                0x1000,
                0,
            )
        })?;
        Err(EPROTO)
    };
    let errno = match run() {
        Err(e) => e,
        Ok(()) => EPROTO,
    };
    c(
        WRITE,
        i64::from(errors[1]),
        (&errno as *const i32) as i64,
        4,
    );
    finish(127)
}
unsafe fn exact_arg(argument: *const u8, expected: &[u8]) -> bool {
    if argument.is_null() {
        return false;
    }
    for (i, wanted) in expected.iter().enumerate() {
        if unsafe { argument.add(i).read() } != *wanted {
            return false;
        }
    }
    true
}
fn entry_contract(stack: *const usize) -> Result<()> {
    let argc = unsafe { stack.read() };
    if argc != 3
        || !unsafe { exact_arg(stack.add(2).read() as *const u8, b"--target\0") }
        || !unsafe { exact_arg(stack.add(3).read() as *const u8, b"/linkerconfig\0") }
    {
        return Err(EPROTO);
    }
    for call in [GETUID, GETEUID, GETGID, GETEGID] {
        if c(call, 0, 0, 0) != 0 {
            return Err(EPROTO);
        }
    }
    if c(GETPID, 0, 0, 0) <= 1
        || c(GETPPID, 0, 0, 0) != 1
        || unsafe { syscall(PRCTL, 39, 0, 0, 0, 0, 0) } != 1
        || unsafe { syscall(PRCTL, 21, 0, 0, 0, 0, 0) } != 2
    {
        return Err(EPROTO);
    }
    // Reduce only this helper's dumpability. The original ELF's own post-exec
    // state still needs a separate actual capability/MAC/seccomp observation.
    checked(unsafe { syscall(PRCTL, 4, 0, 0, 0, 0, 0) })?;
    checked(unsafe { syscall(PRCTL, 1, i64::from(SIGKILL), 0, 0, 0, 0) })?;
    if c(GETPPID, 0, 0, 0) != 1 || unsafe { syscall(PRCTL, 3, 0, 0, 0, 0, 0) } != 0 {
        return Err(EPROTO);
    }
    let mut action = [0_u64; 4];
    checked(unsafe {
        syscall(
            RT_SIGACTION,
            i64::from(SIGCHLD),
            0,
            action.as_mut_ptr() as i64,
            8,
            0,
            0,
        )
    })?;
    if action[0] != 0 || action[1] & 2 != 0 {
        return Err(EPROTO);
    }
    Ok(())
}
#[unsafe(no_mangle)]
extern "C" fn linkerconfig_entry(stack: *const usize) -> ! {
    if entry_contract(stack).is_err() {
        finish(126);
    }
    let mut state = State::new();
    if let Err(error) = state.perform() {
        state.fail(error);
    }
    if !state.reaped {
        state.fail(EPROTO);
    }
    if state.terminal_code == CLD_EXITED {
        finish(state.terminal_status);
    }
    // Re-raise the original terminating signal. The complete original waitid
    // code/status is retained in the broker; core dumping is never enabled.
    let signal = state.terminal_status;
    let action = [0_u64; 4];
    let mask = 1_u64 << (signal - 1);
    if unsafe {
        syscall(
            RT_SIGACTION,
            i64::from(signal),
            action.as_ptr() as i64,
            0,
            8,
            0,
            0,
        )
    } != 0
        || unsafe { syscall(RT_SIGPROCMASK, 1, (&mask as *const u64) as i64, 0, 8, 0, 0) } != 0
    {
        finish(127);
    }
    c(
        TGKILL,
        c(GETPID, 0, 0, 0),
        c(GETTID, 0, 0, 0),
        i64::from(signal),
    );
    finish(127)
}
