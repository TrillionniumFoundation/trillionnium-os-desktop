//! Three finite inverse renames under the fresh returned owner and freezer.
//! All four image OFDs remain in WorkingReturnData. Only directory/selection
//! names move; original images are never opened writable, fsynced or relabeled.
use super::*;
use crate::cold_original_qualification::WorkingReturnQuiescence;
use std::collections::BTreeSet;

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
struct Directory {
    snapshot: labels::Snapshot,
    members: BTreeMap<String, labels::Snapshot>,
}
fn observe_directory(file: &File) -> Result<Directory> {
    let snapshot = labels::snapshot(file)?;
    let mut members = BTreeMap::new();
    let reader = File::from(rustix::fs::openat(
        file,
        ".",
        OFlags::RDONLY | OFlags::DIRECTORY | OFlags::CLOEXEC | OFlags::NOFOLLOW,
        Mode::empty(),
    )?);
    for entry in rustix::fs::Dir::read_from(&reader)? {
        let entry = entry?;
        let name = entry.file_name().to_str()?;
        if matches!(name, "." | "..") {
            continue;
        }
        ensure(
            members.len() < 4096,
            "returned data parent exceeds its closed member bound",
        )?;
        let child = File::from(rustix::fs::openat(
            file,
            name,
            OFlags::PATH | OFlags::NOFOLLOW | OFlags::CLOEXEC,
            Mode::empty(),
        )?);
        ensure(
            members
                .insert(name.into(), labels::snapshot(&child)?)
                .is_none(),
            "duplicate returned parent member",
        )?;
    }
    ensure(
        labels::snapshot(file)? == snapshot,
        "returned parent changed during its complete member capture",
    )?;
    Ok(Directory { snapshot, members })
}
fn same_renamed(before: &labels::Snapshot, after: &labels::Snapshot) -> Result<()> {
    labels::verify_data_snapshot(before, after, false)?;
    ensure(
        labels::only_ctime_changed(
            labels::snapshot_identity(before),
            labels::snapshot_identity(after),
        ),
        "returned owned rename changed more than the same inode's ctime",
    )
}
fn parent_delta(
    before: &Directory,
    after: &Directory,
    replacements: &BTreeMap<String, Option<labels::Snapshot>>,
) -> Result<()> {
    labels::verify_data_snapshot(&before.snapshot, &after.snapshot, false)?;
    let old = labels::snapshot_identity(&before.snapshot);
    let new = labels::snapshot_identity(&after.snapshot);
    let mut members = before.members.clone();
    let mut delta = 0i64;
    for (name, replacement) in replacements {
        let directory = |s: &labels::Snapshot| {
            FileType::from_raw_mode(labels::snapshot_identity(s).mode) == FileType::Directory
        };
        if let Some(prior) = members.get(name) {
            if directory(prior) {
                delta -= 1;
            }
        }
        match replacement {
            Some(v) => {
                if directory(v) {
                    delta += 1;
                }
                members.insert(name.clone(), v.clone());
            }
            None => {
                members.remove(name);
            }
        }
    }
    let expected_links = (old.nlink as i64)
        .checked_add(delta)
        .ok_or("returned parent link overflow")?;
    let mut stable = new.clone();
    stable.size = old.size;
    stable.mtime_sec = old.mtime_sec;
    stable.mtime_nsec = old.mtime_nsec;
    stable.ctime_sec = old.ctime_sec;
    stable.ctime_nsec = old.ctime_nsec;
    stable.nlink = old.nlink;
    ensure(
        stable == *old && new.nlink as i64 == expected_links && after.members == members,
        "returned data rename changed another parent inode, link count, attribute or complete member",
    )
}

