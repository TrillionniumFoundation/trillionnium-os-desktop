//! A bounded original-host label window. Only exact observed graphical/log
//! writers are frozen; PID1, remote SSH scopes, networking, the once owner and
//! its independently running thaw guard remain outside every selected subtree.
//! The guard has a fixed deadline and can only thaw this intent's same cgroups.
use super::{
    OriginalQualificationAuthority, commands,
    owner::{self, SealedInput},
    state::Phase,
};
use crate::{
    Result,
    boot_files::{self as files, FilePin},
    ensure, fs,
    model::Identity,
};
use rustix::fs::{FileType, Mode, OFlags};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    collections::BTreeSet,
    fs::File,
    io::{Read, Seek, Write},
    os::fd::OwnedFd,
    path::{Path, PathBuf},
    time::{Duration, Instant},
};

const MAGIC: u64 = 0x63677270;
const MAX_SECONDS: u64 = 600;
const BASE: &str = "/sys/fs/cgroup";
const FIXED_UNITS: &[&str] = &[
    "gdm.service",
    "gdm3.service",
    "systemd-journald.service",
    "rsyslog.service",
    "accounts-daemon.service",
    "user@1000.service",
    "user@120.service",
    "user@981.service",
    "user@997.service",
    "hepta-runtime.service",
];

