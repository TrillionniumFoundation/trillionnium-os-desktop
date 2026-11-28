//! Held-inode transaction core used only by the fixed working runtime publisher.
//! Durable records describe effects; only these live descriptors and finite
//! transitions authorize an operation in this process.
use super::super::{
    DirectoryState, Intent, MemberIdentity, Node, Payload, SealedInput, advance_parent, at, attrs,
    observe_kind, publish_one, restore_one_from, same_except_ctime, same_inode, write_json,
};
use crate::{
    Result,
    boot_files::{self as files, FilePin},
    cold_original_data::labels::{WorkingLabelBatch, WorkingLabelDerivation},
    ensure, fs,
};
use droidloom_descriptor_custody::Ext4Handle;
use rustix::fs::{FileType, Mode, OFlags, XattrFlags};
use serde_json::{Value, json};
use std::{
    collections::BTreeMap,
    fs::File,
    io::Seek,
    os::fd::AsFd,
    path::{Path, PathBuf},
};

#[path = "cold_working_file_reopen.rs"]
mod returned;

struct HeldNode {
    file: File,
    node: Node,
}
impl HeldNode {
    fn open(path: &Path, directory: bool) -> Result<Option<Self>> {
        let Some(node) = observe_kind(path, directory)? else {
            return Ok(None);
        };
        let (parent, name) = at(path)?;
        let kind = FileType::from_raw_mode(node.identity.mode);
        let access = if kind == FileType::Symlink {
            OFlags::PATH
        } else {
            OFlags::RDONLY
        };
        let file = File::from(rustix::fs::openat(
            &parent,
            name.as_str(),
            access | OFlags::NOFOLLOW | OFlags::NONBLOCK | OFlags::CLOEXEC,
            Mode::empty(),
        )?);
        let held = Self { file, node };
        held.guard(path, directory)?;
        Ok(Some(held))
    }
    fn read(&self) -> Result<Node> {
        let identity = fs::stat(&self.file)?;
        let (handle, _) = Ext4Handle::capture(self.file.as_fd())?;
        ensure(
            handle.inode_number() as u64 == identity.ino,
            "held working inode generation differs",
        )?;
        let attributes = attrs(&self.file)?;
        let (sha256, link) = match FileType::from_raw_mode(identity.mode) {
            FileType::RegularFile => {
                ensure(
                    identity.size <= 512 * 1024 * 1024,
                    "bounded held working content",
                )?;
                let mut f = &self.file;
                f.rewind()?;
                (Some(fs::hash(&self.file)?), None)
            }
            FileType::Symlink => {
                let value = rustix::fs::readlinkat(&self.file, "", Vec::new())?;
                let value = std::str::from_utf8(value.to_bytes())?.to_owned();
                ensure(
                    value.len() <= 4096 && !value.contains('\0'),
                    "bounded held link",
                )?;
                (None, Some(value))
            }
            FileType::Directory => (None, None),
            _ => return Err("working custody acquired a special inode".into()),
        };
        ensure(
            fs::stat(&self.file)? == identity,
            "held working inode changed during full readback",
        )?;
        Ok(Node {
            identity,
            handle_type: handle.handle_type(),
            handle: hex::encode(handle.bytes()),
            attributes,
            sha256,
            link,
        })
    }
    fn guard(&self, path: &Path, directory: bool) -> Result<()> {
        ensure(
            self.read()? == self.node && observe_kind(path, directory)? == Some(self.node.clone()),
            "held or named working inode changed",
        )
    }
    fn guard_custody(&self, path: &Path, directory: bool) -> Result<()> {
        let verify = |file: &File| -> Result<()> {
            let identity = fs::stat(file)?;
            let (handle, _) = Ext4Handle::capture(file.as_fd())?;
            ensure(
                identity == self.node.identity
                    && handle.handle_type() == self.node.handle_type
                    && hex::encode(handle.bytes()) == self.node.handle
                    && attrs(file)? == self.node.attributes,
                "working bounded-window held inode custody changed",
            )?;
            if FileType::from_raw_mode(identity.mode) == FileType::Symlink {
                let target = rustix::fs::readlinkat(file, "", Vec::new())?;
                ensure(
                    self.node.link.as_deref() == Some(std::str::from_utf8(target.to_bytes())?),
                    "working bounded-window link target changed",
                )?;
            }
            ensure(
                fs::stat(file)? == identity,
                "working inode changed during custody readback",
            )
        };
        verify(&self.file)?;
        let (parent, name) = at(path)?;
        let kind = FileType::from_raw_mode(self.node.identity.mode);
        ensure(
            directory == (kind == FileType::Directory),
            "working window inode role changed",
        )?;
        let flags = if kind == FileType::Symlink {
            OFlags::PATH
        } else {
            OFlags::RDONLY
        };
        let named = File::from(rustix::fs::openat(
            &parent,
            name.as_str(),
            flags | OFlags::NOFOLLOW | OFlags::NONBLOCK | OFlags::CLOEXEC,
            Mode::empty(),
        )?);
        verify(&named)?;
        verify(&self.file)
    }
    fn renamed(&self, path: &Path, directory: bool) -> Result<Node> {
        let actual = self.read()?;
        ensure(
            same_except_ctime(&self.node, &actual)
                && observe_kind(path, directory)? == Some(actual.clone()),
            "working rename changed more than this held inode's ctime",
        )?;
        Ok(actual)
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Phase {
    Staged,
    Ready,
    Publishing,
    Published,
    Restoring,
    Restored,
}

struct Reverse {
    public: DirectoryState,
    private: DirectoryState,
}
struct Step {
    target: PathBuf,
    pending: PathBuf,
    record: PathBuf,
    payload: Payload,
    directory: bool,
    prepared: HeldNode,
    original: Option<HeldNode>,
    intent: Option<Intent>,
    reverse: Option<Reverse>,
    reverse_attempts: usize,
    phase: Phase,
}
impl Step {
    fn before_roles(&self, retired: &BTreeMap<PathBuf, PathBuf>) -> Result<()> {
        self.prepared.guard(&self.pending, self.directory)?;
        match &self.original {
            Some(node) => node.guard(&self.target, self.directory),
            None => absent(&self.target, self.directory, retired),
        }
    }
    fn after_roles(&self) -> Result<()> {
        self.prepared.guard(&self.target, self.directory)?;
        match &self.original {
            Some(node) => node.guard(&self.pending, self.directory),
            None => ensure(
                observe_kind(&self.pending, self.directory)?.is_none(),
                "working private path gained a foreign inode",
            ),
        }
    }
    fn guard_label_custody(&self) -> Result<()> {
        ensure(
            self.phase == Phase::Published,
            "working label window needs complete publication",
        )?;
        self.prepared.guard_custody(&self.target, self.directory)?;
        match &self.original {
            Some(node) => node.guard_custody(&self.pending, self.directory),
            None => ensure(
                observe_kind(&self.pending, self.directory)?.is_none(),
                "working private target gained a foreign inode",
            ),
        }
    }
    fn guard(&self, retired: &BTreeMap<PathBuf, PathBuf>) -> Result<()> {
        match self.phase {
            Phase::Staged => self.prepared.guard(&self.pending, self.directory),
            Phase::Ready | Phase::Restored => self.before_roles(retired),
            Phase::Published => self.after_roles(),
            Phase::Publishing | Phase::Restoring => {
                Err("working operation outcome needs exact read-only reconciliation".into())
            }
        }
    }
}
fn absent(path: &Path, directory: bool, retired: &BTreeMap<PathBuf, PathBuf>) -> Result<()> {
    if let Some(parent) = path.parent().filter(|p| retired.contains_key(*p)) {
        ensure(
            observe_kind(parent, true)?.is_none(),
            "retired source-created parent was recreated",
        )?;
        return Ok(());
    }
    ensure(
        observe_kind(path, directory)?.is_none(),
        "absent working target gained a foreign inode",
    )
}

#[derive(Default)]
struct Parents {
    files: BTreeMap<PathBuf, File>,
    states: BTreeMap<PathBuf, DirectoryState>,
}
impl Parents {
    fn hold(&mut self, path: &Path) -> Result<()> {
        if let Some(file) = self.files.get(path) {
            return ensure(
                DirectoryState::held(path, file)? == self.states[path],
                "working parent differs from its actual previous checkpoint",
            );
        }
        let held = DirectoryState::capture(path)?;
        self.states.insert(path.into(), held.state);
        self.files.insert(path.into(), held.file);
        Ok(())
    }
    fn guard(&self) -> Result<()> {
        ensure(
            self.files.len() == self.states.len(),
            "working parent descriptor roster differs",
        )?;
        for (path, file) in &self.files {
            ensure(
                DirectoryState::held(path, file)? == self.states[path],
                "working parent generation, attributes or complete members drifted",
            )?;
        }
        Ok(())
    }
    fn actual(&self, path: &Path) -> Result<DirectoryState> {
        DirectoryState::held(
            path,
            self.files
                .get(path)
                .ok_or("working parent descriptor absent")?,
        )
    }
}

fn label_record<'a>(
    batch: &'a WorkingLabelBatch,
    path: &Path,
) -> Result<&'a WorkingLabelDerivation> {
    batch
        .records()
        .iter()
        .find(|record| record.paths().iter().any(|known| known == path))
        .ok_or_else(|| "working parent change lacks this actual normal label transition".into())
}

