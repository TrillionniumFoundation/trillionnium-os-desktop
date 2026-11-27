//! Descriptor-bound label changes. Source admission and the sealed once owner
//! are the only future callers of the mutation core; this module exposes no
//! physical mutation command and does not infer authority from a receipt flag.
use crate::{Result, ensure, fs, model::Identity};
use serde::{Deserialize, Serialize};
use std::{
    collections::BTreeMap,
    ffi::CString,
    fs::File,
    os::fd::{AsFd, AsRawFd},
    path::{Path, PathBuf},
    sync::Arc,
};

#[path = "cold_original_label_journal.rs"]
mod journal;
#[path = "cold_original_label_plan.rs"]
mod plan;
#[path = "cold_original_label_scope.rs"]
mod scope;
#[path = "cold_original_label_service_state.rs"]
mod service_state;
#[path = "cold_working_input_labels.rs"]
pub(crate) mod working_inputs;
pub(crate) use journal::{
    OriginalLabelRestorationTransaction, OriginalLabelTransaction, OriginalLabelsApplied,
    OriginalLabelsRestored, OriginalPairRestored,
};
pub(super) use journal::{restore_retired_pair, withdraw_labeled_selection};
pub(crate) use plan::{
    OriginalLabelRestoreSources, OriginalLabelSources,
    inspect_files as inspect_original_labels_files,
};

#[cfg(test)]
#[path = "cold_original_label_snapshot_tests.rs"]
mod snapshot_custody_tests;

const LABEL: &str = "security.selinux";
const MAX_NAMES: usize = 65_536;
const MAX_VALUE: usize = 65_536;
const MAX_TOTAL: usize = 8_388_608;

