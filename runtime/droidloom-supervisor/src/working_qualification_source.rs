//! Comparison records for the fixed working-qualification source publication.
//!
//! None of these deserializable records is Main, source-owner, execution or
//! production authority. Only InitialWorkingSource, created from the actual
//! boot/unit/watchdog/Main owners, may publish the normal v2 pair.
use super::{UnitOwner, boot::BootOwner, watchdog};
use crate::control::{MainCustodyObservation, application_probe::RuntimeEpoch};
use crate::native_working_contract as c;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{
    path::{Component, Path, PathBuf},
    time::{SystemTime, UNIX_EPOCH},
};

pub(super) fn require(value: bool, why: &str) -> Result<(), String> {
    if value { Ok(()) } else { Err(why.into()) }
}
fn hash(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

/// Read-only comparison of the PID1 and kernel identities retained by UnitOwner.
#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct WorkingUnitIdentity {
    pub unit: String,
    pub invocation: String,
    pub parent_pid: u32,
    pub parent_start_ticks: u64,
    pub cgroup: String,
    pub cgroup_identity: [u64; 5],
    pub owner_start_monotonic_ns: u64,
}
impl WorkingUnitIdentity {
    pub fn validate(&self) -> Result<(), String> {
        require(
            self.unit == c::PARENT_UNIT
                && self.cgroup == format!("/sys/fs/cgroup/system.slice/{}", c::PARENT_UNIT)
                && self.invocation.len() == 32
                && self
                    .invocation
                    .bytes()
                    .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
                && (2..=i32::MAX as u32).contains(&self.parent_pid)
                && self.parent_start_ticks > 0
                && self.cgroup_identity[0] > 0
                && self.cgroup_identity[1] > 0
                && self.cgroup_identity[2] & 0o170000 == 0o040000
                && self.cgroup_identity[2] & 0o022 == 0
                && self.cgroup_identity[3..5] == [0, 0],
            "working source owner is not the fixed root singleton comparison",
        )?;
        c::WorkingSchedule::selected()
            .authorization_end_ns(self.owner_start_monotonic_ns)
            .map(|_| ())
            .map_err(|e| e.to_string())
    }
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct WorkingProgramPin {
    pub bytes: u64,
    pub sha256: String,
}
impl WorkingProgramPin {
    fn validate(&self) -> Result<(), String> {
        require(
            self.bytes > 0 && self.bytes <= 128 * 1024 * 1024 && c::digest(&self.sha256),
            "bounded normal working program identity required",
        )
    }
}

/// The original wall sample fixes only the source lease's human UTC expiry.
/// Working authorization always also requires the unchanged kernel monotonic
/// end. A later wall clock or new case never renews this initial owner.
#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct WorkingSourceOrigin {
    pub schema: String,
    pub candidate_id: String,
    pub first_once_candidate: String,
    pub boot_id: String,
    pub source_commit: String,
    pub source_tree: String,
    pub admitted_materials_sha256: String,
    pub joint_policy_sha256: String,
    pub applications: WorkingProgramPin,
    pub selected_configuration: WorkingProgramPin,
    pub cell_configuration: WorkingProgramPin,
    pub unit: WorkingUnitIdentity,
    pub original_end_monotonic_ns: u64,
    pub lease_sample_monotonic_ns: u64,
    pub lease_sample_unix_seconds: u64,
    pub owner_expires_unix_seconds: u64,
    pub main_epoch: RuntimeEpoch,
    pub main_custody_sha256: String,
}
fn lease_expiry(sample_ns: u64, wall: u64, end_ns: u64) -> Result<u64, String> {
    let left = end_ns
        .checked_sub(sample_ns)
        .filter(|v| *v > 0)
        .ok_or("initial working lease sample is outside its original end")?;
    wall.checked_add(left.div_ceil(1_000_000_000))
        .and_then(|v| v.checked_add(c::budget::RETIREMENT_SECONDS))
        .ok_or_else(|| "initial working lease expiry overflow".into())
}
pub fn utc_text(seconds: u64) -> Result<String, String> {
    require(
        seconds < 253_402_300_800,
        "working lease UTC is outside the fixed calendar bound",
    )?;
    let mut days = seconds / 86400;
    let mut year = 1970u64;
    loop {
        let leap = year % 4 == 0 && (year % 100 != 0 || year % 400 == 0);
        let count = if leap { 366 } else { 365 };
        if days < count {
            break;
        }
        days -= count;
        year += 1;
    }
    let leap = year % 4 == 0 && (year % 100 != 0 || year % 400 == 0);
    let months = [
        31,
        if leap { 29 } else { 28 },
        31,
        30,
        31,
        30,
        31,
        31,
        30,
        31,
        30,
        31,
    ];
    let mut month = 0;
    while days >= months[month] {
        days -= months[month];
        month += 1;
    }
    let time = seconds % 86400;
    Ok(format!(
        "{year:04}-{:02}-{:02}T{:02}:{:02}:{:02}Z",
        month + 1,
        days + 1,
        time / 3600,
        time % 3600 / 60,
        time % 60
    ))
}
#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct WorkingForegroundOwner {
    pub acquisition: String,
    pub acquisition_id: String,
    pub active_until_utc: String,
    pub generation: String,
    pub name: String,
    pub scope: String,
}
impl WorkingSourceOrigin {
    pub(super) fn capture(
        boot: &BootOwner,
        unit: &UnitOwner,
        main: &MainCustodyObservation,
        original_end_ns: u64,
    ) -> Result<Self, String> {
        boot.compare_main(main).map_err(|e| e.to_string())?;
        let identity = unit.working_identity()?;
        let sample_ns = watchdog::monotonic_ns().map_err(|e| e.to_string())?;
        let wall = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map_err(|e| e.to_string())?
            .as_secs();
        let config = boot.config();
        let copy = |p: &c::PayloadPin| WorkingProgramPin {
            bytes: p.bytes,
            sha256: p.sha256.clone(),
        };
        let result = Self {
            schema: "droidloom.working-source-owner.v1".into(),
            candidate_id: config.candidate_id.clone(),
            first_once_candidate: config.first_once_candidate.clone(),
            boot_id: boot.boot_id().into(),
            source_commit: config.host_source_commit.clone(),
            source_tree: config.host_source_tree.clone(),
            admitted_materials_sha256: config.admitted_materials_sha256.clone(),
            joint_policy_sha256: config.joint_policy_sha256.clone(),
            applications: copy(&config.applications),
            selected_configuration: copy(&config.selection),
            cell_configuration: copy(&config.cell),
            unit: identity,
            original_end_monotonic_ns: original_end_ns,
            lease_sample_monotonic_ns: sample_ns,
            lease_sample_unix_seconds: wall,
            owner_expires_unix_seconds: lease_expiry(sample_ns, wall, original_end_ns)?,
            main_epoch: main.facts().epoch.clone(),
            main_custody_sha256: hash(
                &serde_json::to_vec(main.facts()).map_err(|e| e.to_string())?,
            ),
        };
        result.validate()?;
        boot.compare_main(main).map_err(|e| e.to_string())?;
        Ok(result)
    }
    pub fn validate(&self) -> Result<(), String> {
        self.unit.validate()?;
        self.applications.validate()?;
        self.selected_configuration.validate()?;
        self.cell_configuration.validate()?;
        require(
            self.schema == "droidloom.working-source-owner.v1"
                && c::digest(&self.candidate_id)
                && c::digest(&self.first_once_candidate)
                && self.candidate_id != self.first_once_candidate
                && c::uuid(&self.boot_id)
                && c::commit(&self.source_commit)
                && c::commit(&self.source_tree)
                && c::digest(&self.admitted_materials_sha256)
                && c::digest(&self.joint_policy_sha256)
                && c::digest(&self.main_custody_sha256)
                && self.main_epoch.boot_id == self.boot_id
                && self.main_epoch.cell_host_pid > 1
                && self.main_epoch.framework_host_pid > 1
                && self.main_epoch.framework_start_ticks > 0,
            "working source origin does not describe one source-bound fresh boot",
        )?;
        let end = c::WorkingSchedule::selected()
            .authorization_end_ns(self.unit.owner_start_monotonic_ns)
            .map_err(|e| e.to_string())?;
        require(
            self.original_end_monotonic_ns == end
                && self.lease_sample_monotonic_ns >= self.unit.owner_start_monotonic_ns
                && self.owner_expires_unix_seconds
                    == lease_expiry(
                        self.lease_sample_monotonic_ns,
                        self.lease_sample_unix_seconds,
                        end,
                    )?,
            "working source record extended or replaced its original owner window",
        )?;
        utc_text(self.owner_expires_unix_seconds)?;
        Ok(())
    }
    pub fn foreground_owner(&self) -> Result<WorkingForegroundOwner, String> {
        self.validate()?;
        Ok(WorkingForegroundOwner {
            acquisition: "normal-returned-working-copy-qualification".into(),
            acquisition_id: self.unit.invocation.clone(),
            active_until_utc: utc_text(self.owner_expires_unix_seconds)?,
            generation: self.candidate_id.clone(),
            name: "droidloom-working-qualification".into(),
            scope: format!(
                "candidate={};boot={};unit={}",
                self.candidate_id, self.boot_id, self.unit.unit
            ),
        })
    }
    /// Compare a separate real opaque observation; this never builds Main from
    /// the serialized epoch or hash in a detached source record.
    pub fn matches_main(&self, main: &MainCustodyObservation) -> Result<(), String> {
        self.validate()?;
        require(
            main.facts().epoch == self.main_epoch
                && hash(&serde_json::to_vec(main.facts()).map_err(|e| e.to_string())?)
                    == self.main_custody_sha256,
            "actual opaque Main differs from the initial working source owner",
        )
    }
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct WorkingSourceFilePin {
    pub path: PathBuf,
    pub bytes: u64,
    pub sha256: String,
}
impl WorkingSourceFilePin {
    pub fn validate(&self, limit: u64) -> Result<(), String> {
        require(
            self.path.is_absolute()
                && self.path.to_str().is_some_and(|s| {
                    s.starts_with('/')
                        && !s.contains('\0')
                        && s[1..]
                            .split('/')
                            .all(|p| !p.is_empty() && p != "." && p != "..")
                })
                && self
                    .path
                    .components()
                    .all(|v| matches!(v, Component::RootDir | Component::Normal(_)))
                && self.bytes > 0
                && self.bytes <= limit
                && c::digest(&self.sha256),
            "working source requires a canonical bounded file pin",
        )
    }
}
#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct WorkingCurrentPreimage {
    pub path: PathBuf,
    pub bytes: u64,
    pub sha256: String,
    pub f9: [u64; 9],
}

