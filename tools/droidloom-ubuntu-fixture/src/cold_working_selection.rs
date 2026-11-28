//! Atomic working selected.json publication from the same labelled pair.
//! The immutable pair intent stays unchanged. Exact live descriptor checkpoints
//! follow only these two source-owned renames and their durable readback.
use super::*;
use crate::{boot_files as files, cold_original_qualification::WorkingLabelSourceIdentity};
use std::rc::Rc;

#[derive(Clone, Debug, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct SelectionDirectory {
    pub(crate) snapshot: labels::Snapshot,
    pub(crate) members: BTreeMap<String, labels::Snapshot>,
}
fn directory(held: &File) -> Result<SelectionDirectory> {
    let before = labels::snapshot(held)?;
    ensure(
        FileType::from_raw_mode(labels::snapshot_identity(&before).mode) == FileType::Directory,
        "working selection parent must remain an actual directory",
    )?;
    let mut members = BTreeMap::new();
    for name in names(held)? {
        let child = File::from(rustix::fs::openat(
            held,
            name.as_str(),
            OFlags::PATH | OFlags::NOFOLLOW | OFlags::CLOEXEC,
            Mode::empty(),
        )?);
        ensure(
            members.len() < 4096 && members.insert(name, labels::snapshot(&child)?).is_none(),
            "bounded unique working selection parent inventory required",
        )?;
    }
    ensure(
        labels::snapshot(held)? == before,
        "working selection parent changed across its inventory",
    )?;
    Ok(SelectionDirectory {
        snapshot: before,
        members,
    })
}
fn same_renamed(before: &labels::Snapshot, after: &labels::Snapshot) -> Result<()> {
    labels::verify_data_snapshot(before, after, false)?;
    ensure(
        labels::only_ctime_changed(
            labels::snapshot_identity(before),
            labels::snapshot_identity(after),
        ),
        "working selected rename changed an unrelated inode field",
    )
}
fn parent_delta(
    before: &SelectionDirectory,
    after: &SelectionDirectory,
    name: &str,
    original: Option<&labels::Snapshot>,
    replacement: Option<&labels::Snapshot>,
) -> Result<()> {
    ensure(
        before.members.get(name) == original,
        "selected parent preimage does not name its actual held file",
    )?;
    let mut same = labels::snapshot_identity(&after.snapshot).clone();
    same.size = labels::snapshot_identity(&before.snapshot).size;
    same.mtime_sec = labels::snapshot_identity(&before.snapshot).mtime_sec;
    same.mtime_nsec = labels::snapshot_identity(&before.snapshot).mtime_nsec;
    same.ctime_sec = labels::snapshot_identity(&before.snapshot).ctime_sec;
    same.ctime_nsec = labels::snapshot_identity(&before.snapshot).ctime_nsec;
    ensure(
        same == *labels::snapshot_identity(&before.snapshot),
        "working selection changed parent authority, generation, links or attributes",
    )?;
    labels::verify_data_snapshot(&before.snapshot, &after.snapshot, false)?;
    let mut members = before.members.clone();
    match replacement {
        Some(file) => {
            members.insert(name.into(), file.clone());
        }
        None => {
            members.remove(name);
        }
    }
    ensure(
        members == after.members,
        "working selection changed another exact parent member",
    )
}
#[derive(Clone, Copy, Debug, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "snake_case")]
pub(crate) enum SelectionOperation {
    Publish,
    Withdraw,
}
#[derive(Clone, Debug, serde::Serialize, serde::Deserialize)]
#[serde(deny_unknown_fields)]
struct Observation {
    parent: SelectionDirectory,
    work: SelectionDirectory,
    candidate: labels::Snapshot,
    original: Option<labels::Snapshot>,
}
struct Handles {
    public: File,
    work: File,
    candidate: File,
    original: Option<File>,
    work_path: PathBuf,
    public_path: PathBuf,
    candidate_sha256: String,
    original_sha256: Option<String>,
}
impl Handles {
    fn observation(&self, selected: bool) -> Result<Observation> {
        let candidate = labels::snapshot(&self.candidate)?;
        ensure(
            fs::digest(&read_small(&self.candidate, 16384)?) == self.candidate_sha256
                && labels::snapshot(&self.candidate)? == candidate,
            "working candidate selection changed its actual complete source bytes",
        )?;
        let original = match (&self.original, &self.original_sha256) {
            (Some(file), Some(sha)) => {
                let snapshot = labels::snapshot(file)?;
                ensure(
                    fs::digest(&read_small(file, 16384)?) == *sha
                        && labels::snapshot(file)? == snapshot,
                    "original selection changed through its retained read-only descriptor",
                )?;
                Some(snapshot)
            }
            (None, None) => None,
            _ => return Err("working selected original descriptor roster differs".into()),
        };
        let parent = directory(&self.public)?;
        let work = directory(&self.work)?;
        let (public, private) = if selected {
            (Some(&candidate), original.as_ref())
        } else {
            (original.as_ref(), Some(&candidate))
        };
        ensure(
            parent.members.get("selected.json") == public && work.members.get(PENDING) == private,
            "working selected paths no longer name the two exact retained descriptions",
        )?;
        let named = fs::Tree::open("/", 0)?;
        ensure(
            labels::snapshot(&named.dir(&fs::absolute_string(&self.public_path)?)?)?
                == parent.snapshot
                && labels::snapshot(&named.dir(&fs::absolute_string(&self.work_path)?)?)?
                    == work.snapshot,
            "working selected parent pathname was replaced",
        )?;
        Ok(Observation {
            parent,
            work,
            candidate,
            original,
        })
    }
}
#[derive(Clone, Debug, serde::Serialize, serde::Deserialize)]
#[serde(deny_unknown_fields)]
struct Intent {
    schema: String,
    candidate_id: String,
    pair_intent: FilePin,
    label_plan: FilePin,
    applied_labels: FilePin,
    operation: SelectionOperation,
    before: Observation,
}
#[derive(Clone, Debug, serde::Serialize, serde::Deserialize)]
#[serde(deny_unknown_fields)]
struct Completion {
    schema: String,
    intent: FilePin,
    after: Observation,
}

