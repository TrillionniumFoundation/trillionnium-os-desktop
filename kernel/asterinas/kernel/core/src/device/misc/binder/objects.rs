// SPDX-License-Identifier: MPL-2.0
//! Object identities and owned reference contributions for the bounded profile.
//!
//! Lock order is DOMAIN -> Node.state. Reference Drop only takes Node.state,
//! never DOMAIN; queued payloads and failed receive copyouts therefore retain
//! the same contribution without recursive locking or duplicate increments.

use super::uapi::*;
use crate::prelude::*;

pub(super) const MAX_OBJECTS: usize = 32;
pub(super) const MAX_NODES: usize = 256;
pub(super) const MAX_LOCAL_NODES: usize = 16;
const MAX_HANDLES: usize = 128;
const MAX_USER_REFS: usize = 32;
const MAX_NODE_REFS: usize = 4096;

pub(super) struct Node {
    pub(super) id: u64,
    pub(super) owner: u64,
    pub(super) pointer: u64,
    pub(super) cookie: u64,
    state: Mutex<NodeState>,
}
#[derive(Default)]
struct NodeState {
    strong: usize,
    weak: usize,
    has_strong: bool,
    has_weak: bool,
    pending_strong: bool,
    pending_weak: bool,
}
impl NodeState {
    fn work(&self) -> Option<u32> {
        if self.strong + self.weak > 0 && !self.has_weak {
            Some(BR_INCREFS)
        } else if self.strong > 0 && !self.has_strong {
            Some(BR_ACQUIRE)
        } else if self.strong == 0 && self.has_strong && !self.pending_strong {
            Some(BR_RELEASE)
        } else if self.strong + self.weak == 0
            && self.has_weak
            && !self.has_strong
            && !self.pending_strong
            && !self.pending_weak
        {
            Some(BR_DECREFS)
        } else {
            None
        }
    }
}
impl Node {
    pub(super) fn new(id: u64, owner: u64, pointer: u64, cookie: u64) -> Self {
        Self {
            id,
            owner,
            pointer,
            cookie,
            state: Mutex::new(NodeState::default()),
        }
    }
    pub(super) fn preflight(&self, count: usize) -> Result<()> {
        let s = self.state.lock();
        if count > MAX_NODE_REFS - s.strong - s.weak {
            return_errno!(Errno::ENOSPC);
        }
        Ok(())
    }
    pub(super) fn has_work(&self) -> bool {
        self.state.lock().work().is_some()
    }
    pub(super) fn prepare_work(&self) -> Option<(u32, PtrCookie)> {
        let mut s = self.state.lock();
        let command = s.work()?;
        match command {
            BR_INCREFS => {
                s.has_weak = true;
                s.pending_weak = true;
            }
            BR_ACQUIRE => {
                s.has_strong = true;
                s.pending_strong = true;
            }
            BR_RELEASE => s.has_strong = false,
            BR_DECREFS => s.has_weak = false,
            _ => unreachable!(),
        }
        Some((
            command,
            PtrCookie {
                pointer: self.pointer,
                cookie: self.cookie,
            },
        ))
    }
    pub(super) fn acknowledge(&self, strong: bool, cookie: u64) -> Result<()> {
        let mut s = self.state.lock();
        if cookie != self.cookie
            || !(if strong {
                s.pending_strong
            } else {
                s.pending_weak
            })
        {
            return_errno!(Errno::EINVAL);
        }
        if strong {
            s.pending_strong = false;
        } else {
            s.pending_weak = false;
        }
        Ok(())
    }
    pub(super) fn idle(&self) -> bool {
        let s = self.state.lock();
        s.strong + s.weak == 0
            && !s.has_strong
            && !s.has_weak
            && !s.pending_strong
            && !s.pending_weak
    }
}

/// One real reference contribution. Arc cloning a payload or prepared event
/// shares this contribution; only a new transfer or explicit BC_* creates one.
pub(super) struct Reference {
    pub(super) node: Arc<Node>,
    pub(super) strong: bool,
}
impl Reference {
    // Caller preflights aggregate deltas under DOMAIN before any new reference.
    pub(super) fn new(node: Arc<Node>, strong: bool) -> Arc<Self> {
        {
            let mut s = node.state.lock();
            if strong {
                s.strong += 1;
            } else {
                s.weak += 1;
            }
        }
        Arc::new(Self { node, strong })
    }
}
impl Drop for Reference {
    fn drop(&mut self) {
        let mut s = self.node.state.lock();
        if self.strong {
            s.strong -= 1;
        } else {
            s.weak -= 1;
        }
    }
}

#[derive(Clone)]
pub(super) struct Object {
    pub(super) offset: usize,
    pub(super) reference: Arc<Reference>,
}
#[derive(Clone)]
pub(super) struct Payload {
    pub(super) bytes: Vec<u8>,
    pub(super) offsets: Vec<u64>,
    pub(super) objects: Vec<Object>,
    pub(super) target: Option<Arc<Reference>>,
}
impl Payload {
    pub(super) fn references(&self) -> Vec<Arc<Reference>> {
        self.objects
            .iter()
            .map(|o| o.reference.clone())
            .chain(self.target.iter().cloned())
            .collect()
    }
}

