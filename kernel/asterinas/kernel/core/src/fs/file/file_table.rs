// SPDX-License-Identifier: MPL-2.0

use core::{
    fmt::Display,
    sync::atomic::{AtomicU8, Ordering},
};

use aster_util::{ranged_integer::RangedU32, slot_vec::SlotVec};
use ostd::{sync::RwArc, task::Task};

use super::file_handle::FileLike;
use crate::{
    fs::vfs::range_lock::RangeLockOwner,
    prelude::*,
    process::{
        posix_thread::FileTableRefMut,
        rlimit::{ResourceLimits, ResourceType, SYSCTL_NR_OPEN},
    },
};

/// Represents a validated, non-negative file descriptor.
///
/// The value is guaranteed to be in the range `[0, i32::MAX]`.
/// Use [`RawFileDesc`] at syscall boundaries,
/// then convert to `FileDesc` via `TryFrom` for kernel-internal use.
///
/// Some system calls (e.g., `fcntl`) reinterpret
/// values of types other than [`RawFileDesc`] (e.g., `u64` or `usize`)
/// as file descriptors. Linux typically truncates the high bits
/// without checking whether the full argument fits in range.
/// To avoid accidental misuse, we do not implement `TryFrom` for
/// those types. The syscall layer should first convert them to
/// a [`RawFileDesc`] in an explicit, syscall-specific way,
/// and then convert that value to a `FileDesc`.
#[derive(Clone, Copy, Debug, Eq, Ord, PartialEq, PartialOrd)]
pub(crate) struct FileDesc(RangedU32<0, { i32::MAX as _ }>);

/// A raw file descriptor as received from or returned to user space.
///
/// This is the `int` type from Linux syscall signatures.
/// It may hold negative sentinel values like `AT_FDCWD` (-100).
/// Convert to [`FileDesc`] via `TryFrom` before use.
pub(crate) type RawFileDesc = i32;

impl FileDesc {
    /// File descriptor 0.
    pub(crate) const ZERO: Self = Self(RangedU32::new(0));
}

impl Display for FileDesc {
    fn fmt(&self, f: &mut core::fmt::Formatter<'_>) -> core::fmt::Result {
        write!(f, "{}", self.0.get())
    }
}

impl From<FileDesc> for RawFileDesc {
    fn from(value: FileDesc) -> Self {
        value.0.get() as _
    }
}

impl From<FileDesc> for isize {
    fn from(value: FileDesc) -> Self {
        value.0.get() as _
    }
}

impl From<FileDesc> for u32 {
    fn from(value: FileDesc) -> Self {
        value.0.get()
    }
}

impl From<FileDesc> for u64 {
    fn from(value: FileDesc) -> Self {
        value.0.get() as _
    }
}

impl From<FileDesc> for usize {
    fn from(value: FileDesc) -> Self {
        value.0.get() as _
    }
}

// Intentionally, `TryFrom<RawFileDesc>` is
// the only `TryFrom` implementation for `FileDesc`.
//
// We do not implement conversions from wider integer types
// for Linux compatibility reasons; see the `FileDesc` type docs.
// We also do not implement `TryFrom<u32>` directly,
// to encourage callers to name `RawFileDesc` explicitly
// instead of using a plain `u32`.
impl TryFrom<RawFileDesc> for FileDesc {
    type Error = Error;

    fn try_from(value: RawFileDesc) -> Result<Self> {
        if value < 0 {
            return_errno_with_message!(Errno::EBADF, "negative FDs are not valid");
        }
        Ok(Self(RangedU32::new(value.cast_unsigned())))
    }
}

/// A file table.
///
/// A file table is created within an [`RwArc`] and remains within it (see [`Self::new`] and
/// [`Self::fork_from`]). The file table's address is used as a [`RangeLockOwner`], so users should
/// not try to move the file table to a different address.
pub(crate) struct FileTable {
    table: SlotVec<FileTableSlot>,
}

