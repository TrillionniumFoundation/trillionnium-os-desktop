//! A distinct phase for the original init's three native propagation calls.
//! Private preparation parsing remains unchanged. This parser admits only a
//! single shared:N field; master/slave/unknown fields are rejected. Causality
//! comes from the held pending single actor and actual fixed helper operation.
use super::*;
use crate::production_namespace::OriginalInitPropagationRequest;
use crate::production_runtime_assets::{OriginalInitPropagation, OriginalInitPropagationKind};
use writable_proc::{MountInventory, MountRecord};
#[path = "production_namespace_init_storage_projection.rs"]
mod storage;
use storage::StorageProjection;
#[path = "production_namespace_init_storage_bind_projection.rs"]
mod storage_binds;
pub(crate) use storage_binds::{InitialStorageBindProjection, NativeStorageSnapshot};

#[derive(Clone, Debug, Eq, PartialEq)]
struct PropagationInventory {
    base: MountInventory,
    shared: BTreeMap<u64, u64>,
}

fn parse_records(bytes: &[u8]) -> Result<(BTreeMap<u64, MountRecord>, BTreeMap<u64, u64>)> {
    let text = std::str::from_utf8(bytes)
        .map_err(|_| NamespaceError::Rejected("non-text original propagation inventory"))?;
    if bytes.len() > 65536 || text.is_empty() || !text.ends_with('\n') || text.lines().count() > 256
    {
        return Err(NamespaceError::Rejected(
            "bounded complete propagation inventory required",
        ));
    }
    let mut private_fields = String::new();
    let mut shared = BTreeMap::new();
    for line in text.lines() {
        let (left, right) = line
            .split_once(" - ")
            .ok_or(NamespaceError::Rejected("propagation mount separator"))?;
        let fields: Vec<_> = left.split_ascii_whitespace().collect();
        if !(6..=7).contains(&fields.len()) {
            return Err(NamespaceError::Rejected(
                "foreign or duplicate propagation field",
            ));
        }
        if fields.len() == 7 {
            let value = fields[6]
                .strip_prefix("shared:")
                .ok_or(NamespaceError::Rejected(
                    "master/slave/unknown propagation rejected",
                ))?;
            let group: u64 = value
                .parse()
                .map_err(|_| NamespaceError::Rejected("shared mount group overflow"))?;
            let id: u64 = fields[0]
                .parse()
                .map_err(|_| NamespaceError::Rejected("propagation mount ID overflow"))?;
            if id == 0
                || group == 0
                || value != group.to_string()
                || shared.insert(id, group).is_some()
            {
                return Err(NamespaceError::Rejected(
                    "noncanonical or duplicate shared mount group",
                ));
            }
        }
        // The unchanged strict parser checks every non-propagation field.
        // This is a structured base record, never a claim the actual mount
        // is private; the separate shared map is always retained and checked.
        private_fields.push_str(&fields[..6].join(" "));
        private_fields.push_str(" - ");
        private_fields.push_str(right);
        private_fields.push('\n');
    }
    let records = writable_proc::mount_records(private_fields.as_bytes())?;
    Ok((records, shared))
}

impl PropagationInventory {
    fn observe(child: &TreeChild) -> Result<Self> {
        child.verify()?;
        let raw = read_proc(&child.proc_dir, "mountinfo")?;
        let (records, shared) = parse_records(&raw)?;
        let root = held_child_root(child)?;
        let targets: BTreeSet<_> = records.values().map(|r| r.target.clone()).collect();
        let mut held = Vec::new();
        let mut actual = BTreeMap::new();
        for target in targets {
            let file = writable_proc::target_from_root(&root, &target)?;
            let id = writable_proc::held_mount_id(&file)?;
            let device = file.metadata()?.dev();
            actual.insert(target.clone(), (id, device));
            held.push((target, file, id, device));
        }
        let visible = writable_proc::checked_visible(&records, &actual)?;
        for (target, file, id, device) in &held {
            let named = writable_proc::target_from_root(&root, target)?;
            if writable_proc::held_mount_id(file)? != *id
                || writable_proc::held_mount_id(&named)? != *id
                || file.metadata()?.dev() != *device
                || Node::of(file)? != Node::of(&named)?
            {
                return Err(NamespaceError::Rejected(
                    "propagation visible mount changed",
                ));
            }
        }
        if read_proc(&child.proc_dir, "mountinfo")? != raw {
            return Err(NamespaceError::Rejected(
                "propagation changed during complete observation",
            ));
        }
        child.verify()?;
        Ok(Self {
            base: MountInventory { records, visible },
            shared,
        })
    }
}