/// Compare complete parent inventories before accepting any new checkpoint.
/// Every difference must be one actual source-owned normal label write.
fn require_labelled_parent(
    before: &DirectoryState,
    after: &DirectoryState,
    batch: &WorkingLabelBatch,
) -> Result<()> {
    ensure(
        before.path == after.path && before.members.keys().eq(after.members.keys()),
        "working label batch changed a parent path or complete member-name roster",
    )?;
    if before.identity != after.identity
        || before.handle_type != after.handle_type
        || before.handle != after.handle
        || before.attributes != after.attributes
    {
        label_record(batch, &before.path)?.require_transition(
            &before.path,
            (
                &before.identity,
                before.handle_type,
                &before.handle,
                &before.attributes,
            ),
            (
                &after.identity,
                after.handle_type,
                &after.handle,
                &after.attributes,
            ),
        )?;
    }
    for (name, old) in &before.members {
        let new = &after.members[name];
        if old != new {
            let path = before.path.join(name);
            label_record(batch, &path)?.require_member_transition(
                &path,
                (&old.identity, old.handle_type, &old.handle),
                (&new.identity, new.handle_type, &new.handle),
            )?;
        }
    }
    Ok(())
}

/// A private live owner, not a deserializable reconstruction from a log.
pub(super) struct Transaction {
    work: PathBuf,
    candidate: String,
    steps: Vec<Step>,
    parents: Parents,
    seals: Vec<SealedInput>,
    retired: BTreeMap<PathBuf, PathBuf>,
}
impl Transaction {
    pub(super) fn new(work: PathBuf, candidate: String) -> Self {
        Self {
            work,
            candidate,
            steps: Vec::new(),
            parents: Parents::default(),
            seals: Vec::new(),
            retired: BTreeMap::new(),
        }
    }
    pub(super) fn initialize(&self) -> Result<()> {
        files::private_dir(&self.work)?;
        File::open(
            self.work
                .parent()
                .ok_or("working publication work parent")?,
        )?
        .sync_all()?;
        Ok(())
    }
    fn staging(&self) -> Result<(PathBuf, PathBuf)> {
        ensure(
            // Three optional normal parents, three owned evidence directories,
            // and the exact sixteen published runtime files.
            self.steps.len() < 22,
            "working publication staging exceeds its finite roster",
        )?;
        let record = self.work.join(format!("item-{:03}", self.steps.len()));
        files::private_dir(&record)?;
        let payload = record.join("payload");
        files::private_dir(&payload)?;
        File::open(&record)?.sync_all()?;
        File::open(&self.work)?.sync_all()?;
        Ok((record, payload.join("value")))
    }
    pub(super) fn stage_file(&mut self, target: &Path, source: &FilePin, mode: u32) -> Result<()> {
        let (record, pending) = self.staging()?;
        files::copy_pin(source, &pending, mode)?;
        File::open(pending.parent().ok_or("working private parent")?)?.sync_all()?;
        let prepared = HeldNode::open(&pending, false)?.ok_or("new working payload absent")?;
        ensure(
            prepared.node.identity.mode & 0o7777 == mode
                && prepared.node.identity.size == source.bytes
                && prepared.node.sha256.as_ref() == Some(&source.sha256),
            "staged working payload differs from its complete normal source",
        )?;
        self.steps.push(Step {
            target: target.into(),
            pending,
            record,
            payload: Payload::Regular {
                source: source.clone(),
                mode,
            },
            directory: false,
            prepared,
            original: None,
            intent: None,
            reverse: None,
            reverse_attempts: 0,
            phase: Phase::Staged,
        });
        Ok(())
    }
    pub(super) fn stage_symlink(&mut self, target: &Path, link: &str) -> Result<()> {
        ensure(
            !link.is_empty() && link.len() <= 4096 && !link.contains('\0'),
            "bounded literal working link",
        )?;
        let (record, pending) = self.staging()?;
        let (parent, name) = at(&pending)?;
        rustix::fs::symlinkat(link, &parent, name.as_str())?;
        parent.sync_all()?;
        let prepared = HeldNode::open(&pending, false)?.ok_or("new working link absent")?;
        ensure(
            prepared.node.link.as_deref() == Some(link)
                && prepared.node.identity.mode == 0o120777
                && prepared.node.identity.uid == 0
                && prepared.node.identity.gid == 0
                && prepared.node.identity.nlink == 1,
            "new working link custody differs",
        )?;
        self.steps.push(Step {
            target: target.into(),
            pending,
            record,
            payload: Payload::Symlink {
                target: link.into(),
            },
            directory: false,
            prepared,
            original: None,
            intent: None,
            reverse: None,
            reverse_attempts: 0,
            phase: Phase::Staged,
        });
        Ok(())
    }
    pub(super) fn stage_directory(&mut self, target: &Path) -> Result<()> {
        self.stage_directory_mode(target, 0o755)
    }
    pub(super) fn stage_private_directory(&mut self, target: &Path) -> Result<()> {
        self.stage_directory_mode(target, 0o700)
    }
    fn stage_directory_mode(&mut self, target: &Path, mode: u32) -> Result<()> {
        ensure(
            matches!(mode, 0o700 | 0o755),
            "closed working directory modes",
        )?;
        let (record, pending) = self.staging()?;
        let (parent, name) = at(&pending)?;
        rustix::fs::mkdirat(&parent, name.as_str(), Mode::from_raw_mode(mode))?;
        let file = File::open(&pending)?;
        rustix::fs::fchmod(&file, Mode::from_raw_mode(mode))?;
        file.sync_all()?;
        parent.sync_all()?;
        let prepared = HeldNode::open(&pending, true)?.ok_or("new working directory absent")?;
        ensure(
            prepared.node.identity.mode & 0o7777 == mode,
            "source-created working directory mode differs",
        )?;
        self.steps.push(Step {
            target: target.into(),
            pending,
            record,
            payload: Payload::Absent,
            directory: true,
            prepared,
            original: None,
            intent: None,
            reverse: None,
            reverse_attempts: 0,
            phase: Phase::Staged,
        });
        Ok(())
    }
    pub(super) fn lookup_entries(&self) -> Vec<(&Path, &File, bool)> {
        self.steps
            .iter()
            .map(|s| (s.target.as_path(), &s.prepared.file, s.directory))
            .collect()
    }
    pub(super) fn apply_labels(&mut self, contexts: &[Vec<u8>]) -> Result<()> {
        ensure(
            contexts.len() == self.steps.len()
                && self.steps.iter().all(|s| s.phase == Phase::Staged),
            "normal contexts do not cover all private working inodes",
        )?;
        for (step, context) in self.steps.iter_mut().zip(contexts) {
            ensure(
                !context.is_empty()
                    && context.len() <= 4096
                    && context.last() == Some(&0)
                    && !context[..context.len() - 1].contains(&0),
                "one bounded normal SELinux context required",
            )?;
            step.prepared.guard(&step.pending, step.directory)?;
            let before = step.prepared.node.clone();
            rustix::fs::fsetxattr(
                &step.prepared.file,
                "security.selinux",
                context,
                XattrFlags::empty(),
            )?;
            step.prepared.file.sync_all()?;
            let after = step.prepared.read()?;
            let mut expected = before.clone();
            expected
                .attributes
                .insert("security.selinux".into(), hex::encode(context));
            ensure(
                same_except_ctime(&expected, &after)
                    && observe_kind(&step.pending, step.directory)? == Some(after.clone()),
                "normal staged label changed an unrelated inode field",
            )?;
            step.prepared.node = after;
        }
        self.guard()
    }
    pub(super) fn retain_seal(&mut self, pin: &FilePin) -> Result<()> {
        self.seals.push(SealedInput::open(pin)?);
        Ok(())
    }
    fn seal(&mut self, path: &Path, value: &impl serde::Serialize) -> Result<FilePin> {
        let pin = write_json(path, value)?;
        self.retain_seal(&pin)?;
        Ok(pin)
    }
    pub(super) fn guard(&self) -> Result<()> {
        for seal in &self.seals {
            seal.revalidate()?;
        }
        self.parents.guard()?;
        for step in &self.steps {
            step.guard(&self.retired)?;
        }
        self.parents.guard()
    }

