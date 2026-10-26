// SPDX-License-Identifier: MPL-2.0

//! Prepared per-CPU group entities. Production uses this same tree's root leaf
//! until live membership admission and cross-CPU handoff are implemented.

use alloc::{sync::Weak, vec, vec::Vec};

use ostd::{Error, Result};

use super::*;
use crate::fs::cgroupfs::CpuSchedulingGroup;

mod prepare;

pub(super) type GroupId = usize;

#[derive(Debug)]
struct Node {
    owner: Option<CpuSchedulingGroup>,
    parent: Option<GroupId>,
    weight: u64,
    vruntime: u64,
    min_vruntime: u64,
    tasks: BinaryHeap<Reverse<FairQueueItem>>,
    children: BinaryHeap<Reverse<(u64, GroupId)>>,
    task_weight: u64,
    child_weight: u64,
    queued_tasks: usize,
    admitted_tasks: usize,
    admitted_children: usize,
    queued: bool,
    current: bool,
    current_child: Option<GroupId>,
    pending_child: Option<GroupId>,
    pending_task_key: Option<u64>,
    period_delta: u64,
}

impl Node {
    fn new(owner: Option<CpuSchedulingGroup>, parent: Option<GroupId>) -> Self {
        let weight = owner
            .as_ref()
            .map_or(WEIGHT_0, |owner| owner.weight() * WEIGHT_0 / 100);
        Self {
            owner,
            parent,
            weight,
            vruntime: 0,
            min_vruntime: 0,
            tasks: BinaryHeap::new(),
            children: BinaryHeap::new(),
            task_weight: 0,
            child_weight: 0,
            queued_tasks: 0,
            admitted_tasks: 0,
            admitted_children: 0,
            queued: false,
            current: false,
            current_child: None,
            pending_child: None,
            pending_task_key: None,
            period_delta: 0,
        }
    }

    fn count(&self) -> usize {
        self.tasks.len() + self.children.len() + 1
    }

    fn period(&self) -> u64 {
        (base_slice_clocks() * self.count().max(1) as u64).max(min_period_clocks())
            * u64::from((1 + num_cpus()).ilog2())
    }

    fn vtime_slice(&self) -> u64 {
        self.period() / self.count().max(1) as u64
    }
}

/// A move-only selection, consumed at either cancellation or the real handoff.
pub(in crate::sched::sched_class) struct Selection {
    leaf: GroupId,
}

#[derive(Debug)]
struct Binding {
    key: usize,
    task: Weak<Task>,
    leaf: GroupId,
}

#[derive(Debug)]
pub(in crate::sched::sched_class) struct GroupTree {
    nodes: Vec<Node>,
    bindings: Vec<Binding>,
    current_leaf: Option<GroupId>,
    pending: Option<GroupId>,
    legacy_root: bool,
}

impl GroupTree {
    pub(super) fn root() -> Self {
        Self {
            nodes: vec![Node::new(None, None)],
            bindings: Vec::new(),
            current_leaf: None,
            pending: None,
            legacy_root: true,
        }
    }

    fn binding(&self, task: &Task) -> Option<GroupId> {
        if self.legacy_root {
            return Some(0);
        }
        self.bindings
            .binary_search_by_key(&(task as *const Task as usize), |binding| binding.key)
            .ok()
            .and_then(|index| {
                let binding = &self.bindings[index];
                binding
                    .task
                    .upgrade()
                    .filter(|original| core::ptr::eq(original.as_ref(), task))
                    .map(|_| binding.leaf)
            })
    }

    fn activate(&mut self, mut id: GroupId) {
        while let Some(parent) = self.nodes[id].parent {
            if self.nodes[id].queued || self.nodes[id].current {
                break;
            }
            self.nodes[id].vruntime = self.nodes[id].vruntime.max(self.nodes[parent].min_vruntime);
            let key = self.nodes[id].vruntime;
            let weight = self.nodes[id].weight;
            // All non-root child slots were admitted by prepare().
            assert!(self.nodes[parent].children.len() < self.nodes[parent].admitted_children);
            self.nodes[parent].children.push(Reverse((key, id)));
            self.nodes[parent].child_weight += weight;
            self.nodes[id].queued = true;
            id = parent;
        }
    }