fn root_descendants(base: &MountInventory) -> Result<BTreeSet<u64>> {
    let root = *base
        .visible
        .get("/")
        .ok_or(NamespaceError::Rejected("original visible root absent"))?;
    if base.records.get(&root).is_none_or(|row| row.target != "/") {
        return Err(NamespaceError::Rejected(
            "original visible root is not recorded",
        ));
    }
    let mut descendants = BTreeSet::from([root]);
    loop {
        let mut changed = false;
        for row in base.records.values() {
            if descendants.contains(&row.parent) {
                changed |= descendants.insert(row.id);
            }
        }
        if !changed {
            return Ok(descendants);
        }
    }
}

fn exact_delta(
    before: &PropagationInventory,
    after: &PropagationInventory,
    kind: OriginalInitPropagationKind,
) -> Result<()> {
    if before.base != after.base {
        return Err(NamespaceError::Rejected(
            "propagation changed a mount identity, flag or visible layer",
        ));
    }
    match kind {
        OriginalInitPropagationKind::RootShared => {
            let descendants = root_descendants(&before.base)?;
            if !before.shared.is_empty()
                || after.shared.keys().copied().collect::<BTreeSet<_>>() != descendants
                || after.shared.values().any(|group| *group == 0)
                || after
                    .shared
                    .values()
                    .copied()
                    .collect::<BTreeSet<_>>()
                    .len()
                    != after.shared.len()
            {
                return Err(NamespaceError::Rejected(
                    "private root subtree did not receive distinct actual new shared groups",
                ));
            }
        }
        OriginalInitPropagationKind::ApexPrivate
        | OriginalInitPropagationKind::LinkerconfigPrivate => {
            let target = kind
                .target()
                .to_str()
                .map_err(|_| NamespaceError::Rejected("fixed propagation target encoding"))?;
            let visible = *before
                .base
                .visible
                .get(target)
                .ok_or(NamespaceError::Rejected("original private target absent"))?;
            let mut expected = before.shared.clone();
            if expected.remove(&visible).is_none() || after.shared != expected {
                return Err(NamespaceError::Rejected(
                    "nonrecursive PRIVATE must change only the actual visible top mount",
                ));
            }
        }
    }
    Ok(())
}

pub(crate) struct InitialPropagationProjection {
    identity: ProcessIdentity,
    nonce: [u8; 16],
    pidfd: Node,
    proc: Node,
    expected: PropagationInventory,
    storage: Option<StorageProjection>,
    completed: usize,
    failed: bool,
}

