// SPDX-License-Identifier: MPL-2.0

//! Cold, fallible admission for an immutable internal topology.

use super::*;

impl GroupTree {
    /// Build the complete internal topology and immutable task bindings before
    /// publication. No group/node/path allocation occurs in scheduling calls.
    /// The root's old task-heap growth remains the pre-existing legacy path.
    pub(in crate::sched::sched_class) fn prepare(
        groups: &[(CpuSchedulingGroup, GroupId)],
        bindings: &[(Arc<Task>, GroupId)],
    ) -> Result<Self> {
        ostd::task::atomic_mode::might_sleep();
        let mut tree = Self {
            nodes: Vec::new(),
            bindings: Vec::new(),
            current_leaf: None,
            pending: None,
            legacy_root: false,
        };
        tree.nodes
            .try_reserve_exact(groups.len().checked_add(1).ok_or(Error::Overflow)?)
            .map_err(|_| Error::NoMemory)?;
        tree.bindings
            .try_reserve_exact(bindings.len())
            .map_err(|_| Error::NoMemory)?;
        tree.nodes.push(Node::new(None, None));
        for (owner, parent) in groups {
            if *parent >= tree.nodes.len()
                || tree.nodes.iter().any(|n| {
                    n.owner
                        .as_ref()
                        .is_some_and(|old| old.same_incarnation(owner))
                })
            {
                return Err(Error::InvalidArgs);
            }
            let original_parent = owner.parent().ok_or(Error::InvalidArgs)?;
            if let Some(parent_owner) = &tree.nodes[*parent].owner {
                if !original_parent.same_incarnation(parent_owner) {
                    return Err(Error::InvalidArgs);
                }
            } else if *parent != 0 || original_parent.parent().is_some() {
                return Err(Error::InvalidArgs);
            } else {
                tree.nodes[0].owner = Some(original_parent);
            }
            tree.nodes
                .push(Node::new(Some(owner.clone()), Some(*parent)));
        }
        for id in 1..tree.nodes.len() {
            let parent = tree.nodes[id].parent.unwrap();
            tree.nodes[parent].admitted_children += 1;
        }
        for (task, leaf) in bindings {
            if *leaf >= tree.nodes.len() {
                return Err(Error::InvalidArgs);
            }
            match CpuSchedulingGroup::for_task(task) {
                Some(owner) => {
                    if let Some(expected) = &tree.nodes[*leaf].owner {
                        if !expected.same_incarnation(&owner) {
                            return Err(Error::InvalidArgs);
                        }
                    } else if *leaf == 0 && owner.parent().is_none() {
                        tree.nodes[0].owner = Some(owner);
                    } else {
                        return Err(Error::InvalidArgs);
                    }
                }
                None if *leaf == 0 => (),
                None => return Err(Error::InvalidArgs),
            }
            tree.bindings.push(Binding {
                key: Arc::as_ptr(task) as usize,
                task: Arc::downgrade(task),
                leaf: *leaf,
            });
            tree.nodes[*leaf].admitted_tasks += 1;
        }
        tree.bindings.sort_unstable_by_key(|binding| binding.key);
        if tree
            .bindings
            .windows(2)
            .any(|pair| pair[0].key == pair[1].key)
        {
            return Err(Error::InvalidArgs);
        }
        for node in &mut tree.nodes {
            node.children
                .try_reserve_exact(node.admitted_children)
                .map_err(|_| Error::NoMemory)?;
            node.tasks
                .try_reserve_exact(node.admitted_tasks)
                .map_err(|_| Error::NoMemory)?;
        }
        Ok(tree)
    }
}