fn bounded(mut f: &File, limit: usize) -> Result<String> {
    f.rewind()?;
    let mut bytes = Vec::new();
    f.take(limit as u64 + 1).read_to_end(&mut bytes)?;
    ensure(bytes.len() <= limit, "bounded kernel readback exceeded")?;
    Ok(String::from_utf8(bytes)?)
}
fn clock_ms() -> Result<u64> {
    let text = bounded(&File::open("/proc/uptime")?, 128)?;
    let value = text.split_whitespace().next().ok_or("boot clock absent")?;
    let (whole, fraction) = value.split_once('.').ok_or("boot clock format")?;
    ensure(
        !whole.is_empty()
            && whole.bytes().all(|b| b.is_ascii_digit())
            && fraction.len() == 2
            && fraction.bytes().all(|b| b.is_ascii_digit()),
        "boot clock precision differs",
    )?;
    Ok(whole
        .parse::<u64>()?
        .checked_mul(1000)
        .and_then(|v| v.checked_add(fraction.parse::<u64>().ok()? * 10))
        .ok_or("boot clock overflow")?)
}
fn starttime(pid: u32) -> Result<u64> {
    let text = bounded(&File::open(format!("/proc/{pid}/stat"))?, 8192)?;
    let after = text.rfind(')').ok_or("process stat format")?;
    let fields: Vec<_> = text[after + 1..].split_whitespace().collect();
    ensure(
        fields.len() >= 20 && !matches!(fields[0], "Z" | "X"),
        "process retired",
    )?;
    Ok(fields[19].parse()?)
}
fn same_object(a: &Identity, b: &Identity) -> bool {
    (a.dev, a.ino, a.mode, a.uid, a.gid, a.nlink) == (b.dev, b.ino, b.mode, b.uid, b.gid, b.nlink)
}
fn within(path: &str, parent: &str) -> bool {
    path == parent
        || path
            .strip_prefix(parent)
            .is_some_and(|s| s.starts_with('/'))
}
fn cgroup_path(path: &str) -> Result<()> {
    ensure(
        path.starts_with('/')
            && path.len() <= 512
            && path != "/"
            && path != "/system.slice"
            && path != "/user.slice"
            && !path.ends_with('/')
            && path.split('/').skip(1).all(|c| {
                !c.is_empty()
                    && c != "."
                    && c != ".."
                    && c.bytes()
                        .all(|b| b.is_ascii_alphanumeric() || b"._@-\\".contains(&b))
            }),
        "unsafe or host-wide freeze cgroup",
    )
}
fn events_frozen(text: &str) -> Result<bool> {
    let rows: Vec<_> = text
        .lines()
        .filter_map(|l| l.strip_prefix("frozen "))
        .collect();
    ensure(
        rows.len() == 1 && matches!(rows[0], "0" | "1"),
        "cgroup freezer events malformed",
    )?;
    Ok(rows[0] == "1")
}

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct GroupRecord {
    path: String,
    unit: String,
    directory: Identity,
    freeze: Identity,
    events: Identity,
}
struct Group {
    record: GroupRecord,
    dir: File,
    freeze: File,
    events: File,
}
impl Group {
    fn open(path: &str, unit: &str) -> Result<Self> {
        cgroup_path(path)?;
        let full = format!("{BASE}{path}");
        let dir = fs::Tree::open("/", 0)?.dir(&full)?;
        let directory = fs::stat(&dir)?;
        ensure(
            directory.uid == 0
                && directory.gid == 0
                && directory.mode & 0o022 == 0
                && rustix::fs::fstatfs(&dir)?.f_type as u64 == MAGIC,
            "freeze target is not original root-owned cgroup-v2",
        )?;
        let freeze = File::from(rustix::fs::openat(
            &dir,
            "cgroup.freeze",
            OFlags::RDWR | OFlags::NOFOLLOW | OFlags::CLOEXEC,
            Mode::empty(),
        )?);
        let events = File::from(rustix::fs::openat(
            &dir,
            "cgroup.events",
            OFlags::RDONLY | OFlags::NOFOLLOW | OFlags::CLOEXEC,
            Mode::empty(),
        )?);
        for f in [&freeze, &events] {
            let id = fs::stat(f)?;
            ensure(
                FileType::from_raw_mode(id.mode) == FileType::RegularFile
                    && id.dev == directory.dev
                    && id.uid == 0
                    && id.gid == 0
                    && id.nlink == 1
                    && id.mode & 0o022 == 0
                    && rustix::fs::fstatfs(f)?.f_type as u64 == MAGIC,
                "cgroup control identity differs",
            )?;
        }
        let record = GroupRecord {
            path: path.into(),
            unit: unit.into(),
            directory,
            freeze: fs::stat(&freeze)?,
            events: fs::stat(&events)?,
        };
        let result = Self {
            record,
            dir,
            freeze,
            events,
        };
        result.custody()?;
        Ok(result)
    }
    fn from_record(record: &GroupRecord) -> Result<Self> {
        let result = Self::open(&record.path, &record.unit)?;
        ensure(
            same_object(&result.record.directory, &record.directory)
                && same_object(&result.record.freeze, &record.freeze)
                && same_object(&result.record.events, &record.events),
            "recorded freeze inode was replaced",
        )?;
        Ok(result)
    }
    fn custody(&self) -> Result<()> {
        let named = fs::Tree::open("/", 0)?.dir(&format!("{BASE}{}", self.record.path))?;
        ensure(
            same_object(&fs::stat(&self.dir)?, &self.record.directory)
                && same_object(&fs::stat(&named)?, &self.record.directory)
                && same_object(&fs::stat(&self.freeze)?, &self.record.freeze)
                && same_object(&fs::stat(&self.events)?, &self.record.events)
                && fs::identity(&rustix::fs::statat(
                    &named,
                    "cgroup.freeze",
                    rustix::fs::AtFlags::SYMLINK_NOFOLLOW,
                )?) == fs::stat(&self.freeze)?
                && fs::identity(&rustix::fs::statat(
                    &named,
                    "cgroup.events",
                    rustix::fs::AtFlags::SYMLINK_NOFOLLOW,
                )?) == fs::stat(&self.events)?,
            "held/named cgroup control changed",
        )
    }
    fn is_frozen(&self) -> Result<bool> {
        self.custody()?;
        events_frozen(&bounded(&self.events, 4096)?)
    }
    fn set(&self, frozen: bool) -> Result<()> {
        self.custody()?;
        let mut f = &self.freeze;
        f.rewind()?;
        f.write_all(if frozen { b"1" } else { b"0" })?;
        let until = Instant::now() + Duration::from_secs(10);
        loop {
            if self.is_frozen()? == frozen {
                return Ok(());
            }
            ensure(
                Instant::now() < until,
                "actual cgroup freezer did not converge",
            )?;
            std::thread::sleep(Duration::from_millis(25));
        }
    }
}

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct FreezeIntent {
    schema: String,
    candidate_id: String,
    original_boot_id: String,
    base_intent: FilePin,
    producer: FilePin,
    owner_pid: u32,
    owner_starttime: u64,
    owner_control_group: String,
    deadline_boot_ms: u64,
    inventory: FilePin,
    groups: Vec<GroupRecord>,
    excluded_remote_scopes: Vec<String>,
    critical_excluded: Vec<String>,
}

