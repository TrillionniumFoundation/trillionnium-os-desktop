//! One live, consume-only transition from the captured application Complete.
//! The private child has no public constructor accepting a report, PID or path.
use super::*;
use crate::production_commit_contract as c;
use std::{ffi::CString, os::unix::net::UnixDatagram};
#[path = "production_commit_io.rs"]
mod pio;
#[path = "production_commit_records.rs"]
mod records;
#[path = "production_commit_source.rs"]
mod source;
#[path = "production_commit_verify.rs"]
mod verify;
use source::{Actor, Sources};
#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct InheritedPin {
    identity: [u64; 9],
    bytes: u64,
    sha256: String,
}
#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Grant {
    schema: String,
    configuration: c::BytesPin,
    inputs: [InheritedPin; 4],
    original_child_pid: u32,
    original_child_start_ticks: u64,
    parent_observation: Value,
    deadline_ns: u64,
}
fn local_capture(captured: &CapturedCompleteApplicationRun) -> io::Result<()> {
    captured.plan.guard()?;
    for o in [
        &captured.summary,
        &captured.binding_output,
        &captured.stderr,
    ] {
        o.guard()?;
    }
    Ok(())
}
fn readonly(f: &File, id: [u64; 9]) -> io::Result<File> {
    let f = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_CLOEXEC)
        .open(format!("/proc/self/fd/{}", f.as_raw_fd()))?;
    if f9(&f)? != id
        || unsafe { libc::fcntl(f.as_raw_fd(), libc::F_GETFL) } & libc::O_ACCMODE != libc::O_RDONLY
    {
        return Err(error("Complete handoff is not the same readonly inode"));
    }
    let n = unsafe { libc::fcntl(f.as_raw_fd(), libc::F_DUPFD_CLOEXEC, 64) };
    if n < 0 {
        return Err(io::Error::last_os_error());
    }
    Ok(unsafe { File::from_raw_fd(n) })
}
fn packet(sequence: u32, kind: u8, end_ns: u64, payload: Vec<u8>) -> socket::Packet {
    socket::Packet {
        sequence,
        kind,
        case: 255,
        end_ns,
        payload,
    }
}
fn require(p: &socket::Packet, sequence: u32, kind: u8, end: u64) -> io::Result<()> {
    p.require_sequence(sequence)?;
    if p.kind != kind || p.case != 255 || p.end_ns != end {
        return Err(error("production private phase or original end differs"));
    }
    Ok(())
}
fn receive(s: &socket::Socket, pid: u32, end: Instant) -> io::Result<socket::Packet> {
    loop {
        if let Some(p) = s.try_receive(pid)? {
            return Ok(p);
        }
        socket::wait(s.file.as_raw_fd(), libc::POLLIN, end)?;
    }
}
fn spawn(
    captured: &CapturedCompleteApplicationRun,
    child_socket: &socket::Socket,
) -> io::Result<ChildOwner> {
    let channel = readonly_socket(&child_socket.file)?;
    let descriptors = [
        readonly(&captured.plan.file, captured.plan.pin)?,
        readonly(&captured.summary.file, captured.summary.pin)?,
        readonly(&captured.binding_output.file, captured.binding_output.pin)?,
        readonly(&captured.stderr.file, captured.stderr.pin)?,
    ];
    let exe = readonly(
        captured.owner.unit().executable(),
        f9(captured.owner.unit().executable())?,
    )?;
    let watchdog = captured
        .owner
        .child_transition()
        .ok_or_else(|| error("production only consumes a working singleton"))?;
    let parent = unsafe { libc::getpid() };
    let args = [
        CString::new(c::EXECUTABLE).unwrap(),
        CString::new(c::COMMIT_MODE).unwrap(),
    ];
    let mut command = Command::new(c::EXECUTABLE);
    command
        .stdin(Stdio::null())
        .stdout(Stdio::inherit())
        .stderr(Stdio::inherit())
        .env_clear()
        .current_dir("/");
    unsafe {
        command.pre_exec(move || {
            if libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGKILL, 0, 0, 0) != 0
                || libc::getppid() != parent
            {
                return Err(io::Error::last_os_error());
            }
            crate::working_qualification::child_exec::prepare(
                crate::working_qualification::child_exec::Kind::ProductionCommit,
                watchdog,
            )?;
            if libc::dup3(channel.as_raw_fd(), 3, 0) < 0 {
                return Err(io::Error::last_os_error());
            }
            for (i, f) in descriptors.iter().enumerate() {
                if libc::dup3(f.as_raw_fd(), 4 + i as i32, 0) < 0 {
                    return Err(io::Error::last_os_error());
                }
            }
            if libc::dup3(exe.as_raw_fd(), 8, libc::O_CLOEXEC) < 0
                || libc::syscall(libc::SYS_close_range, 9u32, u32::MAX, 4u32) != 0
            {
                return Err(io::Error::last_os_error());
            }
            let av = [args[0].as_ptr(), args[1].as_ptr(), std::ptr::null()];
            let ev = [
                c"PATH=/usr/sbin:/usr/bin:/sbin:/bin".as_ptr(),
                c"LANG=C.UTF-8".as_ptr(),
                std::ptr::null(),
            ];
            libc::syscall(
                libc::SYS_execveat,
                8,
                c"".as_ptr(),
                av.as_ptr(),
                ev.as_ptr(),
                libc::AT_EMPTY_PATH,
            );
            Err(io::Error::last_os_error())
        });
    }
    let mut child = command.spawn()?;
    let pid = child.id();
    let pidfd = match open_pidfd(pid) {
        Ok(v) => v,
        Err(e) => {
            let _ = child.kill();
            let _ = child.wait();
            return Err(e);
        }
    };
    Ok(ChildOwner {
        child,
        pidfd,
        pid,
        reaped: None,
    })
}
fn readonly_socket(f: &File) -> io::Result<File> {
    let n = unsafe { libc::fcntl(f.as_raw_fd(), libc::F_DUPFD_CLOEXEC, 64) };
    if n < 0 {
        return Err(io::Error::last_os_error());
    }
    Ok(unsafe { File::from_raw_fd(n) })
}
impl CapturedCompleteApplicationRun {
    /// Consumes the one live capture. There is intentionally no successful return:
    /// the original owner and nowayout watchdog remain alive until normal shutdown.
    pub fn commit_production(self) -> Result<Value, String> {
        consume(self).map_err(|e| e.to_string())
    }
}
fn consume(mut captured: CapturedCompleteApplicationRun) -> io::Result<Value> {
    captured.guard().map_err(|e| error(&e.to_string()))?;
    let (configuration, end) = match &mut captured.owner {
        RunOwner::Working(owner) => owner
            .begin_production_commit(&captured.binding)
            .map_err(|e| error(&e.to_string()))?,
        RunOwner::Template(_) => return Err(error("a template Complete cannot commit production")),
    };
    let ns = super::super::end_ns(end)?;
    local_capture(&captured)?;
    let grant = Grant {
        schema: "droidloom.production-private-complete.v1".into(),
        configuration,
        inputs: [
            InheritedPin {
                identity: captured.plan.pin,
                bytes: captured.plan.pin[6],
                sha256: captured.plan.digest.clone(),
            },
            InheritedPin {
                identity: captured.summary.pin,
                bytes: captured.summary.pin[6],
                sha256: captured.summary.sha.clone(),
            },
            InheritedPin {
                identity: captured.binding_output.pin,
                bytes: captured.binding_output.pin[6],
                sha256: captured.binding_output.sha.clone(),
            },
            InheritedPin {
                identity: captured.stderr.pin,
                bytes: captured.stderr.pin[6],
                sha256: captured.stderr.sha.clone(),
            },
        ],
        original_child_pid: captured.child_pid,
        original_child_start_ticks: captured.child_start,
        parent_observation: captured.owner.observation(),
        deadline_ns: ns,
    };
    let (socket, child_socket) = socket::Socket::pair()?;
    let mut child = spawn(&captured, &child_socket)?;
    drop(child_socket);
    let result = (|| {
        let bound = BoundProcess::capture(child.pid)?;
        let hello = receive(&socket, child.pid, end)?;
        require(&hello, 0, 1, ns).or_else(|_| {
            // The child has no caller-selected deadline. Only this live parent sends it.
            if hello.sequence == 0
                && hello.kind == 1
                && hello.case == 255
                && hello.end_ns == 0
                && hello.payload == b"droidloom.production-private-hello.v1"
            {
                Ok(())
            } else {
                Err(error("production child hello differs"))
            }
        })?;
        if hello.payload != b"droidloom.production-private-hello.v1" {
            return Err(error("production hello body differs"));
        }
        captured
            .owner
            .child_guard(&bound)
            .map_err(|e| error(&e.to_string()))?;
        captured
            .owner
            .boundary(Some(&bound), end)
            .map_err(|e| error(&e.to_string()))?;
        local_capture(&captured)?;
        socket.send(&packet(0, 5, ns, serde_json::to_vec(&grant)?), end)?;
        let staged = receive(&socket, child.pid, end)?;
        require(&staged, 1, 2, ns)?;
        if staged.payload.len() != 64
            || !c::digest(std::str::from_utf8(&staged.payload).map_err(io::Error::other)?)
        {
            return Err(error(
                "production child omitted the actual trial record digest",
            ));
        }
        captured
            .owner
            .child_guard(&bound)
            .map_err(|e| error(&e.to_string()))?;
        captured
            .owner
            .boundary(Some(&bound), end)
            .map_err(|e| error(&e.to_string()))?;
        local_capture(&captured)?;
        if Instant::now() + Duration::from_secs(30) >= end {
            return Err(error(
                "ordinary reboot no longer fits the original commit tail",
            ));
        }
        socket.send(&packet(1, 5, ns, Vec::new()), end)?;
        let requested = receive(&socket, child.pid, end)?;
        require(&requested, 2, 3, ns)?;
        if requested.payload.len() != 64
            || !c::digest(std::str::from_utf8(&requested.payload).map_err(io::Error::other)?)
        {
            return Err(error(
                "production child omitted its actual normal request record",
            ));
        }
        // This final acknowledgement precedes the one normal request. The live
        // Main and capture are checked before allowing PID1 to start stopping them.
        captured.owner.child_guard(&bound).map_err(|e| error(&e))?;
        captured
            .owner
            .boundary(Some(&bound), end)
            .map_err(|e| error(&e))?;
        local_capture(&captured)?;
        // There is no new KEEPALIVE lease: this entire tail is shorter than the
        // already armed 900 s. Child retirement during normal cgroup shutdown
        // must not start a competing OnFailure return while the parent is alive.
        socket.send(&packet(2, 5, ns, Vec::new()), end)?;
        loop {
            if Instant::now() >= end {
                return Err(error(
                    "normal production shutdown did not retire the original owner within its reserved end",
                ));
            }
            std::thread::sleep(Duration::from_millis(50));
        }
    })();
    let cleanup = child.stop(end);
    if let Err(e) = cleanup {
        return Err(error(&format!(
            "production child retirement unproven: {e}; original error={result:?}"
        )));
    }
    result
}
struct Incoming {
    files: [File; 4],
    pins: [InheritedPin; 4],
}
impl Incoming {
    fn take(pins: [InheritedPin; 4]) -> io::Result<Self> {
        let mut files = Vec::new();
        for fd in 4..=7 {
            let n = unsafe { libc::fcntl(fd, libc::F_DUPFD_CLOEXEC, 64) };
            if n < 0 {
                return Err(io::Error::last_os_error());
            }
            let f = unsafe { File::from_raw_fd(n) };
            if unsafe { libc::close(fd) } != 0 {
                return Err(io::Error::last_os_error());
            }
            files.push(f);
        }
        let value = Self {
            files: files
                .try_into()
                .map_err(|_| error("private Complete descriptor count differs"))?,
            pins,
        };
        value.guard()?;
        Ok(value)
    }
    fn guard(&self) -> io::Result<()> {
        for (i, (f, p)) in self.files.iter().zip(&self.pins).enumerate() {
            let limit = match i {
                0 => 64 * 1024 * 1024,
                1 => SUMMARY_LIMIT as u64,
                2 => BINDING_LIMIT as u64,
                _ => 0,
            };
            if p.bytes > limit
                || p.identity[6] != p.bytes
                || p.identity[3..6] != [0, 0, 1]
                || !c::digest(&p.sha256)
                || f9(f)? != p.identity
                || unsafe { libc::fcntl(f.as_raw_fd(), libc::F_GETFL) } & libc::O_ACCMODE
                    != libc::O_RDONLY
                || pio::whole(f, p.bytes)? != p.sha256
            {
                return Err(error(
                    "private Complete descriptor metadata or entire bytes differ",
                ));
            }
        }
        Ok(())
    }
    fn bytes(&self, i: usize) -> io::Result<Vec<u8>> {
        self.guard()?;
        let mut v = vec![0; self.pins[i].bytes as usize];
        self.files[i].read_exact_at(&mut v, 0)?;
        self.guard()?;
        Ok(v)
    }
}
fn commit_child() -> io::Result<()> {
    let hello_end = Instant::now() + Duration::from_secs(15);
    let peer = ChildPeer::capture_production_commit()?;
    let socket = socket::Socket::inherited()?;
    socket.send(
        &packet(0, 1, 0, b"droidloom.production-private-hello.v1".to_vec()),
        hello_end,
    )?;
    let raw = receive(&socket, peer.parent_pid(), hello_end)?;
    if raw.sequence != 0 || raw.kind != 5 || raw.case != 255 || raw.end_ns == 0 {
        return Err(error("production source grant absent"));
    }
    let grant: Grant = serde_json::from_slice(&raw.payload)?;
    if grant.schema != "droidloom.production-private-complete.v1"
        || grant.deadline_ns != raw.end_ns
        || grant.original_child_pid <= 1
        || grant.original_child_start_ticks == 0
    {
        return Err(error("production Complete lineage differs"));
    }
    let now = monotonic_ns()?;
    if raw.end_ns <= now || raw.end_ns - now > c::COMMIT_SECONDS * 1_000_000_000 {
        return Err(error("production source grant attempted to renew the end"));
    }
    let end = instant_until(
        raw.end_ns,
        Instant::now() + Duration::from_secs(c::COMMIT_SECONDS),
    )?;
    let sources = Sources::open(Actor::Commit, Some(&grant.configuration))?;
    let incoming = Incoming::take(grant.inputs)?;
    peer.guard()?;
    sources.guard()?;
    let main: RuntimeMainCustody = serde_json::from_slice(&incoming.bytes(2)?)?;
    main.validate(&main.epoch)
        .map_err(|e| error(&e.to_string()))?;
    if main.epoch.boot_id != sources.boot_id {
        return Err(error("private Complete Main is not this actual boot"));
    }
    let mut records = records::Records::new_commit(&sources)?;
    for (i, name) in ["PLAN.json", "SUMMARY.json", "MAIN.json", "STDERR.log"]
        .iter()
        .enumerate()
    {
        records.write(name, &incoming.bytes(i)?)?;
    }
    let complete = json!({"schema":"droidloom.live-production-complete-history.v1",
  "candidate_id":sources.config.candidate_id,"configuration":sources.config_input.pin,
  "boot_id":sources.boot_id,"commit_pid":std::process::id(),"parent_pid":peer.parent_pid(),
  "original_end_ns":raw.end_ns,
  "original_physical_child":{"pid":grant.original_child_pid,"start_ticks":grant.original_child_start_ticks},
  "parent_observation":grant.parent_observation,"documents":records.pins(),
  "production_ready":false,"ordinary_boot_observation_required":true});
    let history = records.write_json("COMMIT.json", &complete)?;
    sources.guard()?;
    incoming.guard()?;
    peer.guard()?;
    journal_commit(&sources, &history.sha256)?;
    let mut environment = pio::Environment::open()?;
    let trial = environment.select(
        &sources.grub,
        &sources.config.candidate_id,
        true,
        end - Duration::from_secs(30),
    )?;
    let trial_pin = records.write_json("TRIAL.json", &trial)?;
    sources.guard()?;
    incoming.guard()?;
    peer.guard()?;
    socket.send(
        &packet(1, 2, raw.end_ns, trial_pin.sha256.as_bytes().to_vec()),
        end,
    )?;
    let ack = receive(&socket, peer.parent_pid(), end)?;
    require(&ack, 1, 5, raw.end_ns)?;
    if !ack.payload.is_empty() {
        return Err(error("production parent reboot grant has external data"));
    }
    sources.guard()?;
    records.guard()?;
    environment.guard()?;
    // Persist only the actual prepared intent, before PID1 can stop this unit.
    // Its false observation flags are deliberate: ordinary-boot acceptance
    // still requires the separate trusted historical PID1 shutdown proof.
    let request_record = records::request_intent(&sources, &history, &trial_pin, raw.end_ns)?;
    let request_pin = records.write_json("REQUEST.json", &request_record)?;
    socket.send(
        &packet(2, 3, raw.end_ns, request_pin.sha256.as_bytes().to_vec()),
        end,
    )?;
    let ack = receive(&socket, peer.parent_pid(), end)?;
    require(&ack, 2, 5, raw.end_ns)?;
    if !ack.payload.is_empty() {
        return Err(error("production final request grant has external data"));
    }
    sources.guard()?;
    incoming.guard()?;
    records.guard()?;
    environment.guard()?;
    peer.guard()?;
    // Exactly one mutation, only after the actual parent is already waiting
    // with its owner and nowayout descriptor. Loss of the query connection
    // during normal shutdown cannot initiate a competing failure return.
    let request = pio::request_reboot(&sources.systemctl, end);
    let observed = pio::observe_reboot(&sources.systemctl, end);
    loop {
        if Instant::now() >= end {
            return Err(error(&format!(
                "normal production reboot did not retire the actual child; request={}; observation={}",
                request
                    .as_ref()
                    .map(pio::CommandResult::observation)
                    .unwrap_or_else(|e| json!({"error":e.to_string()})),
                observed
                    .as_ref()
                    .cloned()
                    .unwrap_or_else(|e| json!({"error":e.to_string()}))
            )));
        }
        std::thread::sleep(Duration::from_millis(50));
    }
}
fn journal_commit(s: &Sources, pin: &str) -> io::Result<()> {
    s.guard()?;
    if !c::digest(pin) {
        return Err(error("journal needs the entire owned history digest"));
    }
    let message = format!(
        "MESSAGE=DROIDLOOM_PRODUCTION_COMMIT {} {}\nSYSLOG_IDENTIFIER=droidloom-production-commit\nDROIDLOOM_COMMIT_SHA256={}\nDROIDLOOM_CANDIDATE={}\n",
        s.config.candidate_id, pin, pin, s.config.candidate_id
    );
    let socket = UnixDatagram::unbound()?;
    if socket.send_to(message.as_bytes(), "/run/systemd/journal/socket")? != message.len() {
        return Err(error(
            "normal journal did not accept the complete source marker",
        ));
    }
    Ok(())
}
pub fn dispatch_fixed_production_entry() -> Result<bool, String> {
    let args = std::env::args_os().collect::<Vec<_>>();
    let Some(mode) = args.get(1).and_then(|v| v.to_str()) else {
        return Ok(false);
    };
    if ![c::COMMIT_MODE, c::OBSERVE_MODE, c::RETURN_MODE].contains(&mode) {
        return Ok(false);
    }
    if args.len() != 2 || args[0] != c::EXECUTABLE {
        return Err("production entry has no caller selectors".into());
    }
    let result = match mode {
        c::COMMIT_MODE => commit_child(),
        c::OBSERVE_MODE => verify::observe(),
        _ => verify::return_original(),
    };
    result.map(|_| true).map_err(|e| e.to_string())
}
