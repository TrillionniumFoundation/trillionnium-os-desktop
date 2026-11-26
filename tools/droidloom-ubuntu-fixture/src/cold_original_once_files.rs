//! Durable, finite per-machine configuration publication. Original inodes are
//! retained by atomic exchange; a restored value is never synthesized from a
//! convenient matching pathname. Only the once dispatcher supplies entries.
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
    parent: Identity,
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
            && id.nlink == 1
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
        _ => return Err("configuration is neither regular nor a symbolic link".into()),
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
                "droidloom-original-once.target",
                "droidloom-original-once-return.service",
                "droidloom-original-once-return.timer",
                "user@1000.service.d/60-droidloom-original-once.conf",
            ]
            .contains(&unit);
    }
    false
}

fn parent_directories(path: &Path, work: &Path) -> Result<()> {
    let mut missing = Vec::new();
    let mut here = path.parent().ok_or("target parent missing")?;
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
    for dir in missing.iter().rev() {
        let (parent, name) = at(dir)?;
        let before = fs::stat(&parent)?;
        ensure(
            before.uid == 0 && before.gid == 0 && before.mode & 0o022 == 0,
            "configuration ancestor custody",
        )?;
        // Preimage publication precedes each create-only directory operation.
        let ordinal = std::fs::read_dir(work)?.count();
        let note = work.join(format!("DIRECTORY-{ordinal:04}-INTENT.json"));
        write_json(
            &note,
            &json!({"schema":"droidloom.original-once-directory-intent.v1","path":dir,"parent":before,"mode":0o755}),
        )?;
        rustix::fs::mkdirat(&parent, name.as_str(), Mode::from_raw_mode(0o755))?;
        parent.sync_all()?;
        let opened = File::from(rustix::fs::openat(
            &parent,
            name.as_str(),
            OFlags::RDONLY | OFlags::DIRECTORY | OFlags::NOFOLLOW | OFlags::CLOEXEC,
            Mode::empty(),
        )?);
        let (generation, _) = Ext4Handle::capture(opened.as_fd())?;
        write_json(
            &work.join(format!("DIRECTORY-{ordinal:04}-CREATED.json")),
            &json!({"intent":files::pin_file(&note)?,"identity":fs::stat(&opened)?,"handle_type":generation.handle_type(),"handle":hex::encode(generation.bytes())}),
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
            ["package-masks", "runtime", "recovery", "grub"].contains(&group),
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
            ["package-masks", "runtime", "recovery", "grub"].contains(&group),
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
        let mut reports = Vec::new();
        for (ordinal, e) in entries.into_iter().enumerate() {
            a.verify_current_owner()?;
            ensure(
                allowed(&e.path, &self.candidate) && seen.insert(e.path.clone()),
                "configuration target not in fixed original-once scope",
            )?;
            parent_directories(&e.path, &self.work)?;
            let item = self.work.join(format!("item-{ordinal:03}"));
            files::private_dir(&item)?;
            let pending = item.join("pending");
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
                    rustix::fs::symlinkat(target.as_str(), &File::open(&item)?, "pending")?;
                }
                Payload::Absent => {}
            }
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
                target: e.path,
                pending,
                payload: e.payload,
                original,
                prepared,
                parent: fs::stat(&parent)?,
            };
            let pin = write_json(&item.join("INTENT.json"), &intent)?;
            let actual = publish_one(&intent)?;
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
    pub(super) fn restore(&self, a: &OriginalQualificationAuthority) -> Result<Value> {
        a.verify_current_owner()?;
        let mut paths = Vec::new();
        for e in std::fs::read_dir(&self.work)? {
            let e = e?;
            let n = e
                .file_name()
                .into_string()
                .map_err(|_| "nonutf8 configuration entry")?;
            if n.starts_with("item-") {
                ensure(
                    n.len() == 8 && n[5..].bytes().all(|b| b.is_ascii_digit()),
                    "configuration ordinal",
                )?;
                paths.push(e.path());
            }
        }
        paths.sort();
        ensure(paths.len() <= 64, "configuration restore bound")?;
        let mut reports = Vec::new();
        for item in paths.into_iter().rev() {
            a.verify_current_owner()?;
            let ip = item.join("INTENT.json");
            if !ip.exists() {
                continue;
            } // only a private pending file could exist; no publication intent.
            let pin = files::pin_file(&ip)?;
            let seal = SealedInput::open(&pin)?;
            let i: Intent = serde_json::from_slice(&seal.read()?)?;
            ensure(
                i.schema == "droidloom.original-once-configuration-intent.v1"
                    && i.candidate_id == self.candidate
                    && i.group == self.group
                    && i.pending == item.join("pending")
                    && i.target == i.logical_path
                    && allowed(&i.target, &self.candidate),
                "configuration restore source identity",
            )?;
            let actual = restore_one(&i)?;
            seal.revalidate()?;
            let out = item.join("RESTORED.json");
            if !out.exists() {
                write_json(&out, &json!({"intent":pin,"actual":actual}))?;
            }
            reports.push(files::pin_file(&out)?);
            a.verify_current_owner()?;
        }
        Ok(
            json!({"schema":"droidloom.original-once-configurations-restored.v1","candidate_id":self.candidate,"group":self.group,"items":reports}),
        )
    }
}