    /// Held metadata only within the separately guarded finite label window.
    /// Complete file bodies are verified by guard at both window boundaries.
    pub(super) fn guard_label_custody(&self) -> Result<()> {
        ensure(
            self.all_published(),
            "working label window requires complete publication",
        )?;
        for seal in &self.seals {
            seal.revalidate_custody()?;
        }
        self.parents.guard()?;
        for step in &self.steps {
            step.guard_label_custody()?;
        }
        self.parents.guard()
    }

    /// Advance all held parent checkpoints together after this batch's actual
    /// normal label writes. Prepared and original payloads keep strict custody.
    /// No source-wide guard runs while other batch consumers remain pending.
    pub(super) fn accept_working_label_batch(&mut self, batch: &WorkingLabelBatch) -> Result<()> {
        ensure(
            self.all_published() && batch.candidate_id() == self.candidate,
            "working label acceptance needs this completely published candidate",
        )?;
        batch.revalidate()?;
        for seal in &self.seals {
            seal.revalidate_custody()?;
        }
        for step in &self.steps {
            step.guard_label_custody()?;
        }
        ensure(
            self.parents.files.keys().eq(self.parents.states.keys()),
            "working label acceptance lost a parent descriptor",
        )?;
        let mut after = BTreeMap::new();
        for (path, file) in &self.parents.files {
            let actual = DirectoryState::held(path, file)?;
            let before = &self.parents.states[path];
            if path.starts_with(&self.work) {
                ensure(
                    &actual == before,
                    "working private payload parent changed during the full-root label batch",
                )?;
            } else {
                require_labelled_parent(before, &actual, batch)?;
            }
            after.insert(path.clone(), actual);
        }
        batch.revalidate()?;
        for (path, file) in &self.parents.files {
            ensure(
                DirectoryState::held(path, file)? == after[path],
                "working labelled parent changed before the complete batch checkpoint",
            )?;
        }
        for step in &self.steps {
            step.guard_label_custody()?;
        }
        let old = std::mem::replace(&mut self.parents.states, after);
        if let Err(error) = self.guard_label_custody().and_then(|_| batch.revalidate()) {
            // Keep the previous exact state and every live FD. The caller still
            // owns the actual batch and may reconcile this unresolved boundary.
            self.parents.states = old;
            return Err(error);
        }
        Ok(())
    }

