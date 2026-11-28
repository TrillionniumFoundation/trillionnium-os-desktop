//! Source-owned parent of the separately bounded physical qualification suite.
//! Private child of application_leaf_unit: reuse the unchanged authenticated
//! PID1 bus and held executable/namespace machinery, not a second trust model.
use super::super::physical_qualification_channel as protocol;
use super::*;
use std::io::{Read, Write};
use crate::native_working_contract as working;
#[path = "working_qualification_peer.rs"]
pub(crate) mod working_peer;

// Source-selected service modes. The working singleton is admitted from its
// actual boot configuration before any dynamic plan exists; a template hash
// cannot select or authorize it.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum OwnerKind {
    PhysicalTemplate,
    WorkingSingleton,
}
impl OwnerKind {
    fn unit(self, digest: &str) -> io::Result<String> {
        match self {
            Self::PhysicalTemplate => protocol::unit_name(digest),
            Self::WorkingSingleton => Ok(working::PARENT_UNIT.into()),
        }
    }
    fn fragment(self) -> &'static str {
        match self {
            Self::PhysicalTemplate => protocol::TEMPLATE_NAME,
            Self::WorkingSingleton => working::PARENT_UNIT,
        }
    }
    fn source(self) -> &'static str {
        match self {
            Self::PhysicalTemplate => protocol::TEMPLATE,
            Self::WorkingSingleton => include_str!("../../../packaging/systemd/system/droidloom-working-qualification.service"),
        }
    }
    fn argv(self, digest: &str) -> Vec<String> {
        match self {
            Self::PhysicalTemplate => protocol::parent_argv(digest),
            Self::WorkingSingleton => vec![protocol::EXE.into(), working::PARENT_MODE.into()],
        }
    }
    fn service_seconds(self) -> u64 {
        match self {
            Self::PhysicalTemplate => protocol::SERVICE_SECONDS,
            Self::WorkingSingleton => working::WorkingSchedule::selected().service_runtime_seconds,
        }
    }
    fn authorization_seconds(self) -> u64 {
        match self {
            Self::PhysicalTemplate => protocol::SUITE_SECONDS,
            Self::WorkingSingleton => working::WorkingSchedule::selected().whole_suite_seconds,
        }
    }
}