impl InitialPropagationProjection {
    pub(crate) fn begin(
        mounts: &InitialMountProjection,
        observation: &RuntimeObservation,
        child: &TreeChild,
    ) -> Result<Self> {
        if !mounts.complete() {
            return Err(NamespaceError::Rejected(
                "all original tmpfs calls required before propagation",
            ));
        }
        let base = mounts.verify_current(observation, child)?;
        let value = Self {
            identity: child.identity,
            nonce: child.nonce,
            pidfd: descriptor_node(child.pidfd.as_fd())?,
            proc: child.proc_node,
            expected: PropagationInventory {
                base,
                shared: BTreeMap::new(),
            },
            storage: None,
            completed: 0,
            failed: false,
        };
        value.verify_current(mounts, observation, child)?;
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
                "propagation belongs to another original tree",
            ));
        }
        Ok(())
    }

    fn observe_expected(
        &self,
        mounts: &InitialMountProjection,
        observation: &RuntimeObservation,
        child: &TreeChild,
    ) -> Result<()> {
        self.original(child)?;
        let now = PropagationInventory::observe(child)?;
        if now != self.expected {
            return Err(NamespaceError::Rejected(
                "complete original propagation view changed",
            ));
        }
        let original_base = match &self.storage {
            Some(storage) => storage.verify_and_original_base(&now.base, child)?,
            None => &now.base,
        };
        mounts.verify_propagated_base(observation, child, original_base)?;
        self.original(child)
    }

    pub(crate) fn verify_current(
        &self,
        mounts: &InitialMountProjection,
        observation: &RuntimeObservation,
        child: &TreeChild,
    ) -> Result<()> {
        if self.failed {
            return Err(NamespaceError::Rejected(
                "failed propagation requires original tree retirement",
            ));
        }
        self.observe_expected(mounts, observation, child)
    }

    pub(crate) fn admit_storage(
        &mut self,
        mounts: &InitialMountProjection,
        observation: &RuntimeObservation,
        child: &TreeChild,
        init: &ExecutedInitWitness<'_>,
        request: &OriginalInitPropagationRequest<'_>,
        completed: &crate::production_runtime_assets::OriginalInitStorage,
    ) -> Result<()> {
        if self.failed
            || self.completed != 0
            || self.storage.is_some()
            || !self.expected.shared.is_empty()
            || request.kind() != OriginalInitPropagationKind::RootShared
        {
            return Err(NamespaceError::Rejected(
                "storage preparation can occur only at the first actual barrier",
            ));
        }
        request.revalidate(init)?;
        self.original(child)?;
        self.failed = true;
        let after =
            writable_proc::MountInventory::observe(child, "after-original-storage-preparation")?;
        let storage =
            StorageProjection::admit(&self.expected.base, &after, child, init, request, completed)?;
        self.storage = Some(storage);
        self.expected.base = after;
        self.observe_expected(mounts, observation, child)?;
        request.revalidate(init)?;
        self.failed = false;
        Ok(())
    }

    pub(crate) fn admit_actual(
        &mut self,
        mounts: &InitialMountProjection,
        observation: &RuntimeObservation,
        child: &TreeChild,
        init: &ExecutedInitWitness<'_>,
        request: &OriginalInitPropagationRequest<'_>,
        completed: &OriginalInitPropagation,
    ) -> Result<()> {
        if self.failed
            || self.storage.is_none()
            || OriginalInitPropagationKind::ALL.get(self.completed) != Some(&request.kind())
        {
            return Err(NamespaceError::Rejected(
                "original propagation sequence differs",
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
                "failed native operation cannot advance propagation",
            ));
        }
        let after = PropagationInventory::observe(child)?;
        exact_delta(&self.expected, &after, request.kind())?;
        self.expected = after;
        self.completed += 1;
        self.observe_expected(mounts, observation, child)?;
        request.revalidate(init)?;
        self.failed = false;
        Ok(())
    }

    pub(crate) fn complete(&self) -> bool {
        !self.failed
            && self.storage.is_some()
            && self.completed == OriginalInitPropagationKind::ALL.len()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn fixture() -> PropagationInventory {
        let records = writable_proc::mount_records(
            b"1 100 8:1 / / ro - ext4 /dev/system ro\n\
              2 1 0:2 / /apex rw,nosuid,nodev,noexec - tmpfs none rw\n\
              3 2 0:3 / /apex rw,nosuid,nodev,noexec - tmpfs tmpfs rw\n\
              4 1 0:4 / /linkerconfig rw,nosuid,nodev,noexec - tmpfs none rw\n\
              5 4 0:5 / /linkerconfig rw,nosuid,nodev,noexec - tmpfs tmpfs rw\n",
        )
        .unwrap();
        PropagationInventory {
            base: MountInventory {
                records,
                visible: BTreeMap::from([
                    ("/".into(), 1),
                    ("/apex".into(), 3),
                    ("/linkerconfig".into(), 5),
                ]),
            },
            shared: BTreeMap::new(),
        }
    }

    #[test]
    fn original_propagation_parser_keeps_shared_fields_and_rejects_master_or_unknown_state() {
        let private = b"1 100 8:1 / / ro - ext4 /dev/system ro\n";
        assert!(parse_records(private).unwrap().1.is_empty());
        let actual = b"1 100 8:1 / / ro shared:91 - ext4 /dev/system ro\n";
        assert_eq!(parse_records(actual).unwrap().1, BTreeMap::from([(1, 91)]));
        // The original private parser is not broadened by this phase.
        assert!(writable_proc::mount_records(actual).is_err());
        for field in [
            "master:1",
            "propagate_from:1",
            "unbindable",
            "shared:0",
            "shared:01",
            "shared:+1",
            "shared:18446744073709551616",
            "shared:2 shared:3",
            "shared:2 master:3",
        ] {
            let text = format!("1 100 8:1 / / ro {field} - ext4 /dev/system ro\n");
            assert!(parse_records(text.as_bytes()).is_err(), "{field}");
        }
    }

    #[test]
    fn original_propagation_delta_retains_all_lower_layers_and_only_privatizes_visible_top() {
        let before = fixture();
        let mut shared = before.clone();
        shared.shared = BTreeMap::from([(1, 31), (2, 32), (3, 33), (4, 34), (5, 35)]);
        exact_delta(&before, &shared, OriginalInitPropagationKind::RootShared).unwrap();
        let mut apex_private = shared.clone();
        apex_private.shared.remove(&3);
        exact_delta(
            &shared,
            &apex_private,
            OriginalInitPropagationKind::ApexPrivate,
        )
        .unwrap();
        assert_eq!(apex_private.shared[&2], 32);
        let mut complete = apex_private.clone();
        complete.shared.remove(&5);
        exact_delta(
            &apex_private,
            &complete,
            OriginalInitPropagationKind::LinkerconfigPrivate,
        )
        .unwrap();
        assert_eq!(complete.shared[&4], 34);
        for flaw in [
            "missing-covered",
            "duplicate-peer",
            "foreign-peer",
            "changed-row",
            "changed-visible",
        ] {
            let mut wrong = shared.clone();
            match flaw {
                "missing-covered" => {
                    wrong.shared.remove(&2);
                }
                "duplicate-peer" => {
                    wrong.shared.insert(2, 31);
                }
                "foreign-peer" => {
                    wrong.shared.insert(99, 99);
                }
                "changed-row" => {
                    wrong.base.records.get_mut(&2).unwrap().parent = 100;
                }
                "changed-visible" => {
                    wrong.base.visible.insert("/apex".into(), 2);
                }
                _ => unreachable!(),
            }
            assert!(
                exact_delta(&before, &wrong, OriginalInitPropagationKind::RootShared).is_err(),
                "{flaw}"
            );
        }
        let mut wrong = apex_private.clone();
        wrong.shared.remove(&2);
        assert!(exact_delta(&shared, &wrong, OriginalInitPropagationKind::ApexPrivate).is_err());
        let mut lower_root = before.clone();
        lower_root.base.records.get_mut(&1).unwrap().parent = 10;
        let mut lower = lower_root.base.records[&1].clone();
        lower.id = 10;
        lower.parent = 100;
        lower_root.base.records.insert(10, lower);
        let mut after = lower_root.clone();
        after.shared = shared.shared.clone();
        exact_delta(&lower_root, &after, OriginalInitPropagationKind::RootShared).unwrap();
        after.shared.insert(10, 40);
        assert!(exact_delta(&lower_root, &after, OriginalInitPropagationKind::RootShared).is_err());
    }
}
