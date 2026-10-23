// SPDX-License-Identifier: MPL-2.0

use super::TidDirOps;
use crate::{
    events::IoEvents,
    fs::{
        file::{AccessMode, PerOpenFileOps, StatusFlags, mkmod},
        procfs::template::{ProcFile, ProcFileOpsByHandle},
        vfs::inode::{FileOps, Inode},
    },
    prelude::*,
    process::{
        VmarSnapshot,
        posix_thread::{AsPosixThread, alien_access::AlienAccessMode},
        signal::{PollHandle, Pollable},
    },
    thread::Thread,
};

/// Represents the inode at `/proc/[pid]/task/[tid]/mem` (and also `/proc/[pid]/mem`).
pub(super) struct MemFileOps(TidDirOps);

impl MemFileOps {
    pub(super) fn new_inode(dir: &TidDirOps, parent: Weak<dyn Inode>) -> Arc<dyn Inode> {
        // Reference: <https://elixir.bootlin.com/linux/v6.16.5/source/fs/proc/base.c#L3347>
        ProcFile::new(Self(dir.clone()), parent, mkmod!(u+rw))
    }
}

impl ProcFileOpsByHandle for MemFileOps {
    fn owner_thread(&self) -> Option<Arc<Thread>> {
        self.0.thread()
    }

    fn open(
        &self,
        _access_mode: AccessMode,
        _status_flags: StatusFlags,
    ) -> Result<Box<dyn PerOpenFileOps>> {
        let Some(process) = self.0.process() else {
            return_errno_with_message!(Errno::ESRCH, "the process does not exist");
        };
        // Hold the process VMAR lock while checking access permissions and
        // taking the VMAR identity snapshot to prevent race conditions.
        let vmar_guard = process.lock_vmar();

        process
            .main_thread()
            .as_posix_thread()
            .unwrap()
            .check_alien_access_from(
                current_thread!().as_posix_thread().unwrap(),
                AlienAccessMode::ATTACH_WITH_FS_CREDS,
            )
            .map_err(|_| Error::with_message(Errno::EACCES, "alien access is denied"))?;

        let vmar = vmar_guard.snapshot();
        Ok(Box::new(MemFileHandle(self.0.clone(), vmar)))
    }
}

/// A file handle opened from `/proc/[pid]/task/[tid]/mem` (and also `/proc/[pid]/mem`).
struct MemFileHandle(TidDirOps, VmarSnapshot);

impl Pollable for MemFileHandle {
    fn poll(&self, mask: IoEvents, _poller: Option<&mut PollHandle>) -> IoEvents {
        let events = IoEvents::IN | IoEvents::OUT;
        events & mask
    }
}

impl FileOps for MemFileHandle {
    fn read_at(
        &self,
        offset: usize,
        writer: &mut VmWriter,
        _status_flags: StatusFlags,
    ) -> Result<usize> {
        let Some(process) = self.0.process() else {
            // The process does not exist.
            return Ok(0);
        };
        let vmar_guard = process.lock_vmar();
        if !vmar_guard.is_same_as(&self.1) {
            // The process has executed a new program.
            return Ok(0);
        }
        let Some(vmar) = vmar_guard.as_ref() else {
            // The process has exited.
            return Ok(0);
        };

        match vmar.read_alien(offset, writer) {
            Ok(bytes) => Ok(bytes),
            Err((_, 0)) => Err(Error::new(Errno::EIO)),
            Err((_, bytes)) => Ok(bytes),
        }
    }

    fn write_at(
        &self,
        offset: usize,
        reader: &mut VmReader,
        _status_flags: StatusFlags,
    ) -> Result<usize> {
        let Some(process) = self.0.process() else {
            // The process does not exist.
            return Ok(0);
        };
        let vmar_guard = process.lock_vmar();
        if !vmar_guard.is_same_as(&self.1) {
            // The process has executed a new program.
            return Ok(0);
        }
        let Some(vmar) = vmar_guard.as_ref() else {
            // The process has exited.
            return Ok(0);
        };

        match vmar.write_alien(offset, reader) {
            Ok(bytes) => Ok(bytes),
            Err((_, 0)) => Err(Error::new(Errno::EIO)),
            Err((_, bytes)) => Ok(bytes),
        }
    }
}

impl PerOpenFileOps for MemFileHandle {
    fn check_seekable(&self) -> Result<()> {
        Ok(())
    }

    fn is_offset_aware(&self) -> bool {
        true
    }
}

#[cfg(ktest)]
mod tests {
    use ostd::prelude::ktest;

    use super::*;
    use crate::{
        process::test_util,
        vm::{page_cache::VmoOptions, perms::VmPerms, vmar::VmarMapOffset},
    };

    #[ktest]
    fn an_already_open_mem_handle_cannot_write_after_its_vmar_is_fenced() {
        let (process, _task) = test_util::new_unstarted_process();
        let base = 0x400000;
        let ram = VmoOptions::new(PAGE_SIZE).alloc().unwrap();
        process
            .lock_vmar()
            .unwrap()
            .new_map(PAGE_SIZE, VmPerms::READ | VmPerms::WRITE)
            .vmo(ram)
            .offset(VmarMapOffset::FixedNoReplace(base))
            .build()
            .unwrap();
        test_util::with_registered_process(&process, |entry| {
            // The same concrete per-open handle and original VMAR snapshot
            // used by MemFileOps::open, retained across the protection change.
            let handle = MemFileHandle(TidDirOps::new(entry), process.lock_vmar().snapshot());
            assert_eq!(
                handle
                    .write_at(
                        base,
                        &mut VmReader::from(&[0x33u8][..]).to_fallible(),
                        StatusFlags::empty()
                    )
                    .unwrap(),
                1
            );
            process
                .lock_vmar()
                .unwrap()
                .prepare_external_write_fence()
                .unwrap()
                .commit();
            let error = handle
                .write_at(
                    base,
                    &mut VmReader::from(&[0x77u8][..]).to_fallible(),
                    StatusFlags::empty(),
                )
                .unwrap_err();
            assert_eq!(error.error(), Errno::EIO);
            let mut value = [0u8; 1];
            assert_eq!(
                handle
                    .read_at(
                        base,
                        &mut VmWriter::from(&mut value[..]).to_fallible(),
                        StatusFlags::empty()
                    )
                    .unwrap(),
                1
            );
            assert_eq!(value, [0x33]);
        });
    }
}
