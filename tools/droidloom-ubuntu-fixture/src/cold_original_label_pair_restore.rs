//! The reverse whole-pair move, authorized only by actual original retirement.
//! Its fixed public parent and working directory evolution is retained for the
//! subsequent label restoration; it never labels the original rollback pair.
use super::selection::{DirectoryState, directory_state};
use super::*;
use crate::cold_original_qualification::OriginalRetirement;

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct PairIntent {
    schema: String,
    candidate_id: String,
    pair_intent: FilePin,
    retirement: FilePin,
    parent: DirectoryState,
    original: Snapshot,
    working: Snapshot,
}
#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct PairResult {
    schema: String,
    intent: FilePin,
    parent: DirectoryState,
    original: Snapshot,
    working: Snapshot,
}
pub(crate) struct OriginalPairRestored {
    intent: FilePin,
    result: FilePin,
}
fn locations(
    scope: &RootScope,
    data: &OriginalDataTransaction,
    layout: data::Layout,
) -> Result<(Snapshot, Snapshot)> {
    let original = if layout == data::Layout::Switched {
        data.transaction.locations.work_path.join(data::ROLLBACK)
    } else {
        PathBuf::from(data::ORIGINAL)
    };
    let working = match layout {
        data::Layout::Ready => PathBuf::from(data::WORKING),
        data::Layout::Staged => data.transaction.locations.work_path.join(data::ROLLBACK),
        data::Layout::Switched => PathBuf::from(data::ORIGINAL),
    };
    Ok((
        snapshot(&scope.open_named(&original)?)?,
        snapshot(&scope.open_named(&working)?)?,
    ))
}
fn same_directory(before: &Snapshot, after: &Snapshot) -> Result<()> {
    ensure(
        before.handle == after.handle
            && before.attributes == after.attributes
            && only_ctime_changed(&before.identity, &after.identity),
        "pair rename changed an unrelated directory field, generation or label",
    )
}
fn verify_parent(
    before: &DirectoryState,
    after: &DirectoryState,
    original: &Snapshot,
) -> Result<()> {
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
        "original pair parent lost its identity, authority, links or labels",
    )?;
    let mut expected = before.members.clone();
    expected.insert("data".into(), original.identity.clone());
    ensure(
        expected == after.members,
        "pair restoration changed an unrelated public parent member",
    )
}
fn read(
    records: &Records,
    retirement: &OriginalRetirement,
    data: &OriginalDataTransaction,
) -> Result<(FilePin, PairIntent)> {
    let pin = record_pin(records, "PREIMAGE.json")?;
    let (_, _, body) = records.read("PREIMAGE.json")?;
    let intent: PairIntent = serde_json::from_slice(&body)?;
    ensure(
        intent.schema == "droidloom.original-pair-restoration-intent.v1"
            && intent.candidate_id == retirement.candidate_id()
            && pin_equal(&intent.pair_intent, data.intent()),
        "pair restoration is not this retired immutable transaction",
    )?;
    let old: Value =
        serde_json::from_slice(&data::root_pin(&intent.retirement, 16 * 1024 * 1024)?)?;
    ensure(
        old["schema"] == "droidloom.original-once-retirement.v1"
            && old["candidate_id"] == retirement.candidate_id()
            && old["normal_sources"] == serde_json::to_value(retirement.source_pin())?,
        "pair restoration's historical retirement source differs",
    )?;
    Ok((pin, intent))
}
pub(in crate::cold_original_data) fn restore_pair(
    retirement: &OriginalRetirement,
    data: &OriginalDataTransaction,
) -> Result<OriginalPairRestored> {
    retirement.revalidate()?;
    let authority = retirement.authority();
    data.binding(authority)?;
    ensure(
        pin_equal(retirement.pair_intent(), data.intent()),
        "retirement and data intents differ",
    )?;
    let (mut layout, selected) = data.transaction.observe(true)?;
    ensure(
        selected == data::SelectionState::Original,
        "pair restoration requires actual selection withdrawal",
    )?;
    super::restore::seal_pair_label_outcomes(retirement, data)?;
    let scope = RootScope::original(&data.transaction.intent.cold_clone)?;
    let path = authority.work().join("pair-restoration");
    match std::fs::symlink_metadata(&path) {
        Ok(_) => {}
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => {
            crate::boot_files::private_dir(&path)?
        }
        Err(e) => return Err(e.into()),
    }
    let records = Records::open(&path)?;
    if !records.exists("PREIMAGE.json")? {
        records.verify_unpublished_preimage()?;
        let (original, working) = locations(&scope, data, layout)?;
        let parent = directory_state(&data.transaction.locations.original_parent)?;
        retirement.revalidate()?;
        records.publish(
            "PREIMAGE.json",
            &PairIntent {
                schema: "droidloom.original-pair-restoration-intent.v1".into(),
                candidate_id: retirement.candidate_id().into(),
                pair_intent: data.intent().clone(),
                retirement: retirement.report_pin().clone(),
                parent,
                original,
                working,
            },
        )?;
    }
    let (pin, intent) = read(&records, retirement, data)?;
    let (original, working) = locations(&scope, data, layout)?;
    same_directory(&intent.original, &original)?;
    same_directory(&intent.working, &working)?;
    if layout == data::Layout::Switched {
        ensure(
            serde_json::to_value(directory_state(
                &data.transaction.locations.original_parent,
            )?)? == serde_json::to_value(&intent.parent)?,
            "pair restore parent changed before its actual atomic exchange",
        )?;
        authority.verify_data_step(OriginalDataStep::Restore)?;
        retirement.revalidate()?;
        data.transaction.locations.exchange_pair()?;
        retirement.revalidate()?;
        layout = data.transaction.observe(true)?.0;
    }
    if layout == data::Layout::Staged {
        let (original, working) = locations(&scope, data, layout)?;
        same_directory(&intent.original, &original)?;
        same_directory(&intent.working, &working)?;
        verify_parent(
            &intent.parent,
            &directory_state(&data.transaction.locations.original_parent)?,
            &original,
        )?;
        authority.verify_data_step(OriginalDataStep::Restore)?;
        retirement.revalidate()?;
        data.transaction
            .locations
            .move_pair(data::Place::Rollback, data::Place::Working)?;
    }
    ensure(
        data.transaction.observe(true)? == (data::Layout::Ready, data::SelectionState::Original),
        "original pair was not restored to the exact finite layout",
    )?;
    let (original, working) = locations(&scope, data, data::Layout::Ready)?;
    same_directory(&intent.original, &original)?;
    same_directory(&intent.working, &working)?;
    let parent = directory_state(&data.transaction.locations.original_parent)?;
    verify_parent(&intent.parent, &parent, &original)?;
    data.transaction.locations.original_parent.sync_all()?;
    data.transaction.locations.working_parent.sync_all()?;
    data.transaction.locations.work.sync_all()?;
    retirement.revalidate()?;
    data.binding(authority)?;
    let actual = PairResult {
        schema: "droidloom.original-pair-restoration-result.v1".into(),
        intent: pin.clone(),
        parent,
        original,
        working,
    };
    let result = if records.exists("RESULT.json")? {
        let (_, _, body) = records.read("RESULT.json")?;
        ensure(
            serde_json::from_slice::<Value>(&body)? == serde_json::to_value(&actual)?,
            "restored pair differs from its actual durable readback",
        )?;
        record_pin(&records, "RESULT.json")?
    } else {
        records.publish("RESULT.json", &actual)?
    };
    let result = OriginalPairRestored {
        intent: pin,
        result,
    };
    result.revalidate(retirement, data)?;
    Ok(result)
}
impl OriginalPairRestored {
    pub(crate) fn report(&self) -> &FilePin {
        &self.result
    }
    pub(crate) fn revalidate(
        &self,
        retirement: &OriginalRetirement,
        data: &OriginalDataTransaction,
    ) -> Result<()> {
        retirement.revalidate()?;
        data.binding(retirement.authority())?;
        let records = Records::open(&retirement.authority().work().join("pair-restoration"))?;
        let (pin, intent) = read(&records, retirement, data)?;
        ensure(
            pin_equal(&pin, &self.intent)
                && pin_equal(&record_pin(&records, "RESULT.json")?, &self.result),
            "restored pair evidence was replaced",
        )?;
        let (_, _, body) = records.read("RESULT.json")?;
        let result: PairResult = serde_json::from_slice(&body)?;
        ensure(
            result.schema == "droidloom.original-pair-restoration-result.v1"
                && pin_equal(&result.intent, &self.intent)
                && data.transaction.observe(true)?
                    == (data::Layout::Ready, data::SelectionState::Original),
            "restored pair result or layout differs",
        )?;
        let scope = RootScope::original(&data.transaction.intent.cold_clone)?;
        let (original, working) = locations(&scope, data, data::Layout::Ready)?;
        same_directory(&intent.original, &original)?;
        same_directory(&intent.working, &working)?;
        let parent = directory_state(&data.transaction.locations.original_parent)?;
        verify_parent(&intent.parent, &parent, &original)?;
        ensure(
            original == result.original
                && working == result.working
                && serde_json::to_value(parent)? == serde_json::to_value(result.parent)?,
            "restored pair named generations or public parent changed",
        )?;
        retirement.revalidate()
    }
    pub(super) fn derived_snapshots(
        &self,
        retirement: &OriginalRetirement,
        data: &OriginalDataTransaction,
    ) -> Result<BTreeMap<PathBuf, Snapshot>> {
        // Historical exact rename evidence remains useful while a subsequent
        // typed label restoration legitimately changes these same ctimes.
        self.validate_history(retirement, data)?;
        let value: PairResult =
            serde_json::from_slice(&data::root_pin(&self.result, 32 * 1024 * 1024)?)?;
        Ok(BTreeMap::from([
            (
                PathBuf::from("/var/lib/droidloom/users/1000"),
                value.parent.snapshot,
            ),
            (PathBuf::from(data::ORIGINAL), value.working),
        ]))
    }
    pub(super) fn resume_for_labels(
        retirement: &OriginalRetirement,
        data: &OriginalDataTransaction,
    ) -> Result<Self> {
        retirement.revalidate()?;
        data.binding(retirement.authority())?;
        ensure(
            data.transaction.observe(true)?
                == (data::Layout::Ready, data::SelectionState::Original),
            "label restoration requires the actual completed original pair layout",
        )?;
        let records = Records::open(&retirement.authority().work().join("pair-restoration"))?;
        let (intent, _) = read(&records, retirement, data)?;
        let value = Self {
            intent,
            result: record_pin(&records, "RESULT.json")?,
        };
        value.validate_history(retirement, data)?;
        Ok(value)
    }
    fn validate_history(
        &self,
        retirement: &OriginalRetirement,
        data: &OriginalDataTransaction,
    ) -> Result<()> {
        let records = Records::open(&retirement.authority().work().join("pair-restoration"))?;
        let (pin, intent) = read(&records, retirement, data)?;
        ensure(
            pin_equal(&pin, &self.intent)
                && pin_equal(&record_pin(&records, "RESULT.json")?, &self.result),
            "preserved whole-pair rename evidence was replaced",
        )?;
        let (_, _, body) = records.read("RESULT.json")?;
        let result: PairResult = serde_json::from_slice(&body)?;
        ensure(
            result.schema == "droidloom.original-pair-restoration-result.v1"
                && pin_equal(&result.intent, &pin),
            "preserved whole-pair rename result has another intent",
        )?;
        same_directory(&intent.original, &result.original)?;
        same_directory(&intent.working, &result.working)?;
        verify_parent(&intent.parent, &result.parent, &result.original)
    }
}
