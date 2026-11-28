//! Fresh original-kernel custody of both real data pairs after working boot.
//! Historical pins are comparison inputs. This factory freshly opens and locks
//! all four actual read-only backings, scans real references, hashes the original
//! pair without cache writeback, and synchronizes only the retired working pair.
use super::*;
use crate::cold_original_qualification::{WorkingBootRetirement, WorkingRecoverySources};
use sha2::{Digest, Sha256};
use std::{
    rc::Rc,
    time::{Duration, Instant},
};
#[path = "cold_working_retained_read.rs"]
mod original_read;
#[path = "cold_working_return_pair.rs"]
mod pair_restore;

struct HeldNode {
    logical: PathBuf,
    file: File,
    current: labels::Snapshot,
    image_index: Option<usize>,
    working: bool,
}
pub(crate) struct WorkingReturnData {
    sources: Rc<WorkingRecoverySources>,
    retirement: Rc<WorkingBootRetirement>,
    transaction: DataTransaction,
    nodes: Vec<HeldNode>,
    evidence: Value,
    report: FilePin,
    report_file: File,
    report_identity: Identity,
    restoration: Option<pair_restore::State>,
}
fn valid_working_intent(intent: &Intent, sources: &WorkingRecoverySources) -> Result<()> {
    ensure(
        intent.schema == "droidloom.working-data-exchange-intent.v1"
            && intent.candidate_id == sources.candidate()
            && intent.original_boot_id == sources.original_boot_id()
            && intent.work == sources.work()
            && same_pin(&intent.selection, sources.selection())
            && same_pin(&intent.cold_clone, sources.cold_clone())
            && intent.working_copy.sha256 == COPY_SHA
            && intent.cold_clone.sha256 == CLONE_SHA
            && intent.expected_cell.path == Path::new("/etc/droidloom/cell.json")
            && intent.expected_cell.bytes == sources.configuration().cell.bytes
            && intent.expected_cell.sha256 == sources.configuration().cell.sha256
            && intent
                .original
                .members
                .keys()
                .map(String::as_str)
                .eq(IMAGES)
            && intent
                .working
                .members
                .keys()
                .map(String::as_str)
                .eq(WORKING_MEMBERS)
            && !inode(&intent.original.directory, &intent.working.directory),
        "returned data input is outside the fixed actual working source closure",
    )?;
    let retained = sources.retained();
    for (entry, name) in retained.files.iter().zip(IMAGES) {
        let expected: labels::Snapshot =
            serde_json::from_value(serde_json::to_value(&entry.snapshot)?)?;
        ensure(
            entry.name == name && intent.original.members[name].label_identity == expected,
            "returned data intent does not preserve the exact admitted original image snapshot",
        )?;
    }
    for pair in [&intent.original, &intent.working] {
        labels::verify_snapshot_identity(&pair.directory_label_identity, &pair.directory)?;
        for member in pair.members.values() {
            labels::verify_snapshot_identity(&member.label_identity, &member.identity)?;
        }
    }
    let before = serde_json::to_value(&intent.original.directory_label_identity)?;
    let directory = serde_json::to_value(&retained.directory)?;
    ensure(
        before["handle"] == directory["handle"] && before["attributes"] == directory["attributes"],
        "returned original directory changed its admitted generation or xattrs",
    )?;
    for name in ["dev", "ino", "mode", "uid", "gid", "nlink", "size"] {
        ensure(
            before["identity"][name] == directory["identity"][name],
            "returned original directory differs from the retained exact stable identity",
        )?;
    }
    Ok(())
}

