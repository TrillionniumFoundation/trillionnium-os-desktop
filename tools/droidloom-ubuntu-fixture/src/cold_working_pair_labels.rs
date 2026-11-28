//! Actual current checkpoints for the continuously held H2 working pair.
//! The old immutable pair intent is retained unchanged. Only a completed label
//! batch can advance these checkpoints; a directory move has its separate
//! PendingStep witness. No saved receipt or caller flag constructs this state.
use super::*;

pub(super) struct PairLabelState {
    pub(super) working: PairRecord,
    pub(super) pending: PublicFile,
    pub(super) pending_snapshot: labels::Snapshot,
    directory: File,
    members: BTreeMap<String, File>,
}

pub(super) struct PairLabelAdoption {
    working: PairRecord,
    pending: PublicFile,
    pending_snapshot: labels::Snapshot,
}

pub(super) fn changed_snapshot(
    batch: &labels::WorkingLabelBatch,
    path: &Path,
    before: &labels::Snapshot,
    after: &labels::Snapshot,
) -> Result<()> {
    if before == after {
        return Ok(());
    }
    let record = batch
        .records()
        .iter()
        .find(|record| record.paths().iter().any(|known| known == path))
        .ok_or("working pair or parent changed outside this actual label batch")?;
    record.require_snapshot_transition(path, before, after)
}

impl PairLabelState {
    pub(super) fn capture(tx: &DataTransaction, pending: &File) -> Result<Self> {
        ensure(
            tx.observe(false)? == (Layout::Switched, SelectionState::Original),
            "working label custody requires the actual completed private exchange",
        )?;
        let working = tx
            .locations
            .pair(Place::Original, &tx.intent.working, false)?;
        ensure(
            working
                .members
                .keys()
                .map(String::as_str)
                .eq(WORKING_MEMBERS),
            "working label target roster differs from the nine admitted members",
        )?;
        let (parent, name) = tx.locations.at(Place::Original);
        let directory = open_at(parent, name, true)?;
        ensure(
            labels::snapshot(&directory)? == working.directory_label_identity,
            "working label directory changed while retaining its descriptor",
        )?;
        let mut members = BTreeMap::new();
        for name in WORKING_MEMBERS {
            let held = if let Some(index) = IMAGES.iter().position(|image| image == &name) {
                // Preserve the same locked image open-file-description.
                tx.images
                    .get(index + 2)
                    .ok_or("working image OFD absent")?
                    .0
                    .try_clone()?
            } else {
                open_at(&directory, name, false)?
            };
            ensure(
                labels::snapshot(&held)? == working.members[name].label_identity,
                "working member changed while its actual descriptor was retained",
            )?;
            members.insert(name.to_owned(), held);
        }
        let pending_snapshot = labels::snapshot(pending)?;
        ensure(
            labels::snapshot_identity(&pending_snapshot) == &tx.intent.new_selection.identity,
            "working pending selection changed before label custody",
        )?;
        let value = Self {
            working,
            pending: tx.intent.new_selection.clone(),
            pending_snapshot,
            directory,
            members,
        };
        value.guard_files(pending, None)?;
        Ok(value)
    }

    fn guard_files(&self, pending: &File, movement: Option<&PendingStep>) -> Result<()> {
        let actual_directory = labels::snapshot(&self.directory)?;
        if actual_directory != self.working.directory_label_identity {
            ensure(
                movement.is_some(),
                "working directory changed outside its actual move",
            )?;
            ensure(
                labels::only_ctime_changed(
                    &self.working.directory,
                    labels::snapshot_identity(&actual_directory),
                ),
                "working directory move changed a non-ctime field",
            )?;
            labels::verify_data_snapshot(
                &self.working.directory_label_identity,
                &actual_directory,
                false,
            )?;
        }
        ensure(
            list(&self.directory)? == WORKING_MEMBERS.map(str::to_owned).to_vec()
                && self.members.keys().map(String::as_str).eq(WORKING_MEMBERS),
            "held working member roster changed",
        )?;
        for (name, held) in &self.members {
            let expected = &self.working.members[name];
            ensure(
                labels::snapshot(held)? == expected.label_identity
                    && named(&self.directory, name)? == Some(expected.identity.clone()),
                "held or named working member changed",
            )?;
            if let Some(hash) = &expected.sha256 {
                ensure(
                    fs::digest(&read_small(held, 64 * 1024)?) == *hash,
                    "working comparison member bytes changed",
                )?;
            }
            ensure(
                labels::snapshot(held)? == expected.label_identity,
                "working member changed during complete readback",
            )?;
        }
        ensure(
            labels::snapshot(pending)? == self.pending_snapshot
                && fs::digest(&read_small(pending, 16384)?) == self.pending.sha256
                && labels::snapshot(pending)? == self.pending_snapshot,
            "held pending selection left its actual labelled checkpoint",
        )?;
        ensure(
            labels::snapshot(&self.directory)? == actual_directory,
            "working directory changed across its held-member readback",
        )
    }

