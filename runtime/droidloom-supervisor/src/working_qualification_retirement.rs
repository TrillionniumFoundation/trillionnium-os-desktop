//! Fresh PID1/kernel retirement observation for the fixed working parent.
//! A CAPTURE document is only compared after this independent owner has read
//! the actual stopped invocation. The live UnitOwner is never relaxed.
use super::*;
use crate::control::application_command::physical_qualification_channel::working_runtime::boot::BootOwner;
use crate::native_working_contract as contract;

#[derive(Clone, Debug, PartialEq, Eq)]
struct Snapshot {
    unit: bus::Properties,
    service: bus::Properties,
}
#[derive(Clone, Debug, PartialEq, Eq)]
struct ParentTerminal {
    invocation: [u8; 16],
    pid: u32,
    main_start: u64,
    command_started: [u64; 2],
    command_exited: [u64; 2],
    main_exit: u64,
    state_changed: u64,
    code: i32,
    status: i32,
    result: String,
    active: String,
    sub: String,
    group: String,
    group_id: u64,
}
// The same normal ELF retains its historical once default transition. Only
// this fixed unit's non-ignorable explicit MAC context selects the working
// return entry, and the live BootOwner separately measures the actual role.
fn return_mac_selection(service: &bus::Properties) -> Result<(), String> {
    exact(
        service,
        "AppArmorProfile",
        bus::Value::Profile(false, "droidloom-working-return".into()),
    )?;
    let role = std::str::from_utf8(contract::layout::WORKING_RETURN_ROLE)
        .map_err(|_| "fixed working return role is not UTF-8")?;
    exact(
        service,
        "SELinuxContext",
        bus::Value::Profile(false, role.into()),
    )
}

