//! Exact post-call view of the original init's three new tmpfs mounts.
//! The initial RuntimeObservation verifier is unchanged. This distinct owner
//! admits one actually executed finite transition at a time, including every
//! retained lower layer and the actual statx-selected visible mount.
use super::*;
use crate::production_namespace::OriginalInitTmpfsRequest;
use crate::production_runtime_assets::OriginalInitMount;

const ORDER: [ActivationRootRole; 3] = [
    ActivationRootRole::Apex,
    ActivationRootRole::BootstrapApex,
    ActivationRootRole::Linkerconfig,
];

fn exact_delta(
    before: &writable_proc::MountInventory,
    after: &writable_proc::MountInventory,
    role: ActivationRootRole,
    source_mount: u64,
    source_device: u64,
) -> Result<()> {
    let old = *before
        .visible
        .get(role.target())
        .ok_or(NamespaceError::Rejected(
            "original tmpfs target absent from prior view",
        ))?;
    if source_mount == 0
        || before.records.contains_key(&source_mount)
        || before
            .records
            .values()
            .any(|row| row.device == source_device)
        || after.records.len() != before.records.len() + 1
    {
        return Err(NamespaceError::Rejected(
            "new tmpfs mount is not one distinct filesystem",
        ));
    }
    for (id, row) in &before.records {
        if after.records.get(id) != Some(row) {
            return Err(NamespaceError::Rejected(
                "original tmpfs call changed a retained mount",
            ));
        }
    }
    let row = after
        .records
        .get(&source_mount)
        .ok_or(NamespaceError::Rejected(
            "actual newly mounted source absent",
        ))?;
    if row.parent != old
        || row.device != source_device
        || row.target != role.target()
        || row.root != "/"
        || row.filesystem != "tmpfs"
        || row.source != "tmpfs"
        || !["rw", "nosuid", "nodev", "noexec"]
            .iter()
            .all(|f| row.flags.contains(*f))
        || row.flags.contains("ro")
        || !row.options.split(',').any(|v| v == "rw")
        || row.options.split(',').any(|v| v == "ro")
    {
        return Err(NamespaceError::Rejected(
            "new tmpfs mount has another source, target or protection",
        ));
    }
    let mut visible = before.visible.clone();
    visible.insert(role.target().into(), source_mount);
    if after.visible != visible {
        return Err(NamespaceError::Rejected(
            "original tmpfs call changed an undeclared visible mount",
        ));
    }
    Ok(())
}

struct PublishedRoot {
    role: ActivationRootRole,
    source: File,
    node: ImmutableNode,
    mount_id: u64,
}

impl PublishedRoot {
    fn same_node(&self, file: &File) -> Result<bool> {
        let now = ImmutableNode::of(file)?;
        Ok((now.dev, now.ino, now.mode, now.uid, now.gid)
            == (
                self.node.dev,
                self.node.ino,
                self.node.mode,
                self.node.uid,
                self.node.gid,
            )
            && now.nlink >= 2
            && writable_proc::held_mount_id(file)? == self.mount_id)
    }
}

pub(crate) struct InitialMountProjection {
    identity: ProcessIdentity,
    nonce: [u8; 16],
    pidfd: Node,
    proc: Node,
    expected: writable_proc::MountInventory,
    roots: Vec<PublishedRoot>,
    failed: bool,
}