// The selected kernel's empty-path xattrat path rejects O_PATH. Its procfd
// magic link instead jumps directly to the held dentry, including a symlink,
// without following that symlink's target. Only this fixed current-process
// descriptor bridge is allowed; original pathnames never enter an xattr call.
// The once owner additionally binds all original PID1 namespaces. These
// held proc and namespace identities make each bridge call fail if this
// process itself changes namespace custody between its surrounding fences.
struct ProcCustody {
    pid: u32,
    process: File,
    process_identity: Identity,
    namespaces: Vec<(&'static str, File, Identity)>,
}
impl ProcCustody {
    fn capture() -> Result<Self> {
        let process = File::from(rustix::fs::open(
            "/proc/self",
            rustix::fs::OFlags::RDONLY
                | rustix::fs::OFlags::DIRECTORY
                | rustix::fs::OFlags::CLOEXEC,
            rustix::fs::Mode::empty(),
        )?);
        let process_identity = fs::stat(&process)?;
        ensure(
            rustix::fs::fstatfs(&process)?.f_type as u64 == 0x9fa0,
            "label process custody is outside procfs",
        )?;
        let mut namespaces = Vec::new();
        for kind in ["mnt", "pid", "user"] {
            let file = File::open(format!("/proc/self/ns/{kind}"))?;
            let identity = fs::stat(&file)?;
            namespaces.push((kind, file, identity));
        }
        let result = Self {
            pid: std::process::id(),
            process,
            process_identity,
            namespaces,
        };
        result.revalidate()?;
        Ok(result)
    }
    fn revalidate(&self) -> Result<()> {
        ensure(
            std::process::id() == self.pid,
            "label process identity changed",
        )?;
        // These temporary name observations need metadata, not another held
        // descriptor. Follow the same fixed proc names and compare every
        // original custody field; the initial captured descriptors stay held.
        let actual = fs::identity(&rustix::fs::statat(
            rustix::fs::CWD,
            "/proc/self",
            rustix::fs::AtFlags::empty(),
        )?);
        let same = |a: &Identity, b: &Identity| {
            (a.dev, a.ino, a.mode, a.uid, a.gid) == (b.dev, b.ino, b.mode, b.uid, b.gid)
        };
        ensure(
            same(&actual, &self.process_identity)
                && same(&fs::stat(&self.process)?, &self.process_identity),
            "label process proc inode changed",
        )?;
        for (kind, held, identity) in &self.namespaces {
            let actual = fs::identity(&rustix::fs::statat(
                rustix::fs::CWD,
                format!("/proc/self/ns/{kind}"),
                rustix::fs::AtFlags::empty(),
            )?);
            ensure(
                same(&fs::stat(held)?, identity) && same(&actual, identity),
                "label bridge namespace changed",
            )?;
        }
        Ok(())
    }
}

struct DescriptorAlias<'a> {
    directory: File,
    file: &'a File,
    name: String,
    path: String,
    custody: ProcCustody,
}
impl<'a> DescriptorAlias<'a> {
    fn new(file: &'a File) -> Result<Self> {
        let directory = File::from(rustix::fs::open(
            "/proc/self/fd",
            rustix::fs::OFlags::RDONLY
                | rustix::fs::OFlags::DIRECTORY
                | rustix::fs::OFlags::CLOEXEC,
            rustix::fs::Mode::empty(),
        )?);
        ensure(
            rustix::fs::fstatfs(&directory)?.f_type as u64 == 0x9fa0,
            "descriptor bridge is not the actual proc filesystem",
        )?;
        let name = file.as_raw_fd().to_string();
        let value = Self {
            directory,
            file,
            path: format!("/proc/self/fd/{name}"),
            name,
            custody: ProcCustody::capture()?,
        };
        value.validate()?;
        Ok(value)
    }
    fn validate(&self) -> Result<()> {
        self.custody.revalidate()?;
        let held = fs::stat(self.file)?;
        let named = fs::identity(&rustix::fs::statat(
            &self.directory,
            self.name.as_str(),
            rustix::fs::AtFlags::empty(),
        )?);
        let current_proc = fs::identity(&rustix::fs::statat(
            rustix::fs::CWD,
            "/proc/self/fd",
            rustix::fs::AtFlags::empty(),
        )?);
        let held_proc = fs::stat(&self.directory)?;
        ensure(
            (
                current_proc.dev,
                current_proc.ino,
                current_proc.mode,
                current_proc.uid,
                current_proc.gid,
            ) == (
                held_proc.dev,
                held_proc.ino,
                held_proc.mode,
                held_proc.uid,
                held_proc.gid,
            ),
            "fixed procfd directory changed inode or custody",
        )?;
        ensure(
            named == held,
            &format!("fixed procfd target identity differs: held={held:?} named={named:?}"),
        )
    }
}
fn list(alias: &DescriptorAlias<'_>, value: &mut [u8]) -> Result<usize> {
    alias.validate()?;
    let result = if value.is_empty() {
        rustix::fs::listxattr_query(alias.path.as_str())?
    } else {
        rustix::fs::listxattr(alias.path.as_str(), value)?
    };
    alias.validate()?;
    Ok(result)
}
fn get(alias: &DescriptorAlias<'_>, name: &str, value: &mut [u8]) -> Result<usize> {
    alias.validate()?;
    let name = CString::new(name)?;
    let result = if value.is_empty() {
        rustix::fs::getxattr_query(alias.path.as_str(), name.as_c_str())?
    } else {
        rustix::fs::getxattr(alias.path.as_str(), name.as_c_str(), value)?
    };
    alias.validate()?;
    Ok(result)
}
fn set(file: &File, name: &str, value: Option<&[u8]>) -> Result<()> {
    let alias = DescriptorAlias::new(file)?;
    let name = CString::new(name)?;
    match value {
        Some(value) => rustix::fs::setxattr(
            alias.path.as_str(),
            name.as_c_str(),
            value,
            rustix::fs::XattrFlags::empty(),
        )?,
        None => rustix::fs::removexattr(alias.path.as_str(), name.as_c_str())?,
    }
    alias.validate()
}

