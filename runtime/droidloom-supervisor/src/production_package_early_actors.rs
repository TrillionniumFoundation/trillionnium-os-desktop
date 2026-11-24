//! Original early native actors retained before the package retirement request.
//! Actual PIDFDs outlive their old main processes. A collected manager unit
//! is accepted only with exact NoSuchUnit, kernel exit0 and a dead original cgroup. No actor procfs directory is opened and no process is signalled.
use super::super::bus::package_jobs::{CompletedStop, EarlyActor};
use super::*;
use std::cell::{Cell, RefCell};

const ACTORS: [EarlyActor; 3] = [
    EarlyActor::Factory,
    EarlyActor::Launcher,
    EarlyActor::Observer,
];

pub(super) struct EarlyActors {
    original: [ActorLifetime; 3],
    begun: Cell<bool>,
    completed: RefCell<Vec<ActorCompletion>>,
}
/// An already retired actor is represented by duplicate handles to the same
/// original kernel objects. It is neither a fabricated StopUnit job nor a
/// terminal state reconstructed from a unit name or serialized observation.
struct PreviouslyRetired {
    actor: EarlyActor,
    invocation: [u8; 16],
    pidfd: File,
    cgroup: File,
    events: File,
}
impl PreviouslyRetired {
    fn verifies(&self, original: &ActorLifetime) -> Result<bool> {
        let same = |a: &File, b: &File| -> Result<bool> {
            let a = a.metadata()?;
            let b = b.metadata()?;
            Ok(a.dev() == b.dev() && a.ino() == b.ino())
        };
        Ok(self.actor == original.actor
            && self.invocation == original.original.invocation.id
            && same(&self.pidfd, &original.pidfd)?
            && same(&self.cgroup, &original.cgroup)?
            && same(&self.events, &original.events)?)
    }
}
enum StopTarget {
    RunningOriginal,
    AlreadyRetired(PreviouslyRetired),
}
enum ActorCompletion {
    StopJob(CompletedStop),
    AlreadyRetired(PreviouslyRetired),
}
impl ActorCompletion {
    fn verifies(&self, original: &ActorLifetime) -> Result<bool> {
        match self {
            Self::StopJob(job) => Ok(job.verifies(original.actor)),
            Self::AlreadyRetired(proof) => proof.verifies(original),
        }
    }
}
impl EarlyActors {
    pub(super) fn capture(bus: &PrivateBus, deadline: Instant) -> Result<Self> {
        let [factory, launcher, observer] = ACTORS;
        Ok(Self {
            original: [
                ActorLifetime::capture(bus, factory, deadline)?,
                ActorLifetime::capture(bus, launcher, deadline)?,
                ActorLifetime::capture(bus, observer, deadline)?,
            ],
            begun: Cell::new(false),
            completed: RefCell::new(Vec::new()),
        })
    }

    pub(super) fn revalidate_before_commit(
        &self,
        bus: &PrivateBus,
        deadline: Instant,
    ) -> Result<()> {
        require(!self.begun.get(), "early native stop was already attempted")?;
        for original in &self.original {
            original.revalidate_running(bus, deadline)?;
        }
        Ok(())
    }

    pub(super) fn stop(
        &self,
        bus: &PrivateBus,
        deadline: Instant,
        progress: &impl Fn() -> Result<()>,
    ) -> Result<()> {
        require(
            !self.begun.replace(true),
            "early native stop cannot be retried or renewed",
        )?;
        progress()?;
        let jobs = bus.package_jobs(deadline)?;
        // The owner is already normally dead. Complete the original observer
        // and launcher first; the persistent factory must remain available for
        // its final DLDONE/waitid protocol until the launcher itself has exited.
        for index in [2, 1, 0] {
            progress()?;
            let original = &self.original[index];
            let completed = match original.revalidate_stop_target(bus, deadline)? {
                StopTarget::RunningOriginal => {
                    ActorCompletion::StopJob(jobs.stop(original.actor, deadline, progress)?)
                }
                StopTarget::AlreadyRetired(proof) => ActorCompletion::AlreadyRetired(proof),
            };
            original
                .revalidate_retired(bus, deadline)
                .map_err(|error| {
                    CgroupError::Io(io::Error::other(format!(
                        "original {:?} retirement: {error}",
                        original.actor
                    )))
                })?;
            require(
                completed.verifies(original)?,
                "retirement proof belongs to another original early actor",
            )?;
            self.completed.borrow_mut().push(completed);
        }
        self.revalidate_retired(bus, deadline)?;
        progress()
    }

