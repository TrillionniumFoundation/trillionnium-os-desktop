//! Distinct actual view for the six original storage bind/slave/shared calls.
//! The earlier private/shared-only parsers remain unchanged.
use super::*;
use crate::production_namespace::OriginalInitStorageBindRequest;
use crate::production_runtime_assets::{
    OriginalInitStorageBind, OriginalInitStorageBindKind, OriginalInitStorageDirectories,
};

#[derive(Clone, Debug, Eq, PartialEq)]
struct BindInventory {
    base: MountInventory,
    shared: BTreeMap<u64, u64>,
    masters: BTreeMap<u64, u64>,
}

fn parse_bind_records(bytes: &[u8]) -> Result<BindInventory> {
    let text = std::str::from_utf8(bytes)
        .map_err(|_| NamespaceError::Rejected("non-text storage bind inventory"))?;
    if bytes.len() > 65536 || text.is_empty() || !text.ends_with('\n') || text.lines().count() > 256
    {
        return Err(NamespaceError::Rejected(
            "bounded complete storage bind inventory required",
        ));
    }
    let mut base = String::new();
    let mut shared = BTreeMap::new();
    let mut masters = BTreeMap::new();
    for line in text.lines() {
        let (left, right) = line
            .split_once(" - ")
            .ok_or(NamespaceError::Rejected("storage bind mount separator"))?;
        let fields: Vec<_> = left.split_ascii_whitespace().collect();
        if !(6..=8).contains(&fields.len()) {
            return Err(NamespaceError::Rejected(
                "foreign storage propagation fields",
            ));
        }
        let id: u64 = fields[0]
            .parse()
            .map_err(|_| NamespaceError::Rejected("storage mount ID overflow"))?;
        let mut seen_shared = false;
        let mut seen_master = false;
        for field in &fields[6..] {
            let (prefix, value) = field.split_once(':').ok_or(NamespaceError::Rejected(
                "foreign storage propagation field",
            ))?;
            let group: u64 = value
                .parse()
                .map_err(|_| NamespaceError::Rejected("storage group overflow"))?;
            if id == 0 || group == 0 || value != group.to_string() {
                return Err(NamespaceError::Rejected(
                    "noncanonical storage propagation group",
                ));
            }
            match prefix {
                "shared" if !seen_shared && !seen_master => {
                    if shared.insert(id, group).is_some() {
                        return Err(NamespaceError::Rejected("duplicate storage shared field"));
                    }
                    seen_shared = true;
                }
                "master" if !seen_master => {
                    if masters.insert(id, group).is_some() {
                        return Err(NamespaceError::Rejected("duplicate storage master field"));
                    }
                    seen_master = true;
                }
                _ => {
                    return Err(NamespaceError::Rejected(
                        "unknown, repeated or reordered storage propagation field",
                    ));
                }
            }
        }
        if seen_master && seen_shared && shared[&id] == masters[&id] {
            return Err(NamespaceError::Rejected(
                "storage peer cannot be its own master",
            ));
        }
        base.push_str(&fields[..6].join(" "));
        base.push_str(" - ");
        base.push_str(right);
        base.push('\n');
    }
    let records = writable_proc::mount_records(base.as_bytes())?;
    Ok(BindInventory {
        base: MountInventory {
            records,
            visible: BTreeMap::new(),
        },
        shared,
        masters,
    })
}

impl BindInventory {
    fn observe(child: &TreeChild) -> Result<Self> {
        child.verify()?;
        let raw = read_proc(&child.proc_dir, "mountinfo")?;
        let mut value = parse_bind_records(&raw)?;
        let root = held_child_root(child)?;
        let targets: BTreeSet<_> = value
            .base
            .records
            .values()
            .map(|r| r.target.clone())
            .collect();
        let mut held = Vec::new();
        let mut actual = BTreeMap::new();
        for target in targets {
            let file = writable_proc::target_from_root(&root, &target)?;
            let id = writable_proc::held_mount_id(&file)?;
            let device = file.metadata()?.dev();
            actual.insert(target.clone(), (id, device));
            held.push((target, file, id, device));
        }
        value.base.visible = writable_proc::checked_visible(&value.base.records, &actual)?;
        for (target, file, id, device) in &held {
            let named = writable_proc::target_from_root(&root, target)?;
            if writable_proc::held_mount_id(file)? != *id
                || writable_proc::held_mount_id(&named)? != *id
                || file.metadata()?.dev() != *device
                || Node::of(file)? != Node::of(&named)?
            {
                return Err(NamespaceError::Rejected(
                    "storage visible mount changed during observation",
                ));
            }
        }
        if read_proc(&child.proc_dir, "mountinfo")? != raw {
            return Err(NamespaceError::Rejected(
                "storage mount inventory changed during observation",
            ));
        }
        child.verify()?;
        Ok(value)
    }
}