fn need(value: bool, reason: &'static str) -> Result<(), String> {
    if value { Ok(()) } else { Err(reason.into()) }
}
fn text<'a>(p: &'a bus::Properties, name: &str) -> Result<&'a str, String> {
    match p.get(name) {
        Some(bus::Value::Text(v)) => Ok(v),
        _ => Err(format!("working terminal {name} has no exact string")),
    }
}
fn number(p: &bus::Properties, name: &str) -> Result<u64, String> {
    match p.get(name) {
        Some(bus::Value::U64(v)) => Ok(*v),
        _ => Err(format!("working terminal {name} has no exact u64")),
    }
}
fn pid(p: &bus::Properties, name: &str) -> Result<u32, String> {
    match p.get(name) {
        Some(bus::Value::U32(v)) => Ok(*v),
        _ => Err(format!("working terminal {name} has no exact u32")),
    }
}
fn signed(p: &bus::Properties, name: &str) -> Result<i32, String> {
    match p.get(name) {
        Some(bus::Value::I32(v)) => Ok(*v),
        _ => Err(format!("working terminal {name} has no exact i32")),
    }
}
fn exact(p: &bus::Properties, name: &str, expected: bus::Value) -> Result<(), String> {
    need(
        p.get(name) == Some(&expected),
        "working terminal effective unit value differs",
    )
}
fn invocation(unit: &bus::Properties) -> Result<[u8; 16], String> {
    let Some(bus::Value::Bytes(v)) = unit.get("InvocationID") else {
        return Err("working terminal InvocationID absent".into());
    };
    let id: [u8; 16] = v
        .as_slice()
        .try_into()
        .map_err(|_| "working InvocationID length differs")?;
    need(
        id.iter().any(|v| *v != 0),
        "unrun inactive unit has no working invocation",
    )?;
    Ok(id)
}
fn commands(service: &bus::Properties) -> Result<&bus::ExecCommand, String> {
    for name in [
        "ExecConditionEx",
        "ExecStartPreEx",
        "ExecStartPostEx",
        "ExecReloadEx",
        "ExecStopEx",
        "ExecStopPostEx",
    ] {
        exact(service, name, bus::Value::Commands(Vec::new()))?;
    }
    match service.get("ExecStartEx") {
        Some(bus::Value::Commands(v)) if v.len() == 1 => Ok(&v[0]),
        _ => Err("working terminal requires exactly one original command".into()),
    }
}
fn loaded(unit: &bus::Properties, name: &str) -> Result<(), String> {
    use bus::Value as V;
    exact(unit, "Id", V::Text(name.into()))?;
    exact(unit, "LoadState", V::Text("loaded".into()))?;
    exact(
        unit,
        "FragmentPath",
        V::Text(format!("/usr/lib/systemd/system/{name}")),
    )?;
    exact(unit, "SourcePath", V::Text(String::new()))?;
    exact(unit, "Transient", V::Boolean(false))?;
    exact(unit, "NeedDaemonReload", V::Boolean(false))?;
    exact(unit, "DropInPaths", V::Strings(Vec::new()))?;
    exact(unit, "Job", V::Job(0, "/".into()))
}
fn fixed_parent_configuration(snapshot: &Snapshot) -> Result<(), String> {
    use bus::Value as V;
    loaded(&snapshot.unit, contract::PARENT_UNIT)?;
    for key in ["OnSuccess", "OnFailure"] {
        exact(
            &snapshot.unit,
            key,
            V::Strings(vec![contract::RETURN_UNIT.into()]),
        )?;
    }
    let service = &snapshot.service;
    for (name, expected) in [
        ("Type", "exec"),
        ("ExitType", "main"),
        ("User", "root"),
        ("Group", "root"),
        ("Restart", "no"),
        ("KillMode", "control-group"),
        ("TimeoutStopFailureMode", "terminate"),
        ("Slice", "system.slice"),
        ("WorkingDirectory", "/"),
        ("RootDirectory", ""),
        ("RootImage", ""),
        ("DelegateSubgroup", ""),
    ] {
        exact(service, name, V::Text(expected.into()))?;
    }
    for (name, expected) in [
        ("RemainAfterExit", false),
        ("SendSIGKILL", true),
        ("SendSIGHUP", false),
        ("PrivateMounts", false),
        ("DynamicUser", false),
        ("Delegate", false),
    ] {
        exact(service, name, V::Boolean(expected))?;
    }
    for (name, expected) in [
        ("KillSignal", 15),
        ("RestartKillSignal", 15),
        ("FinalKillSignal", 9),
    ] {
        exact(service, name, V::I32(expected))?;
    }
    for (name, expected) in [
        ("MemoryMax", 2_147_483_648),
        ("MemorySwapMax", 0),
        ("TasksMax", 64),
        ("LimitCORE", 0),
        ("CPUQuotaPerSecUSec", 2_000_000),
        ("CPUQuotaPeriodUSec", 100_000),
        ("RuntimeMaxUSec", protocol::SERVICE_SECONDS * 1_000_000),
        ("TimeoutStopUSec", protocol::RETIREMENT_SECONDS * 1_000_000),
        ("AmbientCapabilities", 0),
    ] {
        exact(service, name, V::U64(expected))?;
    }
    exact(service, "NRestarts", V::U32(0))?;
    exact(service, "UMask", V::U32(0o77))?;
    exact(
        service,
        "AppArmorProfile",
        V::Profile(false, "droidloom-working-qualification".into()),
    )?;
    need(
        matches!(service.get("CPUAffinity"), Some(V::Bytes(v)) if affinity(v) == [20,21]),
        "working terminal source CPU affinity changed",
    )?;
    let command = commands(service)?;
    need(
        command.path == protocol::EXE
            && command.arguments == protocol::parent_argv()
            && command.flags.is_empty(),
        "working terminal exact parent command changed",
    )
}
fn terminal(snapshot: &Snapshot) -> Result<ParentTerminal, String> {
    use bus::Value as V;
    fixed_parent_configuration(snapshot)?;
    let unit = &snapshot.unit;
    let service = &snapshot.service;
    let active = text(unit, "ActiveState")?;
    let sub = text(unit, "SubState")?;
    need(
        matches!((active, sub), ("inactive", "dead") | ("failed", "failed")),
        "working parent has not actually reached a terminal unit state",
    )?;
    exact(service, "MainPID", V::U32(0))?;
    exact(service, "ControlPID", V::U32(0))?;
    let command = commands(service)?;
    let original_pid = pid(service, "ExecMainPID")?;
    let main_start = number(service, "ExecMainStartTimestampMonotonic")?;
    let main_exit = number(service, "ExecMainExitTimestampMonotonic")?;
    let changed = number(unit, "StateChangeTimestampMonotonic")?;
    let code = signed(service, "ExecMainCode")?;
    let status = signed(service, "ExecMainStatus")?;
    let result = text(service, "Result")?;
    need(
        original_pid > 1
            && command.pid == original_pid
            && main_start > 0
            && command.started.iter().all(|n| *n > 0)
            && main_exit >= main_start
            && main_exit == command.exited[1]
            && command.exited[0] >= command.started[0]
            && command.exited[1] >= command.started[1]
            && changed >= main_exit
            && command.code == code
            && command.status == status
            && [libc::CLD_EXITED, libc::CLD_KILLED, libc::CLD_DUMPED].contains(&code)
            && !result.is_empty()
            && result.len() <= 64,
        "inactive working unit has no preserved actual command exit",
    )?;
    let group = text(service, "ControlGroup")?;
    need(
        group.is_empty() || group == format!("/system.slice/{}", contract::PARENT_UNIT),
        "terminal parent manager points at a foreign cgroup",
    )?;
    let group_id = number(service, "ControlGroupId")?;
    need(
        group_id != 0,
        "terminal parent lost its original cgroup generation",
    )?;
    Ok(ParentTerminal {
        invocation: invocation(unit)?,
        pid: original_pid,
        main_start,
        command_started: command.started,
        command_exited: command.exited,
        main_exit,
        state_changed: changed,
        code,
        status,
        result: result.into(),
        active: active.into(),
        sub: sub.into(),
        group: group.into(),
        group_id,
    })
}
impl ParentTerminal {
    fn clean(&self) -> bool {
        self.active == "inactive"
            && self.sub == "dead"
            && self.result == "success"
            && self.code == libc::CLD_EXITED
            && self.status == 0
    }
    fn start_ns(&self) -> Result<u64, String> {
        self.main_start
            .min(self.command_started[1])
            .checked_mul(1000)
            .ok_or_else(|| "working terminal start overflow".into())
    }
    fn exit_ns(&self) -> Result<u64, String> {
        self.main_exit
            .checked_mul(1000)
            .ok_or_else(|| "working terminal exit overflow".into())
    }
}
fn snapshot_named(connection: &Connection, until: Instant) -> Result<Snapshot, String> {
    connection.guard()?;
    let named = connection
        .bus
        .working_parent(until)
        .map_err(|e| e.to_string())?;
    let unit = connection
        .bus
        .working_parent_properties(&named, bus::Interface::Unit, until)
        .map_err(|e| e.to_string())?;
    let service = connection
        .bus
        .working_parent_properties(&named, bus::Interface::Service, until)
        .map_err(|e| e.to_string())?;
    let after = connection
        .bus
        .working_parent(until)
        .map_err(|e| e.to_string())?;
    need(
        named == after,
        "fixed parent object changed during retirement observation",
    )?;
    connection.guard()?;
    need(
        Instant::now() < until,
        "working terminal manager read exceeded its original end",
    )?;
    Ok(Snapshot { unit, service })
}
fn group_file(parent: &File, name: &CStr) -> Result<File, String> {
    super::super::super::open_at(
        parent.as_raw_fd(),
        name,
        libc::O_RDONLY | libc::O_NONBLOCK | libc::O_CLOEXEC,
    )
    .map_err(|e| e.to_string())
}
fn cgroup_type(file: &File) -> Result<(), String> {
    let mut value = std::mem::MaybeUninit::<libc::statfs>::uninit();
    if unsafe { libc::fstatfs(file.as_raw_fd(), value.as_mut_ptr()) } != 0 {
        return Err(io::Error::last_os_error().to_string());
    }
    need(
        unsafe { value.assume_init() }.f_type == libc::CGROUP2_SUPER_MAGIC,
        "working return needs the actual host cgroup2 filesystem",
    )
}
struct ParentGroup {
    slice: File,
    slice_pin: [u64; 9],
    directory: Option<File>,
    pin: Option<[u64; 9]>,
}
impl ParentGroup {
    fn open(actual: &ParentTerminal) -> Result<Self, String> {
        let slice_path = Path::new("/sys/fs/cgroup/system.slice");
        need(
            slice_path.canonicalize().map_err(|e| e.to_string())? == slice_path,
            "working return system slice alias",
        )?;
        let slice = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open(slice_path)
            .map_err(|e| e.to_string())?;
        cgroup_type(&slice)?;
        let slice_pin = identity(&slice).map_err(|e| e.to_string())?;
        need(
            slice_pin[3..5] == [0, 0] && slice_pin[2] & 0o022 == 0,
            "working return system slice is not root protected",
        )?;
        let directory = match super::super::super::open_at(
            slice.as_raw_fd(),
            &CString::new(contract::PARENT_UNIT).unwrap(),
            libc::O_RDONLY | libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC,
        ) {
            Ok(file) => Some(file),
            Err(error) if error.raw_os_error() == Some(libc::ENOENT) => None,
            Err(error) => return Err(error.to_string()),
        };
        let pin = directory
            .as_ref()
            .map(identity)
            .transpose()
            .map_err(|e| e.to_string())?;
        let value = Self {
            slice,
            slice_pin,
            directory,
            pin,
        };
        value.guard(actual)?;
        Ok(value)
    }
    fn guard(&self, actual: &ParentTerminal) -> Result<(), String> {
        let named_slice = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open("/sys/fs/cgroup/system.slice")
            .map_err(|e| e.to_string())?;
        need(
            identity(&self.slice).map_err(|e| e.to_string())?[..5] == self.slice_pin[..5]
                && identity(&named_slice).map_err(|e| e.to_string())?[..5] == self.slice_pin[..5],
            "held working return system slice changed",
        )?;
        let named = super::super::super::open_at(
            self.slice.as_raw_fd(),
            &CString::new(contract::PARENT_UNIT).unwrap(),
            libc::O_RDONLY | libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC,
        );
        match (&self.directory, &self.pin, named) {
            (None, None, Err(error)) if error.raw_os_error() == Some(libc::ENOENT) => need(
                actual.group.is_empty(),
                "PID1 still names an absent working cgroup",
            )?,
            (Some(held_group), Some(pin), Ok(named)) => {
                cgroup_type(held_group)?;
                need(
                    pin[1] == actual.group_id
                        && pin[3..5] == [0, 0]
                        && pin[2] & 0o022 == 0
                        && identity(held_group).map_err(|e| e.to_string())?[..5] == pin[..5]
                        && identity(&named).map_err(|e| e.to_string())?[..5] == pin[..5]
                        && crate::native_hardware_label::label(held_group)
                            .map_err(|e| e.to_string())?
                            == b"u:object_r:p4_linux_working_cgroup_t:s0",
                    "retired working cgroup is another actual generation",
                )?;
                let procs = super::super::super::bounded_text(
                    group_file(held_group, c"cgroup.procs")?,
                    65536,
                )
                .map_err(|e| e.to_string())?;
                need(
                    procs.is_empty(),
                    "retired working cgroup still contains a process",
                )?;
                let events = super::super::super::bounded_text(
                    group_file(held_group, c"cgroup.events")?,
                    4096,
                )
                .map_err(|e| e.to_string())?;
                let populated = events
                    .lines()
                    .filter_map(|s| s.strip_prefix("populated "))
                    .collect::<Vec<_>>();
                need(
                    populated == ["0"],
                    "retired working cgroup is still populated",
                )?;
                let path = Path::new("/sys/fs/cgroup/system.slice").join(contract::PARENT_UNIT);
                need(
                    !fs::read_dir(path).map_err(|e| e.to_string())?.any(|entry| {
                        entry.map_or(true, |e| e.file_type().map_or(true, |t| t.is_dir()))
                    }),
                    "retired working parent left an unretired nested cgroup",
                )?;
            }
            _ => return Err("working parent cgroup presence or generation changed".into()),
        }
        Ok(())
    }
}

