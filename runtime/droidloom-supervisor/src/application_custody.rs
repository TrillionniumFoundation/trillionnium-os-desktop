//! Observations returned by the owned production image-inspection path.
//!
//! These serializable values are evidence, never namespace, mount, execution,
//! data-migration, or release authority. No request accepts them as a permit.
//! The producer borrows the original Ready owner and uses its held resources.
use std::collections::BTreeSet;

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

use super::application_probe::{AndroidProbe, ApplicationInspection, RuntimeEpoch};

pub(crate) const GALLERY_PACKAGE: &str = "com.android.gallery3d";
pub(crate) const GALLERY_BYTES: u64 = 7_390_425;
pub(crate) const GALLERY_SHA256: &str =
    "835fe119745324276457b4434fc39f25b633e752c822d2fc9be40eb4b2d45439";
pub(crate) const SYSTEM_BYTES: u64 = 2_294_853_632;
pub(crate) const SYSTEM_SHA256: &str =
    "dc781249bb4724b7a0777e5077321b84576db46f61abb4b9086b81077bfd0ab4";
pub(crate) const GALLERY_SOURCE_PATH: &str = "/system/product/app/Gallery2/Gallery2.apk";
pub(crate) const GALLERY_PM_PATHS: [&str; 2] = [
    GALLERY_SOURCE_PATH,
    "/product/app/Gallery2/Gallery2.apk",
];

/// Actual kernel metadata of one held regular file, directory, or loop node.
#[derive(Clone, Copy, Debug, Deserialize, Serialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct CustodyFileIdentity {
    pub device: u64,
    pub inode: u64,
    pub mode: u32,
    pub uid: u32,
    pub gid: u32,
    pub links: u64,
    pub bytes: u64,
    pub modified: (i64, i64),
    pub changed: (i64, i64),
}

/// One original namespace descriptor, observed through the same Ready owner.
#[derive(Clone, Debug, Deserialize, Serialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct CustodyNamespace {
    pub name: String,
    pub device: u64,
    pub inode: u64,
}

/// Fresh whole-body hash plus the actual bound loop and mounted filesystem.
#[derive(Clone, Debug, Deserialize, Serialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct CustodyImage {
    pub role: String,
    pub path: String,
    pub file: CustodyFileIdentity,
    pub sha256: String,
    pub loop_node: CustodyFileIdentity,
    pub loop_device: u64,
    pub loop_number: u32,
    pub loop_source_device: u64,
    pub loop_source_inode: u64,
    pub loop_offset: u64,
    pub loop_size_limit: u64,
    pub loop_flags: u32,
    pub mount_id: u64,
    pub mount_root: CustodyFileIdentity,
    pub mount_flags: u64,
    pub filesystem: String,
}

/// Complete current base-image cohort, observed before and after the reads.
#[derive(Clone, Debug, Deserialize, Serialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct CustodyCohort {
    pub manifest_path: String,
    pub manifest: CustodyFileIdentity,
    pub manifest_sha256: String,
    pub host_uid: u32,
    pub user_namespace: CustodyNamespace,
    pub uid_range: (u32, u32),
    pub gid_range: (u32, u32),
    pub system: CustodyImage,
    pub vendor: CustodyImage,
}

/// The original APK read from the admitted readonly system mount itself.
#[derive(Clone, Debug, Deserialize, Serialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct CustodyImageMember {
    pub path: String,
    pub file: CustodyFileIdentity,
    pub sha256: String,
    pub mount_id: u64,
}

/// Current original owner and configuration binding, not a saved PID selector.
#[derive(Clone, Debug, Deserialize, Serialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct CustodyOwner {
    pub host_uid: u32,
    pub cell_host_pid: u32,
    pub cell_start_ticks: u64,
    pub selection_binding_sha256: String,
    pub base_cohort_sha256: String,
    pub runtime_manifest_sha256: String,
    pub namespaces: Vec<CustodyNamespace>,
}

