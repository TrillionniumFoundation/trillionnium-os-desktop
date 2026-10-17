//! Test-only adapter: production transitions unchanged; reference counts not instrumented.
pub(crate) use loom::sync::{Mutex, MutexGuard};
pub(crate) use std::sync::{Arc, Weak};
pub(crate) fn lock_unpoisoned<T>(mutex: &Mutex<T>) -> MutexGuard<'_, T> {
    mutex.lock().unwrap_or_else(|error| error.into_inner())
}
