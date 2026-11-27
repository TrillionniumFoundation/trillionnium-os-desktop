//! Source-owned parent of the separately bounded physical qualification suite.
//! Private child of application_leaf_unit: reuse the unchanged authenticated
//! PID1 bus and held executable/namespace machinery, not a second trust model.
use super::super::physical_qualification_channel as protocol;
use super::*;
use std::cell::{Cell, RefCell};
use std::io::{Read, Write};

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) enum KernelProfile {
    Standard,
    Calendar,
    DocumentsBuild,
}
impl KernelProfile {
    fn values(self) -> [&'static str; 4] {
        [
            match self {
                Self::Calendar => "50000 100000",
                Self::DocumentsBuild => "100000 100000",
                Self::Standard => "200000 100000",
            },
            if self != Self::Standard {
                "536870912"
            } else {
                "2147483648"
            },
            "0",
            "64",
        ]
    }
}
const CONTROL_NAMES: [&CStr; 4] = [c"cpu.max", c"memory.max", c"memory.swap.max", c"pids.max"];
const GROUP_LABEL: &[u8] = b"u:object_r:p4_linux_working_cgroup_t:s0";
const MEMBERSHIP_LABEL: &[u8] = b"u:object_r:p4_linux_working_cgroup_membership_t:s0";

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum ControlAccess {
    MutableProfile,
    ReadOnly,
}
impl ControlAccess {
    fn for_name(name: &CStr) -> io::Result<Self> {
        match name.to_bytes() {
            b"cpu.max" | b"memory.max" => Ok(Self::MutableProfile),
            b"memory.swap.max"
            | b"pids.max"
            | b"memory.events"
            | b"memory.swap.current"
            | b"pids.events"
            | b"memory.current" => Ok(Self::ReadOnly),
            _ => Err(invalid("physical owner does not admit this cgroup control")),
        }
    }
    fn flags(self) -> libc::c_int {
        match self {
            Self::MutableProfile => libc::O_RDWR,
            Self::ReadOnly => libc::O_RDONLY,
        }
    }
    fn label(self) -> &'static [u8] {
        match self {
            Self::MutableProfile => b"u:object_r:p4_linux_working_cgroup_mutable_t:s0",
            Self::ReadOnly => b"u:object_r:p4_linux_working_cgroup_readonly_t:s0",
        }
    }
}

fn root() -> io::Result<()> {
    protocol::require_working_actor()?;
    // SAFETY: identity queries do not mutate state.
    if unsafe {
        (
            libc::getuid(),
            libc::geteuid(),
            libc::getgid(),
            libc::getegid(),
        )
    } != (0, 0, 0, 0)
    {
        return Err(invalid(
            "physical qualification requires the actual root owner",
        ));
    }
    let mut limit = std::mem::MaybeUninit::<libc::rlimit>::uninit();
    // SAFETY: limit is correctly sized writable storage for this process.
    if unsafe { libc::getrlimit(libc::RLIMIT_NOFILE, limit.as_mut_ptr()) } != 0 {
        return Err(io::Error::last_os_error());
    }
    let limit = unsafe { limit.assume_init() };
    if limit.rlim_cur != protocol::NOFILE_LIMIT || limit.rlim_max != protocol::NOFILE_LIMIT {
        return Err(invalid(
            "physical qualification requires its actual fixed NOFILE limit",
        ));
    }
    if std::env::var_os("LD_PRELOAD").is_some() || std::env::var_os("LD_AUDIT").is_some() {
        return Err(invalid(
            "physical qualification does not accept loader injection",
        ));
    }
    Ok(())
}
fn process_root(process: &BoundProcess) -> io::Result<()> {
    let text = super::super::bounded_text(process.open("status", false)?, 64 * 1024)?;
    for field in ["Uid:", "Gid:"] {
        let rows: Vec<_> = text.lines().filter_map(|l| l.strip_prefix(field)).collect();
        if rows.len() != 1
            || rows[0].split_ascii_whitespace().collect::<Vec<_>>() != ["0", "0", "0", "0"]
        {
            return Err(invalid("physical producer process root credentials differ"));
        }
    }
    Ok(())
}
fn cmdline(process: &BoundProcess) -> io::Result<Vec<String>> {
    let mut raw = Vec::new();
    process
        .open("cmdline", false)?
        .take(8193)
        .read_to_end(&mut raw)?;
    if raw.len() > 8192 || raw.last() != Some(&0) {
        return Err(invalid("physical process argv bound differs"));
    }
    raw.pop();
    raw.split(|b| *b == 0)
        .map(|s| {
            String::from_utf8(s.to_vec()).map_err(|_| invalid("physical process argv is not UTF-8"))
        })
        .collect()
}
fn process_mac(process: &BoundProcess, role: &[u8], profile: &[u8]) -> io::Result<()> {
    process.validate()?;
    for (name, wanted) in [
        ("attr/selinux/current", role),
        ("attr/apparmor/current", profile),
    ] {
        let mut raw = Vec::new();
        process.open(name, false)?.take(513).read_to_end(&mut raw)?;
        if raw.is_empty() || raw.len() > 512 {
            return Err(invalid("working peer MAC observation exceeds bound"));
        }
        if raw.last() == Some(&b'\n') {
            raw.pop();
        }
        if raw.last() == Some(&0) {
            raw.pop();
        }
        if raw.contains(&0) || raw != wanted {
            return Err(invalid(
                "working peer has a different SELinux domain or AppArmor profile",
            ));
        }
    }
    process.validate()
}
fn process_group(process: &BoundProcess, group: &Path) -> io::Result<()> {
    let actual = super::super::bounded_text(process.open("cgroup", false)?, 8192)?;
    let relative = group
        .strip_prefix("/sys/fs/cgroup")
        .map_err(|_| invalid("fixed cgroup prefix"))?;
    if actual.trim() != format!("0::{}", relative.display()) {
        return Err(invalid("physical producer left its owned group"));
    }
    Ok(())
}