fn equal_pin(a: &FilePin, b: &FilePin) -> bool {
    a.path == b.path && a.bytes == b.bytes && a.sha256 == b.sha256
}
fn verify_transition(intent: &Intent, after: &Observation) -> Result<()> {
    same_renamed(&intent.before.candidate, &after.candidate)?;
    match (&intent.before.original, &after.original) {
        (Some(before), Some(after)) => same_renamed(before, after)?,
        (None, None) => (),
        _ => return Err("working selection lost or invented the original inode".into()),
    }
    let (public_before, public_after, private_before, private_after) = match intent.operation {
        SelectionOperation::Publish => (
            intent.before.original.as_ref(),
            Some(&after.candidate),
            Some(&intent.before.candidate),
            after.original.as_ref(),
        ),
        SelectionOperation::Withdraw => (
            Some(&intent.before.candidate),
            after.original.as_ref(),
            intent.before.original.as_ref(),
            Some(&after.candidate),
        ),
    };
    parent_delta(
        &intent.before.parent,
        &after.parent,
        "selected.json",
        public_before,
        public_after,
    )?;
    parent_delta(
        &intent.before.work,
        &after.work,
        PENDING,
        private_before,
        private_after,
    )
}
fn save(path: &Path, value: &impl serde::Serialize) -> Result<FilePin> {
    let bytes = serde_json::to_vec(value)?;
    ensure(
        !bytes.is_empty() && bytes.len() <= 16 * 1024 * 1024,
        "bounded working selection record required",
    )?;
    let parent = fs::Tree::open("/", 0)?.dir(&fs::absolute_string(
        path.parent().ok_or("selection record parent")?,
    )?)?;
    let name = path
        .file_name()
        .and_then(|n| n.to_str())
        .ok_or("selection record name")?;
    if named(&parent, name)?.is_some() {
        let held = open_at(&parent, name, false)?;
        let identity = fs::stat(&held)?;
        ensure(
            identity.uid == 0
                && identity.gid == 0
                && identity.mode == 0o100400
                && identity.nlink == 1
                && fs::xattrs(&held)?.is_empty()
                && read_small(&held, 16 * 1024 * 1024)? == bytes,
            "working selection record changed or has an unresolved partial publication",
        )?;
        return Ok(FilePin {
            path: path.into(),
            bytes: bytes.len() as u64,
            sha256: fs::digest(&bytes),
        });
    }
    let pending = format!("{name}.pending");
    if let Some(identity) = named(&parent, &pending)? {
        let held = open_at(&parent, &pending, false)?;
        ensure(
            fs::stat(&held)? == identity
                && identity.uid == 0
                && identity.gid == 0
                && identity.mode == 0o100400
                && identity.nlink == 1
                && fs::xattrs(&held)?.is_empty(),
            "unrecognized working selection pending record",
        )?;
        let mut preserved = false;
        for serial in 0..64 {
            let history = format!("{pending}.interrupted-{serial}");
            if named(&parent, &history)?.is_none() {
                rustix::fs::renameat_with(
                    &parent,
                    pending.as_str(),
                    &parent,
                    history.as_str(),
                    RenameFlags::NOREPLACE,
                )?;
                ensure(
                    labels::only_ctime_changed(&identity, &fs::stat(&held)?),
                    "interrupted selection record moved to another inode",
                )?;
                parent.sync_all()?;
                preserved = true;
                break;
            }
        }
        ensure(
            preserved,
            "working selection exhausted its bounded interrupted record history",
        )?;
    }
    let mut held = File::from(rustix::fs::openat(
        &parent,
        pending.as_str(),
        OFlags::RDWR | OFlags::CREATE | OFlags::EXCL | OFlags::NOFOLLOW | OFlags::CLOEXEC,
        Mode::from_raw_mode(0o400),
    )?);
    held.write_all(&bytes)?;
    rustix::fs::fchmod(&held, Mode::from_raw_mode(0o400))?;
    held.sync_all()?;
    let before = fs::stat(&held)?;
    parent.sync_all()?;
    rustix::fs::renameat_with(
        &parent,
        pending.as_str(),
        &parent,
        name,
        RenameFlags::NOREPLACE,
    )?;
    parent.sync_all()?;
    let after = fs::stat(&held)?;
    ensure(
        labels::only_ctime_changed(&before, &after)
            && named(&parent, name)? == Some(after.clone())
            && read_small(&held, 16 * 1024 * 1024)? == bytes
            && fs::stat(&held)? == after,
        "working selected record publication changed its actual held body",
    )?;
    Ok(FilePin {
        path: path.into(),
        bytes: bytes.len() as u64,
        sha256: fs::digest(&bytes),
    })
}

