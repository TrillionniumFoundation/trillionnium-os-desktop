//! Exact mount-graph epochs around the original init's native NEWNS round trip.
//! No path list, serialized mount IDs, bool or standalone parser result can
//! construct an accepted epoch. The entry baseline comes from the completed
//! original six-call storage owner; both native results remain ptrace-stopped.
use super::super::runtime::NativeStorageSnapshot;
use super::super::writable_proc::{MountInventory, MountRecord};
use super::*;
use std::collections::{BTreeMap, BTreeSet};

#[derive(Clone, Debug, Eq, PartialEq)]
struct Records {
    base: MountInventory,
    shared: BTreeMap<u64, u64>,
    masters: BTreeMap<u64, u64>,
}

fn parse(raw: &[u8]) -> Result<Records> {
    let text = std::str::from_utf8(raw)
        .map_err(|_| NamespaceError::Rejected("native mount inventory encoding"))?;
    if raw.is_empty() || raw.len() > 65536 || !text.ends_with('\n') || text.lines().count() > 256 {
        return Err(NamespaceError::Rejected(
            "bounded complete native mount inventory",
        ));
    }
    let mut ordinary = String::new();
    let mut shared = BTreeMap::new();
    let mut masters = BTreeMap::new();
    for line in text.lines() {
        let (left, right) = line
            .split_once(" - ")
            .ok_or(NamespaceError::Rejected("native mount separator"))?;
        let fields: Vec<_> = left.split_ascii_whitespace().collect();
        if !(6..=8).contains(&fields.len()) {
            return Err(NamespaceError::Rejected(
                "native mount optional fields differ",
            ));
        }
        let id = fields[0]
            .parse::<u64>()
            .map_err(|_| NamespaceError::Rejected("native mount ID encoding"))?;
        if id == 0 || id.to_string() != fields[0] {
            return Err(NamespaceError::Rejected("noncanonical native mount ID"));
        }
        let mut have_shared = false;
        let mut have_master = false;
        for field in &fields[6..] {
            let (kind, value) = field
                .split_once(':')
                .ok_or(NamespaceError::Rejected("native propagation field"))?;
            let group = value
                .parse::<u64>()
                .map_err(|_| NamespaceError::Rejected("native propagation group encoding"))?;
            if group == 0 || group.to_string() != value {
                return Err(NamespaceError::Rejected(
                    "noncanonical native propagation group",
                ));
            }
            match kind {
                "shared" if !have_shared && !have_master => {
                    if shared.insert(id, group).is_some() {
                        return Err(NamespaceError::Rejected("duplicate native shared group"));
                    }
                    have_shared = true;
                }
                "master" if !have_master => {
                    if masters.insert(id, group).is_some() {
                        return Err(NamespaceError::Rejected("duplicate native master group"));
                    }
                    have_master = true;
                }
                _ => return Err(NamespaceError::Rejected("foreign native propagation field")),
            }
        }
        if shared
            .get(&id)
            .is_some_and(|group| masters.get(&id) == Some(group))
        {
            return Err(NamespaceError::Rejected("native peer is its own master"));
        }
        ordinary.push_str(&fields[..6].join(" "));
        ordinary.push_str(" - ");
        ordinary.push_str(right);
        ordinary.push('\n');
    }
    let records = super::super::writable_proc::mount_records(ordinary.as_bytes())?;
    Ok(Records {
        base: MountInventory {
            records,
            visible: BTreeMap::new(),
        },
        shared,
        masters,
    })
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct VisibleNode {
    node: Node,
    mode: u32,
    uid: u32,
    gid: u32,
}
impl VisibleNode {
    fn of(file: &File) -> Result<Self> {
        let m = file.metadata()?;
        Ok(Self {
            node: Node::of(file)?,
            mode: m.mode(),
            uid: m.uid(),
            gid: m.gid(),
        })
    }
}

struct View {
    records: Records,
    visible_nodes: BTreeMap<String, VisibleNode>,
    held: Vec<(String, File, u64, VisibleNode)>,
    root: File,
    root_node: VisibleNode,
}
impl View {
    fn duplicate_held(&self) -> Result<Self> {
        self.revalidate_held()?;
        let held = self
            .held
            .iter()
            .map(|(target, file, mount, node)| {
                Ok((target.clone(), file.try_clone()?, *mount, *node))
            })
            .collect::<Result<Vec<_>>>()?;
        let value = Self {
            records: self.records.clone(),
            visible_nodes: self.visible_nodes.clone(),
            held,
            root: self.root.try_clone()?,
            root_node: self.root_node,
        };
        value.revalidate_held()?;
        self.revalidate_held()?;
        Ok(value)
    }

    fn observe(proc: &File, root: &File) -> Result<Self> {
        let raw = read_proc(proc, "mountinfo")?;
        let mut records = parse(&raw)?;
        let root_node = VisibleNode::of(root)?;
        let targets: BTreeSet<_> = records
            .base
            .records
            .values()
            .map(|record| record.target.clone())
            .collect();
        let mut actual = BTreeMap::new();
        let mut visible_nodes = BTreeMap::new();
        let mut held = Vec::new();
        for target in targets {
            let file = super::super::writable_proc::target_from_root(root, &target)?;
            let mount = super::super::writable_proc::held_mount_id(&file)?;
            let node = VisibleNode::of(&file)?;
            actual.insert(target.clone(), (mount, node.node.device));
            visible_nodes.insert(target.clone(), node);
            held.push((target, file, mount, node));
        }
        records.base.visible =
            super::super::writable_proc::checked_visible(&records.base.records, &actual)?;
        let value = Self {
            records,
            visible_nodes,
            held,
            root: root.try_clone()?,
            root_node,
        };
        value.revalidate_held()?;
        if read_proc(proc, "mountinfo")? != raw {
            return Err(NamespaceError::Rejected(
                "native mount view changed while stopped",
            ));
        }
        Ok(value)
    }

    fn revalidate_held(&self) -> Result<()> {
        if VisibleNode::of(&self.root)? != self.root_node {
            return Err(NamespaceError::Rejected("held native root changed"));
        }
        for (target, file, mount, node) in &self.held {
            let named = super::super::writable_proc::target_from_root(&self.root, target)?;
            if VisibleNode::of(file)? != *node
                || VisibleNode::of(&named)? != *node
                || super::super::writable_proc::held_mount_id(file)? != *mount
                || super::super::writable_proc::held_mount_id(&named)? != *mount
            {
                return Err(NamespaceError::Rejected(
                    "native visible mount identity changed",
                ));
            }
        }
        Ok(())
    }

    // Only this fixed, already-observed bind may cover the old /apex path.
    // Every original descriptor and every other visible pathname stays exact.
    fn revalidate_bootstrap_bind_history(&self) -> Result<()> {
        if VisibleNode::of(&self.root)? != self.root_node {
            return Err(NamespaceError::Rejected(
                "bootstrap bind changed the held root",
            ));
        }
        for (target, file, mount, node) in &self.held {
            if VisibleNode::of(file)? != *node
                || super::super::writable_proc::held_mount_id(file)? != *mount
            {
                return Err(NamespaceError::Rejected(
                    "bootstrap bind lost an original held mount",
                ));
            }
            if target != "/apex" {
                let named = super::super::writable_proc::target_from_root(&self.root, target)?;
                if VisibleNode::of(&named)? != *node
                    || super::super::writable_proc::held_mount_id(&named)? != *mount
                {
                    return Err(NamespaceError::Rejected(
                        "bootstrap bind changed another visible path",
                    ));
                }
            }
        }
        Ok(())
    }

    fn bootstrap_bind_descriptors(&self, source: &File, target: &File) -> Result<()> {
        for (path, file) in [("/bootstrap-apex", source), ("/apex", target)] {
            let id = self
                .records
                .base
                .visible
                .get(path)
                .ok_or(NamespaceError::Rejected(
                    "bootstrap bind original visible role absent",
                ))?;
            if self.visible_nodes.get(path) != Some(&VisibleNode::of(file)?)
                || super::super::writable_proc::held_mount_id(file)? != *id
            {
                return Err(NamespaceError::Rejected(
                    "bootstrap bind substituted an original role",
                ));
            }
        }
        if Node::of(source)? == Node::of(target)? {
            return Err(NamespaceError::Rejected(
                "bootstrap source and old target must differ",
            ));
        }
        Ok(())
    }

    fn equals_actual(&self, now: &Self) -> Result<()> {
        self.revalidate_held()?;
        now.revalidate_held()?;
        if self.records != now.records
            || self.visible_nodes != now.visible_nodes
            || self.root_node != now.root_node
        {
            return Err(NamespaceError::Rejected("actual namespace epoch changed"));
        }
        Ok(())
    }
}

fn same_row(before: &MountRecord, after: &MountRecord) -> bool {
    before.device == after.device
        && before.root == after.root
        && before.target == after.target
        && before.flags == after.flags
        && before.filesystem == after.filesystem
        && before.source == after.source
        && before.options == after.options
}

fn leaf_mount(records: &Records, id: u64) -> Result<()> {
    if !records.base.records.contains_key(&id) {
        return Err(NamespaceError::Rejected("bootstrap role mount absent"));
    }
    for row in records.base.records.values() {
        if row.id == id {
            continue;
        }
        let mut parent = row.parent;
        let mut visited = BTreeSet::new();
        while let Some(ancestor) = records.base.records.get(&parent) {
            if ancestor.id == id || !visited.insert(ancestor.id) {
                return Err(NamespaceError::Rejected(
                    "bootstrap recursive bind has a child or cyclic edge",
                ));
            }
            parent = ancestor.parent;
        }
    }
    Ok(())
}

fn bootstrap_bind_roles(before: &Records) -> Result<(u64, u64)> {
    let source = *before
        .base
        .visible
        .get("/bootstrap-apex")
        .ok_or(NamespaceError::Rejected("original bootstrap source absent"))?;
    let target = *before
        .base
        .visible
        .get("/apex")
        .ok_or(NamespaceError::Rejected(
            "original private apex target absent",
        ))?;
    if source == target
        || !before.shared.contains_key(&source)
        || before.masters.contains_key(&source)
        || before.shared.contains_key(&target)
        || before.masters.contains_key(&target)
    {
        return Err(NamespaceError::Rejected(
            "original bootstrap bind propagation roles differ",
        ));
    }
    leaf_mount(before, source)?;
    leaf_mount(before, target)?;
    Ok((source, target))
}

/// The original recursive bind is currently a leaf copy. Covered lower mounts
/// remain in the graph; only the visible /apex row changes. This does not turn
/// the shared source into a private mount or invent a propagation exception.
fn bootstrap_bind_delta(before: &Records, after: &Records) -> Result<u64> {
    let (source, target) = bootstrap_bind_roles(before)?;
    if after.base.records.len() != before.base.records.len() + 1 {
        return Err(NamespaceError::Rejected(
            "bootstrap bind must add exactly its actual leaf mount",
        ));
    }
    for (id, row) in &before.base.records {
        if after.base.records.get(id) != Some(row)
            || after.shared.get(id) != before.shared.get(id)
            || after.masters.get(id) != before.masters.get(id)
        {
            return Err(NamespaceError::Rejected(
                "bootstrap bind altered an original graph row",
            ));
        }
    }
    let added = after
        .base
        .records
        .keys()
        .filter(|id| !before.base.records.contains_key(id))
        .copied()
        .collect::<Vec<_>>();
    if added.len() != 1 {
        return Err(NamespaceError::Rejected(
            "bootstrap bind new mount identity is ambiguous",
        ));
    }
    let new_id = added[0];
    let source_row = before.base.records.get(&source).unwrap();
    let mut expected = source_row.clone();
    expected.id = new_id;
    expected.parent = target;
    expected.target = "/apex".into();
    let mut visible = before.base.visible.clone();
    visible.insert("/apex".into(), new_id);
    let mut shared = before.shared.clone();
    shared.insert(new_id, *before.shared.get(&source).unwrap());
    if after.base.records.get(&new_id) != Some(&expected)
        || after.base.visible != visible
        || after.shared != shared
        || after.masters != before.masters
    {
        return Err(NamespaceError::Rejected(
            "bootstrap bind source, flags, peer group or visible layer differs",
        ));
    }
    Ok(new_id)
}

/// Matching is by the complete graph and observed visible layers, not row
/// ordering, increasing IDs or a guessed ID offset. Ambiguous copies fail.
fn copied_graph(before: &Records, after: &Records) -> Result<BTreeMap<u64, u64>> {
    if before.base.records.is_empty()
        || before.base.records.len() != after.base.records.len()
        || before
            .base
            .records
            .keys()
            .any(|id| after.base.records.contains_key(id))
        || before.base.visible.keys().collect::<Vec<_>>()
            != after.base.visible.keys().collect::<Vec<_>>()
    {
        return Err(NamespaceError::Rejected(
            "native copy must have a distinct complete mount-ID set",
        ));
    }
    let mut map = BTreeMap::new();
    let mut used = BTreeSet::new();
    let mut external_parents = BTreeMap::new();
    while map.len() != before.base.records.len() {
        let mut progress = false;
        for old in before.base.records.values() {
            if map.contains_key(&old.id) {
                continue;
            }
            let internal = before.base.records.contains_key(&old.parent);
            if internal && !map.contains_key(&old.parent) {
                continue;
            }
            let matches: Vec<_> = after
                .base
                .records
                .values()
                .filter(|new| {
                    !used.contains(&new.id)
                        && same_row(old, new)
                        && before.shared.get(&old.id) == after.shared.get(&new.id)
                        && before.masters.get(&old.id) == after.masters.get(&new.id)
                        && (before.base.visible.get(&old.target) == Some(&old.id))
                            == (after.base.visible.get(&new.target) == Some(&new.id))
                        && if internal {
                            map.get(&old.parent) == Some(&new.parent)
                        } else {
                            !after.base.records.contains_key(&new.parent)
                                && external_parents
                                    .get(&old.parent)
                                    .is_none_or(|id| *id == new.parent)
                                && !external_parents
                                    .iter()
                                    .any(|(id, mapped)| *id != old.parent && *mapped == new.parent)
                        }
                })
                .collect();
            if matches.len() != 1 {
                continue;
            }
            let new = matches[0];
            if !internal {
                external_parents.insert(old.parent, new.parent);
            }
            map.insert(old.id, new.id);
            used.insert(new.id);
            progress = true;
        }
        if !progress {
            return Err(NamespaceError::Rejected(
                "native mount copy has a missing, foreign or ambiguous edge",
            ));
        }
    }
    for (target, id) in &before.base.visible {
        if map.get(id) != after.base.visible.get(target) {
            return Err(NamespaceError::Rejected(
                "native copy changed a visible layer",
            ));
        }
    }
    if used.len() != after.base.records.len() {
        return Err(NamespaceError::Rejected(
            "native copy added a foreign mount",
        ));
    }
    Ok(map)
}

/// Separate historical graph observation for a later, kernel-armed task.
/// It cannot substitute for NativeStorageSnapshot or qualify initial mounts.
pub(super) struct SuccessorGraph {
    view: View,
}
impl SuccessorGraph {
    pub(super) fn before_original_bootstrap_bind(
        &self,
        source: &File,
        target: &File,
    ) -> Result<()> {
        self.view.revalidate_held()?;
        self.view.bootstrap_bind_descriptors(source, target)?;
        bootstrap_bind_roles(&self.view.records)?;
        Ok(())
    }

    pub(super) fn verify_original_bootstrap_bind(
        &self,
        after: &Self,
        source: &File,
        target: &File,
        errno: i32,
    ) -> Result<()> {
        if !(0..=4095).contains(&errno) {
            return Err(NamespaceError::Rejected(
                "bootstrap bind actual errno is invalid",
            ));
        }
        self.view.bootstrap_bind_descriptors(source, target)?;
        if errno != 0 {
            return self.same_observation(after);
        }
        self.view.revalidate_bootstrap_bind_history()?;
        after.view.revalidate_held()?;
        bootstrap_bind_delta(&self.view.records, &after.view.records)?;
        let mut visible = self.view.visible_nodes.clone();
        visible.insert(
            "/apex".into(),
            *self
                .view
                .visible_nodes
                .get("/bootstrap-apex")
                .ok_or(NamespaceError::RetirementUnproven)?,
        );
        if after.view.visible_nodes != visible || after.view.root_node != self.view.root_node {
            return Err(NamespaceError::Rejected(
                "bootstrap bind inode, owner, idmap or root changed",
            ));
        }
        self.view.revalidate_bootstrap_bind_history()?;
        after.view.revalidate_held()
    }

    pub(super) fn revalidate_bootstrap_bind_history(&self) -> Result<()> {
        self.view.revalidate_bootstrap_bind_history()
    }

    pub(super) fn revalidate_held(&self) -> Result<()> {
        self.view.revalidate_held()
    }

    pub(super) fn duplicate_held(&self) -> Result<Self> {
        Ok(Self {
            view: self.view.duplicate_held()?,
        })
    }

    pub(super) fn observe(proc: &File, root: &File) -> Result<Self> {
        Ok(Self {
            view: View::observe(proc, root)?,
        })
    }

    pub(super) fn matches(&self, proc: &File, root: &File) -> Result<()> {
        self.view.equals_actual(&View::observe(proc, root)?)
    }

    pub(super) fn same_observation(&self, after: &Self) -> Result<()> {
        self.view.equals_actual(&after.view)
    }

    pub(super) fn exact_clone(&self, after: &Self) -> Result<()> {
        self.view.revalidate_held()?;
        after.view.revalidate_held()?;
        copied_graph(&self.view.records, &after.view.records)?;
        if self.view.visible_nodes != after.view.visible_nodes
            || self.view.root_node != after.view.root_node
        {
            return Err(NamespaceError::Rejected(
                "inherited native clone changed visible inodes, ownership or idmap",
            ));
        }
        self.view.revalidate_held()?;
        after.view.revalidate_held()
    }
}

pub(super) struct NativeMountEpoch {
    before: View,
    default: Option<View>,
    copied_ids: BTreeMap<u64, u64>,
    restored: bool,
}
impl NativeMountEpoch {
    pub(super) fn begin(snapshot: NativeStorageSnapshot, resources: &Resources) -> Result<Self> {
        snapshot.matches_original(
            resources.binding.identity,
            resources.binding.nonce,
            resources.binding.pidfd,
            resources.binding.proc,
        )?;
        let root = namespace_root(&resources.proc)?;
        if Node::of(&root)? != Node::of(&resources.bootstrap_root)? {
            return Err(NamespaceError::Rejected("native baseline root differs"));
        }
        let before = View::observe(&resources.proc, &root)?;
        snapshot.matches_actual_parts(
            &before.records.base,
            &before.records.shared,
            &before.records.masters,
        )?;
        Ok(Self {
            before,
            default: None,
            copied_ids: BTreeMap::new(),
            restored: false,
        })
    }

    pub(super) fn admit_clone(&mut self, proc: &File, root: &File) -> Result<()> {
        if self.default.is_some() || !self.copied_ids.is_empty() || self.restored {
            return Err(NamespaceError::Rejected("native mount-copy epoch replay"));
        }
        self.before.revalidate_held()?;
        let after = View::observe(proc, root)?;
        let ids = copied_graph(&self.before.records, &after.records)?;
        if self.before.visible_nodes != after.visible_nodes
            || self.before.root_node != after.root_node
        {
            return Err(NamespaceError::Rejected(
                "native copy changed an inode, owner or idmap view",
            ));
        }
        self.before.revalidate_held()?;
        self.default = Some(after);
        self.copied_ids = ids;
        Ok(())
    }

    pub(super) fn verify_default(&self, proc: &File, root: &File) -> Result<()> {
        if self.restored || self.copied_ids.len() != self.before.records.base.records.len() {
            return Err(NamespaceError::Rejected(
                "actual default epoch is incomplete",
            ));
        }
        self.before.revalidate_held()?;
        let expected = self
            .default
            .as_ref()
            .ok_or(NamespaceError::Rejected("native default epoch absent"))?;
        let now = View::observe(proc, root)?;
        expected.equals_actual(&now)
    }

    pub(super) fn admit_restoration(&mut self, proc: &File, root: &File) -> Result<()> {
        if self.restored || self.default.is_none() {
            return Err(NamespaceError::Rejected(
                "original namespace restoration phase",
            ));
        }
        let now = View::observe(proc, root)?;
        self.before.equals_actual(&now)?;
        self.default.as_ref().unwrap().revalidate_held()?;
        self.restored = true;
        Ok(())
    }

    // These graphs are issued only from the completed original two-call
    // observation. Later code cannot mint a baseline from a fresh snapshot.
    pub(super) fn completed_graphs(&self) -> Result<(SuccessorGraph, SuccessorGraph)> {
        self.verify_completed()?;
        let original = SuccessorGraph {
            view: self.before.duplicate_held()?,
        };
        let default = SuccessorGraph {
            view: self
                .default
                .as_ref()
                .ok_or(NamespaceError::RetirementUnproven)?
                .duplicate_held()?,
        };
        self.verify_completed()?;
        Ok((original, default))
    }

    pub(super) fn verify_completed(&self) -> Result<()> {
        if !self.restored || self.copied_ids.len() != self.before.records.base.records.len() {
            return Err(NamespaceError::Rejected(
                "native namespace round trip lacks complete actual epochs",
            ));
        }
        self.before.revalidate_held()?;
        self.default
            .as_ref()
            .ok_or(NamespaceError::RetirementUnproven)?
            .revalidate_held()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn bootstrap_before() -> Records {
        let mut before = parse(
            b"7 900 8:1 / / ro shared:71 - ext4 /dev/system ro\n\
            11 7 0:2 / /apex rw,nosuid,nodev,noexec shared:72 - tmpfs none rw\n\
            19 11 0:3 / /apex rw,nosuid,nodev,noexec - tmpfs tmpfs rw\n\
            23 7 0:4 / /bootstrap-apex rw,nosuid,nodev,noexec shared:73 - tmpfs tmpfs rw\n",
        )
        .unwrap();
        before.base.visible = BTreeMap::from([
            ("/".into(), 7),
            ("/apex".into(), 19),
            ("/bootstrap-apex".into(), 23),
        ]);
        before
    }

    fn bootstrap_after(before: &Records) -> Records {
        let mut after = before.clone();
        let mut row = before.base.records[&23].clone();
        row.id = 13;
        row.parent = 19;
        row.target = "/apex".into();
        after.base.records.insert(13, row);
        after.base.visible.insert("/apex".into(), 13);
        after.shared.insert(13, 73);
        after
    }

    #[test]
    fn original_bootstrap_bind_keeps_covered_layers_and_actual_source_shared_group() {
        let before = bootstrap_before();
        let after = bootstrap_after(&before);
        assert_eq!(bootstrap_bind_delta(&before, &after).unwrap(), 13);
        assert_eq!(after.base.records[&11], before.base.records[&11]);
        assert_eq!(after.base.records[&19], before.base.records[&19]);
        assert_eq!(after.shared[&13], after.shared[&23]);
        assert!(after.base.records.contains_key(&19));
    }

    #[test]
    fn original_bootstrap_bind_rejects_foreign_graph_edges_propagation_and_recursive_children() {
        let original = bootstrap_before();
        for case in [
            "parent", "source", "root", "flags", "visible", "old", "missing", "extra", "peer",
            "master",
        ] {
            let mut after = bootstrap_after(&original);
            match case {
                "parent" => after.base.records.get_mut(&13).unwrap().parent = 7,
                "source" => after.base.records.get_mut(&13).unwrap().source = "foreign".into(),
                "root" => after.base.records.get_mut(&13).unwrap().root = "/other".into(),
                "flags" => {
                    after
                        .base
                        .records
                        .get_mut(&13)
                        .unwrap()
                        .flags
                        .remove("nodev");
                }
                "visible" => {
                    after.base.visible.insert("/apex".into(), 19);
                }
                "old" => {
                    after
                        .base
                        .records
                        .get_mut(&11)
                        .unwrap()
                        .options
                        .push_str(",foreign");
                }
                "missing" => {
                    after.base.records.remove(&11);
                }
                "extra" => {
                    let mut row = after.base.records[&13].clone();
                    row.id = 99;
                    after.base.records.insert(99, row);
                }
                "peer" => {
                    after.shared.insert(13, 99);
                }
                "master" => {
                    after.masters.insert(13, 71);
                }
                _ => unreachable!(),
            }
            assert!(bootstrap_bind_delta(&original, &after).is_err(), "{case}");
        }
        for role in [19, 23] {
            let mut before = original.clone();
            let mut row = before.base.records[&role].clone();
            row.id = 99;
            row.parent = role;
            row.target = format!("{}/nested", row.target);
            before.base.records.insert(99, row);
            assert!(bootstrap_bind_roles(&before).is_err());
        }
        let mut shared_target = original.clone();
        shared_target.shared.insert(19, 72);
        assert!(bootstrap_bind_roles(&shared_target).is_err());
        let mut slave_source = original.clone();
        slave_source.masters.insert(23, 71);
        assert!(bootstrap_bind_roles(&slave_source).is_err());
    }

    fn original() -> Records {
        let mut records = parse(b"7 900 8:1 / / ro shared:71 - ext4 /dev/system ro\n\
            11 7 0:2 / /apex rw,nosuid,nodev,noexec shared:72 - tmpfs none rw\n\
            19 11 0:3 / /apex rw,nosuid,nodev,noexec - tmpfs tmpfs rw\n\
            23 7 0:4 / /mnt rw,nosuid,nodev,noexec shared:73 - tmpfs tmpfs rw\n\
            29 23 0:4 /user /mnt/installer rw,nosuid,nodev,noexec shared:74 master:73 - tmpfs tmpfs rw\n").unwrap();
        records.base.visible = BTreeMap::from([
            ("/".into(), 7),
            ("/apex".into(), 19),
            ("/mnt".into(), 23),
            ("/mnt/installer".into(), 29),
        ]);
        records
    }

    fn actual_copy(before: &Records) -> Records {
        let mapping = BTreeMap::from([(7, 103), (11, 207), (19, 61), (23, 405), (29, 151)]);
        let mut after = before.clone();
        after.base.records = before
            .base
            .records
            .values()
            .map(|old| {
                let mut new = old.clone();
                new.id = mapping[&old.id];
                new.parent = mapping.get(&old.parent).copied().unwrap_or(990);
                (new.id, new)
            })
            .collect();
        after.base.visible = before
            .base
            .visible
            .iter()
            .map(|(path, id)| (path.clone(), mapping[id]))
            .collect();
        after.shared = before
            .shared
            .iter()
            .map(|(id, group)| (mapping[id], *group))
            .collect();
        after.masters = before
            .masters
            .iter()
            .map(|(id, group)| (mapping[id], *group))
            .collect();
        after
    }

    #[test]
    fn native_namespace_copy_keeps_covered_layers_and_shared_slave_groups_without_id_order_assumptions()
     {
        let before = original();
        let after = actual_copy(&before);
        let ids = copied_graph(&before, &after).unwrap();
        assert_eq!(ids[&11], 207);
        assert_eq!(ids[&19], 61);
        assert_eq!(after.base.visible["/apex"], 61);
        assert_eq!(after.shared[&151], 74);
        assert_eq!(after.masters[&151], 73);
    }

    #[test]
    fn native_namespace_copy_rejects_reused_ids_foreign_edges_flags_and_missing_layers() {
        let before = original();
        for case in [
            "reuse", "edge", "flags", "source", "missing", "master", "visible",
        ] {
            let mut after = actual_copy(&before);
            match case {
                "reuse" => {
                    let mut row = after.base.records.remove(&103).unwrap();
                    row.id = 7;
                    after.base.records.insert(7, row);
                }
                "edge" => after.base.records.get_mut(&61).unwrap().parent = 103,
                "flags" => {
                    after
                        .base
                        .records
                        .get_mut(&61)
                        .unwrap()
                        .flags
                        .remove("nodev");
                }
                "source" => after.base.records.get_mut(&151).unwrap().root = "/other".into(),
                "missing" => {
                    after.base.records.remove(&207);
                }
                "master" => {
                    after.masters.insert(151, 74);
                }
                "visible" => {
                    after.base.visible.insert("/apex".into(), 207);
                }
                _ => unreachable!(),
            }
            assert!(copied_graph(&before, &after).is_err(), "{case}");
        }
    }
}