/// Literal finite query, complete stdout, and the original executor receipt.
/// The receipt is serialized from the non-deserializable `ReadReceipt`; its
/// nested exec observation is preserved without converting it into authority.
#[derive(Clone, Debug, Deserialize, Serialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct CustodyRead {
    pub argv: Vec<String>,
    pub stdout: String,
    pub receipt: serde_json::Value,
}

/// Actual image-installed Gallery observation. Persistent data continuity and
/// application acceptance remain separate, explicitly unqualified gates.
#[derive(Clone, Debug, Deserialize, Serialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct ImageApplicationCustody {
    pub schema: String,
    pub application: ApplicationInspection,
    pub owner: CustodyOwner,
    pub cohort: CustodyCohort,
    pub original_apk: CustodyImageMember,
    /// Second complete system/vendor byte reads after all seven queries.
    pub after_cohort: CustodyCohort,
    /// Second complete original APK byte read through its retained descriptor.
    pub after_original_apk: CustodyImageMember,
    pub reads: Vec<CustodyRead>,
    pub elapsed_millis: u64,
    pub data_continuity_qualified: bool,
    pub runtime_qualified: bool,
    pub business_qualified: bool,
    pub production_ready: bool,
}

fn require(value: bool, reason: &'static str) -> Result<(), String> {
    if value { Ok(()) } else { Err(reason.into()) }
}

fn digest(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn regular(file: &CustodyFileIdentity) -> bool {
    file.device != 0
        && file.inode != 0
        && file.mode & 0o170000 == 0o100000
        && file.uid == 0
        && file.gid == 0
        && file.links == 1
        && file.mode & 0o022 == 0
}

fn read_valid(read: &CustodyRead) -> Result<(), String> {
    let receipt = &read.receipt;
    let object = receipt.as_object().ok_or("image custody receipt is not an object")?;
    let keys = object.keys().map(String::as_str).collect::<BTreeSet<_>>();
    require(keys == BTreeSet::from([
        "worker_pid", "worker_waitid_code", "worker_waitid_status", "query_pid",
        "query_waitid_code", "query_waitid_status", "exec", "output_bytes",
        "output_sha256", "elapsed_millis", "cgroup_removed",
    ]), "image custody receipt shape differs from the original executor")?;
    let exec = &receipt["exec"];
    let exec_object = exec.as_object().ok_or("image custody stopped-exec observation is absent")?;
    require(
        exec_object.keys().map(String::as_str).collect::<BTreeSet<_>>() == BTreeSet::from([
            "query_start_ticks", "original_parent_pid", "tracer_tid", "waitid_code",
            "waitid_status", "event_previous_tid", "executable", "executable_mount_id",
            "executable_sha256", "executable_selinux", "process_selinux", "process_apparmor",
            "uid", "gid", "no_new_privileges", "seccomp_filter_mode",
        ])
            && exec["query_start_ticks"].as_u64().is_some_and(|value| value > 0)
            && exec["original_parent_pid"].as_u64().is_some_and(|value| value > 0)
            && exec["tracer_tid"].as_u64().is_some_and(|value| value > 0)
            && exec["waitid_code"].as_i64() == Some(4)
            && exec["waitid_status"].as_i64() == Some(1029)
            && exec["event_previous_tid"].as_u64() == receipt["query_pid"].as_u64()
            && exec["executable"].is_object()
            && exec["executable_mount_id"].as_u64().is_some_and(|value| value > 0)
            && exec["executable_sha256"].as_str().is_some_and(digest)
            && exec["executable_selinux"].as_str() == Some("u:object_r:droidloom_query_exec:s0")
            && exec["process_selinux"].as_str() == Some("u:r:droidloom_query:s0")
            && exec["process_apparmor"].as_str()
                == Some("droidloom-production-android//&droidloom-production-broker (enforce)")
            && exec["no_new_privileges"].as_bool() == Some(true)
            && exec["seccomp_filter_mode"].as_u64() == Some(2),
        "image custody original stopped-exec observation differs",
    )?;
    require(
        read.stdout.len() <= 65_536
            && receipt["output_bytes"].as_u64() == Some(read.stdout.len() as u64)
            && receipt["output_sha256"].as_str()
                == Some(format!("{:x}", Sha256::digest(read.stdout.as_bytes())).as_str())
            && receipt["worker_pid"].as_u64().is_some_and(|pid| pid > 0)
            && receipt["query_pid"].as_u64().is_some_and(|pid| pid > 0)
            && receipt["query_pid"].as_u64() != receipt["worker_pid"].as_u64()
            && receipt["worker_waitid_code"].as_i64() == Some(1)
            && receipt["query_waitid_code"].as_i64() == Some(1)
            && receipt["worker_waitid_status"].as_i64() == Some(0)
            && receipt["query_waitid_status"].as_i64() == Some(0)
            && receipt["cgroup_removed"].as_bool() == Some(true)
            && receipt["elapsed_millis"].as_u64().is_some_and(|value| value < 30_000),
        "image custody read output or original retirement receipt differs",
    )
}

struct Transcript<'a> {
    epoch: &'a RuntimeEpoch,
    reads: &'a [CustodyRead],
    cursor: usize,
}
impl AndroidProbe for Transcript<'_> {
    fn epoch(&mut self) -> Result<RuntimeEpoch, String> {
        Ok(self.epoch.clone())
    }
    fn command(&mut self, args: &[String]) -> Result<String, String> {
        let read = self.reads.get(self.cursor).ok_or("image custody query is absent")?;
        require(read.argv == args, "image custody query order or arguments differ")?;
        read_valid(read)?;
        self.cursor += 1;
        Ok(read.stdout.clone())
    }
}

