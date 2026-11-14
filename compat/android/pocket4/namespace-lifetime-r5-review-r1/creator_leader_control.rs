//! Actual group-leader arm/rearm controls against the same raw child source.
//! This program never maps identities, creates namespaces or grants admission.

use std::fs::File;
use std::io;
use std::os::fd::{AsRawFd, FromRawFd, OwnedFd};
use std::os::unix::fs::FileExt;
use std::time::{Duration, Instant};

#[derive(Debug)]
enum NamespaceError {
    Rejected(&'static str),
    Io(io::Error),
}
impl From<io::Error> for NamespaceError {
    fn from(error: io::Error) -> Self {
        Self::Io(error)
    }
}
type Result<T> = std::result::Result<T, NamespaceError>;

#[path = "../source/runtime/droidloom-supervisor/src/production_namespace_child.rs"]
mod child;
use child::{Packet, Phase};

struct Probe {
    pid: u32,
    wire_pid: u32,
    pidfd: OwnedFd,
    control: OwnedFd,
    parent: u32,
    nonce: [u8; 16],
    reaped: bool,
}
impl Probe {
    fn receive(&self, wanted: Phase) {
        let deadline = Instant::now() + Duration::from_secs(3);
        loop {
            let mut packet = Packet::zeroed();
            let n = unsafe {
                libc::recv(
                    self.control.as_raw_fd(),
                    (&mut packet as *mut Packet).cast(),
                    std::mem::size_of::<Packet>(),
                    libc::MSG_DONTWAIT | libc::MSG_TRUNC,
                )
            };
            if n >= 0 {
                assert_eq!(n as usize, std::mem::size_of::<Packet>());
                assert!(packet.matches(self.nonce, self.wire_pid));
                assert_eq!(packet.phase, wanted as u32);
                assert_eq!(packet.errno, 0);
                return;
            }
            assert_eq!(io::Error::last_os_error().kind(), io::ErrorKind::WouldBlock);
            assert!(Instant::now() < deadline, "private child protocol timeout");
            std::thread::sleep(Duration::from_millis(2));
        }
    }
    fn send(&self, phase: Phase) {
        let packet = Packet::new(self.nonce, phase, 0, self.parent);
        let n = unsafe {
            libc::send(
                self.control.as_raw_fd(),
                (&packet as *const Packet).cast(),
                std::mem::size_of::<Packet>(),
                libc::MSG_NOSIGNAL,
            )
        };
        assert_eq!(n as usize, std::mem::size_of::<Packet>());
    }
    fn signal(&self) {
        unsafe {
            libc::syscall(
                libc::SYS_pidfd_send_signal,
                self.pidfd.as_raw_fd(),
                libc::SIGKILL,
                std::ptr::null::<libc::siginfo_t>(),
                0,
            );
        }
    }
    fn reap(&mut self) -> (i32, i32) {
        let mut event = libc::pollfd {
            fd: self.pidfd.as_raw_fd(),
            events: libc::POLLIN,
            revents: 0,
        };
        if unsafe { libc::poll(&mut event, 1, 2000) } <= 0 {
            self.signal();
            assert!(unsafe { libc::poll(&mut event, 1, 2000) } > 0);
        }
        let mut info: libc::siginfo_t = unsafe { std::mem::zeroed() };
        assert_eq!(
            unsafe {
                libc::waitid(
                    libc::P_PIDFD,
                    self.pidfd.as_raw_fd() as u32,
                    &mut info,
                    libc::WEXITED | libc::WNOHANG,
                )
            },
            0
        );
        assert_eq!(unsafe { info.si_pid() }, self.pid as i32);
        self.reaped = true;
        (info.si_code, unsafe { info.si_status() })
    }
}
impl Drop for Probe {
    fn drop(&mut self) {
        if !self.reaped {
            self.signal();
            let _ = self.reap();
        }
    }
}

fn leader_case(rearm: bool) -> ! {
    let leader = std::process::id();
    assert_eq!(unsafe { libc::syscall(libc::SYS_gettid) } as u32, leader);
    let mode = if rearm {
        child::Mode::CreatorGoneBeforeRearm
    } else {
        child::Mode::CreatorGoneBeforeArm
    };
    let (pid, pidfd, control, parent, creator_tid, nonce) = child::spawn(mode).unwrap();
    assert_eq!(creator_tid as u32, leader);
    assert_eq!(parent, leader);
    let mut probe = Probe {
        pid,
        wire_pid: pid,
        pidfd,
        control,
        parent,
        nonce,
        reaped: false,
    };
    probe.receive(Phase::Created);
    if rearm {
        probe.send(Phase::Enter);
        probe.receive(Phase::Parked);
    }
    let stat = File::open(format!("/proc/self/task/{leader}/stat")).unwrap();
    let raw = unsafe { libc::syscall(libc::SYS_pidfd_open, leader, libc::O_EXCL) };
    assert!(raw >= 0);
    let creator_pidfd = unsafe { OwnedFd::from_raw_fd(raw as i32) };
    let (ready_tx, ready_rx) = std::sync::mpsc::sync_channel(0);
    std::thread::spawn(move || {
        let outcome = std::panic::catch_unwind(std::panic::AssertUnwindSafe(move || {
            ready_tx.send(()).unwrap();
            let deadline = Instant::now() + Duration::from_secs(3);
            let (state, flags) = loop {
                let mut bytes = [0_u8; 4096];
                let count = stat.read_at(&mut bytes, 0).unwrap();
                let raw = std::str::from_utf8(&bytes[..count]).unwrap();
                let tail = raw.rsplit_once(')').unwrap().1;
                let fields: Vec<_> = tail.split_ascii_whitespace().collect();
                let flags: u64 = fields[6].parse().unwrap();
                if matches!(fields[0], "Z" | "X") {
                    break (fields[0].to_owned(), flags);
                }
                assert!(
                    Instant::now() < deadline,
                    "actual leader kernel exit not observed"
                );
                std::thread::sleep(Duration::from_millis(2));
            };
            assert_ne!(flags & 4, 0);
            let mut event = libc::pollfd {
                fd: creator_pidfd.as_raw_fd(),
                events: libc::POLLIN,
                revents: 0,
            };
            assert_eq!(unsafe { libc::poll(&mut event, 1, 0) }, 0);
            assert_eq!(event.revents, 0);
            assert_eq!(std::process::id(), leader);
            probe.send(if rearm { Phase::Go } else { Phase::Enter });
            let (reason, status) = probe.reap();
            println!(
                "leader creator control rearm={rearm}: creator_tid=tgid={leader}; held_stat_state={state}; held_stat_flags={flags}; creator_pidfd_readable=false; same_tgid_alive=true; child_pid={pid}; child_waitid_reason={reason}; child_exit={status}; actually_reaped=true; expected_exit=125; production_admission=false Android_starts=0"
            );
            reason == libc::CLD_EXITED && status == 125
        }));
        std::process::exit(if matches!(outcome, Ok(true)) { 0 } else { 1 });
    });
    ready_rx.recv().unwrap();
    unsafe {
        libc::syscall(libc::SYS_exit, 0); // only the actual creating group leader
        libc::_exit(99);
    }
}

fn send_creator_fd(keeper: &Probe, creator: &OwnedFd) {
    let packet = Packet::new(keeper.nonce, Phase::PrepareTree, 0, keeper.parent);
    let mut iov = libc::iovec {
        iov_base: (&packet as *const Packet).cast_mut().cast(),
        iov_len: std::mem::size_of::<Packet>(),
    };
    let mut ancillary = [0_usize; 4];
    let mut message: libc::msghdr = unsafe { std::mem::zeroed() };
    message.msg_iov = &mut iov;
    message.msg_iovlen = 1;
    message.msg_control = ancillary.as_mut_ptr().cast();
    message.msg_controllen =
        unsafe { libc::CMSG_SPACE(std::mem::size_of::<i32>() as u32) } as usize;
    unsafe {
        let header = libc::CMSG_FIRSTHDR(&message);
        (*header).cmsg_level = libc::SOL_SOCKET;
        (*header).cmsg_type = libc::SCM_RIGHTS;
        (*header).cmsg_len = libc::CMSG_LEN(std::mem::size_of::<i32>() as u32) as usize;
        std::ptr::write_unaligned(libc::CMSG_DATA(header).cast::<i32>(), creator.as_raw_fd());
        assert_eq!(
            libc::sendmsg(keeper.control.as_raw_fd(), &message, libc::MSG_NOSIGNAL),
            std::mem::size_of::<Packet>() as isize
        );
    }
}

fn receive_tree(keeper: &Probe) -> Probe {
    let deadline = Instant::now() + Duration::from_secs(3);
    loop {
        let mut packet = Packet::zeroed();
        let mut iov = libc::iovec {
            iov_base: (&mut packet as *mut Packet).cast(),
            iov_len: std::mem::size_of::<Packet>(),
        };
        let mut ancillary = [0_usize; 16];
        let mut message: libc::msghdr = unsafe { std::mem::zeroed() };
        message.msg_iov = &mut iov;
        message.msg_iovlen = 1;
        message.msg_control = ancillary.as_mut_ptr().cast();
        message.msg_controllen = std::mem::size_of_val(&ancillary);
        let n = unsafe {
            libc::recvmsg(
                keeper.control.as_raw_fd(),
                &mut message,
                libc::MSG_DONTWAIT | libc::MSG_CMSG_CLOEXEC,
            )
        };
        if n < 0 {
            assert_eq!(io::Error::last_os_error().kind(), io::ErrorKind::WouldBlock);
            assert!(
                Instant::now() < deadline,
                "tree descriptor protocol timeout"
            );
            std::thread::sleep(Duration::from_millis(2));
            continue;
        }
        assert_eq!(n as usize, std::mem::size_of::<Packet>());
        assert_eq!(message.msg_flags & (libc::MSG_TRUNC | libc::MSG_CTRUNC), 0);
        let mut received = None;
        let mut credentials = None;
        let mut header = unsafe { libc::CMSG_FIRSTHDR(&message) };
        while !header.is_null() {
            let h = unsafe { &*header };
            assert_eq!(h.cmsg_level, libc::SOL_SOCKET);
            match h.cmsg_type {
                libc::SCM_RIGHTS => {
                    assert!(received.is_none());
                    assert_eq!(h.cmsg_len, unsafe { libc::CMSG_LEN(8) } as usize);
                    let values = unsafe {
                        std::ptr::read_unaligned(libc::CMSG_DATA(header).cast::<[i32; 2]>())
                    };
                    received = Some(unsafe {
                        [
                            OwnedFd::from_raw_fd(values[0]),
                            OwnedFd::from_raw_fd(values[1]),
                        ]
                    });
                }
                libc::SCM_CREDENTIALS => {
                    assert!(credentials.is_none());
                    assert_eq!(h.cmsg_len, unsafe {
                        libc::CMSG_LEN(std::mem::size_of::<libc::ucred>() as u32)
                    } as usize);
                    credentials = Some(unsafe {
                        std::ptr::read_unaligned(libc::CMSG_DATA(header).cast::<libc::ucred>())
                    });
                }
                _ => panic!("unexpected private tree ancillary record"),
            }
            header = unsafe { libc::CMSG_NXTHDR(&message, header) };
        }
        let [pidfd, control] = received.expect("actual clone pidfd and private control");
        let info =
            std::fs::read_to_string(format!("/proc/self/fdinfo/{}", pidfd.as_raw_fd())).unwrap();
        let pid = info
            .lines()
            .find_map(|line| line.strip_prefix("Pid:"))
            .unwrap()
            .trim()
            .parse::<u32>()
            .unwrap();
        let init = Probe {
            pid,
            wire_pid: 1,
            pidfd,
            control,
            parent: keeper.parent,
            nonce: keeper.nonce,
            reaped: false,
        };
        let credentials = credentials.unwrap();
        assert_eq!(
            (credentials.pid, credentials.uid, credentials.gid),
            (keeper.pid as i32, 200000, 200000)
        );
        assert!(packet.matches(keeper.nonce, keeper.pid));
        assert_eq!(packet.phase, Phase::TreeSpawned as u32);
        assert_eq!(packet.errno, 0);
        return init;
    }
}

fn nested_leader_case() -> ! {
    assert_eq!(unsafe { libc::getuid() }, 0);
    assert_eq!(unsafe { libc::geteuid() }, 0);
    let leader = std::process::id();
    assert_eq!(unsafe { libc::syscall(libc::SYS_gettid) } as u32, leader);
    let (pid, pidfd, control, parent, creator_tid, nonce) =
        child::spawn(child::Mode::TreeCreatorGoneBeforeArm).unwrap();
    assert_eq!(creator_tid as u32, leader);
    let mut keeper = Probe {
        pid,
        wire_pid: pid,
        pidfd,
        control,
        parent,
        nonce,
        reaped: false,
    };
    keeper.receive(Phase::Created);
    keeper.send(Phase::Enter);
    keeper.receive(Phase::Ready);
    // Only the unreaped clone3 child from this Probe can own this proc name.
    // These are fixed synthetic mappings, never host grants or live admission.
    assert_eq!(
        std::fs::read(format!("/proc/{pid}/setgroups")).unwrap(),
        b"allow\n"
    );
    std::fs::write(format!("/proc/{pid}/uid_map"), b"0 200000 100000\n").unwrap();
    std::fs::write(format!("/proc/{pid}/gid_map"), b"0 200000 100000\n").unwrap();
    keeper.send(Phase::Go);
    keeper.receive(Phase::Mapped);
    let raw = unsafe { libc::syscall(libc::SYS_pidfd_open, leader, libc::O_EXCL) };
    assert!(raw >= 0);
    let creator_pidfd = unsafe { OwnedFd::from_raw_fd(raw as i32) };
    let stat = File::open(format!("/proc/self/task/{leader}/stat")).unwrap();
    send_creator_fd(&keeper, &creator_pidfd);
    let mut init = receive_tree(&keeper);
    init.receive(Phase::TreeCreatedUnarmed);
    let init_pid = init.pid;
    let (ready_tx, ready_rx) = std::sync::mpsc::sync_channel(0);
    std::thread::spawn(move || {
        let outcome = std::panic::catch_unwind(std::panic::AssertUnwindSafe(move || {
            ready_tx.send(()).unwrap();
            let deadline = Instant::now() + Duration::from_secs(3);
            let flags = loop {
                let mut bytes = [0_u8; 4096];
                let n = stat.read_at(&mut bytes, 0).unwrap();
                let raw = std::str::from_utf8(&bytes[..n]).unwrap();
                let fields: Vec<_> = raw
                    .rsplit_once(')')
                    .unwrap()
                    .1
                    .split_ascii_whitespace()
                    .collect();
                if matches!(fields[0], "Z" | "X") {
                    break fields[6].parse::<u64>().unwrap();
                }
                assert!(
                    Instant::now() < deadline,
                    "nested creator leader did not exit"
                );
                std::thread::sleep(Duration::from_millis(2));
            };
            assert_ne!(flags & 4, 0);
            let mut event = libc::pollfd {
                fd: creator_pidfd.as_raw_fd(),
                events: libc::POLLIN,
                revents: 0,
            };
            assert_eq!(unsafe { libc::poll(&mut event, 1, 0) }, 0);
            assert_eq!(event.revents, 0);
            assert_eq!(std::process::id(), leader);
            init.send(Phase::Enter);
            let init_exit = init.reap();
            let keeper_exit = keeper.reap();
            println!(
                "nested leader creator control: creator_tid=tgid={leader}; held_stat_flags={flags}; creator_pidfd_readable=false; same_tgid_alive=true; init_pid={init_pid}; init_waitid_reason={}; init_exit={}; keeper_pid={pid}; keeper_waitid_reason={}; keeper_exit={}; init_actually_reaped=true; keeper_actually_reaped=true; expected_init_exit=125; production_admission=false Android_starts=0",
                init_exit.0, init_exit.1, keeper_exit.0, keeper_exit.1
            );
            init_exit == (libc::CLD_EXITED, 125) && keeper_exit == (libc::CLD_KILLED, libc::SIGKILL)
        }));
        std::process::exit(if matches!(outcome, Ok(true)) { 0 } else { 1 });
    });
    ready_rx.recv().unwrap();
    unsafe {
        libc::syscall(libc::SYS_exit, 0);
        libc::_exit(99);
    }
}

fn main() {
    match std::env::args().nth(1).as_deref() {
        Some("initial") => leader_case(false),
        Some("rearm") => leader_case(true),
        Some("nested") => nested_leader_case(),
        None => {
            let executable = std::env::current_exe().unwrap();
            let mut failed = false;
            for case in ["initial", "rearm"] {
                let result = std::process::Command::new(&executable)
                    .arg(case)
                    .output()
                    .unwrap();
                print!("{}", String::from_utf8_lossy(&result.stdout));
                eprint!("{}", String::from_utf8_lossy(&result.stderr));
                println!(
                    "leader outer owned process case={case} exit={:?} reaped=true",
                    result.status.code()
                );
                let text = String::from_utf8_lossy(&result.stdout);
                let marker = format!("leader creator control rearm={}", case == "rearm");
                let records: Vec<_> = text
                    .lines()
                    .filter(|line| line.starts_with(&marker))
                    .collect();
                failed |= !result.status.success()
                    || records.len() != 1
                    || !records[0].contains("child_exit=125; actually_reaped=true;");
            }
            std::process::exit(i32::from(failed));
        }
        _ => panic!("only the two fixed private leader cases are accepted"),
    }
}
