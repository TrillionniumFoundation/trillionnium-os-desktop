// SPDX-License-Identifier: MPL-2.0

//! Stable cgroup identities for the original physical-frame charge token.
//!
//! The transaction lock covers the complete (at most 65-node) ancestor chain,
//! family admission, and allocation binding. No transaction allocates, sleeps,
//! takes membership/tree/VM locks, or drops an owning Arc. Refund uses precisely
//! the identity captured at admission, including after migration or deletion.

use ostd::sync::LocalIrqDisabled;
use spin::Once;

use crate::prelude::*;

pub(crate) const MAX_MEMORY_DEPTH: usize = 64;
static TRANSACTION: SpinLock<()> = SpinLock::new(());
pub(super) type Transaction = SpinLockGuard<'static, (), LocalIrqDisabled>;

pub(super) fn transaction() -> Transaction {
    TRANSACTION.disable_irq().lock()
}

#[derive(Debug, Default)]
struct State {
    pages: usize,
    max_pages: Option<usize>,
    delegated: bool,
    closed: bool,
    max_events: usize,
}

#[derive(Clone, Copy, Debug)]
pub(crate) struct MemorySnapshot {
    pub(crate) pages: usize,
    pub(crate) max_pages: Option<usize>,
    pub(crate) max_events: usize,
    pub(crate) active: bool,
}

/// Identity survives subtree-control toggles and outstanding frame references.
#[derive(Debug)]
pub(crate) struct MemoryDomain {
    parent: Option<Arc<Self>>,
    depth: usize,
    state: SpinLock<State>,
}

impl MemoryDomain {
    pub(crate) fn root() -> Arc<Self> {
        static ROOT: Once<Arc<MemoryDomain>> = Once::new();
        ROOT.call_once(|| {
            Arc::new(Self {
                parent: None,
                depth: 0,
                state: SpinLock::new(State::default()),
            })
        })
        .clone()
    }

    /// Caller must reject depth overflow before publishing a cgroup node.
    pub(crate) fn child(parent: Arc<Self>) -> Option<Arc<Self>> {
        if parent.depth >= MAX_MEMORY_DEPTH {
            return None;
        }
        let depth = parent.depth + 1;
        Some(Arc::new(Self {
            parent: Some(parent),
            depth,
            state: SpinLock::new(State::default()),
        }))
    }

    fn active(&self, _tx: &Transaction) -> bool {
        self.parent
            .as_ref()
            .is_none_or(|parent| parent.state.lock().delegated)
            && !self.state.lock().closed
    }

    pub(crate) fn snapshot(&self) -> MemorySnapshot {
        let tx = transaction();
        let active = self.active(&tx);
        let state = self.state.lock();
        MemorySnapshot {
            pages: state.pages,
            max_pages: state.max_pages,
            max_events: state.max_events,
            active,
        }
    }

    /// Does not reclaim or invoke OOM. Lower-than-current writes fail atomically.
    pub(crate) fn set_max(&self, limit: Option<usize>) -> bool {
        let tx = transaction();
        if !self.active(&tx) {
            return false;
        }
        let mut state = self.state.lock();
        if limit.is_some_and(|limit| limit < state.pages) {
            return false;
        }
        state.max_pages = limit;
        true
    }

    /// Existing pages are always counted. Re-enabling immediately enforces the
    /// saved limit, even if disabled-period allocations already exceed it.
    pub(crate) fn set_delegated(&self, enabled: bool) {
        let _tx = transaction();
        self.state.lock().delegated = enabled;
    }

    pub(crate) fn close(&self) {
        let _tx = transaction();
        self.state.lock().closed = true;
    }

    pub(super) fn is_closed(&self, _tx: &Transaction) -> bool {
        self.state.lock().closed
    }

    pub(super) fn admit(&self, pages: usize, tx: &Transaction) -> Result<()> {
        let mut cursor = Some(self);
        while let Some(node) = cursor {
            let active = node.active(tx);
            let mut state = node.state.lock();
            if state.closed {
                return Err(Error::cgroup_frame_limit());
            }
            if state.pages.checked_add(pages).is_none_or(|next| {
                next > usize::MAX / PAGE_SIZE
                    || (active && state.max_pages.is_some_and(|max| next > max))
            }) {
                state.max_events = state.max_events.saturating_add(1);
                drop(state);
                // memory.events is hierarchical: the event belongs to the
                // rejecting domain and its ancestors, not unrelated children.
                let mut ancestor = node.parent.as_deref();
                while let Some(parent) = ancestor {
                    let mut state = parent.state.lock();
                    state.max_events = state.max_events.saturating_add(1);
                    drop(state);
                    ancestor = parent.parent.as_deref();
                }
                return Err(Error::cgroup_frame_limit());
            }
            drop(state);
            cursor = node.parent.as_deref();
        }
        let mut cursor = Some(self);
        while let Some(node) = cursor {
            node.state.lock().pages += pages;
            cursor = node.parent.as_deref();
        }
        Ok(())
    }

    pub(super) fn refund(&self, pages: usize, _tx: &Transaction) {
        let mut cursor = Some(self);
        while let Some(node) = cursor {
            let mut state = node.state.lock();
            debug_assert!(state.pages >= pages);
            state.pages -= pages;
            drop(state);
            cursor = node.parent.as_deref();
        }
    }
}

#[cfg(ktest)]
pub(crate) fn test_leaf(max: usize) -> Arc<MemoryDomain> {
    let root = Arc::new(MemoryDomain {
        parent: None,
        depth: 0,
        state: SpinLock::new(State::default()),
    });
    root.set_delegated(true);
    let leaf = MemoryDomain::child(root).unwrap();
    assert!(leaf.set_max(Some(max)));
    leaf
}

#[cfg(ktest)]
mod tests;

/// Completes real XArray RCU destruction for physical-owner regressions.
#[cfg(ktest)]
pub(crate) fn test_wait_for_rcu_refunds() {
    tests::grace();
}
