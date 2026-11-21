//! Read-only placement observation of the original init's current threads.
//!
//! Only the actually executed owner can issue this observation. Every use
//! rereads the complete current task directory and every held thread's real
//! procfs identity and cgroup record. Threads may legitimately start or exit
//! between observations; an unstable individual scan is rejected. Two stable
//! scans are not an atomic snapshot and do not prove the absence of a
//! short-lived thread between the scans.
//!
//! This observes init placement, not Android named task-profile actions,
//! non-leader capability policy, APEX activation or execution admission.

use std::collections::BTreeMap;
use std::ffi::{CStr, CString};
use std::fs::{File, Metadata};
use std::io::{self, Read};
use std::marker::PhantomData;
use std::os::fd::{AsRawFd, FromRawFd};
use std::os::unix::fs::MetadataExt;
use std::rc::Rc;
use std::time::{Duration, Instant};

use thiserror::Error;

use crate::production_cgroup::INIT_CGROUP_PATH;
use crate::production_namespace::{ExecutedInitGeneration, ExecutedInitWitness};

const PROC_MAGIC: libc::c_long = 0x9fa0;
const STATUS_LIMIT: usize = 64 * 1024;
const CGROUP_LIMIT: usize = 4096;
// The existing fixed production pids.max is 32768. Observation cannot accept
// a larger task group or grow without a finite byte and wall-clock budget.
const MAX_THREADS: usize = 32768;
const DIRECTORY_LIMIT: usize = MAX_THREADS * 32 + 64;
const OBSERVATION_LIMIT: Duration = Duration::from_secs(2);