fn expected(node: &Option<Node>, actual: &Option<Node>) -> bool {
    match (node, actual) {
        (None, None) => true,
        (Some(a), Some(b)) => same_inode(a, b) && same_except_ctime(a, b),
        _ => false,
    }
}
fn publish_one(i: &Intent) -> Result<Value> {
    ensure(
        observe(&i.target)? == i.original && observe(&i.pending)? == i.prepared,
        "configuration preimage changed before publication",
    )?;
    let (parent, name) = at(&i.target)?;
    let (private, pending) = at(&i.pending)?;
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
    let target = observe(&i.target)?;
    let rollback = observe(&i.pending)?;
    ensure(
        expected(&i.prepared, &target) && expected(&i.original, &rollback),
        "configuration publication did not retain exactly its original inode",
    )?;
    Ok(json!({"target":target,"original_retained":rollback}))
}
fn restore_one(i: &Intent) -> Result<Value> {
    let target = observe(&i.target)?;
    let rollback = observe(&i.pending)?;
    if expected(&i.original, &target) && expected(&i.prepared, &rollback) {
        return Ok(
            json!({"original":target,"candidate_retained":rollback,"already_original":true}),
        );
    }
    ensure(
        expected(&i.prepared, &target) && expected(&i.original, &rollback),
        "configuration has an unknown generation or changed contents; preserve it",
    )?;
    let (parent, name) = at(&i.target)?;
    let (private, pending) = at(&i.pending)?;
    match (&i.original, &i.prepared) {
        (Some(_), Some(_)) => rustix::fs::renameat_with(
            &private,
            pending.as_str(),
            &parent,
            name.as_str(),
            RenameFlags::EXCHANGE,
        )?,
        (None, Some(_)) => rustix::fs::renameat_with(
            &parent,
            name.as_str(),
            &private,
            pending.as_str(),
            RenameFlags::NOREPLACE,
        )?,
        (Some(_), None) => rustix::fs::renameat_with(
            &private,
            pending.as_str(),
            &parent,
            name.as_str(),
            RenameFlags::NOREPLACE,
        )?,
        (None, None) => {}
    }
    parent.sync_all()?;
    private.sync_all()?;
    let target = observe(&i.target)?;
    let candidate = observe(&i.pending)?;
    ensure(
        expected(&i.original, &target) && expected(&i.prepared, &candidate),
        "configuration original inode restoration failed",
    )?;
    Ok(json!({"original":target,"candidate_retained":candidate,"already_original":false}))
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
            let target = work.join("target");
            let pending = work.join("pending");
            if case == "symlink" {
                rustix::fs::symlinkat("/dev/null", &File::open(&work)?, "target")?;
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
                parent: fs::stat(&File::open(&work)?)?,
            };
            publish_one(&i)?; // crash point: no completion record is needed to classify the namespace.
            restore_one(&i)?;
            restore_one(&i)?;
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
            original: observe(&i.target)?,
            prepared: observe(&i.pending)?,
            parent: i.parent.clone(),
        };
        publish_one(&i)
    }
}
