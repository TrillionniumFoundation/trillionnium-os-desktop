// Copyright 2026 Droidloom contributors
// SPDX-License-Identifier: Apache-2.0
//! Bounded real-kernel controls. Explicit PSI modes require an owned fixture.
//! --private-projection is an explicit, separately coordinated host mount-only
//! control: its child retains the job cgroup and binds that cgroup privately.
#![deny(unsafe_op_in_unsafe_fn)]

use droidloom_pressure_relay_owner_candidate::*;
use std::ffi::CString;
use std::fs::{self, OpenOptions};
use std::io::{self, BufRead, BufReader, Read, Write};
use std::mem::{size_of, zeroed};
use std::os::fd::{AsRawFd, FromRawFd, OwnedFd};
use std::os::unix::ffi::OsStrExt;
use std::os::unix::fs::{MetadataExt, OpenOptionsExt, PermissionsExt};
use std::os::unix::process::CommandExt;
use std::path::Path;
use std::process::{Child, Command, Stdio};
use std::sync::Arc;
use std::time::{Duration, Instant};

#[path = "../event_fixture.rs"]
mod event_fixture;

type TestResult<T> = std::result::Result<T, Box<dyn std::error::Error>>;
fn checked(condition: bool, message: &'static str) -> TestResult<()> {
    if !condition { return Err(message.into()); }
    Ok(())
}
fn connect(path: &Path) -> TestResult<OwnedFd> {
    let mut addr: libc::sockaddr_un = unsafe { zeroed() };
    addr.sun_family = libc::AF_UNIX as libc::sa_family_t;
    let bytes = path.as_os_str().as_bytes();
    checked(bytes.len() < addr.sun_path.len(), "endpoint too long")?;
    for (to, from) in addr.sun_path.iter_mut().zip(bytes) { *to = *from as libc::c_char; }
    let raw = unsafe { libc::socket(libc::AF_UNIX, libc::SOCK_SEQPACKET | libc::SOCK_CLOEXEC, 0) };
    if raw < 0 { return Err(io::Error::last_os_error().into()); }
    let socket = unsafe { OwnedFd::from_raw_fd(raw) };
    if unsafe { libc::connect(socket.as_raw_fd(), (&addr as *const libc::sockaddr_un).cast(), size_of::<libc::sockaddr_un>() as libc::socklen_t) } < 0 {
        return Err(io::Error::last_os_error().into());
    }
    Ok(socket)
}
fn child(path: &Path, projection_source: Option<&Path>) -> TestResult<()> {
    let parent = unsafe { libc::getppid() };
    checked(parent > 1, "missing test parent")?;
    if unsafe { libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGKILL) } < 0 { return Err(io::Error::last_os_error().into()); }
    checked(unsafe { libc::getppid() } == parent, "test parent changed")?;
    if let Some(source) = projection_source {
        checked(unsafe { libc::geteuid() } == 0, "mount control requires root")?;
        let namespace_before = fs::metadata("/proc/self/ns/mnt")?;
        let membership_before = fs::read_to_string("/proc/self/cgroup")?;
        let source_before = fs::metadata(source)?;
        if unsafe { libc::unshare(libc::CLONE_NEWNS) } < 0 { return Err(io::Error::last_os_error().into()); }
        checked(fs::metadata("/proc/self/ns/mnt")?.ino() != namespace_before.ino(), "unshare did not change mount identity")?;
        let slash = CString::new("/")?;
        if unsafe { libc::mount(std::ptr::null(), slash.as_ptr(), std::ptr::null(), libc::MS_REC | libc::MS_PRIVATE, std::ptr::null()) } < 0 {
            return Err(io::Error::last_os_error().into());
        }
        let info = fs::read_to_string("/proc/self/mountinfo")?;
        checked(info.lines().all(|line| {
            let before = line.split(" - ").next().unwrap_or("");
            !before.split_whitespace().skip(6).any(|field| field.starts_with("shared:") || field.starts_with("master:") || field.starts_with("propagate_from:"))
        }), "mount propagation is not private before bind")?;
        let source = CString::new(source.as_os_str().as_bytes())?;
        let target = CString::new("/sys/fs/cgroup")?;
        if unsafe { libc::mount(source.as_ptr(), target.as_ptr(), std::ptr::null(), libc::MS_BIND, std::ptr::null()) } < 0 {
            return Err(io::Error::last_os_error().into());
        }
        if unsafe { libc::mount(std::ptr::null(), target.as_ptr(), std::ptr::null(), libc::MS_BIND | libc::MS_REMOUNT | libc::MS_RDONLY | libc::MS_NOSUID | libc::MS_NODEV | libc::MS_NOEXEC, std::ptr::null()) } < 0 {
            return Err(io::Error::last_os_error().into());
        }
        let projected = fs::metadata("/sys/fs/cgroup")?;
        checked(projected.dev() == source_before.dev() && projected.ino() == source_before.ino(), "child projection identity differs from held job group")?;
        checked(fs::read_to_string("/proc/self/cgroup")? == membership_before, "child membership changed")?;
        let projection_file = OpenOptions::new().read(true).custom_flags(libc::O_PATH | libc::O_DIRECTORY | libc::O_CLOEXEC).open("/sys/fs/cgroup")?;
        let mut stat: libc::statx = unsafe { zeroed() };
        if unsafe { libc::statx(projection_file.as_raw_fd(), c"".as_ptr(), libc::AT_EMPTY_PATH, libc::STATX_MNT_ID, &mut stat) } < 0 {
            return Err(io::Error::last_os_error().into());
        }
        checked(stat.stx_mask & libc::STATX_MNT_ID != 0, "kernel omitted projected mount identity")?;
        let info = fs::read_to_string("/proc/self/mountinfo")?;
        let entries: Vec<_> = info.lines().filter(|line| line.split_whitespace().nth(4) == Some("/sys/fs/cgroup")).collect();
        let visible: Vec<_> = entries.iter().filter(|line| line.split_whitespace().next().and_then(|s| s.parse::<u64>().ok()) == Some(stat.stx_mnt_id)).collect();
        let readonly = visible.len() == 1 && visible[0].split_whitespace().nth(5).is_some_and(|opts| {
            ["ro", "nosuid", "nodev", "noexec"].iter().all(|wanted| opts.split(',').any(|o| o == *wanted)) && !opts.split(',').any(|o| o == "rw")
        });
        let cgroup2 = visible.len() == 1 && visible[0].split(" - ").nth(1).is_some_and(|tail| tail.starts_with("cgroup2 "));
        // A covering bind can legitimately leave the covered mount in
        // mountinfo. Identify the visible mount by its kernel statx ID.
        eprintln!("PROJECTION_PROOF visible_id={} same_path_count={} matched_id_count={} readonly={} cgroup2={} private_propagation=true unchanged_membership=true", stat.stx_mnt_id, entries.len(), visible.len(), readonly, cgroup2);
        checked(readonly && cgroup2, "opened child projection is not a read-only cgroup2 mount")?;
    }
    let socket = connect(path)?;
    println!("READY");
    io::stdout().flush()?;
    let mut command = [0u8; 1];
    io::stdin().read_exact(&mut command)?;
    match command[0] {
        b'q' => {},
        b'd' => {
            let byte = [1u8; 1];
            if unsafe { libc::send(socket.as_raw_fd(), byte.as_ptr().cast(), 1, libc::MSG_NOSIGNAL) } != 1 { return Err(io::Error::last_os_error().into()); }
            println!("SENT");
            io::stdout().flush()?;
            io::stdin().read_exact(&mut command)?;
            checked(command[0] == b'q', "unexpected second command")?;
        },
        b'r' => {
            // Exercise a real state change without changing PID/birth/UID/ns.
            println!("STATE");
            io::stdout().flush()?;
            let until = Instant::now() + Duration::from_millis(30);
            while Instant::now() < until { std::hint::spin_loop(); }
            println!("IDLE");
            io::stdout().flush()?;
            io::stdin().read_exact(&mut command)?;
            checked(command[0] == b'q', "unexpected final command")?;
        },
        _ => return Err("unknown child command".into()),
    }
    drop(socket);
    Ok(())
}

