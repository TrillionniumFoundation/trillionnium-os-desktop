//! Exactly the selected.json rename and its normal-parent metadata evolution.
//! The full label proof precedes publication. Each operation has a durable
//! preimage, and an interrupted rename is reconciled from both actual inodes.
use super::*;

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(super) struct DirectoryState {
    pub(super) snapshot: Snapshot,
    pub(super) members: BTreeMap<String, Identity>,
}
#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
enum Operation {
    Publish,
    Withdraw,
}
#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct SelectionIntent {
    schema: String,
    candidate_id: String,
    pair_intent: FilePin,
    source_plan: FilePin,
    operation: Operation,
    parent: DirectoryState,
    work: DirectoryState,
    candidate: Snapshot,
    original: Option<Snapshot>,
}
#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct SelectionResult {
    schema: String,
    intent: FilePin,
    parent: DirectoryState,
    work: DirectoryState,
    candidate: Snapshot,
    original: Option<Snapshot>,
}
pub(super) fn directory_state(held: &File) -> Result<DirectoryState> {
    let before = snapshot(held)?;
    ensure(
        FileType::from_raw_mode(before.identity.mode) == FileType::Directory,
        "selected parent is not an actual directory",
    )?;
    let directory = File::from(rustix::fs::openat(
        held,
        ".",
        OFlags::RDONLY | OFlags::DIRECTORY | OFlags::NOFOLLOW | OFlags::CLOEXEC | OFlags::NOATIME,
        Mode::empty(),
    )?);
    ensure(
        fs::stat(&directory)? == before.identity,
        "selected directory descriptor differs",
    )?;
    let mut members = BTreeMap::new();
    for entry in rustix::fs::Dir::read_from(&directory)? {
        let entry = entry?;
        let name = entry.file_name().to_str()?;
        if matches!(name, "." | "..") {
            continue;
        }
        ensure(
            members.len() < 4096,
            "selected parent has an unbounded member set",
        )?;
        let identity = fs::identity(&rustix::fs::statat(
            &directory,
            name,
            AtFlags::SYMLINK_NOFOLLOW,
        )?);
        ensure(
            members.insert(name.to_owned(), identity).is_none(),
            "duplicate selected parent entry",
        )?;
    }
    ensure(
        snapshot(held)? == before,
        "selected parent changed during complete member capture",
    )?;
    Ok(DirectoryState {
        snapshot: before,
        members,
    })
}
fn metadata_after_rename(before: &Snapshot, after: &Snapshot) -> Result<()> {
    ensure(
        before.handle == after.handle
            && before.attributes == after.attributes
            && only_ctime_changed(&before.identity, &after.identity),
        "owned configuration rename changed an unrelated inode or attribute",
    )
}
fn named(scope: &RootScope, path: &Path) -> Result<Option<Snapshot>> {
    match std::fs::symlink_metadata(path) {
        Ok(_) => Ok(Some(snapshot(&scope.open_named(path)?)?)),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(None),
        Err(error) => Err(error.into()),
    }
}
fn actual_pair(
    scope: &RootScope,
    data: &OriginalDataTransaction,
    state: data::SelectionState,
) -> Result<(Snapshot, Option<Snapshot>)> {
    let pending = data.transaction.locations.work_path.join(data::PENDING);
    let (candidate, original) = if state == data::SelectionState::Candidate {
        (PathBuf::from(data::SELECTED), pending)
    } else {
        (pending, PathBuf::from(data::SELECTED))
    };
    Ok((
        snapshot(&scope.open_named(&candidate)?)?,
        named(scope, &original)?,
    ))
}
fn records(authority: &OriginalQualificationAuthority, operation: Operation) -> Result<Records> {
    let name = match operation {
        Operation::Publish => "selected-publish",
        Operation::Withdraw => "selected-withdraw",
    };
    let path = authority.work().join("labels").join(name);
    match std::fs::symlink_metadata(&path) {
        Ok(_) => {}
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
            crate::boot_files::private_dir(&path)?
        }
        Err(error) => return Err(error.into()),
    }
    Records::open(&path)
}
fn load(
    records: &Records,
    authority: &OriginalQualificationAuthority,
    data: &OriginalDataTransaction,
    operation: Operation,
) -> Result<(FilePin, SelectionIntent)> {
    let pin = record_pin(records, "PREIMAGE.json")?;
    let (_, _, body) = records.read("PREIMAGE.json")?;
    let intent: SelectionIntent = serde_json::from_slice(&body)?;
    ensure(
        intent.schema == "droidloom.original-selection-label-intent.v1"
            && intent.candidate_id == authority.candidate_id()
            && pin_equal(&intent.pair_intent, data.intent())
            && intent.operation == operation
            && intent.source_plan.path == authority.work().join("labels/LABEL-PLAN.json"),
        "selected rename preimage is outside the same original label/data transaction",
    )?;
    authority.verify_label_plan(&intent.source_plan)?;
    Ok((pin, intent))
}
fn verify_result(intent: &SelectionIntent, actual: &SelectionResult) -> Result<()> {
    ensure(
        actual.schema == "droidloom.original-selection-label-result.v1",
        "selected rename result schema differs",
    )?;
    metadata_after_rename(&intent.candidate, &actual.candidate)?;
    let (public_before, public_after, private_before, private_after) = match intent.operation {
        Operation::Publish => (
            intent.original.as_ref().map(|n| &n.identity),
            Some(&actual.candidate.identity),
            Some(&intent.candidate.identity),
            actual.original.as_ref().map(|n| &n.identity),
        ),
        Operation::Withdraw => (
            Some(&intent.candidate.identity),
            actual.original.as_ref().map(|n| &n.identity),
            intent.original.as_ref().map(|n| &n.identity),
            Some(&actual.candidate.identity),
        ),
    };
    match (&intent.original, &actual.original) {
        (Some(before), Some(after)) => metadata_after_rename(before, after)?,
        (None, None) => {}
        _ => return Err("original selected inode was lost or invented".into()),
    }
    verify_directory_delta(
        &intent.parent,
        &actual.parent,
        "selected.json",
        public_before,
        public_after,
    )?;
    verify_directory_delta(
        &intent.work,
        &actual.work,
        data::PENDING,
        private_before,
        private_after,
    )
}
fn verify_directory_delta(
    before: &DirectoryState,
    after: &DirectoryState,
    name: &str,
    old: Option<&Identity>,
    new: Option<&Identity>,
) -> Result<()> {
    ensure(
        before.members.get(name) == old,
        "rename parent does not contain the recorded preimage inode",
    )?;
    let a = &before.snapshot;
    let b = &after.snapshot;
    ensure(
        a.handle == b.handle
            && a.attributes == b.attributes
            && (
                a.identity.dev,
                a.identity.ino,
                a.identity.mode,
                a.identity.uid,
                a.identity.gid,
                a.identity.nlink,
            ) == (
                b.identity.dev,
                b.identity.ino,
                b.identity.mode,
                b.identity.uid,
                b.identity.gid,
                b.identity.nlink,
            ),
        "rename parent changed generation, authority, links or xattrs",
    )?;
    let mut expected = before.members.clone();
    if let Some(identity) = new {
        expected.insert(name.to_owned(), identity.clone());
    } else {
        expected.remove(name);
    }
    ensure(
        expected == after.members,
        "rename changed another parent member",
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::PermissionsExt;
    fn open(path: &Path) -> File {
        File::from(
            rustix::fs::open(
                path,
                OFlags::PATH | OFlags::NOFOLLOW | OFlags::CLOEXEC,
                Mode::empty(),
            )
            .unwrap(),
        )
    }
    fn source() -> FilePin {
        FilePin {
            path: PathBuf::from("/qualification/source"),
            bytes: 1,
            sha256: "a".repeat(64),
        }
    }
    #[test]
    fn actual_atomic_selection_exchange_binds_only_exact_parent_and_inode_changes() {
        let tmp = tempfile::Builder::new()
            .prefix(".p4-selection-label-")
            .tempdir_in(std::env::current_dir().unwrap())
            .unwrap();
        let parent = tmp.path().join("public");
        std::fs::create_dir(&parent).unwrap();
        let work = tmp.path().join("private");
        std::fs::create_dir(&work).unwrap();
        std::fs::set_permissions(&parent, std::fs::Permissions::from_mode(0o700)).unwrap();
        let target = parent.join("selected.json");
        let pending = work.join(data::PENDING);
        std::fs::write(&target, b"original selected bytes").unwrap();
        std::fs::write(&pending, b"candidate selected bytes").unwrap();
        std::fs::write(parent.join("unrelated"), b"preserved").unwrap();
        let held = open(&parent);
        let candidate = open(&pending);
        let old = open(&target);
        let intent = SelectionIntent {
            schema: "droidloom.original-selection-label-intent.v1".into(),
            candidate_id: "b".repeat(64),
            pair_intent: source(),
            source_plan: source(),
            operation: Operation::Publish,
            parent: directory_state(&held).unwrap(),
            work: directory_state(&open(&work)).unwrap(),
            candidate: snapshot(&candidate).unwrap(),
            original: Some(snapshot(&old).unwrap()),
        };
        rustix::fs::renameat_with(
            rustix::fs::CWD,
            &pending,
            rustix::fs::CWD,
            &target,
            RenameFlags::EXCHANGE,
        )
        .unwrap();
        File::open(&parent).unwrap().sync_all().unwrap();
        File::open(&work).unwrap().sync_all().unwrap();
        let output = SelectionResult {
            schema: "droidloom.original-selection-label-result.v1".into(),
            intent: source(),
            parent: directory_state(&held).unwrap(),
            work: directory_state(&open(&work)).unwrap(),
            candidate: snapshot(&candidate).unwrap(),
            original: Some(snapshot(&old).unwrap()),
        };
        verify_result(&intent, &output).unwrap();
        assert_eq!(std::fs::read(&pending).unwrap(), b"original selected bytes");
        assert_eq!(std::fs::read(&target).unwrap(), b"candidate selected bytes");
        std::fs::write(parent.join("unrelated"), b"unrelated change must reject").unwrap();
        let mut wrong = output;
        wrong.parent = directory_state(&held).unwrap();
        assert!(verify_result(&intent, &wrong).is_err());
    }
    #[test]
    fn selection_parent_cannot_change_generation_or_other_xattrs() {
        let tmp = tempfile::Builder::new()
            .prefix(".p4-selection-parent-")
            .tempdir_in(std::env::current_dir().unwrap())
            .unwrap();
        let target = tmp.path().join("selected.json");
        std::fs::write(&target, b"candidate").unwrap();
        let parent = open(tmp.path());
        let held = open(&target);
        let before = directory_state(&parent).unwrap();
        let node = snapshot(&held).unwrap();
        let intent = SelectionIntent {
            schema: "droidloom.original-selection-label-intent.v1".into(),
            candidate_id: "b".repeat(64),
            pair_intent: source(),
            source_plan: source(),
            operation: Operation::Withdraw,
            parent: before.clone(),
            work: before.clone(),
            candidate: node.clone(),
            original: None,
        };
        let mut changed = before;
        changed.members.remove("selected.json");
        changed
            .snapshot
            .attributes
            .insert("user.other".into(), b"unknown".to_vec());
        let output = SelectionResult {
            schema: "droidloom.original-selection-label-result.v1".into(),
            intent: source(),
            parent: changed,
            work: intent.work.clone(),
            candidate: node,
            original: None,
        };
        assert!(verify_result(&intent, &output).is_err());
    }
}
fn finish(
    records: &Records,
    pin: &FilePin,
    intent: &SelectionIntent,
    scope: &RootScope,
    authority: &OriginalQualificationAuthority,
    data: &OriginalDataTransaction,
) -> Result<(FilePin, SelectionResult)> {
    let expected = if intent.operation == Operation::Publish {
        data::SelectionState::Candidate
    } else {
        data::SelectionState::Original
    };
    ensure(
        data.transaction.observe(true)?.1 == expected,
        "selected rename has not reached its exact owned layout",
    )?;
    let parent = directory_state(&data.transaction.locations.selected_parent)?;
    let (candidate, original) = actual_pair(scope, data, expected)?;
    let work = directory_state(&data.transaction.locations.work)?;
    let output = SelectionResult {
        schema: "droidloom.original-selection-label-result.v1".into(),
        intent: pin.clone(),
        parent,
        work,
        candidate,
        original,
    };
    let (result, output) = if records.exists("RESULT.json")? {
        let (_, _, body) = records.read("RESULT.json")?;
        let previous: SelectionResult = serde_json::from_slice(&body)?;
        ensure(
            pin_equal(&previous.intent, pin),
            "completed selection uses another rename intent",
        )?;
        verify_result(intent, &previous)?;
        ensure(
            serde_json::to_value(&previous.parent)? == serde_json::to_value(&output.parent)?
                && previous.candidate == output.candidate
                && previous.original == output.original,
            "completed selection's actual public parent or two inodes changed",
        )?;
        // The once owner may subsequently append its own durable phases under
        // work. Their authority is checked separately; the complete pre/post
        // private-parent evidence here describes exactly the completed rename.
        let a = &previous.work.snapshot;
        let b = &output.work.snapshot;
        ensure(
            a.handle == b.handle
                && a.attributes == b.attributes
                && (
                    a.identity.dev,
                    a.identity.ino,
                    a.identity.mode,
                    a.identity.uid,
                    a.identity.gid,
                ) == (
                    b.identity.dev,
                    b.identity.ino,
                    b.identity.mode,
                    b.identity.uid,
                    b.identity.gid,
                )
                && previous.work.members.get(data::PENDING)
                    == output.work.members.get(data::PENDING),
            "completed selection lost private-parent custody or its exact pending inode",
        )?;
        (record_pin(records, "RESULT.json")?, previous)
    } else {
        verify_result(intent, &output)?;
        data.transaction.locations.selected_parent.sync_all()?;
        data.transaction.locations.work.sync_all()?;
        ensure(
            serde_json::to_value(directory_state(
                &data.transaction.locations.selected_parent,
            )?)? == serde_json::to_value(&output.parent)?
                && serde_json::to_value(directory_state(&data.transaction.locations.work)?)?
                    == serde_json::to_value(&output.work)?,
            "selection parents changed across their durability barriers",
        )?;
        (records.publish("RESULT.json", &output)?, output)
    };
    authority.verify_label_plan(&intent.source_plan)?;
    data.binding(authority)?;
    Ok((result, output))
}

pub(super) fn publish(
    applied: &OriginalLabelsApplied,
    authority: &OriginalQualificationAuthority,
    data: &OriginalDataTransaction,
) -> Result<Value> {
    authority.verify_data_step(OriginalDataStep::PublishSelection)?;
    data.binding(authority)?;
    let records = records(authority, Operation::Publish)?;
    let scope = RootScope::original(&data.transaction.intent.cold_clone)?;
    if !records.exists("PREIMAGE.json")? {
        records.verify_unpublished_preimage()?;
        applied.verify_selection_ready(authority, data)?;
        ensure(
            data.transaction.observe(true)?
                == (data::Layout::Switched, data::SelectionState::Original),
            "selected publication requires complete labels and the unpublished exchanged pair",
        )?;
        let parent = directory_state(&data.transaction.locations.selected_parent)?;
        let expected = applied.applied_snapshot(Path::new("/etc/droidloom/production"))?;
        ensure(
            parent.snapshot == expected,
            "selected parent changed after complete label readback",
        )?;
        let (candidate, original) = actual_pair(&scope, data, data::SelectionState::Original)?;
        ensure(
            candidate == applied.applied_snapshot(Path::new(data::SELECTED))?,
            "pending selection does not have its complete actual source-bound label",
        )?;
        match (&original, &data.transaction.intent.old_selection) {
            (Some(actual), Some(old)) => ensure(
                actual.identity == old.identity,
                "original selected inode changed before publication",
            )?,
            (None, None) => {}
            _ => return Err("original selected existence changed before publication".into()),
        }
        records.publish(
            "PREIMAGE.json",
            &SelectionIntent {
                schema: "droidloom.original-selection-label-intent.v1".into(),
                candidate_id: authority.candidate_id().into(),
                pair_intent: data.intent().clone(),
                source_plan: applied.source_plan().clone(),
                operation: Operation::Publish,
                parent,
                work: directory_state(&data.transaction.locations.work)?,
                candidate,
                original,
            },
        )?;
    }
    let (pin, intent) = load(&records, authority, data, Operation::Publish)?;
    if data.transaction.observe(true)?.1 == data::SelectionState::Original {
        applied.verify_selection_ready(authority, data)?;
        let (candidate, original) = actual_pair(&scope, data, data::SelectionState::Original)?;
        ensure(
            directory_state(&data.transaction.locations.selected_parent)?.snapshot
                == intent.parent.snapshot
                && serde_json::to_value(directory_state(&data.transaction.locations.work)?)?
                    == serde_json::to_value(&intent.work)?
                && candidate == intent.candidate
                && original == intent.original,
            "selected publication preimage changed before its actual rename",
        )?;
        authority.verify_data_step(OriginalDataStep::PublishSelection)?;
        data.binding(authority)?;
        data.transaction.publish_selection()?;
    }
    let (result, actual) = finish(&records, &pin, &intent, &scope, authority, data)?;
    authority.verify_data_step(OriginalDataStep::PublishSelection)?;
    Ok(
        json!({"schema":"droidloom.original-labeled-selection-published.v1","source_plan":intent.source_plan,
        "pair_intent":data.intent(),"actual_rename":result,"selected_identity":actual.candidate,
        "qualification_boot_authorized":false,"runtime_or_migration_accepted":false}),
    )
}

pub(in crate::cold_original_data) fn withdraw(
    authority: &OriginalQualificationAuthority,
    data: &OriginalDataTransaction,
) -> Result<Option<Value>> {
    authority.verify_data_step(OriginalDataStep::WithdrawSelection)?;
    data.binding(authority)?;
    let publication = authority.work().join("labels/selected-publish");
    match std::fs::symlink_metadata(&publication) {
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(None),
        Err(error) => return Err(error.into()),
        Ok(_) => {}
    }
    let forward = Records::open(&publication)?;
    if !forward.exists("PREIMAGE.json")? {
        forward.verify_unpublished_preimage()?;
        ensure(
            data.transaction.observe(true)?.1 == data::SelectionState::Original,
            "selection changed without its durable label preimage",
        )?;
        return Ok(None);
    }
    let (forward_pin, forward_intent) = load(&forward, authority, data, Operation::Publish)?;
    let records = records(authority, Operation::Withdraw)?;
    let scope = RootScope::original(&data.transaction.intent.cold_clone)?;
    if !records.exists("PREIMAGE.json")? {
        records.verify_unpublished_preimage()?;
        if data.transaction.observe(true)?.1 == data::SelectionState::Original {
            let (candidate, original) = actual_pair(&scope, data, data::SelectionState::Original)?;
            ensure(
                candidate == forward_intent.candidate
                    && original == forward_intent.original
                    && directory_state(&data.transaction.locations.selected_parent)?.snapshot
                        == forward_intent.parent.snapshot,
                "unpublished selected intent has an unknown pre-rename outcome",
            )?;
            return Ok(None);
        }
        let (_, published) = finish(
            &forward,
            &forward_pin,
            &forward_intent,
            &scope,
            authority,
            data,
        )?;
        records.publish(
            "PREIMAGE.json",
            &SelectionIntent {
                schema: "droidloom.original-selection-label-intent.v1".into(),
                candidate_id: authority.candidate_id().into(),
                pair_intent: data.intent().clone(),
                source_plan: forward_intent.source_plan.clone(),
                operation: Operation::Withdraw,
                parent: published.parent,
                work: directory_state(&data.transaction.locations.work)?,
                candidate: published.candidate,
                original: published.original,
            },
        )?;
    }
    let (pin, intent) = load(&records, authority, data, Operation::Withdraw)?;
    if data.transaction.observe(true)?.1 == data::SelectionState::Candidate {
        let (candidate, original) = actual_pair(&scope, data, data::SelectionState::Candidate)?;
        ensure(
            candidate == intent.candidate
                && original == intent.original
                && directory_state(&data.transaction.locations.selected_parent)?.snapshot
                    == intent.parent.snapshot
                && serde_json::to_value(directory_state(&data.transaction.locations.work)?)?
                    == serde_json::to_value(&intent.work)?,
            "selected withdrawal changed after its durable actual preimage",
        )?;
        authority.verify_data_step(OriginalDataStep::WithdrawSelection)?;
        data.binding(authority)?;
        data.transaction.restore_selection()?;
    }
    let (result, actual) = finish(&records, &pin, &intent, &scope, authority, data)?;
    authority.verify_data_step(OriginalDataStep::WithdrawSelection)?;
    Ok(Some(
        json!({"schema":"droidloom.original-labeled-selection-withdrawn.v1","actual_rename":result,
        "source_plan":intent.source_plan,"pair_intent":data.intent(),"actual_original_selection":actual.original}),
    ))
}

pub(super) fn published_evolution(
    applied: &OriginalLabelsApplied,
    authority: &OriginalQualificationAuthority,
    data: &OriginalDataTransaction,
) -> Result<(Snapshot, Snapshot)> {
    authority.verify_current_owner()?;
    data.binding(authority)?;
    let records = Records::open(&authority.work().join("labels/selected-publish"))?;
    let (intent_pin, intent) = load(&records, authority, data, Operation::Publish)?;
    ensure(
        pin_equal(&intent.source_plan, applied.source_plan()),
        "published selection uses another actual source plan",
    )?;
    let (_, _, bytes) = records.read("RESULT.json")?;
    let result: SelectionResult = serde_json::from_slice(&bytes)?;
    ensure(
        pin_equal(&result.intent, &intent_pin),
        "published selection result is not linked to its durable preimage",
    )?;
    verify_result(&intent, &result)?;
    let scope = RootScope::original(&data.transaction.intent.cold_clone)?;
    let (candidate, original) = actual_pair(&scope, data, data::SelectionState::Candidate)?;
    let parent = directory_state(&data.transaction.locations.selected_parent)?;
    ensure(
        candidate == result.candidate
            && original == result.original
            && serde_json::to_value(&parent)? == serde_json::to_value(&result.parent)?,
        "published selected inode/parent no longer matches its actual rename derivation",
    )?;
    authority.verify_current_owner()?;
    Ok((result.parent.snapshot, result.candidate))
}

pub(super) fn withdrawn_evolution(
    retirement: &crate::cold_original_qualification::OriginalRetirement,
    data: &OriginalDataTransaction,
) -> Result<BTreeMap<PathBuf, (Snapshot, FilePin)>> {
    let authority = retirement.authority();
    retirement.revalidate()?;
    data.binding(authority)?;
    ensure(
        data.transaction.observe(true)?.1 == data::SelectionState::Original,
        "label restoration requires the actual original selection",
    )?;
    let path = authority.work().join("labels/selected-withdraw");
    match std::fs::symlink_metadata(&path) {
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(BTreeMap::new()),
        Err(e) => return Err(e.into()),
        Ok(_) => {}
    }
    let records = Records::open(&path)?;
    let (intent_pin, intent) = load(&records, authority, data, Operation::Withdraw)?;
    let pin = record_pin(&records, "RESULT.json")?;
    let (_, _, bytes) = records.read("RESULT.json")?;
    let result: SelectionResult = serde_json::from_slice(&bytes)?;
    ensure(
        pin_equal(&result.intent, &intent_pin),
        "withdrawn selection lacks its actual durable intent",
    )?;
    verify_result(&intent, &result)?;
    Ok(BTreeMap::from([
        (
            PathBuf::from("/etc/droidloom/production"),
            (result.parent.snapshot, pin.clone()),
        ),
        (PathBuf::from(data::SELECTED), (result.candidate, pin)),
    ]))
}