pub(crate) struct ChildPeer {
    current: BoundProcess,
    parent: BoundProcess,
    executable: Tool,
    group: PathBuf,
    arguments: Vec<String>,
    namespaces: Vec<(String, File, File)>,
}
impl ChildPeer {
    pub(crate) fn capture(plan: &protocol::Plan) -> io::Result<Self> {
        plan.guard()?;
        protocol::require_suite_actor()?;
        root()?;
        // SAFETY: getppid returns the current actual parent, never a caller PID.
        let parent_pid = unsafe { libc::getppid() };
        if parent_pid <= 1 {
            return Err(invalid("actual physical qualification parent required"));
        }
        let current = BoundProcess::capture(std::process::id())?;
        let parent = BoundProcess::capture(parent_pid as u32)?;
        let executable = Tool::open(protocol::EXE)?;
        let pin = plan.working_applications_pin()?;
        if executable.identity[6] != pin.bytes || executable.sha != pin.sha256 {
            return Err(invalid(
                "working child differs from the boot-admitted applications executable",
            ));
        }
        let group = PathBuf::from(format!(
            "/sys/fs/cgroup/system.slice/{}",
            protocol::unit_name()
        ));
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
            namespaces.push((
                name.into(),
                current.open(name, false)?,
                parent.open(name, false)?,
            ));
        }
        let result = Self {
            current,
            parent,
            executable,
            group,
            arguments: protocol::child_argv(&plan.path, &plan.digest)?,
            namespaces,
        };
        result.guard()?;
        Ok(result)
    }
    pub(crate) fn parent_pid(&self) -> u32 {
        self.parent.identity.pid
    }
    pub(crate) fn guard(&self) -> io::Result<()> {
        protocol::require_suite_actor()?;
        root()?;
        self.current.validate()?;
        self.parent.validate()?;
        if std::process::id() != self.current.identity.pid
            || unsafe { libc::getppid() } as u32 != self.parent.identity.pid
            || cmdline(&self.current)? != self.arguments
            || cmdline(&self.parent)? != protocol::parent_argv()
        {
            return Err(invalid(
                "physical private channel no longer has its exact same-exec parent",
            ));
        }
        self.executable.guard()?;
        process_mac(
            &self.current,
            protocol::layout::WORKING_SUITE_ROLE,
            protocol::layout::WORKING_SUITE_PROFILE,
        )?;
        process_mac(
            &self.parent,
            protocol::layout::WORKING_PARENT_ROLE,
            protocol::layout::WORKING_PARENT_PROFILE,
        )?;
        for p in [&self.current, &self.parent] {
            process_root(p)?;
            process_group(p, &self.group)?;
            if identity(&p.open("exe", false)?)? != self.executable.identity {
                return Err(invalid(
                    "physical parent or child differs from installed executable",
                ));
            }
        }
        for (name, a, b) in &self.namespaces {
            if !super::super::same_file(a, b)?
                || !super::super::same_file(a, &self.current.open(name, false)?)?
                || !super::super::same_file(b, &self.parent.open(name, false)?)?
            {
                return Err(invalid("physical parent/child namespaces changed"));
            }
        }
        Ok(())
    }
}

struct Control {
    name: &'static CStr,
    file: File,
    pin: [u64; 9],
    access: ControlAccess,
}
impl Control {
    fn open(group: &File, name: &'static CStr) -> io::Result<Self> {
        let access = ControlAccess::for_name(name)?;
        let file =
            super::super::open_at(group.as_raw_fd(), name, access.flags() | libc::O_NOFOLLOW)?;
        let pin = identity(&file)?;
        if pin[2] & libc::S_IFMT as u64 != libc::S_IFREG as u64
            || pin[3..5] != [0, 0]
            || pin[2] & 0o022 != 0
            || crate::native_hardware_label::label(&file)? != access.label()
        {
            return Err(invalid("root owned cgroup control required"));
        }
        Ok(Self {
            name,
            file,
            pin,
            access,
        })
    }
    fn text(&self, group: &File) -> io::Result<String> {
        let named = super::super::open_at(
            group.as_raw_fd(),
            self.name,
            libc::O_RDONLY | libc::O_NOFOLLOW,
        )?;
        if identity(&self.file)?[..6] != self.pin[..6]
            || identity(&named)?[..6] != self.pin[..6]
            || crate::native_hardware_label::label(&self.file)? != self.access.label()
            || crate::native_hardware_label::label(&named)? != self.access.label()
        {
            return Err(invalid("held physical resource control changed"));
        }
        let mut raw = [0u8; 8193];
        let n = self.file.read_at(&mut raw, 0)?;
        if n > 8192 {
            return Err(invalid("physical resource metadata exceeds bound"));
        }
        std::str::from_utf8(&raw[..n])
            .map(str::trim)
            .map(str::to_owned)
            .map_err(|_| invalid("physical resource metadata is not UTF-8"))
    }
    fn write(&self, group: &File, value: &str) -> io::Result<()> {
        if self.access != ControlAccess::MutableProfile {
            return Err(invalid(
                "physical owner may only change its CPU and memory profile",
            ));
        }
        self.text(group)?;
        // cgroup pseudo-files are single-command controls, not appendable data.
        let n = self.file.write_at(value.as_bytes(), 0)?;
        if n != value.len() || self.text(group)? != value {
            return Err(invalid("physical resource write/readback differs"));
        }
        Ok(())
    }
}