fn validate_copy_source(
    transaction: &DataTransaction,
    nodes: &[HeldNode],
    sources: &WorkingRecoverySources,
) -> Result<()> {
    let fixed = |name: &str, bytes: u64, sha: &str| -> Result<Value> {
        let rows = nodes
            .iter()
            .filter(|n| n.working && n.logical == Path::new(ORIGINAL).join(name))
            .collect::<Vec<_>>();
        ensure(
            rows.len() == 1,
            "one actual held immutable copy source is required",
        )?;
        let raw = read_small(&rows[0].file, 64 * 1024)?;
        ensure(
            raw.len() as u64 == bytes && fs::digest(&raw) == sha,
            "actual immutable working-copy source differs from its compiled whole-byte commitment",
        )?;
        Ok(serde_json::from_slice(&raw)?)
    };
    let copy = fixed("WORKING-COPY.json", 5217, COPY_SHA)?;
    let clone = fixed("COLD-CLONE-VERIFIED.json", 2843, CLONE_SHA)?;
    ensure(
        copy["schema"] == "p4-real-userdata-independent-working-copy-v1"
            && clone["schema"] == "pocket4-original-data-cold-compatibility-clone-v1"
            && copy["source_cold_clone_receipt"]["bytes"] == 2843
            && copy["source_cold_clone_receipt"]["sha256"] == CLONE_SHA,
        "held working-copy and cold-clone provenance disagree",
    )?;
    let images = copy["images"]
        .as_array()
        .ok_or("held working-copy lacks its image roster")?;
    let original = clone["rows"]
        .as_array()
        .ok_or("held cold clone lacks its original roster")?;
    ensure(
        images.len() == 2 && original.len() == 2,
        "exactly two immutable image source roles required",
    )?;
    let mut distinct = std::collections::BTreeSet::new();
    let device = fs::stat(&transaction.locations.work)?.dev;
    for (i, name) in IMAGES.iter().enumerate() {
        let old = &transaction.intent.original.members[*name].identity;
        let current = &transaction.intent.working.members[*name].identity;
        let row = &images[i];
        let prior = &original[i];
        ensure(
            old.dev == device
                && current.dev == device
                && distinct.insert((old.dev, old.ino))
                && distinct.insert((current.dev, current.ino))
                && prior["source_f9_before"] == as_f9(old)
                && prior["source_f9_after"] == as_f9(old)
                && prior["source_path"] == format!("{ORIGINAL}/{name}")
                && prior["role"] == if i == 0 { "data" } else { "metadata" }
                && prior["bytes"] == old.size
                && prior["sha256"] == sources.retained().files[i].sha256
                && row["name"] == *name
                && row["working_path"] == format!("{WORKING}/{name}")
                && row["source_path"] == prior["clone_path"]
                && row["source_f9_before"] == prior["clone_f9"]
                && row["source_f9_after"] == prior["clone_f9"]
                && row["sha256"] == prior["sha256"],
            "fresh working/source/cold-clone roles, original F9, hash or independence differ",
        )?;
        let comparison = copy_identity(current);
        for field in ["device", "inode", "mode", "uid", "gid", "nlink", "size"] {
            ensure(
                row["working_identity"][field] == comparison[field],
                "mutable working image lost its original independent stable identity",
            )?;
        }
        let name = if i == 0 {
            "data-COPY.json"
        } else {
            "metadata-COPY.json"
        };
        let receipts = nodes
            .iter()
            .filter(|n| n.working && n.logical == Path::new(ORIGINAL).join(name))
            .collect::<Vec<_>>();
        ensure(
            receipts.len() == 1
                && serde_json::from_slice::<Value>(&read_small(&receipts[0].file, 64 * 1024)?)?
                    == *row,
            "actual individual working-copy receipt differs from its immutable full source",
        )?;
    }
    let stable7 = |n: &Identity| {
        [
            n.dev,
            n.ino,
            u64::from(n.mode),
            u64::from(n.uid),
            u64::from(n.gid),
            n.nlink,
            n.size,
        ]
    };
    crate::cold_original_once_recovery::contract::OriginalCopyPolicy::bind_cold_pairs(
        IMAGES.map(|n| stable7(&transaction.intent.original.members[n].identity)),
        IMAGES.map(|n| stable7(&transaction.intent.working.members[n].identity)),
    )?;
    Ok(())
}