enum FileTableSlot {
    Reserved(FdFlags),
    File(FileTableEntry),
}

impl FileTableSlot {
    fn entry(&self) -> Option<&FileTableEntry> {
        match self {
            Self::File(entry) => Some(entry),
            Self::Reserved(_) => None,
        }
    }
}

impl FileTable {
    /// Creates a new file table.
    pub(crate) fn new() -> RwArc<Self> {
        RwArc::new(Self {
            table: SlotVec::new(),
        })
    }

    /// Creates a new file table containing clones of the installed entries in `parent`.
    ///
    /// An in-progress allocation belongs to its original table and must not be inherited.
    pub(crate) fn fork_from(parent: &Self) -> RwArc<Self> {
        let mut table = SlotVec::new();
        for (idx, slot) in parent.table.idxes_and_items() {
            if let Some(entry) = slot.entry() {
                table.put_at(idx, FileTableSlot::File(entry.clone()));
            }
        }
        RwArc::new(Self { table })
    }

    /// Returns the range-lock owner of `file_table`.
    pub(crate) fn range_lock_owner(file_table: &RwArc<Self>) -> RangeLockOwner {
        RangeLockOwner::from_address(file_table.as_ptr().addr())
    }

    fn as_range_lock_owner(&self) -> RangeLockOwner {
        RangeLockOwner::from_address(self as *const Self as usize)
    }

    pub(crate) fn len(&self) -> usize {
        self.table.slots_len()
    }

    /// Reserves the lowest available FD below this caller's current soft limit.
    ///
    /// Reserve before work that may block or have side effects, then install only after
    /// fallible setup and user copyout succeed. Dropping the reservation releases the slot.
    pub(crate) fn reserve_fd(ctx: &Context, flags: FdFlags) -> Result<FileDescReservation> {
        let file_table = ctx.thread_local.borrow_file_table().unwrap().clone();
        Self::reserve_in(file_table, ctx.process.resource_limits(), flags)
    }

    /// Reserves an FD for a file operation that has no explicit syscall context.
    pub(crate) fn reserve_current_fd(flags: FdFlags) -> Result<FileDescReservation> {
        let current_task = Task::current().unwrap();
        let file_table = current_task
            .as_thread_local()
            .unwrap()
            .borrow_file_table()
            .unwrap()
            .clone();
        Self::reserve_in(file_table, current!().resource_limits(), flags)
    }

    fn reserve_in(
        file_table: RwArc<Self>,
        limits: &ResourceLimits,
        flags: FdFlags,
    ) -> Result<FileDescReservation> {
        let fd = {
            let mut locked = file_table.write();
            let fd = locked.first_free_fd(0, Self::nofile_limit(limits))?;
            locked.table.put_at(fd, FileTableSlot::Reserved(flags));
            (fd as RawFileDesc).try_into().unwrap()
        };
        Ok(FileDescReservation {
            file_table,
            fd: Some(fd),
        })
    }

    fn nofile_limit(limits: &ResourceLimits) -> usize {
        // A table can be shared by processes with different limits (CLONE_FILES), so the
        // limit belongs to the allocating caller, not to the table. It is a bound on the
        // descriptor number, not the number of installed entries after a limit reduction.
        limits
            .get_rlimit(ResourceType::RLIMIT_NOFILE)
            .get_cur()
            .min(SYSCTL_NR_OPEN) as usize
    }

    fn first_free_fd(&self, start: usize, limit: usize) -> Result<usize> {
        // Preserve SlotVec's constant-time append path for the usual dense file table.
        if self.table.len() != self.len() {
            for fd in start..self.len().min(limit) {
                if self.table.get(fd).is_none() {
                    return Ok(fd);
                }
            }
        }
        let fd = start.max(self.len());
        if fd < limit {
            return Ok(fd);
        }
        return_errno_with_message!(Errno::EMFILE, "the file descriptor limit is exhausted")
    }