/// The ordinary installed source unit and each of its named ancestors remain
/// held for the whole invocation. A same-byte alias or a replaced parent is not
/// the source object authenticated at entry.
struct SourceUnit {
    path: PathBuf,
    file: File,
    pin: [u64; 9],
    parents: Vec<(PathBuf, File, [u64; 9])>,
}
impl SourceUnit {
    fn open() -> io::Result<Self> {
        let path = Path::new("/usr/lib/systemd/system").join(protocol::UNIT_NAME);
        if path.canonicalize()? != path {
            return Err(invalid("physical source unit alias"));
        }
        let mut parents = Vec::new();
        for parent in path
            .parent()
            .ok_or_else(|| invalid("unit parent absent"))?
            .ancestors()
        {
            let file = OpenOptions::new()
                .read(true)
                .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
                .open(parent)?;
            let pin = identity(&file)?;
            if pin[2] & libc::S_IFMT as u64 != libc::S_IFDIR as u64
                || pin[3..5] != [0, 0]
                || pin[2] & 0o022 != 0
            {
                return Err(invalid("physical source unit root parent required"));
            }
            parents.push((parent.into(), file, pin));
        }
        let file = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open(&path)?;
        let pin = identity(&file)?;
        if pin[2] & libc::S_IFMT as u64 != libc::S_IFREG as u64
            || pin[2] & 0o6022 != 0
            || pin[3..6] != [0, 0, 1]
            || pin[6] != protocol::UNIT_SOURCE.len() as u64
        {
            return Err(invalid("normal physical source unit metadata differs"));
        }
        let result = Self {
            path,
            file,
            pin,
            parents,
        };
        result.guard()?;
        Ok(result)
    }
    fn guard_parents(&self) -> io::Result<()> {
        for (path, file, pin) in &self.parents {
            let named = OpenOptions::new()
                .read(true)
                .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
                .open(path)?;
            // Directory timestamps and link counts may reflect unrelated unit
            // installs. Identity, kind, mode and ownership may not change.
            if identity(file)?[..5] != pin[..5] || identity(&named)?[..5] != pin[..5] {
                return Err(invalid("held physical source unit parent changed"));
            }
        }
        Ok(())
    }
    fn guard(&self) -> io::Result<()> {
        self.guard_parents()?;
        let named = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open(&self.path)?;
        if identity(&self.file)? != self.pin || identity(&named)? != self.pin {
            return Err(invalid("held physical source unit changed"));
        }
        let mut bytes = vec![0; protocol::UNIT_SOURCE.len()];
        self.file.read_exact_at(&mut bytes, 0)?;
        if bytes != protocol::UNIT_SOURCE.as_bytes()
            || self.file.read_at(&mut [0; 1], self.pin[6])? != 0
            || identity(&self.file)? != self.pin
            || identity(&named)? != self.pin
        {
            return Err(invalid("physical source unit changed during whole read"));
        }
        self.guard_parents()
    }
}