    pub(super) fn revalidate_retired(&self, bus: &PrivateBus, deadline: Instant) -> Result<()> {
        before(deadline)?;
        let proofs = self.completed.borrow();
        require(
            self.begun.get() && proofs.len() == ACTORS.len(),
            "all original early actor retirement proofs are required",
        )?;
        for original in &self.original {
            let mut matches = 0;
            for proof in proofs.iter() {
                if proof.verifies(original)? {
                    matches += 1;
                }
            }
            require(
                matches == 1,
                "missing or duplicate original early actor retirement proof",
            )?;
            original.revalidate_retired(bus, deadline)?;
        }
        before(deadline)
    }
}

struct ActorLifetime {
    actor: EarlyActor,
    pidfd: File,
    cgroup: File,
    events: File,
    node: NodeIdentity,
    original: Snapshot,
}
fn actor_group(actor: EarlyActor) -> String {
    format!("/system.slice/{}", actor.text())
}
fn group_path(actor: EarlyActor) -> CString {
    CString::new(format!("/sys/fs/cgroup{}", actor_group(actor))).expect("fixed group name")
}
fn actual_pidfd(pid: u32) -> Result<File> {
    require(
        pid > 1 && pid <= i32::MAX as u32,
        "fixed actor has no valid original main process",
    )?;
    let fd = unsafe { libc::syscall(libc::SYS_pidfd_open, pid, 0) };
    if fd < 0 {
        return Err(io::Error::last_os_error().into());
    }
    let value = unsafe { File::from_raw_fd(fd as i32) };
    require(
        super::super::super::systemd_endpoint::pidfd_pid(&value)? == pid,
        "kernel PIDFD differs from the manager's original main process",
    )?;
    require(
        !ended(&value)?,
        "original actor exited during PIDFD acquisition",
    )?;
    Ok(value)
}
fn ended(pidfd: &File) -> Result<bool> {
    loop {
        let mut event = libc::pollfd {
            fd: pidfd.as_raw_fd(),
            events: libc::POLLIN,
            revents: 0,
        };
        let n = unsafe { libc::poll(&mut event, 1, 0) };
        if n < 0 {
            let error = io::Error::last_os_error();
            if error.kind() == io::ErrorKind::Interrupted {
                continue;
            }
            return Err(error.into());
        }
        require(
            event.revents & (libc::POLLERR | libc::POLLNVAL) == 0,
            "original actor PIDFD became invalid",
        )?;
        if n == 0 && event.revents == 0 {
            return Ok(false);
        }
        require(
            n == 1 && event.revents & libc::POLLIN != 0,
            "unexpected original actor PIDFD event",
        )?;
        return Ok(true);
    }
}
// Linux PIDFD_INFO_SIZE_VER0 is 64 bytes on both the maintained 6.18
// production kernel and newer hosts. Unknown/absent EXIT is never success.
#[repr(C)]
#[derive(Default)]
struct NativePidfdInfo {
    mask: u64,
    cgroupid: u64,
    pid: u32,
    tgid: u32,
    ppid: u32,
    ruid: u32,
    rgid: u32,
    euid: u32,
    egid: u32,
    suid: u32,
    sgid: u32,
    fsuid: u32,
    fsgid: u32,
    exit_code: i32,
}
const _: () = assert!(std::mem::size_of::<NativePidfdInfo>() == 64);
fn pidfd_info(pidfd: &File) -> Result<NativePidfdInfo> {
    let mut value = NativePidfdInfo {
        mask: 8,
        ..NativePidfdInfo::default()
    };
    if unsafe { libc::ioctl(pidfd.as_raw_fd(), 0xc040_ff0b as libc::c_ulong, &mut value) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    Ok(value)
}
fn validate_pidfd_exit(info: &NativePidfdInfo, cgroup: u64) -> Result<()> {
    require(
        info.mask & 12 == 12 && info.exit_code == 0 && info.cgroupid == cgroup,
        "kernel did not prove the original actor's normal exit0 and original cgroup",
    )
}
fn kernel_normal_exit(pidfd: &File, cgroup: u64, deadline: Instant) -> Result<()> {
    // Stop job completion can also precede the adopted main's actual exit.
    // Wait for this same held PIDFD; never reopen a numeric process identity.
    while !ended(pidfd)? {
        before(deadline)?;
        let mut wait = libc::pollfd {
            fd: pidfd.as_raw_fd(),
            events: libc::POLLIN,
            revents: 0,
        };
        let result = unsafe { libc::poll(&mut wait, 1, 10) };
        if result < 0 {
            let error = io::Error::last_os_error();
            if error.kind() != io::ErrorKind::Interrupted {
                return Err(error.into());
            }
        }
        require(
            wait.revents & (libc::POLLERR | libc::POLLNVAL) == 0,
            "original adopted main PIDFD became invalid while stopping",
        )?;
    }
    // A readable PIDFD and a systemd job can precede release_task(). The EXIT
    // field becomes authoritative only after the parent's actual reap. Wait
    // under the original budget; an absent EXIT field never defaults to zero.
    let deadline = deadline.min(Instant::now() + Duration::from_secs(3));
    loop {
        before(deadline)?;
        let info = pidfd_info(pidfd)?;
        if info.mask & 8 != 0 {
            return validate_pidfd_exit(&info, cgroup).map_err(|error| {
                CgroupError::Io(io::Error::other(format!(
                    "{error}; kernel mask={} status={} cgroup={} expected={}",
                    info.mask, info.exit_code, info.cgroupid, cgroup
                )))
            });
        }
        let mut wait = libc::pollfd {
            fd: pidfd.as_raw_fd(),
            events: 0,
            revents: 0,
        };
        let result = unsafe { libc::poll(&mut wait, 1, 10) };
        if result < 0 {
            let error = io::Error::last_os_error();
            if error.kind() != io::ErrorKind::Interrupted {
                return Err(error.into());
            }
        }
        require(
            wait.revents & (libc::POLLERR | libc::POLLNVAL) == 0,
            "original PIDFD became invalid before kernel exit information",
        )?;
        if result > 0 {
            std::thread::sleep(Duration::from_millis(1));
        }
    }
}

fn main_pid(service: &Properties) -> Result<u32> {
    match property(service, "MainPID")? {
        Value::U32(pid) if *pid > 1 && *pid <= i32::MAX as u32 => Ok(*pid),
        _ => Err(CgroupError::Rejected(
            "original fixed actor MainPID is absent",
        )),
    }
}
fn invocation(actor: EarlyActor, unit: &Properties) -> Result<Invocation> {
    let Value::Bytes(bytes) = property(unit, "InvocationID")? else {
        return Err(CgroupError::Rejected(
            "original actor invocation has another type",
        ));
    };
    require(
        bytes.len() == 16 && bytes.iter().any(|b| *b != 0),
        "original actor invocation is empty",
    )?;
    let mut id = [0; 16];
    id.copy_from_slice(bytes);
    Ok(Invocation {
        unit: actor.text().into(),
        path: actor.path().into(),
        id,
    })
}
fn contains(properties: &Properties, name: &str, unit: &str) -> Result<()> {
    require(
        matches!(property(properties, name)?, Value::Strings(values) if values.iter().any(|v| v == unit)),
        "fixed early actor dependency is absent",
    )
}
fn command(actor: EarlyActor) -> &'static str {
    match actor.production() {
        EarlyActor::Factory => "--adopt-early-factory",
        EarlyActor::Launcher => "--launch-early-instance",
        EarlyActor::Observer => "--observe-early-container",
        #[cfg(test)]
        _ => unreachable!(),
    }
}
fn commands(properties: &Properties) -> Result<&super::super::bus::ExecCommand> {
    match property(properties, "ExecStartEx")? {
        Value::Commands(values) if values.len() == 1 => Ok(&values[0]),
        _ => Err(CgroupError::Rejected(
            "fixed actor must have one original ExecStartEx",
        )),
    }
}
fn validate_actor_configuration(actor: EarlyActor, original: &Snapshot, cgroup: u64) -> Result<()> {
    let unit = &original.unit;
    let service = &original.service;
    let pid = main_pid(service)?;
    for (name, value) in [
        ("Id", actor.text()),
        ("LoadState", "loaded"),
        ("SourcePath", ""),
    ] {
        equal(unit, name, Value::Text(value.into()))?;
    }
    let mut fragment = format!("/etc/systemd/system/{}", actor.text());
    let mut transient = false;
    #[cfg(test)]
    if actor != actor.production() {
        fragment = format!("/run/systemd/transient/{}", actor.text());
        transient = true;
    }
    equal(unit, "FragmentPath", Value::Text(fragment))?;
    equal(unit, "Transient", Value::Boolean(transient))?;
    equal(unit, "NeedDaemonReload", Value::Boolean(false))?;
    equal(unit, "DropInPaths", Value::Strings(Vec::new()))?;
    equal(
        unit,
        "InvocationID",
        Value::Bytes(original.invocation.id.to_vec()),
    )?;
    nonzero_time(unit, "StateChangeTimestampMonotonic")?;
    validate_running(unit)?;
    let observer = actor.production() == EarlyActor::Observer;
    let factory = actor.production() == EarlyActor::Factory;
    for (name, value) in [
        ("Type", "notify"),
        ("NotifyAccess", "main"),
        ("ExitType", "main"),
        ("Restart", "no"),
        (
            "KillMode",
            if observer { "control-group" } else { "process" },
        ),
        ("TimeoutStopFailureMode", "terminate"),
        ("User", if observer { "" } else { "root" }),
        ("Group", if observer { "" } else { "root" }),
        ("RootDirectory", ""),
        ("RootImage", ""),
        (
            "WorkingDirectory",
            if actor.production() == EarlyActor::Launcher {
                "/"
            } else {
                ""
            },
        ),
        ("DelegateSubgroup", ""),
        ("Slice", "system.slice"),
        ("Result", "success"),
    ] {
        equal(service, name, Value::Text(value.into()))?;
    }
    equal(service, "ControlGroup", Value::Text(actor_group(actor)))?;
    equal(service, "ControlGroupId", Value::U64(cgroup))?;
    for (name, value) in [
        ("RemainAfterExit", false),
        ("SendSIGKILL", observer),
        ("SendSIGHUP", false),
        ("NoNewPrivileges", true),
        ("PrivateMounts", false),
        ("Delegate", false),
        ("DynamicUser", false),
    ] {
        equal(service, name, Value::Boolean(value))?;
    }
    for (name, value) in [
        ("MainPID", pid),
        ("ExecMainPID", pid),
        ("ControlPID", 0),
        ("NRestarts", 0),
        ("UMask", if factory { 0o022 } else { 0o077 }),
    ] {
        equal(service, name, Value::U32(value))?;
    }
    for (name, value) in [
        ("ExecMainCode", 0),
        ("ExecMainStatus", 0),
        ("KillSignal", libc::SIGTERM),
        ("RestartKillSignal", libc::SIGTERM),
        ("FinalKillSignal", libc::SIGKILL),
    ] {
        equal(service, name, Value::I32(value))?;
    }
    equal(
        service,
        "TimeoutStopUSec",
        Value::U64(if factory {
            210_000_000
        } else if observer {
            15_000_000
        } else {
            30_000_000
        }),
    )?;
    equal(service, "ExecMainExitTimestampMonotonic", Value::U64(0))?;
    nonzero_time(service, "ExecMainStartTimestampMonotonic")?;
    for name in [
        "ExecConditionEx",
        "ExecStartPreEx",
        "ExecStartPostEx",
        "ExecReloadEx",
        "ExecStopEx",
        "ExecStopPostEx",
    ] {
        equal(service, name, Value::Commands(Vec::new()))?;
    }
    let cmd = commands(service)?;
    let mut executable = BROKER_EXECUTABLE;
    let mut arguments = vec![BROKER_EXECUTABLE.to_owned(), command(actor).into()];
    #[cfg(test)]
    if actor != actor.production() {
        executable = "/usr/bin/python3";
        arguments = vec![
            executable.into(),
            "-c".into(),
            TEST_PROGRAM.into(),
            if factory { "factory" } else { "ordinary" }.into(),
        ];
    }
    require(
        cmd.path == executable
            && cmd.arguments == arguments
            && cmd.flags.is_empty()
            && cmd.started[0] > 0
            && cmd.started[1] > 0
            && cmd.pid > 1,
        "fixed early actor ExecStartEx contract changed",
    )?;
    require(
        if factory {
            cmd.pid != pid
        } else {
            cmd.pid == pid && cmd.exited == [0, 0] && cmd.code == 0 && cmd.status == 0
        },
        "original adopted factory or ordinary main process identity is inconsistent",
    )?;
    #[cfg(test)]
    if actor != actor.production() {
        return Ok(());
    }
    contains(unit, "Requires", "droidloom-manager-label.service")?;
    contains(unit, "After", "droidloom-manager-label.service")?;
    match actor.production() {
        EarlyActor::Factory => {
            contains(unit, "Before", EarlyActor::Launcher.text())?;
            equal(unit, "PartOf", Value::Strings(Vec::new()))?;
            equal(
                service,
                "AppArmorProfile",
                Value::Profile(false, "droidloom-instance-launcher".into()),
            )?;
            equal(
                service,
                "SELinuxContext",
                Value::Profile(false, "u:r:droidloom_instance_launcher:s0".into()),
            )?;
        }
        EarlyActor::Launcher => {
            contains(unit, "Requires", EarlyActor::Factory.text())?;
            contains(unit, "BindsTo", EarlyActor::Factory.text())?;
            contains(unit, "PartOf", UNIT)?;
            contains(unit, "After", EarlyActor::Factory.text())?;
            equal(
                service,
                "AppArmorProfile",
                Value::Profile(false, "droidloom-instance-launcher".into()),
            )?;
            equal(
                service,
                "SELinuxContext",
                Value::Profile(false, "u:r:droidloom_instance_launcher:s0".into()),
            )?;
        }
        EarlyActor::Observer => {
            contains(unit, "BindsTo", UNIT)?;
            contains(unit, "After", UNIT)?;
            equal(
                service,
                "AppArmorProfile",
                Value::Profile(false, "droidloom-production-broker".into()),
            )?;
        }
        #[cfg(test)]
        _ => unreachable!(),
    }
    Ok(())
}
fn validate_actor_identity(
    original: &Snapshot,
    unit: &Properties,
    service: &Properties,
) -> Result<()> {
    require(
        unit.len() == original.unit.len()
            && original.unit.iter().all(|(name, value)| {
                matches!(
                    name.as_str(),
                    "ActiveState" | "SubState" | "Job" | "StateChangeTimestampMonotonic"
                ) || unit.get(name) == Some(value)
            }),
        "original early loaded unit or invocation changed",
    )?;
    require(
        service.len() == original.service.len()
            && original.service.iter().all(|(name, value)| {
                matches!(
                    name.as_str(),
                    "MainPID"
                        | "ExecMainCode"
                        | "ExecMainStatus"
                        | "ExecMainExitTimestampMonotonic"
                        | "ExecStartEx"
                        | "ControlGroup"
                        | "ControlGroupId"
                ) || service.get(name) == Some(value)
            }),
        "original early effective service or main identity changed",
    )?;
    let first = commands(&original.service)?;
    let current = commands(service)?;
    require(
        current.path == first.path
            && current.arguments == first.arguments
            && current.flags == first.flags
            && current.pid == first.pid
            && current.started == first.started,
        "original early ExecStartEx command was replaced",
    )?;
    let (Value::U64(first), Value::U64(now)) = (
        property(&original.unit, "StateChangeTimestampMonotonic")?,
        property(unit, "StateChangeTimestampMonotonic")?,
    ) else {
        return Err(CgroupError::Rejected(
            "invalid early service transition time",
        ));
    };
    require(
        *first > 0 && now >= first,
        "early service transition predates original invocation",
    )?;
    let current_group = property(service, "ControlGroup")?;
    let current_id = property(service, "ControlGroupId")?;
    require(
        (current_group == property(&original.service, "ControlGroup")?
            && current_id == property(&original.service, "ControlGroupId")?)
            || (current_group == &Value::Text(String::new())
                && (current_id == &Value::U64(0)
                    || current_id == property(&original.service, "ControlGroupId")?)),
        "original early cgroup was replaced",
    )?;
    equal(service, "Result", Value::Text("success".into()))?;
    equal(service, "ControlPID", Value::U32(0))
}
fn validate_actor_terminal(
    actor: EarlyActor,
    original: &Snapshot,
    unit: &Properties,
    service: &Properties,
) -> Result<()> {
    validate_actor_identity(original, unit, service)?;
    equal(unit, "ActiveState", Value::Text("inactive".into()))?;
    equal(unit, "SubState", Value::Text("dead".into()))?;
    equal(unit, "Job", Value::Job(0, "/".into()))?;
    equal(service, "MainPID", Value::U32(0))?;
    equal(service, "ExecMainCode", Value::I32(libc::CLD_EXITED))?;
    equal(service, "ExecMainStatus", Value::I32(0))?;
    let (Value::U64(started), Value::U64(exited)) = (
        property(&original.service, "ExecMainStartTimestampMonotonic")?,
        property(service, "ExecMainExitTimestampMonotonic")?,
    ) else {
        return Err(CgroupError::Rejected(
            "invalid original early main exit time",
        ));
    };
    require(
        *started > 0 && exited >= started,
        "original early main has no actual exit timestamp",
    )?;
    let first = commands(&original.service)?;
    let last = commands(service)?;
    require(
        last.exited[0] >= first.started[0]
            && last.exited[1] >= first.started[1]
            && last.code == libc::CLD_EXITED
            && last.status == 0,
        "original early ExecStartEx did not exit normally",
    )?;
    // MAINPIDFD intentionally replaces ExecMain*, not the ExecStartEx
    // command's adopter PID. Both real exits must be checked independently.
    if actor.production() != EarlyActor::Factory {
        require(
            last.exited[1] == *exited,
            "original early main and its ExecStartEx exit disagree",
        )?;
    }
    Ok(())
}

