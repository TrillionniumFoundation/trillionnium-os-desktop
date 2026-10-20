// SPDX-License-Identifier: MPL-2.0

//! One process-context lock factory for the original native delivery core.

use os_control::{ControlMutex, LockBackend, LockRole};
use ostd::sync::{Mutex, MutexGuard};

/// All four roles use the existing sleeping OSTD mutex. Table/slot guards
/// remain short; execution/history gates may wait. Callers never acquire a
/// namespace lock under the CPU IRQ-disabling lock or an image/TaskSet guard.
pub(crate) struct KernelControlBackend;
pub(crate) struct KernelControlMutex<T: Send>(Mutex<T>);

impl<T: Send> ControlMutex for KernelControlMutex<T> {
    type Value = T;
    type Guard<'a> = MutexGuard<'a, T> where Self: 'a;

    fn lock(&self) -> Self::Guard<'_> { self.0.lock() }
}

impl LockBackend for KernelControlBackend {
    type Mutex<T: Send> = KernelControlMutex<T>;

    fn new<T: Send>(value: T, _role: LockRole) -> Self::Mutex<T> {
        KernelControlMutex(Mutex::new(value))
    }
}
