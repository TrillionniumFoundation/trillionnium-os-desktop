//! Reopen the finite published file roles under a fresh returned owner.
//! Historical records only identify the original and candidate generations.
//! Every node and parent below is freshly opened and held before any inverse.
use super::*;
use crate::cold_original_data::labels::WorkingReturnedLabelHistory;
use std::collections::BTreeSet;

fn same_generation(a: &Node, b: &Node) -> bool {
    a.identity.dev == b.identity.dev
        && a.identity.ino == b.identity.ino
        && a.handle_type == b.handle_type
        && a.handle == b.handle
}
fn current_node(
    path: &Path,
    directory: bool,
    retired: &BTreeMap<PathBuf, PathBuf>,
) -> Result<Option<HeldNode>> {
    if path.parent().is_some_and(|p| retired.contains_key(p)) {
        absent(path, directory, retired)?;
        return Ok(None);
    }
    HeldNode::open(path, directory)
}
fn restored_prepared(expected: &Node, now: &Node, directory: bool, value: &Value) -> Result<()> {
    let label_identity: crate::model::Identity = serde_json::from_value(value["identity"].clone())?;
    let label_attributes: BTreeMap<String, Vec<u8>> =
        serde_json::from_value(value["attributes"].clone())?;
    let attributes = label_attributes
        .into_iter()
        .map(|(k, v)| (k, hex::encode(v)))
        .collect();
    let mut comparison = expected.clone();
    comparison.identity = label_identity;
    comparison.attributes = attributes;
    ensure(
        same_generation(expected, now)
            && comparison.handle_type
                == serde_json::from_value::<i32>(value["handle"]["handle_type"].clone())?
            && comparison.handle
                == hex::encode(serde_json::from_value::<Vec<u8>>(
                    value["handle"]["bytes"].clone(),
                )?)
            && comparison.sha256 == now.sha256
            && comparison.link == now.link
            && comparison.attributes == now.attributes,
        "returned candidate body, inode generation or restored attributes changed",
    )?;
    if directory {
        let a = &comparison.identity;
        let b = &now.identity;
        ensure(
            (a.dev, a.ino, a.mode, a.uid, a.gid) == (b.dev, b.ino, b.mode, b.uid, b.gid)
                && b.nlink >= 2,
            "returned created directory lost its source-owned type or authority",
        )
    } else {
        ensure(
            same_except_ctime(&comparison, now),
            "returned candidate metadata changed beyond its owned inverse rename",
        )
    }
}