fn selection_nodes(transaction: &DataTransaction) -> Result<(Vec<HeldNode>, Value)> {
    let state = transaction.selection_state()?;
    let (parent, name) = if state == SelectionState::Candidate {
        (
            &transaction.locations.selected_parent,
            transaction.locations.selected_name.as_str(),
        )
    } else {
        (&transaction.locations.work, PENDING)
    };
    let file = open_at(parent, name, false)?;
    let current = labels::data_snapshot(&file, &fs::stat(&file)?)?;
    let candidate_id = fs::stat(&file)?;
    ensure(
        stable(&candidate_id, &transaction.intent.new_selection.identity)
            && fs::digest(&read_small(&file, 16 * 1024)?)
                == transaction.intent.new_selection.sha256,
        "returned selected candidate lost its actual owned immutable inode",
    )?;
    let directory = transaction.locations.selected_parent.try_clone()?;
    let directory_snapshot = labels::data_snapshot(&directory, &fs::stat(&directory)?)?;
    let report = json!({"state":format!("{state:?}"),"candidate_snapshot":current,
        "parent_snapshot":directory_snapshot,"parent_members":list(&directory)?,
        "candidate_source":transaction.intent.selection,
        "initial_candidate":transaction.intent.new_selection,
        "initial_original":transaction.intent.old_selection,
        "current_public":transaction.locations.public_file(&transaction.locations.selected_parent,
            &transaction.locations.selected_name)?,
        "current_pending":transaction.locations.public_file(&transaction.locations.work,PENDING)?});
    Ok((
        vec![
            HeldNode {
                logical: PathBuf::from(SELECTED),
                file,
                current,
                image_index: None,
                working: true,
            },
            HeldNode {
                logical: Path::new(SELECTED).parent().unwrap().to_owned(),
                file: directory,
                current: directory_snapshot,
                image_index: None,
                working: true,
            },
        ],
        report,
    ))
}
fn current_named_members(transaction: &DataTransaction, nodes: &[HeldNode]) -> Result<()> {
    let (layout, selection) = transaction.observe(true)?;
    let (original, working) = transaction.current_pairs(layout)?;
    for node in nodes {
        let actual = fs::stat(&node.file)?;
        let expected = if node.logical == Path::new(SELECTED) {
            let (parent, name) = if selection == SelectionState::Candidate {
                (
                    &transaction.locations.selected_parent,
                    transaction.locations.selected_name.as_str(),
                )
            } else {
                (&transaction.locations.work, PENDING)
            };
            named(parent, name)?.ok_or("held candidate selection has no current owned name")?
        } else if node.logical == Path::new(SELECTED).parent().unwrap() {
            fs::stat(&transaction.locations.selected_parent)?
        } else {
            let retained = transaction.intent.work.join(ROLLBACK);
            let (root, record) = if node.working {
                (Path::new(ORIGINAL), &working)
            } else {
                (retained.as_path(), &original)
            };
            // Original retained names may move back to ORIGINAL; the record
            // above was obtained from the actual current source-bound layout.
            if node.logical == root {
                record.directory.clone()
            } else {
                let name = node
                    .logical
                    .file_name()
                    .and_then(|s| s.to_str())
                    .ok_or("returned member name")?;
                record
                    .members
                    .get(name)
                    .ok_or("held pair member outside exact source roster")?
                    .identity
                    .clone()
            }
        };
        ensure(
            actual == expected,
            "returned held data/selection object differs from its actual source-bound name",
        )?;
    }
    Ok(())
}