impl InitialMountProjection {
    pub(crate) fn begin(observation: &RuntimeObservation, child: &TreeChild) -> Result<Self> {
        if observation.activation_count != 3 {
            return Err(NamespaceError::Rejected(
                "original tmpfs calls require all three fixed roots",
            ));
        }
        let expected = observation.verify_current(child)?;
        let value = Self {
            identity: child.identity,
            nonce: child.nonce,
            pidfd: descriptor_node(child.pidfd.as_fd())?,
            proc: child.proc_node,
            expected,
            roots: Vec::new(),
            failed: false,
        };
        value.verify_current(observation, child)?;
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
                "post-init mount view belongs to another tree",
            ));
        }
        Ok(())
    }

    fn observe(
        &self,
        observation: &RuntimeObservation,
        child: &TreeChild,
    ) -> Result<writable_proc::MountInventory> {
        self.original(child)?;
        let now = writable_proc::MountInventory::observe(child, "original-init-tmpfs-view")?;
        if now != self.expected {
            return Err(NamespaceError::Rejected(
                "complete original post-mount view changed",
            ));
        }
        self.verify_roles(observation, child, &now)?;
        Ok(now)
    }

    fn verify_roles(
        &self,
        observation: &RuntimeObservation,
        child: &TreeChild,
        now: &writable_proc::MountInventory,
    ) -> Result<()> {
        let root = held_child_root(child)?;
        observation.verify_private_root(&root)?;
        for role in &observation.roles {
            if !role.same_node(&role.source)? {
                return Err(NamespaceError::Rejected(
                    "original prepared source custody changed",
                ));
            }
            let target = writable_proc::target_from_root(&root, role.target)?;
            if let Some(published) = self.roots.iter().find(|v| v.role.target() == role.target) {
                if role.activation != Some(published.role)
                    || !published.same_node(&published.source)?
                    || !published.same_node(&target)?
                    || now.visible.get(role.target) != Some(&published.mount_id)
                {
                    return Err(NamespaceError::Rejected(
                        "actual new root differs from original published source",
                    ));
                }
                for file in [&role.source, &published.source, &target] {
                    verify_activation_root(
                        file,
                        published.role,
                        child.uids.start,
                        child.gids.start,
                    )
                    .map_err(|e| NamespaceError::RuntimeResource(e.to_string()))?;
                }
            } else {
                if !role.same_node(&target)?
                    || now.visible.get(role.target) != Some(&writable_proc::held_mount_id(&target)?)
                {
                    return Err(NamespaceError::Rejected(
                        "unaffected runtime role changed after original mount",
                    ));
                }
                if let Some(activation) = role.activation {
                    for file in [&role.source, &target] {
                        verify_activation_root(
                            file,
                            activation,
                            child.uids.start,
                            child.gids.start,
                        )
                        .map_err(|e| NamespaceError::RuntimeResource(e.to_string()))?;
                    }
                } else if role.target == QUERY_TARGET {
                    observation
                        .query
                        .as_ref()
                        .ok_or(NamespaceError::Rejected("original query custody absent"))?
                        .verify(&target)?;
                } else {
                    image_flags(&target, role.noexec)?;
                }
            }
        }
        self.original(child)
    }

    /// Non-propagation identity and role checks only. The distinct later
    /// propagation owner must supply its actual separately verified inventory;
    /// this method never observes or classifies a shared mount as private.
    pub(super) fn verify_propagated_base(
        &self,
        observation: &RuntimeObservation,
        child: &TreeChild,
        now: &writable_proc::MountInventory,
    ) -> Result<()> {
        self.original(child)?;
        if !self.complete() || now != &self.expected {
            return Err(NamespaceError::Rejected(
                "propagation changed the completed original tmpfs base",
            ));
        }
        self.verify_roles(observation, child, now)
    }

    pub(crate) fn verify_current(
        &self,
        observation: &RuntimeObservation,
        child: &TreeChild,
    ) -> Result<writable_proc::MountInventory> {
        if self.failed {
            return Err(NamespaceError::Rejected(
                "failed original mount view requires tree retirement",
            ));
        }
        self.observe(observation, child)
    }

    /// The only source issuer is the actual operation guard, while its
    /// original notification is still pending and the helper is already reaped.
    pub(crate) fn admit_actual(
        &mut self,
        observation: &RuntimeObservation,
        child: &TreeChild,
        init: &ExecutedInitWitness<'_>,
        request: &OriginalInitTmpfsRequest<'_>,
        completed: &OriginalInitMount,
    ) -> Result<()> {
        if self.failed || ORDER.get(self.roots.len()) != Some(&request.role()) {
            return Err(NamespaceError::Rejected(
                "original init tmpfs sequence differs",
            ));
        }
        self.original(child)?;
        request.revalidate(init)?;
        self.failed = true;
        let source = completed
            .published_root(init, request)
            .map_err(|e| NamespaceError::RuntimeResource(e.to_string()))?;
        let source_mount = writable_proc::held_mount_id(&source)?;
        let node = ImmutableNode::of(&source)?;
        let after =
            writable_proc::MountInventory::observe(child, "after-original-init-tmpfs-call")?;
        exact_delta(
            &self.expected,
            &after,
            request.role(),
            source_mount,
            node.dev,
        )?;
        self.roots.push(PublishedRoot {
            role: request.role(),
            source,
            node,
            mount_id: source_mount,
        });
        self.expected = after;
        self.observe(observation, child)?;
        request.revalidate(init)?;
        self.failed = false;
        Ok(())
    }

    pub(crate) fn complete(&self) -> bool {
        !self.failed && self.roots.len() == ORDER.len()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use writable_proc::{MountInventory, MountRecord};

    fn fixture(role: ActivationRootRole) -> (MountInventory, MountInventory) {
        let old = MountRecord {
            id: 2,
            parent: 1,
            device: 10,
            root: "/".into(),
            target: role.target().into(),
            flags: ["rw", "nosuid", "nodev", "noexec"]
                .into_iter()
                .map(str::to_owned)
                .collect(),
            filesystem: "tmpfs".into(),
            source: "none".into(),
            options: "rw,size=65536k,mode=755".into(),
        };
        let before = MountInventory {
            records: BTreeMap::from([(2, old.clone())]),
            visible: BTreeMap::from([(role.target().into(), 2)]),
        };
        let added = MountRecord {
            id: 3,
            parent: 2,
            device: 11,
            source: "tmpfs".into(),
            ..old
        };
        let mut after = before.clone();
        after.records.insert(3, added);
        after.visible.insert(role.target().into(), 3);
        (before, after)
    }

    #[test]
    fn original_tmpfs_delta_retains_lower_layers_and_only_one_visible_replacement() {
        for role in ORDER {
            let (before, after) = fixture(role);
            exact_delta(&before, &after, role, 3, 11).unwrap();
            assert!(exact_delta(&before, &before, role, 3, 11).is_err());
            for changed in [
                "old-row",
                "removed-old",
                "extra",
                "parent",
                "device",
                "source",
                "filesystem",
                "root",
                "flags",
                "options",
                "alias",
                "invisible",
            ] {
                let mut wrong = after.clone();
                match changed {
                    "old-row" => wrong.records.get_mut(&2).unwrap().options.push_str(",ro"),
                    "removed-old" => {
                        wrong.records.remove(&2);
                    }
                    "extra" => {
                        let mut extra = wrong.records[&3].clone();
                        extra.id = 4;
                        wrong.records.insert(4, extra);
                    }
                    "parent" => wrong.records.get_mut(&3).unwrap().parent = 1,
                    "device" => wrong.records.get_mut(&3).unwrap().device = 10,
                    "source" => wrong.records.get_mut(&3).unwrap().source = "none".into(),
                    "filesystem" => wrong.records.get_mut(&3).unwrap().filesystem = "ramfs".into(),
                    "root" => wrong.records.get_mut(&3).unwrap().root = "/foreign".into(),
                    "flags" => {
                        wrong.records.get_mut(&3).unwrap().flags.remove("nodev");
                    }
                    "options" => wrong.records.get_mut(&3).unwrap().options = "ro".into(),
                    "alias" => {
                        wrong.visible.insert("/foreign".into(), 3);
                    }
                    "invisible" => {
                        wrong.visible.insert(role.target().into(), 2);
                    }
                    _ => unreachable!(),
                }
                assert!(
                    exact_delta(&before, &wrong, role, 3, 11).is_err(),
                    "{changed}"
                );
            }
            assert!(exact_delta(&before, &after, role, 2, 11).is_err());
            assert!(exact_delta(&before, &after, role, 3, 10).is_err());
        }
    }
}