    /// Duplicates `fd` onto the lowest-numbered available descriptor equal to
    /// or greater than `ceil_fd`. `None` implements `dup`; `Some` implements the
    /// additional lower-bound validation required by `F_DUPFD` and `F_DUPFD_CLOEXEC`.
    pub(crate) fn dup_ceil(
        &mut self,
        fd: FileDesc,
        ceil_fd: Option<FileDesc>,
        flags: FdFlags,
        limits: &ResourceLimits,
    ) -> Result<FileDesc> {
        let entry = self.duplicate_entry(fd, flags)?;
        let limit = Self::nofile_limit(limits);
        if ceil_fd.is_some_and(|fd| usize::from(fd) >= limit) {
            return_errno_with_message!(Errno::EINVAL, "the FD lower bound exceeds the limit");
        }
        let min_free_fd = self.first_free_fd(ceil_fd.unwrap_or(FileDesc::ZERO).into(), limit)?;
        self.table.put_at(min_free_fd, FileTableSlot::File(entry));
        // Resource limits guarantee the table never exceeds `i32::MAX` entries.
        Ok((min_free_fd as RawFileDesc).try_into().unwrap())
    }

    /// Duplicates `fd` onto the exact descriptor number `new_fd`.
    pub(crate) fn dup_exact(
        &mut self,
        fd: FileDesc,
        new_fd: FileDesc,
        flags: FdFlags,
        limits: &ResourceLimits,
    ) -> Result<Option<ClosedFile>> {
        if usize::from(new_fd) >= Self::nofile_limit(limits) {
            return_errno_with_message!(Errno::EBADF, "the target FD exceeds the limit");
        }
        let entry = self.duplicate_entry(fd, flags)?;
        if matches!(
            self.table.get(new_fd.into()),
            Some(FileTableSlot::Reserved(_))
        ) {
            // Match Linux dup2/dup3 when another thread has allocated this number but
            // has not installed its file. Replacing it would corrupt that allocation.
            return_errno_with_message!(Errno::EBUSY, "the target FD is reserved");
        }
        let closed_file = self.close_file(new_fd);
        self.table.put_at(new_fd.into(), FileTableSlot::File(entry));
        Ok(closed_file)
    }

    fn duplicate_entry(&self, fd: FileDesc, flags: FdFlags) -> Result<FileTableEntry> {
        Ok(FileTableEntry::new(self.get_file(fd)?.clone(), flags))
    }

    pub(crate) fn close_file(&mut self, fd: FileDesc) -> Option<ClosedFile> {
        // Reserved descriptors are not yet visible to close or any file lookup. Only
        // their reservation may release them, so failed copyout cannot close a reused FD.
        self.table.get(fd.into())?.entry()?;
        let FileTableSlot::File(removed_entry) = self.table.remove(fd.into()).unwrap() else {
            unreachable!();
        };
        // POSIX record locks are process-associated and Linux drops them when any fd for the inode is
        // closed by that process, even if duplicated descriptors still exist.
        //
        // Reference: <https://man7.org/linux/man-pages/man2/fcntl_locking.2.html>
        Some(ClosedFile::new(
            removed_entry.file,
            self.as_range_lock_owner(),
        ))
    }

    pub(crate) fn close_files_on_exec(&mut self) -> Vec<ClosedFile> {
        self.close_files(|entry| entry.flags().contains(FdFlags::CLOEXEC))
    }

    pub(crate) fn mark_close_on_exec(&mut self, fd: FileDesc) {
        match self.table.get_mut(fd.into()) {
            Some(FileTableSlot::File(entry)) => {
                entry.set_flags(entry.flags() | FdFlags::CLOEXEC);
            }
            Some(FileTableSlot::Reserved(flags)) => *flags |= FdFlags::CLOEXEC,
            None => (),
        }
    }

