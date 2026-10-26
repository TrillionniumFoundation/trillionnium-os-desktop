// SPDX-License-Identifier: MPL-2.0
//! Actual open-file snapshots and transactional target descriptor installation.
//!
//! DOMAIN never takes a file-table lock or destroys the last FileLike. All
//! queued/prepared files use RetainedFile, whose destructor only enqueues a
//! deferred retirement. The outer operation drains after dropping DOMAIN.
//! Reservations remain hidden and retain their exact descriptor numbers across
//! a failed receive copyout. Installation runs outside DOMAIN after read commit.

use core::sync::atomic::{AtomicBool, Ordering};

use ostd::{sync::WaitQueue, task::Task};
use spin::Once;

use super::uapi::*;
use crate::{
    fs::file::{
        FileLike,
        file_table::{FdFlags, FileDescReservation, FileTable, get_file_fast},
    },
    prelude::*,
    thread::kernel_thread::ThreadOptions,
};

const MAX_RETAINED_FILES: usize = 256;
static RETAINED: Mutex<usize> = Mutex::new(0);
static RETIRED: Once<Mutex<Retirements>> = Once::new();
static CLEANUP: Once<WaitQueue> = Once::new();
static READY: AtomicBool = AtomicBool::new(false);
struct Retirements {
    draining: bool,
    items: Vec<Retirement>,
    spare: Vec<Retirement>,
}

enum Retirement {
    Cleanup(Arc<Task>),
    Reservations(Vec<FileDescReservation>),
}
fn retire(value: Retirement) {
    // At most 256 retained file snapshots and 256 nonempty prepared batches
    // exist, including batches whose endpoint closed during copyout. Permits
    // are returned only after destruction outside the retirement queue lock.
    {
        let mut retired = RETIRED.get().unwrap().lock();
        debug_assert!(retired.items.len() < MAX_RETAINED_FILES * 2);
        retired.items.push(value);
    }
    CLEANUP.get().unwrap().wake_all();
}
pub(super) fn init() {
    RETIRED.call_once(|| {
        Mutex::new(Retirements {
            draining: false,
            items: Vec::with_capacity(MAX_RETAINED_FILES * 2),
            spare: Vec::with_capacity(MAX_RETAINED_FILES * 2),
        })
    });
    CLEANUP.call_once(WaitQueue::new);
    // VMAR teardown may retire an endpoint while holding its VM lock. The
    // cleanup worker guarantees destruction without another user operation
    // or taking a file-table lock in the VMAR path.
    let worker = ThreadOptions::new(|| {
        loop {
            CLEANUP.get().unwrap().wait_until(|| {
                let retired = RETIRED.get().unwrap().lock();
                (!retired.draining && !retired.items.is_empty()).then_some(())
            });
            drop(Drain);
        }
    })
    .try_build(crate::fs::cgroupfs::charge_current_kernel_stack);
    if let Ok(worker) = worker {
        READY.store(true, Ordering::Release);
        worker.run();
    }
    // If initial stack allocation failed, byte/object IPC still works. FD
    // snapshots return ENOMEM rather than creating an undrainable transfer.
}

pub(super) struct Drain;
impl Drop for Drain {
    fn drop(&mut self) {
        let mut retired = RETIRED.get().unwrap().lock();
        if retired.draining {
            return;
        }
        retired.draining = true;
        let mut batch = core::mem::take(&mut retired.spare);
        loop {
            if retired.items.is_empty() {
                retired.spare = batch;
                retired.draining = false;
                return;
            }
            core::mem::swap(&mut batch, &mut retired.items);
            drop(retired);
            // Nested BinderFile destructors enqueue for this drain instead of
            // recursively draining; the queue's draining flag closes that race.
            for item in batch.drain(..) {
                match item {
                    Retirement::Cleanup(task) => task.run(),
                    Retirement::Reservations(reservations) => drop(reservations),
                }
            }
            retired = RETIRED.get().unwrap().lock();
        }
    }
}