    pub(super) fn observe(
        &self,
        tx: &DataTransaction,
        pending: &File,
        movement: Option<&PendingStep>,
    ) -> Result<(Layout, SelectionState)> {
        tx.locations.validate()?;
        tx.validate_intent()?;
        tx.require_writer_locks()?;
        self.guard_files(pending, movement)?;
        for (index, (held, initial, working)) in tx.images.iter().enumerate() {
            let expected = if *working {
                &self.working.members[IMAGES[index % 2]].identity
            } else {
                initial
            };
            ensure(
                fs::stat(held)? == *expected,
                "held pair image changed outside its label batch",
            )?;
            rustix::fs::flock(held, FlockOperation::NonBlockingLockExclusive)?;
        }
        let at = |place| {
            let (parent, name) = tx.locations.at(place);
            named(parent, name)
        };
        let original = at(Place::Original)?.ok_or("original data name disappeared")?;
        let working = at(Place::Working)?;
        let rollback = at(Place::Rollback)?;
        let old = &tx.intent.original;
        let new = &self.working;
        let layout = if inode(&original, &old.directory)
            && working.as_ref().is_some_and(|id| inode(id, &new.directory))
            && rollback.is_none()
        {
            tx.locations.pair(Place::Original, old, false)?;
            tx.locations.pair(Place::Working, new, false)?;
            Layout::Ready
        } else if inode(&original, &old.directory)
            && working.is_none()
            && rollback
                .as_ref()
                .is_some_and(|id| inode(id, &new.directory))
        {
            tx.locations.pair(Place::Original, old, false)?;
            tx.locations.pair(Place::Rollback, new, false)?;
            Layout::Staged
        } else if inode(&original, &new.directory)
            && working.is_none()
            && rollback
                .as_ref()
                .is_some_and(|id| inode(id, &old.directory))
        {
            tx.locations.pair(Place::Original, new, false)?;
            tx.locations.pair(Place::Rollback, old, false)?;
            Layout::Switched
        } else {
            return Err("labelled pair left the exact three source-owned directory layouts".into());
        };
        let selected = tx
            .locations
            .public_file(&tx.locations.selected_parent, &tx.locations.selected_name)?;
        let private = tx.locations.public_file(&tx.locations.work, PENDING)?;
        let selection = if matches_public(selected.as_ref(), tx.intent.old_selection.as_ref())
            && matches_public(private.as_ref(), Some(&self.pending))
        {
            SelectionState::Original
        } else if matches_public(selected.as_ref(), Some(&self.pending))
            && matches_public(private.as_ref(), tx.intent.old_selection.as_ref())
        {
            SelectionState::Candidate
        } else {
            return Err("labelled selection no longer names the exact owned inodes".into());
        };
        ensure(
            selection == SelectionState::Original || layout == Layout::Switched,
            "working selection preceded its actual directory exchange",
        )?;
        Ok((layout, selection))
    }