    fn close_files<F>(&mut self, should_close: F) -> Vec<ClosedFile>
    where
        F: Fn(&FileTableEntry) -> bool,
    {
        let mut closed_files = Vec::new();
        let closed_fds: Vec<FileDesc> = self
            .table
            .idxes_and_items()
            .filter_map(|(idx, slot)| {
                let entry = slot.entry()?;
                if should_close(entry) {
                    // Resource limits guarantee the table never exceeds `i32::MAX` entries.
                    Some((idx as RawFileDesc).try_into().unwrap())
                } else {
                    None
                }
            })
            .collect();

        for fd in closed_fds {
            closed_files.push(self.close_file(fd).unwrap());
        }

        closed_files
    }

    pub(crate) fn get_file(&self, fd: FileDesc) -> Result<&Arc<dyn FileLike>> {
        self.table
            .get(fd.into())
            .and_then(FileTableSlot::entry)
            .map(|entry| entry.file())
            .ok_or_else(|| Error::with_message(Errno::EBADF, "the FD does not exist"))
    }

    pub(crate) fn get_entry(&self, fd: FileDesc) -> Result<&FileTableEntry> {
        self.table
            .get(fd.into())
            .and_then(FileTableSlot::entry)
            .ok_or_else(|| Error::with_message(Errno::EBADF, "the FD does not exist"))
    }

    pub(crate) fn fds_and_files(&self) -> impl Iterator<Item = (FileDesc, &'_ Arc<dyn FileLike>)> {
        // Resource limits guarantee the table never exceeds `i32::MAX` entries.
        self.table.idxes_and_items().filter_map(|(idx, slot)| {
            Some((
                (idx as RawFileDesc).try_into().unwrap(),
                slot.entry()?.file(),
            ))
        })
    }
}

/// An unpublished descriptor in its original file table.
///
/// The reservation holds no lock or thread-local borrow across file creation, blocking IO,
/// or user-memory access. An error releases precisely this slot; successful installation
/// publishes the file with its final FD flags in one file-table critical section.
#[must_use = "dropping an unused reservation releases its descriptor"]
pub(crate) struct FileDescReservation {
    file_table: RwArc<FileTable>,
    fd: Option<FileDesc>,
}

impl FileDescReservation {
    pub(crate) fn fd(&self) -> FileDesc {
        self.fd.unwrap()
    }

    pub(crate) fn install(mut self, file: Arc<dyn FileLike>) -> FileDesc {
        let fd = self.fd.take().unwrap();
        let mut locked = self.file_table.write();
        let slot = locked.table.get_mut(fd.into()).unwrap();
        let FileTableSlot::Reserved(flags) = slot else {
            unreachable!("an FD reservation must own an unpublished slot");
        };
        *slot = FileTableSlot::File(FileTableEntry::new(file, *flags));
        fd
    }
}

impl Drop for FileDescReservation {
    fn drop(&mut self) {
        if let Some(fd) = self.fd.take() {
            let mut locked = self.file_table.write();
            debug_assert!(matches!(
                locked.table.get(fd.into()),
                Some(FileTableSlot::Reserved(_))
            ));
            locked.table.remove(fd.into());
        }
    }
}

impl Drop for FileTable {
    fn drop(&mut self) {
        for (_, file) in self.fds_and_files() {
            if let Ok(inode_handle) = file.as_inode_handle_or_err() {
                inode_handle.release_range_locks(self.as_range_lock_owner());
            }
        }
    }
}

/// A file removed from a [`FileTable`] whose close cleanup is pending.
///
/// Dropping this value may block, so it must be dropped after releasing the file-table lock.
#[must_use = "close cleanup runs when this value is dropped"]
pub(crate) struct ClosedFile {
    file: Arc<dyn FileLike>,
    range_lock_owner: RangeLockOwner,
}

impl ClosedFile {
    fn new(file: Arc<dyn FileLike>, range_lock_owner: RangeLockOwner) -> Self {
        Self {
            file,
            range_lock_owner,
        }
    }
}