struct PeerChild { process: Child, output: BufReader<std::process::ChildStdout> }
impl PeerChild {
    fn spawn(path: &Path, projection: Option<&Path>) -> TestResult<Self> {
        let mut cmd = Command::new(std::env::current_exe()?);
        cmd.arg("--peer").arg(path);
        if let Some(source) = projection { cmd.arg(source); }
        Self::spawn_command(cmd)
    }
    fn spawn_psi(path: &Path, target: &Path) -> TestResult<Self> {
        let mut cmd = Command::new(std::env::current_exe()?);
        cmd.arg("--psi-peer").arg(path).arg(target);
        Self::spawn_command(cmd)
    }
    fn spawn_in_owned_mount(path: &Path, expected: &ProcessPin) -> TestResult<Self> {
        // Only the parent's already owned and unreaped Child supplies this
        // namespace. No PID, namespace descriptor or path comes from a peer.
        expected.live()?;
        let namespaces = expected.namespace_pins()?;
        let mount = OpenOptions::new().read(true).custom_flags(libc::O_CLOEXEC)
            .open(format!("/proc/{}/ns/mnt", expected.pid()))?;
        let m = mount.metadata()?;
        checked(namespaces.identity("mnt") == Some(FileId { device: m.dev(), inode: m.ino() }), "owned mount namespace changed before clone")?;
        expected.live()?;
        let mut cmd = Command::new(std::env::current_exe()?);
        cmd.arg("--peer").arg(path);
        // This affects only the newly forked, directly owned child. The
        // namespace is already private and has a read-only exact projection.
        unsafe {
            cmd.pre_exec(move || {
                if libc::setns(mount.as_raw_fd(), libc::CLONE_NEWNS) < 0 {
                    return Err(io::Error::last_os_error());
                }
                Ok(())
            });
        }
        let child = Self::spawn_command(cmd)?;
        expected.live()?;
        Ok(child)
    }
    fn spawn_command(mut cmd: Command) -> TestResult<Self> {
        let mut process = cmd.stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::inherit()).spawn()?;
        let output = BufReader::new(process.stdout.take().ok_or("missing owned stdout")?);
        let mut child = Self { process, output };
        child.read_line("READY")?;
        Ok(child)
    }
    fn read_line(&mut self, expected: &str) -> TestResult<()> {
        // This test is itself bounded by the remote job timeout; the child's
        // PDEATHSIG and owned-child guard prevent an abandoned test process.
        let mut line = String::new();
        self.output.read_line(&mut line)?;
        checked(line.trim_end() == expected, "unexpected child status")
    }
    fn command(&mut self, command: u8) -> TestResult<()> {
        self.process.stdin.as_mut().ok_or("missing owned stdin")?.write_all(&[command])?;
        Ok(())
    }
    fn finish(&mut self) -> TestResult<()> {
        self.command(b'q')?;
        let until = Instant::now() + Duration::from_secs(2);
        loop {
            if let Some(status) = self.process.try_wait()? { checked(status.success(), "owned child failed")?; return Ok(()); }
            checked(Instant::now() < until, "owned child cleanup timeout")?;
            std::thread::sleep(Duration::from_millis(2));
        }
    }
}
impl Drop for PeerChild {
    fn drop(&mut self) {
        if matches!(self.process.try_wait(), Ok(None)) { let _ = self.process.kill(); let _ = self.process.wait(); }
    }
}
fn accept(listener: &Listener) -> TestResult<AcceptedConnection> {
    let until = Instant::now() + Duration::from_secs(2);
    loop {
        if let Some(connection) = listener.accept()? { return Ok(connection); }
        checked(Instant::now() < until, "accept deadline")?;
        std::thread::sleep(Duration::from_millis(2));
    }
}
fn authority(host: &HostContext, peer: &mut PeerChild, uid: u32, gid: u32, wrong_exe: bool, wrong_ns: bool) -> TestResult<CellAuthority> {
    authority_with_root(host, peer, uid, gid, wrong_exe, wrong_ns, host.owned_self_cgroup()?)
}
fn authority_with_root(host: &HostContext, peer: &mut PeerChild, uid: u32, gid: u32, wrong_exe: bool, wrong_ns: bool, root: std::fs::File) -> TestResult<CellAuthority> {
    let peer_pin = host.pin_owned_child(&mut peer.process)?;
    let namespaces = if wrong_ns { host.pin_self()?.namespace_pins()? } else { peer_pin.namespace_pins()? };
    // Resolve this fixed host test fixture, then still open the resolved file
    // with O_NOFOLLOW. The real authority takes an already pinned image FD.
    let path = if wrong_exe { fs::canonicalize("/usr/bin/true")? } else { std::env::current_exe()? };
    let file = OpenOptions::new().read(true).custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC).open(path)?;
    let sha = ExecutablePin::hash_file_for_receipt(&file)?;
    let executable = ExecutablePin::from_lifecycle(file, sha)?;
    let role = RolePolicy { uid, gid, namespaces, executable, expected_peer: peer_pin };
    Ok(CellAuthority::from_lifecycle(root, host.pin_self()?, host.pin_self()?, role)?)
}
fn rejected(result: Result<VerifiedPeer>, expected: &str) -> TestResult<()> {
    match result {
        Ok(_) => Err("unexpected peer authentication success".into()),
        Err(error) => checked(error.to_string().contains(expected), "different rejection than expected"),
    }
}
fn fd_count() -> TestResult<usize> { Ok(fs::read_dir("/proc/self/fd")?.count()) }
fn emit(name: &str) { println!("PASS {name}"); }
fn endpoint_hup(fd: &OwnedFd) -> TestResult<bool> {
    let mut p = libc::pollfd { fd: fd.as_raw_fd(), events: libc::POLLIN | libc::POLLRDHUP, revents: 0 };
    if unsafe { libc::poll(&mut p, 1, 0) } < 0 { return Err(io::Error::last_os_error().into()); }
    Ok(p.revents & (libc::POLLHUP | libc::POLLRDHUP) != 0)
}
fn wait_hup(fd: &OwnedFd) -> TestResult<()> {
    let until = Instant::now() + Duration::from_secs(2);
    while !endpoint_hup(fd)? {
        checked(Instant::now() < until, "automatic owner revocation deadline")?;
        std::thread::sleep(Duration::from_millis(2));
    }
    Ok(())
}
fn duplicate(fd: &OwnedFd) -> TestResult<OwnedFd> {
    let raw = unsafe { libc::fcntl(fd.as_raw_fd(), libc::F_DUPFD_CLOEXEC, 0) };
    if raw < 0 { return Err(io::Error::last_os_error().into()); }
    Ok(unsafe { OwnedFd::from_raw_fd(raw) })
}
#[derive(Debug, Eq, PartialEq)]
struct SameClass {
    uids: String, gids: String, namespaces: Vec<FileId>, executable: FileId,
    root: FileId, membership: String, projection: FileId,
}
fn same_class(pin: &ProcessPin) -> TestResult<SameClass> {
    pin.live()?;
    let proc = Path::new("/proc").join(pin.pid().to_string());
    let status = fs::read_to_string(proc.join("status"))?;
    let field = |prefix: &str| -> TestResult<String> {
        let mut found = status.lines().filter_map(|line| line.strip_prefix(prefix));
        let value = found.next().ok_or("missing real proc credentials")?.trim().to_owned();
        checked(found.next().is_none(), "duplicate proc credentials")?;
        Ok(value)
    };
    let id = |path: &Path| -> TestResult<FileId> {
        let m = fs::metadata(path)?;
        Ok(FileId { device: m.dev(), inode: m.ino() })
    };
    let pins = pin.namespace_pins()?;
    let namespaces = ["pid", "pid_for_children", "mnt", "cgroup", "user", "net", "ipc", "uts", "time", "time_for_children"]
        .iter().map(|name| pins.identity(name).ok_or_else(|| "missing held namespace".into())).collect::<TestResult<Vec<_>>>()?;
    let snapshot = SameClass {
        uids: field("Uid:")?, gids: field("Gid:")?, namespaces,
        executable: id(&proc.join("exe"))?, root: id(&proc.join("root"))?,
        membership: fs::read_to_string(proc.join("cgroup"))?,
        projection: id(&proc.join("root/sys/fs/cgroup"))?,
    };
    pin.live()?;
    Ok(snapshot)
}
fn peer_birth_control(host: &HostContext, listener: &Listener, path: &Path, projection: &Path, uid: u32, gid: u32) -> TestResult<()> {
    let mut expected_child = PeerChild::spawn(path, Some(projection))?;
    // Capture policy before accepting the connection. The accepted caller is
    // never used to fill in the expected process or namespaces retrospectively.
    let authority = authority(host, &mut expected_child, uid, gid, false, false)?;
    let expected_pin = host.pin_owned_child(&mut expected_child.process)?;
    let legitimate = host.authenticate(accept(listener)?, &authority)?;
    checked((legitimate.credentials().pid, legitimate.birth()) == (expected_pin.pid(), expected_pin.birth()), "legitimate process birth differs")?;
    legitimate.revalidate(host, &authority)?;
    let expected_class = same_class(&expected_pin)?;
    let mut other_child = PeerChild::spawn_in_owned_mount(path, &expected_pin)?;
    let other_pin = host.pin_owned_child(&mut other_child.process)?;
    checked((expected_pin.pid(), expected_pin.birth()) != (other_pin.pid(), other_pin.birth()), "negative control reused intended process generation")?;
    checked(same_class(&other_pin)? == expected_class && same_class(&expected_pin)? == expected_class,
        "negative control does not share all ten namespaces, UID/GID, executable, root, cgroup and projection")?;
    emit("owned second process shares all ten namespaces, UID/GID, executable, root, cgroup and projection; birth tuple differs");
    let accepted = host.authenticate(accept(listener)?, &authority);
    let decision: TestResult<()> = match accepted {
        Err(Error::Reject("accepted peer is not lifecycle-pinned process generation")) => Ok(()),
        Err(error) => Err(format!("wrong-caller rejected by unrelated gate: {error}").into()),
        Ok(incorrect) => {
            // The old-source negative must pass all of its actual metadata
            // gates, not merely miss the new branch due to a fixture defect.
            incorrect.revalidate(host, &authority)?;
            Err("BIRTH_BINDING_MISSING: same-class different owned process authenticated".into())
        },
    };
    other_child.finish()?;
    legitimate.revalidate(host, &authority)?;
    expected_child.finish()?;
    // Always normal-close both owned children before reporting the deliberate
    // old-source negative. The outer suite verifies all descriptors and scope.
    decision?;
    emit("lifecycle-pinned peer authenticates; same-class different owned caller rejected; legitimate peer survives rejection");
    Ok(())
}
fn test_run(private_projection: bool, birth_only: bool) -> TestResult<()> {
    let host = Arc::new(HostContext::open()?);
    emit("host proc PID namespace matches getpid; proc and cgroup2 filesystems verified");
    let uid = unsafe { libc::geteuid() };
    let gid = unsafe { libc::getegid() };
    let base = std::env::temp_dir().join(format!("p4-relay-{}-{}", std::process::id(), Instant::now().elapsed().as_nanos()));
    fs::create_dir(&base)?;
    fs::set_permissions(&base, fs::Permissions::from_mode(0o700))?;
    let path = base.join("enroll.sock");
    let membership = fs::read_to_string("/proc/self/cgroup")?;
    if let Ok(expected) = std::env::var("P4_EXPECTED_JOB_CGROUP") {
        checked(membership == expected, "sudo/test moved outside the exact admitted job cgroup")?;
    }
    let relative = membership.strip_prefix("0::/").and_then(|s| s.strip_suffix('\n')).ok_or("unexpected test job membership")?;
    checked(!relative.is_empty() && !relative.split('/').any(|s| s == ".." || s.is_empty()), "test must remain in a bounded job cgroup")?;
    let projection_path = Path::new("/sys/fs/cgroup").join(relative);
    let projection = private_projection.then_some(projection_path.as_path());
    let original_mount_ns = fs::metadata("/proc/self/ns/mnt")?;
    let original_projection = fs::metadata("/sys/fs/cgroup")?;
    let original_cgroup = host.owned_self_cgroup()?.metadata()?;
    let selected_mounts = || -> TestResult<Vec<String>> {
        Ok(fs::read_to_string("/proc/self/mountinfo")?.lines().filter(|line| matches!(line.split_whitespace().nth(4), Some("/") | Some("/sys/fs/cgroup"))).map(str::to_owned).collect())
    };
    let original_mount_records = selected_mounts()?;
    let before_fds = fd_count()?;
    let controls = (|| -> TestResult<()> {
        let listener = Listener::bind(&path)?;
        if birth_only {
            checked(private_projection, "birth control requires private projection")?;
            return peer_birth_control(&host, &listener, &path, &projection_path, uid, gid);
        }
        for (name, uid_value, gid_value, wrong_exe, reason) in [
            ("kernel accepted credentials reject wrong UID", uid.wrapping_add(1), gid, false, "accepted peer credentials differ"),
            ("kernel accepted credentials reject wrong GID", uid, gid.wrapping_add(1), false, "accepted peer credentials differ"),
            ("pinned executable rejects a different trusted file", uid, gid, true, "executable identity differs"),
        ] {
            let mut peer = PeerChild::spawn(&path, projection)?;
            let expected = authority(&host, &mut peer, uid_value, gid_value, wrong_exe, false)?;
            rejected(host.authenticate(accept(&listener)?, &expected), reason)?;
            peer.finish()?;
            emit(name);
        }
        {
            let mut peer = PeerChild::spawn(&path, projection)?;
            let expected = authority(&host, &mut peer, uid, gid, false, false)?;
            let accepted = accept(&listener)?;
            peer.finish()?;
            rejected(host.authenticate(accepted, &expected), "process generation is dead")?;
            emit("lifecycle-pinned expected peer exit rejects stale enrollment after normal reap");
        }
        {
            let mut expected_child = PeerChild::spawn(&path, projection)?;
            let expected = authority(&host, &mut expected_child, uid, gid, false, false)?;
            let _held_expected_connection = accept(&listener)?;
            let mut departed_child = PeerChild::spawn(&path, projection)?;
            let departed_connection = accept(&listener)?;
            departed_child.finish()?;
            rejected(host.authenticate(departed_connection, &expected), "dead peer before proc open")?;
            expected_child.finish()?;
            emit("SO_PEERPIDFD retains dead connection generation while expected lifecycle peer remains alive");
        }
        if private_projection {
            let mut peer = PeerChild::spawn(&path, projection)?;
            let expected = authority(&host, &mut peer, uid, gid, false, true)?;
            rejected(host.authenticate(accept(&listener)?, &expected), "peer namespace identity differs")?;
            peer.finish()?;
            emit("actual private mount namespace rejects host namespace expectation");
        } else {
            let mut peer = PeerChild::spawn(&path, None)?;
            let expected = authority(&host, &mut peer, uid, gid, false, false)?;
            rejected(host.authenticate(accept(&listener)?, &expected), "peer cgroup projection differs")?;
            peer.finish()?;
            emit("ordinary host child fails the required exact cgroup projection gate");
        }
        if private_projection {
            peer_birth_control(&host, &listener, &path, &projection_path, uid, gid)?;
            for mode in ["explicit-retire", "peer-exit", "unexpected-data", "slot-limit", "generation-change", "state-change"] {
                let mut peer = PeerChild::spawn(&path, projection)?;
                let expected = Arc::new(authority(&host, &mut peer, uid, gid, false, false)?);
                let verified = host.authenticate(accept(&listener)?, &expected)?;
                checked(verified.credentials().pid == peer.process.id() as libc::pid_t && verified.birth() > 0, "accepted peer birth mismatch")?;
                let mut lease = LeaseOwner::new(verified, Arc::clone(&host), Arc::clone(&expected))?;
                let first = lease.prepare_recipient(&host, &expected)?;
                let alias = duplicate(&first)?;
                let second = lease.prepare_recipient(&host, &expected)?;
                checked(!endpoint_hup(&first)? && !endpoint_hup(&second)?, "new capability unexpectedly closed")?;
                let b = [42u8; 1];
                checked(unsafe { libc::send(alias.as_raw_fd(), b.as_ptr().cast(), b.len(), libc::MSG_NOSIGNAL | libc::MSG_DONTWAIT) } < 0 && io::Error::last_os_error().raw_os_error() == Some(libc::EPIPE), "recipient alias can forge notification")?;
                let old_generation = lease.generation();
                match mode {
                    "explicit-retire" => lease.retire(),
                    "peer-exit" => { peer.finish()?; wait_hup(&first)?; checked(lease.is_retired(), "owner failed to revoke exited peer without caller refresh")?; },
                    "unexpected-data" => { peer.command(b'd')?; peer.read_line("SENT")?; wait_hup(&first)?; checked(lease.is_retired(), "owner failed to revoke postgrant data without caller refresh")?; },
                    "slot-limit" => { checked(lease.prepare_recipient(&host, &expected).is_err(), "third monitor accepted")?; },
                    "generation-change" => {
                        let replacement = authority(&host, &mut peer, uid, gid, false, false)?;
                        checked(lease.refresh(&host, &replacement).is_err(), "replacement generation accepted old lease")?;
                    },
                    "state-change" => {
                        peer.command(b'r')?; peer.read_line("STATE")?;
                        lease.refresh(&host, &expected)?;
                        peer.read_line("IDLE")?; lease.refresh(&host, &expected)?;
                        lease.retire();
                    },
                    _ => unreachable!(),
                }
                checked(lease.is_retired() && lease.generation() == [0; 32] && old_generation != [0; 32], "generation retirement missing")?;
                checked(endpoint_hup(&first)? && endpoint_hup(&alias)? && endpoint_hup(&second)?, "retirement does not reach all recipient aliases")?;
                checked(lease.prepare_recipient(&host, &expected).is_err(), "retired lease reused")?;
                checked(lease.finish_retirement(Duration::from_secs(2))?, "worker retirement incomplete")?;
                if mode != "peer-exit" { peer.finish()?; }
                emit(&format!("full authenticated owned host capability: {mode}"));
            }
        }
        Ok(())
    })();
    checked(fd_count()? == before_fds, "owned descriptor leak")?;
    checked(!path.exists(), "owned socket was not removed")?;
    checked(fs::metadata("/proc/self/ns/mnt")?.ino() == original_mount_ns.ino(), "parent mount namespace changed")?;
    checked(selected_mounts()? == original_mount_records, "parent root/cgroup mount attributes changed")?;
    let projected_now = fs::metadata("/sys/fs/cgroup")?;
    checked(projected_now.dev() == original_projection.dev() && projected_now.ino() == original_projection.ino(), "parent cgroup projection changed")?;
    let member_now = host.owned_self_cgroup()?.metadata()?;
    checked(member_now.dev() == original_cgroup.dev() && member_now.ino() == original_cgroup.ino() && fs::read_to_string("/proc/self/cgroup")? == membership, "test migrated out of original job cgroup")?;
    fs::remove_dir(&base)?;
    emit("owned children reaped, descriptors/socket cleaned, parent namespace/projection/membership unchanged");
    controls?;
    println!("RESULT PASS mode={}", if birth_only { "owned-same-class-peer-birth" } else if private_projection { "private-host-mount-only" } else { "host-negative-controls" });
    Ok(())
}
fn psi_peer(path: &Path, target: &Path) -> TestResult<()> {
    checked(unsafe { libc::geteuid() } == 0, "owned PSI namespace control requires root")?;
    let parent = unsafe { libc::getppid() };
    checked(parent > 1, "missing PSI test parent")?;
    if unsafe { libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGKILL) } < 0 { return Err(io::Error::last_os_error().into()); }
    checked(unsafe { libc::getppid() } == parent, "PSI parent changed")?;
    fs::write(target.join("cgroup.procs"), format!("{}\n", std::process::id()))?;
    let old_ns = fs::metadata("/proc/self/ns/cgroup")?;
    if unsafe { libc::unshare(libc::CLONE_NEWCGROUP) } < 0 { return Err(io::Error::last_os_error().into()); }
    checked(fs::metadata("/proc/self/ns/cgroup")?.ino() != old_ns.ino(), "cgroup namespace did not change")?;
    checked(fs::read_to_string("/proc/self/cgroup")? == "0::/\n", "owned target is not namespace root")?;
    // Open after entering the new cgroup namespace, before the read-only bind.
    // This proves the nsdelegate write gate rather than merely EROFS.
    let pressure = OpenOptions::new().read(true).write(true).custom_flags(libc::O_NONBLOCK | libc::O_NOFOLLOW | libc::O_CLOEXEC).open(target.join("memory.pressure"))?;
    let trigger = b"full 70000 1000000";
    let written = unsafe { libc::write(pressure.as_raw_fd(), trigger.as_ptr().cast(), trigger.len()) };
    checked(written == -1 && io::Error::last_os_error().raw_os_error() == Some(libc::EPERM), "noninitial namespace root registration did not fail EPERM")?;
    drop(pressure);
    eprintln!("NAMESPACE_ROOT_PROOF new_cgroup_ns=true membership_root=true pressure_open_after_unshare=true write_errno=EPERM");
    child(path, Some(target))
}
fn pressure_fd_count(target: &Path) -> TestResult<usize> {
    let exact = target.join("memory.pressure");
    let mut count = 0;
    for entry in fs::read_dir("/proc/self/fd")? {
        if fs::read_link(entry?.path()).is_ok_and(|p| p == exact) { count += 1; }
    }
    Ok(count)
}
fn psi_suite(target: &Path, parent: &Path, sibling: &Path) -> TestResult<()> {
    checked(unsafe { libc::geteuid() } == 0, "PSI suite requires owned root fixture")?;
    let host = Arc::new(HostContext::open()?);
    let uid = unsafe { libc::geteuid() }; let gid = unsafe { libc::getegid() };
    let tmp = std::env::temp_dir().join(format!("p4-psi-register-{}", std::process::id()));
    fs::create_dir(&tmp)?; fs::set_permissions(&tmp, fs::Permissions::from_mode(0o700))?;
    let path = tmp.join("enroll.sock");
    let root_open = || OpenOptions::new().read(true).custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC).open(target);
    let configs = [
        PressureConfig { level: PressureLevel::Medium, window_us: 1_000_000, stall_us: 70_000 },
        PressureConfig { level: PressureLevel::Critical, window_us: 1_000_000, stall_us: 70_000 },
    ];
    let before_fds = fd_count()?;
    {
        let listener = Listener::bind(&path)?;
        for mode in ["parent", "sibling", "old-generation", "wrong-budget"] {
            let mut peer = PeerChild::spawn_psi(&path, target)?;
            let authority = Arc::new(authority_with_root(&host, &mut peer, uid, gid, false, false, root_open()?)?);
            let verified = host.authenticate(accept(&listener)?, &authority)?;
            let mut request = authority.scope_request();
            match mode {
                "parent" | "sibling" => {
                    let m = fs::metadata(if mode == "parent" { parent } else { sibling })?;
                    let different = FileId { device: m.dev(), inode: m.ino() };
                    checked(different != request.cgroup, "scope negative is not a different real cgroup")?;
                    request.cgroup = different;
                },
                "old-generation" => request.authority_generation[0] ^= 1,
                "wrong-budget" => request.budget[0] ^= 1,
                _ => unreachable!(),
            }
            match LeaseOwner::register(verified, Arc::clone(&host), Arc::clone(&authority), request, &configs) {
                Ok(_) => return Err("wrong scope registered a PSI lease".into()),
                Err(e) => checked(e.to_string().contains("requested scope is not the held cell generation"), "unexpected wrong-scope failure")?,
            }
            checked(pressure_fd_count(target)? == 0, "rejected request opened or leaked a pressure fd")?;
            peer.finish()?;
            emit(&format!("real held target rejects {mode} scope before pressure open"));
        }
        for mode in ["explicit-retire", "peer-exit", "generation-change", "sealed-slots"] {
            let mut peer = PeerChild::spawn_psi(&path, target)?;
            let authority = Arc::new(authority_with_root(&host, &mut peer, uid, gid, false, false, root_open()?)?);
            let verified = host.authenticate(accept(&listener)?, &authority)?;
            let mut lease = LeaseOwner::register(verified, Arc::clone(&host), Arc::clone(&authority), authority.scope_request(), &configs)?;
            checked(lease.configs == configs && pressure_fd_count(target)? == 2, "real monitor count or exact configuration differs")?;
            let duplicate_recipient = duplicate(&lease.recipients[0])?;
            std::thread::sleep(Duration::from_millis(250));
            let d = lease.owner.diagnostics();
            checked(!lease.owner.is_retired() && d.observations == 0 && d.packets_queued == 0 && d.stop_reason == 0, "quiet real PSI lease is not live and quiet")?;
            for fd in &lease.recipients {
                let mut p = libc::pollfd { fd: fd.as_raw_fd(), events: libc::POLLIN | libc::POLLRDHUP, revents: 0 };
                checked(unsafe { libc::poll(&mut p, 1, 0) } == 0 && p.revents == 0, "quiet kernel trigger synthesized data or closure")?;
            }
            match mode {
                "explicit-retire" => lease.owner.retire(),
                "peer-exit" => { peer.finish()?; wait_hup(&lease.recipients[0])?; checked(lease.owner.is_retired(), "PSI peer death did not automatically retire")?; },
                "generation-change" => {
                    let replacement = authority_with_root(&host, &mut peer, uid, gid, false, false, root_open()?)?;
                    checked(lease.owner.refresh(&host, &replacement).is_err(), "old PSI generation survived replacement")?;
                },
                "sealed-slots" => checked(lease.owner.prepare_recipient(&host, &authority).is_err(), "registered monitor set was mutable")?,
                _ => unreachable!(),
            }
            checked(lease.owner.finish_retirement(Duration::from_secs(2))?, "real PSI worker failed retirement")?;
            checked(pressure_fd_count(target)? == 0, "real PSI fd survived worker completion")?;
            checked(lease.recipients.iter().all(|fd| endpoint_hup(fd).unwrap_or(false)) && endpoint_hup(&duplicate_recipient)?, "real PSI lease aliases not revoked")?;
            if mode != "peer-exit" { peer.finish()?; }
            emit(&format!("real exact-cgroup PSI registration, quiet poll and complete revoke: {mode}"));
        }
    }
    checked(fd_count()? == before_fds && pressure_fd_count(target)? == 0, "PSI suite leaked descriptors")?;
    checked(!path.exists(), "PSI socket not removed")?;
    fs::remove_dir(&tmp)?;
    emit("PSI descriptors and notification aliases closed; workers joined; owned peers reaped; socket removed");
    println!("RESULT PASS mode=real-psi-registration-without-pressure");
    Ok(())
}
fn main() {
    let args: Vec<_> = std::env::args_os().collect();
    let result = if args.get(1).is_some_and(|s| s == "--peer") {
        if args.len() < 3 || args.len() > 4 { Err("invalid peer arguments".into()) }
        else { child(Path::new(&args[2]), args.get(3).map(Path::new)) }
    } else if args.len() == 4 && args[1] == "--psi-peer" { psi_peer(Path::new(&args[2]), Path::new(&args[3])) }
    else if args.len() == 5 && args[1] == "--psi-suite" { psi_suite(Path::new(&args[2]), Path::new(&args[3]), Path::new(&args[4])) }
    else if args.len() == 3 && args[1] == "--psi-event-suite" { event_fixture::run(Path::new(&args[2])) }
    else if args.len() == 4 && args[1] == "--owned-workload" { event_fixture::workload(Path::new(&args[2]), args[3].to_str().unwrap_or("")) }
    else if args.len() == 1 { test_run(false, false) }
    else if args.len() == 2 && args[1] == "--private-projection" { test_run(true, false) }
    else if args.len() == 2 && args[1] == "--peer-birth-only" { test_run(true, true) }
    else { Err("unsupported control arguments".into()) };
    if let Err(error) = result { eprintln!("RESULT FAIL: {error}"); std::process::exit(2); }
}
