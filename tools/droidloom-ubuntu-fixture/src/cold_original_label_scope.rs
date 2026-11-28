//! The original ext4 root's fixed label scope. No caller-supplied exclusion or
//! alternate physical root is accepted. This module only reads inode metadata.
use super::{PersistentHandle, ProcCustody, Snapshot, snapshot};
use crate::{Result, boot_files::FilePin, ensure, fs, model::Identity};
use rustix::fs::{AtFlags, FileType, Mode, OFlags, ResolveFlags};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::{
    collections::{BTreeMap, BTreeSet},
    fs::File,
    path::{Path, PathBuf},
};

const ROOT_UUID: &str = "01c27223-3933-481e-9836-7bd0ef1be8c9";
const MAX_ENTRIES: usize = 1_000_000;
const FIXED_EXCLUSIONS: [(&str, &str); 4] = [
    ("/home/alex/work", "retained-historical-work"),
    (
        "/var/lib/droidloom-qualification",
        "qualification-and-original-rollback-evidence",
    ),
    (
        "/var/lib/droidloom/users/1000/data",
        "separate-exact-working-pair-transaction",
    ),
    (
        "/etc/droidloom/production/selected.json",
        "separate-exact-selected-configuration-transaction",
    ),
];
const DYNAMIC: [(&str, &str); 5] = [
    ("/dev", "devtmpfs"),
    ("/proc", "proc"),
    ("/sys", "sysfs"),
    ("/run", "tmpfs"),
    ("/tmp", "tmpfs"),
];

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct Mount {
    id: u64,
    parent: u64,
    device: String,
    root: String,
    path: String,
    options: Vec<String>,
    filesystem: String,
    source: String,
    super_options: Vec<String>,
}
fn decode_mount(value: &str) -> Result<String> {
    let mut bytes = Vec::with_capacity(value.len());
    let raw = value.as_bytes();
    let mut i = 0;
    while i < raw.len() {
        if raw[i] == b'\\' {
            ensure(
                i + 3 < raw.len() && raw[i + 1..i + 4].iter().all(|v| (b'0'..=b'7').contains(v)),
                "invalid kernel mount path escape",
            )?;
            let n = u16::from(raw[i + 1] - b'0') * 64
                + u16::from(raw[i + 2] - b'0') * 8
                + u16::from(raw[i + 3] - b'0');
            ensure(n <= 255, "out-of-range kernel mount escape")?;
            let n = n as u8;
            ensure(n != 0, "NUL in kernel mount path")?;
            bytes.push(n);
            i += 4;
        } else {
            bytes.push(raw[i]);
            i += 1;
        }
    }
    Ok(String::from_utf8(bytes)?)
}
fn mounts(raw: &str) -> Result<Vec<Mount>> {
    ensure(
        !raw.is_empty() && raw.len() <= 16 * 1024 * 1024,
        "bounded nonempty original mount table required",
    )?;
    let mut ids = BTreeSet::new();
    let mut result = Vec::new();
    for line in raw.lines() {
        let fields = line.split_whitespace().collect::<Vec<_>>();
        let separator = fields
            .iter()
            .position(|v| *v == "-")
            .ok_or("mount separator missing")?;
        ensure(
            separator >= 6 && fields.len() == separator + 4,
            "malformed original mount row",
        )?;
        let id = fields[0].parse()?;
        ensure(ids.insert(id), "duplicate mount identity")?;
        let path = decode_mount(fields[4])?;
        valid_path(&path)?;
        result.push(Mount {
            id,
            parent: fields[1].parse()?,
            device: fields[2].into(),
            root: decode_mount(fields[3])?,
            path,
            options: fields[5].split(',').map(str::to_owned).collect(),
            filesystem: fields[separator + 1].into(),
            source: decode_mount(fields[separator + 2])?,
            super_options: fields[separator + 3]
                .split(',')
                .map(str::to_owned)
                .collect(),
        });
    }
    ensure(
        result.iter().filter(|v| v.path == "/").count() == 1,
        "one actual root mount required",
    )?;
    Ok(result)
}
fn below(path: &str, prefix: &str) -> bool {
    path == prefix
        || path
            .strip_prefix(prefix)
            .is_some_and(|v| v.starts_with('/'))
}
fn valid_path(path: &str) -> Result<()> {
    ensure(
        path.starts_with('/')
            && !path.contains('\0')
            && !path.bytes().any(|v| v.is_ascii_control())
            && (path == "/"
                || (!path.ends_with('/')
                    && !path.contains("//")
                    && !path.contains("/./")
                    && !path.ends_with("/.")
                    && Path::new(path)
                        .components()
                        .skip(1)
                        .all(|v| matches!(v, std::path::Component::Normal(_))))),
        "canonical absolute label pathname required",
    )
}
fn original_capabilities() -> Result<Value> {
    let text = std::fs::read_to_string("/proc/self/status")?;
    ensure(
        text.len() <= 1024 * 1024,
        "bounded current capability readback required",
    )?;
    let mut rows = BTreeMap::new();
    for line in text.lines() {
        let Some((key, value)) = line.split_once(':') else {
            continue;
        };
        if [
            "Uid",
            "Gid",
            "CapInh",
            "CapPrm",
            "CapEff",
            "CapBnd",
            "CapAmb",
            "NoNewPrivs",
        ]
        .contains(&key)
        {
            ensure(
                rows.insert(key.to_owned(), value.trim().to_owned())
                    .is_none(),
                "duplicate current capability field",
            )?;
        }
    }
    ensure(
        rows.len() == 8
            && rows["Uid"].split_whitespace().all(|n| n == "0")
            && rows["Uid"].split_whitespace().count() == 4,
        "original label custody requires actual original root credentials",
    )?;
    let effective = u64::from_str_radix(&rows["CapEff"], 16)?;
    ensure(
        effective & (1 << 2) != 0,
        "actual CAP_DAC_READ_SEARCH required for generation-safe original label recovery",
    )?;
    Ok(serde_json::to_value(rows)?)
}
fn fixed_reason(path: &str) -> Option<&'static str> {
    FIXED_EXCLUSIONS
        .iter()
        .find(|(p, _)| below(path, p))
        .map(|(_, reason)| *reason)
}
fn external_mount_reason(m: &Mount) -> Result<&'static str> {
    for (path, filesystem) in DYNAMIC {
        if m.path == path {
            ensure(
                m.filesystem == filesystem && m.root == "/",
                "fixed dynamic root mount changed type",
            )?;
            return Ok("separate-dynamic-filesystem");
        }
        if below(&m.path, path) {
            return Ok("inside-separate-dynamic-filesystem");
        }
    }
    if fixed_reason(&m.path).is_some() {
        return Ok("inside-fixed-evidence-exclusion");
    }
    if m.path == "/boot/efi" {
        ensure(
            m.filesystem == "vfat" && m.root == "/" && m.source.starts_with("/dev/"),
            "original EFI mount differs",
        )?;
        return Ok("separate-original-efi-filesystem");
    }
    if let Some(relative) = m.path.strip_prefix("/snap/") {
        let parts = relative.split('/').collect::<Vec<_>>();
        ensure(
            parts.len() == 2
                && !parts[0].is_empty()
                && parts[0]
                    .bytes()
                    .all(|v| v.is_ascii_lowercase() || v.is_ascii_digit() || v == b'-')
                && !parts[1].is_empty()
                && parts[1].bytes().all(|v| v.is_ascii_digit())
                && m.filesystem == "squashfs"
                && m.root == "/"
                && m.options.iter().any(|v| v == "ro")
                && m.source
                    .strip_prefix("/dev/loop")
                    .is_some_and(|v| !v.is_empty() && v.bytes().all(|b| b.is_ascii_digit())),
            "original readonly Snap mount has unknown source or mode",
        )?;
        return Ok("immutable-readonly-snap-filesystem");
    }
    Err(format!(
        "unreviewed original mount cannot be silently excluded: {}",
        m.path
    )
    .into())
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(super) struct Entry {
    pub(super) path: PathBuf,
    pub(super) snapshot: Snapshot,
    pub(super) matcher_type: String,
}
#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Exclusion {
    path: PathBuf,
    reason: String,
    identity: Identity,
    persistent_handle: Option<PersistentHandle>,
    original_label: Option<Vec<u8>>,
    mount: Option<Mount>,
}
#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(super) struct Inventory {
    pub(super) schema: String,
    pub(super) root_uuid: String,
    pub(super) root_identity: Identity,
    pub(super) root_handle: PersistentHandle,
    pub(super) actual_capabilities: Value,
    pub(super) cold_clone: FilePin,
    pub(super) source_clone_directories: Vec<PathBuf>,
    pub(super) entries: Vec<Entry>,
    exclusions: Vec<Exclusion>,
    mounts: Vec<Mount>,
}
pub(super) fn matcher_type(mode: u32) -> Result<&'static str> {
    Ok(match FileType::from_raw_mode(mode) {
        FileType::RegularFile => "file",
        FileType::Directory => "dir",
        FileType::Symlink => "lnk_file",
        FileType::CharacterDevice => "chr_file",
        FileType::BlockDevice => "blk_file",
        FileType::Fifo => "fifo_file",
        FileType::Socket => "sock_file",
        _ => return Err("original inode has an unsupported file type".into()),
    })
}