    pub(super) fn enqueue(
        &mut self,
        task: Arc<Task>,
        flags: Option<EnqueueFlags>,
    ) -> core::result::Result<(), Arc<Task>> {
        let Some(leaf) = self.binding(&task) else {
            return Err(task);
        };
        let node = &mut self.nodes[leaf];
        if !self.legacy_root {
            assert!(node.tasks.len() < node.admitted_tasks);
        }
        let attr = &task.as_thread().unwrap().sched_attr().fair;
        let floor = node.min_vruntime
            + if flags == Some(EnqueueFlags::Spawn) {
                node.vtime_slice()
            } else {
                0
            };
        let (_, weight) = attr.fetch_weight();
        let vruntime = attr.vruntime.fetch_max(floor, Ordering::Relaxed).max(floor);
        node.tasks.push(Reverse(FairQueueItem(task, vruntime)));
        node.task_weight += weight;
        let mut id = Some(leaf);
        while let Some(at) = id {
            self.nodes[at].queued_tasks += 1;
            id = self.nodes[at].parent;
        }
        self.activate(leaf);
        Ok(())
    }

    pub(super) fn len(&self) -> usize {
        self.nodes[0].queued_tasks
    }

    #[cfg(ktest)]
    pub(in crate::sched::sched_class) fn state(&self, id: usize) -> (u64, usize, bool) {
        (
            self.nodes[id].vruntime,
            self.nodes[id].queued_tasks,
            self.nodes[id].current,
        )
    }

    #[cfg(ktest)]
    pub(in crate::sched::sched_class) fn capacities(&self) -> Vec<(usize, usize)> {
        self.nodes
            .iter()
            .map(|node| (node.tasks.capacity(), node.children.capacity()))
            .collect()
    }

    pub(super) fn select(&mut self) -> Option<(Arc<Task>, Selection)> {
        assert!(self.pending.is_none());
        if self.len() == 0 {
            return None;
        }
        let mut id = 0;
        loop {
            let node = &self.nodes[id];
            let task_key = node.tasks.peek().map(|item| item.0.key());
            let queued_child = node.children.peek().map(|item| item.0);
            let current_child = node
                .current_child
                .filter(|&child| self.nodes[child].queued_tasks > 0)
                .map(|child| (self.nodes[child].vruntime, child));
            let child = match (queued_child, current_child) {
                (Some(a), Some(b)) => Some(a.min(b)),
                (a, b) => a.or(b),
            };
            if task_key.is_some_and(|key| child.is_none_or(|candidate| key <= candidate.0)) {
                let Reverse(FairQueueItem(task, key)) = self.nodes[id].tasks.pop().unwrap();
                self.nodes[id].pending_task_key = Some(key);
                let (weight, _) = task.as_thread().unwrap().sched_attr().fair.fetch_weight();
                self.nodes[id].task_weight -= weight;
                let mut at = Some(id);
                while let Some(index) = at {
                    self.nodes[index].queued_tasks -= 1;
                    at = self.nodes[index].parent;
                }
                self.pending = Some(id);
                return Some((task, Selection { leaf: id }));
            }
            let (_, child) = child.expect("queued descendant must have an active path");
            self.nodes[id].pending_child = Some(child);
            if self.nodes[child].queued {
                let Reverse((_, popped)) = self.nodes[id].children.pop().unwrap();
                assert_eq!(popped, child);
                let weight = self.nodes[child].weight;
                self.nodes[id].child_weight -= weight;
                self.nodes[child].queued = false;
            }
            id = child;
        }
    }

    pub(super) fn cancel(&mut self, selected: Selection) {
        assert_eq!(self.pending.take(), Some(selected.leaf));
        let mut id = Some(selected.leaf);
        while let Some(at) = id {
            if self.nodes[at].queued_tasks > 0 {
                self.activate(at);
            }
            self.nodes[at].pending_child = None;
            self.nodes[at].pending_task_key = None;
            id = self.nodes[at].parent;
        }
    }

    fn ancestor(&self, ancestor: GroupId, mut leaf: GroupId) -> bool {
        loop {
            if leaf == ancestor {
                return true;
            }
            let Some(parent) = self.nodes[leaf].parent else {
                return false;
            };
            leaf = parent;
        }
    }