fn exact_bind_delta(
    before: &BindInventory,
    after: &BindInventory,
    kind: OriginalInitStorageBindKind,
    source_mount: u64,
    actual_target: u64,
) -> Result<()> {
    let parent = before
        .base
        .records
        .get(&source_mount)
        .ok_or(NamespaceError::Rejected(
            "original storage source mount absent",
        ))?;
    let source_group = *before
        .shared
        .get(&source_mount)
        .ok_or(NamespaceError::Rejected(
            "original storage parent is not shared",
        ))?;
    if source_group == 0
        || parent.target != "/mnt"
        || parent.root != "/"
        || parent.filesystem != "tmpfs"
        || before.base.visible.get("/mnt") != Some(&source_mount)
        || before.masters.contains_key(&source_mount)
    {
        return Err(NamespaceError::Rejected(
            "storage source mount differs from the original shared parent",
        ));
    }
    let target = kind
        .target()
        .to_str()
        .map_err(|_| NamespaceError::Rejected("fixed storage target encoding"))?;
    if kind.is_bind() {
        if actual_target == 0
            || before.base.records.contains_key(&actual_target)
            || before.base.visible.contains_key(target)
            || after.base.records.len() != before.base.records.len() + 1
        {
            return Err(NamespaceError::Rejected(
                "bind requires one actual new mount",
            ));
        }
        for (id, row) in &before.base.records {
            if after.base.records.get(id) != Some(row) {
                return Err(NamespaceError::Rejected(
                    "bind changed a retained lower layer",
                ));
            }
        }
        let mut expected_row = parent.clone();
        expected_row.id = actual_target;
        expected_row.parent = source_mount;
        expected_row.root = "/user".into();
        expected_row.target = target.into();
        if after.base.records.get(&actual_target) != Some(&expected_row) {
            return Err(NamespaceError::Rejected(
                "actual bind is not the original /user subdirectory",
            ));
        }
        let mut visible = before.base.visible.clone();
        visible.insert(target.into(), actual_target);
        let mut shared = before.shared.clone();
        shared.insert(actual_target, source_group);
        if after.base.visible != visible
            || after.shared != shared
            || after.masters != before.masters
        {
            return Err(NamespaceError::Rejected(
                "bind changed foreign visibility or propagation peers",
            ));
        }
    } else {
        if before.base != after.base || before.base.visible.get(target) != Some(&actual_target) {
            return Err(NamespaceError::Rejected(
                "storage propagation changed a mount identity or visible layer",
            ));
        }
        let mut shared = before.shared.clone();
        let mut masters = before.masters.clone();
        match kind {
            OriginalInitStorageBindKind::SlaveInstaller
            | OriginalInitStorageBindKind::SlaveAndroidWritable => {
                if shared.remove(&actual_target) != Some(source_group)
                    || masters.insert(actual_target, source_group).is_some()
                {
                    return Err(NamespaceError::Rejected(
                        "SLAVE requires the actual original bind peer",
                    ));
                }
            }
            OriginalInitStorageBindKind::SharedInstaller
            | OriginalInitStorageBindKind::SharedAndroidWritable => {
                let group = *after
                    .shared
                    .get(&actual_target)
                    .ok_or(NamespaceError::Rejected(
                        "SHARED did not receive an actual group",
                    ))?;
                if group == 0
                    || shared.contains_key(&actual_target)
                    || masters.get(&actual_target) != Some(&source_group)
                    || shared.values().any(|v| *v == group)
                    || masters.values().any(|v| *v == group)
                {
                    return Err(NamespaceError::Rejected(
                        "SHARED requires a distinct new group and retained original master",
                    ));
                }
                shared.insert(actual_target, group);
            }
            _ => {
                return Err(NamespaceError::Rejected(
                    "foreign storage propagation operation",
                ));
            }
        }
        if after.shared != shared || after.masters != masters {
            return Err(NamespaceError::Rejected(
                "storage propagation changed a foreign peer or master",
            ));
        }
    }
    Ok(())
}

pub(crate) struct InitialStorageBindProjection {
    identity: ProcessIdentity,
    nonce: [u8; 16],
    pidfd: Node,
    proc: Node,
    prior: PropagationInventory,
    expected: BindInventory,
    directories: OriginalInitStorageDirectories,
    original_files: [File; 3],
    original_nodes: [ImmutableNode; 3],
    source_mount: u64,
    added: Vec<u64>,
    completed: usize,
    failed: bool,
}

