//! A separate, finite H2 label freezer. Only the observed fixed writer groups
//! are frozen, and the normal producer starts its independent working thaw
//! unit before the first cgroup write. No original-once authority is created.
use super::{
    FreezeIntent, FreezePurpose, Group, MAX_SECONDS, Quiescence, SealedInput, ThawCleanup, bounded,
    clock_ms, inventory_groups_for_units, starttime,
};
use crate::{
    Result,
    boot_files::{self as files, FilePin},
    cold_original_qualification::{
        PublishedWorkingBootFiles, WorkingLabelSourceIdentity, WorkingRuntimeSources, owner,
        working_packages::WorkingPackages,
    },
    ensure, fs,
};
use serde_json::{Value, json};
use std::{
    fs::File,
    path::Path,
    time::{Duration, Instant},
};

fn inventory_groups(
    value: &Value,
    candidate: &str,
) -> Result<(Vec<(String, String)>, Vec<String>)> {
    inventory_groups_for_units(
        value,
        &format!("droidloom-working-cold@{candidate}.service"),
        &format!("droidloom-working-thaw@{candidate}.service"),
        "no",
    )
}

pub(crate) struct WorkingQuiescence {
    source: WorkingLabelSourceIdentity,
    core: Quiescence,
}
impl WorkingQuiescence {
    pub(in crate::cold_original_qualification) fn begin(
        boot: &PublishedWorkingBootFiles,
        packages: &mut WorkingPackages,
    ) -> Result<Self> {
        boot.guard()?;
        packages.verify_installed()?;
        let source = boot.runtime().source();
        ensure(
            source.pair_exchanged(boot.runtime())?,
            "working freezer requires the actual exchanged data pair",
        )?;
        let observed = source.current_owner_evidence()?;
        ensure(
            observed["schema"] == "droidloom.working-qualification-cold-owner.v1"
                && observed["candidate_id"] == source.candidate(),
            "working freezer lost its actual distinct owner",
        )?;
        let invocation = observed["actual_original"]["invocation_id"]
            .as_str()
            .ok_or("working freezer invocation absent")?
            .to_owned();
        let owner_group = format!(
            "/system.slice/droidloom-working-cold@{}.service",
            source.candidate()
        );
        ensure(
            invocation.len() == 32
                && invocation.bytes().all(|b| b.is_ascii_hexdigit())
                && observed["actual_original"]["control_group"] == owner_group,
            "working freezer actual unit identity differs",
        )?;
        let (inventory, inventory_pin) = packages.freeze_inventory()?;
        let unit = format!("droidloom-working-cold@{}.service", source.candidate());
        let actual_owner = inventory["units"]
            .as_array()
            .ok_or("actual units absent")?
            .iter()
            .filter(|row| row["RequestedId"] == unit)
            .collect::<Vec<_>>();
        ensure(
            actual_owner.len() == 1
                && actual_owner[0]["MainPID"] == std::process::id().to_string()
                && actual_owner[0]["InvocationID"] == invocation
                && actual_owner[0]["DropInPaths"] == "",
            "PID1 working writer inventory belongs to another owner or override",
        )?;
        let (paths, remote) = inventory_groups(&inventory, source.candidate())?;
        let groups = paths
            .iter()
            .map(|(p, u)| Group::open(p, u))
            .collect::<Result<Vec<_>>>()?;
        for group in &groups {
            ensure(
                !group.is_frozen()? && bounded(&group.freeze, 16)?.trim() == "0",
                "a pre-existing freezer request cannot become this owner's undo",
            )?;
        }
        let base: Value =
            serde_json::from_slice(&files::read_pin(source.boot_intent(), 16 * 1024 * 1024)?)?;
        let producer: FilePin = serde_json::from_value(base["normal_producer"].clone())?;
        ensure(
            base["schema"] == "droidloom.working-qualification-boot-intent.v1"
                && base["candidate_id"] == source.candidate()
                && base["original_boot_id"] == source.configuration().original_boot_id
                && observed["actual_producer"] == serde_json::to_value(&producer)?,
            "working thaw producer is outside its actual normal boot source",
        )?;
        let running = File::open("/proc/self/exe")?;
        let (_, executable_identity) = files::open_pin(&producer)?;
        ensure(
            fs::stat(&running)? == executable_identity && fs::hash(&running)? == producer.sha256,
            "working freezer is not the retained actual normal producer",
        )?;
        let deadline = clock_ms()?
            .checked_add(MAX_SECONDS * 1000)
            .ok_or("working freezer deadline overflow")?;
        let intent = FreezeIntent {
            schema: "droidloom.working-freeze-intent.v1".into(),
            candidate_id: source.candidate().into(),
            original_boot_id: source.configuration().original_boot_id.clone(),
            admitted_original_boot_id: source.configuration().original_boot_id.clone(),
            owner_invocation: invocation.clone(),
            purpose: FreezePurpose::Forward,
            base_intent: source.boot_intent().clone(),
            producer: producer.clone(),
            owner_pid: std::process::id(),
            owner_starttime: starttime(std::process::id())?,
            owner_control_group: owner_group,
            deadline_boot_ms: deadline,
            inventory: inventory_pin,
            groups: groups
                .iter()
                .map(|g| {
                    serde_json::from_value(serde_json::to_value(&g.record)?).map_err(Into::into)
                })
                .collect::<Result<_>>()?,
            excluded_remote_scopes: remote,
            critical_excluded: inventory["critical_excluded"]
                .as_array()
                .ok_or("working critical exclusions absent")?
                .iter()
                .map(|v| {
                    v.as_str()
                        .map(str::to_owned)
                        .ok_or_else(|| "critical exclusion string".into())
                })
                .collect::<Result<_>>()?,
        };
        let directory = source
            .work()
            .join(format!("working-quiescence-forward-{invocation}"));
        files::private_dir(&directory)?;
        let path = directory.join("FREEZE-INTENT.json");
        files::write_new(&path, &serde_json::to_vec(&intent)?, 0o400)?;
        File::open(&directory)?.sync_all()?;
        let pin = files::pin_file(&path)?;
        packages.start_thaw_guard(&producer, &pin)?;
        let until = Instant::now() + Duration::from_secs(15);
        let ready = directory.join("READY.json");
        while !ready.exists() {
            ensure(
                Instant::now() < until,
                "actual working thaw guard did not become ready",
            )?;
            std::thread::sleep(Duration::from_millis(50));
        }
        let ready = SealedInput::open(&files::pin_file(&ready)?)?;
        let actual: Value = serde_json::from_slice(&ready.read()?)?;
        ensure(
            actual["schema"] == "droidloom.working-thaw-ready.v1"
                && actual["freeze_intent"] == serde_json::to_value(&pin)?
                && actual["candidate_id"] == source.candidate(),
            "working thaw readiness belongs to another actual intent",
        )?;
        let reaper_pid: u32 = actual["pid"]
            .as_u64()
            .ok_or("working thaw PID")?
            .try_into()?;
        let reaper_starttime = actual["starttime"]
            .as_u64()
            .ok_or("working thaw start time")?;
        let reaper_pidfd = rustix::process::pidfd_open(
            rustix::process::Pid::from_raw(reaper_pid as i32).ok_or("working thaw PID range")?,
            rustix::process::PidfdFlags::empty(),
        )?;
        ensure(
            starttime(reaper_pid)? == reaper_starttime,
            "actual working thaw process changed",
        )?;
        let value = Self {
            source: source.label_source_identity()?,
            core: Quiescence {
                candidate: source.candidate().into(),
                purpose: FreezePurpose::Forward,
                intent: SealedInput::open(&pin)?,
                groups,
                deadline,
                reaper_pid,
                reaper_starttime,
                reaper_pidfd,
                reaper_exe: serde_json::from_value(actual["executable"].clone())?,
                reaper_namespaces: serde_json::from_value(actual["namespaces"].clone())?,
                finished: false,
            },
        };
        value.core.verify_guard()?;
        // The wrapper's Drop always attempts every original-zero group and a
        // durable release, including a failure after only a prefix was frozen.
        for group in &value.core.groups {
            group.set(true)?;
            value.core.verify_guard()?;
        }
        value.verify()?;
        boot.guard()?;
        files::write_new(
            &directory.join("FROZEN.json"),
            &serde_json::to_vec(&json!({
                "schema":"droidloom.working-frozen.v1","freeze_intent":pin,
                "deadline_boot_ms":deadline,
                "actual_frozen":value.core.groups.iter().map(|g|&g.record.path).collect::<Vec<_>>()
            }))?,
            0o400,
        )?;
        File::open(&directory)?.sync_all()?;
        Ok(value)
    }
    pub(crate) fn require_source(&self, source: &WorkingRuntimeSources) -> Result<()> {
        self.source.require_source(source)?;
        self.verify()
    }
    pub(crate) fn verify(&self) -> Result<()> {
        self.source.revalidate_normal_source()?;
        self.core.verify_forward()
    }
    pub(crate) fn deadline_boot_ms(&self) -> u64 {
        self.core.deadline
    }
    fn release(&mut self) -> Result<()> {
        if self.core.finished {
            return Ok(());
        }
        self.core.intent.revalidate_custody()?;
        let mut failures = Vec::new();
        for group in self.core.groups.iter().rev() {
            if let Err(error) = group.set(false) {
                failures.push(format!("{}: {error}", group.record.path));
            }
        }
        ensure(
            failures.is_empty(),
            &format!("working thaw remains incomplete: {failures:?}"),
        )?;
        let directory = self
            .core
            .intent
            .pin()
            .path
            .parent()
            .ok_or("working freeze parent")?;
        let path = directory.join("RELEASED.json");
        let body = json!({"schema":"droidloom.working-freeze-released.v1",
            "freeze_intent":self.core.intent.pin(),
            "actual_thawed":self.core.groups.iter().map(|g|&g.record.path).collect::<Vec<_>>()});
        match std::fs::symlink_metadata(&path) {
            Ok(_) => {
                let read = SealedInput::open(&files::pin_file(&path)?)?;
                ensure(
                    serde_json::from_slice::<Value>(&read.read()?)? == body,
                    "working freezer release has another source or group set",
                )?;
            }
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
                files::write_new(&path, &serde_json::to_vec(&body)?, 0o400)?
            }
            Err(error) => return Err(error.into()),
        }
        File::open(directory)?.sync_all()?;
        self.core.finished = true;
        Ok(())
    }
    pub(crate) fn finish(&mut self) -> Result<()> {
        self.release()
    }
}
impl Drop for WorkingQuiescence {
    fn drop(&mut self) {
        if let Err(error) = self.release() {
            eprintln!("working freezer release remains unconfirmed: {error}");
        }
    }
}