    pub(super) fn accept_grub(
        &mut self,
        proof: &crate::cold_original_data::labels::WorkingGrubProof,
    ) -> Result<()> {
        ensure(
            self.all_published() && proof.candidate_id() == self.candidate,
            "working GRUB parent adoption requires this actual published owner",
        )?;
        let values = proof.member_records()?;
        let member = |value: &Value| -> Result<MemberIdentity> {
            Ok(MemberIdentity {
                identity: serde_json::from_value(value["identity"].clone())?,
                handle_type: serde_json::from_value(value["handle"]["handle_type"].clone())?,
                handle: hex::encode(serde_json::from_value::<Vec<u8>>(
                    value["handle"]["bytes"].clone(),
                )?),
            })
        };
        let old = member(&values["before"])?;
        let new = member(&values["after"])?;
        let mut updates = BTreeMap::new();
        for (path, file) in &self.parents.files {
            let actual = DirectoryState::held(path, file)?;
            let before = &self.parents.states[path];
            let mut expected = before.clone();
            if path == Path::new("/boot/grub") {
                ensure(
                    matches!(before.members.get("grubenv"),Some(v) if v==&old || v==&new),
                    "working GRUB parent did not retain the exact source inode",
                )?;
                expected.members.insert("grubenv".into(), new.clone());
            }
            ensure(
                actual == expected,
                "working GRUB changed another complete publication parent/member",
            )?;
            updates.insert(path.clone(), actual);
        }
        proof.guard()?;
        for (path, state) in updates {
            self.parents.states.insert(path, state);
        }
        self.guard_label_custody()
    }
    pub(super) fn accept_selection(
        &mut self,
        proof: &crate::cold_original_data::WorkingSelectionProof,
    ) -> Result<()> {
        ensure(
            self.all_published() && proof.candidate_id() == self.candidate,
            "working selected adoption needs this fully published runtime",
        )?;
        proof.guard()?;
        let records = proof.parent_records()?;
        let projected = |value: &Value| -> Result<DirectoryState> {
            let node = |value: &Value| -> Result<MemberIdentity> {
                Ok(MemberIdentity {
                    identity: serde_json::from_value(value["identity"].clone())?,
                    handle_type: serde_json::from_value(value["handle"]["handle_type"].clone())?,
                    handle: hex::encode(serde_json::from_value::<Vec<u8>>(
                        value["handle"]["bytes"].clone(),
                    )?),
                })
            };
            let main = node(&value["snapshot"])?;
            let raw: BTreeMap<String, Vec<u8>> =
                serde_json::from_value(value["snapshot"]["attributes"].clone())?;
            let members = value["members"]
                .as_object()
                .ok_or("actual selected parent members absent")?
                .iter()
                .map(|(name, value)| node(value).map(|member| (name.clone(), member)))
                .collect::<Result<BTreeMap<_, _>>>()?;
            Ok(DirectoryState {
                path: PathBuf::from("/etc/droidloom/production"),
                identity: main.identity,
                handle_type: main.handle_type,
                handle: main.handle,
                attributes: raw
                    .into_iter()
                    .map(|(name, bytes)| (name, hex::encode(bytes)))
                    .collect(),
                members,
            })
        };
        let previous = projected(&records["before"])?;
        let next = projected(&records["after"])?;
        let mut parents = BTreeMap::new();
        for seal in &self.seals {
            seal.revalidate_custody()?;
        }
        for (path, file) in &self.parents.files {
            let actual = DirectoryState::held(path, file)?;
            let before = &self.parents.states[path];
            if path == &previous.path {
                ensure(
                    (before == &previous || before == &next) && actual == next,
                    "runtime selected parent did not follow its exact actual rename",
                )?;
            } else if Some(path.as_path()) == previous.path.parent() {
                let old_member = MemberIdentity {
                    identity: previous.identity.clone(),
                    handle_type: previous.handle_type,
                    handle: previous.handle.clone(),
                };
                let new_member = MemberIdentity {
                    identity: next.identity.clone(),
                    handle_type: next.handle_type,
                    handle: next.handle.clone(),
                };
                let mut expected = before.clone();
                ensure(
                    matches!(before.members.get("production"),Some(member) if member==&old_member || member==&new_member),
                    "runtime selected ancestor lost its actual child directory generation",
                )?;
                expected.members.insert("production".into(), new_member);
                ensure(
                    actual == expected,
                    "runtime selected rename changed another ancestor member",
                )?;
            } else {
                ensure(
                    &actual == before,
                    "working selected rename changed an unrelated publication parent",
                )?;
            }
            parents.insert(path.clone(), actual);
        }
        let mut nodes = Vec::new();
        for (index, step) in self.steps.iter().enumerate() {
            if step.target == previous.path && step.directory {
                ensure(
                    step.original.is_none(),
                    "source-created selected parent acquired an original role",
                )?;
                let before = &step.prepared.node;
                let matches = |state: &DirectoryState| {
                    before.identity == state.identity
                        && before.handle_type == state.handle_type
                        && before.handle == state.handle
                        && before.attributes == state.attributes
                };
                ensure(
                    matches(&previous) || matches(&next),
                    "selected parent left the actual prepared directory checkpoint",
                )?;
                let mut after = before.clone();
                after.identity = next.identity.clone();
                ensure(
                    step.prepared.read()? == after
                        && observe_kind(&step.target, true)? == Some(after.clone()),
                    "selected parent current inode differs from the exact derived rename",
                )?;
                absent(&step.pending, true, &self.retired)?;
                nodes.push((index, after));
            } else {
                step.guard_label_custody()?;
            }
        }
        proof.guard()?;
        for (path, file) in &self.parents.files {
            ensure(
                DirectoryState::held(path, file)? == parents[path],
                "selected parent changed before all checkpoints advanced",
            )?;
        }
        let old_parents = std::mem::replace(&mut self.parents.states, parents);
        let old_nodes = nodes
            .into_iter()
            .map(|(index, after)| {
                let old = std::mem::replace(&mut self.steps[index].prepared.node, after);
                (index, old)
            })
            .collect::<Vec<_>>();
        if let Err(error) = self.guard_label_custody().and_then(|_| proof.guard()) {
            self.parents.states = old_parents;
            for (index, before) in old_nodes {
                self.steps[index].prepared.node = before;
            }
            return Err(error);
        }
        Ok(())
    }

