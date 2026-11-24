//! Broker-side ownership of the fresh worker and its CLONE_PARENT query.
//! Both handles are atomic clone3 pidfds. No external PID can create them.
use super::protocol::{self, Message};
use super::worker::{self, CloneArgs, SignalMask};
use super::*;
use crate::production_cgroup::ApplicationLeaf;
use sha2::{Digest, Sha256};
use std::fs::OpenOptions;
use std::io::Read;
use std::mem::{self, ManuallyDrop};
use std::os::fd::{AsRawFd, FromRawFd, OwnedFd, RawFd};
use std::os::unix::fs::OpenOptionsExt;
use std::os::unix::process::ExitStatusExt;
use std::time::Instant;

#[path = "production_application_exec_stop.rs"]
mod exec_stop;
pub(super) use exec_stop::ExecReceipt;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
struct Terminal {
    code: i32,
    status: i32,
}

struct Child {
    pid: u32,
    pidfd: ManuallyDrop<OwnedFd>,
    creator: libc::pid_t,
    terminal: Option<Terminal>,
}
impl Child {
    fn owned(pid: u32, pidfd: OwnedFd) -> Self {
        Self {
            pid,
            pidfd: ManuallyDrop::new(pidfd),
            creator: unsafe { libc::syscall(libc::SYS_gettid) } as libc::pid_t,
            terminal: None,
        }
    }
    fn check_thread(&self) -> Result<()> {
        require(
            unsafe { libc::syscall(libc::SYS_gettid) } == libc::c_long::from(self.creator),
            "application owner moved away from the creating thread",
        )
    }
    fn peek(&self) -> Result<Option<Terminal>> {
        self.check_thread()?;
        if let Some(value) = self.terminal {
            return Ok(Some(value));
        }
        self.waitid(false)
    }
    fn waitid(&self, reap: bool) -> Result<Option<Terminal>> {
        let mut info: libc::siginfo_t = unsafe { mem::zeroed() };
        let flags = libc::WEXITED | libc::WNOHANG | if reap { 0 } else { libc::WNOWAIT };
        if unsafe {
            libc::waitid(
                libc::P_PIDFD,
                self.pidfd.as_raw_fd() as libc::id_t,
                &mut info,
                flags,
            )
        } != 0
        {
            return Err(io::Error::last_os_error().into());
        }
        let pid = unsafe { info.si_pid() };
        if pid == 0 {
            return Ok(None);
        }
        require(
            pid == self.pid as libc::pid_t
                && matches!(
                    info.si_code,
                    libc::CLD_EXITED | libc::CLD_KILLED | libc::CLD_DUMPED
                ),
            "application waitid returned a different child or non-terminal state",
        )?;
        Ok(Some(Terminal {
            code: info.si_code,
            status: unsafe { info.si_status() },
        }))
    }
    fn reap(&mut self, expected: Terminal) -> Result<()> {
        self.check_thread()?;
        require(
            self.terminal.is_none(),
            "application child was already reaped",
        )?;
        require(
            self.waitid(true)? == Some(expected),
            "application terminal state changed during waitid",
        )?;
        self.terminal = Some(expected);
        Ok(())
    }
    fn wait(&mut self, deadline: Instant) -> Result<Terminal> {
        loop {
            if let Some(value) = self.peek()? {
                if self.terminal.is_none() {
                    self.reap(value)?;
                }
                return Ok(value);
            }
            poll_once(&[self.pidfd.as_raw_fd()], deadline)?;
        }
    }
    fn signal(&self) -> Result<()> {
        self.check_thread()?;
        if self.terminal.is_some() {
            return Ok(());
        }
        let result = unsafe {
            libc::syscall(
                libc::SYS_pidfd_send_signal,
                self.pidfd.as_raw_fd(),
                libc::SIGKILL,
                std::ptr::null::<libc::siginfo_t>(),
                0_u32,
            )
        };
        if result != 0 && io::Error::last_os_error().raw_os_error() != Some(libc::ESRCH) {
            return Err(io::Error::last_os_error().into());
        }
        Ok(())
    }
    fn retire(&mut self, deadline: Instant) -> Result<()> {
        if self.terminal.is_some() {
            return Ok(());
        }
        if self.peek()?.is_none() {
            self.signal()?;
        }
        self.wait(deadline)?;
        Ok(())
    }
}
impl Drop for Child {
    fn drop(&mut self) {
        if self.retire(Instant::now() + RETIRE_LIMIT).is_ok() {
            unsafe {
                ManuallyDrop::drop(&mut self.pidfd);
            }
        }
        // Unproven ownership retains the descriptor. ApplicationLeaf also
        // fences the original cell's admission; absence is never inferred.
    }
}