pub(super) struct RootScope {
    root: File,
    root_identity: Identity,
    root_handle: PersistentHandle,
    actual_capabilities: Value,
    custody: ProcCustody,
    mount_text: String,
    mounts: Vec<Mount>,
    top_mounts: BTreeMap<String, Mount>,
    cold_clone: FilePin,
    clone_directories: Vec<PathBuf>,
}
impl RootScope {
    pub(super) fn original(cold_clone: &FilePin) -> Result<Self> {
        crate::cold_original_initramfs::original_context()?;
        ensure(
            cold_clone.bytes == 2843 && cold_clone.sha256 == super::super::CLONE_SHA,
            "fixed original cold-clone proof required for label exclusions",
        )?;
        let clone: Value = serde_json::from_slice(&super::super::root_pin(cold_clone, 64 * 1024)?)?;
        ensure(
            clone["schema"] == "pocket4-original-data-cold-compatibility-clone-v1",
            "original cold-clone schema differs",
        )?;
        let rows = clone["rows"]
            .as_array()
            .ok_or("cold-clone image rows missing")?;
        ensure(
            rows.len() == 2,
            "both original clone images must be excluded",
        )?;
        let mut clone_directories = BTreeSet::new();
        for (index, row) in rows.iter().enumerate() {
            ensure(
                row["role"] == if index == 0 { "data" } else { "metadata" },
                "original clone image role differs",
            )?;
            let path = row["clone_path"]
                .as_str()
                .ok_or("original clone path missing")?;
            valid_path(path)?;
            clone_directories.insert(
                Path::new(path)
                    .parent()
                    .ok_or("clone parent missing")?
                    .to_owned(),
            );
        }
        let root = File::from(rustix::fs::open(
            "/",
            OFlags::RDONLY | OFlags::DIRECTORY | OFlags::NOFOLLOW | OFlags::CLOEXEC,
            Mode::empty(),
        )?);
        let root_identity = fs::stat(&root)?;
        let root_handle = PersistentHandle::capture(&root)?;
        let mount_text = std::fs::read_to_string("/proc/self/mountinfo")?;
        let mounts = mounts(&mount_text)?;
        ensure(
            mounts
                .iter()
                .find(|v| v.path == "/")
                .is_some_and(|v| v.filesystem == "ext4" && v.root == "/"),
            "actual original root mount differs",
        )?;
        let mut top_mounts = BTreeMap::new();
        for mount in &mounts {
            if mount.path == "/" {
                continue;
            }
            external_mount_reason(mount)?;
            if DYNAMIC
                .iter()
                .any(|(p, _)| mount.path != *p && below(&mount.path, p))
                || fixed_reason(&mount.path).is_some()
            {
                continue;
            }
            ensure(
                top_mounts
                    .insert(mount.path.clone(), mount.clone())
                    .is_none(),
                "overlapping original mount targets",
            )?;
        }
        let result = Self {
            root,
            root_identity,
            root_handle,
            actual_capabilities: original_capabilities()?,
            custody: ProcCustody::capture()?,
            mount_text,
            mounts,
            top_mounts,
            cold_clone: cold_clone.clone(),
            clone_directories: clone_directories.into_iter().collect(),
        };
        result.revalidate()?;
        Ok(result)
    }
    pub(super) fn revalidate(&self) -> Result<()> {
        self.custody.revalidate()?;
        let current = File::from(rustix::fs::open(
            "/",
            OFlags::RDONLY | OFlags::DIRECTORY | OFlags::NOFOLLOW | OFlags::CLOEXEC,
            Mode::empty(),
        )?);
        ensure(
            fs::stat(&current)? == self.root_identity
                && fs::stat(&self.root)? == self.root_identity
                && PersistentHandle::capture(&current)? == self.root_handle
                && std::fs::read_to_string("/proc/self/mountinfo")? == self.mount_text
                && original_capabilities()? == self.actual_capabilities,
            "original root custody or mount table changed during label inspection",
        )?;
        super::super::root_pin(&self.cold_clone, 64 * 1024)?;
        Ok(())
    }
    fn exclusion_reason(&self, path: &str) -> Option<&str> {
        fixed_reason(path).or_else(|| {
            self.clone_directories
                .iter()
                .any(|p| p.to_str().is_some_and(|p| below(path, p)))
                .then_some("retained-original-cold-clone")
        })
    }
    pub(super) fn collect(&self) -> Result<Inventory> {
        self.revalidate()?;
        let mut entries = Vec::new();
        let mut exclusions = Vec::new();
        self.walk(&self.root, "/", &mut entries, &mut exclusions)?;
        // A retained cold clone can be nested under the historical work tree.
        // Record its exact directory identity as well as the ancestor exclusion;
        // never traverse or open either original clone image body.
        for path in &self.clone_directories {
            if exclusions.iter().any(|e| e.path == *path) {
                continue;
            }
            let held = self.open_named(path)?;
            let before = snapshot(&held)?;
            ensure(
                FileType::from_raw_mode(before.identity.mode) == FileType::Directory,
                "retained original cold-clone parent is no longer a directory",
            )?;
            exclusions.push(Exclusion {
                path: path.clone(),
                reason: "retained-original-cold-clone".into(),
                identity: before.identity,
                persistent_handle: Some(before.handle),
                original_label: before.attributes.get(super::LABEL).cloned(),
                mount: None,
            });
        }

        self.revalidate()?;
        Ok(Inventory {
            schema: "droidloom.original-root-label-scope.v1".into(),
            root_uuid: ROOT_UUID.into(),
            root_identity: self.root_identity.clone(),
            root_handle: self.root_handle.clone(),
            actual_capabilities: self.actual_capabilities.clone(),
            cold_clone: self.cold_clone.clone(),
            source_clone_directories: self.clone_directories.clone(),
            entries,
            exclusions,
            mounts: self.mounts.clone(),
        })
    }
    pub(super) fn verify_inventory(&self, inventory: &Inventory) -> Result<Value> {
        self.verify_inventory_updates(inventory, &BTreeMap::new())
    }
    pub(super) fn verify_inventory_updates(
        &self,
        inventory: &Inventory,
        actual_labels: &BTreeMap<PathBuf, Snapshot>,
    ) -> Result<Value> {
        self.revalidate()?;
        let mut excluded_readback = Vec::new();
        for entry in &inventory.entries {
            let held = self.open_named(&entry.path)?;
            ensure(
                snapshot(&held)? == *actual_labels.get(&entry.path).unwrap_or(&entry.snapshot),
                "original label plan inode changed after source context lookup",
            )?;
        }
        for excluded in &inventory.exclusions {
            if excluded.mount.is_some() {
                let current = std::fs::symlink_metadata(&excluded.path)?;
                use std::os::unix::fs::MetadataExt;
                ensure(
                    (
                        current.dev(),
                        current.ino(),
                        current.mode(),
                        current.uid(),
                        current.gid(),
                    ) == (
                        excluded.identity.dev,
                        excluded.identity.ino,
                        excluded.identity.mode,
                        excluded.identity.uid,
                        excluded.identity.gid,
                    ),
                    "excluded original mount target changed identity",
                )?;
                continue;
            }
            let held = self.open_named(&excluded.path)?;
            let current = snapshot(&held)?;
            if excluded.path == Path::new("/var/lib/droidloom/users/1000/data") {
                if let Some(actual) = actual_labels.get(&excluded.path) {
                    ensure(
                        current == *actual
                            && Some(&current.handle) == excluded.persistent_handle.as_ref()
                            && super::only_ctime_changed(&excluded.identity, &current.identity),
                        "separate working-pair label is not its exact actual derivation",
                    )?;
                    excluded_readback.push(serde_json::json!({"path":excluded.path,
                        "before":excluded.identity,"after":current.identity,
                        "persistent_handle":current.handle,"separate_working_pair_label":true}));
                    continue;
                }
            }
            ensure(
                Some(&current.handle) == excluded.persistent_handle.as_ref()
                    && (
                        current.identity.dev,
                        current.identity.ino,
                        current.identity.mode,
                        current.identity.uid,
                        current.identity.gid,
                    ) == (
                        excluded.identity.dev,
                        excluded.identity.ino,
                        excluded.identity.mode,
                        excluded.identity.uid,
                        excluded.identity.gid,
                    )
                    && current.attributes.get(super::LABEL) == excluded.original_label.as_ref(),
                "an explicitly excluded tree changed identity or original SELinux label",
            )?;
            excluded_readback.push(serde_json::json!({"path":excluded.path,"before":excluded.identity,"after":current.identity,
                "persistent_handle":current.handle,"original_label":excluded.original_label}));
        }
        self.revalidate()?;
        Ok(
            serde_json::json!({"excluded_inode_readback":excluded_readback,"complete_included_count":inventory.entries.len()}),
        )
    }
    pub(super) fn verify_working_selection_inventory(
        &self,
        inventory: &Inventory,
        actual_labels: &BTreeMap<PathBuf, Snapshot>,
        selection: &crate::cold_original_data::WorkingSelectionProof,
    ) -> Result<Value> {
        let selected = Path::new("/etc/droidloom/production/selected.json");
        let prior = inventory
            .exclusions
            .iter()
            .find(|entry| entry.path == selected);
        match (prior, selection.original_initial()) {
            (Some(entry), Some(original)) => crate::ensure(
                entry.identity == original.identity
                    && entry.persistent_handle.as_ref() == Some(&original.handle)
                    && entry.original_label.as_ref() == original.attributes.get(super::LABEL),
                "working selected history differs from the actual initial excluded inode",
            )?,
            (None, None) => (),
            _ => {
                return Err(
                    "working selected history invented or lost the original excluded inode".into(),
                );
            }
        }
        let expected = if selection.selected() {
            Some(selection.candidate_after())
        } else {
            selection.original_after()
        };
        match expected {
            Some(expected) => crate::ensure(
                snapshot(&self.open_named(selected)?)? == *expected,
                "working selected public name differs from its actual completed transition",
            )?,
            None => match std::fs::symlink_metadata(selected) {
                Err(error) if error.kind() == std::io::ErrorKind::NotFound => (),
                _ => return Err("working selected original absence was not restored".into()),
            },
        }
        let mut retained = inventory.clone();
        retained.exclusions.retain(|entry| entry.path != selected);
        self.verify_inventory_updates(&retained, actual_labels)
    }
    pub(super) fn open_named(&self, path: &Path) -> Result<File> {
        if path == Path::new("/") {
            return Ok(self.root.try_clone()?);
        }
        Ok(File::from(rustix::fs::openat2(
            &self.root,
            path.strip_prefix("/")?,
            OFlags::PATH | OFlags::NOFOLLOW | OFlags::CLOEXEC,
            Mode::empty(),
            ResolveFlags::BENEATH
                | ResolveFlags::NO_SYMLINKS
                | ResolveFlags::NO_MAGICLINKS
                | ResolveFlags::NO_XDEV,
        )?))
    }

