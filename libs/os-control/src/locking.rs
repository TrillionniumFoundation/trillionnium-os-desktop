//! Public lock selection for a native delivery namespace.
//!
//! This interface permits an external kernel wrapper to supply its own locks
//! without copying state transitions or changing the host ResourceDomain.
//! A role describes where a lock is used; it does not select IRQ, preemption,
//! sleep, scheduler or allocation policy. Those policies, lock ordering and
//! their validation remain the integrating kernel's responsibility.

use core::ops::{Deref, DerefMut};

/// Logical lock sites used by the delivery namespace.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum LockRole {
    /// Short-held sequence, reservation and retirement state.
    NamespaceTable,
    /// Short-held pending/terminal result state.
    SlotState,
    /// Serializes an effect and its publication, including the owner callback.
    /// This guard may outlive short-held state guards.
    SlotExecution,
    /// Serializes namespace loss while waiting for admitted effects to finish.
    HistoryLoss,
}

/// An exclusive mutable lock supplied by a trusted integration.
///
/// Acquiring a guard must give exclusive access to the same stored value;
/// dropping it must release access and publish changes to later acquirers.
/// Acquisition must not run namespace callbacks. Guards intentionally have no
/// Send or Sync requirement: kernel IRQ/preemption guards are often thread-local.
/// Implementations must preserve these semantics during any supported unwind.
/// This safe trait does not certify a backend's liveness or kernel discipline.
pub trait ControlMutex: Send + Sync {
    type Value: Send;
    type Guard<'a>: Deref<Target = Self::Value> + DerefMut
    where
        Self: 'a;

    fn lock(&self) -> Self::Guard<'_>;
}

/// Static lock factory for one namespace and all of its delivery slots.
///
/// A backend may distinguish short state locks from potentially long execution
/// and history-loss gates by role. All four roles must provide exclusive lock
/// semantics. Construction takes place outside other namespace locks. Any
/// backend allocations, constructor failure policy, IRQ/preemption rules and
/// owner lock ordering remain the caller's integration obligations.
pub trait LockBackend: Send + Sync + 'static {
    type Mutex<T: Send>: ControlMutex<Value = T>;

    fn new<T: Send>(value: T, role: LockRole) -> Self::Mutex<T>;
}

/// Existing std host or experimental portable-spin backend, selected by Cargo
/// features. Neither default choice establishes real kernel IRQ safety.
pub struct DefaultLockBackend;

impl<T: Send> ControlMutex for crate::sync::Mutex<T> {
    type Value = T;
    type Guard<'a>
        = crate::sync::MutexGuard<'a, T>
    where
        Self: 'a;

    fn lock(&self) -> Self::Guard<'_> {
        crate::sync::lock_unpoisoned(self)
    }
}

impl LockBackend for DefaultLockBackend {
    type Mutex<T: Send> = crate::sync::Mutex<T>;

    fn new<T: Send>(value: T, _role: LockRole) -> Self::Mutex<T> {
        crate::sync::Mutex::new(value)
    }
}

pub(crate) fn lock<M: ControlMutex>(mutex: &M) -> M::Guard<'_> {
    mutex.lock()
}
