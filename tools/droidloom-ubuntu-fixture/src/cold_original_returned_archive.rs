//! Read-only validation of the exact normal runtime-evidence archive.
//! This is a historical observation; it cannot recreate OriginalRetirement.
use super::*;
use crate::cold_original_qualification::{
    retirement,
    returned_custody::{HeldDirectory as DirectoryFence, HeldFile, Records},
};
use std::collections::BTreeSet;

pub(in crate::cold_original_qualification) struct ArchivedRuntime {
    directories: Vec<DirectoryFence>,
    payloads: BTreeMap<String, HeldFile>,
    json: BTreeMap<String, Value>,
    records: Records,
}
fn pin(value: &Value) -> Result<FilePin> {
    Ok(serde_json::from_value(value.clone())?)
}
fn allowed_names() -> BTreeSet<String> {
    let mut names = BTreeSet::from([
        "CANDIDATE-OBSERVED.json".into(),
        "COLLECTION-OBSERVED.json".into(),
        "COLLECTION-SKIPPED.json".into(),
        "RETURN-SELECTED.json".into(),
        "RETURN-REQUESTED.json".into(),
    ]);
    for verb in ["collect", "rollback", "reboot"] {
        for suffix in [
            ".stdout",
            ".stderr",
            "-INTENT.json",
            "-RESULT.json",
            "-TIMEOUT.json",
        ] {
            names.insert(format!("{verb}{suffix}"));
        }
    }
    names
}
impl ArchivedRuntime {
    pub(in crate::cold_original_qualification) fn open(
        work: &Path,
        candidate: &str,
        configuration_pin: &FilePin,
        configuration: &Value,
        retirement_pin: &FilePin,
        retirement_report: &Value,
    ) -> Result<Self> {
        let birth = &configuration["actual_runtime_births"];
        ensure(
            birth["actual_retirement"] == serde_json::to_value(retirement_pin)?,
            "archived runtime births belong to another actual retirement",
        )?;
        let nodes: BTreeMap<PathBuf, Node> = serde_json::from_value(birth["members"].clone())?;
        let allowed = allowed_names();
        ensure(
            !nodes.is_empty() && nodes.len() <= allowed.len(),
            "bounded nonempty normal runtime archive required",
        )?;
        let root = Path::new("/var/lib/droidloom/qualification")
            .join(format!("original-once-{candidate}"))
            .join("runtime-evidence");
        let archive = work.join("runtime-evidence-archive");
        let archive_guard = DirectoryFence::open(&archive, 32)?;
        let expected_names = (0..nodes.len())
            .map(|n| format!("member-{n:02}"))
            .collect::<Vec<_>>();
        ensure(
            archive_guard.names_observed() == expected_names,
            "runtime archive member roster differs",
        )?;
        let mut result = Self {
            directories: vec![archive_guard],
            payloads: BTreeMap::new(),
            json: BTreeMap::new(),
            records: Records::new(),
        };
        let historical_rows = retirement_report["runtime_files"]
            .as_array()
            .ok_or("actual retirement runtime inventory absent")?;
        ensure(
            historical_rows.len() == nodes.len(),
            "retirement/archive full runtime counts differ",
        )?;
        let mut historical = BTreeMap::new();
        for row in historical_rows {
            let name = row["name"]
                .as_str()
                .ok_or("retirement runtime name absent")?;
            ensure(
                allowed.contains(name) && historical.insert(name.to_owned(), row).is_none(),
                "duplicate or unapproved retirement runtime member",
            )?;
        }
        for (ordinal, (logical, before)) in nodes.iter().enumerate() {
            ensure(
                logical.parent() == Some(root.as_path()),
                "runtime archive escaped the fixed candidate",
            )?;
            let name = logical
                .file_name()
                .and_then(|s| s.to_str())
                .ok_or("runtime archive name")?;
            ensure(
                allowed.contains(name)
                    && before.link.is_none()
                    && FileType::from_raw_mode(before.identity.mode) == FileType::RegularFile,
                "runtime archive is not a normal regular evidence member",
            )?;
            let row = historical
                .remove(name)
                .ok_or("archive runtime member was not actually retired")?;
            let old_pin = pin(&row["pin"])?;
            let old_identity: Identity = serde_json::from_value(row["identity"].clone())?;
            ensure(
                old_pin.path == *logical
                    && old_pin.bytes == before.identity.size
                    && before.sha256.as_deref() == Some(old_pin.sha256.as_str())
                    && only_ctime_difference(&old_identity, &before.identity),
                "runtime birth differs from its actual retired bytes or inode",
            )?;
            let record = archive.join(format!("member-{ordinal:02}"));
            let directory = DirectoryFence::open(&record, 3)?;
            ensure(
                directory.names_observed() == ["ARCHIVED.json", "INTENT.json", "payload"],
                "runtime archive transaction contains an incomplete or unknown member",
            )?;
            let payload = record.join("payload");
            let private = DirectoryFence::open(&payload, 1)?;
            ensure(
                private.names_observed() == ["evidence"],
                "runtime archive payload roster differs",
            )?;
            let target = payload.join("evidence");
            let intent_pin = files::pin_file(&record.join("INTENT.json"))?;
            let complete_pin = files::pin_file(&record.join("ARCHIVED.json"))?;
            let intent = result.records.read(&intent_pin, 32 * 1024 * 1024)?;
            let complete = result.records.read(&complete_pin, 32 * 1024 * 1024)?;
            ensure(
                intent["schema"] == "droidloom.original-once-runtime-archive-intent.v1"
                    && intent["configuration_source"] == serde_json::to_value(configuration_pin)?
                    && intent["actual_retirement"] == serde_json::to_value(retirement_pin)?
                    && intent["logical_path"] == serde_json::to_value(logical)?
                    && intent["expected"] == serde_json::to_value(before)?
                    && complete["schema"] == "droidloom.original-once-runtime-archived.v1"
                    && complete["configuration_source"] == serde_json::to_value(configuration_pin)?
                    && complete["logical_path"] == serde_json::to_value(logical)?
                    && complete["original"] == serde_json::to_value(before)?
                    && complete["destination"] == serde_json::to_value(&target)?
                    && complete["public_parent_before"] == intent["public_parent"]
                    && complete["private_parent_before"] == intent["private_parent"],
                "runtime archive lost its normal finite rename intent",
            )?;
            let after: Node = serde_json::from_value(complete["archived"].clone())?;
            let private_after: DirectoryState =
                serde_json::from_value(complete["private_parent_after"].clone())?;
            ensure(
                private_after.path == payload
                    && same_except_ctime(&after, before)
                    && observe(logical)?.is_none()
                    && observe(&target)?.as_ref() == Some(&after),
                "runtime archive has a changed inode, body or unknown public placement",
            )?;
            private_after.reopen()?;
            let file = HeldFile::open(
                &FilePin {
                    path: target,
                    bytes: old_pin.bytes,
                    sha256: old_pin.sha256,
                },
                64 * 1024 * 1024,
                Some(0o400),
                true,
            )?;
            ensure(
                file.identity() == &after.identity,
                "archive held payload is another inode",
            )?;
            if name.ends_with(".json") {
                result
                    .json
                    .insert(name.into(), file.json(64 * 1024 * 1024)?);
            }
            ensure(
                result.payloads.insert(name.into(), file).is_none(),
                "runtime archive aliases one member twice",
            )?;
            result.directories.extend([directory, private]);
        }
        ensure(
            historical.is_empty(),
            "actual runtime retirement has unarchived members",
        )?;
        result.guard()?;
        Ok(result)
    }