#[derive(Debug, Error)]
pub(super) enum ObservationError {
    #[error("original init thread placement rejected: {0}")]
    Rejected(&'static str),
    #[error("original init thread owner observation failed: {0}")]
    Owner(String),
    #[error(transparent)]
    Io(#[from] io::Error),
}

type Result<T> = std::result::Result<T, ObservationError>;

fn require(value: bool, reason: &'static str) -> Result<()> {
    if value {
        Ok(())
    } else {
        Err(ObservationError::Rejected(reason))
    }
}

fn before(deadline: Instant) -> Result<()> {
    require(
        Instant::now() < deadline,
        "thread observation deadline elapsed",
    )
}

fn owner<T>(
    result: std::result::Result<T, crate::production_namespace::NamespaceError>,
) -> Result<T> {
    result.map_err(|error| ObservationError::Owner(error.to_string()))
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct ProcNode {
    device: u64,
    inode: u64,
    mode: u32,
    uid: u32,
    gid: u32,
}

impl ProcNode {
    fn of(metadata: &Metadata) -> Self {
        Self {
            device: metadata.dev(),
            inode: metadata.ino(),
            mode: metadata.mode(),
            uid: metadata.uid(),
            gid: metadata.gid(),
        }
    }
}

fn proc_node(file: &File, kind: u32) -> Result<ProcNode> {
    let metadata = file.metadata()?;
    let mut filesystem: libc::statfs = unsafe { std::mem::zeroed() };
    if unsafe { libc::fstatfs(file.as_raw_fd(), &mut filesystem) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    require(
        filesystem.f_type == PROC_MAGIC && metadata.mode() & libc::S_IFMT == kind,
        "thread input must be an original procfs node",
    )?;
    Ok(ProcNode::of(&metadata))
}

fn open_at(parent: &File, name: &CStr, directory: bool) -> Result<File> {
    let flags = libc::O_RDONLY | libc::O_CLOEXEC | libc::O_NOFOLLOW | libc::O_NONBLOCK;
    let raw = unsafe {
        libc::openat(
            parent.as_raw_fd(),
            name.as_ptr(),
            flags | if directory { libc::O_DIRECTORY } else { 0 },
        )
    };
    if raw < 0 {
        return Err(io::Error::last_os_error().into());
    }
    let file = unsafe { File::from_raw_fd(raw) };
    proc_node(
        &file,
        if directory {
            libc::S_IFDIR
        } else {
            libc::S_IFREG
        },
    )?;
    Ok(file)
}

fn bounded_read(parent: &File, name: &CStr, limit: usize, deadline: Instant) -> Result<Vec<u8>> {
    before(deadline)?;
    let file = open_at(parent, name, false)?;
    let mut bytes = Vec::new();
    file.take((limit + 1) as u64).read_to_end(&mut bytes)?;
    before(deadline)?;
    require(
        !bytes.is_empty()
            && bytes.len() <= limit
            && bytes.last() == Some(&b'\n')
            && !bytes.contains(&0),
        "bounded complete proc record required",
    )?;
    Ok(bytes)
}

fn decimal(bytes: &[u8]) -> Result<u32> {
    require(
        !bytes.is_empty()
            && bytes[0] != b'0'
            && bytes.len() <= 10
            && bytes.iter().all(u8::is_ascii_digit),
        "canonical positive task number required",
    )?;
    let text = std::str::from_utf8(bytes)
        .map_err(|_| ObservationError::Rejected("task number encoding"))?;
    let number = text
        .parse::<u32>()
        .map_err(|_| ObservationError::Rejected("task number overflow"))?;
    require(
        number <= i32::MAX as u32,
        "task number outside kernel range",
    )?;
    Ok(number)
}

fn field<'a>(text: &'a str, prefix: &str) -> Result<&'a str> {
    let mut matches = text.lines().filter_map(|line| line.strip_prefix(prefix));
    let value = matches.next().ok_or(ObservationError::Rejected(
        "required thread status field missing",
    ))?;
    require(matches.next().is_none(), "duplicate thread status field")?;
    Ok(value.trim())
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct ThreadStatus {
    tid: u32,
    tgid: u32,
    threads: usize,
}

fn parse_status(bytes: &[u8]) -> Result<ThreadStatus> {
    require(
        !bytes.is_empty()
            && bytes.len() <= STATUS_LIMIT
            && bytes.last() == Some(&b'\n')
            && !bytes.contains(&0),
        "bounded complete thread status required",
    )?;
    let text = std::str::from_utf8(bytes)
        .map_err(|_| ObservationError::Rejected("thread status encoding"))?;
    let state = field(text, "State:")?
        .split_ascii_whitespace()
        .next()
        .ok_or(ObservationError::Rejected("thread state absent"))?;
    require(
        matches!(state, "R" | "S" | "D" | "T" | "t" | "I" | "W" | "P"),
        "thread is dead or has an unknown kernel state",
    )?;
    let threads = decimal(field(text, "Threads:")?.as_bytes())? as usize;
    require(
        threads <= MAX_THREADS,
        "thread count exceeds fixed pids limit",
    )?;
    Ok(ThreadStatus {
        tid: decimal(field(text, "Pid:")?.as_bytes())?,
        tgid: decimal(field(text, "Tgid:")?.as_bytes())?,
        threads,
    })
}

fn parse_cgroup(bytes: &[u8]) -> Result<&str> {
    require(
        !bytes.is_empty()
            && bytes.len() <= CGROUP_LIMIT
            && bytes.last() == Some(&b'\n')
            && !bytes.contains(&0)
            && !bytes.contains(&b'\r'),
        "complete unified thread cgroup record required",
    )?;
    let text = std::str::from_utf8(bytes)
        .map_err(|_| ObservationError::Rejected("thread cgroup encoding"))?;
    let path = text
        .strip_prefix("0::")
        .and_then(|line| line.strip_suffix('\n'))
        .ok_or(ObservationError::Rejected(
            "one unified cgroup record required",
        ))?;
    require(
        path.starts_with('/')
            && !path.contains('\n')
            && !path.bytes().any(|byte| byte < 32 || byte == 127)
            && (path == "/"
                || path[1..]
                    .split('/')
                    .all(|part| !part.is_empty() && !matches!(part, "." | ".."))),
        "canonical unified cgroup path required",
    )?;
    Ok(path)
}

fn task_names(task: &File, deadline: Instant) -> Result<BTreeMap<u32, u64>> {
    // openat(".") creates a new open file description. dup() would share
    // directory position and could turn a second complete scan into EOF.
    let directory = open_at(task, c".", true)?;
    let mut names = BTreeMap::new();
    let mut buffer = [0_u8; 16384];
    let mut total = 0_usize;
    loop {
        before(deadline)?;
        let read = unsafe {
            libc::syscall(
                libc::SYS_getdents64,
                directory.as_raw_fd(),
                buffer.as_mut_ptr(),
                buffer.len(),
            )
        };
        if read < 0 {
            let error = io::Error::last_os_error();
            if error.kind() == io::ErrorKind::Interrupted {
                continue;
            }
            return Err(error.into());
        }
        if read == 0 {
            break;
        }
        let read = read as usize;
        total = total
            .checked_add(read)
            .ok_or(ObservationError::Rejected("task directory size overflow"))?;
        require(
            read <= buffer.len() && total <= DIRECTORY_LIMIT,
            "task directory byte limit",
        )?;
        let mut at = 0_usize;
        while at < read {
            require(at + 19 <= read, "short task directory record")?;
            let length = u16::from_ne_bytes([buffer[at + 16], buffer[at + 17]]) as usize;
            require(
                length >= 24 && length % 8 == 0 && at + length <= read,
                "task directory record bounds",
            )?;
            let body = &buffer[at + 19..at + length];
            let end = body
                .iter()
                .position(|byte| *byte == 0)
                .ok_or(ObservationError::Rejected(
                    "task directory name not terminated",
                ))?;
            let name = &body[..end];
            if name != b"." && name != b".." {
                let tid = decimal(name)?;
                let inode = u64::from_ne_bytes(buffer[at..at + 8].try_into().unwrap());
                require(
                    buffer[at + 18] == libc::DT_DIR
                        && inode != 0
                        && names.insert(tid, inode).is_none()
                        && names.len() <= MAX_THREADS,
                    "duplicate, non-directory or excessive task member",
                )?;
            }
            at += length;
        }
    }
    before(deadline)?;
    require(!names.is_empty(), "original task group is empty")?;
    Ok(names)
}

struct HeldThread {
    name: CString,
    tid: u32,
    file: File,
    node: ProcNode,
}

struct ThreadScan {
    leader_node: ProcNode,
    task: File,
    task_node: ProcNode,
    names: BTreeMap<u32, u64>,
    held: Vec<HeldThread>,
}

fn check_thread(
    thread: &File,
    tid: u32,
    leader: u32,
    count: usize,
    expected_cgroup: &str,
    deadline: Instant,
) -> Result<()> {
    let status = parse_status(&bounded_read(thread, c"status", STATUS_LIMIT, deadline)?)?;
    require(
        status
            == ThreadStatus {
                tid,
                tgid: leader,
                threads: count,
            },
        "thread identity or complete group count changed",
    )?;
    require(
        parse_cgroup(&bounded_read(thread, c"cgroup", CGROUP_LIMIT, deadline)?)? == expected_cgroup,
        "original init thread left the fixed owned init cgroup",
    )
}

impl ThreadScan {
    // Private kernel-reading helpers accept only already-held proc descriptors.
    // They cannot construct the production observation or execution admission.
    fn begin(proc: &File, leader: u32, expected_cgroup: &str, deadline: Instant) -> Result<Self> {
        before(deadline)?;
        let leader_node = proc_node(proc, libc::S_IFDIR)?;
        let task = open_at(proc, c"task", true)?;
        let task_node = proc_node(&task, libc::S_IFDIR)?;
        let names = task_names(&task, deadline)?;
        require(
            names.contains_key(&leader),
            "complete task set lacks the original leader",
        )?;
        check_thread(proc, leader, leader, names.len(), expected_cgroup, deadline)?;
        let mut held = Vec::with_capacity(names.len());
        for (&tid, &inode) in &names {
            before(deadline)?;
            let name = CString::new(tid.to_string()).unwrap();
            let file = open_at(&task, &name, true)?;
            let node = proc_node(&file, libc::S_IFDIR)?;
            require(node.inode == inode, "enumerated thread inode was replaced")?;
            check_thread(&file, tid, leader, names.len(), expected_cgroup, deadline)?;
            held.push(HeldThread {
                name,
                tid,
                file,
                node,
            });
        }
        require(
            task_names(&task, deadline)? == names,
            "task membership changed during acquisition",
        )?;
        Ok(Self {
            leader_node,
            task,
            task_node,
            names,
            held,
        })
    }

    fn finish(
        self,
        proc: &File,
        leader: u32,
        expected_cgroup: &str,
        deadline: Instant,
    ) -> Result<usize> {
        before(deadline)?;
        require(
            proc_node(proc, libc::S_IFDIR)? == self.leader_node,
            "original leader proc changed",
        )?;
        let named_task = open_at(proc, c"task", true)?;
        require(
            proc_node(&named_task, libc::S_IFDIR)? == self.task_node
                && proc_node(&self.task, libc::S_IFDIR)? == self.task_node
                && task_names(&self.task, deadline)? == self.names,
            "held task directory or complete membership changed",
        )?;
        for thread in &self.held {
            before(deadline)?;
            let named = open_at(&self.task, &thread.name, true)?;
            require(
                proc_node(&named, libc::S_IFDIR)? == thread.node
                    && proc_node(&thread.file, libc::S_IFDIR)? == thread.node,
                "original thread proc custody or named member changed",
            )?;
            check_thread(
                &thread.file,
                thread.tid,
                leader,
                self.names.len(),
                expected_cgroup,
                deadline,
            )?;
        }
        check_thread(
            proc,
            leader,
            leader,
            self.names.len(),
            expected_cgroup,
            deadline,
        )?;
        require(
            task_names(&self.task, deadline)? == self.names
                && proc_node(proc, libc::S_IFDIR)? == self.leader_node
                && proc_node(&self.task, libc::S_IFDIR)? == self.task_node,
            "task group changed before observation completed",
        )?;
        before(deadline)?;
        Ok(self.names.len())
    }
}

fn observe_current(init: &ExecutedInitWitness<'_>, deadline: Instant) -> Result<ProcNode> {
    before(deadline)?;
    owner(init.revalidate_guest_cgroup())?;
    let node = proc_node(init.proc_directory(), libc::S_IFDIR)?;
    let scan = ThreadScan::begin(
        init.proc_directory(),
        init.host_pid(),
        INIT_CGROUP_PATH,
        deadline,
    )?;
    scan.finish(
        init.proc_directory(),
        init.host_pid(),
        INIT_CGROUP_PATH,
        deadline,
    )?;
    // The approved path above is the shared fixed policy, not a path learned
    // from a transient leader cgroup read between these ownership bookends.
    owner(init.revalidate_guest_cgroup())?;
    require(
        proc_node(init.proc_directory(), libc::S_IFDIR)? == node,
        "original init proc changed",
    )?;
    before(deadline)?;
    Ok(node)
}

/// A same-owner, same-thread placement observer. No task list, PID, descriptor
/// or stored result is accepted by its issuer. Every revalidation reopens and
/// verifies the then-current complete task set, allowing normal thread churn
/// between successful observations without trusting any previous task list.
pub(super) struct InitThreadPlacementObservation {
    generation: ExecutedInitGeneration,
    proc: ProcNode,
    creator_tid: libc::c_long,
    _same_thread: PhantomData<Rc<()>>,
}

impl InitThreadPlacementObservation {
    pub(super) fn observe(init: &ExecutedInitWitness<'_>) -> Result<Self> {
        let deadline = Instant::now() + OBSERVATION_LIMIT;
        let creator_tid = unsafe { libc::syscall(libc::SYS_gettid) };
        let generation = owner(init.generation())?;
        let proc = observe_current(init, deadline)?;
        require(
            owner(init.generation())? == generation
                && unsafe { libc::syscall(libc::SYS_gettid) } == creator_tid,
            "original init generation or observing thread changed",
        )?;
        before(deadline)?;
        Ok(Self {
            generation,
            proc,
            creator_tid,
            _same_thread: PhantomData,
        })
    }

    pub(super) fn revalidate(&self, init: &ExecutedInitWitness<'_>) -> Result<()> {
        let deadline = Instant::now() + OBSERVATION_LIMIT;
        require(
            unsafe { libc::syscall(libc::SYS_gettid) } == self.creator_tid
                && owner(init.generation())? == self.generation,
            "thread placement belongs to another init or observing thread",
        )?;
        require(
            observe_current(init, deadline)? == self.proc,
            "original init proc custody changed",
        )?;
        require(
            owner(init.generation())? == self.generation
                && unsafe { libc::syscall(libc::SYS_gettid) } == self.creator_tid,
            "original init generation or observing thread changed",
        )?;
        before(deadline)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::{BufRead, BufReader, Write};
    use std::process::{Child, ChildStdin, ChildStdout, Command, Stdio};
    use std::sync::mpsc;

    fn deadline() -> Instant {
        Instant::now() + Duration::from_secs(5)
    }

    #[test]
    fn thread_status_and_cgroup_reject_missing_ambiguous_dead_or_truncated_records() {
        let status = b"State:\tS (sleeping)\nTgid:\t42\nPid:\t43\nThreads:\t2\n";
        assert_eq!(
            parse_status(status).unwrap(),
            ThreadStatus {
                tid: 43,
                tgid: 42,
                threads: 2
            }
        );
        for invalid in [
            b"State:\tS\nTgid:\t42\nPid:\t43\n".as_slice(),
            b"State:\tS\nTgid:\t42\nPid:\t43\nThreads:\t2\nThreads:\t2\n",
            b"State:\tZ (zombie)\nTgid:\t42\nPid:\t43\nThreads:\t2\n",
            b"State:\tS\nTgid:\t42\nPid:\t043\nThreads:\t2\n",
            b"State:\tS\nTgid:\t42\nPid:\t43\nThreads:\t32769\n",
            b"State:\tS\nTgid:\t42\nPid:\t43\nThreads:\t2",
        ] {
            assert!(parse_status(invalid).is_err(), "accepted {invalid:?}");
        }
        assert_eq!(
            parse_cgroup(b"0::/system.slice/owned/init\n").unwrap(),
            "/system.slice/owned/init"
        );
        for invalid in [
            b"0::/init".as_slice(),
            b"0::/init\n0::/init\n",
            b"1:cpu:/init\n",
            b"0::relative\n",
            b"0::/../init\n",
            b"0::/init/\n",
            b"0::/init\0\n",
            b"0::/init\r\n",
            b"0::/init//task\n",
            b"0::/init\nextra\n",
        ] {
            assert!(parse_cgroup(invalid).is_err(), "accepted {invalid:?}");
        }
        for invalid in [
            b"0".as_slice(),
            b"01",
            b"+1",
            b"-1",
            b"2147483648",
            b"1/2",
            b"",
        ] {
            assert!(decimal(invalid).is_err());
        }
    }

    // An ordinary child of this test harness supplies real kernel threads.
    // It never creates an ExecutedInitWitness or a production observation.
    #[test]
    fn ordinary_thread_child() {
        if std::env::var_os("DROIDLOOM_ORDINARY_THREAD_CHILD").as_deref()
            != Some(std::ffi::OsStr::new("1"))
        {
            return;
        }
        let mut workers = Vec::new();
        println!("DROIDLOOM_THREAD_READY");
        io::stdout().flush().unwrap();
        for line in io::stdin().lock().lines() {
            match line.unwrap().as_str() {
                "add" => {
                    let (exit, receive) = mpsc::channel();
                    let (ready, started) = mpsc::channel();
                    let thread = std::thread::spawn(move || {
                        ready.send(()).unwrap();
                        let _ = receive.recv();
                    });
                    started.recv().unwrap();
                    workers.push((exit, thread));
                }
                "remove" => {
                    let (exit, thread) = workers.pop().unwrap();
                    exit.send(()).unwrap();
                    thread.join().unwrap();
                }
                "quit" => break,
                _ => panic!("unexpected ordinary thread command"),
            }
            println!("DROIDLOOM_THREAD_READY");
            io::stdout().flush().unwrap();
        }
        for (exit, thread) in workers {
            let _ = exit.send(());
            thread.join().unwrap();
        }
    }

    struct OrdinaryChild {
        child: Child,
        input: ChildStdin,
        output: BufReader<ChildStdout>,
    }

    impl OrdinaryChild {
        fn start() -> Self {
            let mut child = Command::new(std::env::current_exe().unwrap())
                .args([
                    "--exact",
                    "production_execution::threads::tests::ordinary_thread_child",
                    "--nocapture",
                    "--quiet",
                    "--test-threads=1",
                ])
                .env("DROIDLOOM_ORDINARY_THREAD_CHILD", "1")
                .stdin(Stdio::piped())
                .stdout(Stdio::piped())
                .stderr(Stdio::null())
                .spawn()
                .unwrap();
            let input = child.stdin.take().unwrap();
            let output = BufReader::new(child.stdout.take().unwrap());
            let mut value = Self {
                child,
                input,
                output,
            };
            value.ready();
            value
        }

        fn ready(&mut self) {
            let end = deadline();
            let mut records = 0;
            while records < 16 {
                before(end).unwrap();
                if self.output.buffer().is_empty() {
                    let mut fd = libc::pollfd {
                        fd: self.output.get_ref().as_raw_fd(),
                        events: libc::POLLIN,
                        revents: 0,
                    };
                    let result = unsafe { libc::poll(&mut fd, 1, 1000) };
                    if result == 0 {
                        continue;
                    }
                    if result < 0 && io::Error::last_os_error().kind() == io::ErrorKind::Interrupted
                    {
                        continue;
                    }
                    assert!(result > 0, "ordinary child poll failed");
                }
                let mut line = String::new();
                assert!(self.output.read_line(&mut line).unwrap() > 0);
                assert!(line.len() <= 1024);
                records += 1;
                if line.trim_end() == "DROIDLOOM_THREAD_READY" {
                    return;
                }
            }
            panic!("ordinary child acknowledgement absent");
        }

        fn command(&mut self, command: &str) {
            writeln!(self.input, "{command}").unwrap();
            self.input.flush().unwrap();
            self.ready();
        }

        fn proc(&self) -> File {
            File::open(format!("/proc/{}", self.child.id())).unwrap()
        }
    }

    impl Drop for OrdinaryChild {
        fn drop(&mut self) {
            let _ = self.child.kill();
            let _ = self.child.wait();
        }
    }

    fn child_cgroup(proc: &File) -> String {
        parse_cgroup(&bounded_read(proc, c"cgroup", CGROUP_LIMIT, deadline()).unwrap())
            .unwrap()
            .into()
    }

    fn count(proc: &File, leader: u32, cgroup: &str) -> usize {
        let end = deadline();
        ThreadScan::begin(proc, leader, cgroup, end)
            .unwrap()
            .finish(proc, leader, cgroup, end)
            .unwrap()
    }

    #[test]
    fn actual_current_thread_scans_allow_new_cohorts_between_complete_observations() {
        let mut child = OrdinaryChild::start();
        let proc = child.proc();
        let cgroup = child_cgroup(&proc);
        let initial = count(&proc, child.child.id(), &cgroup);
        child.command("add");
        assert_eq!(count(&proc, child.child.id(), &cgroup), initial + 1);
        child.command("remove");
        assert_eq!(count(&proc, child.child.id(), &cgroup), initial);
        // A caller-chosen path cannot replace the fixed policy in production.
        assert!(
            ThreadScan::begin(
                &proc,
                child.child.id(),
                "/different-owned-cgroup",
                deadline()
            )
            .is_err()
        );
        assert!(ThreadScan::begin(&proc, child.child.id() + 1, &cgroup, deadline()).is_err());
    }

    #[test]
    fn actual_member_exit_during_a_held_scan_and_reaped_leader_are_rejected() {
        let mut child = OrdinaryChild::start();
        child.command("add");
        let proc = child.proc();
        let cgroup = child_cgroup(&proc);
        let end = deadline();
        let scan = ThreadScan::begin(&proc, child.child.id(), &cgroup, end).unwrap();
        child.command("remove");
        assert!(scan.finish(&proc, child.child.id(), &cgroup, end).is_err());
        child.child.kill().unwrap();
        child.child.wait().unwrap();
        assert!(ThreadScan::begin(&proc, child.child.id(), &cgroup, deadline()).is_err());
    }

    #[test]
    fn regular_files_directories_and_expired_scans_never_become_thread_evidence() {
        let temporary = tempfile::tempdir().unwrap();
        let directory = File::open(temporary.path()).unwrap();
        assert!(ThreadScan::begin(&directory, 1, "/", deadline()).is_err());
        let regular = tempfile::tempfile().unwrap();
        assert!(proc_node(&regular, libc::S_IFDIR).is_err());
        let proc = File::open("/proc/self").unwrap();
        assert!(ThreadScan::begin(&proc, std::process::id(), "/", Instant::now()).is_err());
    }
}