fn held_guard(transaction: &DataTransaction, nodes: &[HeldNode]) -> Result<()> {
    transaction.validate_intent_custody()?;
    ensure(
        transaction.images.len() == 4
            && nodes.iter().filter(|n| n.image_index.is_some()).count() == 4,
        "fresh returned data lost one of its four actual backing OFDs",
    )?;
    for node in nodes {
        ensure(
            labels::data_snapshot(&node.file, &fs::stat(&node.file)?)? == node.current,
            "returned pair held inode changed outside its exact owned operation",
        )?;
    }
    for (file, identity, _) in &transaction.images {
        ensure(
            fs::stat(file)? == *identity,
            "returned backing changed its exact fresh checkpoint",
        )?;
    }
    Ok(())
}
fn hash_originals(
    transaction: &DataTransaction,
    nodes: &[HeldNode],
    sources: &WorkingRecoverySources,
) -> Result<Vec<Value>> {
    let end = Instant::now()
        + Duration::from_secs(crate::cold_original_qualification::RETAINED_ORIGINAL_HASH_SECONDS);
    let mut result = Vec::new();
    let mut buffer = vec![0_u8; 1024 * 1024];
    for ((file, identity, working), expected) in transaction
        .images
        .iter()
        .take(2)
        .zip(&sources.retained().files)
    {
        ensure(
            !working && identity.size == expected.snapshot.identity.size,
            "original hash loop cannot read a mutable or differently sized role",
        )?;
        let mut digest = Sha256::new();
        let mut offset = 0;
        while offset < identity.size {
            let count = usize::try_from((identity.size - offset).min(buffer.len() as u64))?;
            original_read::read_exact_at(file, &mut buffer[..count], offset, end, &mut || {
                held_guard(transaction, nodes).map_err(|e| std::io::Error::other(e.to_string()))
            })?;
            digest.update(&buffer[..count]);
            offset += count as u64;
        }
        ensure(
            Instant::now() < end && file.read_at(&mut [0], identity.size)? == 0,
            "original image hash exceeded the unchanged pair budget or has a tail",
        )?;
        let sha256 = hex::encode(digest.finalize());
        ensure(
            sha256 == expected.sha256,
            "actual returned original image whole SHA256 differs",
        )?;
        held_guard(transaction, nodes)?;
        result.push(
            json!({"name":expected.name,"bytes":identity.size,"sha256":sha256,
            "actual_identity":identity,"no_cache_read":true,"read_only_descriptor":true,
            "original_writeback_requested":false}),
        );
    }
    ensure(
        result.len() == 2,
        "both real original image hashes are required",
    )?;
    Ok(result)
}
fn private_attempt(sources: &WorkingRecoverySources) -> Result<PathBuf> {
    let tree = fs::Tree::open(&fs::absolute_string(sources.work())?, 0)?;
    let base = format!("working-return-data-{}", sources.owner().boot_id());
    for index in 0..32 {
        let name = format!("{base}-{index:02}");
        match rustix::fs::mkdirat(&tree.root, name.as_str(), Mode::from_raw_mode(0o700)) {
            Ok(()) => {
                tree.root.sync_all()?;
                return Ok(sources.work().join(name));
            }
            Err(rustix::io::Errno::EXIST) => continue,
            Err(e) => return Err(e.into()),
        }
    }
    Err("returned data capture exhausted its fixed fresh-attempt bound".into())
}
impl WorkingReturnData {
    pub(crate) fn capture(
        sources: Rc<WorkingRecoverySources>,
        retirement: Rc<WorkingBootRetirement>,
    ) -> Result<Self> {
        sources.revalidate()?;
        retirement.require_owner(sources.owner())?;
        ensure(
            same_pin(
                retirement.normal_sources().source_pin(),
                sources.normal_sources().source_pin(),
            ),
            "returned data and actual boot retirement have different normal source custody",
        )?;
        let locations = Locations::physical(sources.work())?;
        let intent_file = open_at(&locations.work, INTENT, false)?;
        let intent_identity = fs::stat(&intent_file)?;
        ensure(
            intent_identity.mode == 0o100400
                && intent_identity.uid == 0
                && intent_identity.gid == 0
                && intent_identity.nlink == 1
                && intent_identity.size == sources.data_intent().bytes,
            "returned data intent is not the actual preserved protected root record",
        )?;
        let raw = read_small(&intent_file, 128 * 1024)?;
        ensure(
            fs::digest(&raw) == sources.data_intent().sha256,
            "returned data intent lost its complete admitted source bytes",
        )?;
        let wrapper: Value = serde_json::from_slice(&raw)?;
        ensure(
            wrapper["schema"] == "droidloom.working-qualification-data-intent.v1"
                && wrapper["first_once_candidate"] == sources.first_once()
                && wrapper["boot_intent"] == serde_json::to_value(sources.boot_intent())?
                && wrapper["normal_return_configuration"]
                    == serde_json::to_value(sources.configuration())?,
            "returned data wrapper belongs to another actual boot contract",
        )?;
        let intent: Intent = serde_json::from_value(wrapper["data"].clone())?;
        valid_working_intent(&intent, &sources)?;
        let mut transaction = DataTransaction {
            locations,
            intent,
            intent_pin: sources.data_intent().clone(),
            intent_file,
            intent_identity,
            images: Vec::new(),
        };
        let layout = transaction.layout(true)?;
        let original_place = if layout == Layout::Switched {
            Place::Rollback
        } else {
            Place::Original
        };
        let working_place = match layout {
            Layout::Ready => Place::Working,
            Layout::Staged => Place::Rollback,
            Layout::Switched => Place::Original,
        };
        let mut nodes = Vec::new();
        for (place, working) in [(original_place, false), (working_place, true)] {
            let record = if working {
                &transaction.intent.working
            } else {
                &transaction.intent.original
            };
            let (parent, name) = transaction.locations.at(place);
            let directory = open_at(parent, name, true)?;
            let current = labels::data_snapshot(&directory, &fs::stat(&directory)?)?;
            labels::verify_data_snapshot(&record.directory_label_identity, &current, working)?;
            let logical = if working {
                PathBuf::from(ORIGINAL)
            } else {
                sources.retained().directory.path.clone()
            };
            nodes.push(HeldNode {
                logical: logical.clone(),
                file: directory.try_clone()?,
                current,
                image_index: None,
                working,
            });
            for (name, member) in &record.members {
                let file = open_at(&directory, name, false)?;
                let identity = fs::stat(&file)?;
                ensure(
                    if working {
                        if image(name) {
                            stable(&identity, &member.identity)
                        } else {
                            labels::only_ctime_changed(&member.identity, &identity)
                        }
                    } else {
                        identity == member.identity
                    },
                    "returned pair member changed its immutable or mutable-role identity",
                )?;
                let current = labels::data_snapshot(&file, &identity)?;
                labels::verify_data_snapshot(&member.label_identity, &current, working)?;
                let image_index = if image(name) {
                    rustix::fs::flock(&file, FlockOperation::NonBlockingLockExclusive)?;
                    let index = transaction.images.len();
                    transaction
                        .images
                        .push((file.try_clone()?, identity.clone(), working));
                    Some(index)
                } else {
                    None
                };
                nodes.push(HeldNode {
                    logical: logical.join(name),
                    file,
                    current,
                    image_index,
                    working,
                });
            }
        }
        let (selected_nodes, selected_evidence) = selection_nodes(&transaction)?;
        nodes.extend(selected_nodes);
        transaction.require_writer_locks()?;
        validate_copy_source(&transaction, &nodes, &sources)?;
        current_named_members(&transaction, &nodes)?;
        held_guard(&transaction, &nodes)?;
        let (original, working) = transaction.current_pairs(layout)?;
        let scan_before =
            reference_scan::require_no_other_references(&reference_targets(&original, &working))?;
        sources.revalidate_custody()?;
        retirement.revalidate()?;
        held_guard(&transaction, &nodes)?;
        let original_hashes = hash_originals(&transaction, &nodes, &sources)?;
        let mut working_synchronization = Vec::new();
        for (file, _, working) in &transaction.images {
            if *working {
                let before = labels::data_snapshot(file, &fs::stat(file)?)?;
                file.sync_all()?;
                let after = labels::data_snapshot(file, &fs::stat(file)?)?;
                ensure(
                    before == after,
                    "working backing changed while its actual retired data was synchronized",
                )?;
                working_synchronization
                    .push(json!({"before":before,"after":after,"operation":"fsync"}));
            }
        }
        ensure(
            working_synchronization.len() == 2,
            "both actual working OFDs must be synchronized",
        )?;
        held_guard(&transaction, &nodes)?;
        let (after_original, after_working) = transaction.current_pairs(layout)?;
        let scan_after = reference_scan::require_no_other_references(&reference_targets(
            &after_original,
            &after_working,
        ))?;
        ensure(
            original == after_original && working == after_working,
            "returned pair changed across locks, full original hashes and working synchronization",
        )?;
        sources.revalidate_custody()?;
        retirement.revalidate()?;
        held_guard(&transaction, &nodes)?;
        let attempt = private_attempt(&sources)?;
        let evidence = json!({"schema":"droidloom.working-returned-data-custody.v1",
            "candidate_id":sources.candidate(),"actual_original_boot_id":sources.owner().boot_id(),
            "source_input":sources.owner().input_pin(),"boot_retirement":retirement.report_pin(),
            "normal_sources":sources.normal_sources().source_pin(),"boot_intent":sources.boot_intent(),
            "normal_return_observed":retirement.normal_return_observed(),"pair_intent":sources.data_intent(),
            "layout":format!("{layout:?}"),"original":original,"working":working,"selection":selected_evidence,
            "reference_scan_before":scan_before,"reference_scan_after":scan_after,
            "original_complete_hashes":original_hashes,
            "actual_four_readonly_backing_locks_owned":true,"working_backings_synchronized":true,
            "working_synchronization":working_synchronization,
            "original_backings_synchronized":false,"original_backings_written":false,
            "original_data_restored":false,"production_ready":false});
        let path = attempt.join("DATA-RETIRED.json");
        let raw = serde_json::to_vec(&evidence)?;
        crate::boot_files::write_new(&path, &raw, 0o400)?;
        File::open(&attempt)?.sync_all()?;
        let report = crate::boot_files::pin_file(&path)?;
        let (report_file, report_identity) = crate::boot_files::open_pin(&report)?;
        let value = Self {
            sources,
            retirement,
            transaction,
            nodes,
            evidence,
            report,
            report_file,
            report_identity,
            restoration: None,
        };
        value.revalidate()?;
        Ok(value)
    }
    pub(crate) fn revalidate(&self) -> Result<()> {
        self.revalidate_custody()?;
        let layout = self.transaction.layout(true)?;
        let (original, working) = self.transaction.current_pairs(layout)?;
        reference_scan::require_no_other_references(&reference_targets(&original, &working))?;
        self.revalidate_custody()
    }
    /// Every target mutation also holds the actual fresh freezer. Rechecking
    /// that window and all four retained OFDs is the per-inode fence; the
    /// complete bounded process/reference scans bookend the entire operation.
    pub(crate) fn revalidate_custody(&self) -> Result<()> {
        self.sources.revalidate_custody()?;
        self.retirement.require_owner(self.sources.owner())?;
        held_guard(&self.transaction, &self.nodes)?;
        current_named_members(&self.transaction, &self.nodes)?;
        ensure(
            fs::stat(&self.report_file)? == self.report_identity
                && fs::Tree::open("/", 0)?.identity(&fs::absolute_string(&self.report.path)?)?
                    == self.report_identity,
            "returned data evidence was replaced",
        )?;
        held_guard(&self.transaction, &self.nodes)
    }
    pub(in crate::cold_original_data) fn candidate_is_selected(&self) -> Result<bool> {
        self.revalidate_custody()?;
        Ok(self.transaction.selection_state()? == SelectionState::Candidate)
    }
    pub(crate) fn require_sources(&self, sources: &Rc<WorkingRecoverySources>) -> Result<()> {
        ensure(
            Rc::ptr_eq(&self.sources, sources),
            "returned data belongs to a different actual fresh source factory",
        )?;
        self.revalidate()
    }
    pub(crate) fn sources(&self) -> &Rc<WorkingRecoverySources> {
        &self.sources
    }
    pub(crate) fn retirement(&self) -> &Rc<WorkingBootRetirement> {
        &self.retirement
    }
    pub(crate) fn report(&self) -> &FilePin {
        &self.report
    }
    pub(crate) fn evidence(&self) -> &Value {
        &self.evidence
    }
    pub(crate) fn begin_restoration(
        &mut self,
        labels: labels::WorkingReturnedLabels,
        window: &crate::cold_original_qualification::WorkingReturnQuiescence,
    ) -> Result<()> {
        let history = labels::WorkingReturnedLabelHistory::seal(&labels, self, window)?;
        pair_restore::begin(self, history, window)
    }
    pub(crate) fn resume_restoration(
        &mut self,
        history: labels::WorkingReturnedLabelHistory,
        window: &crate::cold_original_qualification::WorkingReturnQuiescence,
    ) -> Result<()> {
        history.require_data(self, window)?;
        pair_restore::begin(self, history, window)
    }
    pub(crate) fn returned_label_history(&self) -> Result<&labels::WorkingReturnedLabelHistory> {
        Ok(&self.restoration.as_ref()
            .ok_or("returned data has no completed label comparison source")?.labels)
    }
    pub(crate) fn restore_original_pair(
        &mut self,
        window: &crate::cold_original_qualification::WorkingReturnQuiescence,
    ) -> Result<FilePin> {
        pair_restore::restore(self, window)
    }
    pub(crate) fn verify_original_restored(&self) -> Result<()> {
        pair_restore::verify(self)
    }
    pub(crate) fn restored_label_metadata(
        &self,
        paths: &std::collections::BTreeSet<PathBuf>,
    ) -> Result<Value> {
        self.restoration
            .as_ref()
            .ok_or("returned data has no actual completed label custody")?
            .labels
            .preserved_metadata(paths)
    }
    pub(crate) fn restored_label_report(&self) -> Result<&FilePin> {
        Ok(self
            .restoration
            .as_ref()
            .ok_or("returned data has no actual completed label custody")?
            .labels
            .report())
    }
    pub(crate) fn label_sensitive_paths(&self) -> std::collections::BTreeSet<PathBuf> {
        self.nodes
            .iter()
            .filter(|n| n.working)
            .map(|n| n.logical.clone())
            .collect()
    }
    pub(crate) fn accept_label_restoration(
        &mut self,
        proof: &labels::WorkingReturnedLabelRestoration,
    ) -> Result<()> {
        proof.require_owner(self.sources.owner().as_ref())?;
        for node in &mut self.nodes {
            if proof.paths().iter().any(|p| p == &node.logical) {
                ensure(
                    node.working,
                    "original image retention forbids relabeling the retained original pair",
                )?;
                let before = fs::stat(&node.file)?;
                let known = serde_json::to_value(&node.current)?;
                let expected: Identity = serde_json::from_value(known["identity"].clone())?;
                let after = proof.require_held_transition(&node.logical, &node.file, &expected)?;
                ensure(
                    after == before,
                    "returned data proof changed during adoption",
                )?;
                node.current = labels::data_snapshot(&node.file, &after)?;
                if let Some(index) = node.image_index {
                    self.transaction.images[index].1 = after;
                }
            }
        }
        held_guard(&self.transaction, &self.nodes)
    }
    pub(in crate::cold_original_data) fn held_working_label_targets(
        &self,
    ) -> Result<Vec<(PathBuf, File, labels::Snapshot)>> {
        self.revalidate()?;
        self.nodes
            .iter()
            .filter(|n| {
                n.working && (n.logical.starts_with(ORIGINAL) || n.logical == Path::new(SELECTED))
            })
            .map(|n| Ok((n.logical.clone(), n.file.try_clone()?, n.current.clone())))
            .collect()
    }
}