    fn change_current(&mut self, next: Option<GroupId>) {
        let mut old = self.current_leaf;
        while let Some(id) = old {
            if next.is_none_or(|leaf| !self.ancestor(id, leaf)) {
                self.nodes[id].current = false;
                self.nodes[id].current_child = None;
                if self.nodes[id].queued_tasks > 0 {
                    self.activate(id);
                }
            }
            old = self.nodes[id].parent;
        }
        let mut child = None;
        let mut at = next;
        while let Some(id) = at {
            if !self.nodes[id].current {
                self.nodes[id].period_delta = 0;
            }
            self.nodes[id].current = true;
            self.nodes[id].current_child = child;
            child = Some(id);
            at = self.nodes[id].parent;
        }
        self.current_leaf = next;
    }

    pub(super) fn commit(&mut self, selected: Selection) {
        assert_eq!(self.pending.take(), Some(selected.leaf));
        self.change_current(Some(selected.leaf));
        let mut at = Some(selected.leaf);
        while let Some(id) = at {
            self.nodes[id].pending_child = None;
            self.nodes[id].pending_task_key = None;
            at = self.nodes[id].parent;
        }
    }

    pub(super) fn finish_current(&mut self) {
        self.change_current(None);
    }

    pub(super) fn attach_current(&mut self, task: &Arc<Task>) {
        // Only used to initialize an otherwise empty queue/current pair.
        assert_eq!(self.len(), 0);
        self.change_current(Some(
            self.binding(task)
                .expect("current task needs an admitted binding"),
        ));
    }

    pub(super) fn charge(&mut self, task: &Task, delta: u64) {
        if self.current_leaf.is_none() {
            assert_eq!(
                self.binding(task),
                Some(0),
                "live non-root class rebinding is not admitted"
            );
            self.change_current(Some(0));
        }
        let leaf = self.current_leaf.unwrap();
        let mut id = Some(leaf);
        while let Some(at) = id {
            let node = &mut self.nodes[at];
            node.period_delta = node.period_delta.saturating_add(delta);
            if at != 0 {
                let increment = (u128::from(delta) * u128::from(WEIGHT_0) / u128::from(node.weight))
                    .min(u128::from(u64::MAX)) as u64;
                node.vruntime = node.vruntime.saturating_add(increment);
            }
            id = node.parent;
        }
        let mut at = Some(leaf);
        while let Some(id) = at {
            let current = self.nodes[id].current_child.map_or_else(
                || {
                    task.as_thread()
                        .unwrap()
                        .sched_attr()
                        .fair
                        .vruntime
                        .load(Ordering::Relaxed)
                },
                |child| self.nodes[child].vruntime,
            );
            let queued_task = self.nodes[id].tasks.peek().map(|item| item.0.key());
            let queued_child = self.nodes[id].children.peek().map(|item| item.0.0);
            let pending = self.nodes[id]
                .pending_child
                .map(|child| self.nodes[child].vruntime)
                .or(self.nodes[id].pending_task_key);
            let minimum = queued_task
                .into_iter()
                .chain(queued_child)
                .chain(pending)
                .fold(current, u64::min);
            self.nodes[id].min_vruntime = self.nodes[id].min_vruntime.max(minimum);
            at = self.nodes[id].parent;
        }
    }

    pub(super) fn should_preempt(
        &mut self,
        rt: &CurrentRuntime,
        attr: &SchedAttr,
        flags: UpdateFlags,
    ) -> bool {
        if self.len() == 0 {
            return false;
        }
        if self.current_leaf.is_none() {
            return true;
        }
        if matches!(flags, UpdateFlags::Wait | UpdateFlags::Exit) {
            return true;
        }
        let (_, weight) = attr.fair.fetch_weight();
        let mut current_weight = weight;
        let mut current_key = attr.fair.vruntime.load(Ordering::Relaxed);
        let mut at = self.current_leaf.or(Some(0));
        while let Some(id) = at {
            let node = &self.nodes[id];
            let elapsed = if Some(id) == self.current_leaf {
                rt.period_delta
            } else {
                self.nodes[node.current_child.unwrap()].period_delta
            };
            if elapsed
                > node.period() * current_weight
                    / (node.task_weight + node.child_weight + current_weight)
                || current_key > node.min_vruntime.saturating_add(node.vtime_slice())
            {
                return true;
            }
            current_key = node.vruntime;
            current_weight = node.weight;
            at = node.parent;
        }
        false
    }
}
