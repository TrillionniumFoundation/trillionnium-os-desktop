//! Test-only lock-depth and allocator instrumentation. The production crate
//! imports its mutex API from this separate harness crate through sync.rs.

use std::alloc::{GlobalAlloc, Layout, System};
use std::cell::Cell;
use std::ops::{Deref, DerefMut};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Mutex as StdMutex, MutexGuard as StdMutexGuard};

pub use std::sync::{Arc, Weak};

thread_local! {
    // Constant TLS initialization has no lazy heap allocation or destructor.
    static DEPTH: Cell<usize> = const { Cell::new(0) };
    static FAIL_NEXT: Cell<bool> = const { Cell::new(false) };
}

static INJECTED_FAILURES: AtomicU64 = AtomicU64::new(0);

/// Only the fixture arms this immediately before a known fallible Vec reserve.
/// Never arm around Arc::new or another infallible allocation.
pub fn fail_next_allocation() {
    FAIL_NEXT.with(|armed| assert!(!armed.replace(true), "allocation failure already armed"));
}

pub fn injected_failures() -> u64 {
    INJECTED_FAILURES.load(Ordering::Relaxed)
}

fn consume_failure() -> bool {
    if FAIL_NEXT
        .try_with(|armed| armed.replace(false))
        .unwrap_or(false)
    {
        INJECTED_FAILURES.fetch_add(1, Ordering::Relaxed);
        true
    } else {
        false
    }
}

pub fn lock_depth() -> usize {
    DEPTH.try_with(Cell::get).unwrap_or(0)
}

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct Counts {
    pub alloc: u64,
    pub realloc: u64,
    pub dealloc: u64,
    pub allocated_bytes: u64,
    pub reallocated_bytes: u64,
    pub deallocated_bytes: u64,
}

impl Counts {
    pub fn since(self, before: Self) -> Self {
        Self {
            alloc: self.alloc - before.alloc,
            realloc: self.realloc - before.realloc,
            dealloc: self.dealloc - before.dealloc,
            allocated_bytes: self.allocated_bytes - before.allocated_bytes,
            reallocated_bytes: self.reallocated_bytes - before.reallocated_bytes,
            deallocated_bytes: self.deallocated_bytes - before.deallocated_bytes,
        }
    }

    pub fn is_zero(self) -> bool {
        self.alloc == 0 && self.realloc == 0 && self.dealloc == 0
    }
}

static ALLOC: AtomicU64 = AtomicU64::new(0);
static REALLOC: AtomicU64 = AtomicU64::new(0);
static DEALLOC: AtomicU64 = AtomicU64::new(0);
static ALLOCATED_BYTES: AtomicU64 = AtomicU64::new(0);
static REALLOCATED_BYTES: AtomicU64 = AtomicU64::new(0);
static DEALLOCATED_BYTES: AtomicU64 = AtomicU64::new(0);

pub fn counts() -> Counts {
    Counts {
        alloc: ALLOC.load(Ordering::Relaxed),
        realloc: REALLOC.load(Ordering::Relaxed),
        dealloc: DEALLOC.load(Ordering::Relaxed),
        allocated_bytes: ALLOCATED_BYTES.load(Ordering::Relaxed),
        reallocated_bytes: REALLOCATED_BYTES.load(Ordering::Relaxed),
        deallocated_bytes: DEALLOCATED_BYTES.load(Ordering::Relaxed),
    }
}

pub struct TrackingAllocator;

// Unsafe belongs only to this test harness, never the copied production crate.
// Hooks call no formatter, heap collection or panic. They record before
// delegating to the exact corresponding System allocator operation.
unsafe impl GlobalAlloc for TrackingAllocator {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        if lock_depth() > 0 {
            ALLOC.fetch_add(1, Ordering::Relaxed);
            ALLOCATED_BYTES.fetch_add(layout.size() as u64, Ordering::Relaxed);
        }
        if consume_failure() {
            return std::ptr::null_mut();
        }
        unsafe { System.alloc(layout) }
    }

    unsafe fn alloc_zeroed(&self, layout: Layout) -> *mut u8 {
        if lock_depth() > 0 {
            ALLOC.fetch_add(1, Ordering::Relaxed);
            ALLOCATED_BYTES.fetch_add(layout.size() as u64, Ordering::Relaxed);
        }
        if consume_failure() {
            return std::ptr::null_mut();
        }
        unsafe { System.alloc_zeroed(layout) }
    }

    unsafe fn realloc(&self, pointer: *mut u8, layout: Layout, new_size: usize) -> *mut u8 {
        if lock_depth() > 0 {
            REALLOC.fetch_add(1, Ordering::Relaxed);
            REALLOCATED_BYTES.fetch_add(new_size as u64, Ordering::Relaxed);
        }
        if consume_failure() {
            return std::ptr::null_mut();
        }
        unsafe { System.realloc(pointer, layout, new_size) }
    }

    unsafe fn dealloc(&self, pointer: *mut u8, layout: Layout) {
        if lock_depth() > 0 {
            DEALLOC.fetch_add(1, Ordering::Relaxed);
            DEALLOCATED_BYTES.fetch_add(layout.size() as u64, Ordering::Relaxed);
        }
        unsafe { System.dealloc(pointer, layout) }
    }
}

#[derive(Debug)]
pub struct Mutex<T> {
    inner: StdMutex<T>,
}

impl<T> Mutex<T> {
    pub const fn new(value: T) -> Self {
        Self {
            inner: StdMutex::new(value),
        }
    }

    pub fn is_poisoned(&self) -> bool {
        self.inner.is_poisoned()
    }
}

pub struct MutexGuard<'a, T> {
    inner: Option<StdMutexGuard<'a, T>>,
}

impl<T> Deref for MutexGuard<'_, T> {
    type Target = T;
    fn deref(&self) -> &Self::Target {
        self.inner.as_ref().expect("live instrumentation guard")
    }
}

impl<T> DerefMut for MutexGuard<'_, T> {
    fn deref_mut(&mut self) -> &mut Self::Target {
        self.inner.as_mut().expect("live instrumentation guard")
    }
}

impl<T> Drop for MutexGuard<'_, T> {
    fn drop(&mut self) {
        // Keep depth nonzero until the real mutex has actually unlocked.
        drop(self.inner.take());
        let _ = DEPTH.try_with(|depth| depth.set(depth.get().saturating_sub(1)));
    }
}

pub fn lock_unpoisoned<T>(mutex: &Mutex<T>) -> MutexGuard<'_, T> {
    let inner = mutex
        .inner
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner());
    DEPTH.with(|depth| depth.set(depth.get().saturating_add(1)));
    MutexGuard { inner: Some(inner) }
}
