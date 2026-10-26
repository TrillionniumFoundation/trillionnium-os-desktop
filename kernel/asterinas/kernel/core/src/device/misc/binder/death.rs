// SPDX-License-Identifier: MPL-2.0
//! Bounded death subscriptions attached to actual handle/node identities.
//!
//! A subscription is not a strong or weak object reference. Last handle
//! reference removal cancels attached work. CLEAR detaches first; its owed
//! death/ack/clear handshake survives subsequent handle removal.

use super::{objects::Node, uapi::*};
use crate::prelude::*;

const MAX_RECORDS: usize = 32;

#[derive(Clone, Copy, PartialEq, Eq)]
enum State {
    Live,
    DeadQueued,
    DeadDelivered,
    Acknowledged,
    ClearQueued,
}
struct Record {
    handle: u32,
    node: Arc<Node>,
    cookie: u64,
    attached: bool,
    clear_pending: bool,
    state: State,
}
#[derive(Default)]
pub(super) struct Subscriptions {
    next: u64,
    records: BTreeMap<u64, Record>,
}
#[derive(Clone, Copy)]
pub(super) struct Delivery {
    id: u64,
    clear: bool,
    pub(super) cookie: u64,
}
impl Delivery {
    pub(super) fn command(&self) -> u32 {
        if self.clear {
            BR_CLEAR_DEATH_NOTIFICATION_DONE
        } else {
            BR_DEAD_BINDER
        }
    }
}
impl Subscriptions {
    pub(super) fn request(
        &mut self,
        handle: u32,
        node: Arc<Node>,
        cookie: u64,
        alive: bool,
    ) -> Result<()> {
        // DONE carries cookie alone. Reject ambiguous cookie reuse even after
        // CLEAR detached a record whose handshake is still outstanding.
        if self
            .records
            .values()
            .any(|r| r.cookie == cookie || (r.attached && r.handle == handle))
        {
            return_errno!(Errno::EINVAL);
        }
        if self.records.len() == MAX_RECORDS {
            return_errno!(Errno::ENOSPC);
        }
        let id = self
            .next
            .checked_add(1)
            .ok_or_else(|| Error::with_message(Errno::ENOSPC, "Binder death identity exhausted"))?;
        self.next = id;
        self.records.insert(
            id,
            Record {
                handle,
                node,
                cookie,
                attached: true,
                clear_pending: false,
                state: if alive {
                    State::Live
                } else {
                    State::DeadQueued
                },
            },
        );
        Ok(())
    }
    pub(super) fn clear(&mut self, handle: u32, cookie: u64) -> Result<()> {
        let record = self
            .records
            .values_mut()
            .find(|r| r.attached && r.handle == handle && r.cookie == cookie)
            .ok_or_else(|| {
                Error::with_message(Errno::EINVAL, "Unknown Binder death subscription")
            })?;
        record.attached = false;
        match record.state {
            State::Live | State::Acknowledged => record.state = State::ClearQueued,
            State::DeadQueued | State::DeadDelivered => record.clear_pending = true,
            State::ClearQueued => unreachable!(),
        }
        Ok(())
    }
    pub(super) fn done(&mut self, cookie: u64) -> Result<()> {
        let record = self
            .records
            .values_mut()
            .find(|r| r.cookie == cookie && r.state == State::DeadDelivered)
            .ok_or_else(|| {
                Error::with_message(
                    Errno::EINVAL,
                    "Binder death was not delivered or already acknowledged",
                )
            })?;
        record.state = if record.clear_pending {
            State::ClearQueued
        } else {
            State::Acknowledged
        };
        Ok(())
    }
    pub(super) fn owner_closed(&mut self, owner: u64) {
        for record in self.records.values_mut() {
            if record.attached && record.node.owner == owner && record.state == State::Live {
                record.state = State::DeadQueued;
            }
        }
    }
    pub(super) fn cancel_handles(&mut self, removed: &[u32]) {
        self.records
            .retain(|_, r| !r.attached || !removed.contains(&r.handle));
    }
    pub(super) fn has_work(&self) -> bool {
        self.records
            .values()
            .any(|r| matches!(r.state, State::DeadQueued | State::ClearQueued))
    }
    pub(super) fn prepare(&self) -> Option<Delivery> {
        self.records.iter().find_map(|(&id, r)| match r.state {
            State::DeadQueued => Some(Delivery {
                id,
                clear: false,
                cookie: r.cookie,
            }),
            State::ClearQueued => Some(Delivery {
                id,
                clear: true,
                cookie: r.cookie,
            }),
            _ => None,
        })
    }
    pub(super) fn commit(&mut self, delivery: Delivery) -> Result<()> {
        let record = self.records.get_mut(&delivery.id).ok_or_else(|| {
            Error::with_message(Errno::EINVAL, "Binder death delivery was cancelled")
        })?;
        if record.cookie != delivery.cookie
            || record.state
                != if delivery.clear {
                    State::ClearQueued
                } else {
                    State::DeadQueued
                }
        {
            return_errno!(Errno::EINVAL);
        }
        if delivery.clear {
            self.records.remove(&delivery.id);
        } else {
            record.state = State::DeadDelivered;
        }
        Ok(())
    }
}

