use std::fs::File;
use std::os::fd::{AsRawFd, FromRawFd, OwnedFd};
use std::os::unix::fs::FileExt;
use std::time::{Duration, Instant};

fn main() {
    let tgid = std::process::id();
    let tid = unsafe { libc::syscall(libc::SYS_gettid) } as u32;
    assert_eq!(tgid, tid, "probe must create from the actual group leader");
    let raw = unsafe { libc::syscall(libc::SYS_pidfd_open, tid, libc::O_EXCL) };
    assert!(raw >= 0);
    let pidfd = unsafe { OwnedFd::from_raw_fd(raw as i32) };
    let status = File::open(format!("/proc/self/task/{tid}/stat")).unwrap();
    let (ready_tx, ready_rx) = std::sync::mpsc::sync_channel(0);
    std::thread::spawn(move || {
        let helper = unsafe { libc::syscall(libc::SYS_gettid) } as u32;
        assert_ne!(helper, tgid);
        ready_tx.send(()).unwrap();
        let deadline = Instant::now() + Duration::from_secs(3);
        loop {
            let mut bytes = [0_u8; 4096];
            let n = status.read_at(&mut bytes, 0).unwrap();
            let text = std::str::from_utf8(&bytes[..n]).unwrap();
            let after_comm = text.rsplit_once(')').unwrap().1;
            let fields: Vec<_> = after_comm.split_ascii_whitespace().collect();
            let state = fields[0];
            let flags: u64 = fields[6].parse().unwrap();
            let mut event = libc::pollfd {
                fd: pidfd.as_raw_fd(),
                events: libc::POLLIN,
                revents: 0,
            };
            let polled = unsafe { libc::poll(&mut event, 1, 0) };
            assert!(polled >= 0);
            if matches!(state, "Z" | "X") {
                println!(
                    "leader-exit observation: tgid={tgid} creator_tid={tid} helper_tid={helper} held_stat_state={state} held_stat_flags={flags} pf_exiting={} pidfd_poll_result={polled} pidfd_revents={} same_tgid_alive={}",
                    flags & 4 != 0,
                    event.revents,
                    std::process::id() == tgid,
                );
                std::process::exit(0);
            }
            assert!(Instant::now() < deadline, "leader did not reach kernel exit");
            std::thread::sleep(Duration::from_millis(2));
        }
    });
    ready_rx.recv().unwrap();
    unsafe {
        libc::syscall(libc::SYS_exit, 0);
        libc::_exit(99);
    }
}