/// No public constructor, Deserialize, or caller-provided PID/endpoint. This
/// observes the actual fixed parent only in the admitted independent return role.
pub(crate) struct RetiredWorkingParent {
    connection: Connection,
    current: BoundProcess,
    manager: BoundProcess,
    manager_program: Tool,
    namespaces: Vec<(File, File)>,
    source: SourceUnit,
    snapshot: Snapshot,
    terminal: ParentTerminal,
    group: ParentGroup,
    original_end: Instant,
    original_end_ns: u64,
    return_invocation: bus::Invocation,
    return_snapshot: Snapshot,
    return_source: SourceUnit,
    return_group: ReturnGroup,
    command_active: Cell<bool>,
    next_command: Cell<u8>,
    poisoned: Cell<bool>,
}
impl RetiredWorkingParent {
    pub(crate) fn observe(boot: &BootOwner, admission_end: Instant) -> Result<Self, String> {
        boot.require_return().map_err(|e| e.to_string())?;
        let until = admission_end.min(Instant::now() + Duration::from_secs(15));
        let current = BoundProcess::capture(std::process::id()).map_err(|e| e.to_string())?;
        let manager = BoundProcess::capture(1).map_err(|e| e.to_string())?;
        let manager_program = Tool::open("/usr/lib/systemd/systemd").map_err(|e| e.to_string())?;
        need(
            manager.identity.comm == "systemd"
                && identity(&manager.open("exe", false).map_err(|e| e.to_string())?)
                    .map_err(|e| e.to_string())?
                    == manager_program.identity,
            "working return PID1 is not the selected normal manager inode",
        )?;
        let mut namespaces = Vec::new();
        for name in [
            "ns/mnt",
            "ns/user",
            "ns/pid",
            "ns/cgroup",
            "ns/net",
            "ns/ipc",
            "ns/uts",
        ] {
            let own = current.open(name, false).map_err(|e| e.to_string())?;
            let manager_ns = manager.open(name, false).map_err(|e| e.to_string())?;
            need(
                super::super::super::same_file(&own, &manager_ns).map_err(|e| e.to_string())?,
                "working return left the actual original manager namespace",
            )?;
            namespaces.push((own, manager_ns));
        }
        let source = SourceUnit::open().map_err(|e| e.to_string())?;
        let connection = Connection::open(until)?;
        let snapshot = snapshot_named(&connection, until)?;
        let terminal = terminal(&snapshot)?;
        contract::WorkingSchedule::selected()
            .authorization_end_ns(terminal.start_ns()?)
            .map_err(|e| e.to_string())?;
        let source_stop_end = terminal
            .start_ns()?
            .checked_add(
                (contract::budget::SERVICE_SECONDS + contract::budget::RETIREMENT_SECONDS)
                    * 1_000_000_000,
            )
            .ok_or("parent stop end overflow")?;
        need(
            terminal.exit_ns()? <= source_stop_end
                && source_stop_end
                    <= contract::WorkingSchedule::selected().parent_stop_end_by_boot_seconds
                        * 1_000_000_000,
            "working parent exited after its actual source-owned PID1 stop bound",
        )?;
        let group = ParentGroup::open(&terminal)?;
        let original_end_ns = terminal
            .exit_ns()?
            .checked_add(contract::RETURN_SECONDS * 1_000_000_000)
            .ok_or("working return end overflow")?
            .min(
                contract::WorkingSchedule::selected().normal_return_end_by_boot_seconds
                    * 1_000_000_000,
            );
        let now_ns = protocol::monotonic_ns().map_err(|e| e.to_string())?;
        need(
            now_ns < original_end_ns,
            "independent return started after the original parent return window",
        )?;
        let original_end = Instant::now() + Duration::from_nanos(original_end_ns - now_ns);
        let return_invocation = connection
            .bus
            .invocation(current.pidfd.as_fd(), until)
            .map_err(|e| e.to_string())?;
        let return_snapshot = return_snapshot(&connection, &return_invocation, until)?;
        validate_return(
            &return_snapshot,
            &return_invocation,
            current.identity.pid,
            terminal.main_exit,
        )?;
        let return_source = SourceUnit::open_return().map_err(|e| e.to_string())?;
        let return_group = ReturnGroup::open(&return_snapshot, current.identity.pid)?;
        need(
            snapshot_named(&connection, until)? == snapshot,
            "working parent terminal metadata changed across kernel retirement read",
        )?;
        let value = Self {
            connection,
            current,
            manager,
            manager_program,
            namespaces,
            source,
            snapshot,
            terminal,
            group,
            original_end,
            original_end_ns,
            return_invocation,
            return_snapshot,
            return_source,
            return_group,
            command_active: Cell::new(false),
            next_command: Cell::new(0),
            poisoned: Cell::new(false),
        };
        value.guard(boot)?;
        let start_us = number(
            &value.return_snapshot.service,
            "ExecMainStartTimestampMonotonic",
        )?
        .min(commands(&value.return_snapshot.service)?.started[1]);
        let admission_cap = start_us
            .checked_mul(1000)
            .and_then(|v| v.checked_add(30_000_000_000))
            .ok_or("independent return admission end overflow")?;
        need(
            Instant::now() < admission_end
                && protocol::monotonic_ns().map_err(|e| e.to_string())? < admission_cap,
            "independent return admission consumed its actual PID1-start based local prefix",
        )?;
        Ok(value)
    }
    pub(crate) fn guard(&self, boot: &BootOwner) -> Result<(), String> {
        boot.require_return().map_err(|e| e.to_string())?;
        need(
            !self.poisoned.get()
                && Instant::now() < self.original_end
                && protocol::monotonic_ns().map_err(|e| e.to_string())? < self.original_end_ns,
            "working return retirement window exhausted or a command was retained",
        )?;
        self.current.validate().map_err(|e| e.to_string())?;
        self.manager.validate().map_err(|e| e.to_string())?;
        self.manager_program.guard().map_err(|e| e.to_string())?;
        self.source.guard().map_err(|e| e.to_string())?;
        self.return_source.guard().map_err(|e| e.to_string())?;
        for (index, name) in [
            "ns/mnt",
            "ns/user",
            "ns/pid",
            "ns/cgroup",
            "ns/net",
            "ns/ipc",
            "ns/uts",
        ]
        .iter()
        .enumerate()
        {
            let (own, manager) = &self.namespaces[index];
            need(
                super::super::super::same_file(own, manager).map_err(|e| e.to_string())?
                    && super::super::super::same_file(
                        own,
                        &self.current.open(name, false).map_err(|e| e.to_string())?,
                    )
                    .map_err(|e| e.to_string())?
                    && super::super::super::same_file(
                        manager,
                        &self.manager.open(name, false).map_err(|e| e.to_string())?,
                    )
                    .map_err(|e| e.to_string())?,
                "working return retained namespace identity changed",
            )?;
        }
        self.group.guard(&self.terminal)?;
        let until = self
            .original_end
            .min(Instant::now() + Duration::from_secs(15));
        need(
            snapshot_named(&self.connection, until)? == self.snapshot,
            "working parent original terminal invocation changed",
        )?;
        self.group.guard(&self.terminal)?;
        need(
            self.connection
                .bus
                .invocation(self.current.pidfd.as_fd(), until)
                .map_err(|e| e.to_string())?
                == self.return_invocation,
            "actual independent return invocation changed",
        )?;
        need(
            return_snapshot(&self.connection, &self.return_invocation, until)?
                == self.return_snapshot,
            "actual independent return service changed",
        )?;
        self.return_group
            .guard(self.current.identity.pid, self.command_active.get())?;
        Ok(())
    }
    pub(crate) fn normal_return_end_ns(&self) -> Result<u64, String> {
        Ok(self.original_end_ns)
    }
    pub(crate) fn clean(&self) -> bool {
        self.terminal.clean()
    }
    pub(crate) fn deadline(&self) -> Instant {
        self.original_end
    }
    pub(crate) fn parent_pid(&self) -> u32 {
        self.terminal.pid
    }
    pub(crate) fn parent_start_ns(&self) -> Result<u64, String> {
        self.terminal.start_ns()
    }
    pub(crate) fn parent_exit_ns(&self) -> Result<u64, String> {
        self.terminal.exit_ns()
    }