pub(crate) struct UnitOwner {
    current: BoundProcess,
    manager: BoundProcess,
    manager_exe: Tool,
    executable: Tool,
    namespaces: Vec<(&'static str, File, File)>,
    connection: Connection,
    invocation: bus::Invocation,
    properties: BTreeMap<String, String>,
    group_path: PathBuf,
    group: File,
    group_pin: [u64; 9],
    controls: Vec<Control>,
    events: Control,
    swap: Control,
    pids_events: Control,
    memory_current: Control,
    profile: Cell<KernelProfile>,
    source_unit: SourceUnit,
    child_arguments: RefCell<Option<Vec<String>>>,
    end: Instant,
}
impl UnitOwner {
    pub(crate) fn capture(
        applications: &crate::native_working_contract::PayloadPin,
        end: Instant,
    ) -> Result<Self, String> {
        protocol::require_parent_actor().map_err(|e| e.to_string())?;
        root().map_err(|e| e.to_string())?;
        let group_path = current_cgroup_parent().map_err(|e| e.to_string())?;
        if group_path
            != PathBuf::from(format!(
                "/sys/fs/cgroup/system.slice/{}",
                protocol::unit_name()
            ))
        {
            return Err("actual physical qualification unit/cgroup required".into());
        }
        let current = BoundProcess::capture(std::process::id()).map_err(|e| e.to_string())?;
        let manager = BoundProcess::capture(1).map_err(|e| e.to_string())?;
        let manager_exe = Tool::open("/usr/lib/systemd/systemd").map_err(|e| e.to_string())?;
        let executable = Tool::open(protocol::EXE).map_err(|e| e.to_string())?;
        applications
            .validate(128 * 1024 * 1024)
            .map_err(|e| e.to_string())?;
        if executable.identity[6] != applications.bytes || executable.sha != applications.sha256 {
            return Err(
                "working parent differs from the boot-admitted applications executable".into(),
            );
        }
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
            namespaces.push((
                name,
                current.open(name, false).map_err(|e| e.to_string())?,
                manager.open(name, false).map_err(|e| e.to_string())?,
            ));
        }
        let group = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open(&group_path)
            .map_err(|e| e.to_string())?;
        let group_pin = identity(&group).map_err(|e| e.to_string())?;
        let mut fs = std::mem::MaybeUninit::<libc::statfs>::uninit();
        // SAFETY: group is held and fs is correctly sized writable storage.
        if unsafe { libc::fstatfs(group.as_raw_fd(), fs.as_mut_ptr()) } != 0 {
            return Err(io::Error::last_os_error().to_string());
        }
        if unsafe { fs.assume_init() }.f_type != libc::CGROUP2_SUPER_MAGIC
            || group_pin[3..5] != [0, 0]
            || group_pin[2] & 0o022 != 0
            || crate::native_hardware_label::label(&group).map_err(|e| e.to_string())?
                != GROUP_LABEL
        {
            return Err("root-owned cgroup v2 qualification unit required".into());
        }
        let source_unit = SourceUnit::open().map_err(|e| e.to_string())?;
        let controls = CONTROL_NAMES
            .iter()
            .map(|n| Control::open(&group, n))
            .collect::<io::Result<Vec<_>>>()
            .map_err(|e| e.to_string())?;
        let events = Control::open(&group, c"memory.events").map_err(|e| e.to_string())?;
        let swap = Control::open(&group, c"memory.swap.current").map_err(|e| e.to_string())?;
        let pids_events = Control::open(&group, c"pids.events").map_err(|e| e.to_string())?;
        let memory_current = Control::open(&group, c"memory.current").map_err(|e| e.to_string())?;
        let query_end = end.min(Instant::now() + Duration::from_secs(15));
        let connection = Connection::open(query_end)?;
        let invocation = connection
            .bus
            .invocation(current.pidfd.as_fd(), query_end)
            .map_err(|e| e.to_string())?;
        let mut value = Self {
            current,
            manager,
            manager_exe,
            executable,
            namespaces,
            connection,
            invocation,
            properties: BTreeMap::new(),
            group_path,
            group,
            group_pin,
            controls,
            events,
            swap,
            pids_events,
            memory_current,
            profile: Cell::new(KernelProfile::Standard),
            source_unit,
            child_arguments: RefCell::new(None),
            end,
        };
        value.properties = value.query(end)?;
        value.boundary(None, end)?;
        Ok(value)
    }
    fn source_guard(&self) -> Result<(), String> {
        protocol::require_parent_actor().map_err(|e| e.to_string())?;
        root().map_err(|e| e.to_string())?;
        self.current.validate().map_err(|e| e.to_string())?;
        self.manager.validate().map_err(|e| e.to_string())?;
        self.manager_exe.guard().map_err(|e| e.to_string())?;
        self.executable.guard().map_err(|e| e.to_string())?;
        if self.current.identity.pid != std::process::id()
            || self.manager.identity.comm != "systemd"
            || identity(&self.manager.open("exe", false).map_err(|e| e.to_string())?)
                .map_err(|e| e.to_string())?
                != self.manager_exe.identity
            || identity(&self.current.open("exe", false).map_err(|e| e.to_string())?)
                .map_err(|e| e.to_string())?
                != self.executable.identity
            || cmdline(&self.current).map_err(|e| e.to_string())? != protocol::parent_argv()
        {
            return Err("physical qualifier or PID1 actual executable/argv changed".into());
        }
        for (name, current, manager) in &self.namespaces {
            if !super::super::same_file(current, manager).map_err(|e| e.to_string())?
                || !super::super::same_file(
                    current,
                    &self.current.open(name, false).map_err(|e| e.to_string())?,
                )
                .map_err(|e| e.to_string())?
                || !super::super::same_file(
                    manager,
                    &self.manager.open(name, false).map_err(|e| e.to_string())?,
                )
                .map_err(|e| e.to_string())?
            {
                return Err("physical qualifier host namespaces changed".into());
            }
        }
        self.source_unit.guard().map_err(|e| e.to_string())?;
        actual_affinity(OwnedLeafProfile::Gallery)?;
        self.connection.guard()?;
        if Instant::now() >= self.end {
            return Err("physical qualifier original deadline exhausted".into());
        }
        Ok(())
    }
    fn query(&self, deadline: Instant) -> Result<BTreeMap<String, String>, String> {
        self.source_guard()?;
        let until = self
            .end
            .min(deadline)
            .min(Instant::now() + Duration::from_secs(15));
        let invocation = self
            .connection
            .bus
            .invocation(self.current.pidfd.as_fd(), until)
            .map_err(|e| e.to_string())?;
        if invocation != self.invocation || invocation.unit != protocol::unit_name() {
            return Err("physical qualifier actual PIDFD unit generation differs".into());
        }
        let unit = self
            .connection
            .bus
            .properties(&invocation, bus::Interface::Unit, until)
            .map_err(|e| e.to_string())?;
        let service = self
            .connection
            .bus
            .properties(&invocation, bus::Interface::Service, until)
            .map_err(|e| e.to_string())?;
        let values =
            qualification_properties(&unit, &service, &invocation, self.current.identity.pid)?;
        if self
            .connection
            .bus
            .invocation(self.current.pidfd.as_fd(), until)
            .map_err(|e| e.to_string())?
            != invocation
        {
            return Err("physical qualifier invocation changed during manager read".into());
        }
        self.source_guard()?;
        if Instant::now() >= until {
            return Err("physical manager observation exhausted original request end".into());
        }
        Ok(values)
    }
    pub(crate) fn manager_start_ns(&self) -> Result<u64, String> {
        [
            "ExecMainStartTimestampMonotonic",
            "ExecStartCommandMonotonic",
        ]
        .iter()
        .map(|key| {
            self.properties
                .get(*key)
                .ok_or("manager start absent")?
                .parse::<u64>()
                .map_err(|_| "manager start invalid")
        })
        .collect::<Result<Vec<_>, _>>()?
        .into_iter()
        .min()
        .ok_or("manager starts absent")?
        .checked_mul(1000)
        .ok_or_else(|| "manager start overflow".into())
    }
    pub(crate) fn restrict_end(&mut self, end: Instant) -> Result<(), String> {
        if end > self.end || Instant::now() >= end {
            return Err("working owner cannot extend its original end".into());
        }
        self.end = end;
        Ok(())
    }
    pub(crate) fn bind_plan(&self, plan: &protocol::Plan, end: Instant) -> Result<(), String> {
        self.boundary(None, end)?;
        plan.guard().map_err(|e| e.to_string())?;
        let pin = plan.working_applications_pin().map_err(|e| e.to_string())?;
        if self.child_arguments.borrow().is_some()
            || self.executable.identity[6] != pin.bytes
            || self.executable.sha != pin.sha256
        {
            return Err(
                "working owner already has a plan or selected another applications input".into(),
            );
        }
        *self.child_arguments.borrow_mut() =
            Some(protocol::child_argv(&plan.path, &plan.digest).map_err(|e| e.to_string())?);
        Ok(())
    }
    pub(crate) fn executable(&self) -> &File {
        &self.executable.file
    }
    pub(crate) fn child_guard(&self, child: &BoundProcess) -> Result<(), String> {
        child.validate().map_err(|e| e.to_string())?;
        process_root(child).map_err(|e| e.to_string())?;
        process_mac(
            child,
            protocol::layout::WORKING_SUITE_ROLE,
            protocol::layout::WORKING_SUITE_PROFILE,
        )
        .map_err(|e| e.to_string())?;
        process_group(child, &self.group_path).map_err(|e| e.to_string())?;
        if cmdline(child).map_err(|e| e.to_string())?
            != *self
                .child_arguments
                .borrow()
                .as_ref()
                .ok_or("working owner has no retained source plan")?
            || identity(&child.open("exe", false).map_err(|e| e.to_string())?)
                .map_err(|e| e.to_string())?
                != self.executable.identity
        {
            return Err("physical child is not this installed same-exec producer".into());
        }
        Ok(())
    }
    pub(crate) fn boundary(
        &self,
        child: Option<&BoundProcess>,
        deadline: Instant,
    ) -> Result<(), String> {
        if self.query(deadline)? != self.properties {
            return Err("physical qualifier manager properties changed".into());
        }
        self.kernel_guard(child, false)?;
        if Instant::now() >= self.end.min(deadline) {
            return Err("physical boundary exhausted original end".into());
        }
        Ok(())
    }
    pub(crate) fn preparation_boundary(&self, deadline: Instant) -> Result<(), String> {
        if self.query(deadline)? != self.properties {
            return Err("working preparation manager changed".into());
        }
        self.kernel_guard(None, true)?;
        if Instant::now() >= self.end.min(deadline) {
            return Err("working preparation end exhausted".into());
        }
        Ok(())
    }
    pub(crate) fn probe_parent(&self, deadline: Instant) -> Result<(&Path, &File), String> {
        self.boundary(None, deadline)?;
        Ok((&self.group_path, &self.group))
    }
    /// The same actual unit and cgroup while a bounded child is in flight.
    /// All ordinary case and completion boundaries still require full retirement.
    pub(crate) fn watchdog_boundary(
        &self,
        child: Option<&BoundProcess>,
        preparation: bool,
        end: Instant,
    ) -> Result<(), String> {
        if self.query(end)? != self.properties {
            return Err("working watchdog manager properties changed".into());
        }
        self.kernel_guard_mode(child, preparation, child.is_some())?;
        if Instant::now() >= self.end.min(end) {
            return Err("working watchdog original owner end exhausted".into());
        }
        Ok(())
    }
    fn kernel_guard(&self, child: Option<&BoundProcess>, preparation: bool) -> Result<(), String> {
        self.kernel_guard_mode(child, preparation, false)
    }
    fn kernel_guard_mode(
        &self,
        child: Option<&BoundProcess>,
        preparation: bool,
        live_suite: bool,
    ) -> Result<(), String> {
        if current_cgroup_parent().map_err(|e| e.to_string())? != self.group_path {
            return Err("physical qualifier moved cgroup".into());
        }
        let named = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open(&self.group_path)
            .map_err(|e| e.to_string())?;
        if identity(&named).map_err(|e| e.to_string())?[..5] != self.group_pin[..5]
            || identity(&self.group).map_err(|e| e.to_string())?[..5] != self.group_pin[..5]
            || crate::native_hardware_label::label(&named).map_err(|e| e.to_string())?
                != GROUP_LABEL
            || crate::native_hardware_label::label(&self.group).map_err(|e| e.to_string())?
                != GROUP_LABEL
        {
            return Err("physical qualifier cgroup replaced".into());
        }
        let mut expected = vec![self.current.identity.pid];
        if let Some(child) = child {
            self.child_guard(child)?;
            expected.push(child.identity.pid);
        }
        expected.sort();
        let membership = super::super::open_at(
            self.group.as_raw_fd(),
            c"cgroup.procs",
            libc::O_RDONLY | libc::O_NOFOLLOW,
        )
        .map_err(|e| e.to_string())?;
        if crate::native_hardware_label::label(&membership).map_err(|e| e.to_string())?
            != MEMBERSHIP_LABEL
        {
            return Err("working owner membership is not its exact singleton cgroup label".into());
        }
        let procs = super::super::bounded_text(membership, 8192).map_err(|e| e.to_string())?;
        let mut actual = procs
            .lines()
            .map(|s| s.parse::<u32>())
            .collect::<std::result::Result<Vec<_>, _>>()
            .map_err(|_| "physical cgroup process list invalid")?;
        actual.sort();
        if actual != expected {
            return Err("physical owner has an unretired direct process".into());
        }
        if preparation {
            super::super::working_owned_probe::verify_preparation_children(
                &self.group_path,
                &self.group,
            )
            .map_err(|e| e.to_string())?;
        } else if live_suite {
            super::super::working_owned_probe::verify_live_suite_children(
                &self.group_path,
                &self.group,
                child.ok_or("actual working suite child absent")?,
            )
            .map_err(|e| e.to_string())?;
        } else if fs::read_dir(&self.group_path)
            .map_err(|e| e.to_string())?
            .any(|r| r.map_or(true, |e| e.file_type().map_or(true, |t| t.is_dir())))
        {
            return Err("physical case boundary has an unretired nested cgroup".into());
        }
        for (control, expected) in self.controls.iter().zip(self.profile.get().values()) {
            if control.text(&self.group).map_err(|e| e.to_string())? != expected {
                return Err("physical qualifier actual kernel profile changed".into());
            }
        }
        let events = self.events.text(&self.group).map_err(|e| e.to_string())?;
        for key in ["max", "oom", "oom_kill", "oom_group_kill"] {
            let rows: Vec<_> = events
                .lines()
                .filter_map(|l| l.strip_prefix(&format!("{key} ")))
                .collect();
            if rows != ["0"] {
                return Err(format!("physical qualifier memory event {key}"));
            }
        }
        if self.swap.text(&self.group).map_err(|e| e.to_string())? != "0"
            || self
                .pids_events
                .text(&self.group)
                .map_err(|e| e.to_string())?
                != "max 0"
        {
            return Err("physical qualifier used swap or exhausted its process limit".into());
        }
        Ok(())
    }
    pub(crate) fn switch(
        &self,
        profile: KernelProfile,
        child: &BoundProcess,
        deadline: Instant,
    ) -> Result<(), String> {
        self.switch_profile(profile, Some(child), deadline)
    }
    pub(crate) fn preparation_profile(
        &self,
        profile: KernelProfile,
        deadline: Instant,
    ) -> Result<(), String> {
        self.switch_profile(profile, None, deadline)
    }
    fn switch_profile(
        &self,
        profile: KernelProfile,
        child: Option<&BoundProcess>,
        deadline: Instant,
    ) -> Result<(), String> {
        self.boundary(child, deadline)?;
        if self.profile.get() == profile {
            return Ok(());
        }
        let current = self
            .memory_current
            .text(&self.group)
            .map_err(|e| e.to_string())?
            .parse::<u64>()
            .map_err(|_| "physical memory.current invalid")?;
        if profile != KernelProfile::Standard && current >= 536_870_912 - 32 * 1024 * 1024 {
            return Err("working owner does not fit its next original 512 MiB scope".into());
        }
        let values = profile.values();
        for i in [0, 1] {
            self.controls[i]
                .write(&self.group, values[i])
                .map_err(|e| e.to_string())?;
        }
        self.profile.set(profile);
        self.kernel_guard(child, false)?;
        if Instant::now() >= self.end.min(deadline) {
            return Err("physical profile acknowledgement expired".into());
        }
        Ok(())
    }
    pub(crate) fn observation(&self) -> Value {
        json!({"schema":"droidloom.physical-qualification-parent.v1",
            "unit":self.invocation.unit,"invocation":self.invocation.id.iter().map(|b| format!("{b:02x}")).collect::<String>(),
            "parent_pid":self.current.identity.pid,"parent_start_ticks":self.current.identity.start_ticks,
            "properties":self.properties,"cgroup":self.group_path,"cgroup_identity":self.group_pin,
            "normal_unit":{"path":self.source_unit.path,"f9":self.source_unit.pin,
                "sha256":format!("{:x}",Sha256::digest(protocol::UNIT_SOURCE.as_bytes()))},
            "normal_executable":{"path":self.executable.path,"f9":self.executable.identity,"sha256":self.executable.sha},
            "profile":format!("{:?}",self.profile.get()),"all_child_processes_retired":true,
            "parent_unit_retirement_requires_external_readback":true})
    }
}