    pub(super) fn len(&self) -> usize {
        self.steps.len()
    }
    pub(super) fn target(&self, index: usize) -> &Path {
        &self.steps[index].target
    }
    pub(super) fn all_published(&self) -> bool {
        !self.steps.is_empty() && self.steps.iter().all(|s| s.phase == Phase::Published)
    }
    /// True only before any public rename syscall has been attempted. Even a
    /// completed reverse keeps a Restored phase, so it cannot masquerade as an
    /// admission failure with no effects.
    pub(super) fn never_published(&self) -> bool {
        self.steps
            .iter()
            .all(|s| matches!(s.phase, Phase::Staged | Phase::Ready))
    }
    pub(super) fn all_restored(&self) -> bool {
        self.steps
            .iter()
            .all(|s| matches!(s.phase, Phase::Staged | Phase::Ready | Phase::Restored))
    }
    fn prepare_intent(&mut self, index: usize) -> Result<()> {
        self.guard()?;
        let step = &self.steps[index];
        ensure(step.phase == Phase::Staged, "working intent is create-only")?;
        let parent = step
            .target
            .parent()
            .ok_or("working target parent")?
            .to_owned();
        let private = step
            .pending
            .parent()
            .ok_or("working private parent")?
            .to_owned();
        self.parents.hold(&parent)?;
        self.parents.hold(&private)?;
        let original = HeldNode::open(&step.target, step.directory)?;
        ensure(
            !step.directory || original.is_none(),
            "working directory creation raced with another inode",
        )?;
        let step = &mut self.steps[index];
        let intent = Intent {
            schema: "droidloom.working-runtime-file-intent.v1".into(),
            candidate_id: self.candidate.clone(),
            group: "working-runtime".into(),
            ordinal: index,
            logical_path: step.target.clone(),
            target: step.target.clone(),
            pending: step.pending.clone(),
            payload: step.payload.clone(),
            original: original.as_ref().map(|n| n.node.clone()),
            prepared: Some(step.prepared.node.clone()),
            parent: self.parents.states[&parent].clone(),
            private_parent: self.parents.states[&private].clone(),
            purpose_target: step.directory.then(|| step.target.clone()),
        };
        let path = step.record.join("INTENT.json");
        let value = serde_json::to_value(&intent)?;
        step.original = original;
        step.intent = Some(intent);
        step.phase = Phase::Ready;
        self.seal(&path, &value)?;
        self.guard()
    }
    pub(super) fn require_original(
        &self,
        index: usize,
        identity: &crate::model::Identity,
        source: &FilePin,
    ) -> Result<()> {
        let step = &self.steps[index];
        let actual = HeldNode::open(&step.target, false)?.ok_or("actual original cell absent")?;
        ensure(
            actual.node.identity == *identity
                && actual.node.identity.size == source.bytes
                && actual.node.sha256.as_ref() == Some(&source.sha256)
                && step.target == source.path,
            "working publisher lost its exact actual original cell preimage",
        )?;
        actual.guard(&step.target, false)
    }
    pub(super) fn publish(&mut self, index: usize) -> Result<()> {
        self.prepare_intent(index)?;
        self.publish_prepared(index)
    }
    /// Bind a caller's previously held full preimage to this exact intent.
    /// A changed inode or a formerly absent target is rejected before rename.
    pub(super) fn publish_captured(&mut self, index: usize, expected: Option<&Node>) -> Result<()> {
        self.prepare_intent(index)?;
        ensure(
            self.steps[index].original.as_ref().map(|held| &held.node) == expected,
            "working publication original differs from the retained full preimage",
        )?;
        self.publish_prepared(index)
    }
    fn publish_prepared(&mut self, index: usize) -> Result<()> {
        self.guard()?;
        self.steps[index].phase = Phase::Publishing;
        // An error may be after rename or fsync. Leave the actual descriptors
        // and intent in Publishing; never infer that an error means no effect.
        publish_one(
            self.steps[index]
                .intent
                .as_ref()
                .ok_or("working intent absent")?,
        )?;
        self.reconcile(index)?;
        ensure(
            self.steps[index].phase == Phase::Published,
            "working publication had no observed effect",
        )?;
        let path = self.steps[index].record.join("PUBLISHED.json");
        self.seal(&path, &self.step_report(index)?)?;
        self.guard()
    }
    fn advanced(
        &self,
        transitions: &[(&DirectoryState, &DirectoryState)],
    ) -> Result<(BTreeMap<PathBuf, DirectoryState>, Vec<(usize, Node)>)> {
        let mut states = self.parents.states.clone();
        let mut changed = Vec::new();
        for (before, after) in transitions {
            advance_parent(&mut states, before, after)?;
            for (index, step) in self.steps.iter().enumerate() {
                if step.directory && step.phase == Phase::Published && step.target == before.path {
                    let node = &step.prepared.node;
                    ensure(
                        node.identity == before.identity
                            && node.handle_type == before.handle_type
                            && node.handle == before.handle
                            && node.attributes == before.attributes,
                        "working created directory lost its exact child-operation checkpoint",
                    )?;
                    let mut node = node.clone();
                    node.identity = after.identity.clone();
                    ensure(
                        step.prepared.read()? == node,
                        "working created directory differs after its exact owned child operation",
                    )?;
                    changed.push((index, node));
                }
            }
        }
        Ok((states, changed))
    }
    fn reconcile(&mut self, index: usize) -> Result<()> {
        let step = &self.steps[index];
        let reverse = step.phase == Phase::Restoring;
        ensure(
            reverse || step.phase == Phase::Publishing,
            "only one unknown actual operation may reconcile",
        )?;
        let intent = step
            .intent
            .as_ref()
            .ok_or("working reconciliation has no intent")?;
        let (public_before, private_before) = if reverse {
            let r = step
                .reverse
                .as_ref()
                .ok_or("working reverse has no held checkpoint")?;
            (&r.public, &r.private)
        } else {
            (&intent.parent, &intent.private_parent)
        };
        let public_after = self.parents.actual(&public_before.path)?;
        let private_after = self.parents.actual(&private_before.path)?;
        let before_roles = if reverse {
            step.after_roles()
        } else {
            step.before_roles(&self.retired)
        };
        if before_roles.is_ok()
            && public_after == *public_before
            && private_after == *private_before
        {
            self.steps[index].phase = if reverse {
                Phase::Published
            } else {
                Phase::Ready
            };
            return self.guard();
        }
        let prepared_path = if reverse { &step.pending } else { &step.target };
        let original_path = if reverse { &step.target } else { &step.pending };
        let prepared = step.prepared.renamed(prepared_path, step.directory)?;
        let original = match &step.original {
            Some(node) => Some(node.renamed(original_path, step.directory)?),
            None => {
                ensure(
                    observe_kind(original_path, step.directory)?.is_none(),
                    "working rename acquired an unowned original",
                )?;
                None
            }
        };
        let target = if reverse {
            original.clone()
        } else {
            Some(prepared.clone())
        };
        let pending = if reverse {
            Some(prepared.clone())
        } else {
            original.clone()
        };
        let target_name = step
            .target
            .file_name()
            .and_then(|s| s.to_str())
            .ok_or("working target name")?;
        let pending_name = step
            .pending
            .file_name()
            .and_then(|s| s.to_str())
            .ok_or("working pending name")?;
        public_before.after_replace(&public_after, target_name, &target)?;
        private_before.after_replace(&private_after, pending_name, &pending)?;
        let (states, changed) = self.advanced(&[
            (public_before, &public_after),
            (private_before, &private_after),
        ])?;
        self.parents.states = states;
        for (number, node) in changed {
            self.steps[number].prepared.node = node;
        }
        let step = &mut self.steps[index];
        step.prepared.node = prepared;
        if let (Some(held), Some(actual)) = (&mut step.original, original) {
            held.node = actual;
        }
        step.phase = if reverse {
            Phase::Restored
        } else {
            Phase::Published
        };
        if reverse && step.directory {
            ensure(
                self.parents
                    .states
                    .get(&step.target)
                    .is_none_or(|p| p.members.is_empty()),
                "retired working directory still has members",
            )?;
            self.parents.states.remove(&step.target);
            self.parents.files.remove(&step.target);
            self.retired
                .insert(step.target.clone(), step.pending.clone());
        }
        self.guard()
    }
    /// Read-only: this never repeats a possibly completed filesystem mutation.
    pub(super) fn reconcile_pending(&mut self) -> Result<()> {
        let pending: Vec<_> = self
            .steps
            .iter()
            .enumerate()
            .filter_map(|(n, s)| {
                matches!(s.phase, Phase::Publishing | Phase::Restoring).then_some(n)
            })
            .collect();
        ensure(
            pending.len() <= 1,
            "working transaction has more than one unresolved effect",
        )?;
        for index in pending {
            self.reconcile(index)?;
        }
        self.guard()
    }
    pub(super) fn restore(&mut self, index: usize) -> Result<()> {
        self.guard()?;
        if matches!(
            self.steps[index].phase,
            Phase::Staged | Phase::Ready | Phase::Restored
        ) {
            return Ok(());
        }
        let step = &self.steps[index];
        ensure(
            step.phase == Phase::Published && step.reverse_attempts < 4,
            "working reverse lacks a known published effect or exceeded its bound",
        )?;
        if step.directory {
            if let Some(state) = self.parents.states.get(&step.target) {
                ensure(
                    state.members.is_empty(),
                    "working directory contains an unfinished or foreign child",
                )?;
            }
        }
        let old = step
            .intent
            .as_ref()
            .ok_or("working reverse lacks original intent")?;
        let public = self.parents.states[&old.parent.path].clone();
        let private = self.parents.states[&old.private_parent.path].clone();
        let operation = Intent {
            schema: old.schema.clone(),
            candidate_id: old.candidate_id.clone(),
            group: old.group.clone(),
            ordinal: old.ordinal,
            logical_path: old.logical_path.clone(),
            target: old.target.clone(),
            pending: old.pending.clone(),
            payload: old.payload.clone(),
            original: step.original.as_ref().map(|n| n.node.clone()),
            prepared: Some(step.prepared.node.clone()),
            parent: public.clone(),
            private_parent: private.clone(),
            purpose_target: old.purpose_target.clone(),
        };
        let path = step
            .record
            .join(format!("RESTORE-INTENT-{:02}.json", step.reverse_attempts));
        let value = json!({"schema":"droidloom.working-runtime-reverse-intent.v1",
            "candidate_id":self.candidate,"ordinal":index,"operation":operation});
        self.seal(&path, &value)?;
        let step = &mut self.steps[index];
        step.reverse = Some(Reverse {
            public: public.clone(),
            private: private.clone(),
        });
        step.reverse_attempts += 1;
        step.phase = Phase::Restoring;
        restore_one_from(&operation, &public, &private)?;
        self.reconcile(index)?;
        ensure(
            self.steps[index].phase == Phase::Restored,
            "working reverse had no observed effect",
        )?;
        let path = self.steps[index].record.join("RESTORED.json");
        self.seal(&path, &self.step_report(index)?)?;
        self.guard()
    }
    fn step_report(&self, index: usize) -> Result<Value> {
        let step = &self.steps[index];
        ensure(
            matches!(step.phase, Phase::Published | Phase::Restored),
            "only an observed working effect is reportable",
        )?;
        Ok(
            json!({"schema":"droidloom.working-runtime-file-observed.v1",
            "candidate_id":self.candidate,"ordinal":index,"target":step.target,"pending":step.pending,
            "phase":format!("{:?}",step.phase),"original":step.original.as_ref().map(|n| &n.node),
            "candidate":step.prepared.node,"directory":step.directory,"parents":self.parents.states}),
        )
    }
    pub(super) fn seal_summary(&mut self, restored: bool) -> Result<FilePin> {
        self.guard()?;
        ensure(
            if restored {
                self.all_restored()
            } else {
                self.all_published()
            },
            "working publication summary cannot skip an actual operation",
        )?;
        let path = self.work.join(if restored {
            "RESTORED.json"
        } else {
            "PUBLISHED.json"
        });
        let steps = self
            .steps
            .iter()
            .map(|s| {
                json!({"target":s.target,"pending":s.pending,
            "phase":format!("{:?}",s.phase),"directory":s.directory,
            "original":s.original.as_ref().map(|n| &n.node),"candidate":s.prepared.node})
            })
            .collect::<Vec<_>>();
        self.seal(
            &path,
            &json!({"schema":"droidloom.working-runtime-observed.v1",
            "candidate_id":self.candidate,"restored":restored,"steps":steps,
            "parents":self.parents.states,"retired_created_directories":self.retired,
            "application_business_accepted":false,"production_ready":false}),
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::MetadataExt;

    struct Fixture {
        root: PathBuf,
    }
    impl Fixture {
        fn new(name: &str) -> Result<Self> {
            ensure(
                rustix::process::geteuid().is_root(),
                "actual root inode test required",
            )?;
            let stamp = std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)?
                .as_nanos();
            let root = PathBuf::from(format!(
                "/var/lib/droidloom-qualification/working-config-{name}-{}-{stamp}",
                std::process::id()
            ));
            files::private_dir(&root)?;
            files::private_dir(&root.join("public"))?;
            files::write_new(
                &root.join("source"),
                b"actual source-owned candidate",
                0o400,
            )?;
            Ok(Self { root })
        }
        fn transaction(&self) -> Result<Transaction> {
            let value = Transaction::new(self.root.join("transaction"), "a".repeat(64));
            value.initialize()?;
            Ok(value)
        }
        fn source(&self) -> Result<FilePin> {
            files::pin_file(&self.root.join("source"))
        }
    }
    impl Drop for Fixture {
        fn drop(&mut self) {
            // Only this test's newly created root is removed.
            let _ = std::fs::remove_dir_all(&self.root);
        }
    }

    #[test]
    #[ignore = "root/ext4 only; actual bounded-window inode and descriptor-offset controls"]
    fn actual_working_label_custody_preserves_offset_and_rejects_unowned_inode_changes()
    -> Result<()> {
        use std::io::{Seek, SeekFrom};
        for mutation in ["bytes", "replacement", "attributes"] {
            let fixture = Fixture::new(mutation)?;
            let target = fixture.root.join("public/target");
            files::write_new(&target, b"actual bounded-window original", 0o644)?;
            let held = HeldNode::open(&target, false)?.ok_or("test held target absent")?;
            let mut reader = &held.file;
            reader.seek(SeekFrom::Start(7))?;
            held.guard_custody(&target, false)?;
            assert_eq!(reader.stream_position()?, 7);
            match mutation {
                "bytes" => std::fs::write(&target, b"changed bounded-window source")?,
                "replacement" => {
                    std::fs::rename(&target, fixture.root.join("retained"))?;
                    files::write_new(&target, b"actual bounded-window original", 0o644)?;
                }
                "attributes" => rustix::fs::fsetxattr(
                    &held.file,
                    "user.working-window-unowned",
                    b"foreign",
                    XattrFlags::empty(),
                )?,
                _ => unreachable!(),
            }
            assert!(held.guard_custody(&target, false).is_err());
            assert_eq!(reader.stream_position()?, 7);
        }
        Ok(())
    }

    #[test]
    #[ignore = "root/ext4 only; exact retained preimage and absent-target drift"]
    fn actual_working_captured_preimage_rejects_foreign_changes_before_rename() -> Result<()> {
        for case in ["absent-became-present", "same-bytes-new-inode", "unchanged"] {
            let fixture = Fixture::new(case)?;
            let target = fixture.root.join("public/target");
            if case != "absent-became-present" {
                files::write_new(&target, b"retained original", 0o644)?;
            }
            let expected = observe_kind(&target, false)?;
            let mut transaction = fixture.transaction()?;
            transaction.stage_file(&target, &fixture.source()?, 0o644)?;
            if case == "absent-became-present" {
                files::write_new(&target, b"unowned new file", 0o644)?;
            } else if case == "same-bytes-new-inode" {
                std::fs::rename(&target, fixture.root.join("retained-original"))?;
                files::write_new(&target, b"retained original", 0o644)?;
            }
            let before = observe_kind(&target, false)?;
            let result = transaction.publish_captured(0, expected.as_ref());
            if case == "unchanged" {
                result?;
                assert!(!transaction.never_published());
                transaction.restore(0)?;
                assert!(!transaction.never_published());
                let restored = observe_kind(&target, false)?.unwrap();
                assert!(same_inode(expected.as_ref().unwrap(), &restored));
                assert_eq!(restored.sha256, expected.as_ref().unwrap().sha256);
            } else {
                assert!(result.is_err());
                assert!(transaction.never_published());
                assert_eq!(observe_kind(&target, false)?, before);
                transaction.restore(0)?;
                assert_eq!(observe_kind(&target, false)?, before);
            }
            transaction.guard()?;
            assert!(transaction.all_restored());
        }
        Ok(())
    }

    #[test]
    #[ignore = "root/ext4 only; isolated held-inode exchange and exact reverse"]
    fn actual_working_publication_retains_original_fds_and_restores_both_presence_states()
    -> Result<()> {
        let fixture = Fixture::new("roundtrip")?;
        let target = fixture.root.join("public/existing");
        let absent_target = fixture.root.join("public/absent");
        files::write_new(&target, b"original content retained", 0o644)?;
        let before = observe_kind(&target, false)?.unwrap();
        let mut transaction = fixture.transaction()?;
        transaction.stage_file(&target, &fixture.source()?, 0o644)?;
        transaction.stage_file(&absent_target, &fixture.source()?, 0o400)?;
        transaction.publish(0)?;
        transaction.publish(1)?;
        transaction.guard()?;
        assert!(transaction.all_published());
        assert!(same_inode(
            &before,
            &transaction.steps[0].original.as_ref().unwrap().read()?
        ));
        assert_eq!(
            transaction.steps[0].original.as_ref().unwrap().node.sha256,
            before.sha256
        );
        let candidate0 = transaction.steps[0].prepared.node.clone();
        let candidate1 = transaction.steps[1].prepared.node.clone();
        transaction.restore(1)?;
        transaction.restore(0)?;
        transaction.guard()?;
        assert!(transaction.all_restored());
        assert!(same_inode(&before, &observe_kind(&target, false)?.unwrap()));
        assert!(observe_kind(&absent_target, false)?.is_none());
        for (index, candidate) in [candidate0, candidate1].iter().enumerate() {
            assert!(same_inode(
                candidate,
                &transaction.steps[index].prepared.read()?
            ));
            transaction.steps[index]
                .prepared
                .guard(&transaction.steps[index].pending, false)?;
        }
        transaction.seal_summary(true)?;
        Ok(())
    }

    #[test]
    #[ignore = "root/ext4 only; isolated created directory and exact child history"]
    fn actual_working_parent_chain_composes_children_and_retires_only_empty_created_directory()
    -> Result<()> {
        let fixture = Fixture::new("parents")?;
        let directory = fixture.root.join("public/created");
        let mut transaction = fixture.transaction()?;
        transaction.stage_private_directory(&directory)?;
        assert_eq!(
            transaction.steps[0].prepared.node.identity.mode & 0o7777,
            0o700
        );
        transaction.stage_file(&directory.join("first"), &fixture.source()?, 0o644)?;
        transaction.stage_file(&directory.join("second"), &fixture.source()?, 0o400)?;
        for index in 0..3 {
            transaction.publish(index)?;
        }
        transaction.guard()?;
        let directory_inode = transaction.steps[0].prepared.node.clone();
        assert_eq!(transaction.parents.states[&directory].members.len(), 2);
        for index in (0..3).rev() {
            transaction.restore(index)?;
        }
        transaction.guard()?;
        assert!(transaction.all_restored());
        assert!(!directory.exists());
        assert!(same_inode(
            &directory_inode,
            &transaction.steps[0].prepared.read()?
        ));
        assert!(
            DirectoryState::capture(&transaction.steps[0].pending)?
                .state
                .members
                .is_empty()
        );
        transaction.seal_summary(true)?;
        Ok(())
    }

    #[test]
    #[ignore = "root/ext4 only; isolated lost-completion and foreign-inode controls"]
    fn actual_working_unknown_outcome_reconciles_only_held_effect_and_rejects_equal_bytes_replacement()
    -> Result<()> {
        let fixture = Fixture::new("unknown")?;
        let target = fixture.root.join("public/target");
        files::write_new(&target, b"retained original", 0o644)?;
        let mut transaction = fixture.transaction()?;
        transaction.stage_file(&target, &fixture.source()?, 0o644)?;
        transaction.prepare_intent(0)?;
        transaction.steps[0].phase = Phase::Publishing;
        // The real atomic exchange completes; deliberately discard completion.
        publish_one(transaction.steps[0].intent.as_ref().unwrap())?;
        assert!(transaction.guard().is_err());
        transaction.reconcile_pending()?;
        assert!(transaction.all_published());
        transaction.guard()?;
        let retained_candidate = fixture.root.join("same-candidate-preserved");
        std::fs::rename(&target, &retained_candidate)?;
        files::copy_pin(&fixture.source()?, &target, 0o644)?;
        let foreign_inode = std::fs::metadata(&target)?.ino();
        assert_ne!(
            foreign_inode,
            transaction.steps[0].prepared.node.identity.ino
        );
        assert!(transaction.guard().is_err());
        assert!(transaction.restore(0).is_err());
        assert_eq!(std::fs::metadata(&target)?.ino(), foreign_inode);
        assert!(same_inode(
            &transaction.steps[0].prepared.node,
            &observe_kind(&retained_candidate, false)?.unwrap()
        ));
        Ok(())
    }

    #[test]
    #[ignore = "root/ext4 only; isolated unrelated-parent-member negative control"]
    fn actual_working_parent_drift_blocks_reverse_before_any_rename() -> Result<()> {
        let fixture = Fixture::new("drift")?;
        let target = fixture.root.join("public/target");
        files::write_new(&target, b"retained original", 0o644)?;
        let mut transaction = fixture.transaction()?;
        transaction.stage_file(&target, &fixture.source()?, 0o644)?;
        transaction.publish(0)?;
        let candidate = observe_kind(&target, false)?;
        let retained = observe_kind(&transaction.steps[0].pending, false)?;
        files::write_new(&fixture.root.join("public/foreign"), b"unrelated", 0o644)?;
        assert!(transaction.restore(0).is_err());
        assert_eq!(observe_kind(&target, false)?, candidate);
        assert_eq!(
            observe_kind(&transaction.steps[0].pending, false)?,
            retained
        );
        Ok(())
    }
}