#[derive(Clone, Default)]
pub(super) struct Handles {
    next: u32,
    entries: BTreeMap<u32, Handle>,
}
#[derive(Clone)]
struct Handle {
    node: Arc<Node>,
    strong: Vec<Arc<Reference>>,
    weak: Vec<Arc<Reference>>,
}
impl Handles {
    pub(super) fn descriptor(&mut self, node: &Arc<Node>) -> Result<u32> {
        if let Some((&handle, _)) = self.entries.iter().find(|(_, h)| h.node.id == node.id) {
            return Ok(handle);
        }
        if self.entries.len() >= MAX_HANDLES {
            return_errno!(Errno::ENOSPC);
        }
        let handle = self
            .next
            .checked_add(1)
            .ok_or_else(|| Error::with_message(Errno::ENOSPC, "Binder handle space exhausted"))?;
        self.next = handle;
        self.entries.insert(
            handle,
            Handle {
                node: node.clone(),
                strong: Vec::new(),
                weak: Vec::new(),
            },
        );
        Ok(handle)
    }
    pub(super) fn resolve(
        &self,
        handle: u64,
        strong: bool,
        buffers: &[Option<Vec<Arc<Reference>>>],
    ) -> Result<Arc<Node>> {
        let descriptor = u32::try_from(handle)
            .map_err(|_| Error::with_message(Errno::EINVAL, "Invalid Binder handle width"))?;
        let entry = self
            .entries
            .get(&descriptor)
            .ok_or_else(|| Error::with_message(Errno::EINVAL, "Unknown Binder handle"))?;
        let buffered = buffers
            .iter()
            .flatten()
            .flatten()
            .any(|r| r.node.id == entry.node.id && (!strong || r.strong));
        if entry.strong.is_empty() && (strong || entry.weak.is_empty()) && !buffered {
            return_errno!(Errno::EINVAL);
        }
        Ok(entry.node.clone())
    }
    pub(super) fn change(&mut self, descriptor: u32, command: u32, node: Arc<Node>) -> Result<()> {
        let entry = self
            .entries
            .get_mut(&descriptor)
            .ok_or_else(|| Error::with_message(Errno::EINVAL, "Unknown Binder handle"))?;
        let strong = matches!(command, ACQUIRE | RELEASE);
        let refs = if strong {
            &mut entry.strong
        } else {
            &mut entry.weak
        };
        if matches!(command, ACQUIRE | INCREFS) {
            if refs.len() == MAX_USER_REFS {
                return_errno!(Errno::ENOSPC);
            }
            node.preflight(1)?;
            refs.push(Reference::new(node, strong));
        } else if refs.pop().is_none() {
            return_errno!(Errno::EINVAL);
        }
        Ok(())
    }
    pub(super) fn prune(&mut self, buffers: &[Option<Vec<Arc<Reference>>>]) {
        self.entries.retain(|_, h| {
            !h.strong.is_empty()
                || !h.weak.is_empty()
                || buffers
                    .iter()
                    .flatten()
                    .flatten()
                    .any(|r| r.node.id == h.node.id)
        });
    }
}

#[cfg(ktest)]
mod tests {
    use ostd::prelude::*;

    use super::*;
    #[ktest]
    fn actual_reference_drop_and_acknowledgement() {
        let node = Arc::new(Node::new(1, 9, 0x1234, 0x5678));
        let reference = Reference::new(node.clone(), true);
        let shared = reference.clone();
        assert_eq!(node.prepare_work().unwrap().0, BR_INCREFS);
        assert_eq!(node.prepare_work().unwrap().0, BR_ACQUIRE);
        assert!(!node.has_work());
        assert!(node.acknowledge(true, 0x9999).is_err());
        node.acknowledge(true, 0x5678).unwrap();
        assert!(node.acknowledge(true, 0x5678).is_err());
        drop(reference);
        assert!(!node.has_work());
        drop(shared);
        assert_eq!(node.prepare_work().unwrap().0, BR_RELEASE);
        assert!(!node.has_work());
        node.acknowledge(false, 0x5678).unwrap();
        assert_eq!(node.prepare_work().unwrap().0, BR_DECREFS);
        assert!(node.idle());
    }
    #[ktest]
    fn buffer_reference_retention_and_nonreuse() {
        let node = Arc::new(Node::new(2, 9, 0x1234, 0x5678));
        let mut handles = Handles::default();
        let first = handles.descriptor(&node).unwrap();
        let mut buffers = vec![Some(vec![Reference::new(node.clone(), true)])];
        assert!(handles.resolve(first as u64, true, &buffers).is_ok());
        assert!(handles.change(first, RELEASE, node.clone()).is_err());
        handles.change(first, ACQUIRE, node.clone()).unwrap();
        buffers[0] = None;
        handles.prune(&buffers);
        assert!(handles.resolve(first as u64, true, &buffers).is_ok());
        handles.change(first, RELEASE, node.clone()).unwrap();
        handles.prune(&buffers);
        assert!(handles.resolve(first as u64, false, &buffers).is_err());
        assert!(handles.descriptor(&node).unwrap() > first);
    }
}
