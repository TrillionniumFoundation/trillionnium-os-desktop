// SPDX-License-Identifier: MPL-2.0

//! Bounded admission of persistent UNIX-object ownership edges.
//!
//! The graph contains identities only, never strong references to socket files,
//! queues, processes or payloads. Object locks precede this lock. No graph
//! operation calls an object, allocates, sleeps or drops an object reference.
//! An edge is installed before its strong owner is published and removed only
//! after that owner is removed. Conservative edges can reject an operation;
//! missing edges would permit a real reference cycle.

use crate::prelude::*;

const MAX_NODES: usize = 1024;
const MAX_EDGES: usize = 4096;
const NONE: u16 = u16::MAX;

static GRAPH: SpinLock<Graph> = SpinLock::new(Graph::new());

#[derive(Clone, Debug)]
pub(super) struct Node(Arc<Identity>);

#[derive(Debug)]
struct Identity {
    id: Id,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct Id {
    index: u16,
    generation: u64,
}

impl Node {
    pub(super) fn new() -> Result<Self> {
        // Allocate outside the IRQ-disabled graph transaction, including on
        // error. The unregistered identity's destructor is a no-op.
        let mut identity = Arc::new(Identity {
            id: Id {
                index: NONE,
                generation: 0,
            },
        });
        let result = { GRAPH.disable_irq().lock().allocate_node() };
        let id = result?;
        Arc::get_mut(&mut identity).unwrap().id = id;
        Ok(Self(identity))
    }
}

impl Drop for Identity {
    fn drop(&mut self) {
        if self.id.index == NONE {
            return;
        }
        let mut graph = GRAPH.disable_irq().lock();
        let slot = &mut graph.nodes[self.id.index as usize];
        assert!(slot.live && slot.generation == self.id.generation);
        // Every live lease keeps both endpoint identities alive.
        assert_eq!(slot.incoming, NONE);
        assert_eq!(slot.outgoing, NONE);
        slot.live = false;
    }
}

/// Clones retain the same admission until its last actual control-data owner.
/// Fields that own real files must precede this lease in their containing type.
#[derive(Clone, Debug)]
pub(super) struct Lease {
    _inner: Arc<LeaseInner>,
}

#[derive(Debug)]
struct LeaseInner {
    source: Node,
    targets: Vec<Node>,
    admitted: bool,
}

impl Lease {
    pub(super) fn new(source: &Node, targets: Vec<Node>) -> Result<Self> {
        let mut inner = Arc::new(LeaseInner {
            source: source.clone(),
            targets,
            admitted: false,
        });
        {
            let inner = Arc::get_mut(&mut inner).unwrap();
            let result = {
                GRAPH
                    .disable_irq()
                    .lock()
                    .admit(&inner.source, &inner.targets)
            };
            result?;
            inner.admitted = true;
        }
        Ok(Self { _inner: inner })
    }

    pub(super) fn single(source: &Node, target: &Node) -> Result<Self> {
        let mut targets = Vec::new();
        targets
            .try_reserve_exact(1)
            .map_err(|_| Error::new(Errno::ENOMEM))?;
        targets.push(target.clone());
        Self::new(source, targets)
    }
}

impl Drop for LeaseInner {
    fn drop(&mut self) {
        if self.admitted {
            let mut graph = GRAPH.disable_irq().lock();
            for target in &self.targets {
                graph.release(self.source.0.id, target.0.id);
            }
        }
        // Endpoint Arc fields drop after the graph guard above is released.
    }
}

#[derive(Clone, Copy)]
struct NodeSlot {
    generation: u64,
    live: bool,
    incoming: u16,
    outgoing: u16,
}

impl NodeSlot {
    const EMPTY: Self = Self {
        generation: 0,
        live: false,
        incoming: NONE,
        outgoing: NONE,
    };
}

#[derive(Clone, Copy)]
struct EdgeSlot {
    source: u16,
    target: u16,
    next_in: u16,
    next_out: u16,
    references: u32,
}

impl EdgeSlot {
    const EMPTY: Self = Self {
        source: NONE,
        target: NONE,
        next_in: NONE,
        next_out: NONE,
        references: 0,
    };
}

struct Graph {
    nodes: [NodeSlot; MAX_NODES],
    edges: [EdgeSlot; MAX_EDGES],
}

impl Graph {
    const fn new() -> Self {
        Self {
            nodes: [NodeSlot::EMPTY; MAX_NODES],
            edges: [EdgeSlot::EMPTY; MAX_EDGES],
        }
    }