/// Frozen only by the complete six-call original storage projection. This is
/// not a caller-authored mount inventory or a namespace-transition witness.
/// Its private binding is compared to the original stopped trace owner.
pub(crate) struct NativeStorageSnapshot {
    identity: ProcessIdentity,
    nonce: [u8; 16],
    pidfd: Node,
    proc: Node,
    expected: BindInventory,
}

impl NativeStorageSnapshot {
    pub(crate) fn matches_original(
        &self,
        identity: ProcessIdentity,
        nonce: [u8; 16],
        pidfd: Node,
        proc: Node,
    ) -> Result<()> {
        if self.identity != identity
            || self.nonce != nonce
            || self.pidfd != pidfd
            || self.proc != proc
        {
            return Err(NamespaceError::Rejected(
                "native snapshot belongs to another original tree",
            ));
        }
        Ok(())
    }

    pub(crate) fn matches_actual_parts(
        &self,
        base: &MountInventory,
        shared: &BTreeMap<u64, u64>,
        masters: &BTreeMap<u64, u64>,
    ) -> Result<()> {
        if &self.expected.base != base
            || &self.expected.shared != shared
            || &self.expected.masters != masters
        {
            return Err(NamespaceError::Rejected(
                "native baseline differs from the complete original storage view",
            ));
        }
        Ok(())
    }
}

impl InitialStorageBindProjection {
    pub(crate) fn native_snapshot(
        &self,
        previous: &InitialPropagationProjection,
        mounts: &InitialMountProjection,
        observation: &RuntimeObservation,
        child: &TreeChild,
    ) -> Result<NativeStorageSnapshot> {
        if !self.complete() {
            return Err(NamespaceError::Rejected(
                "native namespaces require all six actual storage calls",
            ));
        }
        self.verify_current(previous, mounts, observation, child)?;
        let value = NativeStorageSnapshot {
            identity: self.identity,
            nonce: self.nonce,
            pidfd: self.pidfd,
            proc: self.proc,
            expected: self.expected.clone(),
        };
        self.verify_current(previous, mounts, observation, child)?;
        Ok(value)
    }

    pub(crate) fn begin(
        previous: &InitialPropagationProjection,
        mounts: &InitialMountProjection,
        observation: &RuntimeObservation,
        child: &TreeChild,
        init: &ExecutedInitWitness<'_>,
        request: &OriginalInitStorageBindRequest<'_>,
        directories: OriginalInitStorageDirectories,
    ) -> Result<Self> {
        request.revalidate(init)?;
        if !previous.complete() || request.kind() != OriginalInitStorageBindKind::BindInstaller {
            return Err(NamespaceError::Rejected(
                "storage binds require the original completed propagation phase",
            ));
        }
        previous.verify_current(mounts, observation, child)?;
        let files = directories
            .original_files(init)
            .map_err(|e| NamespaceError::RuntimeResource(e.to_string()))?;
        let nodes = [
            ImmutableNode::of(&files[0])?,
            ImmutableNode::of(&files[1])?,
            ImmutableNode::of(&files[2])?,
        ];
        let source_mount = directories
            .parent_mount(init)
            .map_err(|e| NamespaceError::RuntimeResource(e.to_string()))?;
        if previous.expected.base.visible.get("/mnt") != Some(&source_mount)
            || previous
                .expected
                .base
                .visible
                .contains_key("/mnt/installer")
            || previous
                .expected
                .base
                .visible
                .contains_key("/mnt/androidwritable")
        {
            return Err(NamespaceError::Rejected(
                "storage bind source or initial targets differ",
            ));
        }
        let value = Self {
            identity: child.identity,
            nonce: child.nonce,
            pidfd: descriptor_node(child.pidfd.as_fd())?,
            proc: child.proc_node,
            prior: previous.expected.clone(),
            expected: BindInventory {
                base: previous.expected.base.clone(),
                shared: previous.expected.shared.clone(),
                masters: BTreeMap::new(),
            },
            directories,
            original_files: files,
            original_nodes: nodes,
            source_mount,
            added: Vec::new(),
            completed: 0,
            failed: false,
        };
        value.verify_current(previous, mounts, observation, child)?;
        request.revalidate(init)?;
        Ok(value)
    }