// Called only after the owning transaction has checked the durable preimage,
// finite freezer and same actual owner. Tests use actual held temporary files.
fn rename_selection(handles: &Handles, intent: &Intent) -> Result<()> {
    let selected = intent.operation == SelectionOperation::Withdraw;
    let flags = if intent.before.original.is_some() {
        RenameFlags::EXCHANGE
    } else {
        RenameFlags::NOREPLACE
    };
    let (from, from_name, to, to_name) = if selected {
        (&handles.public, "selected.json", &handles.work, PENDING)
    } else {
        (&handles.work, PENDING, &handles.public, "selected.json")
    };
    rustix::fs::renameat_with(from, from_name, to, to_name, flags)?;
    handles.public.sync_all()?;
    handles.work.sync_all()?;
    Ok(())
}

/// Opaque proof constructed only after an actual atomic rename, complete
/// parent/member readback, filesystem sync and a durable completion record.
pub(crate) struct WorkingSelectionProof {
    source: WorkingLabelSourceIdentity,
    handles: Rc<Handles>,
    intent: Intent,
    before_pin: FilePin,
    after: Observation,
    completed: FilePin,
    previous: Option<Rc<WorkingSelectionProof>>,
}
impl WorkingSelectionProof {
    pub(crate) fn require_identity(&self, source: &WorkingLabelSourceIdentity) -> Result<()> {
        self.source.require_identity(source)?;
        self.guard_records()
    }
    fn guard_records(&self) -> Result<()> {
        self.source.revalidate_normal_source()?;
        ensure(
            files::read_pin(&self.before_pin, 16 * 1024 * 1024)?
                == serde_json::to_vec(&self.intent)?,
            "working selected immutable preimage changed",
        )?;
        let result: Completion =
            serde_json::from_slice(&files::read_pin(&self.completed, 16 * 1024 * 1024)?)?;
        ensure(
            result.schema == "droidloom.working-selection-completed.v1"
                && equal_pin(&result.intent, &self.before_pin)
                && serde_json::to_value(&result.after)? == serde_json::to_value(&self.after)?,
            "working selection completion changed",
        )?;
        verify_transition(&self.intent, &self.after)?;
        if let Some(previous) = &self.previous {
            previous.guard_records()?;
            self.source.require_identity(&previous.source)?;
            ensure(
                previous.selected()
                    && !self.selected()
                    && equal_pin(&previous.intent.pair_intent, &self.intent.pair_intent)
                    && equal_pin(&previous.intent.label_plan, &self.intent.label_plan)
                    && previous.after.parent == self.intent.before.parent
                    && previous.after.candidate == self.intent.before.candidate
                    && previous.after.original == self.intent.before.original,
                "working selection history is not its exact forward/reverse checkpoint chain",
            )?;
        } else {
            ensure(
                self.selected(),
                "working withdrawal has no actual prior publication",
            )?;
        }
        Ok(())
    }
    pub(crate) fn guard(&self) -> Result<()> {
        self.guard_records()?;
        ensure(
            serde_json::to_value(self.handles.observation(self.selected())?)?
                == serde_json::to_value(&self.after)?,
            "working selected current state differs from its actual completed transition",
        )?;
        self.guard_records()
    }
    pub(crate) fn require_source(
        &self,
        source: &crate::cold_original_qualification::WorkingRuntimeSources,
    ) -> Result<()> {
        self.source.require_source(source)?;
        self.guard_records()
    }
    pub(crate) fn candidate_id(&self) -> &str {
        self.source.candidate()
    }
    pub(crate) fn parent_records(&self) -> Result<Value> {
        self.guard_records()?;
        Ok(json!({"before":self.intent.before.parent,"after":self.after.parent}))
    }
    pub(crate) fn require_label_evolution(
        &self,
        path: &Path,
        applied: &labels::Snapshot,
        current: &labels::Snapshot,
    ) -> Result<()> {
        self.guard_records()?;
        ensure(
            !self.selected(),
            "working label restoration requires actual selected withdrawal",
        )?;
        let first = self
            .previous
            .as_ref()
            .ok_or("working selection publication history absent")?;
        let (before, after) = if path == Path::new(SELECTED) {
            (&first.intent.before.candidate, &self.after.candidate)
        } else if path == Path::new("/etc/droidloom/production") {
            (
                &first.intent.before.parent.snapshot,
                &self.after.parent.snapshot,
            )
        } else {
            return Err("working selected evolution requested an unrelated inode".into());
        };
        ensure(
            before == applied && after == current,
            "working label current preimage differs from the two exact completed renames",
        )
    }
    pub(crate) fn selected(&self) -> bool {
        self.intent.operation == SelectionOperation::Publish
    }
    pub(crate) fn candidate_before(&self) -> &labels::Snapshot {
        &self.intent.before.candidate
    }
    pub(crate) fn candidate_after(&self) -> &labels::Snapshot {
        &self.after.candidate
    }
    pub(crate) fn original_initial(&self) -> Option<&labels::Snapshot> {
        self.previous
            .as_ref()
            .map_or(self.intent.before.original.as_ref(), |first| {
                first.intent.before.original.as_ref()
            })
    }
    pub(crate) fn original_before(&self) -> Option<&labels::Snapshot> {
        self.intent.before.original.as_ref()
    }
    pub(crate) fn original_after(&self) -> Option<&labels::Snapshot> {
        self.after.original.as_ref()
    }
    pub(crate) fn parent_before(&self) -> &SelectionDirectory {
        &self.intent.before.parent
    }
    pub(crate) fn parent_after(&self) -> &SelectionDirectory {
        &self.after.parent
    }
    pub(crate) fn report(&self) -> &FilePin {
        &self.completed
    }
    pub(crate) fn label_plan(&self) -> &FilePin {
        &self.intent.label_plan
    }
    pub(crate) fn pair_intent(&self) -> &FilePin {
        &self.intent.pair_intent
    }
    pub(crate) fn guard_original(&self, original: &Backing) -> Result<()> {
        self.guard_records()?;
        let expected = self
            .original_after()
            .ok_or("working selected original source absent")?;
        ensure(
            original.path == Path::new(SELECTED)
                && self.handles.original.as_ref().is_some_and(|file| {
                    fs::stat(file).ok().as_ref() == Some(labels::snapshot_identity(expected))
                })
                && labels::snapshot(&original.file)? == *expected,
            "working selected original no longer belongs to its actual retained descriptor",
        )?;
        let (parent, name) = if self.selected() {
            (&self.handles.work, PENDING)
        } else {
            (&self.handles.public, "selected.json")
        };
        let named = open_at(parent, name, false)?;
        ensure(
            labels::snapshot(&named)? == *expected,
            "working selected original pathname no longer names its retained inode",
        )
    }
}