    fn allocate_node(&mut self) -> Result<Id> {
        for (index, slot) in self.nodes.iter_mut().enumerate() {
            if slot.live {
                continue;
            }
            let Some(generation) = slot.generation.checked_add(1) else {
                continue;
            };
            *slot = NodeSlot {
                generation,
                live: true,
                ..NodeSlot::EMPTY
            };
            return Ok(Id {
                index: index as u16,
                generation,
            });
        }
        Err(Error::with_message(
            Errno::ENOBUFS,
            "the UNIX ownership graph has no node slots",
        ))
    }

    fn valid(&self, id: Id) -> bool {
        self.nodes
            .get(id.index as usize)
            .is_some_and(|slot| slot.live && slot.generation == id.generation)
    }

    fn find(&self, source: u16, target: u16) -> Option<usize> {
        let mut edge = self.nodes[source as usize].outgoing;
        while edge != NONE {
            let slot = &self.edges[edge as usize];
            if slot.target == target {
                return Some(edge as usize);
            }
            edge = slot.next_out;
        }
        None
    }

    fn admit(&mut self, source: &Node, targets: &[Node]) -> Result<()> {
        let source = source.0.id;
        if !self.valid(source) || targets.iter().any(|target| !self.valid(target.0.id)) {
            return Err(Error::new(Errno::EINVAL));
        }
        // Reverse reachability marks all objects already owning the source.
        // Each live node enters the fixed stack at most once; each existing
        // edge is visited at most once. No recursion or heap scratch storage.
        let mut reaches_source = [false; MAX_NODES];
        let mut pending = [NONE; MAX_NODES];
        let mut count = 1;
        pending[0] = source.index;
        reaches_source[source.index as usize] = true;
        while count > 0 {
            count -= 1;
            let mut edge = self.nodes[pending[count] as usize].incoming;
            while edge != NONE {
                let slot = &self.edges[edge as usize];
                if !reaches_source[slot.source as usize] {
                    reaches_source[slot.source as usize] = true;
                    pending[count] = slot.source;
                    count += 1;
                }
                edge = slot.next_in;
            }
        }
        for target in targets {
            if reaches_source[target.0.id.index as usize] {
                return Err(Error::with_message(
                    Errno::ELOOP,
                    "the UNIX ownership edge would create a cycle",
                ));
            }
        }
        // Admit the whole batch or undo only its unpublished prefix. The lock
        // remains held through rollback, so concurrent opposite edges cannot
        // both observe an acyclic prior graph.
        for (index, target) in targets.iter().enumerate() {
            if let Err(error) = self.add(source.index, target.0.id.index) {
                for prior in &targets[..index] {
                    self.release(source, prior.0.id);
                }
                return Err(error);
            }
        }
        Ok(())
    }

    fn add(&mut self, source: u16, target: u16) -> Result<()> {
        if let Some(index) = self.find(source, target) {
            self.edges[index].references = self.edges[index]
                .references
                .checked_add(1)
                .ok_or_else(|| Error::new(Errno::ENOBUFS))?;
            return Ok(());
        }
        let index = self
            .edges
            .iter()
            .position(|edge| edge.references == 0)
            .ok_or_else(|| {
                Error::with_message(Errno::ENOBUFS, "the UNIX ownership graph has no edge slots")
            })?;
        self.edges[index] = EdgeSlot {
            source,
            target,
            next_in: self.nodes[target as usize].incoming,
            next_out: self.nodes[source as usize].outgoing,
            references: 1,
        };
        self.nodes[target as usize].incoming = index as u16;
        self.nodes[source as usize].outgoing = index as u16;
        Ok(())
    }

    fn release(&mut self, source: Id, target: Id) {
        assert!(self.valid(source) && self.valid(target));
        let index = self.find(source.index, target.index).unwrap();
        self.edges[index].references -= 1;
        if self.edges[index].references != 0 {
            return;
        }
        let removed = self.edges[index];
        let mut link = &mut self.nodes[source.index as usize].outgoing;
        while *link != index as u16 {
            link = &mut self.edges[*link as usize].next_out;
        }
        *link = removed.next_out;
        let mut link = &mut self.nodes[target.index as usize].incoming;
        while *link != index as u16 {
            link = &mut self.edges[*link as usize].next_in;
        }
        *link = removed.next_in;
        self.edges[index] = EdgeSlot::EMPTY;
    }
}

#[cfg(ktest)]
mod tests;