fn inventory_groups(
    value: &Value,
    candidate: &str,
) -> Result<(Vec<(String, String)>, Vec<String>)> {
    let owner = format!("/system.slice/droidloom-original-qualification@{candidate}.service");
    let thaw = format!("/system.slice/droidloom-original-thaw@{candidate}.service");
    let sessions = value["sessions"]
        .as_array()
        .ok_or("actual login session inventory absent")?;
    let mut graphical = BTreeSet::new();
    let mut remote = Vec::new();
    for row in sessions {
        let scope = row["Scope"].as_str().unwrap_or("");
        if row["Remote"] == "yes" {
            ensure(
                scope.starts_with("session-") && scope.ends_with(".scope"),
                "remote session scope differs",
            )?;
            remote.push(scope.to_owned());
        }
        if row["Remote"] == "no"
            && row["Class"] == "user"
            && ["1000", "120", "981"].iter().any(|u| row["User"] == *u)
            && ["wayland", "x11"].iter().any(|v| row["Type"] == *v)
        {
            graphical.insert(scope.to_owned());
        }
    }
    let mut result = Vec::new();
    let mut observed_owner = false;
    for row in value["units"]
        .as_array()
        .ok_or("actual unit inventory absent")?
    {
        let requested = row["RequestedId"]
            .as_str()
            .ok_or("requested unit identity absent")?;
        if requested == format!("droidloom-original-qualification@{candidate}.service") {
            ensure(
                row["ControlGroup"] == owner
                    && row["ActiveState"] == "active"
                    && row["Restart"] == "on-failure",
                "once owner must have an observed normal failure restart",
            )?;
            observed_owner = true;
            continue;
        }
        ensure(
            FIXED_UNITS.contains(&requested) || graphical.contains(requested),
            "unlisted writer cannot be frozen",
        )?;
        if row["LoadState"] == "not-found"
            || row["ActiveState"] == "inactive"
            || row["ActiveState"] == "failed"
        {
            continue;
        }
        ensure(
            row["LoadState"] == "loaded" && row["ActiveState"] == "active",
            "writer is changing lifecycle during freeze inventory",
        )?;
        let path = row["ControlGroup"].as_str().ok_or("writer cgroup absent")?;
        cgroup_path(path)?;
        ensure(
            !within(&owner, path)
                && !within(&thaw, path)
                && !remote.iter().any(|s| path.ends_with(&format!("/{s}")))
                && (path.ends_with(&format!("/{requested}"))
                    || (matches!(requested, "gdm.service" | "gdm3.service")
                        && ["/system.slice/gdm.service", "/system.slice/gdm3.service"]
                            .contains(&path))),
            "critical owner or foreign/remote session was selected for freeze",
        )?;
        result.push((path.to_owned(), requested.to_owned()));
    }
    ensure(
        observed_owner,
        "actual original owner unit was not observed",
    )?;
    result.sort();
    result.dedup_by(|a, b| a.0 == b.0);
    let all: Vec<_> = result.iter().map(|v| v.0.clone()).collect();
    result.retain(|(path, _)| {
        !all.iter()
            .any(|parent| parent != path && within(path, parent))
    });
    ensure(
        !result.is_empty() && result.len() <= 64,
        "empty or oversized fixed writer inventory",
    )?;
    Ok((result, remote))
}

