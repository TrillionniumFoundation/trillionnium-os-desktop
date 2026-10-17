//! Synchronization selection for the host model and portable build experiments.
//!
//! The `portable-spin` backend only makes the same state core buildable without
//! `std`. It has not been validated as an Asterinas lock adapter and must not be
//! called directly from IRQ context: same-CPU reentry can deadlock. A real
//! kernel integration must supply and verify its interrupt, preemption and
//! scheduler lock discipline before using these state transitions.

#[cfg(feature = "std")]
pub(crate) use std::sync::{Arc, Mutex, MutexGuard};

#[cfg(all(not(feature = "std"), feature = "portable-spin"))]
pub(crate) use alloc::sync::Arc;
#[cfg(all(not(feature = "std"), feature = "portable-spin"))]
pub(crate) use spin::{Mutex, MutexGuard};

#[cfg(feature = "std")]
pub(crate) fn lock_unpoisoned<T>(mutex: &Mutex<T>) -> MutexGuard<'_, T> {
    mutex.lock().unwrap_or_else(|error| error.into_inner())
}

#[cfg(all(not(feature = "std"), feature = "portable-spin"))]
pub(crate) fn lock_unpoisoned<T>(mutex: &Mutex<T>) -> MutexGuard<'_, T> {
    mutex.lock()
}