    pub(crate) fn compare_capture(&self, parent: &Value, boot: &BootOwner) -> Result<(), String> {
        self.guard(boot)?;
        need(
            self.clean(),
            "failed working parent cannot authenticate a successful capture",
        )?;
        let invocation = self
            .terminal
            .invocation
            .iter()
            .map(|b| format!("{b:02x}"))
            .collect::<String>();
        let p = parent
            .get("properties")
            .ok_or("working capture parent properties absent")?;
        let f9: [u64; 9] =
            serde_json::from_value(parent["cgroup_identity"].clone()).map_err(|e| e.to_string())?;
        let executable_f9: [u64; 9] =
            serde_json::from_value(parent["normal_executable"]["f9"].clone())
                .map_err(|e| e.to_string())?;
        let unit_f9: [u64; 9] = serde_json::from_value(parent["normal_unit"]["f9"].clone())
            .map_err(|e| e.to_string())?;
        need(
            parent["schema"] == "droidloom.physical-qualification-parent.v1"
                && parent["unit"] == contract::PARENT_UNIT
                && parent["invocation"] == invocation
                && parent["parent_pid"] == self.terminal.pid
                && parent["parent_start_ticks"].as_u64().is_some_and(|n| n > 0)
                && p["ExecMainStartTimestampMonotonic"] == self.terminal.main_start.to_string()
                && p["ExecStartCommandMonotonic"] == self.terminal.command_started[1].to_string()
                && p["ExecStartCommandRealtime"] == self.terminal.command_started[0].to_string()
                && p["InvocationID"] == invocation
                && p["MainPID"] == self.terminal.pid.to_string()
                && parent["cgroup"]
                    == format!("/sys/fs/cgroup/system.slice/{}", contract::PARENT_UNIT)
                && f9[1] == self.terminal.group_id
                && f9[3..5] == [0, 0]
                && parent["normal_executable"]["path"] == contract::APPLICATIONS_EXECUTABLE
                && parent["normal_executable"]["sha256"] == boot.config().applications.sha256
                && executable_f9 == boot.applications_identity().map_err(|e| e.to_string())?
                && parent["normal_unit"]["path"] == self.source.path.to_str().unwrap()
                && unit_f9 == self.source.pin
                && parent["normal_unit"]["sha256"]
                    == protocol::sha(protocol::UNIT_SOURCE.as_bytes())
                && parent["all_child_processes_retired"] == true
                && parent["parent_unit_retirement_requires_external_readback"] == true,
            "protected working capture differs from actual retired PID1 parent generation",
        )?;
        Ok(())
    }
    pub(crate) fn observation(&self) -> Value {
        json!({"schema":"droidloom.working-parent-retirement-observed.v1",
            "unit":contract::PARENT_UNIT,
            "invocation":self.terminal.invocation.iter().map(|b|format!("{b:02x}")).collect::<String>(),
            "parent_pid":self.terminal.pid,"main_start_monotonic_us":self.terminal.main_start,
            "command_started":self.terminal.command_started,"command_exited":self.terminal.command_exited,
            "main_exit_monotonic_us":self.terminal.main_exit,"state_change_monotonic_us":self.terminal.state_changed,
            "exit_code_kind":self.terminal.code,"exit_status":self.terminal.status,"result":self.terminal.result,
            "manager_cgroup_id":self.terminal.group_id,"cgroup_present":self.group.directory.is_some(),
            "fresh_private_pid1_double_read":true,"actual_parent_group_unpopulated":true,
            "actual_parent_clean_exit":self.clean(),"capture_from_json_reconstructed":false,
            "independent_return_invocation": self.return_invocation.id.iter().map(|b|format!("{b:02x}")).collect::<String>(),
            "independent_return_pid": self.current.identity.pid,
            "normal_return_end_monotonic_ns": self.original_end_ns,
            "original_return_observed":false,"production_ready":false})
    }
}

