//! Normal return from the separately admitted working-copy qualification boot.
//! Reuses the original held-file, evidence and three maintenance commands.
//! It never opens the watchdog, stops another service, grants activation or
//! reconstructs complete application authority from saved output.
use super::{
    caps, command, filesystem, hash, held, monotonic, normal_collection,
    original_reboot_requested, original_selected, root_directory, text,
    Evidence, Identity, Input, PayloadPin, reject,
};
use crate::native_working_contract as c;
use serde_json::{Value, json};
use std::{
    ffi::{CString, OsString},
    fs::{File, OpenOptions},
    io::{self, Read},
    os::{fd::AsRawFd, unix::fs::{MetadataExt, OpenOptionsExt}},
    path::Path,
    time::{Duration, Instant},
};
const ROLE: &[u8] = b"u:system_r:p4_linux_working_return_t:s0";
const PROFILE: &[u8] = b"droidloom-working-qualification-return (enforce)";
const CONFIG_LABEL: &[u8] = b"u:object_r:p4_linux_working_config_t:s0";
const EVIDENCE_LABEL: &[u8] = b"u:object_r:p4_linux_working_evidence_t:s0";
// These two source modules share the same comparison schema but are compiled
// as distinct Rust types. Preserve both fields before the original held-file
// constructor applies its unchanged byte, owner, mode and identity checks.
fn once_pin(pin: &c::PayloadPin) -> PayloadPin {
    PayloadPin { bytes: pin.bytes, sha256: pin.sha256.clone() }
}
struct Owner {
    root: File,
    boot_id: String,
    pid: u32,
    config: c::WorkingReturnConfiguration,
    inputs: Vec<Input>,
}
impl Owner {
    fn open() -> io::Result<Self> {
        let root = root_directory(Path::new("/"))?;
        filesystem(&root, 0xef53)?;
        held::namespaces(&root)?;
        let proc = root_directory(Path::new("/proc"))?;
        filesystem(&proc, 0x9fa0)?;
        // The original PID1 owns the recorded mount namespace for this
        // whole boot. A self-MNT bind is deliberately not used: it would form
        // a reference cycle. No foreign /proc/1 namespace/root is inspected.
        let rm = root.metadata()?;
        if rm.ino() != 2 {
            return Err(reject("once return is not the actual ext4 root inode"));
        }
        let block = std::fs::metadata(format!("/dev/disk/by-uuid/{}", c::ROOT_UUID))?;
        if block.mode() & libc::S_IFMT != libc::S_IFBLK || block.rdev() != rm.dev() {
            return Err(reject("once return is not on the original root UUID"));
        }
        if text(Path::new("/proc/sys/kernel/osrelease"), 256)? != c::KERNEL
            || text(Path::new("/sys/fs/selinux/enforce"), 8)? != "1"
        {
            return Err(reject("once return needs its selected enforcing kernel"));
        }
        let args = c::boot_arguments(&text(Path::new("/proc/cmdline"), 32768)?)?;
        let path = Path::new(c::RETURN_CONFIG);
        let size = std::fs::symlink_metadata(path)?.len();
        if size > 65536 {
            return Err(reject("return config exceeds bound"));
        }
        let input = Input::open(
            path,
            &PayloadPin {
                bytes: size,
                sha256: args["droidloom.working.return"].clone(),
            },
            &[0o400],
            Some(CONFIG_LABEL),
        )?;
        let config: c::WorkingReturnConfiguration =
            serde_json::from_slice(&input.bytes()?).map_err(io::Error::other)?;
        config.validate()?;
        if args["droidloom.working"] != config.intent_sha256
            || args["droidloom.working.config"] != config.early_config_sha256
        {
            return Err(reject("return config differs from the durable boot intent"));
        }
        let boot_id = text(Path::new("/proc/sys/kernel/random/boot_id"), 64)?;
        if !c::uuid(&boot_id) || boot_id == config.original_boot_id {
            return Err(reject("once return did not enter a fresh candidate boot"));
        }
        let executable = Input::open(
            Path::new(c::RETURN_EXECUTABLE),
            &once_pin(&config.executable),
            &[0o755],
            None,
        )?;
        if Identity::from(std::fs::metadata("/proc/self/exe")?) != executable.identity {
            return Err(reject("once return is not its normal executable"));
        }
        let maintenance = Input::open(
            Path::new(c::MAINTENANCE_EXECUTABLE),
            &once_pin(&config.maintenance),
            &[0o755],
            None,
        )?;
        let installation = Input::open(
            Path::new(c::INSTALLATION),
            &once_pin(&config.installation),
            &[0o400, 0o444],
            None,
        )?;
        let cell = Input::open(
            Path::new("/etc/droidloom/cell.json"),
            &once_pin(&config.cell),
            &[0o644],
            None,
        )?;
        let selection = Input::open(
            Path::new("/etc/droidloom/production/selected.json"),
            &once_pin(&config.selection),
            &[0o400],
            None,
        )?;
        let v: Value = serde_json::from_slice(&installation.bytes()?).map_err(io::Error::other)?;
        if v["schema"] != "droidloom-maintenance-installation-v1"
            || v["root_uuid"] != c::ROOT_UUID
            || v["original_kernel"] != c::ORIGINAL_KERNEL
            || v["original_entry"] != c::ORIGINAL_ENTRY
        {
            return Err(reject("maintenance is not bound to the original entry"));
        }
        let witness_path = Path::new("/run/droidloom-early/host-mount-identity.json");
        let witness_parent = root_directory(witness_path.parent().unwrap())?;
        if held::label(&witness_parent)? != b"u:object_r:p4_linux_early_handoff_dir_t:s0" {
            return Err(reject("mount witness parent is not the original publisher"));
        }
        let mut witness_file = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_CLOEXEC | libc::O_NOFOLLOW | libc::O_NONBLOCK)
            .open(witness_path)?;
        let before = Identity::from(witness_file.metadata()?);
        if before.mode != libc::S_IFREG | 0o400
            || before.uid != 0
            || before.gid != 0
            || before.links != 1
            || before.bytes == 0
            || before.bytes >= 512
        {
            return Err(reject(
                "mount identity witness is not its bounded original inode",
            ));
        }
        let mut body = Vec::new();
        (&mut witness_file).take(512).read_to_end(&mut body)?;
        if Identity::from(witness_file.metadata()?) != before || body.len() as u64 != before.bytes {
            return Err(reject("mount identity witness changed during readback"));
        }
        let witness = Input::open(
            witness_path,
            &PayloadPin {
                bytes: before.bytes,
                sha256: hash(&body),
            },
            &[0o400],
            Some(b"u:object_r:p4_linux_host_mount_identity_t:s0"),
        )?;
        let value = Self {
            root,
            boot_id,
            pid: std::process::id(),
            config,
            inputs: vec![
                input,
                executable,
                maintenance,
                installation,
                cell,
                selection,
                witness,
            ],
        };
        value.revalidate()?;
        value.parent_retired()?;
        Ok(value)
    }
    fn revalidate(&self) -> io::Result<()> {
        caps::revalidate()?;
        if self.pid != std::process::id()
            || unsafe { libc::getppid() } != 1
            || held::current(101)? != ROLE
            || held::current(104)? != PROFILE
            || text(Path::new("/proc/sys/kernel/random/boot_id"), 64)? != self.boot_id
            || text(Path::new("/sys/fs/selinux/enforce"), 8)? != "1"
        {
            return Err(reject("once return lost boot, process or MAC custody"));
        }
        held::namespaces(&self.root)?;
        self.exact_unit()?;
        for i in &self.inputs {
            i.revalidate()?;
        }
        self.mount_namespace()?;
        self.watchdog()
    }
    fn mount_namespace(&self) -> io::Result<()> {
        #[derive(serde::Deserialize)]
        #[serde(deny_unknown_fields)]
        struct Witness {
            schema: String,
            boot_id: String,
            joint_policy_sha256: String,
            device: u64,
            inode: u64,
        }
        let w: Witness =
            serde_json::from_slice(&self.inputs[6].bytes()?).map_err(io::Error::other)?;
        if w.schema != "droidloom.host-mount-identity.v1"
            || w.boot_id != self.boot_id
            || w.joint_policy_sha256 != self.config.joint_policy_sha256
        {
            return Err(reject(
                "mount identity is not from this source-bound original boot",
            ));
        }
        let actual = File::open("/proc/self/ns/mnt")?;
        filesystem(&actual, 0x6e736673)?;
        let m = actual.metadata()?;
        if (m.dev(), m.ino()) != (w.device, w.inode)
            || unsafe {
                libc::ioctl(
                    actual.as_raw_fd(),
                    0xb703 as libc::c_ulong,
                    0 as libc::c_ulong,
                )
            } != libc::CLONE_NEWNS
        {
            return Err(reject(
                "once return left the actual original mount namespace",
            ));
        }
        Ok(())
    }

    fn watchdog(&self) -> io::Result<()> {
        let sys = root_directory(Path::new("/sys"))?;
        filesystem(&sys, 0x62656572)?;
        // The exact selected softdog module declares its parameters with
        // sysfs permission 0: no /sys/module/softdog/parameters files exist.
        // Their values are bound by the admitted normal initrd and its exact
        // early helper invocation. Read the kernel's real watchdog attributes
        // here; never claim a readback of nonexistent parameter files.
        let base = Path::new("/sys/devices/virtual/watchdog");
        let parent = root_directory(base)?;
        let mut count = 0;
        let mut total = 0;
        for row in std::fs::read_dir(base)? {
            total += 1;
            if total > 16 {
                return Err(reject("virtual watchdog inventory exceeds bound"));
            }
            let row = row?;
            let name = row.file_name();
            let name = name
                .to_str()
                .ok_or_else(|| reject("invalid watchdog name"))?;
            let n = name
                .strip_prefix("watchdog")
                .ok_or_else(|| reject("unexpected watchdog child"))?;
            if n.is_empty() || n.len() > 3 || !n.bytes().all(|b| b.is_ascii_digit()) {
                return Err(reject("noncanonical watchdog number"));
            }
            let f = held::path_at(
                parent.as_raw_fd(),
                &CString::new(name).map_err(io::Error::other)?,
            )?;
            held::directory(&f)?;
            filesystem(&f, 0x62656572)?;
            if text(&row.path().join("identity"), 128)? == "Software Watchdog" {
                count += 1;
                if text(&row.path().join("state"), 32)? != "active"
                    || text(&row.path().join("nowayout"), 32)? != "1"
                    || text(&row.path().join("timeout"), 32)?
                        != self.config.recovery.schedule.watchdog_interval_seconds.to_string()
                {
                    return Err(reject("software watchdog is not actually armed"));
                }
            }
        }
        if count != 1 {
            return Err(reject("software watchdog identity is not unique"));
        }
        Ok(())
    }
}