    fn original(&self, child: &TreeChild) -> Result<()> {
        child.verify()?;
        if child.identity != self.identity
            || child.nonce != self.nonce
            || child.proc_node != self.proc
            || descriptor_node(child.pidfd.as_fd())? != self.pidfd
        {
            return Err(NamespaceError::Rejected(
                "storage bind projection belongs to another original tree",
            ));
        }
        Ok(())
    }

    fn observed(
        &self,
        previous: &InitialPropagationProjection,
        mounts: &InitialMountProjection,
        observation: &RuntimeObservation,
        child: &TreeChild,
    ) -> Result<()> {
        self.original(child)?;
        if !previous.complete() || previous.expected != self.prior {
            return Err(NamespaceError::Rejected(
                "original storage propagation predecessor changed",
            ));
        }
        let now = BindInventory::observe(child)?;
        if now != self.expected {
            return Err(NamespaceError::Rejected(
                "complete original storage bind view changed",
            ));
        }
        let root = held_child_root(child)?;
        self.directories
            .verify_view(&root)
            .map_err(|e| NamespaceError::RuntimeResource(e.to_string()))?;
        for (file, node) in self.original_files.iter().zip(&self.original_nodes) {
            if ImmutableNode::of(file)? != *node
                || writable_proc::held_mount_id(file)? != self.source_mount
            {
                return Err(NamespaceError::Rejected(
                    "original covered storage directory changed",
                ));
            }
        }
        for (index, target) in [(1, "/mnt/installer"), (2, "/mnt/androidwritable")] {
            let file = writable_proc::target_from_root(&root, target)?;
            let (node, mount) = match now.base.visible.get(target) {
                Some(id) => (self.original_nodes[0], *id),
                None => (self.original_nodes[index], self.source_mount),
            };
            if ImmutableNode::of(&file)? != node || writable_proc::held_mount_id(&file)? != mount {
                return Err(NamespaceError::Rejected(
                    "actual storage target is not the original directory/source",
                ));
            }
        }
        let mut prior = now;
        for id in &self.added {
            let row = prior
                .base
                .records
                .remove(id)
                .ok_or(NamespaceError::Rejected("actual storage bind row missing"))?;
            if prior.base.visible.remove(&row.target) != Some(*id) {
                return Err(NamespaceError::Rejected(
                    "actual storage bind visible row missing",
                ));
            }
            prior.shared.remove(id);
            prior.masters.remove(id);
        }
        if !prior.masters.is_empty()
            || prior.base != self.prior.base
            || prior.shared != self.prior.shared
        {
            return Err(NamespaceError::Rejected(
                "storage bind overlay did not preserve the complete prior view",
            ));
        }
        let original_base = previous
            .storage
            .as_ref()
            .ok_or(NamespaceError::Rejected(
                "original storage preparation owner absent",
            ))?
            .verify_and_original_base(&prior.base, child)?;
        mounts.verify_propagated_base(observation, child, original_base)?;
        previous.original(child)?;
        self.original(child)
    }

    pub(crate) fn verify_current(
        &self,
        previous: &InitialPropagationProjection,
        mounts: &InitialMountProjection,
        observation: &RuntimeObservation,
        child: &TreeChild,
    ) -> Result<()> {
        if self.failed {
            return Err(NamespaceError::Rejected(
                "failed storage binds require original tree retirement",
            ));
        }
        self.observed(previous, mounts, observation, child)
    }

    pub(crate) fn admit_actual(
        &mut self,
        previous: &InitialPropagationProjection,
        mounts: &InitialMountProjection,
        observation: &RuntimeObservation,
        child: &TreeChild,
        init: &ExecutedInitWitness<'_>,
        request: &OriginalInitStorageBindRequest<'_>,
        completed: &OriginalInitStorageBind,
    ) -> Result<()> {
        if self.failed
            || OriginalInitStorageBindKind::ALL.get(self.completed) != Some(&request.kind())
        {
            return Err(NamespaceError::Rejected(
                "original storage bind sequence differs",
            ));
        }
        request.revalidate(init)?;
        self.original(child)?;
        self.failed = true;
        if completed
            .actual_errno(init, request)
            .map_err(|e| NamespaceError::RuntimeResource(e.to_string()))?
            != 0
        {
            return Err(NamespaceError::Rejected(
                "failed actual storage operation cannot advance the view",
            ));
        }
        let target = completed
            .actual_target(init, request, &self.directories)
            .map_err(|e| NamespaceError::RuntimeResource(e.to_string()))?;
        let target_id = writable_proc::held_mount_id(&target)?;
        let after = BindInventory::observe(child)?;
        exact_bind_delta(
            &self.expected,
            &after,
            request.kind(),
            self.source_mount,
            target_id,
        )?;
        if request.kind().is_bind() {
            self.added.push(target_id);
        }
        self.expected = after;
        self.completed += 1;
        self.observed(previous, mounts, observation, child)?;
        request.revalidate(init)?;
        self.failed = false;
        Ok(())
    }