impl ActorLifetime {
    fn read(bus: &PrivateBus, actor: EarlyActor, deadline: Instant) -> Result<Snapshot> {
        let unit = bus.properties_at(actor.path(), Interface::EarlyUnit, deadline)?;
        let invocation = invocation(actor, &unit)?;
        let service = bus.properties(&invocation, Interface::Service, deadline)?;
        Ok(Snapshot {
            invocation,
            unit,
            service,
        })
    }
    fn capture(bus: &PrivateBus, actor: EarlyActor, deadline: Instant) -> Result<Self> {
        before(deadline)?;
        require(
            bus.actor_is_loaded(actor, deadline)?,
            "original early actor unit is not loaded",
        )?;
        let cgroup = open_absolute(&group_path(actor), libc::O_PATH | libc::O_DIRECTORY)?;
        trusted_directory(&cgroup)?;
        cgroup_filesystem(&cgroup)?;
        let original = Self::read(bus, actor, deadline).map_err(|error| {
            CgroupError::Io(io::Error::other(format!("original actor GetAll: {error}")))
        })?;
        validate_actor_configuration(actor, &original, cgroup.metadata()?.ino())?;
        let pidfd = actual_pidfd(main_pid(&original.service)?)?;
        let info = pidfd_info(&pidfd)?;
        require(
            info.mask & 7 == 7
                && info.mask & 8 == 0
                && info.pid == main_pid(&original.service)?
                && info.tgid == info.pid
                && info.cgroupid == cgroup.metadata()?.ino()
                && [
                    info.ruid, info.euid, info.suid, info.fsuid, info.rgid, info.egid, info.sgid,
                    info.fsgid,
                ] == [0; 8],
            "actual original early actor PIDFD identity or host credentials differ",
        )?;
        require(
            bus.invocation(pidfd.as_fd(), deadline).map_err(|error| {
                CgroupError::Io(io::Error::other(format!(
                    "original actor GetUnitByPIDFD: {error}"
                )))
            })? == original.invocation,
            "original PIDFD belongs to a different early unit or invocation",
        )?;
        let events = open_at(&cgroup, c"cgroup.events", libc::O_RDONLY | libc::O_NONBLOCK)?;
        cgroup_filesystem(&events)?;
        retained_cgroup_events(&events)?;
        let value = Self {
            actor,
            pidfd,
            node: NodeIdentity::of(&cgroup)?,
            cgroup,
            events,
            original,
        };
        value.revalidate_running(bus, deadline)?;
        Ok(value)
    }
    fn revalidate_running(&self, bus: &PrivateBus, deadline: Instant) -> Result<()> {
        before(deadline)?;
        require(
            !ended(&self.pidfd)?,
            "original early actor exited before commit",
        )?;
        let named = open_absolute(&group_path(self.actor), libc::O_PATH | libc::O_DIRECTORY)?;
        require(
            NodeIdentity::of(&named)? == self.node && NodeIdentity::of(&self.cgroup)? == self.node,
            "original early actor cgroup changed",
        )?;
        let current = Self::read(bus, self.actor, deadline)?;
        require(
            current == self.original
                && bus.invocation(self.pidfd.as_fd(), deadline)? == self.original.invocation,
            "original early actor unit or main process changed before commit",
        )?;
        require(
            !ended(&self.pidfd)?,
            "original early actor died during live revalidation",
        )?;
        before(deadline)
    }
    fn observed_retired(&self, bus: &PrivateBus, deadline: Instant) -> Result<StopTarget> {
        self.revalidate_retired(bus, deadline)?;
        let proof = PreviouslyRetired {
            actor: self.actor,
            invocation: self.original.invocation.id,
            pidfd: self.pidfd.try_clone()?,
            cgroup: self.cgroup.try_clone()?,
            events: self.events.try_clone()?,
        };
        require(
            proof.verifies(self)?,
            "retired original handles changed during proof transfer",
        )?;
        self.revalidate_retired(bus, deadline)?;
        Ok(StopTarget::AlreadyRetired(proof))
    }
    fn revalidate_stop_target(&self, bus: &PrivateBus, deadline: Instant) -> Result<StopTarget> {
        before(deadline)?;
        // GetUnit is a read-only lookup. A false result is only the manager's
        // exact NoSuchUnit response, never an access failure or timeout.
        if !bus.actor_is_loaded(self.actor, deadline)? {
            return self.observed_retired(bus, deadline);
        }
        let current = match Self::read(bus, self.actor, deadline) {
            Ok(current) => current,
            Err(error) => {
                // A dependency may let systemd collect the original between
                // GetUnit and GetAll. Re-prove its actual original kernel exit
                // and dead cgroup; never reload its former unit to stop it.
                if !bus.actor_is_loaded(self.actor, deadline)? {
                    return self.observed_retired(bus, deadline);
                }
                return Err(error);
            }
        };
        validate_actor_identity(&self.original, &current.unit, &current.service)?;
        let state = property(&current.unit, "ActiveState")?;
        if state == &Value::Text("inactive".into()) {
            return self.observed_retired(bus, deadline);
        }
        require(
            state == &Value::Text("active".into()) || state == &Value::Text("deactivating".into()),
            "original early actor is neither running nor orderly stopping",
        )?;
        let dead = ended(&self.pidfd)?;
        require(
            property(&current.service, "MainPID")?
                == if dead {
                    &Value::U32(0)
                } else {
                    property(&self.original.service, "MainPID")?
                },
            "early stop would target a different main process",
        )?;
        if !dead {
            require(
                bus.invocation(self.pidfd.as_fd(), deadline)? == self.original.invocation,
                "original early stop PIDFD changed unit or invocation",
            )?;
        }
        let named = match open_absolute(&group_path(self.actor), libc::O_PATH | libc::O_DIRECTORY) {
            Ok(named) => named,
            Err(error) => {
                if !bus.actor_is_loaded(self.actor, deadline)? {
                    return self.observed_retired(bus, deadline);
                }
                return Err(error);
            }
        };
        require(
            NodeIdentity::of(&named)? == self.node && NodeIdentity::of(&self.cgroup)? == self.node,
            "original early stop cgroup was replaced",
        )?;
        before(deadline)?;
        Ok(StopTarget::RunningOriginal)
    }
    fn read_if_loaded(
        bus: &PrivateBus,
        actor: EarlyActor,
        deadline: Instant,
    ) -> Result<Option<Snapshot>> {
        if !bus.actor_is_loaded(actor, deadline)? {
            return Ok(None);
        }
        match Self::read(bus, actor, deadline) {
            Ok(current) => Ok(Some(current)),
            Err(error) => {
                if !bus.actor_is_loaded(actor, deadline)? {
                    Ok(None)
                } else {
                    Err(error)
                }
            }
        }
    }
    fn revalidate_retired(&self, bus: &PrivateBus, deadline: Instant) -> Result<()> {
        before(deadline)?;
        kernel_normal_exit(&self.pidfd, self.node.ino, deadline)?;
        let current = Self::read_if_loaded(bus, self.actor, deadline)?;
        if let Some(current) = &current {
            validate_actor_terminal(self.actor, &self.original, &current.unit, &current.service)?;
        }
        cgroup_filesystem(&self.cgroup)?;
        require(
            NodeIdentity::of(&self.cgroup)? == self.node,
            "held early cgroup changed",
        )?;
        match open_absolute(&group_path(self.actor), libc::O_PATH | libc::O_DIRECTORY) {
            Ok(named) => {
                require(
                    NodeIdentity::of(&named)? == self.node,
                    "retired early cgroup was replaced",
                )?;
                require(
                    current.is_some(),
                    "a collected original unit requires the actual original cgroup to be dead",
                )?;
                require(
                    !populated(&self.cgroup)?,
                    "original early cgroup remains populated",
                )?;
            }
            Err(CgroupError::Io(error)) if error.kind() == io::ErrorKind::NotFound => {
                match retained_cgroup_events(&self.events) {
                    Err(error) if error.raw_os_error() == Some(libc::ENODEV) => {}
                    Err(error) => return Err(error.into()),
                    Ok(_) => {
                        return Err(CgroupError::Rejected(
                            "named early cgroup vanished while original events remain live",
                        ));
                    }
                }
            }
            Err(error) => return Err(error),
        }
        kernel_normal_exit(&self.pidfd, self.node.ino, deadline)?;
        match current {
            Some(current) => {
                // If the manager collected the original after the first read,
                // restart this bounded observation to prove its dead cgroup.
                if let Some(last) = Self::read_if_loaded(bus, self.actor, deadline)? {
                    require(
                        last == current,
                        "original early terminal lifetime changed across cgroup readback",
                    )?;
                } else {
                    require(
                        matches!(open_absolute(&group_path(self.actor), libc::O_PATH | libc::O_DIRECTORY),
                        Err(CgroupError::Io(error)) if error.kind() == io::ErrorKind::NotFound),
                        "collected original early cgroup has not disappeared",
                    )?;
                    require(
                        matches!(retained_cgroup_events(&self.events),
                        Err(error) if error.raw_os_error() == Some(libc::ENODEV)),
                        "collected original early cgroup events are not dead",
                    )?;
                    kernel_normal_exit(&self.pidfd, self.node.ino, deadline)?;
                    require(
                        !bus.actor_is_loaded(self.actor, deadline)?,
                        "collected original early unit reappeared",
                    )?;
                }
            }
            None => require(
                !bus.actor_is_loaded(self.actor, deadline)?,
                "collected early unit reappeared during original retirement proof",
            )?,
        }
        before(deadline)
    }
}

#[cfg(test)]
const TEST_PROGRAM: &str = r#"import os,signal,socket,array,time
signal.signal(signal.SIGTERM, lambda *args: exit(int(os.environ.get('DROIDLOOM_TEST_STOP_STATUS','0'))))
s=socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM|socket.SOCK_CLOEXEC)
address=os.environ['NOTIFY_SOCKET']
s.connect('\0'+address[1:] if address.startswith('@') else address)
if __import__('sys').argv[1]=='factory':
    pid=os.fork()
    if pid:
        fd=os.pidfd_open(pid)
        s.sendmsg([b'MAINPIDFD=1\nREADY=1'],[(socket.SOL_SOCKET,socket.SCM_RIGHTS,array.array('i',[fd]))])
        os.close(fd)
        s.close()
        os._exit(0)
s.send(b'READY=1') if __import__('sys').argv[1]!='factory' else None
s.close()
while True: signal.pause()
"#;

#[cfg(test)]
#[path = "production_package_early_actors_tests.rs"]
mod tests;