    fn command(&self, verb: &str, intent: &str, boot: &str) -> Result<Value> {
        let result = self
            .json
            .get(&format!("{verb}-RESULT.json"))
            .ok_or("normal maintenance result absent")?;
        let start = self
            .json
            .get(&format!("{verb}-INTENT.json"))
            .ok_or("normal maintenance intent absent")?;
        ensure(
            result["schema"] == "droidloom.original-once-maintenance-command.v1"
                && result["intent_sha256"] == intent
                && result["boot_id"] == boot
                && result["verb"] == verb
                && start["intent_sha256"] == intent
                && start["boot_id"] == boot
                && start["verb"] == verb
                && result["completed"] == true
                && result["exit_code"] == 0
                && !self.payloads.contains_key(&format!("{verb}-TIMEOUT.json")),
            "incomplete, timed out or foreign normal maintenance command",
        )?;
        for suffix in ["stdout", "stderr"] {
            let output = self
                .payloads
                .get(&format!("{verb}.{suffix}"))
                .ok_or("normal maintenance stream absent")?;
            ensure(
                result[suffix]["bytes"] == output.pin().bytes
                    && result[suffix]["sha256"] == output.pin().sha256,
                "normal maintenance stream differs from its actual command result",
            )?;
        }
        self.payloads[&format!("{verb}.stdout")].json(64 * 1024 * 1024)
    }
    pub(in crate::cold_original_qualification) fn verify_normal_return(
        &self,
        candidate: &str,
        intent: &FilePin,
        admitted_boot: &str,
        candidate_boot: &str,
        actual: &Value,
    ) -> Result<()> {
        self.guard()?;
        let observed = self
            .json
            .get("CANDIDATE-OBSERVED.json")
            .ok_or("candidate boot observation absent")?;
        ensure(
            observed["schema"] == "droidloom.original-once-candidate-observed.v1"
                && observed["candidate_id"] == candidate
                && observed["intent_sha256"] == intent.sha256
                && observed["original_boot_id"] == admitted_boot
                && observed["boot_id"] == candidate_boot,
            "archived candidate observation belongs to another actual boot",
        )?;
        let collect = self.command("collect", &intent.sha256, candidate_boot)?;
        let rollback = self.command("rollback", &intent.sha256, candidate_boot)?;
        let reboot = self.command("reboot", &intent.sha256, candidate_boot)?;
        ensure(
            retirement::normal_chain_outputs(
                &collect,
                &rollback,
                &reboot,
                &self.json,
                &intent.sha256,
                candidate_boot,
                actual,
            )?,
            "archived commands and trusted PID1 history do not prove a normal return",
        )?;
        self.guard()
    }
    pub(in crate::cold_original_qualification) fn guard(&self) -> Result<()> {
        self.records.guard()?;
        for d in &self.directories {
            d.guard()?;
        }
        for p in self.payloads.values() {
            p.guard_custody()?;
        }
        Ok(())
    }
    pub(in crate::cold_original_qualification) fn payload_pins(&self) -> Vec<&FilePin> {
        self.payloads.values().map(HeldFile::pin).collect()
    }
}
fn only_ctime_difference(before: &Identity, after: &Identity) -> bool {
    let mut adjusted = after.clone();
    adjusted.ctime_sec = before.ctime_sec;
    adjusted.ctime_nsec = before.ctime_nsec;
    adjusted == *before
}