fn return_snapshot(
    connection: &Connection,
    invocation: &bus::Invocation,
    until: Instant,
) -> Result<Snapshot, String> {
    connection.guard()?;
    let unit = connection
        .bus
        .properties(invocation, bus::Interface::Unit, until)
        .map_err(|e| e.to_string())?;
    let service = connection
        .bus
        .properties(invocation, bus::Interface::Service, until)
        .map_err(|e| e.to_string())?;
    connection.guard()?;
    need(
        Instant::now() < until,
        "independent return manager read exhausted the original end",
    )?;
    Ok(Snapshot { unit, service })
}
fn validate_return(
    snapshot: &Snapshot,
    invocation: &bus::Invocation,
    actual_pid: u32,
    parent_exit: u64,
) -> Result<(), String> {
    use bus::Value as V;
    let unit = &snapshot.unit;
    let service = &snapshot.service;
    loaded(unit, contract::RETURN_UNIT)?;
    need(
        invocation.unit == contract::RETURN_UNIT
            && invocation.path
                == "/org/freedesktop/systemd1/unit/droidloom_2dworking_2dqualification_2dreturn_2eservice",
        "independent return is not the actual fixed PID1 unit",
    )?;
    exact(unit, "InvocationID", V::Bytes(invocation.id.to_vec()))?;
    exact(unit, "ActiveState", V::Text("active".into()))?;
    exact(unit, "SubState", V::Text("running".into()))?;
    for key in ["OnSuccess", "OnFailure"] {
        exact(unit, key, V::Strings(Vec::new()))?;
    }
    for (key, value) in [
        ("Type", "exec"),
        ("ExitType", "main"),
        ("User", "root"),
        ("Group", "root"),
        ("Restart", "no"),
        ("KillMode", "control-group"),
        ("TimeoutStopFailureMode", "terminate"),
        ("Slice", "system.slice"),
        ("WorkingDirectory", "/"),
        ("RootDirectory", ""),
        ("RootImage", ""),
        ("DelegateSubgroup", ""),
        ("Result", "success"),
    ] {
        exact(service, key, V::Text(value.into()))?;
    }
    for (key, value) in [
        ("RemainAfterExit", false),
        ("SendSIGKILL", true),
        ("SendSIGHUP", false),
        ("PrivateMounts", false),
        ("DynamicUser", false),
        ("Delegate", false),
        // PID1's configured initial state is false. BootOwner independently
        // verifies that the running entry has already sealed actual NNP=true.
        ("NoNewPrivileges", false),
    ] {
        exact(service, key, V::Boolean(value))?;
    }
    for (key, value) in [
        ("KillSignal", 15),
        ("RestartKillSignal", 15),
        ("FinalKillSignal", 9),
        ("ExecMainCode", 0),
        ("ExecMainStatus", 0),
    ] {
        exact(service, key, V::I32(value))?;
    }
    for (key, value) in [
        ("MemoryMax", 536_870_912),
        ("MemorySwapMax", 0),
        ("TasksMax", 32),
        ("LimitCORE", 0),
        ("CPUQuotaPerSecUSec", 1_000_000),
        ("CPUQuotaPeriodUSec", 100_000),
        ("RuntimeMaxUSec", contract::RETURN_SECONDS * 1_000_000),
        ("TimeoutStopUSec", 10_000_000),
        ("AmbientCapabilities", 0),
        (
            "CapabilityBoundingSet",
            crate::native_once_capabilities::MAINTENANCE,
        ),
        ("ExecMainExitTimestampMonotonic", 0),
    ] {
        exact(service, key, V::U64(value))?;
    }
    for (key, value) in [
        ("MainPID", actual_pid),
        ("ExecMainPID", actual_pid),
        ("ControlPID", 0),
        ("NRestarts", 0),
        ("UMask", 0o77),
    ] {
        exact(service, key, V::U32(value))?;
    }
    exact(
        service,
        "ControlGroup",
        V::Text(format!("/system.slice/{}", contract::RETURN_UNIT)),
    )?;
    return_mac_selection(service)?;
    need(
        matches!(service.get("CPUAffinity"),Some(V::Bytes(v)) if affinity(v)==[20]),
        "independent return left its fixed source CPU affinity",
    )?;
    let start = number(service, "ExecMainStartTimestampMonotonic")?;
    let command = commands(service)?;
    need(
        start >= parent_exit
            && command.started[1] >= parent_exit
            && command.path == contract::RETURN_EXECUTABLE
            && command.arguments == [contract::RETURN_EXECUTABLE, contract::RETURN_MODE]
            && command.flags.is_empty()
            && command.pid == actual_pid
            && command.started.iter().all(|v| *v > 0)
            && command.exited == [0, 0]
            && command.code == 0
            && command.status == 0,
        "independent return does not follow the actual parent exit with its one fixed command",
    )?;
    Ok(())
}
struct ReturnGroup {
    path: PathBuf,
    file: File,
    pin: [u64; 9],
    manager_id: u64,
}
impl ReturnGroup {
    fn open(snapshot: &Snapshot, pid: u32) -> Result<Self, String> {
        let path = Path::new("/sys/fs/cgroup/system.slice").join(contract::RETURN_UNIT);
        need(
            path.canonicalize().map_err(|e| e.to_string())? == path,
            "independent return cgroup alias",
        )?;
        let file = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open(&path)
            .map_err(|e| e.to_string())?;
        cgroup_type(&file)?;
        let pin = identity(&file).map_err(|e| e.to_string())?;
        let manager_id = number(&snapshot.service, "ControlGroupId")?;
        let value = Self {
            path,
            file,
            pin,
            manager_id,
        };
        value.guard(pid, false)?;
        Ok(value)
    }
    fn guard(&self, pid: u32, actual_command_in_flight: bool) -> Result<(), String> {
        cgroup_type(&self.file)?;
        let named = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open(&self.path)
            .map_err(|e| e.to_string())?;
        need(
            self.pin[1] == self.manager_id
                && self.pin[3..5] == [0, 0]
                && self.pin[2] & 0o022 == 0
                && identity(&self.file).map_err(|e| e.to_string())?[..5] == self.pin[..5]
                && identity(&named).map_err(|e| e.to_string())?[..5] == self.pin[..5]
                && crate::native_hardware_label::label(&self.file).map_err(|e| e.to_string())?
                    == b"u:object_r:p4_linux_working_return_cgroup_t:s0",
            "independent return lost its exact fixed cgroup generation",
        )?;
        let current = super::super::super::bounded_text(
            File::open("/proc/self/cgroup").map_err(|e| e.to_string())?,
            8192,
        )
        .map_err(|e| e.to_string())?;
        need(
            current.trim() == format!("0::/system.slice/{}", contract::RETURN_UNIT),
            "independent return process left its fixed cgroup",
        )?;
        for (name, value) in [
            (c"cpu.max", "100000 100000"),
            (c"memory.max", "536870912"),
            (c"memory.swap.max", "0"),
            (c"pids.max", "32"),
            (c"memory.swap.current", "0"),
        ] {
            let file = group_file(&self.file, name)?;
            need(
                crate::native_hardware_label::label(&file).map_err(|e| e.to_string())?
                    == b"u:object_r:p4_linux_working_return_cgroup_control_t:s0",
                "independent return control has another normal MAC label",
            )?;
            let actual =
                super::super::super::bounded_text(file, 4096).map_err(|e| e.to_string())?;
            need(
                actual.trim() == value,
                "independent return kernel resource bound changed",
            )?;
        }
        let procs =
            super::super::super::bounded_text(group_file(&self.file, c"cgroup.procs")?, 65536)
                .map_err(|e| e.to_string())?;
        let mut members = std::collections::BTreeSet::new();
        for part in procs.split_ascii_whitespace() {
            let value = part
                .parse::<u32>()
                .map_err(|_| "invalid independent return cgroup member")?;
            need(
                value > 1 && members.insert(value) && members.len() <= 32,
                "independent return kernel membership exceeds its fixed bound",
            )?;
        }
        need(
            members.contains(&pid) && (actual_command_in_flight || members == [pid].into()),
            "independent return has an unowned or unretired process",
        )?;
        // Only the private actual-spawn factory sets command_active. There is
        // no external boolean or PID-list constructor, delegation, migration,
        // caller cgroup path or second simultaneous command.
        need(
            !fs::read_dir(&self.path)
                .map_err(|e| e.to_string())?
                .any(|v| v.map_or(true, |e| e.file_type().map_or(true, |t| t.is_dir()))),
            "independent return left a nested process group",
        )?;
        for (name, keys) in [
            (c"memory.events", &["oom", "oom_kill", "oom_group_kill"][..]),
            (c"pids.events", &["max"][..]),
        ] {
            let body = super::super::super::bounded_text(group_file(&self.file, name)?, 4096)
                .map_err(|e| e.to_string())?;
            for key in keys {
                let values = body
                    .lines()
                    .filter_map(|line| line.split_once(' '))
                    .filter_map(|(k, v)| (k == *key).then_some(v))
                    .collect::<Vec<_>>();
                need(
                    values == ["0"],
                    "independent return resource controller reported a failure",
                )?;
            }
        }
        need(
            identity(&named).map_err(|e| e.to_string())?[..5] == self.pin[..5],
            "independent return cgroup changed during kernel read",
        )?;
        Ok(())
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) enum MaintenanceOperation {
    Collect,
    Rollback,
    Reboot,
}
impl MaintenanceOperation {
    pub(crate) fn name(self) -> &'static str {
        match self {
            Self::Collect => "collect",
            Self::Rollback => "rollback",
            Self::Reboot => "reboot",
        }
    }
    pub(crate) fn seconds(self) -> u64 {
        match self {
            Self::Collect => 90,
            Self::Rollback | Self::Reboot => 30,
        }
    }
    fn ordinal(self) -> u8 {
        match self {
            Self::Collect => 0,
            Self::Rollback => 1,
            Self::Reboot => 2,
        }
    }
    fn future_seconds(self) -> u64 {
        match self {
            Self::Collect => 60,
            Self::Rollback => 30,
            Self::Reboot => 0,
        }
    }
}
/// A retained real std::process::Child and kernel PIDFD from exactly one
/// fixed normal execveat. It cannot be recreated from its pid or JSON output.
pub(crate) struct MaintenanceInvocation<'a> {
    owner: &'a RetiredWorkingParent,
    child: std::process::Child,
    pidfd: File,
    operation: MaintenanceOperation,
    end: Instant,
    last_guard: Instant,
    retired: bool,
}
impl Drop for MaintenanceInvocation<'_> {
    fn drop(&mut self) {
        if !self.retired {
            self.owner.poisoned.set(true);
        }
        // An incomplete command remains the unit's responsibility. Returning
        // failure makes PID1 stop this exact control-group before its fixed
        // final SIGKILL. Never start a second operation on top of it.
    }
}
impl RetiredWorkingParent {
    pub(crate) fn spawn_maintenance<'a>(
        &'a self,
        boot: &BootOwner,
        operation: MaintenanceOperation,
        stdout: &File,
        stderr: &File,
    ) -> Result<MaintenanceInvocation<'a>, String> {
        use std::os::unix::process::CommandExt;
        use std::process::{Command, Stdio};
        self.guard(boot)?;
        need(
            !self.command_active.get() && self.next_command.get() == operation.ordinal(),
            "working return maintenance sequence is not the one actual fresh command",
        )?;
        let reserve = Duration::from_secs(operation.future_seconds());
        let end = (Instant::now() + Duration::from_secs(operation.seconds())).min(
            self.original_end
                .checked_sub(reserve)
                .ok_or("return operation reserve underflow")?,
        );
        need(
            Instant::now() < end,
            "normal return lacks the remaining fixed maintenance budget",
        )?;
        let fd = boot
            .maintenance_executable()
            .map_err(|e| e.to_string())?
            .as_raw_fd();
        let argv = [
            CString::new(contract::MAINTENANCE_EXECUTABLE).unwrap(),
            CString::new(operation.name()).unwrap(),
        ];
        let environment = [
            CString::new("PATH=/usr/sbin:/usr/bin:/sbin:/bin").unwrap(),
            CString::new("LC_ALL=C").unwrap(),
        ];
        let mut command = Command::new(contract::MAINTENANCE_EXECUTABLE);
        command
            .arg(operation.name())
            .env_clear()
            .current_dir("/")
            .stdin(Stdio::null())
            .stdout(stdout.try_clone().map_err(|e| e.to_string())?)
            .stderr(stderr.try_clone().map_err(|e| e.to_string())?);
        let parent = std::process::id();
        unsafe {
            command.pre_exec(move || {
                if libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGKILL) != 0 {
                    return Err(io::Error::last_os_error());
                }
                if libc::getppid() as u32 != parent {
                    return Err(invalid("independent return died before normal exec"));
                }
                let args = [argv[0].as_ptr(), argv[1].as_ptr(), std::ptr::null()];
                let env = [
                    environment[0].as_ptr(),
                    environment[1].as_ptr(),
                    std::ptr::null(),
                ];
                libc::syscall(
                    libc::SYS_execveat,
                    fd,
                    c"".as_ptr(),
                    args.as_ptr(),
                    env.as_ptr(),
                    libc::AT_EMPTY_PATH,
                );
                Err(io::Error::last_os_error())
            });
        }
        let mut child = command.spawn().map_err(|e| e.to_string())?;
        self.command_active.set(true);
        let raw = unsafe { libc::syscall(libc::SYS_pidfd_open, child.id(), 0) } as libc::c_int;
        if raw < 0 {
            self.poisoned.set(true);
            let error = io::Error::last_os_error();
            let _ = child.kill();
            let _ = child.wait();
            return Err(format!("actual normal maintenance PIDFD: {error}"));
        }
        let pidfd = unsafe { File::from_raw_fd(raw) };
        Ok(MaintenanceInvocation {
            owner: self,
            child,
            pidfd,
            operation,
            end,
            last_guard: Instant::now(),
            retired: false,
        })
    }
}
impl MaintenanceInvocation<'_> {
    pub(crate) fn deadline(&self) -> Instant {
        self.end
    }
    pub(crate) fn poll(
        &mut self,
        boot: &BootOwner,
    ) -> Result<Option<std::process::ExitStatus>, String> {
        need(
            !self.retired && Instant::now() < self.end,
            "actual normal maintenance command exceeded its immutable operation end",
        )?;
        match self.child.try_wait().map_err(|e| e.to_string())? {
            None => {
                // Full owner validation hashes the held normal manager and
                // re-reads PID1. Keep a bounded one-second custody cadence,
                // without repeating that work on every 50 ms child poll.
                // The immutable command end is still checked on every poll.
                let now = Instant::now();
                if now.saturating_duration_since(self.last_guard) >= Duration::from_secs(1) {
                    self.last_guard = now;
                    self.owner.guard(boot)?;
                }
                need(
                    Instant::now() < self.end,
                    "normal maintenance exhausted its original end during revalidation",
                )?;
                Ok(None)
            }
            Some(status) => {
                let mut poll = libc::pollfd {
                    fd: self.pidfd.as_raw_fd(),
                    events: libc::POLLIN,
                    revents: 0,
                };
                need(
                    unsafe { libc::poll(&mut poll, 1, 0) } == 1 && poll.revents & libc::POLLIN != 0,
                    "reaped normal child has not retired its actual PIDFD",
                )?;
                self.owner.command_active.set(false);
                self.owner.guard(boot)?;
                self.retired = true;
                self.owner.next_command.set(self.operation.ordinal() + 1);
                Ok(Some(status))
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn snapshot() -> Snapshot {
        use bus::Value as V;
        let mut unit = bus::Properties::new();
        let mut service = bus::Properties::new();
        for (key, value) in [
            ("Id", contract::PARENT_UNIT),
            ("LoadState", "loaded"),
            ("ActiveState", "inactive"),
            ("SubState", "dead"),
            ("FragmentPath", protocol::UNIT_FRAGMENT),
            ("SourcePath", ""),
        ] {
            unit.insert(key.into(), V::Text(value.into()));
        }
        for key in ["Transient", "NeedDaemonReload"] {
            unit.insert(key.into(), V::Boolean(false));
        }
        unit.insert("DropInPaths".into(), V::Strings(vec![]));
        unit.insert("InvocationID".into(), V::Bytes(vec![7; 16]));
        unit.insert("StateChangeTimestampMonotonic".into(), V::U64(900));
        unit.insert("Job".into(), V::Job(0, "/".into()));
        for key in ["OnSuccess", "OnFailure"] {
            unit.insert(key.into(), V::Strings(vec![contract::RETURN_UNIT.into()]));
        }
        for (key, value) in [
            ("Type", "exec"),
            ("ExitType", "main"),
            ("User", "root"),
            ("Group", "root"),
            ("Restart", "no"),
            ("KillMode", "control-group"),
            ("TimeoutStopFailureMode", "terminate"),
            ("Slice", "system.slice"),
            ("WorkingDirectory", "/"),
            ("RootDirectory", ""),
            ("RootImage", ""),
            ("DelegateSubgroup", ""),
            ("ControlGroup", ""),
            ("Result", "success"),
        ] {
            service.insert(key.into(), V::Text(value.into()));
        }
        for (key, value) in [
            ("RemainAfterExit", false),
            ("SendSIGKILL", true),
            ("SendSIGHUP", false),
            ("PrivateMounts", false),
            ("DynamicUser", false),
            ("Delegate", false),
        ] {
            service.insert(key.into(), V::Boolean(value));
        }
        for (key, value) in [
            ("KillSignal", 15),
            ("RestartKillSignal", 15),
            ("FinalKillSignal", 9),
            ("ExecMainCode", libc::CLD_EXITED),
            ("ExecMainStatus", 0),
        ] {
            service.insert(key.into(), V::I32(value));
        }
        for (key, value) in [
            ("MemoryMax", 2_147_483_648),
            ("MemorySwapMax", 0),
            ("TasksMax", 64),
            ("LimitCORE", 0),
            ("CPUQuotaPerSecUSec", 2_000_000),
            ("CPUQuotaPeriodUSec", 100_000),
            ("RuntimeMaxUSec", protocol::SERVICE_SECONDS * 1_000_000),
            ("TimeoutStopUSec", protocol::RETIREMENT_SECONDS * 1_000_000),
            ("AmbientCapabilities", 0),
            ("ExecMainStartTimestampMonotonic", 100),
            ("ExecMainExitTimestampMonotonic", 850),
            ("ControlGroupId", 197206),
        ] {
            service.insert(key.into(), V::U64(value));
        }
        for (key, value) in [
            ("MainPID", 0),
            ("ControlPID", 0),
            ("ExecMainPID", 1234),
            ("NRestarts", 0),
            ("UMask", 0o77),
        ] {
            service.insert(key.into(), V::U32(value));
        }
        service.insert(
            "AppArmorProfile".into(),
            V::Profile(false, "droidloom-working-qualification".into()),
        );
        service.insert("CPUAffinity".into(), V::Bytes(vec![0, 0, 0x30]));
        for key in [
            "ExecConditionEx",
            "ExecStartPreEx",
            "ExecStartPostEx",
            "ExecReloadEx",
            "ExecStopEx",
            "ExecStopPostEx",
        ] {
            service.insert(key.into(), V::Commands(vec![]));
        }
        service.insert(
            "ExecStartEx".into(),
            V::Commands(vec![bus::ExecCommand {
                path: protocol::EXE.into(),
                arguments: protocol::parent_argv(),
                flags: vec![],
                started: [1_000_000, 99],
                exited: [1_000_751, 850],
                pid: 1234,
                code: libc::CLD_EXITED,
                status: 0,
            }]),
        );
        Snapshot { unit, service }
    }
    #[test]
    fn working_return_same_elf_requires_its_non_ignorable_explicit_mac_selection() {
        use bus::Value as V;
        let mut properties = bus::Properties::new();
        properties.insert(
            "AppArmorProfile".into(),
            V::Profile(false, "droidloom-working-return".into()),
        );
        let role = std::str::from_utf8(contract::layout::WORKING_RETURN_ROLE).unwrap();
        properties.insert("SELinuxContext".into(), V::Profile(false, role.into()));
        assert!(return_mac_selection(&properties).is_ok());
        for wrong in [
            V::Profile(true, role.into()),
            V::Profile(false, "u:system_r:p4_linux_once_return_t:s0".into()),
            V::Profile(false, String::new()),
            V::Text(role.into()),
        ] {
            let mut other = properties.clone();
            other.insert("SELinuxContext".into(), wrong);
            assert!(return_mac_selection(&other).is_err());
        }
        properties.remove("SELinuxContext");
        assert!(return_mac_selection(&properties).is_err());
    }
    #[test]
    fn working_retirement_inactive_without_real_invocation_or_exit_is_rejected() {
        use bus::Value as V;
        let good = snapshot();
        assert!(terminal(&good).unwrap().clean());
        for (key, value) in [
            ("ExecMainPID", V::U32(0)),
            ("ExecMainStartTimestampMonotonic", V::U64(0)),
            ("ExecMainExitTimestampMonotonic", V::U64(0)),
            ("ControlGroupId", V::U64(0)),
            ("MainPID", V::U32(1234)),
            ("ControlPID", V::U32(1235)),
        ] {
            let mut bad = good.clone();
            bad.service.insert(key.into(), value);
            assert!(terminal(&bad).is_err(), "{key}");
        }
        let mut bad = good.clone();
        bad.unit
            .insert("InvocationID".into(), V::Bytes(vec![0; 16]));
        assert!(terminal(&bad).is_err());
        let mut bad = good.clone();
        bad.unit.insert("InvocationID".into(), V::Bytes(vec![]));
        assert!(terminal(&bad).is_err());
    }
    #[test]
    fn working_retirement_retains_failed_parent_without_claiming_clean_capture() {
        use bus::Value as V;
        let mut failed = snapshot();
        failed
            .unit
            .insert("ActiveState".into(), V::Text("failed".into()));
        failed
            .unit
            .insert("SubState".into(), V::Text("failed".into()));
        failed
            .service
            .insert("Result".into(), V::Text("exit-code".into()));
        failed.service.insert("ExecMainStatus".into(), V::I32(1));
        let V::Commands(commands) = failed.service.get_mut("ExecStartEx").unwrap() else {
            panic!()
        };
        commands[0].status = 1;
        assert!(!terminal(&failed).unwrap().clean());
    }
    #[test]
    fn working_retirement_rejects_command_exit_and_manager_generation_mismatch() {
        use bus::Value as V;
        let good = snapshot();
        for (field, value) in [
            ("StateChangeTimestampMonotonic", V::U64(849)),
            ("Job", V::Job(1, "/job/1".into())),
            ("OnSuccess", V::Strings(vec!["caller.service".into()])),
        ] {
            let mut bad = good.clone();
            bad.unit.insert(field.into(), value);
            assert!(terminal(&bad).is_err(), "{field}");
        }
        for variant in 0..4 {
            let mut bad = good.clone();
            let V::Commands(commands) = bad.service.get_mut("ExecStartEx").unwrap() else {
                panic!()
            };
            match variant {
                0 => commands[0].pid = 4321,
                1 => commands[0].exited[1] = 851,
                2 => commands[0].arguments.push("/tmp/caller".into()),
                _ => commands[0].started[0] = 0,
            }
            assert!(terminal(&bad).is_err());
        }
    }
    #[test]
    fn working_return_command_roster_and_caps_preserve_one_original_interval() {
        let operations = [
            MaintenanceOperation::Collect,
            MaintenanceOperation::Rollback,
            MaintenanceOperation::Reboot,
        ];
        assert_eq!(
            operations.map(MaintenanceOperation::name),
            ["collect", "rollback", "reboot"]
        );
        assert_eq!(operations.map(MaintenanceOperation::ordinal), [0, 1, 2]);
        assert_eq!(operations.map(MaintenanceOperation::seconds), [90, 30, 30]);
        assert_eq!(
            operations.map(MaintenanceOperation::future_seconds),
            [60, 30, 0]
        );
        assert_eq!(
            operations
                .iter()
                .copied()
                .map(MaintenanceOperation::seconds)
                .sum::<u64>()
                + 30,
            contract::RETURN_SECONDS
        );
    }
}
