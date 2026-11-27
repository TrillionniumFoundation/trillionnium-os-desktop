//! Read-only custody of the actual returned original and working image pairs.
//! Only a held, normal ReturnedOnceHistory can supply the finite post-label
//! snapshots. Old COPY/CLONE timestamps are not refreshed after runtime writes.
use super::*;
use crate::cold_original_qualification::ReturnedOnceHistory;
use std::collections::BTreeSet;
#[path = "cold_returned_preparation.rs"]
mod preparation;
pub(crate) use preparation::{PreparedReturnedPair, WorkingPairTransaction};

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct RestoredRow {
    ordinal: u32,
    prelabel: labels::Snapshot,
    current_before: labels::Snapshot,
    restored: labels::Snapshot,
    original_preimage: Option<FilePin>,
    restoration: Option<FilePin>,
    recognized_history: Option<FilePin>,
    target_write: bool,
}
struct Backing {
    path: PathBuf,
    file: File,
    identity: Identity,
    snapshot: labels::Snapshot,
}
pub(crate) struct ReturnedWorkingPair {
    pid: u32,
    candidate: String,
    pair_intent: FilePin,
    original: PairRecord,
    working: PairRecord,
    parents: Vec<(PathBuf, File, labels::Snapshot)>,
    backings: Vec<Backing>,
    selection: Option<PublicFile>,
    pending: PublicFile,
    selection_file: Option<Backing>,
    pending_file: Backing,
    references: Value,
}
fn current_pair(path: &str, names: &[&str]) -> Result<PairRecord> {
    let (parent, name) = fs::Tree::open("/", 0)?.parent(path)?;
    capture_pair(&parent, &name, names, 0)
}
fn current_public(path: &Path) -> Result<Option<PublicFile>> {
    let tree = fs::Tree::open("/", 0)?;
    let (parent, name) = match tree.parent(&fs::absolute_string(path)?) {
        Ok(v) => v,
        Err(e) if e.downcast_ref::<rustix::io::Errno>() == Some(&rustix::io::Errno::NOENT) => {
            return Ok(None);
        }
        Err(e) => return Err(e),
    };
    let Some(before) = named(&parent, &name)? else {
        return Ok(None);
    };
    let file = open_at(&parent, &name, false)?;
    ensure(
        fs::stat(&file)? == before,
        "returned selection inode changed before read",
    )?;
    let body = read_small(&file, 1024 * 1024)?;
    ensure(
        fs::stat(&file)? == before && named(&parent, &name)? == Some(before.clone()),
        "returned selection inode changed during read",
    )?;
    Ok(Some(PublicFile {
        identity: before,
        sha256: fs::digest(&body),
    }))
}
fn snapshot_from(v: &Value) -> Result<labels::Snapshot> {
    Ok(serde_json::from_value(v.clone())?)
}
fn held_metadata(held: &File, named: &File, expected: &Identity) -> Result<()> {
    ensure(
        fs::stat(held)? == *expected && fs::stat(named)? == *expected,
        "returned held/named file lost its complete observed identity",
    )
}
fn hold_public(path: &Path, expected: &PublicFile) -> Result<Backing> {
    let file = fs::Tree::open("/", 0)?.file(&fs::absolute_string(path)?)?;
    ensure(
        fs::stat(&file)? == expected.identity,
        "returned public file changed before custody",
    )?;
    let snapshot = labels::snapshot(&file)?;
    ensure(
        fs::stat(&file)? == expected.identity,
        "returned public file changed during custody",
    )?;
    Ok(Backing {
        path: path.to_owned(),
        file,
        identity: expected.identity.clone(),
        snapshot,
    })
}
fn guard_file(file: &Backing) -> Result<()> {
    let named = fs::Tree::open("/", 0)?.file(&fs::absolute_string(&file.path)?)?;
    held_metadata(&file.file, &named, &file.identity)?;
    ensure(
        labels::snapshot(&file.file)? == file.snapshot
            && labels::snapshot(&named)? == file.snapshot,
        "returned file changed its exact generation or attributes",
    )?;
    held_metadata(&file.file, &named, &file.identity)
}
fn verify_current_preimage(
    history: &mut ReturnedOnceHistory,
    directory: &Path,
    logical: &Path,
    target: &Value,
    row: &RestoredRow,
    source: &FilePin,
    actual: &Value,
) -> Result<()> {
    let preimage: FilePin = serde_json::from_value(actual["current_preimage"].clone())?;
    let current = history.read_work_record(&preimage, 32 * 1024 * 1024)?;
    let retired_pin: FilePin = serde_json::from_value(current["retirement"].clone())?;
    let retired = history.read_retirement_record(&retired_pin)?;
    let applied_pin: FilePin = serde_json::from_value(current["applied"].clone())?;
    ensure(
        preimage.path
            == directory
                .join(format!("retirement-{}", retired_pin.sha256))
                .join("CURRENT-PREIMAGE.json")
            && current["schema"] == "droidloom.current-label-restore-preimage.v1"
            && current["original_preimage"] == serde_json::to_value(source)?
            && current["class"].is_null()
            && applied_pin.path == directory.join("APPLIED.json"),
        "working current preimage lost its exact source or actual retirement epoch",
    )?;
    let applied = history.read_work_record(&applied_pin, 32 * 1024 * 1024)?;
    let before = snapshot_from(&target["before"])?;
    let applied_after = snapshot_from(&applied["after"])?;
    ensure(
        applied["schema"] == "droidloom.original-label-applied.v1"
            && applied["preimage"] == serde_json::to_value(source)?
            && applied["before"] == target["before"]
            && applied["after"]["attributes"]["security.selinux"] == target["desired"]
            && labels::only_ctime_changed(
                labels::snapshot_identity(&before),
                labels::snapshot_identity(&applied_after),
            ),
        "working original label application lacks its exact source transition",
    )?;
    labels::verify_data_snapshot(&before, &applied_after, true)?;
    let captured = snapshot_from(&current["current"])?;
    ensure(
        stable(
            labels::snapshot_identity(&before),
            labels::snapshot_identity(&captured),
        ),
        "working current preimage changed the fixed inode authority",
    )?;
    labels::verify_data_snapshot(&applied_after, &captured, false)?;
    let is_backing = IMAGES
        .iter()
        .any(|name| logical == Path::new(ORIGINAL).join(name));
    if current["evolution"].is_null() {
        ensure(
            captured == applied_after,
            "immutable working proof acquired a runtime metadata change",
        )?;
    } else {
        let evolution = &current["evolution"];
        ensure(
            evolution["actual"] == current["current"]
                && ((is_backing && evolution["kind"] == "working_backing")
                    || (logical == Path::new(ORIGINAL) && evolution["kind"] == "pair_rename")),
            "working current preimage contains an unapproved evolution class",
        )?;
        let evolution_pin: FilePin = serde_json::from_value(evolution["evidence"].clone())?;
        if is_backing {
            ensure(
                same_pin(&evolution_pin, &retired_pin),
                "working backing evolution used another actual retirement",
            )?;
            let sync = &retired["working_data"]["actual_synchronization"];
            let rows = sync["backings"]
                .as_array()
                .ok_or("historical working fsync rows absent")?;
            let captured_id = serde_json::to_value(labels::snapshot_identity(&captured))?;
            ensure(
                sync["schema"] == "droidloom.working-pair-recovery-fsync.v1"
                    && rows.len() == 2
                    && sync["original_images_synchronized"] == false
                    && rows
                        .iter()
                        .filter(|r| {
                            r["before"] == captured_id
                                && r["after"] == captured_id
                                && r["fsync_completed"] == true
                        })
                        .count()
                        == 1,
                "working current preimage is not its actually synchronized backing",
            )?;
        } else {
            let rename = history.read_work_record(&evolution_pin, 32 * 1024 * 1024)?;
            let rename_intent: FilePin = serde_json::from_value(rename["intent"].clone())?;
            let intent = history.read_work_record(&rename_intent, 32 * 1024 * 1024)?;
            ensure(
                rename["schema"] == "droidloom.original-pair-restoration-result.v1"
                    && rename["working"] == current["current"]
                    && intent["schema"] == "droidloom.original-pair-restoration-intent.v1"
                    && intent["candidate_id"] == history.candidate()
                    && intent["pair_intent"] == serde_json::to_value(history.pair_pin())?,
                "working directory evolution lacks its normal completed pair rename",
            )?;
        }
    }
    if let Some(prior) = &row.recognized_history {
        ensure(
            same_pin(prior, &preimage)
                && actual["recognized_without_target_write"] == true
                && !row.target_write
                && row.current_before == row.restored,
            "recognized restoration has a foreign or changed current preimage",
        )?;
        // A previous attempt can have removed the label before its final
        // result was published. Only the original label is restored; all
        // unrelated attributes and this exact generation remain unchanged.
        let mut old_label = serde_json::to_value(&captured)?;
        old_label["attributes"] = target["before"]["attributes"].clone();
        let previous = snapshot_from(&old_label)?;
        labels::verify_data_snapshot(&previous, &row.current_before, false)?;
        ensure(
            if is_backing {
                stable(
                    labels::snapshot_identity(&previous),
                    labels::snapshot_identity(&row.current_before),
                )
            } else {
                labels::only_ctime_changed(
                    labels::snapshot_identity(&previous),
                    labels::snapshot_identity(&row.current_before),
                )
            },
            "recognized working restoration acquired unexplained metadata changes",
        )?;
    } else {
        ensure(
            same_pin(&retired_pin, history.retirement_pin()) && captured == row.current_before,
            "working restoration differs from its actual current preimage",
        )?;
    }
    Ok(())
}
fn verify_row(
    history: &mut ReturnedOnceHistory,
    logical: &Path,
    target: &Value,
    row: &RestoredRow,
) -> Result<()> {
    let before = snapshot_from(&target["before"])?;
    let before_id = labels::snapshot_identity(&before);
    ensure(
        row.ordinal == target["ordinal"].as_u64().ok_or("label target ordinal")? as u32
            && row.prelabel == before
            && stable(before_id, labels::snapshot_identity(&row.current_before))
            && stable(before_id, labels::snapshot_identity(&row.restored))
            && labels::only_ctime_changed(
                labels::snapshot_identity(&row.current_before),
                labels::snapshot_identity(&row.restored),
            ),
        "returned working metadata is not the same finite source inode",
    )?;
    labels::verify_data_snapshot(&before, &row.current_before, true)?;
    labels::verify_data_snapshot(&before, &row.restored, false)?;
    let source = row
        .original_preimage
        .as_ref()
        .ok_or("booted working label lacks its actual original preimage")?;
    let directory = history
        .work()
        .join("labels")
        .join(format!("inode-{:06}", row.ordinal));
    ensure(
        source.path == directory.join("PREIMAGE.json"),
        "working label preimage moved",
    )?;
    let original = history.read_work_record(source, 32 * 1024 * 1024)?;
    ensure(
        original["schema"] == "droidloom.original-label-preimage.v1"
            && original["candidate_id"] == history.candidate()
            && original["source_plan"] == serde_json::to_value(history.label_plan_pin())?
            && original["logical_path"] == serde_json::to_value(logical)?
            && original["before"] == target["before"]
            && original["desired"] == target["desired"]
            && original["attribute"] == "security.selinux"
            && original["ordinal"] == row.ordinal,
        "working label preimage is not from the exact complete source plan",
    )?;
    let restoration = row
        .restoration
        .as_ref()
        .ok_or("booted working inode lacks its actual label-restoration result")?;
    ensure(
        restoration.path.starts_with(&directory),
        "working restoration escaped its fixed inode records",
    )?;
    let actual = history.read_work_record(restoration, 32 * 1024 * 1024)?;
    let current = actual["schema"] == "droidloom.current-label-restored.v1";
    let strict = actual["schema"] == "droidloom.original-label-restored.v1";
    ensure(
        (current || strict)
            && actual[if current {
                "original_preimage"
            } else {
                "preimage"
            }] == serde_json::to_value(source)?
            && actual[if current {
                "before"
            } else {
                "observed_before_restore"
            }] == serde_json::to_value(&row.current_before)?
            && actual["after"] == serde_json::to_value(&row.restored)?
            && actual["target_metadata_durability"]["operation"] == "syncfs"
            && actual["target_metadata_durability"]["filesystem_dev"] == before_id.dev,
        "working restoration lacks the exact synchronized metadata transition",
    )?;
    if current {
        ensure(
            actual["retirement"] == serde_json::to_value(history.retirement_pin())?,
            "working label restoration used a different actual retirement",
        )?;
        verify_current_preimage(history, &directory, logical, target, row, source, &actual)?;
    }
    if let Some(prior) = &row.recognized_history {
        ensure(
            prior.path.starts_with(&directory)
                && actual["current_preimage"] == serde_json::to_value(prior)?
                && actual["recognized_without_target_write"] == true
                && !row.target_write
                && row.current_before == row.restored,
            "recognized label restoration has an unknown finite history",
        )?;
        let _ = history.read_work_record(prior, 32 * 1024 * 1024)?;
    } else if !row.target_write {
        ensure(
            row.current_before == row.restored,
            "a no-write label observation changed an inode",
        )?;
    }
    Ok(())
}
impl ReturnedWorkingPair {
    pub(crate) fn open(history: &mut ReturnedOnceHistory) -> Result<Self> {
        history.guard()?;
        let intent: Intent = serde_json::from_value(history.pair().clone())?;
        ensure(
            intent.schema == "droidloom.original-data-exchange-intent.v1"
                && intent.candidate_id == history.candidate()
                && intent.work == history.work()
                && intent.working_copy.sha256 == COPY_SHA
                && intent.cold_clone.sha256 == CLONE_SHA
                && intent
                    .original
                    .members
                    .keys()
                    .map(String::as_str)
                    .collect::<BTreeSet<_>>()
                    == IMAGES.into_iter().collect()
                && intent
                    .working
                    .members
                    .keys()
                    .map(String::as_str)
                    .collect::<BTreeSet<_>>()
                    == WORKING_MEMBERS.into_iter().collect(),
            "returned data intent lost its source-fixed pairs or lineage inputs",
        )?;
        let original = current_pair(ORIGINAL, &IMAGES)?;
        let working = current_pair(WORKING, &WORKING_MEMBERS)?;
        ensure(
            stable(&original.directory, &intent.original.directory)
                && stable(&working.directory, &intent.working.directory)
                && original.members == intent.original.members,
            "original pair or exact initial working directory identity changed",
        )?;
        let original_directory = snapshot_from(&history.pair_restoration()["original"])?;
        ensure(
            original.directory_label_identity == original_directory,
            "restored original directory no longer matches its actual reverse rename",
        )?;
        labels::verify_data_snapshot(
            &intent.original.directory_label_identity,
            &original_directory,
            false,
        )?;
        for name in WORKING_MEMBERS {
            ensure(
                stable(
                    &working.members[name].identity,
                    &intent.working.members[name].identity,
                ) && working.members[name].sha256 == intent.working.members[name].sha256,
                "returned working member identity or immutable proof body changed",
            )?;
        }
        let copy_body = root_pin(
            &FilePin {
                path: Path::new(WORKING).join("WORKING-COPY.json"),
                bytes: working.members["WORKING-COPY.json"].identity.size,
                sha256: working.members["WORKING-COPY.json"]
                    .sha256
                    .clone()
                    .ok_or("working lineage body absent")?,
            },
            1024 * 1024,
        )?;
        let clone_body = root_pin(&intent.cold_clone, 1024 * 1024)?;
        admitted_lineage(
            &serde_json::from_slice(&copy_body)?,
            &serde_json::from_slice(&clone_body)?,
            &intent.original,
            &intent.working,
        )?;
        let targets = history.label_plan()["targets"]
            .as_array()
            .ok_or("complete label targets absent")?;
        let rows = history.labels()["targets"]
            .as_array()
            .ok_or("complete restoration rows absent")?;
        ensure(
            targets.len() == rows.len() && !targets.is_empty(),
            "label target/restoration cardinality changed",
        )?;
        let expected: BTreeSet<PathBuf> = std::iter::once(PathBuf::from(ORIGINAL))
            .chain(WORKING_MEMBERS.iter().map(|n| Path::new(ORIGINAL).join(n)))
            .collect();
        let mut selected = Vec::new();
        let mut all_paths = BTreeSet::new();
        let mut pending_snapshot = None;
        for (index, (target, row_value)) in targets.iter().zip(rows).enumerate() {
            ensure(
                target["ordinal"] == index
                    && row_value["ordinal"] == index
                    && row_value["prelabel"] == target["before"],
                "complete restored label order or source changed",
            )?;
            let aliases = target["aliases"]
                .as_array()
                .ok_or("complete target aliases absent")?;
            ensure(!aliases.is_empty(), "label target has no source alias")?;
            for alias in aliases {
                let logical = PathBuf::from(
                    alias["logical"]
                        .as_str()
                        .ok_or("label logical path absent")?,
                );
                ensure(
                    all_paths.insert(logical.clone()),
                    "duplicate logical target in complete label source",
                )?;
                if alias["placement"] == "working_pair" {
                    ensure(
                        aliases.len() == 1
                            && expected.contains(&logical)
                            && alias["physical"] == serde_json::to_value(&logical)?,
                        "working label scope differs from the fixed directory and nine members",
                    )?;
                    ensure(
                        selected.len() < 10,
                        "working target count exceeded its fixed roster",
                    )?;
                    selected.push((logical, target.clone(), row_value.clone()));
                } else if alias["placement"] == "pending_selection" {
                    ensure(
                        logical == Path::new(SELECTED)
                            && aliases.len() == 1
                            && alias["physical"]
                                == serde_json::to_value(history.work().join(PENDING))?
                            && pending_snapshot.is_none(),
                        "pending selection source is not exact",
                    )?;
                    pending_snapshot = Some(snapshot_from(&row_value["restored"])?);
                } else {
                    ensure(
                        alias["placement"] == "root",
                        "unknown normal label target placement",
                    )?;
                }
            }
        }
        let mut observed = BTreeMap::new();
        for (logical, target, row_value) in selected {
            let row: RestoredRow = serde_json::from_value(row_value)?;
            verify_row(history, &logical, &target, &row)?;
            ensure(
                observed.insert(logical, row).is_none(),
                "working label target repeated",
            )?;
        }
        ensure(
            observed.keys().cloned().collect::<BTreeSet<_>>() == expected,
            "returned labels omitted a fixed working inode",
        )?;
        let restored_directory = &observed[Path::new(ORIGINAL)].restored;
        ensure(
            &working.directory_label_identity == restored_directory,
            "returned working directory differs from its actual final label snapshot",
        )?;
        for name in WORKING_MEMBERS {
            ensure(
                working.members[name].label_identity
                    == observed[&Path::new(ORIGINAL).join(name)].restored,
                "returned working member differs from its actual post-retirement label snapshot",
            )?;
        }
        let synchronization = &history.retirement()["working_data"]["actual_synchronization"];
        ensure(
            synchronization["schema"] == "droidloom.working-pair-recovery-fsync.v1"
                && synchronization["original_images_synchronized"] == false,
            "normal return did not record only working-image synchronization",
        )?;
        let sync_rows = synchronization["backings"]
            .as_array()
            .ok_or("normal working synchronization rows absent")?;
        ensure(
            sync_rows.len() == 2,
            "both actual working backings must have been synchronized",
        )?;
        let mut synchronized = BTreeSet::new();
        for row in sync_rows {
            let before: Identity = serde_json::from_value(row["before"].clone())?;
            let after: Identity = serde_json::from_value(row["after"].clone())?;
            ensure(
                before == after && row["fsync_completed"] == true,
                "historical working synchronization did not preserve the actual inode",
            )?;
            let names = IMAGES
                .iter()
                .filter(|name| inode(&after, &intent.working.members[**name].identity))
                .collect::<Vec<_>>();
            ensure(
                names.len() == 1
                    && synchronized.insert(*names[0])
                    && after
                        == *labels::snapshot_identity(
                            &observed[&Path::new(ORIGINAL).join(names[0])].current_before,
                        ),
                "normal fsync is not the exact working inode before label restoration",
            )?;
        }
        let tree = fs::Tree::open("/", 0)?;
        let work = tree.dir(&fs::absolute_string(history.work())?)?;
        ensure(
            named(&work, ROLLBACK)?.is_none(),
            "returned pair still has an unknown rollback placement",
        )?;
        let selection = current_public(Path::new(SELECTED))?;
        let pending = current_public(&history.work().join(PENDING))?
            .ok_or("restored candidate selection was not retained")?;
        ensure(
            matches_public(selection.as_ref(), intent.old_selection.as_ref())
                && matches_public(Some(&pending), Some(&intent.new_selection)),
            "actual original/candidate selection restoration differs",
        )?;
        let pending_file = hold_public(&history.work().join(PENDING), &pending)?;
        ensure(
            pending_file.snapshot
                == pending_snapshot
                    .ok_or("pending selection was omitted from label restoration")?,
            "retained candidate selection changed after label restoration",
        )?;
        let selection_file = selection
            .as_ref()
            .map(|p| hold_public(Path::new(SELECTED), p))
            .transpose()?;
        let mut parents = Vec::new();
        for path in [
            Path::new(ORIGINAL).parent().unwrap(),
            Path::new(WORKING).parent().unwrap(),
        ] {
            let file = tree.dir(&fs::absolute_string(path)?)?;
            parents.push((path.to_owned(), file.try_clone()?, labels::snapshot(&file)?));
        }
        let mut backings = Vec::new();
        for (path, pair) in [(ORIGINAL, &original), (WORKING, &working)] {
            let directory = tree.dir(path)?;
            for name in IMAGES {
                let file = open_at(&directory, name, false)?;
                let identity = fs::stat(&file)?;
                ensure(
                    identity == pair.members[name].identity,
                    "returned backing replaced before read-only lock",
                )?;
                rustix::fs::flock(&file, FlockOperation::NonBlockingLockExclusive)?;
                let snapshot = labels::data_snapshot(&file, &identity)?;
                backings.push(Backing {
                    path: Path::new(path).join(name),
                    file,
                    identity,
                    snapshot,
                });
            }
        }
        let references =
            reference_scan::require_no_other_references(&reference_targets(&original, &working))?;
        let value = Self {
            pid: std::process::id(),
            candidate: history.candidate().into(),
            pair_intent: history.pair_pin().clone(),
            original,
            working,
            parents,
            backings,
            selection,
            pending,
            selection_file,
            pending_file,
            references,
        };
        value.guard(history)?;
        Ok(value)
    }
    pub(crate) fn guard(&self, history: &ReturnedOnceHistory) -> Result<()> {
        history.guard()?;
        ensure(
            self.pid == std::process::id()
                && self.candidate == history.candidate()
                && same_pin(&self.pair_intent, history.pair_pin()),
            "returned copy observation changed owner or source",
        )?;
        let tree = fs::Tree::open("/", 0)?;
        for (path, held, before) in &self.parents {
            let named = tree.dir(&fs::absolute_string(path)?)?;
            ensure(
                labels::snapshot(held)? == *before && labels::snapshot(&named)? == *before,
                "returned copy parent was replaced or changed",
            )?;
        }
        for backing in &self.backings {
            rustix::fs::flock(&backing.file, FlockOperation::NonBlockingLockExclusive)?;
            guard_file(backing)?;
        }
        guard_file(&self.pending_file)?;
        if let Some(selection) = &self.selection_file {
            guard_file(selection)?;
        }
        ensure(
            current_pair(ORIGINAL, &IMAGES)? == self.original
                && current_pair(WORKING, &WORKING_MEMBERS)? == self.working
                && current_public(Path::new(SELECTED))? == self.selection
                && current_public(&history.work().join(PENDING))?.as_ref() == Some(&self.pending),
            "returned copy, proof members or selections changed during observation",
        )?;
        let _ = reference_scan::require_no_other_references(&reference_targets(
            &self.original,
            &self.working,
        ))?;
        history.guard()
    }
    pub(crate) fn summary(&self) -> Value {
        json!({"schema":"droidloom.returned-working-pair-observation.v1","candidate_id":self.candidate,
            "pair_intent":self.pair_intent,"original":self.original,"working":self.working,
            "actual_retirement_references":self.references,"held_image_count":self.backings.len(),
            "image_descriptors_read_only":true,"image_bodies_read":false,"image_bodies_written":false,
            "original_images_synchronized":false,"old_copy_or_clone_rewritten":false,
            "original_and_working_current_full_identity_checked":true,
            "source_ext4_generation_and_all_xattrs_checked":true,"qualification_boot_authorized":false,
            "account_business_accepted":false,"permanent_promotion_authorized":false})
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{
        io::Write,
        sync::atomic::{AtomicU64, Ordering},
    };

    static NEXT: AtomicU64 = AtomicU64::new(0);
    struct Temporary(PathBuf);
    impl Temporary {
        fn new() -> Self {
            let path = std::env::temp_dir().join(format!(
                "returned-custody-{}-{}",
                std::process::id(),
                NEXT.fetch_add(1, Ordering::Relaxed),
            ));
            std::fs::create_dir(&path).unwrap();
            Self(path)
        }
    }
    impl Drop for Temporary {
        fn drop(&mut self) {
            let _ = std::fs::remove_dir_all(&self.0);
        }
    }

    #[test]
    fn returned_successor_rejects_same_bytes_replaced_inode() {
        let temporary = Temporary::new();
        let path = temporary.0.join("observed");
        let replacement = temporary.0.join("replacement");
        std::fs::write(&path, b"fixed public test bytes").unwrap();
        let held = File::open(&path).unwrap();
        let identity = fs::stat(&held).unwrap();
        held_metadata(&held, &File::open(&path).unwrap(), &identity).unwrap();
        std::fs::write(&replacement, b"fixed public test bytes").unwrap();
        std::fs::rename(&replacement, &path).unwrap();
        assert!(held_metadata(&held, &File::open(&path).unwrap(), &identity).is_err());
    }

    #[test]
    fn returned_successor_rejects_write_after_read_only_observation() {
        let temporary = Temporary::new();
        let path = temporary.0.join("observed");
        std::fs::write(&path, b"fixed public test bytes").unwrap();
        let held = File::open(&path).unwrap();
        let identity = fs::stat(&held).unwrap();
        held_metadata(&held, &File::open(&path).unwrap(), &identity).unwrap();
        let mut writer = std::fs::OpenOptions::new()
            .append(true)
            .open(&path)
            .unwrap();
        writer.write_all(b"changed").unwrap();
        writer.sync_all().unwrap();
        assert!(held_metadata(&held, &File::open(&path).unwrap(), &identity).is_err());
    }
}