pub(super) struct Children {
    worker: Option<Child>,
    query: Option<Child>,
    unknown_worker: bool,
    unknown_query: bool,
    creator: libc::pid_t,
    pub(super) cgroup_identity: (u64, u64),
}
impl Children {
    fn new(cgroup_identity: (u64, u64)) -> Self {
        Self {
            worker: None,
            query: None,
            unknown_worker: false,
            unknown_query: false,
            creator: unsafe { libc::syscall(libc::SYS_gettid) } as libc::pid_t,
            cgroup_identity,
        }
    }
    pub(super) fn verify_retirement(&self) -> Result<()> {
        require(
            unsafe { libc::syscall(libc::SYS_gettid) } == libc::c_long::from(self.creator),
            "application retirement moved threads",
        )?;
        if self.unknown_worker
            || self.unknown_query
            || self
                .worker
                .as_ref()
                .is_some_and(|child| child.terminal.is_none())
            || self
                .query
                .as_ref()
                .is_some_and(|child| child.terminal.is_none())
        {
            return Err(ApplicationError::RetirementUnproven);
        }
        Ok(())
    }
    fn retire(&mut self, leaf: &ApplicationLeaf<'_>) -> Result<()> {
        let deadline = Instant::now() + RETIRE_LIMIT;
        if self.unknown_worker
            || self.unknown_query
            || self
                .worker
                .as_ref()
                .is_some_and(|child| child.terminal.is_none())
            || self
                .query
                .as_ref()
                .is_some_and(|child| child.terminal.is_none())
        {
            leaf.kill().map_err(external)?;
        }
        // Signal the complete fixed leaf first. Every known direct child is
        // then reaped against the same absolute retirement deadline.
        if let Some(query) = self.query.as_mut() {
            query.retire(deadline)?;
        }
        if let Some(worker) = self.worker.as_mut() {
            worker.retire(deadline)?;
        }
        leaf.wait_empty(deadline).map_err(external)?;
        self.verify_retirement()
    }
}