impl Transaction {
    /// The caller supplies its compiled fixed roster and fences this entire
    /// factory with the fresh owner, four image locks and real frozen groups.
    /// This method provides no public path-selectable mutation entrypoint.
    pub(in crate::cold_original_qualification::configurations) fn reopen_returned(
        work: PathBuf,
        candidate: String,
        required: &BTreeMap<PathBuf, Payload>,
        optional_directories: &BTreeSet<PathBuf>,
        retained: &BTreeSet<PathBuf>,
        labels: &WorkingReturnedLabelHistory,
    ) -> Result<Self> {
        labels.revalidate()?;
        let value = Self::reopen_comparisons(
            work,
            candidate,
            required,
            optional_directories,
            retained,
            &|path| labels.snapshot_value_at(path),
        )?;
        labels.revalidate()?;
        Ok(value)
    }
    /// A source-owned service published before the label plan can be retired
    /// after exact original labels return. Historical bytes select no paths:
    /// the caller supplies its closed normal two-member unit recipe, and this
    /// factory newly holds every matching generation and current parent.
    pub(in crate::cold_original_qualification::configurations) fn reopen_preserved_birth(
        work: PathBuf,
        candidate: String,
        required: &BTreeMap<PathBuf, Payload>,
    ) -> Result<Self> {
        ensure(
            required.len() == 2,
            "owned recovery service has exactly two file roles",
        )?;
        let pin = files::pin_file(&work.join("PUBLISHED.json"))?;
        let seal = SealedInput::open(&pin)?;
        let body: Value = serde_json::from_slice(&seal.read()?)?;
        let rows = body["steps"]
            .as_array()
            .ok_or("owned service publication lacks rows")?;
        let mut snapshots = BTreeMap::new();
        for row in rows {
            let path: PathBuf = serde_json::from_value(row["target"].clone())?;
            ensure(
                row["original"].is_null()
                    && row["directory"] == false
                    && required.contains_key(&path),
                "owned service cannot replace or retire an original host file",
            )?;
            let node: Node = serde_json::from_value(row["candidate"].clone())?;
            let attributes = node
                .attributes
                .iter()
                .map(|(k, v)| Ok((k.clone(), hex::decode(v)?)))
                .collect::<Result<BTreeMap<_, _>>>()?;
            ensure(
                snapshots
                    .insert(
                        path,
                        json!({"identity":node.identity,"attributes":attributes,
                "handle":{"handle_type":node.handle_type,"bytes":hex::decode(&node.handle)?}}),
                    )
                    .is_none(),
                "owned service publication repeated a file role",
            )?;
        }
        ensure(
            snapshots.len() == 2,
            "owned service publication omitted a role",
        )?;
        let result = Self::reopen_comparisons(
            work,
            candidate,
            required,
            &BTreeSet::new(),
            &BTreeSet::new(),
            &|path| {
                snapshots
                    .get(path)
                    .cloned()
                    .ok_or_else(|| "owned service snapshot escaped its closed roles".into())
            },
        )?;
        seal.revalidate()?;
        Ok(result)
    }
    fn reopen_comparisons(
        work: PathBuf,
        candidate: String,
        required: &BTreeMap<PathBuf, Payload>,
        optional_directories: &BTreeSet<PathBuf>,
        retained: &BTreeSet<PathBuf>,
        snapshot: &impl Fn(&Path) -> Result<Value>,
    ) -> Result<Self> {
        let directory = fs::Tree::open("/", 0)?.dir(&fs::absolute_string(&work)?)?;
        let id = fs::stat(&directory)?;
        ensure(
            id.uid == 0 && id.gid == 0 && id.mode & 0o7777 == 0o700,
            "returned file transaction lost its source-owned private directory",
        )?;
        let mut names = BTreeSet::new();
        let mut reader = rustix::fs::Dir::read_from(&directory)?;
        for entry in &mut reader {
            let entry = entry?;
            let name = entry.file_name().to_str()?;
            if name.starts_with("item-") {
                ensure(
                    name.len() == 8
                        && name[5..].bytes().all(|b| b.is_ascii_digit())
                        && names.insert(name.to_owned())
                        && names.len() <= 22,
                    "returned publication has an invalid or excessive actual item directory",
                )?;
            }
        }
        ensure(
            !names.is_empty(),
            "returned publication has no actual file intents",
        )?;
        let mut inputs = Vec::new();
        let mut intents = Vec::new();
        let mut roster = BTreeSet::new();
        for (ordinal, name) in names.into_iter().enumerate() {
            ensure(
                name == format!("item-{ordinal:03}"),
                "returned publication has a hole in its source ordinal roster",
            )?;
            let record = work.join(name);
            let pin = files::pin_file(&record.join("INTENT.json"))?;
            let seal = SealedInput::open(&pin)?;
            let intent: Intent = serde_json::from_slice(&seal.read()?)?;
            let directory = intent.purpose_target.is_some();
            ensure(
                intent.schema == "droidloom.working-runtime-file-intent.v1"
                    && intent.candidate_id == candidate
                    && intent.group == "working-runtime"
                    && intent.ordinal == ordinal
                    && intent.logical_path == intent.target
                    && intent.pending == record.join("payload/value")
                    && intent.parent.path
                        == intent.target.parent().ok_or("returned public parent")?
                    && intent.private_parent.path == record.join("payload")
                    && intent.purpose_target == directory.then(|| intent.target.clone())
                    && roster.insert(intent.target.clone()),
                "returned publication intent escaped its exact normal path, ordinal or payload slot",
            )?;
            let expected = required.get(&intent.target);
            ensure(
                expected.is_some() || (directory && optional_directories.contains(&intent.target)),
                "returned publication target is outside its compiled finite roster",
            )?;
            if let Some(expected) = expected {
                ensure(
                    serde_json::to_value(&intent.payload)? == serde_json::to_value(expected)?,
                    "returned file payload differs from its actual normal source pin",
                )?;
            } else {
                ensure(
                    matches!(intent.payload, Payload::Absent),
                    "optional returned parent has a file payload",
                )?;
            }
            ensure(
                !directory
                    || (intent.original.is_none() && matches!(intent.payload, Payload::Absent)),
                "returned directory is not a source-created absent target",
            )?;
            let prepared = intent
                .prepared
                .as_ref()
                .ok_or("returned file has no actual prepared generation")?;
            if let Payload::Regular { source, mode } = &intent.payload {
                ensure(
                    prepared.sha256.as_ref() == Some(&source.sha256)
                        && prepared.identity.size == source.bytes
                        && prepared.identity.mode & 0o7777 == *mode,
                    "returned prepared file is not the complete admitted normal source",
                )?;
            }
            if let Payload::Symlink { target } = &intent.payload {
                ensure(
                    prepared.link.as_ref() == Some(target)
                        && prepared.sha256.is_none()
                        && prepared.identity.mode == 0o120777
                        && prepared.identity.uid == 0
                        && prepared.identity.gid == 0
                        && prepared.identity.nlink == 1,
                    "returned prepared link is not the exact normal literal target",
                )?;
            }
            inputs.push(seal);
            intents.push((record, intent));
        }
        ensure(
            required.keys().all(|p| roster.contains(p))
                && retained.iter().all(|p| roster.contains(p)),
            "returned publication omitted a required normal file or retained evidence directory",
        )?;
        let summary_pin = files::pin_file(&work.join("PUBLISHED.json"))?;
        let summary = SealedInput::open(&summary_pin)?;
        let body: Value = serde_json::from_slice(&summary.read()?)?;
        let rows = body["steps"]
            .as_array()
            .ok_or("returned publication summary lacks steps")?;
        ensure(
            body["schema"] == "droidloom.working-runtime-observed.v1"
                && body["candidate_id"] == candidate
                && body["restored"] == false
                && rows.len() == intents.len(),
            "returned publication is not its actual complete forward result",
        )?;
        let mut result = Self::new(work, candidate);
        // Find source-created parents already retired by an earlier process.
        // Their original inode is absent, so only their exact prepared inode
        // at the fixed private payload name can establish this placement.
        for (_, intent) in &intents {
            if intent.purpose_target.is_some() && !retained.contains(&intent.target) {
                if let Some(node) = HeldNode::open(&intent.pending, true)? {
                    if same_generation(intent.prepared.as_ref().unwrap(), &node.node) {
                        ensure(
                            current_node(&intent.target, true, &result.retired)?.is_none(),
                            "retired normal directory was recreated outside the owned inverse",
                        )?;
                        result
                            .retired
                            .insert(intent.target.clone(), intent.pending.clone());
                    }
                }
            }
        }
        for ((record, intent), row) in intents.into_iter().zip(rows) {
            let directory = intent.purpose_target.is_some();
            ensure(
                row["target"] == serde_json::to_value(&intent.target)?
                    && row["pending"] == serde_json::to_value(&intent.pending)?
                    && row["phase"] == "Published"
                    && row["directory"] == directory,
                "returned forward summary changed a fixed actual file role",
            )?;
            let published: Node = serde_json::from_value(row["candidate"].clone())?;
            let original: Option<Node> = serde_json::from_value(row["original"].clone())?;
            ensure(
                same_generation(intent.prepared.as_ref().unwrap(), &published)
                    && original
                        .as_ref()
                        .zip(intent.original.as_ref())
                        .is_none_or(|(a, b)| same_except_ctime(a, b))
                    && original.is_some() == intent.original.is_some(),
                "returned original or prepared generation changed in the forward record",
            )?;
            let public = current_node(&intent.target, directory, &result.retired)?;
            let private = HeldNode::open(&intent.pending, directory)?;
            let published_role = public
                .as_ref()
                .is_some_and(|n| same_generation(&published, &n.node));
            let restored_role = private
                .as_ref()
                .is_some_and(|n| same_generation(&published, &n.node));
            ensure(
                published_role != restored_role,
                "returned candidate has no unique real current role",
            )?;
            ensure(
                !retained.contains(&intent.target) || published_role,
                "retirement evidence must remain at its actual retained public names",
            )?;
            let (prepared, original_current, phase) = if published_role {
                (public.unwrap(), private, Phase::Published)
            } else {
                (private.unwrap(), public, Phase::Restored)
            };
            restored_prepared(
                &published,
                &prepared.node,
                directory,
                &snapshot(&intent.target)?,
            )?;
            ensure(
                original
                    .as_ref()
                    .zip(original_current.as_ref())
                    .is_none_or(|(a, b)| same_except_ctime(a, &b.node))
                    && original.is_some() == original_current.is_some(),
                "returned original is not its actually retained full preimage",
            )?;
            let mut attempts = 0;
            for n in 0..4 {
                let path = record.join(format!("RESTORE-INTENT-{n:02}.json"));
                match std::fs::symlink_metadata(&path) {
                    Ok(_) => {
                        ensure(n == attempts, "returned reverse attempts contain a hole")?;
                        let seal = SealedInput::open(&files::pin_file(&path)?)?;
                        let value: Value = serde_json::from_slice(&seal.read()?)?;
                        ensure(
                            value["schema"] == "droidloom.working-runtime-reverse-intent.v1"
                                && value["candidate_id"] == result.candidate
                                && value["ordinal"] == intent.ordinal,
                            "returned previous inverse intent belongs to another fixed item",
                        )?;
                        result.seals.push(seal);
                        attempts += 1;
                    }
                    Err(e) if e.kind() == std::io::ErrorKind::NotFound => {}
                    Err(e) => return Err(e.into()),
                }
            }
            if !result.retired.contains_key(&intent.parent.path) {
                result.parents.hold(&intent.parent.path)?;
            }
            result.parents.hold(&intent.private_parent.path)?;
            result.steps.push(Step {
                target: intent.target.clone(),
                pending: intent.pending.clone(),
                record,
                payload: intent.payload.clone(),
                directory,
                prepared,
                original: original_current,
                intent: Some(intent),
                reverse: None,
                reverse_attempts: attempts,
                phase,
            });
        }
        result.seals.extend(inputs);
        result.seals.push(summary);
        result.guard()?;
        Ok(result)
    }
    pub(in crate::cold_original_qualification::configurations) fn all_restored_except(
        &self,
        retained: &BTreeSet<PathBuf>,
    ) -> bool {
        self.steps.iter().all(|s| {
            s.phase == Phase::Restored
                || (retained.contains(&s.target) && s.phase == Phase::Published)
        })
    }
    pub(in crate::cold_original_qualification::configurations) fn returned_evidence(
        &self,
        retained: &BTreeSet<PathBuf>,
    ) -> Result<Value> {
        self.guard()?;
        ensure(
            self.all_restored_except(retained),
            "returned files still have an unfinished non-evidence inverse",
        )?;
        Ok(
            json!({"steps":self.steps.iter().map(|s|json!({"target":s.target,"pending":s.pending,
            "phase":format!("{:?}",s.phase),"candidate":s.prepared.node,"original":s.original.as_ref().map(|n|&n.node)})).collect::<Vec<_>>(),
            "parents":self.parents.states,"retained_evidence_paths":retained,
            "retired_created_directories":self.retired}),
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    struct Fixture(PathBuf);
    impl Drop for Fixture {
        fn drop(&mut self) {
            let _ = std::fs::remove_dir_all(&self.0);
        }
    }
    fn snapshot_value(node: &Node) -> Result<Value> {
        let attributes = node
            .attributes
            .iter()
            .map(|(k, v)| Ok((k.clone(), hex::decode(v)?)))
            .collect::<Result<BTreeMap<_, Vec<u8>>>>()?;
        Ok(
            json!({"identity":node.identity,"handle":{"handle_type":node.handle_type,
            "bytes":hex::decode(&node.handle)?},"attributes":attributes}),
        )
    }
    #[test]
    #[ignore = "root/ext4 only; actual full seventeen-item producer, nonempty evidence and fresh inverse"]
    fn actual_returned_twenty_two_member_roster_preserves_evidence_and_rejects_foreign_inode()
    -> Result<()> {
        ensure(
            rustix::process::geteuid().is_root(),
            "actual isolated root inode fixture required",
        )?;
        for foreign in [false, true] {
            let time = std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)?
                .as_nanos();
            let fixture = Fixture(PathBuf::from(format!(
                "/var/lib/droidloom-qualification/returned-files-{}-{time}",
                std::process::id()
            )));
            files::private_dir(&fixture.0)?;
            let public = fixture.0.join("public");
            files::private_dir(&public)?;
            let source = fixture.0.join("source");
            files::write_new(&source, b"actual normal source payload", 0o400)?;
            let source = files::pin_file(&source)?;
            let candidate = "a".repeat(64);
            let work = fixture.0.join("transaction");
            let mut transaction = Transaction::new(work.clone(), candidate.clone());
            transaction.initialize()?;
            let mut optional = BTreeSet::new();
            let mut required = BTreeMap::new();
            for n in 0..3 {
                let p = public.join(format!("parent-{n}"));
                optional.insert(p.clone());
                transaction.stage_directory(&p)?;
            }
            let retained = BTreeSet::from([
                public.join("candidate"),
                public.join("candidate/evidence"),
                public.join("production"),
            ]);
            for path in &retained {
                required.insert(path.clone(), Payload::Absent);
                transaction.stage_private_directory(path)?;
            }
            let original = public.join("original");
            files::write_new(&original, b"actual original retained", 0o644)?;
            let original_before = observe_kind(&original, false)?.unwrap();
            let mut file_paths = Vec::new();
            for n in 0..16 {
                let target = if n == 0 {
                    original.clone()
                } else {
                    public.join(format!("parent-{}/file-{n}", n % 3))
                };
                required.insert(
                    target.clone(),
                    Payload::Regular {
                        source: source.clone(),
                        mode: 0o644,
                    },
                );
                transaction.stage_file(&target, &source, 0o644)?;
                file_paths.push(target);
            }
            assert_eq!(transaction.len(), 22);
            assert!(
                transaction
                    .stage_file(&public.join("outside"), &source, 0o644)
                    .is_err()
            );
            for n in 0..transaction.len() {
                transaction.publish(n)?;
            }
            transaction.seal_summary(false)?;
            // Actual owned runtime writes after cold publication make these
            // directories nonempty. The fresh return never treats them as
            // disposable or silently moves their held retirement evidence.
            let evidence = public.join("candidate/evidence");
            for n in 0..6 {
                files::write_new(
                    &evidence.join(format!("record-{n}.json")),
                    b"actual retained runtime record",
                    0o600,
                )?;
            }
            let production = public.join("production");
            for name in [
                "PLAN.json",
                "SUMMARY.json",
                "MAIN.json",
                "STDERR.log",
                "COMMIT.json",
                "TRIAL.json",
                "REQUEST.json",
                "ACTIVE.json",
            ] {
                files::write_new(
                    &production.join(name),
                    b"actual retained production runtime record",
                    0o600,
                )?;
            }
            let comparisons = transaction
                .steps
                .iter()
                .map(|s| {
                    let current = observe_kind(&s.target, s.directory)?
                        .ok_or("fixture publication disappeared")?;
                    Ok((s.target.clone(), snapshot_value(&current)?))
                })
                .collect::<Result<BTreeMap<_, _>>>()?;
            drop(transaction);
            if foreign {
                std::fs::rename(&file_paths[1], fixture.0.join("foreign-retained-candidate"))?;
                files::write_new(&file_paths[1], b"actual normal source payload", 0o644)?;
            }
            let result = Transaction::reopen_comparisons(
                work.clone(),
                candidate.clone(),
                &required,
                &optional,
                &retained,
                &|p| {
                    comparisons
                        .get(p)
                        .cloned()
                        .ok_or_else(|| "missing actual fixture comparison".into())
                },
            );
            if foreign {
                assert!(result.is_err());
                continue;
            }
            let mut returned = result?;
            for n in (0..returned.len()).rev() {
                if !retained.contains(returned.target(n)) {
                    returned.restore(n)?;
                }
            }
            assert!(returned.all_restored_except(&retained));
            let report = returned.returned_evidence(&retained)?;
            assert_eq!(
                report["retained_evidence_paths"],
                serde_json::to_value(&retained)?
            );
            assert!(same_inode(
                &original_before,
                &observe_kind(&original, false)?.unwrap()
            ));
            assert_eq!(std::fs::read_dir(&evidence)?.count(), 6);
            assert_eq!(std::fs::read_dir(&production)?.count(), 8);
            for p in &optional {
                assert!(!p.exists());
            }
            drop(returned);
            let reopened = Transaction::reopen_comparisons(
                work,
                candidate,
                &required,
                &optional,
                &retained,
                &|p| {
                    comparisons
                        .get(p)
                        .cloned()
                        .ok_or_else(|| "missing actual fixture comparison".into())
                },
            )?;
            assert!(reopened.all_restored_except(&retained));
            reopened.guard()?;
            assert_eq!(std::fs::read_dir(&evidence)?.count(), 6);
            assert_eq!(std::fs::read_dir(&production)?.count(), 8);
        }
        Ok(())
    }
}
