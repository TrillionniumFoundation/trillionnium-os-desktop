//! Read-only parent/source witness for the fixed working suite child.
//! All process choices originate in getppid/current proc, then the authenticated
//! PID1 invocation. The serialized origin only supplies comparison values.
use super::super::super::working_qualification::WorkingUnitIdentity;
use super::*;

pub(crate) struct WorkingParent {
    peer: ChildPeer,
    manager: BoundProcess,
    manager_exe: Tool,
    namespaces: Vec<(&'static str, File, File)>,
    connection: Connection,
    group: File,
    group_pin: [u64; 5],
    unit_file: File,
    unit_pin: [u64; 9],
    unit_parents: Vec<(PathBuf, File, [u64; 5])>,
    expected: WorkingUnitIdentity,
    end: Instant,
}
impl WorkingParent {
    pub(crate) fn capture(expected: &WorkingUnitIdentity, end: Instant) -> Result<Self, String> {
        expected.validate()?;
        let actual = BoundProcess::capture(std::process::id()).map_err(|e| e.to_string())?;
        let argv = cmdline(&actual).map_err(|e| e.to_string())?;
        if argv.len() != 5
            || argv[0] != protocol::EXE
            || argv[1] != "--physical-application-plan"
            || argv[3] != "--expect-physical-plan-sha256"
            || !protocol::digest_ok(&argv[4])
        {
            return Err("working source is available only in the actual normal suite child".into());
        }
        let peer = ChildPeer::capture(&argv[4]).map_err(|e| e.to_string())?;
        if peer.kind != OwnerKind::WorkingSingleton
            || peer.parent.identity.pid != expected.parent_pid
            || peer.parent.identity.start_ticks != expected.parent_start_ticks
            || peer.group.to_str() != Some(expected.cgroup.as_str())
        {
            return Err("actual same-exec working parent differs from source origin".into());
        }
        let group = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open(&peer.group)
            .map_err(|e| e.to_string())?;
        let group_pin: [u64; 5] = identity(&group).map_err(|e| e.to_string())?[..5]
            .try_into()
            .map_err(|_| "working group identity")?;
        if group_pin != expected.cgroup_identity {
            return Err("actual working parent cgroup inode differs".into());
        }
        let manager = BoundProcess::capture(1).map_err(|e| e.to_string())?;
        let manager_exe = Tool::open("/usr/lib/systemd/systemd").map_err(|e| e.to_string())?;
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
                peer.parent.open(name, false).map_err(|e| e.to_string())?,
                manager.open(name, false).map_err(|e| e.to_string())?,
            ));
        }
        let path = PathBuf::from(format!("/usr/lib/systemd/system/{}", working::PARENT_UNIT));
        if path.canonicalize().map_err(|e| e.to_string())? != path {
            return Err("working unit source path is aliased".into());
        }
        let mut unit_parents = Vec::new();
        for p in path
            .parent()
            .ok_or("working unit parent missing")?
            .ancestors()
        {
            let file = OpenOptions::new()
                .read(true)
                .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
                .open(p)
                .map_err(|e| e.to_string())?;
            let pin: [u64; 5] = identity(&file).map_err(|e| e.to_string())?[..5]
                .try_into()
                .map_err(|_| "working unit parent identity")?;
            if pin[2] & 0o170000 != 0o040000 || pin[2] & 0o022 != 0 || pin[3..5] != [0, 0] {
                return Err("working unit requires exact protected root parents".into());
            }
            unit_parents.push((p.into(), file, pin));
        }
        let unit_file = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open(&path)
            .map_err(|e| e.to_string())?;
        let unit_pin = identity(&unit_file).map_err(|e| e.to_string())?;
        let source = OwnerKind::WorkingSingleton.source();
        if unit_pin[2] & 0o170000 != 0o100000
            || unit_pin[2] & 0o6022 != 0
            || unit_pin[3..6] != [0, 0, 1]
            || unit_pin[6] != source.len() as u64
        {
            return Err("working source unit file metadata differs".into());
        }
        let until = end.min(Instant::now() + Duration::from_secs(15));
        let connection = Connection::open(until)?;
        let invocation = connection
            .bus
            .invocation(peer.parent.pidfd.as_fd(), until)
            .map_err(|e| e.to_string())?;
        let unit = connection
            .bus
            .properties(&invocation, bus::Interface::Unit, until)
            .map_err(|e| e.to_string())?;
        let service = connection
            .bus
            .properties(&invocation, bus::Interface::Service, until)
            .map_err(|e| e.to_string())?;
        let values = owner_properties(
            &unit,
            &service,
            &invocation,
            peer.parent.identity.pid,
            "",
            OwnerKind::WorkingSingleton,
        )?;
        let start = [
            "ExecMainStartTimestampMonotonic",
            "ExecStartCommandMonotonic",
        ]
        .iter()
        .map(|k| {
            values
                .get(*k)
                .ok_or("working actual start absent")?
                .parse::<u64>()
                .map_err(|_| "working actual start invalid")
        })
        .collect::<Result<Vec<_>, _>>()?
        .into_iter()
        .min()
        .ok_or("working actual starts absent")?
        .checked_mul(1000)
        .ok_or("working actual start overflow")?;
        if invocation.unit != expected.unit
            || values.get("InvocationID") != Some(&expected.invocation)
            || start != expected.owner_start_monotonic_ns
            || connection
                .bus
                .invocation(peer.parent.pidfd.as_fd(), until)
                .map_err(|e| e.to_string())?
                != invocation
            || Instant::now() >= until
        {
            return Err("actual working parent PID1 invocation/start changed or differs".into());
        }
        let result = Self {
            peer,
            manager,
            manager_exe,
            namespaces,
            connection,
            group,
            group_pin,
            unit_file,
            unit_pin,
            unit_parents,
            expected: expected.clone(),
            end,
        };
        result.guard()?;
        Ok(result)
    }
    pub(crate) fn guard(&self) -> Result<(), String> {
        self.peer.guard().map_err(|e| e.to_string())?;
        self.connection.guard()?;
        self.manager.validate().map_err(|e| e.to_string())?;
        self.manager_exe.guard().map_err(|e| e.to_string())?;
        if self.manager.identity.comm != "systemd"
            || identity(&self.manager.open("exe", false).map_err(|e| e.to_string())?)
                .map_err(|e| e.to_string())?
                != self.manager_exe.identity
            || self.peer.parent.identity.pid != self.expected.parent_pid
            || self.peer.parent.identity.start_ticks != self.expected.parent_start_ticks
            || Instant::now() >= self.end
        {
            return Err("working source parent/manager retired or original end exhausted".into());
        }
        for (name, a, b) in &self.namespaces {
            if !super::super::super::same_file(a, b).map_err(|e| e.to_string())?
                || !super::super::super::same_file(
                    a,
                    &self
                        .peer
                        .parent
                        .open(name, false)
                        .map_err(|e| e.to_string())?,
                )
                .map_err(|e| e.to_string())?
                || !super::super::super::same_file(
                    b,
                    &self.manager.open(name, false).map_err(|e| e.to_string())?,
                )
                .map_err(|e| e.to_string())?
            {
                return Err("actual working source parent host namespaces changed".into());
            }
        }
        for (p, file, pin) in &self.unit_parents {
            let named = OpenOptions::new()
                .read(true)
                .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
                .open(p)
                .map_err(|e| e.to_string())?;
            if identity(file).map_err(|e| e.to_string())?[..5] != *pin
                || identity(&named).map_err(|e| e.to_string())?[..5] != *pin
            {
                return Err("held working unit source parent changed".into());
            }
        }
        let path = format!("/usr/lib/systemd/system/{}", working::PARENT_UNIT);
        let named = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open(path)
            .map_err(|e| e.to_string())?;
        let mut body = vec![0; OwnerKind::WorkingSingleton.source().len()];
        self.unit_file
            .read_exact_at(&mut body, 0)
            .map_err(|e| e.to_string())?;
        let group = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open(&self.peer.group)
            .map_err(|e| e.to_string())?;
        if identity(&self.unit_file).map_err(|e| e.to_string())? != self.unit_pin
            || identity(&named).map_err(|e| e.to_string())? != self.unit_pin
            || body != OwnerKind::WorkingSingleton.source().as_bytes()
            || identity(&self.group).map_err(|e| e.to_string())?[..5] != self.group_pin
            || identity(&group).map_err(|e| e.to_string())?[..5] != self.group_pin
        {
            return Err("working source unit body or held cgroup generation changed".into());
        }
        Ok(())
    }
}