/// v2 retains the actual whole CURRENT preimage. It replaces the legacy CI
/// identity fields with the normal installed boot/unit/Main origin above; it
/// does not invent a CI run or a CI success count.
#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct WorkingLeafManifest {
    pub schema: String,
    pub protocol: String,
    pub binary: WorkingSourceFilePin,
    pub selection: WorkingSourceFilePin,
    pub catalog: WorkingSourceFilePin,
    pub foreground_owner: WorkingForegroundOwner,
    pub owner_expires_unix_seconds: u64,
    pub before_current: WorkingCurrentPreimage,
    pub before_current_copy: WorkingSourceFilePin,
    pub source_tree: String,
    pub source_commit: String,
    pub working_owner: WorkingSourceOrigin,
    pub runtime_qualified: bool,
    pub production_ready: bool,
}
impl WorkingLeafManifest {
    pub fn validate(&self) -> Result<(), String> {
        self.working_owner.validate()?;
        self.binary.validate(64 * 1024 * 1024)?;
        self.selection.validate(1024 * 1024)?;
        self.catalog.validate(65536)?;
        self.before_current_copy.validate(2 * 1024 * 1024)?;
        require(
            self.schema == "pocket4-native-application-leaf-release-v2"
                && self.protocol == "droidloom-gallery-image-custody-v1"
                && !self.runtime_qualified
                && !self.production_ready
                && self.binary.path == Path::new(c::APPLICATIONS_EXECUTABLE)
                && self.binary.bytes == self.working_owner.applications.bytes
                && self.binary.sha256 == self.working_owner.applications.sha256
                && self.source_commit == self.working_owner.source_commit
                && self.source_tree == self.working_owner.source_tree
                && self.owner_expires_unix_seconds == self.working_owner.owner_expires_unix_seconds
                && self.foreground_owner == self.working_owner.foreground_owner()?,
            "working source manifest differs from its actual normal source owner comparison",
        )?;
        let root = "/etc/droidloom/native-application-leaves";
        require(
            self.catalog.path
                == PathBuf::from(format!("{root}/catalogs/{}.json", self.catalog.sha256))
                && self.before_current_copy.path
                    == PathBuf::from(format!(
                        "{root}/current-preimages/{}.json",
                        self.before_current_copy.sha256
                    ))
                && self.before_current.path
                    == Path::new("/home/alex/work/pocket4-android-final/CONTINUATION_CURRENT.json")
                && self.before_current.f9[2..6] == [0o100600, 1000, 1000, 1]
                && self.before_current.bytes == self.before_current_copy.bytes
                && self.before_current.sha256 == self.before_current_copy.sha256
                && self.before_current.f9[6] == self.before_current.bytes,
            "working source must preserve the actual complete CURRENT preimage",
        )?;
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn initial_source_utc_and_monotonic_lease_are_finite_and_not_renewed() {
        assert_eq!(utc_text(0).unwrap(), "1970-01-01T00:00:00Z");
        assert_eq!(utc_text(951_782_400).unwrap(), "2000-02-29T00:00:00Z");
        assert_eq!(utc_text(2_147_483_647).unwrap(), "2038-01-19T03:14:07Z");
        assert!(utc_text(253_402_300_800).is_err());
        assert_eq!(lease_expiry(20, 100, 1_000_000_021).unwrap(), 282);
        assert!(lease_expiry(30, 100, 30).is_err());
        assert!(lease_expiry(31, 100, 30).is_err());
        assert!(lease_expiry(1, u64::MAX, 2).is_err());
    }
}