impl ImageApplicationCustody {
    /// Check internal consistency of an actual daemon response. This method
    /// executes no command and never accepts an imported value as a runtime
    /// capability or as persistent-data, business, or production qualification.
    pub fn validate(&self, expected: &ApplicationInspection) -> Result<(), String> {
        require(
            self.schema == "droidloom-image-application-custody-v1"
                && &self.application == expected
                && expected.package == GALLERY_PACKAGE
                && expected.user == 0
                && expected.version_code == 40_030
                && expected.apks.len() == 1
                && self.after_cohort == self.cohort
                && self.after_original_apk == self.original_apk
                && !self.data_continuity_qualified
                && !self.runtime_qualified
                && !self.business_qualified
                && !self.production_ready
                && self.elapsed_millis < 300_000,
            "image custody scope, identity, or unqualified gates differ",
        )?;
        let apk = &expected.apks[0];
        require(
            apk.name == "base.apk"
                && GALLERY_PM_PATHS.contains(&apk.path.as_str())
                && apk.bytes == GALLERY_BYTES
                && apk.sha256 == GALLERY_SHA256
                && self.original_apk.path == GALLERY_SOURCE_PATH
                && self.original_apk.sha256 == GALLERY_SHA256
                && self.original_apk.file.bytes == GALLERY_BYTES
                && self.original_apk.file.mode & 0o170000 == 0o100000,
            "image custody APK is not the exact original CP3A Gallery",
        )?;
        let owner = &self.owner;
        let cohort = &self.cohort;
        require(
            owner.host_uid > 0
                && owner.host_uid != u32::MAX
                && owner.host_uid == cohort.host_uid
                && owner.cell_host_pid == expected.epoch.cell_host_pid
                && owner.cell_start_ticks > 0
                && digest(&owner.selection_binding_sha256)
                && digest(&owner.runtime_manifest_sha256)
                && digest(&owner.base_cohort_sha256)
                && owner.base_cohort_sha256 == cohort.manifest_sha256
                && cohort.manifest_path
                    == format!("/etc/droidloom/cohorts/{}.json", cohort.manifest_sha256)
                && regular(&cohort.manifest)
                && cohort.manifest.bytes > 0
                && cohort.manifest.bytes <= 16 * 1024,
            "image custody owner or complete manifest binding differs",
        )?;
        let names: BTreeSet<_> = owner.namespaces.iter().map(|row| row.name.as_str()).collect();
        require(
            owner.namespaces.len() == 7
                && names == BTreeSet::from(["user", "mount", "pid", "ipc", "uts", "net", "cgroup"])
                && owner.namespaces.iter().all(|row| row.device != 0 && row.inode != 0)
                && owner.namespaces.iter().find(|row| row.name == "user")
                    == Some(&cohort.user_namespace)
                && cohort.uid_range.1 != 0
                && cohort.gid_range.1 != 0,
            "image custody original namespace set differs",
        )?;
        for (role, image) in [("system", &cohort.system), ("vendor", &cohort.vendor)] {
            require(
                image.role == role
                    && image.path == format!(
                        "/var/lib/droidloom/cohorts/{}/images/{role}.img", cohort.manifest_sha256
                    )
                    && regular(&image.file)
                    && (4096..=8 * 1024 * 1024 * 1024).contains(&image.file.bytes)
                    && image.file.bytes % 512 == 0
                    && digest(&image.sha256)
                    && image.loop_node.mode & 0o170000 == 0o060000
                    && image.loop_node.uid == 0
                    && image.loop_node.mode & 0o002 == 0
                    && image.loop_offset == 0
                    && image.loop_size_limit == 0
                    && image.loop_flags == 5
                    && image.loop_source_device == image.file.device
                    && image.loop_source_inode == image.file.inode
                    && image.mount_id != 0
                    && image.mount_root.device == image.loop_device
                    && image.mount_root.mode & 0o170000 == 0o040000
                    && image.mount_root.uid == cohort.uid_range.0
                    && image.mount_root.gid == cohort.gid_range.0
                    && image.mount_flags & 7 == 7
                    && matches!(image.filesystem.as_str(), "ext4" | "erofs"),
                "image custody whole-file, loop, or readonly mount differs",
            )?;
        }
        require(
            cohort.system.file.bytes == SYSTEM_BYTES
                && cohort.system.sha256 == SYSTEM_SHA256
                && (cohort.system.file.device, cohort.system.file.inode)
                    != (cohort.vendor.file.device, cohort.vendor.file.inode)
                && self.original_apk.mount_id == cohort.system.mount_id
                && self.original_apk.file.device == cohort.system.mount_root.device,
            "image custody whole official system or original member mount differs",
        )?;
        require(self.reads.len() == 7, "image custody requires the complete seven-read ledger")?;
        for read in &self.reads {
            require(
                read.receipt["exec"]["uid"].as_u64()
                    == Some(u64::from(cohort.uid_range.0) + 2000)
                    && read.receipt["exec"]["gid"].as_u64()
                        == Some(u64::from(cohort.gid_range.0) + 2000),
                "image custody query did not use this owner's mapped Android shell",
            )?;
        }
        let mut transcript = Transcript {
            epoch: &expected.epoch,
            reads: &self.reads,
            cursor: 0,
        };
        let observed = super::application_probe::inspect(&mut transcript, GALLERY_PACKAGE, 0)?;
        require(
            observed == *expected && transcript.cursor == self.reads.len(),
            "image custody actual query transcript does not reproduce the PM observation",
        )?;
        for read in self.reads.iter().filter(|row| row.argv.get(1).is_some_and(|arg| arg == "stat")) {
            let fields = read.stdout.trim().splitn(4, ':').collect::<Vec<_>>();
            require(
                fields.len() == 4
                    && fields[0].parse::<u64>().ok() == Some(self.original_apk.file.device)
                    && fields[1].parse::<u64>().ok() == Some(self.original_apk.file.inode)
                    && fields[2].parse::<u64>().ok() == Some(self.original_apk.file.bytes),
                "PM APK is not the same inode on the admitted whole-image mount",
            )?;
        }
        Ok(())
    }
}

#[cfg(test)]
#[path = "application_custody_tests.rs"]
mod tests;