/// Private proof of actual live freezer state, with a separately running
/// same-source guard. There is no serde or caller-provided `quiet` flag.
pub(super) struct Quiescence {
    candidate: String,
    intent: SealedInput,
    groups: Vec<Group>,
    deadline: u64,
    reaper_pid: u32,
    reaper_starttime: u64,
    reaper_pidfd: OwnedFd,
    finished: bool,
}
impl Quiescence {
    pub(super) fn begin(a: &OriginalQualificationAuthority) -> Result<Self> {
        a.verify_current_owner()?;
        ensure(
            a.journal.borrow().phase() == Some(Phase::GrubPublished),
            "freeze is only after public/recovery/GRUB publication",
        )?;
        let inventory = commands::call(
            a,
            "label-writer-inventory",
            "quiescence-inventory",
            json!({}),
            90,
        )?;
        let (paths, remote) = inventory_groups(&inventory.report, a.candidate_id())?;
        let groups = paths
            .iter()
            .map(|(p, u)| Group::open(p, u))
            .collect::<Result<Vec<_>>>()?;
        for group in &groups {
            ensure(
                !group.is_frozen()? && bounded(&group.freeze, 16)?.trim() == "0",
                "already frozen group is not ours to thaw",
            )?;
        }
        let observed = a.owner.borrow().evidence();
        let base: Value = serde_json::from_slice(&a.intent.read()?)?;
        let producer: FilePin = serde_json::from_value(base["normal_producer"].clone())?;
        let deadline = clock_ms()?
            .checked_add(MAX_SECONDS * 1000)
            .ok_or("freeze deadline overflow")?;
        let intent = FreezeIntent {
            schema: "droidloom.original-once-freeze-intent.v1".into(),
            candidate_id: a.candidate_id().into(),
            original_boot_id: a.owner.borrow().boot_id().into(),
            base_intent: a.intent.pin().clone(),
            producer: producer.clone(),
            owner_pid: std::process::id(),
            owner_starttime: starttime(std::process::id())?,
            owner_control_group: observed["actual_original"]["control_group"]
                .as_str()
                .ok_or("actual owner cgroup")?
                .into(),
            deadline_boot_ms: deadline,
            inventory: inventory.pin,
            groups: groups
                .iter()
                .map(|g| {
                    serde_json::from_value(serde_json::to_value(&g.record)?).map_err(Into::into)
                })
                .collect::<Result<_>>()?,
            excluded_remote_scopes: remote,
            critical_excluded: inventory.report["critical_excluded"]
                .as_array()
                .ok_or("critical inventory")?
                .iter()
                .map(|v| {
                    v.as_str()
                        .map(str::to_owned)
                        .ok_or_else(|| "critical unit string".into())
                })
                .collect::<Result<_>>()?,
        };
        let dir = a.work().join("quiescence");
        files::private_dir(&dir)?;
        let path = dir.join("FREEZE-INTENT.json");
        files::write_new(&path, &serde_json::to_vec_pretty(&intent)?, 0o400)?;
        File::open(&dir)?.sync_all()?;
        let pin = files::pin_file(&path)?;
        commands::call(
            a,
            "label-thaw-guard-start",
            "quiescence-reaper",
            json!({"producer":producer,"freeze_intent":pin}),
            45,
        )?;
        let until = Instant::now() + Duration::from_secs(15);
        let ready = dir.join("READY.json");
        while !ready.exists() {
            ensure(
                Instant::now() < until,
                "independent thaw guard did not become ready",
            )?;
            std::thread::sleep(Duration::from_millis(50));
        }
        let ready = SealedInput::open(&files::pin_file(&ready)?)?;
        let value: Value = serde_json::from_slice(&ready.read()?)?;
        ensure(
            value["freeze_intent"] == serde_json::to_value(&pin)?
                && value["candidate_id"] == a.candidate_id(),
            "thaw ready belongs to another immutable intent",
        )?;
        let reaper_pid: u32 = value["pid"].as_u64().ok_or("thaw pid")?.try_into()?;
        let reaper_starttime = value["starttime"].as_u64().ok_or("thaw starttime")?;
        let reaper_pidfd = rustix::process::pidfd_open(
            rustix::process::Pid::from_raw(reaper_pid as i32).ok_or("thaw pid range")?,
            rustix::process::PidfdFlags::empty(),
        )?;
        ensure(
            starttime(reaper_pid)? == reaper_starttime,
            "thaw process identity changed",
        )?;
        let mut result = Self {
            candidate: a.candidate_id().into(),
            intent: SealedInput::open(&pin)?,
            groups,
            deadline,
            reaper_pid,
            reaper_starttime,
            reaper_pidfd,
            finished: false,
        };
        result.verify_guard()?;
        // Write-ahead intent already describes the full original-zero set. A
        // process crash during this loop is therefore safely thawed by guard.
        for group in &result.groups {
            group.set(true)?;
            result.verify_guard()?;
        }
        result.verify()?;
        a.verify_current_owner()?;
        files::write_new(
            &dir.join("FROZEN.json"),
            &serde_json::to_vec(
                &json!({"schema":"droidloom.original-once-frozen.v1","freeze_intent":pin,"deadline_boot_ms":deadline,"actual_frozen":result.groups.iter().map(|g|&g.record.path).collect::<Vec<_>>()}),
            )?,
            0o400,
        )?;
        File::open(&dir)?.sync_all()?;
        Ok(result)
    }
    fn verify_guard(&self) -> Result<()> {
        self.intent.revalidate_custody()?;
        ensure(
            clock_ms()? < self.deadline && starttime(self.reaper_pid)? == self.reaper_starttime,
            "label window deadline or independent guard custody ended",
        )?;
        let fd = rustix::fs::fstat(&self.reaper_pidfd)?;
        ensure(fd.st_nlink == 1, "thaw process descriptor differs")?;
        Ok(())
    }
    pub(super) fn verify(&self) -> Result<()> {
        self.verify_guard()?;
        ensure(!self.finished, "freeze window already retired")?;
        for g in &self.groups {
            ensure(g.is_frozen()?, "a selected writer is no longer frozen")?;
        }
        Ok(())
    }
    pub(super) fn candidate_id(&self) -> &str {
        &self.candidate
    }
    pub(super) fn finish(mut self) -> Result<()> {
        self.verify()?;
        for group in self.groups.iter().rev() {
            group.set(false)?;
        }
        let path = self
            .intent
            .pin()
            .path
            .parent()
            .ok_or("freeze parent")?
            .join("RELEASED.json");
        files::write_new(
            &path,
            &serde_json::to_vec(
                &json!({"schema":"droidloom.original-once-freeze-released.v1","freeze_intent":self.intent.pin(),"actual_thawed":self.groups.iter().map(|g|&g.record.path).collect::<Vec<_>>(),"boot_ms":clock_ms()?}),
            )?,
            0o400,
        )?;
        File::open(path.parent().ok_or("release parent")?)?.sync_all()?;
        self.finished = true;
        Ok(())
    }
}
impl Drop for Quiescence {
    fn drop(&mut self) {
        if !self.finished {
            for group in self.groups.iter().rev() {
                let _ = group.set(false);
            }
        }
        // Dropping never declares a completed transaction. The guard keeps its
        // deadline and the durable intent for recovery even if this thaw fails.
    }
}