struct FilePermit;
impl FilePermit {
    fn acquire() -> Result<Self> {
        let mut retained = RETAINED.lock();
        if *retained == MAX_RETAINED_FILES {
            return_errno!(Errno::ENOSPC);
        }
        *retained += 1;
        Ok(Self)
    }
}
impl Drop for FilePermit {
    fn drop(&mut self) {
        *RETAINED.lock() -= 1;
    }
}
struct CleanupJob {
    file: Mutex<Option<Arc<dyn FileLike>>>,
}
/// A prebuilt cleanup task owns the source file and permit. Last reference
/// retirement only queues that task; it never allocates a stack or blocks on
/// arbitrary FileLike destruction under DOMAIN or a shared cleanup drain.
pub(super) struct RetainedFile {
    job: Arc<CleanupJob>,
    cleanup: Option<Arc<Task>>,
}
impl RetainedFile {
    pub(super) fn snapshot(descriptor: u64) -> Result<Arc<Self>> {
        if !READY.load(Ordering::Acquire) {
            return_errno!(Errno::ENOMEM);
        }
        if descriptor > i32::MAX as u64 {
            return_errno!(Errno::EBADF);
        }
        // Acquire the global permit and finish every fallible stack allocation
        // before retaining the FileLike or publishing a transaction. The stack
        // uses the original source account's existing per-frame charge path.
        let permit = FilePermit::acquire()?;
        let job = Arc::new(CleanupJob {
            file: Mutex::new(None),
        });
        let job_for_task = job.clone();
        let cleanup = ThreadOptions::new(move || {
            let file = job_for_task.file.lock().take();
            drop(file); // SO_LINGER or another slow close affects only this task.
            drop(permit);
        })
        .try_build(crate::fs::cgroupfs::charge_current_kernel_stack)?;
        let task = Task::current().unwrap();
        let mut table = task.as_thread_local().unwrap().borrow_file_table_mut();
        let file = get_file_fast!(&mut table, (descriptor as i32).try_into()?).into_owned();
        *job.file.lock() = Some(file);
        Ok(Arc::new(Self {
            job,
            cleanup: Some(cleanup),
        }))
    }
    fn file(&self) -> Arc<dyn FileLike> {
        self.job.file.lock().as_ref().unwrap().clone()
    }
}
impl Drop for RetainedFile {
    fn drop(&mut self) {
        retire(Retirement::Cleanup(self.cleanup.take().unwrap()));
    }
}

#[derive(Clone)]
pub(super) struct FileObject {
    pub(super) offset: usize,
    pub(super) file: Arc<RetainedFile>,
}

pub(super) struct PendingFds {
    files: Vec<FileObject>,
    descriptors: Vec<u32>,
    reservations: Mutex<Option<Vec<FileDescReservation>>>,
}
impl PendingFds {
    // Must run outside DOMAIN. Any partial reservation failure rolls back all
    // hidden slots before returning; no target file has been installed.
    pub(super) fn reserve(files: Vec<FileObject>) -> Result<Arc<Self>> {
        if files.is_empty() {
            return_errno!(Errno::EINVAL);
        }
        let mut reservations = Vec::new();
        let mut descriptors = Vec::new();
        for _ in &files {
            let reservation = FileTable::reserve_current_fd(FdFlags::CLOEXEC)?;
            descriptors.push(reservation.fd().into());
            reservations.push(reservation);
        }
        Ok(Arc::new(Self {
            files,
            descriptors,
            reservations: Mutex::new(Some(reservations)),
        }))
    }
    pub(super) fn encode(&self, bytes: &mut [u8]) {
        for (file, &descriptor) in self.files.iter().zip(&self.descriptors) {
            let object = FlatObject {
                kind: TYPE_FD,
                flags: 0,
                value: descriptor as u64,
                cookie: 0,
            };
            bytes[file.offset..file.offset + size_of::<FlatObject>()]
                .copy_from_slice(object.as_bytes());
        }
    }
    pub(super) fn install(&self) {
        let reservations = self.reservations.lock().take().unwrap();
        for (reservation, file) in reservations.into_iter().zip(&self.files) {
            reservation.install(file.file.file());
        }
    }
}
impl Drop for PendingFds {
    fn drop(&mut self) {
        if let Some(reservations) = self.reservations.get_mut().take() {
            retire(Retirement::Reservations(reservations));
        }
    }
}

#[cfg(ktest)]
mod tests {
    use ostd::prelude::*;

    use super::*;

    fn refuse_stack(_: usize) -> ostd::Result<Box<dyn ostd::task::StackReservation>> {
        Err(ostd::Error::NoMemory)
    }

    #[ktest]
    fn cleanup_stack_failure_returns_unpublished_file_permit() {
        let before = *RETAINED.lock();
        let permit = FilePermit::acquire().unwrap();
        assert_eq!(*RETAINED.lock(), before + 1);
        let invoked = Arc::new(AtomicBool::new(false));
        let from_task = invoked.clone();
        let result = ThreadOptions::new(move || {
            from_task.store(true, Ordering::Release);
            drop(permit);
        })
        .try_build(refuse_stack);
        assert!(matches!(result, Err(error) if error.error() == Errno::ENOMEM));
        assert!(!invoked.load(Ordering::Acquire));
        assert_eq!(*RETAINED.lock(), before);
    }
}