    pub(super) fn verify_returned_working_inventory(
        &self,
        inventory: &Inventory,
        actual_labels: &BTreeMap<PathBuf, Snapshot>,
        data: &crate::cold_original_data::WorkingReturnData,
    ) -> Result<Value> {
        data.revalidate_custody()?;
        let selected = Path::new("/etc/droidloom/production/selected.json");
        let mut retained = inventory.clone();
        if data.candidate_is_selected()? {
            let prior = inventory
                .exclusions
                .iter()
                .find(|e| e.path == selected)
                .ok_or("fresh returned scope omitted its actual selected candidate")?;
            let current = snapshot(&self.open_named(selected)?)?;
            if let Some(actual) = actual_labels.get(selected) {
                ensure(
                    current == *actual
                        && Some(&current.handle) == prior.persistent_handle.as_ref()
                        && super::only_ctime_changed(&prior.identity, &current.identity),
                    "returned selected exclusion differs from its held actual label result",
                )?;
            } else {
                ensure(
                    current.identity == prior.identity
                        && Some(&current.handle) == prior.persistent_handle.as_ref()
                        && current.attributes.get(super::LABEL) == prior.original_label.as_ref(),
                    "returned selected exclusion changed before its owned restoration",
                )?;
            }
            retained.exclusions.retain(|entry| entry.path != selected);
        }
        self.verify_inventory_updates(&retained, actual_labels)
    }
    pub(super) fn reopen_generation(&self, expected: &PersistentHandle) -> Result<File> {
        self.revalidate()?;
        expected.reopen(&self.root)
    }
    pub(super) fn accept_working_batch(&mut self, batch: &super::WorkingLabelBatch) -> Result<()> {
        if let Some(step) = batch
            .records()
            .iter()
            .find(|step| step.paths().iter().any(|p| p == Path::new("/")))
        {
            self.root_identity =
                step.require_held_transition(Path::new("/"), &self.root, &self.root_identity)?;
        }
        self.revalidate()
    }
    pub(super) fn accept_returned_working_label(
        &mut self,
        proof: &super::WorkingReturnedLabelRestoration,
    ) -> Result<()> {
        if proof.paths().iter().any(|path| path == Path::new("/")) {
            self.root_identity =
                proof.require_held_transition(Path::new("/"), &self.root, &self.root_identity)?;
        }
        Ok(())
    }
    pub(super) fn accept_root_label(
        &mut self,
        step: &super::OriginalLabelDerivation,
    ) -> Result<()> {
        if step.path() != Path::new("/") {
            return Ok(());
        }
        step.revalidate()?;
        ensure(
            step.core.before.handle == self.root_handle
                && (self.root_identity == step.core.before.identity
                    || self.root_identity == step.core.after.identity)
                && fs::stat(&self.root)? == step.core.after.identity,
            "root identity can only follow its actual own label transition",
        )?;
        self.root_identity = step.core.after.identity.clone();
        self.revalidate()
    }
    pub(super) fn accept_root_restoration(
        &mut self,
        step: &super::OriginalLabelRestoration,
    ) -> Result<()> {
        if step.path() != Path::new("/") {
            return Ok(());
        }
        step.revalidate()?;
        ensure(
            step.core.before.handle == self.root_handle
                && (self.root_identity == step.core.before.identity
                    || self.root_identity == step.core.after.identity)
                && fs::stat(&self.root)? == step.core.after.identity,
            "root restoration is not the exact held generation and actual label transition",
        )?;
        self.root_identity = step.core.after.identity.clone();
        self.revalidate()
    }
    pub(super) fn verify_restored_exclusions(
        &self,
        inventory: &Inventory,
        data: &super::super::OriginalDataTransaction,
    ) -> Result<Value> {
        self.revalidate()?;
        ensure(
            data.transaction.observe(true)?
                == (
                    super::super::Layout::Ready,
                    super::super::SelectionState::Original,
                ),
            "retained exclusions require the actual original pair and selection",
        )?;
        let mut rows = Vec::new();
        for excluded in &inventory.exclusions {
            if let Some(old) = &excluded.mount {
                let actual = self
                    .mounts
                    .iter()
                    .find(|m| m.path == old.path)
                    .ok_or("original excluded mount missing after return")?;
                ensure(
                    actual.root == old.root
                        && actual.filesystem == old.filesystem
                        && actual.source == old.source
                        && actual.options == old.options
                        && actual.super_options == old.super_options,
                    "returned excluded mount no longer has its original normal source and flags",
                )?;
                rows.push(serde_json::json!({"path":excluded.path,"prior_boot_mount":old,"returned_mount":actual}));
                continue;
            }
            let current = snapshot(&self.open_named(&excluded.path)?)?;
            if excluded.path == Path::new(super::super::ORIGINAL) {
                super::verify_data_snapshot(
                    &data.transaction.intent.original.directory_label_identity,
                    &current,
                    false,
                )?;
                rows.push(
                    serde_json::json!({"path":excluded.path,"original_pair_generation":current,
                    "original_label_not_written":true}),
                );
                continue;
            }
            ensure(
                Some(&current.handle) == excluded.persistent_handle.as_ref()
                    && (
                        current.identity.dev,
                        current.identity.ino,
                        current.identity.mode,
                        current.identity.uid,
                        current.identity.gid,
                    ) == (
                        excluded.identity.dev,
                        excluded.identity.ino,
                        excluded.identity.mode,
                        excluded.identity.uid,
                        excluded.identity.gid,
                    )
                    && current.attributes.get(super::LABEL) == excluded.original_label.as_ref(),
                "retained original clone/evidence tree lost its generation, custody or original label",
            )?;
            rows.push(serde_json::json!({"path":excluded.path,"before":excluded.identity,"returned":current,
                "excluded_tree_contents_not_traversed":true}));
        }
        self.revalidate()?;
        Ok(serde_json::json!({"retained_exclusions":rows}))
    }
    fn walk(
        &self,
        file: &File,
        path: &str,
        entries: &mut Vec<Entry>,
        exclusions: &mut Vec<Exclusion>,
    ) -> Result<()> {
        ensure(
            entries.len() + exclusions.len() < MAX_ENTRIES,
            "original root label inventory exceeds one million inodes",
        )?;
        let before = snapshot(file)?;
        ensure(
            before.identity.dev == self.root_identity.dev,
            "label target left the actual original filesystem",
        )?;
        if let Some(reason) = self.exclusion_reason(path) {
            exclusions.push(Exclusion {
                path: path.into(),
                reason: reason.into(),
                identity: before.identity,
                persistent_handle: Some(before.handle),
                original_label: before.attributes.get(super::LABEL).cloned(),
                mount: None,
            });
            return Ok(());
        }
        let directory = FileType::from_raw_mode(before.identity.mode) == FileType::Directory;
        entries.push(Entry {
            path: path.into(),
            matcher_type: matcher_type(before.identity.mode)?.into(),
            snapshot: before.clone(),
        });
        if directory {
            let held = File::from(rustix::fs::openat(
                file,
                ".",
                OFlags::RDONLY
                    | OFlags::DIRECTORY
                    | OFlags::NOFOLLOW
                    | OFlags::CLOEXEC
                    | OFlags::NOATIME,
                Mode::empty(),
            )?);
            ensure(
                fs::stat(&held)? == before.identity,
                "label traversal directory changed",
            )?;
            let mut names = Vec::new();
            for entry in rustix::fs::Dir::read_from(&held)? {
                let entry = entry?;
                let name = entry.file_name().to_str()?;
                if name != "." && name != ".." {
                    names.push(name.to_owned());
                }
                ensure(
                    names.len() < MAX_ENTRIES,
                    "one original directory has too many entries",
                )?;
            }
            names.sort();
            for name in names {
                let logical = if path == "/" {
                    format!("/{name}")
                } else {
                    format!("{path}/{name}")
                };
                valid_path(&logical)?;
                if let Some(mount) = self.top_mounts.get(&logical) {
                    let identity = fs::identity(&rustix::fs::statat(
                        &held,
                        name.as_str(),
                        AtFlags::SYMLINK_NOFOLLOW,
                    )?);
                    exclusions.push(Exclusion {
                        path: logical.into(),
                        reason: external_mount_reason(mount)?.into(),
                        identity,
                        persistent_handle: None,
                        original_label: None,
                        mount: Some(mount.clone()),
                    });
                    continue;
                }
                let child = File::from(rustix::fs::openat2(
                    &held,
                    name.as_str(),
                    OFlags::PATH | OFlags::NOFOLLOW | OFlags::CLOEXEC,
                    Mode::empty(),
                    ResolveFlags::BENEATH
                        | ResolveFlags::NO_SYMLINKS
                        | ResolveFlags::NO_MAGICLINKS
                        | ResolveFlags::NO_XDEV,
                )?);
                self.walk(&child, &logical, entries, exclusions)?;
                ensure(
                    fs::identity(&rustix::fs::statat(
                        &held,
                        name.as_str(),
                        AtFlags::SYMLINK_NOFOLLOW,
                    )?) == fs::stat(&child)?,
                    "normal pathname was replaced during original label inspection",
                )?;
            }
        }
        ensure(
            snapshot(file)? == before,
            "original inode changed during complete label inspection",
        )?;
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn exclusions_are_exact_source_paths_without_a_blanket_home_exemption() {
        assert_eq!(
            fixed_reason("/home/alex/work/public"),
            Some("retained-historical-work")
        );
        assert!(fixed_reason("/home/alex/work-copy").is_none());
        assert!(fixed_reason("/home/alex/Documents/private-name").is_none());
        assert!(fixed_reason("/home/gdm/.config").is_none());
        assert_eq!(
            fixed_reason("/var/lib/droidloom/users/1000/data/data.img"),
            Some("separate-exact-working-pair-transaction")
        );
        assert!(fixed_reason("/var/lib/droidloom/users/1000/database").is_none());
        assert_eq!(
            fixed_reason("/var/lib/droidloom-qualification/once/data-pair.rollback"),
            Some("qualification-and-original-rollback-evidence")
        );
        assert!(fixed_reason("/var/lib/droidloom/identity-reservations/u1000.lease").is_none());
    }
    fn mount(path: &str, filesystem: &str, source: &str, options: &str) -> Mount {
        Mount {
            id: 2,
            parent: 1,
            device: "7:1".into(),
            root: "/".into(),
            path: path.into(),
            filesystem: filesystem.into(),
            source: source.into(),
            options: options.split(',').map(str::to_owned).collect(),
            super_options: vec![],
        }
    }
    #[test]
    fn unknown_mounts_or_writable_snap_sources_cannot_become_exclusions() {
        assert!(
            external_mount_reason(&mount(
                "/snap/firefox/9036",
                "squashfs",
                "/dev/loop10",
                "ro,nodev"
            ))
            .is_ok()
        );
        for m in [
            mount("/snap/firefox/9036", "squashfs", "/dev/loop10", "rw"),
            mount("/home/alex/Documents", "ext4", "/dev/nvme0n1p2", "rw"),
            mount("/usr", "ext4", "/dev/nvme0n1p2", "ro"),
            mount("/snap/firefox/current", "squashfs", "/dev/loop10", "ro"),
            mount("/tmp", "ext4", "/dev/nvme0n1p2", "rw"),
        ] {
            assert!(external_mount_reason(&m).is_err());
        }
    }
    #[test]
    fn actual_mount_text_requires_one_root_and_canonical_paths() {
        let base = "33 2 259:2 / / rw,relatime shared:1 - ext4 /dev/nvme0n1p2 rw\n";
        assert_eq!(mounts(base).unwrap()[0].path, "/");
        assert!(mounts("").is_err());
        assert!(mounts(&(base.to_owned() + base)).is_err());
        assert!(valid_path("/var/../home").is_err());
        assert!(valid_path("/var//lib").is_err());
        assert!(valid_path("/var/./lib").is_err());
        assert!(valid_path("/var/.").is_err());
        assert!(valid_path("/home/alex/ordinary name").is_ok());
        assert_eq!(decode_mount("/a\\040b").unwrap(), "/a b");
        assert!(decode_mount("/a\\000b").is_err());
    }
    #[test]
    fn real_ext4_walk_records_symlink_inode_and_never_enters_excluded_work() {
        let area = tempfile::Builder::new()
            .prefix(".p4-scope-")
            .tempdir_in(std::env::current_dir().unwrap())
            .unwrap();
        std::fs::write(
            area.path().join("ordinary"),
            b"not read by metadata inventory",
        )
        .unwrap();
        std::os::unix::fs::symlink("/etc/shadow", area.path().join("link")).unwrap();
        let root = File::from(
            rustix::fs::open(
                area.path(),
                OFlags::RDONLY | OFlags::DIRECTORY | OFlags::NOFOLLOW | OFlags::CLOEXEC,
                Mode::empty(),
            )
            .unwrap(),
        );
        let id = fs::stat(&root).unwrap();
        let handle = PersistentHandle::capture(&root).unwrap();
        let scope = RootScope {
            root,
            root_identity: id,
            root_handle: handle,
            actual_capabilities: serde_json::json!({}),
            custody: ProcCustody::capture().unwrap(),
            mount_text: String::new(),
            mounts: vec![],
            top_mounts: BTreeMap::new(),
            cold_clone: FilePin {
                path: area.path().join("unused-proof"),
                bytes: 1,
                sha256: "a".repeat(64),
            },
            clone_directories: vec![],
        };
        let mut entries = Vec::new();
        let mut exclusions = Vec::new();
        scope
            .walk(&scope.root, "/", &mut entries, &mut exclusions)
            .unwrap();
        assert_eq!(entries.len(), 3);
        assert!(exclusions.is_empty());
        let link = entries
            .iter()
            .find(|e| e.path == Path::new("/link"))
            .unwrap();
        assert_eq!(link.matcher_type, "lnk_file");
        assert_eq!(link.snapshot.identity.mode & 0o170000, 0o120000);
        entries.clear();
        scope
            .walk(
                &scope.root,
                "/home/alex/work",
                &mut entries,
                &mut exclusions,
            )
            .unwrap();
        assert!(entries.is_empty());
        assert_eq!(exclusions.len(), 1);
    }
}