fn qualification_properties(
    unit: &bus::Properties,
    service: &bus::Properties,
    invocation: &bus::Invocation,
    pid: u32,
) -> Result<BTreeMap<String, String>, String> {
    use bus::Value as V;
    let expected_unit = protocol::unit_name().to_owned();
    if invocation.unit != expected_unit
        || unit.get("InvocationID") != Some(&V::Bytes(invocation.id.to_vec()))
        || unit.get("Transient") != Some(&V::Boolean(false))
        || unit.get("NeedDaemonReload") != Some(&V::Boolean(false))
        || unit.get("DropInPaths") != Some(&V::Strings(Vec::new()))
        || ["OnSuccess", "OnFailure"].iter().any(|key| {
            unit.get(*key)
                != Some(&V::Strings(vec![
                    crate::native_working_contract::RETURN_UNIT.into(),
                ]))
        })
        || ["OnSuccessJobMode", "OnFailureJobMode"]
            .iter()
            .any(|key| unit.get(*key) != Some(&V::Text("replace".into())))
    {
        return Err("fixed installed physical unit or invocation metadata differs".into());
    }
    let mut values = BTreeMap::new();
    for (key, want) in [
        ("Id", expected_unit.as_str()),
        ("LoadState", "loaded"),
        ("ActiveState", "active"),
        ("SubState", "running"),
        ("FragmentPath", protocol::UNIT_FRAGMENT),
    ] {
        if unit.get(key) != Some(&V::Text(want.into())) {
            return Err(format!("physical unit {key} differs"));
        }
        values.insert(key.into(), want.into());
    }
    for (key, want) in [
        ("Type", "exec"),
        ("User", "root"),
        ("Group", "root"),
        ("Restart", "no"),
        ("KillMode", "control-group"),
        ("TimeoutStopFailureMode", "terminate"),
    ] {
        if service.get(key) != Some(&V::Text(want.into())) {
            return Err(format!("physical service {key} differs"));
        }
        values.insert(key.into(), want.into());
    }
    let cg = format!("/system.slice/{expected_unit}");
    if service.get("MainPID") != Some(&V::U32(pid))
        || service.get("ControlGroup") != Some(&V::Text(cg.clone()))
        || service.get("KillSignal") != Some(&V::I32(15))
        || service.get("FinalKillSignal") != Some(&V::I32(9))
        || service.get("SendSIGKILL") != Some(&V::Boolean(true))
        || !matches!(service.get("CPUAffinity"),Some(V::Bytes(bytes)) if affinity(bytes)==[20,21])
    {
        return Err(
            "physical service actual process, affinity or retirement controls differ".into(),
        );
    }
    for (key, want) in [
        ("MemoryMax", 2_147_483_648),
        ("MemorySwapMax", 0),
        ("TasksMax", 64),
        ("LimitCORE", 0),
        ("CPUQuotaPerSecUSec", 2_000_000),
        ("CPUQuotaPeriodUSec", 100_000),
        ("RuntimeMaxUSec", protocol::SERVICE_SECONDS * 1_000_000),
        ("TimeoutStopUSec", protocol::RETIREMENT_SECONDS * 1_000_000),
    ] {
        if service.get(key) != Some(&V::U64(want)) {
            return Err(format!("physical service source budget {key} differs"));
        }
        values.insert(key.into(), want.to_string());
    }
    let start = match service.get("ExecMainStartTimestampMonotonic") {
        Some(V::U64(n)) if *n > 0 => *n,
        _ => return Err("actual physical unit start instant required".into()),
    };
    values.insert("ExecMainStartTimestampMonotonic".into(), start.to_string());
    values.insert(
        "InvocationID".into(),
        invocation
            .id
            .iter()
            .map(|b| format!("{b:02x}"))
            .collect::<String>(),
    );
    values.insert("MainPID".into(), pid.to_string());
    values.insert("ControlGroup".into(), cg);
    for key in [
        "ExecConditionEx",
        "ExecStartPreEx",
        "ExecStartPostEx",
        "ExecReloadEx",
        "ExecStopEx",
        "ExecStopPostEx",
    ] {
        if service.get(key) != Some(&V::Commands(Vec::new())) {
            return Err(format!("physical unit {key} must be empty"));
        }
    }
    let Some(V::Commands(commands)) = service.get("ExecStartEx") else {
        return Err("physical ExecStartEx absent".into());
    };
    let [command] = commands.as_slice() else {
        return Err("one physical ExecStart required".into());
    };
    if command.path != protocol::EXE
        || command.arguments != protocol::parent_argv()
        || !command.flags.is_empty()
        || command.pid != pid
        || command.started.iter().any(|n| *n == 0)
        || command.exited != [0, 0]
        || command.code != 0
        || command.status != 0
    {
        return Err("physical qualifier exact normal command differs".into());
    }
    values.insert(
        "ExecStartCommandRealtime".into(),
        command.started[0].to_string(),
    );
    values.insert(
        "ExecStartCommandMonotonic".into(),
        command.started[1].to_string(),
    );
    Ok(values)
}