/// Stored by the live dispatcher before any selection effect. An error retains
/// its preimage and both actual descriptions for exact reverse-only recovery.
pub(crate) struct WorkingSelectionTransaction {
    source: WorkingLabelSourceIdentity,
    handles: Rc<Handles>,
    pair_intent: FilePin,
    label_plan: FilePin,
    applied_labels: FilePin,
    records: PathBuf,
    initial: Observation,
    current: Option<Rc<WorkingSelectionProof>>,
    pending: Option<(Intent, FilePin)>,
    forward_attempted: bool,
}
impl WorkingSelectionTransaction {
    pub(super) fn prepare(
        pair: &WorkingPairTransaction,
        prepared: &PreparedReturnedPair,
        history: &ReturnedOnceHistory,
        applied: &labels::WorkingLabelsApplied,
    ) -> Result<Self> {
        pair.guard(prepared, history)?;
        applied.require_identity(&pair.label_source)?;
        ensure(
            pair.in_flight.is_none()
                && pair.observe()? == (Layout::Switched, SelectionState::Original)
                && pair.selected.is_none(),
            "working selection requires the same settled unselected labelled pair",
        )?;
        let state = pair
            .labelled
            .as_ref()
            .ok_or("working selection lacks actual label custody")?;
        let handles = Rc::new(Handles {
            public: pair.tx.locations.selected_parent.try_clone()?,
            work: pair.tx.locations.work.try_clone()?,
            candidate: pair.pending_file.try_clone()?,
            original: prepared
                .pair
                .selection_file
                .as_ref()
                .map(|s| s.file.try_clone())
                .transpose()?,
            work_path: pair.tx.locations.work_path.clone(),
            public_path: "/etc/droidloom/production".into(),
            candidate_sha256: state.pending.sha256.clone(),
            original_sha256: pair
                .tx
                .intent
                .old_selection
                .as_ref()
                .map(|s| s.sha256.clone()),
        });
        let records = pair.tx.locations.work_path.join("working-selection");
        files::private_dir(&records)?;
        files::private_dir(&records.join("publish"))?;
        files::private_dir(&records.join("withdraw"))?;
        let initial = handles.observation(false)?;
        ensure(
            initial.candidate == state.pending_snapshot
                && initial.original.as_ref()
                    == prepared.pair.selection_file.as_ref().map(|b| &b.snapshot),
            "working selection lost its exact original/candidate label observations",
        )?;
        let value = Self {
            source: pair.label_source.clone(),
            handles,
            pair_intent: pair.tx.intent_pin.clone(),
            label_plan: applied.source_plan().clone(),
            applied_labels: applied.report().clone(),
            records,
            initial,
            current: None,
            pending: None,
            forward_attempted: false,
        };
        pair.guard(prepared, history)?;
        Ok(value)
    }
    fn checkpoint(&self) -> &Observation {
        self.current.as_ref().map_or(&self.initial, |p| &p.after)
    }
    fn owner(&self) -> Result<()> {
        self.source.revalidate_selection_owner()
    }
    pub(crate) fn current(&self) -> Option<&Rc<WorkingSelectionProof>> {
        self.current.as_ref()
    }
    pub(crate) fn publish(
        &mut self,
        frozen: &crate::cold_original_qualification::WorkingQuiescence,
    ) -> Result<Rc<WorkingSelectionProof>> {
        ensure(
            !self.forward_attempted,
            "working selection forward cannot be replayed",
        )?;
        self.forward_attempted = true;
        frozen.require_identity(&self.source)?;
        self.begin(SelectionOperation::Publish)?;
        self.effect()?;
        self.reconcile()?
            .ok_or_else(|| "working selected publication did not occur".into())
    }
    fn begin(&mut self, operation: SelectionOperation) -> Result<()> {
        self.owner()?;
        ensure(
            self.pending.is_none(),
            "working selected previous atomic outcome remains unresolved",
        )?;
        let selected = operation == SelectionOperation::Withdraw;
        let before = self.handles.observation(selected)?;
        ensure(
            serde_json::to_value(&before)? == serde_json::to_value(self.checkpoint())?,
            "working selection changed outside its last exact completed transition",
        )?;
        let intent = Intent {
            schema: "droidloom.working-selection-intent.v1".into(),
            candidate_id: self.source.candidate().into(),
            pair_intent: self.pair_intent.clone(),
            label_plan: self.label_plan.clone(),
            applied_labels: self.applied_labels.clone(),
            operation,
            before,
        };
        let root = self
            .records
            .join(if selected { "withdraw" } else { "publish" });
        let pin = save(&root.join("INTENT.json"), &intent)?;
        self.pending = Some((intent, pin));
        self.owner()
    }
    fn effect(&self) -> Result<()> {
        self.owner()?;
        let (intent, _) = self
            .pending
            .as_ref()
            .ok_or("working selected effect has no durable preimage")?;
        let selected = intent.operation == SelectionOperation::Withdraw;
        ensure(
            serde_json::to_value(self.handles.observation(selected)?)?
                == serde_json::to_value(&intent.before)?,
            "working selection drifted after its durable preimage",
        )?;
        rename_selection(&self.handles, intent)
    }
    fn reconcile(&mut self) -> Result<Option<Rc<WorkingSelectionProof>>> {
        self.owner()?;
        let Some((intent, pin)) = &self.pending else {
            return Ok(self.current.clone());
        };
        let after_selected = intent.operation == SelectionOperation::Publish;
        if let Ok(before) = self.handles.observation(!after_selected) {
            ensure(
                serde_json::to_value(before)? == serde_json::to_value(&intent.before)?,
                "unapplied working selection changed another actual parent or inode",
            )?;
            self.pending = None;
            return Ok(self.current.clone());
        }
        let after = self.handles.observation(after_selected)?;
        verify_transition(intent, &after)?;
        self.handles.public.sync_all()?;
        self.handles.work.sync_all()?;
        let completed = save(
            &pin.path
                .parent()
                .ok_or("selection intent parent")?
                .join("COMPLETED.json"),
            &Completion {
                schema: "droidloom.working-selection-completed.v1".into(),
                intent: pin.clone(),
                after: after.clone(),
            },
        )?;
        let proof = Rc::new(WorkingSelectionProof {
            source: self.source.clone(),
            handles: Rc::clone(&self.handles),
            intent: intent.clone(),
            before_pin: pin.clone(),
            after,
            completed,
            previous: self.current.clone(),
        });
        proof.guard()?;
        self.current = Some(Rc::clone(&proof));
        self.pending = None;
        Ok(Some(proof))
    }
    pub(crate) fn reconcile_forward(&mut self) -> Result<Option<Rc<WorkingSelectionProof>>> {
        self.reconcile()
    }
    pub(crate) fn withdraw(
        &mut self,
        frozen: &crate::cold_original_qualification::WorkingQuiescence,
    ) -> Result<Option<Rc<WorkingSelectionProof>>> {
        frozen.require_identity(&self.source)?;
        self.reconcile()?;
        let Some(current) = &self.current else {
            return Ok(None);
        };
        if !current.selected() {
            current.guard()?;
            return Ok(Some(Rc::clone(current)));
        }
        self.begin(SelectionOperation::Withdraw)?;
        self.effect()?;
        self.reconcile()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::PermissionsExt;
    const ORIGINAL: &[u8] = b"original retained selected";
    const CANDIDATE: &[u8] = b"new exact selected";
    struct Fixture {
        root: tempfile::TempDir,
        handles: Handles,
    }
    impl Fixture {
        fn new(original: bool) -> Self {
            let root = tempfile::Builder::new()
                .prefix(".p4-working-selected-")
                .tempdir_in(std::env::current_dir().unwrap())
                .unwrap();
            let public_path = root.path().join("public");
            let work_path = root.path().join("private");
            std::fs::create_dir(&public_path).unwrap();
            std::fs::create_dir(&work_path).unwrap();
            std::fs::write(work_path.join(PENDING), CANDIDATE).unwrap();
            if original {
                std::fs::write(public_path.join("selected.json"), ORIGINAL).unwrap();
            }
            std::fs::write(public_path.join("unrelated"), b"untouched").unwrap();
            std::fs::write(work_path.join("unrelated"), b"private untouched").unwrap();
            let handles = Handles {
                public: File::open(&public_path).unwrap(),
                work: File::open(&work_path).unwrap(),
                candidate: File::open(work_path.join(PENDING)).unwrap(),
                original: original.then(|| File::open(public_path.join("selected.json")).unwrap()),
                public_path,
                work_path,
                candidate_sha256: fs::digest(CANDIDATE),
                original_sha256: original.then(|| fs::digest(ORIGINAL)),
            };
            Self { root, handles }
        }
        fn intent(&self, operation: SelectionOperation) -> Intent {
            let pin = FilePin {
                path: self.root.path().join("source-pin"),
                bytes: 1,
                sha256: "a".repeat(64),
            };
            Intent {
                schema: "droidloom.working-selection-intent.v1".into(),
                candidate_id: "b".repeat(64),
                pair_intent: pin.clone(),
                label_plan: pin.clone(),
                applied_labels: pin,
                operation,
                before: self
                    .handles
                    .observation(operation == SelectionOperation::Withdraw)
                    .unwrap(),
            }
        }
    }
    #[test]
    fn working_selected_actual_exchange_and_absent_selection_roundtrip() {
        for original in [false, true] {
            let fixture = Fixture::new(original);
            let publish = fixture.intent(SelectionOperation::Publish);
            rename_selection(&fixture.handles, &publish).unwrap();
            let after = fixture.handles.observation(true).unwrap();
            verify_transition(&publish, &after).unwrap();
            assert!(fixture.handles.observation(false).is_err());
            assert_eq!(
                std::fs::read(fixture.handles.public_path.join("selected.json")).unwrap(),
                CANDIDATE
            );
            let withdraw = fixture.intent(SelectionOperation::Withdraw);
            rename_selection(&fixture.handles, &withdraw).unwrap();
            let restored = fixture.handles.observation(false).unwrap();
            verify_transition(&withdraw, &restored).unwrap();
            assert_eq!(
                std::fs::read(fixture.handles.work_path.join(PENDING)).unwrap(),
                CANDIDATE
            );
            if original {
                assert_eq!(
                    std::fs::read(fixture.handles.public_path.join("selected.json")).unwrap(),
                    ORIGINAL
                );
                assert_eq!(
                    serde_json::to_value(restored.original.as_ref().unwrap()).unwrap()["handle"],
                    serde_json::to_value(publish.before.original.as_ref().unwrap()).unwrap()["handle"]
                );
            } else {
                assert!(!fixture.handles.public_path.join("selected.json").exists());
            }
            assert_eq!(
                serde_json::to_value(&restored.candidate).unwrap()["handle"],
                serde_json::to_value(&publish.before.candidate).unwrap()["handle"]
            );
        }
    }
    #[test]
    fn working_selected_rejects_same_bytes_replacement_and_unrelated_parent_changes() {
        let fixture = Fixture::new(true);
        let publish = fixture.intent(SelectionOperation::Publish);
        rename_selection(&fixture.handles, &publish).unwrap();
        let path = fixture.handles.public_path.join("unrelated");
        let file = File::open(&path).unwrap();
        rustix::fs::fsetxattr(
            &file,
            "user.droidloom.foreign",
            b"changed",
            rustix::fs::XattrFlags::empty(),
        )
        .unwrap();
        let after = fixture.handles.observation(true).unwrap();
        assert!(verify_transition(&publish, &after).is_err());
        let selected = fixture.handles.public_path.join("selected.json");
        std::fs::rename(
            &selected,
            fixture.handles.public_path.join("foreign-displaced"),
        )
        .unwrap();
        std::fs::write(&selected, CANDIDATE).unwrap();
        assert!(fixture.handles.observation(true).is_err());
        assert_eq!(
            read_small(&fixture.handles.candidate, 16384).unwrap(),
            CANDIDATE
        );
    }
    #[test]
    fn working_selected_create_only_record_preserves_interruption_and_rejects_overwrite() {
        let root = tempfile::Builder::new()
            .prefix(".p4-working-selected-record-")
            .tempdir_in(std::env::current_dir().unwrap())
            .unwrap();
        let path = root.path().join("COMPLETED.json");
        let interrupted = root.path().join("COMPLETED.json.pending");
        std::fs::write(&interrupted, b"actual interrupted bytes").unwrap();
        std::fs::set_permissions(&interrupted, std::fs::Permissions::from_mode(0o400)).unwrap();
        let record = json!({"actual":"first complete observation"});
        let pin = save(&path, &record).unwrap();
        assert_eq!(
            std::fs::read(root.path().join("COMPLETED.json.pending.interrupted-0")).unwrap(),
            b"actual interrupted bytes"
        );
        assert!(equal_pin(&pin, &save(&path, &record).unwrap()));
        assert!(save(&path, &json!({"foreign":"overwrite"})).is_err());
        assert_eq!(
            files::read_pin(&pin, 16384).unwrap(),
            serde_json::to_vec(&record).unwrap()
        );
    }
}