#[cfg(ktest)]
mod tests {
    use ostd::prelude::*;

    use super::*;
    fn node() -> Arc<Node> {
        Arc::new(Node::new(8, 5, 0x1000, 0x2000, 0))
    }
    #[ktest]
    fn death_clear_waits_for_actual_delivery_and_ack() {
        let mut subs = Subscriptions::default();
        subs.request(1, node(), 77, false).unwrap();
        subs.clear(1, 77).unwrap();
        let prepared = subs.prepare().unwrap();
        assert_eq!(prepared.command(), BR_DEAD_BINDER);
        assert!(subs.done(77).is_err());
        assert_eq!(subs.prepare().unwrap().cookie, 77);
        subs.commit(prepared).unwrap();
        assert!(!subs.has_work());
        assert!(subs.done(78).is_err());
        subs.done(77).unwrap();
        assert!(subs.done(77).is_err());
        let clear = subs.prepare().unwrap();
        assert_eq!(clear.command(), BR_CLEAR_DEATH_NOTIFICATION_DONE);
        subs.commit(clear).unwrap();
        assert!(subs.records.is_empty());
    }
    #[ktest]
    fn last_handle_cancels_attached_but_not_detached_work() {
        let mut subs = Subscriptions::default();
        subs.request(1, node(), 1, false).unwrap();
        subs.commit(subs.prepare().unwrap()).unwrap();
        subs.cancel_handles(&[1]);
        assert!(subs.done(1).is_err());
        subs.request(2, node(), 2, false).unwrap();
        subs.clear(2, 2).unwrap();
        subs.cancel_handles(&[2]);
        assert_eq!(subs.records.len(), 1);
        subs.commit(subs.prepare().unwrap()).unwrap();
        subs.done(2).unwrap();
        subs.commit(subs.prepare().unwrap()).unwrap();
        assert!(subs.records.is_empty());
    }
    #[ktest]
    fn live_clear_and_record_capacity_are_real_state() {
        let mut subs = Subscriptions::default();
        for i in 0..32 {
            subs.request(1, node(), i, true).unwrap();
            subs.clear(1, i).unwrap();
        }
        assert!(subs.request(1, node(), 32, true).is_err());
        subs.owner_closed(5); // Every record was detached before death.
        for _ in 0..32 {
            let next = subs.prepare().unwrap();
            assert_eq!(next.command(), BR_CLEAR_DEATH_NOTIFICATION_DONE);
            subs.commit(next).unwrap();
        }
        subs.request(1, node(), 32, false).unwrap();
        assert_eq!(subs.prepare().unwrap().command(), BR_DEAD_BINDER);
    }
}
