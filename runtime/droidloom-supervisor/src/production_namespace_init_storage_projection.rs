//! The actual one-mount /mnt preparation before any propagation change.
//! This is an explicit overlay over the completed original tmpfs phase; its
//! lower row is retained and never silently removed from the full inventory.
use super::*;
use crate::production_runtime_assets::{OriginalInitStorage, verify_storage_root};

fn exact_storage_delta(
    before: &MountInventory,
    after: &MountInventory,
    source_mount: u64,
    source_device: u64,
) -> Result<()> {
    let lower = *before.visible.get("/mnt").ok_or(NamespaceError::Rejected(
        "original storage lower mount absent",
    ))?;
    if source_mount == 0
        || before.records.contains_key(&source_mount)
        || before.records.values().any(|r| r.device == source_device)
        || after.records.len() != before.records.len() + 1
    {
        return Err(NamespaceError::Rejected(
            "storage preparation needs one distinct new mount",
        ));
    }
    for (id, row) in &before.records {
        if after.records.get(id) != Some(row) {
            return Err(NamespaceError::Rejected(
                "storage preparation changed an existing mount",
            ));
        }
    }
    let row = after
        .records
        .get(&source_mount)
        .ok_or(NamespaceError::Rejected(
            "actual storage source mount absent",
        ))?;
    if row.parent != lower
        || row.device != source_device
        || row.target != "/mnt"
        || row.root != "/"
        || row.filesystem != "tmpfs"
        || row.source != "tmpfs"
        || !["rw", "nosuid", "nodev", "noexec"]
            .iter()
            .all(|v| row.flags.contains(*v))
        || row.flags.contains("ro")
        || !row.options.split(',').any(|v| v == "rw")
        || row.options.split(',').any(|v| v == "ro")
    {
        return Err(NamespaceError::Rejected(
            "storage mount source, parent, role or flags differ",
        ));
    }
    let mut visible = before.visible.clone();
    visible.insert("/mnt".into(), source_mount);
    if after.visible != visible {
        return Err(NamespaceError::Rejected(
            "storage changed another visible mount",
        ));
    }
    Ok(())
}

pub(super) struct StorageProjection {
    original_base: MountInventory,
    record: MountRecord,
    source: File,
    node: ImmutableNode,
}

impl StorageProjection {
    pub(super) fn admit(
        before: &MountInventory,
        after: &MountInventory,
        child: &TreeChild,
        init: &ExecutedInitWitness<'_>,
        request: &OriginalInitPropagationRequest<'_>,
        completed: &OriginalInitStorage,
    ) -> Result<Self> {
        request.revalidate(init)?;
        if request.kind() != OriginalInitPropagationKind::RootShared {
            return Err(NamespaceError::Rejected(
                "storage preparation has another barrier",
            ));
        }
        let source = completed
            .published_root(init, request)
            .map_err(|e| NamespaceError::RuntimeResource(e.to_string()))?;
        let node = ImmutableNode::of(&source)?;
        let id = writable_proc::held_mount_id(&source)?;
        exact_storage_delta(before, after, id, node.dev)?;
        let value = Self {
            original_base: before.clone(),
            record: after.records[&id].clone(),
            source,
            node,
        };
        value.verify_and_original_base(after, child)?;
        request.revalidate(init)?;
        Ok(value)
    }

    /// Return the earlier phase projection only after proving that the actual
    /// current base is precisely that base plus this original published mount.
    /// The caller still retains and verifies the complete current inventory.
    pub(super) fn verify_and_original_base<'a>(
        &'a self,
        current: &MountInventory,
        child: &TreeChild,
    ) -> Result<&'a MountInventory> {
        exact_storage_delta(&self.original_base, current, self.record.id, self.node.dev)?;
        if current.records.get(&self.record.id) != Some(&self.record) {
            return Err(NamespaceError::Rejected(
                "original storage mount record changed",
            ));
        }
        let root = held_child_root(child)?;
        let target = writable_proc::target_from_root(&root, "/mnt")?;
        let gid = child
            .gids
            .start
            .checked_add(1000)
            .ok_or(NamespaceError::Rejected("storage mapped gid overflow"))?;
        for file in [&self.source, &target] {
            let now = ImmutableNode::of(file)?;
            if (now.dev, now.ino, now.mode, now.uid, now.gid)
                != (
                    self.node.dev,
                    self.node.ino,
                    self.node.mode,
                    self.node.uid,
                    self.node.gid,
                )
                || now.nlink < 2
                || writable_proc::held_mount_id(file)? != self.record.id
            {
                return Err(NamespaceError::Rejected(
                    "storage lost its actual original source inode",
                ));
            }
            verify_storage_root(file, child.uids.start, gid)
                .map_err(|e| NamespaceError::RuntimeResource(e.to_string()))?;
        }
        Ok(&self.original_base)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn storage_mount_projection_requires_one_new_source_and_keeps_the_original_lower_layer() {
        let records = writable_proc::mount_records(
            b"1 100 0:1 / / rw,nosuid,nodev - tmpfs none rw\n\
              2 1 8:1 /mnt /mnt ro,nosuid,nodev - ext4 /dev/system ro\n",
        )
        .unwrap();
        let before = MountInventory {
            records,
            visible: BTreeMap::from([("/".into(), 1), ("/mnt".into(), 2)]),
        };
        let mut after = before.clone();
        let row = writable_proc::mount_records(
            b"3 2 0:4 / /mnt rw,nosuid,nodev,noexec - tmpfs tmpfs rw,size=16384k,nr_inodes=4096\n",
        )
        .unwrap()
        .remove(&3)
        .unwrap();
        after.records.insert(3, row);
        after.visible.insert("/mnt".into(), 3);
        let source_device = after.records[&3].device;
        exact_storage_delta(&before, &after, 3, source_device).unwrap();
        assert_eq!(after.records[&2], before.records[&2]);
        for flaw in [
            "lower-removed",
            "lower-mutated",
            "foreign-source",
            "reused-device",
            "readonly",
            "executable",
            "wrong-parent",
            "wrong-source-name",
            "foreign-visible",
            "duplicate",
        ] {
            let mut bad = after.clone();
            match flaw {
                "lower-removed" => {
                    bad.records.remove(&2);
                }
                "lower-mutated" => {
                    bad.records.get_mut(&2).unwrap().root = "/other".into();
                }
                "foreign-source" => {
                    bad.records.get_mut(&3).unwrap().target = "/data".into();
                }
                "reused-device" => {
                    bad.records.get_mut(&3).unwrap().device = before.records[&2].device;
                }
                "readonly" => {
                    bad.records.get_mut(&3).unwrap().flags.insert("ro".into());
                }
                "executable" => {
                    bad.records.get_mut(&3).unwrap().flags.remove("noexec");
                }
                "wrong-parent" => {
                    bad.records.get_mut(&3).unwrap().parent = 1;
                }
                "wrong-source-name" => {
                    bad.records.get_mut(&3).unwrap().source = "none".into();
                }
                "foreign-visible" => {
                    bad.visible.insert("/system".into(), 3);
                }
                "duplicate" => {
                    let mut r = bad.records[&3].clone();
                    r.id = 4;
                    bad.records.insert(4, r);
                }
                _ => unreachable!(),
            }
            assert!(
                exact_storage_delta(&before, &bad, 3, source_device).is_err(),
                "{flaw}"
            );
        }
        assert!(exact_storage_delta(&before, &after, 2, source_device).is_err());
        assert!(exact_storage_delta(&before, &after, 3, before.records[&2].device).is_err());
    }
}