impl Owner {
    fn exact_unit(&self) -> io::Result<()> {
        let expected = format!("0::/system.slice/{}", c::RETURN_UNIT);
        if text(Path::new("/proc/self/cgroup"), 8192)? != expected {
            return Err(reject("working return is outside its exact PID1-owned unit"));
        }
        let raw = include_bytes!("../../../packaging/systemd/system/droidloom-working-qualification-return.service");
        let source = Input::open(
            Path::new("/usr/lib/systemd/system/droidloom-working-qualification-return.service"),
            &PayloadPin { bytes: raw.len() as u64, sha256: hash(raw) },
            &[0o444], None,
        )?;
        if source.bytes()? != raw { return Err(reject("working return unit source changed")); }
        Ok(())
    }
    fn parent_retired(&self) -> io::Result<()> {
        let source = include_bytes!("../../../packaging/systemd/system/droidloom-working-qualification.service");
        let parent_source = Input::open(
            Path::new("/usr/lib/systemd/system/droidloom-working-qualification.service"),
            &PayloadPin { bytes: source.len() as u64, sha256: hash(source) },
            &[0o444], None,
        )?;
        if parent_source.bytes()? != source {
            return Err(reject("working parent source changed before normal return"));
        }
        let path = Path::new("/sys/fs/cgroup/system.slice").join(c::PARENT_UNIT);
        let parent = root_directory(path.parent().ok_or_else(|| reject("working cgroup parent absent"))?)?;
        filesystem(&parent, libc::CGROUP2_SUPER_MAGIC)?;
        let directory = match OpenOptions::new().read(true)
            .custom_flags(libc::O_DIRECTORY | libc::O_CLOEXEC | libc::O_NOFOLLOW)
            .open(&path) {
            Ok(value) => value,
            Err(e) if e.kind() == io::ErrorKind::NotFound => return Ok(()),
            Err(e) => return Err(e),
        };
        let before = Identity::from(directory.metadata()?);
        filesystem(&directory, libc::CGROUP2_SUPER_MAGIC)?;
        if before.uid != 0 || before.gid != 0 || before.mode & 0o022 != 0 {
            return Err(reject("working parent cgroup protection changed"));
        }
        let events = text(&path.join("cgroup.events"), 8192)?;
        let processes = text(&path.join("cgroup.procs"), 8192)?;
        retired_fields(&events, &processes)?;
        if Identity::from(directory.metadata()?) != before
            || Identity::from(std::fs::symlink_metadata(&path)?) != before {
            return Err(reject("working parent cgroup changed during retirement observation"));
        }
        parent_source.revalidate()?;
        Ok(())
    }
}
fn retired_fields(events: &str, processes: &str) -> io::Result<()> {
    let rows = events.lines().filter_map(|v| v.strip_prefix("populated ")).collect::<Vec<_>>();
    if rows != ["0"] || !processes.trim().is_empty() {
        return Err(reject("working parent or one of its descendants remains live"));
    }
    Ok(())
}
impl super::MaintenanceOwner for Owner {
    fn revalidate(&self) -> io::Result<()> { Owner::revalidate(self)?; self.parent_retired() }
    fn maintenance(&self) -> &Input { &self.inputs[2] }
    fn intent(&self) -> &str { &self.config.intent_sha256 }
    fn boot(&self) -> &str { &self.boot_id }
    fn command_schema(&self) -> &'static str { "droidloom.working-qualification-maintenance-command.v1" }
    fn incomplete_schema(&self) -> &'static str { "droidloom.working-qualification-incomplete-command.v1" }
}
fn remaining(end: Instant, maximum: u64) -> io::Result<u64> {
    let left = end.checked_duration_since(Instant::now())
        .ok_or_else(|| reject("working normal return exhausted its original end"))?.as_secs();
    if left == 0 { return Err(reject("working return has no complete command second")); }
    Ok(left.min(maximum))
}
pub(super) fn dispatch(args: &[OsString]) -> io::Result<bool> {
    let requested = args.first().is_some_and(|v| v == c::RETURN_MODE);
    let own = held::current(101).as_ref().is_ok_and(|v| v == ROLE);
    if !requested && !own { return Ok(false); }
    if !requested || args.len() != 1 || !own || held::current(104)? != PROFILE {
        return Err(reject("working return requires its distinct fixed argv and MAC entry"));
    }
    caps::seal()?;
    let owner = Owner::open()?;
    let schedule = c::WorkingSchedule::selected();
    let now = monotonic()?;
    if now >= schedule.normal_return_end_by_boot_seconds {
        return Err(reject("working return entered beyond its source-derived boot cap"));
    }
    let seconds = c::RETURN_SECONDS.min(schedule.normal_return_end_by_boot_seconds - now);
    let end = Instant::now() + Duration::from_secs(seconds);
    let evidence = Evidence::open_path(owner.config.runtime_evidence_directory(), EVIDENCE_LABEL)?;
    evidence.record("WORKING-RETURN-OBSERVED.json", json!({
        "schema":"droidloom.working-qualification-return-observed.v1",
        "intent_sha256":owner.config.intent_sha256,"candidate_id":owner.config.candidate_id,
        "first_once_candidate":owner.config.first_once_candidate,"boot_id":owner.boot_id,
        "original_boot_id":owner.config.original_boot_id,"monotonic":now,
        "actual_parent_tree_empty":true,"normal_return_seconds":seconds,
        "permanent_acceptance_granted":false,"production_ready":false
    }))?;
    // Collection has its original 90s ceiling; reserve the two unchanged
    // 30s maintenance operations within this same return end.
    let collection_budget = remaining(end, c::RETURN_SECONDS)?.saturating_sub(60)
        .min(u64::from(super::c::COLLECT_BUDGET_SECONDS));
    let collected = if collection_budget == u64::from(super::c::COLLECT_BUDGET_SECONDS) {
        let v = command(&owner, &evidence, "collect", collection_budget)?;
        let complete = normal_collection(&v, &owner.boot_id);
        evidence.record("WORKING-COLLECTION-OBSERVED.json", json!({
            "schema":"droidloom.working-qualification-collection-observed.v1",
            "boot_id":owner.boot_id,"normal_maintenance_collection_complete":complete,
            "ordinary_shutdown_verified":false,"production_ready":false
        }))?;
        complete
    } else {
        evidence.record("WORKING-COLLECTION-SKIPPED.json", json!({
            "schema":"droidloom.working-qualification-failed-collection.v1",
            "boot_id":owner.boot_id,"reason":"remaining original return window cannot fit the complete normal collector and rollback/reboot",
            "normal_maintenance_collection_complete":false,"production_ready":false
        }))?;
        false
    };
    owner.revalidate()?;
    owner.parent_retired()?;
    let rollback = command(&owner, &evidence, "rollback", remaining(end, 30)?)?;
    if !original_selected(&rollback) {
        return Err(reject("working maintenance did not read back the preserved original entry"));
    }
    evidence.record("WORKING-RETURN-SELECTED.json", json!({
        "schema":"droidloom.working-qualification-return-selected.v1",
        "intent_sha256":owner.config.intent_sha256,"boot_id":owner.boot_id,
        "normal_maintenance_collection_complete":collected,"maintenance":rollback,
        "original_return_observed":false,"production_ready":false
    }))?;
    let reboot = command(&owner, &evidence, "reboot", remaining(end, 30)?)?;
    if !original_reboot_requested(&reboot) {
        return Err(reject("working maintenance did not accept the exact original return request"));
    }
    evidence.record("WORKING-RETURN-REQUESTED.json", json!({
        "schema":"droidloom.working-qualification-return-requested.v1",
        "intent_sha256":owner.config.intent_sha256,"boot_id":owner.boot_id,
        "maintenance":reboot,"original_return_observed":false,
        "ordinary_shutdown_verified":false,"production_ready":false
    }))?;
    Ok(true)
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn working_return_requires_empty_whole_parent_group() {
        retired_fields("populated 0\nfrozen 0", "").unwrap();
        for (events, pids) in [("populated 1\nfrozen 0", ""),
            ("populated 0\npopulated 0", ""), ("frozen 0", ""),
            ("populated 0", "42\n")] {
            assert!(retired_fields(events, pids).is_err());
        }
    }
    #[test]
    fn working_return_cannot_be_selected_by_caller_argv_or_an_extra_path() {
        assert!(dispatch(&[c::RETURN_MODE.into()]).is_err());
        assert!(dispatch(&[c::RETURN_MODE.into(), "/tmp/return".into()]).is_err());
    }
}