    pub(super) fn stage_batch(
        &self,
        pending: &File,
        batch: &labels::WorkingLabelBatch,
    ) -> Result<PairLabelAdoption> {
        let mut working = self.working.clone();
        let directory = labels::snapshot(&self.directory)?;
        changed_snapshot(
            batch,
            Path::new(ORIGINAL),
            &working.directory_label_identity,
            &directory,
        )?;
        ensure(
            list(&self.directory)? == WORKING_MEMBERS.map(str::to_owned).to_vec(),
            "normal label application changed working member names",
        )?;
        working.directory = labels::snapshot_identity(&directory).clone();
        working.directory_label_identity = directory;
        for (name, held) in &self.members {
            let member = working
                .members
                .get_mut(name)
                .ok_or("working member role absent")?;
            let after = labels::snapshot(held)?;
            changed_snapshot(
                batch,
                &Path::new(ORIGINAL).join(name),
                &member.label_identity,
                &after,
            )?;
            ensure(
                named(&self.directory, name)? == Some(labels::snapshot_identity(&after).clone()),
                "working member label no longer belongs to its held named inode",
            )?;
            if let Some(expected) = &member.sha256 {
                ensure(
                    fs::digest(&read_small(held, 64 * 1024)?) == *expected,
                    "labelled working proof member changed its exact bytes",
                )?;
            }
            ensure(
                labels::snapshot(held)? == after,
                "working member moved during batch readback",
            )?;
            member.identity = labels::snapshot_identity(&after).clone();
            member.label_identity = after;
        }
        let pending_snapshot = labels::snapshot(pending)?;
        changed_snapshot(
            batch,
            Path::new(SELECTED),
            &self.pending_snapshot,
            &pending_snapshot,
        )?;
        ensure(
            fs::digest(&read_small(pending, 16384)?) == self.pending.sha256
                && labels::snapshot(pending)? == pending_snapshot
                && labels::snapshot(&self.directory)? == working.directory_label_identity,
            "working label batch changed selection bytes or an observed inode",
        )?;
        let value = PairLabelAdoption {
            working,
            pending: PublicFile {
                identity: labels::snapshot_identity(&pending_snapshot).clone(),
                sha256: self.pending.sha256.clone(),
            },
            pending_snapshot,
        };
        Ok(value)
    }

    pub(super) fn adopt(&mut self, update: PairLabelAdoption) {
        self.working = update.working;
        self.pending = update.pending;
        self.pending_snapshot = update.pending_snapshot;
    }

    pub(super) fn after_move(&mut self, movement: &PendingStep, pending: &File) -> Result<()> {
        self.guard_files(pending, Some(movement))?;
        let current = labels::snapshot(&self.directory)?;
        self.working.directory = labels::snapshot_identity(&current).clone();
        self.working.directory_label_identity = current;
        self.guard_files(pending, None)
    }