    pub(crate) fn complete(&self) -> bool {
        !self.failed
            && self.completed == OriginalInitStorageBindKind::ALL.len()
            && self.added.len() == 2
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn original_storage_parser_retains_canonical_shared_slave_fields_without_weakening_earlier_parsers()
     {
        let raw=b"9 3 0:7 /user /mnt/installer rw,nosuid,nodev,noexec shared:201 master:103 - tmpfs tmpfs rw\n";
        let parsed = parse_bind_records(raw).unwrap();
        assert_eq!(parsed.shared, BTreeMap::from([(9, 201)]));
        assert_eq!(parsed.masters, BTreeMap::from([(9, 103)]));
        assert!(super::parse_records(raw).is_err());
        assert!(writable_proc::mount_records(raw).is_err());
        for field in [
            "master:0",
            "master:01",
            "master:+1",
            "master:18446744073709551616",
            "master:3 master:4",
            "master:3 shared:4",
            "shared:3 master:3",
            "propagate_from:3",
            "unbindable",
            "shared:3 master:4 propagate_from:5",
        ] {
            let row = format!("9 3 0:7 /user /mnt/installer rw {field} - tmpfs tmpfs rw\n");
            assert!(parse_bind_records(row.as_bytes()).is_err(), "{field}");
        }
    }

    fn fixture() -> BindInventory {
        let mut v=parse_bind_records(b"1 100 0:1 / / rw,nosuid,nodev shared:101 - tmpfs none rw\n\
             2 1 8:1 /mnt /mnt ro,nosuid,nodev shared:102 - ext4 /dev/system ro\n\
             3 2 0:7 / /mnt rw,nosuid,nodev,noexec shared:103 - tmpfs tmpfs rw,size=16384k,nr_inodes=4096\n").unwrap();
        v.base.visible = BTreeMap::from([("/".into(), 1), ("/mnt".into(), 3)]);
        v
    }

    #[test]
    fn original_storage_bind_delta_keeps_two_real_layers_and_tracks_each_slave_master() {
        let mut before = fixture();
        let original = before.clone();
        for (at, kind) in OriginalInitStorageBindKind::ALL.into_iter().enumerate() {
            let id = if at % 2 == 0 { 10 } else { 11 };
            let mut after = before.clone();
            if kind.is_bind() {
                let mut row = before.base.records[&3].clone();
                row.id = id;
                row.parent = 3;
                row.root = "/user".into();
                row.target = kind.target().to_str().unwrap().into();
                after.base.visible.insert(row.target.clone(), id);
                after.base.records.insert(id, row);
                after.shared.insert(id, 103);
            } else if at < 4 {
                after.shared.remove(&id);
                after.masters.insert(id, 103);
            } else {
                after.shared.insert(id, 201 + id - 10);
            }
            exact_bind_delta(&before, &after, kind, 3, id).unwrap();
            for flaw in [
                "old-row",
                "foreign-peer",
                "foreign-master",
                "visible",
                "root",
                "missing-layer",
            ] {
                let mut bad = after.clone();
                match flaw {
                    "old-row" => {
                        bad.base.records.get_mut(&2).unwrap().source = "foreign".into();
                    }
                    "foreign-peer" => {
                        bad.shared.insert(1, 999);
                    }
                    "foreign-master" => {
                        bad.masters.insert(id, 102);
                    }
                    "visible" => {
                        bad.base.visible.insert("/mnt".into(), 2);
                    }
                    "root" => {
                        bad.base.records.get_mut(&id).unwrap().root = "/".into();
                    }
                    "missing-layer" => {
                        bad.base.records.remove(&2);
                    }
                    _ => unreachable!(),
                }
                assert!(
                    exact_bind_delta(&before, &bad, kind, 3, id).is_err(),
                    "{at} {flaw}"
                );
            }
            before = after;
        }
        for (id, row) in &original.base.records {
            assert_eq!(before.base.records[id], *row);
        }
        assert_eq!(before.masters, BTreeMap::from([(10, 103), (11, 103)]));
        assert_eq!(before.shared[&3], 103);
        assert_eq!(before.shared[&10], 201);
        assert_eq!(before.shared[&11], 202);
    }
}