pub(in crate::cold_original_qualification) fn run_thaw_guard(
    config: &Path,
    expected: &str,
) -> Result<()> {
    let pin = files::pin_file(config)?;
    ensure(pin.sha256 == expected, "thaw config hash differs")?;
    let sealed = SealedInput::open(&pin)?;
    let v: FreezeIntent = serde_json::from_slice(&sealed.read()?)?;
    ensure(
        v.schema == "droidloom.working-freeze-intent.v1"
            && v.purpose == FreezePurpose::Forward
            && fs::valid_digest(&v.candidate_id)
            && config
                == Path::new("/var/lib/droidloom-qualification").join(format!(
                    "working-qualification-{}/working-quiescence-{}-{}/FREEZE-INTENT.json",
                    v.candidate_id,
                    v.purpose.name(),
                    v.owner_invocation
                ))
            && v.owner_control_group
                == format!(
                    "/system.slice/droidloom-working-cold@{}.service",
                    v.candidate_id
                )
            && v.owner_invocation.len() == 32
            && v.owner_invocation.bytes().all(|b| b.is_ascii_hexdigit())
            && v.groups.len() <= 64
            && !v.groups.is_empty(),
        "thaw intent scope differs",
    )?;
    let thaw_owner = owner::verify_working_thaw_owner(&v.candidate_id, &v.original_boot_id)?;
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
        base_value["schema"] == "droidloom.working-qualification-boot-intent.v1"
            && base_value["candidate_id"] == v.candidate_id
            && base_value["original_boot_id"] == v.admitted_original_boot_id
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
    let mut cleanup = ThawCleanup::new(groups, directory, &pin)?;
    cleanup.schema = "droidloom.working-thaw-result.v1";
    let monitored = (|| -> Result<&'static str> {
        files::write_new(
            &directory.join("READY.json"),
            &serde_json::to_vec(
                &json!({"schema":"droidloom.working-thaw-ready.v1","candidate_id":v.candidate_id,"freeze_intent":pin,
            "pid":std::process::id(),"starttime":starttime(std::process::id())?,"deadline_boot_ms":v.deadline_boot_ms,
            "executable":fs::stat(&exe)?,"namespaces":thaw_owner["namespaces"]}),
            )?,
            0o400,
        )?;
        File::open(directory)?.sync_all()?;
        let reason = loop {
            sealed.revalidate_custody()?;
            base.revalidate_custody()?;
            inventory.revalidate_custody()?;
            owner::verify_working_thaw_owner(&v.candidate_id, &v.original_boot_id)?;
            ensure(
                fs::stat(&exe)? == source,
                "guard executable identity changed",
            )?;
            if directory.join("RELEASED.json").exists() {
                let release =
                    SealedInput::open(&files::pin_file(&directory.join("RELEASED.json"))?)?;
                let actual: Value = serde_json::from_slice(&release.read()?)?;
                ensure(
                    actual["freeze_intent"] == serde_json::to_value(&pin)?
                        && cleanup
                            .groups
                            .iter()
                            .all(|g| g.is_frozen().is_ok_and(|x| !x)),
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
        sealed.revalidate()?;
        base.revalidate()?;
        inventory.revalidate()?;
        ensure(
            fs::stat(&exe)? == source
                && fs::hash(&exe)? == v.producer.sha256
                && fs::stat(&exe)? == source,
            "guard source changed during frozen window",
        )?;
        Ok(reason)
    })();
    let reason = monitored
        .as_ref()
        .copied()
        .unwrap_or("guard-validation-failed");
    let cause = monitored.as_ref().err().map(ToString::to_string);
    // Always try every exact held group before propagating any observer error.
    // Durable reporting uses the held private directory, never a replacement.
    let thaw = cleanup.finish(reason, cause.as_deref());
    let stop_owner = matches!(reason, "deadline" | "guard-validation-failed")
        && starttime(v.owner_pid).ok() == Some(v.owner_starttime);
    let stop: Result<()> = if stop_owner {
        rustix::process::pidfd_send_signal(&owner_fd, rustix::process::Signal::KILL)
            .map_err(Into::into)
    } else {
        Ok(())
    };
    if let Err(e) = monitored {
        if let Err(t) = &thaw {
            eprintln!("working thaw recovery error: {t}");
        }
        if let Err(t) = &stop {
            eprintln!("working held-owner termination error: {t}");
        }
        return Err(e);
    }
    thaw?;
    stop?;
    Ok(())
}