    pub(super) fn targets(&self, pending: &File) -> Result<Vec<(PathBuf, File)>> {
        self.guard_files(pending, None)?;
        let mut rows = vec![(PathBuf::from(ORIGINAL), self.directory.try_clone()?)];
        for (name, held) in &self.members {
            rows.push((Path::new(ORIGINAL).join(name), held.try_clone()?));
        }
        rows.push((PathBuf::from(SELECTED), pending.try_clone()?));
        ensure(
            rows.len() == 11,
            "working labels require ten pair inodes and one selection",
        )?;
        self.guard_files(pending, None)?;
        Ok(rows)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::{OpenOptionsExt, PermissionsExt};

    struct ActualPair {
        _root: tempfile::TempDir,
        path: PathBuf,
        pending_path: PathBuf,
        state: PairLabelState,
        pending: File,
    }

    fn actual_pair() -> ActualPair {
        assert_eq!(rustix::process::geteuid().as_raw(), 0);
        let root = tempfile::Builder::new()
            .prefix(".p4-working-pair-label-")
            .tempdir_in(std::env::current_dir().unwrap())
            .unwrap();
        let path = root.path().join("data");
        std::fs::create_dir(&path).unwrap();
        std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o700)).unwrap();
        let directory = File::open(&path).unwrap();
        let mut members = BTreeMap::new();
        let mut records = BTreeMap::new();
        for name in WORKING_MEMBERS {
            let bytes = format!("actual test member {name}\n").into_bytes();
            let mut writer = std::fs::OpenOptions::new()
                .create_new(true)
                .write(true)
                .mode(if image(name) { 0o600 } else { 0o400 })
                .open(path.join(name))
                .unwrap();
            writer.write_all(&bytes).unwrap();
            writer.sync_all().unwrap();
            drop(writer);
            let held = open_at(&directory, name, false).unwrap();
            let snap = labels::snapshot(&held).unwrap();
            let identity = labels::snapshot_identity(&snap).clone();
            records.insert(
                name.to_owned(),
                crate::cold_original_data::Member {
                    identity,
                    sha256: (!image(name)).then(|| fs::digest(&bytes)),
                    label_identity: snap,
                },
            );
            members.insert(name.to_owned(), held);
        }
        let pending_path = root.path().join("pending");
        std::fs::write(&pending_path, b"{\"candidate\":\"actual-test\"}\n").unwrap();
        std::fs::set_permissions(&pending_path, std::fs::Permissions::from_mode(0o600)).unwrap();
        let pending = File::open(&pending_path).unwrap();
        let pending_snapshot = labels::snapshot(&pending).unwrap();
        let dir_snapshot = labels::snapshot(&directory).unwrap();
        let state = PairLabelState {
            working: PairRecord {
                directory: labels::snapshot_identity(&dir_snapshot).clone(),
                directory_label_identity: dir_snapshot,
                members: records,
            },
            pending: PublicFile {
                identity: labels::snapshot_identity(&pending_snapshot).clone(),
                sha256: fs::digest(&read_small(&pending, 16384).unwrap()),
            },
            pending_snapshot,
            directory,
            members,
        };
        state.guard_files(&pending, None).unwrap();
        ActualPair {
            _root: root,
            path,
            pending_path,
            state,
            pending,
        }
    }

    #[test]
    fn working_pair_label_readback_keeps_actual_fds_and_exact_eleven_targets() {
        let pair = actual_pair();
        for _ in 0..2 {
            pair.state.guard_files(&pair.pending, None).unwrap();
            let targets = pair.state.targets(&pair.pending).unwrap();
            let expected = std::iter::once(PathBuf::from(ORIGINAL))
                .chain(WORKING_MEMBERS.map(|name| Path::new(ORIGINAL).join(name)))
                .chain(std::iter::once(PathBuf::from(SELECTED)))
                .collect::<Vec<_>>();
            assert_eq!(
                targets.iter().map(|(p, _)| p.clone()).collect::<Vec<_>>(),
                expected
            );
            assert_eq!(
                labels::snapshot(&targets[0].1).unwrap(),
                pair.state.working.directory_label_identity
            );
            for ((_, held), name) in targets[1..10].iter().zip(WORKING_MEMBERS) {
                assert_eq!(
                    labels::snapshot(held).unwrap(),
                    pair.state.working.members[name].label_identity
                );
                assert_eq!(
                    rustix::fs::fcntl_getfl(held).unwrap() & OFlags::ACCMODE,
                    OFlags::RDONLY
                );
            }
            assert_eq!(
                labels::snapshot(&targets[10].1).unwrap(),
                pair.state.pending_snapshot
            );
        }
    }

    #[test]
    fn working_pair_label_rejects_same_bytes_named_inode_replacement() {
        let pair = actual_pair();
        let name = "WORKING-COPY.json";
        let bytes = std::fs::read(pair.path.join(name)).unwrap();
        let old_inode = fs::stat(&pair.state.members[name]).unwrap();
        std::fs::remove_file(pair.path.join(name)).unwrap();
        std::fs::write(pair.path.join(name), &bytes).unwrap();
        std::fs::set_permissions(pair.path.join(name), std::fs::Permissions::from_mode(0o400))
            .unwrap();
        assert_ne!(
            named(&pair.state.directory, name).unwrap().unwrap().ino,
            old_inode.ino
        );
        assert!(pair.state.guard_files(&pair.pending, None).is_err());
        assert!(pair.state.targets(&pair.pending).is_err());
    }

    #[test]
    fn working_pair_label_rejects_same_length_proof_mutation() {
        let pair = actual_pair();
        let file = pair.path.join("INTENT.json");
        let mut bytes = std::fs::read(&file).unwrap();
        bytes[0] ^= 1;
        std::fs::write(&file, &bytes).unwrap();
        assert_eq!(
            bytes.len() as u64,
            pair.state.working.members["INTENT.json"].identity.size
        );
        assert!(pair.state.guard_files(&pair.pending, None).is_err());
    }

    #[test]
    fn working_pair_label_rejects_unrelated_extended_attribute() {
        let pair = actual_pair();
        rustix::fs::fsetxattr(
            &pair.state.members["metadata.img"],
            "user.p4-working-pair-label-negative",
            b"unrelated",
            rustix::fs::XattrFlags::empty(),
        )
        .unwrap();
        assert!(pair.state.guard_files(&pair.pending, None).is_err());
    }

    #[test]
    fn working_pair_label_rejects_pending_selection_byte_change() {
        let pair = actual_pair();
        let mut bytes = std::fs::read(&pair.pending_path).unwrap();
        bytes[2] ^= 1;
        std::fs::write(&pair.pending_path, &bytes).unwrap();
        assert!(pair.state.guard_files(&pair.pending, None).is_err());
    }

    #[test]
    fn working_pair_label_rejects_extra_name_and_directory_mode_change() {
        let pair = actual_pair();
        std::fs::write(pair.path.join("unowned"), b"extra").unwrap();
        assert!(pair.state.guard_files(&pair.pending, None).is_err());
        let pair = actual_pair();
        std::fs::set_permissions(&pair.path, std::fs::Permissions::from_mode(0o755)).unwrap();
        assert!(pair.state.guard_files(&pair.pending, None).is_err());
    }
}