fn attributes(file: &File) -> Result<BTreeMap<String, Vec<u8>>> {
    let before = fs::stat(file)?;
    // Bind one complete attribute snapshot to the same held process, procfd
    // directory and namespace identities. Each individual list/get still
    // validates that full custody before and after its actual syscall.
    // Nothing is cached across snapshots, and attribute bytes are never cached.
    let alias = DescriptorAlias::new(file)?;
    let count = list(&alias, &mut [])?;
    ensure(count <= MAX_NAMES, "inode has too many xattr name bytes")?;
    let mut names = vec![0; count];
    ensure(
        list(&alias, &mut names)? == count,
        "xattr name inventory changed",
    )?;
    ensure(
        names.is_empty() || names.last() == Some(&0),
        "unterminated xattr name",
    )?;
    let mut rows = BTreeMap::new();
    let mut total = 0usize;
    for raw in names.split(|v| *v == 0).filter(|v| !v.is_empty()) {
        let name = std::str::from_utf8(raw)?.to_owned();
        let count = get(&alias, &name, &mut [])?;
        ensure(count <= MAX_VALUE, "inode xattr exceeds the Linux bound")?;
        total = total.checked_add(count).ok_or("xattr size overflow")?;
        ensure(
            total <= MAX_TOTAL,
            "inode xattr inventory exceeds eight MiB",
        )?;
        let mut value = vec![0; count];
        ensure(
            get(&alias, &name, &mut value)? == count,
            "inode xattr value changed",
        )?;
        ensure(rows.insert(name, value).is_none(), "duplicate xattr name")?;
    }
    let mut again = vec![0; names.len()];
    ensure(
        list(&alias, &mut again)? == names.len() && again == names && fs::stat(file)? == before,
        "inode identity or xattr names changed during the descriptor readback",
    )?;
    Ok(rows)
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct PersistentHandle {
    handle_type: i32,
    bytes: Vec<u8>,
}
impl PersistentHandle {
    fn capture(file: &File) -> Result<Self> {
        ensure(
            rustix::fs::fstatfs(file)?.f_type as u64 == 0xef53,
            "original label custody requires the admitted ext4 filesystem",
        )?;
        let (handle, _) = droidloom_descriptor_custody::Ext4Handle::capture(file.as_fd())?;
        let id = fs::stat(file)?;
        ensure(
            u64::from(handle.inode_number()) == id.ino && id.nlink > 0,
            "persistent handle differs from the linked held inode",
        )?;
        Ok(Self {
            handle_type: handle.handle_type(),
            bytes: handle.bytes().to_vec(),
        })
    }
    fn reopen(&self, admitted_mount: &File) -> Result<File> {
        ensure(
            rustix::fs::fstatfs(admitted_mount)?.f_type as u64 == 0xef53,
            "label recovery mount is not the admitted ext4 filesystem",
        )?;
        let handle =
            droidloom_descriptor_custody::Ext4Handle::from_record(self.handle_type, &self.bytes)?;
        let held = File::from(handle.reopen(admitted_mount.as_fd())?);
        ensure(
            Self::capture(&held)? == *self && fs::stat(&held)?.dev == fs::stat(admitted_mount)?.dev,
            "reopened label handle no longer identifies the same filesystem inode",
        )?;
        Ok(held)
    }
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub(super) struct Snapshot {
    identity: Identity,
    handle: PersistentHandle,
    attributes: BTreeMap<String, Vec<u8>>,
}
pub(super) fn snapshot_identity(snapshot: &Snapshot) -> &Identity {
    &snapshot.identity
}
pub(super) fn snapshot(file: &File) -> Result<Snapshot> {
    let identity = fs::stat(file)?;
    let handle = PersistentHandle::capture(file)?;
    let attributes = attributes(file)?;
    ensure(
        fs::stat(file)? == identity && PersistentHandle::capture(file)? == handle,
        "label snapshot inode changed",
    )?;
    Ok(Snapshot {
        identity,
        handle,
        attributes,
    })
}
pub(super) fn verify_data_snapshot(
    source: &Snapshot,
    current: &Snapshot,
    working_observation: bool,
) -> Result<()> {
    ensure(
        source.handle == current.handle
            && source.identity.dev == current.identity.dev
            && source.identity.ino == current.identity.ino,
        "original/working data generation changed",
    )?;
    let mut before = source.attributes.clone();
    let mut after = current.attributes.clone();
    if working_observation {
        before.remove(LABEL);
        after.remove(LABEL);
    }
    ensure(
        before == after,
        "original data labels or unrelated working xattrs changed",
    )
}
pub(super) fn data_snapshot(file: &File, identity: &Identity) -> Result<Snapshot> {
    let actual = snapshot(file)?;
    ensure(
        actual.identity == *identity,
        "data label snapshot is not the same complete metadata observation",
    )?;
    Ok(actual)
}
pub(super) fn verify_snapshot_identity(value: &Snapshot, identity: &Identity) -> Result<()> {
    ensure(
        value.identity == *identity,
        "data intent identity and generation snapshot disagree",
    )
}
pub(super) fn only_ctime_changed(a: &Identity, b: &Identity) -> bool {
    let mut actual = b.clone();
    actual.ctime_sec = a.ctime_sec;
    actual.ctime_nsec = a.ctime_nsec;
    actual == *a
}

// This is deliberately not Deserialize/Clone and has no public constructor.
// Once wiring adds its source-bound scope, a reference to this actual held
// inode derivation can rebind an owner's exact lock ctime without weakening
// inode/mode/owner/size/mtime or any other extended attribute.
pub(super) struct LabelDerivation {
    file: File,
    before: Snapshot,
    after: Snapshot,
}
impl LabelDerivation {
    fn revalidate(&self) -> Result<()> {
        ensure(
            snapshot(&self.file)? == self.after,
            "applied label derivation changed",
        )
    }
}

// Shared custody of the potentially large immutable complete source plan.
// Admission and final readback hash all bytes; each inode step checks the held
// and named complete identity. A caller cannot construct this seal or a label
// derivation by deserializing a receipt.
struct PlanSeal {
    pin: crate::boot_files::FilePin,
    file: File,
    identity: Identity,
    attributes: BTreeMap<String, Vec<u8>>,
}
impl PlanSeal {
    fn open(pin: &crate::boot_files::FilePin) -> Result<Self> {
        super::root_pin(pin, 512 * 1024 * 1024)?;
        let (file, identity) = crate::boot_files::open_pin(pin)?;
        let attributes = attributes(&file)?;
        let value = Self {
            pin: pin.clone(),
            file,
            identity,
            attributes,
        };
        value.revalidate()?;
        Ok(value)
    }
    fn revalidate(&self) -> Result<()> {
        ensure(
            fs::stat(&self.file)? == self.identity
                && attributes(&self.file)? == self.attributes
                && fs::Tree::open("/", 0)?.identity(&fs::absolute_string(&self.pin.path)?)?
                    == self.identity
                && fs::stat(&self.file)? == self.identity,
            "held immutable complete label plan was changed or replaced",
        )?;
        super::no_privilege_attributes(&self.file)
    }
    fn full_readback(&self) -> Result<()> {
        self.revalidate()?;
        super::root_pin(&self.pin, 512 * 1024 * 1024)?;
        self.revalidate()
    }
}

/// The once owner accepts only this actual held-inode, source-bound transition.
/// There is no public constructor, Deserialize, Clone or caller-passed success.
/// The complete label adapter owns construction after durable target syncfs.
pub(crate) struct OriginalLabelDerivation {
    candidate_id: String,
    logical_path: PathBuf,
    plan: Arc<PlanSeal>,
    preimage: crate::boot_files::FilePin,
    applied: crate::boot_files::FilePin,
    core: LabelDerivation,
}
impl OriginalLabelDerivation {
    pub(crate) fn candidate_id(&self) -> &str {
        &self.candidate_id
    }
    pub(crate) fn path(&self) -> &Path {
        &self.logical_path
    }
    pub(crate) fn source_plan(&self) -> &crate::boot_files::FilePin {
        &self.plan.pin
    }
    pub(crate) fn before_identity(&self) -> &Identity {
        &self.core.before.identity
    }
    pub(crate) fn after_identity(&self) -> &Identity {
        &self.core.after.identity
    }
    pub(crate) fn revalidate(&self) -> Result<()> {
        self.plan.revalidate()?;
        self.core.revalidate()?;
        let mut wanted = self.core.before.attributes.clone();
        let label = self
            .core
            .after
            .attributes
            .get(LABEL)
            .ok_or("actual source-bound label missing")?;
        let preimage: serde_json::Value =
            serde_json::from_slice(&super::root_pin(&self.preimage, 32 * 1024 * 1024)?)?;
        ensure(
            preimage["schema"] == "droidloom.original-label-preimage.v1"
                && preimage["candidate_id"] == self.candidate_id
                && preimage["logical_path"] == self.logical_path.to_string_lossy().as_ref()
                && preimage["source_plan"] == serde_json::to_value(&self.plan.pin)?
                && preimage["attribute"] == LABEL
                && preimage["desired"] == serde_json::to_value(label)?
                && preimage["before"] == serde_json::to_value(&self.core.before)?,
            "opaque label preimage is not this actual source-bound transition",
        )?;
        wanted.insert(LABEL.into(), label.clone());
        ensure(
            only_ctime_changed(&self.core.before.identity, &self.core.after.identity)
                && self.core.before.handle == self.core.after.handle
                && wanted == self.core.after.attributes,
            "opaque label transition changed an unrelated attribute or inode field",
        )?;
        let record: serde_json::Value =
            serde_json::from_slice(&super::root_pin(&self.applied, 32 * 1024 * 1024)?)?;
        ensure(
            record["schema"] == "droidloom.original-label-applied.v1"
                && record["preimage"] == serde_json::to_value(&self.preimage)?
                && record["before"] == serde_json::to_value(&self.core.before)?
                && record["after"] == serde_json::to_value(&self.core.after)?
                && record["target_metadata_durability"]["operation"] == "syncfs"
                && record["target_metadata_durability"]["filesystem_dev"]
                    == self.core.after.identity.dev,
            "actual durable label transition record differs",
        )?;
        self.core.revalidate()?;
        self.plan.revalidate()
    }
}

/// Actual restoration of only our label from a fresh, admitted current
/// snapshot. It cannot turn mutable runtime metadata into an unchanged-source
/// claim, and it has no public constructor or serialized authority form.
pub(crate) struct OriginalLabelRestoration {
    candidate_id: String,
    logical_path: PathBuf,
    plan: Arc<PlanSeal>,
    original_preimage: crate::boot_files::FilePin,
    restored: crate::boot_files::FilePin,
    core: LabelDerivation,
}
impl OriginalLabelRestoration {
    pub(crate) fn candidate_id(&self) -> &str {
        &self.candidate_id
    }
    pub(crate) fn path(&self) -> &Path {
        &self.logical_path
    }
    pub(crate) fn source_plan(&self) -> &crate::boot_files::FilePin {
        &self.plan.pin
    }
    pub(crate) fn before_identity(&self) -> &Identity {
        &self.core.before.identity
    }
    pub(crate) fn after_identity(&self) -> &Identity {
        &self.core.after.identity
    }
    pub(crate) fn revalidate(&self) -> Result<()> {
        self.plan.revalidate()?;
        self.core.revalidate()?;
        let original: serde_json::Value =
            serde_json::from_slice(&super::root_pin(&self.original_preimage, 32 * 1024 * 1024)?)?;
        ensure(
            original["schema"] == "droidloom.original-label-preimage.v1"
                && original["candidate_id"] == self.candidate_id
                && original["logical_path"] == self.logical_path.to_string_lossy().as_ref()
                && original["source_plan"] == serde_json::to_value(&self.plan.pin)?,
            "restoration preimage is not bound to this actual candidate and source plan",
        )?;
        let before: Snapshot = serde_json::from_value(original["before"].clone())?;
        let mut wanted = self.core.before.attributes.clone();
        match before.attributes.get(LABEL) {
            Some(label) => {
                wanted.insert(LABEL.into(), label.clone());
            }
            None => {
                wanted.remove(LABEL);
            }
        }
        ensure(
            self.core.before.handle == before.handle
                && self.core.before.handle == self.core.after.handle
                && only_ctime_changed(&self.core.before.identity, &self.core.after.identity)
                && wanted == self.core.after.attributes,
            "restoration changed another current inode field, generation or extended attribute",
        )?;
        let actual: serde_json::Value =
            serde_json::from_slice(&super::root_pin(&self.restored, 32 * 1024 * 1024)?)?;
        let current = actual["schema"] == "droidloom.current-label-restored.v1";
        let strict = actual["schema"] == "droidloom.original-label-restored.v1";
        ensure(
            (current || strict)
                && actual[if current {
                    "original_preimage"
                } else {
                    "preimage"
                }] == serde_json::to_value(&self.original_preimage)?
                && actual[if current {
                    "before"
                } else {
                    "observed_before_restore"
                }] == serde_json::to_value(&self.core.before)?
                && actual["after"] == serde_json::to_value(&self.core.after)?
                && actual["target_metadata_durability"]["operation"] == "syncfs"
                && actual["target_metadata_durability"]["filesystem_dev"]
                    == self.core.after.identity.dev,
            "restoration lacks its actual synchronized complete before/after record",
        )?;
        self.core.revalidate()?;
        self.plan.revalidate()
    }
}
pub(super) fn accept_retired_snapshot(
    expected: &mut Snapshot,
    step: &OriginalLabelRestoration,
) -> Result<()> {
    step.revalidate()?;
    ensure(
        *expected == step.core.before || *expected == step.core.after,
        "retired working snapshot is outside the actual complete restoration derivation",
    )?;
    *expected = step.core.after.clone();
    Ok(())
}

fn apply_one(file: File, before: &Snapshot, desired: &[u8], name: &str) -> Result<LabelDerivation> {
    ensure(
        name == LABEL || cfg!(test),
        "only the source-bound SELinux xattr may change",
    )?;
    ensure(
        snapshot(&file)? == *before,
        "label preimage identity or xattrs changed",
    )?;
    ensure(
        !desired.is_empty() && desired.len() <= 4096,
        "bounded raw label required",
    )?;
    let mut expected = before.attributes.clone();
    expected.insert(name.to_owned(), desired.to_vec());
    // Already-correct labels have no write side effect. Rewriting the same
    // value would create an unexplained ctime-only outcome on later recovery.
    if before.attributes.get(name).map(Vec::as_slice) != Some(desired) {
        set(&file, name, Some(desired))?;
    }
    let after = snapshot(&file)?;
    ensure(
        only_ctime_changed(&before.identity, &after.identity)
            && before.handle == after.handle
            && after.attributes == expected,
        "label mutation changed another inode field or extended attribute",
    )?;
    Ok(LabelDerivation {
        file,
        before: before.clone(),
        after,
    })
}
fn restore_one(step: &LabelDerivation, name: &str) -> Result<Snapshot> {
    ensure(
        name == LABEL || cfg!(test),
        "only the recorded SELinux xattr may be restored",
    )?;
    step.revalidate()?;
    if step.before.attributes.get(name) != step.after.attributes.get(name) {
        set(
            &step.file,
            name,
            step.before.attributes.get(name).map(Vec::as_slice),
        )?;
    }
    let restored = snapshot(&step.file)?;
    ensure(
        only_ctime_changed(&step.before.identity, &restored.identity)
            && step.before.handle == restored.handle
            && restored.attributes == step.before.attributes,
        "label rollback changed an unrelated inode field or xattr",
    )?;
    Ok(restored)
}

#[cfg(test)]
mod tests {
    use super::*;
    use rustix::fs::{Mode, OFlags};
    use std::os::unix::fs::symlink;

    fn path_inode(path: &std::path::Path) -> File {
        File::from(
            rustix::fs::open(
                path,
                OFlags::PATH | OFlags::NOFOLLOW | OFlags::CLOEXEC,
                Mode::empty(),
            )
            .unwrap(),
        )
    }
    #[test]
    fn an_already_correct_label_does_not_create_a_new_ctime() {
        let tmp = tempfile::Builder::new()
            .prefix(".p4-label-noop-")
            .tempdir_in(std::env::current_dir().unwrap())
            .unwrap();
        let path = tmp.path().join("inode");
        std::fs::write(&path, b"ordinary public test").unwrap();
        let file = path_inode(&path);
        set(&file, "user.droidloom.testlabel", Some(b"already-correct")).unwrap();
        let before = snapshot(&file).unwrap();
        let applied = apply_one(
            file,
            &before,
            b"already-correct",
            "user.droidloom.testlabel",
        )
        .unwrap();
        assert_eq!(applied.before, applied.after);
        assert_eq!(
            restore_one(&applied, "user.droidloom.testlabel").unwrap(),
            before
        );
    }
    #[test]
    fn actual_descriptor_label_and_rollback_preserve_other_xattrs_and_mtime() {
        let area = tempfile::Builder::new()
            .prefix(".p4-label-test-")
            .tempdir_in(std::env::current_dir().unwrap())
            .unwrap();
        let path = area.path().join("target");
        std::fs::write(&path, b"unchanged ordinary content").unwrap();
        let file = path_inode(&path);
        set(&file, "user.droidloom.unrelated", Some(b"preserved")).unwrap();
        let before = snapshot(&file).unwrap();
        let step = apply_one(
            file,
            &before,
            b"u:object_r:p4_linux_product_store_t:s0",
            "user.droidloom.testlabel",
        )
        .unwrap();
        step.revalidate().unwrap();
        let restored = restore_one(&step, "user.droidloom.testlabel").unwrap();
        assert_eq!(restored.attributes, before.attributes);
        assert!(only_ctime_changed(&before.identity, &restored.identity));
        assert_eq!(std::fs::read(&path).unwrap(), b"unchanged ordinary content");
    }
    #[test]
    fn held_inode_does_not_retarget_a_replaced_final_path_or_follow_symlinks() {
        let area = tempfile::Builder::new()
            .prefix(".p4-label-test-")
            .tempdir_in(std::env::current_dir().unwrap())
            .unwrap();
        let path = area.path().join("target");
        let old = area.path().join("old");
        std::fs::write(&path, b"old").unwrap();
        let held = path_inode(&path);
        std::fs::rename(&path, &old).unwrap();
        std::fs::write(&path, b"new").unwrap();
        set(&held, "user.droidloom.testlabel", Some(b"old inode only")).unwrap();
        assert!(
            !attributes(&path_inode(&path))
                .unwrap()
                .contains_key("user.droidloom.testlabel")
        );
        assert!(
            attributes(&path_inode(&old))
                .unwrap()
                .contains_key("user.droidloom.testlabel")
        );
        let link = area.path().join("link");
        symlink(&old, &link).unwrap();
        assert!(
            !attributes(&path_inode(&link))
                .unwrap()
                .contains_key("user.droidloom.testlabel")
        );
    }
    #[test]
    fn intervening_identity_or_xattr_change_prevents_apply_and_restore() {
        let area = tempfile::Builder::new()
            .prefix(".p4-label-test-")
            .tempdir_in(std::env::current_dir().unwrap())
            .unwrap();
        let path = area.path().join("target");
        std::fs::write(&path, b"original").unwrap();
        let file = path_inode(&path);
        let before = snapshot(&file).unwrap();
        set(&file, "user.droidloom.unrelated", Some(b"external change")).unwrap();
        assert!(apply_one(file, &before, b"label", "user.droidloom.testlabel").is_err());
        let file = path_inode(&path);
        let before = snapshot(&file).unwrap();
        let step = apply_one(file, &before, b"label", "user.droidloom.testlabel").unwrap();
        set(
            &step.file,
            "user.droidloom.unrelated",
            Some(b"changed again"),
        )
        .unwrap();
        assert!(restore_one(&step, "user.droidloom.testlabel").is_err());
    }

    #[test]
    #[ignore = "requires root; changes only newly created isolated symlink test inodes"]
    fn actual_security_label_targets_held_symlink_after_its_name_is_replaced() {
        ensure(
            rustix::process::getuid().as_raw() == 0,
            "root-only isolated test",
        )
        .unwrap();
        let area = tempfile::Builder::new()
            .prefix("p4-label-inode-test-")
            .tempdir_in("/var/lib/droidloom-qualification")
            .unwrap();
        let first = area.path().join("first-target");
        let second = area.path().join("second-target");
        std::fs::write(&first, b"first independent test target").unwrap();
        std::fs::write(&second, b"second independent test target").unwrap();
        let first_fd = path_inode(&first);
        let second_fd = path_inode(&second);
        set(
            &first_fd,
            "user.droidloom.target",
            Some(b"first target only"),
        )
        .unwrap();
        set(
            &second_fd,
            "user.droidloom.target",
            Some(b"second target only"),
        )
        .unwrap();
        let first_before = snapshot(&first_fd).unwrap();
        let second_before = snapshot(&second_fd).unwrap();
        let path = area.path().join("link");
        let retained = area.path().join("retained-link");
        symlink(&first, &path).unwrap();
        let held = path_inode(&path);
        std::fs::rename(&path, &retained).unwrap();
        symlink(&second, &path).unwrap();
        let replacement_fd = path_inode(&path);
        let replacement_before = snapshot(&replacement_fd).unwrap();
        let before = snapshot(&held).unwrap();
        let raw = b"u:object_r:p4_linux_product_store_t:s0\0";
        let step = apply_one(held, &before, raw, LABEL).unwrap();
        assert_eq!(snapshot(&path_inode(&retained)).unwrap(), step.after);
        assert_eq!(snapshot(&replacement_fd).unwrap(), replacement_before);
        assert_eq!(snapshot(&first_fd).unwrap(), first_before);
        assert_eq!(snapshot(&second_fd).unwrap(), second_before);
        let restored = restore_one(&step, LABEL).unwrap();
        assert_eq!(restored.attributes, before.attributes);
        assert!(only_ctime_changed(&before.identity, &restored.identity));
        assert_eq!(snapshot(&replacement_fd).unwrap(), replacement_before);
        assert_eq!(snapshot(&first_fd).unwrap(), first_before);
        assert_eq!(snapshot(&second_fd).unwrap(), second_before);
        println!(
            "{}",
            serde_json::json!({"schema":"droidloom.private-symlink-label-replacement-test.v1",
            "held_before":before,"held_after":step.after,"held_restored":restored,
            "replacement_before":replacement_before,"replacement_after":snapshot(&replacement_fd).unwrap(),
            "first_target_before":first_before,"first_target_after":snapshot(&first_fd).unwrap(),
            "second_target_before":second_before,"second_target_after":snapshot(&second_fd).unwrap(),
            "original_host_or_data_modified":false})
        );
    }
}