fn child_arguments(kind: OwnerKind, digest: &str) -> io::Result<Vec<String>> {
    if kind == OwnerKind::WorkingSingleton && digest.is_empty() {
        return Ok(vec![protocol::EXE.into(), "--working-qualification-prepare".into()]);
    }
    protocol::child_argv(digest)
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) enum KernelProfile {
    Standard,
    Calendar,
}
impl KernelProfile {
    fn values(self) -> [&'static str; 4] {
        [
            if self == Self::Calendar {
                "50000 100000"
            } else {
                "200000 100000"
            },
            if self == Self::Calendar {
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

fn root() -> io::Result<()> {
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
    digest: String,
    kind: OwnerKind,
    namespaces: Vec<(String, File, File)>,
}
impl ChildPeer {
    pub(crate) fn capture(digest: &str) -> io::Result<Self> {
        if !protocol::digest_ok(digest) {
            return Err(invalid("physical child requires the exact normal plan digest"));
        }
        Self::capture_actual(digest)
    }
    pub(crate) fn capture_preparation() -> io::Result<Self> {
        Self::capture_actual("")
    }
    fn capture_actual(digest: &str) -> io::Result<Self> {
        root()?;
        // SAFETY: getppid returns the current actual parent, never a caller PID.
        let parent_pid = unsafe { libc::getppid() };
        if parent_pid <= 1 {
            return Err(invalid("actual physical qualification parent required"));
        }
        let current = BoundProcess::capture(std::process::id())?;
        let parent = BoundProcess::capture(parent_pid as u32)?;
        let executable = Tool::open(protocol::EXE)?;
        let group = current_cgroup_parent()?;
        let working_group = PathBuf::from(format!(
            "/sys/fs/cgroup/system.slice/{}", working::PARENT_UNIT));
        let kind = if group == working_group {
            OwnerKind::WorkingSingleton
        } else if !digest.is_empty() && group == PathBuf::from(format!(
            "/sys/fs/cgroup/system.slice/{}", protocol::unit_name(digest)?)) {
            OwnerKind::PhysicalTemplate
        } else {
            return Err(invalid("child is outside its fixed actual normal owner"));
        };
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
            digest: digest.into(),
            kind,
            namespaces,
        };
        result.guard()?;
        Ok(result)
    }
    pub(crate) fn parent_pid(&self) -> u32 {
        self.parent.identity.pid
    }
    pub(crate) fn guard(&self) -> io::Result<()> {
        root()?;
        self.current.validate()?;
        self.parent.validate()?;
        if std::process::id() != self.current.identity.pid
            || unsafe { libc::getppid() } as u32 != self.parent.identity.pid
            || cmdline(&self.current)? != child_arguments(self.kind, &self.digest)?
            || cmdline(&self.parent)? != self.kind.argv(&self.digest)
        {
            return Err(invalid(
                "physical private channel no longer has its exact same-exec parent",
            ));
        }
        self.executable.guard()?;
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
}
impl Control {
    fn open(group: &File, name: &'static CStr, write: bool) -> io::Result<Self> {
        let file = super::super::open_at(
            group.as_raw_fd(),
            name,
            if write {
                libc::O_RDWR | libc::O_NOFOLLOW
            } else {
                libc::O_RDONLY | libc::O_NOFOLLOW
            },
        )?;
        let pin = identity(&file)?;
        if pin[3..5] != [0, 0] || pin[2] & 0o022 != 0 {
            return Err(invalid("root owned cgroup control required"));
        }
        Ok(Self { name, file, pin })
    }
    fn text(&self, group: &File) -> io::Result<String> {
        let named = super::super::open_at(
            group.as_raw_fd(),
            self.name,
            libc::O_RDONLY | libc::O_NOFOLLOW,
        )?;
        if identity(&self.file)?[..6] != self.pin[..6] || identity(&named)?[..6] != self.pin[..6] {
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
    fn write(&mut self, group: &File, value: &str) -> io::Result<()> {
        self.text(group)?;
        // cgroup pseudo-files are single-command controls, not appendable data.
        let n = self.file.write_at(value.as_bytes(), 0)?;
        if n != value.len() || self.text(group)? != value {
            return Err(invalid("physical resource write/readback differs"));
        }
        Ok(())
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
    profile: KernelProfile,
    template: File,
    template_pin: [u64; 9],
    digest: String,
    kind: OwnerKind,
    end: Instant,
}
impl UnitOwner {
    pub(crate) fn capture(digest: &str, end: Instant) -> Result<Self, String> {
        Self::capture_kind(digest, end, OwnerKind::PhysicalTemplate)
    }
    pub(crate) fn capture_working(end: Instant) -> Result<Self, String> {
        Self::capture_kind("", end, OwnerKind::WorkingSingleton)
    }
    fn capture_kind(digest: &str, end: Instant, kind: OwnerKind) -> Result<Self, String> {
        root().map_err(|e| e.to_string())?;
        let group_path = current_cgroup_parent().map_err(|e| e.to_string())?;
        if group_path
            != PathBuf::from(format!(
                "/sys/fs/cgroup/system.slice/{}",
                kind.unit(digest).map_err(|e| e.to_string())?
            ))
        {
            return Err("actual physical qualification unit/cgroup required".into());
        }
        let current = BoundProcess::capture(std::process::id()).map_err(|e| e.to_string())?;
        let manager = BoundProcess::capture(1).map_err(|e| e.to_string())?;
        let manager_exe = Tool::open("/usr/lib/systemd/systemd").map_err(|e| e.to_string())?;
        let executable = Tool::open(protocol::EXE).map_err(|e| e.to_string())?;
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
        {
            return Err("root-owned cgroup v2 qualification unit required".into());
        }
        let template_path = format!("/usr/lib/systemd/system/{}", kind.fragment());
        // Parent paths are canonical and root-owned; retain their normal source
        // unit via a held regular FD as well as the manager's FragmentPath.
        let path = Path::new(&template_path);
        if path.canonicalize().map_err(|e| e.to_string())? != path {
            return Err("physical unit template alias".into());
        }
        for parent in path.parent().ok_or("unit parent absent")?.ancestors() {
            let m = fs::symlink_metadata(parent).map_err(|e| e.to_string())?;
            if !m.is_dir() || m.uid() != 0 || m.gid() != 0 || m.mode() & 0o022 != 0 {
                return Err("physical unit template root parent required".into());
            }
        }
        let template = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open(path)
            .map_err(|e| e.to_string())?;
        let template_pin = identity(&template).map_err(|e| e.to_string())?;
        if template_pin[2] & 0o170000 != 0o100000
            || template_pin[2] & 0o6022 != 0
            || template_pin[3..6] != [0, 0, 1]
            || template_pin[6] != kind.source().len() as u64
        {
            return Err("normal physical unit template metadata differs".into());
        }
        let controls = CONTROL_NAMES
            .iter()
            .enumerate()
            .map(|(index, n)| Control::open(&group, n, index < 2))
            .collect::<io::Result<Vec<_>>>()
            .map_err(|e| e.to_string())?;
        let events = Control::open(&group, c"memory.events", false).map_err(|e| e.to_string())?;
        let swap =
            Control::open(&group, c"memory.swap.current", false).map_err(|e| e.to_string())?;
        let pids_events =
            Control::open(&group, c"pids.events", false).map_err(|e| e.to_string())?;
        let memory_current =
            Control::open(&group, c"memory.current", false).map_err(|e| e.to_string())?;
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
            profile: KernelProfile::Standard,
            template,
            template_pin,
            digest: digest.into(),
            kind,
            end,
        };
        value.properties = value.query(end)?;
        value.boundary(None, end)?;
        Ok(value)
    }
    fn source_guard(&self) -> Result<(), String> {
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
            || cmdline(&self.current).map_err(|e| e.to_string())?
                != self.kind.argv(&self.digest)
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
        let mut bytes = vec![0; self.kind.source().len()];
        self.template
            .read_exact_at(&mut bytes, 0)
            .map_err(|e| e.to_string())?;
        let named = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open(format!(
                "/usr/lib/systemd/system/{}",
                self.kind.fragment()
            ))
            .map_err(|e| e.to_string())?;
        if bytes != self.kind.source().as_bytes()
            || identity(&self.template).map_err(|e| e.to_string())? != self.template_pin
            || identity(&named).map_err(|e| e.to_string())? != self.template_pin
        {
            return Err("physical qualifier normal unit template changed".into());
        }
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
        if invocation != self.invocation
            || invocation.unit != self.kind.unit(&self.digest).map_err(|e| e.to_string())?
        {
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
        let values = owner_properties(
            &unit,
            &service,
            &invocation,
            self.current.identity.pid,
            &self.digest,
            self.kind,
        )?;
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
    /// Local held-resource check for the working owner's short event-loop
    /// iterations. The full actual PID1 observation remains mandatory before
    /// feeding the watchdog, switching profiles or accepting a boundary.
    pub(crate) fn local_guard(&self, child: Option<&BoundProcess>, deadline: Instant) -> Result<(), String> {
        self.source_guard()?;
        self.kernel_owner_guard()?;
        if let Some(child) = child { self.child_guard(child)?; }
        if Instant::now() >= self.end.min(deadline) {
            return Err("working local owner exhausted its original end".into());
        }
        Ok(())
    }
    pub(crate) fn working_identity(&self) -> Result<super::super::working_qualification::WorkingUnitIdentity, String> {
        if self.kind != OwnerKind::WorkingSingleton {
            return Err("working source identity requires the actual singleton".into());
        }
        self.source_guard()?;
        Ok(super::super::working_qualification::WorkingUnitIdentity {
            unit: self.invocation.unit.clone(),
            invocation: self.invocation.id.iter().map(|b| format!("{b:02x}")).collect(),
            parent_pid: self.current.identity.pid,
            parent_start_ticks: self.current.identity.start_ticks,
            cgroup: self.group_path.to_str().ok_or("working cgroup is not UTF-8")?.into(),
            cgroup_identity: self.group_pin[..5].try_into().map_err(|_| "working cgroup identity")?,
            owner_start_monotonic_ns: self.manager_start_ns()?,
        })
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
    pub(crate) fn manager_deadline_ns(&self) -> Result<u64, String> {
        self.manager_start_ns()?
            .checked_add(self.kind.authorization_seconds() * 1_000_000_000)
            .ok_or_else(|| "manager deadline overflow".into())
    }
    pub(crate) fn bind_working_plan(&mut self, digest: &str, end: Instant) -> Result<(), String> {
        if self.kind != OwnerKind::WorkingSingleton || !self.digest.is_empty()
            || !protocol::digest_ok(digest) || end > self.end {
            return Err("working plan may bind once inside its original actual owner end".into());
        }
        self.boundary(None, end)?;
        self.digest = digest.into();
        self.end = end;
        Ok(())
    }
    pub(crate) fn live_guard(&self, child: Option<&BoundProcess>, deadline: Instant) -> Result<(), String> {
        if self.query(deadline)? != self.properties {
            return Err("working live owner manager properties changed".into());
        }
        self.kernel_owner_guard()?;
        if let Some(child) = child { self.child_guard(child)?; }
        if Instant::now() >= self.end.min(deadline) {
            return Err("working live owner exhausted its original end".into());
        }
        // This deliberately does not claim nested children retired. Only the
        // unchanged strict boundary() can authorize the next case or Complete.
        Ok(())
    }
    pub(crate) fn executable(&self) -> &File {
        &self.executable.file
    }
    pub(crate) fn child_guard(&self, child: &BoundProcess) -> Result<(), String> {
        child.validate().map_err(|e| e.to_string())?;
        process_root(child).map_err(|e| e.to_string())?;
        process_group(child, &self.group_path).map_err(|e| e.to_string())?;
        if cmdline(child).map_err(|e| e.to_string())?
            != child_arguments(self.kind, &self.digest).map_err(|e| e.to_string())?
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
        self.kernel_guard(child)?;
        if Instant::now() >= self.end.min(deadline) {
            return Err("physical boundary exhausted original end".into());
        }
        Ok(())
    }
    fn kernel_owner_guard(&self) -> Result<(), String> {
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
        {
            return Err("physical qualifier cgroup replaced".into());
        }
        for (control, expected) in self.controls.iter().zip(self.profile.values()) {
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
    fn kernel_guard(&self, child: Option<&BoundProcess>) -> Result<(), String> {
        self.kernel_owner_guard()?;
        let mut expected = vec![self.current.identity.pid];
        if let Some(child) = child {
            self.child_guard(child)?;
            expected.push(child.identity.pid);
        }
        expected.sort();
        let procs = super::super::bounded_text(
            super::super::open_at(
                self.group.as_raw_fd(),
                c"cgroup.procs",
                libc::O_RDONLY | libc::O_NOFOLLOW,
            )
            .map_err(|e| e.to_string())?,
            8192,
        )
        .map_err(|e| e.to_string())?;
        let mut actual = procs
            .lines()
            .map(|s| s.parse::<u32>())
            .collect::<std::result::Result<Vec<_>, _>>()
            .map_err(|_| "physical cgroup process list invalid")?;
        actual.sort();
        if actual != expected
            || fs::read_dir(&self.group_path)
                .map_err(|e| e.to_string())?
                .any(|r| r.map_or(true, |e| e.file_type().map_or(true, |t| t.is_dir())))
        {
            return Err("previous physical case has an unretired process or nested cgroup".into());
        }
        Ok(())
    }
    pub(crate) fn switch(
        &mut self,
        profile: KernelProfile,
        child: &BoundProcess,
        deadline: Instant,
    ) -> Result<(), String> {
        self.boundary(Some(child), deadline)?;
        if self.profile == profile {
            return Ok(());
        }
        let current = self
            .memory_current
            .text(&self.group)
            .map_err(|e| e.to_string())?
            .parse::<u64>()
            .map_err(|_| "physical memory.current invalid")?;
        // Leave explicit headroom before lowering the live same-process group.
        if profile == KernelProfile::Calendar && current >= 536_870_912 - 32 * 1024 * 1024 {
            return Err("physical owner does not fit the next original 512 MiB case".into());
        }
        let values = profile.values();
        for i in [0, 1] {
            self.controls[i]
                .write(&self.group, values[i])
                .map_err(|e| e.to_string())?;
        }
        self.profile = profile;
        self.kernel_guard(Some(child))?;
        if Instant::now() >= self.end.min(deadline) {
            return Err("physical profile ACK expired".into());
        }
        Ok(())
    }
    pub(crate) fn observation(&self) -> Value {
        json!({"schema":"droidloom.physical-qualification-parent.v1",
            "unit":self.invocation.unit,"invocation":self.invocation.id.iter().map(|b| format!("{b:02x}")).collect::<String>(),
            "parent_pid":self.current.identity.pid,"parent_start_ticks":self.current.identity.start_ticks,
            "properties":self.properties,"cgroup":self.group_path,"cgroup_identity":self.group_pin,
            "normal_executable":{"path":self.executable.path,"f9":self.executable.identity,"sha256":self.executable.sha},
            "profile":format!("{:?}",self.profile),"all_child_processes_retired":true,
            "parent_unit_retirement_requires_external_readback":true,
            "working_singleton":self.kind==OwnerKind::WorkingSingleton})
    }
}

fn qualification_properties(
    unit: &bus::Properties,
    service: &bus::Properties,
    invocation: &bus::Invocation,
    pid: u32,
    digest: &str,
) -> Result<BTreeMap<String, String>, String> {
    owner_properties(unit, service, invocation, pid, digest, OwnerKind::PhysicalTemplate)
}
fn owner_properties(
    unit: &bus::Properties,
    service: &bus::Properties,
    invocation: &bus::Invocation,
    pid: u32,
    digest: &str,
    kind: OwnerKind,
) -> Result<BTreeMap<String, String>, String> {
    use bus::Value as V;
    let expected_unit = kind.unit(digest).map_err(|e| e.to_string())?;
    let fragment_path = format!("/usr/lib/systemd/system/{}", kind.fragment());
    if invocation.unit != expected_unit
        || unit.get("InvocationID") != Some(&V::Bytes(invocation.id.to_vec()))
        || unit.get("Transient") != Some(&V::Boolean(false))
        || unit.get("NeedDaemonReload") != Some(&V::Boolean(false))
        || unit.get("DropInPaths") != Some(&V::Strings(Vec::new()))
    {
        return Err("fixed installed physical unit or invocation metadata differs".into());
    }
    let mut values = BTreeMap::new();
    for (key, want) in [
        ("Id", expected_unit.as_str()),
        ("LoadState", "loaded"),
        ("ActiveState", "active"),
        ("SubState", "running"),
        (
            "FragmentPath",
            fragment_path.as_str(),
        ),
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
        (
            "RuntimeMaxUSec",
            kind.service_seconds() * 1_000_000,
        ),
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
        || command.arguments != kind.argv(digest)
        || !command.flags.is_empty()
        || command.pid != pid
        || command.started[1] == 0
        || command.exited != [0, 0]
        || command.code != 0
        || command.status != 0
    {
        return Err("physical qualifier exact normal command differs".into());
    }
    values.insert(
        "ExecStartCommandMonotonic".into(),
        command.started[1].to_string(),
    );
    Ok(values)
}

#[cfg(test)]
mod tests {
    use super::*;
    fn fixture() -> (bus::Properties, bus::Properties, bus::Invocation, String) {
        use bus::Value as V;
        let digest = "a".repeat(64);
        let name = protocol::unit_name(&digest).unwrap();
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
            (
                "FragmentPath",
                "/usr/lib/systemd/system/droidloom-physical-qualification@.service",
            ),
        ] {
            unit.insert(key.into(), V::Text(value.into()));
        }
        unit.insert("InvocationID".into(), V::Bytes(vec![7; 16]));
        unit.insert("Transient".into(), V::Boolean(false));
        unit.insert("NeedDaemonReload".into(), V::Boolean(false));
        unit.insert("DropInPaths".into(), V::Strings(vec![]));
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
            (
                "RuntimeMaxUSec",
                protocol::SERVICE_SECONDS * 1_000_000,
            ),
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
                arguments: protocol::parent_argv(&digest),
                flags: vec![],
                started: [5, 99],
                exited: [0, 0],
                pid: 1234,
                code: 0,
                status: 0,
            }]),
        );
        (unit, service, invocation, digest)
    }
    #[test]
    fn physical_qualification_parent_requires_fixed_actual_command_and_invocation() {
        use bus::Value as V;
        let (unit, service, invocation, digest) = fixture();
        assert!(qualification_properties(&unit, &service, &invocation, 1234, &digest).is_ok());
        let mut wrong = unit.clone();
        wrong.insert("InvocationID".into(), V::Bytes(vec![8; 16]));
        assert!(qualification_properties(&wrong, &service, &invocation, 1234, &digest).is_err());
        let mut wrong = service.clone();
        let V::Commands(rows) = wrong.get_mut("ExecStartEx").unwrap() else {
            panic!()
        };
        rows[0].arguments[1] = "--physical-application-plan".into();
        assert!(qualification_properties(&unit, &wrong, &invocation, 1234, &digest).is_err());
        assert!(qualification_properties(&unit, &service, &invocation, 1235, &digest).is_err());
    }
    #[test]
    fn physical_qualification_rejects_extra_commands_dropins_and_raised_budget() {
        use bus::Value as V;
        let (unit, service, invocation, digest) = fixture();
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
                qualification_properties(&unit, &wrong, &invocation, 1234, &digest).is_err(),
                "{key}"
            );
        }
        let mut wrong = unit.clone();
        wrong.insert(
            "DropInPaths".into(),
            V::Strings(vec!["/tmp/override".into()]),
        );
        assert!(qualification_properties(&wrong, &service, &invocation, 1234, &digest).is_err());
        let mut wrong = service.clone();
        wrong.insert("ExecStartPostEx".into(), service["ExecStartEx"].clone());
        assert!(qualification_properties(&unit, &wrong, &invocation, 1234, &digest).is_err());
    }
    #[test]
    fn working_singleton_cannot_reuse_a_template_or_caller_plan_argv() {
        use bus::Value as V;
        let (mut unit, mut service, mut invocation, digest) = fixture();
        assert!(owner_properties(&unit, &service, &invocation, 1234, "", OwnerKind::WorkingSingleton).is_err());
        invocation.unit = working::PARENT_UNIT.into();
        unit.insert("Id".into(), V::Text(invocation.unit.clone()));
        unit.insert("FragmentPath".into(), V::Text(format!("/usr/lib/systemd/system/{}", working::PARENT_UNIT)));
        service.insert("ControlGroup".into(), V::Text(format!("/system.slice/{}", working::PARENT_UNIT)));
        let V::Commands(commands) = service.get_mut("ExecStartEx").unwrap() else { panic!() };
        commands[0].arguments = OwnerKind::WorkingSingleton.argv("");
        service.insert("RuntimeMaxUSec".into(), V::U64(OwnerKind::WorkingSingleton.service_seconds() * 1_000_000));
        assert!(owner_properties(&unit, &service, &invocation, 1234, "", OwnerKind::WorkingSingleton).is_ok());
        assert!(qualification_properties(&unit, &service, &invocation, 1234, &digest).is_err());
        let mut wrong = service.clone();
        let V::Commands(commands) = wrong.get_mut("ExecStartEx").unwrap() else { panic!() };
        commands[0].arguments.push(digest.clone());
        assert!(owner_properties(&unit, &wrong, &invocation, 1234, "", OwnerKind::WorkingSingleton).is_err());
        let mut wrong = unit.clone();
        wrong.insert("FragmentPath".into(), V::Text(format!("/usr/lib/systemd/system/{}", protocol::TEMPLATE_NAME)));
        assert!(owner_properties(&wrong, &service, &invocation, 1234, "", OwnerKind::WorkingSingleton).is_err());
        assert!(OwnerKind::WorkingSingleton.source().contains(&format!("RuntimeMaxSec={}s\n", OwnerKind::WorkingSingleton.service_seconds())));
        assert!(OwnerKind::WorkingSingleton.source().contains("LimitNOFILE=32768\n"));
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
    #[test]
    fn working_preparation_child_is_a_closed_preplan_entry() {
        let digest = "a".repeat(64);
        assert_eq!(child_arguments(OwnerKind::WorkingSingleton, "").unwrap(),
            vec![protocol::EXE.to_string(), "--working-qualification-prepare".into()]);
        assert!(child_arguments(OwnerKind::PhysicalTemplate, "").is_err());
        let physical = protocol::child_argv(&digest).unwrap();
        assert_eq!(child_arguments(OwnerKind::WorkingSingleton, &digest).unwrap(), physical);
        assert_eq!(child_arguments(OwnerKind::PhysicalTemplate, &digest).unwrap(), physical);
        assert!(child_arguments(OwnerKind::WorkingSingleton, "../caller").is_err());
        let mut caller = child_arguments(OwnerKind::WorkingSingleton, "").unwrap();
        caller.push("/caller/plan.json".into());
        assert_ne!(caller, child_arguments(OwnerKind::WorkingSingleton, "").unwrap());
        assert_ne!(physical, child_arguments(OwnerKind::WorkingSingleton, "").unwrap());
    }

}