impl Drop for ClosedFile {
    fn drop(&mut self) {
        if let Ok(inode_handle) = self.file.as_inode_handle_or_err() {
            inode_handle.release_range_locks(self.range_lock_owner);
        }
    }
}

/// A helper trait that provides methods to operate the file table.
pub(crate) trait WithFileTable {
    /// Calls `f` with the file table.
    ///
    /// This method is lockless if the file table is not shared. Otherwise, `f` is called while
    /// holding the read lock on the file table.
    fn read_with<R>(&mut self, f: impl FnOnce(&FileTable) -> R) -> R;
}

impl WithFileTable for FileTableRefMut<'_> {
    fn read_with<R>(&mut self, f: impl FnOnce(&FileTable) -> R) -> R {
        let file_table = self.unwrap();

        if let Some(inner) = file_table.get() {
            f(inner)
        } else {
            f(&file_table.read())
        }
    }
}

/// Gets a file from a file descriptor as fast as possible.
///
/// `file_table` should be a mutable borrow of the file table contained in the `file_table` field
/// (which is a [`RefCell`]) in [`ThreadLocal`]. A mutable borrow is required because its
/// exclusivity can be useful for achieving lockless file lookups.
///
/// If the file table is not shared with another thread, this macro will be free of locks
/// ([`RwArc::read`]) and free of reference counting ([`Arc::clone`]).
///
/// If the file table is shared, the read lock is taken, the file is cloned, and then the read lock
/// is released. Cloning and releasing the lock is necessary because we cannot hold such locks when
/// operating on files, since many operations on files can block.
///
/// Note: This has to be a macro due to a limitation in the Rust borrow check implementation. Once
/// <https://github.com/rust-lang/rust/issues/58910> is fixed, we can try to convert this macro to
/// a function.
///
/// [`RefCell`]: core::cell::RefCell
/// [`ThreadLocal`]: crate::process::posix_thread::ThreadLocal
/// [`RwArc::read`]: ostd::sync::RwArc::read
macro_rules! get_file_fast {
    ($file_table:expr, $file_desc:expr) => {{
        use alloc::borrow::Cow;

        use ostd::sync::RwArc;
        use $crate::{
            fs::file::file_table::{FileDesc, FileTable},
            process::posix_thread::FileTableRefMut,
        };

        let file_table: &mut FileTableRefMut<'_> = $file_table;
        let file_table: &mut RwArc<FileTable> = file_table.unwrap();
        let file_desc: FileDesc = $file_desc;

        if let Some(inner) = file_table.get() {
            // Fast path: The file table is not shared, we can get the file in a lockless way.
            Cow::Borrowed(inner.get_file(file_desc)?)
        } else {
            // Slow path: The file table is shared, we need to hold the lock and clone the file.
            Cow::Owned(file_table.read().get_file(file_desc)?.clone())
        }
    }};
}

pub(crate) use get_file_fast;

pub(crate) struct FileTableEntry {
    file: Arc<dyn FileLike>,
    flags: AtomicU8,
}

impl FileTableEntry {
    pub(crate) fn new(file: Arc<dyn FileLike>, flags: FdFlags) -> Self {
        Self {
            file,
            flags: AtomicU8::new(flags.bits()),
        }
    }

    pub(crate) fn file(&self) -> &Arc<dyn FileLike> {
        &self.file
    }

    pub(crate) fn flags(&self) -> FdFlags {
        FdFlags::from_bits(self.flags.load(Ordering::Relaxed)).unwrap()
    }

    pub(crate) fn set_flags(&self, flags: FdFlags) {
        self.flags.store(flags.bits(), Ordering::Relaxed);
    }
}

impl Clone for FileTableEntry {
    fn clone(&self) -> Self {
        Self {
            file: self.file.clone(),
            flags: AtomicU8::new(self.flags.load(Ordering::Relaxed)),
        }
    }
}

bitflags! {
    pub(crate) struct FdFlags: u8 {
        /// Close on exec
        const CLOEXEC = 1;
    }
}