#[cfg(test)]
mod tests {
    use super::*;

    struct TestDirectory(PathBuf);
    impl TestDirectory {
        fn new() -> Self {
            let nonce = std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos();
            let path = std::env::temp_dir().join(format!(
                "droidloom-physical-owner-{}-{nonce}",
                std::process::id()
            ));
            fs::create_dir(&path).unwrap();
            Self(path)
        }
    }
    impl Drop for TestDirectory {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.0);
        }
    }
    fn source_fixture(root: &TestDirectory) -> SourceUnit {
        // Exercise retained-object readback without impersonating the root-only
        // installed constructor or writing any installed source path.
        let parent = root.0.join("unit-parent");
        fs::create_dir(&parent).unwrap();
        let path = parent.join("unit.service");
        fs::write(&path, protocol::UNIT_SOURCE).unwrap();
        let file = File::open(&path).unwrap();
        let pin = identity(&file).unwrap();
        let directory = File::open(&parent).unwrap();
        let directory_pin = identity(&directory).unwrap();
        SourceUnit {
            path,
            file,
            pin,
            parents: vec![(parent, directory, directory_pin)],
        }
    }
    #[test]
    fn physical_qualification_source_unit_rejects_same_bytes_on_a_replacement_inode() {
        let root = TestDirectory::new();
        let unit = source_fixture(&root);
        unit.guard().unwrap();
        fs::rename(&unit.path, root.0.join("retained.service")).unwrap();
        fs::write(&unit.path, protocol::UNIT_SOURCE).unwrap();
        assert!(unit.guard().is_err());
    }
    #[test]
    fn physical_qualification_source_unit_retains_named_parent_identity() {
        let root = TestDirectory::new();
        let unit = source_fixture(&root);
        unit.guard_parents().unwrap();
        let parent = &unit.parents[0].0;
        fs::rename(parent, root.0.join("retained-parent")).unwrap();
        fs::create_dir(parent).unwrap();
        assert!(unit.guard_parents().is_err());
    }
    #[test]
    fn physical_qualification_read_only_controls_reject_writes_before_effects() {
        let root = TestDirectory::new();
        let group = File::open(&root.0).unwrap();
        for name in [
            c"memory.swap.max",
            c"pids.max",
            c"memory.events",
            c"memory.swap.current",
            c"pids.events",
            c"memory.current",
        ] {
            let path = root.0.join(name.to_str().unwrap());
            fs::write(&path, "64").unwrap();
            // Even an accidentally writable retained FD must not turn a
            // read-only observation into an admitted control write.
            let file = OpenOptions::new()
                .read(true)
                .write(true)
                .open(&path)
                .unwrap();
            let pin = identity(&file).unwrap();
            let access = ControlAccess::for_name(name).unwrap();
            assert_eq!(access.flags() & libc::O_ACCMODE, libc::O_RDONLY);
            let mut control = Control {
                name,
                file,
                pin,
                access,
            };
            assert!(control.write(&group, "65").is_err());
            assert_eq!(fs::read_to_string(&path).unwrap(), "64");
        }
        for name in [
            c"cgroup.procs",
            c"cgroup.threads",
            c"cgroup.kill",
            c"cgroup.subtree_control",
            c"../cpu.max",
            c"cpu.max.burst",
            c"memory.high",
        ] {
            assert!(ControlAccess::for_name(name).is_err(), "{name:?}");
        }
    }

    fn fixture() -> (bus::Properties, bus::Properties, bus::Invocation) {
        use bus::Value as V;
        let name = protocol::unit_name().to_owned();
        let invocation = bus::Invocation {
            path: "/org/freedesktop/systemd1/unit/example".into(),
            unit: name.clone(),
            id: [7; 16],
        };
        let mut unit = bus::Properties::new();
        let mut service = bus::Properties::new();
        for (key, value) in [
            ("Id", name.as_str()),
            ("LoadState", "loaded"),
            ("ActiveState", "active"),
            ("SubState", "running"),
            ("FragmentPath", protocol::UNIT_FRAGMENT),
        ] {
            unit.insert(key.into(), V::Text(value.into()));
        }
        unit.insert("InvocationID".into(), V::Bytes(vec![7; 16]));
        unit.insert("Transient".into(), V::Boolean(false));
        unit.insert("NeedDaemonReload".into(), V::Boolean(false));
        unit.insert("DropInPaths".into(), V::Strings(vec![]));
        for name in ["OnSuccess", "OnFailure"] {
            unit.insert(
                name.into(),
                V::Strings(vec![crate::native_working_contract::RETURN_UNIT.into()]),
            );
        }
        for name in ["OnSuccessJobMode", "OnFailureJobMode"] {
            unit.insert(name.into(), V::Text("replace".into()));
        }
        for (key, value) in [
            ("Type", "exec"),
            ("User", "root"),
            ("Group", "root"),
            ("Restart", "no"),
            ("KillMode", "control-group"),
            ("TimeoutStopFailureMode", "terminate"),
        ] {
            service.insert(key.into(), V::Text(value.into()));
        }
        service.insert("MainPID".into(), V::U32(1234));
        service.insert(
            "ControlGroup".into(),
            V::Text(format!("/system.slice/{name}")),
        );
        service.insert("KillSignal".into(), V::I32(15));
        service.insert("FinalKillSignal".into(), V::I32(9));
        service.insert("SendSIGKILL".into(), V::Boolean(true));
        // Normal sd-bus CPU affinity can contain trailing zero bytes.
        let mut cpus = vec![0; 128];
        cpus[2] = 0x30;
        service.insert("CPUAffinity".into(), V::Bytes(cpus));
        for (key, value) in [
            ("MemoryMax", 2_147_483_648),
            ("MemorySwapMax", 0),
            ("TasksMax", 64),
            ("LimitCORE", 0),
            ("CPUQuotaPerSecUSec", 2_000_000),
            ("CPUQuotaPeriodUSec", 100_000),
            ("RuntimeMaxUSec", protocol::SERVICE_SECONDS * 1_000_000),
            ("TimeoutStopUSec", protocol::RETIREMENT_SECONDS * 1_000_000),
            ("ExecMainStartTimestampMonotonic", 100),
        ] {
            service.insert(key.into(), V::U64(value));
        }
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
                started: [5, 99],
                exited: [0, 0],
                pid: 1234,
                code: 0,
                status: 0,
            }]),
        );
        (unit, service, invocation)
    }
    #[test]
    fn physical_qualification_parent_requires_fixed_actual_command_and_invocation() {
        use bus::Value as V;
        let (unit, service, invocation) = fixture();
        assert!(qualification_properties(&unit, &service, &invocation, 1234).is_ok());
        let mut wrong = unit.clone();
        wrong.insert("InvocationID".into(), V::Bytes(vec![8; 16]));
        assert!(qualification_properties(&wrong, &service, &invocation, 1234).is_err());
        let mut wrong = service.clone();
        let V::Commands(rows) = wrong.get_mut("ExecStartEx").unwrap() else {
            panic!()
        };
        rows[0].arguments[1] = "--physical-application-plan".into();
        assert!(qualification_properties(&unit, &wrong, &invocation, 1234).is_err());
        assert!(qualification_properties(&unit, &service, &invocation, 1235).is_err());
    }
    #[test]
    fn physical_qualification_rejects_legacy_template_and_caller_plan_arguments() {
        use bus::Value as V;
        let (unit, service, invocation) = fixture();
        let mut wrong = unit.clone();
        wrong.insert(
            "FragmentPath".into(),
            V::Text("/usr/lib/systemd/system/droidloom-physical-qualification@.service".into()),
        );
        assert!(qualification_properties(&wrong, &service, &invocation, 1234).is_err());
        let mut wrong = service.clone();
        let V::Commands(rows) = wrong.get_mut("ExecStartEx").unwrap() else {
            panic!()
        };
        rows[0].arguments = vec![
            protocol::EXE.into(),
            "--owned-physical-plan-sha256".into(),
            "a".repeat(64),
        ];
        assert!(qualification_properties(&unit, &wrong, &invocation, 1234).is_err());
        assert_eq!(
            protocol::parent_argv(),
            [protocol::EXE, "--owned-working-qualification"]
        );
    }
    #[test]
    fn physical_qualification_rejects_extra_commands_dropins_and_raised_budget() {
        use bus::Value as V;
        let (unit, service, invocation) = fixture();
        for (key, value) in [
            ("MemoryMax", 2_147_483_649),
            ("MemorySwapMax", 1),
            ("TasksMax", 65),
            ("CPUQuotaPerSecUSec", 2_000_001),
            (
                "RuntimeMaxUSec",
                (protocol::SERVICE_SECONDS + 1) * 1_000_000,
            ),
        ] {
            let mut wrong = service.clone();
            wrong.insert(key.into(), V::U64(value));
            assert!(
                qualification_properties(&unit, &wrong, &invocation, 1234).is_err(),
                "{key}"
            );
        }
        let mut wrong = unit.clone();
        wrong.insert(
            "DropInPaths".into(),
            V::Strings(vec!["/tmp/override".into()]),
        );
        assert!(qualification_properties(&wrong, &service, &invocation, 1234).is_err());
        let mut wrong = service.clone();
        wrong.insert("ExecStartPostEx".into(), service["ExecStartEx"].clone());
        assert!(qualification_properties(&unit, &wrong, &invocation, 1234).is_err());
    }
    #[test]
    fn physical_qualification_rejects_missing_or_foreign_independent_return() {
        use bus::Value as V;
        let (unit, service, invocation) = fixture();
        for key in ["OnSuccess", "OnFailure"] {
            for destinations in [
                vec![],
                vec!["caller.service".into()],
                vec![
                    crate::native_working_contract::RETURN_UNIT.into(),
                    "caller.service".into(),
                ],
            ] {
                let mut wrong = unit.clone();
                wrong.insert(key.into(), V::Strings(destinations));
                assert!(qualification_properties(&wrong, &service, &invocation, 1234).is_err());
            }
        }
        for key in ["OnSuccessJobMode", "OnFailureJobMode"] {
            let mut wrong = unit.clone();
            wrong.insert(key.into(), V::Text("ignore-dependencies".into()));
            assert!(qualification_properties(&wrong, &service, &invocation, 1234).is_err());
        }
    }
    #[test]
    fn physical_qualification_profiles_preserve_original_exact_memory_and_quota() {
        assert_eq!(
            KernelProfile::Calendar.values(),
            ["50000 100000", "536870912", "0", "64"]
        );
        assert_eq!(
            KernelProfile::Standard.values(),
            ["200000 100000", "2147483648", "0", "64"]
        );
    }
}
