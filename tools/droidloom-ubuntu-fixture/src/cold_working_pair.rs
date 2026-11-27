//! H2 directory exchange from the still-held Returned observation.
//! The four image OFDs are duplicated with dup, never dropped and reopened.
//! This module cannot publish selected.json, relabel a backing, or arm GRUB.
use super::*;
use crate::cold_original_qualification::PublishedWorkingRuntime;
#[path = "cold_working_pair_labels.rs"]
mod label_custody;
use label_custody::PairLabelState;

type ImageOfds = Vec<(File, Identity, bool)>;

fn duplicate_image_ofds(rows: [(&File, &Identity, bool); 4]) -> Result<ImageOfds> {
    let mut seen = std::collections::BTreeSet::new();
    let mut images = Vec::new();
    ensure(
        rows.iter().map(|r| r.2).eq([false, false, true, true]),
        "working image OFD roles are not the two actual ordered pairs",
    )?;
    for (file, expected, working) in rows {
        ensure(
            fs::stat(file)? == *expected
                && seen.insert((expected.dev, expected.ino))
                && rustix::fs::fcntl_getfl(file)? & OFlags::ACCMODE == OFlags::RDONLY,
            "working OFD projection changed a complete identity or aliases a role",
        )?;
        rustix::fs::flock(file, FlockOperation::NonBlockingLockExclusive)?;
        // try_clone duplicates this exact open-file-description. A fresh open
        // here would compete with the locks held by the Returned observation.
        let duplicate = file.try_clone()?;
        ensure(
            fs::stat(&duplicate)? == *expected && fs::stat(file)? == *expected,
            "working OFD changed while its actual description was duplicated",
        )?;
        rustix::fs::flock(&duplicate, FlockOperation::NonBlockingLockExclusive)?;
        images.push((duplicate, expected.clone(), working));
    }
    Ok(images)
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Step {
    Stage,
    Exchange,
    Unexchange,
    Return,
}
impl Step {
    fn states(self) -> (Layout, Layout) {
        match self {
            Self::Stage => (Layout::Ready, Layout::Staged),
            Self::Exchange => (Layout::Staged, Layout::Switched),
            Self::Unexchange => (Layout::Switched, Layout::Staged),
            Self::Return => (Layout::Staged, Layout::Ready),
        }
    }
    fn working_links(self) -> i64 {
        match self {
            Self::Stage => 1,
            Self::Return => -1,
            _ => 0,
        }
    }
}

enum EntryChange<'a> {
    None,
    Remove(&'a str),
    Add(&'a str, &'a Identity),
    Replace(&'a str, &'a Identity),
}

fn link_delta(old: u64, delta: i64) -> Option<u64> {
    u64::try_from(i128::from(old) + i128::from(delta)).ok()
}

// A private comparison helper. Only the four source-owned Step variants below
// can select its exception names; no external path/permission callback exists.
fn verify_inventory_transition(
    before: &DirectoryInventory,
    directory: &File,
    change: EntryChange<'_>,
    owned_work: Option<(&str, i64)>,
) -> Result<()> {
    let start = fs::stat(directory)?;
    let mut expected = before
        .members
        .iter()
        .map(|m| m.name.clone())
        .collect::<Vec<_>>();
    let changed = match &change {
        EntryChange::None => None,
        EntryChange::Remove(name) => {
            ensure(
                expected.iter().filter(|n| n.as_str() == *name).count() == 1,
                "removed member was not unique",
            )?;
            expected.retain(|n| n != name);
            Some(*name)
        }
        EntryChange::Add(name, _) => {
            ensure(
                !expected.iter().any(|n| n == name),
                "new member already existed",
            )?;
            expected.push((*name).to_owned());
            Some(*name)
        }
        EntryChange::Replace(name, _) => {
            ensure(
                expected.iter().filter(|n| n.as_str() == *name).count() == 1,
                "exchanged member was not unique",
            )?;
            Some(*name)
        }
    };
    if let Some((work, _)) = owned_work {
        ensure(
            changed != Some(work),
            "owned work and moved member roles alias",
        )?;
    }
    expected.sort();
    ensure(
        names(directory)? == expected,
        "working exchange changed another parent member name",
    )?;
    for member in &before.members {
        if changed == Some(member.name.as_str()) {
            continue;
        }
        let actual = named(directory, &member.name)?.ok_or("retained parent member disappeared")?;
        let held = fs::stat(&member.file)?;
        if let Some((name, delta)) = owned_work.filter(|(name, _)| *name == member.name) {
            let _ = name;
            ensure(
                actual == held
                    && same_directory_inode(&member.identity, &actual)
                    && link_delta(member.identity.nlink, delta) == Some(actual.nlink),
                "owned private workspace changed more than this directory exchange",
            )?;
        } else {
            ensure(
                actual == member.identity && held == member.identity,
                "an unrelated parent member changed during exchange",
            )?;
        }
    }
    match change {
        EntryChange::None => (),
        EntryChange::Remove(name) => ensure(
            named(directory, name)?.is_none(),
            "moved source remained present",
        )?,
        EntryChange::Add(name, expected) | EntryChange::Replace(name, expected) => {
            let actual = named(directory, name)?.ok_or("moved directory disappeared")?;
            ensure(
                FileType::from_raw_mode(actual.mode) == FileType::Directory
                    && labels::only_ctime_changed(expected, &actual),
                "moved directory is not its source-owned inode and complete non-ctime metadata",
            )?;
        }
    }
    ensure(
        fs::stat(directory)? == start,
        "parent changed across exchange inventory readback",
    )
}

struct PendingStep {
    step: Step,
    parents: Vec<labels::Snapshot>,
    inventories: Vec<DirectoryInventory>,
}
impl PendingStep {
    fn capture(step: Step, prepared: &PreparedReturnedPair, tx: &DataTransaction) -> Result<Self> {
        let parents = prepared
            .pair
            .parents
            .iter()
            .map(|(_, file, _)| labels::snapshot(file))
            .collect::<Result<Vec<_>>>()?;
        let inventories = [
            &tx.locations.original_parent,
            &tx.locations.working_parent,
            &tx.locations.work,
        ]
        .into_iter()
        .map(DirectoryInventory::capture)
        .collect::<Result<Vec<_>>>()?;
        Ok(Self {
            step,
            parents,
            inventories,
        })
    }
    fn verify(
        &self,
        prepared: &PreparedReturnedPair,
        tx: &DataTransaction,
        layout: Layout,
    ) -> Result<Vec<labels::Snapshot>> {
        let (before, after) = self.step.states();
        ensure(
            layout == before || layout == after,
            "interrupted working exchange left both allowed atomic layouts",
        )?;
        let current = prepared
            .pair
            .parents
            .iter()
            .map(|(path, held, _)| {
                let snap = labels::snapshot(held)?;
                let named = fs::Tree::open("/", 0)?.dir(&fs::absolute_string(path)?)?;
                ensure(
                    labels::snapshot(&named)? == snap,
                    "working parent pathname left its held inode",
                )?;
                Ok(snap)
            })
            .collect::<Result<Vec<_>>>()?;
        ensure(
            current.len() == 2 && self.parents.len() == 2 && self.inventories.len() == 3,
            "working parent witness roster differs",
        )?;
        if layout == before {
            ensure(current == self.parents, "unapplied exchange parent changed")?;
            for (inventory, file) in self.inventories.iter().zip([
                &tx.locations.original_parent,
                &tx.locations.working_parent,
                &tx.locations.work,
            ]) {
                inventory.verify(file, &[])?;
            }
            return Ok(current);
        }
        let work_name = prepared
            .work
            .path
            .file_name()
            .and_then(|v| v.to_str())
            .ok_or("fixed work basename")?;
        let work_links = self.step.working_links();
        for (index, (old, new)) in self.parents.iter().zip(&current).enumerate() {
            let changes = match self.step {
                Step::Stage | Step::Return => index == 1,
                Step::Exchange | Step::Unexchange => index == 0,
            };
            if !changes {
                ensure(old == new, "an unchanged exchange parent changed metadata")?;
            } else {
                let a = labels::snapshot_identity(old);
                let b = labels::snapshot_identity(new);
                let delta = if index == 1 { -work_links } else { 0 };
                ensure(
                    same_directory_inode(a, b) && link_delta(a.nlink, delta) == Some(b.nlink),
                    "exchange changed parent authority or an additional directory",
                )?;
                labels::verify_data_snapshot(old, new, false)?;
            }
        }
        let (old_change, new_change, work_change) = match self.step {
            Step::Stage => (
                EntryChange::None,
                EntryChange::Remove(&tx.locations.working_name),
                EntryChange::Add(ROLLBACK, &tx.intent.working.directory),
            ),
            Step::Exchange => (
                EntryChange::Replace(&tx.locations.original_name, &tx.intent.working.directory),
                EntryChange::None,
                EntryChange::Replace(ROLLBACK, &tx.intent.original.directory),
            ),
            Step::Unexchange => (
                EntryChange::Replace(&tx.locations.original_name, &tx.intent.original.directory),
                EntryChange::None,
                EntryChange::Replace(ROLLBACK, &tx.intent.working.directory),
            ),
            Step::Return => (
                EntryChange::None,
                EntryChange::Add(&tx.locations.working_name, &tx.intent.working.directory),
                EntryChange::Remove(ROLLBACK),
            ),
        };
        verify_inventory_transition(
            &self.inventories[0],
            &tx.locations.original_parent,
            old_change,
            None,
        )?;
        verify_inventory_transition(
            &self.inventories[1],
            &tx.locations.working_parent,
            new_change,
            Some((work_name, work_links)),
        )?;
        verify_inventory_transition(&self.inventories[2], &tx.locations.work, work_change, None)?;
        prepared.work.guard()?;
        Ok(current)
    }
}

/// A new H2 transaction. No deserializer/Clone/reopen constructor exists.
/// The historical observer remains alive in WorkingColdCustody throughout it.
pub(crate) struct WorkingPairTransaction {
    tx: DataTransaction,
    first_once: String,
    prior_intent: FilePin,
    work_identity: Identity,
    parents: Vec<labels::Snapshot>,
    in_flight: Option<PendingStep>,
    pending_file: File,
    labelled: Option<PairLabelState>,
    label_source: crate::cold_original_qualification::WorkingLabelSourceIdentity,
}
impl WorkingPairTransaction {
    pub(crate) fn prepare(
        prepared: &PreparedReturnedPair,
        history: &ReturnedOnceHistory,
        published: &PublishedWorkingRuntime,
    ) -> Result<Self> {
        published.guard()?;
        prepared.guard(history)?;
        let source = published.source();
        ensure(
            source.work() == prepared.work.path
                && source.configuration().first_once_candidate == history.candidate()
                && source.candidate() != history.candidate()
                && prepared.work.path.file_name().and_then(|s| s.to_str())
                    == Some(&format!("working-qualification-{}", source.candidate())),
            "working pair factory changed the actual owner workspace or candidate",
        )?;
        ensure(
            prepared.pair.backings.len() == 4,
            "all four original image OFDs must remain held",
        )?;
        for (index, backing) in prepared.pair.backings.iter().enumerate() {
            let base = if index < 2 { ORIGINAL } else { WORKING };
            let record = if index < 2 {
                &prepared.pair.original
            } else {
                &prepared.pair.working
            };
            ensure(
                backing.path == Path::new(base).join(IMAGES[index % 2])
                    && backing.identity == record.members[IMAGES[index % 2]].identity
                    && labels::data_snapshot(&backing.file, &backing.identity)? == backing.snapshot,
                "inherited working backing role, generation or attributes differ",
            )?;
        }
        let b = &prepared.pair.backings;
        let images = duplicate_image_ofds([
            (&b[0].file, &b[0].identity, false),
            (&b[1].file, &b[1].identity, false),
            (&b[2].file, &b[2].identity, true),
            (&b[3].file, &b[3].identity, true),
        ])?;
        let locations = Locations::physical(source.work())?;
        ensure(
            fs::stat(&locations.work)? == fs::stat(&prepared.work.file)?,
            "pair work is not the held preparation directory",
        )?;
        for name in [INTENT, PENDING, ROLLBACK, COMMITTED, RESTORED] {
            ensure(
                named(&locations.work, name)?.is_none(),
                "new H2 pair journal must be create-only",
            )?;
        }
        let selection = source.selection_source()?;
        let cell = FilePin {
            path: "/etc/droidloom/cell.json".into(),
            bytes: source.configuration().cell.bytes,
            sha256: source.configuration().cell.sha256.clone(),
        };
        let bytes = selection_input(&cell, &selection)?;
        let old_selection =
            locations.public_file(&locations.selected_parent, &locations.selected_name)?;
        ensure(
            old_selection == prepared.pair.selection,
            "old selected inode changed after its Returned observation",
        )?;
        let mut pending = File::from(rustix::fs::openat(
            &locations.work,
            PENDING,
            OFlags::RDWR | OFlags::CREATE | OFlags::EXCL | OFlags::NOFOLLOW | OFlags::CLOEXEC,
            Mode::from_raw_mode(0o444),
        )?);
        pending.write_all(&bytes)?;
        rustix::fs::fchmod(&pending, Mode::from_raw_mode(0o444))?;
        pending.sync_all()?;
        locations.work.sync_all()?;
        let new_selection = locations
            .public_file(&locations.work, PENDING)?
            .ok_or("new private selection disappeared")?;
        ensure(
            new_selection.identity == fs::stat(&pending)?
                && new_selection.sha256 == selection.sha256
                && new_selection.identity.size == selection.bytes,
            "private working selection differs from the normal source",
        )?;
        let pending_file = open_at(&locations.work, PENDING, false)?;
        ensure(
            fs::stat(&pending_file)? == fs::stat(&pending)?,
            "pending selection changed before read-only custody",
        )?;
        drop(pending);
        let intent = Intent {
            schema: "droidloom.working-data-exchange-intent.v1".into(),
            candidate_id: source.candidate().into(),
            original_boot_id: history.current_boot_id().into(),
            work: source.work().into(),
            expected_cell: cell,
            selection,
            working_copy: serde_json::from_value(history.pair()["working_copy"].clone())?,
            cold_clone: history.retained_cold_clone()?,
            original: prepared.pair.original.clone(),
            working: prepared.pair.working.clone(),
            old_selection,
            new_selection,
        };
        let intent_pin = locations.write_json(INTENT, &json!({
            "schema":"droidloom.working-qualification-data-intent.v1",
            "first_once_candidate":history.candidate(), "historical_pair_intent":history.pair_pin(),
            "boot_intent":source.boot_intent(), "normal_return_configuration":source.configuration(),
            "data":intent, "old_live_retirement_reconstructed":false
        }))?;
        let intent_file = open_at(&locations.work, INTENT, false)?;
        let intent_identity = fs::stat(&intent_file)?;
        ensure(
            fs::digest(&read_small(&intent_file, 128 * 1024)?) == intent_pin.sha256,
            "H2 intent readback differs",
        )?;
        let tx = DataTransaction {
            locations,
            intent,
            intent_pin,
            intent_file,
            intent_identity,
            images,
        };
        tx.require_writer_locks()?;
        ensure(
            tx.observe(false)? == (Layout::Ready, SelectionState::Original),
            "new working pair began outside the actual original selection",
        )?;
        let value = Self {
            tx,
            first_once: history.candidate().into(),
            prior_intent: history.pair_pin().clone(),
            work_identity: fs::stat(&prepared.work.file)?,
            parents: prepared
                .pair
                .parents
                .iter()
                .map(|(_, _, snapshot)| snapshot.clone())
                .collect(),
            in_flight: None,
            pending_file,
            labelled: None,
            label_source: source.label_source_identity()?,
        };
        value.guard(prepared, history)?;
        published.guard()?;
        Ok(value)
    }

    fn observe(&self) -> Result<(Layout, SelectionState)> {
        match &self.labelled {
            Some(state) => state.observe(&self.tx, &self.pending_file, self.in_flight.as_ref()),
            None => self.tx.observe(false),
        }
    }

    pub(crate) fn begin_label_custody(
        &mut self,
        prepared: &PreparedReturnedPair,
        history: &ReturnedOnceHistory,
    ) -> Result<()> {
        self.guard(prepared, history)?;
        ensure(
            self.in_flight.is_none()
                && self.observe()? == (Layout::Switched, SelectionState::Original),
            "working label source requires a settled directory exchange",
        )?;
        if self.labelled.is_none() {
            self.labelled = Some(PairLabelState::capture(&self.tx, &self.pending_file)?);
        }
        self.guard(prepared, history)
    }

    pub(crate) fn label_targets(
        &self,
        prepared: &PreparedReturnedPair,
        history: &ReturnedOnceHistory,
    ) -> Result<Vec<(PathBuf, File)>> {
        self.guard(prepared, history)?;
        ensure(
            self.in_flight.is_none()
                && self.observe()? == (Layout::Switched, SelectionState::Original),
            "working label targets left the actual exchanged layout",
        )?;
        let targets = self
            .labelled
            .as_ref()
            .ok_or("working label inode custody was not prepared")?
            .targets(&self.pending_file)?;
        self.guard(prepared, history)?;
        Ok(targets)
    }

    pub(crate) fn accept_working_label_batch(
        &mut self,
        prepared: &PreparedReturnedPair,
        history: &ReturnedOnceHistory,
        batch: &labels::WorkingLabelBatch,
    ) -> Result<()> {
        batch.require_identity(&self.label_source)?;
        ensure(
            self.in_flight.is_none() && batch.candidate_id() == self.tx.intent.candidate_id,
            "working label batch entered an unsettled pair operation or another candidate",
        )?;
        // Source locks were advanced by the same actual batch before this call.
        // Private history/intent/working-source records never receive exceptions.
        history.guard()?;
        prepared.work.guard()?;
        prepared.source_work.guard()?;
        if let Some((directory, _)) = &prepared.recovery {
            directory.guard()?;
        }
        self.tx.validate_intent()?;
        self.tx.require_writer_locks()?;
        let state = self
            .labelled
            .as_ref()
            .ok_or("working label batch has no pre-write held-inode custody")?;
        let update = state.stage_batch(&self.pending_file, batch)?;
        let parents = prepared
            .pair
            .parents
            .iter()
            .zip(&self.parents)
            .map(|((path, held, _), before)| {
                let after = labels::snapshot(held)?;
                let named = fs::Tree::open("/", 0)?.dir(&fs::absolute_string(path)?)?;
                ensure(
                    labels::snapshot(&named)? == after,
                    "working pair label parent left its held named inode",
                )?;
                label_custody::changed_snapshot(batch, path, before, &after)?;
                Ok(after)
            })
            .collect::<Result<Vec<_>>>()?;
        ensure(
            parents.len() == self.parents.len(),
            "working pair label parent roster changed",
        )?;
        // The actual held descriptors remain the same; only verified snapshots
        // advance. A failed final fence retains both the batch and old state.
        let state = self.labelled.as_mut().unwrap();
        let old_working = state.working.clone();
        let old_pending = state.pending.clone();
        let old_pending_snapshot = state.pending_snapshot.clone();
        let old_parents = self.parents.clone();
        state.adopt(update);
        self.parents = parents;
        let result = self.guard(prepared, history);
        if result.is_err() {
            let state = self.labelled.as_mut().unwrap();
            state.working = old_working;
            state.pending = old_pending;
            state.pending_snapshot = old_pending_snapshot;
            self.parents = old_parents;
        }
        result
    }

    pub(crate) fn guard(
        &self,
        prepared: &PreparedReturnedPair,
        history: &ReturnedOnceHistory,
    ) -> Result<()> {
        history.guard()?;
        ensure(
            self.first_once == history.candidate()
                && same_pin(&self.prior_intent, history.pair_pin())
                && prepared.work.path == self.tx.locations.work_path
                && same_directory_inode(&self.work_identity, &fs::stat(&prepared.work.file)?)
                && prepared.pair.pid == std::process::id(),
            "working transaction left its actual historical observer and private workspace",
        )?;
        prepared.work.guard()?;
        prepared.source_work.guard()?;
        if let Some((directory, _)) = &prepared.recovery {
            directory.guard()?;
        }
        guard_file(&prepared.pair.pending_file)?;
        if let Some(selection) = &prepared.pair.selection_file {
            guard_file(selection)?;
        }
        ensure(
            prepared.pair.backings.len() == 4 && self.tx.images.len() == 4,
            "held working backing roster differs",
        )?;
        for (index, (old, (held, initial, working))) in prepared
            .pair
            .backings
            .iter()
            .zip(&self.tx.images)
            .enumerate()
        {
            let labelled = self
                .labelled
                .as_ref()
                .filter(|_| *working)
                .map(|state| &state.working.members[IMAGES[index % 2]]);
            let expected = labelled.map_or(initial, |member| &member.identity);
            let snapshot = labelled.map_or(&old.snapshot, |member| &member.label_identity);
            ensure(
                old.identity == *initial
                    && fs::stat(&old.file)? == *expected
                    && fs::stat(held)? == *expected
                    && labels::data_snapshot(&old.file, expected)? == *snapshot,
                "cold working exchange changed an actual backing or its complete source attributes",
            )?;
        }
        self.tx.require_writer_locks()?;
        let (layout, selection) = self.observe()?;
        ensure(
            selection == SelectionState::Original,
            "pair exchange cannot publish a candidate selection",
        )?;
        ensure(
            fs::stat(&self.pending_file)?
                == self
                    .labelled
                    .as_ref()
                    .map_or(&self.tx.intent.new_selection.identity, |state| {
                        &state.pending.identity
                    })
                    .clone()
                && fs::digest(&read_small(&self.pending_file, 16384)?)
                    == self.tx.intent.selection.sha256,
            "pending selection left its held complete prelabel source",
        )?;
        if let Some(pending) = &self.in_flight {
            pending.verify(prepared, &self.tx, layout)?;
        } else {
            for ((path, file, _), expected) in prepared.pair.parents.iter().zip(&self.parents) {
                let named = fs::Tree::open("/", 0)?.dir(&fs::absolute_string(path)?)?;
                ensure(
                    labels::snapshot(file)? == *expected && labels::snapshot(&named)? == *expected,
                    "working parent changed outside its exact exchange",
                )?;
            }
        }
        let _ = reference_scan::require_no_other_references(&reference_targets(
            &self.tx.intent.original,
            self.labelled
                .as_ref()
                .map_or(&self.tx.intent.working, |state| &state.working),
        ))?;
        history.guard()
    }

    fn operation(
        &mut self,
        prepared: &PreparedReturnedPair,
        history: &ReturnedOnceHistory,
        step: Step,
    ) -> Result<()> {
        self.guard(prepared, history)?;
        if self.in_flight.is_none() {
            ensure(
                self.observe()?.0 == step.states().0,
                "working exchange step is out of order",
            )?;
            let witness = PendingStep::capture(step, prepared, &self.tx)?;
            ensure(
                witness.parents == self.parents,
                "working parent changed while its exact operation witness was captured",
            )?;
            self.guard(prepared, history)?;
            self.in_flight = Some(witness);
        }
        ensure(
            self.in_flight.as_ref().unwrap().step == step,
            "another atomic working step is still unsettled",
        )?;
        let layout = self.observe()?.0;
        self.in_flight
            .as_ref()
            .unwrap()
            .verify(prepared, &self.tx, layout)?;
        if layout == step.states().0 {
            match step {
                Step::Stage => self
                    .tx
                    .locations
                    .move_pair(Place::Working, Place::Rollback)?,
                Step::Exchange | Step::Unexchange => self.tx.locations.exchange_pair()?,
                Step::Return => self
                    .tx
                    .locations
                    .move_pair(Place::Rollback, Place::Working)?,
            }
        }
        let layout = self.observe()?.0;
        ensure(
            layout == step.states().1,
            "fixed working rename did not reach its exact next layout",
        )?;
        let after = self
            .in_flight
            .as_ref()
            .unwrap()
            .verify(prepared, &self.tx, layout)?;
        if let Some(state) = &mut self.labelled {
            state.after_move(self.in_flight.as_ref().unwrap(), &self.pending_file)?;
        }
        self.parents = after;
        self.in_flight = None;
        self.guard(prepared, history)
    }

    pub(crate) fn advance(
        &mut self,
        prepared: &PreparedReturnedPair,
        history: &ReturnedOnceHistory,
    ) -> Result<()> {
        self.guard(prepared, history)?;
        let step = if let Some(pending) = &self.in_flight {
            pending.step
        } else {
            match self.observe()?.0 {
                Layout::Ready => Step::Stage,
                Layout::Staged => Step::Exchange,
                Layout::Switched => return Ok(()),
            }
        };
        ensure(
            matches!(step, Step::Stage | Step::Exchange),
            "a rollback step cannot be advanced as a boot preparation",
        )?;
        self.operation(prepared, history, step)
    }
    pub(crate) fn exchanged(
        &self,
        prepared: &PreparedReturnedPair,
        history: &ReturnedOnceHistory,
    ) -> Result<bool> {
        self.guard(prepared, history)?;
        Ok(self.in_flight.is_none() && self.observe()?.0 == Layout::Switched)
    }
    pub(crate) fn restore_cold(
        &mut self,
        prepared: &PreparedReturnedPair,
        history: &ReturnedOnceHistory,
    ) -> Result<()> {
        self.guard(prepared, history)?;
        if let Some(pending) = &self.in_flight {
            let actual = self.observe()?.0;
            let after = pending.verify(prepared, &self.tx, actual)?;
            if let Some(state) = &mut self.labelled {
                state.after_move(pending, &self.pending_file)?;
            }
            self.parents = after;
            self.in_flight = None;
        }
        match self.observe()?.0 {
            Layout::Switched => self.operation(prepared, history, Step::Unexchange)?,
            Layout::Staged | Layout::Ready => (),
        }
        if self.observe()?.0 == Layout::Staged {
            self.operation(prepared, history, Step::Return)?;
        }
        ensure(
            self.observe()? == (Layout::Ready, SelectionState::Original),
            "same-boot working rollback did not restore the actual original pair",
        )?;
        self.guard(prepared, history)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{
        os::unix::fs::PermissionsExt,
        sync::atomic::{AtomicU64, Ordering},
    };
    static NEXT: AtomicU64 = AtomicU64::new(0);
    struct Temporary(PathBuf);
    impl Temporary {
        fn new() -> Self {
            let path = std::env::temp_dir().join(format!(
                "working-pair-ofds-{}-{}",
                std::process::id(),
                NEXT.fetch_add(1, Ordering::Relaxed)
            ));
            std::fs::create_dir(&path).unwrap();
            std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o700)).unwrap();
            Self(path)
        }
    }
    impl Drop for Temporary {
        fn drop(&mut self) {
            let _ = std::fs::remove_dir_all(&self.0);
        }
    }
    fn actual_four() -> (Temporary, Vec<File>, Vec<Identity>) {
        let dir = Temporary::new();
        let mut files = Vec::new();
        let mut ids = Vec::new();
        for n in 0..4 {
            let path = dir.0.join(format!("image-{n}"));
            std::fs::write(&path, [n as u8; 16]).unwrap();
            std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o600)).unwrap();
            let file = File::open(path).unwrap();
            rustix::fs::flock(&file, FlockOperation::NonBlockingLockExclusive).unwrap();
            ids.push(fs::stat(&file).unwrap());
            files.push(file);
        }
        (dir, files, ids)
    }
    fn rows<'a>(files: &'a [File], ids: &'a [Identity]) -> [(&'a File, &'a Identity, bool); 4] {
        [
            (&files[0], &ids[0], false),
            (&files[1], &ids[1], false),
            (&files[2], &ids[2], true),
            (&files[3], &ids[3], true),
        ]
    }
    #[test]
    fn working_pair_dup_retains_all_four_actual_flocks_when_original_fds_close() {
        let (dir, originals, ids) = actual_four();
        let duplicated = duplicate_image_ofds(rows(&originals, &ids)).unwrap();
        for (old, (new, expected, _)) in originals.iter().zip(&duplicated) {
            assert_ne!(old.as_raw_fd(), new.as_raw_fd());
            assert_eq!(fs::stat(new).unwrap(), *expected);
        }
        let competitors = (0..4)
            .map(|n| File::open(dir.0.join(format!("image-{n}"))).unwrap())
            .collect::<Vec<_>>();
        for file in &competitors {
            assert!(rustix::fs::flock(file, FlockOperation::NonBlockingLockExclusive).is_err());
        }
        drop(originals);
        for file in &competitors {
            assert!(rustix::fs::flock(file, FlockOperation::NonBlockingLockExclusive).is_err());
        }
        drop(duplicated);
        for file in &competitors {
            rustix::fs::flock(file, FlockOperation::NonBlockingLockExclusive).unwrap();
        }
    }
    #[test]
    fn working_pair_dup_rejects_an_inode_alias_and_a_wrong_role_order() {
        let (_dir, files, ids) = actual_four();
        let mut aliased = rows(&files, &ids);
        aliased[2] = (&files[0], &ids[0], true);
        assert!(duplicate_image_ofds(aliased).is_err());
        let mut wrong = rows(&files, &ids);
        wrong[0].2 = true;
        wrong[2].2 = false;
        assert!(duplicate_image_ofds(wrong).is_err());
    }
    #[test]
    fn working_pair_dup_rejects_write_capable_fd_and_stale_complete_identity() {
        let (dir, files, ids) = actual_four();
        let writable = std::fs::OpenOptions::new()
            .read(true)
            .write(true)
            .open(dir.0.join("image-0"))
            .unwrap();
        let mut wrong = rows(&files, &ids);
        wrong[0].0 = &writable;
        assert!(duplicate_image_ofds(wrong).is_err());
        writable.set_len(17).unwrap();
        assert!(duplicate_image_ofds(rows(&files, &ids)).is_err());
    }
    fn inventory_fixture() -> (Temporary, File, File, DirectoryInventory) {
        let dir = Temporary::new();
        let from = dir.0.join("from");
        let to = dir.0.join("to");
        std::fs::create_dir(&from).unwrap();
        std::fs::create_dir(&to).unwrap();
        std::fs::create_dir(from.join("moving")).unwrap();
        std::fs::write(from.join("untouched"), b"same contents").unwrap();
        let from = File::open(from).unwrap();
        let to = File::open(to).unwrap();
        let before = DirectoryInventory::capture(&from).unwrap();
        (dir, from, to, before)
    }
    #[test]
    fn working_parent_inventory_accepts_only_the_actual_fixed_move() {
        let (_dir, from, to, before) = inventory_fixture();
        let moving = named(&from, "moving").unwrap().unwrap();
        rustix::fs::renameat_with(&from, "moving", &to, "moving", RenameFlags::NOREPLACE).unwrap();
        verify_inventory_transition(&before, &from, EntryChange::Remove("moving"), None).unwrap();
        let empty = DirectoryInventory {
            members: Vec::new(),
        };
        verify_inventory_transition(&empty, &to, EntryChange::Add("moving", &moving), None)
            .unwrap();
    }
    #[test]
    fn working_parent_inventory_rejects_same_bytes_sibling_replacement() {
        let (dir, from, to, before) = inventory_fixture();
        rustix::fs::renameat_with(&from, "moving", &to, "moving", RenameFlags::NOREPLACE).unwrap();
        std::fs::remove_file(dir.0.join("from/untouched")).unwrap();
        std::fs::write(dir.0.join("from/untouched"), b"same contents").unwrap();
        assert!(
            verify_inventory_transition(&before, &from, EntryChange::Remove("moving"), None)
                .is_err()
        );
    }
    #[test]
    fn working_parent_inventory_rejects_an_extra_birth_during_the_move() {
        let (dir, from, to, before) = inventory_fixture();
        rustix::fs::renameat_with(&from, "moving", &to, "moving", RenameFlags::NOREPLACE).unwrap();
        std::fs::write(dir.0.join("from/extra"), b"unowned").unwrap();
        assert!(
            verify_inventory_transition(&before, &from, EntryChange::Remove("moving"), None)
                .is_err()
        );
    }
}