fn above_reserved(file: &File) -> Result<File> {
    let raw = unsafe { libc::fcntl(file.as_raw_fd(), libc::F_DUPFD_CLOEXEC, 64) };
    if raw < 0 {
        return Err(io::Error::last_os_error().into());
    }
    Ok(unsafe { File::from_raw_fd(raw) })
}
fn pipe() -> Result<(File, File)> {
    let mut fds = [-1; 2];
    if unsafe { libc::pipe2(fds.as_mut_ptr(), libc::O_CLOEXEC) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    let read = unsafe { File::from_raw_fd(fds[0]) };
    let write = unsafe { File::from_raw_fd(fds[1]) };
    if unsafe { libc::fcntl(read.as_raw_fd(), libc::F_SETFL, libc::O_NONBLOCK) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    Ok((read, write))
}

fn start_worker(
    leaf: &mut ApplicationLeaf<'_>,
    socket: OwnedFd,
    children: &mut Children,
) -> Result<()> {
    worker::require_wait_semantics()?;
    let executable =
        crate::production_host_admission::application_worker_executable().map_err(external)?;
    let executable = above_reserved(&executable)?;
    let socket = above_reserved(&File::from(socket))?;
    let null = OpenOptions::new()
        .read(true)
        .write(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC | libc::O_NONBLOCK)
        .open("/dev/null")?;
    require(
        null.metadata()?.mode() & libc::S_IFMT == libc::S_IFCHR && null.metadata()?.rdev() == 259,
        "application stdin is not the host null device",
    )?;
    let null = above_reserved(&null)?;
    let action = CString::new(WORKER_ARGUMENT).map_err(external)?;
    let argv = [
        c"droidloom-owned-application-read".as_ptr(),
        action.as_ptr(),
        std::ptr::null(),
    ];
    let envp = [
        c"LC_ALL=C".as_ptr(),
        c"PATH=/usr/sbin:/usr/bin:/sbin:/bin".as_ptr(),
        std::ptr::null(),
    ];
    let parent = unsafe { libc::getpid() };
    let target = leaf.clone_target().map_err(external)?;
    let mut pidfd = -1_i32;
    let args = CloneArgs {
        flags: libc::CLONE_PIDFD as u64 | 0x2_0000_0000,
        pidfd: (&mut pidfd as *mut i32) as u64,
        exit_signal: libc::SIGCHLD as u64,
        cgroup: target.as_raw_fd() as u64,
        ..CloneArgs::default()
    };
    let mut mask = SignalMask::block()?;
    let pid = unsafe { libc::syscall(libc::SYS_clone3, &args, mem::size_of_val(&args)) };
    if pid < 0 {
        return Err(io::Error::last_os_error().into());
    }
    if pid == 0 {
        unsafe {
            worker::bootstrap(
                parent,
                executable.as_raw_fd(),
                socket.as_raw_fd(),
                null.as_raw_fd(),
                argv.as_ptr(),
                envp.as_ptr(),
            );
        }
    }
    children.unknown_worker = true;
    if pidfd < 0 {
        return Err(ApplicationError::RetirementUnproven);
    }
    children.worker = Some(Child::owned(pid as u32, unsafe {
        OwnedFd::from_raw_fd(pidfd)
    }));
    children.unknown_worker = false;
    mask.restore()
}

pub(super) fn run(
    authority: &dyn ApplicationWorkerAuthority,
    request: &ApplicationOperation,
    workflow_deadline: Instant,
) -> Result<OperationResult> {
    let result = run_owned(authority, request, workflow_deadline)?;
    // Existing reads, Browser and Contacts keep their original strict result
    // contract. Only the separate closed Launch entry exposes actual nonzero
    // status/stderr to the reviewed pending-display retry parser.
    require(
        result.receipt.query_waitid_code == libc::CLD_EXITED
            && result.receipt.query_waitid_status == 0
            && result.output.stderr.is_empty(),
        "fixed Android read failed or produced stderr",
    )?;
    let output = String::from_utf8(result.output.stdout)
        .map_err(|_| reject("Android query returned non-UTF8 output"))?;
    require(
        Instant::now() < result.operation_deadline,
        "application workflow deadline",
    )?;
    Ok(OperationResult {
        output,
        receipt: result.receipt,
    })
}

pub(super) fn run_launch(
    authority: &dyn ApplicationWorkerAuthority,
    command: &LaunchCommand,
    workflow_deadline: Instant,
) -> Result<LaunchCommandResult> {
    run_owned(
        authority,
        &ApplicationOperation::Launch {
            value: command.clone(),
        },
        workflow_deadline,
    )
}

fn run_owned(
    authority: &dyn ApplicationWorkerAuthority,
    request: &ApplicationOperation,
    workflow_deadline: Instant,
) -> Result<LaunchCommandResult> {
    let started = Instant::now();
    let deadline = (started + QUERY_LIMIT).min(workflow_deadline);
    require(Instant::now() < deadline, "application workflow deadline")?;
    request.validate()?;
    authority.revalidate().map_err(external)?;
    let mut files = authority.descriptors(request.binary()).map_err(external)?;
    let classpath = if request.needs_content_jar() {
        Some(authority.contacts_content_descriptors().map_err(external)?)
    } else {
        None
    };
    require(Instant::now() < deadline, "application workflow deadline")?;
    // Read CLOCK_MONOTONIC before deriving remaining Instant duration, so
    // the worker's absolute deadline cannot extend this broker's deadline.
    let anchor_ns = protocol::monotonic_ns()?;
    let remaining = deadline.saturating_duration_since(Instant::now());
    require(!remaining.is_zero(), "application workflow deadline")?;
    let deadline_ns = anchor_ns
        .checked_add(remaining.as_nanos() as u64)
        .ok_or_else(|| reject("query deadline overflow"))?;
    let (root_uid, root_gid) = authority.mapped_root().map_err(external)?;
    let executable_binding = if request.needs_content_jar() {
        exec_stop::ExecutableBinding::from_contacts_role(
            &files[protocol::EXECUTABLE],
            root_uid,
            root_gid,
            deadline,
        )?
    } else {
        exec_stop::ExecutableBinding::from_held_role(
            &files[protocol::EXECUTABLE],
            root_uid,
            root_gid,
            deadline,
        )?
    };
    let shell_uid = root_uid
        .checked_add(2000)
        .ok_or_else(|| reject("shell UID overflow"))?;
    let shell_gid = root_gid
        .checked_add(2000)
        .ok_or_else(|| reject("shell GID overflow"))?;
    let mut nonce = [0_u8; 16];
    let count =
        unsafe { libc::syscall(libc::SYS_getrandom, nonce.as_mut_ptr(), nonce.len(), 0_u32) };
    require(
        count == nonce.len() as libc::c_long,
        "application nonce generation failed",
    )?;
    let (control, worker_control) = protocol::socketpair()?;
    let (gate, query_gate) = protocol::socketpair()?;
    let (mut output, output_write) = pipe()?;
    let (mut error, error_write) = pipe()?;
    files.extend([output_write, error_write, File::from(query_gate)]);
    if let Some(classpath) = classpath {
        files.extend(classpath);
    }
    require(
        files.len() == request.descriptor_count(),
        "fixed operation descriptor layout differs",
    )?;
    // Finish fallible immutable-input/IPC preparation before allocating the
    // owned cgroup leaf. Every subsequent return passes actual retirement.
    let mut leaf = authority.leaf().map_err(external)?;
    let mut children = Children::new(leaf.identity().map_err(external)?);
    let result = (|| -> Result<(CapturedOutput, ExecReceipt)> {
        start_worker(&mut leaf, worker_control, &mut children)?;
        let worker = children.worker.as_ref().unwrap();
        let (worker_proc, actual_worker) = authority
            .bind_created_process(&worker.pidfd, false)
            .map_err(external)?;
        require(
            actual_worker == worker.pid,
            "fresh worker generation differs",
        )?;
        leaf.verify_member(&worker_proc).map_err(external)?;
        children.unknown_query = true;
        let raw: Vec<_> = files.iter().map(AsRawFd::as_raw_fd).collect();
        protocol::send(
            control.as_raw_fd(),
            &Message::Request {
                nonce,
                query: request.clone(),
                projection: authority.query_projection(),
                deadline_ns,
            },
            &raw,
            deadline,
        )?;
        // Only the worker and query may retain write ends after this point.
        drop(files);
        let received = protocol::receive(control.as_raw_fd(), deadline)?;
        require(
            received.peer.pid == children.worker.as_ref().unwrap().pid as libc::pid_t,
            "application worker response peer differs",
        )?;
        match received.message {
            Message::RejectedBeforeClone {
                nonce: actual,
                message,
            } => {
                require(
                    actual == nonce
                        && received.files.is_empty()
                        && message.len() <= 8192
                        && [0, root_uid].contains(&received.peer.uid)
                        && [0, root_gid].contains(&received.peer.gid),
                    "invalid pre-clone application rejection",
                )?;
                children.unknown_query = false;
                return Err(reject(message));
            }
            Message::Spawned { nonce: actual } => {
                require(
                    actual == nonce
                        && received.files.len() == 1
                        && received.peer.uid == root_uid
                        && received.peer.gid == root_gid,
                    "application child transfer identity differs",
                )?;
                let fd = received.files.into_iter().next().unwrap();
                // Keep the transferred capability before any fallible ioctl.
                // PID zero is deliberately not a valid wait identity; an
                // unbindable descriptor remains retained and quarantined.
                children.query = Some(Child::owned(0, fd));
                children.unknown_query = false;
                let query = children.query.as_mut().unwrap();
                query.pid = worker::created_query_pid(&query.pidfd)?;
            }
            _ => return Err(reject("application child transfer phase differs")),
        }
        // The short-lived join worker is outside the descendant PID namespace
        // until it creates the query. Reap it before the existing live-task
        // admission scan; no new exception to owned-task policy is introduced.
        let worker_exit = children.worker.as_mut().unwrap().wait(deadline)?;
        require(
            worker_exit
                == Terminal {
                    code: libc::CLD_EXITED,
                    status: 0,
                },
            "fresh application worker failed",
        )?;
        let query = children.query.as_ref().unwrap();
        let (query_proc, actual_query) = authority
            .bind_created_process(&query.pidfd, true)
            .map_err(external)?;
        require(
            actual_query == query.pid,
            "application query generation differs",
        )?;
        leaf.verify_member(&query_proc).map_err(external)?;
        authority.revalidate().map_err(external)?;
        let query_pid = query.pid;
        // Seize the held, unreaped direct child while it is still parked.
        // It remains attached through its original wait owner's final reap.
        let trace = exec_stop::ExecTrace::seize(children.query.as_mut().unwrap(), &query_proc)?;
        protocol::send(gate.as_raw_fd(), &Message::Go { nonce }, &[], deadline)?;
        let armed = protocol::receive(gate.as_raw_fd(), deadline)?;
        require(
            matches!(armed.message, Message::Armed { nonce: actual } if actual == nonce)
                && armed.files.is_empty()
                && armed.peer.pid == query_pid as libc::pid_t
                && armed.peer.uid == shell_uid
                && armed.peer.gid == shell_gid,
            "application exec phase or shell credentials differ",
        )?;
        let exec = trace.verify_and_continue(
            &executable_binding,
            shell_uid,
            shell_gid,
            request.domain(),
            deadline,
        )?;
        let mut native_progress = || {
            authority
                .progress_inherited_native(deadline)
                .map_err(external)
        };
        let output = collect_with_progress(
            children.query.as_mut().unwrap(),
            &mut output,
            &mut error,
            deadline,
            Some(&mut native_progress),
        )?;
        Ok((output, exec))
    })();
    // No return, successful or otherwise, bypasses actual cgroup retirement.
    if children.retire(&leaf).is_err() {
        return Err(ApplicationError::RetirementUnproven);
    }
    let proof = ApplicationRetired {
        children: &children,
    };
    if leaf.retire(&proof).is_err() {
        return Err(ApplicationError::RetirementUnproven);
    }
    let (captured, exec) = result?;
    let worker = children
        .worker
        .as_ref()
        .ok_or(ApplicationError::RetirementUnproven)?;
    let query = children
        .query
        .as_ref()
        .ok_or(ApplicationError::RetirementUnproven)?;
    let worker_exit = worker
        .terminal
        .ok_or(ApplicationError::RetirementUnproven)?;
    let query_exit = query.terminal.ok_or(ApplicationError::RetirementUnproven)?;
    let receipt = ReadReceipt {
        worker_pid: worker.pid,
        worker_waitid_code: worker_exit.code,
        worker_waitid_status: worker_exit.status,
        query_pid: query.pid,
        query_waitid_code: query_exit.code,
        query_waitid_status: query_exit.status,
        exec,
        output_bytes: captured.stdout.len(),
        output_sha256: format!("{:x}", Sha256::digest(&captured.stdout)),
        elapsed_millis: started
            .elapsed()
            .as_millis()
            .try_into()
            .map_err(|_| reject("query time overflow"))?,
        cgroup_removed: true,
    };
    require(
        captured.terminal == query_exit,
        "captured output and actual reaped query differ",
    )?;
    let status = exit_status(query_exit)?;
    let stderr_bytes = captured.stderr.len();
    let stderr_sha256 = format!("{:x}", Sha256::digest(&captured.stderr));
    let output = std::process::Output {
        status,
        stdout: captured.stdout,
        stderr: captured.stderr,
    };
    require(
        Instant::now() < deadline,
        "application operation completed after its deadline",
    )?;
    Ok(LaunchCommandResult {
        output,
        receipt,
        stderr_bytes,
        stderr_sha256,
        operation_deadline: deadline,
    })
}

pub(super) fn connect_bridge(
    authority: &dyn ApplicationWorkerAuthority,
    endpoint: &File,
    workflow_deadline: Instant,
) -> Result<BridgeConnection> {
    let started = Instant::now();
    let deadline = (started + QUERY_LIMIT).min(workflow_deadline);
    require(
        Instant::now() < deadline,
        "bridge connection workflow deadline",
    )?;
    authority.revalidate().map_err(external)?;
    // Obtain the existing original-owner prefix through the exact QueryLayout
    // path. Neither of its executable descriptors is sent to the connector.
    let mut files = authority.descriptors(c"cmd").map_err(external)?;
    require(files.len() == 12, "original bridge owner prefix shape")?;
    files.truncate(10);
    files.push(endpoint.try_clone()?);
    let (uid, gid) = authority.mapped_root().map_err(external)?;
    let system_uid = uid
        .checked_add(1000)
        .ok_or_else(|| reject("bridge system UID overflow"))?;
    let system_gid = gid
        .checked_add(1000)
        .ok_or_else(|| reject("bridge system GID overflow"))?;
    let mut nonce = [0_u8; 16];
    require(
        unsafe { libc::syscall(libc::SYS_getrandom, nonce.as_mut_ptr(), nonce.len(), 0_u32) }
            == nonce.len() as libc::c_long,
        "bridge nonce generation failed",
    )?;
    let anchor = protocol::monotonic_ns()?;
    let remaining = deadline.saturating_duration_since(Instant::now());
    require(!remaining.is_zero(), "bridge connection absolute deadline")?;
    let deadline_ns = anchor
        .checked_add(remaining.as_nanos() as u64)
        .ok_or_else(|| reject("bridge connection deadline overflow"))?;
    let (control, worker_control) = protocol::socketpair()?;
    let mut leaf = authority.leaf().map_err(external)?;
    let mut children = Children::new(leaf.identity().map_err(external)?);
    let result = (|| -> Result<File> {
        start_worker(&mut leaf, worker_control, &mut children)?;
        let worker = children
            .worker
            .as_ref()
            .ok_or(ApplicationError::RetirementUnproven)?;
        let (directory, pid) = authority
            .bind_created_process(&worker.pidfd, false)
            .map_err(external)?;
        require(pid == worker.pid, "bridge worker identity differs")?;
        leaf.verify_member(&directory).map_err(external)?;
        let raw: Vec<_> = files.iter().map(AsRawFd::as_raw_fd).collect();
        protocol::send(
            control.as_raw_fd(),
            &Message::BridgeRequest { nonce, deadline_ns },
            &raw,
            deadline,
        )?;
        drop(files);
        let received = protocol::receive(control.as_raw_fd(), deadline)?;
        require(
            received.peer.pid == pid as libc::pid_t,
            "bridge reply is not the original worker",
        )?;
        let socket = match received.message {
            Message::BridgeConnected { nonce: actual } => {
                require(
                    actual == nonce
                        && received.files.len() == 1
                        && received.peer.uid == system_uid
                        && received.peer.gid == system_gid,
                    "bridge connected capability sender differs",
                )?;
                File::from(received.files.into_iter().next().unwrap())
            }
            Message::BridgeRejected {
                nonce: actual,
                message,
            } => {
                require(
                    actual == nonce
                        && received.files.is_empty()
                        && message.len() <= 8192
                        && [0, uid, system_uid].contains(&received.peer.uid)
                        && [0, gid, system_gid].contains(&received.peer.gid),
                    "bridge rejection sender differs",
                )?;
                return Err(reject(message));
            }
            _ => return Err(reject("bridge response phase differs")),
        };
        let terminal = children.worker.as_mut().unwrap().wait(deadline)?;
        require(
            terminal
                == Terminal {
                    code: libc::CLD_EXITED,
                    status: 0,
                },
            "bridge connector failed",
        )?;
        Ok(socket)
    })();
    // Both success and every error pass the same original PIDFD/cgroup
    // retirement. No connection escapes a failed or unproven cleanup.
    if children.retire(&leaf).is_err() {
        return Err(ApplicationError::RetirementUnproven);
    }
    if leaf
        .retire(&ApplicationRetired {
            children: &children,
        })
        .is_err()
    {
        return Err(ApplicationError::RetirementUnproven);
    }
    let socket = result?;
    let worker = children
        .worker
        .as_ref()
        .ok_or(ApplicationError::RetirementUnproven)?;
    let terminal = worker
        .terminal
        .ok_or(ApplicationError::RetirementUnproven)?;
    authority.revalidate().map_err(external)?;
    require(
        Instant::now() < deadline,
        "bridge connector completed after deadline",
    )?;
    Ok(BridgeConnection {
        socket,
        receipt: BridgeReceipt {
            worker_pid: worker.pid,
            worker_waitid_code: terminal.code,
            worker_waitid_status: terminal.status,
            elapsed_millis: started
                .elapsed()
                .as_millis()
                .try_into()
                .map_err(|_| reject("bridge timing overflow"))?,
            cgroup_removed: true,
        },
    })
}

fn poll_once(fds: &[RawFd], deadline: Instant) -> Result<()> {
    let left = deadline.saturating_duration_since(Instant::now());
    require(!left.is_zero(), "application read absolute deadline")?;
    let mut polls: Vec<_> = fds
        .iter()
        .map(|fd| libc::pollfd {
            fd: *fd,
            events: libc::POLLIN,
            revents: 0,
        })
        .collect();
    let result = unsafe {
        libc::poll(
            polls.as_mut_ptr(),
            polls.len() as libc::nfds_t,
            left.as_millis().clamp(1, 20) as i32,
        )
    };
    if result < 0 && io::Error::last_os_error().kind() != io::ErrorKind::Interrupted {
        return Err(io::Error::last_os_error().into());
    }
    require(
        !polls.iter().any(|row| row.revents & libc::POLLNVAL != 0),
        "application read descriptor became invalid",
    )
}
fn drain(file: &mut File, bytes: &mut Vec<u8>, total: &mut usize, eof: &mut bool) -> Result<()> {
    if *eof {
        return Ok(());
    }
    loop {
        let mut buffer = [0_u8; 4096];
        match file.read(&mut buffer) {
            Ok(0) => {
                *eof = true;
                return Ok(());
            }
            Ok(count) => {
                *total = total
                    .checked_add(count)
                    .ok_or_else(|| reject("application output size overflow"))?;
                require(*total <= OUTPUT_LIMIT, "application combined output bound")?;
                bytes.extend_from_slice(&buffer[..count]);
            }
            Err(error) if error.kind() == io::ErrorKind::Interrupted => continue,
            Err(error) if error.kind() == io::ErrorKind::WouldBlock => return Ok(()),
            Err(error) => return Err(error.into()),
        }
    }
}
struct CapturedOutput {
    stdout: Vec<u8>,
    stderr: Vec<u8>,
    terminal: Terminal,
}

fn exit_status(terminal: Terminal) -> Result<std::process::ExitStatus> {
    let raw = match terminal {
        Terminal {
            code: libc::CLD_EXITED,
            status,
        } if (0..=255).contains(&status) => status << 8,
        Terminal {
            code: libc::CLD_KILLED,
            status,
        } if (1..=64).contains(&status) => status,
        Terminal {
            code: libc::CLD_DUMPED,
            status,
        } if (1..=64).contains(&status) => status | 0x80,
        _ => return Err(reject("invalid owned query terminal status")),
    };
    Ok(std::process::ExitStatus::from_raw(raw))
}

#[cfg(test)]
fn collect(
    child: &mut Child,
    output: &mut File,
    error: &mut File,
    deadline: Instant,
) -> Result<CapturedOutput> {
    collect_with_progress(child, output, error, deadline, None)
}

fn collect_with_progress(
    child: &mut Child,
    output: &mut File,
    error: &mut File,
    deadline: Instant,
    mut progress: Option<&mut dyn FnMut() -> Result<()>>,
) -> Result<CapturedOutput> {
    let mut stdout = Vec::new();
    let mut stderr = Vec::new();
    let mut total = 0;
    let mut output_eof = false;
    let mut error_eof = false;
    loop {
        require(
            Instant::now() < deadline,
            "application output absolute deadline",
        )?;
        if let Some(callback) = progress.as_mut() {
            callback()?;
        }
        require(
            Instant::now() < deadline,
            "application output progress deadline",
        )?;
        drain(output, &mut stdout, &mut total, &mut output_eof)?;
        drain(error, &mut stderr, &mut total, &mut error_eof)?;
        if let Some(terminal) = child.peek()? {
            if output_eof && error_eof {
                child.reap(terminal)?;
                return Ok(CapturedOutput {
                    stdout,
                    stderr,
                    terminal,
                });
            }
        }
        poll_once(
            &[
                child.pidfd.as_raw_fd(),
                output.as_raw_fd(),
                error.as_raw_fd(),
            ],
            deadline,
        )?;
    }
}

#[cfg(test)]
#[path = "production_application_launch_capture_tests.rs"]
mod launch_capture_tests;

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::Duration;
    fn child(park: bool) -> Child {
        worker::require_wait_semantics().unwrap();
        let mut pidfd = -1_i32;
        let args = CloneArgs {
            flags: libc::CLONE_PIDFD as u64,
            pidfd: (&mut pidfd as *mut i32) as u64,
            exit_signal: libc::SIGCHLD as u64,
            ..CloneArgs::default()
        };
        let mut mask = SignalMask::block().unwrap();
        let pid = unsafe { libc::syscall(libc::SYS_clone3, &args, mem::size_of_val(&args)) };
        assert!(
            pid >= 0,
            "ordinary clone3 fixture: {}",
            io::Error::last_os_error()
        );
        if pid == 0 {
            unsafe {
                if park {
                    loop {
                        libc::pause();
                    }
                }
                libc::_exit(7);
            }
        }
        assert!(pidfd >= 0);
        let child = Child::owned(pid as u32, unsafe { OwnedFd::from_raw_fd(pidfd) });
        mask.restore().unwrap();
        child
    }
    #[test]
    fn production_application_actual_pidfd_child_is_reaped_once() {
        let mut value = child(false);
        let actual = value.wait(Instant::now() + Duration::from_secs(2)).unwrap();
        assert_eq!(
            actual,
            Terminal {
                code: libc::CLD_EXITED,
                status: 7
            }
        );
        let mut info: libc::siginfo_t = unsafe { mem::zeroed() };
        assert_eq!(
            unsafe {
                libc::waitid(
                    libc::P_PIDFD,
                    value.pidfd.as_raw_fd() as libc::id_t,
                    &mut info,
                    libc::WEXITED | libc::WNOHANG,
                )
            },
            -1
        );
        assert_eq!(
            io::Error::last_os_error().raw_os_error(),
            Some(libc::ECHILD)
        );
    }
    #[test]
    fn production_application_actual_clone_parent_pidfd_transfer_is_waitable() {
        // This ordinary host control creates two short-lived private children.
        // It cannot issue Ready authority or execute an Android command.
        worker::require_wait_semantics().unwrap();
        let (receiver, sender) = protocol::socketpair().unwrap();
        let nonce = [19; 16];
        let bytes = protocol::encoded(&Message::Spawned { nonce }).unwrap();
        let mut first_pidfd = -1_i32;
        let first = CloneArgs {
            flags: libc::CLONE_PIDFD as u64,
            pidfd: (&mut first_pidfd as *mut i32) as u64,
            exit_signal: libc::SIGCHLD as u64,
            ..CloneArgs::default()
        };
        let mut mask = SignalMask::block().unwrap();
        let first_pid =
            unsafe { libc::syscall(libc::SYS_clone3, &first, mem::size_of_val(&first)) };
        assert!(
            first_pid >= 0,
            "first ordinary clone3: {}",
            io::Error::last_os_error()
        );
        if first_pid == 0 {
            unsafe {
                let mut query_pidfd = -1_i32;
                let args = CloneArgs {
                    flags: (libc::CLONE_PARENT | libc::CLONE_PIDFD) as u64,
                    pidfd: (&mut query_pidfd as *mut i32) as u64,
                    exit_signal: 0,
                    ..CloneArgs::default()
                };
                let query_pid = libc::syscall(libc::SYS_clone3, &args, mem::size_of_val(&args));
                if query_pid < 0 || (query_pid > 0 && query_pidfd < 0) {
                    libc::_exit(125);
                }
                if query_pid == 0 {
                    libc::_exit(9);
                }
                let mut iov = libc::iovec {
                    iov_base: bytes.as_ptr().cast_mut().cast(),
                    iov_len: bytes.len(),
                };
                let mut ancillary = [0_usize; 16];
                let mut header: libc::msghdr = mem::zeroed();
                header.msg_iov = &mut iov;
                header.msg_iovlen = 1;
                header.msg_control = ancillary.as_mut_ptr().cast();
                header.msg_controllen = libc::CMSG_SPACE(mem::size_of::<i32>() as u32) as usize;
                let cmsg = libc::CMSG_FIRSTHDR(&header);
                if cmsg.is_null() {
                    libc::_exit(125);
                }
                (*cmsg).cmsg_level = libc::SOL_SOCKET;
                (*cmsg).cmsg_type = libc::SCM_RIGHTS;
                (*cmsg).cmsg_len = libc::CMSG_LEN(mem::size_of::<i32>() as u32) as usize;
                std::ptr::write_unaligned(libc::CMSG_DATA(cmsg).cast::<i32>(), query_pidfd);
                if libc::sendmsg(sender.as_raw_fd(), &header, libc::MSG_NOSIGNAL)
                    != bytes.len() as isize
                {
                    libc::_exit(125);
                }
                libc::_exit(0);
            }
        }
        assert!(first_pidfd >= 0);
        let mut first = Child::owned(first_pid as u32, unsafe {
            OwnedFd::from_raw_fd(first_pidfd)
        });
        mask.restore().unwrap();
        drop(sender);
        let deadline = Instant::now() + Duration::from_secs(2);
        let received = protocol::receive(receiver.as_raw_fd(), deadline).unwrap();
        assert!(matches!(received.message, Message::Spawned { nonce: actual } if actual == nonce));
        assert_eq!(received.peer.pid, first.pid as libc::pid_t);
        assert_eq!(received.files.len(), 1);
        let pidfd = received.files.into_iter().next().unwrap();
        let pid = worker::created_query_pid(&pidfd).unwrap();
        let mut query = Child::owned(pid, pidfd);
        assert_eq!(
            first.wait(deadline).unwrap(),
            Terminal {
                code: libc::CLD_EXITED,
                status: 0
            }
        );
        assert_eq!(
            query.wait(deadline).unwrap(),
            Terminal {
                code: libc::CLD_EXITED,
                status: 9
            }
        );
    }
    #[test]
    fn production_application_actual_deadline_then_pidfd_retirement() {
        let mut value = child(true);
        assert!(
            value
                .wait(Instant::now() + Duration::from_millis(10))
                .is_err()
        );
        value
            .retire(Instant::now() + Duration::from_secs(2))
            .unwrap();
        assert_eq!(
            value.terminal,
            Some(Terminal {
                code: libc::CLD_KILLED,
                status: libc::SIGKILL
            })
        );
    }
    #[test]
    fn production_application_actual_native_progress_failure_keeps_original_child_for_retirement() {
        let mut value = child(true);
        let (mut output, _output_write) = pipe().unwrap();
        let (mut error, _error_write) = pipe().unwrap();
        let mut calls = 0;
        let mut progress = || -> Result<()> {
            calls += 1;
            Err(reject("actual progress control failure"))
        };
        assert!(
            collect_with_progress(
                &mut value,
                &mut output,
                &mut error,
                Instant::now() + Duration::from_secs(2),
                Some(&mut progress)
            )
            .is_err()
        );
        drop(progress);
        assert_eq!(calls, 1);
        assert_eq!(value.terminal, None);
        value
            .retire(Instant::now() + Duration::from_secs(2))
            .unwrap();
        assert_eq!(
            value.terminal,
            Some(Terminal {
                code: libc::CLD_KILLED,
                status: libc::SIGKILL,
            })
        );
    }

    #[test]
    fn production_application_combined_pipe_bound_is_actual_read_bound() {
        let (mut read, write) = pipe().unwrap();
        let data = [1_u8; 64];
        assert_eq!(
            unsafe { libc::write(write.as_raw_fd(), data.as_ptr().cast(), data.len()) },
            data.len() as isize
        );
        drop(write);
        let mut output = Vec::new();
        let mut total = OUTPUT_LIMIT - 32;
        let mut eof = false;
        assert!(drain(&mut read, &mut output, &mut total, &mut eof).is_err());
        assert!(output.is_empty());
    }
}
