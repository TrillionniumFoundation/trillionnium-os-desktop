//! Durable, finite per-machine configuration publication. Original inodes are
//! retained by atomic exchange; a restored value is never synthesized from a
//! convenient matching pathname. Only the once dispatcher supplies entries.
#[path = "cold_original_once_package_parents.rs"]
pub(super) mod package_parents;
use super::{OriginalQualificationAuthority, owner::SealedInput};
use crate::{
    Result,
    boot_files::{self as files, FilePin},
    ensure, fs,
    model::Identity,
};
use droidloom_descriptor_custody::Ext4Handle;
use rustix::fs::{AtFlags, FileType, Mode, OFlags, RenameFlags};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    collections::BTreeMap,
    fs::File,
    io::{Read, Seek, Write},
    os::fd::{AsFd, AsRawFd},
    path::{Path, PathBuf},
};

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub(super) enum Payload {
    Regular { source: FilePin, mode: u32 },
    Symlink { target: String },
    Absent,
}
pub(super) struct Entry {
    pub(super) path: PathBuf,
    pub(super) payload: Payload,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct Node {
    identity: Identity,
    handle_type: i32,
    handle: String,
    attributes: BTreeMap<String, String>,
    sha256: Option<String>,
    link: Option<String>,
}
#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Intent {
    schema: String,
    candidate_id: String,
    group: String,
    ordinal: usize,
    logical_path: PathBuf,
    target: PathBuf,
    pending: PathBuf,
    payload: Payload,
    original: Option<Node>,
    prepared: Option<Node>,
    parent: DirectoryState,
    private_parent: DirectoryState,
    purpose_target: Option<PathBuf>,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct MemberIdentity {
    identity: Identity,
    handle_type: i32,
    handle: String,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct DirectoryState {
    path: PathBuf,
    identity: Identity,
    handle_type: i32,
    handle: String,
    attributes: BTreeMap<String, String>,
    members: BTreeMap<String, MemberIdentity>,
}
struct HeldDirectory {
    file: File,
    state: DirectoryState,
}
fn member(file: &File) -> Result<MemberIdentity> {
    let identity = fs::stat(file)?;
    let (handle, _) = Ext4Handle::capture(file.as_fd())?;
    ensure(
        handle.inode_number() as u64 == identity.ino,
        "configuration member generation differs",
    )?;
    Ok(MemberIdentity {
        identity,
        handle_type: handle.handle_type(),
        handle: hex::encode(handle.bytes()),
    })
}
impl DirectoryState {
    fn capture(path: &Path) -> Result<HeldDirectory> {
        let file = fs::Tree::open("/", 0)?.dir(&fs::absolute_string(path)?)?;
        let state = Self::held(path, &file)?;
        Ok(HeldDirectory { file, state })
    }
    fn held(path: &Path, file: &File) -> Result<Self> {
        let before = member(file)?;
        ensure(
            FileType::from_raw_mode(before.identity.mode) == FileType::Directory
                && before.identity.uid == 0
                && before.identity.gid == 0
                && before.identity.mode & 0o022 == 0,
            "configuration parent custody",
        )?;
        let attributes = attrs(file)?;
        let mut members = BTreeMap::new();
        for e in std::fs::read_dir(format!("/proc/self/fd/{}", file.as_raw_fd()))? {
            let name = e?
                .file_name()
                .into_string()
                .map_err(|_| "configuration parent nonUTF8 member")?;
            ensure(
                !name.is_empty()
                    && name.len() <= 255
                    && name != "."
                    && name != ".."
                    && !name.contains('/')
                    && members.len() < 65536,
                "bounded complete configuration parent inventory",
            )?;
            let child = File::from(rustix::fs::openat(
                file,
                name.as_str(),
                OFlags::PATH | OFlags::NOFOLLOW | OFlags::CLOEXEC,
                Mode::empty(),
            )?);
            ensure(
                members.insert(name, member(&child)?).is_none(),
                "duplicate configuration parent member",
            )?;
        }
        ensure(
            member(file)? == before && attrs(file)? == attributes,
            "configuration parent changed during inventory",
        )?;
        let named = fs::Tree::open("/", 0)?.dir(&fs::absolute_string(path)?)?;
        ensure(
            member(&named)? == before && attrs(&named)? == attributes,
            "configuration parent pathname replaced",
        )?;
        Ok(Self {
            path: path.into(),
            identity: before.identity,
            handle_type: before.handle_type,
            handle: before.handle,
            attributes,
            members,
        })
    }
    fn reopen(&self) -> Result<HeldDirectory> {
        let held = Self::capture(&self.path)?;
        ensure(
            held.state == *self,
            "configuration parent full generation/attributes/members changed",
        )?;
        Ok(held)
    }
    fn after_replace(&self, actual: &Self, name: &str, value: &Option<Node>) -> Result<()> {
        let mut id = actual.identity.clone();
        id.size = self.identity.size;
        id.mtime_sec = self.identity.mtime_sec;
        id.mtime_nsec = self.identity.mtime_nsec;
        id.ctime_sec = self.identity.ctime_sec;
        id.ctime_nsec = self.identity.ctime_nsec;
        let old_dir = self
            .members
            .get(name)
            .is_some_and(|v| FileType::from_raw_mode(v.identity.mode) == FileType::Directory);
        let new_dir = value
            .as_ref()
            .is_some_and(|v| FileType::from_raw_mode(v.identity.mode) == FileType::Directory);
        ensure(
            actual.identity.nlink == self.identity.nlink + (new_dir as u64) - (old_dir as u64),
            "parent link count not explained by exact child directory change",
        )?;
        id.nlink = self.identity.nlink;
        ensure(
            id == self.identity
                && actual.path == self.path
                && actual.handle_type == self.handle_type
                && actual.handle == self.handle
                && actual.attributes == self.attributes,
            "configuration parent changed beyond its exact child rename",
        )?;
        let mut expected = self.members.clone();
        match value {
            Some(n) => {
                expected.insert(
                    name.into(),
                    MemberIdentity {
                        identity: n.identity.clone(),
                        handle_type: n.handle_type,
                        handle: n.handle.clone(),
                    },
                );
            }
            None => {
                expected.remove(name);
            }
        }
        ensure(
            expected == actual.members,
            "configuration parent changed an unrelated member",
        )?;
        if expected == self.members {
            ensure(
                actual == self,
                "configuration parent clock/size drift has no actual child transition",
            )?;
        }
        Ok(())
    }
}

// A later source-owned child operation also changes that directory's metadata
// as a member of any already checkpointed ancestor. Compose only this exact
// generation/F9 transition; unrelated siblings never receive a clock waiver.
fn advance_parent(
    states: &mut BTreeMap<PathBuf, DirectoryState>,
    before: &DirectoryState,
    after: &DirectoryState,
) -> Result<()> {
    if let Some(known) = states.get(&before.path) {
        ensure(
            known == before,
            "owned parent operation lost its exact prior checkpoint",
        )?;
    }
    if let Some(parent) = before.path.parent() {
        if let Some(ancestor) = states.get_mut(parent) {
            let name = before
                .path
                .file_name()
                .and_then(|v| v.to_str())
                .ok_or("owned directory member name")?;
            let member = ancestor
                .members
                .get_mut(name)
                .ok_or("owned directory disappeared from ancestor checkpoint")?;
            ensure(
                member.identity == before.identity
                    && member.handle_type == before.handle_type
                    && member.handle == before.handle,
                "owned child generation was replaced before parent evolution",
            )?;
            member.identity = after.identity.clone();
        }
    }
    states.insert(after.path.clone(), after.clone());
    Ok(())
}

fn attrs(file: &File) -> Result<BTreeMap<String, String>> {
    let before = fs::stat(file)?;
    let proc = File::open("/proc/self/fd")?;
    ensure(
        rustix::fs::fstatfs(&proc)?.f_type as u64 == 0x9fa0,
        "configuration descriptor bridge is not procfs",
    )?;
    let leaf = file.as_raw_fd().to_string();
    ensure(
        fs::identity(&rustix::fs::statat(&proc, leaf.as_str(), AtFlags::empty())?) == before,
        "held descriptor alias differs",
    )?;
    let path = format!("/proc/self/fd/{leaf}");
    let size = rustix::fs::listxattr_query(path.as_str())?;
    ensure(size <= 65536, "bounded configuration xattr names required")?;
    let mut names = vec![0u8; size];
    ensure(
        rustix::fs::listxattr(path.as_str(), &mut names)? == size,
        "configuration xattrs changed",
    )?;
    ensure(
        names.is_empty() || names.last() == Some(&0),
        "unterminated configuration xattrs",
    )?;
    let mut result = BTreeMap::new();
    let mut total = 0;
    for raw in names.split(|b| *b == 0).filter(|v| !v.is_empty()) {
        let name = std::str::from_utf8(raw)?;
        let size = rustix::fs::getxattr_query(path.as_str(), name)?;
        total += size;
        ensure(
            size <= 65536 && total <= 1024 * 1024,
            "bounded configuration xattr values required",
        )?;
        let mut value = vec![0u8; size];
        ensure(
            rustix::fs::getxattr(path.as_str(), name, &mut value)? == size,
            "configuration xattr value changed",
        )?;
        ensure(
            result.insert(name.into(), hex::encode(value)).is_none(),
            "duplicate xattr",
        )?;
    }
    ensure(
        fs::stat(file)? == before
            && fs::identity(&rustix::fs::statat(&proc, leaf.as_str(), AtFlags::empty())?) == before,
        "configuration inode changed during attribute observation",
    )?;
    Ok(result)
}
fn at(path: &Path) -> Result<(File, String)> {
    let tree = fs::Tree::open("/", 0)?;
    tree.parent(&fs::absolute_string(path)?)
}
fn observe(path: &Path) -> Result<Option<Node>> {
    observe_kind(path, false)
}
fn observe_kind(path: &Path, directory: bool) -> Result<Option<Node>> {
    let (parent, name) = at(path)?;
    let f = match rustix::fs::openat(
        &parent,
        name.as_str(),
        OFlags::PATH | OFlags::NOFOLLOW | OFlags::CLOEXEC,
        Mode::empty(),
    ) {
        Ok(f) => File::from(f),
        Err(rustix::io::Errno::NOENT) => return Ok(None),
        Err(e) => return Err(e.into()),
    };
    let id = fs::stat(&f)?;
    ensure(
        id.uid == 0
            && id.gid == 0
            && (id.nlink == 1
                || directory
                    && FileType::from_raw_mode(id.mode) == FileType::Directory
                    && id.nlink >= 2)
            && (FileType::from_raw_mode(id.mode) == FileType::Symlink || id.mode & 0o7022 == 0),
        "configuration inode owner, links or mode differs",
    )?;
    let (handle, _) = Ext4Handle::capture(f.as_fd())?;
    ensure(
        handle.inode_number() as u64 == id.ino,
        "configuration generation does not name held inode",
    )?;
    let attributes = attrs(&f)?;
    let (sha256, link) = match FileType::from_raw_mode(id.mode) {
        FileType::RegularFile => {
            ensure(id.size <= 512 * 1024 * 1024, "configuration content bound")?;
            let body = File::from(rustix::fs::openat(
                &parent,
                name.as_str(),
                OFlags::RDONLY | OFlags::NONBLOCK | OFlags::NOFOLLOW | OFlags::CLOEXEC,
                Mode::empty(),
            )?);
            ensure(fs::stat(&body)? == id, "configuration content fd differs")?;
            (Some(fs::hash(&body)?), None)
        }
        FileType::Symlink => {
            let target = rustix::fs::readlinkat(&parent, name.as_str(), Vec::new())?;
            let s = std::str::from_utf8(target.to_bytes())?.to_owned();
            ensure(
                s.len() <= 4096 && !s.contains('\0'),
                "bounded original configuration link",
            )?;
            (None, Some(s))
        }
        FileType::Directory if directory => (None, None),
        _ => {
            return Err(
                "configuration is neither its exact file type nor a prepared directory".into(),
            );
        }
    };
    ensure(
        fs::stat(&f)? == id
            && fs::identity(&rustix::fs::statat(
                &parent,
                name.as_str(),
                AtFlags::SYMLINK_NOFOLLOW,
            )?) == id,
        "configuration changed during complete observation",
    )?;
    Ok(Some(Node {
        identity: id,
        handle_type: handle.handle_type(),
        handle: hex::encode(handle.bytes()),
        attributes,
        sha256,
        link,
    }))
}
fn same_inode(a: &Node, b: &Node) -> bool {
    a.identity.dev == b.identity.dev
        && a.identity.ino == b.identity.ino
        && a.handle_type == b.handle_type
        && a.handle == b.handle
}
fn same_except_ctime(a: &Node, b: &Node) -> bool {
    let mut n = b.clone();
    n.identity.ctime_sec = a.identity.ctime_sec;
    n.identity.ctime_nsec = a.identity.ctime_nsec;
    n == *a
}
fn write_json(path: &Path, value: &impl Serialize) -> Result<FilePin> {
    let mut b = serde_json::to_vec(value)?;
    b.push(b'\n');
    ensure(
        b.len() <= 4 * 1024 * 1024,
        "bounded owned configuration record",
    )?;
    files::write_new(path, &b, 0o400)?;
    File::open(path.parent().ok_or("configuration record parent")?)?.sync_all()?;
    files::pin_file(path)
}
fn read_json(path: &Path) -> Result<Value> {
    let pin = files::pin_file(path)?;
    let s = SealedInput::open(&pin)?;
    Ok(serde_json::from_slice(&s.read()?)?)
}

fn allowed(path: &Path, candidate: &str) -> bool {
    let s = path.to_string_lossy();
    if [
        "/etc/droidloom/cell.json",
        "/etc/droidloom/container-launcher.json",
        "/etc/droidloom-maintenance/installation.json",
        "/etc/droidloom/qualification/early.json",
        "/etc/droidloom/qualification/return.json",
        "/boot/grub/custom.cfg",
    ]
    .contains(&s.as_ref())
    {
        return true;
    }
    if let Some(name) = s.strip_prefix("/etc/droidloom/host-mac/") {
        return [
            "contract.json",
            "manager-label.json",
            "policy.bin",
            "policy-export.bin",
            "derivation.json",
        ]
        .contains(&name);
    }
    if s == format!("/boot/droidloom/qualification/{candidate}/initrd.img") {
        return true;
    }
    if s == format!(
        "/var/lib/droidloom/qualification/original-once-{candidate}/runtime-evidence/owner.lock"
    ) || s
        == "/etc/systemd/user/graphical-session.target.wants/droidloom-production-desktop.service"
    {
        return true;
    }
    let owner = format!("droidloom-original-qualification@{candidate}.service");
    if s == format!("/etc/systemd/system/{owner}")
        || s == format!("/etc/systemd/system/multi-user.target.wants/{owner}")
    {
        return true;
    }
    if let Some(unit) = s.strip_prefix("/etc/systemd/system/") {
        use crate::cold_original_once_recovery::contract as c;
        return c::PACKAGE_WRITERS.contains(&unit)
            || c::SUSPEND_TARGETS.contains(&unit)
            || [
                "droidloom-manager-label.service",
                "droidloom-instance-factory.service",
                "droidloom-instance-launcher.service",
                "droidloom-production.service",
                "droidloom-early-observer.service",
                "droidloom-original-once.target",
                "droidloom-original-once-return.service",
                "droidloom-original-once-return.timer",
                "user@1000.service.d/60-droidloom-original-once.conf",
            ]
            .contains(&unit);
    }
    false
}

fn parent_directories(path: &Path, work: &Path, candidate: &str, group: &str) -> Result<()> {
    ensure(
        allowed(path, candidate),
        "directory preparation target outside exact configuration roster",
    )?;
    let mut missing = Vec::new();
    let mut here = path.parent().ok_or("target parent")?;
    loop {
        match std::fs::symlink_metadata(here) {
            Ok(m) => {
                ensure(m.is_dir(), "configuration ancestor is not a directory")?;
                break;
            }
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => {
                missing.push(here.to_owned());
                here = here.parent().ok_or("configuration escaped root")?;
            }
            Err(e) => return Err(e.into()),
        }
    }
    for target in missing.iter().rev() {
        let ordinal = std::fs::read_dir(work)?
            .filter_map(|e| e.ok())
            .filter(|e| e.file_name().to_string_lossy().starts_with("dir-"))
            .count();
        ensure(ordinal < 128, "bounded source-created directories")?;
        let record = work.join(format!("dir-{ordinal:03}"));
        files::private_dir(&record)?;
        let staging = record.join("payload");
        files::private_dir(&staging)?;
        let pending = staging.join("value");
        let runtime = Path::new("/var/lib/droidloom/qualification")
            .join(format!("original-once-{candidate}"))
            .join("runtime-evidence");
        let mode = if target == &runtime { 0o700 } else { 0o755 };
        rustix::fs::mkdirat(&File::open(&staging)?, "value", Mode::from_raw_mode(mode))?;
        File::open(&pending)?.sync_all()?;
        File::open(&staging)?.sync_all()?;
        File::open(&record)?.sync_all()?;
        let i = Intent {
            schema: "droidloom.original-once-directory-intent.v2".into(),
            candidate_id: candidate.into(),
            group: group.into(),
            ordinal,
            logical_path: target.clone(),
            target: target.clone(),
            pending: pending.clone(),
            payload: Payload::Absent,
            original: None,
            prepared: observe_kind(&pending, true)?,
            parent: DirectoryState::capture(target.parent().ok_or("created public parent")?)?.state,
            private_parent: DirectoryState::capture(&staging)?.state,
            purpose_target: Some(path.into()),
        };
        ensure(
            observe_kind(target, true)?.is_none(),
            "create-only configuration directory appeared",
        )?;
        let pin = write_json(&record.join("INTENT.json"), &i)?;
        let actual = publish_one(&i)?;
        write_json(
            &record.join("PUBLISHED.json"),
            &json!({"intent":pin,"actual":actual}),
        )?;
    }
    at(path)?;
    Ok(())
}

/// All fields are private. The only public-to-module constructors require the
/// actual original owner; test fixtures reach the private finite rename core.
pub(super) struct Configurations {
    work: PathBuf,
    candidate: String,
    group: String,
}
impl Configurations {
    pub(super) fn create(a: &OriginalQualificationAuthority, group: &str) -> Result<Self> {
        a.verify_current_owner()?;
        ensure(
            ["owner", "package-masks", "runtime", "recovery", "grub"].contains(&group),
            "fixed once configuration group",
        )?;
        let root = a.work().join("configuration-transactions");
        if !root.exists() {
            files::private_dir(&root)?;
            File::open(a.work())?.sync_all()?;
        }
        let work = root.join(group);
        files::private_dir(&work)?;
        Ok(Self {
            work,
            candidate: a.candidate_id().into(),
            group: group.into(),
        })
    }
    pub(super) fn reopen(a: &OriginalQualificationAuthority, group: &str) -> Result<Option<Self>> {
        a.verify_current_owner()?;
        ensure(
            ["owner", "package-masks", "runtime", "recovery", "grub"].contains(&group),
            "fixed once configuration group",
        )?;
        let work = a.work().join("configuration-transactions").join(group);
        match std::fs::symlink_metadata(&work) {
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(None),
            Err(e) => return Err(e.into()),
            Ok(m) => ensure(m.is_dir(), "configuration work is not directory")?,
        };
        let tree = fs::Tree::open(&fs::absolute_string(&work)?, 0)?;
        let id = fs::stat(&tree.root)?;
        ensure(id.mode & 0o7777 == 0o700, "configuration work custody")?;
        Ok(Some(Self {
            work,
            candidate: a.candidate_id().into(),
            group: group.into(),
        }))
    }
    pub(super) fn publish(
        &self,
        a: &OriginalQualificationAuthority,
        entries: Vec<Entry>,
    ) -> Result<Value> {
        ensure(entries.len() <= 64, "bounded source configuration roster")?;
        let mut seen = std::collections::BTreeSet::new();
        for e in &entries {
            ensure(
                allowed(&e.path, &self.candidate) && seen.insert(e.path.clone()),
                "closed unique configuration target",
            )?;
            parent_directories(&e.path, &self.work, &self.candidate, &self.group)?;
        }
        seen.clear();
        let mut parents: BTreeMap<PathBuf, DirectoryState> = BTreeMap::new();
        let mut reports = Vec::new();
        for (ordinal, e) in entries.into_iter().enumerate() {
            a.verify_current_owner()?;
            ensure(
                allowed(&e.path, &self.candidate) && seen.insert(e.path.clone()),
                "configuration target not in fixed original-once scope",
            )?;
            parent_directories(&e.path, &self.work, &self.candidate, &self.group)?;
            let item = self.work.join(format!("item-{ordinal:03}"));
            files::private_dir(&item)?;
            let payload_directory = item.join("payload");
            files::private_dir(&payload_directory)?;
            let pending = payload_directory.join("value");
            match &e.payload {
                Payload::Regular { source, mode } => {
                    ensure(
                        [0o400, 0o444, 0o644, 0o755].contains(mode),
                        "fixed configuration mode required",
                    )?;
                    files::copy_pin(source, &pending, *mode)?;
                }
                Payload::Symlink { target } => {
                    ensure(
                        target.len() <= 512 && !target.contains('\0') && !target.contains('\n'),
                        "fixed configuration symlink required",
                    )?;
                    rustix::fs::symlinkat(
                        target.as_str(),
                        &File::open(&payload_directory)?,
                        "value",
                    )?;
                }
                Payload::Absent => {}
            }
            File::open(&payload_directory)?.sync_all()?;
            File::open(&item)?.sync_all()?;
            let original = observe(&e.path)?;
            let prepared = observe(&pending)?;
            let (parent, _) = at(&e.path)?;
            let intent = Intent {
                schema: "droidloom.original-once-configuration-intent.v1".into(),
                candidate_id: self.candidate.clone(),
                group: self.group.clone(),
                ordinal,
                logical_path: e.path.clone(),
                target: e.path.clone(),
                pending,
                payload: e.payload,
                original,
                prepared,
                parent: DirectoryState::held(e.path.parent().ok_or("public parent")?, &parent)?,
                private_parent: DirectoryState::capture(&payload_directory)?.state,
                purpose_target: None,
            };
            if let Some(previous) = parents.get(&intent.parent.path) {
                ensure(
                    previous == &intent.parent,
                    "own previous configuration parent checkpoint changed",
                )?;
            }
            let pin = write_json(&item.join("INTENT.json"), &intent)?;
            let actual = publish_one(&intent)?;
            let after = serde_json::from_value(actual["public_parent_after"].clone())?;
            advance_parent(&mut parents, &intent.parent, &after)?;
            reports.push(write_json(
                &item.join("PUBLISHED.json"),
                &json!({"intent":pin,"actual":actual}),
            )?);
            a.verify_current_owner()?;
        }
        let value = json!({"schema":"droidloom.original-once-configurations-published.v1","candidate_id":self.candidate,"group":self.group,"items":reports});
        let pin = write_json(&self.work.join("PUBLISHED.json"), &value)?;
        Ok(json!({"receipt":pin,"actual":value}))
    }
    pub(super) fn restore(
        &self,
        a: &OriginalQualificationAuthority,
        restoration: &mut ConfigurationRestoration,
    ) -> Result<Value> {
        a.verify_current_owner()?;
        let items = group_items(&self.work, &self.candidate, &self.group)?;
        let mut reports = Vec::new();
        for record in items.into_iter().rev() {
            a.verify_current_owner()?;
            let item = record.directory;
            let pin = record.pin;
            let seal = SealedInput::open(&pin)?;
            let mut i = record.intent;
            let out = item.join("RESTORED.json");
            if out.exists() {
                let v = read_json(&out)?;
                ensure(
                    v["intent"] == serde_json::to_value(&pin)?
                        && v["restore_source"] == serde_json::to_value(restoration.source.pin())?,
                    "existing reverse event source differs",
                )?;
                // The context constructor replayed all completed effects. No
                // existing event is rewritten or applied twice.
                let target = restored_target_observation(
                    &i.target,
                    i.purpose_target.is_some(),
                    i.original.is_none(),
                    &restoration.parents,
                    &restoration.retired_directories,
                )?;
                let retained: Option<Node> =
                    serde_json::from_value(v["actual"]["candidate_retained"].clone())?;
                ensure(
                    expected(&i.original, &target)
                        && observe_kind(&i.pending, i.purpose_target.is_some())? == retained,
                    "completed configuration original or retained candidate changed",
                )?;
                reports.push(files::pin_file(&out)?);
                continue;
            }
            let reverse_intent = item.join("RESTORE-INTENT.json");
            if reverse_intent.exists() {
                let v = read_json(&reverse_intent)?;
                ensure(
                    v["schema"] == "droidloom.original-once-configuration-reverse-intent.v1"
                        && v["intent"] == serde_json::to_value(&pin)?
                        && v["restore_source"] == serde_json::to_value(restoration.source.pin())?,
                    "durable reverse intent lost its actual sources",
                )?;
                let prepared: Option<Node> =
                    serde_json::from_value(v["candidate_expected"].clone())?;
                validate_reverse_candidate(&i, &prepared)?;
                i.prepared = prepared;
                for (path, key) in [
                    (&i.parent.path, "public_parent"),
                    (&i.private_parent.path, "private_parent"),
                ] {
                    ensure(
                        restoration.parents.get(path)
                            == Some(&serde_json::from_value(v[key].clone())?),
                        "reverse intent parent is not the actual configuration history",
                    )?;
                }
            } else if i.purpose_target.is_some() && restoration.parents.contains_key(&i.target) {
                let state = restoration
                    .parents
                    .get(&i.target)
                    .ok_or("created directory checkpoint missing")?;
                ensure(
                    state.members.is_empty(),
                    "source-created directory retains a foreign/unfinished child",
                )?;
                let prepared = i
                    .prepared
                    .as_mut()
                    .ok_or("created directory original node")?;
                ensure(
                    prepared.handle == state.handle
                        && prepared.handle_type == state.handle_type
                        && prepared.attributes == state.attributes
                        && prepared.identity.dev == state.identity.dev
                        && prepared.identity.ino == state.identity.ino
                        && prepared.identity.mode == state.identity.mode
                        && prepared.identity.uid == state.identity.uid
                        && prepared.identity.gid == state.identity.gid,
                    "created directory changed generation/owner/attrs",
                )?;
                prepared.identity = state.identity.clone();
            }
            restoration.revalidate(a)?;
            let public = restoration
                .parents
                .get(&i.parent.path)
                .ok_or("recorded configuration public parent absent")?;
            let private = restoration
                .parents
                .get(&i.private_parent.path)
                .ok_or("recorded private parent absent")?;
            if !reverse_intent.exists() {
                // The exact post-child directory identity is durable before
                // its reverse rename. A crash after rename never invents a
                // replacement generation or a fresh candidate preimage.
                write_json(
                    &reverse_intent,
                    &json!({"schema":"droidloom.original-once-configuration-reverse-intent.v1","intent":pin,"restore_source":restoration.source.pin(),"candidate_expected":i.prepared,"public_parent":public,"private_parent":private}),
                )?;
            }
            let actual = restore_one_from(&i, public, private)?;
            seal.revalidate()?;
            let out = item.join("RESTORED.json");
            if !out.exists() {
                write_json(
                    &out,
                    &json!({"intent":pin,"restore_source":restoration.source.pin(),"candidate_expected":i.prepared,"actual":actual}),
                )?;
            }
            let before: DirectoryState =
                serde_json::from_value(actual["public_parent_before"].clone())?;
            let after: DirectoryState =
                serde_json::from_value(actual["public_parent_after"].clone())?;
            advance_parent(&mut restoration.parents, &before, &after)?;
            let before: DirectoryState =
                serde_json::from_value(actual["private_parent_before"].clone())?;
            let after: DirectoryState =
                serde_json::from_value(actual["private_parent_after"].clone())?;
            advance_parent(&mut restoration.parents, &before, &after)?;
            if i.purpose_target.is_some() {
                let retained: Node = serde_json::from_value(actual["candidate_retained"].clone())?;
                ensure(
                    i.original.is_none(),
                    "only source-created directories may retire",
                )?;
                restoration
                    .retired_directories
                    .insert(i.target.clone(), (i.pending.clone(), retained));
                restoration.parents.remove(&i.target);
            }
            reports.push(files::pin_file(&out)?);
            restoration.revalidate(a)?;
            a.verify_current_owner()?;
        }
        Ok(
            json!({"schema":"droidloom.original-once-configurations-restored.v1","candidate_id":self.candidate,"group":self.group,"items":reports}),
        )
    }
}

/// No caller data or phase flag constructs this context. It is derived from
/// the exact configuration intent chain and, when labels ran, the opaque whole
/// restoration produced by the actual original-return transaction.
pub(super) struct ConfigurationRestoration {
    candidate: String,
    source: SealedInput,
    parents: BTreeMap<PathBuf, DirectoryState>,
    inputs: Vec<SealedInput>,
    // Populated only from this producer's actual completed directory reversals.
    // A vanished ancestor is never accepted merely because lookup returned ENOENT.
    retired_directories: BTreeMap<PathBuf, (PathBuf, Node)>,
}
fn restored_target_observation(
    path: &Path,
    directory: bool,
    original_absent: bool,
    parents: &BTreeMap<PathBuf, DirectoryState>,
    retired: &BTreeMap<PathBuf, (PathBuf, Node)>,
) -> Result<Option<Node>> {
    let removed = retired
        .iter()
        .filter(|(ancestor, _)| path.starts_with(ancestor))
        .min_by_key(|(ancestor, _)| ancestor.components().count());
    let Some((ancestor, (pending, saved))) = removed else {
        return observe_kind(path, directory);
    };
    ensure(
        original_absent,
        "an original configuration cannot disappear with an owned new directory",
    )?;
    let public = ancestor.parent().ok_or("retired directory public parent")?;
    let private = pending.parent().ok_or("retired directory private parent")?;
    parents
        .get(public)
        .ok_or("retired directory lacks its surviving ancestor checkpoint")?
        .reopen()?;
    parents
        .get(private)
        .ok_or("retired directory lacks its exact private checkpoint")?
        .reopen()?;
    ensure(
        observe_kind(ancestor, true)?.is_none()
            && observe_kind(pending, true)?.as_ref() == Some(saved),
        "missing configuration ancestor is not the retained original generation",
    )?;
    Ok(None)
}
struct Item {
    directory: PathBuf,
    pin: FilePin,
    intent: Intent,
}
fn valid_item(i: &Intent, record: &Path, root: &Path, candidate: &str, group: &str) -> Result<()> {
    let is_dir = i.purpose_target.is_some();
    ensure(
        i.candidate_id == candidate
            && i.group == group
            && i.pending == record.join("payload/value")
            && i.target == i.logical_path
            && i.parent.path == i.target.parent().ok_or("public parent")?
            && i.private_parent.path == i.pending.parent().ok_or("private parent")?
            && record
                == root.join(format!(
                    "{}-{:03}",
                    if is_dir { "dir" } else { "item" },
                    i.ordinal
                )),
        "closed configuration intent lineage",
    )?;
    if let Some(purpose) = &i.purpose_target {
        ensure(
            i.schema == "droidloom.original-once-directory-intent.v2"
                && allowed(purpose, candidate)
                && purpose.starts_with(&i.target)
                && purpose != &i.target
                && i.original.is_none()
                && i.prepared.as_ref().is_some_and(|n| {
                    n.identity.mode
                        == if i.target
                            == Path::new("/var/lib/droidloom/qualification")
                                .join(format!("original-once-{candidate}"))
                                .join("runtime-evidence")
                        {
                            0o40700
                        } else {
                            0o40755
                        }
                        && n.identity.uid == 0
                        && n.identity.gid == 0
                        && n.sha256.is_none()
                        && n.link.is_none()
                }),
            "source-created directory identity/purpose",
        )?;
    } else {
        ensure(
            i.schema == "droidloom.original-once-configuration-intent.v1"
                && allowed(&i.target, candidate),
            "configuration file source contract",
        )?;
    }
    Ok(())
}
fn group_items(root: &Path, candidate: &str, group: &str) -> Result<Vec<Item>> {
    let mut directories = Vec::new();
    let mut files_list = Vec::new();
    for entry in std::fs::read_dir(root)? {
        let entry = entry?;
        let name = entry
            .file_name()
            .into_string()
            .map_err(|_| "configuration history name")?;
        let (prefix, out) = if name.starts_with("dir-") {
            (4, &mut directories)
        } else if name.starts_with("item-") {
            (5, &mut files_list)
        } else {
            continue;
        };
        ensure(
            name.len() == prefix + 3 && name[prefix..].bytes().all(|b| b.is_ascii_digit()),
            "configuration history ordinal",
        )?;
        out.push(entry.path());
    }
    directories.sort();
    files_list.sort();
    ensure(
        directories.len() <= 128 && files_list.len() <= 64,
        "bounded source configuration history",
    )?;
    let mut result = Vec::new();
    for directory in directories.into_iter().chain(files_list) {
        let ip = directory.join("INTENT.json");
        if !ip.exists() {
            continue;
        }
        let pin = files::pin_file(&ip)?;
        let seal = SealedInput::open(&pin)?;
        let i: Intent = serde_json::from_slice(&seal.read()?)?;
        valid_item(&i, &directory, root, candidate, group)?;
        result.push(Item {
            directory,
            pin,
            intent: i,
        });
    }
    Ok(result)
}
fn configuration_items(a: &OriginalQualificationAuthority) -> Result<Vec<Item>> {
    let mut result = Vec::new();
    for group in ["owner", "package-masks", "runtime", "recovery", "grub"] {
        let root = a.work().join("configuration-transactions").join(group);
        if root.exists() {
            result.extend(group_items(&root, a.candidate_id(), group)?);
        }
    }
    Ok(result)
}
/// Read the exact source-owned package attempts in their dispatch order. A
/// missing observation can only be reconciled while its real command remains
/// the active interrupted operation; historical observations are never
/// compared to the later, legitimately evolved namespace.
pub(super) fn native_parent_history(
    a: &OriginalQualificationAuthority,
    operation: package_parents::NativeOperation,
    reconcile: bool,
) -> Result<Vec<package_parents::Changes>> {
    let root = a.work().join("native-package-parents");
    if !root.try_exists()? {
        return Ok(Vec::new());
    }
    let suffix = match operation {
        package_parents::NativeOperation::Install => "-native-apply",
        package_parents::NativeOperation::Rollback => "-native-rollback",
    };
    let mut names = Vec::new();
    for e in std::fs::read_dir(&root)? {
        let name = e?
            .file_name()
            .into_string()
            .map_err(|_| "native parent history nonUTF8 name")?;
        let rest = name
            .strip_prefix("dispatch-")
            .ok_or("native parent history command prefix")?;
        ensure(
            rest.len() > 5
                && rest.is_ascii()
                && rest.as_bytes()[4] == b'-'
                && rest[..4].bytes().all(|b| b.is_ascii_digit())
                && ["native-apply", "native-rollback"].contains(&&rest[5..])
                && names.len() < 4096,
            "bounded fixed native parent command roster",
        )?;
        if name.ends_with(suffix) {
            names.push(name);
        }
    }
    names.sort();
    let mut result = Vec::new();
    for name in names {
        if package_parents::preserve_uncommitted(a, operation, &name)?.is_some() {
            // This retained private prefix never acquired a BEFORE record or
            // command input. It cannot supply a package-success/directory delta.
            continue;
        }
        let path = root.join(&name).join("OBSERVATION.json");
        let changes = if path.try_exists()? {
            package_parents::Changes::reopen(a, &files::pin_file(&path)?)?
        } else {
            ensure(
                reconcile,
                "normal package metadata has no completed or interrupted observation",
            )?;
            let phase = a
                .journal
                .borrow()
                .phase()
                .ok_or("native parent reconciliation phase")?;
            let allowed = match operation {
                package_parents::NativeOperation::Install => matches!(
                    phase,
                    super::state::Phase::Aborting | super::state::Phase::NativeInstallIntent
                ),
                package_parents::NativeOperation::Rollback => {
                    phase == super::state::Phase::CellRestored
                }
            };
            ensure(
                allowed,
                "unobserved native operation is no longer the active interrupted phase",
            )?;
            package_parents::Capture::reopen(a, &name)?.reconcile_interrupted(a)?
        };
        result.push(changes);
    }
    Ok(result)
}
fn replay_native_parents(
    a: &OriginalQualificationAuthority,
    operation: package_parents::NativeOperation,
    states: &mut BTreeMap<PathBuf, DirectoryState>,
    inputs: &mut Vec<SealedInput>,
) -> Result<()> {
    for change in native_parent_history(a, operation, false)? {
        change.apply_to(states)?;
        inputs.push(SealedInput::open(change.pin())?);
    }
    Ok(())
}

fn published_parents(
    a: &OriginalQualificationAuthority,
) -> Result<(BTreeMap<PathBuf, DirectoryState>, Vec<SealedInput>)> {
    let mut states: BTreeMap<PathBuf, DirectoryState> = BTreeMap::new();
    let mut held = Vec::new();
    let items = configuration_items(a)?;
    for group in ["owner", "package-masks", "runtime", "recovery", "grub"] {
        for item in items.iter().filter(|item| item.intent.group == group) {
            let i = &item.intent;
            held.push(SealedInput::open(&item.pin)?);
            for before in [&i.parent, &i.private_parent] {
                if let Some(previous) = states.get(&before.path) {
                    ensure(
                        previous == before,
                        "configuration parent history contains an unowned intervening mutation",
                    )?;
                }
            }
            let path = item.directory.join("PUBLISHED.json");
            let (target, pending, p, q) = if path.exists() {
                let seal = SealedInput::open(&files::pin_file(&path)?)?;
                let row: Value = serde_json::from_slice(&seal.read()?)?;
                ensure(
                    row["intent"] == serde_json::to_value(&item.pin)?,
                    "published configuration source pin differs",
                )?;
                let values = (
                    serde_json::from_value::<Option<Node>>(row["actual"]["target"].clone())?,
                    serde_json::from_value::<Option<Node>>(
                        row["actual"]["original_retained"].clone(),
                    )?,
                    serde_json::from_value::<DirectoryState>(
                        row["actual"]["public_parent_after"].clone(),
                    )?,
                    serde_json::from_value::<DirectoryState>(
                        row["actual"]["private_parent_after"].clone(),
                    )?,
                );
                ensure(
                    expected(&i.prepared, &values.0) && expected(&i.original, &values.1),
                    "published source has unknown original/candidate inode",
                )?;
                held.push(seal);
                values
            } else {
                let target = observe_kind(&i.target, i.purpose_target.is_some())?;
                let pending = observe_kind(&i.pending, i.purpose_target.is_some())?;
                ensure(
                    expected(&i.original, &target) && expected(&i.prepared, &pending)
                        || expected(&i.prepared, &target) && expected(&i.original, &pending),
                    "interrupted configuration has unknown finite namespace",
                )?;
                (
                    target,
                    pending,
                    DirectoryState::capture(&i.parent.path)?.state,
                    DirectoryState::capture(&i.private_parent.path)?.state,
                )
            };
            i.parent.after_replace(
                &p,
                i.target
                    .file_name()
                    .and_then(|x| x.to_str())
                    .ok_or("public name")?,
                &target,
            )?;
            i.private_parent.after_replace(
                &q,
                i.pending
                    .file_name()
                    .and_then(|x| x.to_str())
                    .ok_or("private name")?,
                &pending,
            )?;
            advance_parent(&mut states, &i.parent, &p)?;
            advance_parent(&mut states, &i.private_parent, &q)?;
            // The directory's exact empty initial state is itself a later parent
            // checkpoint. Subsequent own child changes update it through the same
            // chain, including its identity as an ancestor's member.
            if i.purpose_target.is_some() {
                if let Some(n) = &target {
                    let state = DirectoryState {
                        path: i.target.clone(),
                        identity: n.identity.clone(),
                        handle_type: n.handle_type,
                        handle: n.handle.clone(),
                        attributes: n.attributes.clone(),
                        members: BTreeMap::new(),
                    };
                    ensure(
                        states.insert(i.target.clone(), state).is_none(),
                        "duplicate prepared directory",
                    )?;
                }
            }
        }
        if group == "package-masks" {
            replay_native_parents(
                a,
                package_parents::NativeOperation::Install,
                &mut states,
                &mut held,
            )?;
        }
    }
    Ok((states, held))
}

fn identity_from_label(
    row: &Value,
    old: &Identity,
    now: &Identity,
    handle_type: i32,
    handle: &str,
) -> Result<()> {
    let before: Identity = serde_json::from_value(row["prelabel"]["identity"].clone())?;
    let restored: Identity = serde_json::from_value(row["restored"]["identity"].clone())?;
    let before_handle = &row["prelabel"]["handle"];
    let restored_handle = &row["restored"]["handle"];
    let bytes: Vec<u8> = serde_json::from_value(before_handle["bytes"].clone())?;
    ensure(
        before == *old
            && restored == *now
            && before_handle == restored_handle
            && before_handle["handle_type"] == handle_type
            && hex::encode(bytes) == handle,
        "restored configuration metadata is not the same actual prelabel generation",
    )
}
fn restoration_checkpoint_path(work: &Path, labels: Option<&FilePin>) -> Result<PathBuf> {
    match labels {
        Some(pin) => {
            ensure(
                fs::valid_digest(&pin.sha256),
                "actual label restoration digest required",
            )?;
            Ok(work.join(format!("CONFIGURATION-RESTORE-SOURCE-{}.json", pin.sha256)))
        }
        None => Ok(work.join("CONFIGURATION-RESTORE-SOURCE.json")),
    }
}
fn preservation_checkpoint_path(work: &Path, labels: &FilePin) -> Result<PathBuf> {
    ensure(
        fs::valid_digest(&labels.sha256),
        "actual label restoration digest required",
    )?;
    Ok(work.join(format!(
        "NORMAL-PACKAGE-PRESERVATION-{}.json",
        labels.sha256
    )))
}
impl ConfigurationRestoration {
    pub(super) fn pin(&self) -> &FilePin {
        self.source.pin()
    }
    pub(super) fn unlabelled(a: &OriginalQualificationAuthority) -> Result<Self> {
        a.verify_current_owner()?;
        ensure(
            a.journal
                .borrow()
                .observation(super::state::Phase::LabelsIntent)?
                .is_none(),
            "unlabelled recovery cannot bypass an actual label intent",
        )?;
        let retained = a.work().join("CONFIGURATION-RESTORE-SOURCE.json");
        if retained.exists() {
            return Self::reopen(a, &files::pin_file(&retained)?);
        }
        let (parents, inputs) = published_parents(a)?;
        for p in parents.values() {
            p.reopen()?;
        }
        Self::persist(a, parents, inputs, Vec::new(), None, Value::Null)
    }
    pub(super) fn after_labels(
        retirement: &super::OriginalRetirement,
        data: &crate::cold_original_data::OriginalDataTransaction,
        labels: &crate::cold_original_data::labels::OriginalLabelsRestored,
    ) -> Result<Self> {
        let a = retirement.authority();
        retirement.revalidate()?;
        labels.verify_complete(retirement, data)?;
        let retained = restoration_checkpoint_path(a.work(), Some(labels.report()))?;
        if retained.exists() {
            let p = files::pin_file(&retained)?;
            let old = read_json(&retained)?;
            ensure(
                old["actual_label_restoration"] == serde_json::to_value(labels.report())?,
                "retained configuration metadata proof belongs to a different actual label restoration",
            )?;
            return Self::reopen(a, &p);
        }
        let runtime = retirement.runtime_inventory()?;
        let runtime_path = Path::new("/var/lib/droidloom/qualification")
            .join(format!("original-once-{}", a.candidate_id()))
            .join("runtime-evidence");
        let mut newborn = BTreeMap::<PathBuf, Node>::new();
        if !runtime["actual"].is_null() {
            ensure(
                runtime["actual"]["directory"] == runtime_path.to_string_lossy().as_ref(),
                "runtime inventory path differs",
            )?;
            for row in runtime["actual"]["files"]
                .as_array()
                .ok_or("actual held runtime roster")?
            {
                let p: FilePin = serde_json::from_value(row["pin"].clone())?;
                ensure(
                    p.path.parent() == Some(runtime_path.as_path())
                        && p.path.file_name().and_then(|n| n.to_str()) == row["name"].as_str(),
                    "actual runtime birth member location",
                )?;
                let n = observe(&p.path)?.ok_or("retired runtime member disappeared")?;
                ensure(
                    serde_json::to_value(&n.identity)? == row["identity"]
                        && serde_json::to_value(&n.attributes)? == row["attributes"]
                        && n.sha256.as_deref() == Some(p.sha256.as_str())
                        && n.identity.size == p.bytes,
                    "runtime birth is not the actual held retirement file",
                )?;
                ensure(
                    newborn.insert(p.path.clone(), n).is_none(),
                    "duplicate actual runtime member",
                )?;
            }
        }
        let (mut parents, inputs) = published_parents(a)?;
        let mut current = BTreeMap::new();
        let mut wanted = std::collections::BTreeSet::new();
        for (path, old) in &parents {
            let now = DirectoryState::capture(path)?.state;
            let mut expected_names = old
                .members
                .keys()
                .cloned()
                .collect::<std::collections::BTreeSet<_>>();
            if path == &runtime_path {
                for (p, n) in &newborn {
                    let name = p
                        .file_name()
                        .and_then(|s| s.to_str())
                        .ok_or("runtime name")?;
                    ensure(
                        !old.members.contains_key(name) && expected_names.insert(name.into()),
                        "runtime birth collides with an original label preimage",
                    )?;
                    let member = now
                        .members
                        .get(name)
                        .ok_or("actual runtime member absent from parent")?;
                    ensure(
                        member.identity == n.identity
                            && member.handle_type == n.handle_type
                            && member.handle == n.handle,
                        "actual runtime generation changed",
                    )?;
                }
            }
            ensure(
                now.handle == old.handle
                    && now.handle_type == old.handle_type
                    && now
                        .members
                        .keys()
                        .cloned()
                        .collect::<std::collections::BTreeSet<_>>()
                        == expected_names,
                "restored configuration parent generation/member names differ",
            )?;
            if now.identity != old.identity || now.attributes != old.attributes {
                wanted.insert(path.clone());
            }
            for (name, member) in &old.members {
                let actual = &now.members[name];
                ensure(
                    member.handle == actual.handle && member.handle_type == actual.handle_type,
                    "restored configuration sibling generation differs",
                )?;
                if member.identity != actual.identity {
                    wanted.insert(path.join(name));
                }
            }
            current.insert(path.clone(), now);
        }
        let mut rows = BTreeMap::new();
        let mut proofs = Vec::new();
        let paths = wanted.into_iter().collect::<Vec<_>>();
        for chunk in paths.chunks(256) {
            let proof = labels.restored_metadata_derivations(retirement, data, chunk)?;
            for (path, row) in proof["paths"]
                .as_object()
                .ok_or("actual label metadata paths")?
            {
                ensure(
                    rows.insert(PathBuf::from(path), row.clone()).is_none(),
                    "duplicate actual metadata query",
                )?;
            }
            proofs.push(proof);
        }
        for (path, old) in &mut parents {
            let now = &current[path];
            if now.identity != old.identity || now.attributes != old.attributes {
                let row = rows
                    .get(path)
                    .ok_or("missing real parent label derivation")?;
                identity_from_label(
                    row,
                    &old.identity,
                    &now.identity,
                    old.handle_type,
                    &old.handle,
                )?;
                let before: BTreeMap<String, Vec<u8>> =
                    serde_json::from_value(row["prelabel"]["attributes"].clone())?;
                let after: BTreeMap<String, Vec<u8>> =
                    serde_json::from_value(row["restored"]["attributes"].clone())?;
                ensure(
                    before
                        .into_iter()
                        .map(|(k, v)| (k, hex::encode(v)))
                        .collect::<BTreeMap<_, _>>()
                        == old.attributes
                        && after
                            .into_iter()
                            .map(|(k, v)| (k, hex::encode(v)))
                            .collect::<BTreeMap<_, _>>()
                            == now.attributes,
                    "restored parent attributes lack exact actual source derivation",
                )?;
            }
            for (name, member) in &old.members {
                let actual = &now.members[name];
                if actual.identity != member.identity {
                    identity_from_label(
                        rows.get(&path.join(name))
                            .ok_or("missing actual sibling label derivation")?,
                        &member.identity,
                        &actual.identity,
                        member.handle_type,
                        &member.handle,
                    )?;
                }
            }
            *old = now.clone();
        }
        Self::persist(
            a,
            parents,
            inputs,
            proofs,
            Some(labels.report()),
            json!({"actual_retirement":retirement.report_pin(),"held_inventory":runtime,"members":newborn}),
        )
    }
    fn persist(
        a: &OriginalQualificationAuthority,
        parents: BTreeMap<PathBuf, DirectoryState>,
        inputs: Vec<SealedInput>,
        proofs: Vec<Value>,
        labels: Option<&FilePin>,
        runtime: Value,
    ) -> Result<Self> {
        let value = json!({"schema":"droidloom.original-once-configuration-restore-source.v1","candidate_id":a.candidate_id(),"intent":a.intent.pin(),"parents":parents,"source_inputs":inputs.iter().map(SealedInput::pin).collect::<Vec<_>>(),"actual_label_restoration":labels,"actual_metadata_derivations":proofs,"actual_runtime_births":runtime});
        let destination = restoration_checkpoint_path(a.work(), labels)?;
        let pin = if destination.exists() {
            ensure(
                read_json(&destination)? == value,
                "unacknowledged configuration restore source differs from actual reconstruction",
            )?;
            files::pin_file(&destination)?
        } else {
            write_json(&destination, &value)?
        };
        let result = Self {
            candidate: a.candidate_id().into(),
            source: SealedInput::open(&pin)?,
            parents,
            inputs,
            retired_directories: BTreeMap::new(),
        };
        result.revalidate(a)?;
        Ok(result)
    }
    pub(super) fn reopen(a: &OriginalQualificationAuthority, pin: &FilePin) -> Result<Self> {
        a.verify_current_owner()?;
        let source = SealedInput::open(pin)?;
        let value: Value = serde_json::from_slice(&source.read()?)?;
        let labels: Option<FilePin> =
            serde_json::from_value(value["actual_label_restoration"].clone())?;
        ensure(
            pin.path == restoration_checkpoint_path(a.work(), labels.as_ref())?,
            "configuration restoration source location",
        )?;
        ensure(
            value["schema"] == "droidloom.original-once-configuration-restore-source.v1"
                && value["candidate_id"] == a.candidate_id()
                && value["intent"] == serde_json::to_value(a.intent.pin())?,
            "configuration rollback source changed",
        )?;
        let parents = serde_json::from_value(value["parents"].clone())?;
        let pins: Vec<FilePin> = serde_json::from_value(value["source_inputs"].clone())?;
        let mut result = Self {
            candidate: a.candidate_id().into(),
            source,
            parents,
            inputs: pins.iter().map(SealedInput::open).collect::<Result<_>>()?,
            retired_directories: BTreeMap::new(),
        };
        let archives = replay_runtime_archives(a, &mut result)?;
        let items = configuration_items(a)?;
        for group in ["grub", "recovery", "runtime", "package-masks", "owner"] {
            for item in items.iter().rev().filter(|item| item.intent.group == group) {
                let path = item.directory.join("RESTORED.json");
                if !path.exists() {
                    continue;
                }
                let pin = files::pin_file(&path)?;
                let seal = SealedInput::open(&pin)?;
                let v: Value = serde_json::from_slice(&seal.read()?)?;
                ensure(
                    v["intent"] == serde_json::to_value(&item.pin)?
                        && v["restore_source"] == serde_json::to_value(result.source.pin())?,
                    "configuration reverse event source differs",
                )?;
                let i = &item.intent;
                let target: Option<Node> = serde_json::from_value(v["actual"]["original"].clone())?;
                let pending: Option<Node> =
                    serde_json::from_value(v["actual"]["candidate_retained"].clone())?;
                let candidate_expected: Option<Node> =
                    serde_json::from_value(v["candidate_expected"].clone())?;
                validate_reverse_candidate(i, &candidate_expected)?;
                ensure(
                    expected(&i.original, &target) && expected(&candidate_expected, &pending),
                    "configuration reverse event inode differs",
                )?;
                for (key, before_key, after_key, name, node) in [
                    (
                        &i.parent.path,
                        "public_parent_before",
                        "public_parent_after",
                        i.target.file_name(),
                        &target,
                    ),
                    (
                        &i.private_parent.path,
                        "private_parent_before",
                        "private_parent_after",
                        i.pending.file_name(),
                        &pending,
                    ),
                ] {
                    let before: DirectoryState =
                        serde_json::from_value(v["actual"][before_key].clone())?;
                    let after: DirectoryState =
                        serde_json::from_value(v["actual"][after_key].clone())?;
                    ensure(
                        result.parents.get(key) == Some(&before),
                        "configuration reverse parent chain was rewritten",
                    )?;
                    before.after_replace(
                        &after,
                        name.and_then(|x| x.to_str())
                            .ok_or("configuration reverse child")?,
                        node,
                    )?;
                    advance_parent(&mut result.parents, &before, &after)?;
                }
                if i.purpose_target.is_some() {
                    ensure(
                        i.original.is_none(),
                        "only source-created directory history may retire",
                    )?;
                    result.retired_directories.insert(
                        i.target.clone(),
                        (
                            i.pending.clone(),
                            pending
                                .clone()
                                .ok_or("retired directory candidate absent")?,
                        ),
                    );
                    result.parents.remove(&i.target);
                }
                result.inputs.push(seal);
            }
            if group == "runtime" {
                replay_native_parents(
                    a,
                    package_parents::NativeOperation::Rollback,
                    &mut result.parents,
                    &mut result.inputs,
                )?;
            }
        }
        // Current public paths are checked only after the complete historical
        // configuration reverse chain has reconstructed any retired ancestors.
        for (path, destination, saved) in archives {
            ensure(
                restored_target_observation(
                    &path,
                    false,
                    true,
                    &result.parents,
                    &result.retired_directories,
                )?
                .is_none()
                    && observe(&destination)?.as_ref() == Some(&saved),
                "archived runtime evidence is not in its actual restored placement",
            )?;
        }
        result.revalidate(a)?;
        Ok(result)
    }
    pub(super) fn advance_native(
        &mut self,
        a: &OriginalQualificationAuthority,
        change: &package_parents::Changes,
    ) -> Result<()> {
        self.revalidate(a)?;
        change.apply_to(&mut self.parents)?;
        self.inputs.push(SealedInput::open(change.pin())?);
        self.revalidate(a)
    }
    fn revalidate(&self, a: &OriginalQualificationAuthority) -> Result<()> {
        ensure(
            self.candidate == a.candidate_id(),
            "configuration rollback candidate differs",
        )?;
        self.source.revalidate()?;
        for input in &self.inputs {
            input.revalidate()?;
        }
        Ok(())
    }
}

fn expected(node: &Option<Node>, actual: &Option<Node>) -> bool {
    match (node, actual) {
        (None, None) => true,
        (Some(a), Some(b)) => same_inode(a, b) && same_except_ctime(a, b),
        _ => false,
    }
}

fn f9(id: &Identity) -> Value {
    json!([
        id.dev,
        id.ino,
        id.mode,
        id.uid,
        id.gid,
        id.nlink,
        id.size,
        i128::from(id.mtime_sec) * 1_000_000_000 + i128::from(id.mtime_nsec),
        i128::from(id.ctime_sec) * 1_000_000_000 + i128::from(id.ctime_nsec)
    ])
}

/// This seal is produced from the actual typed return and complete label
/// restoration. It does not rewrite either normal package snapshot. Both
/// engines still compare every preserved node, using only this exact observed
/// source -> runtime -> restored metadata evolution where necessary.
pub(super) fn seal_public_preservation(
    retirement: &super::OriginalRetirement,
    data: &crate::cold_original_data::OriginalDataTransaction,
    restored: &crate::cold_original_data::labels::OriginalLabelsRestored,
) -> Result<FilePin> {
    let a = retirement.authority();
    retirement.revalidate()?;
    let mut wanted = std::collections::BTreeSet::new();
    let mut snapshots = BTreeMap::new();
    for (kind, phase, key) in [
        (
            "public",
            super::state::Phase::PublicInstallIntent,
            "preserved_metadata_only",
        ),
        (
            "native",
            super::state::Phase::NativeInstallIntent,
            "private_metadata",
        ),
    ] {
        let Some(event) = a.journal.borrow().observation(phase)? else {
            continue;
        };
        let p: FilePin = serde_json::from_value(event["actual"]["snapshot"].clone())?;
        let v: Value = serde_json::from_slice(&files::read_pin(&p, 32 * 1024 * 1024)?)?;
        let fields = v[key]
            .as_object()
            .ok_or("actual normal snapshot preservation roster")?;
        for (name, node) in fields {
            if kind == "native" && node["absent"] == true {
                continue;
            }
            let path = PathBuf::from(if name.starts_with('/') {
                name.clone()
            } else {
                format!("/{name}")
            });
            ensure(
                [
                    "/etc/passwd",
                    "/etc/group",
                    "/etc/shadow",
                    "/etc/gshadow",
                    "/etc/ssh",
                    "/etc/ssh/sshd_config",
                    "/etc/ssh/ssh_host_ed25519_key",
                    "/etc/ssh/ssh_host_rsa_key",
                    "/home",
                    "/home/alex",
                ]
                .iter()
                .any(|s| path == Path::new(s)),
                "unreviewed preserved normal package path",
            )?;
            wanted.insert(path);
        }
        snapshots.insert(kind, json!({"snapshot":p,"original":fields}));
    }
    let proof = restored.restored_metadata_derivations(
        retirement,
        data,
        &wanted.into_iter().collect::<Vec<_>>(),
    )?;
    for (kind, source) in &snapshots {
        for (name, old) in source["original"].as_object().ok_or("snapshot fields")? {
            if *kind == "native" && old["absent"] == true {
                continue;
            }
            let path = if name.starts_with('/') {
                name.clone()
            } else {
                format!("/{name}")
            };
            let row = &proof["paths"][&path];
            let before: Identity = serde_json::from_value(row["prelabel"]["identity"].clone())?;
            let expected = if *kind == "public" { old } else { &old["f9"] };
            ensure(
                f9(&before) == *expected,
                "normal package preservation preimage differs from the actual prelabel source",
            )?;
        }
    }
    let value = json!({"schema":"droidloom.original-once-package-preservation.v1","candidate_id":a.candidate_id(),"intent":a.intent.pin(),"actual_retirement":retirement.report_pin(),"actual_label_restoration":restored.report(),"snapshots":snapshots,"metadata":proof});
    let path = preservation_checkpoint_path(a.work(), restored.report())?;
    let p = if path.try_exists()? {
        ensure(
            read_json(&path)? == value,
            "retained normal preservation differs from the actual same restoration",
        )?;
        files::pin_file(&path)?
    } else {
        write_json(&path, &value)?
    };
    retirement.revalidate()?;
    Ok(p)
}
pub(super) fn public_preservation_pin(
    a: &OriginalQualificationAuthority,
) -> Result<Option<FilePin>> {
    let event = {
        let journal = a.journal.borrow();
        journal
            .observation(super::state::Phase::CellRestoreIntent)?
            .or(journal.observation(super::state::Phase::LabelsRestored)?)
    };
    let labels_prepared = a
        .journal
        .borrow()
        .observation(super::state::Phase::LabelsIntent)?
        .is_some();
    let Some(event) = event else {
        ensure(
            !labels_prepared,
            "labelled package rollback has no durable restoration checkpoint",
        )?;
        return Ok(None);
    };
    if event["package_preservation"].is_null() {
        ensure(
            !labels_prepared,
            "labelled package restoration lacks actual metadata evolution",
        )?;
        return Ok(None);
    }
    let p: FilePin = serde_json::from_value(event["package_preservation"].clone())?;
    let seal = SealedInput::open(&p)?;
    let v: Value = serde_json::from_slice(&seal.read()?)?;
    let labels: FilePin = serde_json::from_value(v["actual_label_restoration"].clone())?;
    ensure(
        p.path == preservation_checkpoint_path(a.work(), &labels)?
            && v["schema"] == "droidloom.original-once-package-preservation.v1"
            && v["candidate_id"] == a.candidate_id()
            && v["intent"] == serde_json::to_value(a.intent.pin())?
            && event["actual_retirement"] == v["actual_retirement"],
        "package metadata evolution belongs to another actual preparation",
    )?;
    Ok(Some(p))
}

pub(super) struct PackagePreservation {
    seal: SealedInput,
    held: Vec<(PathBuf, File, MemberIdentity, BTreeMap<String, String>)>,
}
impl PackagePreservation {
    pub(super) fn open(a: &OriginalQualificationAuthority, pin: &FilePin) -> Result<Self> {
        ensure(
            public_preservation_pin(a)?
                .as_ref()
                .is_some_and(|p| super::same_pin(p, pin)),
            "normal rollback requested another metadata proof",
        )?;
        let seal = SealedInput::open(pin)?;
        let value: Value = serde_json::from_slice(&seal.read()?)?;
        let mut held = Vec::new();
        for (path, row) in value["metadata"]["paths"]
            .as_object()
            .ok_or("normal metadata proof paths")?
        {
            let path = PathBuf::from(path);
            let (parent, leaf) = at(&path)?;
            let file = File::from(rustix::fs::openat(
                &parent,
                leaf.as_str(),
                OFlags::PATH | OFlags::NOFOLLOW | OFlags::CLOEXEC,
                Mode::empty(),
            )?);
            let m = member(&file)?;
            let x = attrs(&file)?;
            let restored = &row["restored"];
            let h: Vec<u8> = serde_json::from_value(restored["handle"]["bytes"].clone())?;
            let expected_attrs: BTreeMap<String, Vec<u8>> =
                serde_json::from_value(restored["attributes"].clone())?;
            ensure(
                serde_json::to_value(&m.identity)? == restored["identity"]
                    && restored["handle"]["handle_type"] == m.handle_type
                    && hex::encode(h) == m.handle
                    && expected_attrs
                        .into_iter()
                        .map(|(k, v)| (k, hex::encode(v)))
                        .collect::<BTreeMap<_, _>>()
                        == x,
                "normal rollback preserved inode is not the actual same-generation restored value",
            )?;
            held.push((path, file, m, x));
        }
        ensure(
            !held.is_empty() && held.len() <= 16,
            "fixed preservation proof bound",
        )?;
        let result = Self { seal, held };
        result.revalidate()?;
        Ok(result)
    }
    pub(super) fn revalidate(&self) -> Result<()> {
        self.seal.revalidate()?;
        for (path, held, id, x) in &self.held {
            let (parent, name) = at(path)?;
            let named = File::from(rustix::fs::openat(
                &parent,
                name.as_str(),
                OFlags::PATH | OFlags::NOFOLLOW | OFlags::CLOEXEC,
                Mode::empty(),
            )?);
            ensure(
                member(held)? == *id
                    && member(&named)? == *id
                    && attrs(held)? == *x
                    && attrs(&named)? == *x,
                "normal package changed preserved account/SSH/home metadata beyond the actual label derivation",
            )?;
        }
        self.seal.revalidate()
    }
}

pub(super) fn package_writers_preimage(
    a: &OriginalQualificationAuthority,
) -> Result<Option<FilePin>> {
    let root = a.work().join("commands");
    if !root.exists() {
        return Ok(None);
    }
    let mut found = None;
    for e in std::fs::read_dir(&root)? {
        let p = e?.path().join("WRITERS-INTENT.json");
        if !p.exists() {
            continue;
        }
        let pin = files::pin_file(&p)?;
        let seal = SealedInput::open(&pin)?;
        let v: Value = serde_json::from_slice(&seal.read()?)?;
        ensure(
            v["schema"] == "droidloom.original-once-package-writers.v1"
                && v["candidate_id"] == a.candidate_id()
                && v["intent"] == serde_json::to_value(a.intent.pin())?,
            "writer preimage identity differs",
        )?;
        ensure(
            found.replace(pin).is_none(),
            "multiple initial writer inventories",
        )?;
    }
    Ok(found)
}

// Replay completed archive actions before configuration reversals. Their
// source inventory is a real held retirement observation of newly born files,
// never a synthetic original label preimage. Reopening performs no mutation.
fn replay_runtime_archives(
    a: &OriginalQualificationAuthority,
    ctx: &mut ConfigurationRestoration,
) -> Result<Vec<(PathBuf, PathBuf, Node)>> {
    let source: Value = serde_json::from_slice(&ctx.source.read()?)?;
    let birth = &source["actual_runtime_births"];
    if birth.is_null() {
        return Ok(Vec::new());
    }
    let nodes: BTreeMap<PathBuf, Node> = serde_json::from_value(birth["members"].clone())?;
    let root = Path::new("/var/lib/droidloom/qualification")
        .join(format!("original-once-{}", a.candidate_id()))
        .join("runtime-evidence");
    let archive = a.work().join("runtime-evidence-archive");
    let mut gap = false;
    let mut archived = Vec::new();
    for (ordinal, (path, expected)) in nodes.iter().enumerate() {
        ensure(
            path.parent() == Some(root.as_path())
                && path.file_name() != Some(std::ffi::OsStr::new("owner.lock")),
            "fixed runtime birth replay path",
        )?;
        let record = archive.join(format!("member-{ordinal:02}"));
        let complete = record.join("ARCHIVED.json");
        if !complete.exists() {
            gap = true;
            continue;
        }
        ensure(
            !gap,
            "runtime archive history skipped an earlier exact member",
        )?;
        let cp = files::pin_file(&complete)?;
        let guard = SealedInput::open(&cp)?;
        let v: Value = serde_json::from_slice(&guard.read()?)?;
        let ip = files::pin_file(&record.join("INTENT.json"))?;
        let intent = SealedInput::open(&ip)?;
        let iv: Value = serde_json::from_slice(&intent.read()?)?;
        let destination = record.join("payload/evidence");
        ensure(
            v["schema"] == "droidloom.original-once-runtime-archived.v1"
                && v["configuration_source"] == serde_json::to_value(ctx.source.pin())?
                && v["logical_path"] == path.to_string_lossy().as_ref()
                && v["original"] == serde_json::to_value(expected)?
                && v["destination"] == destination.to_string_lossy().as_ref()
                && iv["schema"] == "droidloom.original-once-runtime-archive-intent.v1"
                && iv["configuration_source"] == v["configuration_source"]
                && iv["logical_path"] == v["logical_path"]
                && iv["expected"] == v["original"]
                && iv["actual_retirement"] == birth["actual_retirement"],
            "runtime archive lost its immutable actual sources",
        )?;
        let before: DirectoryState = serde_json::from_value(v["public_parent_before"].clone())?;
        let after: DirectoryState = serde_json::from_value(v["public_parent_after"].clone())?;
        let pb: DirectoryState = serde_json::from_value(v["private_parent_before"].clone())?;
        let pa: DirectoryState = serde_json::from_value(v["private_parent_after"].clone())?;
        let saved: Node = serde_json::from_value(v["archived"].clone())?;
        ensure(
            before.path == root
                && pb.path == record.join("payload")
                && iv["public_parent"] == serde_json::to_value(&before)?
                && iv["private_parent"] == serde_json::to_value(&pb)?
                && same_except_ctime(&saved, expected),
            "runtime archive changed the exact generation or evidence bytes",
        )?;
        before.after_replace(
            &after,
            path.file_name()
                .and_then(|n| n.to_str())
                .ok_or("runtime leaf")?,
            &None,
        )?;
        pb.after_replace(&pa, "evidence", &Some(saved.clone()))?;
        ensure(
            observe(&destination)?.as_ref() == Some(&saved),
            "archived runtime file changed after its actual return",
        )?;
        archived.push((path.clone(), destination, saved));
        pa.reopen()?;
        advance_parent(&mut ctx.parents, &before, &after)?;
        ctx.inputs.push(intent);
        ctx.inputs.push(guard);
    }
    Ok(archived)
}

/// New runtime evidence is archived after the typed label restoration, with
/// its own preimage and exact finite rename. It is never claimed to be an old
/// label target. Original owner.lock and directory restoration happens later.
pub(super) fn archive_runtime_evidence(
    a: &OriginalQualificationAuthority,
    ctx: &mut ConfigurationRestoration,
) -> Result<Value> {
    a.verify_current_owner()?;
    ctx.revalidate(a)?;
    let source: Value = serde_json::from_slice(&ctx.source.read()?)?;
    let birth = &source["actual_runtime_births"];
    if birth.is_null() {
        return Ok(json!({"runtime_files":0,"actual_birth_inventory_absent":true}));
    }
    let nodes: BTreeMap<PathBuf, Node> = serde_json::from_value(birth["members"].clone())?;
    let root = Path::new("/var/lib/droidloom/qualification")
        .join(format!("original-once-{}", a.candidate_id()))
        .join("runtime-evidence");
    let archive = a.work().join("runtime-evidence-archive");
    if !archive.exists() {
        files::private_dir(&archive)?;
        File::open(a.work())?.sync_all()?;
    }
    let mut reports = Vec::new();
    for (ordinal, (path, node)) in nodes.iter().enumerate() {
        ensure(
            path.parent() == Some(root.as_path())
                && path.file_name() != Some(std::ffi::OsStr::new("owner.lock")),
            "archive source is not an admitted runtime birth",
        )?;
        let name = path
            .file_name()
            .and_then(|s| s.to_str())
            .ok_or("runtime birth name")?;
        let record = archive.join(format!("member-{ordinal:02}"));
        if !record.exists() {
            files::private_dir(&record)?;
            File::open(&archive)?.sync_all()?;
        }
        let payload = record.join("payload");
        if !payload.exists() {
            files::private_dir(&payload)?;
            File::open(&record)?.sync_all()?;
        }
        let target = payload.join("evidence");
        let intent = record.join("INTENT.json");
        let complete = record.join("ARCHIVED.json");
        if complete.exists() {
            let v = read_json(&complete)?;
            ensure(
                v["configuration_source"] == serde_json::to_value(ctx.source.pin())?
                    && v["logical_path"] == path.to_string_lossy().as_ref(),
                "runtime archive replay lost its real source",
            )?;
            let after: DirectoryState = serde_json::from_value(v["public_parent_after"].clone())?;
            let before: DirectoryState = serde_json::from_value(v["public_parent_before"].clone())?;
            if ctx.parents.get(&root) == Some(&before) {
                advance_parent(&mut ctx.parents, &before, &after)?;
            }
            let saved: Node = serde_json::from_value(v["archived"].clone())?;
            let private: DirectoryState =
                serde_json::from_value(v["private_parent_after"].clone())?;
            ensure(
                same_except_ctime(&saved, node)
                    && observe(path)?.is_none()
                    && observe(&target)?.as_ref() == Some(&saved),
                "completed runtime archive evidence changed",
            )?;
            private.reopen()?;
            reports.push(files::pin_file(&complete)?);
            continue;
        }
        let (before, private_before) = if intent.exists() {
            let v = read_json(&intent)?;
            ensure(
                v["configuration_source"] == serde_json::to_value(ctx.source.pin())?
                    && v["logical_path"] == path.to_string_lossy().as_ref()
                    && v["expected"] == serde_json::to_value(node)?,
                "runtime archive intent changed",
            )?;
            (
                serde_json::from_value::<DirectoryState>(v["public_parent"].clone())?,
                serde_json::from_value::<DirectoryState>(v["private_parent"].clone())?,
            )
        } else {
            let public = ctx
                .parents
                .get(&root)
                .ok_or("runtime parent lacks its actual restored checkpoint")?
                .clone();
            public.reopen()?;
            let private = DirectoryState::capture(&payload)?.state;
            ensure(
                observe(path)?.as_ref() == Some(node) && observe(&target)?.is_none(),
                "runtime birth changed before durable archive",
            )?;
            write_json(
                &intent,
                &json!({"schema":"droidloom.original-once-runtime-archive-intent.v1","configuration_source":ctx.source.pin(),"actual_retirement":birth["actual_retirement"],"logical_path":path,"expected":node,"public_parent":public,"private_parent":private}),
            )?;
            (public, private)
        };
        ensure(
            ctx.parents.get(&root) == Some(&before),
            "runtime archive public checkpoint differs",
        )?;
        let current = observe(path)?;
        let saved = observe(&target)?;
        if current.as_ref() == Some(node) && saved.is_none() {
            let src = before.reopen()?;
            let dst = private_before.reopen()?;
            rustix::fs::renameat_with(
                &src.file,
                name,
                &dst.file,
                "evidence",
                RenameFlags::NOREPLACE,
            )?;
            src.file.sync_all()?;
            dst.file.sync_all()?;
        } else {
            ensure(
                current.is_none() && saved.as_ref().is_some_and(|n| same_except_ctime(n, node)),
                "runtime archive has an unknown finite placement",
            )?;
        }
        let after = DirectoryState::capture(&root)?.state;
        before.after_replace(&after, name, &None)?;
        let archived = observe(&target)?.ok_or("runtime archive destination absent")?;
        let private_after = DirectoryState::capture(&payload)?.state;
        private_before.after_replace(&private_after, "evidence", &Some(archived.clone()))?;
        ensure(
            same_except_ctime(&archived, node),
            "runtime archival changed evidence bytes or unrelated metadata",
        )?;
        let receipt = write_json(
            &complete,
            &json!({"schema":"droidloom.original-once-runtime-archived.v1","configuration_source":ctx.source.pin(),"logical_path":path,"original":node,"archived":archived,"destination":target,"public_parent_before":before,"public_parent_after":after,"private_parent_before":private_before,"private_parent_after":private_after,"runtime_birth_not_original_label_preimage":true}),
        )?;
        advance_parent(&mut ctx.parents, &before, &after)?;
        reports.push(receipt);
    }
    Ok(
        json!({"schema":"droidloom.original-once-runtime-archive.v1","configuration_source":ctx.source.pin(),"members":reports}),
    )
}
fn publish_one(i: &Intent) -> Result<Value> {
    ensure(
        observe_kind(&i.target, i.purpose_target.is_some())? == i.original
            && observe_kind(&i.pending, i.purpose_target.is_some())? == i.prepared,
        "configuration preimage changed before publication",
    )?;
    ensure(
        i.parent.path == i.target.parent().ok_or("public parent")?
            && i.private_parent.path == i.pending.parent().ok_or("private parent")?,
        "configuration parent source paths differ",
    )?;
    let public = i.parent.reopen()?;
    let private_held = i.private_parent.reopen()?;
    let parent = &public.file;
    let private = &private_held.file;
    let name = i
        .target
        .file_name()
        .and_then(|v| v.to_str())
        .ok_or("target name")?
        .to_owned();
    let pending = i
        .pending
        .file_name()
        .and_then(|v| v.to_str())
        .ok_or("pending name")?
        .to_owned();
    match (&i.original, &i.prepared) {
        (Some(_), Some(_)) => rustix::fs::renameat_with(
            &private,
            pending.as_str(),
            &parent,
            name.as_str(),
            RenameFlags::EXCHANGE,
        )?,
        (None, Some(_)) => rustix::fs::renameat_with(
            &private,
            pending.as_str(),
            &parent,
            name.as_str(),
            RenameFlags::NOREPLACE,
        )?,
        (Some(_), None) => rustix::fs::renameat_with(
            &parent,
            name.as_str(),
            &private,
            pending.as_str(),
            RenameFlags::NOREPLACE,
        )?,
        (None, None) => {}
    }
    parent.sync_all()?;
    private.sync_all()?;
    let target = observe_kind(&i.target, i.purpose_target.is_some())?;
    let rollback = observe_kind(&i.pending, i.purpose_target.is_some())?;
    ensure(
        expected(&i.prepared, &target) && expected(&i.original, &rollback),
        "configuration publication did not retain exactly its original inode",
    )?;
    let public_after = DirectoryState::held(&i.parent.path, parent)?;
    let private_after = DirectoryState::held(&i.private_parent.path, private)?;
    i.parent.after_replace(&public_after, &name, &target)?;
    i.private_parent
        .after_replace(&private_after, &pending, &rollback)?;
    Ok(
        json!({"target":target,"original_retained":rollback,"public_parent_before":i.parent,"public_parent_after":public_after,"private_parent_before":i.private_parent,"private_parent_after":private_after}),
    )
}
#[cfg(test)]
fn restore_one(i: &Intent) -> Result<Value> {
    // The producer reconstructs an interrupted publication from its exact
    // immutable original intent before beginning a reverse transaction.
    let target = observe_kind(&i.target, i.purpose_target.is_some())?;
    let pending = observe_kind(&i.pending, i.purpose_target.is_some())?;
    let p = DirectoryState::capture(&i.parent.path)?.state;
    let q = DirectoryState::capture(&i.private_parent.path)?.state;
    i.parent.after_replace(
        &p,
        i.target
            .file_name()
            .and_then(|n| n.to_str())
            .ok_or("test public child")?,
        &target,
    )?;
    i.private_parent.after_replace(
        &q,
        i.pending
            .file_name()
            .and_then(|n| n.to_str())
            .ok_or("test private child")?,
        &pending,
    )?;
    restore_one_from(i, &p, &q)
}
fn restore_one_from(
    i: &Intent,
    public_expected: &DirectoryState,
    private_expected: &DirectoryState,
) -> Result<Value> {
    let target = observe_kind(&i.target, i.purpose_target.is_some())?;
    let rollback = observe_kind(&i.pending, i.purpose_target.is_some())?;
    let public = DirectoryState::capture(&i.parent.path)?;
    let private = DirectoryState::capture(&i.private_parent.path)?;
    let name = i
        .target
        .file_name()
        .and_then(|v| v.to_str())
        .ok_or("public name")?;
    let pending = i
        .pending
        .file_name()
        .and_then(|v| v.to_str())
        .ok_or("private name")?;
    let already = expected(&i.original, &target) && expected(&i.prepared, &rollback);
    ensure(
        already || expected(&i.prepared, &target) && expected(&i.original, &rollback),
        "configuration has an unknown generation or changed body",
    )?;
    if already {
        public_expected.after_replace(&public.state, name, &target)?;
        private_expected.after_replace(&private.state, pending, &rollback)?;
    } else {
        ensure(
            public.state == *public_expected && private.state == *private_expected,
            "configuration parent drift before the actual reverse rename",
        )?;
    }
    // Complete current parent snapshot is now the held preimage for only this
    // reverse operation. Both named generations are checked again after fsync.
    if !already {
        match (&i.original, &i.prepared) {
            (Some(_), Some(_)) => rustix::fs::renameat_with(
                &private.file,
                pending,
                &public.file,
                name,
                RenameFlags::EXCHANGE,
            )?,
            (None, Some(_)) => rustix::fs::renameat_with(
                &public.file,
                name,
                &private.file,
                pending,
                RenameFlags::NOREPLACE,
            )?,
            (Some(_), None) => rustix::fs::renameat_with(
                &private.file,
                pending,
                &public.file,
                name,
                RenameFlags::NOREPLACE,
            )?,
            (None, None) => {}
        }
    }
    public.file.sync_all()?;
    private.file.sync_all()?;
    let target = observe_kind(&i.target, i.purpose_target.is_some())?;
    let candidate = observe_kind(&i.pending, i.purpose_target.is_some())?;
    ensure(
        expected(&i.original, &target) && expected(&i.prepared, &candidate),
        "configuration original inode restoration failed",
    )?;
    let public_after = DirectoryState::held(&i.parent.path, &public.file)?;
    let private_after = DirectoryState::held(&i.private_parent.path, &private.file)?;
    public.state.after_replace(&public_after, name, &target)?;
    private
        .state
        .after_replace(&private_after, pending, &candidate)?;
    // `before` is the durable transaction checkpoint, including when this is
    // a readback after an interrupted successful rename. Only the exact one
    // member effect above can bridge it to the actual current directory.
    public_expected.after_replace(&public_after, name, &target)?;
    private_expected.after_replace(&private_after, pending, &candidate)?;
    Ok(
        json!({"original":target,"candidate_retained":candidate,"already_original":already,
        "public_parent_before":public_expected,"public_parent_after":public_after,
        "private_parent_before":private_expected,"private_parent_after":private_after}),
    )
}

fn validate_reverse_candidate(i: &Intent, actual: &Option<Node>) -> Result<()> {
    if i.purpose_target.is_some() {
        let before = i
            .prepared
            .as_ref()
            .ok_or("source-created directory preimage")?;
        let after = actual
            .as_ref()
            .ok_or("source-created directory reverse preimage")?;
        ensure(
            same_inode(before, after)
                && before.attributes == after.attributes
                && before.identity.mode == after.identity.mode
                && before.identity.uid == after.identity.uid
                && before.identity.gid == after.identity.gid
                && before.sha256 == after.sha256
                && before.link == after.link,
            "created directory reverse identity is not its actual source generation",
        )
    } else {
        ensure(
            expected(&i.prepared, actual),
            "reverse candidate source differs",
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn only_the_exact_once_configuration_paths_are_admitted() {
        let c = "a".repeat(64);
        assert!(allowed(Path::new("/etc/droidloom/cell.json"), &c));
        assert!(allowed(Path::new("/etc/droidloom/host-mac/policy.bin"), &c));
        assert!(allowed(
            &PathBuf::from(format!(
                "/etc/systemd/system/droidloom-original-qualification@{c}.service"
            )),
            &c
        ));
        for p in [
            "/etc/passwd",
            "/etc/shadow",
            "/home/alex/.ssh/authorized_keys",
            "/etc/systemd/system/ssh.service",
            "/etc/systemd/system/droidloomd.service",
            "/etc/droidloom/host-mac/../cell.json",
        ] {
            assert!(!allowed(Path::new(p), &c), "{p}");
        }
    }
    #[test]
    #[ignore = "requires root; only creates isolated configuration/generation test inodes"]
    fn actual_atomic_publication_restores_original_inode_and_rejects_replacement() -> Result<()> {
        ensure(rustix::process::geteuid().is_root(), "root test required")?;
        let stamp = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)?
            .as_nanos();
        let root = PathBuf::from(format!(
            "/var/lib/droidloom-qualification/once-config-core-test-{}-{stamp}",
            std::process::id()
        ));
        files::private_dir(&root)?;
        for case in ["regular", "symlink", "original-absent", "candidate-absent"] {
            let work = root.join(case);
            files::private_dir(&work)?;
            let public = work.join("public");
            let private = work.join("private");
            files::private_dir(&public)?;
            files::private_dir(&private)?;
            let target = public.join("target");
            let pending = private.join("pending");
            if case == "symlink" {
                rustix::fs::symlinkat("/dev/null", &File::open(&public)?, "target")?;
            } else if case != "original-absent" {
                files::write_new(&target, b"preserved original", 0o644)?;
            }
            if case != "candidate-absent" {
                files::write_new(&pending, b"source-owned candidate", 0o644)?;
            }
            let i = Intent {
                schema: "test".into(),
                candidate_id: "a".repeat(64),
                group: case.into(),
                ordinal: 0,
                logical_path: target.clone(),
                target: target.clone(),
                pending: pending.clone(),
                payload: Payload::Absent,
                original: observe(&target)?,
                prepared: observe(&pending)?,
                parent: DirectoryState::capture(&public)?.state,
                private_parent: DirectoryState::capture(&private)?.state,
                purpose_target: None,
            };
            let published = publish_one(&i)?; // completion bytes are not required to recover a real rename.
            let p: DirectoryState =
                serde_json::from_value(published["public_parent_after"].clone())?;
            let q: DirectoryState =
                serde_json::from_value(published["private_parent_after"].clone())?;
            restore_one_from(&i, &p, &q)?;
            // Actual reverse happened, but its completion was not persisted.
            restore_one_from(&i, &p, &q)?;
            assert!(expected(&i.original, &observe(&target)?));
            publish_one_replay(&i)?;
            if i.prepared.is_some() {
                std::fs::rename(&target, work.join("unrelated-preserved"))?;
                files::write_new(&target, b"source-owned candidate", 0o644)?;
                assert!(restore_one(&i).is_err());
            }
        }
        Ok(())
    }

    #[test]
    #[ignore = "root only; source-owned independent parent/generation test directories"]
    fn exact_parent_evolution_composes_and_rejects_foreign_members_and_parent_replacement()
    -> Result<()> {
        ensure(rustix::process::geteuid().is_root(), "root only")?;
        let stamp = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)?
            .as_nanos();
        let base = PathBuf::from(format!(
            "/var/lib/droidloom-qualification/once-config-parents-{}-{stamp}",
            std::process::id()
        ));
        files::private_dir(&base)?;
        let public = base.join("public");
        files::private_dir(&public)?;
        let mut records = Vec::new();
        let mut previous = None;
        for ordinal in 0..2 {
            let private = base.join(format!("private-{ordinal}"));
            files::private_dir(&private)?;
            let target = public.join(format!("target-{ordinal}"));
            let pending = private.join("value");
            files::write_new(&pending, b"actual prepared source", 0o644)?;
            let i = Intent {
                schema: "test".into(),
                candidate_id: "a".repeat(64),
                group: "test".into(),
                ordinal,
                logical_path: target.clone(),
                target,
                pending,
                payload: Payload::Absent,
                original: None,
                prepared: observe(&private.join("value"))?,
                parent: DirectoryState::capture(&public)?.state,
                private_parent: DirectoryState::capture(&private)?.state,
                purpose_target: None,
            };
            if let Some(old) = previous {
                ensure(
                    i.parent == old,
                    "first publication lost its exact next parent checkpoint",
                )?;
            }
            let published = publish_one(&i)?;
            previous = Some(serde_json::from_value(
                published["public_parent_after"].clone(),
            )?);
            records.push((i, published));
        }
        let mut checkpoint = previous.unwrap();
        for (i, published) in records.iter().rev() {
            let private: DirectoryState =
                serde_json::from_value(published["private_parent_after"].clone())?;
            let actual = restore_one_from(i, &checkpoint, &private)?;
            checkpoint = serde_json::from_value(actual["public_parent_after"].clone())?;
        }
        ensure(
            checkpoint.members.is_empty(),
            "reverse publication left a candidate file",
        )?;
        let old = base.join("parent-preserved");
        std::fs::rename(&public, &old)?;
        files::private_dir(&public)?;
        assert!(
            checkpoint.reopen().is_err(),
            "same pathname/owner is not the original parent generation"
        );
        let private = base.join("private-dir");
        files::private_dir(&private)?;
        let pending = private.join("value");
        std::fs::create_dir(&pending)?;
        use std::os::unix::fs::PermissionsExt;
        std::fs::set_permissions(&pending, std::fs::Permissions::from_mode(0o755))?;
        let target = public.join("created");
        let i = Intent {
            schema: "droidloom.original-once-directory-intent.v2".into(),
            candidate_id: "a".repeat(64),
            group: "test".into(),
            ordinal: 0,
            logical_path: target.clone(),
            target: target.clone(),
            pending: pending.clone(),
            payload: Payload::Absent,
            original: None,
            prepared: observe_kind(&pending, true)?,
            parent: DirectoryState::capture(&public)?.state,
            private_parent: DirectoryState::capture(&private)?.state,
            purpose_target: Some(target.join("configuration")),
        };
        let actual = publish_one(&i)?;
        let p: DirectoryState = serde_json::from_value(actual["public_parent_after"].clone())?;
        let q: DirectoryState = serde_json::from_value(actual["private_parent_after"].clone())?;
        files::write_new(&public.join("foreign"), b"unrelated", 0o644)?;
        assert!(
            restore_one_from(&i, &p, &q).is_err(),
            "unrelated directory member must block reverse rename"
        );
        // Preserve the failed fixture. A distinct exact context proves only
        // the source-owned create/rename crash case, never arbitrary adoption.
        let isolated = base.join("directory-crash");
        files::private_dir(&isolated)?;
        let pp = isolated.join("public");
        let qq = isolated.join("private");
        files::private_dir(&pp)?;
        files::private_dir(&qq)?;
        let pending = qq.join("value");
        std::fs::create_dir(&pending)?;
        std::fs::set_permissions(&pending, std::fs::Permissions::from_mode(0o755))?;
        let target = pp.join("new-directory");
        let j = Intent {
            schema: i.schema.clone(),
            candidate_id: i.candidate_id.clone(),
            group: i.group.clone(),
            ordinal: 0,
            logical_path: target.clone(),
            target: target.clone(),
            pending: pending.clone(),
            payload: Payload::Absent,
            original: None,
            prepared: observe_kind(&pending, true)?,
            parent: DirectoryState::capture(&pp)?.state,
            private_parent: DirectoryState::capture(&qq)?.state,
            purpose_target: Some(target.join("configuration")),
        };
        publish_one(&j)?;
        restore_one(&j)?;
        ensure(
            !target.exists() && expected(&j.prepared, &observe_kind(&pending, true)?),
            "created directory generation was not retained after crash recovery",
        )?;
        Ok(())
    }
    #[test]
    #[ignore = "root only; actual independent configuration parent drift counterexamples"]
    fn parent_only_drift_before_reverse_is_rejected() -> Result<()> {
        ensure(rustix::process::geteuid().is_root(), "root only")?;
        let stamp = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)?
            .as_nanos();
        let base = PathBuf::from(format!(
            "/var/lib/droidloom-qualification/once-config-parent-drift-{}-{stamp}",
            std::process::id()
        ));
        files::private_dir(&base)?;
        for case in [
            "public-touch",
            "private-touch",
            "public-create-delete",
            "private-create-delete",
        ] {
            let work = base.join(case);
            files::private_dir(&work)?;
            let public = work.join("public");
            let private = work.join("private");
            files::private_dir(&public)?;
            files::private_dir(&private)?;
            let target = public.join("target");
            let pending = private.join("value");
            files::write_new(&target, b"original", 0o644)?;
            files::write_new(&pending, b"candidate", 0o644)?;
            let i = Intent {
                schema: "test".into(),
                candidate_id: "a".repeat(64),
                group: "test".into(),
                ordinal: 0,
                logical_path: target.clone(),
                target: target.clone(),
                pending: pending.clone(),
                payload: Payload::Absent,
                original: observe(&target)?,
                prepared: observe(&pending)?,
                parent: DirectoryState::capture(&public)?.state,
                private_parent: DirectoryState::capture(&private)?.state,
                purpose_target: None,
            };
            let published = publish_one(&i)?;
            let p: DirectoryState =
                serde_json::from_value(published["public_parent_after"].clone())?;
            let q: DirectoryState =
                serde_json::from_value(published["private_parent_after"].clone())?;
            let drift = if case.starts_with("public") {
                &public
            } else {
                &private
            };
            if case.ends_with("touch") {
                let file = File::open(drift)?;
                file.set_times(
                    std::fs::FileTimes::new()
                        .set_modified(std::time::UNIX_EPOCH + std::time::Duration::from_secs(42)),
                )?;
                file.sync_all()?;
            } else {
                files::write_new(&drift.join("foreign"), b"external transient member", 0o644)?;
                std::fs::remove_file(drift.join("foreign"))?;
                File::open(drift)?.sync_all()?;
            }
            ensure(
                DirectoryState::capture(&public)?.state.members == p.members
                    && DirectoryState::capture(&private)?.state.members == q.members,
                "counterexample must keep all members unchanged",
            )?;
            assert!(
                restore_one_from(&i, &p, &q).is_err(),
                "{case} must not become an owned rename"
            );
            ensure(
                expected(&i.prepared, &observe(&target)?)
                    && expected(&i.original, &observe(&pending)?),
                "rejected parent-only drift wrote a configuration",
            )?;
        }
        Ok(())
    }
    #[test]
    #[ignore = "root only; exact source-created parent retirement and archived evidence replay"]
    fn completed_reverse_reopens_after_its_actual_parent_directory_was_retired() -> Result<()> {
        ensure(rustix::process::geteuid().is_root(), "root only")?;
        let stamp = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)?
            .as_nanos();
        let base = PathBuf::from(format!(
            "/var/lib/droidloom-qualification/once-retired-parent-{}-{stamp}",
            std::process::id()
        ));
        files::private_dir(&base)?;
        for case in ["valid", "missing-proof", "foreign-public", "foreign-saved"] {
            let work = base.join(case);
            files::private_dir(&work)?;
            let public = work.join("public");
            let private = work.join("private");
            files::private_dir(&public)?;
            files::private_dir(&private)?;
            let pending = private.join("value");
            files::private_dir(&pending)?;
            let target = public.join("runtime-evidence");
            let i = Intent {
                schema: "test".into(),
                candidate_id: "a".repeat(64),
                group: "test".into(),
                ordinal: 0,
                logical_path: target.clone(),
                target: target.clone(),
                pending: pending.clone(),
                payload: Payload::Absent,
                original: None,
                prepared: observe_kind(&pending, true)?,
                parent: DirectoryState::capture(&public)?.state,
                private_parent: DirectoryState::capture(&private)?.state,
                purpose_target: Some(target.join("owner.lock")),
            };
            let published = publish_one(&i)?;
            let before: DirectoryState =
                serde_json::from_value(published["public_parent_after"].clone())?;
            let private_before: DirectoryState =
                serde_json::from_value(published["private_parent_after"].clone())?;
            let reversed = restore_one_from(&i, &before, &private_before)?;
            let saved: Node = serde_json::from_value(reversed["candidate_retained"].clone())?;
            let parents = [
                (
                    public.clone(),
                    serde_json::from_value(reversed["public_parent_after"].clone())?,
                ),
                (
                    private.clone(),
                    serde_json::from_value(reversed["private_parent_after"].clone())?,
                ),
            ]
            .into_iter()
            .collect();
            let mut retired: BTreeMap<PathBuf, (PathBuf, Node)> =
                [(target.clone(), (pending.clone(), saved))]
                    .into_iter()
                    .collect();
            let original = target.join("runtime-RESULT.json");
            assert!(
                observe(&original).is_err(),
                "the real parent must be absent"
            );
            if case == "missing-proof" {
                retired.clear();
            }
            if case == "foreign-public" {
                files::private_dir(&target)?;
            }
            if case == "foreign-saved" {
                files::write_new(&pending.join("foreign"), b"not owned", 0o400)?;
            }
            let actual = restored_target_observation(&original, false, true, &parents, &retired);
            if case == "valid" {
                ensure(
                    actual?.is_none(),
                    "owned retired ancestor did not prove exact original absence",
                )?;
                assert!(
                    restored_target_observation(&original, false, false, &parents, &retired)
                        .is_err()
                );
            } else {
                assert!(
                    actual.is_err(),
                    "{case} must not prove a source-owned absent parent"
                );
            }
        }
        Ok(())
    }
    fn publish_one_replay(i: &Intent) -> Result<Value> {
        // Renames legitimately changed ctime. Reconstruct the exact current
        // immutable source observations for this second independent test.
        let i = Intent {
            schema: i.schema.clone(),
            candidate_id: i.candidate_id.clone(),
            group: i.group.clone(),
            ordinal: i.ordinal,
            logical_path: i.logical_path.clone(),
            target: i.target.clone(),
            pending: i.pending.clone(),
            payload: i.payload.clone(),
            original: observe_kind(&i.target, i.purpose_target.is_some())?,
            prepared: observe_kind(&i.pending, i.purpose_target.is_some())?,
            parent: DirectoryState::capture(i.target.parent().ok_or("test public parent")?)?.state,
            private_parent: DirectoryState::capture(
                i.pending.parent().ok_or("test private parent")?,
            )?
            .state,
            purpose_target: i.purpose_target.clone(),
        };
        publish_one(&i)
    }
}