/// Hidden normal-fixture entry. It can only thaw an exact original-zero set;
/// it cannot obtain package, data, labels, GRUB or qualification authority.
pub(super) fn run_thaw_guard(config: &Path, expected: &str) -> Result<()> {
    let pin = files::pin_file(config)?;
    ensure(pin.sha256 == expected, "thaw config hash differs")?;
    let sealed = SealedInput::open(&pin)?;
    let v: FreezeIntent = serde_json::from_slice(&sealed.read()?)?;
    ensure(
        v.schema == "droidloom.original-once-freeze-intent.v1"
            && fs::valid_digest(&v.candidate_id)
            && config
                == Path::new("/var/lib/droidloom-qualification").join(format!(
                    "original-once-{}/quiescence/FREEZE-INTENT.json",
                    v.candidate_id
                ))
            && v.owner_control_group
                == format!(
                    "/system.slice/droidloom-original-qualification@{}.service",
                    v.candidate_id
                )
            && v.groups.len() <= 64
            && !v.groups.is_empty(),
        "thaw intent scope differs",
    )?;
    owner::verify_thaw_owner(&v.candidate_id, &v.original_boot_id)?;
    let initial = clock_ms()?;
    ensure(
        v.deadline_boot_ms > initial && v.deadline_boot_ms - initial <= MAX_SECONDS * 1000,
        "thaw deadline is not bounded",
    )?;
    let exe = File::open("/proc/self/exe")?;
    let (_, source) = files::open_pin(&v.producer)?;
    ensure(
        fs::stat(&exe)? == source && fs::hash(&exe)? == v.producer.sha256,
        "thaw is not the normal selected producer",
    )?;
    let base = SealedInput::open(&v.base_intent)?;
    let base_value: Value = serde_json::from_slice(&base.read()?)?;
    ensure(
        base_value["candidate_id"] == v.candidate_id
            && base_value["original_boot_id"] == v.original_boot_id
            && base_value["normal_producer"] == serde_json::to_value(&v.producer)?,
        "thaw base identity differs",
    )?;
    let inventory = SealedInput::open(&v.inventory)?;
    let iv: Value = serde_json::from_slice(&inventory.read()?)?;
    let (allowed, _) = inventory_groups(&iv["actual"]["result"], &v.candidate_id)?;
    ensure(
        allowed
            .iter()
            .map(|p| (&p.0, &p.1))
            .eq(v.groups.iter().map(|g| (&g.path, &g.unit))),
        "thaw cgroups differ from normal observed writer roster",
    )?;
    let groups = v
        .groups
        .iter()
        .map(Group::from_record)
        .collect::<Result<Vec<_>>>()?;
    let owner_fd = rustix::process::pidfd_open(
        rustix::process::Pid::from_raw(v.owner_pid as i32).ok_or("owner pid range")?,
        rustix::process::PidfdFlags::empty(),
    )?;
    ensure(
        starttime(v.owner_pid)? == v.owner_starttime
            && bounded(&File::open(format!("/proc/{}/cgroup", v.owner_pid))?, 4096)?
                == format!("0::{}\n", v.owner_control_group),
        "thaw's original owner is not the selected process",
    )?;
    let directory = config.parent().ok_or("thaw parent")?;
    files::write_new(
        &directory.join("READY.json"),
        &serde_json::to_vec(
            &json!({"schema":"droidloom.original-once-thaw-ready.v1","candidate_id":v.candidate_id,"freeze_intent":pin,"pid":std::process::id(),"starttime":starttime(std::process::id())?,"deadline_boot_ms":v.deadline_boot_ms}),
        )?,
        0o400,
    )?;
    File::open(directory)?.sync_all()?;
    let reason = loop {
        sealed.revalidate_custody()?;
        base.revalidate_custody()?;
        owner::verify_thaw_owner(&v.candidate_id, &v.original_boot_id)?;
        if directory.join("RELEASED.json").exists() {
            let release = SealedInput::open(&files::pin_file(&directory.join("RELEASED.json"))?)?;
            let actual: Value = serde_json::from_slice(&release.read()?)?;
            ensure(
                actual["freeze_intent"] == serde_json::to_value(&pin)?
                    && groups.iter().all(|g| g.is_frozen().is_ok_and(|x| !x)),
                "release did not actually thaw selected cgroups",
            )?;
            break "released";
        }
        if starttime(v.owner_pid).ok() != Some(v.owner_starttime) {
            break "owner-retired";
        }
        if clock_ms()? >= v.deadline_boot_ms {
            break "deadline";
        }
        std::thread::sleep(Duration::from_millis(200));
    };
    let mut failures = Vec::new();
    for g in groups.iter().rev() {
        if let Err(e) = g.set(false) {
            failures.push(format!("{}: {e}", g.record.path));
        }
    }
    let result = json!({"schema":"droidloom.original-once-thaw-result.v1","freeze_intent":pin,"reason":reason,"failures":failures,"boot_ms":clock_ms()?,"qualification_pass":false});
    files::write_new(
        &directory.join("THAWED.json"),
        &serde_json::to_vec(&result)?,
        0o400,
    )?;
    File::open(directory)?.sync_all()?;
    ensure(
        failures.is_empty(),
        "same-inode automatic thaw did not complete",
    )?;
    if reason == "deadline" && starttime(v.owner_pid).ok() == Some(v.owner_starttime) {
        // The observed normal owner has Restart=on-failure. Kill only its held
        // pidfd after all selected groups are confirmed thawed. Its dispatcher
        // resumes the durable intent rather than reapplying initial mutations.
        rustix::process::pidfd_send_signal(&owner_fd, rustix::process::Signal::KILL)?;
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn critical_roots_and_remote_scope_are_not_freeze_candidates() {
        for p in [
            "/",
            "/system.slice",
            "/user.slice",
            "/user.slice/../init.scope",
            "/system.slice/ssh.service/",
        ] {
            assert!(cgroup_path(p).is_err());
        }
        assert!(cgroup_path("/user.slice/user-1000.slice/user@1000.service").is_ok());
        let id = "a".repeat(64);
        let owner = format!("droidloom-original-qualification@{id}.service");
        let mut v = json!({"sessions":[{"Scope":"session-4.scope","Remote":"yes","User":"1000","Type":"tty","Class":"user"}],"units":[{"RequestedId":owner,"ControlGroup":format!("/system.slice/{owner}"),"ActiveState":"active","Restart":"on-failure"},{"RequestedId":"gdm.service","LoadState":"loaded","ActiveState":"active","ControlGroup":"/system.slice/gdm.service"}]});
        assert_eq!(inventory_groups(&v, &id).unwrap().0.len(), 1);
        v["units"][1]["RequestedId"] = json!("session-4.scope");
        v["units"][1]["ControlGroup"] = json!("/user.slice/user-1000.slice/session-4.scope");
        assert!(inventory_groups(&v, &id).is_err());
    }
    #[test]
    fn actual_freezer_completion_not_requested_flag_is_required() {
        assert!(!events_frozen("populated 1\nfrozen 0\n").unwrap());
        assert!(events_frozen("populated 1\nfrozen 1\n").unwrap());
        for s in ["frozen 1\nfrozen 1\n", "freeze 1\n", "frozen 2\n"] {
            assert!(events_frozen(s).is_err());
        }
    }

    #[test]
    #[ignore = "root only; creates a new cgroup and moves only its own bounded child"]
    fn actual_private_cgroup_freeze_thaw_preserves_observer_and_original_groups() {
        struct Cleanup {
            path: std::path::PathBuf,
            child: Option<std::process::Child>,
        }
        impl Drop for Cleanup {
            fn drop(&mut self) {
                let _ = std::fs::write(self.path.join("cgroup.freeze"), b"0");
                if let Some(child) = &mut self.child {
                    let _ = child.kill();
                    let _ = child.wait();
                }
                let _ = std::fs::remove_dir(&self.path);
            }
        }
        let own = std::fs::read_to_string("/proc/self/cgroup").unwrap();
        let path = format!(
            "/droidloom-once-freezer-test-{}-{}",
            std::process::id(),
            clock_ms().unwrap()
        );
        let full = std::path::PathBuf::from(format!("{BASE}{path}"));
        std::fs::create_dir(&full).unwrap();
        let child = std::process::Command::new("/usr/bin/sleep")
            .arg("20")
            .spawn()
            .unwrap();
        let mut cleanup = Cleanup {
            path: full.clone(),
            child: Some(child),
        };
        let pid = cleanup.child.as_ref().unwrap().id();
        std::fs::write(full.join("cgroup.procs"), pid.to_string()).unwrap();
        let group = Group::open(&path, "isolated-test.service").unwrap();
        assert!(!group.is_frozen().unwrap());
        group.set(true).unwrap();
        assert!(group.is_frozen().unwrap());
        assert_eq!(std::fs::read_to_string("/proc/self/cgroup").unwrap(), own);
        assert_eq!(
            std::fs::read_to_string(format!("/proc/{pid}/cgroup")).unwrap(),
            format!("0::{path}\n")
        );
        group.set(false).unwrap();
        assert!(!group.is_frozen().unwrap());
        cleanup.child.as_mut().unwrap().kill().unwrap();
        cleanup.child.as_mut().unwrap().wait().unwrap();
        cleanup.child = None;
    }
}