struct Slot {
    path: PathBuf,
    file: File,
    identity: Identity,
    sealed: Option<FilePin>,
}
impl Slot {
    fn create(path: PathBuf) -> Result<Self> {
        let (parent, name) = path
            .parent()
            .zip(path.file_name())
            .ok_or("returned private slot name")?;
        let directory = fs::Tree::open("/", 0)?.dir(&fs::absolute_string(parent)?)?;
        let file = File::from(rustix::fs::openat(
            &directory,
            name,
            OFlags::RDWR | OFlags::CREATE | OFlags::EXCL | OFlags::NOFOLLOW | OFlags::CLOEXEC,
            Mode::from_raw_mode(0o600),
        )?);
        let identity = fs::stat(&file)?;
        ensure(
            identity.uid == 0
                && identity.gid == 0
                && identity.nlink == 1
                && identity.mode == 0o100600
                && identity.size == 0,
            "returned private record must start as one empty owned root inode",
        )?;
        Ok(Self {
            path,
            file,
            identity,
            sealed: None,
        })
    }
    fn publish(&mut self, value: &Value) -> Result<FilePin> {
        let raw = serde_json::to_vec(value)?;
        ensure(
            !raw.is_empty() && raw.len() <= 16 * 1024 * 1024,
            "bounded returned actual rename evidence required",
        )?;
        if let Some(pin) = &self.sealed {
            ensure(
                fs::stat(&self.file)? == self.identity
                    && fs::Tree::open("/", 0)?.identity(&fs::absolute_string(&self.path)?)?
                        == self.identity
                    && read_small(&self.file, 16 * 1024 * 1024)? == raw,
                "returned completed record changed its held inode or full body",
            )?;
            return Ok(pin.clone());
        }
        let actual = fs::stat(&self.file)?;
        ensure(
            inode(&actual, &self.identity)
                && actual.uid == 0
                && actual.gid == 0
                && actual.nlink == 1
                && matches!(actual.mode, 0o100600 | 0o100400)
                && fs::Tree::open("/", 0)?.identity(&fs::absolute_string(&self.path)?)? == actual,
            "returned unfinished evidence lost its actual private inode",
        )?;
        let existing = read_small(&self.file, 16 * 1024 * 1024)?;
        ensure(
            raw.starts_with(&existing) && existing.len() <= raw.len(),
            "returned partial record is not its exact pending source body",
        )?;
        if existing.len() < raw.len() {
            ensure(
                actual.mode == 0o100600,
                "sealed returned record has a partial body",
            )?;
            self.file
                .write_all_at(&raw[existing.len()..], existing.len() as u64)?;
        }
        rustix::fs::fchmod(&self.file, Mode::from_raw_mode(0o400))?;
        self.file.sync_all()?;
        let final_identity = fs::stat(&self.file)?;
        ensure(
            read_small(&self.file, 16 * 1024 * 1024)? == raw
                && fs::Tree::open("/", 0)?.identity(&fs::absolute_string(&self.path)?)?
                    == final_identity,
            "returned evidence was not completely read back through the actual held inode",
        )?;
        let pin = FilePin {
            path: self.path.clone(),
            bytes: raw.len() as u64,
            sha256: fs::digest(&raw),
        };
        self.identity = final_identity;
        self.sealed = Some(pin.clone());
        Ok(pin)
    }
    fn revalidate(&self) -> Result<()> {
        ensure(
            fs::stat(&self.file)? == self.identity
                && fs::Tree::open("/", 0)?.identity(&fs::absolute_string(&self.path)?)?
                    == self.identity,
            "returned sealed operation evidence changed actual inode",
        )?;
        if let Some(pin) = &self.sealed {
            ensure(
                fs::digest(&read_small(&self.file, 16 * 1024 * 1024)?) == pin.sha256,
                "returned sealed operation evidence changed actual bytes",
            )?;
        }
        Ok(())
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord)]
enum Kind {
    Selection,
    Exchange,
    Working,
}
impl Kind {
    fn name(self) -> &'static str {
        match self {
            Self::Selection => "selection",
            Self::Exchange => "exchange",
            Self::Working => "working",
        }
    }
    fn states(self, before: (Layout, SelectionState)) -> Result<(Layout, SelectionState)> {
        match (self, before) {
            (Self::Selection, (Layout::Switched, SelectionState::Candidate)) => {
                Ok((Layout::Switched, SelectionState::Original))
            }
            (Self::Exchange, (Layout::Switched, SelectionState::Original)) => {
                Ok((Layout::Staged, SelectionState::Original))
            }
            (Self::Working, (Layout::Staged, SelectionState::Original)) => {
                Ok((Layout::Ready, SelectionState::Original))
            }
            _ => {
                Err("returned inverse step is outside the fixed selected/pair state machine".into())
            }
        }
    }
}
struct OriginalSelection {
    file: File,
    snapshot: labels::Snapshot,
    sha256: String,
}
struct Parent {
    path: PathBuf,
    file: File,
    before: Directory,
}
struct Active {
    kind: Kind,
    attempt: usize,
    before_state: (Layout, SelectionState),
    after_state: (Layout, SelectionState),
    nodes: Vec<labels::Snapshot>,
    original: Option<labels::Snapshot>,
    parents: Vec<Parent>,
    intent: FilePin,
    attempted: bool,
    after: Option<Value>,
}
pub(super) struct State {
    pub(super) labels: labels::WorkingReturnedLabelHistory,
    slots: BTreeMap<String, Slot>,
    original: Option<OriginalSelection>,
    active: Option<Active>,
    attempts: BTreeMap<Kind, usize>,
    completed: Vec<FilePin>,
    report: Option<FilePin>,
}
fn original_selection(data: &WorkingReturnData) -> Result<Option<OriginalSelection>> {
    let Some(expected) = &data.transaction.intent.old_selection else {
        return Ok(None);
    };
    let state = data.transaction.selection_state()?;
    let (parent, name) = if state == SelectionState::Candidate {
        (&data.transaction.locations.work, PENDING)
    } else {
        (
            &data.transaction.locations.selected_parent,
            data.transaction.locations.selected_name.as_str(),
        )
    };
    let file = open_at(parent, name, false)?;
    let snapshot = labels::snapshot(&file)?;
    ensure(
        stable(labels::snapshot_identity(&snapshot), &expected.identity)
            && fs::digest(&read_small(&file, 16 * 1024)?) == expected.sha256,
        "original selected preimage is not the actual source-bound protected inode",
    )?;
    if state == SelectionState::Candidate {
        let pin = crate::boot_files::pin_file(
            &data
                .sources
                .work()
                .join("working-selection/publish/INTENT.json"),
        )?;
        let value: Value = serde_json::from_slice(&root_pin(&pin, 16 * 1024 * 1024)?)?;
        ensure(
            value["schema"] == "droidloom.working-selection-intent.v1"
                && value["candidate_id"] == data.sources.candidate()
                && value["operation"] == "publish",
            "returned original selection has no source-owned actual publication preimage",
        )?;
        let before: labels::Snapshot = serde_json::from_value(value["before"]["original"].clone())?;
        same_renamed(&before, &snapshot)?;
    }
    Ok(Some(OriginalSelection {
        file,
        snapshot,
        sha256: expected.sha256.clone(),
    }))
}
fn guard_original(data: &WorkingReturnData, state: &State) -> Result<()> {
    if let Some(original) = &state.original {
        ensure(
            labels::snapshot(&original.file)? == original.snapshot
                && fs::digest(&read_small(&original.file, 16 * 1024)?) == original.sha256,
            "held original selection changed outside its exact inverse rename",
        )?;
        let (parent, name) = if data.transaction.selection_state()? == SelectionState::Candidate {
            (&data.transaction.locations.work, PENDING)
        } else {
            (
                &data.transaction.locations.selected_parent,
                data.transaction.locations.selected_name.as_str(),
            )
        };
        ensure(
            named(parent, name)? == Some(labels::snapshot_identity(&original.snapshot).clone()),
            "original selection lost its actual owned name",
        )?;
    }
    Ok(())
}
fn fence(data: &WorkingReturnData, state: &State, window: &WorkingReturnQuiescence) -> Result<()> {
    window.require_sources(&data.sources)?;
    data.revalidate_custody()?;
    guard_original(data, state)?;
    for slot in state.slots.values().filter(|s| s.sealed.is_some()) {
        slot.revalidate()?;
    }
    Ok(())
}
pub(super) fn begin(
    data: &mut WorkingReturnData,
    labels: labels::WorkingReturnedLabelHistory,
    window: &WorkingReturnQuiescence,
) -> Result<()> {
    ensure(
        data.restoration.is_none(),
        "returned data inverse already owns its completed label capability",
    )?;
    labels.require_data(data, window)?;
    data.revalidate()?;
    let root = data
        .report
        .path
        .parent()
        .ok_or("returned data epoch directory")?;
    let mut slots = BTreeMap::new();
    for kind in [Kind::Selection, Kind::Exchange, Kind::Working] {
        for attempt in 0..4 {
            for suffix in ["INTENT", "RESULT"] {
                let name = format!("{}-{attempt:02}-{suffix}.json", kind.name());
                slots.insert(name.clone(), Slot::create(root.join(name))?);
            }
        }
    }
    slots.insert(
        "RESTORED.json".into(),
        Slot::create(root.join("RESTORED.json"))?,
    );
    File::open(root)?.sync_all()?;
    let original = original_selection(data)?;
    let state = State {
        labels,
        slots,
        original,
        active: None,
        attempts: BTreeMap::new(),
        completed: Vec::new(),
        report: None,
    };
    fence(data, &state, window)?;
    data.restoration = Some(state);
    Ok(())
}
fn parents(data: &WorkingReturnData, kind: Kind) -> Result<Vec<Parent>> {
    let loc = &data.transaction.locations;
    let rows = match kind {
        Kind::Selection => vec![
            (
                Path::new(SELECTED).parent().unwrap().to_owned(),
                &loc.selected_parent,
            ),
            (data.sources.work().to_owned(), &loc.work),
        ],
        Kind::Exchange => vec![
            (
                Path::new(ORIGINAL).parent().unwrap().to_owned(),
                &loc.original_parent,
            ),
            (data.sources.work().to_owned(), &loc.work),
        ],
        Kind::Working => vec![
            (data.sources.work().to_owned(), &loc.work),
            (
                Path::new(WORKING).parent().unwrap().to_owned(),
                &loc.working_parent,
            ),
        ],
    };
    rows.into_iter()
        .map(|(path, file)| {
            Ok(Parent {
                path,
                file: file.try_clone()?,
                before: observe_directory(file)?,
            })
        })
        .collect()
}
fn prepare(
    data: &WorkingReturnData,
    state: &mut State,
    window: &WorkingReturnQuiescence,
    kind: Kind,
) -> Result<()> {
    fence(data, state, window)?;
    let before = data.transaction.observe(true)?;
    let after = kind.states(before)?;
    let attempt = *state.attempts.get(&kind).unwrap_or(&0);
    ensure(
        attempt < 4,
        "returned inverse exceeded its bounded known-no-effect retry count",
    )?;
    let parents = parents(data, kind)?;
    let nodes = data
        .nodes
        .iter()
        .map(|n| n.current.clone())
        .collect::<Vec<_>>();
    let original = state.original.as_ref().map(|o| o.snapshot.clone());
    let value = json!({"schema":"droidloom.working-returned-data-rename-intent.v1","candidate_id":data.sources.candidate(),
        "actual_owner":data.sources.owner().evidence(),"actual_data_retirement":data.report(),
        "actual_labels":state.labels.report(),"actual_freezer":window.intent_pin(),
        "operation":kind.name(),"attempt":attempt,"before_state":format!("{before:?}"),"after_state":format!("{after:?}"),
        "parents":parents.iter().map(|p|json!({"path":p.path,"before":p.before})).collect::<Vec<_>>(),
        "held_nodes":nodes,"original_selection":original});
    let name = format!("{}-{attempt:02}-INTENT.json", kind.name());
    let intent = state
        .slots
        .get_mut(&name)
        .ok_or("returned intent slot absent")?
        .publish(&value)?;
    for parent in &parents {
        ensure(
            observe_directory(&parent.file)? == parent.before,
            "returned parent changed during durable intent publication",
        )?;
    }
    fence(data, state, window)?;
    state.active = Some(Active {
        kind,
        attempt,
        before_state: before,
        after_state: after,
        nodes,
        original,
        parents,
        intent,
        attempted: false,
        after: None,
    });
    state.attempts.insert(kind, attempt + 1);
    Ok(())
}
fn operation(data: &WorkingReturnData, active: &mut Active) -> Result<()> {
    ensure(
        !active.attempted,
        "returned unknown inverse syscall cannot be repeated",
    )?;
    active.attempted = true;
    match active.kind {
        Kind::Selection => data.transaction.restore_selection(),
        Kind::Exchange => data.transaction.locations.exchange_pair(),
        Kind::Working => data
            .transaction
            .locations
            .move_pair(Place::Rollback, Place::Working),
    }
}
fn desired_replacements(
    active: &Active,
    after: &BTreeMap<PathBuf, Directory>,
    data: &WorkingReturnData,
    state: &State,
) -> Result<BTreeMap<PathBuf, BTreeMap<String, Option<labels::Snapshot>>>> {
    let mut result = active
        .parents
        .iter()
        .map(|p| (p.path.clone(), BTreeMap::new()))
        .collect::<BTreeMap<_, _>>();
    let node = |working: bool| -> Result<labels::Snapshot> {
        let matches = data
            .nodes
            .iter()
            .filter(|n| {
                n.working == working
                    && FileType::from_raw_mode(labels::snapshot_identity(&n.current).mode)
                        == FileType::Directory
                    && if working {
                        n.logical == Path::new(ORIGINAL)
                    } else {
                        n.logical == data.sources.retained().directory.path
                    }
            })
            .collect::<Vec<_>>();
        ensure(
            matches.len() == 1,
            "returned inverse lost its exact held directory role",
        )?;
        labels::snapshot(&matches[0].file)
    };
    let insert = |out: &mut BTreeMap<PathBuf, BTreeMap<String, Option<labels::Snapshot>>>,
                  parent: &Path,
                  name: &str,
                  value: Option<labels::Snapshot>|
     -> Result<()> {
        ensure(
            out.get_mut(parent)
                .ok_or("returned operation parent outside its actual pair")?
                .insert(name.into(), value)
                .is_none(),
            "duplicate returned rename member",
        )
    };
    match active.kind {
        Kind::Selection => {
            let candidate = data
                .nodes
                .iter()
                .find(|n| n.logical == Path::new(SELECTED))
                .ok_or("returned selected FD missing")?;
            insert(
                &mut result,
                Path::new(SELECTED).parent().unwrap(),
                "selected.json",
                state
                    .original
                    .as_ref()
                    .map(|o| labels::snapshot(&o.file))
                    .transpose()?,
            )?;
            insert(
                &mut result,
                data.sources.work(),
                PENDING,
                Some(labels::snapshot(&candidate.file)?),
            )?;
        }
        Kind::Exchange => {
            insert(
                &mut result,
                Path::new(ORIGINAL).parent().unwrap(),
                "data",
                Some(node(false)?),
            )?;
            insert(
                &mut result,
                data.sources.work(),
                ROLLBACK,
                Some(node(true)?),
            )?;
        }
        Kind::Working => {
            insert(&mut result, data.sources.work(), ROLLBACK, None)?;
            insert(
                &mut result,
                Path::new(WORKING).parent().unwrap(),
                Path::new(WORKING).file_name().unwrap().to_str().unwrap(),
                Some(node(true)?),
            )?;
        }
    }
    // Moving the rollback directory out of the private work also changes the
    // work directory's own F9, which is a member of the other held parent.
    for (path, directory) in after {
        if let Some(parent) = path.parent().filter(|p| result.contains_key(*p)) {
            let name = path
                .file_name()
                .and_then(|n| n.to_str())
                .ok_or("returned nested parent name")?;
            ensure(
                result
                    .get_mut(parent)
                    .unwrap()
                    .insert(name.into(), Some(directory.snapshot.clone()))
                    .is_none(),
                "returned nested parent overlaps the actual moved member",
            )?;
        }
    }
    Ok(result)
}
fn reconcile(
    data: &mut WorkingReturnData,
    state: &mut State,
    window: &WorkingReturnQuiescence,
    active: &mut Active,
) -> Result<bool> {
    window.verify_window_custody()?;
    data.sources.revalidate_custody()?;
    data.retirement.revalidate()?;
    let observed = data.transaction.observe(true)?;
    if active.after.is_none() && observed == active.before_state {
        ensure(
            data.nodes
                .iter()
                .map(|n| labels::snapshot(&n.file))
                .collect::<Result<Vec<_>>>()?
                == active.nodes
                && state
                    .original
                    .as_ref()
                    .map(|o| labels::snapshot(&o.file))
                    .transpose()?
                    == active.original,
            "known-no-effect returned rename changed one held inode",
        )?;
        for parent in &active.parents {
            ensure(
                observe_directory(&parent.file)? == parent.before,
                "known-no-effect returned rename changed a parent",
            )?;
        }
        let value = json!({"schema":"droidloom.working-returned-data-rename-result.v1","intent":active.intent,
            "candidate_id":data.sources.candidate(),"outcome":"known-no-effect","actual_state":format!("{observed:?}")});
        let pin = state
            .slots
            .get_mut(&format!(
                "{}-{:02}-RESULT.json",
                active.kind.name(),
                active.attempt
            ))
            .unwrap()
            .publish(&value)?;
        state.completed.push(pin);
        return Ok(false);
    }
    ensure(
        observed == active.after_state,
        "returned inverse has an unknown layout; no rename replay is permitted",
    )?;
    if active.after.is_none() {
        let mut after = BTreeMap::new();
        for parent in &active.parents {
            parent.file.sync_all()?;
            after.insert(parent.path.clone(), observe_directory(&parent.file)?);
        }
        let replacements = desired_replacements(active, &after, data, state)?;
        for parent in &active.parents {
            parent_delta(
                &parent.before,
                &after[&parent.path],
                &replacements[&parent.path],
            )?;
        }
        let current = data
            .nodes
            .iter()
            .map(|n| labels::snapshot(&n.file))
            .collect::<Result<Vec<_>>>()?;
        for ((node, before), now) in data.nodes.iter().zip(&active.nodes).zip(&current) {
            if let Some(parent) = active.parents.iter().find(|p| p.path == node.logical) {
                ensure(
                    *before == parent.before.snapshot && *now == after[&parent.path].snapshot,
                    "returned data parent lost its actual causal delta",
                )?;
            } else {
                let renamed = match active.kind {
                    Kind::Selection => node.logical == Path::new(SELECTED),
                    Kind::Exchange => {
                        node.logical == Path::new(ORIGINAL)
                            || node.logical == data.sources.retained().directory.path
                    }
                    Kind::Working => node.logical == Path::new(ORIGINAL),
                };
                if renamed {
                    same_renamed(before, now)?;
                } else {
                    ensure(
                        before == now,
                        "returned inverse changed an unrelated held inode",
                    )?;
                }
            }
        }
        let original = state
            .original
            .as_ref()
            .map(|o| labels::snapshot(&o.file))
            .transpose()?;
        match (&active.original, &original) {
            (Some(a), Some(b)) if active.kind == Kind::Selection => same_renamed(a, b)?,
            (a, b) => ensure(a == b, "returned pair operation changed original selection")?,
        }
        let result = json!({"schema":"droidloom.working-returned-data-rename-result.v1","intent":active.intent,
            "candidate_id":data.sources.candidate(),"outcome":"completed","actual_state":format!("{observed:?}"),
            "parents":after,"held_nodes":current,"original_selection":original,
            "actual_directory_fsyncs":active.parents.iter().map(|p|&p.path).collect::<Vec<_>>(),
            "original_images_written":false,"original_images_synchronized":false});
        // Only this exact held operation may advance those snapshots. Image
        // identities, generations, hashes and descriptors never change here.
        for (node, actual) in data.nodes.iter_mut().zip(current) {
            node.current = actual;
        }
        if let (Some(held), Some(snapshot)) = (&mut state.original, original) {
            held.snapshot = snapshot;
        }
        active.after = Some(result);
    }
    fence(data, state, window)?;
    let pin = state
        .slots
        .get_mut(&format!(
            "{}-{:02}-RESULT.json",
            active.kind.name(),
            active.attempt
        ))
        .unwrap()
        .publish(active.after.as_ref().unwrap())?;
    if !state.completed.iter().any(|p| same_pin(p, &pin)) {
        state.completed.push(pin);
    }
    fence(data, state, window)?;
    Ok(true)
}
fn run(
    data: &mut WorkingReturnData,
    state: &mut State,
    window: &WorkingReturnQuiescence,
) -> Result<FilePin> {
    if let Some(mut active) = state.active.take() {
        let result = reconcile(data, state, window, &mut active);
        if result.is_err() {
            state.active = Some(active);
        }
        result?;
    }
    fence(data, state, window)?;
    loop {
        let observed = data.transaction.observe(true)?;
        let kind = match observed {
            (Layout::Switched, SelectionState::Candidate) => Kind::Selection,
            (Layout::Switched, SelectionState::Original) => Kind::Exchange,
            (Layout::Staged, SelectionState::Original) => Kind::Working,
            (Layout::Ready, SelectionState::Original) => break,
            _ => return Err("returned inverse observed an unsupported data state".into()),
        };
        prepare(data, state, window, kind)?;
        let mut active = state
            .active
            .take()
            .ok_or("prepared returned inverse lost its actual pending operation")?;
        fence(data, state, window)?;
        let command = operation(data, &mut active);
        let actual = reconcile(data, state, window, &mut active);
        match actual {
            Ok(true) => {}
            Ok(false) => {
                return Err(command.err().unwrap_or_else(|| {
                    "returned inverse syscall produced no actual effect".into()
                }));
            }
            Err(e) => {
                state.active = Some(active);
                return Err(e);
            }
        }
        // An acknowledged syscall error is retained in its actual readback;
        // completed is still a real completed rename, never sent a second time.
    }
    fence(data, state, window)?;
    data.revalidate()?;
    let (original, working) = data.transaction.current_pairs(Layout::Ready)?;
    let value = json!({"schema":"droidloom.working-original-pair-returned.v1","candidate_id":data.sources.candidate(),
        "actual_data_retirement":data.report(),"actual_label_restoration":state.labels.report(),
        "actual_boot_retirement":data.retirement.report_pin(),"actual_owner":data.sources.owner().evidence(),
        "actual_inverse_operations":state.completed,"original":original,"working":working,
        "original_selection":data.transaction.locations.public_file(&data.transaction.locations.selected_parent,
            &data.transaction.locations.selected_name)?,"original_complete_hashes":data.evidence["original_complete_hashes"],
        "original_data_restored":true,"original_images_written":false,"original_images_synchronized":false,
        "actual_four_readonly_backing_locks_owned":true,"production_ready":false});
    let pin = state
        .slots
        .get_mut("RESTORED.json")
        .unwrap()
        .publish(&value)?;
    state.report = Some(pin.clone());
    fence(data, state, window)?;
    Ok(pin)
}
pub(super) fn restore(
    data: &mut WorkingReturnData,
    window: &WorkingReturnQuiescence,
) -> Result<FilePin> {
    let mut state = data
        .restoration
        .take()
        .ok_or("returned inverse requires the actual completed label capability")?;
    let result = run(data, &mut state, window);
    data.restoration = Some(state);
    result
}
pub(super) fn verify(data: &WorkingReturnData) -> Result<()> {
    let state = data
        .restoration
        .as_ref()
        .ok_or("returned original pair has no actual inverse owner")?;
    ensure(
        state.report.is_some()
            && state.active.is_none()
            && data.transaction.observe(true)? == (Layout::Ready, SelectionState::Original),
        "returned original pair has not completed every actual inverse operation",
    )?;
    guard_original(data, state)?;
    for slot in state.slots.values().filter(|s| s.sealed.is_some()) {
        slot.revalidate()?;
    }
    data.revalidate()
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn actual_inverse_exchange_requires_all_parent_members_and_preserves_held_contents()
    -> Result<()> {
        let tmp = tempfile::Builder::new()
            .prefix(".p4-return-pair-delta-")
            .tempdir_in(std::env::current_dir()?)?;
        for name in ["public", "private"] {
            std::fs::create_dir(tmp.path().join(name))?;
        }
        std::fs::write(tmp.path().join("public/value"), b"original named bytes")?;
        std::fs::write(tmp.path().join("private/value"), b"candidate named bytes")?;
        std::fs::write(tmp.path().join("public/unrelated"), b"must remain exact")?;
        let a = File::open(tmp.path().join("public"))?;
        let b = File::open(tmp.path().join("private"))?;
        let old_a = observe_directory(&a)?;
        let old_b = observe_directory(&b)?;
        let f = File::open(tmp.path().join("public/value"))?;
        let g = File::open(tmp.path().join("private/value"))?;
        rustix::fs::renameat_with(&a, "value", &b, "value", RenameFlags::EXCHANGE)?;
        a.sync_all()?;
        b.sync_all()?;
        let new_a = observe_directory(&a)?;
        let new_b = observe_directory(&b)?;
        same_renamed(&old_a.members["value"], &new_b.members["value"])?;
        same_renamed(&old_b.members["value"], &new_a.members["value"])?;
        parent_delta(
            &old_a,
            &new_a,
            &BTreeMap::from([("value".into(), Some(new_a.members["value"].clone()))]),
        )?;
        parent_delta(
            &old_b,
            &new_b,
            &BTreeMap::from([("value".into(), Some(new_b.members["value"].clone()))]),
        )?;
        assert_eq!(read_small(&f, 1024)?, b"original named bytes");
        assert_eq!(read_small(&g, 1024)?, b"candidate named bytes");
        std::fs::write(tmp.path().join("public/unrelated"), b"foreign mutation")?;
        assert!(
            parent_delta(
                &old_a,
                &observe_directory(&a)?,
                &BTreeMap::from([("value".into(), Some(new_a.members["value"].clone()))])
            )
            .is_err()
        );
        Ok(())
    }
    #[test]
    fn actual_directory_return_requires_exact_links_and_nested_parent_delta() -> Result<()> {
        let tmp = tempfile::Builder::new()
            .prefix(".p4-return-dir-delta-")
            .tempdir_in(std::env::current_dir()?)?;
        let root = File::open(tmp.path())?;
        std::fs::create_dir(tmp.path().join("work"))?;
        std::fs::create_dir(tmp.path().join("work/rollback"))?;
        std::fs::write(
            tmp.path().join("work/rollback/retained"),
            b"same original body",
        )?;
        let work = File::open(tmp.path().join("work"))?;
        let before_root = observe_directory(&root)?;
        let before_work = observe_directory(&work)?;
        rustix::fs::renameat_with(&work, "rollback", &root, "returned", RenameFlags::NOREPLACE)?;
        work.sync_all()?;
        root.sync_all()?;
        let after_root = observe_directory(&root)?;
        let after_work = observe_directory(&work)?;
        same_renamed(
            &before_work.members["rollback"],
            &after_root.members["returned"],
        )?;
        parent_delta(
            &before_work,
            &after_work,
            &BTreeMap::from([("rollback".into(), None)]),
        )?;
        parent_delta(
            &before_root,
            &after_root,
            &BTreeMap::from([
                (
                    "returned".into(),
                    Some(after_root.members["returned"].clone()),
                ),
                ("work".into(), Some(after_work.snapshot.clone())),
            ]),
        )?;
        let mut wrong = after_root.clone();
        wrong.members.remove("returned");
        assert!(
            parent_delta(
                &before_root,
                &wrong,
                &BTreeMap::from([("work".into(), Some(after_work.snapshot.clone()))])
            )
            .is_err()
        );
        Ok(())
    }
}
